import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location("sender_network", Path(__file__).parents[1] / "scripts/send_wecom.py")
sender = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sender)


class NetworkPolicyTest(unittest.TestCase):
    def run_sender(self, response):
        config = {"webhook_url": "https://example.invalid/bot", "recipient_scope": "self", "recipient_label": "test"}
        with mock.patch.object(sender, "load_config", return_value=config), mock.patch.object(sys, "argv", ["send_wecom.py", "--message", "test"]), mock.patch.object(sender, "send_message", return_value=response) as send:
            sender.main()
            send.assert_called_once()

    def test_main_preserves_required_proxy_and_no_proxy(self):
        route = {"https_proxy": "http://127.0.0.1:1082", "HTTP_PROXY": "http://127.0.0.1:1082", "no_proxy": "localhost"}
        with mock.patch.dict(os.environ, route, clear=True):
            self.run_sender({"errcode": 0, "errmsg": "ok"})
            self.assertEqual(dict(os.environ), route)

    def test_main_does_not_create_proxy_on_direct_host(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.run_sender({"errcode": 0, "errmsg": "ok"})
            self.assertEqual(dict(os.environ), {})

    def test_http_success_with_wecom_rejection_is_failure(self):
        with self.assertRaises(SystemExit) as error:
            self.run_sender({"errcode": 40008, "errmsg": "invalid message type"})
        self.assertEqual(error.exception.code, 1)

    def test_network_failure_does_not_change_route(self):
        route = {"https_proxy": "http://127.0.0.1:1082"}
        with mock.patch.dict(os.environ, route, clear=True), mock.patch.object(sender.urllib.request, "urlopen", side_effect=sender.urllib.error.URLError("timeout")) as opened:
            with self.assertRaises(RuntimeError):
                sender.send_message("https://example.invalid/bot", "test", max_attempts=1)
            opened.assert_called_once()
            self.assertEqual(dict(os.environ), route)


if __name__ == "__main__":
    unittest.main()
