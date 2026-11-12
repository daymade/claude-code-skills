"""Synthetic CLI integration tests; no account, credential store or network access."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "lark-cli-router/scripts/lark_device_flow.py"
FAKE = r'''#!PYTHON
import json, os, pathlib, sys, time
root = pathlib.Path(os.environ["SYNTHETIC_LARK_ROOT"])
args = sys.argv[1:]
config = json.loads((root / "config.json").read_text())
for key in ("LARK_CLI_NO_PROXY", "LARKSUITE_CLI_NO_UPDATE_NOTIFIER", "LARKSUITE_CLI_NO_SKILLS_NOTIFIER"):
    assert os.environ.get(key) == "1", key
with (root / "calls.jsonl").open("a") as out:
    out.write(json.dumps(args) + "\n")
if args == ["--version"]:
    print("lark-cli synthetic-test-1")
    sys.exit(0)
assert args[:2] in (["auth", "status"], ["auth", "login"]), args
assert args[2:4] == ["--profile", "authorized account"], args
assert "--json" in args, args
if args[1] == "status":
    assert args[4:] in (["--json"], ["--json", "--verify"]), args
    saved = (root / "saved").exists()
    user = {"openId": "ou_synthetic_other" if saved and config.get("wrong") else "ou_synthetic_expected",
            "available": saved, "status": "ready" if saved else config.get("status", "expired"),
            "tokenStatus": "valid" if saved else "expired", "scope": "minutes:minute:readonly offline_access",
            "expiresAt": "2099-01-01T00:00:00Z", "refreshExpiresAt": "2099-02-01T00:00:00Z"}
    if "--verify" in args:
        user["verified"] = saved and not config.get("verify_false", False)
    if "openid" in config:
        user["openId"] = config["openid"]
    print(json.dumps({"appId": "cli_synthetic_app", "identities": {"user": user}}))
    sys.exit(0)
if "--no-wait" in args:
    assert "--device-code" not in args
    assert "--scope" in args or "--domain" in args or "--recommend" in args
    print(json.dumps({"verification_url": "https://example.invalid/authorize?user_code=SYNTHETIC",
                      "device_code": "synthetic-device-secret", "expires_in": config.get("expires_in", 20)}))
    sys.exit(0)
assert args[4:] == ["--device-code", "synthetic-device-secret", "--json"], args
(root / "polling").write_text(str(os.getpid()))
mode = config.get("mode", "approval")
if mode in ("expired", "denied"):
    print(json.dumps({"error": "expired_token" if mode == "expired" else "access_denied"}))
    sys.exit(2)
while not (root / "approved").exists():
    time.sleep(.02)
(root / "saved").write_text("credentials saved by synthetic CLI")
payload = {"event": "authorization_complete", "user_open_id": "ou_synthetic_expected",
           "credentials_saved": True, "scope": "minutes:minute:readonly offline_access",
           "missing": config.get("missing", []), "access_token": "synthetic-access-secret",
           "refresh_token": "synthetic-refresh-secret"}
if "refresh_token_issued" in config:
    payload["refresh_token_issued"] = config["refresh_token_issued"]
print(json.dumps(payload))
sys.exit(config.get("poll_exit", 0))
'''


class DeviceFlowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="lark flow tests ")
        self.root = Path(self.temporary.name)
        self.state = self.root / "private state with spaces"
        self.cli = self.root / "synthetic lark CLI"
        self.cli.write_text(FAKE.replace("#!PYTHON", "#!" + sys.executable))
        self.cli.chmod(0o700)
        self.config = {}
        self.env = dict(os.environ, SYNTHETIC_LARK_ROOT=str(self.root))
        self.flow = None
        self.write_config()

    def write_config(self):
        (self.root / "config.json").write_text(json.dumps(self.config))

    def command(self, action, *extra, okay=True):
        result = subprocess.run([sys.executable, str(SCRIPT), action, "--state-dir", str(self.state), *extra],
                                env=self.env, text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0 if okay else 1, result.stderr)
        public = json.loads(result.stdout if okay else result.stderr)
        serialized = json.dumps(public)
        for secret in ("synthetic-device-secret", "synthetic-access-secret", "synthetic-refresh-secret"):
            self.assertNotIn(secret, serialized)
        return public

    def start(self):
        result = self.command("start", "--profile", "authorized account", "--owner", "synthetic-session",
                              "--cli", str(self.cli), "--scope", "minutes:minute:readonly offline_access",
                              "--domain", "minutes", "--exclude", "minutes:minute:write",
                              "--authorization-confirmed")
        self.flow = result["flow_id"]
        return result

    def status(self):
        return self.command("status", "--flow-id", self.flow)

    def wait_for(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = predicate()
            if result:
                return result
            time.sleep(.03)
        self.fail("synthetic flow did not reach expected observable state")

    def terminal(self):
        def probe():
            result = self.status()
            return result if not result["worker_active"] else None
        return self.wait_for(probe)

    def calls(self):
        return [json.loads(s) for s in (self.root / "calls.jsonl").read_text().splitlines()]

    def approve(self):
        (self.root / "approved").touch()

    def tearDown(self):
        self.approve()
        if self.flow:
            self.wait_for(lambda: not self.status()["worker_active"])
        self.temporary.cleanup()

    def test_start_returns_promptly_approval_saves_and_verifies_private_state(self):
        before = time.monotonic()
        initial = self.start()
        self.assertLess(time.monotonic() - before, 1.5)
        self.assertEqual(initial["verification_url"], "https://example.invalid/authorize?user_code=SYNTHETIC")
        self.assertTrue(initial["worker_active"])
        self.assertFalse((self.root / "saved").exists())
        self.wait_for(lambda: (self.root / "polling").exists())
        self.assertTrue(self.status()["worker_active"])
        for path in self.state.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o700)
        self.approve()
        final = self.terminal()
        self.assertEqual(final["outcome"], "auth_verified")
        self.assertTrue(final["credentials_saved"])
        self.assertTrue(final["identity_verified"])
        self.assertEqual(final["business_read"], "required_in_selected_domain_guide")
        persisted = json.loads((self.state / (self.flow + ".json")).read_text())
        self.assertNotIn("device_code", persisted)
        self.assertNotIn("synthetic-access-secret", json.dumps(persisted))
        self.assertTrue(any("--verify" in call for call in self.calls()))

    def test_denied_and_expired_requests_are_terminal(self):
        for mode in ("denied", "expired"):
            with self.subTest(mode=mode):
                self.config["mode"] = mode
                self.write_config()
                self.start()
                final = self.terminal()
                self.assertEqual(final["outcome"], mode)
                self.assertFalse(final["identity_verified"])
                self.assertNotIn("verification_url", final)

    def test_wrong_identity_stops_actions_and_retry(self):
        self.config["wrong"] = True
        self.write_config()
        self.start()
        self.approve()
        final = self.terminal()
        self.assertEqual(final["outcome"], "wrong_identity")
        self.assertFalse(final["identity_verified"])
        result = self.command("retry", "--flow-id", self.flow, "--owner", "later-session",
                              "--authorization-confirmed", okay=False)
        self.assertIn("profile_identity_changed", result["error"])
        self.config["wrong"] = False  # Official account owner has restored the original binding.
        self.write_config()
        self.command("retry", "--flow-id", self.flow, "--owner", "later-session",
                     "--authorization-confirmed")
        self.assertEqual(self.terminal()["outcome"], "auth_verified")

    def test_deadline_expires_without_approval_and_stops_its_own_poll(self):
        self.config["expires_in"] = 1
        self.write_config()
        self.start()
        final = self.terminal()
        self.assertEqual(final["outcome"], "expired")
        self.assertFalse((self.root / "saved").exists())
        self.assertFalse(final["worker_active"])

    def test_refresh_token_boolean_false_and_absence_stay_distinct(self):
        for flag in (False, True, "absent"):
            with self.subTest(flag=flag):
                self.config = {} if flag == "absent" else {"refresh_token_issued": flag}
                self.write_config()
                self.start()
                self.approve()
                final = self.terminal()
                self.assertEqual(final["refresh_token_issued"], "unknown" if flag == "absent" else flag)
                self.assertEqual("warning" in final, flag is False)

    def test_duplicate_start_reuses_active_flow_without_new_code(self):
        first = self.start()
        second = self.start()
        self.assertEqual(first["flow_id"], second["flow_id"])
        self.assertEqual(first["worker_pid"], second["worker_pid"])
        self.assertEqual(len([c for c in self.calls() if "--no-wait" in c]), 1)
        self.assertEqual(first["deadline"], second["deadline"])

    def test_worker_lost_child_still_finishes_then_continuation_verifies(self):
        first = self.start()
        self.wait_for(lambda: (self.root / "polling").exists())
        os.kill(first["worker_pid"], signal.SIGKILL)  # Our synthetic worker only.
        self.assertTrue(self.status()["worker_active"])  # Polling child retains the lock.
        self.approve()
        self.wait_for(lambda: not self.status()["worker_active"])
        self.assertEqual(self.status()["outcome"], "worker_lost")
        result = self.command("continue", "--flow-id", self.flow, "--owner", "resumed-session")
        self.assertEqual(result["outcome"], "auth_verified_after_worker_loss")
        self.assertTrue(result["identity_verified"])
        self.assertEqual(result["credentials_saved"], "unknown")
        self.assertEqual(len([c for c in self.calls() if "--device-code" in c]), 1)

    def test_lost_worker_and_child_resume_same_unexpired_code(self):
        first = self.start()
        child_pid = self.wait_for(lambda: (self.root / "polling").read_text() if (self.root / "polling").exists() else None)
        os.kill(first["worker_pid"], signal.SIGKILL)
        os.kill(int(child_pid), signal.SIGKILL)  # Both processes belong to this synthetic test.
        self.wait_for(lambda: not self.status()["worker_active"])
        result = self.command("continue", "--flow-id", self.flow, "--owner", "resumed-session")
        self.assertTrue(result["worker_active"])
        self.approve()
        self.assertEqual(self.terminal()["outcome"], "auth_verified")
        self.assertEqual(len([c for c in self.calls() if "--no-wait" in c]), 1)

    def test_nonzero_completion_uses_independent_status_keeps_scope_gap(self):
        self.config.update(poll_exit=2, missing=["minutes:minute:write"])
        self.write_config()
        self.start()
        self.approve()
        final = self.terminal()
        self.assertEqual(final["outcome"], "auth_verified")
        self.assertEqual(final["poll_exit_code"], 2)
        self.assertEqual(final["missing_scopes"], ["minutes:minute:write"])

    def test_expired_retry_preserves_selectors_and_excludes(self):
        self.config["mode"] = "expired"
        self.write_config()
        self.start()
        self.terminal()
        self.command("retry", "--flow-id", self.flow, "--owner", "resumed-session",
                     "--authorization-confirmed")
        self.terminal()
        requests = [c for c in self.calls() if "--no-wait" in c]
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0], requests[1])

    def test_needs_refresh_does_not_start_login(self):
        self.config["status"] = "needs_refresh"
        self.write_config()
        result = self.command("start", "--profile", "authorized account", "--owner", "synthetic-session",
                              "--cli", str(self.cli), "--scope", "minutes:minute:readonly",
                              "--authorization-confirmed", okay=False)
        self.assertIn("needs_refresh", result["error"])
        self.assertFalse(any("--no-wait" in call for call in self.calls()))

    def test_missing_and_empty_existing_identity_do_not_start(self):
        for missing in (None, ""):
            with self.subTest(identity=missing):
                self.config["openid"] = missing
                self.write_config()
                self.command("start", "--profile", "authorized account", "--owner", "synthetic-session",
                             "--cli", str(self.cli), "--scope", "minutes:minute:readonly",
                             "--authorization-confirmed", okay=False)
        self.assertFalse(any("--no-wait" in call for call in self.calls()))

    def test_verification_failure_is_not_ready(self):
        self.config["verify_false"] = True
        self.write_config()
        self.start()
        self.approve()
        final = self.terminal()
        self.assertEqual(final["outcome"], "login_unverified")
        self.assertTrue(final["credentials_saved"])
        self.assertFalse(final["identity_verified"])


if __name__ == "__main__":
    unittest.main()
