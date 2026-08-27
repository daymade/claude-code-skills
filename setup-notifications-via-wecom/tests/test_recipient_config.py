import importlib.util
import hashlib
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


SENDER = load_module("send_wecom", ROOT / "scripts" / "send_wecom.py")
SETTER = load_module("set_recipient", ROOT / "scripts" / "set_recipient.py")


class RecipientConfigTests(unittest.TestCase):
    def configured(self, scope="self", label="Owner self channel"):
        sender_path = (ROOT / "scripts" / "send_wecom.py").resolve()
        return {
            "webhook_url": "https://example.invalid/hook",
            "recipient_scope": scope,
            "recipient_label": label,
            "sender_path": str(sender_path),
            "sender_sha256": SETTER.sha256_path(sender_path),
        }

    def test_setter_preserves_webhook_and_mode(self):
        with tempfile.TemporaryDirectory(prefix="tinkle_wecom_") as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({"webhook_url": "https://example.invalid/hook"}))
            path.chmod(0o600)
            sender_path = ROOT / "scripts" / "send_wecom.py"
            self.assertTrue(
                SETTER.set_recipient(
                    path, "self", "Owner self channel", sender_path
                )
            )
            self.assertFalse(
                SETTER.set_recipient(
                    path, "self", "Owner self channel", sender_path
                )
            )
            config = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(config["webhook_url"], "https://example.invalid/hook")
            self.assertEqual(config["recipient_scope"], "self")
            self.assertEqual(config["recipient_label"], "Owner self channel")
            self.assertEqual(config["sender_path"], str(sender_path.resolve()))
            self.assertEqual(
                config["sender_sha256"], SETTER.sha256_path(sender_path.resolve())
            )
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(list(path.parent.glob(".tinkle_*.tmp")), [])

    def test_sender_rejects_unclassified_target(self):
        with tempfile.TemporaryDirectory(prefix="tinkle_wecom_") as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({"webhook_url": "https://example.invalid/hook"}))
            with mock.patch.object(SENDER, "CONFIG_PATH", path):
                with self.assertRaises(SystemExit):
                    SENDER.load_config()

    def test_sender_accepts_explicit_other_target(self):
        with tempfile.TemporaryDirectory(prefix="tinkle_wecom_") as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps(self.configured("others", "Engineering group")))
            with mock.patch.object(SENDER, "CONFIG_PATH", path):
                config = SENDER.load_config()
            self.assertEqual(config["recipient_scope"], "others")
            self.assertEqual(config["recipient_label"], "Engineering group")

    def test_outbox_requires_notify_wecom_contract(self):
        with tempfile.TemporaryDirectory(prefix="tinkle_wecom_") as tmp:
            path = Path(tmp) / "alert.json"
            config = self.configured()
            webhook_sha256 = hashlib.sha256(
                config["webhook_url"].encode("utf-8")
            ).hexdigest()
            payload = {
                "schema": "runaway_self_alert_v1",
                "delivery": {
                    "status": "pending_auto_self",
                    "sender_skill": "notify-wecom",
                    "recipient_scope": "self",
                    "recipient_label": config["recipient_label"],
                    "webhook_sha256": webhook_sha256,
                    "sender_path": config["sender_path"],
                    "sender_sha256": config["sender_sha256"],
                },
                "message": "hello",
            }
            path.write_text(json.dumps(payload))
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(SENDER.load_outbox(path, config, digest), "hello")
            path.write_text(json.dumps({"message": "hello"}))
            with self.assertRaises(SystemExit):
                SENDER.load_outbox(
                    path, config, hashlib.sha256(path.read_bytes()).hexdigest()
                )

    def test_outbox_digest_rejects_replaced_content(self):
        with tempfile.TemporaryDirectory(prefix="tinkle_wecom_") as tmp:
            path = Path(tmp) / "alert.json"
            path.write_text('{"message":"approved"}')
            approved = hashlib.sha256(path.read_bytes()).hexdigest()
            path.write_text('{"message":"replaced"}')
            with self.assertRaises(SystemExit):
                SENDER.load_outbox(path, self.configured(), approved)

    def test_outbox_main_disables_http_retry(self):
        with tempfile.TemporaryDirectory(prefix="tinkle_wecom_") as tmp:
            root = Path(tmp)
            config_path = root / "config.json"
            config = self.configured()
            config_path.write_text(json.dumps(config))
            webhook_sha256 = hashlib.sha256(
                config["webhook_url"].encode("utf-8")
            ).hexdigest()
            alert_path = root / "alert.json"
            alert_path.write_text(
                json.dumps({
                    "schema": "runaway_self_alert_v1",
                    "delivery": {
                        "status": "pending_auto_self",
                        "sender_skill": "notify-wecom",
                        "recipient_scope": "self",
                        "recipient_label": config["recipient_label"],
                        "webhook_sha256": webhook_sha256,
                        "sender_path": config["sender_path"],
                        "sender_sha256": config["sender_sha256"],
                    },
                    "message": "hello",
                })
            )
            digest = hashlib.sha256(alert_path.read_bytes()).hexdigest()
            argv = [
                "send_wecom.py", "--outbox", str(alert_path),
                "--expected-sha256", digest,
            ]
            with (
                mock.patch.object(SENDER, "CONFIG_PATH", config_path),
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(
                    SENDER, "send_message", return_value={"errcode": 0, "errmsg": "ok"}
                ) as sender,
            ):
                SENDER.main()
            sender.assert_called_once_with(
                config["webhook_url"], "hello", max_attempts=1
            )


if __name__ == "__main__":
    unittest.main()
