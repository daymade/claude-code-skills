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
                  per tool type, tool_result folded into Obsidian collapsible
                  callouts (> [!info]-), web_search citations collected into a
                  "Sources cited" list. Obsidian is the default because its Live
                  Preview cannot render HTML <details>.
  --format markdown  use HTML <details> instead of Obsidian callouts.
  --list-files    inventory every downloadable file (uploads / images / sandbox
                  outputs) with the endpoint family each needs.
  --extract-file  reconstruct a sandbox-created file's FINAL content by replaying
                  its create_file block plus every later str_replace in message
                  order — no download needed.
  --allow-lossy   override the fidelity gate (see below). Rarely correct.

Fidelity gate (why this script refuses to run silently):
  Rendering loss here is invisible by construction — a shape the renderer doesn't
  know produces '' and the markdown still looks perfectly well-formed. So nothing is
  written until every unit is accounted for: this unit carried N characters in the
  payload; did the renderer emit anything for it? If content reached the transcript
  as nothing, the export FAILS (exit 2) rather than hand over a plausible-looking
  fraction of the conversation.

  Two properties do the work, and both were learned by getting them wrong:

    * The budget is measured off the RAW payload and never switches on type. A
      per-type measure only looks at the fields that type's renderer happened to know
      about, so the audit inherits the renderer's blind spots and a new field on a
      known type vanishes at "100% retention".
    * The renderer may decide how to PRESENT a field. It may not decide that a field
      it doesn't recognize isn't content — whatever the type-specific branch leaves on
      the floor gets dumped, ugly but visible.

  Audited per tool_result ITEM, per message-level field, and per attachment body —
  not merely per block, because those are the granularities content actually gets lost
  at. Content the PLATFORM emptied (share snapshots) is tracked separately as a
  disclosed gap and never counted as loss.

  Changing the renderer? Run scripts/selftest_fidelity.py. Every case in it is a
  payload that fooled a previous version of this gate.

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
import re
import sys
from urllib.parse import urlparse


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
        head = f'### {title}'.strip()          # our own heading — safe to trim
        if url:
            head += f'\n<{url}>'
        body = item.get('text', '')
        # The body is NOT trimmed. A trailing space in the payload is part of the
        # payload: strip it and the original string no longer appears in the transcript,
        # which an independent byte-level proof correctly reports as missing content.
        # The rule, for every branch in this file: wrap and concatenate the payload's
        # text — never edit it. Cosmetics are not worth a byte of fidelity.
        return f'{head}\n\n{body}' if head else body
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
        if extra:
            return json.dumps(extra, ensure_ascii=False)
        # Leave a mark. Returning '' would be indistinguishable, to a reader, from the
        # renderer having quietly skipped something — and this whole file exists to
        # make "nothing came out" impossible to confuse with "nothing was there".
        return '*(image — the binary is not carried in the JSON; see --list-files)*'
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


def dump_fields(d, label):
    """Dump leftover content fields as ORIGINAL text — never json.dumps'd.

    json.dumps escapes newlines and quotes, so the string in the transcript is no longer
    the string in the payload. The audit's own `v in rendered` check then fails on any
    real content, and the export is refused with "nothing rendered" for a field that was,
    in fact, rendered. On one real account export that rejected 321 of 339 conversations.

    The selftest sailed through it, because its fixtures used escape-free strings
    ('Q' * 8000). Synthetic data hid the bug precisely where real data trips over it —
    which is the argument for running the real corpus, not for writing more fixtures.
    """
    parts = []
    for k in sorted(d):
        v = d[k]
        if isinstance(v, str):
            parts.append(f'**{k}** ({len(v)} chars):\n\n' + fence(v))
            continue
        # Nested value. The JSON shows the shape — but json.dumps escapes every string
        # inside it, so the payload's actual TEXT would still not appear in the
        # transcript, and an independent check would (correctly) call it missing. Emit
        # the structure for legibility AND every substantial leaf verbatim, so the text
        # is really there.
        parts.append(f'**{k}**:\n\n'
                     + fence(json.dumps(v, ensure_ascii=False, indent=2), 'json'))
        for s in string_leaves(v):
            if len(s) >= 40 and s.strip():
                parts.append(fence(s))
    n = sum(len(s) for s in string_leaves(d))
    return (f'<details><summary>{label}, {n} chars ({", ".join(sorted(d))})</summary>\n\n'
            + '\n\n'.join(parts) + '\n\n</details>')


