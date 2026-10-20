"""Real Git, archive writer/reader and integration controls; no network or secrets."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import release_readiness as rr
from release_distribution import POLICY_PATH


class RebindTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / "source"
        self.archive = self.root / "archive"
        for repo in (self.repo, self.archive):
            repo.mkdir()
            self.git(repo, "init", "--quiet")
            for key, value in (("user.name", "Fixture"), ("user.email", "fixture@example.invalid"),
                               ("core.hooksPath", "/dev/null"), ("commit.gpgsign", "false")):
                self.git(repo, "config", key, value)
        self.git(self.repo, "remote", "add", "origin", "https://example.invalid/skills.git")
        self.paths = ["suite/a"]
        self.deps = ["shared"]
        self.write(".claude-plugin/marketplace.json", json.dumps({"plugins": [
            {"name": "suite", "source": "./suite", "version": "1.0.0", "skills": ["./a", "./b"]},
            {"name": "other", "source": "./other", "version": "1.0.0"}]}))
        for name in ("suite/a/SKILL.md", "suite/b/SKILL.md", "other/SKILL.md",
                     "suite/helper.py", "shared/helper.py", POLICY_PATH):
            self.write(name, "synthetic stable content\n")
        self.base = self.commit(self.repo)
        manifest = json.loads((self.repo / ".claude-plugin/marketplace.json").read_text())
        manifest["plugins"][0]["version"] = "1.0.1"
        self.write(".claude-plugin/marketplace.json", json.dumps(manifest))
        self.before = self.commit(self.repo)
        self.git(self.repo, "update-ref", "refs/remotes/origin/main", self.before)
        self.review_path = "reviews/initial.md"
        self.review(self.deps)
        self.original_receipt = rr.attest(self.repo, self.before, self.paths, self.archive,
                                          self.review_commit, self.review_path)
        self.original_bytes = self.original_receipt.read_bytes()
        self.archive_bytes = (self.archive / self.review_path).read_bytes()

    def git(self, repo, *args, check=True):
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
        if check and result.returncode:
            raise AssertionError(result.stderr)
        return result.stdout.strip()

    def write(self, name, text):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self, repo):
        self.git(repo, "add", "--all")
        self.git(repo, "commit", "--quiet", "--allow-empty", "-m", "synthetic fixture")
        return self.git(repo, "rev-parse", "HEAD")

    def review(self, dependency_paths):
        metadata = dict(schema=1, result="passed", candidate=self.before, skill_paths=self.paths)
        if dependency_paths is not MISSING:
            metadata["rebind_dependencies"] = dependency_paths
        path = self.archive / self.review_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Synthetic independent review\n<!-- skill-release-review\n" +
                        json.dumps(metadata) + "\n-->\n")
        self.review_commit = self.commit(self.archive)

    def integration(self, changes=None):
        self.git(self.repo, "checkout", "--quiet", "-b", "new-main", self.base)
        self.write("other/SKILL.md", "unrelated main change\n")
        for name, text in (changes or {}).items():
            self.write(name, text)
        main = self.commit(self.repo)
        self.git(self.repo, "update-ref", "refs/remotes/origin/main", main)
        self.git(self.repo, "checkout", "--quiet", "-b", "candidate", self.before)
        self.git(self.repo, "merge", "--quiet", "--no-ff", "--no-edit", main)
        return self.git(self.repo, "rev-parse", "HEAD"), main

    def test_actual_integrated_rebind_reopens_without_rewriting_review(self):
        candidate, base = self.integration()
        target = rr.rebind(self.repo, candidate, self.paths, self.before, base)
        record = rr.verify(self.repo, candidate, self.paths)
        self.assertEqual(record["schema"], 2)
        self.assertEqual(record["original_candidate"], self.before)
        self.assertEqual(record["distribution"]["examined_files"], 5)
        self.assertEqual(record["original_receipt_sha256"], hashlib.sha256(self.original_bytes).hexdigest())
        self.assertEqual(self.original_receipt.read_bytes(), self.original_bytes)
        self.assertEqual((self.archive / self.review_path).read_bytes(), self.archive_bytes)
        self.assertEqual(rr.rebind(self.repo, candidate, self.paths, self.before, base), target)
        # Existing schema-1 records remain readable by the exact frozen old reader.
        spec = importlib.util.spec_from_file_location("old_release_reader", ROOT / "tests/fixtures/persisted-receipt/release_readiness_old.py")
        old = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(old)
        self.assertEqual(old.verify(self.repo, self.before, self.paths)["candidate"], self.before)
        with self.assertRaises(old.ReleaseError):
            old.verify(self.repo, candidate, self.paths)

    def test_complete_plugin_and_dependency_changes_block(self):
        for name in ("suite/a/SKILL.md", "suite/b/SKILL.md", "suite/helper.py", "shared/helper.py",
                     POLICY_PATH):
            with self.subTest(name=name):
                self.write(name, "changed\n")
                candidate = self.commit(self.repo)
                self.git(self.repo, "update-ref", "refs/remotes/origin/main", candidate)
                with self.assertRaisesRegex(rr.ReleaseError, "distributed plugin"):
                    rr.rebind(self.repo, candidate, self.paths, self.before, candidate)
                self.assertFalse(rr.receipt_path(self.repo, candidate).exists())
                self.write(name, "synthetic stable content\n")
                self.commit(self.repo)

    def test_excluded_skill_tests_can_change(self):
        candidate, base = self.integration({"suite/a/tests/probe.py": "synthetic excluded test\n"})
        rr.rebind(self.repo, candidate, self.paths, self.before, base)
        self.assertEqual(rr.verify(self.repo, candidate, self.paths)["distribution"]["examined_files"], 5)

    def test_cli_writes_then_fresh_process_verifies(self):
        candidate, base = self.integration()
        common = ["--repo", str(self.repo), "--candidate", candidate, "--skill-path", self.paths[0]]
        result = subprocess.run([sys.executable, str(ROOT / "scripts/release_readiness.py"),
                                 "rebind", *common, "--from-candidate", self.before, "--base", base],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        persisted = rr.receipt_path(self.repo, candidate).read_bytes()
        result = subprocess.run([sys.executable, str(ROOT / "scripts/release_readiness.py"),
                                 "verify", *common], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"schema": 2', result.stdout.replace("'", '"'))
        for extras in ([], ["--review-path", "replacement.md"]):
            result = subprocess.run([sys.executable, str(ROOT / "scripts/release_readiness.py"),
                                     "rebind", *common, "--from-candidate", self.before, *extras],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(rr.receipt_path(self.repo, candidate).read_bytes(), persisted)

    def test_mode_symlink_and_unreviewed_shared_helper_changes_block(self):
        (self.repo / "suite/helper.py").chmod(0o755)
        candidate = self.commit(self.repo)
        self.git(self.repo, "update-ref", "refs/remotes/origin/main", candidate)
        with self.assertRaisesRegex(rr.ReleaseError, "distributed plugin"):
            rr.rebind(self.repo, candidate, self.paths, self.before, candidate)
        (self.repo / "suite/helper.py").chmod(0o644)
        self.write("scripts/new-shared-helper.py", "new shared implementation\n")
        candidate = self.commit(self.repo)
        self.git(self.repo, "update-ref", "refs/remotes/origin/main", candidate)
        with self.assertRaisesRegex(rr.ReleaseError, "distributed plugin"):
            rr.rebind(self.repo, candidate, self.paths, self.before, candidate)
        (self.repo / "scripts/new-shared-helper.py").unlink()
        (self.repo / "suite/helper.py").unlink()
        (self.repo / "suite/helper.py").symlink_to("../shared/helper.py")
        candidate = self.commit(self.repo)
        self.git(self.repo, "update-ref", "refs/remotes/origin/main", candidate)
        with self.assertRaisesRegex(rr.ReleaseError, "distributed plugin"):
            rr.rebind(self.repo, candidate, self.paths, self.before, candidate)

    def test_internal_symlink_binds_target_in_other_plugin(self):
        self.write("other/linked.py", "linked implementation\n")
        (self.repo / "suite/a/linked.py").symlink_to("../../other/linked.py")
        self.before = self.commit(self.repo)
        self.review(self.deps)
        rr.attest(self.repo, self.before, self.paths, self.archive, self.review_commit, self.review_path)
        candidate, base = self.integration()
        rr.rebind(self.repo, candidate, self.paths, self.before, base)
        data = rr.verify(self.repo, candidate, self.paths)["distribution"]
        self.assertEqual(data["examined_files"], 7)
        self.assertEqual(data["entries"]["suite/a/linked.py"][0], "120000")
        self.assertIn("other/linked.py", data["entries"])
        self.write("other/linked.py", "changed linked implementation\n")
        candidate = self.commit(self.repo)
        self.git(self.repo, "update-ref", "refs/remotes/origin/main", candidate)
        with self.assertRaisesRegex(rr.ReleaseError, "distributed plugin"):
            rr.rebind(self.repo, candidate, self.paths, self.before, candidate)

    def test_external_dangling_and_cyclic_links_block_original_opt_in(self):
        for target in ("../../../escape", "/external/location", "missing.py", "invalid.py"):
            with self.subTest(target=target):
                link = self.repo / "suite/a/invalid.py"
                link.symlink_to(target)
                self.before = self.commit(self.repo)
                self.review(self.deps)
                with self.assertRaisesRegex(ValueError, "symlink"):
                    rr.attest(self.repo, self.before, self.paths, self.archive,
                              self.review_commit, self.review_path)
                self.assertFalse(rr.receipt_path(self.repo, self.before).exists())
                link.unlink()
                self.commit(self.repo)
    def test_changed_plugin_registration_and_missing_dependency_block(self):
        manifest = json.loads((self.repo / ".claude-plugin/marketplace.json").read_text())
        manifest["plugins"][0]["version"] = "1.0.2"
        self.write(".claude-plugin/marketplace.json", json.dumps(manifest))
        candidate = self.commit(self.repo)
        self.git(self.repo, "update-ref", "refs/remotes/origin/main", candidate)
        with self.assertRaisesRegex(rr.ReleaseError, "distributed plugin"):
            rr.rebind(self.repo, candidate, self.paths, self.before, candidate)
        (self.repo / "shared/helper.py").unlink()
        candidate = self.commit(self.repo)
        self.git(self.repo, "update-ref", "refs/remotes/origin/main", candidate)
        with self.assertRaisesRegex(ValueError, "missing rebind dependency"):
            rr.rebind(self.repo, candidate, self.paths, self.before, candidate)

    def test_changed_archive_at_current_head_and_missing_original_receipt_block(self):
        candidate, base = self.integration()
        target = rr.rebind(self.repo, candidate, self.paths, self.before, base)
        original = target.read_bytes()
        (self.archive / self.review_path).write_bytes(self.archive_bytes + b"changed committed review\n")
        self.commit(self.archive)
        with self.assertRaisesRegex(rr.ReleaseError, "changed since"):
            rr.verify(self.repo, candidate, self.paths)
        self.assertEqual(target.read_bytes(), original)
        self.original_receipt.unlink()
        with self.assertRaises(OSError):
            rr.verify(self.repo, candidate, self.paths)

    def test_original_contract_or_receipt_replacement_does_not_get_normalized(self):
        candidate, base = self.integration()
        target = rr.rebind(self.repo, candidate, self.paths, self.before, base)
        for value in (None, {}, {"distribution": {}}, {"source_identity": {}},
                      {"source_identity": rr.source_identity(self.repo), "distribution": {}}):
            with self.subTest(value=value):
                record = json.loads(self.original_bytes)
                record["rebind_contract"] = value
                self.original_receipt.write_text(json.dumps(record))
                persisted = self.original_receipt.read_bytes()
                with self.assertRaises(rr.ReleaseError):
                    rr.verify(self.repo, candidate, self.paths)
                self.assertEqual(self.original_receipt.read_bytes(), persisted)
        self.original_receipt.write_bytes(self.original_bytes)
        self.assertEqual(rr.verify(self.repo, candidate, self.paths)["candidate"], candidate)
        target.write_text("preexisting independent evidence\n")
        with self.assertRaisesRegex(rr.ReleaseError, "already exists"):
            rr.rebind(self.repo, candidate, self.paths, self.before, base)
        self.assertEqual(target.read_text(), "preexisting independent evidence\n")

    def test_exemption_and_rebased_history_cannot_rebind(self):
        candidate, base = self.integration()
        rr.attest(self.repo, self.before, self.paths, review_not_required="typo-only", reason="synthetic")
        with self.assertRaisesRegex(rr.ReleaseError, "independent review"):
            rr.rebind(self.repo, candidate, self.paths, self.before, base)
        self.original_receipt.write_bytes(self.original_bytes)
        unrelated = self.git(self.repo, "commit-tree", self.git(self.repo, "rev-parse", candidate + "^{tree}"),
                             "-m", "synthetic rewritten history")
        self.git(self.repo, "update-ref", "refs/remotes/origin/main", unrelated)
        with self.assertRaises(rr.ReleaseError):
            rr.rebind(self.repo, unrelated, self.paths, self.before, unrelated)

    def test_declared_dependency_scope_is_not_optional_or_replaceable(self):
        for value in (MISSING, [], None, "shared", [""], [None], ["shared", None], ["shared", "shared"]):
            with self.subTest(value=repr(value)):
                self.review(value)
                if value is MISSING:
                    rr.attest(self.repo, self.before, self.paths, self.archive, self.review_commit, self.review_path)
                    candidate = self.commit(self.repo)
                    self.git(self.repo, "update-ref", "refs/remotes/origin/main", candidate)
                    with self.assertRaisesRegex(rr.ReleaseError, "no complete rebind contract"):
                        rr.rebind(self.repo, candidate, self.paths, self.before, candidate)
                else:
                    with self.assertRaises((rr.ReleaseError, ValueError)):
                        rr.attest(self.repo, self.before, self.paths, self.archive, self.review_commit, self.review_path)

    def test_scope_archive_source_and_integration_fail_closed(self):
        candidate, base = self.integration()
        for paths in ([], ["suite/b"], ["suite/a", "suite/b"]):
            with self.subTest(paths=paths), self.assertRaises(rr.ReleaseError):
                rr.rebind(self.repo, candidate, paths, self.before, base)
        with self.assertRaisesRegex(rr.ReleaseError, "current fetched"):
            rr.rebind(self.repo, candidate, self.paths, self.before, self.before)
        self.git(self.repo, "remote", "set-url", "origin", "https://example.invalid/changed.git")
        with self.assertRaisesRegex(rr.ReleaseError, "source identity"):
            rr.rebind(self.repo, candidate, self.paths, self.before, base)
        self.git(self.repo, "remote", "set-url", "origin", "https://example.invalid/skills.git")
        (self.archive / self.review_path).write_text(self.archive_bytes.decode() + "dirty\n")
        with self.assertRaisesRegex(rr.ReleaseError, "dirty"):
            rr.rebind(self.repo, candidate, self.paths, self.before, base)

    def test_reader_rejects_missing_null_empty_and_forged_rebind_without_mutation(self):
        candidate, base = self.integration()
        target = rr.rebind(self.repo, candidate, self.paths, self.before, base)
        valid = target.read_bytes()
        record = json.loads(valid)
        for key in record:
            for value in (MISSING, None, "", [], {}):
                with self.subTest(key=key, value=repr(value)):
                    changed = dict(record)
                    if value is MISSING:
                        del changed[key]
                    else:
                        changed[key] = value
                    content = json.dumps(changed)
                    target.write_text(content)
                    with self.assertRaises((rr.ReleaseError, ValueError, TypeError)):
                        rr.verify(self.repo, candidate, self.paths)
                    self.assertEqual(target.read_text(), content)
        target.write_bytes(valid)
        self.assertEqual(rr.verify(self.repo, candidate, self.paths)["candidate"], candidate)
        self.git(self.repo, "checkout", "--quiet", "new-main")
        self.write("other/next.md", "main advanced\n")
        next_main = self.commit(self.repo)
        self.git(self.repo, "update-ref", "refs/remotes/origin/main", next_main)
        with self.assertRaisesRegex(rr.ReleaseError, "does not include"):
            rr.verify(self.repo, candidate, self.paths)
        self.assertEqual(target.read_bytes(), valid)

    def test_deciding_equivalence_mutation_is_detected(self):
        candidate, base = self.integration({"suite/b/SKILL.md": "changed sibling\n"})
        with self.assertRaises(rr.ReleaseError):
            rr.rebind(self.repo, candidate, self.paths, self.before, base)
        stable = rr.distribution_identity(self.repo, self.before, self.paths, self.deps)
        with mock.patch.object(rr, "distribution_identity", return_value=stable):
            # Removing the production equivalence predicate makes the rejection
            # assertion fail, demonstrating that it exercises the deciding path.
            with self.assertRaises(AssertionError):
                with self.assertRaises(rr.ReleaseError):
                    rr.rebind(self.repo, candidate, self.paths, self.before, base)


MISSING = object()

if __name__ == "__main__":
    unittest.main()
