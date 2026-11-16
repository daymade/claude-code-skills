"""Actual ordinary Stage-1 CLI and publisher; isolated synthetic native files."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from unittest.mock import patch
from unittest import SkipTest

try:
    import pytest
except ModuleNotFoundError as error:
    if error.name != "pytest":
        raise
    raise SkipTest("Optional history integration tests require pytest and daudio>=0.1.8") from error

try:
    from daudio.client import Daudio
    from daudio.imports import SourceImporter
except ModuleNotFoundError as error:
    if error.name != "daudio":
        raise
    raise SkipTest("Optional history integration tests require daudio>=0.1.8") from error
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from core.correction_repository import CorrectionRepository
from history_projection import flush, three_way


@pytest.fixture
def journey(tmp_path, monkeypatch):
    for key in list(os.environ):
        if key.startswith(("DAUDIO_", "DAYMADE_AUDIO_", "TRANSCRIPT_FIXER_")):
            monkeypatch.delenv(key)
    config_dir = tmp_path / "native"
    config_dir.mkdir()
    guard = tmp_path / "guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text("import socket\ndef denied(*a,**k): raise RuntimeError('Network forbidden including17843')\nsocket.socket.connect=denied\nsocket.create_connection=denied\n")
    for key in ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        monkeypatch.setenv(key, str(tmp_path / key.lower()))
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([str(guard), str(SCRIPTS), *sys.path]))
    monkeypatch.setenv("TRANSCRIPT_FIXER_CONFIG_DIR", str(config_dir))
    native_db = config_dir / "corrections.db"
    monkeypatch.setenv("TRANSCRIPT_FIXER_DB_PATH", str(native_db))
    monkeypatch.setenv("TRANSCRIPT_FIXER_ENABLE_LEARNING", "false")
    monkeypatch.setenv("DAUDIO_ENDPOINT", "http://127.0.0.1:1")
    registry = tmp_path / "registry.sqlite3"
    monkeypatch.setenv("DAUDIO_DB", str(registry))
    daudio_profile, audio_profile = tmp_path / "daudio.json", tmp_path / "audio.json"
    monkeypatch.setenv("DAUDIO_CONFIG", str(daudio_profile))
    monkeypatch.setenv("DAYMADE_AUDIO_CONFIG", str(audio_profile))
    helper = SCRIPTS / "history_projection.py"
    provider = {"operations": ["correct-stage1"], "argv": [sys.executable, str(helper), "recompute", "--options", "{options_json}"],
        "stdout_format": "json", "result_kind": "transcript", "result_text_field": "text"}
    core_config = {"database": {"path": str(registry)}, "device": {"id": "synthetic-device-a"},
        "providers": {"fixer-stage1": provider}}
    daudio_profile.write_text(json.dumps(core_config))
    native = CorrectionRepository(native_db)
    native.add_correction("zzsynthetictpy", "zzcanonicalone", domain="alpha", confidence=.99, added_by="fixture")
    native.close()
    client = Daudio(registry, config=core_config)
    dictionary = SourceImporter(client.registry).import_dictionary(native_db, source_key="synthetic-owned-dictionary", domain=None)
    state = config_dir / "history-projections.json"
    publisher = [sys.executable, "-m", "daudio.cli", "import"]
    profile = {"device": {"id": "synthetic-device-a"},
        "external_dispatch": {"protocol": 1, "argv": [sys.executable, "-m", "daudio.cli", "dispatch-request"]},
        "source_reader": {"protocol": 1, "argv": [sys.executable, "-m", "daudio.cli", "get"]},
        "source_publisher": {"protocol": 1, "argv": [sys.executable, str(helper), "publish", "--state", str(state), "--publisher-json", json.dumps(publisher), "--"]},
        "history_projection": {"protocol": 1, "argv": [sys.executable, str(helper)]},
        "history_projection_provider": "fixer-stage1",
        "evidence_bindings": {"transcript-fixer.dictionary": {"uri": dictionary["uri"], "domain": None, "owner_device_id": "synthetic-device-a"}}}
    audio_profile.write_text(json.dumps(profile))
    source = tmp_path / "controlled-native.md"
    source.write_bytes("zzsynthetictpy。\n人工备注：原文。\n".encode())
    output = tmp_path / "controlled-output.md"
    cli = SCRIPTS / "fix_transcription.py"
    def run(*args):
        result = subprocess.run([sys.executable, str(cli), *args], capture_output=True, timeout=60)
        assert result.returncode == 0, result.stderr.decode() + result.stdout.decode()
        return result
    def ordinary():
        return run("--input", str(source), "--output", str(output), "--stage", "1", "--domain", "alpha", "--apply-domain", "--json")
    def change_rule(value):
        return run("--add", "zzsynthetictpy", value, "--domain", "alpha", "--force")
    return {"root": tmp_path, "client": client, "native_db": native_db, "state": state,
        "source": source, "output": output, "ordinary": ordinary, "change_rule": change_rule,
        "helper": helper, "publisher": publisher, "profile": profile, "audio_profile": audio_profile,
        "run": run, "guard": guard}


def test_actual_cli_dictionary_update_preserves_manual_edit_and_versions(journey):
    j = journey
    before_source = j["source"].read_bytes()
    native_result = j["ordinary"]()
    status = json.loads(native_result.stdout)
    assert status["applied"] == 1
    state = json.loads(j["state"].read_text())
    assert state["pending"] == {}, native_result.stderr.decode()
    assert len(state["receipts"]) == 1
    receipt = next(iter(state["receipts"].values()))
    first = j["client"].get(receipt["baseline_ref"])
    assert first["metadata"]["text"] == "zzcanonicalone。\n人工备注：原文。\n"
    source_ref = j["client"].get(receipt["source_ref"])
    assert source_ref["metadata"]["text"].encode() == before_source
    native_output = "zzcanonicalone。\n人工备注：人工保留。\n".encode()
    j["output"].write_bytes(native_output)
    j["change_rule"]("zzcanonicaltwo")
    refreshed = j["client"].get(first["uri"])
    assert refreshed["version"] == 2, json.loads(j["state"].read_text())
    assert refreshed["metadata"]["text"] == "zzcanonicaltwo。\n人工备注：原文。\n"
    assert j["output"].read_text() == "zzcanonicaltwo。\n人工备注：人工保留。\n"
    assert j["source"].read_bytes() == before_source
    assert j["client"].get(first["version_uri"])["metadata"]["text"] == first["metadata"]["text"]
    state = json.loads(j["state"].read_text())
    receipt = next(iter(state["receipts"].values()))
    assert receipt["status"] == "current" and receipt["baseline_ref"] == refreshed["version_uri"]
    assert j["client"].get(receipt["observed_ref"])["metadata"]["sha256"]


def test_conflict_is_pending_with_complete_manual_and_derived_versions(journey):
    j = journey
    j["ordinary"]()
    original = json.loads(j["state"].read_text())
    receipt = next(iter(original["receipts"].values()))
    manual = "人工选择。\n人工备注：原文。\n".encode()
    j["output"].write_bytes(manual)
    j["change_rule"]("zzcanonicaltwo")
    state = json.loads(j["state"].read_text())
    retained = next(iter(state["receipts"].values()))
    assert retained["status"] == "pending"
    assert j["output"].read_bytes() == manual
    assert j["client"].get(receipt["target_uri"])["version"] == 2
    assert j["client"].get(retained["readback_ref"])["metadata"]["original_bytes_base64"]
    assert retained["baseline_ref"] == receipt["baseline_ref"]


def test_merge_refuses_overlapping_edits_and_retains_nonconflicting_bytes():
    assert three_way(b"old\r\nnotes:old\r\n", b"old\r\nnotes:human\r\n", b"new\r\nnotes:old\r\n") == b"new\r\nnotes:human\r\n"
    with pytest.raises(ValueError, match="conflict"):
        three_way(b"old", b"human", b"new")


def test_without_original_dispatch_baseline_native_success_is_retained_pending(journey):
    j = journey
    profile = dict(j["profile"])
    profile.pop("external_dispatch")
    j["audio_profile"].write_text(json.dumps(profile))
    result = j["ordinary"]()
    assert json.loads(result.stdout)["applied"] == 1
    state = json.loads(j["state"].read_text())
    assert state["receipts"] == {} and len(state["pending"]) == 1
    payload = next(iter(state["pending"].values()))
    assert payload["parent_job_uri"] is None
    from history_projection import decoded
    assert decoded(payload["input_bytes_base64"]) == j["source"].read_bytes()
    assert decoded(payload["output_bytes_base64"]) == j["output"].read_bytes()
    assert j["client"].list(kind="transcript") == []


def test_registry_outage_recovers_at_existing_ordinary_workpoint_without_reprocessing(journey, monkeypatch):
    j = journey
    site = j["guard"] / "sitecustomize.py"
    site.write_text(site.read_text() + "\nimport os\nif os.environ.get('FIXTURE_FAIL_RESULT')=='1':\n from daudio.results import ResultRecorder\n def fail(*a,**k): raise OSError('synthetic registry result outage')\n ResultRecorder.record_result=fail\n")
    monkeypatch.setenv("FIXTURE_FAIL_RESULT", "1")
    result = j["ordinary"]()
    assert json.loads(result.stdout)["applied"] == 1
    output = j["output"].read_bytes()
    state = json.loads(j["state"].read_text())
    assert len(state["pending"]) == 1 and state["receipts"] == {}
    original_jobs = [item for item in j["client"].list(kind="job") if item["metadata"].get("provider") == "transcript.correct"]
    assert len(original_jobs) == 1
    monkeypatch.delenv("FIXTURE_FAIL_RESULT")
    j["run"]("--list", "--domain", "alpha")
    recovered = json.loads(j["state"].read_text())
    assert recovered["pending"] == {} and len(recovered["receipts"]) == 1
    assert j["output"].read_bytes() == output
    assert len([item for item in j["client"].list(kind="job") if item["metadata"].get("provider") == "transcript.correct"]) == 1


def prepared_unprojected_update(j):
    j["ordinary"]()
    profile = dict(j["profile"])
    profile.pop("history_projection")
    profile["source_publisher"] = {"protocol": 1, "argv": j["publisher"]}
    j["audio_profile"].write_text(json.dumps(profile))
    j["change_rule"]("zzcanonicaltwo")
    receipt = next(iter(json.loads(j["state"].read_text())["receipts"].values()))
    assert j["client"].get(receipt["target_uri"])["version"] == 2
    assert "zzcanonicalone" in j["output"].read_text()
    return receipt


def test_projection_oserror_keeps_complete_evidence_and_restart_recovers(journey):
    j = journey
    receipt = prepared_unprojected_update(j)
    native_before = j["output"].read_bytes()
    from history_projection import os as history_os
    original = history_os.link
    def fail_native(source, destination):
        if Path(destination) == j["output"] and Path(source).name.startswith(".stage1-projection-"):
            raise OSError("synthetic native filesystem unavailable")
        return original(source, destination)
    with patch.object(history_os, "link", fail_native):
        flush(j["state"])
    assert j["output"].read_bytes() == native_before
    failed = next(iter(json.loads(j["state"].read_text())["receipts"].values()))
    assert failed["status"] == "pending" and failed["candidate_ref"] and failed["observed_ref"]
    assert failed["baseline_ref"] == receipt["baseline_ref"]
    subprocess.run([sys.executable, str(j["helper"]), "flush", "--state", str(j["state"])], check=True, capture_output=True)
    assert "zzcanonicaltwo" in j["output"].read_text()
    assert next(iter(json.loads(j["state"].read_text())["receipts"].values()))["status"] == "current"


def test_projection_detects_manual_write_between_merge_and_replace(journey):
    j = journey
    receipt = prepared_unprojected_update(j)
    import history_projection
    original = history_projection._replace_projection
    manual = "人工抢先修改。\n".encode()
    def interleaved(client, prepared):
        j["output"].write_bytes(manual)
        return original(client, prepared)
    with patch.object(history_projection, "_replace_projection", interleaved):
        flush(j["state"])
    state = next(iter(json.loads(j["state"].read_text())["receipts"].values()))
    assert state["status"] == "pending" and state["error_type"] == "ValueError"
    assert j["output"].read_bytes() == manual
    assert state["baseline_ref"] == receipt["baseline_ref"]
    assert j["client"].get(state["readback_ref"])["metadata"]["original_bytes_base64"]


def test_projection_readback_mismatch_preserves_external_content(journey):
    j = journey
    prepared_unprojected_update(j)
    from history_projection import os as history_os
    original = history_os.link
    manual = "人工在原子替换后编辑。\n".encode()
    def interleaved(source, destination):
        result = original(source, destination)
        if Path(destination) == j["output"]:
            j["output"].write_bytes(manual)
        return result
    with patch.object(history_os, "link", interleaved):
        flush(j["state"])
    receipt = next(iter(json.loads(j["state"].read_text())["receipts"].values()))
    assert receipt["status"] == "pending" and j["output"].read_bytes() == manual
    from history_projection import decoded
    observed = j["client"].get(receipt["readback_ref"])
    assert decoded(observed["metadata"]["original_bytes_base64"]) == manual


def test_publisher_wrapper_preserves_exit_stdout_and_original_arguments(journey):
    j = journey
    publisher = j["root"] / "synthetic-publisher.py"
    publisher.write_text("import json,sys;print(json.dumps(dict(argv=sys.argv[1:])));raise SystemExit(7)")
    args = ["context", "source with spaces.md", "--domain", "alpha"]
    result = subprocess.run([sys.executable, str(j["helper"]), "publish", "--state", str(j["state"]),
        "--publisher-json", json.dumps([sys.executable, str(publisher)]), "--", *args], capture_output=True)
    assert result.returncode == 7
    assert json.loads(result.stdout) == {"argv": args}
    assert not j["state"].exists()


def test_actual_context_publisher_updates_stage1_demotion_without_llm(journey):
    j = journey
    contexts = j["root"] / "native" / "contexts"
    contexts.mkdir()
    context_path = contexts / "alpha.md"
    context_path.write_text("# Alpha context\n")
    context = SourceImporter(j["client"].registry).import_text(context_path, source_key="synthetic-context", domain="alpha", text_kind="context")
    profile = dict(j["profile"])
    profile["evidence_bindings"] = {**profile["evidence_bindings"],
        "transcript-fixer.contexts": [{"uri": context["uri"], "domain": "alpha"}]}
    j["audio_profile"].write_text(json.dumps(profile))
    j["ordinary"]()
    context_path.write_text("# Alpha context\n- **`zzsynthetictpy` → zzcanonicalone** — 禁裸词\n")
    result = subprocess.run([*profile["source_publisher"]["argv"], "context", str(context_path),
        "--source-key", "synthetic-context", "--domain", "alpha"], capture_output=True)
    assert result.returncode == 0, result.stderr.decode()
    assert json.loads(result.stdout)["version"] == 2
    receipt = next(iter(json.loads(j["state"].read_text())["receipts"].values()))
    updated = j["client"].get(receipt["target_uri"])
    assert updated["version"] == 2
    assert updated["metadata"]["provider_result"]["deferred"] == 1
    assert "zzsynthetictpy" in updated["metadata"]["text"]
    assert "zzsynthetictpy" in j["output"].read_text()


def test_foreign_device_refuses_native_projection_before_file_read(journey, monkeypatch):
    j = journey
    prepared_unprojected_update(j)
    core_path = Path(os.environ["DAUDIO_CONFIG"])
    configuration = json.loads(core_path.read_text())
    configuration["device"]["id"] = "synthetic-foreign-device"
    core_path.write_text(json.dumps(configuration))
    original_read = Path.read_bytes
    reads = []
    def read(path):
        if path == j["output"]:
            reads.append(str(path))
            pytest.fail("foreign native file must not be read")
        return original_read(path)
    monkeypatch.setattr(Path, "read_bytes", read)
    flush(j["state"])
    receipt = next(iter(json.loads(j["state"].read_text())["receipts"].values()))
    assert receipt["status"] == "pending" and reads == []


def test_no_history_binding_retains_standalone_behavior_without_state(journey):
    j = journey
    profile = dict(j["profile"])
    profile.pop("history_projection")
    profile.pop("history_projection_provider")
    profile["source_publisher"] = {"protocol": 1, "argv": j["publisher"]}
    j["audio_profile"].write_text(json.dumps(profile))
    j["ordinary"]()
    assert not j["state"].exists()
    assert "zzcanonicalone" in j["output"].read_text()


def test_prepared_native_write_survives_process_interruption_before_checkpoint(journey):
    j = journey
    prepared_unprojected_update(j)
    import history_projection
    original = history_projection._replace_projection
    def interrupt_after_native_write(client, prepared):
        original(client, prepared)
        raise SystemExit("synthetic process interruption after native write")
    with patch.object(history_projection, "_replace_projection", interrupt_after_native_write):
        with pytest.raises(SystemExit):
            flush(j["state"])
    interrupted = next(iter(json.loads(j["state"].read_text())["receipts"].values()))
    assert interrupted["status"] == "prepared"
    assert "zzcanonicaltwo" in j["output"].read_text()
    before = j["output"].read_bytes()
    subprocess.run([sys.executable, str(j["helper"]), "flush", "--state", str(j["state"])], check=True, capture_output=True)
    recovered = next(iter(json.loads(j["state"].read_text())["receipts"].values()))
    assert recovered["status"] == "current" and recovered["baseline_ref"] == interrupted["projecting_ref"]
    assert j["output"].read_bytes() == before


def test_final_rename_boundary_retains_the_actual_manual_preimage(journey):
    j = journey
    before = prepared_unprojected_update(j)
    import history_projection as history
    original = history.os.rename
    manual = b"manual change at the final rename boundary\n"
    def write_before_rename(source, destination):
        if Path(source) == j["output"]:
            j["output"].write_bytes(manual)
        return original(source, destination)
    with patch.object(history.os, "rename", write_before_rename):
        flush(j["state"])
    receipt = next(iter(json.loads(j["state"].read_text())["receipts"].values()))
    assert receipt["status"] == "pending" and receipt["baseline_ref"] == before["baseline_ref"]
    assert j["output"].read_bytes() == manual
    preimage = j["client"].get(receipt["preimage_ref"])
    assert history.decoded(preimage["metadata"]["original_bytes_base64"]) == manual
    assert Path(receipt["recovery_path"]).read_bytes() == manual


def test_editor_recreated_destination_is_never_overwritten_by_install(journey):
    j = journey
    before = prepared_unprojected_update(j)
    import history_projection as history
    original = history.os.link
    manual = b"atomic editor replacement during the destination gap\n"
    def recreate_before_link(source, destination):
        if Path(destination) == j["output"]:
            j["output"].write_bytes(manual)
        return original(source, destination)
    with patch.object(history.os, "link", recreate_before_link):
        flush(j["state"])
    receipt = next(iter(json.loads(j["state"].read_text())["receipts"].values()))
    assert receipt["status"] == "pending" and receipt["baseline_ref"] == before["baseline_ref"]
    assert j["output"].read_bytes() == manual
    assert receipt["candidate_ref"] and receipt["preimage_ref"]


def test_prepared_foreign_device_never_reads_or_advances_native_baseline(journey, monkeypatch):
    j = journey
    before = prepared_unprojected_update(j)
    import history_projection as history
    client = j["client"]
    state = json.loads(j["state"].read_text())
    receipt = next(iter(state["receipts"].values()))
    prepared = history._project(client, receipt)
    j["output"].write_bytes(prepared[2])
    j["state"].write_text(json.dumps(state))
    config_path = Path(os.environ["DAUDIO_CONFIG"])
    config = json.loads(config_path.read_text())
    config["device"]["id"] = "synthetic-foreign-device"
    config_path.write_text(json.dumps(config))
    original = Path.read_bytes
    reads = []
    def read(path):
        if path == j["output"]:
            reads.append(str(path))
            pytest.fail("prepared foreign receipt opened the native path")
        return original(path)
    monkeypatch.setattr(Path, "read_bytes", read)
    flush(j["state"])
    after = next(iter(json.loads(j["state"].read_text())["receipts"].values()))
    assert reads == [] and after["baseline_ref"] == before["baseline_ref"]
    assert after["status"] == "pending"


def test_rename_before_install_interruption_recovers_the_original_entry(journey):
    j = journey
    prepared_unprojected_update(j)
    import history_projection as history
    original = history.os.link
    def stop_before_install(source, destination):
        if Path(source).name.startswith(".stage1-projection-"):
            raise SystemExit("synthetic process stop after native preimage move")
        return original(source, destination)
    with patch.object(history.os, "link", stop_before_install):
        with pytest.raises(SystemExit):
            flush(j["state"])
    receipt = next(iter(json.loads(j["state"].read_text())["receipts"].values()))
    assert receipt["status"] == "prepared" and not j["output"].exists()
    assert Path(receipt["recovery_path"]).exists()
    subprocess.run([sys.executable, str(j["helper"]), "flush", "--state", str(j["state"])], check=True, capture_output=True)
    after = next(iter(json.loads(j["state"].read_text())["receipts"].values()))
    assert after["status"] == "current" and "recovery_path" not in after
    assert "zzcanonicaltwo" in j["output"].read_text()


def test_derived_version_changed_during_install_stays_pending(journey):
    j = journey
    before = prepared_unprojected_update(j)
    import history_projection as history
    original = history.os.link
    def update_after_install(source, destination):
        result = original(source, destination)
        if Path(destination) == j["output"]:
            target = j["client"].get(before["target_uri"])
            j["client"].registry.revise(target["uri"], metadata={**target["metadata"], "concurrent": True}, expected_version=target["version"])
        return result
    with patch.object(history.os, "link", update_after_install):
        flush(j["state"])
    receipt = next(iter(json.loads(j["state"].read_text())["receipts"].values()))
    assert receipt["status"] == "pending" and receipt["baseline_ref"] == before["baseline_ref"]
    assert receipt["candidate_ref"] and receipt["preimage_ref"]
