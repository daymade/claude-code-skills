import json
from pathlib import Path
from types import SimpleNamespace

import scripts.security_scan as security_scan
from scripts.package_skill import validate_security_marker


def _make_scan_fixture(tmp_path: Path) -> Path:
    skill_dir = tmp_path / "test-skill"
    (skill_dir / "evals").mkdir(parents=True)
    (skill_dir / ".enrich" / "run").mkdir(parents=True)
    (skill_dir / "tests").mkdir()
    (skill_dir / "dist").mkdir()
    (skill_dir / "scripts").mkdir()
    (skill_dir / "SKILL.md").write_text("# Test skill\n", encoding="utf-8")
    (skill_dir / "evals" / "cases.json").write_text("[]\n", encoding="utf-8")
    (skill_dir / ".enrich" / "run" / "chunks.jsonl").write_text("ignored\n", encoding="utf-8")
    (skill_dir / "tests" / "test_runtime.py").write_text("ignored\n", encoding="utf-8")
    (skill_dir / "dist" / "old.skill").write_text("ignored\n", encoding="utf-8")
    (skill_dir / "scripts" / "client.py").write_text("print('ok')\n", encoding="utf-8")
    return skill_dir


def test_run_gitleaks_stages_packaging_superset_only(tmp_path, monkeypatch):
    skill_dir = _make_scan_fixture(tmp_path)

    def fake_run(args, **_kwargs):
        source = Path(args[args.index("--source") + 1])
        assert source != skill_dir
        assert (source / "SKILL.md").exists()
        assert (source / "scripts" / "client.py").exists()
        assert (source / "evals" / "cases.json").exists()
        assert not (source / ".enrich").exists()
        assert not (source / "tests").exists()
        assert not (source / "dist").exists()
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(security_scan.subprocess, "run", fake_run)

    result = security_scan.run_gitleaks(skill_dir)

    assert result is not None
    assert result.findings == []


def test_run_gitleaks_remaps_staged_finding_to_source(tmp_path, monkeypatch):
    skill_dir = _make_scan_fixture(tmp_path)

    def fake_run(args, **_kwargs):
        source = Path(args[args.index("--source") + 1])
        report = Path(args[args.index("--report-path") + 1])
        report.write_text(
            json.dumps([
                {
                    "File": str(source / "scripts" / "client.py"),
                    "StartLine": 1,
                    "RuleID": "generic-api-key",
                }
            ]),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=1, stdout="", stderr="")

    monkeypatch.setattr(security_scan.subprocess, "run", fake_run)

    result = security_scan.run_gitleaks(skill_dir)

    assert result is not None
    assert result.findings[0]["File"] == str(skill_dir / "scripts" / "client.py")


def test_run_gitleaks_exit_one_without_findings_fails_closed(tmp_path, monkeypatch):
    skill_dir = _make_scan_fixture(tmp_path)

    def fake_run(args, **_kwargs):
        report = Path(args[args.index("--report-path") + 1])
        report.write_text("[]\n", encoding="utf-8")
        return SimpleNamespace(returncode=1, stdout="", stderr="simulated scan error")

    monkeypatch.setattr(security_scan.subprocess, "run", fake_run)

    assert security_scan.run_gitleaks(skill_dir) is None


def test_run_gitleaks_unexpected_exit_code_fails_closed(tmp_path, monkeypatch):
    skill_dir = _make_scan_fixture(tmp_path)

    def fake_run(_args, **_kwargs):
        return SimpleNamespace(returncode=126, stdout="", stderr="cannot execute")

    monkeypatch.setattr(security_scan.subprocess, "run", fake_run)

    assert security_scan.run_gitleaks(skill_dir) is None


def test_scanned_hash_cannot_attest_post_stage_mutation(tmp_path, monkeypatch):
    skill_dir = _make_scan_fixture(tmp_path)
    scanned = {}

    def fake_run(args, **_kwargs):
        source = Path(args[args.index("--source") + 1])
        scanned["hash"] = security_scan.calculate_skill_hash(source)
        with (skill_dir / "SKILL.md").open("a", encoding="utf-8") as handle:
            handle.write("late mutation\n")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(security_scan.subprocess, "run", fake_run)

    result = security_scan.run_gitleaks(skill_dir)

    assert result is not None
    assert result.content_hash == scanned["hash"]
    assert result.content_hash != security_scan.calculate_skill_hash(skill_dir)
    security_scan.create_security_marker(skill_dir, result.content_hash)
    assert validate_security_marker(skill_dir)[0] is False


def test_pattern_scan_uses_same_packaging_superset(tmp_path):
    skill_dir = _make_scan_fixture(tmp_path)
    shipping_path = "/" + "Users" + "/fixture/private"
    ignored_path = "/" + "Users" + "/ignored/private"
    (skill_dir / ".shipping-config").write_text(
        json.dumps({"path": shipping_path}) + "\n", encoding="utf-8"
    )
    (skill_dir / "template.html").write_text(
        f"<p>{shipping_path}</p>\n", encoding="utf-8"
    )
    (skill_dir / "asset.bin").write_bytes(b"\0" + shipping_path.encode("utf-8"))
    (skill_dir / ".enrich" / "run" / "private.json").write_text(
        json.dumps({"path": ignored_path}) + "\n", encoding="utf-8"
    )

    issues, _stats = security_scan.scan_skill_patterns(skill_dir)

    assert any(issue.file_path.endswith(".shipping-config") for issue in issues)
    assert any(issue.file_path.endswith("template.html") for issue in issues)
    assert not any(issue.file_path.endswith("asset.bin") for issue in issues)
    assert not any(".enrich" in issue.file_path for issue in issues)
