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

    def test_replace_failure_does_not_truncate_previous_file(self):
        self.config.parent.mkdir(parents=True)
        self.config.write_text("original")
        with patch.object(local.os, "replace", side_effect=OSError("synthetic failure")):
            with self.assertRaises(OSError):
                local.atomic_json(self.config, {"new": True})
        self.assertEqual(self.config.read_text(), "original")


if __name__ == "__main__":
    unittest.main()
