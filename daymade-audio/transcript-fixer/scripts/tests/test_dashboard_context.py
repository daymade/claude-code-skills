"""Status × feature matrix tests for the review dashboard's context/audio API.

Born from a real gap: every original test exercised the DECIDING action
(pending → verdict → rollback → guards), none exercised LOOKING BACK at a
decided item. accepted/overridden are states this system itself creates — the
verdict rewrites the file, so the original text is legitimately gone — and the
context endpoint used to misreport that as "file drifted, re-anchor needed",
which also killed the audio clip (the play button quietly vanished exactly on
the items a reviewer most wants to re-hear).

Matrix covered here: {pending, accepted, overridden, skipped, drifted} ×
{context lines, anchor mark, audio clip window, honest note}.
"""

from __future__ import annotations

import importlib
import sqlite3
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

TRANSCRIPT = """---
date: 2026-01-01
source: test
audio: {audio_path}
---

说话人甲 00:01:00.000
第一句话，含有目标错词在里面。

说话人乙 00:01:30.000
第二句话，正常内容。

说话人甲 00:02:00.000
第三句话，收尾。
"""


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Isolated config dir + DB + transcript + (stub) audio + imported server app."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setenv("TRANSCRIPT_FIXER_CONFIG_DIR", str(config_dir))

    # pytest tmp_path lives under tempfile.gettempdir(), which the queue's
    # temp-anchor guard rightly refuses (pipeline staging copies vanish). The
    # guard has its own dedicated test; here it would only block the fixtures.
    import core.review_queue as rq
    monkeypatch.setattr(rq, "is_temp_path", lambda _p: False)

    # Fresh DB with the real schema.
    from core.correction_repository import CorrectionRepository
    from utils import config as config_module
    importlib.reload(config_module)
    db_path = config_module.get_config().database.path
    CorrectionRepository(db_path).close()

    # Real-shaped transcript + a stub audio file (existence is what's checked).
    audio = tmp_path / "recording.m4a"
    audio.write_bytes(b"\x00" * 64)
    transcript = tmp_path / "meeting.md"
    transcript.write_text(TRANSCRIPT.format(audio_path=audio), encoding="utf-8")

    # Import the dashboard app AFTER the env var points at the isolated dir.
    dash_dir = SCRIPTS_DIR / "review-dashboard"
    sys.path.insert(0, str(dash_dir))
    for mod in ("server",):
        if mod in sys.modules:
            del sys.modules[mod]
    server = importlib.import_module("server")
    importlib.reload(server)
    assert Path(server.DB_PATH) == Path(db_path)

    from core.review_queue import ReviewQueue
    queue = ReviewQueue(db_path, dict_add_fn=lambda *a, **k: None)

    yield {
        "client": TestClient(server.app),
        "queue": queue,
        "transcript": transcript,
        "db_path": db_path,
    }
    sys.path.remove(str(dash_dir))


def _enqueue(queue, transcript, original="目标错词", suggested="目标正词", line=7):
    return queue.enqueue([{
        "original": original, "suggested": suggested,
        "file": str(transcript), "line": line,
        "context": "第一句话，含有目标错词在里面。",
        "kind": "wording", "domain": "matrix-test", "source": "manual",
    }])["added"][0]


def _ctx(client, item_id):
    res = client.get(f"/api/context/{item_id}")
    assert res.status_code == 200
    return res.json()


def assert_full_context(data, expected_mark):
    assert data["lines"], f"context lines missing: {data}"
    assert data["anchor_line"], f"anchor missing: {data}"
    assert data["mark_text"] == expected_mark
    assert data["audio"] and data["audio"]["available"], f"audio missing: {data}"
    # 00:01:00 utterance → clip runs to the 00:01:30 line (+padding)
    assert data["audio"]["start"] == pytest.approx(59.7, abs=0.01)
    assert data["audio"]["end"] == pytest.approx(90.3, abs=0.01)
    assert not (data.get("note") or ""), f"unexpected warning note: {data['note']}"


