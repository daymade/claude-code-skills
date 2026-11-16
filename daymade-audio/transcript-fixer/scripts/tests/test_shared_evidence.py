"""Synthetic source-reader/producer cases. No network, inference or user state."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
from core.correction_repository import CorrectionRepository
from core.correction_service import CorrectionService
from shared_evidence import SharedEvidence, EvidenceError


def digest(data):
    return hashlib.sha256(data).hexdigest()


def resource(kind, identifier, metadata, version=1):
    uri = f"daudio://{kind}/{identifier}"
    return {"uri": uri, "version": version, "version_uri": f"{uri}/versions/{version}", "kind": kind,
            "source_key": f"source-import:{kind}:fixture:{identifier}", "metadata": metadata,
            "locations": [], "refs": [], "future_field": {"retained": True}}


def text_resource(identifier, text, text_kind="context", domain="alpha"):
    data = text.encode()
    return resource("context", identifier, {"import_kind": "text", "text_kind": text_kind, "domain": domain,
        "source": {"uri": "fixture://sources/" + identifier, "sha256": digest(data), "size_bytes": len(data), "encoding": "utf-8"},
        "original_bytes_base64": base64.b64encode(data).decode(), "text": text})


def dictionary_resource(path):
    with sqlite3.connect(path) as conn, sqlite3.connect(":memory:") as backup:
        conn.backup(backup)
        image = backup.serialize()
        backup.row_factory = sqlite3.Row
        tables = {"audit_log": {"rows": [dict(r) for r in backup.execute("SELECT * FROM audit_log")]}}
    original = path.read_bytes()
    return resource("dictionary", "fixture-dictionary", {"import_kind": "transcript_fixer_sqlite", "domain": None,
        "source": {"uri": path.resolve().as_uri(), "sha256": digest(original), "size_bytes": len(original)},
        "original_bytes_base64": base64.b64encode(original).decode(),
        "sqlite_snapshot": {"format": "sqlite_backup", "sha256": digest(image), "bytes_base64": base64.b64encode(image).decode(), "tables": tables}})


class SharedEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="shared-evidence-fixture-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = self.root / "native"
        self.config.mkdir()
        # Every child inherits this isolated tree and cannot connect anywhere.
        env = {k: v for k, v in os.environ.items() if not any(word in k.upper() for word in ("TOKEN", "API_KEY", "SECRET"))
               and not k.startswith(("DAUDIO_", "DAYMADE_AUDIO_", "TRANSCRIPT_FIXER_"))}
        env.update(HOME=str(self.root), XDG_CONFIG_HOME=str(self.root / "xdg"), XDG_DATA_HOME=str(self.root / "data"),
                   TRANSCRIPT_FIXER_CONFIG_DIR=str(self.config), DAYMADE_AUDIO_CONFIG=str(self.root / "audio.json"),
                   DAUDIO_CONFIG=str(self.root / "daudio.json"), DAUDIO_DB=str(self.root / "registry.db"),
                   PYTHONPATH=str(self.root / "guard") + os.pathsep + str(SCRIPTS), PYTHONDONTWRITEBYTECODE="1")
        self.env = env
        self.patchenv = patch.dict(os.environ, env, clear=True)
        self.patchenv.start()
        self.addCleanup(self.patchenv.stop)
        guard = self.root / "guard"
        guard.mkdir()
        (guard / "sitecustomize.py").write_text('import socket\ndef denied(*a,**k): raise RuntimeError("Fixture forbids network including canonical17843")\nsocket.socket.connect=denied\nsocket.create_connection=denied\n')
        self.source_db = self.root / "shared.db"
        repo = CorrectionRepository(self.source_db)
        repo.add_correction("示例错字", "共享正字", domain="alpha", added_by="fixture")
        repo.add_correction("第二错字", "共享二字", domain="beta", added_by="fixture")
        with repo._transaction() as conn:
            conn.execute("INSERT INTO context_rules(pattern,replacement,description,priority,domain) VALUES('示例词','共享词','shared fixture',7,'alpha')")
        repo.close()
        self.native_db = self.config / "corrections.db"
        self.native = CorrectionRepository(self.native_db)
        self.addCleanup(self.native.close)
        self.resources = [dictionary_resource(self.source_db), text_resource("roster", "### 甲明\n- **ASR 变体**: 甲铭, 唐老师\n", "people_roster", None),
                          text_resource("alpha-context", "# Alpha context\n- **示例错字 → 共享正字** — 禁裸词\nAlpha-only synthetic context."),
                          text_resource("beta-context", "# Beta context\nBeta-only synthetic context.", domain="beta")]
        self.fixture = self.root / "resources.json"
        self.calls = self.root / "calls.jsonl"
        self.reader = self.root / "reader.py"
        self.reader.write_text('''import json,sys
from pathlib import Path
rows=json.loads(Path(sys.argv[1]).read_text())
with Path(sys.argv[2]).open('a') as f:f.write(json.dumps(sys.argv[3:])+"\\n")
uri=sys.argv[3]
value=next(x for x in rows if x['uri']==uri or x['version_uri']==uri)
print(json.dumps(value))
''')
        self.profile = {"source_reader": {"protocol": 1, "argv": [sys.executable, str(self.reader), str(self.fixture), str(self.calls)]},
                        "evidence_bindings": {"transcript-fixer.dictionary": {"uri": self.resources[0]["uri"], "domain": None},
                            "transcript-fixer.roster": {"uri": self.resources[1]["uri"], "domain": None},
                            "transcript-fixer.contexts": [{"uri": r["uri"], "domain": r["metadata"]["domain"]} for r in self.resources[2:]]}}
        (self.config / "config.json").write_text(json.dumps({"database": {"path": str(self.native_db)},
            "paths": {"config_dir": str(self.config), "intermediate_root": str(self.root / "work")},
            "api": {"api_key": "synthetic-not-a-real-credential"}, "features": {"enable_learning": False}}))
        self.write()

    def write(self):
        self.fixture.write_text(json.dumps(self.resources))
        (self.root / "audio.json").write_text(json.dumps(self.profile))

    def evidence(self):
        value = SharedEvidence(self.profile)
        self.addCleanup(value.close)
        value.preflight()
        return value

    def test_pin_once_bytes_and_native_id_not_reused(self):
        self.native.add_correction("本机错字", "本机正字", domain="alpha", added_by="fixture")
        evidence = self.evidence()
        source_before = self.source_db.read_bytes()
        shared_path = evidence.path(self.profile["evidence_bindings"]["transcript-fixer.dictionary"], "dictionary")
        with evidence._dictionary_repos[self.resources[0]["uri"]]._pool.get_connection() as conn:
            self.assertEqual(conn.execute("PRAGMA query_only").fetchone()[0], 1)
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("DELETE FROM corrections")
        service = CorrectionService(self.native, read_repository=evidence.attach(self.native))
        rows = service.read_repository.get_all_corrections("alpha")
        shared = next(c for c in rows if c.from_text == "示例错字")
        self.assertIsNone(shared.id)
        self.assertEqual(shared.source_native_id, 1)
        self.assertTrue(service.report_false_positive("示例错字", "共享正字", "alpha"))
        self.assertEqual(self.native.get_correction("本机错字", "alpha").to_text, "本机正字")
        self.assertNotIn("示例错字", service.get_corrections("alpha"))
        self.assertEqual(self.source_db.read_bytes(), source_before)
        self.assertFalse(Path(str(shared_path) + "-wal").exists())
        self.assertEqual(len(self.calls.read_text().splitlines()), 4)
        self.assertEqual(service.get_corrections("beta")["第二错字"], "共享二字")

    def test_exact_pair_disable_retarget_and_reenable(self):
        self.native.add_correction("示例错字", "原先目标", "alpha")
        self.native.delete_correction("示例错字", "alpha")
        service = CorrectionService(self.native, read_repository=self.evidence().attach(self.native))
        self.assertEqual(service.get_corrections("alpha")["示例错字"], "共享正字")
        self.assertTrue(service.report_false_positive("示例错字", "共享正字", "alpha"))
        self.assertNotIn("示例错字", service.get_corrections("alpha"))
        self.assertEqual(service.get_disabled_pairs("alpha"), {("示例错字", "原先目标"), ("示例错字", "共享正字")})
        self.native.add_correction("示例错字", "原先目标", "alpha", force=True)
        self.assertEqual(service.get_corrections("alpha")["示例错字"], "原先目标")
        self.assertIn(("示例错字", "共享正字"), service.get_disabled_pairs("alpha"))

    def test_native_context_disabled_and_active_precedence(self):
        with self.native._transaction() as conn:
            conn.execute("INSERT INTO context_rules(pattern,replacement,priority,is_active,domain) VALUES('示例词','本机词',2,0,'alpha')")
        service = CorrectionService(self.native, read_repository=self.evidence().attach(self.native))
        self.assertEqual(service.load_context_rules(["alpha"]), [])
        with self.native._transaction() as conn:
            conn.execute("UPDATE context_rules SET is_active=1")
        self.assertEqual(service.load_context_rules(["alpha"])[0]["replacement"], "本机词")

    def test_roster_original_parser_and_local_precedence(self):
        evidence = self.evidence()
        local = self.root / "people.md"
        local.write_text("### 乙明\n- **ASR 变体**: 甲铭\n")
        values, _ = evidence.people(local)
        self.assertEqual(values["甲铭"], "乙明")
        self.assertNotIn("唐老师", values)
        self.assertIn("乙明", evidence.people(local, names=True))

    def test_bad_missing_empty_foreign_domain_and_sha_fail_closed(self):
        for mutate in (
            lambda p, r: p.update(source_reader=None),
            lambda p, r: p["evidence_bindings"].update({"transcript-fixer.dictionary": None}),
            lambda p, r: p["evidence_bindings"]["transcript-fixer.dictionary"].pop("domain"),
            lambda p, r: r[0].update(uri="daudio://dictionary/foreign"),
            lambda p, r: r[0].update(version_uri="daudio://dictionary/foreign/versions/1"),
            lambda p, r: r[0]["metadata"].update(import_kind="aliases"),
            lambda p, r: r[0]["metadata"]["source"].pop("uri"),
            lambda p, r: r[0]["metadata"]["source"].update(uri=""),
            lambda p, r: r[0]["metadata"]["source"].update(sha256="0" * 64),
            lambda p, r: r[0]["metadata"]["sqlite_snapshot"].update(sha256="0" * 64),
            lambda p, r: r[2]["metadata"].update(domain="foreign"),
            lambda p, r: r[2]["metadata"].update(text="drift"),
            lambda p, r: p["evidence_bindings"]["transcript-fixer.contexts"].append({"uri": r[3]["uri"], "domain": "alpha"}),
        ):
            with self.subTest(mutate=mutate):
                oldp, oldr = self.profile, self.resources
                self.profile, self.resources = copy.deepcopy(oldp), copy.deepcopy(oldr)
                mutate(self.profile, self.resources)
                self.write()
                evidence = None
                try:
                    with self.assertRaises((EvidenceError, StopIteration)):
                        evidence = SharedEvidence(self.profile)
                        evidence.preflight()
                finally:
                    if evidence: evidence.close()
                    self.profile, self.resources = oldp, oldr
        self.write()

    def test_stable_is_pinned_once_and_explicit_old_version_does_not_drift(self):
        evidence = self.evidence()
        binding = self.profile["evidence_bindings"]["transcript-fixer.dictionary"]
        self.resources[0]["version"] = 2
        self.resources[0]["version_uri"] = self.resources[0]["uri"] + "/versions/2"
        self.write()
        self.assertEqual(evidence.resource(binding, "dictionary")["version"], 1)
        self.assertEqual(self.evidence().resource(binding, "dictionary")["version"], 2)
        binding["uri"] += "/versions/1"
        self.write()
        bad = SharedEvidence(self.profile)
        self.addCleanup(bad.close)
        with self.assertRaises(EvidenceError):
            bad.preflight()

    def test_publication_failure_retains_native_and_replay_captures_audit_cursor(self):
        self.resources[0] = dictionary_resource(self.native_db)
        # Redundant JSON table declarations are not the SQLite source of truth.
        self.resources[0]["metadata"]["sqlite_snapshot"]["tables"]["audit_log"]["rows"] = [{"id": 99999}]
        publisher = self.root / "publisher.py"
        fail = self.root / "fail-publish"
        fail.touch()
        publisher_calls = self.root / "publisher-calls.jsonl"
        publisher.write_text("""import json,runpy,sys