def render_block(b, snapshot=False):
    """Render a block, then dump whatever the type-specific renderer left on the floor.

    The two-stage shape is deliberate. `_render_block_core` is allowed to be
    incomplete — it pretty-prints the shapes we know about, and the server owns the
    schema, so it will meet fields it has never heard of. What it is NOT allowed to be
    is silent. So instead of hoping every branch stays exhaustive against a schema we
    don't control, we ask it afterwards what it didn't emit, and dump that.

    A renderer may decide how to present a field. It may not decide that a field it
    doesn't recognize isn't content.
    """
    if not isinstance(b, dict):
        return fence(str(b))
    core = _render_block_core(b, snapshot)
    left = unrendered_fields(b, core)
    if not left:
        return core
    tail = dump_fields(left, '⚠️ fields this renderer does not know')
    return (core + '\n\n' + tail) if core.strip() else tail


def _render_block_core(b, snapshot=False):
    """Pretty-print the block shapes we know. `snapshot` = this payload came from a
    /share/ link.

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
        # No .rstrip(): it edits the payload's own text, so the original string no longer
        # appears in the transcript and an independent proof rightly calls it missing.
        # Cosmetics are not worth breaking byte-fidelity.
        txt = result_text(b)
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
    'extracted_content_file_uuid', 'success',
    'thumbnail_asset', 'preview_asset',
})


def image_file_url(f, base_url=''):
    """Return an absolute or relative URL for an image file's preview asset."""
    if not isinstance(f, dict) or f.get('file_kind') != 'image':
        return ''
    asset = f.get('preview_asset') or f.get('thumbnail_asset') or {}
    url = asset.get('url', '')
    if url and base_url and not url.startswith('http'):
        url = base_url.rstrip('/') + url
    return url


def image_file_markdown(f, base_url=''):
    """Markdown image reference for an image file, or '' if not renderable."""
    url = image_file_url(f, base_url)
    if not url:
        return ''
    return f'![{f.get("file_name", "?")}]({url})'


def file_text(f, base_url=''):
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
    if f.get('file_kind') == 'image':
        return image_file_markdown(f, base_url)
    # EVERY body key, not the first one that hits. Returning on the first match while
    # the budget counted them all — and while account() credited the file its full
    # budget on any non-empty body — let a second body key vanish at 100%. Same
    # all-or-nothing credit bug as the per-block audit, one level down.
    parts = [f[k] for k in FILE_TEXT_KEYS
             if isinstance(f.get(k), str) and f[k].strip()]
    unknown = {k: v for k, v in f.items()
               if k not in FILE_META_KEYS and k not in FILE_TEXT_KEYS
               and isinstance(v, str) and v.strip()}
    if unknown:
        parts.append(json.dumps(unknown, ensure_ascii=False, indent=2))
    return '\n\n'.join(parts)


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


def render_files(files, label, base_url=''):
    if not files:
        return []
    parts = ['{} **{} files ({})**: {}'.format(
        '📎' if label == 'uploaded' else '📦', label, len(files),
        ', '.join(f'`{f.get("file_name", "?")}`' for f in files if isinstance(f, dict)))]
    for f in files:
        if f.get('file_kind') == 'image':
            md = image_file_markdown(f, base_url)
            if md:
                parts.append(md)
            continue
        body = file_text(f, base_url)
        if body:
            parts.append(
                f'<details><summary>📄 {f.get("file_name", "?")} ({len(body)} chars)</summary>\n\n'
                + fence(body) + '\n\n</details>')
    return parts


def render_msg(m, snapshot=False, base_url=''):
    who = 'human' if m.get('sender') == 'human' else 'assistant'
    parts = [f'## {who} ({m.get("created_at", "")})']
    files = message_files(m)
    if files and who == 'human':
        parts += render_files(files, 'uploaded', base_url)
    blocks = message_blocks(m)
    parts.extend(x for x in (render_block(b, snapshot) for b in blocks) if x)
    top_text = m.get('text')
    content_texts = {
        b.get('text') for b in blocks
        if isinstance(b, dict) and b.get('type') == 'text' and b.get('text')
    }
    if top_text and top_text not in content_texts:
        # Agent turns can store thinking/tools in content[] and the final answer
        # only in top-level text. Preserve both without duplicating a text block.
        parts.append(top_text)
    if files and who == 'assistant':
        parts += render_files(files, 'produced', base_url)
    # Message-level fields no branch above rendered. `compaction_summary` is a real one
    # on real payloads and nothing here had ever heard of it; there will be others. A
    # field living at message level is invisible to any content[]-only audit, so if it
    # isn't dumped here it disappears without trace.
    left = {k: v for k, v in m.items()
            if k not in MSG_META_KEYS and isinstance(v, str) and v.strip()}
    if left:
        parts.append(dump_fields(left, '⚠️ message fields this renderer does not know'))
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
    # `source` carries the image BINARY (or a reference to it), not readable text.
    # It belongs here — but note the tension with rule 2 above: taking it out of this
    # set (an over-correction in the other direction) made the budget count a base64
    # blob the renderer had no business printing, and the gate then failed a perfectly
    # healthy export. The line is: exclude a key only when it is structurally incapable
    # of carrying prose. Binary carriers qualify. "Looks like metadata" does not.
    'source',
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


