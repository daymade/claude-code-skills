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
    if t == 'image':
        # The binary never rides in the JSON, so an image item usually carries no text
        # and emitting nothing IS correct. But do not hard-code that to '': if the item
        # ever carries a caption, OCR, alt text — anything — returning '' here while
        # the budget also skipped images would put both sides of the audit in the same
        # blind spot, which is the collusion this module exists to prevent.
        #
        # The invariant, stated once for every branch above and below: ANY non-metadata
        # string in the payload must be visible to BOTH the renderer and the budget.
        # An empty render is only ever allowed where the budget is also, independently,
        # zero.
        txt = item.get('text')
        if isinstance(txt, str) and txt:
            return txt
        extra = {k: v for k, v in item.items()
                 if k not in ITEM_META_KEYS and isinstance(v, str) and v.strip()}
        return json.dumps(extra, ensure_ascii=False) if extra else ''
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


def render_block(b, snapshot=False):
    """Render one content block. `snapshot` = this payload came from a /share/ link.

    That flag exists because the same observation — a tool call with no arguments —
    means two completely different things depending on provenance, and getting it
    wrong means lying to the user about their own data. On a shared snapshot the
    platform really did strip the sharer's file contents, and the reader must be
    told the hole is permanent. On the user's OWN conversation an empty `input` is
    just an empty input, and claiming "the platform stripped this, unrecoverable"
    would be a fabricated provenance claim about a conversation they can re-fetch in
    full. Never assert the stronger, scarier story without the evidence for it.
    """
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
            if snapshot:
                # A shared-link snapshot strips the arguments of tool calls that
                # touched the sharer's private files (a `view` of an upload keeps
                # its name but loses `path` and the file's content). Say so: an
                # empty "view ()" reads like a bug in this script and implies the
                # call did nothing, when in fact the payload is simply not in this
                # link and never will be.
                return (f'**🔧 {name}** — ⚠️ arguments stripped by the platform '
                        '(shared-link snapshot; not recoverable from this link)')
            return f'**🔧 {name}** — (no arguments recorded)'
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


# A message's files/attachments can carry the file's TEXT right in the payload
# (a pasted document, an extracted PDF). Listing only the filename throws that away —
# and because those live at message level, not in content[], a block-level audit
# cannot even see the loss.
FILE_TEXT_KEYS = ('extracted_content', 'preview_contents', 'text', 'content')

# Structural metadata on a file object. Used ONLY by the budget side.
FILE_META_KEYS = frozenset({
    'file_name', 'file_kind', 'file_uuid', 'uuid', 'id', 'path', 'size_bytes',
    'created_at', 'type', 'preview_url', 'thumbnail_url', 'document_asset_uuid',
    'extracted_content_file_uuid',
})


def file_text(f):
    """The file's text content, if the payload carries it.

    Unknown shapes must DUMP, never drop — the same rule as result_item_text(), for
    the same reason. An attachment body sitting under a key we don't recognize has to
    come out ugly; it must not come out missing. (It did: a 9,000-char body under
    `document_body` rendered as nothing while the gate reported 100%, because
    file_text() was serving as both the renderer's extractor AND the budget's measure
    — the exact collusion this file forbids two hundred lines further up. Writing the
    rule down did not prevent me from breaking it in the very same commit.)
    """
    if not isinstance(f, dict):
        return ''
    for k in FILE_TEXT_KEYS:
        v = f.get(k)
        if isinstance(v, str) and v.strip():
            return v
    unknown = {k: v for k, v in f.items()
               if k not in FILE_META_KEYS and isinstance(v, str) and v.strip()}
    if unknown:
        return json.dumps(unknown, ensure_ascii=False, indent=2)
    return ''


def file_source_chars(f):
    """Content this file carries, measured off the RAW object — never via file_text()."""
    if not isinstance(f, dict):
        return 0
    total = 0
    for k, v in f.items():
        if k in FILE_META_KEYS:
            continue
        if isinstance(v, str):
            total += len(v)
        elif isinstance(v, (dict, list)):
            total += len(json.dumps(v, ensure_ascii=False))
    return total


def message_files(m):
    return (m.get('files') or []) + (m.get('attachments') or [])


def render_files(files, label):
    if not files:
        return []
    parts = ['{} **{} files ({})**: {}'.format(
        '📎' if label == 'uploaded' else '📦', label, len(files),
        ', '.join(f'`{f.get("file_name", "?")}`' for f in files if isinstance(f, dict)))]
    for f in files:
        body = file_text(f)
        if body:
            parts.append(
                f'<details><summary>📄 {f.get("file_name", "?")} ({len(body)} chars)</summary>\n\n'
                + fence(body) + '\n\n</details>')
    return parts


