#!/usr/bin/env python3
"""Synthetic byte/schema tests. These fixtures do not establish reader behavior."""

import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import batch_html
import reader_pilot_gate as gate


SOURCE = '''<!doctype html><html><body><main>
<h1>Pilot</h1><p><a href="#Chapter">Chapter</a> <a href="#Reference">[1]</a></p>
<h2>Chapter</h2><p>Chapter landing marker.</p>
<figure><img src="assets/figure.png" alt="A to B"><p>A → B</p>
<figcaption>A leads to B.</figcaption></figure>
<h2>Reference</h2><p>Source landing marker.</p>
<pre><code>[[Note]]
[[1]](#source-1)
# Code heading
</code></pre><p>Keep <code>[[Note]]</code> and ordinary [draft].</p>
</main></body></html>'''


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fixture(directory):
    """Construct known-answer evidence with synthetic artifact bytes, never real captures."""
    root = directory / "input"
    root.mkdir()
    (root / "assets").mkdir()
    (root / "assets/figure.png").write_bytes(b"synthetic-image-bytes")
    (root / "page.html").write_text(SOURCE, encoding="utf-8")
    (root / "next.html").write_text('<h1>Next</h1><p><a href="page.md#Chapter">Back</a></p>', encoding="utf-8")
    settings = directory / "reader-settings.json"
    save(settings, {"reader": "Synthetic reader", "version": "fixture-1", "mode": "reading",
                    "theme": "light", "body_width_css_px": 680, "device_scale": 2,
                    "capture_context": "synthetic fixture; no actual UI observation"})
    plan = directory / "plan.json"
    save(plan, {"input_root": str(root), "reader_settings_path": str(settings),
                "pages": [{"source": "page.html", "output": "page.md", "selector": "main", "heading_offset": 0},
                          {"source": "next.html", "output": "next.md", "heading_offset": 1}]})
    manifest_path = directory / "manifest.json"
    manifest = batch_html.prepare(plan, manifest_path, directory / "pilot")
    artifact = directory / "observations.txt"
    artifact.write_text("Synthetic schema observations only. Chapter; [1]; A → B; A leads to B.\n")
    captures = []
    for kind in ("source", "recipient"):
        path = directory / f"{kind}-capture.txt"
        path.write_text(f"Synthetic {kind} capture; not visual acceptance.\n")
        entry = {"id": kind, "kind": kind, "source_role": "prepared", "artifact": gate.binding(path),
                 "source_sha256": manifest["inputs"]["page.html"]}
        if kind == "recipient":
            entry.update({"note_sha256": manifest["pilot"]["note"]["sha256"],
                          "assets_sha256": gate.digest_object(manifest["pilot"]["assets"]),
                          "reader_settings_sha256": manifest["reader_settings"]["sha256"]})
        captures.append(entry)
    def link(label, target, landing):
        return {"source_href": target, "label": label, "observed_label": label,
                "intended_destination": target, "observed_destination": target,
                "intended_landing_text": landing, "observed_landing_text": landing,
                "capture_id": "recipient"}
    evidence = {"schema_version": 1, "manifest_sha256": gate.file_hash(manifest_path),
                "observer": {"identity": "synthetic observer", "method": "deterministic schema fixture",
                             "observed_at": "2000-01-01T00:00:00Z"},
                "observation_artifact": gate.binding(artifact), "reader_state": manifest["reader_state"],
                "captures": captures,
                "observations": {"navigation": [link("Chapter", "#Chapter", "Chapter landing marker.")],
                                 "citations": [link("[1]", "#Reference", "Source landing marker.")],
                                 "figures": [{"source_labels": ["A", "B"], "observed_labels": ["A", "B"],
                                              "source_relations": ["A → B"], "observed_relations": ["A → B"],
                                              "source_caption": "A leads to B.", "observed_caption": "A leads to B.",
                                              "source_capture_id": "source", "recipient_capture_id": "recipient"}]}}
    evidence_path = directory / "evidence.json"
    save(evidence_path, evidence)
    return root, plan, manifest_path, evidence_path, manifest, evidence


class FixtureCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name).resolve()
        (self.root, self.plan, self.manifest_path, self.evidence_path,
         self.manifest, self.evidence) = fixture(self.directory)

    def tearDown(self):
        self.temporary.cleanup()

    def reject_evidence(self, evidence, message=None):
        save(self.evidence_path, evidence)
        with self.assertRaises(ValueError) as error:
            gate.validate_evidence(self.manifest_path, self.evidence_path)
        if message:
            self.assertIn(message, str(error.exception))


@unittest.skipUnless(shutil.which("pandoc"), "requires Pandoc")
class ReaderGateTests(FixtureCase):
    def test_healthy_evidence_has_nonzero_observation_counts(self):
        _, _, counts = gate.validate_evidence(self.manifest_path, self.evidence_path)
        self.assertEqual(counts, {"navigation": 1, "citations": 1, "figures": 1})

    def test_passed_boolean_is_not_evidence(self):
        self.reject_evidence({"schema_version": 1, "passed": True})

    def test_required_categories_missing_null_and_empty(self):
        for key in ("navigation", "citations", "figures"):
            for value in ("missing", None, []):
                with self.subTest(key=key, value=value):
                    evidence = copy.deepcopy(self.evidence)
                    if value == "missing":
                        del evidence["observations"][key]
                    else:
                        evidence["observations"][key] = value
                    self.reject_evidence(evidence, "nonempty list")

    def test_observer_and_artifact_missing_null_and_blank(self):
        for key in ("identity", "method", "observed_at"):
            for value in ("missing", None, "", "  "):
                with self.subTest(key=key, value=value):
                    evidence = copy.deepcopy(self.evidence)
                    if value == "missing":
                        del evidence["observer"][key]
                    else:
                        evidence["observer"][key] = value
                    self.reject_evidence(evidence, "nonempty text")
        for value in ("missing", None, {}, {"path": "", "sha256": ""}):
            evidence = copy.deepcopy(self.evidence)
            if value == "missing":
                del evidence["observation_artifact"]
            else:
                evidence["observation_artifact"] = value
            self.reject_evidence(evidence)

    def test_link_fields_missing_null_empty(self):
        for category in ("navigation", "citations"):
            for key in self.evidence["observations"][category][0]:
                for value in ("missing", None, ""):
                    with self.subTest(category=category, key=key, value=value):
                        evidence = copy.deepcopy(self.evidence)
                        if value == "missing":
                            del evidence["observations"][category][0][key]
                        else:
                            evidence["observations"][category][0][key] = value
                        self.reject_evidence(evidence)

    def test_wrong_landing_and_stripped_numbered_label(self):
        for key, value in (("observed_destination", "#Wrong"), ("observed_landing_text", "Wrong text"),
                           ("observed_label", "1"), ("label", "1"), ("intended_landing_text", "Invented")):
            evidence = copy.deepcopy(self.evidence)
            evidence["observations"]["citations"][0][key] = value
            self.reject_evidence(evidence)

    def test_figure_fields_missing_null_and_empty(self):
        for key in self.evidence["observations"]["figures"][0]:
            for value in ("missing", None, [], ""):
                with self.subTest(key=key, value=value):
                    evidence = copy.deepcopy(self.evidence)
                    if value == "missing":
                        del evidence["observations"]["figures"][0][key]
                    else:
                        evidence["observations"]["figures"][0][key] = value
                    self.reject_evidence(evidence)

    def test_whole_figure_mutations_reject(self):
        for key, value in (("observed_labels", ["A"]), ("observed_relations", ["B → A"]),
                           ("observed_caption", "Wrong caption"), ("source_labels", ["Invented label"])):
            evidence = copy.deepcopy(self.evidence)
            evidence["observations"]["figures"][0][key] = value
            self.reject_evidence(evidence)

    def test_reader_state_and_capture_binding_mutations_reject(self):
        for key, value in (("theme", "dark"), ("mode", "editing"), ("body_width_css_px", 320),
                           ("capture_context", "different window")):
            evidence = copy.deepcopy(self.evidence)
            evidence["reader_state"][key] = value
            self.reject_evidence(evidence, "reader state")
        for key in ("source_sha256", "note_sha256", "assets_sha256", "reader_settings_sha256"):
            evidence = copy.deepcopy(self.evidence)
            evidence["captures"][1][key] = "0" * 64
            self.reject_evidence(evidence, "stale capture")

    def test_stale_source_asset_note_settings_capture_and_artifact(self):
        paths = [self.root / "page.html", self.root / "assets/figure.png",
                 Path(self.manifest["pilot"]["note"]["path"]), Path(self.manifest["reader_settings"]["path"]),
                 Path(self.evidence["captures"][1]["artifact"]["path"]),
                 Path(self.evidence["observation_artifact"]["path"]), self.directory / "pilot/assets/figure.png"]
        for path in paths:
            with self.subTest(path=path.name):
                saved = path.read_bytes()
                path.write_bytes(saved + b" changed")
                with self.assertRaises(ValueError):
                    gate.validate_evidence(self.manifest_path, self.evidence_path)
                path.write_bytes(saved)

    def test_stale_recipe_converter_identity(self):
        for key in ("name", "manual_postprocessing", "files", "pandoc", "arguments"):
            manifest = copy.deepcopy(self.manifest)
            manifest["recipe"][key] = None
            save(self.manifest_path, manifest)
            with self.assertRaisesRegex(ValueError, "recipe"):
                gate.validate_evidence(self.manifest_path, self.evidence_path)
        save(self.manifest_path, self.manifest)
        with patch.object(gate, "recipe_identity", return_value={"mutated": True}):
            with self.assertRaisesRegex(ValueError, "recipe"):
                gate.validate_evidence(self.manifest_path, self.evidence_path)

    def test_manual_pilot_repair_cannot_authorize_fixed_batch(self):
        note = Path(self.manifest["pilot"]["note"]["path"])
        note.write_text(note.read_text() + "\nManual block repair. ^chapter\n")
        manifest = copy.deepcopy(self.manifest)
        manifest["pilot"]["note"] = gate.binding(note)
        save(self.manifest_path, manifest)
        evidence = copy.deepcopy(self.evidence)
        evidence["manifest_sha256"] = gate.file_hash(self.manifest_path)
        save(self.evidence_path, evidence)
        with self.assertRaisesRegex(ValueError, "not reproducible"):
            gate.validate_evidence(self.manifest_path, self.evidence_path)

    def test_gate_cli_has_visible_reject_and_honest_success(self):
        script = Path(gate.__file__)
        command = [sys.executable, str(script), "check", str(self.manifest_path), str(self.evidence_path)]
        healthy = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(healthy.returncode, 0, healthy.stderr)
        self.assertIn('"navigation": 1', healthy.stdout)
        self.assertIn("remain observer claims", healthy.stdout)
        save(self.evidence_path, {"passed": True})
        broken = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(broken.returncode, 1)
        self.assertIn("Reader pilot rejected:", broken.stderr)

    def test_retained_raw_source_and_declared_prepared_remap(self):
        raw = self.directory / "retained-raw.html"
        raw.write_text(SOURCE)
        prepared = self.root / "page.html"
        prepared.write_text(SOURCE.replace('href="#Chapter"', 'href="#^chapter"')
                            .replace('Chapter landing marker.</p>', 'Chapter landing marker. ^chapter</p>'))
        plan = gate.load_json(self.plan)
        plan["provenance"] = [{"prepared_source": "page.html", "raw_source": gate.binding(raw),
                               "target_mapping": [{"from": "#Chapter", "to": "#^chapter"}], "asset_mapping": []},
                              {"prepared_source": "next.html", "raw_source": gate.binding(self.root / "next.html"),
                               "target_mapping": [], "asset_mapping": []}]
        save(self.plan, plan)
        manifest_path = self.directory / "prepared-manifest.json"
        manifest = batch_html.prepare(self.plan, manifest_path, self.directory / "prepared-pilot")
        evidence = copy.deepcopy(self.evidence)
        evidence["manifest_sha256"] = gate.file_hash(manifest_path)
        evidence["captures"][0]["source_role"] = "raw"
        evidence["captures"][0]["source_sha256"] = manifest["provenance"][0]["raw_source"]["sha256"]
        evidence["captures"][1]["source_sha256"] = manifest["inputs"]["page.html"]
        evidence["captures"][1]["note_sha256"] = manifest["pilot"]["note"]["sha256"]
        for key in ("source_href", "intended_destination", "observed_destination"):
            evidence["observations"]["navigation"][0][key] = "#^chapter"
        save(self.evidence_path, evidence)
        _, _, counts = gate.validate_evidence(manifest_path, self.evidence_path)
        self.assertEqual(counts["navigation"], 1)
        result = batch_html.run_batch(manifest_path, self.evidence_path, self.directory / "prepared-batch")
        self.assertEqual(result["status"], "complete")
        self.assertIn("^chapter", (self.directory / "prepared-batch/page.md").read_text())
        self.assertEqual(raw.read_text(), SOURCE)
        raw.write_text(SOURCE + " changed")
        with self.assertRaisesRegex(ValueError, "raw_source: stale"):
            gate.validate_evidence(manifest_path, self.evidence_path)

    def test_capture_record_required_fields_missing_null_blank(self):
        for kind_index in (0, 1):
            for key in self.evidence["captures"][kind_index]:
                for value in ("missing", None, ""):
                    with self.subTest(kind_index=kind_index, key=key, value=value):
                        evidence = copy.deepcopy(self.evidence)
                        if value == "missing":
                            del evidence["captures"][kind_index][key]
                        else:
                            evidence["captures"][kind_index][key] = value
                        self.reject_evidence(evidence)