# Structural metadata on a content BLOCK. Used ONLY by the budget side.
# Same rule as ITEM_META_KEYS: when in doubt, leave the key out. Over-counting merely
# obliges the renderer to emit something; under-counting is how the gate goes blind.
BLOCK_META_KEYS = frozenset({
    'type', 'id', 'uuid', 'tool_use_id', 'start_timestamp', 'stop_timestamp',
    'flags', 'is_error', 'citations', 'citations_grouping_mode', 'index',
    'integration_name', 'integration_icon_url', 'icon_name', 'tool_identifier',
    'mcp_server_url', 'is_mcp_app', 'approval_options', 'approval_key',
    'approval_key_legacy', 'name',
    # NOT here: 'display_content'. It looks like presentation metadata and it carries
    # real content (a json_block, on real payloads). Excluding it blinded both sides at
    # once — the failure mode this whole list is warned about.
})

# Structural metadata on a MESSAGE. Everything else a message carries is content, and
# content that nobody renders is content that silently disappeared — `compaction_summary`
# is a real field on real payloads and no renderer here had ever heard of it.
MSG_META_KEYS = frozenset({
    'uuid', 'parent_message_uuid', 'sender', 'index', 'created_at', 'updated_at',
    'content', 'text', 'files', 'attachments', 'input_mode', 'stop_reason',
    'truncated', 'image_count', 'file_count', 'sync_sources', 'is_internal',
})

# Structural metadata on the CONVERSATION itself. The audit used to begin at
# `chat_messages`, so anything the conversation carried at top level was invisible to
# every check in this file — however rigorous they got. `summary` is populated on 284
# of 339 conversations in one real account export (652k chars), and no renderer here
# had ever looked at it. Three levels now audited: conversation, message, block/item.
CONV_META_KEYS = frozenset({
    'uuid', 'name', 'snapshot_name', 'conversation_uuid', 'created_at', 'updated_at',
    'chat_messages', 'current_leaf_message_uuid', 'creator', 'created_by', 'account',
    'is_public', 'up_to_date', 'project_uuid', 'settings', 'is_starred', 'model',
})


def conv_extra_md(conv):
    """Conversation-level content fields, rendered. Shared by the renderer and (as the
    tally, not the budget) by the audit — the same discipline as render_msg()."""
    extra = {k: v for k, v in conv.items()
             if k not in CONV_META_KEYS and isinstance(v, str) and v.strip()}
    if not extra:
        return ''
    return dump_fields(extra, '📋 conversation-level fields')


def message_blocks(m):
    """content[], normalized.

    A payload that puts a bare string in `content` used to make the renderer iterate
    its characters and die on `b.get(...)`. Normalizing is not collusion: it decides
    the SHAPE, not what counts as content.
    """
    c = m.get('content')
    if isinstance(c, str):
        return [{'type': 'text', 'text': c}] if c else []
    return c if isinstance(c, list) else []


def string_leaves(v):
    """Every string buried anywhere inside a value."""
    if isinstance(v, str):
        return [v]
    if isinstance(v, dict):
        return [s for vv in v.values() for s in string_leaves(vv)]
    if isinstance(v, list):
        return [s for vv in v for s in string_leaves(vv)]
    return []


