"""Offline controls for dated recording lookup; no account or network access."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock


SCRIPT = (Path(__file__).resolve().parents[1] / "daymade-claude-code" /
          "lark-cli-router" / "scripts" / "find_recording_candidates.py")
SPEC = importlib.util.spec_from_file_location("lark_recording_lookup", SCRIPT)
LOOKUP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LOOKUP)
DAY = "2026-03-10"


def item(token="record-a", url="https://example.feishu.cn/minutes/record-a", display="Review"):
    return {"token": token, "meta_data": {"app_link": url}, "display_info": display}


def response(items=(), *, more=False, token=None):
    data = {"items": list(items), "has_more": more}
    if token is not None:
        data["page_token"] = token
    return raw_response({"ok": True, "data": data})


def raw_response(payload):
    return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")


class Runner:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []
        self.lock = threading.Lock()

    def __call__(self, command, **kwargs):
        profile = command[command.index("--profile") + 1]
        page = command[command.index("--page-token") + 1] if "--page-token" in command else None
        with self.lock:
            self.calls.append((command, kwargs))
        result = self.routes[(profile, page)]
        if isinstance(result, Exception):
            raise result
        return result


class LookupTests(unittest.TestCase):
    def run_lookup(self, routes, profiles=("account-a",)):
        runner = Runner(routes)
        return LOOKUP.lookup(list(profiles), DAY, DAY, runner=runner), runner

    def test_multiple_profiles_pages_deduplicate_without_losing_sources(self):
        changed = item(url="https://example.feishu.cn/minutes/record-a-other", display="Updated")
        result, runner = self.run_lookup({
            ("account-a", None): response([item()], more=True, token="second"),
            ("account-a", "second"): response([item(), changed, item("record-b", None)]),
            ("account-b", None): response([item(display="Shared")]),
        }, ("account-a", "account-b", "account-a"))
        self.assertTrue(result["complete"])
        self.assertEqual(result["requested_profiles"], ["account-a", "account-b"])
        self.assertEqual(len(runner.calls), 3)
        self.assertEqual([c["token"] for c in result["candidates"]], ["record-a", "record-b"])
        self.assertEqual(len(result["candidates"][0]["sources"]), 3)
        self.assertIsNone(result["candidates"][1]["sources"][0]["url"])
        self.assertEqual([r["pages_read"] for r in result["coverage"]], [2, 1])
        for command, options in runner.calls:
            self.assertEqual(command[0], "lark-cli")
            self.assertIn("minutes", command)
            self.assertIn("+search", command)
            self.assertNotIn("--query", command)
            self.assertNotIn("--participant-ids", command)
            self.assertEqual(command[command.index("--as") + 1], "user")
            self.assertEqual(command[command.index("--start") + 1], DAY)
            self.assertEqual(command[command.index("--end") + 1], DAY)
            self.assertTrue(options["capture_output"])
            for key in ("LARK_CLI_NO_PROXY", "LARKSUITE_CLI_NO_UPDATE_NOTIFIER",
                        "LARKSUITE_CLI_NO_SKILLS_NOTIFIER"):
                self.assertEqual(options["env"][key], "1")

    def test_complete_empty_is_distinct_from_failed_profile(self):
        result, runner = self.run_lookup({("account-a", None): response()})
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["coverage"][0]["pages_read"], 1)
        self.assertEqual(len(runner.calls), 1)
        failed, _ = self.run_lookup({("account-a", None): OSError("synthetic unavailable CLI")})
        self.assertFalse(failed["complete"])
        self.assertEqual(failed["status"], "error")
        self.assertEqual(failed["coverage"][0]["pages_read"], 0)

    def test_one_failed_profile_keeps_another_profiles_candidates(self):
        result, runner = self.run_lookup({
            ("account-a", None): response([item()]),
            ("account-b", None): SimpleNamespace(returncode=7, stdout="", stderr="synthetic denied"),
        }, ("account-a", "account-b"))
        self.assertFalse(result["complete"])
        self.assertEqual(result["status"], "partial")
        self.assertEqual([c["token"] for c in result["candidates"]], ["record-a"])
        self.assertEqual([r["status"] for r in result["coverage"]], ["complete", "error"])
        self.assertEqual(len(runner.calls), 2)

    def test_second_page_failure_keeps_first_page(self):
        result, runner = self.run_lookup({
            ("account-a", None): response([item()], more=True, token="second"),
            ("account-a", "second"): subprocess.TimeoutExpired("synthetic command", 1),
        })
        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["coverage"][0]["pages_read"], 1)
        self.assertEqual(len(runner.calls), 2)

    def test_missing_null_and_wrong_response_shapes_never_report_complete(self):
        healthy_data = {"items": [item()], "has_more": False}
        invalid = [None, [], {}, {"ok": False}, {"ok": True},
                   {"data": healthy_data}, {"ok": None, "data": healthy_data},
                   {"ok": False, "data": healthy_data},
                   {"ok": True, "data": None}, {"ok": True, "data": {}},
                   {"ok": True, "data": []},
                   {"ok": True, "data": {"items": None, "has_more": False}},
                   {"ok": True, "data": {"items": {}, "has_more": False}},
                   {"ok": True, "data": {"items": [item()]}},
                   {"ok": True, "data": {"items": [item()], "has_more": None}},
                   {"ok": True, "data": {"items": [], "has_more": 0}}]
        for payload in invalid:
            with self.subTest(payload=payload):
                result, runner = self.run_lookup({("account-a", None): raw_response(payload)})
                self.assertFalse(result["complete"])
                self.assertIsNotNone(result["coverage"][0]["error"])
                self.assertEqual(len(runner.calls), 1)

    def test_bad_json_is_an_error(self):
        result, _ = self.run_lookup({("account-a", None):
                                    SimpleNamespace(returncode=0, stdout="not JSON", stderr="")})
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["coverage"][0]["error"]["type"], "JSONDecodeError")

    def test_invalid_items_are_explicit_and_valid_neighbors_are_retained(self):
        result, runner = self.run_lookup({("account-a", None): response([item(), None, {}])})
        self.assertFalse(result["complete"])
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["coverage"][0]["items_received"], 3)
        self.assertEqual(result["coverage"][0]["usable_items"], 1)
        self.assertEqual(len(runner.calls), 1)

    def test_no_url_is_unknown_and_is_never_constructed(self):
        result, _ = self.run_lookup({("account-a", None): response([
            {"token": "record-a"}, {"token": "record-b", "meta_data": None},
            item("record-c", ""), item("record-d", 1),
        ])})
        self.assertTrue(result["complete"])
        self.assertEqual(len(result["candidates"]), 4)
        self.assertTrue(all(c["sources"][0]["url"] is None for c in result["candidates"]))

    def test_missing_blank_and_repeated_next_tokens_are_incomplete(self):
        for token in (None, "", " "):
            with self.subTest(token=token):
                result, runner = self.run_lookup({("account-a", None):
                                                  response([item()], more=True, token=token)})
                self.assertFalse(result["complete"])
                self.assertEqual(len(runner.calls), 1)
                self.assertEqual(len(result["candidates"]), 1)
        result, runner = self.run_lookup({
            ("account-a", None): response([item()], more=True, token="again"),
            ("account-a", "again"): response([item("record-b")], more=True, token="again"),
        })
        self.assertFalse(result["complete"])
        self.assertEqual(len(runner.calls), 2)
        self.assertEqual(len(result["candidates"]), 2)
        explicit_null, null_runner = self.run_lookup({("account-a", None): raw_response(
            {"ok": True, "data": {"items": [item()], "has_more": True, "page_token": None}})})
        self.assertFalse(explicit_null["complete"])
        self.assertEqual(len(null_runner.calls), 1)

    def test_invalid_arguments_do_not_query(self):
        valid = ["--profile", "account-a", "--start", DAY, "--end", DAY]
        cases = [[], valid[2:], valid[:4], ["--profile", "", *valid[2:]],
                 ["--profile", " ", *valid[2:]],
                 ["--profile", "account-a", "--start", "2026-02-30", "--end", DAY],
                 ["--profile", "account-a", "--start", "20260310", "--end", DAY],
                 ["--profile", "account-a", "--start", "2026-03-11", "--end", DAY]]
        cases.extend([*valid, "--timeout", value] for value in ("0", "-1", "nan", "inf"))
        for arguments in cases:
            with self.subTest(arguments=arguments), mock.patch.object(LOOKUP, "lookup") as query:
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                    LOOKUP.main(arguments)
                self.assertEqual(error.exception.code, 2)
                query.assert_not_called()

    def test_cli_exit_follows_coverage(self):
        arguments = ["--profile", "account-a", "--start", DAY, "--end", DAY]
        for complete, code in ((True, 0), (False, 1)):
            with mock.patch.object(LOOKUP, "lookup", return_value={"complete": complete}):
                with redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(LOOKUP.main(arguments), code)
                self.assertEqual(json.loads(output.getvalue())["complete"], complete)

    def test_real_subprocess_cli_contract_with_an_offline_fake(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / "lark-cli"
            fake.write_text(f"#!{sys.executable}\n" +
                            "import json,sys\n"
                            "p=sys.argv[sys.argv.index('--profile')+1]\n"
                            "assert sys.argv[3:5]==['minutes','+search']\n"
                            "print(json.dumps({'ok':True,'data':{'has_more':False,'items':"
                            "[{'token':p,'display_info':'Synthetic recording','meta_data':"
                            "{'app_link':'https://example.feishu.cn/minutes/'+p}}]}}))\n")
            fake.chmod(0o755)
            env = dict(os.environ, PATH=directory + os.pathsep + os.environ.get("PATH", ""))
            result = subprocess.run([sys.executable, str(SCRIPT), "--profile", "account-a",
                                     "--profile", "account-b", "--start", DAY, "--end", DAY],
                                    env=env, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertTrue(data["complete"])
            self.assertEqual(data["requested_profiles"], ["account-a", "account-b"])
            self.assertEqual(len(data["coverage"]), 2)
            self.assertEqual(len(data["candidates"]), 2)


if __name__ == "__main__":
    unittest.main()
