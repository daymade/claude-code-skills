"""Network-free comment capture contracts, including both pagination layers."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).parents[1] / "scripts" / "fetch_comments.py"
spec = importlib.util.spec_from_file_location("fetch_comments", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def reply(rid, text="Keep the reviewed examples", **extra):
    return {"reply_id": rid, "user_id": "reader-1", "create_time": 1700000000,
            "content": {"elements": [{"type": "text_run", "text_run": {"text": text}}]}, **extra}


def card(cid, **extra):
    return {"comment_id": cid, "is_solved": False, "is_whole": False,
            "quote": "The tool cannot assess presentation quality", **extra}


def page(items, more=False, token=""):
    return {"items": items, "has_more": more, "page_token": token,
            "file_token": "document-1", "file_type": "docx"}


class CommentTests(unittest.TestCase):
    def test_two_page_layers_preserve_all_feedback(self):
        calls = []
        c1 = card("c1", reply_list={"replies": [reply("r1")]},
                  relation={"content_deleted": True, "relation": "{}"})
        responses = [page([c1], True, "cp2"), page([reply("r1")], True, "rp2"),
                     page([reply("r2", "Agreed\n```text\nquoted fence")]),
                     page([card("c2", is_solved=True)]), page([reply("r3")])]
        def call(args, profile):
            calls.append((args, profile))
            return responses.pop(0)
        got = mod.capture("https://example.feishu.cn/wiki/node", "all", "chosen", caller=call)
        self.assertEqual(got["status"], "complete")
        self.assertEqual([len(t["replies"]) for t in got["comments"]], [2, 1])
        self.assertEqual(calls[3][0][-2:], ["--page-token", "cp2"])
        self.assertEqual(json.loads(calls[2][0][-1])["page_token"], "rp2")
        self.assertTrue(all(p == "chosen" for _, p in calls))
        self.assertEqual(got["comments"][0]["card"], c1)
        text = mod.render(got)
        self.assertIn('"content_deleted": true', text)
        self.assertIn("````text\nAgreed", text)

    def test_zero_comments_is_complete_only_after_success(self):
        got = mod.capture("https://example.feishu.cn/docx/doc", caller=lambda *_: page([]))
        self.assertEqual(got["status"], "complete")
        self.assertIn("No comments in the selected scope", mod.render(got))
        self.assertEqual(got["solved_status"], "false")

    def test_reply_failure_retains_received_card_and_partial_state(self):
        count = 0
        def call(*_):
            nonlocal count
            count += 1
            if count == 1:
                return page([card("c1", reply_list={"replies": [reply("preview")]})])
            raise mod.CaptureError("permission denied")
        got = mod.capture("https://example.feishu.cn/docx/doc", caller=call)
        self.assertEqual(got["status"], "partial")
        self.assertFalse(got["threads_complete"])
        self.assertEqual(got["comments"][0]["card"]["reply_list"]["replies"][0]["reply_id"], "preview")
        self.assertNotIn("No comments", mod.render(got))

    def test_explicit_pagination_boundary_required(self):
        for response in ({"items": []}, page([], True, "")):
            with self.subTest(response=response):
                got = mod.capture("https://example.feishu.cn/docx/doc", caller=lambda *_: response)
                self.assertEqual(got["status"], "partial")
                self.assertTrue(got["errors"])

    def test_repeated_cursor_and_page_budget_fail(self):
        for max_pages in (1, 5):
            with self.subTest(max_pages=max_pages):
                got = mod.capture("https://example.feishu.cn/docx/doc", max_pages=max_pages,
                                  caller=lambda *_: page([], True, "same"))
                self.assertEqual(got["status"], "partial")

    def test_preview_reply_cannot_disappear(self):
        responses = [page([card("c1", reply_list={"replies": [reply("r1")]})]), page([])]
        got = mod.capture("https://example.feishu.cn/docx/doc", caller=lambda *_: responses.pop(0))
        self.assertEqual(got["status"], "partial")

    def test_unknown_elements_and_images_are_retained_not_called_read(self):
        r = reply("r1", extra={"image_list": ["image-token"]})
        r["content"]["elements"].append({"type": "future_format", "payload": "feedback"})
        responses = [page([card("c1")]), page([r])]
        got = mod.capture("https://example.feishu.cn/docx/doc", caller=lambda *_: responses.pop(0))
        self.assertTrue(got["threads_complete"])
        self.assertEqual(got["status"], "partial")
        self.assertEqual(len(got["unexpanded_content"]), 2)
        self.assertIn("future_format", mod.render(got))
        self.assertIn("image-token", mod.render(got))

    def test_identity_drift_is_rejected(self):
        responses = [page([], True, "next"), {**page([]), "file_token": "another-document"}]
        got = mod.capture("https://example.feishu.cn/docx/doc", caller=lambda *_: responses.pop(0))
        self.assertEqual(got["status"], "partial")
        self.assertIn("identity", got["errors"][0])

    def test_malformed_cli_envelope_and_reply_are_not_success(self):
        for stdout in ('[]', '{"ok":true,"data":null}', 'not json'):
            with patch.object(mod.subprocess, "run") as run:
                run.return_value.returncode = 0
                run.return_value.stdout = stdout
                with self.assertRaises(mod.CaptureError):
                    mod.call_cli(["drive", "+list-comments"])
        responses = [page([card("c1")]), page([{**reply("r1"), "content": None}])]
        got = mod.capture("https://example.feishu.cn/docx/doc", caller=lambda *_: responses.pop(0))
        self.assertEqual(got["status"], "partial")

    def test_changed_duplicate_reply_is_rejected(self):
        responses = [page([card("c1")]), page([reply("r1")], True, "next"),
                     page([reply("r1", "different")])]
        got = mod.capture("https://example.feishu.cn/docx/doc", caller=lambda *_: responses.pop(0))
        self.assertEqual(got["status"], "partial")

    def test_new_snapshot_and_old_snapshot_preserved(self):
        got = mod.capture("https://example.feishu.cn/docx/doc", caller=lambda *_: page([]))
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "discussion"
            mod.write_snapshot(target, got)
            before = {p.name: p.read_bytes() for p in target.iterdir()}
            self.assertEqual(json.loads(before["comments.json"])["status"], "complete")
            with self.assertRaises(ValueError):
                mod.write_snapshot(target, {**got, "status": "partial"})
            self.assertEqual(before, {p.name: p.read_bytes() for p in target.iterdir()})

    def test_cli_partial_exit_and_existing_output(self):
        partial = mod.capture("https://example.feishu.cn/docx/doc", caller=lambda *_: {})
        with tempfile.TemporaryDirectory() as directory, patch.object(mod, "capture", return_value=partial):
            target = str(Path(directory) / "discussion")
            with patch("sys.stdout"):
                self.assertEqual(mod.main(["--url", "https://example.feishu.cn/docx/doc", "--out-dir", target]), 3)
            with self.assertRaises(SystemExit):
                mod.main(["--url", "https://example.feishu.cn/docx/doc", "--out-dir", target])


if __name__ == "__main__":
    unittest.main()
