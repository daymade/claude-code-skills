"""Opt-in background artifacts through the actual CLI and persisted configuration."""
import json
from pathlib import Path

import pytest

from .test_occurrence_contract import isolated, cli
from cli import commands
from utils.config import Config, intermediate_directory, reset_config


def configure(tmp_path, root):
    config = tmp_path / "config" / "config.json"
    config.write_text(json.dumps({"paths": {"intermediate_root": str(root)}}))
    reset_config()


def seed_rules():
    repository = commands._get_service().repository
    repository.add_correction("alphaa", "alpha", domain="fixture", confidence=0.8)
    repository.add_correction("gammma", "gamma", domain="fixture", confidence=1.0)


def test_default_background_run_retains_pending_without_annotation(isolated, tmp_path, monkeypatch, capsys):
    root = tmp_path / "background artifacts"
    configure(tmp_path, root)
    seed_rules()
    vault = tmp_path / "vault"
    vault.mkdir()
    transcript = vault / "meeting notes.md"
    transcript.write_text("alphaa gammma.\n")
    status, result = cli(monkeypatch, capsys, "--input", transcript, "--stage", 1, "--domain", "fixture")
    assert status == 0, result
    assert result["applied"] == result["deferred"] == result["review_enqueued"] == 1
    assert sorted(p.name for p in vault.iterdir()) == [transcript.name]
    work = intermediate_directory(transcript)
    assert Path(result["output_path"]).parent == work
    assert Path(result["needs_review_path"]).parent == work
    assert Path(result["output_path"]).read_text() == "alphaa gamma.\n"
    assert transcript.read_text() == "alphaa gammma.\n"
    status, promoted = cli(monkeypatch, capsys, "--input", transcript, "--stage", 1, "--domain", "fixture")
    assert status == 0 and Path(promoted["output_path"]) == transcript
    assert transcript.read_text() == "alphaa gamma.\n"
    assert list(vault.iterdir()) == [transcript]
    before = isolated.list_items(file_path=str(transcript.resolve()))
    assert len(before) == 1 and before[0].status == "pending"
    # The ordinary closure consumer discovers the configured and registered
    # reports, retains unresolved evidence, and never converts it to a verdict.
    status, report = cli(monkeypatch, capsys, "--close-sidecars", "--input", transcript, "--dry-run")
    assert status == 1 and report["verdict"] == "open", report
    assert Path(result["needs_review_path"]).is_file()
    assert isolated.get(before[0].id).to_dict() == before[0].to_dict()


def test_explicit_paths_win_without_changing_default_report_policy(isolated, tmp_path, monkeypatch, capsys):
    configure(tmp_path, tmp_path / "background")
    seed_rules()
    transcript = tmp_path / "notes.md"
    transcript.write_text("alphaa gammma.\n")
    explicit = tmp_path / "chosen" / "result.md"
    report_dir = tmp_path / "chosen reports"
    status, result = cli(monkeypatch, capsys, "--input", transcript, "--stage", 1,
        "--domain", "fixture", "--output", explicit, "--sidecar-dir", report_dir)
    assert status == 0, result
    assert Path(result["output_path"]) == explicit
    assert Path(result["needs_review_path"]).parent == report_dir


def test_unconfigured_default_and_same_basename_identity(isolated, tmp_path, monkeypatch, capsys):
    seed_rules()
    transcript = tmp_path / "notes.md"
    transcript.write_text("alphaa gammma.\n")
    status, result = cli(monkeypatch, capsys, "--input", transcript, "--stage", 1, "--domain", "fixture")
    assert status == 0 and Path(result["output_path"]).parent == tmp_path
    assert intermediate_directory(transcript) is None
    configure(tmp_path, tmp_path / "background")
    first = intermediate_directory(tmp_path / "one" / "same.md")
    second = intermediate_directory(tmp_path / "two" / "same.md")
    assert first != second and first.parent == second.parent


def test_output_directory_also_pins_reports_for_existing_callers(isolated, tmp_path, monkeypatch, capsys):
    configure(tmp_path, tmp_path / "background")
    seed_rules()
    transcript = tmp_path / "notes.md"
    transcript.write_text("alphaa gammma.\n")
    output = tmp_path / "caller workspace"
    status, result = cli(monkeypatch, capsys, "--input", transcript, "--stage", 1,
        "--domain", "fixture", "--output", output)
    assert status == 0, result
    assert Path(result["output_path"]).parent == output
    assert Path(result["needs_review_path"]).parent == output


@pytest.mark.parametrize("value", ["", " ", "relative/path", False, 4, []])
def test_invalid_work_root_is_not_silently_disabled(tmp_path, value):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"paths": {"intermediate_root": value}}))
    with pytest.raises((ValueError, TypeError)):
        Config.from_file(config)


@pytest.mark.parametrize("paths", [{}, {"intermediate_root": None}])
def test_missing_or_null_preserves_legacy_config(tmp_path, paths):
    source = tmp_path / "config.json"
    source.write_text(json.dumps({"paths": paths}))
    assert Config.from_file(source).paths.intermediate_root is None


def test_config_writer_and_reader_keep_work_root(tmp_path):
    source = tmp_path / "config.json"
    root = tmp_path / "background"
    source.write_text(json.dumps({"paths": {"intermediate_root": str(root)}}))
    config = Config.from_file(source)
    saved = tmp_path / "saved.json"
    config.save_to_file(saved)
    assert Config.from_file(saved).paths.intermediate_root == root
