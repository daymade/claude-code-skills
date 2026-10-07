import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

BASE = Path(__file__).parents[1] / "scripts"

def load(name):
    spec = importlib.util.spec_from_file_location(name, BASE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

source = load("source_contract")


class SourceContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "owner"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.manifest = self.repo / ".claude-plugin/marketplace.json"
        self.manifest.parent.mkdir()
        self.write_manifest([{"name": "seed", "source": "./seed"}])
        self.skill(self.repo / "seed", "seed")

    def write_manifest(self, entries):
        self.manifest.write_text(json.dumps({"name": "test-market", "plugins": entries}))

    def skill(self, path, name):
        path.mkdir(parents=True, exist_ok=True)
        (path / "SKILL.md").write_text(f"---\nname: {name}\ndescription: test\n---\n")

    def inventory(self):
        file = self.root / "inventory.json"
        file.write_text(json.dumps({"schema_version": 2, "marketplaces": {"test-market": {
            "seed": {"source_dir": str(self.repo / "seed"), "plugin_id": "seed@test-market"}}}}))
        return file

    def test_create_allowed_but_delivery_requires_registration(self):
        target = self.repo / "new-skill"
        result = source.check_source(target, repo=self.repo, phase="create")
        self.assertEqual(result["status"], "valid")
        self.assertTrue(result["registration_pending"])
        self.assertFalse(target.exists())
        self.skill(target, "new-skill")
        self.assertEqual(source.check_source(target, repo=self.repo)["status"], "invalid")
        self.write_manifest([{"name": "new-skill", "source": "./new-skill"}])
        link = self.root / "installed"
        link.symlink_to(target, target_is_directory=True)
        report = source.check_source(target, repo=self.repo, install_path=link)
        self.assertEqual(report["status"], "valid")
        self.assertEqual(report["checks"]["installation"]["status"], "valid")
        self.assertEqual(report["runtime"]["status"], "unknown")

    def test_runnable_skill_in_wrong_repo_rejected(self):
        wrong = self.root / "pkm"
        wrong.mkdir()
        subprocess.run(["git", "init", "-q", str(wrong)], check=True)
        target = wrong / "next/05-Tools/skills/new-skill"
        self.skill(target, "new-skill")
        (target / "run.py").write_text("print('working')\n")
        self.assertEqual(subprocess.check_output(["python3", str(target / "run.py")], text=True).strip(), "working")
        self.assertEqual(source.check_source(target, repo=self.repo)["status"], "invalid")
        self.assertEqual(source.check_source(target, phase="create")["status"], "invalid")

    def test_automatic_owner_rejects_impersonated_marketplace(self):
        wrong = self.root / "pkm"
        wrong.mkdir()
        subprocess.run(["git", "init", "-q", str(wrong)], check=True)
        (wrong / ".claude-plugin").mkdir()
        (wrong / ".claude-plugin/marketplace.json").write_text(self.manifest.read_text())
        report = source.check_source(wrong / "new-skill", phase="create", inventory=self.inventory())
        self.assertEqual(report["status"], "invalid")

    def test_explicit_repo_cannot_override_existing_local_owner(self):
        wrong = self.root / "wrong-owner"
        wrong.mkdir()
        subprocess.run(["git", "-C", str(wrong), "init", "-q"], check=True)
        (wrong / ".claude-plugin").mkdir()
        (wrong / ".claude-plugin/marketplace.json").write_text(self.manifest.read_text())
        self.skill(wrong / "seed", "seed")
        owner_script = self.root / ".config/claude-switch-models-setup/sync-local-skill-sources.py"
        owner_script.parent.mkdir(parents=True)
        owner_script.touch()
        evidence = json.loads(self.inventory().read_text())
        with patch.object(source.Path, "home", return_value=self.root), patch.object(source, "load_inventory", return_value=evidence):
            self.assertEqual(source.check_source(wrong / "seed", repo=wrong)["status"], "invalid")
            self.assertEqual(source.check_source(self.repo / "seed", repo=self.repo)["status"], "valid")
            self.write_manifest([{"name": "seed", "source": "./seed"}])
            data = json.loads(self.manifest.read_text())
            data["name"] = "unmanaged-third-party"
            self.manifest.write_text(json.dumps(data))
            self.assertEqual(source.check_source(self.repo / "seed", repo=self.repo)["status"], "valid")

    def test_quoted_frontmatter_and_missing_plugin_identity(self):
        skill = self.repo / "seed"
        (skill / "SKILL.md").write_text('---\nname: "seed" # identity\ndescription: test\n---\n')
        self.assertEqual(source.check_source(skill, repo=self.repo)["status"], "valid")
        for bad in (None, ""):
            self.write_manifest([{"name": bad, "source": "./seed"}])
            self.assertNotEqual(source.check_source(skill, repo=self.repo)["status"], "valid")

    def test_project_scope_needs_no_marketplace(self):
        project = self.root / "project"
        project.mkdir()
        subprocess.run(["git", "init", "-q", str(project)], check=True)
        target = project / ".agents/skills/local-helper"
        self.skill(target, "local-helper")
        result = source.check_source(target, repo=project, scope="project")
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["checks"]["installation"]["status"], "unknown")

    def test_install_copy_is_not_source_backed_link(self):
        self.skill(self.root / "installed-copy", "seed")
        report = source.check_source(self.repo / "seed", repo=self.repo, install_path=self.root / "installed-copy")
        self.assertEqual(report["status"], "invalid")

    def test_missing_and_empty_inventory_keys_are_unknown(self):
        file = self.root / "inventory.json"
        for data in [{}, {"schema_version": 2}, {"schema_version": 2, "marketplaces": {}},
                     {"schema_version": 2, "marketplaces": None}]:
            with self.subTest(data=data):
                file.write_text(json.dumps(data))
                result = source.check_source(self.repo / "seed", phase="create", inventory=file)
                self.assertEqual(result["status"], "unknown")

    def test_missing_null_and_blank_source_dirs_never_use_cwd_as_owner(self):
        file = self.root / "inventory.json"
        previous = Path.cwd()
        try:
            os.chdir(self.repo)
            for candidate in ({}, {"source_dir": None}, {"source_dir": ""}, {"source_dir": "   "},
                              {"source_dir": "."}, {"source_dir": "missing/skill"}, {"source_dir": "~/unresolved-owner"}):
                with self.subTest(candidate=candidate):
                    file.write_text(json.dumps({"schema_version": 2, "marketplaces": {
                        "test-market": {"seed": candidate}}}))
                    result = source.check_source(self.repo / "seed", inventory=file)
                    self.assertEqual(result["status"], "unknown")
            self.assertEqual(source.check_source(self.repo / "seed", inventory=self.inventory())["status"], "valid")
        finally:
            os.chdir(previous)

    def test_escaping_source_and_alias_rejected(self):
        outside = self.root / "outside"
        self.skill(outside, "seed")
        self.write_manifest([{"name": "seed", "source": "./../outside"}])
        self.assertNotEqual(source.check_source(self.repo / "seed", repo=self.repo)["status"], "valid")
        alias = self.repo / "alias"
        alias.symlink_to(outside, target_is_directory=True)
        self.assertEqual(source.check_source(alias, repo=self.repo)["status"], "invalid")

    def test_initializer_checks_before_writing(self):
        import sys
        sys.path.insert(0, str(BASE))
        self.addCleanup(lambda: sys.path.remove(str(BASE)))
        init = load("init_skill")
        bad_parent = self.root / "installed-root"
        self.assertIsNone(init.init_skill("new-skill", bad_parent, repo=self.repo))
        self.assertFalse(bad_parent.exists())
        target = init.init_skill("new-skill", self.repo, repo=self.repo)
        self.assertEqual(target, self.repo / "new-skill")
        self.assertTrue((target / "SKILL.md").is_file())
        self.assertIsNone(init.init_skill("../escape", self.repo, repo=self.repo))
        self.assertFalse((self.root / "escape").exists())