def render_msg(m, snapshot=False):
    who = 'human' if m.get('sender') == 'human' else 'assistant'
    parts = [f'## {who} ({m.get("created_at", "")})']
    files = message_files(m)
    if files and who == 'human':
        parts += render_files(files, 'uploaded')
    blocks = m.get('content') or []
    rendered_blocks = [x for x in (render_block(b, snapshot) for b in blocks) if x]
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
        parts += render_files(files, 'produced')
    return '\n\n'.join(parts)


# Structural metadata on a tool_result ITEM. Used ONLY by the budget side.
#
# Two rules govern this list, both learned the hard way:
#
# 1. It contains no item *type*. An earlier version excluded `type == 'image'` from
#    the budget while the renderer also returned '' for images — putting both sides of
#    the audit in the same blind spot, so an image item carrying 38k chars of text
#    scored a triumphant 100%. Judge a field by what it IS, never by what the item
#    claims to be.
#
# 2. Keep it SMALL. Over-counting the budget is safe: the renderer just has to emit
#    something for the block, and result_item_text() dumps what it doesn't recognize,
#    so a metadata field counted as content costs nothing. Under-counting is how the
#    gate goes blind. An earlier version padded this list with keys copied in from the
#    file and block layers ('name', 'path', 'file_name', …) that an item may not even
#    have — every one of them a field the audit would refuse to look at. When in
#    doubt, leave a key OUT of this set.
ITEM_META_KEYS = frozenset({
    'type', 'id', 'uuid', 'tool_use_id', 'is_error', 'is_citable', 'is_missing',
    'metadata', 'prompt_context_metadata', 'links', 'citations',
    'start_timestamp', 'stop_timestamp', 'flags',
    'icon_name', 'integration_name', 'integration_icon_url', 'mcp_server_url',
})


def item_source_chars(item):
    """Content ONE tool_result item carries, measured off the RAW payload.

    Never routed through result_item_text(): the budget and the tally must be
    computed by code that cannot agree with each other's mistakes.
    """
    if not isinstance(item, dict):
        return len(str(item or ''))
    total = 0
    for k, v in item.items():
        if k in ITEM_META_KEYS:
            continue
        if isinstance(v, str):
            total += len(v)
        elif isinstance(v, (dict, list)):
            total += len(json.dumps(v, ensure_ascii=False))
    return total


def block_source_chars(b):
    """Content this block carries in the payload (tool_result is audited per item)."""
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
        if isinstance(c, list):
            return sum(item_source_chars(i) for i in c)
        return len(str(c or ''))
    return len(json.dumps(b, ensure_ascii=False)) if b else 0


