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


if __name__ == "__main__":
    unittest.main()
