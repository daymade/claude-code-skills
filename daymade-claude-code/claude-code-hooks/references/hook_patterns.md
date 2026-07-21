# Hook Patterns — runnable skeletons

Four battle-tested shapes plus the shlex command-position walker. Every snippet
here is distilled from a hook that has run in production. Copy, rename the
TRIGGER, keep the structure.

## Table of contents
1. [JSON event contract](#json-event-contract)
2. [Pattern A — PreToolUse block](#pattern-a--pretooluse-block)
3. [The shlex command-position walker](#the-shlex-command-position-walker)
4. [Pattern B — PreToolUse with a human-confirmation release gate](#pattern-b--pretooluse-with-a-human-confirmation-release-gate)
5. [Pattern C — SessionStart health check](#pattern-c--sessionstart-health-check)
6. [Pattern D — PostToolUse context injection](#pattern-d--posttooluse-context-injection)
7. [Registration](#registration)

---

## JSON event contract

The hook reads one JSON object on **stdin**. The fields you care about:

```jsonc
// PreToolUse / PostToolUse
{
  "tool_name": "Bash",                       // or "Agent", "WebFetch", "Edit", …
  "tool_input": { "command": "…" }           // Bash: .command; Agent: .prompt; Edit: .file_path/.new_string
}
```

Extract them defensively (never assume the shape — a parse failure should
**allow**, not crash):

```bash
INPUT=$(cat)
TOOL=$(printf '%s' "$INPUT" | python3 -c "import sys,json;print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null||echo "")
CMD=$(printf '%s' "$INPUT"  | python3 -c "import sys,json;print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null||echo "")
```

**Exit codes:** `0` = allow / proceed; `2` = block (PreToolUse) — stderr is shown
to the model; anything else = non-blocking error. SessionStart must always exit 0.

**stdin is single-use.** If you delegate logic to python, do NOT feed the script
via `python3 - <<'PY'` — that heredoc IS the script and consumes stdin, so
`json.load(sys.stdin)` reads the *script text*, fails, and (with a defensive
`except: exit 0`) the hook silently allows **everything**. Read stdin in bash
into a var, pass it to python via an **env var**:

```bash
INPUT=$(cat)
HOOK_JSON="$INPUT" python3 - <<'PY'
import os, json
data = json.loads(os.environ.get("HOOK_JSON") or "{}")
PY
```

---

## Pattern A — PreToolUse block

The workhorse: inspect a Bash command, block if it does the banned thing. This is
`proxy-guard` / `qlmanage-guard`.

```bash
#!/usr/bin/env bash
# PreToolUse hook: block <BANNED THING>.
# WHY: <one line — why prose couldn't hold this>.
# SSOT: ~/scripts/claude-hooks/<name>.sh, symlinked to ~/.claude/hooks/<name>.sh
set -euo pipefail
INPUT=$(cat)
TOOL=$(printf '%s' "$INPUT" | python3 -c "import sys,json;print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null||echo "")
[ "$TOOL" != "Bash" ] && exit 0
CMD=$(printf '%s' "$INPUT" | python3 -c "import sys,json;print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null||echo "")
[ -z "$CMD" ] && exit 0
printf '%s' "$CMD" | grep -qw 'TRIGGER' || exit 0     # fast path: token absent → allow

# precise detection — see the shlex walker below for command-position matching
HOOK_CMD="$CMD" python3 - <<'PY'
import os, sys, shlex, re
cmd = os.environ["HOOK_CMD"]
try: toks = shlex.split(cmd, posix=True, comments=True)
except ValueError: toks = cmd.split()
SEPS = {";","&&","||","|","&","(",")","{","}","|&"}
ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
at_cmd = True
for t in toks:
    if t in SEPS: at_cmd = True; continue
    if at_cmd:
        if ENV.match(t): continue          # VAR=val prefix, command is still ahead
        if t == "TRIGGER": sys.exit(2)     # command-position hit → block
        at_cmd = False                     # this token is the command; rest are args
sys.exit(0)
PY
rc=$?
if [ "$rc" = "2" ]; then
  {
    echo "BLOCKED: <BANNED THING> is not allowed here."
    echo "WHY: <the failure mode this prevents>."
    echo "USE INSTEAD: <the correct command / workflow>."
  } >&2
  exit 2
fi
exit 0
```

Note the two-stage match: a cheap `grep -qw` fast-path (allow immediately if the
token is entirely absent), then the precise shlex walker only when it's present.

---

## The shlex command-position walker

The single most important idea. It answers "does this command **execute**
TRIGGER" — not "does the string contain TRIGGER". Handles quotes, pipes, env
prefixes, and compound commands correctly.

```python
import shlex, re
SEPS = {";", "&&", "||", "|", "&", "(", ")", "{", "}", "|&"}
ENV  = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

def executes(cmd: str, target: str) -> bool:
    try: toks = shlex.split(cmd, posix=True, comments=True)   # quotes honored; # comment dropped
    except ValueError: toks = cmd.split()                     # unbalanced quotes → best effort
    at_cmd = True                                             # start of line is a command slot
    for t in toks:
        if t in SEPS: at_cmd = True; continue                # separator → next token is a command
        if at_cmd:
            if ENV.match(t): continue                        # skip VAR=val prefixes
            if t == target: return True                      # command-position match
            at_cmd = False                                   # this is the command; args follow
    return False
```

Why each piece matters:
- `shlex.split` keeps a quoted `"a|TRIGGER|b"` as ONE token → a regex arg to
  `grep`/`sed` is never mistaken for a command. This is the whole reason not to
  awk-split the raw string.
- `comments=True` drops a trailing `# TRIGGER` comment so it doesn't match.
- The `at_cmd` flag + `SEPS` means `ls | TRIGGER x` matches (after the pipe) but
  `grep TRIGGER f` does not (TRIGGER is grep's argument).
- `ENV` skip means `FOO=1 TRIGGER` matches (TRIGGER is still the command).

**What it deliberately does NOT catch:** `$(TRIGGER)` / backtick command
substitution. A raw-string regex for `$(TRIGGER` would misfire on a *quoted*
literal `'$(TRIGGER)'` (which doesn't execute). Since the real use of most
banned commands is a direct call, missing the rare substitution case beats
false-positives. If you truly need it, detect it in a context that distinguishes
single- from double-quotes — usually not worth it.

---

## Pattern B — PreToolUse with a human-confirmation release gate

For an irreversible action you want to *allow with explicit human consent*, never
a static env var (the model can set env vars). This is `git-worktree-guard` /
`git-commit-scope-guard`. Two channels the model physically cannot drive:

```bash
# ... detection decided this action needs confirmation ...
BYPASS_LOG="${HOME}/.hook-bypass.log"
stamp() { printf '%s\t%s\t%s\n' "$(date '+%F %T')" "$1" "${CMD:0:80}" >> "$BYPASS_LOG"; }

# Channel 1: native macOS dialog — the model cannot click a button.
if command -v osascript >/dev/null 2>&1; then
  DLG="display dialog \"Allow <ACTION>?\n\n$CMD\" buttons {\"拒绝\",\"允许\"} default button \"拒绝\" cancel button \"拒绝\" with icon stop giving up after 40 with title \"my-guard\""
  if osascript -e "$DLG" 2>/dev/null | grep -q '允许'; then
    stamp "dialog-allow"; exit 0
  fi
  # explicit 拒绝 / cancel / 40s timeout → fall through to hard NO (do NOT fall to tty and re-ask)
  stamp "dialog-deny"; echo "BLOCKED: denied at confirmation dialog." >&2; exit 2
fi

# Channel 2 (no GUI at all): typed YES on the user's terminal — the model cannot type there.
if [ -e /dev/tty ]; then
  printf 'Allow <ACTION>? type YES to proceed: ' > /dev/tty
  read -r ANS < /dev/tty || ANS=""
  [ "$ANS" = "YES" ] && { stamp "tty-allow"; exit 0; }
fi
stamp "blocked"; echo "BLOCKED: <ACTION> requires human confirmation." >&2; exit 2
```

Rules that make this a real gate: **refuse / cancel / timeout = hard NO**, and a
denial on one channel must **not** be overridable by a second channel. Log every
prompt and outcome — reflexive bypass is the guards' one collective failure mode,
so the audit trail is what keeps it honest. (Retired anti-pattern: a static
`GUARD_OK=1` env var — the model just adds it. Any gate the model can satisfy by
itself is not a gate.)

---

## Pattern C — SessionStart health check

The guards are their own failure domain: a corrupted hook, a dangling symlink
after reinstall, or a profile that never registered the guard all disable
protection with zero signal. This is `hook-health-check` — **silent when healthy,
always exit 0**.

```bash
#!/usr/bin/env bash
# SessionStart hook: verify the guard rails THEMSELVES are alive.
# Contract: SILENT when healthy; warn to stderr on breakage; ALWAYS exit 0
# (a broken health check must never block session start — 误杀 > 漏报).
set -uo pipefail
PROBLEMS=()

# 1. Every installed hook parses and its symlink resolves.
for h in "$HOME"/.claude/hooks/*.sh; do
  [ -e "$h" ] || { PROBLEMS+=("dangling symlink: $h"); continue; }   # -e follows the link
  bash -n "$h" 2>/dev/null || PROBLEMS+=("syntax error: $h")
done
# 2. The ACTIVE profile actually registers the Tier-0 guards.
SETTINGS="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json"
for g in proxy-guard git-worktree-guard <your-tier0-guards>; do
  grep -q "$g" "$SETTINGS" 2>/dev/null || PROBLEMS+=("not registered in $SETTINGS: $g.sh")
done

if [ "${#PROBLEMS[@]}" -gt 0 ]; then
  { printf '⚠️  hook-health-check: %d problem(s):\n' "${#PROBLEMS[@]}"
    printf '    - %s\n' "${PROBLEMS[@]}"; } >&2
fi
exit 0
```

Register once per profile under `SessionStart`. It's how the 2026-07-05 poisoning
class ("environment acting up" that was really a broken hook) becomes visible at
startup instead of after hours of confusion.

---

## Pattern D — PostToolUse context injection

PostToolUse can't undo a tool call, but it can make the **truth** appear so a
later hallucination can't stand. This is `git-commit-headcheck`: after any real
`git commit`, independently re-read HEAD and inject it.

```bash
#!/usr/bin/env bash
# PostToolUse (matcher: Bash): after a real `git commit`, inject the true HEAD.
set -euo pipefail
INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | python3 -c "import sys,json;print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null||echo "")
printf '%s' "$CMD" | grep -qE '(^|[^[:alnum:]])git[[:space:]].*commit([[:space:]]|$)' || exit 0
printf '%s' "$CMD" | grep -q -- '--dry-run' && exit 0
# honor `git -C <dir>` / a leading `cd <dir>` so the HEAD read happens in the right repo
HEAD=$(git rev-parse --short HEAD 2>/dev/null || echo "?")
SUBJ=$(git log -1 --format='%s' 2>/dev/null || echo "?")
STAGED=$(git diff --cached --name-only 2>/dev/null | wc -l | tr -d ' ')
echo "[headcheck] real HEAD = $HEAD $SUBJ | staged remaining = $STAGED" >&2
exit 0
```

The value is that the model **cannot forget a check that runs automatically**.
Injected truth beats "I think the commit worked."

---

## Registration

`settings.json` groups hooks by event, then by `matcher` (the tool name):

```jsonc
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash", "hooks": [
        { "type": "command", "command": "~/.claude/hooks/my-guard.sh" }
      ]},
      { "matcher": "Agent", "hooks": [ /* scope guards on subagent prompts */ ] }
    ],
    "PostToolUse":  [ { "matcher": "Bash", "hooks": [ { "type": "command", "command": "~/.claude/hooks/headcheck.sh" } ] } ],
    "SessionStart": [ { "hooks": [ { "type": "command", "command": "~/.claude/hooks/hook-health-check.sh" } ] } ]
  }
}
```

Add to an existing `matcher: "Bash"` entry's `hooks` array (don't create a second
Bash entry). Then **converge every profile** — a guard registered only in the
main profile leaves the others unprotected. Editing settings.json programmatically
with python (read → append if absent → write) is safer than hand-editing JSON.