from pathlib import Path
with Path(sys.argv[2]).open('a') as f:f.write(json.dumps(sys.argv[3:])+"\\n")
if Path(sys.argv[1]).exists():raise SystemExit(3)
helpers=runpy.run_path(sys.argv[3])
value=helpers['dictionary_resource'](Path(sys.argv[5]))
value['version']=2
value['version_uri']=value['uri']+'/versions/2'
value['metadata']['sqlite_snapshot']['tables']['audit_log']['rows'].append({'id':99999})
print(json.dumps(value))
""")
        self.profile["source_publisher"] = {"protocol": 1, "argv": [sys.executable, str(publisher), str(fail), str(publisher_calls), str(Path(__file__).resolve())]}
        self.profile["device"] = {"id": "synthetic-device-A"}
        self.profile["evidence_bindings"]["transcript-fixer.dictionary"]["owner_device_id"] = "synthetic-device-A"
        self.write()
        evidence = self.evidence()
        service = CorrectionService(self.native, read_repository=evidence.attach(self.native))
        service.add_correction("新增错字", "新增正字", "alpha")
        evidence.publish(self.config)
        statefile = self.config / "shared-publications.json"
        state = json.loads(statefile.read_text())
        self.assertEqual(len(state["pending"]), 1)
        self.assertEqual(service.get_corrections("alpha")["新增错字"], "新增正字")
        fail.unlink()
        good_profile = copy.deepcopy(self.profile)
        # The publisher is now available: each wrong/unknown identity must still
        # retain A's pending work and make zero additional import calls.
        for device, owner in (("missing", "synthetic-device-A"), (None, "synthetic-device-A"), ({}, "synthetic-device-A"),
                              ({"id": None}, "synthetic-device-A"), ({"id": ""}, "synthetic-device-A"),
                              ({"id": "synthetic-device-B"}, "synthetic-device-A"),
                              ({"id": "synthetic-device-A"}, "missing"),
                              ({"id": "synthetic-device-A"}, None), ({"id": "synthetic-device-A"}, ""),
                              ({"id": "synthetic-device-B"}, "synthetic-device-B")):
            with self.subTest(device=device, owner=owner):
                self.profile = copy.deepcopy(good_profile)
                if device == "missing":
                    self.profile.pop("device")
                else:
                    self.profile["device"] = device
                binding = self.profile["evidence_bindings"]["transcript-fixer.dictionary"]
                if owner == "missing":
                    binding.pop("owner_device_id")
                else:
                    binding["owner_device_id"] = owner
                self.write()
                foreign = self.evidence()
                foreign.attach(self.native)
                foreign.publish(self.config)
                held = json.loads(statefile.read_text())
                pending = held["pending"][str(self.native_db.resolve())]
                self.assertEqual(pending["device_id"], "synthetic-device-A")
                self.assertEqual(pending["owner_device_id"], "synthetic-device-A")
                self.assertEqual(len(publisher_calls.read_text().splitlines()), 1)
        self.profile = good_profile
        self.write()
        service.add_correction("再次错字", "再次正字", "alpha")
        replay = self.evidence()
        replay.attach(self.native)
        replay.publish(self.config)
        state = json.loads(statefile.read_text())
        self.assertEqual(state["pending"], {})
        receipt = state["receipts"][str(self.native_db.resolve())]
        self.assertEqual(receipt["captured_through_audit_cursor"], 2)
        self.assertEqual(receipt["device_id"], "synthetic-device-A")
        self.assertEqual(receipt["version_uri"], self.resources[0]["uri"] + "/versions/2")
        self.assertNotIn("新增正字", statefile.read_text())
        self.assertEqual(len(publisher_calls.read_text().splitlines()), 2)

    def test_unknown_pending_identity_cannot_be_assigned_after_profile_repair(self):
        import shared_evidence
        self.resources[0] = dictionary_resource(self.native_db)
        self.profile["source_publisher"] = {"protocol": 1, "argv": ["synthetic-publisher"]}
        self.write()
        evidence = self.evidence()
        evidence.attach(self.native)
        self.native.add_correction("synthetic_unknown_from", "synthetic_unknown_to", "alpha")
        original_invoke = shared_evidence._invoke
        calls = []

        def publisher(argv):
            if argv[0] == "synthetic-publisher":
                calls.append(argv)
                value = dictionary_resource(self.native_db)
                value.update(version=2, version_uri=value["uri"] + "/versions/2")
                return value
            return original_invoke(argv)

        with patch.object(shared_evidence, "_invoke", publisher):
            evidence.publish(self.config)
        state_path = self.config / "shared-publications.json"
        before = json.loads(state_path.read_text())
        self.assertEqual(len(before["pending"]), 1)
        self.assertFalse(calls)
        self.profile["device"] = {"id": "synthetic-device-B"}
        self.profile["evidence_bindings"]["transcript-fixer.dictionary"]["owner_device_id"] = "synthetic-device-B"
        self.write()
        repaired = self.evidence()
        repaired.attach(self.native)
        with patch.object(shared_evidence, "_invoke", publisher):
            repaired.publish(self.config)
        self.assertEqual(json.loads(state_path.read_text()), before)
        self.assertFalse(calls)
        # Old records without the keys are a distinct negative from JSON null.
        for pending in before["pending"].values():
            pending.pop("device_id")
            pending.pop("owner_device_id")
        state_path.write_text(json.dumps(before))
        with patch.object(shared_evidence, "_invoke", publisher):
            repaired.publish(self.config)
        self.assertEqual(json.loads(state_path.read_text()), before)
        self.assertFalse(calls)

    def cli(self, args, *, fake_ai=False):
        entry = SCRIPTS / "fix_transcription.py"
        if fake_ai:
            bootstrap = self.root / "fake_ai_entry.py"
            bootstrap.write_text('''import json,os,runpy,sys
from pathlib import Path
import core
class FakeAI:
 failed_chunks=0
 total_chunks=1
 models_used={'synthetic-offline'}
 model='synthetic-offline'
 def __init__(self,*a,**kw):pass
 def process(self,text,context=''):
  Path(os.environ['FIXTURE_CONTEXT']).write_text(context)
  return text,[]
core.AIProcessor=FakeAI
runpy.run_path(sys.argv.pop(1),run_name='__main__')
''')
            command = [sys.executable, str(bootstrap), str(entry)]
        else:
            command = [sys.executable, str(entry)]
        return subprocess.run([*command, *args], env={**self.env, "FIXTURE_CONTEXT": str(self.root / "received-context.txt")},
                              capture_output=True, text=True, timeout=30)

    def test_actual_cli_stage1_shared_roster_and_trap_veto(self):
        source = self.root / "input.md"
        source.write_text("示例错字，甲铭。\n")
        output = self.root / "corrected.md"
        result = self.cli(["--input", str(source), "--output", str(output), "--stage", "1", "--domain", "alpha", "--apply-domain", "--json"])
        self.assertEqual(result.returncode, 0, result.stderr)
        refs = json.loads(result.stdout)["evidence_sources"]
        self.assertEqual([r["domain"] for r in refs if r["role"] == "transcript-fixer.contexts"], ["alpha"])
        self.assertIn("示例错字", output.read_text())  # Context veto wins trusted domain.
        self.assertIn("甲铭", output.read_text())  # Roster keeps its original risk policy.
        self.assertIn("甲明", (self.root / "input_needs_review.md").read_text())
        self.assertEqual(source.read_text(), "示例错字，甲铭。\n")
        self.assertEqual(len(self.calls.read_text().splitlines()), 4)

    def test_actual_cli_stage2_receives_only_selected_pinned_domain_context(self):
        source = self.root / "input.md"
        source.write_text("这是合成测试句。\n")
        result = self.cli(["--input", str(source), "--output", str(self.root / "out"), "--stage", "2", "--domain", "alpha"], fake_ai=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        context = (self.root / "received-context.txt").read_text()
        self.assertIn("Alpha-only synthetic context", context)
        self.assertIn("/versions/1", context)
        self.assertNotIn("Beta-only", context)
        with sqlite3.connect(self.native_db) as conn:
            details = json.loads(conn.execute("SELECT details FROM audit_log WHERE action='shared_evidence_read'").fetchone()[0])
        self.assertEqual(details["domain"], "alpha")
        self.assertTrue(all("/versions/1" in r["source_ref"] for r in details["source_refs"]))

    def test_no_bindings_do_not_invoke_reader_or_change_native_rules(self):
        self.profile = {"source_reader": None, "evidence_bindings": {"other.skill": {"future": True}}}
        self.write()
        evidence = self.evidence()
        self.assertIs(evidence.attach(self.native), self.native)
        self.assertIsNone(evidence.stage2_context(["alpha"], self.config))
        self.assertFalse(self.calls.exists())

    def test_actual_cli_bad_binding_refuses_before_native_db_creation(self):
        self.native.close()
        self.native_db.unlink()
        self.resources[0]["metadata"]["source"]["sha256"] = "0" * 64
        self.write()
        result = self.cli(["--list"])
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.native_db.exists())
        self.profile = {}
        self.write()
        control = self.cli(["--list"])
        self.assertEqual(control.returncode, 0, control.stderr)
        self.assertTrue(self.native_db.exists())


if __name__ == "__main__":
    unittest.main()
