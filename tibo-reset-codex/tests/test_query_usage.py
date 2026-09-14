import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request


SPEC = importlib.util.spec_from_file_location(
    "query_usage", Path(__file__).resolve().parents[1] / "scripts" / "query_usage.py")
usage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(usage)


class UsageTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            "account_id": "account-test", "email": "account@example.com", "plan_type": "pro",
            "rate_limit": {"primary_window": {
                "used_percent": 48, "limit_window_seconds": 604800, "reset_at": 1893456000},
                "secondary_window": None},
            "credits": {"has_credits": False, "balance": "0"},
            "rate_limit_reset_credits": {"available_count": 2, "applicable_available_count": 0},
        }

    def read(self):
        return usage.normalize_usage(self.data, "account-test")

    def test_zero_purchased_credits_does_not_erase_banked_resets(self):
        result = self.read()
        self.assertEqual(result["banked_resets_available"], 2)
        self.assertEqual(result["banked_resets_applicable_now"], 0)
        self.assertEqual(result["purchased_credits_balance"], "0")
        self.assertEqual(result["windows"][0]["remaining_percent"], 52)

    def test_swapped_slots_are_identified_by_duration(self):
        weekly = self.data["rate_limit"]["primary_window"]
        self.data["rate_limit"] = {"secondary_window": weekly, "primary_window": {
            "used_percent": 3, "limit_window_seconds": 18000, "reset_at": None}}
        result = {w["window_seconds"]: w for w in self.read()["windows"]}
        self.assertEqual(result[604800]["remaining_percent"], 52)
        self.assertEqual(result[18000]["remaining_percent"], 97)
        self.assertIsNone(result[18000]["reset_at_utc"])

    def test_full_and_exhausted_and_nearly_full_are_distinct(self):
        for used, remaining in [(0, 100), (3, 97), (100, 0)]:
            with self.subTest(used=used):
                self.data["rate_limit"]["primary_window"]["used_percent"] = used
                self.assertEqual(self.read()["windows"][0]["remaining_percent"], remaining)

    def test_missing_banked_is_unknown_but_explicit_zero_is_zero(self):
        del self.data["rate_limit_reset_credits"]
        self.assertIsNone(self.read()["banked_resets_available"])
        self.assertEqual(self.read()["status"], "partial")
        self.data["rate_limit_reset_credits"] = {"available_count": 0}
        self.assertEqual(self.read()["banked_resets_available"], 0)

    def test_auxiliary_zero_bucket_never_becomes_weekly_quota(self):
        auxiliary = copy.deepcopy(self.data["rate_limit"])
        auxiliary["primary_window"]["used_percent"] = 0
        self.data["rate_limit"] = None
        self.data["additional_rate_limits"] = [{"limit_id": "auxiliary", "rate_limit": auxiliary}]
        self.data["code_review_rate_limit"] = {"used_percent": 0}
        self.assertEqual(self.read()["windows"], [])
        self.assertEqual(self.read()["status"], "partial")

    def test_wrong_account_or_email_is_rejected(self):
        with self.assertRaises(usage.UsageError):
            usage.normalize_usage(self.data, "another-account")
        with self.assertRaises(usage.UsageError):
            usage.normalize_usage(self.data, "account-test", "other@example.com")

    def test_unknown_duration_cannot_be_reported_as_full_quota(self):
        self.data["rate_limit"]["primary_window"].update(
            limit_window_seconds=1, used_percent=0)
        result = self.read()
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["windows"], [])

    def test_duplicate_weekly_windows_cannot_report_conflicting_balances(self):
        weekly = self.data["rate_limit"]["primary_window"]
        for other_used in [weekly["used_percent"], 0, 100, "invalid"]:
            with self.subTest(other_used=other_used):
                self.data["rate_limit"]["secondary_window"] = dict(weekly, used_percent=other_used)
                result = self.read()
                self.assertEqual(result["status"], "partial")
                self.assertEqual(result["windows"], [])

    def test_missing_reset_time_and_applicability_are_partial(self):
        del self.data["rate_limit"]["primary_window"]["reset_at"]
        del self.data["rate_limit_reset_credits"]["applicable_available_count"]
        result = self.read()
        self.assertEqual(result["status"], "partial")
        self.assertIsNone(result["windows"][0]["reset_at_utc"])
        self.assertIsNone(result["banked_resets_applicable_now"])
        self.assertEqual(result["banked_resets_available"], 2)

    def test_invalid_counts_and_percentages_do_not_produce_full_quota(self):
        for value in [True, -1, 101, float("nan"), "0"]:
            with self.subTest(value=value):
                self.data["rate_limit"]["primary_window"]["used_percent"] = value
                self.assertEqual(self.read()["windows"], [])
        self.data["rate_limit_reset_credits"]["available_count"] = True
        self.assertIsNone(self.read()["banked_resets_available"])

    def test_redirects_are_refused(self):
        request = urllib.request.Request(usage.USAGE_URL)
        with self.assertRaises(usage.UsageError):
            usage.NoRedirect().redirect_request(request, None, 302, "", {}, "https://example.com")

    def test_query_reads_auth_without_writes_and_uses_only_get(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "auth.json"
            path.write_text(json.dumps({"auth_mode": "chatgpt", "tokens": {
                "account_id": "account-test", "access_token": "test-only"}}))
            before = path.read_bytes()
            with patch.object(usage.urllib.request, "build_opener") as factory:
                factory.return_value.open.return_value = io.BytesIO(json.dumps(self.data).encode())
                result = usage.query(path)
                request = factory.return_value.open.call_args.args[0]
                self.assertEqual(request.full_url, usage.USAGE_URL)
                self.assertEqual(request.get_method(), "GET")
                self.assertEqual(factory.return_value.open.call_count, 1)
                self.assertNotIn("test-only", json.dumps(result))
            self.assertEqual(path.read_bytes(), before)

    def test_auth_failure_is_not_quota_exhaustion_or_a_retry_loop(self):
        with patch.object(usage, "read_auth", return_value=({
            "access_token": "test-only", "account_id": "account-test"}, None)):
            with patch.object(usage.urllib.request, "build_opener") as factory:
                factory.return_value.open.side_effect = urllib.error.HTTPError(
                    usage.USAGE_URL, 401, "test-only must not leak", {}, None)
                with self.assertRaises(usage.UsageError) as caught:
                    usage.query(Path("unused"))
                self.assertIn("quota unknown", str(caught.exception))
                self.assertNotIn("test-only", str(caught.exception))
                self.assertEqual(factory.return_value.open.call_count, 1)

    def test_transient_failures_stop_after_three_attempts(self):
        with patch.object(usage, "read_auth", return_value=({
            "access_token": "test-only", "account_id": "account-test"}, None)):
            with patch.object(usage.urllib.request, "build_opener") as factory, patch.object(usage.time, "sleep"):
                factory.return_value.open.side_effect = urllib.error.URLError("test-only")
                with self.assertRaises(usage.UsageError):
                    usage.query(Path("unused"))
                self.assertEqual(factory.return_value.open.call_count, 3)


if __name__ == "__main__":
    unittest.main()
