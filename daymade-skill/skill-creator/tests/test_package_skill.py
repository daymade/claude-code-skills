import shlex
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

import scripts.package_skill as package_module
from scripts.package_skill import package_skill, should_exclude
from scripts.security_scan import calculate_skill_hash


@pytest.mark.parametrize(
    "rel_path,expected",
    [
        (Path("my-skill/__pycache__/foo.cpython-313.pyc"), True),
        (Path("my-skill/scripts/__pycache__/bar.py"), True),
        (Path("my-skill/node_modules/lodash/index.js"), True),
        (Path("my-skill/.pytest_cache/v/cache/nodeids"), True),
        (Path("my-skill/.ruff_cache/CACHEDIR.TAG"), True),
        (Path("my-skill/.DS_Store"), True),
        (Path("my-skill/.skill-regression-reviewed"), True),
        (Path("my-skill/.authorization"), True),
        (Path("my-skill/scripts/.authorization"), True),
        (Path("my-skill/.env.example"), False),
        (Path("my-skill/config/authorization.json"), False),
        (Path("my-skill/evals/evals.json"), True),
        (Path("my-skill/dist/my-skill.skill"), True),
        (Path("my-skill/tests/test_runtime.py"), True),
        (Path("my-skill/.enrich/run/manifest.json"), True),
        (Path("my-skill/.in_use/12345"), True),
        (Path("my-skill/scripts/nested/evals/helper.py"), False),
        (Path("my-skill/references/guide.md"), False),
        (Path("my-skill/SKILL.md"), False),
    ],
)
def test_should_exclude(rel_path, expected):
    assert should_exclude(rel_path) is expected


def test_included_eval_fixture_can_use_exact_authorization_filename():
    assert should_exclude(Path("my-skill/evals/.authorization"), include_evals=True) is False


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

    artifact = package_skill(skill_dir, new_skill=True)

    assert artifact is not None
    expected = skill_dir / "dist" / "test-skill.skill"
    assert artifact == expected
    assert artifact.exists()
    assert artifact.parent == skill_dir / "dist"


def test_package_skill_custom_output_dir(tmp_path):
    skill_dir = _make_minimal_skill(tmp_path, "test-skill")
    _add_security_marker(skill_dir)
    custom_dir = tmp_path / "custom-artifacts"

    artifact = package_skill(skill_dir, output_dir=str(custom_dir), new_skill=True)

    assert artifact is not None
    assert artifact == custom_dir / "test-skill.skill"
    assert artifact.exists()
    # Default dist/ should NOT be created when a custom dir is provided.
    assert not (skill_dir / "dist").exists()


def test_package_skill_rejects_custom_output_inside_shipping_tree(tmp_path, capsys):
    skill_dir = _make_minimal_skill(tmp_path, "test-skill")
    _add_security_marker(skill_dir)

    artifact = package_skill(
        skill_dir,
        output_dir=skill_dir / "out",
        new_skill=True,
    )

    assert artifact is None
    assert not (skill_dir / "out").exists()
    assert "must be under the excluded dist/ root" in capsys.readouterr().out


