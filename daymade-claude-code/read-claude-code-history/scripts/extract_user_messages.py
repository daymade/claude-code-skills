#!/usr/bin/env python3
"""Extract verbatim user messages ("what the user actually said") from session history.

Covers every active Claude config home plus registered long-term archives (same
source discovery as analyze_sessions.py), de-duplicates across copies, and
separates genuine user prose from the five contamination classes documented in
references/session_file_format.md ("A user-role record is not necessarily
user-authored text"):

  1. command envelopes (XML wrappers and bare `/cmd` strings) -> appendix
  2. hook/loop-injected boilerplate — detected generically by frequency
     (identical text, >= --min-dup occurrences, >= 400 normalized chars), both
     standalone records and the tail-appended shape -> stripped / appendix
  3. `[Image #N]` placeholders -> stripped (count kept)
  4. whole-document pastes (>= 2000 normalized chars AND (>= 60% ASCII OR
     >= 10 non-blank lines)) -> appendix. The multi-line branch catches CJK
     meeting transcripts / multi-turn dialog / agent re-injections that stay
     below the ASCII bar, while coherent voice dictation (few long paragraphs)
     is preserved. Speaker-label counting was tried and rejected: user prose
     that quotes people racks up more "name:" labels than a real transcript.
  5. agent-voiced re-injection -> dropped when the text matches (exact or
     contained-in) an assistant text that exists EARLIER than the record

Mid-work input typed while the assistant was busy is recovered from
`attachment.queued_command` records (origin.kind == "human") and de-duplicated
against later-delivered user records (same normalized text within 120s).

Usage:
  extract_user_messages.py [OUT_BASE] [--days 7] [--group-by project|day]
      [--min-dup 5] [--home PATH ...]

OUT_BASE defaults to ~/.claude-flow-viewer/user-words — persistent; avoid /tmp
(the OS purges it; 2026-08-07 战例: 产物写 /tmp 次日被清). Writes OUT_BASE.html
and OUT_BASE.md. Dates come from internal record
timestamps (UTC+8 rendering); file mtime is only a coarse prefilter.
"""

import argparse
import hashlib
import html as htmllib
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Multi-home discovery lives in the bundled `_core` package (see analyze_sessions.py).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _core.sources import discover_claude_sources  # noqa: E402
from _core.text import iter_jsonl  # noqa: E402

CST = timezone(timedelta(hours=8))

# Records that are reliably not user prose, by structure alone.
NOISE_PREFIX = (
    '<task-notification',
    '[Request interrupted by user',
    'Caveat:',
    'Stop hook feedback:',
    'Continue from where you left off',
    '<local-command-',
    '[Your previous response had no visible output',
    'This session is being continued from a previous conversation',
    'Another Claude session sent a message:',
)
CMD_RE = re.compile(r'<command-name>([^<]+)</command-name>\s*(?:<command-args>(.*?)</command-args>)?', re.S)
BARE_CMD_RE = re.compile(r'^(/[a-z][\w:-]*)\s*(.*)$', re.S)
IMG_TOKEN_RE = re.compile(r'\[Image #\d+\]\s*')
PATHISH_PREFIX = ('//', '/Users', '/tmp', '/var', '/home', '/opt')

FILLER = {x.lower() for x in (
    '继续', '继续吧', '你直接继续', 'ok', 'okay', 'yes', '好', '好的', '好嘞', '嗯', '嗯嗯',
    '对', '是的', '行', '可以', '做吧', 'done', 'check', 'fix', 'go', 'hi', 'hello', '收到',
)}

BOILER_MIN_CHARS = 400      # injected boilerplate is long; short repeats are just filler
PASTE_MIN_CHARS = 2000      # whole-document paste splitter …
PASTE_ASCII_RATIO = 0.60    # … length AND mostly-ASCII; long voice dictation stays below the ASCII bar
PASTE_MULTI_LINE_MIN = 10   # … OR long text spanning >= N non-blank lines = transcript/dialog/paste
AGENT_EXACT_MIN = 30        # below this a coincidental same-text match is plausible
AGENT_CONTAINS_MIN = 60
DELIVERED_WINDOW_SEC = 120


@dataclass
class Entry:
    ts: datetime
    project: str
    text: str
    session_id: str = ""
    images: int = 0
    filler: bool = False


