"""Queue closure is independent of arrival, event confirmation and scoring."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

import test_event_followup as helpers

log, legacy = helpers.log, helpers.legacy


class AccountFollowupTests(unittest.TestCase):
    forecast = helpers.EventFollowupTests.forecast
    review = helpers.EventFollowupTests.review

    def setUp(self):
        helpers.EventFollowupTests.setUp(self)
        self.row = self.forecast()
        self.hit = self.review(self.row, event_start="2026-10-02T18:00:00Z",
                               event_end="2026-10-02T18:00:00Z", time_basis="occurrence",
                               first_event_verified=True)
        for account in ("1234abcd", "5678abcd"):
            self.review(self.row, unknown=True, account_status="unknown", account_ref=account,
                        account_checked_at="2026-10-02T23:00:00Z")
        self.finding = log.append_finding(self.path.parent / "findings.jsonl", {
            "invocation": "account", "query": "Synthetic current identity", "endpoints": [],
            "readings": {"account_ref": "5678abcd"}}, self.now)
        self.decision = {"forecast_id": self.row["id"], "account_ref": "1234abcd",
                         "status": "closed", "reason": "Account left the monitoring context.",
                         "evidence_refs": [self.finding["id"]]}

    def test_close_reopen_roundtrip_does_not_change_arrival_event_or_hit(self):
        original = self.path.read_bytes()
        before = log.summarize(self.path)
        closed = log.append_account_followup(self.path, self.decision)
        after = log.summarize(self.path)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(after["cycle_counts"], before["cycle_counts"])
        self.assertEqual(after["recent_resolved"], before["recent_resolved"])
        self.assertEqual([x["account_ref"] for x in after["account_followup"]], ["5678abcd"])
        self.assertEqual(after["closed_account_followups"][0]["account_status"], "unknown")
        self.assertEqual(after["closed_account_followups"][0]["followup_id"], closed["id"])
        self.assertEqual(log.append_account_followup(self.path, self.decision)["id"], closed["id"])
        reopened = log.append_account_followup(self.path, {**self.decision, "status": "open"})
        self.assertNotEqual(reopened["id"], closed["id"])
        self.assertEqual(len(log.followup_plan(self.path)["account_tasks"]), 2)
        closed_again = log.append_account_followup(self.path, self.decision)
        self.assertNotEqual(closed_again["id"], closed["id"])
        self.assertEqual(len(log.followup_plan(self.path)["closed_account_tasks"]), 1)

    def test_arrival_review_cannot_implicitly_reopen_closed_followup(self):
        log.append_account_followup(self.path, self.decision)
        self.review(self.row, unknown=True, account_status="not_delivered", account_ref="1234abcd",
                    account_checked_at="2026-10-02T23:42:54Z")
        result = log.followup_plan(self.path)
        self.assertEqual([x["account_ref"] for x in result["account_tasks"]], ["5678abcd"])
        self.assertEqual(result["closed_account_tasks"][0]["account_status"], "not_delivered")

    def test_old_new_writers_and_readers_keep_shared_history_compatible(self):
        # The actual frozen old reader ignores the additive sidecar, keeping the
        # account's unresolved arrival rather than interpreting closure as delivery.
        before = legacy.summarize(self.path)
        log.append_account_followup(self.path, self.decision)
        after = legacy.summarize(self.path)
        self.assertEqual(after, {**before, "checked_at": after["checked_at"]})
        self.assertEqual(log.summarize(self.path)["cycle_counts"], before["cycle_counts"])
        self.review(self.row, writer=legacy, unknown=True, account_status="not_delivered",
                    account_ref="1234abcd", account_checked_at="2026-10-02T23:42:54Z")
        self.assertEqual([x["account_ref"] for x in log.followup_plan(self.path)["account_tasks"]],
                         ["5678abcd"])

    def test_invalid_decisions_leave_last_valid_record_and_other_state_intact(self):
        log.append_account_followup(self.path, self.decision)
        sidecar = self.path.parent / "account_followups.jsonl"
        original = sidecar.read_bytes()
        main = self.path.read_bytes()
        for key in ("forecast_id", "account_ref", "status", "reason", "evidence_refs"):
            for value in (None, "", [], [None]):
                data = {**self.decision, key: value}
                with self.subTest(key=key, value=value), self.assertRaises((ValueError, TypeError)):
                    log.append_account_followup(self.path, data)
            data = dict(self.decision)
            data.pop(key)
            with self.subTest(missing=key), self.assertRaises(ValueError):
                log.append_account_followup(self.path, data)
        for delta in ({"status": "delivered"}, {"account_ref": "ffffffff"},
                      {"forecast_id": "not-a-record"}, {"evidence_refs": ["not-a-finding"]}):
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                log.append_account_followup(self.path, {**self.decision, **delta})
        self.assertEqual(sidecar.read_bytes(), original)
        self.assertEqual(self.path.read_bytes(), main)

    def test_cli_close_then_read_from_a_new_process(self):
        payload = self.path.parent / "close.json"
        payload.write_text(json.dumps(self.decision))
        cmd = [sys.executable, log.__file__, "--state-dir", str(self.path.parent), "--no-git"]
        result = subprocess.run([*cmd, "account-followup", "--input", str(payload)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        result = subprocess.run([*cmd, "followup"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        state = json.loads(result.stdout)
        self.assertEqual([x["account_ref"] for x in state["account_tasks"]], ["5678abcd"])
        self.assertEqual(state["closed_account_tasks"][0]["account_status"], "unknown")


if __name__ == "__main__":
    unittest.main()
