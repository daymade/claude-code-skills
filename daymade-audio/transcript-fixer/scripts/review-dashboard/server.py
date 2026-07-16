#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "fastapi",
#   "uvicorn",
# ]
# ///
"""Local review dashboard for the transcript-fixer review queue.

One command starts it:

    uv run scripts/review-dashboard/server.py

Design contract (mirrors the annotation-tool pattern this queue is built on):
READS go straight to the SQLite DB (fast, read-only); every WRITE shells out
to the transcript-fixer CLI (`--resolve-review …`) so the CLI's state machine,
anchor guards, and audit logging stay the single source of truth — this UI
never mutates the database itself. Agent (CLI) and human (this page) are
equal writers of the same queue.
"""

from __future__ import annotations

import json
import re
import subprocess
import sqlite3
import sys
import webbrowser
from pathlib import Path
from threading import Timer

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

DASHBOARD_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = DASHBOARD_DIR.parent
STATIC_DIR = DASHBOARD_DIR / "static"
CLI_SCRIPT = SCRIPTS_DIR / "fix_transcription.py"

# Reuse the CLI's own config resolution (env override + config.json) so the
# dashboard can never read a different database than the CLI writes.
sys.path.insert(0, str(SCRIPTS_DIR))
from utils.config import get_config  # noqa: E402

DB_PATH = get_config().database.path
PORT = 8767

app = FastAPI(title="转写修正审核台")


def _connect_ro() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def run_cli(*args: str) -> str:
    """Invoke the transcript-fixer CLI; returns stdout (the --json line).

    rc 0 = success, 1 = user/state error, 2 = anchor guard tripped — all three
    put a machine-readable {error, message} object on stdout under --json, so
    they are returned for parsing (the caller maps them to proper HTTP codes)
    instead of being flattened into an opaque 500."""
    result = subprocess.run(
        ["uv", "run", str(CLI_SCRIPT), *args],
        capture_output=True, text=True, timeout=120, cwd=str(SCRIPTS_DIR),
    )
    if result.returncode not in (0, 1, 2):
        raise RuntimeError((result.stderr or result.stdout).strip()[:800])
    return result.stdout.strip()


