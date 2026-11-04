"""Standard-library admission controls in the existing registered CI suite.

Real media/CLI cases remain in scripts/tests and the source adapter field check.
"""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]/"scripts"
sys.path.insert(0, str(SCRIPTS))
from core.review_queue import ReviewQueue, ReviewQueueError
from source_clip import SourceClips, MAX_WINDOW


class SourceDomainContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root/"queue.db"
        with sqlite3.connect(self.db) as conn:
            conn.executescript((SCRIPTS/"core/schema.sql").read_text())
        self.queue = ReviewQueue(self.db)
        self.file = str(self.root/"transcript.md")
        guard = patch("core.review_queue.is_temp_path", return_value=False)
        guard.start()
        self.addCleanup(guard.stop)

    def test_omitted_domain_refuses_whole_batch_and_explicit_domain_works(self):
        self.queue.enqueue([{"file": self.file, "original": "first", "domain": "project-a"}])
        with self.assertRaises(ReviewQueueError):
            self.queue.enqueue([{"file": self.file, "original": "second", "domain": "project-a"},
                                {"file": self.file, "original": "third"}])
        self.assertEqual(len(self.queue.list_items(status=None)), 1)
        self.assertEqual(len(self.queue.enqueue([{"file": self.file, "original": "second",
                                            "domain": "project-a"}])["added"]), 1)

    def test_repair_preview_and_apply_preserve_every_other_column(self):
        self.queue.enqueue([{"file": self.file, "original": "word", "domain": "general"}])
        with sqlite3.connect(self.db) as conn:
            before = conn.execute("SELECT * FROM review_items").fetchone()
            names = [row[1] for row in conn.execute("PRAGMA table_info(review_items)")]
        args = dict(file_path=self.file, from_domain="general", to_domain="project-a",
                    reason="Source manifest classification", by="fixture")
        self.queue.repair_domain([before[0]], **args)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT * FROM review_items").fetchone(), before)
        self.queue.repair_domain([before[0]], **args, apply=True)
        with sqlite3.connect(self.db) as conn:
            after = conn.execute("SELECT * FROM review_items").fetchone()
        self.assertEqual([name for name, old, new in zip(names, before, after) if old != new], ["domain"])

    def test_unbounded_window_refuses_before_any_source_operation(self):
        spec = self.root/"source.json"
        spec.write_text(json.dumps({"schema": "transcript-source-v1", "kind": "local", "path": "/synthetic.wav",
                                    "sha256": "a"*64, "fingerprint": {"size": 1}, "duration": 1000}))
        source = SourceClips(spec, self.root/"cache")
        with patch("source_clip.run_worker") as worker:
            with self.assertRaises(ValueError):
                source.fetch(0, MAX_WINDOW+1, self.root/"out.wav")
        worker.assert_not_called()
        self.assertFalse((self.root/"out.wav").exists())


if __name__ == "__main__":
    unittest.main()