class DeliveryIdentityTests(unittest.TestCase):
    """Run under the existing source-contract CI suite; no host/network needed."""

    def setUp(self):
        import sys
        sys.path.insert(0, str(BASE))
        self.addCleanup(lambda: sys.path.remove(str(BASE)))
        self.delivery = load("delivery_identity")
        self.identity = {
            "skill_name": "chart-judgment", "source_repo": "https://github.com/example/skills",
            "source_commit": "a" * 40, "source_path": "chart-judgment",
            "plugin_name": "chart-judgment", "plugin_version": "1.2.0",
            "version_kind": "standalone",
            "evidence_url": "https://github.com/example/skills/tree/" + "a" * 40 + "/chart-judgment",
        }

    def candidate(self):
        return "Updated the requested Skill.\n\n" + self.delivery.render_entry(self.identity)

    def test_generated_entry_and_actual_reply_not_merely_json_are_checked(self):
        text = self.candidate()
        receipt = self.delivery.prepare_receipt("task-a", [self.identity], text)
        result = self.delivery.check_receipt(receipt, "task-a", text)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["examined_count"], 1)
        for actual in (text.replace("`chart-judgment`", "chart"),
                       text.replace("v1.2.0", "v1.3.0"),
                       text.replace("example/skills", "other/skills"),
                       text + "\nAnother sentence.", "chart is installed."):
            with self.subTest(actual=actual):
                result = self.delivery.check_receipt(receipt, "task-a", actual)
                self.assertEqual(result["status"], "invalid")
                self.assertEqual(result["examined_count"], 1)

    def test_quote_alias_and_chinese_description_do_not_create_new_subjects(self):
        for prefix in ('中文说明：该技能用于图表判断。\n',
                       'Earlier I wrote "chart is installed"; that was an imprecise alias.\n',
                       'Quoted diagnostic: `chart` means the chart renderer.\n'):
            text = prefix + self.candidate()
            receipt = self.delivery.prepare_receipt("task-a", [self.identity], text)
            self.assertEqual(self.delivery.check_receipt(receipt, "task-a", text)["status"], "valid")

    def test_healthy_free_text_and_reference_to_an_old_alias(self):
        text = ('是正式技能 **`chart-judgment`**，属于 '
                '[example/skills](https://github.com/example/skills/tree/main/chart-judgment)。\n\n'
                '“chart-lite”是此前不准确的简称。\n版本升到 **1.2.0**。')
        receipt = self.delivery.prepare_receipt("task-a", [self.identity], text)
        self.assertEqual(self.delivery.check_receipt(receipt, "task-a", text)["status"], "valid")
        for wrong in (text + "\nchart-lite 的新版安装入口已核验完成。",
                      text + "\nchart-lite 已发布完成。"):
            with self.assertRaises(self.delivery.DeliveryError):
                self.delivery.prepare_receipt("task-a", [self.identity], wrong)

    def test_alias_only_and_no_examined_identities_cannot_prepare(self):
        for identities, text in (([self.identity], "chart installed"),
                                 ([], self.candidate()), (None, self.candidate())):
            with self.subTest(identities=identities):
                with self.assertRaises(self.delivery.DeliveryError):
                    self.delivery.prepare_receipt("task-a", identities, text)

    def test_missing_empty_values_and_wrong_links_fail(self):
        for field in self.identity:
            for value in (None, "", " "):
                with self.subTest(field=field, value=value):
                    broken = dict(self.identity, **{field: value})
                    with self.assertRaises(self.delivery.DeliveryError):
                        self.delivery.render_entry(broken)
            broken = dict(self.identity)
            del broken[field]
            with self.assertRaises(self.delivery.DeliveryError):
                self.delivery.render_entry(broken)
        for suffix in ("/other-skill", "/chart-judgment?target=other", "/chart-judgment#other"):
            broken = dict(self.identity, evidence_url=self.identity["evidence_url"].rsplit("/", 1)[0] + suffix)
            with self.assertRaises(self.delivery.DeliveryError):
                self.delivery.render_entry(broken)

    def test_suite_version_stays_with_plugin(self):
        suite = dict(self.identity, plugin_name="author-tools", version_kind="suite")
        line = self.delivery.render_entry(suite)
        self.assertIn('suite `author-tools` v1.2.0', line)
        self.assertIn('`chart-judgment`', line)
        self.assertNotIn('`chart-judgment` v1.2.0', line)

    def test_session_tampering_and_missing_actual_are_unknown(self):
        receipt = self.delivery.prepare_receipt("task-a", [self.identity], self.candidate())
        for receipt_arg, session, actual in ((receipt, "task-b", self.candidate()),
                                             (dict(receipt, candidate_text="changed"), "task-a", self.candidate()),
                                             (receipt, "task-a", ""),
                                             ({}, "task-a", self.candidate()),
                                             (receipt, "", self.candidate())):
            with self.subTest(session=session, actual=actual):
                self.assertEqual(self.delivery.check_receipt(receipt_arg, session, actual)["status"], "unknown")

    def test_multi_skill_entries_each_examined_and_not_cross_assigned(self):
        second = dict(self.identity, skill_name="document-export", source_path="document-export",
                      plugin_name="document-export", evidence_url=self.identity["evidence_url"].rsplit("/", 1)[0] + "/document-export")
        text = self.candidate() + "\n" + self.delivery.render_entry(second)
        receipt = self.delivery.prepare_receipt("task-a", [self.identity, second], text)
        result = self.delivery.check_receipt(receipt, "task-a", text)
        self.assertEqual((result["status"], result["examined_count"]), ("valid", 2))
        result = self.delivery.check_receipt(receipt, "task-a", self.candidate())
        self.assertEqual((result["status"], result["examined_count"]), ("invalid", 2))

    def test_committed_metadata_reuses_source_owner_and_exact_registration(self):
        fixture = SourceContractTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.write_manifest([{"name": "seed", "source": "./seed", "version": "1.0.0"}])
        subprocess.run(["git", "-C", str(fixture.repo), "remote", "add", "origin", "https://github.com/example/skills.git"], check=True)
        subprocess.run(["git", "-C", str(fixture.repo), "add", "seed", ".claude-plugin/marketplace.json"], check=True)
        subprocess.run(["git", "-C", str(fixture.repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "-qm", "fixture"], check=True)
        identity = self.delivery.build_identity(fixture.repo / "seed", fixture.repo)
        self.assertEqual(identity["skill_name"], "seed")
        self.assertEqual(identity["plugin_version"], "1.0.0")
        self.assertEqual(len(identity["source_commit"]), 40)
        self.assertNotIn(str(fixture.repo), json.dumps(identity))
        fixture.write_manifest([{"name": "seed", "source": "./seed", "version": "9.9.9"}])
        # Mutable metadata cannot silently supply the published version.
        self.assertEqual(self.delivery.build_identity(fixture.repo / "seed", fixture.repo)["plugin_version"], "1.0.0")
        with patch.object(self.delivery.source, "check_source", return_value={"status": "unknown", "errors": ["missing owner"]}):
            with self.assertRaises(self.delivery.DeliveryError):
                self.delivery.build_identity(fixture.repo / "seed", fixture.repo)


if __name__ == "__main__":
    unittest.main()