def block_source_chars(b):
    """ALL non-metadata content in a block, measured off the raw payload.

    Deliberately does NOT switch on block type — and that is the whole point. A
    per-type measure only ever looks at the fields that type's renderer happened to
    know about when it was written, so the budget inherits the renderer's blind spots
    by construction: a NEW field on a KNOWN type is invisible to both, and vanishes at
    a serene "100% retention". That exact bug shipped three times here (a text block's
    unknown field, a tool_use input's unknown field, an attachment body under an
    unfamiliar key) because each fix taught one more branch about one more field
    instead of removing the assumption that the branches know what content is.

    They don't. Count everything structural-looking out, and everything else in.
    """
    if not isinstance(b, dict):
        return len(str(b or ''))
    total = 0
    for k, v in b.items():
        if k in BLOCK_META_KEYS:
            continue
        if k == 'content':
            if isinstance(v, list):
                total += sum(item_source_chars(i) for i in v)   # audited per item
            else:
                total += len(str(v or ''))
            continue
        if isinstance(v, str):
            total += len(v)
        elif isinstance(v, (dict, list)):
            total += sum(len(s) for s in string_leaves(v))
    return total


def unrendered_fields(b, rendered):
    """Content fields the type-specific renderer left on the floor.

    The backstop for the recurring failure above. Rather than demand every branch be
    exhaustive about a schema it does not control, ask it afterwards what it didn't
    emit. The renderer may pretty-print the fields it knows; it may NOT decide that a
    field it does not know is not content.
    """
    leftovers = {}
    # `content` is skipped only where it is genuinely audited elsewhere — i.e. on a
    # tool_result, which fidelity_report walks per item. Skipping it unconditionally
    # meant a future block type carrying content[] (an mcp_tool_result, say) would have
    # its items checked by nobody.
    audited_elsewhere = {'content'} if b.get('type') == 'tool_result' else set()
    for k, v in b.items():
        if k in BLOCK_META_KEYS or k in audited_elsewhere:
            continue
        missing = [s for s in string_leaves(v) if s.strip() and s not in rendered]
        if missing:
            leftovers[k] = v
    return leftovers


def fidelity_report(conv, source_url=''):
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
    base_url = ''
    if source_url:
        try:
            p = urlparse(source_url)
            base_url = f'{p.scheme}://{p.netloc}'
        except Exception:
            pass
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
        # `if emitted`, NOT `if emitted.strip()`. claude.ai emits text blocks whose
        # entire content is "\n\n" around tool calls — 185 of them across 11.8% of the
        # conversations in one real account export. The renderer reproduces them
        # faithfully; .strip() then declares that faithful reproduction to be nothing,
        # books it as a dropped block, and refuses the export with a message telling the
        # user their payload contains a shape the renderer can't handle. It doesn't.
        #
        # The budget counted that whitespace as content. The tally must count the same
        # whitespace as output. One definition per character, or the gate manufactures
        # failures out of its own inconsistency — and a gate that cries wolf on 12% of
        # real conversations teaches people to pass --allow-lossy, which is the one
        # thing that actually destroys it.
        if emitted:
            rendered += src
        else:
            dropped.append({'unit': unit, 'type': kind, 'name': name, 'chars': src})

    # Conversation-level content. Audited FIRST because for years it wasn't audited at
    # all: the walk started at chat_messages, so a 652k-char `summary` sat outside every
    # check in this file.
    conv_md = conv_extra_md(conv)
    for k, v in conv.items():
        if k in CONV_META_KEYS or not isinstance(v, str) or not v.strip():
            continue
        account(f'conv.{k}', 'conversation-field', k, len(v), v if v in conv_md else '')

    for i, m in enumerate(msgs):
        blocks = message_blocks(m)
        msg_md = render_msg(m, snapshot, base_url)     # measured, never assumed

        for f in message_files(m):
            # Budget from the raw object, tally from the rendered message. Using
            # file_text() for both — as an earlier version did — makes the audit agree
            # with the renderer's blind spots by construction.
            src = file_source_chars(f)
            if src:
                body = file_text(f, base_url)
                account(f'msg[{i}].file', 'attachment', f.get('file_name', '?'),
                        src, body if body and body in msg_md else '')

        # Message-level content fields. Outside content[], therefore outside the reach
        # of any block-level audit no matter how rigorous — `compaction_summary` sat
        # there, real and unrendered, through every previous version of this gate.
        for k, v in m.items():
            if k in MSG_META_KEYS or not isinstance(v, str) or not v.strip():
                continue
            account(f'msg[{i}].{k}', 'message-field', k, len(v), v if v in msg_md else '')

        for j, b in enumerate(blocks):
            if not isinstance(b, dict):
                account(f'msg[{i}].block[{j}]', 'raw', '', len(str(b)),
                        str(b) if str(b) in msg_md else '')
                continue
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