def fidelity_report(conv):
    """Did everything in the payload actually reach the transcript?

    The failure this guards against is SILENT: a renderer that meets a shape it
    doesn't know returns '' and nothing complains — clean markdown, exit 0, and most
    of the conversation gone. So we don't ask the renderer how it did. We measure the
    payload independently, then check what the renderer emitted for each unit.

    **Audited per ITEM, not per block.** That distinction is the whole gate. An
    earlier version credited a block its full budget on any non-empty output, so a
    38k-char item that vanished went unnoticed because a 16-char sibling in the same
    `content[]` rendered fine. The original 91%-loss incident was caught only by luck
    — those tool_results happened to contain nothing *but* the unrecognized items.
    Mix one recognized item in and the identical bug ships at "100% retention".
    Items are the granularity result_item_text() can lose things at, so items are the
    granularity we audit at.

    Three other things a block-level audit structurally cannot see, all covered here:
      * message-level file/attachment BODIES (they live outside content[]),
      * top-level `text` (measured against the rendered message, not assumed),
      * messages the active_path() walk never reached (a broken parent chain).

    `stripped` is a different animal from loss and is only ever recorded for a
    /share/ snapshot, where the platform genuinely removed the sharer's file
    contents. On the user's own conversation an empty tool input is just an empty
    tool input — claiming "the platform stripped this, unrecoverable" about a
    conversation they can re-fetch in full would be a fabricated provenance claim.
    """
    snapshot = bool(conv.get('conversation_uuid'))
    all_msgs = conv.get('chat_messages') or []
    msgs = active_path(conv)

    carried = rendered = 0
    dropped, stripped = [], []

    def account(unit, kind, name, src, emitted):
        nonlocal carried, rendered
        if src <= 0:
            return
        carried += src
        if emitted and emitted.strip():
            rendered += src
        else:
            dropped.append({'unit': unit, 'type': kind, 'name': name, 'chars': src})

    for i, m in enumerate(msgs):
        blocks = m.get('content') or []
        msg_md = render_msg(m, snapshot)     # measured, never assumed

        for f in message_files(m):
            # Budget from the raw object, tally from the rendered message. Using
            # file_text() for both — as an earlier version did — makes the audit agree
            # with the renderer's blind spots by construction.
            src = file_source_chars(f)
            if src:
                body = file_text(f)
                account(f'msg[{i}].file', 'attachment', f.get('file_name', '?'),
                        src, body if body and body in msg_md else '')

        for j, b in enumerate(blocks):
            kind, name = b.get('type'), b.get('name', '')
            unit = f'msg[{i}].block[{j}]'

            if kind == 'tool_result':
                items = b.get('content')
                if not items:
                    if snapshot:
                        stripped.append({'msg': i, 'type': kind, 'name': name})
                    continue
                if isinstance(items, list):
                    for k, it in enumerate(items):
                        itype = it.get('type') if isinstance(it, dict) else '?'
                        account(f'{unit}.item[{k}]', f'tool_result/{itype}', name,
                                item_source_chars(it), result_item_text(it))
                    continue
                account(unit, kind, name, len(str(items)), result_text(b))
                continue

            if kind == 'tool_use' and not (b.get('input') or {}):
                if snapshot:
                    stripped.append({'msg': i, 'type': kind, 'name': name})
                continue

            account(unit, kind, name, block_source_chars(b), render_block(b, snapshot))

        top = m.get('text') or ''
        if top:
            account(f'msg[{i}].text', 'text', '', len(top), top if top in msg_md else '')

    # Truncation detection. Two shapes, both invisible to a per-block audit (the
    # blocks in question are never iterated at all), and both of which must be told
    # apart from the abandoned edit/regeneration branches that any edited conversation
    # is full of.
    #
    #   ORPHANS — messages whose ancestry never reaches the active path. A regenerated
    #   answer is emphatically NOT one: it hangs off a message that IS on the path,
    #   which is exactly what makes it a branch rather than debris. Following the
    #   ancestry is what separates them; counting unwalked messages cannot.
    #
    #   LEAF WITH CHILDREN — the payload declares the thread ends at a message that
    #   demonstrably has messages after it, so the walk stopped short of the real end.
    #
    # Getting this wrong in the safe-looking direction is not safe. An earlier attempt
    # keyed on "the first walked message's parent is absent from the payload" — which
    # is true of EVERY conversation, since a thread's first message points at something
    # predating it — and so rejected every conversation the user had ever edited. A
    # detector that fires on healthy input is worse than no detector at all: people
    # learn to reach for --allow-lossy, and then it guards nothing.
    by_id_all = {mm.get('uuid'): mm for mm in all_msgs}
    path_ids = {mm.get('uuid') for mm in msgs}
    orphans = []
    for mm in all_msgs:
        if mm.get('uuid') in path_ids:
            continue
        mid, seen = mm.get('parent_message_uuid'), set()
        while mid and mid in by_id_all and mid not in seen:
            if mid in path_ids:
                break                              # hangs off the path => a branch
            seen.add(mid)
            mid = by_id_all[mid].get('parent_message_uuid')
        else:
            orphans.append(mm.get('uuid'))         # ancestry never touched the path
    leaf = conv.get('current_leaf_message_uuid')
    leaf_has_children = bool(leaf) and any(
        mm.get('parent_message_uuid') == leaf for mm in all_msgs)
    unwalked = len(all_msgs) - len(msgs)
    return {
        'snapshot': snapshot,
        'messages_total': len(all_msgs),
        'messages_walked': len(msgs),
        'messages_unwalked': unwalked,
        'orphaned_messages': orphans,
        'leaf_has_children': leaf_has_children,
        'truncated': bool(orphans) or leaf_has_children,
        'carried_chars': carried,
        'rendered_chars': rendered,
        # Zero carried is 0%, NOT 100%. An empty payload is the limit case of the
        # very bug this gate exists for; scoring it perfect would be the gate failing
        # at its own job.
        'retention': (rendered / carried) if carried else 0.0,
        'dropped_blocks': dropped,     # payload had content, renderer emitted nothing => BUG
        'stripped_blocks': stripped,   # platform emptied it (snapshots only) => disclosed gap
    }


