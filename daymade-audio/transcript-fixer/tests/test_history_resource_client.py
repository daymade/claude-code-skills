"""The application's default resource client is thin, with no registry fallback."""
import builtins
import json
import sys
from pathlib import Path
from unittest import SkipTest

try:
    import pytest
    import daudio_client
except ModuleNotFoundError as error:
    if error.name not in {"pytest", "daudio_client"}:
        raise
    raise SkipTest("Optional resource-client tests require pytest and daudio-client") from error
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from history_projection import _resource_client


@pytest.fixture
def profile(tmp_path, monkeypatch):
    for key in list(__import__("os").environ):
        if key.startswith(("DAUDIO_", "DAYMADE_AUDIO_")):
            monkeypatch.delenv(key)
    audio = tmp_path / "audio.json"
    config = tmp_path / "daudio.json"
    database = tmp_path / "must-not-be-opened.sqlite3"
    audio.write_text("{}")
    config.write_text(json.dumps({"device": {"id": "synthetic-device"},
                                  "database": {"path": str(database)},
                                  "api": {"endpoint": "http://127.0.0.1:1"}}))
    monkeypatch.setenv("DAYMADE_AUDIO_CONFIG", str(audio))
    monkeypatch.setenv("DAUDIO_CONFIG", str(config))
    return audio, config, database


def test_default_constructs_independent_thin_client_without_local_engine_import(profile, monkeypatch):
    from daudio_client import DaudioClient
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name == "daudio" or name.startswith("daudio."):
            raise AssertionError("Default application client cannot import the local runtime")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    client = _resource_client()
    assert isinstance(client, DaudioClient)
    assert client.device_id == "synthetic-device"
    assert not profile[2].exists()


@pytest.mark.parametrize("endpoint", [None, ""])
def test_missing_or_empty_endpoint_fails_without_registry_fallback(profile, monkeypatch, endpoint):
    audio, config, database = profile
    value = json.loads(config.read_text())
    if endpoint is None:
        value.pop("api")
    else:
        value["api"]["endpoint"] = endpoint
    config.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        _resource_client()
    assert not database.exists()


def test_missing_thin_sdk_does_not_import_the_available_local_runtime(profile, monkeypatch):
    original = builtins.__import__
    def missing(name, *args, **kwargs):
        if name == "daudio_client":
            raise ModuleNotFoundError("missing synthetic thin dependency", name="daudio_client")
        if name == "daudio" or name.startswith("daudio."):
            raise AssertionError("Missing thin SDK must not select a local engine")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", missing)
    with pytest.raises(ModuleNotFoundError):
        _resource_client()
    assert not profile[2].exists()


@pytest.mark.parametrize("mode", [None, "", "local", "server"])
def test_unknown_mode_never_selects_local_storage(profile, mode):
    profile[0].write_text(json.dumps({"history_resource_mode": mode}))
    with pytest.raises(ValueError):
        _resource_client()
    assert not profile[2].exists()


def test_explicit_local_worker_retains_offline_resource_behavior(profile):
    pytest.importorskip("daudio")
    profile[0].write_text(json.dumps({"history_resource_mode": "local-worker"}))
    client = _resource_client()
    try:
        assert client.device_id == "synthetic-device"
        original = client.register("transcript", metadata={"text": "synthetic original"})
        assert client.get(original["version_uri"]) == original
        assert profile[2].exists()
    finally:
        client.registry.close()
