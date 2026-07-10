#!/usr/bin/env python3
"""Render an exported claude.ai conversation JSON into a faithful markdown transcript.

Input: the JSON captured by scripts/export_conversation.js (any rendering_mode
works; render_all_tools=true gives real tool blocks instead of placeholders).

Usage:
  uv run python render_transcript.py conversation.json -o transcript.md
  uv run python render_transcript.py conversation.json --source-url https://claude.ai/chat/<id>
  uv run python render_transcript.py conversation.json --list-files
  uv run python render_transcript.py conversation.json --extract-file /mnt/user-data/outputs/script.py -o script.py

Modes:
  (default)       full markdown transcript: timestamped speaker headers, upload/
                  output file inventories per message, tool_use blocks rendered
                  per tool type, tool_result folded into <details>.
  --list-files    inventory every downloadable file (uploads / images / sandbox
                  outputs) with the endpoint family each needs.
  --extract-file  reconstruct a sandbox-created file's FINAL content by replaying
                  its create_file block plus every later str_replace in message
                  order — no download needed.
"""
import argparse
import json
import sys


class ExtractionError(RuntimeError):
    """Raised when a sandbox file cannot be reconstructed exactly."""


def active_path(conv):
    """Walk the active branch (leaf -> root); fall back to raw array order."""
    msgs = conv.get('chat_messages') or []
    by_id = {m.get('uuid'): m for m in msgs}
    path, seen, mid = [], set(), conv.get('current_leaf_message_uuid')
    while mid and mid in by_id and mid not in seen:
        seen.add(mid)
        path.insert(0, by_id[mid])
        mid = by_id[mid].get('parent_message_uuid')
    return path if path else msgs


def result_text(block):
    c = block.get('content')
    if isinstance(c, list):
        return '\n'.join(i.get('text', '') for i in c
                         if isinstance(i, dict) and i.get('type') == 'text')
    return str(c or '')


def fence(text, lang=''):
    """Pick a fence longer than any backtick run inside the content."""
    n = 3
    while ('`' * n) in text:
        n += 1
    f = '`' * max(n, 3)
    return f'{f}{lang}\n{text}\n{f}'


def render_block(b):
    t = b.get('type')
    if t == 'text':
        return b.get('text', '')
    if t == 'thinking':
        thought = b.get('thinking', '')
        return f'<details><summary>💭 thinking</summary>\n\n{thought}\n\n</details>' if thought else ''
    if t == 'tool_use':
        name = b.get('name', '')
        inp = b.get('input') or {}
        desc = inp.get('description', '')
        if name == 'bash_tool':
            return f'**🔧 bash** — {desc}\n\n' + fence(inp.get('command', ''), 'bash')
        if name == 'view':
            return f'**🔧 view** — {desc}（`{inp.get("path", "")}`）'
        if name == 'create_file':
            return (f'**🔧 create_file** — {desc}（`{inp.get("path", "")}`）\n\n'
                    + fence(inp.get('file_text', '')))
        if name == 'str_replace':
            return (f'**🔧 str_replace** — {desc}（`{inp.get("path", "")}`）\n\n'
                    'old:\n' + fence(inp.get('old_str', ''))
                    + '\nnew:\n' + fence(inp.get('new_str', '')))
        if name == 'present_files':
            fps = inp.get('filepaths') or []
            return '**📤 deliverables**: ' + ', '.join(f'`{p}`' for p in fps)
        return f'**🔧 {name}**\n\n' + fence(json.dumps(inp, ensure_ascii=False, indent=2), 'json')
    if t == 'tool_result':
        txt = result_text(b).rstrip()
        if not txt:
            return ''  # image results etc. carry no text — the binary never rides in the JSON
        err = ' (ERROR)' if b.get('is_error') else ''
        return (f'<details><summary>▶ tool output{err} ({len(txt)} chars)</summary>\n\n'
                + fence(txt) + '\n\n</details>')
    return ''


