import json
from pathlib import Path
from types import SimpleNamespace

import scripts.security_scan as security_scan


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

    assert security_scan.run_gitleaks(skill_dir) == []


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

    findings = security_scan.run_gitleaks(skill_dir)

    assert findings is not None
    assert findings[0]["File"] == str(skill_dir / "scripts" / "client.py")


def test_pattern_scan_uses_same_packaging_superset(tmp_path):
    skill_dir = _make_scan_fixture(tmp_path)
    shipping_path = "/" + "Users" + "/fixture/private"
    ignored_path = "/" + "Users" + "/ignored/private"
    (skill_dir / ".visible-config.json").write_text(
        json.dumps({"path": shipping_path}) + "\n", encoding="utf-8"
    )
    (skill_dir / ".enrich" / "run" / "private.json").write_text(
        json.dumps({"path": ignored_path}) + "\n", encoding="utf-8"
    )

    issues, _stats = security_scan.scan_skill_patterns(skill_dir)

    assert any(issue.file_path.endswith(".visible-config.json") for issue in issues)
    assert not any(".enrich" in issue.file_path for issue in issues)
