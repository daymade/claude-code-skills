#!/usr/bin/env python3
"""Render an exported claude.ai conversation JSON into a faithful markdown transcript.

Input: the JSON captured by scripts/export_conversation.js (a /chat/ conversation)
or by the shared-snapshot endpoint (a /share/ link). Both shapes are handled — see
"Two payload shapes" below; always fetch with render_all_tools=true, or the tool
blocks arrive as placeholders and the export is a shell of the conversation.

Usage:
  uv run python render_transcript.py conversation.json -o transcript.md
  uv run python render_transcript.py conversation.json --source-url https://claude.ai/chat/<id>
  uv run python render_transcript.py conversation.json --list-files
  uv run python render_transcript.py conversation.json --extract-file /mnt/user-data/outputs/script.py -o script.py

Modes:
  (default)       full markdown transcript: timestamped speaker headers, upload/
                  output file inventories per message, tool_use blocks rendered
                  per tool type, tool_result folded into <details>, web_search
                  citations collected into a "Sources cited" list.
  --list-files    inventory every downloadable file (uploads / images / sandbox
                  outputs) with the endpoint family each needs.
  --extract-file  reconstruct a sandbox-created file's FINAL content by replaying
                  its create_file block plus every later str_replace in message
                  order — no download needed.
  --allow-lossy   override the fidelity gate (see below). Rarely correct.

Fidelity gate (why this script refuses to run silently):
  Rendering loss here is invisible by construction — an unhandled block type
  renders as '' and the markdown still looks perfectly well-formed. So before
  writing anything, every block is audited: it carried N characters of text; did
  the renderer emit anything for it? If any block carried text and produced
  nothing, the export FAILS (exit 2) instead of handing over a plausible-looking
  fraction of the conversation. Blocks the platform itself emptied (see below) are
  tracked separately as a disclosed gap, never counted as loss.

Two payload shapes:
  /chat/  — `name` holds the title; tool_result.content is a text[] list.
  /share/ — `name` is null (title lives in `snapshot_name`); web_search results
            arrive as `knowledge` items (title/url/text), and every tool call that
            touched the sharer's uploads has its input/content emptied by the
            platform. Those gaps are real and unrecoverable from the link; they are
            disclosed in the transcript header rather than passed off as complete.
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


def result_item_text(item):
    """Text carried by ONE item inside a tool_result's content[].

    The critical property here is that an unrecognized item must never render as
    the empty string. `tool_result.content[]` is not a fixed schema — a shared
    snapshot returns web_search hits as `knowledge` items (title/url/text), where
    a /chat/ export returns plain `text` items. The original code matched only
    `type == 'text'` and returned '' for everything else, so an export could lose
    the overwhelming majority of its content and still look perfectly well-formed
    — verified on a research conversation where the search results were 91% of the
    payload. Anything unknown is therefore dumped rather than dropped: a future
    server-side block type should degrade into ugly JSON we can see, never into
    silence we can't.
    """
    if not isinstance(item, dict):
        return str(item or '')
    t = item.get('type')
    if t == 'text':
        return item.get('text', '')
    if t == 'knowledge':                       # web_search result
        title, url = item.get('title', ''), item.get('url', '')
        head = f'### {title}'.strip()
        if url:
            head += f'\n<{url}>'
        return f'{head}\n\n{item.get("text", "")}'.strip()
    if t == 'image':                           # binary never rides in the JSON
        return ''
    body = item.get('text') or item.get('content')
    if isinstance(body, str) and body:
        return body
    return json.dumps(item, ensure_ascii=False)


def result_text(block):
    c = block.get('content')
    if isinstance(c, list):
        return '\n\n'.join(t for t in (result_item_text(i) for i in c) if t)
    if isinstance(c, str):
        return c
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
        if not inp:
            # A shared-link snapshot strips the arguments of tool calls that
            # touched the sharer's private files (a `view` of an upload keeps its
            # name but loses `path` and the file's content). Say so out loud:
            # rendering it as "view ()" reads like a bug in this script, and
            # implies the call did nothing — when in fact the payload is simply
            # not in this link and never will be. Only the original conversation,
            # opened by its owner, still has it.
            return (f'**🔧 {name}** — ⚠️ arguments stripped by the platform '
                    '(shared-link snapshot; not recoverable from this link)')
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


def block_source_chars(b):
    """How much content this block carries IN THE PAYLOAD (0 = it carries none).

    Measured straight off the raw JSON — deliberately never through result_text()
    or any other rendering-path parser. A gate that asks the parser how much there
    was to render can only ever confirm the parser's own blind spots: the parser
    that couldn't see `knowledge` items would have reported a budget of zero for
    them, and the gate would have cheerfully agreed that losing 91% of the
    conversation was fine. The budget must come from the payload, the tally from
    the renderer, and the two must be computed by code that cannot collude.
    """
    t = b.get('type')
    if t == 'text':
        return len(b.get('text') or '')
    if t == 'thinking':
        return len(b.get('thinking') or '')
    if t == 'tool_use':
        inp = b.get('input') or {}
        return len(json.dumps(inp, ensure_ascii=False)) if inp else 0
    if t == 'tool_result':
        c = b.get('content')
        if not c:
            return 0                                  # genuinely empty => stripped
        if isinstance(c, list):
            # Image results legitimately carry no text (the binary never rides in
            # the JSON), so they are not a budget the renderer failed to meet.
            textual = [i for i in c
                       if not (isinstance(i, dict) and i.get('type') == 'image')]
            return len(json.dumps(textual, ensure_ascii=False)) if textual else 0
        return len(str(c))
    return len(json.dumps(b, ensure_ascii=False)) if b else 0


def fidelity_report(conv):
    """Account for every block: did the text in the payload reach the transcript?

    This exists because the failure it catches is SILENT. A renderer that doesn't
    recognize a block type returns '' and nothing complains — the markdown looks
    clean, the run exits 0, and the loss is invisible unless you happen to know
    how long the conversation was. So instead of trusting the renderer, we ask it,
    block by block: this block carried N characters — did you emit anything at all
    for it? Any block that carried text and rendered to nothing is a real defect,
    and the export must fail rather than quietly hand over a plausible-looking
    fraction of the conversation.

    A block that carries NO text in the payload is a different animal and must not
    be conflated with loss: shared-link snapshots ship tool calls whose arguments
    and results the platform removed. Those are counted separately as `stripped` —
    a known, disclosed, unrecoverable gap rather than a bug in this script.

    Known limit, stated so nobody mistakes this for more than it is: the check is
    binary per block — "did the renderer emit anything for it?" It catches a block
    that vanished (the real, observed failure: an unrecognized type returning ''),
    not a block that was rendered but truncated. Crediting the block its full source
    length on any non-empty output is what makes that so. If truncation is ever
    introduced into render_block(), this gate will not notice, and it would need to
    compare emitted content rather than merely detect its presence.
    """
    carried = rendered = 0
    dropped, stripped = [], []
    for i, m in enumerate(active_path(conv)):
        blocks = m.get('content') or []
        for b in blocks:
            src = block_source_chars(b)
            kind = b.get('type')
            if src == 0:
                if kind in ('tool_use', 'tool_result'):
                    stripped.append({'msg': i, 'type': kind, 'name': b.get('name', '')})
                continue
            carried += src
            if render_block(b).strip():
                rendered += src
            else:
                dropped.append({'msg': i, 'type': kind, 'name': b.get('name', ''), 'chars': src})
        top = m.get('text') or ''
        seen = {b.get('text') for b in blocks if b.get('type') == 'text' and b.get('text')}
        if top and top not in seen:
            carried += len(top)
            rendered += len(top)      # render_msg always appends it
    return {
        'carried_chars': carried,
        'rendered_chars': rendered,
        'retention': (rendered / carried) if carried else 1.0,
        'dropped_blocks': dropped,     # payload had text, renderer emitted nothing => BUG
        'stripped_blocks': stripped,   # payload itself was emptied by the platform => disclosed gap
    }


def gap_notice(report):
    """The disclosure banner. A reader must never mistake a snapshot for the whole
    conversation just because the export ran cleanly."""
    stripped = report['stripped_blocks']
    if not stripped:
        return []
    names = sorted({s['name'] for s in stripped if s['name']})
    tools = ', '.join(f'`{n}`' for n in names) or 'tool'
    return [
        '', f'> ⚠️ **Known gap — {len(stripped)} tool blocks were emptied by the platform** '
            f'({tools}). A shared-link snapshot omits the arguments and results of '
            'calls that touched the sharer\'s uploaded files, so their content is '
            'absent from this export and **cannot be recovered from this link**. '
            'This is a platform-side omission, not an export failure. Only the '
            'original conversation, fetched by the account that owns it, still '
            'carries them — see the skill\'s account-case table.', '',
    ]


def citation_sources(conv):
    """web_search citations carry the URLs the answer actually leaned on — the
    most reusable artifact in a research conversation. They live on text blocks,
    so a renderer that only walks block bodies throws them away."""
    urls = []
    for m in active_path(conv):
        for b in (m.get('content') or []):
            for c in (b.get('citations') or []):
                u = (c.get('details') or {}).get('url')
                if u and u not in urls:
                    urls.append(u)
    if not urls:
        return ''
    lines = ['', '## Sources cited', '']
    lines += [f'{i}. <{u}>' for i, u in enumerate(urls, 1)]
    return '\n'.join(lines) + '\n'


def render_transcript(conv, source_url='', report=None):
    # The disclosure is computed here when the caller didn't supply it, so that no
    # code path can produce a transcript that quietly omits it. Making the banner
    # depend on an optional argument would mean the one function that hides the
    # holes is the easiest one to call — precisely the silent-by-default shape this
    # script exists to eliminate.
    if report is None:
        report = fidelity_report(conv)
    msgs = active_path(conv)
    # A share payload leaves `name` null and puts the real title in snapshot_name.
    title = conv.get('name') or conv.get('snapshot_name') or 'Untitled conversation'
    head = [f'# {title}', '']
    if source_url:
        head.append(f'> Source: {source_url}')
    if conv.get('conversation_uuid'):           # => this is a shared snapshot
        creator = (conv.get('creator') or {}).get('full_name') or conv.get('created_by') or '?'
        head.append(f'> Shared-link snapshot of conversation `{conv["conversation_uuid"]}` '
                    f'(shared by: {creator})')
    head += [f'Created: {conv.get("created_at", "?")}', f'Messages: {len(msgs)}']
    head += gap_notice(report)
    head += ['', '---', '']
    body = '\n\n---\n\n'.join(render_msg(m) for m in msgs)
    return '\n'.join(head) + body + '\n' + citation_sources(conv)


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
    ap.add_argument('--allow-lossy', action='store_true',
                    help='write the transcript even if blocks failed to render '
                         '(default: refuse, because that loss is otherwise silent)')
    args = ap.parse_args(argv)

    conv = json.load(open(args.json_path, encoding='utf-8'))
    if args.list_files:
        list_files(conv)
        return 0
    if args.extract_file:
        try:
            out = extract_file(conv, args.extract_file)
        except ExtractionError as exc:
            print(f'ERROR: {exc}', file=sys.stderr)
            return 1
    else:
        report = fidelity_report(conv)
        out = render_transcript(conv, args.source_url, report)

        if report['dropped_blocks'] and not args.allow_lossy:
            print('FIDELITY CHECK FAILED — refusing to write a lossy transcript.\n',
                  file=sys.stderr)
            for d in report['dropped_blocks'][:10]:
                print(f"  msg[{d['msg']}] {d['type']}/{d['name'] or '-'}: "
                      f"{d['chars']:,} chars in the payload, nothing rendered",
                  file=sys.stderr)
            extra = len(report['dropped_blocks']) - 10
            if extra > 0:
                print(f'  … and {extra} more', file=sys.stderr)
            print(
                f"\n{len(report['dropped_blocks'])} block(s) carried text that never reached the\n"
                f"transcript ({report['retention']:.0%} retention). This is exactly the silent loss\n"
                f"this check exists to catch — the payload almost certainly contains a block shape\n"
                f"render_block()/result_item_text() doesn't handle yet. Inspect one:\n"
                f"    python -c \"import json;d=json.load(open('{args.json_path}'));"
                f"b=d['chat_messages'][{report['dropped_blocks'][0]['msg']}]['content'];"
                f"print(json.dumps(b[0],ensure_ascii=False)[:800])\"\n"
                f"then teach the renderer that shape. Use --allow-lossy only after you have\n"
                f"decided, explicitly, that losing this content is acceptable.",
                file=sys.stderr)
            return 2

        if report['dropped_blocks']:   # only reachable with --allow-lossy
            print(f"⚠️  WROTE A LOSSY TRANSCRIPT ON PURPOSE (--allow-lossy): "
                  f"{len(report['dropped_blocks'])} block(s) carrying "
                  f"{sum(d['chars'] for d in report['dropped_blocks']):,} chars were dropped. "
                  f"Do not describe this export as complete.", file=sys.stderr)
        print(f"fidelity: {report['rendered_chars']:,}/{report['carried_chars']:,} chars rendered "
              f"({report['retention']:.1%})", file=sys.stderr)
        if report['stripped_blocks']:
            names = sorted({s['name'] for s in report['stripped_blocks'] if s['name']})
            print(f"known gap: {len(report['stripped_blocks'])} tool blocks were emptied by the "
                  f"platform ({', '.join(names) or 'unnamed'}) — disclosed in the transcript header, "
                  f"NOT recoverable from a shared link", file=sys.stderr)

    if args.output:
        open(args.output, 'w', encoding='utf-8').write(out)
        print(f'wrote {len(out)} chars to {args.output}', file=sys.stderr)
    else:
        sys.stdout.write(out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