def render_msg(m):
    who = 'human' if m.get('sender') == 'human' else 'assistant'
    parts = [f'## {who} ({m.get("created_at", "")})']
    files = (m.get('files') or []) + (m.get('attachments') or [])
    if files and who == 'human':
        parts.append('📎 **uploaded files ({})**: {}'.format(
            len(files), ', '.join(f'`{f.get("file_name", "?")}`' for f in files)))
    blocks = m.get('content') or []
    rendered_blocks = [x for x in (render_block(b) for b in blocks) if x]
    parts.extend(rendered_blocks)
    top_text = m.get('text')
    content_texts = {
        b.get('text') for b in blocks
        if b.get('type') == 'text' and b.get('text')
    }
    if top_text and top_text not in content_texts:
        # Agent turns can store thinking/tools in content[] and the final answer
        # only in top-level text. Preserve both without duplicating a text block.
        parts.append(top_text)
    if files and who == 'assistant':
        parts.append('📦 **produced files ({})**: {}'.format(
            len(files), ', '.join(f'`{f.get("file_name", "?")}`' for f in files)))
    return '\n\n'.join(parts)


def render_transcript(conv, source_url=''):
    msgs = active_path(conv)
    head = [f'# {conv.get("name", "Untitled conversation")}', '']
    if source_url:
        head.append(f'> Source: {source_url}')
    head += [f'Created: {conv.get("created_at", "?")}',
             f'Messages: {len(msgs)}', '', '---', '']
    return '\n'.join(head) + '\n\n---\n\n'.join(render_msg(m) for m in msgs) + '\n'


def list_files(conv):
    """Inventory downloadable files + which endpoint family each needs."""
    rows = []
    for i, m in enumerate(active_path(conv)):
        for f in (m.get('files') or []) + (m.get('attachments') or []):
            kind = f.get('file_kind')
            if kind == 'blob':
                rows.append((i, m.get('sender'), f.get('file_name'), f.get('size_bytes'),
                             'wiggle/download-file?path=' + str(f.get('path'))))
            elif kind == 'image':
                rows.append((i, m.get('sender'), f.get('file_name'), None,
                             f'files/{f.get("file_uuid") or f.get("uuid")}/contents'))
        for b in (m.get('content') or []):
            if b.get('type') == 'tool_use' and b.get('name') == 'present_files':
                for p in (b.get('input') or {}).get('filepaths') or []:
                    rows.append((i, 'assistant', p.split('/')[-1], None,
                                 'wiggle/download-file?path=' + p))
    for i, sender, name, size, endpoint in rows:
        size_s = f'{size}B' if size else '-'
        print(f'msg[{i}] {sender:9s} {size_s:>10s}  {name}  →  {endpoint}')
    if not rows:
        print('no files found in this conversation')


def extract_file(conv, sandbox_path):
    """Replay create_file + later str_replace edits → final file content."""
    content, ops = None, []
    for i, m in enumerate(active_path(conv)):
        for b in (m.get('content') or []):
            if b.get('type') != 'tool_use':
                continue
            inp = b.get('input') or {}
            if inp.get('path') != sandbox_path:
                continue
            if b.get('name') == 'create_file':
                content = inp.get('file_text', '')
                ops.append(f'msg[{i}] create_file ({len(content)} chars)')
            elif b.get('name') == 'str_replace' and content is not None:
                old = inp.get('old_str', '')
                matches = content.count(old) if old else 0
                if matches != 1:
                    raise ExtractionError(
                        f'msg[{i}] str_replace expected one old_str match but found '
                        f'{matches}; refusing to emit stale or ambiguous content'
                    )
                content = content.replace(old, inp.get('new_str', ''), 1)
                ops.append(f'msg[{i}] str_replace applied')
    print('\n'.join(ops) or f'no create_file found for {sandbox_path}', file=sys.stderr)
    if content is None:
        raise ExtractionError(f'no create_file found for {sandbox_path}')
    return content


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('json_path')
    ap.add_argument('-o', '--output', help='write result here instead of stdout')
    ap.add_argument('--source-url', default='', help='conversation URL for the transcript header')
    ap.add_argument('--list-files', action='store_true')
    ap.add_argument('--extract-file', metavar='SANDBOX_PATH',
                    help='e.g. /mnt/user-data/outputs/script.py')
    args = ap.parse_args(argv)

    conv = json.load(open(args.json_path, encoding='utf-8'))
    if args.list_files:
        list_files(conv)
        return
    try:
        out = (extract_file(conv, args.extract_file) if args.extract_file
               else render_transcript(conv, args.source_url))
    except ExtractionError as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    if args.output:
        open(args.output, 'w', encoding='utf-8').write(out)
        print(f'wrote {len(out)} chars to {args.output}', file=sys.stderr)
    else:
        sys.stdout.write(out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