def _cli_json(*args: str) -> dict:
    out = run_cli(*args, "--json")
    for line in reversed(out.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise RuntimeError(f"CLI returned no JSON status line: {out[:300]}")


ITEM_COLUMNS = (
    "id, created_at, source, domain, file_path, line_number, context_snippet, "
    "original_text, suggested_text, kind, evidence, actions_json, priority, "
    "status, decided_at, decided_by, decision_note, resolved_text, applied_at, apply_log"
)


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["actions"] = json.loads(d.pop("actions_json")) if d.get("actions_json") else []
    d["apply_log"] = json.loads(d["apply_log"]) if d.get("apply_log") else None
    if d.get("file_path"):
        d["file_name"] = Path(d["file_path"]).name
    return d


@app.get("/api/queue")
def api_queue(status: str = "pending", domain: str = "", source: str = "", kind: str = ""):
    query = f"SELECT {ITEM_COLUMNS} FROM review_items WHERE 1=1"
    params: list = []
    if status and status != "all":
        query += " AND status = ?"
        params.append(status)
    if domain:
        query += " AND domain = ?"
        params.append(domain)
    if source:
        query += " AND source = ?"
        params.append(source)
    if kind:
        query += " AND kind = ?"
        params.append(kind)
    query += " ORDER BY priority DESC, id ASC LIMIT 500"
    with _connect_ro() as conn:
        rows = conn.execute(query, params).fetchall()
        by_status = dict(conn.execute(
            "SELECT status, COUNT(*) FROM review_items GROUP BY status").fetchall())
        domains = [r[0] for r in conn.execute(
            "SELECT DISTINCT domain FROM review_items ORDER BY domain").fetchall()]
        kinds = [r[0] for r in conn.execute(
            "SELECT DISTINCT kind FROM review_items ORDER BY kind").fetchall()]
        sources = [r[0] for r in conn.execute(
            "SELECT DISTINCT source FROM review_items ORDER BY source").fetchall()]
    return {
        "items": [_row_to_dict(r) for r in rows],
        "stats": {"by_status": by_status, "pending_total": by_status.get("pending", 0)},
        "filters": {"domains": domains, "kinds": kinds, "sources": sources},
    }


def _find_anchor_line(lines: list[str], needle: str, line_hint: int | None) -> int | None:
    """1-based line containing `needle`, preferring the hinted line."""
    if not needle:
        return None
    if line_hint and 1 <= line_hint <= len(lines) and needle in lines[line_hint - 1]:
        return line_hint
    return next((i + 1 for i, l in enumerate(lines) if needle in l), None)


@app.get("/api/context/{item_id}")
def api_context(item_id: int, window: int = 12):
    with _connect_ro() as conn:
        row = conn.execute(
            f"SELECT {ITEM_COLUMNS} FROM review_items WHERE id = ?", (item_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "item not found")
    item = _row_to_dict(row)
    if not item.get("file_path"):
        return {"lines": [], "anchor_line": None, "audio": None, "note": "此条目没有文件锚点"}
    path = Path(item["file_path"])
    if not path.exists():
        return {"lines": [], "anchor_line": None, "audio": None,
                "note": f"文件已不在原处：{path}（需要重新锚定）"}
    if path.stat().st_size > 20 * 1024 * 1024:
        return {"lines": [], "anchor_line": None, "audio": None,
                "note": "文件超过 20MB，不在页面内联展示——请在编辑器中打开核对"}
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    # line_number is coerced defensively: SQLite columns are dynamically typed.
    try:
        line_hint = int(item.get("line_number") or 0) or None
    except (TypeError, ValueError):
        line_hint = None
    # Anchor fallback chain: the ORIGINAL text (pending / kept_original items) →
    # the RESOLVED text (accepted/overridden items — the file now carries the
    # verdict, so the original is legitimately gone; that is not drift) → the
    # bare line hint (real drift: still show the neighborhood + audio, flagged).
    note = None
    mark_text = item["original_text"]
    line_no = _find_anchor_line(lines, item["original_text"], line_hint)
    if line_no is None and item.get("resolved_text"):
        line_no = _find_anchor_line(lines, item["resolved_text"], line_hint)
        if line_no is not None:
            mark_text = item["resolved_text"]
    if line_no is None and line_hint and 1 <= line_hint <= len(lines):
        line_no = line_hint
        mark_text = None
        note = "原文与终裁文本都未命中——按登记行号显示附近内容（文件可能已漂移）"
    if line_no is None:
        return {"lines": [], "anchor_line": None, "audio": None,
                "note": "原文在文件中已找不到（文件已被修改，需要重新锚定）"}
    start = max(0, line_no - 1 - window)
    end = min(len(lines), line_no + window)
    audio_info = None
    if _frontmatter_audio(path) is not None:
        win = _clip_window(lines, line_no - 1)
        if win:
            audio_info = {"available": True, "start": round(win[0], 3), "end": round(win[1], 3)}
    return {
        "lines": [{"no": i + 1, "text": lines[i][:2000], "is_anchor": (i + 1) == line_no}
                  for i in range(start, end)],
        "anchor_line": line_no,
        "mark_text": mark_text,
        "audio": audio_info,
        "note": note,
    }


# ── audio playback ──────────────────────────────────────────────────────────
# A transcript declares its recording EXPLICITLY via a frontmatter `audio:`
# field (absolute path). No implicit directory scanning: if the field is
# absent, the card simply has no play button. Speaker-timestamp lines
# (`<speaker> HH:MM:SS.mmm`) around the anchor line give the clip window.

_TS_LINE = re.compile(r"^\S.*?\s(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*$")
_AUDIO_MIME = {".m4a": "audio/mp4", ".mp3": "audio/mpeg", ".wav": "audio/wav",
               ".flac": "audio/flac", ".opus": "audio/ogg", ".ogg": "audio/ogg",
               ".aac": "audio/aac"}


def _frontmatter_audio(md_path: Path) -> Path | None:
    """Return the Path declared in the transcript's frontmatter `audio:` field."""
    try:
        with open(md_path, encoding="utf-8", errors="replace") as f:
            first = f.readline()
            if first.strip() != "---":
                return None
            for _ in range(60):
                line = f.readline()
                if not line or line.strip() == "---":
                    return None
                if line.startswith("audio:"):
                    p = Path(line.split(":", 1)[1].strip())
                    return p if p.exists() else None
    except OSError:
        return None
    return None


def _ts_to_seconds(m: re.Match) -> float:
    h, mi, s, ms = (int(m.group(i)) for i in range(1, 5))
    return h * 3600 + mi * 60 + s + ms / 1000


def _clip_window(lines: list[str], anchor_idx: int) -> tuple[float, float] | None:
    """Clip = [nearest speaker timestamp above the anchor, next one below]."""
    start = None
    for i in range(anchor_idx, -1, -1):
        m = _TS_LINE.match(lines[i])
        if m:
            start = _ts_to_seconds(m)
            break
    if start is None:
        return None
    end = start + 30.0
    for i in range(anchor_idx + 1, min(len(lines), anchor_idx + 80)):
        m = _TS_LINE.match(lines[i])
        if m:
            end = _ts_to_seconds(m)
            break
    return max(0.0, start - 0.3), end + 0.3


@app.get("/api/audio/{item_id}")
def api_audio(item_id: int):
    with _connect_ro() as conn:
        row = conn.execute(
            "SELECT file_path FROM review_items WHERE id = ?", (item_id,)
        ).fetchone()
    if not row or not row["file_path"]:
        raise HTTPException(404, "item has no file anchor")
    audio = _frontmatter_audio(Path(row["file_path"]))
    if audio is None:
        raise HTTPException(404, "transcript declares no audio: frontmatter field")
    media_type = _AUDIO_MIME.get(audio.suffix.lower(), "application/octet-stream")
    # FileResponse handles HTTP Range, so <audio> can seek without full download.
    return FileResponse(audio, media_type=media_type)


class ResolveBody(BaseModel):
    id: int
    decision: str  # accepted | overridden | kept_original | skipped | reopen
    override_to: str | None = None
    note: str | None = None
    by: str | None = None


@app.post("/api/resolve")
def api_resolve(body: ResolveBody):
    args = ["--resolve-review", str(body.id), "--decision", body.decision]
    if body.override_to:
        args += ["--override-to", body.override_to]
    if body.note:
        args += ["--note", body.note]
    if body.by:
        args += ["--by", body.by]
    try:
        result = _cli_json(*args)
    except (RuntimeError, json.JSONDecodeError) as e:
        raise HTTPException(500, str(e))
    if result.get("error") == "re_anchor_needed":
        # Guard tripped: the file drifted since enqueue. Nothing was applied.
        raise HTTPException(409, result.get("message", "re-anchor needed"))
    if result.get("error"):
        # State/user errors (already resolved, missing override text, …) are
        # client errors, not server faults.
        raise HTTPException(400, result.get("message", result["error"]))
    return result


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _preflight():
    """Fail fast if the DB or CLI is unusable — otherwise every button 500s."""
    if not Path(DB_PATH).exists():
        raise SystemExit(f"preflight FAILED: database not found at {DB_PATH} — run --init first")
    try:
        with _connect_ro() as conn:
            conn.execute("SELECT 1 FROM review_items LIMIT 1")
    except sqlite3.DatabaseError as e:
        raise SystemExit(
            f"preflight FAILED: review_items table unavailable ({e}).\n"
            f"If the table is merely missing, run any transcript-fixer command once "
            f"to apply the schema. If the file itself is corrupt, restore a backup "
            f"from the backups/ directory next to it (never delete the live DB blindly).")
    try:
        result = subprocess.run(
            ["uv", "run", str(CLI_SCRIPT), "--help"],
            capture_output=True, text=True, timeout=90, cwd=str(SCRIPTS_DIR),
        )
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout).strip()[:400])
    except Exception as e:
        raise SystemExit(
            f"preflight FAILED: cannot invoke the CLI at {CLI_SCRIPT}\nerror: {e}\n"
            f"Every resolve action shells out to it — fix this before starting.")


if __name__ == "__main__":
    import uvicorn

    _preflight()
    Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    print(f"转写修正审核台 → http://127.0.0.1:{PORT}   (DB: {DB_PATH})")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
