import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "scripts" / "research_assets.py"
RUNS = ROOT / "scripts" / "provider_runs.py"


class ResearchAssetsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.catalog = self.root / "research-catalog.jsonl"
        self.spec = self.root / "spec.json"
        self.spec.write_text(json.dumps({
            "schema_version": 2,
            "study_id": "filing-study",
            "as_of": "2026-09-26",
            "business_outcome": "Explain a fund filing with traceable evidence",
            "dispatch_context": "Target: Fund Alpha (FA01); seed: https://example.org/report.pdf",
            "decision_questions": [{"id": "Q1", "question": "What changed?"}],
            "lanes": [{"lane_id": "official", "provider": "direct",
                       "mode": "primary-source", "task_id": "Q1",
                       "prompt": "Target: Fund Alpha (FA01); seed: https://example.org/report.pdf. Open the issuer filing"}],
        }), encoding="utf-8")
        self.request = self.root / "request.txt"
        self.request.write_text("Explain the filing using the original source", encoding="utf-8")
        spec = json.loads(self.spec.read_text())
        spec["request_mode_contract"] = {
            "basis": {"kind": "user", "path": "sources/requests/request.txt",
                      "sha256": hashlib.sha256(self.request.read_bytes()).hexdigest(),
                      "quote": self.request.read_text(), "locator": "synthetic intake turn"},
            "interpretation": "User explicitly asks for a direct original source route",
            "modes": [{"request_id": "R1", "provider": "direct", "mode": "primary-source", "lane_ids": ["official"]}],
        }
        self.spec.write_text(json.dumps(spec), encoding="utf-8")
        self.study = self.root / "study"

    def cli(self, script, *args):
        args = list(args)
        if script == ASSETS and args[0] == "start":
            args.extend(["--request-source", self.request])
        if script == RUNS and args[0] == "record" and args[3] == "collected" and "--imported" in args:
            proof = Path(args[1]) / "sources" / "direct-route.txt"
            proof.write_text("Synthetic investigator command log: direct primary-source retrieval", encoding="utf-8")
            args.extend(["--observed-provider", "direct", "--observed-mode", "primary-source", "--mode-proof", proof])
        return subprocess.run([sys.executable, str(script), *map(str, args)],
                              capture_output=True, text=True)

    def start(self):
        result = self.cli(ASSETS, "start", self.study, "--spec", self.spec,
                          "--catalog", self.catalog, "--query", "fund filing")
        self.assertEqual(result.returncode, 0, result.stderr)

    def collect(self, body):
        path = self.study / "sources" / "official.md"
        path.write_text(body, encoding="utf-8")
        result = self.cli(RUNS, "record", self.study, "official", "collected",
                          "--imported", "--origin-task-id", "local-source",
                          "--file", path)
        self.assertEqual(result.returncode, 0, result.stderr)

    def source(self, url="https://example.org/report.pdf", status="approved", **kwargs):
        args = ["source", self.study, "--url", url, "--title", "Official filing",
                "--status", status, "--source-type", "official",
                "--accessibility", "public", "--family", "filing-1",
                "--locator", "page 4, table 2"]
        for key, value in kwargs.items():
            args.extend(["--" + key.replace("_", "-"), value])
        return self.cli(ASSETS, *args)

    def claim(self, study=None, url="https://example.org/report.pdf"):
        directory = study or self.study
        sid = hashlib.sha256(url.encode()).hexdigest()[:20]
        return self.cli(ASSETS, "claim", directory, "--claim-id", "C1",
                        "--text", "The filing shows a change", "--status", "supported",
                        "--source-id", sid, "--locator", "page 4, table 2",
                        "--boundary", "An end-date holding does not date the trade")

    def test_today_shape_fails_then_single_route_with_original_passes_and_reuses(self):
        # A prose answer and temporary evidence without a study cannot pass.
        outside_report = self.root / "answer.md"
        outside_report.write_text("See [C1] https://example.org/report.pdf", encoding="utf-8")
        missing = self.cli(ASSETS, "check", self.study, "--report", outside_report)
        self.assertEqual(missing.returncode, 2)

        self.start()
        report = self.study / "report.md"
        report.write_text(outside_report.read_text(), encoding="utf-8")
        unfinished = self.cli(ASSETS, "check", self.study, "--report", report)
        self.assertEqual(unfinished.returncode, 2)
        self.assertIn("nonterminal lanes", unfinished.stderr)

        self.collect("Official filing: https://example.org/report.pdf")
        no_sources = self.cli(ASSETS, "check", self.study, "--report", report)
        self.assertEqual(no_sources.returncode, 2)
        self.assertIn("approved original", no_sources.stderr)

        original = self.root / "report.pdf"
        original.write_bytes(b"%PDF-example-source")
        approved = self.source(file=original, locator="page 4, table 2")
        self.assertEqual(approved.returncode, 0, approved.stderr)
        self.assertEqual(self.claim().returncode, 0)
        outside = self.cli(ASSETS, "check", self.study, "--report", outside_report)
        self.assertEqual(outside.returncode, 2)
        self.assertIn("inside the durable study", outside.stderr)
        self.assertEqual(self.cli(ASSETS, "check", self.study, "--report", report).returncode, 0)
        registered = self.cli(ASSETS, "register", self.study, "--catalog", self.catalog,
                              "--report", report, "--term", "fund", "--term", "filing")
        self.assertEqual(registered.returncode, 0, registered.stderr)

        next_spec = self.root / "next-spec.json"
        next_study = json.loads(self.spec.read_text())
        next_study["study_id"] = "followup-study"
        next_spec.write_text(json.dumps(next_study), encoding="utf-8")
        next_dir = self.root / "followup"
        discovered = self.cli(ASSETS, "start", next_dir, "--spec", next_spec,
                              "--catalog", self.catalog, "--query", "fund")
        self.assertEqual(discovered.returncode, 0, discovered.stderr)
        self.assertIn("filing-study", discovered.stdout)
        receipt = json.loads((next_dir / "prior-research.json").read_text())
        self.assertEqual(receipt["matches"][0]["decision"], "pending")
        decision = self.cli(ASSETS, "decide", next_dir, "filing-study", "reuse",
                            "--reason", "same fund filing; recheck its date before citation")
        self.assertEqual(decision.returncode, 0, decision.stderr)

    def test_dispatch_context_blocks_ambiguous_provider_prompt(self):
        spec = json.loads(self.spec.read_text())
        spec["lanes"].append({"lane_id": "provider", "provider": "example",
                              "mode": "research", "task_id": "Q1",
                              "prompt": "Research the four funds and specified stocks"})
        self.spec.write_text(json.dumps(spec), encoding="utf-8")
        blocked = self.cli(ASSETS, "start", self.study, "--spec", self.spec,
                           "--catalog", self.catalog, "--query", "fund filing")
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("omits dispatch_context", blocked.stderr)
        self.assertFalse(self.study.exists())
        spec["lanes"][-1]["prompt"] += "\n" + spec["dispatch_context"]
        self.spec.write_text(json.dumps(spec), encoding="utf-8")
        self.assertEqual(self.cli(ASSETS, "start", self.study, "--spec", self.spec,
                                  "--catalog", self.catalog, "--query", "fund filing").returncode, 0)

    def test_uncataloged_report_link_and_changed_original_fail(self):
        self.start()
        self.collect("Retrieved an issuer document.")
        original = self.root / "report.pdf"
        original.write_bytes(b"%PDF-example-source")
        self.assertEqual(self.source(file=original).returncode, 0)
        report = self.study / "report.md"
        self.assertEqual(self.claim().returncode, 0)
        report.write_text("See [C1] https://example.org/report.pdf and https://example.org/other",
                          encoding="utf-8")
        missing = self.cli(ASSETS, "check", self.study, "--report", report)
        self.assertEqual(missing.returncode, 2)
        self.assertIn("report URLs lack approved", missing.stderr)
        report.write_text("See [C1] https://example.org/report.pdf", encoding="utf-8")
        self.assertEqual(self.cli(ASSETS, "check", self.study, "--report", report).returncode, 0)
        originals = list((self.study / "sources" / "originals").iterdir())
        self.assertEqual(len(originals), 1)
        originals[0].write_bytes(b"changed")
        tampered = self.cli(ASSETS, "check", self.study, "--report", report)
        self.assertEqual(tampered.returncode, 2)
        self.assertIn("source artifact missing or changed", tampered.stderr)

    def test_provider_links_are_harvested_without_becoming_verified(self):
        self.start()
        self.collect("Sources: https://example.org/report.pdf https://example.org/lead")
        original = self.root / "report.pdf"
        original.write_bytes(b"%PDF-example-source")
        self.assertEqual(self.source(file=original).returncode, 0)
        self.assertEqual(self.claim().returncode, 0)
        report = self.study / "report.md"
        report.write_text("[C1] https://example.org/report.pdf", encoding="utf-8")
        unrecorded = self.cli(ASSETS, "check", self.study, "--report", report)
        self.assertEqual(unrecorded.returncode, 2)
        self.assertIn("provider URLs unrecorded", unrecorded.stderr)
        harvested = self.cli(ASSETS, "harvest", self.study)
        self.assertEqual(harvested.returncode, 0, harvested.stderr)
        self.assertIn("harvested 1", harvested.stdout)
        self.assertEqual(self.cli(ASSETS, "check", self.study, "--report", report).returncode, 0)
        report.write_text("[C1] https://example.org/lead", encoding="utf-8")
        lead_cited = self.cli(ASSETS, "check", self.study, "--report", report)
        self.assertEqual(lead_cited.returncode, 2)
        self.assertIn("report URLs lack approved", lead_cited.stderr)

    def test_html_export_harvests_citation_anchors_without_ui_assets(self):
        self.start()
        original = self.root / "report.pdf"
        original.write_bytes(b"%PDF-example-source")
        self.assertEqual(self.source(file=original).returncode, 0)
        self.collect("Official source already recorded")
        html = self.study / "sources" / "rendered.html"
        html.write_text('<link rel="icon" href="https://assets.example/favicon.ico">'
                        '<svg xmlns="http://www.w3.org/2000/svg"></svg>'
                        '<script>const image="https://assets.example/script.png";</script>'
                        '<a href="https://example.org/lead">candidate citation</a>'
                        '<p>Visible source: https://example.org/visible</p>', encoding="utf-8")
        self.assertEqual(self.cli(RUNS, "record", self.study, "official", "collected",
                                  "--origin-task-id", "local-source", "--file", html).returncode, 0)
        harvested = self.cli(ASSETS, "harvest", self.study)
        self.assertEqual(harvested.returncode, 0, harvested.stderr)
        self.assertIn("harvested 2", harvested.stdout)
        urls = [json.loads(line)["url"] for line in (self.study / "source-ledger.jsonl").read_text().splitlines()]
        self.assertIn("https://example.org/lead", urls)
        self.assertIn("https://example.org/visible", urls)
        self.assertNotIn("https://assets.example/favicon.ico", urls)
        self.assertNotIn("https://assets.example/script.png", urls)
        self.assertNotIn("http://www.w3.org/2000/svg", urls)

    def test_existing_source_gains_provider_discovery_provenance(self):
        self.start()
        original = self.root / "report.pdf"
        original.write_bytes(b"%PDF-example-source")
        self.assertEqual(self.source(file=original).returncode, 0)
        self.collect("Provider found https://example.org/report.pdf")
        harvested = self.cli(ASSETS, "harvest", self.study)
        self.assertEqual(harvested.returncode, 0, harvested.stderr)
        latest = json.loads((self.study / "source-ledger.jsonl").read_text().splitlines()[-1])
        self.assertEqual(latest["surfaced_by"], ["official"])
        self.assertEqual(latest["status"], "approved")

    def test_claim_cannot_borrow_an_unrelated_approved_url(self):
        self.start()
        self.collect("Two originals")
        original = self.root / "report.pdf"
        original.write_bytes(b"%PDF-example-source")
        self.assertEqual(self.source(file=original).returncode, 0)
        other = self.root / "other.pdf"
        other.write_bytes(b"%PDF-unrelated-source")
        self.assertEqual(self.source(url="https://example.org/other.pdf", file=other).returncode, 0)
        self.assertEqual(self.claim().returncode, 0)
        report = self.study / "report.md"
        report.write_text("The filing proves it [C1]. https://example.org/other.pdf", encoding="utf-8")
        mismatch = self.cli(ASSETS, "check", self.study, "--report", report)
        self.assertEqual(mismatch.returncode, 2)
        self.assertIn("lacks its bound original", mismatch.stderr)
        report.write_text("The filing proves it [C1]. https://example.org/report.pdf", encoding="utf-8")
        self.assertEqual(self.cli(ASSETS, "check", self.study, "--report", report).returncode, 0)

    def test_adjacent_chinese_markdown_links_match_bound_sources(self):
        self.start()
        self.collect("Two originals")
        original = self.root / "report.pdf"
        original.write_bytes(b"%PDF-example-source")
        other = self.root / "other.pdf"
        other.write_bytes(b"%PDF-other-source")
        self.assertEqual(self.source(file=original).returncode, 0)
        self.assertEqual(self.source(url="https://example.org/other.pdf", file=other).returncode, 0)
        sid_a = hashlib.sha256(b"https://example.org/report.pdf").hexdigest()[:20]
        sid_b = hashlib.sha256(b"https://example.org/other.pdf").hexdigest()[:20]
        self.assertEqual(self.cli(ASSETS, "claim", self.study, "--claim-id", "C1",
                                  "--text", "Both reports support the finding", "--status", "supported",
                                  "--source-id", sid_a, "--source-id", sid_b,
                                  "--locator", "page 4", "--boundary", "Two reports only").returncode, 0)
        report = self.study / "report.md"
        report.write_text("Finding [C1] [A](https://example.org/report.pdf)、[B](https://example.org/other.pdf)", encoding="utf-8")
        checked = self.cli(ASSETS, "check", self.study, "--report", report)
        self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_local_original_uses_content_urn_and_relative_report_link(self):
        self.start()
        self.collect("Local user PDF supplied")
        original = self.root / "private.pdf"
        original.write_bytes(b"%PDF-private-source")
        local = self.cli(ASSETS, "source", self.study, "--title", "User supplied report",
                         "--status", "approved", "--source-type", "other",
                         "--accessibility", "exclusive-user-provided", "--family", "local-report",
                         "--locator", "page 1", "--file", original)
        self.assertEqual(local.returncode, 0, local.stderr)
        sid = json.loads(local.stdout)["source_id"]
        row = json.loads((self.study / "source-ledger.jsonl").read_text().splitlines()[-1])
        self.assertEqual(row["url"], "urn:sha256:" + hashlib.sha256(original.read_bytes()).hexdigest())
        self.assertEqual(self.cli(ASSETS, "claim", self.study, "--claim-id", "C1",
                                  "--text", "Local report observation", "--status", "supported",
                                  "--source-id", sid, "--locator", "page 1",
                                  "--boundary", "One report does not establish external prevalence").returncode, 0)
        report = self.study / "report.md"
        report.write_text("Observation [C1] [original](" + row["artifact"]["path"] + ")", encoding="utf-8")
        self.assertEqual(self.cli(ASSETS, "check", self.study, "--report", report).returncode, 0)

    def test_prior_search_combines_entity_and_question_across_study_fields(self):
        spec = json.loads(self.spec.read_text())
        spec["study_id"] = "acme-study"
        self.spec.write_text(json.dumps(spec))
        report = self.finish_valid()
        sid = hashlib.sha256(b"https://example.org/report.pdf").hexdigest()[:20]
        self.assertEqual(self.cli(ASSETS, "claim", self.study, "--claim-id", "C2",
                                  "--text", "Margin improved", "--status", "supported",
                                  "--source-id", sid, "--locator", "page 1",
                                  "--boundary", "Synthetic company only").returncode, 0)
        self.assertEqual(self.cli(ASSETS, "register", self.study, "--catalog", self.catalog,
                                  "--report", report, "--term", "Acme").returncode, 0)
        found = self.cli(ASSETS, "search", "--catalog", self.catalog,
                         "--query", "Acme margin")
        self.assertEqual(found.returncode, 0, found.stderr)
        self.assertEqual(json.loads(found.stdout)[0]["study_id"], "acme-study")

    def test_prior_search_excludes_unverified_leads_unless_requested(self):
        spec = json.loads(self.spec.read_text())
        spec["study_id"] = "acme-study"
        self.spec.write_text(json.dumps(spec))
        report = self.finish_valid()
        self.assertEqual(self.source(url="https://assets.example/favicon", status="candidate").returncode, 0)
        self.assertEqual(self.cli(ASSETS, "register", self.study, "--catalog", self.catalog,
                                  "--report", report, "--term", "Acme").returncode, 0)
        normal = self.cli(ASSETS, "search", "--catalog", self.catalog, "--query", "Acme favicon")
        self.assertEqual(json.loads(normal.stdout), [])
        leads = self.cli(ASSETS, "search", "--catalog", self.catalog,
                         "--query", "Acme favicon", "--include-leads")
        self.assertEqual(json.loads(leads.stdout)[0]["source_matches"][-1]["status"], "candidate")
        approved = self.cli(ASSETS, "search", "--catalog", self.catalog, "--query", "Acme filing")
        self.assertEqual(json.loads(approved.stdout)[0]["study_id"], "acme-study")

    def test_only_registration_changes_append_a_verifiable_event(self):
        self.start()
        self.collect("https://example.org/report.pdf")
        original = self.root / "report.pdf"
        original.write_bytes(b"%PDF-example-source")
        self.assertEqual(self.source(file=original).returncode, 0)
        self.assertEqual(self.claim().returncode, 0)
        report = self.study / "report.md"
        report.write_text("[C1] https://example.org/report.pdf", encoding="utf-8")
        register = ("register", self.study, "--catalog", self.catalog, "--report", report)
        self.assertEqual(self.cli(ASSETS, *register, "--term", "fund").returncode, 0)
        self.assertEqual(self.cli(ASSETS, *register).returncode, 0)
        self.assertEqual(len(self.catalog.read_text().splitlines()), 1)
        self.assertEqual(self.source(url="https://example.org/lead", status="candidate").returncode, 0)
        refreshed = self.cli(ASSETS, *register)
        self.assertEqual(refreshed.returncode, 0, refreshed.stderr)
        self.assertIn("already registered", refreshed.stdout)
        self.assertEqual(len(self.catalog.read_text().splitlines()), 1)
        registered = self.cli(ASSETS, *register, "--term", "alias")
        self.assertEqual(registered.returncode, 0, registered.stderr)
        self.assertIn("revision 2", registered.stdout)
        rows = [json.loads(line) for line in self.catalog.read_text().splitlines()]
        self.assertEqual(len(rows), 2)
        self.assertNotIn("revision", rows[1])
        self.assertEqual(rows[1]["terms"], ["fund", "alias"])
        found = self.cli(ASSETS, "search", "--catalog", self.catalog, "--query", "fund")
        self.assertEqual(len(json.loads(found.stdout)), 1)
        rows[1]["supersedes_sha256"] = "0" * 64
        self.catalog.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
        invalid = self.cli(ASSETS, "search", "--catalog", self.catalog, "--query", "fund")
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("invalid catalog revision", invalid.stderr)

    def test_new_study_catalog_survives_moving_project_tree(self):
        self.start()
        receipt = json.loads((self.study / "prior-research.json").read_text())
        self.assertEqual(receipt["catalog"], "../research-catalog.jsonl")
        self.collect("https://example.org/report.pdf")
        original = self.root / "report.pdf"
        original.write_bytes(b"%PDF-example-source")
        self.assertEqual(self.source(file=original).returncode, 0)
        self.assertEqual(self.claim().returncode, 0)
        report = self.study / "report.md"
        report.write_text("[C1] https://example.org/report.pdf", encoding="utf-8")
        self.assertEqual(self.cli(ASSETS, "register", self.study, "--catalog", self.catalog,
                                  "--report", report).returncode, 0)
        moved = self.root / "moved"
        moved.mkdir()
        shutil.move(str(self.study), moved / "study")
        shutil.move(str(self.catalog), moved / "research-catalog.jsonl")
        moved_study = moved / "study"
        moved_catalog = moved / "research-catalog.jsonl"
        checked = self.cli(ASSETS, "check", moved_study, "--report", moved_study / "report.md")
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertEqual(self.cli(ASSETS, "register", moved_study, "--catalog", moved_catalog,
                                  "--report", moved_study / "report.md").returncode, 0)

    def test_old_absolute_catalog_path_requires_verified_relink(self):
        self.start()
        self.collect("https://example.org/report.pdf")
        original = self.root / "report.pdf"
        original.write_bytes(b"%PDF-example-source")
        self.assertEqual(self.source(file=original).returncode, 0)
        self.assertEqual(self.claim().returncode, 0)
        report = self.study / "report.md"
        report.write_text("[C1] https://example.org/report.pdf", encoding="utf-8")
        self.assertEqual(self.cli(ASSETS, "register", self.study, "--catalog", self.catalog,
                                  "--report", report).returncode, 0)
        prior_path = self.study / "prior-research.json"
        prior = json.loads(prior_path.read_text())
        prior["catalog"] = str(self.root / "retired-checkout" / "research-catalog.jsonl")
        prior_path.write_text(json.dumps(prior))
        self.assertIn("catalog is missing", self.cli(ASSETS, "check", self.study,
                                                   "--report", report).stderr)
        wrong_catalog = self.root / "wrong.jsonl"
        wrong_catalog.write_text(json.dumps({"study_id": "another", "path": "other"}) + "\n")
        rejected = self.cli(ASSETS, "relink-catalog", self.study, "--catalog", wrong_catalog,
                            "--reason", "moved the project checkout")
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("does not preserve the searched catalog snapshot", rejected.stderr)
        unrelated = self.root / "unrelated.jsonl"
        unrelated.write_text(json.dumps({"study_id": "filing-study", "path": "other-study",
                                         "as_of": "2026-01-01",
                                         "business_outcome": "Wrong unrelated study"}) + "\n")
        rejected = self.cli(ASSETS, "relink-catalog", self.study, "--catalog", unrelated,
                            "--reason", "moved the project checkout")
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("different path", rejected.stderr)
        relinked = self.cli(ASSETS, "relink-catalog", self.study, "--catalog", self.catalog,
                            "--reason", "moved the project checkout")
        self.assertEqual(relinked.returncode, 0, relinked.stderr)
        self.assertEqual(self.cli(ASSETS, "check", self.study, "--report", report).returncode, 0)
        self.assertEqual(json.loads(prior_path.read_text())["catalog"], "../research-catalog.jsonl")
        second = self.root / "second-catalog.jsonl"
        shutil.copyfile(self.catalog, second)
        self.assertEqual(self.cli(ASSETS, "relink-catalog", self.study, "--catalog", second,
                                  "--reason", "renamed catalog").returncode, 0)
        history = json.loads(prior_path.read_text())["catalog_relink_history"]
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["from"], str(self.root / "retired-checkout" / "research-catalog.jsonl"))

    def test_unregistered_study_can_relink_to_unchanged_catalog(self):
        self.catalog.write_text(json.dumps({"study_id": "earlier-study", "path": "earlier-study",
                                            "terms": ["unrelated"]}) + "\n")
        self.start()
        prior_path = self.study / "prior-research.json"
        prior = json.loads(prior_path.read_text())
        prior["catalog"] = str(self.root / "retired-checkout" / "research-catalog.jsonl")
        prior_path.write_text(json.dumps(prior))
        relinked = self.cli(ASSETS, "relink-catalog", self.study, "--catalog", self.catalog,
                            "--reason", "moved unfinished study")
        self.assertEqual(relinked.returncode, 0, relinked.stderr)
        self.assertEqual(json.loads(prior_path.read_text())["catalog"], "../research-catalog.jsonl")

    def test_rejected_source_and_prior_match_need_reasons(self):
        self.start()
        no_reason = self.source(status="rejected")
        self.assertEqual(no_reason.returncode, 2)
        self.assertIn("requires a reason", no_reason.stderr)
        original = self.root / "report.pdf"
        original.write_bytes(b"%PDF-example-source")
        self.collect("https://example.org/report.pdf")
        self.assertEqual(self.source(file=original).returncode, 0)
        self.assertEqual(self.claim().returncode, 0)
        report = self.study / "report.md"
        report.write_text("[C1] https://example.org/report.pdf", encoding="utf-8")
        self.assertEqual(self.cli(ASSETS, "check", self.study, "--report", report).returncode, 0)
        self.assertEqual(self.cli(ASSETS, "register", self.study, "--catalog", self.catalog,
                                  "--report", report, "--term", "fund").returncode, 0)
        next_spec = self.root / "next-spec.json"
        spec = json.loads(self.spec.read_text())
        spec["study_id"] = "next"
        next_spec.write_text(json.dumps(spec), encoding="utf-8")
        next_dir = self.root / "next"
        self.assertEqual(self.cli(ASSETS, "start", next_dir, "--spec", next_spec,
                                  "--catalog", self.catalog, "--query", "fund").returncode, 0)
        next_report = next_dir / "report.md"
        next_report.write_text("[C1] https://example.org/report.pdf", encoding="utf-8")
        next_original = self.root / "next.pdf"
        next_original.write_bytes(b"%PDF-next")
        self.assertEqual(self.cli(RUNS, "record", next_dir, "official", "collected",
                                  "--imported", "--origin-task-id", "local-next",
                                  "--file", self._next_provider_file(next_dir)).returncode, 0)
        self.assertEqual(self.cli(ASSETS, "source", next_dir, "--url",
                                  "https://example.org/report.pdf", "--title", "Official filing",
                                  "--status", "approved", "--source-type", "official",
                                  "--accessibility", "public", "--family", "filing-1",
                                  "--locator", "page 4, table 2",
                                  "--file", next_original).returncode, 0)
        self.assertEqual(self.claim(next_dir).returncode, 0)
        undecided = self.cli(ASSETS, "check", next_dir, "--report", next_report)
        self.assertEqual(undecided.returncode, 2)
        self.assertIn("undecided prior study", undecided.stderr)

    def test_legacy_provider_study_is_searchable_without_false_finalization(self):
        self.start()
        self.collect("Provider report with a claim and sources")
        (self.study / "evidence.jsonl").write_text(json.dumps({
            "id": "E01", "claim": "A rival has versioned research notes",
            "source": "https://example.org/rival", "source_type": "vendor_documentation",
            "status": "verified",
        }) + "\n", encoding="utf-8")
        imported = self.cli(ASSETS, "import-legacy", self.study, "--catalog", self.catalog,
                            "--reason", "Selected evidence only; original pages need fresh readback",
                            "--term", "research")
        self.assertEqual(imported.returncode, 0, imported.stderr)
        found = self.cli(ASSETS, "search", "--catalog", self.catalog,
                         "--query", "versioned research")
        self.assertEqual(found.returncode, 0, found.stderr)
        result = json.loads(found.stdout)
        self.assertEqual(result[0]["coverage"], "recorded-only")
        self.assertEqual(result[0]["recorded_lane_coverage"]["coverage"], "legacy_selected_sources")
        self.assertEqual(result[0]["claim_matches"][0]["claim_id"], "E01")
        unrelated = self.cli(ASSETS, "search", "--catalog", self.catalog,
                             "--query", "unrelated research")
        self.assertEqual(json.loads(unrelated.stdout), [])
        incomplete = self.cli(ASSETS, "check", self.study,
                              "--report", self.study / "report.md")
        self.assertEqual(incomplete.returncode, 2)

    @staticmethod
    def _next_provider_file(directory):
        path = directory / "sources" / "official.md"
        path.write_text("https://example.org/report.pdf", encoding="utf-8")
        return path


    def finish_valid(self):
        self.start()
        self.collect("https://example.org/report.pdf")
        original = self.root / "report.pdf"
        original.write_bytes(b"%PDF-example-source")
        self.assertEqual(self.source(file=original).returncode, 0)
        self.assertEqual(self.claim().returncode, 0)
        report = self.study / "report.md"
        report.write_text("[C1] https://example.org/report.pdf", encoding="utf-8")
        return report

    def register_valid(self):
        report = self.finish_valid()
        registered = self.cli(ASSETS, "register", self.study, "--catalog", self.catalog,
                              "--report", report, "--term", "filing")
        self.assertEqual(registered.returncode, 0, registered.stderr)
        return report

    def search(self, query):
        result = self.cli(ASSETS, "search", "--catalog", self.catalog, "--query", query)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_current_source_claim_and_study_changes_need_no_reregistration(self):
        report = self.register_valid()
        before = self.catalog.read_bytes()
        row = json.loads(before)
        for derived in ("source_index", "claim_index", "as_of", "business_outcome",
                        "coverage", "request_mode_coverage", "revision", "deferred_lanes"):
            self.assertNotIn(derived, row)
        source = json.loads((self.study / "source-ledger.jsonl").read_text())
        source["title"] = "only-current-title-after-change"
        with (self.study / "source-ledger.jsonl").open("a") as stream:
            stream.write(json.dumps(source) + "\n")
        self.assertEqual(self.cli(ASSETS, "claim", self.study, "--claim-id", "C2",
                                  "--text", "only-current-claim-after-change", "--status", "supported",
                                  "--source-id", source["source_id"], "--locator", "page 1",
                                  "--boundary", "Synthetic current record").returncode, 0)
        spec = json.loads((self.study / "study.json").read_text())
        spec.update(as_of="2026-10-11", business_outcome="only-current-outcome")
        (self.study / "study.json").write_text(json.dumps(spec))
        for query in (source["title"], "only-current-claim-after-change", "only-current-outcome"):
            match = self.search(query)[0]
            self.assertEqual(match["query_match"], "matched")
            self.assertEqual(match["coverage"], "recorded-only")
            self.assertEqual(match["as_of"], "2026-10-11")
        self.assertEqual(self.search("Official filing"), [])
        self.assertEqual(self.catalog.read_bytes(), before)
        self.assertEqual(self.cli(ASSETS, "register", self.study, "--catalog", self.catalog,
                                  "--report", report).returncode, 0)
        self.assertEqual(self.catalog.read_bytes(), before)

    def test_legacy_copied_indices_and_numbered_chain_are_not_current_truth(self):
        report = self.register_valid()
        row = json.loads(self.catalog.read_text())
        row.pop("registration_kind")
        row.pop("report_path")
        row.pop("bounded_reason")
        row.update(revision=1, as_of="2000-01-01", business_outcome="stale-outcome",
                   coverage="finalized", source_index=[{"title": "stale-only-title"}],
                   claim_index=[{"text": "stale-only-claim"}])
        digest = hashlib.sha256(json.dumps(row, ensure_ascii=False, sort_keys=True,
                                          separators=(",", ":")).encode()).hexdigest()
        second = {**row, "revision": 2, "supersedes_sha256": digest, "terms": ["filing", "alias"]}
        original = "".join(json.dumps(item) + "\n" for item in (row, second))
        self.catalog.write_text(original)
        self.assertEqual(self.search("stale-only-title"), [])
        self.assertEqual(self.search("stale-only-claim"), [])
        self.assertEqual(self.search("Official filing")[0]["source_matches"][0]["title"], "Official filing")
        self.assertEqual(self.catalog.read_text(), original)
        self.assertEqual(self.cli(ASSETS, "register", self.study, "--catalog", self.catalog,
                                  "--report", report).returncode, 0)
        rows = [json.loads(line) for line in self.catalog.read_text().splitlines()]
        self.assertEqual(rows[:2], [row, second])
        self.assertNotIn("revision", rows[2])
        self.assertEqual(self.search("alias")[0]["coverage"], "recorded-only")

    def test_missing_empty_and_invalid_current_metadata_return_gaps(self):
        self.register_valid()
        before = self.catalog.read_bytes()
        cases = [("study.json", None), ("study.json", "[]"),
                 ("source-ledger.jsonl", None), ("source-ledger.jsonl", ""),
                 ("source-ledger.jsonl", "null\n"), ("claims.jsonl", None),
                 ("claims.jsonl", ""), ("claims.jsonl", "{invalid\n"),
                 ("run-events.jsonl", None), ("run-events.jsonl", "null\n")]
        for name, invalid in cases:
            with self.subTest(name=name, invalid=invalid):
                path = self.study / name
                content = path.read_bytes()
                try:
                    if invalid is None:
                        path.unlink()
                    else:
                        path.write_text(invalid)
                    result = self.search("filing")[0]
                    self.assertEqual(result["coverage"], "unknown")
                    self.assertTrue(result["current_gaps"])
                    self.assertEqual(result["artifact_report_integrity"], "not-checked")
                    self.assertEqual(self.catalog.read_bytes(), before)
                finally:
                    path.write_bytes(content)

    def test_typed_current_text_is_a_study_gap_without_hiding_healthy_studies(self):
        self.register_valid()
        healthy = self.root / "healthy"
        shutil.copytree(self.study, healthy)
        spec = json.loads((healthy / "study.json").read_text())
        spec["study_id"] = "healthy-study"
        (healthy / "study.json").write_text(json.dumps(spec))
        row = json.loads(self.catalog.read_text())
        row.update(study_id="healthy-study", path="healthy")
        with self.catalog.open("a") as stream:
            stream.write(json.dumps(row) + "\n")
        before = self.catalog.read_bytes()
        healthy_control = self.search("filing")
        self.assertEqual(len(healthy_control), 2)
        self.assertTrue(all(hit["coverage"] == "recorded-only" for hit in healthy_control))
        for name, field in (("claims.jsonl", "text"),
                            ("source-ledger.jsonl", "title"),
                            ("source-ledger.jsonl", "url")):
            path = self.study / name
            original = path.read_bytes()
            for kind, value in (("typed", 42), ("null", None),
                                ("empty", ""), ("missing", None)):
                with self.subTest(name=name, field=field, kind=kind):
                    item = json.loads(original)
                    if kind == "missing":
                        item.pop(field)
                    else:
                        item[field] = value
                    try:
                        path.write_text(json.dumps(item) + "\n")
                        hits = {hit["study_id"]: hit for hit in self.search("filing")}
                        gap = hits["filing-study"]
                        self.assertEqual(gap["coverage"], "unknown")
                        self.assertTrue(gap["current_gaps"])
                        self.assertEqual(gap["source_matches"], [])
                        self.assertEqual(gap["claim_matches"], [])
                        self.assertNotIn("recorded_lane_coverage", gap)
                        self.assertEqual(hits["healthy-study"]["coverage"], "recorded-only")
                        self.assertEqual(self.catalog.read_bytes(), before)
                    finally:
                        path.write_bytes(original)
        self.assertTrue(all(hit["coverage"] == "recorded-only" for hit in self.search("filing")))

    def test_typed_legacy_text_returns_gap_but_optional_defaults_remain_searchable(self):
        self.start()
        self.collect("Provider report with selected evidence")
        path = self.study / "evidence.jsonl"
        item = {"claim": "Legacy filing observation", "source": "https://example.org/legacy"}
        path.write_text(json.dumps(item) + "\n")
        imported = self.cli(ASSETS, "import-legacy", self.study, "--catalog", self.catalog,
                            "--reason", "Selected evidence only", "--term", "filing")
        self.assertEqual(imported.returncode, 0, imported.stderr)
        before = self.catalog.read_bytes()
        control = self.search("Legacy filing")[0]
        self.assertEqual(control["coverage"], "recorded-only")
        self.assertEqual(control["claim_matches"][0]["claim_id"], "")
        self.assertEqual(self.search("example.org/legacy")[0]["source_matches"][0]["title"], "source")
        for field in ("claim", "source_type", "source"):
            for value in (42, None, ""):
                with self.subTest(field=field, value=value):
                    path.write_text(json.dumps({**item, field: value}) + "\n")
                    gap = self.search("filing")[0]
                    self.assertEqual(gap["coverage"], "unknown")
                    self.assertTrue(gap["current_gaps"])
                    self.assertEqual(gap["source_matches"], [])
                    self.assertEqual(gap["claim_matches"], [])
                    self.assertNotIn("recorded_lane_coverage", gap)
                    self.assertEqual(self.catalog.read_bytes(), before)
        path.write_text(json.dumps({"source": item["source"]}) + "\n")
        source_only = self.search("example.org/legacy")[0]
        self.assertEqual(source_only["coverage"], "recorded-only")
        self.assertEqual(source_only["claim_matches"], [])

    def test_search_does_not_validate_large_artifacts_or_claim_completion(self):
        report = self.register_valid()
        export = self.study / "sources" / "official.md"
        export.write_text("Changed provider artifact; the stored hash no longer matches")
        result = self.search("filing")[0]
        self.assertEqual(result["coverage"], "recorded-only")
        self.assertEqual(result["recorded_lane_coverage"]["coverage"], "finalized")
        self.assertEqual(result["artifact_report_integrity"], "not-checked")
        check = self.cli(ASSETS, "check", self.study, "--report", report)
        self.assertEqual(check.returncode, 2)
        self.assertIn("SHA-256 mismatch", check.stderr)

    def test_catalog_locator_identity_alias_and_no_directory_scan(self):
        report = self.register_valid()
        alias = self.root / "alias-study"
        alias.symlink_to(self.study, target_is_directory=True)
        row = json.loads(self.catalog.read_text())
        row["path"] = alias.name
        self.catalog.write_text(json.dumps(row) + "\n")
        before = self.catalog.read_bytes()
        self.assertEqual(self.search("filing")[0]["coverage"], "recorded-only")
        self.assertEqual(self.cli(ASSETS, "register", alias, "--catalog", self.catalog,
                                  "--report", report).returncode, 0)
        self.assertEqual(self.catalog.read_bytes(), before)
        hidden = self.root / "not-registered"
        hidden.mkdir()
        (hidden / "study.json").write_text('{"study_id":"unlisted-only-token"}')
        self.assertEqual(self.search("unlisted-only-token"), [])
        spec = json.loads((self.study / "study.json").read_text())
        spec["study_id"] = "different-study"
        (self.study / "study.json").write_text(json.dumps(spec))
        found = self.search("filing")[0]
        self.assertEqual(found["coverage"], "unknown")
        self.assertIn("different study identity", found["current_gaps"][0])

    def test_invalid_catalog_is_not_an_empty_search(self):
        for row in ({"study_id": "seed"}, {"study_id": "seed", "path": ""},
                    {"study_id": "seed", "path": "study", "terms": None}, []):
            with self.subTest(row=row):
                self.catalog.write_text(json.dumps(row) + "\n")
                found = self.cli(ASSETS, "search", "--catalog", self.catalog, "--query", "filing")
                self.assertEqual(found.returncode, 2)
                self.assertIn("invalid catalog", found.stderr)

    def test_new_study_rejects_legacy_format_without_modifying_existing_catalog(self):
        spec = json.loads(self.spec.read_text())
        spec["schema_version"] = 1
        self.spec.write_text(json.dumps(spec))
        result = self.cli(ASSETS, "start", self.study, "--spec", self.spec,
                          "--catalog", self.catalog, "--query", "filing")
        self.assertEqual(result.returncode, 2)
        self.assertIn("new studies require", result.stderr)
        self.assertFalse(self.study.exists())
        self.assertFalse(self.catalog.exists())

    def test_old_copied_finalized_entry_missing_details_is_unknown(self):
        original = json.dumps({"study_id": "old-study", "path": "old",
            "business_outcome": "Compare old filing", "coverage": "finalized",
            "source_index": [], "claim_index": []}) + "\n"
        self.catalog.write_text(original)
        result = self.cli(ASSETS, "search", "--catalog", self.catalog, "--query", "filing")
        self.assertEqual(result.returncode, 0, result.stderr)
        found = json.loads(result.stdout)[0]
        self.assertEqual(found["coverage"], "unknown")
        self.assertTrue(found["current_gaps"])
        self.assertEqual(found["artifact_report_integrity"], "not-checked")
        self.assertEqual(self.catalog.read_text(), original)

    def test_missing_required_mode_blocks_start_and_preserves_request_original(self):
        spec = json.loads(self.spec.read_text())
        spec["request_mode_contract"]["modes"].append({"request_id": "R2", "provider": "vendor",
            "mode": "native-research", "lane_ids": ["vendor-deep"]})
        self.spec.write_text(json.dumps(spec))
        original = self.request.read_bytes()
        result = self.cli(ASSETS, "start", self.study, "--spec", self.spec,
                          "--catalog", self.catalog, "--query", "filing")
        self.assertEqual(result.returncode, 2)
        self.assertIn("missing lane", result.stderr)
        self.assertFalse(self.study.exists())
        self.assertEqual(self.request.read_bytes(), original)

    def test_unknown_route_and_legacy_checks_only_register_bounded_coverage(self):
        report = self.finish_valid()
        spec_path = self.study / "study.json"
        spec = json.loads(spec_path.read_text())
        spec["lanes"].append({"lane_id": "vendor", "provider": "vendor", "mode": "native-research",
                              "task_id": "Q1", "prompt": spec["dispatch_context"]})
        spec["request_mode_contract"]["modes"].append({"request_id": "R2", "provider": "vendor",
            "mode": "native-research", "lane_ids": ["vendor"]})
        spec_path.write_text(json.dumps(spec))
        self.assertEqual(self.cli(RUNS, "record", self.study, "vendor", "prepared").returncode, 0)
        self.assertEqual(self.cli(RUNS, "record", self.study, "vendor", "failed_unknown",
                                  "--note", "Task identity cannot be established; no resubmission").returncode, 0)
        blocked = self.cli(ASSETS, "check", self.study, "--report", report)
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("coverage unknown", blocked.stderr)
        self.assertEqual(self.cli(ASSETS, "check", self.study, "--report", report,
                                  "--bounded-reason", " ").returncode, 2)
        checked = self.cli(ASSETS, "check", self.study, "--report", report,
                           "--bounded-reason", "Native lane unavailable; only direct evidence established")
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertEqual(json.loads(checked.stdout)["coverage"], "bounded")
        registered = self.cli(ASSETS, "register", self.study, "--catalog", self.catalog,
                              "--report", report, "--term", "filing", "--bounded-reason", "Missing native result")
        self.assertEqual(registered.returncode, 0, registered.stderr)
        found = json.loads(self.cli(ASSETS, "search", "--catalog", self.catalog, "--query", "filing").stdout)
        self.assertEqual(found[0]["coverage"], "recorded-only")
        self.assertEqual(found[0]["recorded_lane_coverage"]["coverage"], "bounded")
        # Existing schema-1 bytes remain readable and searchable without inventing mode proofs.
        spec["schema_version"] = 1
        spec.pop("request_mode_contract")
        spec_path.write_text(json.dumps(spec))
        self.assertEqual(self.cli(ASSETS, "check", self.study, "--report", report).returncode, 2)
        checked = self.cli(ASSETS, "check", self.study, "--report", report,
                           "--bounded-reason", "Historical mode inventory was not recorded")
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertEqual(json.loads(checked.stdout)["request_mode_coverage"]["status"], "legacy-request-mode-unverified")

    def test_deferred_requested_route_is_reasoned_and_catalogued_with_limit(self):
        report = self.finish_valid()
        path = self.study / "study.json"
        spec = json.loads(path.read_text())
        spec["lanes"].append({"lane_id": "vendor", "provider": "vendor", "mode": "native-research",
                              "task_id": "Q1", "prompt": spec["dispatch_context"]})
        spec["request_mode_contract"]["modes"].append({"request_id": "R2", "provider": "vendor",
            "mode": "native-research", "lane_ids": ["vendor"]})
        path.write_text(json.dumps(spec))
        self.assertEqual(self.cli(RUNS, "record", self.study, "vendor", "prepared").returncode, 0)
        self.assertEqual(self.cli(RUNS, "record", self.study, "vendor", "deferred",
                                  "--note", "Autonomous plugins cannot enforce authorized spend").returncode, 0)
        checked = self.cli(ASSETS, "check", self.study, "--report", report)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertEqual(json.loads(checked.stdout)["coverage"], "finalized-with-deferred-modes")
        self.assertEqual(self.cli(ASSETS, "register", self.study, "--catalog", self.catalog,
                                  "--report", report).returncode, 0)
        row = json.loads(self.catalog.read_text())
        self.assertNotIn("coverage", row)
        found = json.loads(self.cli(ASSETS, "search", "--catalog", self.catalog,
                                   "--query", "filing").stdout)[0]
        self.assertEqual(found["coverage"], "recorded-only")
        self.assertEqual(found["recorded_lane_coverage"]["coverage"], "finalized-with-deferred-modes")


if __name__ == "__main__":
    unittest.main()
