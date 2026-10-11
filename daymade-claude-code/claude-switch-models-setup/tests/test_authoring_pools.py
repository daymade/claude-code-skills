"""Synthetic local Git fixtures for owner-emitted Fleet authoring evidence."""
import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from test_sync_local_skill_sources import sync


class AuthoringPoolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "source"
        self.repo.mkdir()
        self.git(self.repo, "init", "-b", "main")
        self.git(self.repo, "config", "user.name", "Synthetic Fixture")
        self.git(self.repo, "config", "user.email", "fixture@example.invalid")
        self.git(self.repo, "config", "commit.gpgsign", "false")
        (self.repo / ".claude-plugin").mkdir()
        (self.repo / "bundle/member").mkdir(parents=True)
        (self.repo / "bundle/member/SKILL.md").write_text("---\nname: member\ndescription: fixture\n---\nFixture\n")
        (self.repo / ".claude-plugin/marketplace.json").write_text(json.dumps({
            "name": "daymade-skills", "plugins": [{"name": "suite", "source": "./bundle", "version": "1.0.0", "skills": ["./member"]}]}))
        self.git(self.repo, "add", ".claude-plugin/marketplace.json", "bundle/member/SKILL.md")
        self.git(self.repo, "commit", "-m", "synthetic fixture")
        # The exact configured URL is synthetic and is never contacted.
        self.origin = "https://example.invalid/fixture/skills.git"
        self.git(self.repo, "remote", "add", "origin", self.origin)
        self.pool = self.root / "pool"
        self.pool.mkdir()
        self.clone = self.pool / "slot-1"
        self.git(self.root, "clone", "--no-hardlinks", str(self.repo), str(self.clone))
        self.git(self.clone, "remote", "set-url", "origin", self.origin)
        self.git(self.clone, "switch", "-c", "task/fixture")
        self.base = self.git(self.clone, "rev-parse", "HEAD")
        self.config = {"version": 1, "origin": self.origin, "main": "main", "slots": 2}
        self.leases = {"slot-1": {"token": "fixture-token", "owner": "fixture-owner", "task": "fixture-task", "branch": "task/fixture", "base": self.base}}
        self.manifest = self.root / "authoring-pools.json"
        self.enrollment = {"schema_version": 1, "pools": [{"marketplace": "daymade-skills", "canonical_repo": str(self.repo), "origin": self.origin, "pool_root": str(self.pool)}]}
        self.policy = self.root / "policy.json"
        self.policy.write_text('{"schema_version":3,"active_skills":[]}')
        self.write()
        self.sources = [sync.load_marketplace(self.repo)]

    def git(self, repo, *args):
        result = subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True)
        self.assertEqual(0, result.returncode, result.stderr)
        return result.stdout.strip()

    def write(self):
        for filename, data in (("pool.json", self.config), ("init.json", self.config), ("leases.json", self.leases)):
            (self.pool / filename).write_text(json.dumps(data))
        self.manifest.write_text(json.dumps(self.enrollment))

    def inventory(self):
        return sync.authoring_inventory(self.sources, self.manifest)

    def test_only_exact_enrollment_and_active_lease_grant_clone(self):
        canonical = {"source_dir": str(self.repo / "bundle/member"), "plugin_id": "suite@daymade-skills"}
        self.assertEqual(canonical, sync.authoring_inventory(self.sources, self.root / "absent.json")["daymade-skills"]["member"])
        self.assertEqual([canonical, {"source_dir": str(self.clone / "bundle/member"), "plugin_id": "suite@daymade-skills"}], self.inventory()["daymade-skills"]["member"])
        (self.clone / "bundle/member/SKILL.md").write_text("---\nname: member\ndescription: changed\n---\nDirty authoring\n")
        self.assertEqual(2, len(self.inventory()["daymade-skills"]["member"]))
        self.leases = {}
        self.write()
        self.assertEqual(canonical, self.inventory()["daymade-skills"]["member"])

    def test_real_source_contract_changes_only_enrolled_clone(self):
        creator = Path(__file__).resolve().parents[3] / "daymade-skill/skill-creator/scripts/source_contract.py"
        import importlib.util
        spec = importlib.util.spec_from_file_location("fixture_source_contract", creator)
        contract = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(contract)
        identity = contract.git_identity(self.clone)
        baseline = sync.authoring_inventory(self.sources, self.root / "absent.json")
        self.assertFalse(contract.owned_repository(identity, "daymade-skills", {"marketplaces": baseline}))
        self.assertTrue(contract.owned_repository(identity, "daymade-skills", {"marketplaces": self.inventory()}))
        sibling = self.pool / "slot-2"
        self.git(self.root, "clone", "--no-hardlinks", str(self.repo), str(sibling))
        self.git(sibling, "remote", "set-url", "origin", self.origin)
        self.assertFalse(contract.owned_repository(contract.git_identity(sibling), "daymade-skills", {"marketplaces": self.inventory()}))

    def test_read_only_cli_keeps_selected_source_and_never_enters_sync(self):
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        output = io.StringIO()
        with contextlib.redirect_stdout(output), mock.patch.object(sync, "sync_lock", side_effect=AssertionError("write phase")):
            self.assertEqual(0, sync.main(["--repo", str(self.repo), "--active-skills-manifest", str(self.policy), "--authoring-pools-manifest", str(self.manifest), "--print-source-inventory"]))
        payload = json.loads(output.getvalue())
        self.assertEqual(str(self.repo / "bundle/member"), payload["selected_skills"]["member"]["source_dir"])
        self.assertEqual(2, len(payload["marketplaces"]["daymade-skills"]["member"]))
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_missing_null_blank_and_malformed_enrollment(self):
        valid = copy.deepcopy(self.enrollment)
        for bad in (None, [], {}, {"schema_version": True, "pools": []}, {"schema_version": 1, "pools": None}):
            self.manifest.write_text(json.dumps(bad))
            with self.subTest(bad=bad), self.assertRaises(ValueError): self.inventory()
        for key in valid["pools"][0]:
            for value in (None, "", " ", "relative", True):
                self.enrollment = copy.deepcopy(valid)
                self.enrollment["pools"][0][key] = value
                self.write()
                with self.subTest(key=key, value=value), self.assertRaises((ValueError, OSError)): self.inventory()
            self.enrollment = copy.deepcopy(valid)
            del self.enrollment["pools"][0][key]
            self.write()
            with self.assertRaises(ValueError): self.inventory()

    def test_invalid_pool_and_lease_fail_closed(self):
        valid = copy.deepcopy(self.leases)
        for value in (None, [], {"slot-3": valid["slot-1"]}, {"integration": valid["slot-1"]}, {"slot-1": None}):
            self.leases = value
            self.write()
            with self.subTest(value=value), self.assertRaises(ValueError): self.inventory()
        for key in valid["slot-1"]:
            for value in (None, "", " ", True):
                self.leases = copy.deepcopy(valid)
                self.leases["slot-1"][key] = value
                self.write()
                with self.subTest(key=key, value=value), self.assertRaises(ValueError): self.inventory()
            self.leases = copy.deepcopy(valid)
            del self.leases["slot-1"][key]
            self.write()
            with self.assertRaises(ValueError): self.inventory()
        self.leases = valid
        for key, value in (("slots", True), ("slots", 0), ("slots", 21), ("version", True), ("origin", "foreign"), ("main", None), ("main", " "), ("main", "bad..ref")):
            original = self.config[key]
            self.config[key] = value
            self.write()
            with self.subTest(key=key, value=value), self.assertRaises(ValueError): self.inventory()
            self.config[key] = original

    def test_init_configuration_cannot_borrow_boolean_or_float_equality(self):
        for key, value in (("version", True), ("version", 1.0), ("slots", 2.0)):
            bad = dict(self.config)
            bad[key] = value
            (self.pool / "init.json").write_text(json.dumps(bad))
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.inventory()

    def test_main_reflog_expression_is_not_a_literal_branch(self):
        self.git(self.repo, "switch", "-c", "previous")
        self.git(self.repo, "switch", "main")
        self.config["main"] = "@{-1}"
        self.write()
        with self.assertRaises(ValueError):
            self.inventory()

    def test_canonical_and_clone_metadata_and_skill_symlinks_reject(self):
        for repo in (self.repo, self.clone):
            for relative in (".git", ".claude-plugin/marketplace.json", "bundle/member/SKILL.md"):
                original = repo / relative
                physical = original.with_name(original.name + "-physical")
                original.rename(physical)
                original.symlink_to(physical, target_is_directory=physical.is_dir())
                try:
                    with self.subTest(repo=repo.name, path=relative), self.assertRaises(ValueError):
                        self.inventory()
                finally:
                    original.unlink()
                    physical.rename(original)

    def test_branch_origin_registration_and_symlinks_do_not_grant(self):
        for args in (("remote", "set-url", "origin", "foreign"), ("switch", "main")):
            self.git(self.clone, *args)
            with self.assertRaises(ValueError): self.inventory()
            self.git(self.clone, "remote", "set-url", "origin", self.origin)
            self.git(self.clone, "switch", "task/fixture")
        md = self.clone / "bundle/member/SKILL.md"
        md.write_text("---\nname: renamed\ndescription: fixture\n---\nFixture\n")
        with self.assertRaises(ValueError): self.inventory()
        md.write_text((self.repo / "bundle/member/SKILL.md").read_text())
        alias = self.root / "alias"
        alias.symlink_to(self.pool)
        self.enrollment["pools"][0]["pool_root"] = str(alias)
        self.write()
        with self.assertRaises(ValueError): self.inventory()


if __name__ == "__main__":
    unittest.main()
