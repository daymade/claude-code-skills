"""Behavior tests against the actual HTTP API and durable state, without audio models."""

import copy
import csv
import http.client
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "server.py"
SPEC = importlib.util.spec_from_file_location("review_workbench_server", MODULE_PATH)
workbench = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workbench)


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.audio = b"ID3" + bytes(range(256)) * 32
        self.audio_path = self.root / "misnamed.ogg"
        self.audio_path.write_bytes(self.audio)
        self.project_path = self.root / "project.json"
        self.input_project = {
            "schema_version": 1,
            "project_id": "meeting-test",
            "title": "现场校勘",
            "subtitle": "同场两个设备",
            "people": [{"id": "participant-a", "name": "Participant A", "color": "#624b22"}],
            "sources": [{"id": "B", "label": "设备 B", "duration": 30, "clock": {"offset": 0, "scale": 1}, "audio_path": str(self.audio_path), "peaks": [0.1, 0.8, 0.2]}],
            "items": [
                {"id": "line-1", "kind": "transcript", "source_id": "B", "start": 1, "end": 5, "text": "原句，尚未校对。", "speaker": "Participant A", "identity_status": "candidate"},
                {"id": "line-2", "kind": "speaker_sample", "source_id": "B", "start": 8, "end": 12, "text": "另一段声音。", "speaker": "声音甲", "identity_status": "unknown"},
            ],
        }
        self.write_project()
        self.state_dir = self.root / "private-state"
        self.project = workbench.Project(self.project_path)
        self.store = workbench.StateStore(self.project, self.state_dir)
        self.static = self.root / "static"
        self.static.mkdir()
        (self.static / "index.html").write_text("<main>声音校勘台</main>", encoding="utf-8")
        (self.static / "app.js").write_text("function loadProject() { return 'ready'; }\n", encoding="utf-8")
        (self.static / "styles.css").write_text("main { color: #234; }\n", encoding="utf-8")
        self.start_server()

    def write_project(self):
        self.project_path.write_text(json.dumps(self.input_project, ensure_ascii=False), encoding="utf-8")

    def start_server(self):
        self.server = workbench.WorkbenchServer(("127.0.0.1", 0), self.project, self.store, self.static)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def restart(self):
        self.stop_server()
        self.project = workbench.Project(self.project_path)
        self.store = workbench.StateStore(self.project, self.state_dir)
        self.start_server()

    def tearDown(self):
        self.stop_server()
        self.temporary.cleanup()

    def request(self, method, path, payload=None, headers=None, raw=None):
        request_headers = dict(headers or {})
        if payload is not None:
            raw = json.dumps(payload, ensure_ascii=False).encode()
            request_headers.setdefault("Content-Type", "application/json")
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            connection.request(method, path, body=raw, headers=request_headers)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def api(self, method, path, payload=None, headers=None):
        status, response_headers, body = self.request(method, path, payload, headers)
        return status, json.loads(body), response_headers

    def decision(self, revision=0, request_id="save-1", item_id="line-1", **changes):
        return self.api("POST", "/api/decision", {"project_fingerprint": self.project.fingerprint, "base_revision": revision, "request_id": request_id, "item_id": item_id, "changes": changes})

    def test_public_project_has_no_paths_and_fingerprint_is_stable(self):
        status, public, _ = self.api("GET", "/api/project")
        self.assertEqual(status, 200)
        self.assertNotIn(str(self.root), json.dumps(public))
        self.assertNotIn("audio_path", public["sources"][0])
        self.assertEqual(public["sources"][0]["media_url"], "/media/B?project_fingerprint=" + public["fingerprint"])
        self.assertEqual(public["sources"][0]["mime"], "audio/mpeg")
        self.assertEqual(public["fingerprint"], workbench.Project(self.project_path).fingerprint)
        self.assertEqual(self.api("GET", "/api/state")[1]["fingerprint"], public["fingerprint"])

    def test_static_assets_match_html_urls_with_root_compatibility(self):
        for path, expected, mime in (
            ("/static/app.js", b"function loadProject()", "javascript"),
            ("/app.js", b"function loadProject()", "javascript"),
            ("/static/styles.css", b"main { color:", "text/css"),
        ):
            status, headers, body = self.request("GET", path)
            self.assertEqual(status, 200, path)
            self.assertIn(expected, body)
            self.assertIn(mime, headers["Content-Type"])
            self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(self.request("GET", "/static/%2e%2e/project.json")[0], 404)

    def test_persistence_restart_and_original_input_untouched(self):
        before = self.project_path.read_bytes()
        status, saved, _ = self.decision(status="confirmed", speaker="participant-a", text="已修正的原话。", note="只确认这一句")
        self.assertEqual(status, 200)
        self.assertEqual(saved["revision"], 1)
        self.assertEqual(saved["decisions"]["line-1"]["speaker"], "Participant A")
        self.restart()
        restored = self.api("GET", "/api/state")[1]
        self.assertEqual(restored, saved)
        self.assertEqual(self.project_path.read_bytes(), before)
        self.assertEqual(self.audio_path.read_bytes(), self.audio)
        audit = json.loads((self.state_dir / "state.json").read_text())["audit"]
        self.assertEqual(audit[0]["after"]["text"], "已修正的原话。")

    def test_presentation_changes_keep_saved_decision_but_evidence_changes_refuse_it(self):
        saved = self.decision(status="confirmed", speaker="Participant A", text="人工修改保留")[1]
        self.input_project["title"] = "换一个更清楚的标题"
        self.input_project["subtitle"] = "展示副标题也可以更新"
        self.input_project["sources"][0].update(label="重新命名的设备", peaks=[0.2, 0.9, 0.3, 0.8, 0.1])
        self.input_project["people"][0]["color"] = "#999999"
        self.input_project["items"][0].update(title="新的片段标题", priority="high")
        self.input_project["items"].reverse()
        self.write_project()
        self.restart()
        self.assertEqual(self.api("GET", "/api/state")[1], saved)
        self.assertEqual(self.api("GET", "/api/project")[1]["title"], "换一个更清楚的标题")
        state_bytes = (self.state_dir / "state.json").read_bytes()
        for change in (
            lambda p: p["items"][0].update(text="原文发生改变"),
            lambda p: p["items"][0].update(start=8.1),
            lambda p: p["sources"][0]["clock"].update(scale=1.001),
        ):
            candidate = copy.deepcopy(self.input_project)
            change(candidate)
            self.project_path.write_text(json.dumps(candidate, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(workbench.StateError, "different project"):
                workbench.StateStore(workbench.Project(self.project_path), self.state_dir)
            self.assertEqual((self.state_dir / "state.json").read_bytes(), state_bytes)
        self.write_project()
        self.audio_path.write_bytes(self.audio + b"different recording")
        with self.assertRaisesRegex(workbench.StateError, "different project"):
            workbench.StateStore(workbench.Project(self.project_path), self.state_dir)

    def test_legacy_fingerprint_migrates_only_after_exact_input_match(self):
        saved = self.decision(status="confirmed", speaker="Participant A")[1]
        state_path = self.state_dir / "state.json"
        legacy_state = json.loads(state_path.read_text())
        legacy_state["fingerprint"] = self.project.legacy_fingerprint
        state_path.write_text(json.dumps(legacy_state, ensure_ascii=False), encoding="utf-8")
        self.restart()
        self.assertEqual(self.api("GET", "/api/state")[1], saved)
        self.assertEqual(json.loads(state_path.read_text())["fingerprint"], self.project.fingerprint)
        legacy_state["fingerprint"] = "unverified-older-recording"
        state_path.write_text(json.dumps(legacy_state, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(workbench.StateError, "different project"):
            workbench.StateStore(self.project, self.state_dir)

    def test_conflict_does_not_lose_first_review(self):
        first = self.decision(status="confirmed", speaker="Participant A")[1]
        status, conflict, _ = self.decision(request_id="other-tab", status="confirmed", speaker="Participant C")
        self.assertEqual(status, 409)
        self.assertEqual(conflict["error"], "revision_conflict")
        self.assertEqual(conflict["state"], first)
        self.assertEqual(self.api("GET", "/api/state")[1], first)

    def test_idempotency_survives_restart_and_later_decisions(self):
        original = self.decision(status="confirmed", speaker="Participant A")[1]
        self.decision(revision=1, request_id="second", item_id="line-2", status="unknown")
        self.restart()
        status, duplicate, _ = self.decision(status="confirmed", speaker="Participant A")
        self.assertEqual(status, 200)
        self.assertEqual(duplicate, original)
        self.assertEqual(self.api("GET", "/api/state")[1]["revision"], 2)
        self.assertEqual(self.decision(status="confirmed", speaker="Participant B")[0], 409)

    def test_undo_is_durable_audited_and_does_not_overwrite_other_item(self):
        first = self.decision(status="confirmed", speaker="Participant A")[1]
        self.decision(revision=1, request_id="second", item_id="line-2", status="confirmed", speaker="新同事")
        status, undone, _ = self.api("POST", "/api/undo", {"project_fingerprint": self.project.fingerprint, "base_revision": 2, "request_id": "undo-1"})
        self.assertEqual(status, 200)
        self.assertEqual(undone["revision"], 3)
        self.assertEqual(undone["decisions"], first["decisions"])
        self.restart()
        self.assertEqual(self.api("GET", "/api/state")[1], undone)
        self.assertEqual(self.api("POST", "/api/undo", {"project_fingerprint": self.project.fingerprint, "base_revision": 2, "request_id": "undo-1"})[1], undone)
        audit = json.loads((self.state_dir / "state.json").read_text())["audit"]
        self.assertEqual(audit[-1]["action"], "undo")
        self.assertEqual(audit[-1]["undoes_revision"], 2)
        self.api("POST", "/api/undo", {"project_fingerprint": self.project.fingerprint, "base_revision": 3, "request_id": "undo-2"})
        self.assertEqual(self.api("GET", "/api/state")[1]["decisions"], {})
        self.assertEqual(self.api("POST", "/api/undo", {"project_fingerprint": self.project.fingerprint, "base_revision": 4, "request_id": "undo-3"})[0], 409)

    def test_exports_contain_real_decisions_and_keep_candidate_distinct(self):
        corrected = '改成："视频有效"，然后\n补一句 <script>。'
        self.decision(status="confirmed", speaker="新同事", text=corrected, note="=请复听")
        self.decision(revision=1, request_id="second", item_id="line-2", status="skipped")
        status, exported, _ = self.api("GET", "/api/export?format=json")
        self.assertEqual(status, 200)
        self.assertEqual(exported["decisions"]["line-1"]["text"], corrected)
        self.assertEqual(exported["items"][0]["speaker"], "新同事")
        self.assertEqual(exported["items"][0]["identity_status"], "human_confirmed")
        self.assertEqual(exported["items"][0]["original_identity_status"], "candidate")
        self.assertEqual(exported["items"][1]["identity_status"], "skipped")
        csv_body = self.request("GET", "/api/export?format=csv")[2].decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(csv_body)))
        self.assertEqual(rows[0]["text"], corrected)
        self.assertEqual(rows[0]["note"], "'=请复听")
        markdown = self.request("GET", "/api/export?format=md")[2].decode()
        self.assertIn("人工确认", markdown)
        self.assertIn("已跳过 · 待核", markdown)
        self.assertIn("\\<script\\>", markdown)
        self.assertNotIn(str(self.root), markdown)

    def test_unknown_clears_final_name_and_note_alone_cannot_confirm_identity(self):
        status, state, _ = self.decision(note="先听一遍")
        self.assertEqual(status, 200)
        self.assertNotIn("status", state["decisions"]["line-1"])
        original = self.api("GET", "/api/export?format=json")[1]["items"][0]
        self.assertEqual(original["identity_status"], "candidate")
        self.decision(revision=1, request_id="confirm", status="confirmed", speaker="Participant A")
        self.decision(revision=2, request_id="unknown", status="unknown")
        exported = self.api("GET", "/api/export?format=json")[1]["items"][0]
        self.assertEqual(exported["speaker"], "")
        self.assertEqual(exported["original_speaker"], "Participant A")

    def test_selected_name_wins_over_another_person_id_through_edits_restart_and_exports(self):
        self.input_project["people"] = [{"id": "person-alice", "name": "Alice"}, {"id": "Alice", "name": "Bob"}]
        self.write_project()
        self.restart()
        status, saved, _ = self.decision(status="confirmed", speaker="Alice")
        self.assertEqual(status, 200)
        self.assertEqual(saved["decisions"]["line-1"]["speaker"], "Alice")
        for revision, changes in ((1, {"note": "Synthetic review note"}), (2, {"text": "Synthetic corrected words"})):
            status, saved, _ = self.decision(revision=revision, request_id=f"edit-{revision}", **changes)
            self.assertEqual(status, 200)
            self.assertEqual(saved["decisions"]["line-1"]["speaker"], "Alice")
        self.restart()
        self.assertEqual(self.api("GET", "/api/state")[1], saved)
        status, exported, _ = self.api("GET", "/api/export?format=json")
        self.assertEqual(status, 200)
        row = exported["items"][0]
        self.assertEqual((row["speaker"], row["speaker_id"], row["identity_status"]), ("Alice", "person-alice", "human_confirmed"))
        self.assertEqual((row["text"], row["note"]), ("Synthetic corrected words", "Synthetic review note"))
        csv_status, _, csv_body = self.request("GET", "/api/export?format=csv")
        self.assertEqual(csv_status, 200)
        csv_row = next(csv.DictReader(io.StringIO(csv_body.decode("utf-8-sig"))))
        self.assertEqual((csv_row["speaker"], csv_row["identity_status"]), ("Alice", "human_confirmed"))
        md_status, _, md_body = self.request("GET", "/api/export?format=md")
        self.assertEqual(md_status, 200)
        self.assertIn("· Alice · 人工确认", md_body.decode())
        self.assertNotIn("· Bob · 人工确认", md_body.decode())

    def test_ordinary_names_legacy_ids_and_nonroster_custom_names_keep_their_identity(self):
        self.input_project["people"] = [{"id": "person-alice", "name": "Alice"}, {"id": "Alice", "name": "Bob"}]
        self.write_project()
        self.restart()
        for revision, (submitted, name, person_id) in enumerate((("Bob", "Bob", "Alice"), ("person-alice", "Alice", "person-alice"), ("Synthetic Guest", "Synthetic Guest", ""))):
            with self.subTest(submitted=submitted):
                status, saved, _ = self.decision(revision=revision, request_id=f"speaker-{revision}", status="confirmed", speaker=submitted)
                self.assertEqual(status, 200)
                self.assertEqual(saved["decisions"]["line-1"]["speaker"], name)
                row = self.api("GET", "/api/export?format=json")[1]["items"][0]
                self.assertEqual((row["speaker"], row["speaker_id"], row["identity_status"]), (name, person_id, "human_confirmed"))

    def test_raw_source_speaker_id_resolves_once_and_original_display_survives_review(self):
        self.input_project["people"] = [{"id": "person-alice", "name": "Alice"}, {"id": "Alice", "name": "Bob"}]
        self.input_project["items"][0]["speaker"] = "Alice"
        self.write_project()
        self.state_dir = self.root / "source-id-state"
        self.restart()
        original = self.api("GET", "/api/export?format=json")[1]["items"][0]
        self.assertEqual((original["speaker"], original["speaker_id"], original["original_speaker"]), ("Bob", "Alice", "Bob"))
        status, saved, _ = self.decision(status="confirmed")
        self.assertEqual(status, 200)
        self.assertEqual(saved["decisions"]["line-1"]["speaker"], "Bob")
        status, _, _ = self.decision(revision=1, request_id="select-alice", status="confirmed", speaker="Alice")
        self.assertEqual(status, 200)
        self.restart()
        reviewed = self.api("GET", "/api/export?format=json")[1]["items"][0]
        self.assertEqual((reviewed["speaker"], reviewed["speaker_id"], reviewed["original_speaker"]), ("Alice", "person-alice", "Bob"))

    def test_ipv4_and_ipv6_loopback_serve_actual_http_requests(self):
        self.assertEqual(self.api("GET", "/api/project")[0], 200)
        server = workbench.WorkbenchServer(("::1", 0), self.project, self.store, self.static)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection("::1", server.server_port, timeout=3)
            try:
                connection.request("GET", "/api/project")
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(json.loads(response.read())["project_id"], self.project.project_id)
            finally:
                connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_independent_stores_share_revision_and_cannot_erase_an_acknowledged_edit(self):
        other = workbench.StateStore(self.project, self.state_dir)
        self.decision(status="confirmed", speaker="Participant A")
        with self.assertRaises(workbench.APIError) as caught:
            other.mutate("decision", {"project_fingerprint": self.project.fingerprint, "item_id": "line-2", "changes": {"status": "unknown"}, "base_revision": 0, "request_id": "other-process"})
        self.assertEqual(caught.exception.status, 409)
        self.assertIn("line-1", other.snapshot()["decisions"])
        self.assertEqual(other.snapshot()["revision"], 1)

    def test_text_and_note_edits_preserve_original_human_identity(self):
        self.input_project["items"][0]["identity_status"] = "human_confirmed"
        self.write_project()
        project = workbench.Project(self.project_path)
        store = workbench.StateStore(project, self.root / "original-confirmed-state")
        result = store.mutate("decision", {"project_fingerprint": project.fingerprint, "item_id": "line-1", "changes": {"note": "Synthetic note", "text": "Synthetic correction"}, "base_revision": 0, "request_id": "note-only"})
        row = workbench.derived_items(project, result)[0]
        self.assertEqual((row["identity_status"], row["speaker"]), ("human_confirmed", "Participant A"))
        self.assertEqual(row["text"], "Synthetic correction")
        self.assertNotIn("status", result["decisions"]["line-1"])

    def test_post_replace_fsync_failure_reconciles_before_the_next_edit(self):
        real_fsync = workbench.os.fsync
        calls = 0
        def fail_directory_sync(fd):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("Synthetic directory sync failure after replacement")
            return real_fsync(fd)
        with patch.object(workbench.os, "fsync", side_effect=fail_directory_sync):
            self.assertEqual(self.decision(status="confirmed", speaker="Participant A")[0], 507)
        observed = self.store.snapshot()
        self.assertEqual(observed["revision"], 1)
        self.assertIn("line-1", observed["decisions"])
        self.assertEqual(self.decision(revision=0, request_id="stale-later", item_id="line-2", status="unknown")[0], 409)
        self.assertEqual(self.decision(revision=1, request_id="valid-later", item_id="line-2", status="unknown")[0], 200)
        self.assertEqual(set(self.store.snapshot()["decisions"]), {"line-1", "line-2"})

    def test_range_suffix_head_and_unsatisfiable(self):
        media_url = self.project.public["sources"][0]["media_url"]
        status, headers, body = self.request("GET", media_url, headers={"Range": "bytes=10-29"})
        self.assertEqual((status, body), (206, self.audio[10:30]))
        self.assertEqual(headers["Content-Range"], f"bytes 10-29/{len(self.audio)}")
        self.assertEqual(headers["Content-Type"], "audio/mpeg")
        self.assertEqual(self.request("GET", media_url, headers={"Range": "bytes=-7"})[2], self.audio[-7:])
        self.assertEqual(self.request("GET", media_url, headers={"Range": "bytes=8190-"})[2], self.audio[8190:])
        status, headers, body = self.request("HEAD", media_url, headers={"Range": "bytes=10-29"})
        self.assertEqual(status, 206)
        self.assertEqual(headers["Content-Length"], "20")
        self.assertEqual(body, b"")
        for value in ("bytes=999999-", "bytes=-0", "bytes=20-10", "bytes=0-1,4-5", "nonsense"):
            status, headers, body = self.request("GET", media_url, headers={"Range": value})
            self.assertEqual(status, 416, value)
            self.assertEqual(headers["Content-Range"], f"bytes */{len(self.audio)}")
            self.assertEqual(body, b"")
        self.assertEqual(self.request("GET", media_url)[2], self.audio)
        self.assertEqual(self.request("GET", "/media/../project.json")[0], 404)

    def test_invalid_input_cross_origin_and_traversal_are_rejected(self):
        for changes in ({"status": "sure"}, {"status": []}, {"status": {}}, {"status": None}, {"status": "confirmed", "speaker": []}, {"status": "confirmed", "speaker": "x" * 81}, {"status": "unknown", "text": None}, {"status": "unknown", "unexpected": True}):
            self.assertEqual(self.decision(**changes)[0], 400)
        self.assertEqual(self.decision(item_id="absent", status="unknown")[0], 400)
        payload = {"project_fingerprint": self.project.fingerprint, "base_revision": 0, "request_id": "cross-site", "item_id": "line-1", "changes": {"status": "unknown"}}
        self.assertEqual(self.api("POST", "/api/decision", payload, {"Origin": "https://example.org"})[0], 403)
        self.assertEqual(self.api("POST", "/api/decision", payload, {"Host": "attacker.example"})[0], 403)
        self.assertEqual(self.api("POST", "/api/decision", payload, {"Sec-Fetch-Site": "cross-site"})[0], 403)
        self.assertEqual(self.request("POST", "/api/decision", raw=b"x" * (workbench.MAX_BODY + 1), headers={"Content-Type": "application/json"})[0], 413)
        self.assertEqual(self.request("GET", "/%2e%2e/project.json")[0], 404)
        self.assertEqual(self.request("GET", "/")[0], 200)
        self.assertEqual(self.request("GET", "/")[1]["Cache-Control"], "no-store")
        self.assertEqual(self.api("GET", "/api/state")[1]["revision"], 0)

    def test_corrupt_or_mismatched_state_fails_without_resetting_it(self):
        self.decision(status="confirmed", speaker="Participant A")
        state_path = self.state_dir / "state.json"
        original = state_path.read_bytes()
        state_path.write_text("{broken", encoding="utf-8")
        with self.assertRaises(workbench.StateError):
            workbench.StateStore(self.project, self.state_dir)
        self.assertEqual(state_path.read_text(), "{broken")
        state_path.write_bytes(original)
        self.input_project["items"][0]["text"] = "来源已变更"
        self.write_project()
        with self.assertRaisesRegex(workbench.StateError, "different project"):
            workbench.StateStore(workbench.Project(self.project_path), self.state_dir)
        self.assertEqual(state_path.read_bytes(), original)
        self.audio_path.write_bytes(self.audio + b"changed")
        self.assertEqual(self.decision(revision=1, request_id="changed", status="unknown")[0], 409)

    def test_failed_save_is_not_reported_as_saved(self):
        with patch.object(self.store, "_persist", side_effect=OSError("disk unavailable")):
            status, response, _ = self.decision(status="confirmed", speaker="Participant A")
        self.assertEqual(status, 507)
        self.assertEqual(response["error"], "save_failed")
        self.assertEqual(self.api("GET", "/api/state")[1]["revision"], 0)
        self.restart()
        self.assertEqual(self.api("GET", "/api/state")[1]["decisions"], {})

    def test_invalid_project_does_not_guess_required_values(self):
        for change in (
            lambda p: p["items"].append(copy.deepcopy(p["items"][0])),
            lambda p: p["sources"][0]["clock"].update(scale=0),
            lambda p: p["items"][0].update(source_id="missing"),
            lambda p: p["items"][0].update(source_id=[]),
            lambda p: p["items"][0].update(identity_status=[]),
            lambda p: p["items"][0].update(end=float("inf")),
            lambda p: p["sources"][0].update(audio_path="relative.wav"),
        ):
            candidate = copy.deepcopy(self.input_project)
            change(candidate)
            self.project_path.write_text(json.dumps(candidate), encoding="utf-8")
            with self.assertRaises(workbench.ProjectError):
                workbench.Project(self.project_path)


if __name__ == "__main__":
    unittest.main()