@dataclass
class Extraction:
    entries: list = field(default_factory=list)      # list[Entry]
    commands: list = field(default_factory=list)     # list[Entry]
    injected: list = field(default_factory=list)     # list[Entry] boilerplate
    pastes: list = field(default_factory=list)       # list[Entry]
    subtracted: int = 0                              # agent-voiced re-injections dropped


def normalize_text(s: str) -> str:
    return re.sub(r'\s+', '', s)


def _record_ts(data: dict):
    raw = data.get('timestamp') or ''
    try:
        return datetime.fromisoformat(raw.replace('Z', '+00:00'))
    except ValueError:
        return None


def _iter_session_files(sources, cutoff: datetime):
    """Yield (source_label, Path) for session JSONL files. mtime is only a coarse
    prefilter with a 2-day grace band; the real window is applied per record."""
    grace = cutoff.timestamp() - 2 * 86400
    for src in sources:
        projects = src.home / 'projects'
        if not projects.is_dir():
            continue
        for f in projects.glob('*/*.jsonl'):
            if f.name.startswith('agent-'):
                continue
            try:
                if f.stat().st_mtime < grace:
                    continue
            except OSError:
                continue
            yield src.label, f


def _assistant_texts(record: dict):
    content = (record.get('message') or {}).get('content') if isinstance(record.get('message'), dict) else None
    if record.get('type') != 'assistant' or not isinstance(content, list):
        return
    for block in content:
        if isinstance(block, dict) and block.get('type') == 'text':
            t = normalize_text(block.get('text', ''))
            if t:
                yield t


def build_agent_corpus(sources, cutoff: datetime):
    """Normalized assistant texts: exact-hash -> earliest ts, plus a long-text list
    for containment checks. Used to subtract agent-voiced re-injections."""
    exact = {}
    long_texts = []
    for _label, f in _iter_session_files(sources, cutoff):
        try:
            records = iter_jsonl(f)
            for record in records:
                ts = _record_ts(record)
                if ts is None:
                    continue
                for t in _assistant_texts(record):
                    if len(t) >= AGENT_EXACT_MIN:
                        h = hashlib.md5(t.encode()).digest()
                        if h not in exact or ts < exact[h]:
                            exact[h] = ts
                        if len(t) >= AGENT_CONTAINS_MIN:
                            long_texts.append((ts, t))
        except Exception:
            continue
    giant = '\x00'.join(t for _, t in long_texts)
    return exact, long_texts, giant


def _user_candidate_text(record: dict):
    """Return (text, n_images) for a user record, or None if it is not prose-shaped."""
    content = (record.get('message') or {}).get('content') if isinstance(record.get('message'), dict) else None
    if isinstance(content, str):
        return content, 0
    if isinstance(content, list):
        if any(isinstance(b, dict) and b.get('type') == 'tool_result' for b in content):
            return None
        parts, n_img = [], 0
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get('type') == 'text':
                parts.append(b.get('text', ''))
            elif b.get('type') == 'image':
                n_img += 1
        return '\n'.join(p for p in parts if p), n_img
    return None


def _command_label(text: str):
    """If the text is a slash-command invocation, return its '/name args' label."""
    if text.startswith('<command-message>') or text.startswith('<command-name>'):
        m = CMD_RE.search(text)
        if m:
            return f"{m.group(1)} {(m.group(2) or '').strip()}".strip()
        return text[:60]
    m = BARE_CMD_RE.match(text)
    if m and not text.startswith(PATHISH_PREFIX):
        return f"{m.group(1)} {m.group(2).strip()}".strip()
    return None


