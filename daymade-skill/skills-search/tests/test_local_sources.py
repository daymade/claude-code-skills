"""Exercise the real offline adapter with synthetic repository/configuration state."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "local_sources.py"
spec = importlib.util.spec_from_file_location("local_sources", SCRIPT)
local = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local)


class LocalSourcesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "config" / "sources.json"
        self.cache = self.root / "cache"
        self.env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}

    def git(self, root, *args):
        return subprocess.check_output(["git", "-C", str(root), *args], env=self.env, stderr=subprocess.PIPE).decode().strip()

    def repo(self, name):
        root = self.root / name
        root.mkdir()
        self.git(root, "init", "-b", "main")
        self.git(root, "config", "user.name", "Fixture")
        self.git(root, "config", "user.email", "fixture@example.invalid")
        self.git(root, "remote", "add", "origin", f"https://github.com/example/{name}.git")
        (root / ".claude-plugin").mkdir()
        (root / ".claude-plugin" / "marketplace.json").write_text(json.dumps({"plugins": [
            {"name": "suite", "source": "./bundle", "skills": ["./browser", "./writer"]}]}))
        for entry, description in [("browser", "Chrome 登录 saved browser autofill"), ("writer", "Writes reports")]:
            folder = root / "bundle" / entry
            folder.mkdir(parents=True)
            (folder / "SKILL.md").write_text(f"---\nname: {entry}\ndescription: >-\n  {description}\n---\n# Actual body\n")
        fixture = root / "tests" / "fixture"
        fixture.mkdir(parents=True)
        (fixture / "SKILL.md").write_text("---\nname: fake\ndescription: Chrome fixture only\n---\n")
        self.git(root, "add", "--all")
        self.git(root, "commit", "-m", "fixture")
        return root

    def cli(self, *args):
        result = subprocess.run([sys.executable, str(SCRIPT), "--config", str(self.config), "--cache", str(self.cache), *args],
                                env=self.env, text=True, capture_output=True)
        return result.returncode, json.loads(result.stdout)

    def register(self, name, tier="owned"):
        repo = self.repo(name)
        rc, result = self.cli("register", "--id", name, "--path", str(repo), "--tier", tier, "--ref", "main")
        self.assertEqual(rc, 0, result)
        return repo

    def test_persistent_three_sources_and_limit_does_not_reduce_coverage(self):
        for name in ("public", "team", "private"):
            self.register(name)
        rc, listing = self.cli("list")
        self.assertEqual(rc, 0)
        self.assertEqual(len(listing["sources"]), 3)
        rc, result = self.cli("search", "Chrome 登录", "--limit", "1")
        self.assertEqual(rc, 0)
        self.assertEqual(len(result["coverage"]), 3)
        self.assertEqual([s["examined"] for s in result["coverage"]], [2, 2, 2])
        self.assertEqual(result["matched_count"], 3)
        self.assertEqual(len(result["candidates"]), 1)
        self.assertFalse(result["automatic_expansion"])
        self.assertTrue(all(not s["cache_hit"] for s in result["coverage"]))
        rc, cached = self.cli("search", "Chrome")
        self.assertEqual(rc, 0)
        self.assertTrue(all(s["cache_hit"] for s in cached["coverage"]))

    def test_missing_source_is_not_a_successful_empty_scan(self):
        self.register("public")
        other = self.register("private")
        other.rename(self.root / "unmounted")
        rc, result = self.cli("search", "Chrome")
        self.assertEqual(rc, 1)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(len(result["coverage"]), 2)
        self.assertTrue(result["candidates"])
        self.assertEqual(result["coverage"][0]["status"], "unavailable")

    def test_missing_empty_and_malformed_config_fail_explicitly(self):
        self.assertEqual(self.cli("search", "Chrome")[0], 2)
        self.config.parent.mkdir(parents=True)
        for data in (None, {}, {"schema": 1, "sources": []}, {"schema": 1, "sources": [{}]}):
            self.config.write_text(json.dumps(data))
            self.assertEqual(self.cli("search", "Chrome")[0], 2, data)
        self.config.write_text("broken")
        self.assertEqual(self.cli("list")[0], 2)

    def test_invalid_registration_and_lock_preserve_config(self):
        self.register("public")
        original = self.config.read_bytes()
        repo = self.repo("second")
        rc, _ = self.cli("register", "--id", "", "--path", str(repo), "--tier", "owned", "--ref", "main")
        self.assertEqual(rc, 2)
        self.assertEqual(self.config.read_bytes(), original)
        with local.write_lock(self.config):
            rc, _ = self.cli("register", "--id", "second", "--path", str(repo), "--tier", "owned", "--ref", "main")
        self.assertEqual(rc, 2)
        self.assertEqual(self.config.read_bytes(), original)

    def test_ref_change_rebuilds_metadata_and_old_candidate_read_is_exact(self):
        repo = self.register("public")
        _, before = self.cli("search", "Chrome")
        candidate = before["candidates"][0]
        path = repo / candidate["path"]
        path.write_text(path.read_text().replace("Chrome", "Firefox"))
        self.git(repo, "add", "--", candidate["path"])
        self.git(repo, "commit", "-m", "new edition")
        _, after = self.cli("search", "Chrome")
        self.assertEqual(after["candidates"], [])
        self.assertFalse(after["coverage"][0]["cache_hit"])
        self.assertNotEqual(after["coverage"][0]["commit"], candidate["commit"])
        result = subprocess.run([sys.executable, str(SCRIPT), "--config", str(self.config), "read", "--source", "public",
                                 "--commit", candidate["commit"], "--path", candidate["path"]], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("Chrome", result.stdout)

    def test_trust_layers_and_repository_identity_drift(self):
        repo = self.register("public")
        self.register("partner", "trusted")
        _, owned = self.cli("search", "Chrome")
        self.assertEqual([s["id"] for s in owned["coverage"]], ["public"])
        _, trusted = self.cli("search", "Chrome", "--tier", "trusted")
        self.assertEqual([s["id"] for s in trusted["coverage"]], ["partner"])
        self.git(repo, "remote", "set-url", "origin", "https://github.com/example/different.git")
        rc, drift = self.cli("search", "Chrome")
        self.assertEqual(rc, 1)
        self.assertIn("identity changed", drift["coverage"][0]["error"])

    def test_bad_cache_falls_back_to_real_metadata(self):
        self.register("public")
        self.cli("search", "Chrome")
        cache_file = next(self.cache.glob("*.json"))
        value = json.loads(cache_file.read_text())
        value["entries"] = [{}]
        cache_file.write_text(json.dumps(value))
        rc, result = self.cli("search", "Chrome")
        self.assertEqual(rc, 0)
        self.assertEqual(result["coverage"][0]["examined"], 2)
        self.assertFalse(result["coverage"][0]["cache_hit"])

    def test_empty_cache_cannot_certify_zero_items_examined(self):
        self.register("public")
        self.cli("search", "Chrome")
        cache_file = next(self.cache.glob("*.json"))
        value = json.loads(cache_file.read_text())
        value["entries"] = []
        cache_file.write_text(json.dumps(value))
        rc, result = self.cli("search", "Chrome")
        self.assertEqual(rc, 0)
        self.assertEqual(result["coverage"][0]["examined"], 2)
        self.assertEqual(result["matched_count"], 1)

    def test_source_schema_missing_and_empty_fields(self):
        self.register("public")
        valid = local.load_config(self.config)
        for field in ("id", "path", "ref", "tier", "priority", "enabled"):
            for bad in ("missing", "empty", "null"):
                data = json.loads(json.dumps(valid))
                if bad == "missing":
                    del data["sources"][0][field]
                else:
                    data["sources"][0][field] = "" if bad == "empty" else None
                with self.subTest(field=field, bad=bad), self.assertRaises(local.SourceError):
                    local.validate_config(data)

    def test_paths_and_explicit_roots(self):
        for value in ("../outside", "/outside", "foo/*", "", None, "foo\nbar"):
            with self.assertRaises(local.SourceError):
                local.relative(value)
        repo = self.register("public")
        config = local.load_config(self.config)
        config["sources"][0]["skill_roots"] = ["bundle/browser"]
        local.atomic_json(self.config, config)
        _, result = self.cli("search", "Chrome")
        self.assertEqual(result["coverage"][0]["examined"], 1)
        self.assertEqual(result["candidates"][0]["path"], "bundle/browser/SKILL.md")
        self.assertEqual(local.snapshot(config["sources"][0])[0].resolve(), repo.resolve())

    def test_non_string_tiers_report_structured_config_error(self):
        self.register("public")
        valid = local.load_config(self.config)
        for tier in ([], {}, 1, True):
            data = json.loads(json.dumps(valid))
            data["sources"][0]["tier"] = tier
            self.config.write_text(json.dumps(data))
            with self.subTest(tier=tier):
                rc, result = self.cli("list")
                self.assertEqual(rc, 2)
                self.assertEqual(result["status"], "error")
                self.assertIn("tier", result["error"])

    def test_replace_failure_does_not_truncate_previous_file(self):
        self.config.parent.mkdir(parents=True)
        self.config.write_text("original")
        with patch.object(local.os, "replace", side_effect=OSError("synthetic failure")):
            with self.assertRaises(OSError):
                local.atomic_json(self.config, {"new": True})
        self.assertEqual(self.config.read_text(), "original")

    def project(self, name="task project", roots=(".claude/skills",)):
        repo = self.repo(name)
        for skill_root in roots:
            folder = repo / skill_root / "observer"
            folder.mkdir(parents=True)
            (folder / "SKILL.md").write_text(
                "---\nname: observer\ndescription: trace observability\n---\n# Project instructions\n")
        self.git(repo, "add", "--all")
        self.git(repo, "commit", "-m", "project skills")
        return repo

    def test_project_skill_is_found_alongside_all_owned_catalogs_and_read_at_exact_ref(self):
        for name in ("public", "team", "private"):
            self.register(name)
        project = self.project()
        original_config = self.config.read_bytes()
        rc, result = self.cli("search", "observability", "--project", str(project))
        self.assertEqual(rc, 0, result)
        self.assertEqual(len(result["coverage"]), 4)
        self.assertEqual([r["examined"] for r in result["coverage"][:3]], [2, 2, 2])
        report = result["coverage"][-1]
        self.assertEqual(report["scope"], "project")
        self.assertEqual(report["ref"], "HEAD")
        self.assertEqual(report["commit"], self.git(project, "rev-parse", "HEAD"))
        self.assertEqual(report["roots"], [
            {"path": ".claude/skills", "status": "present", "examined": 1},
            {"path": ".agents/skills", "status": "absent", "examined": 0}])
        candidate, = result["candidates"]
        self.assertEqual(candidate["scope"], "project")
        self.assertEqual(candidate["path"], ".claude/skills/observer/SKILL.md")
        path = project / candidate["path"]
        path.write_text(path.read_text().replace("Project instructions", "Later instructions"))
        self.git(project, "add", "--", candidate["path"])
        self.git(project, "commit", "-m", "later edition")
        read = subprocess.run([sys.executable, str(SCRIPT), "read", "--project", str(project),
                               "--source", candidate["source"], "--commit", candidate["commit"],
                               "--path", candidate["path"]], env=self.env, capture_output=True, text=True)
        self.assertEqual(read.returncode, 0, read.stdout)
        self.assertIn("Project instructions", read.stdout)
        self.assertNotIn("Later instructions", read.stdout)
        self.assertEqual(self.config.read_bytes(), original_config)

    def test_marketplace_only_and_unrelated_project_paths_remain_outside_project_scope(self):
        project = self.register("public")
        rc, result = self.cli("search", "Chrome", "--project", str(project))
        self.assertEqual(rc, 0, result)
        self.assertEqual(result["matched_count"], 1)
        self.assertEqual(result["coverage"][-1]["examined"], 0)
        self.assertTrue(all(r["status"] == "absent" for r in result["coverage"][-1]["roots"]))
        rc, result = self.cli("search", "fixture", "--project", str(project))
        self.assertEqual(rc, 0, result)
        self.assertEqual(result["candidates"], [])

    def test_project_declared_root_ref_and_duplicate_provenance(self):
        project = self.register("public")
        rc, result = self.cli("search", "Chrome", "--project", str(project),
                              "--project-ref", "main", "--project-skill-root", "bundle/browser")
        self.assertEqual(rc, 0, result)
        self.assertEqual(len(result["coverage"]), 2)
        self.assertEqual(result["matched_count"], 1)
        candidate, = result["candidates"]
        self.assertEqual({p["scope"] for p in candidate["provenance"]}, {"configured", "project"})
        self.assertEqual(result["coverage"][-1]["roots"][0]["path"], "bundle/browser")

    def test_project_errors_cannot_hide_healthy_owned_results(self):
        self.register("public")
        project = self.project()
        (project / ".claude/skills/observer/SKILL.md").write_text("not frontmatter")
        self.git(project, "add", "--all")
        self.git(project, "commit", "-m", "invalid metadata")
        for path in (project, self.root / "missing-project"):
            with self.subTest(path=path):
                rc, result = self.cli("search", "Chrome", "--project", str(path))
                self.assertEqual(rc, 1, result)
                self.assertEqual(result["status"], "incomplete")
                self.assertEqual(result["coverage"][0]["status"], "searched")
                self.assertEqual(result["coverage"][-1]["status"], "unavailable")
                self.assertEqual(len(result["candidates"]), 1)

    def test_malformed_project_scope_fails_and_does_not_register(self):
        project = self.register("public")
        before = self.config.read_bytes()
        for extra in (("--project-skill-root", "../outside"),
                      ("--project-skill-root", "."), ("--project-skill-root", ""),
                      ("--project-ref", ""), ("--project-ref=-malformed",)):
            with self.subTest(extra=extra):
                rc, result = self.cli("search", "Chrome", "--project", str(project), *extra)
                self.assertEqual(rc, 2, result)
                self.assertEqual(result["status"], "error")
        rc, result = self.cli("search", "Chrome", "--project", str(project / "bundle"))
        self.assertEqual(rc, 1, result)
        self.assertIn("repository root", result["coverage"][-1]["error"])
        self.assertEqual(self.config.read_bytes(), before)

    def test_both_project_roots_preserve_same_name_candidates_and_ignore_uncommitted_content(self):
        self.register("public")
        project = self.project(roots=(".claude/skills", ".agents/skills"))
        (project / ".claude/skills/observer/SKILL.md").write_text("uncommitted invalid metadata")
        rc, result = self.cli("search", "observability", "--project", str(project), "--limit", "1")
        self.assertEqual(rc, 0, result)
        self.assertEqual(result["matched_count"], 2)
        self.assertEqual(result["coverage"][-1]["examined"], 2)
        self.assertEqual(len(result["candidates"]), 1)

    def test_unreadable_ref_and_nonregular_project_roots_are_incomplete(self):
        project = self.register("public")
        (project / ".claude").mkdir()
        (project / ".claude/skills").symlink_to("../bundle", target_is_directory=True)
        self.git(project, "add", "--all")
        self.git(project, "commit", "-m", "symlink root")
        for extra in ((), ("--project-ref", "missing-ref")):
            with self.subTest(extra=extra):
                rc, result = self.cli("search", "Chrome", "--project", str(project), *extra)
                self.assertEqual(rc, 1, result)
                self.assertEqual(result["coverage"][-1]["status"], "unavailable")
                self.assertNotEqual(result["coverage"][-1]["roots"][0]["status"], "absent")
                self.assertEqual(result["matched_count"], 1)

    def test_project_read_rejects_unrelated_blob_and_requires_scope_for_custom_roots(self):
        self.register("public")
        project = self.project(roots=("automation/skills",))
        commit = self.git(project, "rev-parse", "HEAD")
        common = ["read", "--source", "@project", "--project", str(project), "--commit", commit]
        for path in ("bundle/browser/SKILL.md", "automation/skills/observer/SKILL.md"):
            rc, result = self.cli(*common, "--path", path)
            self.assertEqual(rc, 2, result)
            self.assertIn("not a declared Skill", result["error"])
        result = subprocess.run([sys.executable, str(SCRIPT), *common,
                                 "--path", "automation/skills/observer/SKILL.md",
                                 "--project-skill-root", "automation/skills"],
                                env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Project instructions", result.stdout)


if __name__ == "__main__":
    unittest.main()
