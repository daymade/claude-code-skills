"""JSON keeps validity, advisory diagnostics and parser failures distinct."""
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


def make_skill(tmp_path, guide=None, linked=True):
    skill = tmp_path / "validation-example"
    skill.mkdir()
    body = "---\nname: validation-example\ndescription: Validate an example.\n---\n# Example\n"
    if guide is not None:
        refs = skill / "references"
        refs.mkdir()
        (refs / "guide.md").write_text(guide)
        if linked:
            body += "\nRead [guide](references/guide.md).\n"
    (skill / "SKILL.md").write_text(body)
    return skill


def invoke(skill, *flags):
    return subprocess.run(
        [sys.executable, "-m", "scripts.quick_validate", str(skill), *flags],
        cwd=ROOT, capture_output=True, text=True,
    )


def test_healthy_json_has_no_warning(tmp_path):
    skill = make_skill(tmp_path)
    result = invoke(skill, "--audience", "public", "--format", "json")
    report = json.loads(result.stdout)
    assert result.returncode == 0 and report["valid"] is True
    assert report["schema_version"] == 1
    assert report["warnings"] == [] and report["diagnostics"] == []
    assert report["message"] == "Skill is valid!"


def test_missing_reference_warning_is_not_invalidity(tmp_path):
    skill = make_skill(tmp_path, "Read `scripts/ci/test-suites.txt`.\n")
    result = invoke(skill, "--audience=public", "--format=json")
    report = json.loads(result.stdout)
    assert result.returncode == 0 and report["valid"] is True
    assert any("scripts/ci/test-suites.txt" in line for line in report["warnings"])
    text = invoke(skill, "--audience", "public")
    assert text.returncode == result.returncode
    assert text.stdout == "\n".join([*report["diagnostics"], report["message"]]) + "\n"


def test_explicit_repository_link_does_not_become_bundle_path(tmp_path):
    skill = make_skill(tmp_path, "[CI registry](https://example.invalid/repo/blob/main/scripts/ci/test-suites.txt)\n")
    report = json.loads(invoke(skill, "--audience", "public", "--format", "json").stdout)
    assert report["valid"] is True and report["warnings"] == []


def test_missing_skill_is_invalid_with_parseable_json(tmp_path):
    result = invoke(tmp_path, "--audience", "public", "--format", "json")
    report = json.loads(result.stdout)
    assert result.returncode == 1 and report["valid"] is False
    assert "SKILL.md not found" in report["message"]


def test_unreachable_reference_remains_an_advisory(tmp_path):
    skill = make_skill(tmp_path, "# Guide\n", linked=False)
    result = invoke(skill, "--audience", "public", "--format", "json")
    report = json.loads(result.stdout)
    assert result.returncode == 0 and report["valid"] is True
    assert any("unreachable" in line.lower() for line in report["warnings"])


def test_private_portability_note_is_not_public_warning(tmp_path):
    synthetic_home = "/" + "Users" + "/synthetic_operator/local-notes.md"
    skill = make_skill(tmp_path, f"Use {synthetic_home} for this private task.\n")
    result = invoke(skill, "--audience", "private", "--format", "json")
    report = json.loads(result.stdout)
    assert result.returncode == 0 and report["valid"] is True
    assert report["warnings"] == []
    assert any("PRIVATE" in line or "private" in line for line in report["diagnostics"])


@pytest.mark.parametrize("flags", [["--format"], ["--format", ""], ["--format", "unknown"]])
def test_invalid_or_empty_format_fails_before_validation(tmp_path, flags):
    result = invoke(tmp_path, "--audience", "public", *flags)
    assert result.returncode == 2
    assert result.stdout == "" and "error:" in result.stderr
