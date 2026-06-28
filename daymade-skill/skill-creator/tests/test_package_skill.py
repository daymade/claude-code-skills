import zipfile
from pathlib import Path

import pytest

from scripts.package_skill import package_skill, should_exclude
from scripts.security_scan import calculate_skill_hash


@pytest.mark.parametrize(
    "rel_path,expected",
    [
        (Path("my-skill/__pycache__/foo.cpython-313.pyc"), True),
        (Path("my-skill/scripts/__pycache__/bar.py"), True),
        (Path("my-skill/node_modules/lodash/index.js"), True),
        (Path("my-skill/.pytest_cache/v/cache/nodeids"), True),
        (Path("my-skill/.DS_Store"), True),
        (Path("my-skill/evals/evals.json"), True),
        (Path("my-skill/dist/my-skill.skill"), True),
        (Path("my-skill/scripts/nested/evals/helper.py"), False),
        (Path("my-skill/references/guide.md"), False),
        (Path("my-skill/SKILL.md"), False),
    ],
)
def test_should_exclude(rel_path, expected):
    assert should_exclude(rel_path) is expected


def _make_minimal_skill(tmp_path: Path, name: str = "minimal-skill") -> Path:
    """Create a minimal valid skill folder and its security marker."""
    skill_dir = tmp_path / name
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: A minimal skill for testing\n---\n\n# Minimal\n",
        encoding="utf-8",
    )
    return skill_dir


def _add_security_marker(skill_dir: Path) -> None:
    """Write a .security-scan-passed marker matching the current content hash."""
    content_hash = calculate_skill_hash(skill_dir)
    (skill_dir / ".security-scan-passed").write_text(
        f"Security scan passed\nContent hash: {content_hash}\n", encoding="utf-8"
    )


def test_package_skill_default_output_path(tmp_path):
    skill_dir = _make_minimal_skill(tmp_path, "test-skill")
    _add_security_marker(skill_dir)

    artifact = package_skill(skill_dir)

    assert artifact is not None
    expected = skill_dir / "dist" / "test-skill.skill"
    assert artifact == expected
    assert artifact.exists()
    assert artifact.parent == skill_dir / "dist"


def test_package_skill_custom_output_dir(tmp_path):
    skill_dir = _make_minimal_skill(tmp_path, "test-skill")
    _add_security_marker(skill_dir)
    custom_dir = tmp_path / "custom-artifacts"

    artifact = package_skill(skill_dir, output_dir=str(custom_dir))

    assert artifact is not None
    assert artifact == custom_dir / "test-skill.skill"
    assert artifact.exists()
    # Default dist/ should NOT be created when a custom dir is provided.
    assert not (skill_dir / "dist").exists()


def test_package_skill_artifact_contains_skill_files(tmp_path):
    skill_dir = _make_minimal_skill(tmp_path, "test-skill")
    (skill_dir / "references").mkdir()
    (skill_dir / "references" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    _add_security_marker(skill_dir)

    artifact = package_skill(skill_dir)

    with zipfile.ZipFile(artifact, "r") as zf:
        names = zf.namelist()
    assert any("SKILL.md" in n for n in names)
    assert any("references/guide.md" in n for n in names)
    # Excluded files should not be packaged.
    assert not any("__pycache__" in n for n in names)
    assert not any(".security-scan-passed" in n for n in names)


def test_package_skill_artifact_excludes_dist_directory(tmp_path):
    skill_dir = _make_minimal_skill(tmp_path, "test-skill")
    (skill_dir / "dist").mkdir()
    (skill_dir / "dist" / "old-artifact.skill").write_text("fake", encoding="utf-8")
    _add_security_marker(skill_dir)

    artifact = package_skill(skill_dir)

    with zipfile.ZipFile(artifact, "r") as zf:
        names = zf.namelist()
    assert not any("dist/" in n for n in names)
    assert any("SKILL.md" in n for n in names)


def test_package_skill_missing_security_marker(tmp_path, capsys):
    skill_dir = tmp_path / "unsafe-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: unsafe-skill\ndescription: no security scan\n---\n", encoding="utf-8"
    )

    artifact = package_skill(skill_dir)

    assert artifact is None
    captured = capsys.readouterr()
    assert "Security scan not completed" in captured.out


def test_package_skill_missing_skill_md(tmp_path, capsys):
    skill_dir = tmp_path / "bad-skill"
    skill_dir.mkdir()

    artifact = package_skill(skill_dir)

    assert artifact is None
    captured = capsys.readouterr()
    assert "SKILL.md not found" in captured.out
