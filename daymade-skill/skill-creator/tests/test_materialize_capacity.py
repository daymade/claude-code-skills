"""Selected reserve and mixed-volume pressure controls; only tiny Git fixtures."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from scripts import materialize as m


class MaterializeCapacityTests(unittest.TestCase):
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
        for args in (("init", "-q"), ("config", "user.email", "fixture@example.invalid"),
                     ("config", "user.name", "Fixture")):
            self.git(*args)
        (self.repo / "input.txt").write_text("original\n")
        self.git("add", "input.txt")
        self.git("commit", "-qm", "fixture")
        self.manifest = {"source_repo": str(self.repo), "source_ref": self.git("rev-parse", "HEAD"),
                         "paths": ["input.txt"], "arms": ["work"], "max_total_bytes": 512 * 1024,
                         "minimum_free_bytes": 1, "owner": "capacity-fixture"}
        self.root = self.base / "task"
        self.config = self.base / "capacity.json"

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], env=self.env).decode().strip()

    def config_value(self, value):
        self.config.write_text(json.dumps(value))
        return str(self.config)

    def read(self):
        return json.loads((self.root / m.STATE).read_text())

    def run_child(self, **kwargs):
        return m.run(self.root, "capacity-fixture", "work", [sys.executable, "-c", "print('child')"], **kwargs)

    def cli(self, *args):
        return subprocess.run([sys.executable, str(Path(m.__file__).resolve()), *args],
                              cwd=self.base, env=self.env, capture_output=True)

    def test_selected_reserve_refuses_copy_before_root_creation(self):
        # A real caller shape: 20 GiB caller reserve and an explicitly selected 200 GB floor.
        config = self.config_value({"minimum_free_bytes": 200_000_000_000})
        manifest = {**self.manifest, "minimum_free_bytes": 20 * 1024**3}
        with mock.patch.object(m, "free_bytes", return_value=31_580_000_000):
            with self.assertRaises(m.MaterializationError) as error:
                m.prepare(manifest, self.root, capacity_config=config)
        self.assertEqual(error.exception.reason, "free_space_low")
        self.assertFalse(self.root.exists())

    def test_bad_config_and_binding_values_refuse_before_copy(self):
        bad_documents = ["not-json", "null", "[]", "{}", '{"minimum_free_bytes": null}',
                         '{"minimum_free_bytes": false}', '{"minimum_free_bytes": 0}',
                         '{"minimum_free_bytes": -1}', '{"minimum_free_bytes": 1.5}']
        for body in bad_documents:
            with self.subTest(body=body):
                self.config.write_text(body)
                with self.assertRaises(m.MaterializationError):
                    m.prepare(self.manifest, self.root, capacity_config=str(self.config))
                self.assertFalse(self.root.exists())
        self.config.unlink()
        with self.assertRaises(m.MaterializationError):
            m.prepare(self.manifest, self.root, capacity_config=str(self.config))
        for value in (None, "", " ", False, "relative.json"):
            with self.subTest(binding=value), self.assertRaises(m.MaterializationError):
                m.prepare({**self.manifest, "capacity_config": value}, self.root)
        self.config_value({"minimum_free_bytes": 1})
        alias = self.base / "alias.json"
        alias.symlink_to(self.config)
        with self.assertRaises(m.MaterializationError):
            m.prepare(self.manifest, self.root, capacity_config=str(alias))
        self.assertFalse(self.root.exists())

    def test_frozen_floor_never_drops_and_unrelated_json_fields_are_not_policy(self):
        config = self.config_value({"minimum_free_bytes": 4096, "max_total_bytes": 1,
                                    "unrelated": {"version": "old"}})
        m.prepare(self.manifest, self.root, capacity_config=config)
        self.config_value({"minimum_free_bytes": 8192, "unrelated": "changed"})
        record, code = self.run_child()
        self.assertEqual(code, 0)
        self.assertEqual(record["minimum_free_bytes"], 1)
        self.assertEqual(record["max_total_bytes"], self.manifest["max_total_bytes"])
        self.assertEqual(record["capacity_policy"]["minimum_free_bytes"], 8192)
        self.config_value({"minimum_free_bytes": 1, "unrelated": None})
        record, code = self.run_child()
        self.assertEqual(code, 0)
        self.assertEqual(self.read()["capacity_policy"], {
            "minimum_free_bytes": 8192, "effective_minimum_free_bytes": 8192})
        record["minimum_free_bytes"] = 16384
        self.assertEqual(m.resolve_capacity_limits(record)["minimum_free_bytes"], 16384)
        other = self.base / "other.json"
        other.write_text('{"minimum_free_bytes": 1}')
        with self.assertRaises(m.MaterializationError):
            m.resolve_capacity_limits(record, str(other))

    def test_existing_root_adopts_selected_floor_before_any_child(self):
        m.prepare({**self.manifest, "minimum_free_bytes": 20 * 1024**3}, self.root)
        config = self.config_value({"minimum_free_bytes": 200_000_000_000})
        with mock.patch.object(m, "free_bytes", return_value=31_580_000_000), \
                mock.patch.object(m.subprocess, "Popen") as launch:
            record, code = self.run_child(capacity_config=config)
        self.assertEqual(code, 21)
        launch.assert_not_called()
        self.assertEqual(record["capacity_config"], config)
        self.assertEqual(self.read()["capacity_policy"]["effective_minimum_free_bytes"], 200_000_000_000)
        self.assertNotIn("returncode", record["runs"][-1])

    def test_missing_bound_config_blocks_new_child_but_not_recovery_or_finish(self):
        config = self.config_value({"minimum_free_bytes": 1})
        m.prepare(self.manifest, self.root, capacity_config=config)
        self.config.unlink()
        with mock.patch.object(m.subprocess, "Popen") as launch:
            record, code = self.run_child()
        self.assertEqual(code, 2)
        self.assertEqual(record["state"], "invalid_manifest")
        launch.assert_not_called()
        child = subprocess.Popen([sys.executable, "-c", "pass"])
        child.wait()
        (self.root / m.LOCK).write_text(json.dumps({"owner": "capacity-fixture", "pid": child.pid}))
        with mock.patch.object(m, "free_bytes", return_value=0):
            self.assertEqual(m.recover(self.root, "capacity-fixture")["state"], "recovered")
            done = m.finish(self.root, "capacity-fixture")
        self.assertEqual(done["state"], "finished")
        self.assertEqual(done["cleanup"]["removed"], ["arms/work/input.txt"])
        self.assertEqual(done["outcome_before_finish"], "invalid_manifest")

    def test_mixed_volume_samples_persist_without_per_sample_writes_or_attribution(self):
        m.prepare(self.manifest, self.root)
        record = self.read()
        record.pop("capacity")
        record["charged_bytes"] = 0
        record["path_highwater"] = {}
        with mock.patch.object(m, "scan", return_value={"unchanged-input": 42}), \
                mock.patch.object(m, "free_bytes", side_effect=[1000, 700, 900]), \
                mock.patch.object(m.time, "time", side_effect=[10.0, 20.0, 30.0]), \
                mock.patch.object(m, "save") as writes:
            for _ in range(3):
                m.measure(record, self.root)
            writes.assert_not_called()
        m.save(self.root, record)
        persisted = self.read()
        self.assertEqual(persisted["observed_bytes"], 42)
        self.assertEqual(persisted["charged_bytes"], 42)
        self.assertEqual(persisted["capacity"], {
            "scope": "mixed_filesystem_available_space", "initial_free_bytes": 1000,
            "initial_sampled_at": 10.0, "latest_free_bytes": 900, "latest_sampled_at": 30.0,
            "min_free_bytes": 700, "min_sampled_at": 20.0})
        self.assertEqual(m.receipt_summary(persisted)["capacity"], persisted["capacity"])
        self.assertNotIn("external_task_bytes", persisted["capacity"])

    def test_cli_binding_and_summary_do_not_echo_private_config_or_extra_fields(self):
        config = self.config_value({"minimum_free_bytes": 1})
        manifest = self.base / "manifest.json"
        manifest.write_text(json.dumps(self.manifest))
        prepared = self.cli("prepare", "--manifest", str(manifest), "--root", str(self.root),
                            "--capacity-config", config, "--summary")
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        summary = json.loads(prepared.stdout)
        self.assertEqual(summary["capacity_policy"]["effective_minimum_free_bytes"], 1)
        self.assertNotIn(config.encode(), prepared.stdout)
        result = self.cli("run", "--root", str(self.root), "--owner", "capacity-fixture",
                          "--arm", "work", "--capacity-config", config, "--summary", "--",
                          sys.executable, "-c", "print('child')")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["last_run"]["returncode"], 0)

    def test_no_binding_keeps_old_api_and_does_not_read_a_policy(self):
        m.prepare(self.manifest, self.root)
        record = self.read()
        with mock.patch.object(m.json, "load", side_effect=AssertionError("no policy selected")):
            self.assertEqual(m.resolve_capacity_limits(record), {
                "minimum_free_bytes": 1, "max_total_bytes": self.manifest["max_total_bytes"]})
        self.assertNotIn("capacity_config", record)
        self.assertNotIn("capacity_policy", record)
        _, code = self.run_child()
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