# Below this, strings are payload plumbing: uuids (36), timestamps (~27), type names,
# enum values, short tool names. Demanding those appear in a transcript would make the
# proof unusable. This is a pragmatic floor, not a completeness proof — it catches the
# failure that matters (a BODY of content going missing), not every conceivable one.
PROVE_MIN_CHARS = 120


def prove_no_loss(conv, transcript, min_chars=PROVE_MIN_CHARS):
    """Independent proof: every substantial string in the payload is in the transcript.

    Shares no logic with the budget or the renderer. It does not know what a block is,
    what counts as metadata, or which fields matter — it walks the raw JSON and asks one
    question per string.

    That ignorance is the entire point. The budget and the renderer now agree with each
    other through three shared denylists (BLOCK/ITEM/MSG_META_KEYS). A wrong entry in any
    of them blinds BOTH sides at once, and no amount of rigor inside that machinery can
    see it — those lists have already been wrong twice. So the last check is one that
    trusts none of it.

    Only the active path is walked: messages on abandoned edit branches are correctly
    absent from the transcript, and demanding them would manufacture failures.
    """
    missing = []

    def walk(v, path):
        if isinstance(v, str):
            if len(v) >= min_chars and v not in transcript:
                missing.append((path, len(v)))
        elif isinstance(v, dict):
            for k, vv in v.items():
                walk(vv, f'{path}.{k}')
        elif isinstance(v, list):
            for i, vv in enumerate(v):
                walk(vv, f'{path}[{i}]')

    for k, v in conv.items():
        if k == 'chat_messages':
            continue
        walk(v, f'conv.{k}')
    for i, m in enumerate(active_path(conv)):
        walk(m, f'msg[{i}]')
    return missing


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
        for b in message_blocks(m):
            for c in (b.get('citations') or []):
                u = (c.get('details') or {}).get('url')
                if u and u not in urls:
                    urls.append(u)
    if not urls:
        return ''
    lines = ['', '## Sources cited', '']
    lines += [f'{i}. <{u}>' for i, u in enumerate(urls, 1)]
    return '\n'.join(lines) + '\n'


def obsidian_callout(summary, body):
    """Wrap content in an Obsidian collapsible callout.

    Every line inside the callout must start with '> ' so Obsidian treats the
    whole block as part of the callout. Code fences, nested markdown, and
    blank lines are preserved by prefixing each line individually.
    """
    lines = [f'> [!info]- {summary}', '>']
    for raw in body.splitlines():
        lines.append(f'> {raw}' if raw else '>')
    return '\n'.join(lines)


def details_to_obsidian_callouts(md):
    """Convert the markdown's HTML <details> blocks into Obsidian callouts.

    Obsidian Live Preview does not render HTML <details>, so the collapsible tool
    outputs/thinking/files come out as flat noise there. This rewrites each
    <details><summary>…</summary> … </details> block as a `> [!info]-` callout.

    It runs AFTER the fidelity gate, which audits the verbatim <details> markdown
    where every payload string is preserved — so this is a cosmetic post-pass that
    touches no payload string and cannot affect the retention proof.
    """
    lines = md.splitlines()
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r'<details><summary>(.*)</summary>', line)
        if not m:
            out.append(line)
            i += 1
            continue
        summary = m.group(1)
        i += 1
        if i < len(lines) and lines[i].strip() == '':
            i += 1  # consume optional blank line after the opening tag
        body_lines = []
        while i < len(lines) and lines[i].strip() != '</details>':
            body_lines.append(lines[i])
            i += 1
        if i < len(lines) and lines[i].strip() == '</details>':
            i += 1  # consume the closing tag
        while body_lines and body_lines[-1].strip() == '':
            body_lines.pop()  # drop trailing blank lines inside the body
        out.append(obsidian_callout(summary, '\n'.join(body_lines)))
    return '\n'.join(out)


