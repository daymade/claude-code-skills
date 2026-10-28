#!/usr/bin/env python3
"""Synthetic controls for read-only full-document comparison; no customer fixtures."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from compare_docx import compare_records, render_markdown
from bridge_lib.docx_bridge_client import comparison_snapshot

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def paragraph(text):
    return f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"


def document(path, body, extra=None):
    extra = extra or {}
    types = {"header": "header", "footer": "footer", "footnotes": "footnotes",
             "endnotes": "endnotes", "comments": "comments"}
    root = f'<w:document xmlns:w="{W}" xmlns:r="{R}"><w:body>{body}</w:body></w:document>'
    content = '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    content += '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    content += '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    rels = f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    for n, (name, xml) in enumerate(extra.items(), 1):
        kind = types[name]
        content += f'<Override PartName="/word/{name}.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.{kind}+xml"/>'
        rels += f'<Relationship Id="rId{n}" Type="{R}/{kind}" Target="{name}.xml"/>'
    with ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", content + "</Types>")
        z.writestr("_rels/.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   f'<Relationship Id="rId1" Type="{R}/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr("word/_rels/document.xml.rels", rels + "</Relationships>")
        z.writestr("word/document.xml", root)
        for name, xml in extra.items():
            z.writestr(f"word/{name}.xml", xml)


def snapshot(texts):
    return {"stories": ["body"], "records": [
        {"story": "body", "path": f"/p{i}", "kind": "paragraph", "text": t}
        for i, t in enumerate(texts, 1)], "unsupported": []}


class AlignmentTests(unittest.TestCase):
    def test_unchanged_and_rewrite_commitment(self):
        old = snapshot(["Alpha shall deliver the report.", "Beta shall pay after acceptance."])
        report = compare_records(old, old, ["Beta shall pay"])
        self.assertEqual(report["changes"], [])
        self.assertEqual(report["unchanged_full_block_count"], 2)
        self.assertEqual(report["commitments"][0]["status"], "unchanged_full_blocks")
        changed = compare_records(old, snapshot(["Alpha shall deliver the report.",
                                  "Beta shall pay before acceptance."]), ["Beta shall pay"])
        self.assertEqual(changed["commitments"][0]["status"], "changed_or_missing")
        self.assertEqual(len(changed["changes"]), 1)

    def test_move_and_append_does_not_claim_whole_clause_deleted(self):
        clause = "The campaign budget is separately agreed by Alpha and Beta."
        report = compare_records(snapshot(["Alpha duties.", "Beta duties.", clause]),
                                 snapshot(["Alpha duties.", "Beta duties. " + clause
                                           + " Alpha executes the campaign."]))
        clues = [c for c in report["changes"] if c["kind"] == "possible_move_into_block"]
        self.assertEqual(len(clues), 1)
        self.assertEqual(clues[0]["before"]["text"], clause)
        self.assertIn("Alpha executes", clues[0]["candidates"][0]["text"])

    def test_exact_move(self):
        old = snapshot(["Alpha.", "A movable complete clause.", "Beta.", "Gamma."])
        new = snapshot(["Alpha.", "Beta.", "Gamma.", "A movable complete clause."])
        report = compare_records(old, new)
        self.assertEqual([c["kind"] for c in report["changes"]], ["moved"])

    def test_short_digit_never_pairs_with_full_clause(self):
        old = snapshot(["Payment of 1000 follows acceptance."])
        new = {"stories": ["footer"], "records": [
            {"story": "footer", "path": "/p1", "kind": "paragraph", "text": "1"}]}
        report = compare_records(old, new)
        self.assertEqual([c["kind"] for c in report["changes"]], ["removed", "added"])

    def test_partial_clause_move_and_other_sentence_removal(self):
        budget = "Campaign budget is excluded from the service quotation"
        old = snapshot(["Beta duties.", "No fixed output is promised。" + budget + "。"])
        new = snapshot(["Beta duties. " + budget + ", Alpha executes the campaign."])
        report = compare_records(old, new)
        partial = [c for c in report["changes"] if c["kind"] == "possible_partial_move"]
        self.assertEqual(len(partial), 1)
        self.assertEqual(partial[0]["matched_fragments"][0]["text"], budget)
        self.assertIn("Alpha executes", partial[0]["candidates"][0]["text"])

    def test_missing_or_whitespace_anchor_not_unchanged(self):
        old = snapshot(["Alpha."])
        report = compare_records(old, old, ["Absent"])
        self.assertEqual(report["commitments"][0]["status"], "baseline_missing")
        with self.assertRaises(ValueError):
            compare_records(old, old, [" "])

    def test_literal_markdown_and_coverage_limits(self):
        old = snapshot(["Alpha | Beta"])
        new = snapshot(["Alpha | Gamma"])
        new["unsupported"] = ["body:drawing"]
        report = compare_records(old, new)
        output = render_markdown(report)
        self.assertIn("Alpha \\| Beta", output)
        self.assertIn("覆盖缺口", output)
        self.assertEqual(report["coverage"]["before_records"], 1)


DOTNET_SCRIPT = shutil.which("dotnet-script") or str(Path.home() / ".dotnet/tools/dotnet-script")


@unittest.skipUnless(Path(DOTNET_SCRIPT).is_file() and shutil.which("dotnet"),
                     "requires documented .NET/dotnet-script dependency")
class SdkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="docx-compare-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_all_stories_and_merged_dates(self):
        before = self.root / "sent baseline.docx"
        after = self.root / "returned.docx"
        def parts(suffix):
            return {"header": f'<w:hdr xmlns:w="{W}">{paragraph("Header " + suffix)}</w:hdr>',
                    "footer": f'<w:ftr xmlns:w="{W}">{paragraph("Footer " + suffix)}</w:ftr>',
                    "footnotes": f'<w:footnotes xmlns:w="{W}"><w:footnote w:id="1">{paragraph("Note " + suffix)}</w:footnote></w:footnotes>',
                    "endnotes": f'<w:endnotes xmlns:w="{W}"><w:endnote w:id="2">{paragraph("End " + suffix)}</w:endnote></w:endnotes>'}
        table_old = '<w:tbl><w:tr><w:tc>' + paragraph("2031-01-02") + '</w:tc><w:tc>' + paragraph("2031-01-09") + '</w:tc></w:tr></w:tbl>'
        table_new = '<w:tbl><w:tr><w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr>' + paragraph("2031-01-02 to 2031-01-09") + '</w:tc></w:tr></w:tbl>'
        document(before, paragraph("Body old") + table_old, parts("old"))
        document(after, paragraph("Body new") + table_new, parts("new"))
        original_hashes = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (before, after)]
        old, new = comparison_snapshot(before), comparison_snapshot(after)
        self.assertEqual(len(old["stories"]), 5)
        self.assertEqual(len(old["records"]), 8)
        self.assertEqual(len(new["records"]), 7)
        report = compare_records(old, new)
        affected = {r["story"] for c in report["changes"] for r in [c["before"], c["after"]] if r}
        self.assertEqual(affected, set(old["stories"]))
        self.assertTrue(any(c["before"] and c["before"]["kind"] == "table_shape"
                            for c in report["changes"]))
        self.assertTrue(any(c["after"] and "2031-01-02 to 2031-01-09" in c["after"]["text"]
                            for c in report["changes"]))
        self.assertTrue(any(c["kind"] == "possible_move_into_block"
                            and c["before"]["text"] == "2031-01-09"
                            for c in report["changes"]))
        self.assertEqual(original_hashes, [hashlib.sha256(p.read_bytes()).hexdigest() for p in (before, after)])

    def test_revision_kinds_fail_before_comparison(self):
        cases = {
            "inline": '<w:p><w:ins w:id="1"><w:r><w:t>New</w:t></w:r></w:ins></w:p>',
            "paragraph": '<w:p><w:pPr><w:rPr><w:del w:id="1"/></w:rPr></w:pPr><w:r><w:t>Old</w:t></w:r></w:p>',
            "property": '<w:p><w:pPr><w:pPrChange w:id="1"><w:pPr/></w:pPrChange></w:pPr></w:p>',
            "move": '<w:p><w:moveFrom w:id="1"><w:r><w:t>Old</w:t></w:r></w:moveFrom></w:p>',
            "table": '<w:tbl><w:tr><w:tc><w:tcPr><w:cellDel w:id="1"/></w:tcPr>' + paragraph("Old") + '</w:tc></w:tr></w:tbl>',
            "custom_xml": '<w:customXmlInsRangeStart w:id="1"/>' + paragraph("New"),
            "conflict": '<w:p xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"><w14:conflictIns><w:r><w:t>New</w:t></w:r></w14:conflictIns></w:p>',
        }
        for name, xml in cases.items():
            with self.subTest(kind=name):
                path = self.root / f"{name}.docx"
                document(path, xml)
                with self.assertRaisesRegex(RuntimeError, "Comparison not performed"):
                    comparison_snapshot(path)
        header = self.root / "header-revision.docx"
        document(header, paragraph("Body"), {"header": f'<w:hdr xmlns:w="{W}">{cases["inline"]}</w:hdr>'})
        with self.assertRaisesRegex(RuntimeError, "header:/word/header.xml:ins"):
            comparison_snapshot(header)

    def test_legacy_tracked_reading_is_preserved(self):
        path = self.root / "tracked.docx"
        document(path, '<w:p><w:r><w:t>Alpha </w:t></w:r><w:del w:id="1">'
                 '<w:r><w:delText>old</w:delText></w:r></w:del><w:ins w:id="2">'
                 '<w:r><w:t>new</w:t></w:r></w:ins></w:p>')
        run = subprocess.run([sys.executable, str(SCRIPTS / "extract_review.py"), str(path), "--json"],
                             text=True, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        details = json.loads(run.stdout)["revisions"]["details"]
        self.assertEqual(len(details), 1)
        self.assertEqual(details[0]["deletedText"], "old")
        self.assertEqual(details[0]["insertedText"], "new")
        rejected = subprocess.run([sys.executable, str(SCRIPTS / "compare_docx.py"), str(path), str(path)],
                                  text=True, capture_output=True)
        self.assertEqual(rejected.returncode, 2)
        self.assertEqual(rejected.stdout, "")
        self.assertIn("原件未改", rejected.stderr)
        self.assertIn("独立副本", rejected.stderr)

    def test_sdk_marks_non_text_coverage_gap(self):
        path = self.root / "symbol.docx"
        document(path, '<w:p><w:r><w:sym w:font="Wingdings" w:char="F0A7"/></w:r></w:p>')
        result = comparison_snapshot(path)
        self.assertEqual(result["unsupported"], ["body:sym"])
        self.assertEqual(result["records"], [])

    def test_zero_trace_legacy_cli_and_comparison_cli(self):
        before, after = self.root / "baseline.docx", self.root / "returned.docx"
        document(before, paragraph("Alpha must deliver a report."))
        document(after, paragraph("Alpha must deliver a report on Tuesday."))
        for script, args in [("extract_review.py", [str(after), "--json"]),
                             ("compare_docx.py", [str(before), str(after), "--json"])]:
            run = subprocess.run([sys.executable, str(SCRIPTS / script), *args],
                                 text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            data = json.loads(run.stdout)
            if script == "extract_review.py":
                self.assertEqual(data["comments"]["summary"]["total"], 0)
                self.assertEqual(data["revisions"]["summary"]["revisedParagraphsCount"], 0)
            else:
                self.assertEqual(len(data["changes"]), 1)


if __name__ == "__main__":
    unittest.main()
