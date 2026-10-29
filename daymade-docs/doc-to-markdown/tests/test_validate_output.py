"""Bidirectional controls for actual PDF/DOCX → Markdown comparisons.

Run: python3 -m unittest discover -s tests -v (Pandoc required).
All documents and text are synthetic and stay inside a temporary directory.
"""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from xml.sax.saxutils import escape
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_output.py"
SPEC = importlib.util.spec_from_file_location("validate_output", SCRIPT)
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source document.docx"
        self.output = self.root / "converted note.md"

    def compare(self, source, output):
        xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
               '<w:body><w:p><w:r><w:t>' + escape(source) +
               '</w:t></w:r></w:p></w:body></w:document>')
        with zipfile.ZipFile(self.source, "w") as archive:
            archive.writestr("word/document.xml", xml)
        self.output.write_text(output, encoding="utf-8")
        return validator.validate_conversion(self.source, self.output)

    def test_healthy_has_bounded_score_and_explicit_structure_limit(self):
        result = self.compare("ABCDE", "ABCDE")
        self.assertEqual(result.status, "pass")
        self.assertTrue(result.text_equal)
        self.assertEqual(result.overall_score, 100)
        self.assertFalse(result.structure_verified)

    def test_same_length_wrong_text_is_not_a_pass(self):
        result = self.compare("ABCDE", "VWXYZ")
        self.assertEqual(result.text_retention, 1)
        self.assertEqual(result.status, "fail")
        self.assertFalse(result.text_equal)
        self.assertEqual(result.differences[0]["source"], "ABCDE")

    def test_missing_and_duplicate_content_never_silently_pass(self):
        for changed in ("ABCDE" * 2, "ABCD", ""):
            with self.subTest(changed=changed):
                result = self.compare("ABCDE", changed)
                self.assertNotEqual(result.status, "pass")
                self.assertTrue(result.differences)

    def test_link_labels_code_and_literal_symbols_survive(self):
        result = self.compare("Read Label. x_y=-2.5; a > b",
                              "Read [Label](https://example.org). `x_y=-2.5; a > b`")
        self.assertEqual(result.status, "pass")
        result = self.compare("x_y=-2.5", "```text\nx_y=-2.5\n```")
        self.assertTrue(result.text_equal)

    def test_whitespace_is_normalized_on_both_sides(self):
        result = self.compare("甲\t乙\n丙　丁", "甲 乙\n\n丙丁")
        self.assertTrue(result.text_equal)

    def test_changed_minus_and_unit_are_not_normalized_away(self):
        for changed in ("Limit 2.5 V", "Limit -2.5 W", "Limit -2.6 V"):
            with self.subTest(changed=changed):
                result = self.compare("Limit -2.5 V", changed)
                self.assertNotEqual(result.status, "pass")
        self.assertFalse(self.compare("-2.5", "2.5").numeric_sequences_equal)

    def test_empty_source_does_not_become_success(self):
        for output in ("", "unrelated text"):
            result = self.compare("", output)
            self.assertEqual(result.status, "fail")
            self.assertIsNone(result.overall_score)
            self.assertFalse(result.source_extracted)

    def test_missing_parser_is_explicit_failure(self):
        self.compare("ABCDE", "ABCDE")
        with patch.object(validator.subprocess, "run", side_effect=FileNotFoundError("pandoc")):
            result = validator.validate_conversion(self.source, self.output)
        self.assertEqual(result.status, "fail")
        self.assertIn("pandoc", result.errors[0])

    def test_unknown_source_is_not_zero_tables_or_success(self):
        result = self.compare("ABCDE", "ABCDE")
        self.source = self.root / "unsupported.doc"
        self.source.write_text("ABCDE")
        result = validator.validate_conversion(self.source, self.output)
        self.assertEqual(result.status, "fail")
        self.assertIsNone(result.source_table_count)

    def test_raw_visible_html_requires_reader_inspection(self):
        result = self.compare("ABCDE", "ABCDE\n<div>visible label</div>")
        self.assertNotEqual(result.status, "pass")
        self.assertTrue(any("Raw HTML" in warning for warning in result.warnings))

    def test_code_is_not_counted_as_html_or_an_embedded_image(self):
        result = self.compare('<tag> ![label](file.png)', '`<tag> ![label](file.png)`')
        self.assertEqual(result.status, 'pass')
        self.assertEqual(result.output_image_count, 0)

    def test_pdf_extraction_failure_and_unknown_count_are_explicit(self):
        self.compare("ABCDE", "ABCDE")
        pdf = self.root / "input.pdf"
        pdf.write_bytes(b"%PDF-not-a-document")
        with patch.object(validator, "extract_text_from_pdf", return_value=("ABCDE", None, None)):
            result = validator.validate_conversion(pdf, self.output)
        self.assertEqual(result.status, "warn")
        self.assertTrue(result.text_equal)
        self.assertIsNone(result.table_retention)
        self.assertIsNone(result.overall_score)

    def test_pdf_text_and_numeric_failure_use_same_path(self):
        self.compare("ABCDE", "VALUE 30")
        pdf = self.root / "input.pdf"
        with patch.object(validator, "extract_text_from_pdf", return_value=("VALUE 20", 0, 0)):
            result = validator.validate_conversion(pdf, self.output)
        self.assertEqual(result.status, "fail")
        self.assertFalse(result.numeric_sequences_equal)

    def test_existing_table_and_image_count_checks_survive(self):
        self.compare("ABCDE", "ABCDE")
        pdf = self.root / "input.pdf"
        with patch.object(validator, "extract_text_from_pdf", return_value=("ABCDE", 1, 1)):
            result = validator.validate_conversion(pdf, self.output)
        self.assertEqual(result.status, "fail")
        self.assertEqual(result.table_retention, 0)
        self.assertEqual(result.image_retention, 0)

    def test_real_synthetic_pdf_and_boundary_limit(self):
        fixture = SCRIPT.parents[1] / "assets" / "pdf-fidelity"
        result = validator.validate_conversion(fixture / "source.pdf", fixture / "expected.md")
        self.assertTrue(result.text_equal, result.errors or result.differences)
        self.assertNotEqual(result.status, "fail")
        broken = validator.validate_conversion(fixture / "source.pdf", fixture / "broken.md")
        self.assertTrue(broken.text_equal)
        self.assertFalse(broken.structure_verified)
        self.assertEqual(broken.list_count, 2)

    def test_real_corrupt_pdf_fails_without_a_traceback(self):
        self.compare("ABCDE", "ABCDE")
        pdf = self.root / "corrupt.pdf"
        pdf.write_bytes(b"not a PDF")
        result = validator.validate_conversion(pdf, self.output)
        self.assertEqual(result.status, "fail")
        self.assertIn("Comparison unavailable", result.errors[0])

    def test_cli_json_and_html_are_separate_outputs(self):
        self.compare("ABCDE", "ABCDE")
        report = self.root / "report.html"
        run = subprocess.run([sys.executable, str(SCRIPT), str(self.source), str(self.output),
                              "--json", "--report", str(report)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(result["overall_score"], 100)
        self.assertIn("not certified", report.read_text())
        self.assertIn("100/100", report.read_text())


if __name__ == "__main__":
    unittest.main()