def extract(sources, cutoff: datetime, min_dup: int = 5) -> Extraction:
    result = Extraction()
    seen_uuid = set()
    raw_user = []    # (ts, project, session_id, text, n_img)
    raw_queued = []  # (ts, project, session_id, text)

    for _label, f in _iter_session_files(sources, cutoff):
        project = f.parent.name
        session_id = f.stem
        try:
            records = iter_jsonl(f)
        except Exception:
            continue
        for record in records:
            rtype = record.get('type')
            if rtype not in ('user', 'attachment'):
                continue
            if record.get('isSidechain') or record.get('isMeta'):
                continue
            ts = _record_ts(record)
            if ts is None or ts < cutoff:
                continue

            if rtype == 'attachment':
                att = record.get('attachment') or {}
                origin = att.get('origin') or {}
                if att.get('type') == 'queued_command' and origin.get('kind') == 'human':
                    prompt = att.get('prompt')
                    if isinstance(prompt, list):
                        prompt = '\n'.join(
                            x.get('text', '') if isinstance(x, dict) else str(x) for x in prompt)
                    if isinstance(prompt, str) and prompt.strip():
                        raw_queued.append((ts, project, session_id, prompt.strip()))
                continue

            if record.get('promptSource') not in (None, 'typed', 'queued'):
                continue
            got = _user_candidate_text(record)
            if got is None:
                continue
            text, n_img = got
            text = text.strip()
            if not text or text.startswith(NOISE_PREFIX):
                continue
            uuid = record.get('uuid')
            if uuid:
                if uuid in seen_uuid:
                    continue
                seen_uuid.add(uuid)
            raw_user.append((ts, project, session_id, text, n_img))

    # --- generic boilerplate detection: identical long text repeated many times ---
    # Frequency is counted on raw text (standalone injections are byte-identical);
    # membership checks normalize, tail-stripping searches the raw block.
    freq = {}
    for _ts, _p, _session_id, text, _i in raw_user:
        if len(normalize_text(text)) >= BOILER_MIN_CHARS:
            freq[text] = freq.get(text, 0) + 1
    boilerplate_raw = [t for t, n in freq.items() if n >= min_dup]
    boilerplate_norm = {normalize_text(t) for t in boilerplate_raw}

    agent_exact, agent_long, agent_giant = build_agent_corpus(sources, cutoff)

    def classify(ts, project, session_id, text, n_img, into):
        """Route one candidate text to the right bucket. `into` is 'user' or 'queued'."""
        label = _command_label(text)
        if label is not None:
            result.commands.append(Entry(ts, project, label, session_id=session_id))
            return
        norm = normalize_text(text)
        if norm in boilerplate_norm:
            result.injected.append(Entry(ts, project, text, session_id=session_id))
            return
        for block in boilerplate_raw:
            idx = text.find(block)
            if idx > 0:
                text = text[:idx].rstrip()
                break
        text = IMG_TOKEN_RE.sub('', text).strip()
        if not text:
            return
        norm = normalize_text(text)
        if len(norm) >= PASTE_MIN_CHARS:
            # ascii ratio uses normalized text (whitespace-stripped) so padding can't
            # defeat it; line count uses raw text to see real paragraph structure.
            ascii_ratio = sum(1 for ch in norm if ord(ch) < 128) / len(norm)
            non_empty_lines = sum(1 for line in text.split('\n') if line.strip())
            if ascii_ratio >= PASTE_ASCII_RATIO or non_empty_lines >= PASTE_MULTI_LINE_MIN:
                result.pastes.append(Entry(ts, project, text, session_id=session_id))
                return
        if len(norm) >= AGENT_EXACT_MIN:
            h = hashlib.md5(norm.encode()).digest()
            earlier = agent_exact.get(h)
            if earlier is not None and earlier < ts:
                result.subtracted += 1
                return
            if len(norm) >= AGENT_CONTAINS_MIN and norm in agent_giant:
                if any(ats < ts and norm in at for ats, at in agent_long):
                    result.subtracted += 1
                    return
        probe = re.sub(r'[。！!？?～~．.\s]+$', '', text).lower()
        result.entries.append(
            Entry(
                ts,
                project,
                text,
                session_id=session_id,
                images=n_img,
                filler=probe in FILLER,
            )
        )

    for ts, project, session_id, text, n_img in raw_user:
        classify(ts, project, session_id, text, n_img, 'user')

    # Queued mid-work input: skip when the same text was delivered as a real record
    # (the delivered copy owns the timeline slot).
    delivered = {}
    for e in result.entries + result.commands:
        delivered.setdefault(normalize_text(e.text), []).append(e.ts)
    for ts, project, session_id, text in raw_queued:
        norm = normalize_text(text)
        if any(abs((t2 - ts).total_seconds()) <= DELIVERED_WINDOW_SEC for t2 in delivered.get(norm, [])):
            continue
        before = len(result.entries) + len(result.commands) + len(result.injected) + len(result.pastes)
        classify(ts, project, session_id, text, 0, 'queued')
        after = len(result.entries) + len(result.commands) + len(result.injected) + len(result.pastes)
        if after > before:
            delivered.setdefault(norm, []).append(ts)

    for bucket in (result.entries, result.commands, result.injected, result.pastes):
        bucket.sort(key=lambda e: e.ts)
    return result


