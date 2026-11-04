"""Real CLI/two-window dispatch with synthetic media and a fixture recognizer."""
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import sqlite3
import struct
import subprocess
import sys
import threading
import wave

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
from core.review_queue import ReviewQueue
from source_clip import prepare


@pytest.mark.parametrize("route", ["local", "url", "source-spec"])
def test_actual_two_window_cli_keeps_all_source_routes(tmp_path, route, monkeypatch):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg and ffprobe required")
    config = tmp_path/"isolated config"
    config.mkdir()
    db = config/"corrections.db"
    with sqlite3.connect(db) as conn:
        conn.executescript((SCRIPTS/"core/schema.sql").read_text())
    transcript = tmp_path/"transcript.md"
    transcript.write_text("甲 00:00:00.000\n邻接疑词结束\n")
    q = ReviewQueue(db)
    monkeypatch.setattr("core.review_queue.is_temp_path", lambda _: False)
    q.enqueue([{"file_path": str(transcript), "line_number": 2, "original_text": "疑词",
                      "suggested_text": "新词", "context_snippet": "邻接疑词结束", "domain": "fixture"}])
    tid = q.list_items(status=None)[0].id
    source = tmp_path/"synthetic source.wav"
    with wave.open(str(source), "wb") as stream:
        stream.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        stream.writeframes(b"".join(struct.pack("<h", i % 10000-5000) for i in range(320000)))
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    spec = tmp_path/"source.json"
    spec.write_text(json.dumps(prepare({"kind": "local", "path": str(source), "sha256": source_sha})))
    overrides = tmp_path/"times.json"
    overrides.write_text(json.dumps({str(tid): {"seconds": 10, "anchors": ["邻接"]}}))
    engine = tmp_path/"fixture recognizer.py"
    engine.write_text("print('邻接新词。结束')\n")
    server = None
    if route == "url":
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(tmp_path), **kwargs)
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        from urllib.parse import quote
        source_args = ["--audio", f"http://127.0.0.1:{server.server_port}/"+quote(source.name)]
    else:
        source_args = ["--source-spec", str(spec)] if route == "source-spec" else ["--audio", str(source)]
    out = tmp_path/"evidence"
    env = {**os.environ, "TRANSCRIPT_FIXER_CONFIG_DIR": str(config), "TRANSCRIPT_FIXER_DB_PATH": str(db),
           "TRANSCRIPT_FIXER_PEOPLE_ROSTER": str(tmp_path/"no-roster.md")}
    try:
        cp = subprocess.run([sys.executable, str(SCRIPTS/"verify_queue_audio.py"),
                "--transcript", str(transcript), *source_args, "--tight", "1", "--medium", "2",
                "--time-overrides", str(overrides), "--engine-script", str(engine), "--outdir", str(out)],
                capture_output=True, text=True, env=env, timeout=60)
    finally:
        if server:
            server.shutdown()
            server.server_close()
    assert cp.returncode == 0, cp.stdout+cp.stderr
    result = json.loads((out/"results.json").read_text())[0]
    assert result["status"] == "suggestion_supported"
    assert result["clip_ranges"] == {"tight": [9, 11], "medium": [8, 12]}
    assert result["clip_sha256"]["tight"] != result["clip_sha256"]["medium"]
    if route == "source-spec":
        assert result["source_audio_sha256"] == source_sha
        assert json.loads((out/f"{tid}-tight.wav.source.json").read_text())["source_sha256"] == source_sha
    assert q.list_items(status=None)[0].status == "pending"
