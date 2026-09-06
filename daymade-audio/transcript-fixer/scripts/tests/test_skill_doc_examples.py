"""The skill's copy-me audio examples must survive being copied.

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
import runpy
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[2]
SKILL_MD = SKILL_DIR / "SKILL.md"
REVIEW_QUEUE_MD = SKILL_DIR / "references" / "review_queue_dashboard.md"
AUDIO_DOCS = (SKILL_MD, REVIEW_QUEUE_MD)
SERVER_PY = SKILL_DIR / "scripts" / "review-dashboard" / "server.py"
WORKFLOW_GUIDE = SKILL_DIR / "references" / "workflow_guide.md"
TROUBLESHOOTING = SKILL_DIR / "references" / "troubleshooting.md"
FILE_FORMATS = SKILL_DIR / "references" / "file_formats.md"
DJI_EXAMPLE = SKILL_DIR / "references" / "example_session_dji_minutes.md"
ARGUMENT_PARSER_PY = SKILL_DIR / "scripts" / "cli" / "argument_parser.py"
ADVANCED_EVIDENCE = SKILL_DIR / "references" / "advanced_correction_evidence.md"
IDENTITY_CONTEXT = SKILL_DIR / "references" / "dictionary_identity_and_context.md"
ITERATION_WORKFLOW = SKILL_DIR / "references" / "iteration_workflow.md"
BEST_PRACTICES = SKILL_DIR / "references" / "best_practices.md"
NATIVE_WORKFLOW = SKILL_DIR / "references" / "native_ai_full_workflow.md"
QUICK_REFERENCE = SKILL_DIR / "references" / "quick_reference.md"

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


def test_skill_docs_show_an_audio_example_this_test_can_see():
    texts = {path: path.read_text(encoding="utf-8") for path in AUDIO_DOCS}
    in_block = any(
        any(line.startswith("audio:") for line in block)
        for text in texts.values()
        for block in _frontmatter_blocks(text)
    )
    if in_block:
        return
    # Distinguish "the docs dropped the example" from "the example moved somewhere
    # this extractor cannot see" — they need opposite fixes, and neither is
    # "delete this test".
    malformed = [str(path) for path, text in texts.items()
                 if re.search(r"^audio:", text, re.M)]
    assert not malformed, (
        f"{malformed} has an `audio:` line, but not inside a fenced yaml block whose "
        "first line is `---`, so this check cannot see it. Either restore that "
        "shape or widen _YAML_FENCE / _frontmatter_blocks to match the new one."
    )
    raise AssertionError(
        "The skill docs no longer show an `audio:` frontmatter example. If that is "
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
        (path, block)
        for path in AUDIO_DOCS
        for block in _frontmatter_blocks(path.read_text(encoding="utf-8"))
        if any(line.startswith("audio:") for line in block)
    ]
    assert blocks, "no visible `audio:` example — see test_skill_docs_show_an_audio_example_this_test_can_see"

    for i, (path, block) in enumerate(blocks):
        raw, closed, quoted = _parse_audio(block)
        where = f"`audio:` example #{i + 1} in {path.name}"

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


def test_dictionary_add_examples_never_add_an_identity_mapping():
    text = WORKFLOW_GUIDE.read_text(encoding="utf-8")
    pairs = re.findall(r'--add\s+"([^"]+)"\s+"([^"]+)"', text)
    assert pairs
    assert all(source != target for source, target in pairs)


def test_missing_table_recovery_uses_the_canonical_uv_entrypoint():
    for path in (TROUBLESHOOTING, FILE_FORMATS):
        text = path.read_text(encoding="utf-8")
        section = text.split("### Missing Tables", 1)[1].split("\n### ", 1)[0]
        assert "uv run scripts/fix_transcription.py --init" in section
        assert 'from core import CorrectionRepository' not in section


def test_public_dji_example_is_explicitly_synthetic():
    text = DJI_EXAMPLE.read_text(encoding="utf-8")
    native_workflow = (
        SKILL_DIR / "references" / "native_ai_full_workflow.md"
    ).read_text(encoding="utf-8")
    assert "完全合成的演练 fixture" in text
    assert "不对应任何真实人物、项目或逐字稿" in text
    assert "synthetic failure fixture" in native_workflow
    for private_source_marker in (
        "实战全程",
        "私人实体已化名",
        "我们的民宿就完了",
    ):
        assert private_source_marker not in text
        assert private_source_marker not in native_workflow


def test_public_json_contract_lists_the_complete_always_present_shape():
    skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    parameters = (SKILL_DIR / "references" / "script_parameters.md").read_text(
        encoding="utf-8"
    )
    stage1_contract = skill_text.split("The Stage 1 JSON contract is:", 1)[1].split(
        "For a native end-to-end example", 1
    )[0]
    fields = (
        '"applied"',
        '"deferred"',
        '"output_path"',
        '"needs_review_path"',
        '"input_unchanged"',
        '"review_enqueued"',
        '"stage1_only_incomplete"',
        '"stage2_total_chunks"',
        '"stage2_failed_chunks"',
        '"stage2_degraded"',
        '"boundary_refused"',
    )
    for field in fields:
        assert field in stage1_contract
    assert "All eleven fields are always present" in parameters
    assert "Stage 2/3 runs add" not in parameters

    parser = runpy.run_path(str(ARGUMENT_PARSER_PY))["create_argument_parser"]()
    help_text = parser.format_help()
    for field in fields:
        assert field.strip('"') in help_text
    assert "All eleven status fields are always present" in " ".join(help_text.split())


def test_multi_recording_completion_is_not_satisfied_by_sampled_clips():
    skill = SKILL_MD.read_text(encoding="utf-8")
    evidence = ADVANCED_EVIDENCE.read_text(encoding="utf-8")
    evidence_flat = " ".join(evidence.split())

    assert "a sampled clip settles only that anchored item" in skill
    assert "run an independent ASR across the complete" in evidence_flat
    assert "sampled cross-check only — incomplete" in evidence_flat
    assert "Entity disagreement is a human gate, not a vote" in evidence
    assert "This is mandatory for person names" in evidence


def test_high_quality_claim_is_blocked_by_pending_review_rows():
    skill = SKILL_MD.read_text(encoding="utf-8")
    evidence = ADVANCED_EVIDENCE.read_text(encoding="utf-8")
    evidence_flat = " ".join(evidence.split())

    assert "Detection and enqueueing are not correction" in skill
    assert "zero pending rows is required" in skill
    assert "Queue presence is not issue resolution" in evidence
    assert "draft / unresolved — incomplete" in evidence_flat
    assert "recognizer count is not a verdict" in evidence_flat


def test_human_verdict_does_not_auto_promote_a_one_off_rule():
    skill = SKILL_MD.read_text(encoding="utf-8")
    identity = IDENTITY_CONTEXT.read_text(encoding="utf-8")
    identity_flat = " ".join(identity.split())

    assert "they do not make a replacement reusable" in skill
    assert "a rare sentence-local mishearing stays file-only" in skill
    assert "reusability is a separate decision" in identity
    assert "put only observed ASR *misrecognitions* on `ASR 变体`" in identity_flat
    assert "For one-off names: ✅ `--add --domain`" not in identity
    assert "dictionary is usually less effort" not in identity
    assert "Capture every confirmed variant" not in identity
    assert "- **ASR 变体**: 晓明, 小铭老师" not in identity
    assert "One-off / minor name | **DB**" not in identity
    assert "One-off / minor name | **Exact transcript file only**" in identity
    assert "whole honorific-bearing phrase" in identity


def test_exact_file_review_is_executable_and_old_dictionary_advice_is_unreachable():
    parser = runpy.run_path(str(ARGUMENT_PARSER_PY))["create_argument_parser"]()
    help_text = parser.format_help()
    assert "--review-file FILE" in help_text

    runtime_docs = (
        SKILL_MD,
        REVIEW_QUEUE_MD,
        ITERATION_WORKFLOW,
        BEST_PRACTICES,
        WORKFLOW_GUIDE,
        NATIVE_WORKFLOW,
        QUICK_REFERENCE,
    )
    combined = "\n".join(path.read_text(encoding="utf-8") for path in runtime_docs)
    assert '--review-file "<absolute-canonical-file>"' in combined
    assert "stats.pending_total == 0" in combined
    for forbidden in (
        "IMMEDIATELY save to dictionary",
        "Save EACH correction to dictionary",
        "finish it with `--add`",
        "80%+ dictionary coverage",
        "they compound into dictionary+roster",
        "Check if dictionary corrections are sufficient.",
    ):
        assert forbidden not in combined


def test_full_source_handoff_names_the_asr_skill_and_independence_boundary():
    skill = SKILL_MD.read_text(encoding="utf-8")
    evidence = ADVANCED_EVIDENCE.read_text(encoding="utf-8")

    for text in (skill, evidence):
        assert "/daymade-audio:asr-transcribe-to-text" in text
        assert "same recognizer" in text
        assert "complete-source coverage" in text or "proves coverage" in text
