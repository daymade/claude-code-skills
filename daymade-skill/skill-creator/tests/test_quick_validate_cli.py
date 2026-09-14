"""The CLI accepts its documented audience spelling and preserves validation."""
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("flags", [["--audience", "public"], ["--audience=public"]])
@pytest.mark.parametrize("valid", [True, False])
def test_documented_audience_forms(tmp_path, flags, valid):
    skill = tmp_path / "cli-example"
    skill.mkdir()
    if valid:
        (skill / "SKILL.md").write_text(
            "---\nname: cli-example\ndescription: Validate a CLI example.\n---\n"
            "# CLI example\n\nUse this skill to validate an example.\n"
        )
    result = subprocess.run(
        [sys.executable, "-m", "scripts.quick_validate", str(skill), *flags],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == (0 if valid else 1), result.stdout + result.stderr
    assert ("Skill is valid!" if valid else "SKILL.md not found") in result.stdout


@pytest.mark.parametrize("flags", [["--audience"], ["--audience", "typo"], ["--unknown"]])
def test_malformed_options_fail_before_validation(tmp_path, flags):
    result = subprocess.run(
        [sys.executable, "-m", "scripts.quick_validate", str(tmp_path), *flags],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert "error:" in result.stderr
    assert "SKILL.md not found" not in result.stdout
