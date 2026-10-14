"""Exercise bounded reads through the real CLI, with synthetic source values."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "skill_read_plan.py"


class BoundedReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source.txt"

    def tearDown(self):
        self.temp.cleanup()

    def write(self, text):
        self.source.write_bytes(text.encode("utf-8"))
        return hashlib.sha256(self.source.read_bytes()).hexdigest()

    def run_reader(self, *args, success=True):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(self.source), *map(str, args)],
            cwd=self.root, capture_output=True,
        )
        self.assertEqual(result.returncode, 0 if success else 2, result.stderr[:300])
        self.assertEqual(result.stderr, b"")
        packet = json.loads(result.stdout) if result.stdout else None
        if packet:
            self.assertEqual(packet["output_bytes"], len(result.stdout))
            self.assertEqual(packet["status"], "ok" if success else "error")
        return packet, result

    def test_legacy_plan_contiguous_and_hash_bound(self):
        digest = self.write("甲\nsecond\nthird\n")
        data, _ = self.run_reader("--max-chunk-bytes", 8)
        self.assertEqual(data["sha256"], digest)
        self.assertEqual(data["total_lines"], 3)
        self.assertEqual(sum(c["bytes"] for c in data["chunks"]), self.source.stat().st_size)
        self.assertEqual(data["chunks"][0]["start_line"], 1)
        self.assertEqual(data["chunks"][-1]["end_line"], 3)
        self.assertTrue(data["plan_complete"])
        self.assertEqual(data["source_coverage"], "metadata_only")
        self.assertNotIn("loaded", data)

    def test_json_projection_only_selected_leaf(self):
        document = {"session_id": "synthetic", "results": [{
            "record": 17, "paired_call": {"name": "exec"},
            "original": {"payload": {"output": "PRIVATE-FIXTURE-" * 10000}},
        }]}
        digest = self.write(json.dumps(document))
        packet, result = self.run_reader(
            "--json-pointer", "/results/0/record", "--json-pointer", "/results/0/paired_call/name",
            "--expect-sha256", digest, "--max-output-bytes", 1500,
        )
        self.assertEqual([r["value"] for r in packet["selections"]], [17, "exec"])
        self.assertEqual(packet["source_coverage"], "selected")
        self.assertNotIn(b"PRIVATE-FIXTURE", result.stdout)
        self.assertLessEqual(len(result.stdout), 1500)
        for pointer in ("/records", "/results", "/results/0/missing", "/results/1/record"):
            with self.subTest(pointer=pointer):
                error, failed = self.run_reader("--json-pointer", pointer, "--expect-sha256", digest, success=False)
                self.assertNotIn(b"PRIVATE-FIXTURE", failed.stdout)
                self.assertNotIn("selections", error)

    def test_plan_output_never_exceeds_cap(self):
        digest = self.write("x\n" * 200)
        seen = []
        cursor = 0
        while True:
            data, result = self.run_reader(
                "--max-chunk-bytes", 2, "--max-output-bytes", 700,
                "--cursor", cursor, "--expect-sha256", digest,
            )
            self.assertLessEqual(len(result.stdout), 700)
            self.assertFalse(data["plan_complete"])
            seen.extend(c["start_line"] for c in data["chunks"])
            if data["next_cursor"] is None:
                break
            self.assertGreater(data["next_cursor"], cursor)
            cursor = data["next_cursor"]
        self.assertEqual(seen, list(range(1, 201)))

    def test_lines_chars_unicode_and_escaping(self):
        text = '甲🙂"\\\r\n第二行\nlast'
        digest = self.write(text)
        data, result = self.run_reader("--lines", "1:2", "--expect-sha256", digest)
        self.assertEqual(data["content"], '甲🙂"\\\r\n第二行\n')
        self.assertEqual(data["range"], [1, 2])
        self.assertEqual(data["source_coverage"], "partial")
        self.assertTrue(data["requested_range_complete"])
        data, _ = self.run_reader("--chars", "1:5", "--expect-sha256", digest)
        self.assertEqual(data["content"], text[1:5])
        self.assertEqual(data["range"], [1, 5])
        self.assertLessEqual(len(result.stdout), 6000)
        full, _ = self.run_reader("--chars", f"0:{len(text)}", "--expect-sha256", digest)
        self.assertEqual(full["content"], text)
        self.assertEqual(full["source_coverage"], "full")
        self.assertNotIn("loaded", full)

    def test_oversized_line_and_giant_scalar_require_explicit_range(self):
        digest = self.write("巨🙂" * 10000)
        self.run_reader("--max-chunk-bytes", 100, success=False)
        read, _ = self.run_reader("--chars", "2:8", "--expect-sha256", digest)
        self.assertEqual(read["content"], ("巨🙂" * 10000)[2:8])
        digest = self.write(json.dumps({"results": [{"text": "巨🙂" * 10000}]}, ensure_ascii=False))
        self.run_reader("--json-pointer", "/results/0/text", "--expect-sha256", digest, success=False)
        read, _ = self.run_reader("--json-pointer", "/results/0/text", "--chars", "1:7", "--expect-sha256", digest)
        self.assertEqual(read["selections"][0]["value"], ("巨🙂" * 10000)[1:7])
        self.assertEqual(read["value_coverage"], "partial")

    def test_json_null_empty_missing_and_escaped_pointer_are_distinct(self):
        digest = self.write(json.dumps({"null": None, "empty": "", "list": [], "object": {}, "a/b": {"~": False}}))
        read, _ = self.run_reader("--json-pointer", "/null", "--json-pointer", "/empty", "--json-pointer", "/a~1b/~0", "--expect-sha256", digest)
        self.assertEqual([(r["type"], r["value"]) for r in read["selections"]], [("null", None), ("string", ""), ("boolean", False)])
        for pointer in ("/missing", "/list", "/object", "", "/a~2b", "/list/00"):
            with self.subTest(pointer=pointer):
                self.run_reader("--json-pointer", pointer, "--expect-sha256", digest, success=False)
        shape, _ = self.run_reader("--schema-json", "--at-pointer", "/list")
        self.assertEqual(shape["shape"], {"type": "array", "count": 0})
        self.assertTrue(shape["schema_complete"])

    def test_schema_pages_are_bounded_metadata_not_values(self):
        digest = self.write(json.dumps({f"key-{i}": "DO-NOT-PRINT" for i in range(120)}))
        keys = []
        cursor = 0
        while True:
            shape, result = self.run_reader("--schema-json", "--cursor", cursor, "--expect-sha256", digest, "--max-output-bytes", 700)
            self.assertLessEqual(len(result.stdout), 700)
            self.assertNotIn(b"DO-NOT-PRINT", result.stdout)
            self.assertFalse(shape["schema_complete"])
            keys.extend(r["key"] for r in shape["entries"])
            if shape["next_cursor"] is None:
                break
            self.assertGreater(shape["next_cursor"], cursor)
            cursor = shape["next_cursor"]
        self.assertEqual(keys, [f"key-{i}" for i in range(120)])

    def test_source_change_and_content_without_hash_fail(self):
        old = self.write("first\n")
        self.write("second\n")
        error, _ = self.run_reader("--lines", "1:1", "--expect-sha256", old, success=False)
        self.assertEqual(error["error"], "source_changed")
        self.run_reader("--lines", "1:1", success=False)
        self.run_reader("--schema-json", "--cursor", 1, success=False)

    def test_empty_file_and_legacy_line_ending_boundary(self):
        digest = self.write("")
        self.run_reader("--max-chunk-bytes", 200, success=False)
        empty, _ = self.run_reader("--chars", "0:0", "--expect-sha256", digest)
        self.assertEqual(empty["content"], "")
        self.run_reader("--schema-json", success=False)
        self.write("first\rsecond")
        self.run_reader("--max-chunk-bytes", 200, success=False)

    def test_exact_serialized_cap_and_no_partial_error_payload(self):
        digest = self.write('"\\\n' * 30)
        args = ("--chars", "0:90", "--expect-sha256", digest)
        packet, result = self.run_reader(*args)
        size = len(result.stdout)
        self.run_reader(*args, "--max-output-bytes", size)
        error, failed = self.run_reader(*args, "--max-output-bytes", size - 1, success=False)
        self.assertEqual(error["error"], "output_too_large")
        self.assertNotIn("content", error)
        self.assertLessEqual(len(failed.stdout), size - 1)
        for cap in (1, 0, -1):
            with self.subTest(cap=cap):
                _, failed = self.run_reader(*args, "--max-output-bytes", cap, success=False)
                if cap > 0:
                    self.assertLessEqual(len(failed.stdout), cap)
        _, rejected = self.run_reader("--unknown", "secret", "--max-output-bytes", 1, success=False)
        self.assertEqual(rejected.stdout, b"")

    def test_invalid_and_ambiguous_arguments_do_not_read_as_success(self):
        digest = self.write('{"x":1,"x":2}')
        self.run_reader("--schema-json", success=False)
        for text in ("{broken", '{"x":NaN}', '{"x":Infinity}'):
            self.write(text)
            self.run_reader("--schema-json", success=False)
        digest = self.write('{"a":"ok","b":"other"}')
        invalid = [
            ["--max-chunk-bytes", 0], ["--schema-json", "--lines", "1:1"],
            ["--chars", "0:1", "--json-pointer", "/a", "--json-pointer", "/b"],
            ["--lines", "1:1", "--at-pointer", "/a"], ["--chars", "0:999"],
            ["--lines", "0:1"], ["--chars", "1:0"], ["--json-pointer", "/a", "--cursor", 1],
            ["--chars", "0:1", "--expect-sha256", ""], ["--unknown", "secret"],
        ]
        for args in invalid:
            with self.subTest(args=args):
                self.run_reader(*args, "--expect-sha256", digest, success=False)


if __name__ == "__main__":
    unittest.main()
