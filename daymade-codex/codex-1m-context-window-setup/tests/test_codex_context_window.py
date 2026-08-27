from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "codex_context_window.py"


FAKE_CODEX = r'''#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
if args[:2] == ["debug", "models"]:
    model = os.environ.get("FAKE_CATALOG_MODEL", "gpt-5.6-sol")
    print(json.dumps({"models": [{
        "slug": model,
        "context_window": int(os.environ.get("FAKE_CONTEXT", "272000")),
        "max_context_window": int(os.environ.get("FAKE_MAX", "872000")),
        "effective_context_window_percent": int(os.environ.get("FAKE_PERCENT", "95")),
    }]}))
    raise SystemExit(0)

if "doctor" in args and "--json" in args:
    if "--strict-config" in args and os.environ.get("FAKE_STRICT_FAIL") == "1":
        print("strict failure", file=sys.stderr)
        raise SystemExit(7)
    print(json.dumps({"checks": {"config.load": {
        "status": "ok",
        "details": {"model": os.environ.get("FAKE_SELECTED_MODEL", "gpt-5.6-sol")},
    }}}))
    raise SystemExit(0)

print("unexpected fake codex args: " + repr(args), file=sys.stderr)
raise SystemExit(9)
'''


class CodexContextWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home = self.root / "codex-home"
        self.home.mkdir()
        self.os_home = self.root / "os-home"
        self.os_home.mkdir()
        self.fake = self.root / "codex"
        self.fake.write_text(FAKE_CODEX, encoding="utf-8")
        self.fake.chmod(self.fake.stat().st_mode | stat.S_IXUSR)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_script(self, mode: str, **extra_env: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(extra_env)
        env["CODEX_HOME"] = str(self.home)
        env["HOME"] = str(self.os_home)
        env["USERPROFILE"] = str(self.os_home)
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                mode,
                "--codex-bin",
                str(self.fake),
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )

    def payload(self, result: subprocess.CompletedProcess[str]) -> dict[str, object]:
        return json.loads(result.stdout)

    def test_doctor_derives_sol_model_aware_policy_without_writing(self) -> None:
        result = self.run_script("doctor")
        self.assertEqual(0, result.returncode, result.stderr)
        payload = self.payload(result)
        self.assertEqual("needs_apply", payload["status"])
        self.assertEqual(872_000, payload["recommended_raw_tokens"])
        self.assertEqual(828_400, payload["recommended_usable_tokens"])
        self.assertEqual(523_200, payload["recommended_auto_compact_tokens"])
        self.assertTrue(payload["capped_by_model"])
        self.assertFalse((self.home / "config.toml").exists())

    def test_gpt54_reproduces_historical_1m_600k_policy(self) -> None:
        result = self.run_script(
            "doctor",
            FAKE_SELECTED_MODEL="gpt-5.4",
            FAKE_CATALOG_MODEL="gpt-5.4",
            FAKE_MAX="1000000",
        )
        self.assertEqual(0, result.returncode, result.stderr)
        payload = self.payload(result)
        self.assertEqual(1_000_000, payload["recommended_raw_tokens"])
        self.assertEqual(950_000, payload["recommended_usable_tokens"])
        self.assertEqual(600_000, payload["recommended_auto_compact_tokens"])
        self.assertFalse(payload["capped_by_model"])

    def test_model_with_1m_default_still_applies_compaction_policy(self) -> None:
        doctor = self.run_script(
            "doctor",
            FAKE_SELECTED_MODEL="gpt-1m-default",
            FAKE_CATALOG_MODEL="gpt-1m-default",
            FAKE_CONTEXT="1000000",
            FAKE_MAX="1000000",
        )
        self.assertEqual(0, doctor.returncode, doctor.stderr)
        payload = self.payload(doctor)
        self.assertEqual("needs_apply", payload["status"])
        self.assertFalse(payload["expands_catalog_default"])

        applied = self.run_script(
            "apply",
            FAKE_SELECTED_MODEL="gpt-1m-default",
            FAKE_CATALOG_MODEL="gpt-1m-default",
            FAKE_CONTEXT="1000000",
            FAKE_MAX="1000000",
        )
        self.assertEqual(0, applied.returncode, applied.stderr)
        written = (self.home / "config.toml").read_text(encoding="utf-8")
        self.assertIn("model_context_window = 1000000", written)
        self.assertIn("model_auto_compact_token_limit = 600000", written)

    def test_models_above_1m_are_capped_at_named_ceiling(self) -> None:
        result = self.run_script("doctor", FAKE_MAX="1050000")
        self.assertEqual(0, result.returncode, result.stderr)
        payload = self.payload(result)
        self.assertEqual(1_000_000, payload["recommended_raw_tokens"])
        self.assertEqual(600_000, payload["recommended_auto_compact_tokens"])
        self.assertFalse(payload["capped_by_model"])

    def test_human_doctor_prints_every_promised_catalog_value(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "doctor",
                "--codex-bin",
                str(self.fake),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={
                **os.environ,
                "CODEX_HOME": str(self.home),
                "HOME": str(self.os_home),
                "USERPROFILE": str(self.os_home),
            },
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("catalog_default_raw_tokens: 272000", result.stdout)
        self.assertIn("effective_context_window_percent: 95", result.stdout)
        self.assertIn("requested_ceiling_tokens: 1000000", result.stdout)

    def test_apply_preserves_comments_tables_and_nested_same_named_key(self) -> None:
        config = self.home / "config.toml"
        original = textwrap.dedent(
            """\
            # operator note
            model = "gpt-5.6-sol"
            model_context_window = 300000  # keep this explanation

            [profiles.small]
            model_context_window = 128000
            other = "untouched"
            """
        )
        config.write_text(original, encoding="utf-8")
        result = self.run_script("apply")
        self.assertEqual(0, result.returncode, result.stderr)
        payload = self.payload(result)
        written = config.read_text(encoding="utf-8")
        self.assertIn(
            "model_context_window = 872000  # keep this explanation", written
        )
        self.assertIn("model_auto_compact_token_limit = 523200", written)
        self.assertIn("[profiles.small]\nmodel_context_window = 128000", written)
        self.assertIn('other = "untouched"', written)
        backup = Path(str(payload["backup_path"]))
        self.assertEqual(original.encode(), backup.read_bytes())

    def test_second_apply_is_noop_and_creates_no_new_backup(self) -> None:
        first = self.run_script("apply")
        self.assertEqual(0, first.returncode, first.stderr)
        backup_root = self.home / "backups" / "codex-1m-context-window-setup"
        self.assertFalse(backup_root.exists())
        second = self.run_script("apply")
        self.assertEqual(0, second.returncode, second.stderr)
        payload = self.payload(second)
        self.assertFalse(payload["changed"])
        self.assertIsNone(payload["backup_path"])
        self.assertFalse(backup_root.exists())

    @unittest.skipIf(os.name == "nt", "POSIX permission bits are not stable on Windows")
    def test_new_config_is_private(self) -> None:
        result = self.run_script("apply")
        self.assertEqual(0, result.returncode, result.stderr)
        mode = stat.S_IMODE((self.home / "config.toml").stat().st_mode)
        self.assertEqual(0o600, mode)

    def test_strict_failure_restores_exact_existing_bytes(self) -> None:
        config = self.home / "config.toml"
        original = b'model = "gpt-5.6-sol"\r\n# preserve CRLF\r\n'
        config.write_bytes(original)
        result = self.run_script("apply", FAKE_STRICT_FAIL="1")
        self.assertEqual(2, result.returncode)
        self.assertIn("prior config restored", self.payload(result)["error"])
        self.assertEqual(original, config.read_bytes())
        backups = list(
            (self.home / "backups" / "codex-1m-context-window-setup").glob("*.bak")
        )
        self.assertEqual(1, len(backups))
        self.assertEqual(original, backups[0].read_bytes())

    def test_strict_failure_removes_new_file(self) -> None:
        result = self.run_script("apply", FAKE_STRICT_FAIL="1")
        self.assertEqual(2, result.returncode)
        self.assertFalse((self.home / "config.toml").exists())

    def test_unknown_selected_model_fails_without_writing(self) -> None:
        result = self.run_script("apply", FAKE_SELECTED_MODEL="missing-model")
        self.assertEqual(2, result.returncode)
        self.assertIn("matched 0 live catalog entries", self.payload(result)["error"])
        self.assertFalse((self.home / "config.toml").exists())

    def test_missing_catalog_max_fails_without_writing(self) -> None:
        result = self.run_script("apply", FAKE_MAX="0")
        self.assertEqual(2, result.returncode)
        self.assertIn("no positive max_context_window", self.payload(result)["error"])
        self.assertFalse((self.home / "config.toml").exists())

    def test_invalid_existing_toml_fails_before_write(self) -> None:
        config = self.home / "config.toml"
        original = b"model_context_window = [\n"
        config.write_bytes(original)
        result = self.run_script("apply")
        self.assertEqual(2, result.returncode)
        self.assertIn("invalid TOML", self.payload(result)["error"])
        self.assertEqual(original, config.read_bytes())

    def test_quoted_target_key_fails_instead_of_duplicating(self) -> None:
        config = self.home / "config.toml"
        original = b'"model_context_window" = 300000\n'
        config.write_bytes(original)
        result = self.run_script("apply")
        self.assertEqual(2, result.returncode)
        self.assertIn("conservative editor cannot preserve", self.payload(result)["error"])
        self.assertEqual(original, config.read_bytes())

    def test_verify_reports_mismatch_then_passes_after_apply(self) -> None:
        mismatch = self.run_script("verify")
        self.assertEqual(1, mismatch.returncode)
        self.assertEqual("needs_apply", self.payload(mismatch)["status"])
        applied = self.run_script("apply")
        self.assertEqual(0, applied.returncode, applied.stderr)
        verified = self.run_script("verify")
        self.assertEqual(0, verified.returncode, verified.stderr)
        self.assertEqual("configured", self.payload(verified)["status"])

    def test_model_without_expansion_still_gets_truthful_base_policy(self) -> None:
        doctor = self.run_script("doctor", FAKE_MAX="272000")
        self.assertEqual(0, doctor.returncode)
        self.assertEqual("needs_apply", self.payload(doctor)["status"])
        self.assertFalse(self.payload(doctor)["expands_catalog_default"])
        applied = self.run_script("apply", FAKE_MAX="272000")
        self.assertEqual(0, applied.returncode, applied.stderr)
        written = (self.home / "config.toml").read_text(encoding="utf-8")
        self.assertIn("model_context_window = 272000", written)
        self.assertIn("model_auto_compact_token_limit = 163200", written)


if __name__ == "__main__":
    unittest.main()