def gap_notice(report):
    """The disclosure banner. A reader must never mistake a snapshot for the whole
    conversation just because the export ran cleanly."""
    stripped = report['stripped_blocks']
    if not stripped or not report.get('snapshot'):
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
    snapshot = report.get('snapshot', bool(conv.get('conversation_uuid')))
    msgs = active_path(conv)
    # A share payload leaves `name` null and puts the real title in snapshot_name.
    title = conv.get('name') or conv.get('snapshot_name') or 'Untitled conversation'
    head = [f'# {title}', '']
    if source_url:
        head.append(f'> Source: {source_url}')
    if snapshot:
        creator = (conv.get('creator') or {}).get('full_name') or conv.get('created_by') or '?'
        head.append(f'> Shared-link snapshot of conversation `{conv["conversation_uuid"]}` '
                    f'(shared by: {creator})')
    head += [f'Created: {conv.get("created_at", "?")}', f'Messages: {len(msgs)}']
    head += gap_notice(report)
    head += ['', '---', '']
    body = '\n\n---\n\n'.join(render_msg(m, snapshot) for m in msgs)
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

    try:
        with open(args.json_path, encoding='utf-8') as fh:
            conv = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f'ERROR: cannot read {args.json_path}: {exc}', file=sys.stderr)
        return 1
    if not isinstance(conv, dict):
        # A failed fetch leaves `null` here; a mis-scoped eval leaves a list. Neither
        # is a conversation, and pretending otherwise produced a traceback before.
        print(f'ERROR: {args.json_path} does not contain a conversation object '
              f'(got {type(conv).__name__}). A failed fetch commonly leaves `null`; '
              f're-run the fetch.', file=sys.stderr)
        return 1

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

        # Floors first. An empty or truncated payload is the LIMIT CASE of the very
        # loss this gate exists for — rubber-stamping it at "100%" would be the gate
        # failing at its own job, and an empty fetch is exactly what a broken channel
        # produces.
        fatal = []
        if report['messages_total'] == 0:
            fatal.append('payload contains no chat_messages — this is not a conversation export')
        elif report['carried_chars'] == 0:
            fatal.append('payload carries no readable content at all — almost certainly '
                         'an empty or failed fetch')
        if report['leaf_has_children']:
            fatal.append(
                "truncated payload: the declared leaf message has children, so the walk "
                "stopped short of where the conversation actually ends. Re-fetch — this is "
                "not a rendering problem.")
        if report['orphaned_messages']:
            n = len(report['orphaned_messages'])
            fatal.append(
                f"truncated payload: {n} message(s) are orphaned — their ancestry never "
                f"reaches the active path, so they were neither rendered nor audited. These "
                f"are NOT abandoned edit branches (those hang off the path); the payload is "
                f"missing the messages that would connect them. Re-fetch.")

        for d in report['dropped_blocks'][:10]:
            fatal.append(f"{d['unit']} ({d['type']}/{d['name'] or '-'}): {d['chars']:,} chars "
                         f"in the payload, nothing rendered")
        extra = len(report['dropped_blocks']) - 10
        if extra > 0:
            fatal.append(f'… and {extra} more dropped unit(s)')

        if fatal and not args.allow_lossy:
            print('FIDELITY CHECK FAILED — refusing to write.\n', file=sys.stderr)
            for f in fatal:
                print(f'  * {f}', file=sys.stderr)
            if report['dropped_blocks']:
                print(
                    f"\nContent in the payload never reached the transcript "
                    f"({report['retention']:.0%} retention). This is the silent loss this check "
                    f"exists to catch: the payload almost certainly contains a shape "
                    f"result_item_text()/render_block() doesn't handle yet. Teach the renderer "
                    f"that shape.", file=sys.stderr)
            print("\nUse --allow-lossy only after deciding, explicitly, that losing this is "
                  "acceptable.", file=sys.stderr)
            return 2

        if fatal:      # only reachable with --allow-lossy
            print(f"⚠️  WROTE AN INCOMPLETE TRANSCRIPT ON PURPOSE (--allow-lossy): "
                  f"{len(report['dropped_blocks'])} unit(s) carrying "
                  f"{sum(d['chars'] for d in report['dropped_blocks']):,} chars were dropped. "
                  f"Do NOT describe this export as complete.", file=sys.stderr)
        print(f"fidelity: {report['rendered_chars']:,}/{report['carried_chars']:,} chars rendered "
              f"({report['retention']:.1%}) across {report['messages_walked']} message(s)",
              file=sys.stderr)
        if report['messages_unwalked'] and not report['truncated']:
            print(f"note: {report['messages_unwalked']} message(s) are off the active path "
                  f"(abandoned edit/regeneration branches) — expected, not loss", file=sys.stderr)
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
