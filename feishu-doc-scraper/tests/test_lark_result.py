import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from lark_result import CLIError, parse_cli_result, wiki_token


class LarkResultTests(unittest.TestCase):
    def test_wiki_url_is_reduced_to_token_before_cli(self):
        self.assertEqual(wiki_token("https://demo.feishu.cn/wiki/ExampleNode123?from=copy"), "ExampleNode123")
        self.assertEqual(wiki_token("ExampleNode123"), "ExampleNode123")
        self.assertEqual(wiki_token("https://demo.larksuite.com/wiki/ExampleNode123/"), "ExampleNode123")

    def test_wrong_locator_never_becomes_a_permission_result(self):
        for value in (None, "", "../node", "https://example.org/wiki/ExampleNode123",
                      "https://demo.feishu.cn/docx/ExampleNode123",
                      "https://demo.feishu.cn/wiki/a%2Fb", "http://demo.feishu.cn/wiki/node"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                wiki_token(value)

    def test_error_after_refresh_notice_on_stderr_is_preserved(self):
        error = {"ok": False, "error": {"type": "authorization", "code": 131006,
                                       "message": "resource access denied"}}
        with self.assertRaises(CLIError) as caught:
            parse_cli_result("", "[lark-cli] token refreshed\n" + json.dumps(error), 3)
        self.assertEqual(caught.exception.envelope["error"]["code"], 131006)

    def test_success_on_stdout_and_notice_on_stderr(self):
        item = {"ok": True, "data": {"title": "Source title"}}
        self.assertEqual(parse_cli_result(json.dumps(item), "[notice] refreshed", 0), item)

    def test_nested_source_values_are_not_promoted_to_cli_envelopes(self):
        item = {"ok": True, "data": {"records": [{"ok": False, "error": {"code": 1}}]}}
        self.assertEqual(parse_cli_result(json.dumps(item, indent=2), "", 0), item)
        with self.assertRaises(CLIError):
            parse_cli_result('{"broken": [\n {"ok": true, "data": {}}', "", 0)

    def test_empty_malformed_and_conflicting_results_are_unknown(self):
        good = json.dumps({"ok": True, "data": {}})
        bad = json.dumps({"ok": False, "error": {"code": 131005}})
        for out, err, status in [("", "", 0), ("not JSON", "failed", 1),
                                 (good, bad, 0), (good, "", 3),
                                 ('{"ok": true}', "", 0), ('{"ok": false}', "", 3)]:
            with self.subTest(out=out, status=status), self.assertRaises(CLIError):
                parse_cli_result(out, err, status)

    def test_export_receipt_requires_explicit_schema(self):
        receipt = {"records_count": 1, "has_more": False, "record_file": "records.ndjson"}
        with self.assertRaises(CLIError):
            parse_cli_result(json.dumps(receipt), "", 0)
        self.assertEqual(parse_cli_result(json.dumps(receipt), "", 0,
                        receipt_keys=("records_count", "has_more", "record_file")), receipt)


if __name__ == "__main__":
    unittest.main()