@unittest.skipUnless(shutil.which("pandoc"), "requires Pandoc")
class BatchTests(FixtureCase):
    def test_batch_retains_source_link_counts_order_assets_code_and_raw_sources(self):
        original = gate.inventory(self.root)
        output = self.directory / "batch"
        result = batch_html.run_batch(self.manifest_path, self.evidence_path, output)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["page_order"], ["page.md", "next.md"])
        self.assertEqual(result["source_hyperlinks_retained"], {"page.md": 2, "next.md": 1})
        self.assertEqual((output / "page.md").read_bytes(), Path(self.manifest["pilot"]["note"]["path"]).read_bytes())
        self.assertIn("# Code heading", (output / "page.md").read_text())
        self.assertIn("[[Note]]", (output / "page.md").read_text())
        self.assertEqual((output / "assets/figure.png").read_bytes(), (self.root / "assets/figure.png").read_bytes())
        self.assertEqual(gate.inventory(self.root), original)
        receipt = gate.load_json(output / batch_html.RECEIPT)
        self.assertEqual(receipt, result)
        for rel, digest in receipt["outputs"].items():
            self.assertEqual(gate.file_hash(output / rel), digest)

    def test_gate_rejection_precedes_any_batch_conversion_or_output_creation(self):
        evidence = copy.deepcopy(self.evidence)
        evidence["observations"]["citations"] = []
        save(self.evidence_path, evidence)
        calls = []
        owner = batch_html.html_owner.convert_html
        def observed(path, selector=None, heading_offset=0):
            calls.append(Path(path).name)
            return owner(path, selector, heading_offset)
        with patch.object(batch_html.html_owner, "convert_html", side_effect=observed):
            with self.assertRaises(ValueError):
                batch_html.run_batch(self.manifest_path, self.evidence_path, self.directory / "batch")
        self.assertFalse((self.directory / "batch").exists())
        self.assertNotIn("next.html", calls)

    def test_output_existing_input_evidence_and_pilot_overlap_reject(self):
        for output in (self.root, self.root / "nested", self.directory / "pilot",
                       self.directory / "pilot/nested", self.evidence_path, self.directory):
            with self.subTest(output=output):
                before = gate.inventory(self.root)
                with self.assertRaises((OSError, ValueError)):
                    batch_html.run_batch(self.manifest_path, self.evidence_path, output)
                self.assertEqual(before, gate.inventory(self.root))

    def test_exclusive_write_symlink_escape_and_overwrite_reject(self):
        output = self.directory / "owned"
        output.mkdir()
        (output / "assets").symlink_to(self.root / "assets", target_is_directory=True)
        with self.assertRaises(OSError):
            batch_html.write_new(output / "assets/new.txt", b"bad", output)
        self.assertFalse((self.root / "assets/new.txt").exists())
        target = output / "existing.txt"
        target.write_text("keep")
        with self.assertRaises(FileExistsError):
            batch_html.write_new(target, b"bad", output)
        self.assertEqual(target.read_text(), "keep")

    def test_prepare_rejects_duplicate_traversal_assets_and_unsupported_dependencies(self):
        healthy = gate.load_json(self.plan)
        for mutation in ("duplicate", "traversal", "asset_collision", "input_collision"):
            plan = copy.deepcopy(healthy)
            if mutation == "duplicate":
                plan["pages"][1]["output"] = "page.md"
            elif mutation == "traversal":
                plan["pages"][0]["output"] = "../escape.md"
            elif mutation == "asset_collision":
                (self.root / "batch-result.json").write_text("keep")
            else:
                (self.root / "page.md").write_text("keep")
            save(self.plan, plan)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                batch_html.prepare(self.plan, self.directory / f"{mutation}.json", self.directory / f"{mutation}-pilot")
            self.assertFalse((self.directory / f"{mutation}-pilot").exists())
            if mutation == "asset_collision":
                (self.root / "batch-result.json").unlink()
            if mutation == "input_collision":
                (self.root / "page.md").unlink()
        save(self.plan, healthy)
        for source in ('<img src="https://example.invalid/image.png">', '<base href="https://example.invalid/">',
                       '<img src="../../escape.png">', '<a href="next.html">Next</a>', '<img src="missing.png">',
                       '<a href="#Chapter" onclick="fetch(\'https://example.invalid\')">Chapter</a>',
                       '<object data="https://example.invalid/figure.svg"></object>'):
            (self.root / "page.html").write_text(source)
            with self.subTest(source=source), self.assertRaises(ValueError):
                batch_html.prepare(self.plan, self.directory / "unsupported.json", self.directory / "unsupported-pilot")
            self.assertFalse((self.directory / "unsupported-pilot").exists())

    def test_inputs_change_midrun_leaves_failed_receipt_never_complete(self):
        owner = batch_html.html_owner.convert_html
        def stale(path, selector=None, heading_offset=0):
            note = owner(path, selector, heading_offset)
            if Path(path).name == "next.html":
                (self.root / "assets/figure.png").write_bytes(b"changed mid-run")
            return note
        with patch.object(batch_html.html_owner, "convert_html", side_effect=stale):
            with self.assertRaisesRegex(ValueError, "inputs changed"):
                batch_html.run_batch(self.manifest_path, self.evidence_path, self.directory / "batch")
        receipt = gate.load_json(self.directory / "batch" / batch_html.RECEIPT)
        self.assertEqual(receipt["status"], "failed")
        self.assertNotIn("next.md", receipt["outputs_written"])

    def test_source_dependency_symlink_rejects_before_pilot(self):
        (self.root / "alias").symlink_to(self.directory, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            batch_html.prepare(self.plan, self.directory / "symlink.json", self.directory / "symlink-pilot")
        self.assertFalse((self.directory / "symlink-pilot").exists())


if __name__ == "__main__":
    unittest.main()
