"""Tests for the conversation-mining pipeline."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# Ensure repo root is importable for the `scripts` package.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import mine_conversation, check_references

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "mining-target"
MANIFEST = FIXTURES / "manifest.json"
INIT_SCRIPT = REPO_ROOT / "workflows" / "conversation-mining" / "scripts" / "init_conversation_mining.py"


@pytest.fixture
def enrich_dir(tmp_path: Path) -> Path:
    out = tmp_path / ".enrich"
    out.mkdir()
    return out


@pytest.fixture
def runtime_manifest(tmp_path: Path) -> Path:
    """Create sensitive-looking test data at runtime, never in repository files."""
    transcripts = tmp_path / "transcripts"
    shutil.copytree(FIXTURES / "transcripts", transcripts)

    provider_key = "sk-" + "kimi-" + "runtimefixture1234567890"
    bearer_token = "Bearer " + "runtime-token-12345"
    user_path = "/" + "Users" + "/fixture-person/workspace/examplehub"
    phone = "138" + "0013" + "8000"
    record = {
        "type": "user",
        "message": {
            "role": "user",
            "content": (
                "ExampleHub cache-first test data: "
                f"key={provider_key}; auth={bearer_token}; "
                f"path={user_path}; phone={phone}."
            ),
        },
        "timestamp": "2026-02-01T10:03:00Z",
    }
    excluded_old_record = {
        "type": "user",
        "message": {
            "role": "user",
            "content": "ExampleHub cache-first message outside the declared time window.",
        },
        "timestamp": "2025-07-10T10:03:00Z",
    }
    (transcripts / "runtime_sensitive_session.jsonl").write_text(
        json.dumps(record) + "\n" + json.dumps(excluded_old_record) + "\n",
        encoding="utf-8",
    )

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["sources"]["claude_code_sessions"]["roots"] = [str(transcripts)]
    manifest["sources"]["claude_command_history"]["path"] = str(transcripts / "history.jsonl")
    manifest["sources"]["manual_exports"] = [str(transcripts / "codex_history.jsonl")]
    runtime_path = tmp_path / "manifest.json"
    runtime_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return runtime_path


@pytest.fixture
def runtime_target(tmp_path: Path) -> Path:
    target = tmp_path / "target-skill"
    shutil.copytree(FIXTURES, target)
    (target / "SKILL.fixture.md").rename(target / "SKILL.md")
    return target


def test_mine_conversation_end_to_end(enrich_dir: Path, runtime_manifest: Path) -> None:
    rc = mine_conversation.main([
        "--manifest", str(runtime_manifest),
        "--output", str(enrich_dir),
        "--verbose",
    ])
    assert rc == 0

    assert (enrich_dir / "manifest.json").exists()
    assert (enrich_dir / "redaction_report.json").exists()
    assert (enrich_dir / "chunks").exists()
    assert (enrich_dir / ".gitignore").read_text(encoding="utf-8") == "*\n"

    manifest = json.loads((enrich_dir / "manifest.json").read_text())
    assert manifest["target_skill"] == "mining-target"
    assert manifest["message_counts"]["retained"] >= 3
    assert manifest["chunk_count"] >= 1
    serialized_manifest = json.dumps(manifest, ensure_ascii=False)
    assert str(runtime_manifest) not in serialized_manifest
    assert str(runtime_manifest.parent / "transcripts") not in serialized_manifest
    assert all(source["source_id"].startswith("source-") for source in manifest["sources"])
    assert all(
        set(source) == {"source_id", "type", "sha256", "size_bytes"}
        for source in manifest["sources"]
    )

    redaction = json.loads((enrich_dir / "redaction_report.json").read_text())
    assert redaction["total_replacements"] > 0

    provider_key = "sk-" + "kimi-" + "runtimefixture1234567890"
    bearer_token = "Bearer " + "runtime-token-12345"
    user_path = "/" + "Users" + "/fixture-person/workspace/examplehub"
    phone = "138" + "0013" + "8000"

    # Verify sensitive-looking runtime data is not in chunks.
    all_chunk_text = ""
    for chunk_file in (enrich_dir / "chunks").glob("chunk-*.json"):
        chunk = json.loads(chunk_file.read_text())
        text = json.dumps(chunk, ensure_ascii=False)
        all_chunk_text += text
        assert provider_key not in text
        assert phone not in text
        assert user_path not in text
        assert bearer_token not in text
        assert str(runtime_manifest.parent / "transcripts") not in text
        assert all(source.startswith("source-") for source in chunk["sources"])
        assert all(message["source"].startswith("source-") for message in chunk["messages"])
    assert "outside the declared time window" not in all_chunk_text

    for artifact in enrich_dir.rglob("*"):
        if artifact.is_file():
            artifact_text = artifact.read_text(encoding="utf-8")
            assert str(runtime_manifest) not in artifact_text
            assert str(runtime_manifest.parent / "transcripts") not in artifact_text


def test_mine_conversation_discover_only(enrich_dir: Path, runtime_manifest: Path) -> None:
    rc = mine_conversation.main([
        "--manifest", str(runtime_manifest),
        "--output", str(enrich_dir),
        "--discover-only",
    ])
    assert rc == 0
    manifest = json.loads((enrich_dir / "manifest.json").read_text())
    assert manifest["mode"] == "discover-only"
    assert not (enrich_dir / "chunks").exists()
    assert len(manifest["sources"]) >= 3
    assert "estimated_total_tokens" not in manifest
    assert "redaction_report" not in manifest
    assert manifest["message_time_window"] == {
        "since": "2026-01-01T00:00:00+00:00",
        "until": "2026-12-31T23:59:59+00:00",
    }


def test_check_references_clean(
    enrich_dir: Path,
    runtime_manifest: Path,
    runtime_target: Path,
) -> None:
    # Run the mine first to populate the enrich dir
    mine_conversation.main([
        "--manifest", str(runtime_manifest),
        "--output", str(enrich_dir),
    ])

    # No candidates yet, so check_references should pass with no issues
    rc = check_references.main([
        "--skill", str(runtime_target),
        "--enrich", str(enrich_dir),
        "--verbose",
    ])
    assert rc == 0


def test_check_references_duplicate_name(
    enrich_dir: Path,
    runtime_manifest: Path,
    runtime_target: Path,
) -> None:
    mine_conversation.main([
        "--manifest", str(runtime_manifest),
        "--output", str(enrich_dir),
    ])

    # Create a candidate that duplicates an existing reference name.
    # The filename stem matches the existing reference stem so the test is
    # robust even when PyYAML is not installed.
    candidates_dir = enrich_dir / "candidates"
    candidates_dir.mkdir(exist_ok=True)
    candidate = candidates_dir / "examplehub_cli.md"
    candidate.write_text("---\nname: examplehub-cli\ndescription: dup\n---\n# Duplicate\n")

    rc = check_references.main([
        "--skill", str(runtime_target),
        "--enrich", str(enrich_dir),
    ])
    assert rc == 2


def test_candidate_loader_preserves_same_named_files_from_different_agents(
    enrich_dir: Path,
) -> None:
    for agent in ("patterns", "war-stories"):
        agent_dir = enrich_dir / "candidates" / agent
        agent_dir.mkdir(parents=True)
        (agent_dir / "chunk-000.md").write_text(
            f"# {agent}\n\nDistinct candidate.\n",
            encoding="utf-8",
        )

    candidates = check_references._load_candidates(enrich_dir)

    assert set(candidates) == {
        "patterns/chunk-000.md",
        "war-stories/chunk-000.md",
    }


def test_init_conversation_mining(enrich_dir: Path, runtime_manifest: Path) -> None:
    # Populate enrich dir with chunks
    mine_conversation.main([
        "--manifest", str(runtime_manifest),
        "--output", str(enrich_dir),
    ])

    result = subprocess.run(
        [sys.executable, str(INIT_SCRIPT), "--enrich-dir", str(enrich_dir), "--agent", "patterns", "war-stories"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    patterns_dir = enrich_dir / "candidates" / "patterns"
    assert patterns_dir.exists()
    assert len(list(patterns_dir.glob("chunk-*.prompt.md"))) > 0
    assert (patterns_dir / "manifest.json").exists()

    war_stories_dir = enrich_dir / "candidates" / "war-stories"
    assert war_stories_dir.exists()


def test_init_conversation_mining_synthesize(enrich_dir: Path, runtime_manifest: Path) -> None:
    mine_conversation.main([
        "--manifest", str(runtime_manifest),
        "--output", str(enrich_dir),
    ])
    subprocess.run(
        [sys.executable, str(INIT_SCRIPT), "--enrich-dir", str(enrich_dir), "--agent", "patterns"],
        cwd=REPO_ROOT,
        check=True,
    )

    # Simulate an agent output
    patterns_dir = enrich_dir / "candidates" / "patterns"
    for prompt_file in patterns_dir.glob("chunk-*.prompt.md"):
        output_file = patterns_dir / prompt_file.name.replace(".prompt.md", ".md")
        output_file.write_text("# Mined patterns\n- Cache-first is important.\n")

    code_assets_dir = enrich_dir / "candidates" / "code-assets"
    code_assets_dir.mkdir()
    (code_assets_dir / "chunk-000.md").write_text(
        "# Script candidate\n\nCODE_ASSET_MUST_NOT_ENTER_REFERENCE_SYNTHESIS\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(INIT_SCRIPT), "--enrich-dir", str(enrich_dir), "--synthesize"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    synthesize_prompt = enrich_dir / "candidates" / "synthesize.prompt.md"
    assert synthesize_prompt.exists()
    assert "Mined patterns" in synthesize_prompt.read_text(encoding="utf-8")
    assert "CODE_ASSET_MUST_NOT_ENTER_REFERENCE_SYNTHESIS" not in synthesize_prompt.read_text(encoding="utf-8")


def test_chunking_splits_large_message() -> None:
    counter = mine_conversation.get_token_counter("cl100k_base")
    big_text = "word " * 10000
    messages = [{
        "role": "user",
        "timestamp": None,
        "text": big_text,
        "source": "test",
        "source_line": 1,
    }]
    chunks = mine_conversation._chunk_messages(messages, 1000, counter)
    assert len(chunks) > 1
    # Each chunk is within budget (accounting for single-message overflow split)
    for chunk in chunks:
        assert chunk["tokens"] <= 1000


def test_chunking_enforces_budget_for_multitoken_unicode() -> None:
    counter = mine_conversation.get_token_counter("cl100k_base")
    original = "😀漢字🧪" * 5000
    messages = [{
        "role": "user",
        "timestamp": None,
        "text": original,
        "source": "source-001",
        "source_line": 1,
    }]

    chunks = mine_conversation._chunk_messages(messages, 1000, counter)

    assert "".join(chunk["messages"][0]["text"] for chunk in chunks) == original
    assert all(chunk["tokens"] <= 1000 for chunk in chunks)


def test_redactor_allowlist() -> None:
    redactor = mine_conversation.Redactor(allowlist=["sk-test-*"])
    text = "Key is sk-test-example and another is sk-kimi-fakekey123."
    redacted = redactor.redact(text)
    assert "sk-test-example" in redacted
    assert "sk-kimi-fakekey123" not in redacted
    assert redactor.counts["llm_provider_keys"] == 1


def test_redactor_does_not_allow_substring_matches() -> None:
    redactor = mine_conversation.Redactor(allowlist=["sk-test-*", "test"])
    real_looking = "sk-" + "kimi-con" + "test9abcdef"
    redacted = redactor.redact(f"Key is {real_looking}")
    assert real_looking not in redacted
    assert "<REDACTED-key>" in redacted


@pytest.mark.parametrize("invalid", ["", "*", "sk-*-test", "sk-**"])
def test_redactor_rejects_unsafe_allowlist_patterns(invalid: str) -> None:
    with pytest.raises(ValueError):
        mine_conversation.Redactor(allowlist=[invalid])


def test_redactor_exact_allowlist_does_not_match_suffix() -> None:
    exact = "sk-" + "fixture-exact"
    redactor = mine_conversation.Redactor(allowlist=[exact])
    assert redactor.redact(exact) == exact
    assert redactor.redact(exact + "-extra") == "<REDACTED-key>"


def test_redactor_exact_token_allowlist_uses_value_not_full_assignment() -> None:
    redactor = mine_conversation.Redactor(allowlist=["your-token-here"])
    text = (
        "Bearer your-token-here\n"
        "Authorization: your-token-here\n"
        "api_key=your-token-here"
    )
    assert redactor.redact(text) == text
    assert sum(redactor.counts.values()) == 0


@pytest.mark.parametrize(
    "timestamp,expected",
    [
        ("2025-12-31T23:59:59Z", False),
        ("2026-01-01T00:00:00Z", True),
        ("2026-06-01T12:00:00+08:00", True),
        ("2026-12-31T23:59:59Z", True),
        ("2027-01-01T00:00:00Z", False),
        ("2026-01-01T08:00:00+08:00", True),
        (None, False),
        ("not-a-time", False),
        ("2026-06-01T12:00:00", False),
    ],
)
def test_message_level_time_window(timestamp: str | None, expected: bool) -> None:
    since, until = mine_conversation._parse_time_window({
        "since": "2026-01-01T00:00:00Z",
        "until": "2026-12-31T23:59:59Z",
    })
    assert mine_conversation._message_in_window({"timestamp": timestamp}, since, until) is expected


@pytest.mark.parametrize(
    "since,until",
    [
        ("2026-01-01T00:00:00", "2026-12-31T23:59:59Z"),
        ("not-a-time", "2026-12-31T23:59:59Z"),
        ("2027-01-01T00:00:00Z", "2026-12-31T23:59:59Z"),
    ],
)
def test_invalid_time_window_fails_before_output(
    tmp_path: Path,
    since: str,
    until: str,
) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["sources"]["claude_code_sessions"]["since"] = since
    manifest["sources"]["claude_code_sessions"]["until"] = until
    manifest_path = tmp_path / "invalid-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / ".enrich" / "run"

    rc = mine_conversation.main([
        "--manifest", str(manifest_path),
        "--output", str(output),
    ])

    assert rc == 1
    assert not output.exists()


def test_relative_sources_resolve_from_manifest_directory(tmp_path: Path) -> None:
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()
    (transcripts / "session.jsonl").write_text(
        '{"type":"user","message":{"role":"user","content":"cache-first"},'
        '"timestamp":"2026-06-01T00:00:00Z"}\n',
        encoding="utf-8",
    )
    manifest = {
        "target_skill": "fixture",
        "topic_spec": {"keywords": ["cache-first"], "min_relevance_score": 0},
        "sources": {"claude_code_sessions": {"roots": ["transcripts"]}},
        "redaction": {"allowlisted_placeholders": [], "extra_patterns": []},
        "partitioning": {"chunk_tokens": 1000, "encoding_model": "cl100k_base"},
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / ".enrich" / "run"

    rc = mine_conversation.main([
        "--manifest", str(manifest_path),
        "--output", str(output),
    ])

    assert rc == 0
    run_manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert run_manifest["message_counts"]["parsed"] == 1


def test_missing_declared_source_fails_before_output(tmp_path: Path) -> None:
    manifest = {
        "target_skill": "fixture",
        "topic_spec": {"keywords": ["cache-first"], "min_relevance_score": 0},
        "sources": {"claude_code_sessions": {"roots": ["missing-transcripts"]}},
        "redaction": {"allowlisted_placeholders": [], "extra_patterns": []},
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / ".enrich" / "run"

    rc = mine_conversation.main([
        "--manifest", str(manifest_path),
        "--output", str(output),
    ])

    assert rc == 1
    assert not output.exists()


@pytest.mark.parametrize("chunk_tokens", [0, -1, True, 1.5, "1000"])
def test_invalid_chunk_budget_fails_before_output(tmp_path: Path, chunk_tokens) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["partitioning"]["chunk_tokens"] = chunk_tokens
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / ".enrich" / "run"

    rc = mine_conversation.main([
        "--manifest", str(manifest_path),
        "--output", str(output),
    ])

    assert rc == 1
    assert not output.exists()


def test_invalid_token_encoding_fails_before_output(tmp_path: Path) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["partitioning"]["encoding_model"] = "not-a-real-token-encoding"
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / ".enrich" / "run"

    rc = mine_conversation.main([
        "--manifest", str(manifest_path),
        "--output", str(output),
    ])

    assert rc == 1
    assert not output.exists()


def test_non_object_jsonl_record_does_not_drop_later_messages(tmp_path: Path) -> None:
    source = tmp_path / "manual.jsonl"
    source.write_text(
        "[]\n" + json.dumps({"text": "ExampleHub valid message"}) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "target_skill": "fixture",
        "topic_spec": {"keywords": ["examplehub"], "min_relevance_score": 0},
        "sources": {
            "claude_code_sessions": {"roots": []},
            "manual_exports": [str(source)],
        },
        "redaction": {"allowlisted_placeholders": [], "extra_patterns": []},
        "partitioning": {"chunk_tokens": 1000, "encoding_model": "cl100k_base"},
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / ".enrich" / "run"

    rc = mine_conversation.main([
        "--manifest", str(manifest_path),
        "--output", str(output),
    ])

    assert rc == 0
    run_manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert run_manifest["message_counts"]["parsed"] == 1
    assert run_manifest["message_counts"]["retained"] == 1


def test_nested_subagent_transcript_is_discovered(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    nested = root / "subagents"
    nested.mkdir(parents=True)
    (nested / "session.jsonl").write_text(
        json.dumps({
            "type": "user",
            "message": {"role": "user", "content": "ExampleHub nested transcript"},
            "timestamp": "2026-06-01T00:00:00Z",
        }) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "target_skill": "fixture",
        "topic_spec": {"keywords": ["examplehub"], "min_relevance_score": 0},
        "sources": {"claude_code_sessions": {"roots": [str(root)]}},
        "redaction": {"allowlisted_placeholders": [], "extra_patterns": []},
        "partitioning": {"chunk_tokens": 1000, "encoding_model": "cl100k_base"},
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / ".enrich" / "run"

    rc = mine_conversation.main([
        "--manifest", str(manifest_path),
        "--output", str(output),
    ])

    assert rc == 0
    run_manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert run_manifest["message_counts"]["parsed"] == 1
