"""SKILL.md's copy-me examples must survive being copied.

Why this file exists: the `audio:` frontmatter example has shipped broken twice.
Both times it grew a trailing `# …` annotation explaining what to do with the
line — which is helpful to read and fatal to copy, because the dashboard's
parser takes everything after the first colon and does not strip comments. The
result is a path that does not exist, and the card then renders with no play
button *and no error*, which reads exactly like "this transcript has no audio."

Prose cannot defend against this: the warning against trailing comments was
already sitting nine lines below the broken example both times. A test can.

This file mirrors production rather than importing it (`server.py` pulls in the
web stack, which the test suite does not require). Mirroring is only safe while
the two agree, so the drift guard below is scoped to production's actual
function body — a whole-file substring check would keep passing if production
*added* comment-stripping, which is precisely the change that would invert the
rule encoded here and turn this test into one that fails healthy examples.
"""

from __future__ import annotations

import re
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[2]
SKILL_MD = SKILL_DIR / "SKILL.md"
SERVER_PY = SKILL_DIR / "scripts" / "review-dashboard" / "server.py"

PRODUCTION_FUNC = "_frontmatter_audio"
PRODUCTION_IDIOM = 'line.split(":", 1)[1].strip()'
# Any of these appearing inside the production function would mean it started
# handling comments — at which point the rule this file enforces is wrong.
COMMENT_HANDLING_HINTS = ('split("#"', "split('#'", 'partition("#"', "partition('#')", "#\", 1")

# A fenced yaml block: tolerant of case, an info string, and indentation, all of
# which render identically and are legitimate edits. Being strict here would
# make the suite fail on a healthy document — the failure mode that teaches
# people to delete checks.
_YAML_FENCE = re.compile(
    r"^[ \t]*```[ \t]*ya?ml\b[^\n]*\n(.*?)^[ \t]*```",
    re.S | re.M | re.I,
)


def _production_function_body() -> str:
    """The source of `_frontmatter_audio`, from its `def` to the next top-level `def`."""
    source = SERVER_PY.read_text(encoding="utf-8")
    start = source.find(f"def {PRODUCTION_FUNC}")
    assert start != -1, f"{PRODUCTION_FUNC} no longer exists in server.py"
    rest = source[start + 1 :]
    end = rest.find("\ndef ")
    return rest if end == -1 else rest[:end]


def _frontmatter_blocks(markdown: str) -> list[list[str]]:
    """Every fenced yaml block that opens with a `---` frontmatter marker."""
    blocks = []
    for match in _YAML_FENCE.finditer(markdown):
        lines = match.group(1).splitlines()
        if lines and lines[0].strip() == "---":
            blocks.append(lines)
    return blocks


def _parse_audio(lines: list[str]) -> tuple[str | None, bool, bool]:
    """Mirrors `_frontmatter_audio`: same scan, same stripping, same omissions.

    Returns (value, block_was_closed, value_was_quoted).
    """
    closed = False
    raw: str | None = None
    for line in lines[1:]:
        if line.strip() == "---":
            closed = True
            break
        if line.startswith("audio:"):
            raw = line.split(":", 1)[1].strip()
    quoted = bool(raw) and len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\""
    if quoted:
        raw = raw[1:-1].strip()   # production strips matched surrounding quotes
    return raw, closed, quoted


def test_production_parser_still_matches_this_mirror():
    body = _production_function_body()
    assert PRODUCTION_IDIOM in body, (
        f"{PRODUCTION_FUNC} no longer extracts the value with {PRODUCTION_IDIOM!r}. "
        "Read what it does now and update _parse_audio to match — otherwise this "
        "file enforces a rule production has stopped following."
    )
    found = [h for h in COMMENT_HANDLING_HINTS if h in body]
    assert not found, (
        f"{PRODUCTION_FUNC} now appears to handle comments ({found}). If it strips "
        "them, a trailing `#` in the docs is no longer fatal and the assertion in "
        "test_audio_examples_parse_to_a_usable_path is obsolete — update both."
    )


def test_skill_md_shows_an_audio_example_this_test_can_see():
    text = SKILL_MD.read_text(encoding="utf-8")
    in_block = any(
        any(line.startswith("audio:") for line in block)
        for block in _frontmatter_blocks(text)
    )
    if in_block:
        return
    # Distinguish "the docs dropped the example" from "the example moved somewhere
    # this extractor cannot see" — they need opposite fixes, and neither is
    # "delete this test".
    assert not re.search(r"^audio:", text, re.M), (
        "SKILL.md has an `audio:` line, but not inside a fenced yaml block whose "
        "first line is `---`, so this check cannot see it. Either restore that "
        "shape or widen _YAML_FENCE / _frontmatter_blocks to match the new one."
    )
    raise AssertionError(
        "SKILL.md no longer shows an `audio:` frontmatter example. If that is "
        "deliberate, remove the audio wiring docs too; the example is what this "
        "file exists to protect."
    )


def test_audio_examples_parse_to_a_usable_path():
    """Every `audio:` example must survive being copied verbatim.

    Assertions stay limited to what production actually breaks on. A check that
    also enforced house style would fail examples that work — and a check that
    misfires on healthy input teaches people to ignore it, which costs more than
    the defect it was built for.
    """
    blocks = [
        b for b in _frontmatter_blocks(SKILL_MD.read_text(encoding="utf-8"))
        if any(line.startswith("audio:") for line in b)
    ]
    assert blocks, "no visible `audio:` example — see test_skill_md_shows_an_audio_example_this_test_can_see"

    for i, block in enumerate(blocks):
        raw, closed, quoted = _parse_audio(block)
        where = f"`audio:` example #{i + 1}"

        assert closed, f"{where}: frontmatter block is not closed — production returns None"
        assert raw, f"{where}: the line yields an empty value"
        # The defect signature is whitespace followed by `#` in an UNQUOTED value:
        # that is what an inline annotation looks like once production has taken
        # everything after the colon. A quoted value is explicitly delimited by
        # the author, so a `#` inside it is part of the path and production
        # resolves it — flagging that would be a false positive. (An annotation
        # placed after a quoted value survives as `"…"  # note`, which fails the
        # matched-quote test, stays unquoted here, and is still caught.)
        if not quoted:
            assert not re.search(r"\s#", raw), (
                f"{where} parses to {raw!r} — a trailing annotation becomes part of "
                "the path, so a reader who copies this line gets a card with no play "
                "button and no error. Move the annotation into prose (or quote the "
                "value if the path genuinely contains a space and a hash)."
            )