class TestStatusFeatureMatrix:
    def test_pending_has_context_and_audio(self, env):
        item_id = _enqueue(env["queue"], env["transcript"])
        assert_full_context(_ctx(env["client"], item_id), "目标错词")

    def test_accepted_anchors_on_resolved_text(self, env):
        """After accept the file carries the VERDICT — that's not drift."""
        item_id = _enqueue(env["queue"], env["transcript"])
        env["queue"].resolve(item_id, "accepted")
        assert "目标正词" in env["transcript"].read_text(encoding="utf-8")
        assert_full_context(_ctx(env["client"], item_id), "目标正词")

    def test_overridden_anchors_on_override_text(self, env):
        item_id = _enqueue(env["queue"], env["transcript"])
        env["queue"].resolve(item_id, "overridden", override_to="人工改词")
        assert_full_context(_ctx(env["client"], item_id), "人工改词")

    def test_skipped_keeps_original_anchor(self, env):
        item_id = _enqueue(env["queue"], env["transcript"])
        env["queue"].resolve(item_id, "skipped")
        assert_full_context(_ctx(env["client"], item_id), "目标错词")

    def test_true_drift_falls_back_to_line_hint_with_honest_note(self, env):
        """Neither original nor verdict present → neighborhood + warning, no mark."""
        item_id = _enqueue(env["queue"], env["transcript"])
        t = env["transcript"]
        t.write_text(t.read_text(encoding="utf-8").replace("目标错词", "外部编辑"),
                     encoding="utf-8")
        data = _ctx(env["client"], item_id)
        assert data["lines"] and data["anchor_line"] == 7
        assert data["mark_text"] is None
        assert "漂移" in (data.get("note") or "")
        assert data["audio"] and data["audio"]["available"]  # audio still offered

    def test_audio_endpoint_serves_declared_file(self, env):
        item_id = _enqueue(env["queue"], env["transcript"])
        res = env["client"].get(f"/api/audio/{item_id}")
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("audio/")

    def test_no_audio_frontmatter_means_no_audio_not_error(self, env, tmp_path):
        bare = tmp_path / "bare.md"
        bare.write_text("---\ndate: 2026-01-01\n---\n\n说话人甲 00:01:00.000\n目标错词句子。\n",
                        encoding="utf-8")
        item_id = env["queue"].enqueue([{
            "original": "目标错词", "suggested": "目标正词",
            "file": str(bare), "line": 6, "kind": "wording",
            "domain": "matrix-test", "source": "manual",
        }])["added"][0]
        data = _ctx(env["client"], item_id)
        assert data["lines"]
        assert data["audio"] is None
        assert env["client"].get(f"/api/audio/{item_id}").status_code == 404


class TestFrontmatterAudioParsing:
    """Adversarial-probe regressions: six bugs once lived in this one function
    (empty value → Path('.') → 500; directory → 500; quoted path silently
    dropped; relative path resolved against server cwd; unclosed frontmatter
    parsed as valid; silent 60-line scan cap)."""

    @pytest.fixture()
    def parse(self, env):
        import server
        return server._frontmatter_audio

    def _md(self, tmp_path, fm_lines, name="t.md", close=True):
        body = ["---", *fm_lines] + (["---"] if close else []) + ["", "正文行"]
        p = tmp_path / name
        p.write_text("\n".join(body), encoding="utf-8")
        return p

    def test_empty_value_yields_none_not_cwd(self, parse, tmp_path):
        md = self._md(tmp_path, ["audio:"])
        assert parse(md) is None  # was: Path('.') → FileResponse(dir) → 500

    def test_directory_value_yields_none(self, parse, tmp_path):
        d = tmp_path / "somedir"; d.mkdir()
        md = self._md(tmp_path, [f"audio: {d}"])
        assert parse(md) is None  # was: exists()=True for dirs → 500

    def test_quoted_path_is_unquoted(self, parse, tmp_path):
        wav = tmp_path / "a.wav"; wav.write_bytes(b"\x00")
        md = self._md(tmp_path, [f'audio: "{wav}"'])
        assert parse(md) == wav  # was: quotes kept → silent None

    def test_relative_path_resolves_against_transcript_dir(self, parse, tmp_path):
        sub = tmp_path / "sub"; sub.mkdir()
        wav = sub / "rec.wav"; wav.write_bytes(b"\x00")
        md = self._md(sub, ["audio: rec.wav"])
        assert parse(md) == wav.resolve()  # was: resolved against server cwd

    def test_tilde_is_expanded(self, parse, tmp_path, monkeypatch):
        home = tmp_path / "home"; home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        wav = home / "h.wav"; wav.write_bytes(b"\x00")
        md = self._md(tmp_path, ["audio: ~/h.wav"])
        assert parse(md) == wav

    def test_unclosed_frontmatter_is_not_frontmatter(self, parse, tmp_path):
        wav = tmp_path / "a.wav"; wav.write_bytes(b"\x00")
        md = self._md(tmp_path, [f"audio: {wav}"], close=False)
        assert parse(md) is None  # was: body text parsed as a live field

    def test_long_frontmatter_within_cap_is_found(self, parse, tmp_path):
        wav = tmp_path / "a.wav"; wav.write_bytes(b"\x00")
        filler = [f"k{i}: v{i}" for i in range(80)]
        md = self._md(tmp_path, filler + [f"audio: {wav}"])
        assert parse(md) == wav  # was: silent 60-line cap
