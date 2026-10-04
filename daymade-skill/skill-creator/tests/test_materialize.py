"""KB-scale isolated Git fixtures; no user Git config, hooks, or network."""
import errno
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import signal
import time
import tempfile
import unittest
from unittest import mock

from scripts import materialize as m


class MaterializeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.repo = self.base / "source"
        self.repo.mkdir()
        self.home = self.base / "home"
        self.home.mkdir()
        self.env = {**os.environ, "HOME": str(self.home), "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_GUARD_OSASCRIPT": "/usr/bin/false",
                    "GIT_GUARD_TTY": os.devnull}
        self.g("init", "-q")
        self.g("config", "user.email", "fixture@example.invalid")
        self.g("config", "user.name", "Fixture")
        (self.repo / "selected").mkdir()
        (self.repo / "selected" / "input.txt").write_text("original\n")
        (self.repo / "excluded.bin").write_bytes(b"x" * 16384)
        self.ref = self.commit()
        self.root = self.base / "task"
        self.manifest = {"source_repo": str(self.repo), "source_ref": self.ref,
                         "paths": ["selected"], "arms": ["with", "baseline"],
                         "max_total_bytes": 512 * 1024, "minimum_free_bytes": 1,
                         "owner": "fixture-session"}

    def g(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], env=self.env).decode().strip()

    def commit(self):
        self.g("add", "--all")
        self.g("commit", "-qm", "fixture")
        return self.g("rev-parse", "HEAD")

    def prepare(self, **changes):
        return m.prepare({**self.manifest, **changes}, self.root)

    def run_python(self, code, **kwargs):
        return m.run(self.root, "fixture-session", "with", [sys.executable, "-c", code], **kwargs)

    def read(self):
        return json.loads((self.root / m.STATE).read_text())

    def test_scan_file_removed_between_walk_and_lstat_is_sampled_absent(self):
        self.root.mkdir()
        gone = self.root / ".next" / "export" / "transient.js"
        gone.parent.mkdir(parents=True)
        gone.write_bytes(b"temporary")
        (self.root / "kept.log").write_bytes(b"kept")
        original = Path.lstat
        removed = []

        def remove_then_lstat(path, *args, **kwargs):
            if path == gone:
                path.unlink()
                removed.append(path)
            return original(path, *args, **kwargs)

        with mock.patch.object(Path, "lstat", remove_then_lstat):
            sizes = m.scan(self.root)
        self.assertEqual(removed, [gone])
        self.assertIn("kept.log", sizes)
        self.assertNotIn(".next/export/transient.js", sizes)

    def test_scan_directory_removed_before_scandir_is_sampled_absent(self):
        self.root.mkdir()
        gone = self.root / ".next" / "export"
        gone.mkdir(parents=True)
        (self.root / "kept.log").write_bytes(b"kept")
        original = os.scandir
        removed = []

        def remove_then_scandir(path):
            if Path(path) == gone:
                gone.rmdir()
                removed.append(gone)
            return original(path)

        with mock.patch.object(m.os, "scandir", remove_then_scandir):
            sizes = m.scan(self.root)
        self.assertEqual(removed, [gone])
        self.assertIn("kept.log", sizes)
        self.assertFalse(gone.exists())

    def test_scan_root_missing_or_replaced_during_walk_remains_unknown(self):
        self.root.mkdir()
        with mock.patch.object(m.os, "walk", return_value=iter(())):
            self.assertIn(".", m.scan(self.root))
        for replace in (False, True):
            with self.subTest(replace=replace):
                root = self.base / ("replace-root" if replace else "missing-root")
                root.mkdir()

                def change_root(*args, **kwargs):
                    root.rename(root.with_name(root.name + "-old"))
                    if replace:
                        root.mkdir()
                    yield str(root), [], []

                with mock.patch.object(m.os, "walk", change_root):
                    with self.assertRaises(m.MaterializationError) as error:
                        m.scan(root)
                self.assertEqual(error.exception.reason, "measurement_unknown")
        with self.assertRaises(m.MaterializationError) as error:
            m.scan(self.base / "never-present-root")
        self.assertEqual(error.exception.reason, "measurement_unknown")

    def test_scan_child_permission_io_and_special_files_remain_unknown(self):
        self.root.mkdir()
        child = self.root / "child"
        child.write_bytes(b"kept")
        original = Path.lstat
        for number in (errno.EACCES, errno.EIO):
            with self.subTest(stage="lstat", errno=number):
                def fail_child(path, *args, **kwargs):
                    if path == child:
                        raise OSError(number, "synthetic measurement failure", str(child))
                    return original(path, *args, **kwargs)
                with mock.patch.object(Path, "lstat", fail_child):
                    with self.assertRaises(m.MaterializationError) as error:
                        m.scan(self.root)
                self.assertEqual(error.exception.reason, "measurement_unknown")
            with self.subTest(stage="walk", errno=number):
                def fail_walk(*args, **kwargs):
                    kwargs["onerror"](OSError(number, "synthetic walk failure", str(child)))
                    return iter(())
                with mock.patch.object(m.os, "walk", fail_walk):
                    with self.assertRaises(m.MaterializationError) as error:
                        m.scan(self.root)
                self.assertEqual(error.exception.reason, "measurement_unknown")
        os.mkfifo(self.root / "special")
        with self.assertRaises(m.MaterializationError) as error:
            m.scan(self.root)
        self.assertEqual(error.exception.reason, "measurement_unknown")

    def test_scan_walk_enoent_requires_a_named_strict_descendant(self):
        self.root.mkdir()
        for filename in (None, "", str(self.root), str(self.base / "outside")):
            with self.subTest(filename=filename):
                def fail_walk(*args, **kwargs):
                    kwargs["onerror"](FileNotFoundError(errno.ENOENT, "synthetic disappearance", filename))
                    return iter(())
                with mock.patch.object(m.os, "walk", fail_walk):
                    with self.assertRaises(m.MaterializationError) as error:
                        m.scan(self.root)
                self.assertEqual(error.exception.reason, "measurement_unknown")

    def test_scan_symlink_stays_accounted_without_following_target(self):
        self.root.mkdir()
        target = self.base / "link-target"
        target.mkdir()
        (target / "sentinel").write_bytes(b"outside sentinel")
        link = self.root / "link"
        link.symlink_to(target, target_is_directory=True)
        self.assertEqual((link / "sentinel").read_bytes(), b"outside sentinel")
        sizes = m.scan(self.root)
        self.assertIn("link", sizes)
        self.assertNotIn("link/sentinel", sizes)
        self.assertEqual(set(sizes), {".", "link"})

    def test_disappearing_sample_preserves_saved_highwater_and_budget_overage(self):
        self.prepare()
        gone = self.root / ".next" / "export" / "sampled.js"
        gone.parent.mkdir(parents=True)
        gone.write_bytes(b"x" * 4096)
        record = self.read()
        m.measure(record, self.root)
        previous = record["charged_bytes"]
        highwater = record["path_highwater"][".next/export/sampled.js"]
        original = Path.lstat
        removed = []

        def remove_then_lstat(path, *args, **kwargs):
            if path == gone:
                path.unlink()
                removed.append(path)
            return original(path, *args, **kwargs)

        with mock.patch.object(Path, "lstat", remove_then_lstat):
            m.measure(record, self.root)
        self.assertEqual(removed, [gone])
        self.assertGreaterEqual(record["charged_bytes"], previous)
        self.assertEqual(record["path_highwater"][".next/export/sampled.js"], highwater)
        m.save(self.root, record)
        self.assertEqual(self.read()["charged_bytes"], record["charged_bytes"])
        self.assertEqual(self.read()["path_highwater"][".next/export/sampled.js"], highwater)
        record["max_total_bytes"] = previous - 1
        with self.assertRaises(m.MaterializationError) as error:
            m.measure(record, self.root)
        self.assertEqual(error.exception.reason, "budget_exceeded")

    def test_small_selected_export_uses_immutable_ref_and_no_history(self):
        (self.repo / "selected" / "input.txt").write_text("HEAD changed\n")
        self.commit()
        record = self.prepare()
        self.assertEqual(record["state"], "prepared")
        for arm in self.manifest["arms"]:
            self.assertEqual((self.root / "arms" / arm / "selected" / "input.txt").read_text(), "original\n")
        self.assertFalse(any(p.name in (".git", "excluded.bin") for p in self.root.rglob("*")))
        self.assertEqual(self.read()["source_ref"], self.ref)
        with self.assertRaises(m.MaterializationError):
            self.prepare()

    def test_missing_promisor_blob_does_not_spawn_fetch(self):
        oid = self.g("rev-parse", f"{self.ref}:selected/input.txt")
        self.g("config", "remote.origin.promisor", "true")
        self.g("config", "remote.origin.url", str(self.base / "absent-remote"))
        self.g("config", "extensions.partialClone", "origin")
        (self.repo / ".git" / "objects" / oid[:2] / oid[2:]).unlink()
        trace = self.base / "git-trace.jsonl"
        with mock.patch.dict(os.environ, {"GIT_TRACE2_EVENT": str(trace)}):
            with self.assertRaises(m.MaterializationError):
                self.prepare()
        events = [json.loads(line) for line in trace.read_text().splitlines()]
        children = [e.get("argv", []) for e in events if e.get("event") == "child_start"]
        self.assertFalse(any("fetch" in arg for argv in children for arg in argv), children)
        self.assertFalse(self.root.exists())

    def test_permission_only_change_is_retained(self):
        self.prepare()
        path = self.root / "arms" / "with" / "selected" / "input.txt"
        path.chmod(0o755)
        record = m.finish(self.root, "fixture-session")
        self.assertTrue(path.exists())
        self.assertIn("arms/with/selected/input.txt", record["cleanup"]["retained"])

    def test_cli_sigterm_stops_own_child_and_retains_evidence(self):
        self.prepare()
        child_pgid = None
        p = subprocess.Popen([sys.executable, "-m", "scripts.materialize", "run", "--root", str(self.root),
                              "--owner", "fixture-session", "--arm", "with", "--", sys.executable,
                              "-c", "import time;time.sleep(30)"], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, start_new_session=True, env=self.env)
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                record = self.read()
                if record.get("child_pgid"):
                    child_pgid = record["child_pgid"]
                    break
                time.sleep(0.02)
            self.assertIsNotNone(child_pgid)
            p.send_signal(signal.SIGTERM)
            out, err = p.communicate(timeout=5)
            self.assertEqual(p.returncode, 130, (out, err))
            self.assertEqual(self.read()["state"], "interrupted")
            self.assertFalse(m.alive(child_pgid, group=True))
            result = m.finish(self.root, "fixture-session")
            self.assertIn("artifacts/run-0001/stdout.log", result["cleanup"]["retained"])
        finally:
            if p.poll() is None:
                os.killpg(p.pid, signal.SIGKILL)
                p.communicate()
            if child_pgid and m.alive(child_pgid, group=True):
                os.killpg(child_pgid, signal.SIGKILL)

    def test_missing_blank_null_and_nonpositive_required_keys(self):
        for key in self.manifest:
            for replacement in (None, "", [], 0):
                bad = dict(self.manifest)
                bad[key] = replacement
                with self.subTest(key=key, value=replacement), self.assertRaises((m.MaterializationError, OSError)):
                    m.validate_manifest(bad)
            bad = dict(self.manifest)
            del bad[key]
            with self.subTest(missing=key), self.assertRaises(m.MaterializationError):
                m.validate_manifest(bad)
        for value in (-1, False, 1.5):
            with self.assertRaises(m.MaterializationError):
                m.validate_manifest({**self.manifest, "max_total_bytes": value})

    def test_traversal_absolute_pathspec_and_whole_repository_rejected(self):
        for path in (".", "../source", "/tmp", "selected/../x", ":(glob)**", ".git", "selected/"):
            with self.subTest(path=path), self.assertRaises(m.MaterializationError):
                self.prepare(paths=[path])
        self.assertFalse(self.root.exists())

    def test_selected_git_symlink_and_submodule_rejected(self):
        (self.repo / "selected" / "escape").symlink_to("../../outside")
        ref = self.commit()
        with self.assertRaises(m.MaterializationError):
            self.prepare(source_ref=ref)
        self.assertFalse(self.root.exists())

    def test_all_arms_budget_checked_before_destination_creation(self):
        (self.repo / "selected" / "input.txt").write_bytes(b"z" * 12288)
        ref = self.commit()
        with self.assertRaises(m.MaterializationError) as error:
            self.prepare(source_ref=ref, max_total_bytes=20000)
        self.assertEqual(error.exception.reason, "budget_exceeded")
        self.assertFalse(self.root.exists())

    def test_old_large_blob_estimated_from_ref_not_small_HEAD(self):
        (self.repo / "selected" / "input.txt").write_bytes(b"z" * 65536)
        large_ref = self.commit()
        (self.repo / "selected" / "input.txt").write_text("small")
        self.commit()
        with self.assertRaises(m.MaterializationError) as error:
            self.prepare(source_ref=large_ref, max_total_bytes=32768)
        self.assertEqual(error.exception.reason, "budget_exceeded")
        self.assertFalse(self.root.exists())

    def test_lfs_pointer_default_and_local_only_hash_verification(self):
        body = b"local object" * 40
        oid = hashlib.sha256(body).hexdigest()
        pointer = f"version https://git-lfs.github.com/spec/v1\noid sha256:{oid}\nsize {len(body)}\n"
        (self.repo / "selected" / "lfs.dat").write_text(pointer)
        ref = self.commit()
        self.prepare(source_ref=ref)
        self.assertEqual((self.root / "arms" / "with" / "selected" / "lfs.dat").read_text(), pointer)
        self.root = self.base / "lfs-task"
        with self.assertRaises(m.MaterializationError):
            self.prepare(source_ref=ref, materialize_lfs=True)
        self.assertFalse(self.root.exists())
        obj = self.repo / ".git" / "lfs" / "objects" / oid[:2] / oid[2:4] / oid
        obj.parent.mkdir(parents=True)
        obj.write_bytes(body)
        self.prepare(source_ref=ref, materialize_lfs=True)
        self.assertEqual((self.root / "arms" / "with" / "selected" / "lfs.dat").read_bytes(), body)
        self.root = self.base / "bad-lfs-task"
        obj.write_bytes(b"bad")
        with self.assertRaises(m.MaterializationError):
            self.prepare(source_ref=ref, materialize_lfs=True)

    def test_free_space_and_unknown_measurement_preflight(self):
        with mock.patch.object(m, "free_bytes", return_value=1):
            with self.assertRaises(m.MaterializationError) as error:
                self.prepare(minimum_free_bytes=2)
        self.assertEqual(error.exception.reason, "free_space_low")
        self.assertFalse(self.root.exists())
        with mock.patch.object(m.os, "statvfs", side_effect=OSError("unknown")):
            with self.assertRaises(m.MaterializationError) as error:
                self.prepare()
        self.assertEqual(error.exception.reason, "measurement_unknown")
        self.assertFalse(self.root.exists())

    def test_success_and_child_failure_receipts_reopened_and_finish(self):
        self.prepare()
        record, code = self.run_python("print('process done')")
        self.assertEqual(code, 0)
        self.assertEqual(self.read()["state"], "run_succeeded")
        record, code = self.run_python("import sys; print('green'); sys.exit(7)")
        self.assertEqual(code, 23)
        self.assertEqual(self.read()["runs"][-1]["returncode"], 7)
        record = m.finish(self.root, "fixture-session")
        self.assertEqual(self.read()["outcome_before_finish"], "child_failed")
        self.assertEqual(len(record["cleanup"]["removed"]), 2)
        self.assertTrue((self.root / "artifacts" / "run-0001" / "stdout.log").exists())
        self.assertTrue((self.root / "artifacts" / "run-0002" / "stdout.log").exists())

    def test_child_budget_stops_own_group_and_retains_output(self):
        self.prepare(max_total_bytes=96 * 1024)
        record, code = self.run_python("import sys,time; sys.stdout.write('z'*131072); sys.stdout.flush(); time.sleep(30)", poll_interval=0.01)
        self.assertEqual(code, 20)
        self.assertEqual(self.read()["state"], "budget_exceeded")
        self.assertLess(record["runs"][-1]["returncode"], 0)
        self.assertIsNone(record["child_pgid"])
        done = m.finish(self.root, "fixture-session")
        self.assertIn("artifacts/run-0001/stdout.log", done["cleanup"]["retained"])

    def test_fast_child_budget_detected_after_exit(self):
        self.prepare(max_total_bytes=96 * 1024)
        _, code = self.run_python("print('z'*131072)", poll_interval=0.2)
        self.assertEqual(code, 20)

    def test_multiple_runs_share_budget_and_unique_evidence(self):
        self.prepare(max_total_bytes=96 * 1024)
        _, first = self.run_python("print('z'*24576)")
        self.assertEqual(first, 0)
        codes = [first]
        for _ in range(3):
            _, code = self.run_python("print('z'*24576)")
            codes.append(code)
            if code == 20:
                break
        self.assertIn(20, codes)
        self.assertTrue((self.root / "artifacts" / "run-0001" / "stdout.log").exists())
        self.assertGreater(self.read()["charged_bytes"], 96 * 1024)

    def test_run_free_low_and_unknown_measurement(self):
        self.prepare()
        with mock.patch.object(m, "free_bytes", return_value=0):
            _, code = self.run_python("print('never started')")
        self.assertEqual(code, 21)
        with mock.patch.object(m, "scan", side_effect=m.MaterializationError("unknown", "measurement_unknown")):
            _, code = self.run_python("print('never started')")
        self.assertEqual(code, 22)

    def test_keyboard_interrupt_stops_child_and_finish_records_outcome(self):
        self.prepare()
        with mock.patch.object(m.time, "sleep", side_effect=KeyboardInterrupt):
            _, code = self.run_python("import time; time.sleep(30)")
        self.assertEqual(code, 130)
        self.assertEqual(self.read()["state"], "interrupted")
        m.finish(self.root, "fixture-session")
        self.assertEqual(self.read()["outcome_before_finish"], "interrupted")

    def test_modified_unknown_evidence_and_symlink_escape_preserved(self):
        self.prepare()
        changed = self.root / "arms" / "with" / "selected" / "input.txt"
        changed.write_text("only working copy")
        unknown = self.root / "arms" / "baseline" / "new.txt"
        unknown.write_text("new work")
        evidence = self.root / "artifacts" / "proof.txt"
        evidence.write_text("evidence")
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "input.txt").write_text("original\n")
        baseline = self.root / "arms" / "baseline" / "selected"
        (baseline / "input.txt").unlink()
        baseline.rmdir()
        baseline.symlink_to(outside, target_is_directory=True)
        result = m.finish(self.root, "fixture-session")
        self.assertEqual(changed.read_text(), "only working copy")
        self.assertEqual((outside / "input.txt").read_text(), "original\n")
        self.assertIn("arms/with/selected/input.txt", result["cleanup"]["retained"])
        self.assertIn("arms/baseline/selected", result["cleanup"]["retained"])
        self.assertTrue(unknown.exists())
        self.assertTrue(evidence.exists())

    def test_owner_replaced_root_lock_and_active_child_refused(self):
        self.prepare()
        with self.assertRaises(m.MaterializationError):
            m.finish(self.root, "different-owner")
        record = self.read()
        record["child_pgid"] = os.getpgrp()
        m.save(self.root, record)
        with self.assertRaises(m.MaterializationError):
            m.finish(self.root, "fixture-session")
        record["child_pgid"] = None
        m.save(self.root, record)
        with m.lock_root(self.root, "fixture-session"):
            with self.assertRaises(m.MaterializationError):
                m.finish(self.root, "fixture-session")
        original = self.root
        self.root = self.base / "alias"
        self.root.symlink_to(original, target_is_directory=True)
        with self.assertRaises(m.MaterializationError):
            m.finish(self.root, "fixture-session")

    def test_deleted_data_does_not_reset_charged_budget(self):
        self.prepare()
        _, code = self.run_python("print('z'*4096)")
        self.assertEqual(code, 0)
        before = self.read()["charged_bytes"]
        m.finish(self.root, "fixture-session")
        self.assertGreaterEqual(self.read()["charged_bytes"], before)

    def test_success_finish_and_partial_prepare_failure_preserve_evidence(self):
        self.prepare()
        self.run_python("print('done')")
        result = m.finish(self.root, "fixture-session")
        self.assertEqual(result["outcome_before_finish"], "run_succeeded")
        self.assertEqual(len(result["cleanup"]["removed"]), 2)
        self.root = self.base / "partial"
        with mock.patch.object(m, "measure", side_effect=m.MaterializationError("unknown", "measurement_unknown")):
            with self.assertRaises(m.MaterializationError):
                self.prepare()
        self.assertEqual(self.read()["state"], "prepare_failed")
        m.finish(self.root, "fixture-session")
        self.assertEqual(self.read()["outcome_before_finish"], "prepare_failed")

    def test_stale_lock_recovery_and_file_symlink_never_deleted(self):
        self.prepare()
        child = subprocess.Popen([sys.executable, "-c", "pass"])
        child.wait()
        (self.root / m.LOCK).write_text(json.dumps({"owner": "fixture-session", "pid": child.pid}))
        self.assertEqual(m.recover(self.root, "fixture-session")["state"], "recovered")
        self.assertFalse((self.root / m.LOCK).exists())
        input_path = self.root / "arms" / "with" / "selected" / "input.txt"
        outside = self.base / "unique-work"
        outside.write_text("original\n")
        input_path.unlink()
        input_path.symlink_to(outside)
        result = m.finish(self.root, "fixture-session")
        self.assertTrue(input_path.is_symlink())
        self.assertEqual(outside.read_text(), "original\n")
        self.assertIn("arms/with/selected/input.txt", result["cleanup"]["retained"])

    def test_finish_interruption_retains_unknown_work_and_records_cleanup(self):
        self.prepare()
        unknown = self.root / "artifacts" / "proof.txt"
        unknown.write_text("unique evidence")
        with mock.patch.object(m.os, "walk", side_effect=OSError("unreadable inventory")):
            with self.assertRaises(m.MaterializationError) as error:
                m.finish(self.root, "fixture-session")
        self.assertEqual(error.exception.reason, "measurement_unknown")
        self.assertEqual(self.read()["state"], "cleanup_failed")
        self.assertFalse(self.read()["cleanup"]["inventory_complete"])
        self.assertEqual(self.read()["cleanup"]["removed"], [])
        with mock.patch.object(m, "remove_unchanged", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                m.finish(self.root, "fixture-session")
        record = self.read()
        self.assertEqual(record["state"], "cleanup_interrupted")
        self.assertEqual(record["cleanup"]["removed"], [])
        self.assertIn("artifacts/proof.txt", record["cleanup"]["retained"])
        self.assertTrue(unknown.exists())
        m.finish(self.root, "fixture-session")


if __name__ == "__main__":
    unittest.main()
