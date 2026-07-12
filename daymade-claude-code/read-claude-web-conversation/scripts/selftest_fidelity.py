#!/usr/bin/env python3
"""Regression suite for the fidelity gate. Run it after ANY change to render_transcript.py.

    uv run python scripts/selftest_fidelity.py

Why this file exists, bluntly: the gate has already been wrong twice, and both times
it was wrong in the same direction — reporting **100% retention** on payloads it had
lost almost all of. A gate that fails silently is worse than no gate, because it
launders a broken export into a certified one. Prose cannot defend against that; only
a payload that provably breaks it can.

Each case below is a shape that DID slip through a previous version. Keep them, and
add one whenever a new shape gets past the gate — the cost of a case is a dozen lines,
and the cost of skipping it is a transcript that lies.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
RENDER = HERE / 'render_transcript.py'

BIG = 'x' * 5000      # unmistakably present-or-absent in the output


def msg(uuid, sender='assistant', parent=None, **kw):
    m = {'uuid': uuid, 'sender': sender, 'created_at': '2026-01-01T00:00:00Z',
         'parent_message_uuid': parent, 'content': []}
    m.update(kw)
    return m


def conv(msgs, **kw):
    d = {'chat_messages': msgs}
    d.update(kw)
    return d


# (name, payload, expect_exit, must_contain, must_not_contain)
CASES = [
    (
        'empty payload is not 100%',
        {}, 2, [], [],
    ),
    (
        'no messages is not a conversation',
        conv([]), 2, [], [],
    ),
    (
        # The whole reason for per-ITEM auditing. A block-level gate credited the block
        # its full budget because a sibling item rendered, and 5k chars evaporated at
        # "100% retention".
        'unknown item hiding behind a rendered sibling must not vanish',
        conv([msg('a', content=[{'type': 'tool_result', 'name': 'search', 'content': [
            {'type': 'text', 'text': 'ok'},
            {'type': 'some_future_shape', 'body': BIG},
        ]}])]),
        0, [BIG], [],        # rendered (unknown shapes dump, not drop) => no loss
    ),
    (
        # An image item that carries text: the budget used to skip images by TYPE while
        # the renderer also returned '' for them — both blind, in lockstep.
        'image item carrying text must be rendered, not skipped by both sides',
        conv([msg('a', content=[{'type': 'tool_result', 'name': 'repl', 'content': [
            {'type': 'text', 'text': 'ok'},
            {'type': 'image', 'text': BIG},
        ]}])]),
        0, [BIG], [],
    ),
    (
        # Message-level content is invisible to any content[]-only audit.
        'attachment body must be rendered, not just its filename',
        conv([msg('a', sender='human',
                  attachments=[{'file_name': 'spec.txt', 'extracted_content': BIG}])]),
        0, [BIG], [],
    ),
    (
        # The collusion, round two. file_text() was serving as BOTH the renderer's
        # extractor and the budget's measure, so a body under a key it didn't know
        # scored 100% while vanishing. Written into a commit whose own docstring
        # forbade exactly this, two hundred lines above.
        'attachment body under an UNKNOWN key must still surface (budget must not share the extractor)',
        conv([msg('a', sender='human',
                  attachments=[{'file_name': 'spec.txt', 'document_body': BIG}])]),
        0, [BIG], [],
    ),
    (
        # Budget under-counting is how the gate goes blind. Metadata keys copied in
        # from other layers ('name', 'path', …) were fields the audit refused to look
        # at. Over-counting is safe; under-counting is not.
        'content under a key that looks like metadata must still be audited',
        conv([msg('a', content=[{'type': 'tool_result', 'name': 't', 'content': [
            {'type': 'text', 'text': 'ok'},
            {'type': 'odd', 'name': BIG},
        ]}])]),
        0, [BIG], [],
    ),
    (
        # Truncation shape 1: the payload declares a leaf that demonstrably has
        # messages after it, so the walk stopped short of the real end.
        'leaf with children must fail (truncated payload)',
        conv([msg('a', parent='ghost', content=[{'type': 'text', 'text': 'hi'}]),
              msg('b', parent='a', content=[{'type': 'text', 'text': BIG}])],
             current_leaf_message_uuid='a'),
        2, [], [],
    ),
    (
        # Truncation shape 2 — deliberately DOWNGRADED to a warning. A message whose
        # ancestry never reaches the active path is the signature of a truncated payload
        # AND of the user having edited the FIRST message of the thread (that message's
        # parent is a virtual root, never present in chat_messages, so its abandoned
        # version has nothing to hang from). The two are structurally identical and no
        # cleverness separates them. Failing here rejected real conversations — the third
        # time a truncation check did that. Warn; let the reader judge.
        'orphaned message warns but must NOT fail (indistinguishable from a first-message edit)',
        conv([msg('m2', parent='m1-MISSING', content=[{'type': 'text', 'text': 'a'}]),
              msg('m3', parent='m2', content=[{'type': 'text', 'text': 'b'}]),
              msg('mX', parent='m0-MISSING', content=[{'type': 'text', 'text': BIG}])],
             current_leaf_message_uuid='m3'),
        0, [], [],
    ),

    # ---- Found only by running 339 REAL conversations. Synthetic fixtures had ----
    # ---- passed every one of these, because 'Q'*8000 needs no escaping and has ----
    # ---- no trailing space. The corpus is the test; the fixtures are the memo.  ----
    (
        # claude.ai emits pure-whitespace text blocks around tool calls: 185 of them,
        # across 11.8% of one real account's conversations. The budget counted the
        # whitespace as content; the tally used .strip() and called the same characters
        # nothing. 40 real conversations were refused with "the renderer can't handle
        # this shape" — it could, perfectly.
        'whitespace-only text block must not be booked as loss',
        conv([msg('a', content=[{'type': 'text', 'text': '\n\n', 'citations': []},
                                {'type': 'text', 'text': BIG}])]),
        0, [BIG], [],
    ),
    (
        # `summary` is populated on 284 of 339 real conversations — 652,822 chars. The
        # audit began at chat_messages, so conversation-level content sat outside every
        # check in the file, however rigorous they got.
        'conversation-level content must be rendered and audited',
        conv([msg('a', content=[{'type': 'text', 'text': 'hi'}])], summary=BIG),
        0, [BIG], [],
    ),
    (
        # json.dumps escapes newlines and quotes, so the payload's own text stopped
        # appearing in the transcript and the audit's `v in rendered` check failed on
        # anything real. It rejected 321 of 339 conversations. Every fixture passed.
        'text with newlines/quotes must appear VERBATIM (never json-escaped)',
        conv([msg('a', content=[{'type': 'text', 'text': 'hi'}],
                  compaction_summary='line one\nline "two"\n\tand a tab')]),
        0, ['line one\nline "two"\n\tand a tab'], [],
    ),
    (
        # A trailing space in the payload IS the payload. .strip() on the payload's own
        # text (knowledge bodies, tool_result output) made the original string vanish.
        # Wrap and concatenate the text; never edit it.
        'trailing whitespace in payload text must survive',
        conv([msg('a', content=[{'type': 'tool_result', 'name': 'web_fetch', 'content': [
            {'type': 'knowledge', 'title': 'T', 'url': 'http://example.com',
             'text': 'body with a trailing space '}]}])]),
        0, ['body with a trailing space '], [],
    ),
    (
        # The case that MUST still pass, and the one two different truncation checks
        # have already broken: a plain regeneration. The old answer stays in the
        # payload, off the active path, and the thread's first message points at a
        # parent that predates the payload — both true of a perfectly healthy export.
        # A detector that fires here is worse than no detector at all.
        # (This also guards a KeyError that only triggered when unwalked > 0 — i.e.
        # only on conversations the user had actually edited.)
        'regenerated answer (dead branch) must still export cleanly',
        conv([msg('m1', sender='human', parent='pre-existing-root',
                  content=[{'type': 'text', 'text': 'Q'}]),
              msg('m2_old', parent='m1', content=[{'type': 'text', 'text': 'old answer'}]),
              msg('m2_new', parent='m1', content=[{'type': 'text', 'text': BIG}])],
             current_leaf_message_uuid='m2_new'),
        0, [BIG], ['old answer'],   # dead branch is correctly off the transcript
    ),
    (
        # Provenance honesty: on the user's OWN conversation an empty tool input is just
        # an empty tool input. Claiming the platform stripped it is a fabricated claim
        # about data they can re-fetch in full.
        "own conversation must not be accused of platform stripping",
        conv([msg('a', content=[
            {'type': 'tool_use', 'name': 'repl', 'input': {}},
            {'type': 'tool_result', 'name': 'repl', 'content': [{'type': 'image'}]},
            {'type': 'text', 'text': 'done'},
        ])]),
        0, [], ['stripped by the platform', 'Known gap'],
    ),
    (
        # Same shape, but genuinely from a /share/ link => the disclosure IS warranted.
        'shared snapshot must disclose the platform-stripped gap',
        conv([msg('a', content=[{'type': 'tool_use', 'name': 'view', 'input': {}},
                                {'type': 'text', 'text': 'done'}])],
             conversation_uuid='deadbeef', snapshot_name='shared'),
        0, ['Known gap'], [],
    ),
    # ---- The renderer must not decide that a field it doesn't know isn't content. ----
    # These four all shipped, silently, because each block type's renderer only looked
    # at the fields it was written for, and the budget switched on type too — so a NEW
    # field on a KNOWN type was invisible to both sides at once. Fixing them one branch
    # at a time is what let the next one through; the fix is structural (dump whatever
    # the type-specific renderer left on the floor, and never let the budget switch on
    # type).
    (
        'unknown field on a KNOWN tool (view) must not vanish',
        conv([msg('a', content=[{'type': 'tool_use', 'name': 'view',
                                 'input': {'path': '/a', 'description': 'd',
                                           'payload_v2': BIG}}])]),
        0, [BIG], [],
    ),
    (
        'unknown field on a text block must not vanish',
        conv([msg('a', content=[{'type': 'text', 'text': 'hi', 'extra_body': BIG}])]),
        0, [BIG], [],
    ),
    (
        # `compaction_summary` is a REAL field on real payloads that no renderer here
        # had ever heard of. Message-level content is invisible to any content[]-only
        # audit, however rigorous.
        'unknown MESSAGE-level field must not vanish',
        conv([msg('a', content=[{'type': 'text', 'text': 'hi'}], compaction_summary=BIG)]),
        0, [BIG], [],
    ),
    (
        # `for b in content` iterated the characters of the string and died on b.get().
        'content as a bare string must not crash',
        conv([msg('a', content='a bare string, not a list')]),
        0, ['a bare string, not a list'], [],
    ),
    (
        # The counterweight to all of the above: an image item legitimately carries no
        # text (the binary isn't in the JSON), and its `source` is a binary carrier, not
        # prose. Counting it as content made the gate fail a perfectly healthy export.
        # Exclude a key only when it is structurally incapable of carrying prose.
        'image-only tool result must not be mistaken for loss',
        conv([msg('a', content=[
            {'type': 'tool_result', 'name': 'repl',
             'content': [{'type': 'image', 'source': {'data': 'AAAA'}}]},
            {'type': 'text', 'text': 'chart above'}])]),
        0, ['chart above'], [],
    ),
    (
        'healthy payload passes at 100%',
        conv([msg('a', content=[{'type': 'text', 'text': BIG}])]),
        0, [BIG], [],
    ),
]


def run_case(name, payload, expect_exit, must_contain, must_not_contain):
    with tempfile.TemporaryDirectory() as td:
        src, out = Path(td) / 'c.json', Path(td) / 'out.md'
        src.write_text(json.dumps(payload), encoding='utf-8')
        p = subprocess.run([sys.executable, str(RENDER), str(src), '-o', str(out)],
                           capture_output=True, text=True)
        if p.returncode != expect_exit:
            return f'exit {p.returncode}, expected {expect_exit}\n      {p.stderr.strip()[:200]}'
        if expect_exit != 0:
            if out.exists():
                return 'gate failed but wrote the file anyway'
            return None
        md = out.read_text(encoding='utf-8')
        for needle in must_contain:
            if needle not in md:
                where = f'{len(needle)}-char payload' if len(needle) > 40 else repr(needle)
                return f'{where} never reached the transcript (gate said it was fine)'
        for needle in must_not_contain:
            if needle in md:
                return f'transcript wrongly contains {needle!r}'
        return None


def main():
    failed = 0
    for name, payload, code, yes, no in CASES:
        err = run_case(name, payload, code, yes, no)
        if err:
            failed += 1
            print(f'  FAIL  {name}\n        {err}')
        else:
            print(f'  ok    {name}')
    print()
    if failed:
        print(f'{failed}/{len(CASES)} failed — the fidelity gate is not trustworthy right now.')
        return 1
    print(f'all {len(CASES)} passed — the gate still catches every shape that has fooled it before.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
