"""Real ffmpeg windows, cache reuse, source changes and transfer refusals."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import wave

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from source_clip import SourceClips, prepare


@pytest.fixture
def source(tmp_path):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg and ffprobe required")
    p = tmp_path / "source with 空格.wav"
    frames = b"".join(struct.pack("<h", (i % 2000)-1000) for i in range(16000*5))
    with wave.open(str(p), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(frames)
    spec = prepare({"kind": "local", "path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
    s = tmp_path / "source.json"
    s.write_text(json.dumps(spec))
    return p, s, frames


def test_clip_is_exact_source_window_and_cache_reuses_it(source, tmp_path):
    p, s, frames = source
    clips = SourceClips(s, tmp_path / "cache")
    out = tmp_path / "out.wav"
    first = clips.fetch(1.25, 2.75, out)
    with wave.open(str(out), "rb") as wav:
        assert wav.getnframes() == 24000
        assert wav.readframes(24000) == frames[20000*2:44000*2]
    second = clips.fetch(1.25, 2.75, tmp_path / "other.wav")
    assert first["cache_reused"] is False
    assert second["cache_reused"] is True
    assert first["clip_sha256"] == second["clip_sha256"]
    assert second["source_sha256"] == hashlib.sha256(p.read_bytes()).hexdigest()


def test_source_change_refuses_cached_clip(source, tmp_path):
    p, s, _ = source
    clips = SourceClips(s, tmp_path / "cache")
    clips.fetch(1, 2, tmp_path / "first.wav")
    p.write_bytes(p.read_bytes()+b"changed")
    out = tmp_path / "must-not-exist.wav"
    with pytest.raises(ValueError, match="source version changed"):
        clips.fetch(1, 2, out)
    assert not out.exists()


@pytest.mark.parametrize("start,end", [(-1, 1), (1, 1), (2, 1), (0, 6), (float("nan"), 1)])
def test_invalid_window_is_refused(source, tmp_path, start, end):
    with pytest.raises(ValueError, match="invalid source-clock"):
        SourceClips(source[1], tmp_path / "cache").fetch(start, end, tmp_path / "bad.wav")


def test_wrong_source_hash_does_not_prepare(source):
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        prepare({"kind": "local", "path": str(source[0]), "sha256": "0"*64})


def test_damaged_cache_is_reacquired(source, tmp_path):
    clips = SourceClips(source[1], tmp_path / "cache")
    first = clips.fetch(1, 2, tmp_path / "one.wav")
    next((tmp_path / "cache").glob("*.wav")).write_bytes(b"truncated")
    second = clips.fetch(1, 2, tmp_path / "two.wav")
    assert second["cache_reused"] is False
    assert second["clip_sha256"] == first["clip_sha256"]


def test_transferred_truncation_is_refused(source, tmp_path, monkeypatch):
    import source_clip
    original = source_clip.run_worker
    def broken(spec, request):
        data = original(spec, request)
        return data[:-1] if request["action"] == "extract" else data
    monkeypatch.setattr(source_clip, "run_worker", broken)
    out = tmp_path / "bad.wav"
    with pytest.raises(ValueError, match="transfer/duration"):
        SourceClips(source[1], tmp_path / "cache").fetch(1, 2, out)
    assert not out.exists()


def test_entry_runs_through_symlink_with_spaces(source, tmp_path):
    link = tmp_path / "entry with spaces.py"
    link.symlink_to(Path(__file__).resolve().parents[1] / "source_clip.py")
    cp = subprocess.run([sys.executable, str(link), "fetch", "--source-spec", str(source[1]),
                         "--cache-dir", str(tmp_path / "cache"), "--start", "1", "--end", "2",
                         "--output", str(tmp_path / "out.wav")], capture_output=True, text=True)
    assert cp.returncode == 0, cp.stderr
    assert json.loads(cp.stdout)["duration"] == 1


@pytest.mark.parametrize("which", ["source", "spec", "unrelated"])
def test_fetch_never_replaces_source_spec_or_unknown_output(source, tmp_path, which):
    p, spec, _ = source
    target = {"source": p, "spec": spec, "unrelated": tmp_path/"unrelated.bin"}[which]
    if which == "unrelated":
        target.write_bytes(b"unrelated work")
    before = target.read_bytes()
    with pytest.raises(ValueError, match="conflicts|existing output"):
        SourceClips(spec, tmp_path/"cache").fetch(1, 2, target)
    assert target.read_bytes() == before


def test_prepare_cli_exclusively_publishes_and_keeps_source(source, tmp_path):
    p, _, _ = source
    before = p.read_bytes()
    cp = subprocess.run([sys.executable, str(Path(__file__).parents[1]/"source_clip.py"),
                         "prepare", "--path", str(p), "--sha256", hashlib.sha256(before).hexdigest(),
                         "--output", str(p)], capture_output=True, text=True)
    assert cp.returncode == 2
    assert p.read_bytes() == before


def test_existing_output_can_only_reuse_its_own_unchanged_window(source, tmp_path):
    clips = SourceClips(source[1], tmp_path/"cache")
    out = tmp_path/"window.wav"
    first = clips.fetch(1, 2, out)
    assert clips.fetch(1, 2, out)["clip_sha256"] == first["clip_sha256"]
    with pytest.raises(ValueError, match="existing output"):
        clips.fetch(1, 3, out)
    assert hashlib.sha256(out.read_bytes()).hexdigest() == first["clip_sha256"]


def test_null_cache_metadata_is_reacquired(source, tmp_path):
    clips = SourceClips(source[1], tmp_path/"cache")
    first = clips.fetch(1, 2, tmp_path/"first.wav")
    next((tmp_path/"cache").glob("*.json")).write_text("null")
    second = clips.fetch(1, 2, tmp_path/"second.wav")
    assert second["cache_reused"] is False
    assert second["clip_sha256"] == first["clip_sha256"]
