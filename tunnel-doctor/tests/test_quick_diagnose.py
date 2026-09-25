import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "quick_diagnose.py"
spec = importlib.util.spec_from_file_location("quick_diagnose", SCRIPT)
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)


def probe(ok):
    return {"ok": ok, "http_code": "200" if ok else "000", "exit_code": 0 if ok else 28, "stderr": ""}


class QuickDiagnoseTests(unittest.TestCase):
    def test_scutil_endpoint_requires_enabled_host_and_port(self):
        raw = """<dictionary> {
  HTTPEnable : 1
  HTTPProxy : 127.0.0.1
  HTTPPort : 1082
  HTTPSEnable : 1
  HTTPSProxy : 127.0.0.1
  HTTPSPort : 1082
}"""
        with patch.object(doctor, "run", return_value=(0, raw, "")):
            parsed = doctor.parse_scutil_proxy()
        self.assertEqual(parsed["https_proxy"], "http://127.0.0.1:1082")
        self.assertEqual(parsed["http_proxy"], "http://127.0.0.1:1082")

        with patch.object(doctor, "run", return_value=(0, "HTTPSEnable : 1\nHTTPSProxy : 127.0.0.1", "")):
            self.assertEqual(doctor.parse_scutil_proxy()["https_proxy"], "")
        with patch.object(doctor, "run", return_value=(1, "", "failed")):
            self.assertEqual(doctor.parse_scutil_proxy()["https_proxy"], "")

    def test_curl_modes_force_or_bypass_proxy(self):
        with patch.object(doctor, "run", return_value=(0, "200", "")) as run:
            doctor.curl_status("https://example.test", 2, "direct")
            self.assertEqual(run.call_args.args[0][-2:], ["--noproxy", "*"])
            doctor.curl_status("https://example.test", 2, "forced_proxy", "http://127.0.0.1:1082")
            self.assertEqual(run.call_args.args[0][-4:], ["--noproxy", "", "--proxy", "http://127.0.0.1:1082"])

    def test_env_proxy_follows_url_scheme(self):
        with patch.dict(os.environ, {"http_proxy": "http://127.0.0.1:3", "https_proxy": "http://127.0.0.1:2"}, clear=True):
            self.assertEqual(doctor.pick_proxy_url("https://example.test/"), "http://127.0.0.1:2")
            self.assertEqual(doctor.pick_proxy_url("http://example.test/"), "http://127.0.0.1:3")
        with patch.dict(os.environ, {"HTTPS_PROXY": "http://127.0.0.1:2", "ALL_PROXY": "http://127.0.0.1:4"}, clear=True):
            self.assertEqual(doctor.pick_proxy_url("https://example.test/"), "http://127.0.0.1:2")
            self.assertEqual(doctor.pick_proxy_url("http://example.test/"), "http://127.0.0.1:4")

    def report(self, direct, system_proxy, proxy_endpoint="http://127.0.0.1:1082", env_proxy=None, ambient=None):
        info = {
            "exceptions": [], "http_enabled": True, "https_enabled": True,
            "http_proxy": proxy_endpoint, "https_proxy": proxy_endpoint,
        }

        def curl(_url, _timeout, mode, proxy_url=None):
            if mode == "direct":
                return probe(direct)
            if mode == "forced_proxy":
                if proxy_url == env_proxy:
                    return probe(False)
                return probe(system_proxy)
            return probe(system_proxy if ambient is None else ambient)

        with patch.object(doctor, "parse_scutil_proxy", return_value=info), \
             patch.object(doctor, "pick_proxy_url", return_value=env_proxy), \
             patch.object(doctor, "curl_status", side_effect=curl), \
             patch.object(doctor, "strict_tls_check", return_value=None), \
             patch.object(doctor, "resolve_host", return_value=["203.0.113.1"]):
            return doctor.build_report("example.test", "https://example.test/", 2, None)

    def test_missing_exception_is_not_itself_a_fault(self):
        for direct, proxied in ((False, False), (True, True), (False, True)):
            with self.subTest(direct=direct, proxied=proxied):
                report = self.report(direct, proxied)
                self.assertFalse(any("bypass" in item["fix"].lower() or "DIRECT/skip-proxy" in item["fix"]
                                     for item in report["findings"]))

    def test_bypass_requires_successful_direct_and_failed_proxy(self):
        report = self.report(True, False)
        self.assertIn("System proxy probe failed; client impact unverified", [item["title"] for item in report["findings"]])

    def test_system_proxy_probe_alone_does_not_claim_client_failure(self):
        report = self.report(True, False, ambient=True)
        finding = next(item for item in report["findings"] if item["title"].startswith("System proxy probe"))
        self.assertEqual(finding["level"], "warn")
        self.assertIn("If that path also fails", finding["fix"])
        self.assertFalse(any(item["level"] == "error" for item in report["findings"]))

    def test_missing_proxy_endpoint_leaves_unknown(self):
        report = self.report(True, False, "")
        self.assertIsNone(report["connectivity"]["system_proxy"])
        self.assertFalse(any("System proxy path fails" in item["title"] for item in report["findings"]))

    def test_failed_forced_env_proxy_does_not_condemn_working_ambient_path(self):
        env_proxy = "http://127.0.0.1:3"
        healthy = self.report(True, True, env_proxy=env_proxy, ambient=True)
        self.assertFalse(any("Proxy path is broken" in item["title"] for item in healthy["findings"]))

        broken = self.report(True, True, env_proxy=env_proxy, ambient=False)
        self.assertIn("Proxy path is broken for target host", [item["title"] for item in broken["findings"]])

    def test_lowercase_no_proxy_precedes_uppercase_when_populated(self):
        with patch.dict(os.environ, {"NO_PROXY": "example.test", "no_proxy": "other.test"}, clear=True):
            report = self.report(True, True)
            self.assertEqual(report["env_no_proxy"], "other.test")
            self.assertFalse(report["host_in_no_proxy"])
        with patch.dict(os.environ, {"NO_PROXY": "example.test", "no_proxy": ""}, clear=True):
            report = self.report(True, True)
            self.assertEqual(report["env_no_proxy"], "example.test")
            self.assertTrue(report["host_in_no_proxy"])


if __name__ == "__main__":
    unittest.main()
