"""Branch admission uses real Git projections; snapshot publication stays strict."""
import os
from pathlib import Path
import sys
import unittest

import test_version_progression as fixtures

CHECKER = fixtures.CHECKER
manifest = fixtures.manifest
run = fixtures.run

sys.path.insert(0, str(CHECKER.parent))
import git_projection as projection


class ProjectionTests(unittest.TestCase):
    setUp = fixtures.VersionProgressionTests.setUp
    write_manifest = fixtures.VersionProgressionTests.write_manifest
    commit = fixtures.VersionProgressionTests.commit

    def check(self, base, candidate=None, *, index=False, projected=True):
        return run(
            self.repo, sys.executable, str(CHECKER), "--repo", str(self.repo),
            "--base", base,
            *(["--candidate-index"] if index else ["--candidate", candidate]),
            *(["--projected-merge"] if projected else []), check=False,
        )

    def release(self, *, version="1.1.0", content="candidate\n"):
        skill = self.repo / "daymade-audio/transcript-fixer/SKILL.md"
        skill.write_text(skill.read_text() + content)
        self.write_manifest(manifest(audio=version))
        return self.commit()

    def advance(self, candidate, *, version="2.1.0"):
        run(self.repo, "git", "switch", "-qc", "advanced", self.base)
        self.write_manifest(manifest(docs=version))
        base = self.commit("foreign owner release")
        run(self.repo, "git", "switch", "--detach", candidate)
        return base

    def test_unrelated_owner_advance_projects_without_lowering_foreign_version(self):
        candidate = self.release()
        base = self.advance(candidate)
        strict = self.check(base, candidate, projected=False)
        self.assertEqual(strict.returncode, 1)
        self.assertIn("plugin 'docs' regresses", strict.stderr)
        result = self.check(base, candidate)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("not the pushed snapshot", result.stdout)
        first = projection.projected_merge(self.repo, base, candidate)
        self.assertEqual(first, projection.projected_merge(self.repo, base, candidate))

    def test_projection_preserves_regression_and_unbumped_rejection(self):
        for version, message in [("0.9.0", "regresses"), ("1.0.0", "did not strictly increase")]:
            with self.subTest(version=version):
                run(self.repo, "git", "switch", "--detach", self.base)
                candidate = self.release(version=version)
                result = self.check(self.base, candidate)
                self.assertEqual(result.returncode, 1)
                self.assertIn(message, result.stderr)

    def test_same_owner_same_version_reuse_is_not_foreign_owner_exemption(self):
        (self.repo / "daymade-audio/transcript-fixer/first.md").write_text("first\n")
        candidate = self.release(content="")
        run(self.repo, "git", "switch", "--detach", self.base)
        (self.repo / "daymade-audio/transcript-fixer/second.md").write_text("second\n")
        other = self.release(content="")
        result = self.check(other, candidate)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("did not strictly increase", result.stderr)

    def test_conflicts_unrelated_history_and_missing_inputs_fail_closed(self):
        candidate = self.release()
        run(self.repo, "git", "switch", "--detach", self.base)
        conflicting = self.release(version="1.2.0", content="conflicting\n")
        self.assertEqual(self.check(conflicting, candidate).returncode, 2)
        tree = run(self.repo, "git", "rev-parse", self.base + "^{tree}").stdout.strip()
        orphan = run(self.repo, "git", "commit-tree", tree, "-m", "unrelated").stdout.strip()
        for bad_base in [orphan, "f" * 40, "", " "]:
            with self.subTest(base=bad_base):
                self.assertEqual(self.check(bad_base, candidate).returncode, 2)

    def test_index_uses_effective_copy_and_preserves_real_state(self):
        self.write_manifest(manifest(docs="2.1.0"))
        advanced = self.commit("advanced main")
        run(self.repo, "git", "switch", "-qc", "feature", self.base)
        (self.repo / "README.md").write_text("staged\n")
        run(self.repo, "git", "add", "README.md")
        (self.repo / "README.md").write_text("unstaged must not ship\n")
        index = Path(run(self.repo, "git", "rev-parse", "--path-format=absolute", "--git-path", "index").stdout.strip())
        before = index.read_bytes()
        refs = run(self.repo, "git", "show-ref").stdout
        result = self.check(advanced, index=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(index.read_bytes(), before)
        self.assertEqual(run(self.repo, "git", "show-ref").stdout, refs)
        self.assertEqual((self.repo / "README.md").read_text(), "unstaged must not ship\n")
        alternate = self.repo / "alternate-index"
        alternate.write_bytes(before)
        old = os.environ.get("GIT_INDEX_FILE")
        os.environ["GIT_INDEX_FILE"] = str(alternate)
        try:
            with projection.index_candidate(self.repo) as carried:
                self.assertEqual(run(self.repo, "git", "show", carried + ":README.md").stdout, "staged\n")
            self.assertEqual(alternate.read_bytes(), before)
        finally:
            if old is None:
                os.environ.pop("GIT_INDEX_FILE")
            else:
                os.environ["GIT_INDEX_FILE"] = old
        run(self.repo, "git", "update-index", "--split-index")
        before = index.read_bytes()
        index_mtime = index.stat().st_mtime_ns
        shared = Path(run(self.repo, "git", "rev-parse", "--shared-index-path").stdout.strip())
        if not shared.is_absolute():
            shared = self.repo / shared
        shared_before = (shared.read_bytes(), shared.stat().st_mtime_ns)
        result = self.check(advanced, index=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(index.read_bytes(), before)
        self.assertEqual(index.stat().st_mtime_ns, index_mtime)
        self.assertEqual((shared.read_bytes(), shared.stat().st_mtime_ns), shared_before)

    def test_concurrent_index_and_head_changes_are_rejected_and_never_restored(self):
        run(self.repo, "git", "switch", "-qc", "feature")
        file = self.repo / "README.md"
        file.write_text("first\n")
        run(self.repo, "git", "add", "README.md")
        with self.assertRaisesRegex(projection.ProjectionError, "index changed"):
            with projection.index_candidate(self.repo):
                file.write_text("second\n")
                run(self.repo, "git", "add", "README.md")
                changed = run(self.repo, "git", "show", ":README.md").stdout
        self.assertEqual(run(self.repo, "git", "show", ":README.md").stdout, changed)
        with self.assertRaisesRegex(projection.ProjectionError, "HEAD changed"):
            with projection.index_candidate(self.repo):
                new_head = self.commit("concurrent writer")
        self.assertEqual(run(self.repo, "git", "rev-parse", "HEAD").stdout.strip(), new_head)

    def resolved_merge(self):
        run(self.repo, "git", "switch", "-qc", "feature")
        (self.repo / "CHANGELOG.md").write_text("- audio v1.0.0 -> v1.1.0: source release.\n")
        head = self.release()
        run(self.repo, "git", "switch", "-qc", "advanced", self.base)
        self.write_manifest(manifest(docs="2.1.0"))
        (self.repo / "CHANGELOG.md").write_text("- docs v2.0.0 -> v2.1.0: main release.\n")
        base = self.commit("advanced main")
        run(self.repo, "git", "switch", "feature")
        merge = run(self.repo, "git", "merge", "--no-commit", "--no-ff", base, check=False)
        self.assertNotEqual(merge.returncode, 0, "fixture must have a real merge conflict")
        self.write_manifest(manifest(audio="1.1.0", docs="2.1.0"))
        (self.repo / "CHANGELOG.md").write_text(
            "- docs v2.0.0 -> v2.1.0: main release.\n"
            "- audio v1.0.0 -> v1.1.0: source release.\n"
        )
        run(self.repo, "git", "add", ".claude-plugin/marketplace.json", "CHANGELOG.md")
        return head, base

    def test_resolved_merge_index_carries_both_real_commit_parents(self):
        head, base = self.resolved_merge()
        index = Path(run(self.repo, "git", "rev-parse", "--path-format=absolute", "--git-path", "index").stdout.strip())
        merge_head = Path(run(self.repo, "git", "rev-parse", "--path-format=absolute", "--git-path", "MERGE_HEAD").stdout.strip())
        before = (index.read_bytes(), index.stat().st_mtime_ns, merge_head.read_bytes(), merge_head.stat().st_mtime_ns)
        result = self.check(base, index=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        with projection.index_candidate(self.repo) as carried:
            parents = run(self.repo, "git", "rev-list", "--parents", "-n", "1", carried).stdout.split()[1:]
            self.assertEqual(parents, [head, base])
        self.assertEqual((index.read_bytes(), index.stat().st_mtime_ns, merge_head.read_bytes(), merge_head.stat().st_mtime_ns), before)
        self.assertEqual(run(self.repo, "git", "rev-parse", "HEAD").stdout.strip(), head)

    def test_merge_head_invalid_or_concurrently_changed_is_never_restored(self):
        _, base = self.resolved_merge()
        merge_head = Path(run(self.repo, "git", "rev-parse", "--path-format=absolute", "--git-path", "MERGE_HEAD").stdout.strip())
        valid = merge_head.read_bytes()
        for data in [b"", b"\n", b"HEAD\n", b"f" * 40 + b"\n", b"0" * 40 + b"\n"]:
            with self.subTest(data=data):
                merge_head.write_bytes(data)
                result = self.check(base, index=True)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(merge_head.read_bytes(), data)
        merge_head.write_bytes(valid)
        with self.assertRaisesRegex(projection.ProjectionError, "MERGE_HEAD changed"):
            with projection.index_candidate(self.repo):
                merge_head.write_text(self.base + "\n")
        self.assertEqual(merge_head.read_text(), self.base + "\n")
        merge_head.write_bytes(valid)
        with self.assertRaisesRegex(projection.ProjectionError, "MERGE_HEAD changed"):
            with projection.index_candidate(self.repo):
                merge_head.unlink()
        self.assertFalse(merge_head.exists())
        with self.assertRaisesRegex(projection.ProjectionError, "MERGE_HEAD changed"):
            with projection.index_candidate(self.repo):
                merge_head.write_bytes(valid)
        self.assertEqual(merge_head.read_bytes(), valid)


if __name__ == "__main__":
    unittest.main()
