#!/usr/bin/env python3
"""--lookup TERM: one command answers "does anything already claim this term?"

It must find the term in dictionary rules (active AND disabled, as FROM or
TO), context rules, roster-loaded name variants and review-queue rows, report
each section separately, and say plainly when nothing anywhere matches — the
gap it closes is that --probe needs a corpus and the alternative was raw SQL.
"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import cli.commands as commands  # noqa: E402
import core.review_queue as rq  # noqa: E402
from cli.commands import cmd_lookup  # noqa: E402
from utils.config import reset_config  # noqa: E402


class TestLookup(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="tf_lookup_"))
        config_dir = self.root / "config"
        config_dir.mkdir()
        self._env = {k: os.environ.get(k) for k in
                     ("TRANSCRIPT_FIXER_CONFIG_DIR", "TRANSCRIPT_FIXER_DB_PATH",
                      "TRANSCRIPT_FIXER_PEOPLE_ROSTER")}
        os.environ["TRANSCRIPT_FIXER_CONFIG_DIR"] = str(config_dir)
        os.environ["TRANSCRIPT_FIXER_DB_PATH"] = str(config_dir / "corrections.db")
        roster = self.root / "people.md"
        roster.write_text("### 张三\n- **ASR 变体**: 章三, 张叁\n", encoding="utf-8")
        os.environ["TRANSCRIPT_FIXER_PEOPLE_ROSTER"] = str(roster)
        reset_config()
        self._gettempdir = rq.tempfile.gettempdir
        fake = self.root / "faketmp"
        fake.mkdir()
        rq.tempfile.gettempdir = lambda: str(fake)

        service = commands._get_service()
        service.add_correction("克劳锐", "Claude", "testdom", notes="garble", force=True)
        service.add_correction("旧形", "新形", "testdom", force=True)
        service.report_false_positive("旧形", "新形", domain="testdom") if hasattr(service, "report_false_positive") else None
        service.add_context_rule("妙计(?=比)", "妙记", domain="testdom", description="feishu minutes cue")
        work = self.root / "work"
        work.mkdir()
        transcript = work / "meeting.md"
        transcript.write_text("发言人甲 00:00:01\n请把克劳锐的方案发我\n", encoding="utf-8")
        commands._get_review_queue().enqueue([{
            "source": "native_pass", "domain": "testdom", "file": str(transcript), "line": 2,
            "context": "请把克劳锐的方案发我", "original": "克劳锐", "suggested": "Claude",
            "kind": "entity", "evidence": "test",
        }])

    def tearDown(self):
        rq.tempfile.gettempdir = self._gettempdir
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        reset_config()
        shutil.rmtree(self.root, ignore_errors=True)

    def _lookup(self, term, domain=None, as_json=True):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cmd_lookup(Namespace(lookup_term=term, domain=domain, json_output=as_json))
        return json.loads(out.getvalue()) if as_json else out.getvalue()

    def test_dictionary_hit_as_from_and_as_to(self):
        by_from = self._lookup("克劳锐")
        self.assertEqual([(d["from"], d["to"], d["domain"], d["is_active"]) for d in by_from["dictionary"]],
                         [("克劳锐", "Claude", "testdom", True)])
        by_to = self._lookup("claude")   # ASCII match is case-insensitive
        self.assertEqual([d["from"] for d in by_to["dictionary"]], ["克劳锐"])

    def test_disabled_rule_is_still_reported(self):
        payload = self._lookup("旧形")
        self.assertEqual(len(payload["dictionary"]), 1)
        # Whether or not the false-positive report disabled it, the row is listed
        # with its state visible rather than hidden.
        self.assertIn("is_active", payload["dictionary"][0])

    def test_context_rule_roster_and_queue_sections(self):
        self.assertEqual([r["pattern"] for r in self._lookup("妙计")["context_rules"]], ["妙计(?=比)"])
        roster = self._lookup("章三")["roster"]
        self.assertTrue(roster["path"].endswith("people.md"))
        self.assertEqual(roster["hits"], [{"variant": "章三", "canonical": "张三"}])
        self.assertEqual([h["variant"] for h in self._lookup("张三")["roster"]["hits"]], ["章三", "张叁"])
        queue = self._lookup("克劳锐")["review_queue"]
        self.assertEqual([(r["original"], r["suggested"], r["status"]) for r in queue],
                         [("克劳锐", "Claude", "pending")])

    def test_no_trace_anywhere_is_reported_not_errored(self):
        payload = self._lookup("无此词")
        self.assertEqual((payload["dictionary"], payload["context_rules"], payload["roster"]["hits"],
                          payload["review_queue"]), ([], [], [], []))
        text = self._lookup("无此词", as_json=False)
        self.assertIn("no trace anywhere", text)

    def test_domain_narrows_dictionary_scope_only(self):
        payload = self._lookup("克劳锐", domain="otherdom")
        self.assertEqual(payload["dictionary"], [])
        self.assertEqual(len(payload["review_queue"]), 1)

    def test_text_mode_names_every_section(self):
        text = self._lookup("克劳锐", as_json=False)
        for label in ("Lookup", "Dictionary rules (1)", "Context rules (0)", "People roster (0)", "Review queue (1)"):
            self.assertIn(label, text)


if __name__ == "__main__":
    unittest.main()
