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
        # The walk stops early; every message above the break is never iterated, so a
        # per-block audit sees a perfectly clean 100%.
        'broken parent chain must fail, not report 100%',
        conv([msg('a', parent='ghost', content=[{'type': 'text', 'text': 'hi'}]),
              msg('b', parent='a', content=[{'type': 'text', 'text': BIG}])],
             current_leaf_message_uuid='a'),
        2, [], [],
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
