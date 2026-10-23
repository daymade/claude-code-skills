"""Cross-project write isolation at the HTTP and direct state boundaries."""

import io
import json
import struct
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
import wave

import test_server


workbench = test_server.workbench


class ProjectBindingTests(unittest.TestCase):
    def setUp(self):
        self.case = test_server.WorkbenchTests()
        self.case.setUp()
        self.addCleanup(self.case.tearDown)

    def payload(self, action, request_id, revision):
        payload = {"project_fingerprint": self.case.project.fingerprint,
                   "base_revision": revision, "request_id": request_id}
        if action == "decision":
            payload.update(item_id="line-1", changes={"text": "Synthetic reviewed words", "speaker": "Participant A", "status": "confirmed"})
        return payload

    def assert_rejected_without_writing(self, action, payload, code, *, direct):
        case = self.case
        before = case.store.path.read_bytes()
        snapshot = case.store.snapshot()
        if direct:
            with self.assertRaises(workbench.APIError) as caught:
                case.store.mutate(action, payload)
            error = caught.exception
            self.assertEqual(error.code, code)
            self.assertEqual(error.status, 409 if code == "project_mismatch" else 400)
            self.assertNotIn("state", error.extra)
        else:
            status, error, _ = case.api("POST", "/api/" + action, payload)
            self.assertEqual(error["error"], code)
            self.assertEqual(status, 409 if code == "project_mismatch" else 400)
            self.assertNotIn("state", error)
        self.assertEqual(case.store.path.read_bytes(), before)
        self.assertEqual(case.store.snapshot(), snapshot)

    def test_unbound_and_wrong_project_writes_never_mutate_state(self):
        self.case.decision(status="confirmed", speaker="Participant A")
        for action in ("decision", "undo"):
            for direct in (False, True):
                for binding in (None, "", "  ", [], False, "different-project"):
                    with self.subTest(action=action, direct=direct, binding=binding):
                        payload = self.payload(action, "unsaved-request", 1)
                        if binding is None:
                            payload.pop("project_fingerprint")
                        else:
                            payload["project_fingerprint"] = binding
                        code = "project_mismatch" if binding == "different-project" else "invalid_project_fingerprint"
                        self.assert_rejected_without_writing(action, payload, code, direct=direct)

    def test_binding_is_checked_before_idempotent_replay_or_revision_validation(self):
        for action, revision in (("decision", 0), ("undo", 1)):
            valid = self.payload(action, action + "-request", revision)
            saved = self.case.store.mutate(action, valid)
            for direct in (False, True):
                for binding in (None, "", "different-project"):
                    for base_revision in (revision, -1):
                        with self.subTest(action=action, direct=direct, binding=binding, revision=base_revision):
                            payload = {**valid, "base_revision": base_revision}
                            if binding is None:
                                payload.pop("project_fingerprint")
                            else:
                                payload["project_fingerprint"] = binding
                            code = "project_mismatch" if binding == "different-project" else "invalid_project_fingerprint"
                            self.assert_rejected_without_writing(action, payload, code, direct=direct)
            self.case.restart()
            self.assertEqual(self.case.store.mutate(action, valid), saved)

    def test_same_origin_new_audio_rejects_old_tab_with_reused_item_and_revision(self):
        case = self.case
        stale_decision = self.payload("decision", "shared-request", 0)
        stale_undo = self.payload("undo", "old-tab-undo", 1)
        port = case.server.server_port
        case.stop_server()
        case.audio_path.write_bytes(case.audio + b"synthetic second recording")
        case.project = workbench.Project(case.project_path)
        case.state_dir = case.root / "second-project-state"
        case.store = workbench.StateStore(case.project, case.state_dir)
        case.server = workbench.WorkbenchServer(("127.0.0.1", port), case.project, case.store, case.static)
        case.thread = threading.Thread(target=case.server.serve_forever, daemon=True)
        case.thread.start()
        self.assertEqual(case.server.server_port, port)
        self.assertNotEqual(stale_decision["project_fingerprint"], case.project.fingerprint)
        self.assert_rejected_without_writing("decision", stale_decision, "project_mismatch", direct=False)
        current = self.payload("decision", "shared-request", 0)
        saved = case.api("POST", "/api/decision", current)[1]
        self.assertEqual(saved["revision"], 1)
        self.assert_rejected_without_writing("decision", stale_decision, "project_mismatch", direct=False)
        self.assert_rejected_without_writing("undo", stale_undo, "project_mismatch", direct=False)
        self.assertEqual(case.api("POST", "/api/decision", current)[1], saved)
        undone = case.api("POST", "/api/undo", self.payload("undo", "current-undo", 1))[1]
        self.assertEqual((undone["revision"], undone["decisions"]), (2, {}))

    def test_media_rejects_unbound_and_stale_same_origin_requests_before_bytes(self):
        case = self.case
        old_url = case.project.public["sources"][0]["media_url"]
        case.audio_path.write_bytes(case.audio + b"synthetic replacement compressed audio")
        case.project = workbench.Project(case.project_path)
        case.server.project = case.project
        new_url = case.project.public["sources"][0]["media_url"]
        self.assertNotEqual(old_url, new_url)
        state_bytes = case.store.path.read_bytes()
        for method, headers in (("GET", {}), ("HEAD", {}), ("GET", {"Range": "bytes=0-9"}), ("HEAD", {"Range": "bytes=0-9"})):
            for url, expected in ((old_url, 409), ("/media/B", 400),
                                  ("/media/B?project_fingerprint=", 400),
                                  ("/media/B?project_fingerprint=other", 409)):
                with self.subTest(method=method, headers=headers, url=url):
                    status, response_headers, body = case.request(method, url, headers=headers)
                    self.assertEqual(status, expected)
                    self.assertNotIn("Content-Range", response_headers)
                    self.assertNotIn(case.audio[:10], body)
                    if method == "GET":
                        self.assertEqual(json.loads(body)["error"], "project_mismatch" if expected == 409 else "invalid_project_fingerprint")
        self.assertEqual(case.request("GET", new_url)[2], case.audio_path.read_bytes())
        status, headers, body = case.request("GET", new_url, headers={"Range": "bytes=1-7"})
        self.assertEqual((status, headers["Content-Type"], body), (206, "audio/mpeg", case.audio[1:8]))
        self.assertEqual(case.request("HEAD", new_url)[1]["Content-Length"], str(case.audio_path.stat().st_size))
        self.assertEqual(case.store.path.read_bytes(), state_bytes)