def test_package_skill_artifact_contains_skill_files(tmp_path):
    skill_dir = _make_minimal_skill(tmp_path, "test-skill")
    (skill_dir / "references").mkdir()
    (skill_dir / "references" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (skill_dir / "tests").mkdir()
    (skill_dir / "tests" / "test_runtime.py").write_text("assert True\n", encoding="utf-8")
    (skill_dir / ".enrich" / "run").mkdir(parents=True)
    (skill_dir / ".enrich" / "run" / "manifest.json").write_text("{}\n", encoding="utf-8")
    (skill_dir / ".in_use").mkdir()
    (skill_dir / ".in_use" / "12345").write_text("runtime lock\n", encoding="utf-8")
    (skill_dir / ".ruff_cache").mkdir()
    (skill_dir / ".ruff_cache" / "CACHEDIR.TAG").write_text("cache\n", encoding="utf-8")
    (skill_dir / ".authorization").write_text("local runtime grant\n", encoding="utf-8")
    (skill_dir / "scripts" / ".authorization").parent.mkdir(exist_ok=True)
    (skill_dir / "scripts" / ".authorization").write_text(
        "nested local runtime grant\n", encoding="utf-8"
    )
    (skill_dir / ".env.example").write_text("TOKEN=<token>\n", encoding="utf-8")
    (skill_dir / "config").mkdir()
    (skill_dir / "config" / "authorization.json").write_text("{}\n", encoding="utf-8")
    _add_security_marker(skill_dir)

    artifact = package_skill(skill_dir, new_skill=True)

    with zipfile.ZipFile(artifact, "r") as zf:
        names = zf.namelist()
    assert any("SKILL.md" in n for n in names)
    assert any("references/guide.md" in n for n in names)
    # Excluded files should not be packaged.
    assert not any("__pycache__" in n for n in names)
    assert not any(".security-scan-passed" in n for n in names)
    assert not any("tests/" in n for n in names)
    assert not any(".enrich/" in n for n in names)
    assert not any(".in_use/" in n for n in names)
    assert not any(".ruff_cache/" in n for n in names)
    assert not any(n.endswith("/.authorization") for n in names)
    assert any(n.endswith("/.env.example") for n in names)
    assert any(n.endswith("/config/authorization.json") for n in names)


def test_package_skill_artifact_excludes_dist_directory(tmp_path):
    skill_dir = _make_minimal_skill(tmp_path, "test-skill")
    (skill_dir / "dist").mkdir()
    (skill_dir / "dist" / "old-artifact.skill").write_text("fake", encoding="utf-8")
    _add_security_marker(skill_dir)

    artifact = package_skill(skill_dir, new_skill=True)

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

    artifact = package_skill(skill_dir, new_skill=True)

    assert artifact is None
    captured = capsys.readouterr()
    assert "Security scan not completed" in captured.out


def test_security_recovery_hint_preserves_tool_and_skill_arguments(
    tmp_path, capsys, monkeypatch
):
    skill_dir = _make_minimal_skill(tmp_path, "recovery-skill")
    creator_root = tmp_path / "creator's $project [copy]"
    monkeypatch.setattr(package_module, "PACKAGE_ROOT", creator_root)
    monkeypatch.setattr(package_module, "SCRIPT_DIR", creator_root / "scripts")

    assert package_skill(skill_dir, new_skill=True) is None

    output = capsys.readouterr().out
    command = next(
        line.split("POSIX shell: ", 1)[1]
        for line in output.splitlines()
        if "POSIX shell: " in line
    )
    assert shlex.split(command) == [
        "uv", "run", "--project", str(creator_root), "--frozen", "python",
        str(creator_root / "scripts" / "security_scan.py"), str(skill_dir),
    ]
    assert "PowerShell: & " in output
    assert not (skill_dir / ".security-scan-passed").exists()


@pytest.mark.parametrize("shell", ["posix", "powershell"])
def test_security_recovery_hint_scans_original_skill_and_finishes_package(
    tmp_path, shell
):
    for tool in ("uv", "gitleaks"):
        if not shutil.which(tool):
            pytest.skip(f"Real scan recovery requires {tool}")
    executable = shutil.which("sh" if shell == "posix" else "pwsh")
    if not executable:
        pytest.skip(f"No {shell} shell available")

    # Unquoted interpolation would create sentinel files in the caller directory.
    parent = tmp_path / "author's $HOME [draft] ; $(touch injected) `touch injected-backtick`"
    parent.mkdir()
    skill_dir = _make_minimal_skill(parent, "recovery-skill")
    (skill_dir / "task.txt").write_text("Recovered task content.\n", encoding="utf-8")
    caller = tmp_path / "unrelated caller"
    caller.mkdir()
    # A same-named directory and an invalid caller project must not redirect scanning.
    decoy = _make_minimal_skill(caller, "recovery-skill")
    (caller / "pyproject.toml").write_text("not valid TOML\n", encoding="utf-8")
    relative_skill = Path("..") / parent.name / skill_dir.name
    package_argv = [
        sys.executable, str(package_module.SCRIPT_DIR / "package_skill.py"),
        str(relative_skill), "--new-skill",
    ]

    blocked = subprocess.run(package_argv, cwd=caller, capture_output=True, text=True)
    assert blocked.returncode == 1, blocked.stdout + blocked.stderr
    assert "Security scan not completed" in blocked.stdout
    assert not (skill_dir / "dist").exists()
    label = "POSIX shell: " if shell == "posix" else "PowerShell: "
    command = next(
        line.split(label, 1)[1]
        for line in blocked.stdout.splitlines()
        if label in line
    )
    shell_argv = (
        [executable, "-c", command]
        if shell == "posix"
        else [executable, "-NoProfile", "-NonInteractive", "-Command", command]
    )

    scanned = subprocess.run(shell_argv, cwd=caller, capture_output=True, text=True)
    assert scanned.returncode == 0, scanned.stdout + scanned.stderr
    assert (skill_dir / ".security-scan-passed").is_file()
    assert not (decoy / ".security-scan-passed").exists()
    assert not (caller / "injected").exists()
    assert not (caller / "injected-backtick").exists()

    packaged = subprocess.run(package_argv, cwd=caller, capture_output=True, text=True)
    assert packaged.returncode == 0, packaged.stdout + packaged.stderr
    artifact = skill_dir / "dist" / "recovery-skill.skill"
    with zipfile.ZipFile(artifact) as archive:
        assert archive.read("recovery-skill/task.txt") == b"Recovered task content.\n"
        assert "recovery-skill/SKILL.md" in archive.namelist()
        assert not any(".security-scan-passed" in name for name in archive.namelist())

    # Keep the stale-content gate fail-closed after a genuine successful recovery.
    original_zip = artifact.read_bytes()
    (skill_dir / "task.txt").write_text("Changed after scan.\n", encoding="utf-8")
    stale = subprocess.run(package_argv, cwd=caller, capture_output=True, text=True)
    assert stale.returncode == 1, stale.stdout + stale.stderr
    assert "Skill content changed since last security scan" in stale.stdout
    assert artifact.read_bytes() == original_zip


@pytest.mark.parametrize("corruption", ["duplicate", "trailing-garbage"])
def test_security_marker_rejects_ambiguous_or_malformed_hash_line(tmp_path, corruption):
    skill_dir = _make_minimal_skill(tmp_path, "test-skill")
    _add_security_marker(skill_dir)
    marker = skill_dir / ".security-scan-passed"
    valid_hash = calculate_skill_hash(skill_dir)
    if corruption == "duplicate":
        marker.write_text(
            marker.read_text(encoding="utf-8") + f"Content hash: {'0' * 64}\n",
            encoding="utf-8",
        )
    else:
        marker.write_text(
            f"Security scan passed\nContent hash: {valid_hash} trailing\n",
            encoding="utf-8",
        )

    valid, message = package_module.validate_security_marker(skill_dir)

    assert valid is False
    assert "hash" in message.lower()


def test_package_skill_missing_skill_md(tmp_path, capsys):
    skill_dir = tmp_path / "bad-skill"
    skill_dir.mkdir()

    artifact = package_skill(skill_dir)

    assert artifact is None
    captured = capsys.readouterr()
    assert "SKILL.md not found" in captured.out


def test_package_skill_blocks_changed_existing_skill_without_regression_review(tmp_path, capsys, monkeypatch):
    skill_dir = _make_minimal_skill(tmp_path, "changed-skill")
    _add_security_marker(skill_dir)
    monkeypatch.setattr(
        package_module,
        "requires_regression_review",
        lambda _path, **_kwargs: (True, "existing Git-tracked skill has no attestation"),
    )

    artifact = package_skill(skill_dir)

    assert artifact is None
    assert "Existing skills require their completed old-vs-new capability review" in capsys.readouterr().out


def test_package_skill_accepts_current_completed_regression_review(tmp_path, monkeypatch):
    skill_dir = _make_minimal_skill(tmp_path, "changed-skill")
    _add_security_marker(skill_dir)
    review = tmp_path / "review.json"
    review.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(package_module, "requires_regression_review", lambda _path, **_kwargs: (True, "changed"))
    monkeypatch.setattr(package_module, "verify_review_for_after", lambda _review, _after: (True, []))
    monkeypatch.setattr(package_module, "create_regression_marker", lambda _after, _review: None)

    artifact = package_skill(skill_dir, regression_review=review)

    assert artifact is not None
    assert artifact.exists()


def test_package_uses_attested_snapshot_when_live_source_changes(tmp_path, monkeypatch):
    skill_dir = _make_minimal_skill(tmp_path, "test-skill")
    _add_security_marker(skill_dir)
    original_validate = package_module.validate_security_marker

    def mutate_live_during_staged_validation(candidate_skill):
        if Path(candidate_skill).resolve() != skill_dir.resolve():
            with (skill_dir / "SKILL.md").open("a", encoding="utf-8") as handle:
                handle.write("late live mutation\n")
        return original_validate(candidate_skill)

    monkeypatch.setattr(
        package_module, "validate_security_marker", mutate_live_during_staged_validation
    )

    artifact = package_skill(skill_dir, new_skill=True)

    assert artifact is not None
    with zipfile.ZipFile(artifact, "r") as zf:
        packaged = zf.read("test-skill/SKILL.md").decode("utf-8")
    assert "late live mutation" not in packaged
