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


def test_cache_metadata_cannot_replace_source_spec(source, tmp_path):
    from source_clip import CLIP_SCHEMA
    spec = json.loads(source[1].read_text())
    identity = {"schema": CLIP_SCHEMA, "source": {k: v for k, v in spec.items() if k != "verified_at"},
                "start": 1, "end": 2, "sample_rate": 16000, "channels": 1, "codec": "pcm_s16le"}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    cache = tmp_path/"cache"
    cache.mkdir()
    path = cache/(key+".json")
    path.write_text(json.dumps(spec))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="cache path conflicts"):
        SourceClips(path, cache).fetch(1, 2, tmp_path/"out.wav")
    assert path.read_bytes() == before
    assert not (tmp_path/"out.wav").exists()


@pytest.fixture
def video_source(tmp_path):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg and ffprobe required")
    p = tmp_path / "screen share.mp4"
    cp = subprocess.run(
        [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=duration=2:size=160x120:rate=10",
            "-c:v", "mpeg4", "-pix_fmt", "yuv420p", str(p),
        ],
        capture_output=True,
        text=True,
    )
    if cp.returncode != 0:
        pytest.skip(f"ffmpeg lavfi/mpeg4 unavailable: {cp.stderr.strip()}")
    spec = prepare({"kind": "local", "path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
    s = tmp_path / "video_source.json"
    s.write_text(json.dumps(spec))
    return p, s


def test_frame_extracts_valid_png_and_reuses_cache(video_source, tmp_path):
    p, s = video_source
    clips = SourceClips(s, tmp_path / "cache")
    out = tmp_path / "frame.png"
    first = clips.fetch_frame(1.0, out)
    assert out.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert first["cache_reused"] is False
    assert first["source_sha256"] == hashlib.sha256(p.read_bytes()).hexdigest()
    assert first["source_timestamp"] == 1.0
    second = clips.fetch_frame(1.0, tmp_path / "frame_copy.png")
    assert second["cache_reused"] is True
    assert second["frame_sha256"] == first["frame_sha256"]


@pytest.mark.parametrize("ts", [-0.1, 3.5, float("nan"), float("inf")])
def test_frame_refuses_invalid_timestamp(video_source, tmp_path, ts):
    with pytest.raises(ValueError, match="invalid source-clock timestamp"):
        SourceClips(video_source[1], tmp_path / "cache").fetch_frame(ts, tmp_path / "bad.png")


def test_frame_refuses_source_change(video_source, tmp_path):
    p, s = video_source
    clips = SourceClips(s, tmp_path / "cache")
    clips.fetch_frame(0.5, tmp_path / "first.png")
    p.write_bytes(p.read_bytes() + b"mutated")
    out = tmp_path / "must-not-exist.png"
    with pytest.raises(ValueError, match="source version changed"):
        clips.fetch_frame(0.5, out)
    assert not out.exists()


def test_frame_on_audio_only_source_fails_cleanly(source, tmp_path):
    out = tmp_path / "audio_only.png"
    with pytest.raises(ValueError, match="no video frame|ffmpeg frame extraction failed"):
        SourceClips(source[1], tmp_path / "cache").fetch_frame(1.0, out)
    assert not out.exists()


def test_frame_cli_and_existing_output_protection(video_source, tmp_path):
    _, s = video_source
    out = tmp_path / "cli_frame.png"
    cp = subprocess.run(
        [
            sys.executable, str(Path(__file__).resolve().parents[1] / "source_clip.py"),
            "frame", "--source-spec", str(s), "--cache-dir", str(tmp_path / "cache"),
            "--timestamp", "0.5", "--output", str(out),
        ],
        capture_output=True,
        text=True,
    )
    assert cp.returncode == 0, cp.stderr
    receipt = json.loads(cp.stdout)
    assert receipt["frame_sha256"] == hashlib.sha256(out.read_bytes()).hexdigest()
    # Different timestamp must not overwrite an output bound to 0.5s
    with pytest.raises(ValueError, match="existing output"):
        SourceClips(s, tmp_path / "cache").fetch_frame(1.2, out)
    assert hashlib.sha256(out.read_bytes()).hexdigest() == receipt["frame_sha256"]


def test_frame_damaged_cache_and_truncated_wire_are_handled(video_source, tmp_path, monkeypatch):
    import source_clip
    _, s = video_source
    cache = tmp_path / "cache"
    clips = SourceClips(s, cache)
    first = clips.fetch_frame(0.5, tmp_path / "one.png")
    next(cache.glob("*.png")).write_bytes(b"not-a-png")
    second = clips.fetch_frame(0.5, tmp_path / "two.png")
    assert second["cache_reused"] is False
    assert second["frame_sha256"] == first["frame_sha256"]

    original = source_clip.run_worker
    def broken(spec, request):
        data = original(spec, request)
        return data[:-1] if request["action"] == "frame" else data
    monkeypatch.setattr(source_clip, "run_worker", broken)
    bad = tmp_path / "bad.png"
    with pytest.raises(ValueError, match="transfer/format"):
        SourceClips(s, tmp_path / "cache2").fetch_frame(0.5, bad)
    assert not bad.exists()


def test_locate_interpolates_long_turn_and_skips_frontmatter(tmp_path):
    from source_clip import locate_in_transcript
    transcript = tmp_path / "meeting.md"
    prefix = "甲" * 200
    suffix = "乙" * 200
    transcript.write_text(
        "---\n"
        'asr_note: "待核：目标短语"\n'
        "---\n\n"
        "Speaker A 00:01:00\n"
        f"{prefix}目标短语{suffix}\n\n"
        "Speaker B 00:02:40\n"
        "好的收到。\n",
        encoding="utf-8",
    )
    res = locate_in_transcript(transcript, "目标短语", duration=200.0)
    assert res["exploratory"] is True
    assert len(res["matches"]) == 1
    m = res["matches"][0]
    assert m["line"] == 6
    assert m["speaker"] == "Speaker A"
    assert m["turn_start"] == 60.0
    assert m["next_turn_start"] == 160.0
    assert m["method"] == "turn_interpolation"
    # 200 / 404 of 100s span -> ~109.5s
    assert 108.0 <= m["estimated_source_seconds"] <= 111.0
    assert m["tight_window"][0] == pytest.approx(m["estimated_source_seconds"] - 6.0, abs=0.01)
    assert m["tight_window"][1] == pytest.approx(m["estimated_source_seconds"] + 6.0, abs=0.01)
    assert m["medium_window"][0] == pytest.approx(m["estimated_source_seconds"] - 20.0, abs=0.01)
    assert m["medium_window"][1] == pytest.approx(m["estimated_source_seconds"] + 20.0, abs=0.01)


def test_locate_sparse_turn_uses_speech_rate_cap_and_final_turn_clamps(tmp_path):
    from source_clip import locate_in_transcript
    transcript = tmp_path / "sparse.md"
    transcript.write_text(
        "[00:00:10] Alice: 前置关键点。\n"
        "[00:05:10] Bob: 尾段测试词在这里。\n",
        encoding="utf-8",
    )
    sparse = locate_in_transcript(transcript, "关键点")
    assert sparse["matches"][0]["method"] == "speech_rate_capped"
    assert sparse["matches"][0]["estimated_source_seconds"] < 15.0

    final = locate_in_transcript(transcript, "测试词", duration=312.0, offset=1.5)
    assert final["matches"][0]["method"] == "speech_rate"
    assert final["matches"][0]["tight_window"][1] == 312.0
    assert final["matches"][0]["clamped_to_duration"] is True


def test_locate_cli_line_filter_and_negative_refusals(source, tmp_path):
    transcript = tmp_path / "dup.md"
    transcript.write_text(
        "Unanchored lead-in 重复词\n\n"
        "Speaker 1 00:01\n"
        "第一处 重复词 在这里。\n\n"
        "Speaker 2 [00:00:03.000]\n"
        "第二处 重复词 在这里。\n",
        encoding="utf-8",
    )
    script = Path(__file__).resolve().parents[1] / "source_clip.py"
    cp = subprocess.run(
        [
            sys.executable, str(script), "locate",
            "--transcript", str(transcript), "--needle", "重复词",
            "--line", "7", "--source-spec", str(source[1]),
        ],
        capture_output=True,
        text=True,
    )
    assert cp.returncode == 0, cp.stderr
    payload = json.loads(cp.stdout)
    assert payload["duration"] == pytest.approx(5.0, abs=0.05)
    assert len(payload["matches"]) == 1
    assert payload["matches"][0]["line"] == 7
    assert payload["matches"][0]["speaker"] == "Speaker 2"

    # Missing needle and invalid speech-rate fail closed with exit 2
    cp_missing = subprocess.run(
        [sys.executable, str(script), "locate", "--transcript", str(transcript), "--needle", "不存在"],
        capture_output=True,
        text=True,
    )
    assert cp_missing.returncode == 2
    cp_bad_rate = subprocess.run(
        [sys.executable, str(script), "locate", "--transcript", str(transcript), "--needle", "重复词", "--speech-rate", "0"],
        capture_output=True,
        text=True,
    )
    assert cp_bad_rate.returncode == 2
    cp_over_max = subprocess.run(
        [sys.executable, str(script), "locate", "--transcript", str(transcript), "--needle", "重复词", "--medium-pad", "100"],
        capture_output=True,
        text=True,
    )
    assert cp_over_max.returncode == 2


def test_locate_edge_cases_prose_timestamps_clamping_bom_and_columns(tmp_path):
    from source_clip import SCHEMA, locate_in_transcript

    # BOM + frontmatter + prose clock times + speakerless bracketed turn + inline speaker repeat
    transcript = tmp_path / "edge.md"
    transcript.write_bytes(
        (
            "\ufeff---\n"
            'asr_note: "目标短语"\n'
            "---\n\n"
            "Speaker A 00:01:00\n"
            "明天上午 10:30\n"
            "比例 80:99\n"
            "14:30 我们讨论目标短语。\n"
            "[00:02:00] 这里直接说无说话人短语。\n"
            "[00:03:00] Alice: Alice\n"
        ).encode("utf-8")
    )
    m_prose = locate_in_transcript(transcript, "目标短语")
    assert len(m_prose["matches"]) == 1
    assert m_prose["matches"][0]["speaker"] == "Speaker A"
    assert m_prose["matches"][0]["turn_start"] == 60.0

    m_speakerless = locate_in_transcript(transcript, "无说话人短语")
    assert len(m_speakerless["matches"]) == 1
    assert m_speakerless["matches"][0]["turn_start"] == 120.0
    assert m_speakerless["matches"][0]["speaker"] == ""

    m_col = locate_in_transcript(transcript, "Alice")
    assert len(m_col["matches"]) == 1
    # "[00:03:00] Alice: Alice" -> second "Alice" starts at 1-based column 19
    assert m_col["matches"][0]["column"] == 19

    # Near-duration clamping must keep non-degenerate full window width
    m_end = locate_in_transcript(transcript, "Alice", duration=180.0001, offset=6.0)
    tw = m_end["matches"][0]["tight_window"]
    assert tw[1] > tw[0]
    assert tw[1] - tw[0] == pytest.approx(12.0, abs=0.02)

    # Negative source_est must keep distinct tight and medium windows
    m_neg = locate_in_transcript(transcript, "目标短语", offset=-200.0)
    assert m_neg["matches"][0]["tight_window"] == [0.0, 12.0]
    assert m_neg["matches"][0]["medium_window"] == [0.0, 40.0]
    assert m_neg["matches"][0]["clamped_to_duration"] is True

    # Boolean duration in source_spec is rejected
    bad_spec = tmp_path / "bad_spec.json"
    bad_spec.write_text(json.dumps({"schema": SCHEMA, "duration": True}), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid source spec"):
        locate_in_transcript(transcript, "目标短语", source_spec=bad_spec)