class EvidenceBindingTests(unittest.TestCase):
    def setUp(self):
        self.case = test_server.WorkbenchTests()
        self.case.setUp()
        self.addCleanup(self.case.tearDown)

    def project_with_hashes(self, hashes):
        self.case.input_project["evidence_hashes"] = hashes
        self.case.write_project()
        return workbench.Project(self.case.project_path)

    def test_absent_evidence_hashes_preserves_exact_v2_and_legacy_fingerprints(self):
        project = self.case.project
        self.assertEqual(project.fingerprint, "fafacb89597b46a255f2c2e8b665e63c4a79d6e525c6d95dbd04823220ffc046")
        self.assertEqual(project.legacy_fingerprint, "45a06903ed5c6101d5d664e2126944108f03500fffd939c6a63915407f31e8f3")
        self.assertNotIn("evidence_hashes", project.public)

    def test_nonempty_hash_map_uses_v3_and_is_order_independent(self):
        hashes = {"provenance_sha256": "1" * 64, "source_binding_sha256": "2" * 64}
        project = self.project_with_hashes(hashes)
        self.assertEqual(project.fingerprint, "c281fa93520b0a80cc2165d5780852579b9371c98a56c17c2204217d17bff62f")
        self.assertEqual(project.public["evidence_hashes"], hashes)
        self.assertEqual(project.evidence_hashes, hashes)
        self.assertNotEqual(project.fingerprint, self.case.project.fingerprint)
        reordered = self.project_with_hashes(dict(reversed(list(hashes.items()))))
        self.assertEqual(reordered.fingerprint, project.fingerprint)
        generic = self.project_with_hashes({"3-generic.evidence_key": "a" * 64})
        self.assertEqual(generic.evidence_hashes, {"3-generic.evidence_key": "a" * 64})

    def test_changed_evidence_rejects_existing_state_and_old_bound_request(self):
        original = self.project_with_hashes({"provenance_sha256": "1" * 64, "source_binding_sha256": "2" * 64})
        directory = self.case.root / "evidence-state"
        store = workbench.StateStore(original, directory)
        payload = {"project_fingerprint": original.fingerprint, "base_revision": 0, "request_id": "bound-review",
                   "item_id": "line-1", "changes": {"text": "Synthetic reviewed words", "speaker": "Participant A", "status": "confirmed"}}
        saved = store.mutate("decision", payload)
        before = store.path.read_bytes()
        changed = self.project_with_hashes({"provenance_sha256": "1" * 64, "source_binding_sha256": "3" * 64})
        self.assertNotEqual(changed.fingerprint, original.fingerprint)
        with self.assertRaisesRegex(workbench.StateError, "different project"):
            workbench.StateStore(changed, directory)
        self.assertEqual(store.path.read_bytes(), before)
        self.assertEqual(workbench.StateStore(original, directory).snapshot(), saved)
        fresh = workbench.StateStore(changed, self.case.root / "changed-evidence-state")
        with self.assertRaises(workbench.APIError) as caught:
            fresh.mutate("decision", payload)
        self.assertEqual(caught.exception.code, "project_mismatch")
        self.assertEqual(fresh.snapshot()["revision"], 0)

    def test_v2_or_legacy_state_cannot_be_upgraded_into_a_new_evidence_binding(self):
        old = self.case.project
        old_state = self.case.store.path.read_bytes()
        bound = self.project_with_hashes({"provenance_sha256": "1" * 64})
        for fingerprint in (old.fingerprint, old.legacy_fingerprint):
            with self.subTest(fingerprint=fingerprint):
                state = json.loads(old_state)
                state["fingerprint"] = fingerprint
                self.case.store.path.write_text(json.dumps(state), encoding="utf-8")
                before = self.case.store.path.read_bytes()
                with self.assertRaisesRegex(workbench.StateError, "different project"):
                    workbench.StateStore(bound, self.case.state_dir)
                self.assertEqual(self.case.store.path.read_bytes(), before)

    def test_empty_missing_value_wrong_type_and_invalid_identifier_are_rejected(self):
        for value in (None, {}, [], "", 0, False, {"": "a" * 64}, {"has space": "a" * 64},
                      {"non-ascii-é": "a" * 64}, {"path/key": "a" * 64}, {"a" * 161: "a" * 64},
                      {"key": None}, {"key": ""}, {"key": "a" * 63}, {"key": "A" * 64},
                      {"key": 0}, {"key": []}, {"good": "a" * 64, "missing": None}):
            with self.subTest(value=value):
                with self.assertRaisesRegex(workbench.ProjectError, "evidence_hashes"):
                    self.project_with_hashes(value)