def render_transcript(conv, source_url='', report=None, toc=False):
    base_url = ''
    if source_url:
        try:
            p = urlparse(source_url)
            base_url = f'{p.scheme}://{p.netloc}'
        except Exception:
            pass
    # The disclosure is computed here when the caller didn't supply it, so that no
    # code path can produce a transcript that quietly omits it. Making the banner
    # depend on an optional argument would mean the one function that hides the
    # holes is the easiest one to call — precisely the silent-by-default shape this
    # script exists to eliminate.
    if report is None:
        report = fidelity_report(conv, source_url)
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
    extra = conv_extra_md(conv)
    if extra:
        head += ['', extra]
    head += ['', '---', '']
    if toc:
        toc_lines = ['## Table of contents', '']
        for i, m in enumerate(msgs, 1):
            who = 'human' if m.get('sender') == 'human' else 'assistant'
            ts = m.get('created_at', '')
            toc_lines.append(f'{i}. [{who} ({ts})](#turn-{i})')
        head += toc_lines + ['', '---', '']
    body_parts = []
    for i, m in enumerate(msgs, 1):
        anchor = f'<a id="turn-{i}"></a>\n' if toc else ''
        body_parts.append(anchor + render_msg(m, snapshot, base_url))
    body = '\n\n---\n\n'.join(body_parts)
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
        for b in message_blocks(m):
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
        for b in message_blocks(m):
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
    ap.add_argument('--format', choices=['markdown', 'obsidian'], default='obsidian',
                    help='output format: obsidian (default, collapsible > [!info]- callouts) or '
                         'markdown (HTML <details>). Obsidian is the default because its Live '
                         'Preview cannot render HTML <details>. Applied only after the fidelity gate '
                         'passes on the <details> markdown, so it never affects the retention proof.')
    ap.add_argument('--toc', action='store_true',
                    help='prepend a linked table of contents and add per-message anchors so '
                         'long conversations are navigable')
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
        report = fidelity_report(conv, args.source_url)
        out = render_transcript(conv, args.source_url, report, toc=args.toc)

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
        # Orphans are deliberately NOT fatal. A message whose ancestry exits the payload
        # without touching the active path is the signature of a truncated payload — and
        # ALSO the signature of the user having edited the FIRST message of the thread,
        # because that message's parent is a virtual root that is never in chat_messages,
        # so its abandoned version has nowhere to hang from. The two are structurally
        # identical; no amount of cleverness distinguishes them. Failing here rejected
        # real conversations for the third time. Report, and let the reader judge.

        for d in report['dropped_blocks'][:10]:
            fatal.append(f"{d['unit']} ({d['type']}/{d['name'] or '-'}): {d['chars']:,} chars "
                         f"in the payload, nothing rendered")
        extra = len(report['dropped_blocks']) - 10
        if extra > 0:
            fatal.append(f'… and {extra} more dropped unit(s)')

        # Independent proof, run against the finished transcript. It shares no logic with
        # the audit above — which is the only way to catch a wrong entry in the denylists
        # that audit trusts.
        unproven = prove_no_loss(conv, out)
        for path, n in unproven[:5]:
            fatal.append(f"{path}: {n:,} chars are in the payload and NOT in the transcript "
                         f"(independent proof — this bypasses the audit entirely, so the "
                         f"audit's own denylists cannot hide it)")
        if len(unproven) > 5:
            fatal.append(f'… and {len(unproven) - 5} more unproven string(s)')

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
        if report['messages_unwalked']:
            n_orphan = len(report['orphaned_messages'])
            note = (f"note: {report['messages_unwalked']} message(s) are off the active path "
                    f"(abandoned edit/regeneration branches) — expected, not loss")
            if n_orphan:
                note += (f"; {n_orphan} of them have no ancestry into the path at all, which "
                         f"is what an edit of the FIRST message looks like — but also what a "
                         f"truncated payload looks like. If you expected a longer "
                         f"conversation, re-fetch")
            print(note, file=sys.stderr)
        if report['stripped_blocks']:
            names = sorted({s['name'] for s in report['stripped_blocks'] if s['name']})
            print(f"known gap: {len(report['stripped_blocks'])} tool blocks were emptied by the "
                  f"platform ({', '.join(names) or 'unnamed'}) — disclosed in the transcript header, "
                  f"NOT recoverable from a shared link", file=sys.stderr)

        # Obsidian conversion happens ONLY here — after the fidelity gate has run on the
        # verbatim <details> markdown and passed. Converting to > [!info]- callouts is a
        # cosmetic post-pass that touches no payload string, so it cannot affect the
        # retention proof above. (Kept out of the --extract-file branch on purpose: that
        # emits raw file content, not a transcript.)
        if args.format == 'obsidian':
            out = details_to_obsidian_callouts(out)

    if args.output:
        open(args.output, 'w', encoding='utf-8').write(out)
        print(f'wrote {len(out)} chars to {args.output}', file=sys.stderr)
    else:
        sys.stdout.write(out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
