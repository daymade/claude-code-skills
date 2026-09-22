"""Check installed plugin identities and independently selected Skill members."""

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "skill-install-audit.py"
SPEC = importlib.util.spec_from_file_location("install_audit_coverage", SCRIPT)
audit = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audit
SPEC.loader.exec_module(audit)


class SourcePreferenceAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.pool = self.root / "skills"
        self.pool.mkdir()
        self.manifest = self.root / "policy.json"
        self.repos = []
        for market in ("market-a", "market-b"):
            repo = self.root / market
            (repo / ".claude-plugin").mkdir(parents=True)
            (repo / "bundle").mkdir()
            (repo / "bundle/SKILL.md").write_text("---\nname: shared\ndescription: example\n---\n")
            (repo / ".claude-plugin/marketplace.json").write_text(json.dumps({
                "name": market, "plugins": [{"name": "plugin", "version": "1.0.0", "source": "./bundle"}]}))
            self.repos.append(repo)
        self.policy = {"schema_version": 3, "active_skills": [], "active_marketplaces": ["market-b"],
                       "source_preferences": {"shared": {"prefer": "plugin@market-a", "over": ["plugin@market-b"]}}}
        self.write_policy()
        for target, key, value in (
            (audit, "AGENTS_SKILLS", self.pool), (audit, "CODEX_MANIFEST", self.manifest),
            (audit, "REGISTRY_REPOS", [(r.name, r) for r in self.repos]),
            (audit.source_sync(), "LOCAL_MARKETPLACE_NAMES", ("market-a", "market-b")),
        ):
            patch = mock.patch.object(target, key, value)
            patch.start()
            self.addCleanup(patch.stop)

    def write_policy(self):
        self.manifest.write_text(json.dumps(self.policy))

    def test_selected_source_is_verified_instead_of_last_marketplace(self):
        (self.pool / "shared").symlink_to(self.repos[0] / "bundle")
        self.assertEqual(({"shared"}, {"shared"}), audit.load_codex())
        with mock.patch.object(audit, "REGISTRY_REPOS", list(reversed(audit.REGISTRY_REPOS))):
            self.assertEqual(({"shared"}, {"shared"}), audit.load_codex())

    def test_nonpreferred_same_name_link_cannot_satisfy_policy(self):
        (self.pool / "shared").symlink_to(self.repos[1] / "bundle")
        self.assertEqual(({"shared"}, set()), audit.load_codex())

    def test_include_exclude_and_unresolved_follow_owner_policy(self):
        self.policy.update(active_marketplaces=[], include_skills=["shared", "unregistered"])
        self.write_policy()
        self.assertEqual(({"shared", "unregistered"}, set()), audit.load_codex())
        self.policy.update(active_marketplaces=["market-b"], include_skills=[], exclude_skills=["shared"])
        self.write_policy()
        self.assertEqual((set(), set()), audit.load_codex())

    def test_undeclared_duplicate_and_stale_preference_fail(self):
        self.policy["source_preferences"] = {}
        self.write_policy()
        with self.assertRaisesRegex(ValueError, "duplicate source skill name"):
            audit.load_codex()
        self.policy["source_preferences"] = {"shared": {"prefer": "missing@market-a", "over": ["plugin@market-b"]}}
        self.write_policy()
        with self.assertRaisesRegex(ValueError, "candidate mismatch"):
            audit.load_codex()


class InstallAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / "claude"
        self.pool = self.root / "skills"
        self.repo = self.root / "team-repo"
        self.policy = self.root / "activation.json"
        self.pool.mkdir()
        self.write(self.base / "plugins/installed_plugins.json", {"plugins": {}})
        self.write(self.base / "settings.json", {"enabledPlugins": {}})
        self.write(self.policy, {"schema_version": 1, "active_skills": [],
                                 "active_marketplaces": ["cmks-skills"]})
        self.write(self.repo / ".claude-plugin/marketplace.json", {
            "name": "cmks-skills", "plugins": [{"name": "suite", "version": "1.0.0",
            "source": "./bundle", "skills": ["./first", "./second"]}]})
        for folder, name in [("first", "first-skill"), ("second", "second-skill")]:
            p = self.repo / "bundle" / folder / "SKILL.md"
            p.parent.mkdir(parents=True)
            p.write_text(f"---\nname: {name}\ndescription: Check {name}.\n---\nRun the task.\n")
        self.patches = [mock.patch.object(audit, key, value) for key, value in {
            "BASE": self.base, "AGENTS_SKILLS": self.pool, "CODEX_MANIFEST": self.policy,
            "REGISTRY_REPOS": [("old-directory-label", self.repo)],
            "PROFILES_DIR": self.root / "profiles", "DAEMON_ENTRY": self.root / "absent",
        }.items()]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def write(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))

    def link(self, name, folder):
        (self.pool / name).symlink_to(self.repo / "bundle" / folder)

    def test_whole_marketplace_uses_frontmatter_and_suite_members(self):
        self.link("first-skill", "first")
        self.link("second-skill", "second")
        result = audit.audit()
        self.assertEqual([], result["MANUAL_LINK_RISK"])
        self.assertEqual([], result["CODEX_SELECTED_MISSING"])
        self.assertEqual({"first-skill", "second-skill"}, audit.load_codex()[0])
        self.assertEqual({"cmks-skills": {"suite"}}, audit.load_registry())

    def test_missing_member_of_selected_marketplace_is_reported(self):
        self.link("first-skill", "first")
        self.assertEqual(["second-skill"], audit.audit()["CODEX_SELECTED_MISSING"])

    def test_dangling_entry_does_not_satisfy_activation(self):
        (self.pool / "first-skill").symlink_to(self.root / "missing")
        self.assertIn("first-skill", audit.audit()["CODEX_SELECTED_MISSING"])

    def test_wrong_source_does_not_satisfy_selected_name(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "SKILL.md").write_text("---\nname: first-skill\n---\n")
        (self.pool / "first-skill").symlink_to(outside)
        self.assertIn("first-skill", audit.audit()["CODEX_SELECTED_MISSING"])

    def test_unregistered_selected_name_cannot_borrow_a_foreign_entry(self):
        self.write(self.policy, {"schema_version": 1, "active_skills": ["unregistered"]})
        p = self.pool / "unregistered"
        p.mkdir()
        (p / "SKILL.md").write_text("---\nname: unregistered\n---\n")
        self.assertEqual(["unregistered"], audit.audit()["CODEX_SELECTED_MISSING"])

    def test_relative_link_does_not_satisfy_owner_link_contract(self):
        (self.pool / "first-skill").symlink_to("../team-repo/bundle/first")
        self.assertIn("first-skill", audit.audit()["CODEX_SELECTED_MISSING"])

    def test_unknown_marketplace_fails_instead_of_empty_success(self):
        self.write(self.policy, {"schema_version": 1, "active_skills": [],
                                 "active_marketplaces": ["misspelled"]})
        with self.assertRaisesRegex(ValueError, "unknown"):
            audit.audit()

    def test_declared_marketplace_with_unavailable_source_fails(self):
        self.write(self.policy, {"schema_version": 1, "active_skills": [],
                                 "active_marketplaces": ["daymade-skills-pro"]})
        with self.assertRaisesRegex(ValueError, "no source"):
            audit.audit()

    def test_unselected_owned_link_is_still_reported(self):
        self.write(self.policy, {"schema_version": 1, "active_skills": []})
        self.link("first-skill", "first")
        self.assertEqual(["first-skill"], audit.audit()["MANUAL_LINK_RISK"])

    def test_similar_prefix_is_not_owned(self):
        self.write(self.policy, {"schema_version": 1, "active_skills": []})
        target = self.root / "team-repo-unrelated"
        target.mkdir()
        (self.pool / "foreign").symlink_to(target)
        self.assertEqual([], audit.audit()["MANUAL_LINK_RISK"])

    def test_configured_repo_without_marketplace_is_not_owned(self):
        self.write(self.policy, {"schema_version": 1, "active_skills": []})
        unavailable = self.root / "unavailable-repo"
        unavailable.mkdir()
        link = self.pool / "ghost"
        link.symlink_to(unavailable)
        repos = audit.REGISTRY_REPOS + [("unavailable", unavailable)]
        with mock.patch.object(audit, "REGISTRY_REPOS", repos):
            result = audit.audit()
            sources = audit.registered_sources()
            audit.source_sync().sync_skill_root(
                self.pool, {}, [source.repo for source in sources], "probe", True, False
            )
        self.assertTrue(link.is_symlink())
        self.assertNotIn("ghost", result["MANUAL_LINK_RISK"])

    def test_escape_through_repo_symlink_is_not_owned(self):
        self.write(self.policy, {"schema_version": 1, "active_skills": []})
        outside = self.root / "outside"
        outside.mkdir()
        (self.repo / "escape").symlink_to(outside)
        (self.pool / "foreign").symlink_to(self.repo / "escape")
        self.assertEqual([], audit.audit()["MANUAL_LINK_RISK"])

    def test_relative_link_is_preserved_by_owner_and_not_reported(self):
        self.write(self.policy, {"schema_version": 1, "active_skills": []})
        (self.pool / "first-skill").symlink_to("../team-repo/bundle/first")
        audit.source_sync().sync_skill_root(self.pool, {}, [self.repo], "probe", True, False)
        self.assertEqual(Path("../team-repo/bundle/first"), (self.pool / "first-skill").readlink())
        self.assertEqual([], audit.audit()["MANUAL_LINK_RISK"])

    def test_foreign_symlink_loop_does_not_abort_audit(self):
        self.write(self.policy, {"schema_version": 1, "active_skills": []})
        loop = self.repo / "loop"
        loop.symlink_to(loop)
        (self.pool / "foreign").symlink_to(loop)
        reported = "foreign" in audit.audit()["MANUAL_LINK_RISK"]
        audit.source_sync().sync_skill_root(self.pool, {}, [self.repo], "probe", True, False)
        # pathlib's non-strict cycle resolution differs between Python 3.12
        # and 3.14. The report must match the owner's action on either runtime.
        self.assertEqual(reported, not (self.pool / "foreign").is_symlink())

    def test_suite_is_not_mistaken_for_a_missing_skill(self):
        self.link("first-skill", "first")
        self.link("second-skill", "second")
        self.write(self.base / "settings.json", {"enabledPlugins": {"suite@cmks-skills": True}})
        self.assertEqual([], audit.audit()["CODEX_UNLISTED_ENABLED"])

    def test_enabled_suite_reports_its_missing_members(self):
        self.write(self.policy, {"schema_version": 1, "active_skills": []})
        self.write(self.base / "settings.json", {"enabledPlugins": {"suite@cmks-skills": True}})
        self.assertEqual(["first-skill", "second-skill"], audit.audit()["CODEX_UNLISTED_ENABLED"])

    def test_same_name_plugins_do_not_borrow_enablement(self):
        self.write(self.base / "plugins/installed_plugins.json", {"plugins": {
            "suite@cmks-skills": [{}], "suite@another": [{}]}})
        self.write(self.base / "settings.json", {"enabledPlugins": {
            "suite@cmks-skills": True, "suite@another": False}})
        result = audit.audit()
        self.assertEqual(["suite@cmks-skills"], result["ENABLED"])
        self.assertEqual(["suite@another"], result["INSTALLED_DISABLED"])
        self.assertNotIn("suite@cmks-skills", result["REGISTERED_NOT_INSTALLED"])

    def test_unqualified_plugin_identity_is_invalid(self):
        self.write(self.base / "plugins/installed_plugins.json", {"plugins": {"suite": [{}]}})
        with self.assertRaises(ValueError):
            audit.audit()

    def test_non_boolean_enablement_is_invalid(self):
        self.write(self.base / "settings.json", {"enabledPlugins": {"suite@cmks-skills": "true"}})
        with self.assertRaises(ValueError):
            audit.audit()


if __name__ == "__main__":
    unittest.main()