class BoundedWavTests(unittest.TestCase):
    def setUp(self):
        self.case = test_server.WorkbenchTests()
        self.case.setUp()
        self.addCleanup(self.case.tearDown)
        case = self.case
        case.stop_server()
        self.rate = 1000
        self.samples = b"".join(struct.pack("<h", i) for i in range(20000))
        self.wav_path = case.root / "synthetic.wav"
        with wave.open(str(self.wav_path), "wb") as output:
            output.setparams((1, 2, self.rate, 0, "NONE", "not compressed"))
            output.writeframes(self.samples)
        case.input_project["sources"].extend([
            {"id": sid, "label": sid, "duration": 20, "clock": clock,
             "audio_path": str(self.wav_path), "peaks": []}
            for sid, clock in (("pcm", {"offset": 0, "scale": 1}),
                               ("shifted", {"offset": 3.25, "scale": 1.25}),
                               ("partial", {"offset": 8, "scale": 1}))
        ])
        case.input_project["items"][0].update(source_id="pcm", start=1.0004, end=1.0057)
        case.input_project["items"][1].update(source_id="pcm")
        case.input_project["items"].append({"id": "long", "kind": "transcript", "source_id": "pcm",
                                              "start": 2, "end": 18, "text": "Synthetic long turn", "speaker": "", "identity_status": "unknown"})
        case.write_project()
        case.project = workbench.Project(case.project_path)
        case.state_dir = case.root / "wav-state"
        case.store = workbench.StateStore(case.project, case.state_dir)
        case.start_server()

    def query(self, **overrides):
        values = {"project_fingerprint": self.case.project.fingerprint, "item_id": "line-1",
                  "source_id": "pcm", "context": 0, "reference": 0, **overrides}
        return urlencode({key: value for key, value in values.items() if value is not None})

    def descriptor(self, **overrides):
        status, descriptor, _ = self.case.api("GET", "/api/clip?" + self.query(**overrides))
        self.assertEqual(status, 200, descriptor)
        return descriptor

    def assert_samples(self, descriptor):
        status, headers, body = self.case.request("GET", descriptor["media_url"])
        self.assertEqual((status, headers["Content-Type"]), (200, "audio/wav"))
        with wave.open(io.BytesIO(body)) as audio:
            self.assertEqual(audio.getnframes(), descriptor["end_frame"] - descriptor["start_frame"])
            self.assertEqual(audio.getframerate(), self.rate)
            self.assertEqual(audio.readframes(audio.getnframes()), self.samples[descriptor["start_frame"] * 2:descriptor["end_frame"] * 2])
            self.assertEqual(audio.readframes(1), b"")
        return body

    def test_clip_contains_only_whole_samples_inside_authoritative_item(self):
        descriptor = self.descriptor()
        self.assertEqual((descriptor["start_frame"], descriptor["end_frame"]), (1001, 1005))
        self.assertEqual((descriptor["local_start"], descriptor["local_end"], descriptor["duration"]), (1.001, 1.005, 0.004))
        self.assertTrue(descriptor["coverage_complete"])
        self.assertNotIn(str(self.case.root), json.dumps(descriptor))
        self.assert_samples(descriptor)

    def test_large_clock_offset_snaps_only_infinitesimal_frame_noise(self):
        case = self.case
        self.rate = 16000
        self.samples *= 16
        with wave.open(str(self.wav_path), "wb") as output:
            output.setparams((1, 2, self.rate, 0, "NONE", "not compressed"))
            output.writeframes(self.samples)
        case.input_project["sources"] = [{"id": "pcm", "label": "Synthetic late recording",
            "audio_path": str(self.wav_path), "duration": 20,
            "clock": {"offset": 12345.670000009536, "scale": 1}, "peaks": []}]
        case.input_project["items"] = [case.input_project["items"][0]]
        for name, start, end, expected_frames, complete in (
            ("positive roundoff", 12346.670000009538, 12365.670000009538, (16000, 320000), True),
            ("negative roundoff", 12345.670000009534, 12365.670000009534, (0, 320000), True),
            ("fraction just beyond snap tolerance", 12346.670000009661, 12365.670000009536, (16001, 320000), True),
            ("gap just beyond snap tolerance", 12346.670000009536, 12365.670000009661, (16000, 320000), False),
            ("real inward fractions", 12346.670025009536, 12365.669975009536, (16001, 319999), True),
            ("missing final fractional frame", 12346.670000009536, 12365.670025009536, (16000, 320000), False),
            ("missing final whole frame", 12346.670000009536, 12365.670062509536, (16000, 320000), False),
            ("missing first fractional frame", 12345.669975009536, 12346.670000009536, (0, 16000), False),
            ("missing first whole frame", 12345.669937509536, 12346.670000009536, (0, 16000), False),
        ):
            with self.subTest(name=name):
                case.input_project["items"][0].update(start=start, end=end)
                case.write_project()
                case.project = workbench.Project(case.project_path)
                case.server.project = case.project
                descriptor = self.descriptor()
                self.assertEqual((descriptor["start_frame"], descriptor["end_frame"]), expected_frames)
                self.assertEqual(descriptor["coverage_complete"], complete)
                self.assert_samples(descriptor)

    def test_context_partial_coverage_and_offset_scale_mapping(self):
        shifted = self.descriptor(item_id="line-2", source_id="shifted", context=3)
        self.assertEqual((shifted["local_start"], shifted["local_end"]), (1.4, 9.4))
        self.assertEqual((shifted["canonical_start"], shifted["canonical_end"]), (5, 15))
        self.assertTrue(shifted["coverage_complete"])
        self.assert_samples(shifted)
        partial = self.descriptor(item_id="line-2", source_id="partial", context=3)
        self.assertEqual((partial["canonical_start"], partial["canonical_end"]), (8, 15))
        self.assertFalse(partial["coverage_complete"])
        self.assert_samples(partial)
        status, error, _ = self.case.api("GET", "/api/clip?" + self.query(source_id="shifted"))
        self.assertEqual((status, error["error"]), (416, "clip_unavailable"))
        self.assertEqual(self.case.request("GET", "/api/clip?" + self.query(source_id="shifted", context=3))[0], 416)

    def test_reference_is_capped_and_cannot_borrow_context(self):
        descriptor = self.descriptor(item_id="long", reference=1)
        self.assertEqual((descriptor["canonical_start"], descriptor["canonical_end"], descriptor["duration"]), (2, 10, 8))
        self.assert_samples(descriptor)
        status, error, _ = self.case.api("GET", "/api/clip?" + self.query(item_id="long", reference=1, context=3))
        self.assertEqual((status, error["error"]), (400, "invalid_clip"))

    def test_ranges_and_head_match_the_virtual_wav(self):
        descriptor = self.descriptor()
        body = self.assert_samples(descriptor)
        for value, expected in (("bytes=0-11", body[:12]), ("bytes=42-47", body[42:48]),
                                ("bytes=47-", body[47:]), ("bytes=-3", body[-3:])):
            status, headers, part = self.case.request("GET", descriptor["media_url"], headers={"Range": value})
            self.assertEqual((status, part), (206, expected))
            self.assertEqual(int(headers["Content-Length"]), len(expected))
        status, headers, part = self.case.request("HEAD", descriptor["media_url"], headers={"Range": "bytes=42-47"})
        self.assertEqual((status, headers["Content-Length"], part), (206, "6", b""))
        self.assertEqual(self.case.request("HEAD", descriptor["media_url"])[1]["Content-Length"], str(len(body)))
        for value in ("bytes=999999-", "bytes=-0", "bytes=20-10", "bytes=0-1,4-5", "nonsense"):
            status, headers, part = self.case.request("GET", descriptor["media_url"], headers={"Range": value})
            self.assertEqual((status, part), (416, b""))
            self.assertEqual(headers["Content-Range"], f"bytes */{len(body)}")

    def test_query_binding_source_changes_and_invalid_parameters_fail_closed(self):
        for path in ("/api/clip?", "/clip?"):
            for binding, expected in ((None, "invalid_project_fingerprint"), ("", "invalid_project_fingerprint"), ("other", "project_mismatch")):
                status, error, _ = self.case.api("GET", path + self.query(project_fingerprint=binding))
                self.assertEqual((status, error["error"]), (409 if binding == "other" else 400, expected))
            for params in ({"context": "NaN"}, {"context": -1}, {"context": 4}, {"reference": 2}, {"start": 0}):
                self.assertEqual(self.case.request("GET", path + self.query(**params))[0], 400)
            self.assertEqual(self.case.request("GET", path + self.query() + "&source_id=pcm")[0], 400)
            self.assertEqual(self.case.request("GET", path + self.query(item_id="missing"))[0], 404)
            self.assertEqual(self.case.request("GET", path + self.query(source_id="missing"))[0], 404)
        self.wav_path.write_bytes(self.wav_path.read_bytes() + b"changed")
        for path in ("/api/clip?", "/clip?"):
            status, error, _ = self.case.api("GET", path + self.query())
            self.assertEqual((status, error["error"]), (409, "source_changed"))

    def test_unsupported_source_stays_playable_without_exact_clip_claim(self):
        public = self.case.api("GET", "/api/project")[1]
        sources = {source["id"]: source for source in public["sources"]}
        self.assertEqual((sources["pcm"]["bounded_clip"], sources["pcm"]["sample_rate"]), (True, self.rate))
        self.assertFalse(sources["B"]["bounded_clip"])
        self.assertNotIn("sample_rate", sources["B"])
        for path in ("/api/clip?", "/clip?"):
            status, error, _ = self.case.api("GET", path + self.query(source_id="B"))
            self.assertEqual((status, error["error"]), (415, "unsupported_clip_format"))
        self.assertEqual(self.case.request("GET", sources["B"]["media_url"])[2], self.case.audio)

    def test_partial_pcm_source_exposes_actual_extent_before_playback(self):
        case = self.case
        next(source for source in case.input_project["sources"] if source["id"] == "pcm")["duration"] = 30
        case.input_project["items"][0].update(start=18, end=25)
        case.write_project()
        case.project = workbench.Project(case.project_path)
        case.server.project = case.project
        public = case.api("GET", "/api/project")[1]
        pcm = next(source for source in public["sources"] if source["id"] == "pcm")
        self.assertEqual((pcm["duration"], pcm["available_duration"], pcm["available_frames"]), (30, 20, 20000))
        descriptor = self.descriptor()
        self.assertEqual((descriptor["duration"], descriptor["coverage_complete"]), (2, False))
        self.assert_samples(descriptor)

    def test_capability_metadata_does_not_change_existing_state_fingerprint(self):
        before = self.case.project
        with patch.object(workbench, "_pcm_wav", return_value=None):
            without_capability = workbench.Project(self.case.project_path)
        self.assertEqual(without_capability.fingerprint, before.fingerprint)
        self.assertEqual(without_capability.legacy_fingerprint, before.legacy_fingerprint)
        self.assertEqual(workbench.StateStore(without_capability, self.case.state_dir).snapshot(), self.case.store.snapshot())

    def test_media_reads_only_bounded_chunks_and_requested_sample_bytes(self):
        descriptor = self.descriptor(item_id="long")
        original_open = type(self.wav_path).open
        reads = []

        class BoundedReader:
            def __init__(self, stream):
                self.stream = stream

            def __enter__(self):
                self.stream.__enter__()
                return self

            def __exit__(self, *args):
                return self.stream.__exit__(*args)

            def __getattr__(self, name):
                return getattr(self.stream, name)

            def read(self, count=-1):
                if count < 0 or count > 256 * 1024:
                    raise AssertionError("Clip reads must be bounded")
                result = self.stream.read(count)
                reads.append((count, len(result)))
                return result

        def guarded_open(path, *args, **kwargs):
            stream = original_open(path, *args, **kwargs)
            return BoundedReader(stream) if path == self.wav_path.resolve() else stream

        with patch.object(type(self.wav_path), "open", guarded_open):
            status, _, body = self.case.request("GET", descriptor["media_url"], headers={"Range": "bytes=50-53"})
        self.assertEqual((status, body), (206, self.samples[4006:4010]))
        self.assertEqual(reads, [(4, 4)])

    def test_odd_sized_eight_bit_clip_has_valid_padding_and_range(self):
        case = self.case
        case.stop_server()
        with wave.open(str(self.wav_path), "wb") as output:
            output.setparams((1, 1, 1000, 0, "NONE", "not compressed"))
            output.writeframes(bytes(range(250)) * 80)
        case.input_project["items"][0].update(start=1, end=1.003)
        case.write_project()
        case.project = workbench.Project(case.project_path)
        case.state_dir = case.root / "eight-bit-state"
        case.store = workbench.StateStore(case.project, case.state_dir)
        case.start_server()
        descriptor = self.descriptor()
        status, _, body = case.request("GET", descriptor["media_url"])
        self.assertEqual((status, len(body), body[44:]), (200, 48, b"\0\1\2\0"))
        with wave.open(io.BytesIO(body)) as audio:
            self.assertEqual((audio.getnframes(), audio.readframes(10)), (3, b"\0\1\2"))
        self.assertEqual(case.request("GET", descriptor["media_url"], headers={"Range": "bytes=-1"})[2], b"\0")
        self.assertEqual(case.request("GET", descriptor["media_url"], headers={"Range": "bytes=43-45"})[2], body[43:46])


if __name__ == "__main__":
    unittest.main()
