#!/usr/bin/env python3
"""Observe Ghostty descendants on a calendar; save complete manifests only on change.

Runtime reads one bounded process graph, selected process cwd and one small prior
manifest/profile map. No history index, transcript, GUI, or restore API is used.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone

import ghostty_session as gs
from ghostty_storage import atomic_bytes, atomic_manifest, read_manifest, snapshot_lock

LABEL = 'io.ghostty.session-snapshot'
AUTO_KIND = 'automatic-recovery-snapshot'
DEADLINE_SECONDS = 15
MAX_PROCESS_BYTES = 8 << 20
MAX_PROCESSES = 25000
MAX_SESSIONS = 256
MAX_LOG_BYTES = 1 << 20
DEFAULT_EVERY_MINUTES = 10


def home_state():
    return Path.home() / '.ghostty-session'


def owned_interpreter(state):
    return Path(state) / 'watcher' / 'venv' / 'bin' / 'python'


def owned_script(state):
    return Path(state) / 'watcher' / 'scripts' / 'ghostty_watch.py'


def run_bounded(command, deadline, counters):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ValueError('observation deadline expired')
    counters['commands'] += 1
    result = subprocess.run(command, capture_output=True, text=True, timeout=remaining)
    if result.returncode:
        raise ValueError(f'{Path(command[0]).name} observation failed (exit {result.returncode})')
    if len(result.stdout.encode()) > MAX_PROCESS_BYTES:
        raise ValueError('process observation exceeds byte limit')
    return result.stdout


def parse_processes(text):
    procs = {}
    for line in text.splitlines():
        fields = line.split(None, 3)
        if len(fields) != 4:
            raise ValueError('incomplete ps process graph')
        pid, parent = int(fields[0]), int(fields[1])
        if pid in procs:
            raise ValueError('duplicate pid in ps process graph')
        procs[pid] = {'pid': pid, 'ppid': parent, 'tty': fields[2], 'cmdline': fields[3]}
        if len(procs) > MAX_PROCESSES:
            raise ValueError('process graph exceeds process limit')
    if not procs:
        raise ValueError('empty ps process graph')
    return procs


def executable_tokens(command):
    try:
        tokens = shlex.split(command)
    except ValueError as error:
        raise ValueError('unparseable process command; coverage unknown') from error
    return tokens


# Static option arity from the installed CLIs' --help; never query help per round.
CLAUDE_REQUIRED = set("--agent --agents --append-system-prompt --autocompact --debug-file --effort --environment --fallback-model --input-format --json-schema --max-budget-usd --model -n --name --output-format --permission-mode --permission-prompts --plugin-dir --plugin-url --remote-control-session-name-prefix --session-id --setting-sources --settings --system-prompt --system-prompt-snapshot".split())
CLAUDE_OPTIONAL = set("-d --debug --cloud --from-pr --prompt-suggestions --remote-control -r --resume --teleport -w --worktree".split())
CLAUDE_VARIADIC = set("--add-dir --allowedTools --allowed-tools --betas --disallowedTools --disallowed-tools --file --mcp-config --tools".split())
CLAUDE_BOOLEAN = set("--allow-dangerously-skip-permissions --ax-screen-reader --bg --background --bare --brief --chrome -c --continue --dangerously-skip-permissions --desktop --disable-slash-commands --exclude-dynamic-system-prompt-sections --fork-session --forward-subagent-text -h --help --ide --include-hook-events --include-partial-messages --no-chrome --no-session-persistence -p --print --replay-user-messages --restricted --safe-mode --strict-mcp-config --tmux --verbose -v --version".split())
CLAUDE_OTHER_CONTEXT = set("-p --print --bg --background --desktop --cloud --environment -h --help -v --version".split())
CODEX_REQUIRED = set("-c --config --enable --disable --remote --remote-auth-token-env -m --model --local-provider -p --profile -s --sandbox -C --cd --add-dir -a --ask-for-approval".split())
CODEX_VARIADIC = set("-i --image".split())
CODEX_BOOLEAN = set("--strict-config --oss --approve-for-me --dangerously-bypass-approvals-and-sandbox --dangerously-bypass-hook-trust --worktree --search --no-alt-screen --no-daemon --last --all --include-non-interactive --full-auto -h --help -V --version".split())
CODEX_OTHER_COMMANDS = set("agents exec e review login logout mcp plugin app-server remote-control app completion update doctor sandbox debug apply queue archive delete migrate-rollouts unarchive cloud exec-server features help mcp-server daemon".split())


def cli_identity(row):
    raw = row["cmdline"].split(None, 2)
    if not raw:
        return None
    first = Path(raw[0]).name
    if first not in ("codex", "claude", "node", "nodejs"):
        return None
    if first in ("node", "nodejs") and (len(raw) < 2 or Path(raw[1]).name not in ("codex", "claude")):
        return None
    tokens = executable_tokens(row["cmdline"])
    index = 1 if first in ('node', 'nodejs') else 0
    tool = Path(tokens[index]).name
    required = CLAUDE_REQUIRED if tool == 'claude' else CODEX_REQUIRED
    optional = CLAUDE_OPTIONAL if tool == 'claude' else set()
    variadic = CLAUDE_VARIADIC if tool == 'claude' else CODEX_VARIADIC
    boolean = CLAUDE_BOOLEAN if tool == 'claude' else CODEX_BOOLEAN
    tail = tokens[index + 1:]
    ids, forked, ambiguous, command = set(), False, False, None
    cursor = 0
    positional_only = False
    while cursor < len(tail):
        token = tail[cursor]
        cursor += 1
        if token == '--':
            positional_only = True
            continue
        if not positional_only and token.startswith('-') and token != '-':
            # Required/optional short-option values bind the rest of a cluster.
            cluster = token[1:] if not token.startswith('--') else None
            pending = [token.split('=', 1)[0]] if cluster is None else ['-' + cluster[0]]
            attached = token.split('=', 1)[1] if cluster is None and '=' in token else None
            if cluster is not None:
                cluster = cluster[1:]
            while pending:
                option = pending.pop(0)
                if tool == 'claude' and option in CLAUDE_OTHER_CONTEXT:
                    return None
                if tool == 'codex' and option in ('-h', '--help', '-V', '--version'):
                    return None
                if option in boolean:
                    if option == '--fork-session':
                        forked = True
                    if cluster:
                        pending.append('-' + cluster[0])
                        cluster = cluster[1:]
                    continue
                if option not in required | optional | variadic:
                    ambiguous = True
                    break  # unknown arity: later words cannot establish identity
                value = attached
                if cluster:
                    value, cluster = cluster, ''
                if value is None:
                    if cursor < len(tail) and (option in required or not tail[cursor].startswith('-')):
                        value = tail[cursor]
                        cursor += 1
                    elif option in required or option in variadic:
                        ambiguous = True
                if option in variadic:
                    while cursor < len(tail) and not tail[cursor].startswith('-'):
                        cursor += 1
                if tool == 'claude' and option in ('-r', '--resume', '--session-id'):
                    if value and gs.UUID_RE.fullmatch(value):
                        ids.add(value)
                    else:
                        ambiguous = True
            if ambiguous:
                break
            continue
        if tool == 'codex':
            if command is None:
                command = token
                if command in CODEX_OTHER_COMMANDS:
                    return None
                if command == 'fork':
                    forked = True
            elif command == 'resume' and not ids:
                if gs.UUID_RE.fullmatch(token):
                    ids.add(token)
                else:
                    ambiguous = True
            elif command == 'resume' and ids:
                ambiguous = True  # trailing positional prompt is not replay-safe
        else:
            # ps loses argv quoting: prompt-bearing Claude invocations are
            # unresolved even when an earlier selector looked valid.
            ambiguous = True
            break
    # Codex prompt text beginning "resume <UUID>" is indistinguishable from its
    # subcommand in flattened ps output; this interface relies on that argv boundary.
    sid = next(iter(ids)) if len(ids) == 1 and not forked and not ambiguous else None
    return tool, sid, tokens, index


def parse_cwds(text, pids):
    paths = {pid: [] for pid in pids}
    current = None
    for line in text.splitlines():
        if line.startswith('p'):
            current = int(line[1:])
        elif line.startswith('n') and current in paths:
            paths[current].append(line[1:])
    if any(len(values) != 1 or not values[0].startswith('/') for values in paths.values()):
        raise ValueError('process cwd unavailable or ambiguous; coverage unknown')
    return {pid: values[0] for pid, values in paths.items()}


def observe(deadline=None):
    deadline = deadline or time.monotonic() + DEADLINE_SECONDS
    counters = {'ps_calls': 1, 'lsof_calls': 0, 'commands': 0, 'history_body_reads': 0}
    text = run_bounded(['/bin/ps', '-ww', '-axo', 'pid=,ppid=,tty=,command='], deadline, counters)
    procs = parse_processes(text)
    roots = {pid for pid, row in procs.items()
             if Path(row['cmdline'].split(None, 1)[0]).name.lower() == 'ghostty'}
    candidates, seen = [], set()
    for pid, row in procs.items():
        if time.monotonic() >= deadline:
            raise ValueError('observation deadline expired during process selection')
        current, chain = row['ppid'], set()
        while current in procs and current not in roots and current not in chain:
            chain.add(current)
            current = procs[current]['ppid']
        if current not in roots:
            continue
        identity = cli_identity(row)
        if identity is None:
            continue
        tool, sid, tokens, index = identity
        if not row['tty'].startswith(('ttys', 'pts/')):
            continue
        parent = procs.get(row['ppid'])
        wrapper = cli_identity(parent) if parent else None
        if (wrapper and wrapper[0] == tool and wrapper[3] == 1
                and parent['tty'] == row['tty'] and (sid is None or sid == wrapper[1])):
            continue  # native vendor child of the same Node TUI
        if sid is not None and (tool, sid) in seen:
            continue
        if sid is not None:
            seen.add((tool, sid))
        candidates.append((row, tool, sid))
        if len(candidates) > MAX_SESSIONS:
            raise ValueError('Ghostty session count exceeds observation limit')
    selected, unresolved = [], []
    if candidates:
        pids = [row['pid'] for row, _, _ in candidates]
        counters['lsof_calls'] = 1
        output = run_bounded(['/usr/sbin/lsof', '-a', '-p', ','.join(map(str, pids)),
                              '-d', 'cwd', '-Fpn'], deadline, counters)
        cwds = parse_cwds(output, pids)
        for row, tool, sid in candidates:
            entry = {'tool': tool, 'cwd': cwds[row['pid']], 'cmdline': row['cmdline'],
                     'profile': gs._detect_profile(row['cmdline']), 'tty': row['tty']}
            if sid is None:
                entry.update(pid=row['pid'], reason='CLI UUID absent from argv')
                unresolved.append(entry)
            else:
                entry['sid'] = sid
                selected.append(entry)
    return {'sessions': selected, 'unresolved': unresolved, 'ghostty_processes': len(roots), 'counters': counters}


def profile_mapping(state):
    path = Path(state) / 'profile-env.json'
    if not path.exists():
        return {}
    with path.open('rb') as handle:
        raw = handle.read(65537)
    if len(raw) > 65536:
        raise ValueError('profile map exceeds byte limit')
    mapping = json.loads(raw)
    if not isinstance(mapping, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in mapping.items()):
        raise ValueError('profile environment map must contain string keys and values')
    return mapping


def canonical(sessions, mapping):
    identities = set()
    rows = []
    for row in sessions:
        if not isinstance(row, dict):
            raise ValueError('snapshot session must be an object')
        if row.get('tool') not in ('codex', 'claude') or not gs.UUID_RE.fullmatch(str(row.get('sid', ''))):
            raise ValueError('invalid snapshot session identity')
        identity = (row['tool'], row['sid'])
        if identity in identities:
            raise ValueError('duplicate snapshot identity')
        identities.add(identity)
        command = gs.restore_cmd(row, env_mapping=mapping)
        rows.append({'tool': row['tool'], 'sid': row['sid'], 'cwd': row.get('cwd') or '',
                     'profile': row.get('profile') or 'direct', 'restore_command': command})
    return sorted(rows, key=lambda row: (row['tool'], row['sid']))


def canonical_unresolved(rows):
    values = []
    for row in rows:
        identity = cli_identity(row)
        if identity is None:
            raise ValueError('invalid unresolved CLI record')
        tool, _, tokens, index = identity
        values.append({'tool': tool, 'cwd': row.get('cwd') or '',
                       'profile': row.get('profile') or 'direct', 'argv': tokens[index + 1:]})
    return sorted(values, key=lambda row: json.dumps(row, sort_keys=True))


def cycle(state, observer=observe):
    state = Path(state)
    started = time.monotonic()
    with snapshot_lock(state):
        result = observer(started + DEADLINE_SECONDS)
        if result['ghostty_processes'] == 0:
            return {'state': 'stand-down', 'sessions': 0, 'duration_seconds': time.monotonic() - started,
                    'counters': result['counters']}
        if not result['sessions']:
            raise ValueError('coverage unknown: no identified Ghostty sessions; prior backup retained')
        mapping = profile_mapping(state)
        latest = state / 'snapshots' / 'latest.json'
        previous = None
        old_rows, old_unknown = [], []
        if latest.exists():
            previous = read_manifest(latest)
            old_rows = canonical(previous['sessions'], mapping)
            old_unknown = canonical_unresolved(previous.get('unresolved', []))
            if previous.get('kind') == AUTO_KIND and (
                previous.get('canonical_inventory') != old_rows
                or previous.get('canonical_unresolved', []) != old_unknown
            ):
                raise ValueError('automatic snapshot canonical inventory is corrupt')
        elif latest.parent.is_dir() and any(latest.parent.glob('snapshot-*.json')):
            raise ValueError('latest snapshot missing while archives remain; choose a known archive explicitly')
        observed = list(result['sessions'])
        retained = 0
        if result['unresolved'] and previous:
            known = {(row['tool'], row['sid']) for row in observed}
            for row in previous['sessions']:
                if (row['tool'], row['sid']) not in known:
                    observed.append(dict(row, membership='retained-unverified'))
                    retained += 1
        rows = canonical(observed, mapping)
        unknown = canonical_unresolved(result['unresolved'])
        summary = {'sessions': len(rows), 'unresolved': len(unknown), 'retained_unverified': retained,
                   'duration_seconds': time.monotonic() - started, 'counters': result['counters']}
        if previous is not None and previous.get('kind') == AUTO_KIND and rows == old_rows and unknown == old_unknown:
            return dict(summary, state='unchanged')
        if time.monotonic() - started >= DEADLINE_SECONDS:
            raise ValueError('observation deadline expired before snapshot publish')
        sessions = []
        by_id = {(row['tool'], row['sid']): row for row in rows}
        for row in observed:
            entry = dict(row)
            entry.update(status='unknown', error='not-observed', last_interaction=None, age_hours=None,
                         restore_command=by_id[(row['tool'], row['sid'])]['restore_command'])
            sessions.append(entry)
        doc = {'kind': AUTO_KIND, 'captured_at': datetime.now(timezone.utc).isoformat(),
               'active_hours_threshold': gs.ACTIVE_HOURS, 'liveness': 'not-observed',
               'coverage': 'partial' if unknown else 'identified Ghostty descendants',
               'unresolved': result['unresolved'], 'retained_unverified': retained,
               'canonical_inventory': rows, 'canonical_unresolved': unknown, 'sessions': sessions}
        archive = latest.parent / ('snapshot-auto-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f') + '-' + uuid.uuid4().hex[:8] + '.json')
        atomic_manifest(archive, doc, replace=False)
        atomic_manifest(latest, doc)
        return dict(summary, state='changed', snapshot=str(archive))


def calendar_definition(state, every_minutes=DEFAULT_EVERY_MINUTES):
    state = Path(state).expanduser().absolute()
    return {'Label': LABEL,
            'ProgramArguments': [str(owned_interpreter(state)), str(owned_script(state)), 'run', '--state-dir', str(state)],
            'RunAtLoad': True,
            'StartCalendarInterval': [{'Minute': minute} for minute in range(0, 60, every_minutes)],
            'StandardOutPath': str(state / 'watcher' / 'out.log'),
            'StandardErrorPath': str(state / 'watcher' / 'err.log'),
            'Nice': 10, 'ThrottleInterval': 30,
            'EnvironmentVariables': {'PATH': '/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin'}}


def calendar_minutes(definition):
    """Recognize only the minute-only calendar contract this installer owns."""
    entries = definition.get('StartCalendarInterval') if isinstance(definition, dict) else None
    entries = [entries] if isinstance(entries, dict) else entries
    if not isinstance(entries, list) or not entries:
        return None
    minutes = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {'Minute'}:
            return None
        minute = entry['Minute']
        if type(minute) is not int or not 0 <= minute < 60 or minute in minutes:
            return None
        minutes.append(minute)
    return sorted(minutes)


def active_calendar_minutes(text):
    """Read calendarinterval descriptors only; unfamiliar launchctl text is unknown."""
    lines = text.splitlines()
    def block(start):
        depth = 0
        for end in range(start, len(lines)):
            depth += lines[end].count('{') - lines[end].count('}')
            if depth == 0:
                return lines[start + 1:end], end
            if depth < 0:
                break
        return None
    starts = [i for i, line in enumerate(lines) if re.fullmatch(r'\s*event triggers = \{\s*', line)]
    if len(starts) != 1 or block(starts[0]) is None:
        return None
    body, _ = block(starts[0])
    # Restrict subsequent block parsing to this event-triggers section.
    lines, entries, cursor = body, [], 0
    while cursor < len(lines):
        if not lines[cursor].strip():
            cursor += 1
            continue
        if not re.fullmatch(r'\s*[^{}]+ => \{\s*', lines[cursor]):
            return None
        event = block(cursor)
        if event is None:
            return None
        event_lines, end = event
        cursor = end + 1
        streams = [m[1] for line in event_lines if (m := re.fullmatch(r'\s*stream = (\S+)\s*', line))]
        if len(streams) != 1:
            return None
        if streams[0] != 'com.apple.launchd.calendarinterval':
            continue
        descriptor = '\n'.join(event_lines)
        match = re.search(r'(?m)^\s*descriptor = \{\s*\n([^{}]*)^\s*\}\s*$', descriptor)
        if not match:
            return None
        values = [line.strip() for line in match[1].splitlines() if line.strip()]
        if len(values) != 1 or not (value := re.fullmatch(r'"Minute" => (\d+)', values[0])):
            return None
        entries.append({'Minute': int(value[1])})
    return calendar_minutes({'StartCalendarInterval': entries})


def schedule_readback(target, active_text):
    try:
        disk = calendar_minutes(plistlib.loads(Path(target).read_bytes()))
    except (OSError, ValueError):
        disk = None
    active = active_calendar_minutes(active_text)
    return {'disk_minutes': disk if disk is not None else 'unknown',
            'active_minutes': active if active is not None else 'unknown',
            'match': disk == active if disk is not None and active is not None else 'unknown'}


def launch_target():
    return Path.home() / 'Library' / 'LaunchAgents' / (LABEL + '.plist')


def system_run(command, check=True):
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    if check and result.returncode:
        raise ValueError(f'{Path(command[0]).name} failed: {result.stderr.strip()}')
    return result


def install(state, every_minutes=DEFAULT_EVERY_MINUTES, apply=False):
    state = Path(state).expanduser().absolute()
    definition = calendar_definition(state, every_minutes)
    target = launch_target()
    if target.exists():
        old = plistlib.loads(target.read_bytes())
        if old.get('Label') != LABEL or old.get('ProgramArguments') != definition['ProgramArguments']:
            raise ValueError('existing LaunchAgent is not this managed observer; no overwrite')
    if not apply:
        return {'target': str(target), 'definition': definition, 'apply': False}
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    watcher = state / 'watcher'
    watcher.mkdir(exist_ok=True, mode=0o700)
    interpreter = owned_interpreter(state)
    if not interpreter.exists():
        uv = shutil.which('uv')
        if uv is None:
            raise ValueError('uv required for the one-time owned Python 3.12 environment')
        system_run([uv, 'venv', '--python', '3.12', str(watcher / 'venv')])
    system_run([str(interpreter), '-c', 'import fcntl, json, plistlib; print("owned runtime ready")'])
    source = Path(__file__).resolve().parent
    for filename in ('ghostty_watch.py', 'ghostty_storage.py', 'ghostty_session.py'):
        data = (source / filename).read_bytes()
        installed = watcher / 'scripts' / filename
        if not installed.exists() or installed.read_bytes() != data:
            atomic_bytes(installed, data)
        if installed.read_bytes() != data:
            raise ValueError('installed watcher source readback mismatch')
    for filename in ('out.log', 'err.log'):
        log = watcher / filename
        if not log.exists():
            atomic_bytes(log, b'', replace=False)
    definition_bytes = plistlib.dumps(definition)
    pending = watcher / 'launchagent.plist'
    if not pending.exists() or pending.read_bytes() != definition_bytes:
        atomic_bytes(pending, definition_bytes)
    system_run(['/usr/bin/plutil', '-lint', str(pending)])
    service = f'gui/{os.getuid()}/{LABEL}'
    loaded = system_run(['/bin/launchctl', 'print', service], check=False)
    same = target.exists() and target.read_bytes() == definition_bytes
    expected_minutes = calendar_minutes(definition)
    active_matches = loaded.returncode == 0 and active_calendar_minutes(loaded.stdout) == expected_minutes
    reload_needed = not same or not active_matches
    if loaded.returncode == 0 and reload_needed:
        system_run(['/bin/launchctl', 'bootout', service])
    if not same:
        atomic_bytes(target, definition_bytes)
    system_run(['/bin/launchctl', 'enable', f'user/{os.getuid()}/{LABEL}'])
    if loaded.returncode != 0 or reload_needed:
        system_run(['/bin/launchctl', 'bootstrap', f'gui/{os.getuid()}', str(target)])
    active = system_run(['/bin/launchctl', 'print', service]).stdout
    if str(interpreter) not in active or str(owned_script(state)) not in active:
        raise ValueError('launchd runtime readback mismatch')
    if plistlib.loads(target.read_bytes()) != definition:
        raise ValueError('LaunchAgent disk readback mismatch')
    schedule = schedule_readback(target, active)
    if schedule['active_minutes'] == 'unknown':
        raise ValueError('active launchd calendar schedule unknown; install not verified')
    if schedule['active_minutes'] != expected_minutes or schedule['match'] is not True:
        raise ValueError('active launchd calendar does not match disk/requested minutes')
    return {'installed': True, 'label': LABEL, 'runtime': str(interpreter), 'target': str(target), 'schedule': schedule}


def stop():
    system_run(['/bin/launchctl', 'disable', f'user/{os.getuid()}/{LABEL}'])
    service = f'gui/{os.getuid()}/{LABEL}'
    if system_run(['/bin/launchctl', 'print', service], check=False).returncode == 0:
        system_run(['/bin/launchctl', 'bootout', service])
    if system_run(['/bin/launchctl', 'print', service], check=False).returncode == 0:
        raise ValueError('observer is still loaded after stop')
    disabled = system_run(['/bin/launchctl', 'print-disabled', f'user/{os.getuid()}']).stdout
    if not re.search(r'\"' + re.escape(LABEL) + r'\"\s*=>\s*true', disabled):
        raise ValueError('persistent disabled state could not be verified')
    return {'stopped': True, 'disabled_across_login': True, 'snapshots_retained': True}


def status(state):
    target = launch_target()
    active = system_run(['/bin/launchctl', 'print', f'gui/{os.getuid()}/{LABEL}'], check=False)
    result = {'label': LABEL, 'registered': target.exists(), 'loaded': active.returncode == 0,
              'runtime': str(owned_interpreter(state)), 'runtime_exists': owned_interpreter(state).exists()}
    if active.returncode == 0:
        for key in ('last exit code', 'runs', 'state', 'pid'):
            match = re.search(r'^\s*' + re.escape(key) + r'\s*=\s*(.+)$', active.stdout, re.MULTILINE)
            result[key] = match[1] if match else 'unknown'
    result['schedule'] = schedule_readback(target, active.stdout if active.returncode == 0 else '')
    latest = Path(state) / 'snapshots' / 'latest.json'
    if latest.exists():
        doc = read_manifest(latest)
        result['latest_snapshot'] = {'captured_at': doc.get('captured_at'), 'kind': doc.get('kind', 'manual'),
                                     'recorded_sessions': len(doc['sessions']),
                                     'identified_at_capture': len(doc['sessions']) - doc.get('retained_unverified', 0),
                                     'coverage': doc.get('coverage', 'manual'),
                                     'unresolved': len(doc.get('unresolved', [])), 'retained_unverified': doc.get('retained_unverified', 0)}
    result['meaning'] = 'snapshot time is last change, not last successful observation; inspect launchd exit state'
    return result


def report_error(state, message):
    path = Path(state) / 'watcher' / 'err.log'
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    line = 'Ghostty snapshot observation unknown: ' + str(message)[:2048]
    fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(fd, 0o600)
        if os.fstat(fd).st_size > MAX_LOG_BYTES:
            os.ftruncate(fd, 0)  # failure telemetry only; never touch snapshots
        same_stderr = (os.fstat(2).st_dev, os.fstat(2).st_ino) == (os.fstat(fd).st_dev, os.fstat(fd).st_ino)
        if same_stderr:
            os.lseek(2, 0, os.SEEK_END)
        else:
            os.write(fd, (line + '\n').encode())
        print(line, file=sys.stderr, flush=True)
    finally:
        os.close(fd)


def supervise(state):
    interpreter = owned_interpreter(state)
    script = owned_script(state)
    if not interpreter.is_file() or not script.is_file():
        raise ValueError('owned watcher runtime missing; run install --apply')
    command = [str(interpreter), str(script), '_cycle', '--state-dir', str(state)]
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                               text=True, start_new_session=True)
    try:
        _, error = process.communicate(timeout=DEADLINE_SECONDS)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise ValueError('supervisor deadline expired; prior backup retained')
    if process.returncode:
        raise ValueError(error.strip() or f'observation worker exit {process.returncode}')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('install', 'status', 'stop', 'run', 'probe', '_cycle'):
        item = sub.add_parser(command)
        item.add_argument('--state-dir', type=gs.nonempty, default=str(home_state()))
        if command == 'install':
            item.add_argument('--apply', action='store_true')
            item.add_argument('--every-minutes', type=int, choices=(1, 2, 3, 5, 10, 15, 20, 30, 60), default=DEFAULT_EVERY_MINUTES)
    args = parser.parse_args(argv)
    state = Path(args.state_dir).expanduser().absolute()
    try:
        if args.command == 'run':
            return supervise(state)
        if args.command == '_cycle':
            cycle(state)
            return 0  # no stdout or routine writes on successful unchanged rounds
        if args.command == 'probe':
            started = time.monotonic()
            result = observe()
            result['duration_seconds'] = time.monotonic() - started
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1 if result['unresolved'] or not result['sessions'] else 0
        result = (install(state, args.every_minutes, args.apply) if args.command == 'install'
                  else stop() if args.command == 'stop' else status(state))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        if args.command == 'run':
            report_error(state, error)
        else:
            print('ERROR: ' + str(error), file=sys.stderr)
        return 1 if args.command in ('run', '_cycle', 'probe') else 2


if __name__ == '__main__':
    raise SystemExit(main())