# ---------------- rendering ----------------

def _proj_short(p: str) -> str:
    parts = [x for x in p.lstrip('-').split('-') if x]
    return parts[-1] if parts else p


def _esc(s: str) -> str:
    return htmllib.escape(s)


def render_html(ext: Extraction, days: int, group_by: str) -> str:
    entries = ext.entries
    n_filler = sum(1 for e in entries if e.filler)
    groups = {}
    for e in entries:
        if group_by == 'project':
            key = e.project
        elif group_by == 'session':
            key = e.session_id or '(session unknown)'
        else:
            key = e.ts.astimezone(CST).strftime('%Y-%m-%d')
        groups.setdefault(key, []).append(e)
    if group_by in ('project', 'session'):
        order = sorted(groups, key=lambda k: max(e.ts for e in groups[k]), reverse=True)
    else:
        order = sorted(groups, reverse=True)

    out = [f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>我的原话 · 近{days}天</title>
<style>
  :root {{ --ink:#1a1a1a; --meta:#9a9a9a; --hair:#e8e4de; --bg:#fbfaf8; }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:var(--bg); color:var(--ink); font-family:-apple-system,"PingFang SC","Songti SC",serif;
         display:flex; justify-content:center; padding:48px 20px 120px; }}
  main {{ width:100%; max-width:700px; }}
  header.page {{ font-size:13px; color:var(--meta); margin-bottom:56px;
                 display:flex; justify-content:space-between; align-items:baseline; }}
  header.page label {{ cursor:pointer; user-select:none; }}
  h2.grp {{ font-size:15px; font-weight:600; color:#4a4a4a;
            margin:72px 0 26px; padding-bottom:10px; border-bottom:1px solid var(--hair);
            display:flex; justify-content:space-between; align-items:baseline; gap:12px; }}
  h2.grp:first-of-type {{ margin-top:0; }}
  h2.grp .p {{ font-size:11px; font-weight:400; color:var(--meta);
               font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
               overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
  .msg {{ margin-bottom:34px; }}
  .msg.filler {{ display:none; }}
  body.show-filler .msg.filler {{ display:block; }}
  body.show-filler .msg.filler .words {{ color:#8a8a8a; }}
  .words {{ font-family:"Songti SC","Noto Serif CJK SC",serif; font-size:18.5px; line-height:1.9;
            white-space:pre-wrap; word-break:break-word; }}
  .meta {{ margin-top:7px; font-size:12px; color:var(--meta); }}
  details {{ margin-top:96px; font-size:13px; color:var(--meta); }}
  details summary {{ cursor:pointer; }}
  details ol {{ margin-top:14px; padding-left:20px; line-height:2; }}
  details .c {{ color:#6a6a6a; }}
</style></head><body><main>
<header class="page"><span>我的原话 · 近 {days} 天 · {len(entries)} 条</span>
<label><input type="checkbox" onchange="document.body.classList.toggle('show-filler',this.checked)"> 显示短应答（{n_filler} 条）</label></header>
"""]
    for key in order:
        rs = groups[key]
        label = _proj_short(key) if group_by == 'project' else key
        sub = key if group_by == 'project' else (rs[0].project if group_by == 'session' else '')
        out.append(f'<h2 class="grp"><span>{_esc(label)} · {len(rs)} 条</span><span class="p">{_esc(sub)}</span></h2>\n')
        for e in rs:
            t = e.ts.astimezone(CST).strftime('%m-%d %H:%M')
            img = f' · 附图×{e.images}' if e.images else ''
            cls = ' class="msg filler"' if e.filler else ' class="msg"'
            out.append(f'<div{cls}><div class="words">{_esc(e.text)}</div><div class="meta">{t}{img}</div></div>\n')

    for title, bucket, show_full in (
        ('斜杠命令', ext.commands, False),
        ('注入的固定文本', ext.injected, False),
        ('粘贴的长文', ext.pastes, True),
    ):
        out.append(f'<details><summary>附录 · {title} {len(bucket)} 条（不计入原话）</summary><ol>\n')
        for e in bucket:
            t = e.ts.astimezone(CST).strftime('%m-%d %H:%M')
            head = re.sub(r'\s+', ' ', e.text)[:80]
            out.append(f'<li><span class="c">{t} · {_esc(_proj_short(e.project))}</span> {_esc(head)}'
                       f'{"…" if len(e.text) > 80 else ""}</li>\n')
        out.append('</ol>')
        if show_full:
            for e in bucket:
                t = e.ts.astimezone(CST).strftime('%m-%d %H:%M')
                head = re.sub(r'\s+', ' ', e.text)[:80]
                out.append(f'<details style="margin-top:14px"><summary>全文：{_esc(head)}…</summary>'
                           f'<div style="white-space:pre-wrap;font-size:12px;margin-top:8px">{_esc(e.text[:20000])}</div></details>\n')
        out.append('</details>\n')
    out.append('</main></body></html>\n')
    return ''.join(out)


def render_markdown(ext: Extraction, days: int, group_by: str) -> str:
    entries = ext.entries
    groups = {}
    for e in entries:
        if group_by == 'project':
            key = e.project
        elif group_by == 'session':
            key = e.session_id or '(session unknown)'
        else:
            key = e.ts.astimezone(CST).strftime('%Y-%m-%d')
        groups.setdefault(key, []).append(e)
    if group_by in ('project', 'session'):
        order = sorted(groups, key=lambda k: max(e.ts for e in groups[k]), reverse=True)
    else:
        order = sorted(groups, reverse=True)
    md = [f'# 我的原话 · 近 {days} 天（{len(entries)} 条）\n']
    for key in order:
        rs = groups[key]
        label = _proj_short(key) if group_by == 'project' else key
        md.append(f'\n## {label}（{len(rs)} 条）\n')
        for e in rs:
            t = e.ts.astimezone(CST).strftime('%Y-%m-%d %H:%M:%S %z')
            img = f' · 附图×{e.images}' if e.images else ''
            md.append(f'\n{e.text}\n\n<sub>{t}{img}</sub>\n')
    for title, bucket in (('斜杠命令', ext.commands), ('注入的固定文本', ext.injected), ('粘贴的长文', ext.pastes)):
        md.append(f'\n---\n\n## 附录 · {title}（{len(bucket)} 条，不计入原话）\n')
        for e in bucket:
            head = re.sub(r'\s+', ' ', e.text)[:80]
            md.append(f'\n- {head}{"…" if len(e.text) > 80 else ""} <sub>{e.ts.astimezone(CST).strftime("%m-%d %H:%M")} · {_proj_short(e.project)}</sub>')
    return ''.join(md)


def main() -> int:
    ap = argparse.ArgumentParser(description='Extract verbatim user messages from Claude history.')
    ap.add_argument('out_base', nargs='?', default='~/.claude-flow-viewer/user-words',
                    help='output path without extension (.html/.md appended); '
                         'default ~/.claude-flow-viewer/user-words — persistent, NOT /tmp which the OS purges')
    ap.add_argument('--days', type=int, default=7)
    ap.add_argument('--group-by', choices=('project', 'session', 'day'), default='project')
    ap.add_argument('--min-dup', type=int, default=5,
                    help='identical long texts at/above this count are treated as injected boilerplate')
    ap.add_argument('--home', action='append', default=None,
                    help='exact scope: only this config home (repeatable); bypasses archive registry')
    args = ap.parse_args()

    sources, warnings = discover_claude_sources(explicit_homes=args.home)
    for w in warnings:
        print(f'warning: {w}', file=sys.stderr)
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)

    ext = extract(sources, cutoff, min_dup=args.min_dup)

    out = Path(args.out_base).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix('.html').write_text(render_html(ext, args.days, args.group_by), encoding='utf-8')
    out.with_suffix('.md').write_text(render_markdown(ext, args.days, args.group_by), encoding='utf-8')

    n_filler = sum(1 for e in ext.entries if e.filler)
    print(f'entries={len(ext.entries)} (filler={n_filler}) commands={len(ext.commands)} '
          f'injected={len(ext.injected)} pastes={len(ext.pastes)} agent-subtracted={ext.subtracted}')
    print(f'out={out}.html / {out}.md')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
