#!/usr/bin/env python3
"""Generate a self-contained HTML audit page for ASR transcripts.

Reads speaker-labeled CSV/TXT/diarization files produced by speaker_transcribe.py
and emits a single interactive HTML file with audio playback, per-turn flags/notes,
speaker alias mapping, and export report.

Usage:
  uv run generate_audit_html.py PROJECT_DIR [--output OUTPUT_PATH]
  uv run generate_audit_html.py PROJECT_DIR --manifest MANIFEST.json
"""
# /// script
# dependencies = []
# ///

import argparse
import csv
import html
import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime


class Config:
    """Runtime paths and labels for the audit generator."""
    def __init__(self, project_dir: Path, output_path: Path = None,
                 csv_dir: Path = None, txt_dir: Path = None,
                 diarization_dir: Path = None, audio_dir: Path = None,
                 original_dir: Path = None, manifest_path: Path = None,
                 title: str = "ASR 转写审核", subtitle: str = "Qwen3-ASR + pyannote 说话人分割 · 本地审核",
                 storage_key: str = "asr-audit-v1",
                 material_final: list = None, material_rough: list = None,
                 known_speakers: dict = None):
        self.project_dir = project_dir
        self.output_path = output_path or (project_dir / "audit" / "index.html")
        self.csv_dir = csv_dir or project_dir
        self.txt_dir = txt_dir or project_dir
        self.diarization_dir = diarization_dir or project_dir
        self.audio_dir = audio_dir or project_dir
        self.original_dir = original_dir
        self.manifest_path = manifest_path
        self.title = title
        self.subtitle = subtitle
        self.storage_key = storage_key
        self.material_final = material_final or []
        self.material_rough = material_rough or []
        self.known_speakers = known_speakers or {}


# Populated by main(); functions below read from this singleton.
CONFIG = Config(Path.cwd())


def safe_stem(rel_path: str) -> str:
    """Return the filename stem, matching speaker_transcribe.py's stem logic."""
    return Path(rel_path).stem


def classify_material(rel_path: str) -> str:
    """Classify file as 成片 / 粗剪 / 素材 based on configurable folder-name keywords."""
    lower = rel_path.lower()
    for kw in CONFIG.material_final:
        if kw.lower() in lower:
            return "成片"
    for kw in CONFIG.material_rough:
        if kw.lower() in lower:
            return "粗剪"
    return "素材"


def format_time(seconds: float) -> str:
    seconds = max(0, seconds)
    total_ms = int(round(seconds * 1000))
    h, rem = divmod(total_ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}.{ms:03d}"


def format_duration_total(seconds: float) -> str:
    seconds = max(0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _resolve_audio_path(stem: str, wav_name: str | None) -> Path | None:
    """Resolve a playable audio path under CONFIG.audio_dir, rejecting traversal."""
    candidates = []
    if wav_name:
        candidates.append(Path(wav_name).name)
    for suffix in [".wav", ".m4a", ".mp3"]:
        candidates.append(f"{stem}{suffix}")
    for candidate in candidates:
        if not candidate:
            continue
        if "/" in candidate or "\\" in candidate or candidate.startswith(".."):
            continue
        p = CONFIG.audio_dir / candidate
        try:
            p.resolve().relative_to(CONFIG.audio_dir.resolve())
        except (ValueError, RuntimeError, OSError):
            continue
        if p.exists():
            return p
    return None


def load_csv_rows(stem: str) -> list[dict]:
    path = CONFIG.csv_dir / f"{stem}.csv"
    if not path.exists():
        return []
    rows = []
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                rows.append({
                    "file": row.get("file", ""),
                    "start": _require_float(row.get("start"), "start"),
                    "end": _require_float(row.get("end"), "end"),
                    "duration": _require_float(row.get("duration"), "duration"),
                    "speaker": row.get("speaker", ""),
                    "text": row.get("text", ""),
                })
            except (ValueError, TypeError) as e:
                print(f"WARN: skipping malformed row in {path}: {row} ({e})", file=sys.stderr)
                continue
    return rows


def _require_float(value, field_name: str) -> float:
    """Require a non-empty numeric CSV field; fail-fast instead of defaulting to 0."""
    if value is None or str(value).strip() == "":
        raise ValueError(f"missing required field: {field_name}")
    return float(value)


def load_txt_content(stem: str) -> str:
    path = CONFIG.txt_dir / f"{stem}.txt"
    if not path.exists():
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_diarization(stem: str) -> dict:
    for suffix in [".diarization.json", ".json"]:
        path = CONFIG.diarization_dir / f"{stem}{suffix}"
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                print(f"WARN: failed to parse diarization {path}: {e}", file=sys.stderr)
    return {}


SPEAKER_COLORS = {
    "SPEAKER_00": "#6c757d",
    "SPEAKER_01": "#fd7e14",
    "SPEAKER_02": "#dc3545",
    "SPEAKER_03": "#6f42c1",
    "SPEAKER_04": "#d63384",
    "SPEAKER_05": "#20c997",
    "SPEAKER_06": "#0dcaf0",
    "SPEAKER_07": "#6610f2",
    "SPEAKER_08": "#e83e8c",
    "SPEAKER_09": "#17a2b8",
}

FALLBACK_PALETTE = [
    "#0d6efd", "#198754", "#fd7e14", "#dc3545", "#6f42c1",
    "#d63384", "#20c997", "#0dcaf0", "#6610f2", "#e83e8c",
]

BACKCHANNELS = {
    "嗯", "嗯嗯", "嗯哼", "嗯呢", "嗯好", "嗯行", "嗯对",
    "啊", "哦", "喔", "呵", "哈", "哈哈", "呵呵", "嘿嘿", "嗨",
    "哎", "哎呀", "唉", "咦", "呜", "呼",
    "对", "对的", "对啊", "对呀", "对对", "对嘛",
    "是", "是的", "是啊", "是嘛", "是是", "是是是",
    "没错", "就是", "懂了", "明白", "清楚", "知道了",
    "好的", "好", "好嘛", "好呀", "好哦", "好嘞", "好滴",
    "行", "可以", "ok", "okay", "ok的", "ok好", "ok行",
    "yes", "yeah", "yep", "no", "nope", "right", "sure",
    "uh-huh", "mm-hmm", "hmm", "uh",
    "这样", "原来如此", "好吧", "算了", "怎么", "是啊",
}


def get_speaker_color_py(name: str) -> str:
    if name in SPEAKER_COLORS:
        return SPEAKER_COLORS[name]
    idx = sum(ord(c) for c in name) % len(FALLBACK_PALETTE)
    return FALLBACK_PALETTE[idx]


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    if len(color) == 3:
        r = int(color[0] * 2, 16)
        g = int(color[1] * 2, 16)
        b = int(color[2] * 2, 16)
    else:
        r = int(color[0:2], 16)
        g = int(color[2:4], 16)
        b = int(color[4:6], 16)
    return r, g, b


_HEX_RE = re.compile(r"^#?[0-9a-fA-F]{3}([0-9a-fA-F]{3})?$")


def normalize_color(color: str, fallback: str = "#6c757d") -> str:
    """Validate a hex color string; return fallback on malformed input and warn."""
    if not isinstance(color, str):
        print(f"WARN: color must be a string, got {type(color).__name__}; using {fallback}", file=sys.stderr)
        return fallback
    if _HEX_RE.match(color):
        return color if color.startswith("#") else f"#{color}"
    print(f"WARN: malformed color '{color}'; using {fallback}", file=sys.stderr)
    return fallback


def css_escape(s: str) -> str:
    """Escape a string for safe use inside a CSS double-quoted attribute selector.
    Also escapes characters that could form a closing </style> tag in the host HTML."""
    out = []
    for ch in s:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\A ")
        elif ch == "\r":
            out.append("\\D ")
        elif ch in "<>":
            # Unicode escape so the HTML parser never sees a literal </style> sequence.
            out.append(f"\\{ord(ch):X} ")
        elif ch == "/":
            # Not strictly needed for the attribute selector, but prevents accidental </style>
            # formation when concatenated with other CSS content.
            out.append("\\2F ")
        else:
            out.append(ch)
    return "".join(out)



def _base_speaker_css(speaker: str, color: str) -> str:
    safe = css_escape(speaker)
    color = normalize_color(color)
    return f"""
    .turn-group[data-speaker="{safe}"] .avatar {{ background-color: {color}; }}
    .turn-group[data-speaker="{safe}"] .speaker-name {{ color: {color}; }}
    .turn-group[data-speaker="{safe}"] .group-body {{ border-left-color: {color}; }}
    """


def _switchable_speaker_css(speaker: str, color: str) -> str:
    """Switchable variant: compact view with optional bubble mode."""
    color = normalize_color(color)
    r, g, b = hex_to_rgb(color)
    safe = css_escape(speaker)
    return _base_speaker_css(speaker, color) + f"""
    .turn-group[data-speaker="{safe}"] {{ background-color: rgba({r},{g},{b},0.08); border-radius: 6px; }}
    .turn-group[data-speaker="{safe}"] .segment {{ color: {color}; }}
    .bubble-mode .turn-group[data-speaker="{safe}"] {{ background-color: transparent; }}
    .bubble-mode .turn-group[data-speaker="{safe}"] .group-body {{
        background-color: {color};
        color: #fff;
        border-left: none;
        border-radius: 14px;
        padding: 10px 14px;
        max-width: min(95%, 760px);
    }}
    .bubble-mode .turn-group[data-speaker="{safe}"] .avatar {{
        background-color: #fff;
        color: {color};
        box-shadow: 0 0 0 2px {color};
    }}
    .bubble-mode .turn-group[data-speaker="{safe}"] .speaker-name {{ color: {color}; font-size: 11px; margin-top: 0; }}
    .bubble-mode .turn-group[data-speaker="{safe}"] .segment {{ color: #fff; }}
    .bubble-mode .turn-group[data-speaker="{safe}"] .seg-time {{ color: rgba(255,255,255,0.75); }}
    """


def initial(name: str) -> str:
    if not name:
        return "?"
    return name[0].upper() if name[0].isascii() else name[0]


def is_backchannel(text: str) -> bool:
    t = text.strip().lower()
    if t in BACKCHANNELS:
        return True
    if len(text.strip()) <= 2 and not text.strip().isdigit():
        return True
    return False


def group_rows(rows: list[dict]) -> list[list[dict]]:
    if not rows:
        return []
    groups = []
    current = [rows[0]]
    for row in rows[1:]:
        if row["speaker"] == current[-1]["speaker"]:
            current.append(row)
        else:
            groups.append(current)
            current = [row]
    groups.append(current)
    return groups


def is_short_group(group: list[dict]) -> bool:
    if not group:
        return False
    total_duration = group[-1]["end"] - group[0]["start"]
    if total_duration > 3.0:
        return False
    return all(is_backchannel(row["text"]) for row in group)


def merge_short_runs(groups: list[list[dict]]) -> list:
    merged = []
    run = []
    for group in groups:
        if is_short_group(group):
            run.extend(group)
        else:
            if run:
                merged.append(("short_run", run))
                run = []
            merged.append(group)
    if run:
        merged.append(("short_run", run))
    return merged


def render_segment(row: dict, idx: int, stem: str) -> str:
    turn_id = f"{stem}::{idx}"
    start = row["start"]
    text = html.escape(row["text"])
    return f'''
    <p class="segment" data-turn-idx="{idx}" data-turn-id="{html.escape(turn_id)}">
      <span class="seg-actions">
        <span class="seg-action" data-action="playTurn" data-turn-idx="{idx}" title="播放该句">▶</span>
        <span class="seg-action" data-action="toggleFlag" data-turn-id="{html.escape(turn_id)}" title="标注问题">⚑</span>
        <span class="seg-action" data-action="toggleNote" data-turn-id="{html.escape(turn_id)}" title="备注">📝</span>
      </span>
      <span class="seg-time" data-action="seekTo" data-time="{start}">{format_time(start)}</span>{text}
    </p>
    <div class="audit-extras hidden" id="audit-extras-{html.escape(turn_id)}" data-turn-id="{html.escape(turn_id)}">
      <div class="flag-section">
        <select class="flag-select" data-action="setFlagReason" data-turn-id="{html.escape(turn_id)}">
          <option value="">选择问题类型</option>
          <option value="speaker">说话人错误</option>
          <option value="text">转写错误</option>
          <option value="boundary">时间边界错误</option>
          <option value="missing">漏句</option>
          <option value="other">其他</option>
        </select>
      </div>
      <div class="note-preview hidden"></div>
      <div class="note-section">
        <textarea class="note-input" data-action="setNote" data-turn-id="{html.escape(turn_id)}" placeholder="备注…"></textarea>
      </div>
    </div>
    '''


def render_group(group: list[dict], stem: str, start_idx: int) -> tuple[str, int]:
    speaker = group[0]["speaker"]
    short = is_short_group(group)
    start = group[0]["start"]
    end = group[-1]["end"]
    segments = []
    idx = start_idx
    for row in group:
        segments.append(render_segment(row, idx, stem))
        idx += 1
    segments_html = "".join(segments)
    short_attr = ' data-short="1"' if short else ""
    group_html = f"""
    <div class="turn-group" data-speaker="{html.escape(speaker)}"{short_attr}>
      <div class="group-meta">
        <div class="avatar">{html.escape(initial(speaker))}</div>
        <div class="speaker-name" data-speaker="{html.escape(speaker)}">{html.escape(speaker)}</div>
        <div class="group-time">{format_time(start)} - {format_time(end)}</div>
      </div>
      <div class="group-body">
        {segments_html}
      </div>
    </div>
    """
    return group_html, idx


def render_short_run(rows: list[dict], stem: str, start_idx: int) -> tuple[str, int]:
    tags = []
    extras = []
    idx = start_idx
    for row in rows:
        speaker = row["speaker"]
        start = row["start"]
        text = html.escape(row["text"])
        turn_id = f"{stem}::{idx}"
        tags.append(
            f'<span class="short-tag" data-turn-idx="{idx}" data-turn-id="{html.escape(turn_id)}">'
            f'<span class="short-speaker" data-speaker="{html.escape(speaker)}">{html.escape(speaker)}</span>'
            f'<span class="short-time" data-action="seekTo" data-time="{start}">{format_time(start)}</span>'
            f'<span class="short-actions">'
            f'<span class="short-action" data-action="playTurn" data-turn-idx="{idx}" title="播放该句">▶</span>'
            f'<span class="short-action" data-action="toggleFlag" data-turn-id="{html.escape(turn_id)}" title="标注问题">⚑</span>'
            f'<span class="short-action" data-action="toggleNote" data-turn-id="{html.escape(turn_id)}" title="备注">📝</span>'
            f'</span>'
            f'{text}'
            f'</span>'
        )
        extras.append(
            f'<div class="audit-extras hidden" id="audit-extras-{html.escape(turn_id)}" data-turn-id="{html.escape(turn_id)}" style="flex-basis:100%">'
            f'<div class="flag-section">'
            f'<select class="flag-select" data-action="setFlagReason" data-turn-id="{html.escape(turn_id)}">'
            f'<option value="">选择问题类型</option>'
            f'<option value="speaker">说话人错误</option>'
            f'<option value="text">转写错误</option>'
            f'<option value="boundary">时间边界错误</option>'
            f'<option value="missing">漏句</option>'
            f'<option value="other">其他</option>'
            f'</select>'
            f'</div>'
            f'<div class="note-preview hidden"></div>'
            f'<div class="note-section">'
            f'<textarea class="note-input" data-action="setNote" data-turn-id="{html.escape(turn_id)}" placeholder="备注…"></textarea>'
            f'</div>'
            f'</div>'
        )
        idx += 1
    run_html = f"""
    <div class="turn-group short-run" data-short="1">
      <div class="group-meta">
        <div class="avatar">…</div>
        <div class="speaker-name">短回应</div>
      </div>
      <div class="group-body">
        {"".join(tags)}{"".join(extras)}
      </div>
    </div>
    """
    return run_html, idx


def render_reader_html(stem: str, rows: list[dict]) -> str:
    if not rows:
        return '<div class="reader-empty">无转写数据</div>'
    groups = group_rows(rows)
    merged = merge_short_runs(groups)
    groups_html = []
    idx = 0
    for item in merged:
        if isinstance(item, tuple) and item[0] == "short_run":
            item_html, idx = render_short_run(item[1], stem, idx)
            groups_html.append(item_html)
        else:
            item_html, idx = render_group(item, stem, idx)
            groups_html.append(item_html)
    return f'<div class="reader-transcript">\n{"".join(groups_html)}\n</div>'


def rel_to_audit(path: Path | None) -> str | None:
    """Return a path relative to the audit HTML output directory, or None."""
    if not path or not path.exists():
        return None
    try:
        rel = os.path.relpath(path, CONFIG.output_path.parent)
        return html.escape(rel)
    except ValueError:
        return None


def gather_files() -> list[dict]:
    entries = []
    if CONFIG.manifest_path and CONFIG.manifest_path.exists():
        try:
            with open(CONFIG.manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            raw_entries = manifest.get("files") or manifest.get("items") or []
            for e in raw_entries:
                rel = e.get("input_rel_path") or e.get("path") or e.get("filename")
                if not rel:
                    continue
                duration_seconds = e.get("duration_seconds")
                if duration_seconds is None:
                    print(f"WARN: manifest entry for {rel} missing duration_seconds; defaulting to 0", file=sys.stderr)
                    duration_seconds = 0
                size_bytes = e.get("size_bytes")
                if size_bytes is None:
                    print(f"WARN: manifest entry for {rel} missing size_bytes; defaulting to 0", file=sys.stderr)
                    size_bytes = 0
                entries.append({
                    "input_rel_path": rel,
                    "filename": e.get("filename", Path(rel).name),
                    "duration_seconds": duration_seconds,
                    "size_bytes": size_bytes,
                })
        except (json.JSONDecodeError, OSError) as e:
            print(f"WARN: failed to parse manifest {CONFIG.manifest_path}: {e}", file=sys.stderr)

    if not entries:
        print(f"INFO: no manifest supplied; discovering files from {CONFIG.csv_dir}", file=sys.stderr)
        seen_stems = set()
        for csv_path in sorted(CONFIG.csv_dir.glob("*.csv")):
            stem = csv_path.stem
            seen_stems.add(stem)
            entries.append({
                "input_rel_path": stem,
                "filename": stem,
                "duration_seconds": 0,
                "size_bytes": 0,
            })
        for diar_path in sorted(CONFIG.diarization_dir.glob("*.diarization.json")):
            stem = diar_path.stem.replace(".diarization", "")
            if stem in seen_stems:
                continue
            seen_stems.add(stem)
            entries.append({
                "input_rel_path": stem,
                "filename": stem,
                "duration_seconds": 0,
                "size_bytes": 0,
            })

    files = []
    for info in entries:
        rel_path = info["input_rel_path"]
        stem = safe_stem(rel_path)
        csv_rows = load_csv_rows(stem)
        txt_content = load_txt_content(stem)
        diarization = load_diarization(stem)

        wav_name = csv_rows[0].get("file", "") if csv_rows else None
        if wav_name:
            wav_name = Path(wav_name).name
        audio_path = _resolve_audio_path(stem, wav_name)

        original_path = None
        if CONFIG.original_dir and rel_path:
            original_path = CONFIG.original_dir / rel_path
            if not original_path.exists():
                original_path = None

        csv_path = CONFIG.csv_dir / f"{stem}.csv"
        txt_path = CONFIG.txt_dir / f"{stem}.txt"
        diar_path = CONFIG.diarization_dir / f"{stem}.diarization.json"
        if not diar_path.exists():
            diar_path = CONFIG.diarization_dir / f"{stem}.json"

        reader_html = render_reader_html(stem, csv_rows)

        speakers = sorted({r["speaker"] for r in csv_rows})
        folder = str(Path(rel_path).parent) if "/" in rel_path else "(根目录)"
        material_type = classify_material(rel_path)
        status = "pending"
        if csv_rows:
            status = "done"
        elif audio_path and audio_path.exists() and diarization:
            status = "processing"

        duration_seconds = info.get("duration_seconds") or 0
        if not duration_seconds and csv_rows:
            duration_seconds = max(r["end"] for r in csv_rows)

        files.append({
            "stem": stem,
            "rel_path": rel_path,
            "filename": info.get("filename", stem),
            "folder": folder,
            "duration_seconds": duration_seconds,
            "duration_formatted": format_time(duration_seconds),
            "size_bytes": info.get("size_bytes", 0),
            "status": status,
            "material_type": material_type,
            "turn_count": len(csv_rows),
            "speaker_count": len(speakers),
            "speakers": speakers,
            "wav_rel_path": rel_to_audit(audio_path),
            "original_rel_path": rel_to_audit(original_path),
            "csv_rel_path": rel_to_audit(csv_path),
            "txt_rel_path": rel_to_audit(txt_path),
            "diarization_rel_path": rel_to_audit(diar_path),
            "rows": csv_rows,
            "txt_content": txt_content,
            "reader_html": reader_html,
            "diarization": diarization,
            "speaker_names": diarization.get("speaker_names", {}),
        })

    return files


def build_folder_tree(files: list[dict]) -> list[dict]:
    """Build nested folder tree with per-folder stats."""
    # Collect all folder paths and ancestor paths
    all_paths: set[str] = set()
    by_folder: dict[str, list[dict]] = {}
    for f in files:
        folder = f.get("folder", "(根目录)")
        by_folder.setdefault(folder, []).append(f)
        all_paths.add(folder)
        # Add ancestors
        if folder != "(根目录)":
            parts = folder.split("/")
            for i in range(1, len(parts)):
                all_paths.add("/".join(parts[:i]))

    nodes: dict[str, dict] = {}

    def make_node(path: str) -> dict:
        if path == "(根目录)":
            name = "(根目录)"
            level = 0
            parent = None
        else:
            parts = path.split("/")
            name = parts[-1]
            level = len(parts) - 1
            parent = "/".join(parts[:-1]) if len(parts) > 1 else "(根目录)"
        return {
            "path": path,
            "name": name,
            "level": level,
            "parent": parent,
            "files": [],
            "children": [],
            "stats": None,
            "expanded": True,
        }

    for path in all_paths:
        nodes[path] = make_node(path)

    # Link parents and children
    for node in nodes.values():
        if node["parent"] and node["parent"] in nodes:
            nodes[node["parent"]]["children"].append(node)

    # Add files to their leaf nodes
    for path, folder_files in by_folder.items():
        if path in nodes:
            nodes[path]["files"] = sorted(folder_files, key=lambda x: x["filename"])

    # Sort children by path
    for node in nodes.values():
        node["children"] = sorted(node["children"], key=lambda x: x["path"])

    # Compute stats recursively (post-order)
    def compute_stats(node: dict) -> dict:
        total = len(node["files"])
        done = sum(1 for f in node["files"] if f["status"] == "done")
        processing = sum(1 for f in node["files"] if f["status"] == "processing")
        pending = sum(1 for f in node["files"] if f["status"] == "pending")
        failed = sum(1 for f in node["files"] if f["status"] == "failed")
        duration = sum(f["duration_seconds"] for f in node["files"])

        for child in node["children"]:
            child_stats = compute_stats(child)
            total += child_stats["total"]
            done += child_stats["done"]
            processing += child_stats["processing"]
            pending += child_stats["pending"]
            failed += child_stats["failed"]
            duration += child_stats["duration_seconds"]

        node["stats"] = {
            "total": total,
            "done": done,
            "processing": processing,
            "pending": pending,
            "failed": failed,
            "duration_seconds": duration,
        }
        return node["stats"]

    roots = [n for n in nodes.values() if n["parent"] is None or n["parent"] not in nodes]
    # Sort roots by path
    roots = sorted(roots, key=lambda x: x["path"])

    for root in roots:
        compute_stats(root)

    return roots


def _json_for_script(obj) -> str:
    """Serialize an object to JSON and escape it so it can safely live inside
    a <script type="application/json"> or inline JS literal without
    terminating the surrounding script tag."""
    s = json.dumps(obj, ensure_ascii=False)
    # re.sub with a callable avoids regex replacement-template interpretation;
    # the literal backslash-escape is preserved as written.
    s = re.sub(r"</script", lambda _m: "<\\/script", s, flags=re.IGNORECASE)
    s = s.replace(" ", "\\u2028").replace(" ", "\\u2029")
    return s


def build_html(files: list[dict]) -> str:
    data = {
        "generated_at": datetime.now().isoformat(),
        "files": files,
        "folders": build_folder_tree(files),
        "total_files": len(files),
        "done_files": sum(1 for f in files if f["status"] == "done"),
        "processing_files": sum(1 for f in files if f["status"] == "processing"),
        "pending_files": sum(1 for f in files if f["status"] == "pending"),
        "failed_files": sum(1 for f in files if f["status"] == "failed"),
        "total_duration_seconds": sum(f["duration_seconds"] for f in files),
    }

    json_data = _json_for_script(data)

    all_speakers = set(SPEAKER_COLORS.keys())
    all_speakers.update(CONFIG.known_speakers.keys())
    for f in files:
        all_speakers.update(f.get("speakers", []))

    def _speaker_color(speaker: str) -> str:
        if speaker in CONFIG.known_speakers:
            return normalize_color(CONFIG.known_speakers[speaker])
        return get_speaker_color_py(speaker)

    speaker_css = "\n".join(_switchable_speaker_css(s, _speaker_color(s)) for s in sorted(all_speakers))
    speaker_color_map = {s: _speaker_color(s) for s in sorted(all_speakers)}
    speaker_color_map_json = _json_for_script(speaker_color_map)

    html_out = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(CONFIG.title)}</title>
<style>
:root {{
  --bg: #f8f9fa;
  --surface: #ffffff;
  --surface-2: #f1f3f5;
  --text: #212529;
  --text-muted: #6c757d;
  --text-secondary: #6c757d;
  --border: #dee2e6;
  --primary: #0d6efd;
  --primary-light: #e7f1ff;
  --success: #198754;
  --success-light: #d1e7dd;
  --warning: #f59e0b;
  --warning-light: #fff3cd;
  --danger: #dc3545;
  --danger-light: #f8d7da;
  --gray: #adb5bd;
  --shadow: 0 1px 3px rgba(0,0,0,0.08);
  --radius: 8px;
  --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "PingFang SC", "Microsoft YaHei", sans-serif;
}}

* {{
  box-sizing: border-box;
}}

body {{
  margin: 0;
  font-family: var(--font);
  background: var(--bg);
  color: var(--text);
  font-size: 14px;
  line-height: 1.5;
}}

.app {{
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}}

header {{
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 12px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-shrink: 0;
}}

.header-title {{
  font-size: 18px;
  font-weight: 600;
  margin: 0;
}}

.header-subtitle {{
  color: var(--text-muted);
  font-size: 12px;
  margin-top: 2px;
}}

.header-stats {{
  display: flex;
  gap: 16px;
  align-items: center;
}}

.stat {{
  text-align: center;
}}

.stat-value {{
  font-size: 18px;
  font-weight: 700;
  line-height: 1;
}}

.stat-label {{
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 3px;
}}

.header-actions {{
  display: flex;
  gap: 8px;
}}

button {{
  font-family: inherit;
  font-size: 13px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  padding: 6px 12px;
  border-radius: var(--radius);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: background 0.15s, border-color 0.15s;
}}

button:hover {{
  background: var(--surface-2);
}}

button.primary {{
  background: var(--primary);
  color: white;
  border-color: var(--primary);
}}

button.primary:hover {{
  background: #0b5ed7;
}}

button.ghost {{
  border-color: transparent;
  background: transparent;
}}

button.danger {{
  color: var(--danger);
  border-color: var(--danger);
}}

button.danger:hover {{
  background: var(--danger-light);
}}

.main {{
  display: flex;
  flex: 1;
  overflow: hidden;
}}

.sidebar {{
  width: 320px;
  min-width: 260px;
  max-width: 420px;
  resize: horizontal;
  overflow: auto;
  background: var(--surface);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
}}

.sidebar-toolbar {{
  padding: 12px;
  border-bottom: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex-shrink: 0;
}}

.search-row {{
  display: flex;
  gap: 8px;
}}

input[type="text"], select {{
  font-family: inherit;
  font-size: 13px;
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  color: var(--text);
  flex: 1;
}}

input[type="range"] {{
  flex: 1;
}}

.filter-row {{
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}}

.filter-chip {{
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: var(--surface);
  cursor: pointer;
  user-select: none;
}}

.filter-chip.active {{
  background: var(--primary);
  color: white;
  border-color: var(--primary);
}}

.file-list {{
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}}

.file-item {{
  padding: 10px 12px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  margin-bottom: 8px;
  cursor: pointer;
  background: var(--surface);
  transition: background 0.15s, border-color 0.15s;
}}

.file-item:hover {{
  background: var(--surface-2);
}}

.file-item.active {{
  border-color: var(--primary);
  background: var(--primary-light);
}}

.file-item.pending {{
  opacity: 0.7;
}}

.file-item.failed {{
  border-left: 4px solid var(--danger);
}}

.file-header {{
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 4px;
}}

.file-name {{
  font-weight: 500;
  word-break: break-all;
  line-height: 1.4;
}}

.file-meta {{
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  color: var(--text-muted);
  flex-wrap: wrap;
}}

.badge {{
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 12px;
  white-space: nowrap;
}}

.badge-done {{
  background: var(--success-light);
  color: var(--success);
}}

.badge-processing {{
  background: var(--warning-light);
  color: #856404;
}}

.badge-pending {{
  background: #e9ecef;
  color: var(--text-muted);
}}

.badge-failed {{
  background: var(--danger-light);
  color: var(--danger);
}}

.badge-issue {{
  background: var(--danger-light);
  color: var(--danger);
}}

.badge.material-final {{
  background: #e7f1ff;
  color: var(--primary);
}}

.badge.material-rough {{
  background: #fff3cd;
  color: #856404;
}}

.badge.material-raw {{
  background: #e9ecef;
  color: var(--text-muted);
}}

.badge.speaker-single {{
  background: #d1e7dd;
  color: var(--success);
}}

.badge.speaker-multi {{
  background: #e7f1ff;
  color: #6f42c1;
}}

.folder-node {{
  margin-bottom: 4px;
}}

.folder-header {{
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  border-radius: var(--radius);
  cursor: pointer;
  user-select: none;
  background: var(--surface-2);
  border: 1px solid var(--border);
  margin-bottom: 2px;
}}

.folder-header:hover {{
  background: #e9ecef;
}}

.folder-header-main {{
  display: flex;
  align-items: center;
  gap: 8px;
}}

.folder-toggle {{
  font-size: 10px;
  color: var(--text-muted);
  width: 12px;
  text-align: center;
}}

.folder-name {{
  font-weight: 600;
  flex: 1;
}}

.folder-count {{
  font-size: 11px;
  color: var(--text-muted);
}}

.folder-duration {{
  font-size: 11px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}}

.folder-progress-wrap {{
  display: flex;
  align-items: center;
  gap: 8px;
}}

.folder-progress-bar {{
  flex: 1;
  height: 6px;
  background: #e9ecef;
  border-radius: 3px;
  overflow: hidden;
}}

.folder-progress-fill {{
  height: 100%;
  background: var(--success);
  border-radius: 3px;
  transition: width 0.2s;
}}

.folder-progress-text {{
  font-size: 11px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
  min-width: 36px;
  text-align: right;
}}

.folder-children,
.folder-files {{
  padding-left: 14px;
  border-left: 1px dashed var(--border);
  margin-left: 6px;
}}

.folder-files .file-item {{
  margin-bottom: 4px;
  padding: 8px 10px;
}}

.folder-files .file-header {{
  flex-direction: column;
  align-items: flex-start;
}}

.file-badges {{
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}}

.collapsed {{
  display: none;
}}

.empty-state-small {{
  padding: 16px;
  color: var(--text-muted);
  text-align: center;
  font-size: 13px;
}}

.content {{
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-width: 0;
}}

.empty-state {{
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  text-align: center;
  padding: 40px;
}}

.empty-state-icon {{
  font-size: 48px;
  margin-bottom: 16px;
  opacity: 0.5;
}}

.viewer {{
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}}

.viewer-header {{
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--surface);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}}

.viewer-title {{
  font-size: 16px;
  font-weight: 600;
  margin: 0 0 8px 0;
  word-break: break-all;
}}

.viewer-meta {{
  display: flex;
  gap: 12px;
  align-items: center;
  font-size: 13px;
  color: var(--text-muted);
  flex-wrap: wrap;
}}

.viewer-body {{
  flex: 1;
  overflow: hidden;
  display: flex;
}}

.transcript-panel {{
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  background: var(--bg);
}}

.side-panel {{
  width: 220px;
  min-width: 200px;
  max-width: 360px;
  resize: horizontal;
  overflow: auto;
  background: var(--surface);
  border-left: 1px solid var(--border);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}}

.panel-section {{
  border-bottom: 1px solid var(--border);
  padding-bottom: 16px;
}}

.panel-section:last-child {{
  border-bottom: none;
  padding-bottom: 0;
}}

.panel-title {{
  font-size: 13px;
  font-weight: 600;
  margin: 0 0 10px 0;
  color: var(--text);
}}

.speaker-list {{
  display: flex;
  flex-direction: column;
  gap: 8px;
}}

.speaker-row {{
  display: flex;
  align-items: center;
  gap: 8px;
}}

.speaker-color {{
  width: 12px;
  height: 12px;
  border-radius: 50%;
  flex-shrink: 0;
}}

.speaker-input {{
  flex: 1;
  min-width: 0;
}}

.audio-player {{
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 12px 16px;
  flex-shrink: 0;
}}

.audio-controls {{
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}}

.audio-time {{
  font-size: 12px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
  min-width: 90px;
  text-align: center;
}}

.timeline {{
  position: relative;
  height: 24px;
  background: var(--surface-2);
  border-radius: 12px;
  cursor: pointer;
  overflow: hidden;
}}

.timeline-progress {{
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  background: var(--primary);
  opacity: 0.3;
  width: 0%;
  pointer-events: none;
}}

.timeline-handle {{
  position: absolute;
  top: 0;
  left: 0%;
  width: 8px;
  height: 100%;
  background: var(--primary);
  border-radius: 4px;
  transform: translateX(-50%);
  pointer-events: none;
}}

.timeline-speaker {{
  position: absolute;
  top: 4px;
  height: 16px;
  border-radius: 3px;
  opacity: 0.6;
  pointer-events: none;
}}

/* Audit state styles shared with reader view */
.note-input {{
  width: 100%;
  margin-top: 8px;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  font-family: inherit;
  font-size: 13px;
  resize: vertical;
  min-height: 60px;
}}

.flag-select {{
  width: 100%;
  margin-top: 8px;
}}

.export-modal {{
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.5);
  display: none;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}}

.export-modal.visible {{
  display: flex;
}}

.export-dialog {{
  background: var(--surface);
  border-radius: var(--radius);
  width: 90%;
  max-width: 600px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 4px 20px rgba(0,0,0,0.15);
}}

.export-header {{
  padding: 16px;
  border-bottom: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
}}

.export-body {{
  padding: 16px;
  overflow: auto;
  flex: 1;
}}

.export-textarea {{
  width: 100%;
  height: 300px;
  font-family: monospace;
  font-size: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 10px;
  resize: none;
}}

.export-footer {{
  padding: 12px 16px;
  border-top: 1px solid var(--border);
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}}

.spacer {{
  flex: 1;
}}

.hidden {{
  display: none !important;
}}

.loading {{
  color: var(--text-muted);
  font-style: italic;
}}

/* Reader view: compact chat-like transcript (from reader_switchable.html) */
.reader-transcript {{
  max-width: 100%;
}}
.turn-group {{
  display: flex;
  align-items: flex-start;
  padding: 5px 0;
  border-bottom: 1px solid #f1f3f5;
}}
.group-meta {{
  width: 90px;
  flex-shrink: 0;
  text-align: right;
  padding-right: 12px;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}}
.avatar {{
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 14px;
  font-weight: 700;
  background-color: #adb5bd;
}}
.speaker-name {{
  font-size: 13px;
  font-weight: 600;
  margin-top: 2px;
  color: #adb5bd;
}}
.group-time {{
  font-size: 11px;
  color: #6c757d;
  margin-top: 1px;
}}
.group-body {{
  flex: 1;
  min-width: 0;
  padding-left: 12px;
  border-left: 5px solid #ced4da;
}}
.turn-group[data-short="1"] {{
  opacity: 0.65;
}}
.turn-group[data-short="1"] .group-body {{
  border-left-width: 2px;
}}
.turn-group[data-short="1"] .segment {{
  font-size: 12px;
  color: #6c757d;
}}
.group-body .segment {{
  position: relative;
  margin: 0 0 4px 0;
  line-height: 1.55;
  padding-right: 70px;
}}
.group-body .segment:last-child {{
  margin-bottom: 0;
}}
.group-body .seg-time {{
  font-size: 11px;
  color: #adb5bd;
  margin-right: 7px;
  font-variant-numeric: tabular-nums;
  cursor: pointer;
}}
.group-body .seg-time:hover {{
  color: var(--primary);
  text-decoration: underline;
}}
.seg-actions {{
  position: absolute;
  right: 0;
  top: 0;
  opacity: 0;
  transition: opacity 0.15s;
  background: rgba(255,255,255,0.9);
  border-radius: 4px;
  padding: 0 4px;
  white-space: nowrap;
}}
.segment:hover .seg-actions {{
  opacity: 1;
}}
.seg-action, .short-action {{
  cursor: pointer;
  margin: 0 3px;
  font-size: 12px;
  user-select: none;
}}
.segment.flagged, .short-tag.flagged {{
  background: var(--danger-light);
  border-radius: 4px;
}}
.segment.current, .short-tag.current {{
  background: var(--primary-light);
}}
.short-run .group-body {{
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
  align-items: baseline;
  padding-top: 4px;
  padding-bottom: 4px;
}}
.short-tag {{
  position: relative;
  font-size: 12px;
  color: #6c757d;
  background: #f1f3f5;
  padding: 2px 8px;
  border-radius: 4px;
}}
.short-tag:hover .short-actions {{
  opacity: 1;
}}
.short-speaker {{
  font-weight: 600;
  margin-right: 5px;
}}
.short-time {{
  color: #adb5bd;
  margin-right: 5px;
  font-variant-numeric: tabular-nums;
  cursor: pointer;
}}
.short-time:hover {{
  color: var(--primary);
  text-decoration: underline;
}}
.short-actions {{
  position: absolute;
  right: 2px;
  top: -18px;
  opacity: 0;
  transition: opacity 0.15s;
  background: rgba(255,255,255,0.9);
  border-radius: 4px;
  padding: 0 2px;
  white-space: nowrap;
  z-index: 2;
}}
.audit-extras {{
  margin: 4px 0 8px 0;
  padding: 8px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}}
.audit-extras .flag-section select {{
  width: 100%;
  margin-bottom: 6px;
}}
.audit-extras .note-preview {{
  padding: 6px 8px;
  background: var(--warning-light);
  border-radius: var(--radius);
  font-size: 13px;
  color: #856404;
  margin-bottom: 6px;
}}
body.reader-hide-short .turn-group[data-short="1"] {{
  display: none;
}}

/* Bubble mode (switchable theme) */
.bubble-mode .turn-group {{
  padding: 8px 0;
  border-bottom: none;
  background: none;
  flex-direction: column;
  align-items: flex-start;
}}
.bubble-mode .group-meta {{
  width: auto;
  padding-right: 0;
  margin-bottom: 4px;
  flex-direction: row;
  align-items: center;
  gap: 6px;
}}
.bubble-mode .avatar {{
  width: 22px;
  height: 22px;
  font-size: 10px;
}}
.bubble-mode .speaker-name {{
  font-size: 11px;
  margin-top: 0;
}}
.bubble-mode .group-body {{
  border-left: none;
}}
.bubble-mode .group-body .segment {{
  color: #fff;
  padding-right: 0;
}}
.bubble-mode .seg-actions {{
  position: static;
  display: inline-block;
  background: rgba(0,0,0,0.15);
  margin-left: 8px;
  border-radius: 4px;
}}
.bubble-mode .seg-action {{
  color: #fff;
}}

/* Transcript controls above short runs */
.transcript-controls {{
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 8px;
}}
.short-toggle {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  cursor: pointer;
  color: var(--text-secondary);
}}
.short-toggle input {{
  cursor: pointer;
}}

body.reader-hide-short .short-toggle {{
  color: var(--text-secondary);
}}

{speaker_css}

@media (max-width: 900px) {{
  .main {{ flex-direction: column; }}
  .sidebar {{ width: 100%; height: 40%; resize: none; max-width: none; }}
  .viewer-body {{ flex-direction: column; }}
  .side-panel {{ width: 100%; height: 200px; resize: none; max-width: none; border-left: none; border-top: 1px solid var(--border); }}
}}
</style>
</head>
<body>
<div class="app">
  <header>
    <div>
      <h1 class="header-title">{html.escape(CONFIG.title)}</h1>
      <div class="header-subtitle">{html.escape(CONFIG.subtitle)}</div>
    </div>
    <div class="header-stats" id="header-stats"></div>
    <div class="header-actions">
      <button class="primary" data-action="exportReport">导出审核报告</button>
      <button data-action="refresh">刷新数据</button>
    </div>
  </header>
  <div class="main">
    <aside class="sidebar">
      <div class="sidebar-toolbar">
        <div class="search-row">
          <input type="text" id="search-input" placeholder="搜索文件名" data-action="filter">
        </div>
        <div class="filter-row" id="filter-row-status">
          <span class="filter-chip active" data-filter-status="all">全部</span>
          <span class="filter-chip" data-filter-status="done">已处理</span>
          <span class="filter-chip" data-filter-status="processing">处理中</span>
          <span class="filter-chip" data-filter-status="pending">待处理</span>
          <span class="filter-chip" data-filter-status="flagged">有标注</span>
        </div>
        <div class="filter-row" id="filter-row-material">
          <span class="filter-chip active" data-filter-material="all">全部类型</span>
          <span class="filter-chip" data-filter-material="成片">成片</span>
          <span class="filter-chip" data-filter-material="粗剪">粗剪</span>
          <span class="filter-chip" data-filter-material="素材">素材</span>
        </div>
        <div class="filter-row" id="filter-row-speaker">
          <span class="filter-chip active" data-filter-speaker="all">全部说话人</span>
          <span class="filter-chip" data-filter-speaker="single">单说话人</span>
          <span class="filter-chip" data-filter-speaker="multi">多说话人</span>
        </div>
      </div>
      <div class="file-list" id="file-list"></div>
    </aside>
    <main class="content" id="content">
      <div class="empty-state">
        <div class="empty-state-icon">🎧</div>
        <div>在左侧选择文件，开始审核转写内容</div>
      </div>
    </main>
  </div>
</div>

<div class="export-modal" id="export-modal">
  <div class="export-dialog">
    <div class="export-header">
      <h3>审核报告 JSON</h3>
      <button class="ghost" data-action="closeExport">关闭</button>
    </div>
    <div class="export-body">
      <textarea class="export-textarea" id="export-textarea" readonly></textarea>
    </div>
    <div class="export-footer">
      <button data-action="copyExport">复制</button>
      <button class="primary" data-action="downloadExport">下载</button>
    </div>
  </div>
</div>

<script id="audit-data" type="application/json">{json_data}</script>
<script>
const EMBEDDED_DATA = JSON.parse(document.getElementById('audit-data').textContent);
const STORAGE_KEY = {json.dumps(CONFIG.storage_key)};

const SPEAKER_COLORS = [
  '#0d6efd', '#198754', '#dc3545', '#f59e0b', '#6f42c1', '#d63384',
  '#0dcaf0', '#6610f2', '#fd7e14', '#20c997', '#e83e8c', '#6c757d'
];

const SPEAKER_COLOR_MAP = {speaker_color_map_json};

function getSpeakerColor(speaker) {{
  if (SPEAKER_COLOR_MAP[speaker]) return SPEAKER_COLOR_MAP[speaker];
  // Stable fallback for any other named speaker not seen during generation.
  let hash = 0;
  for (let i = 0; i < speaker.length; i++) {{
    hash = ((hash << 5) - hash) + speaker.charCodeAt(i);
    hash = hash & 0xFFFFFFFF;
  }}
  return SPEAKER_COLORS[(hash >>> 0) % SPEAKER_COLORS.length];
}}

function cssEscape(value) {{
  if (typeof CSS !== 'undefined' && CSS.escape) return CSS.escape(value);
  return String(value).replace(/([^a-zA-Z0-9_-])/g, '\\$1');
}}

function parseTurnId(turnId) {{
  const sepIdx = turnId.lastIndexOf('::');
  if (sepIdx <= 0) return null;
  return {{
    stem: turnId.slice(0, sepIdx),
    idx: parseInt(turnId.slice(sepIdx + 2), 10)
  }};
}}

function formatTime(seconds) {{
  seconds = Math.max(0, seconds);
  const totalMs = Math.round(seconds * 1000);
  const h = Math.floor(totalMs / 3600000);
  const m = Math.floor((totalMs % 3600000) / 60000);
  const s = Math.floor((totalMs % 60000) / 1000);
  const ms = totalMs % 1000;
  if (h > 0) {{
    return `${{h.toString().padStart(2, '0')}}:${{m.toString().padStart(2, '0')}}:${{s.toString().padStart(2, '0')}}`;
  }}
  return `${{m.toString().padStart(2, '0')}}:${{s.toString().padStart(2, '0')}}.${{ms.toString().padStart(3, '0')}}`;
}}

function formatDurationTotal(seconds) {{
  seconds = Math.max(0, seconds);
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) {{
    return `${{h}}:${{m.toString().padStart(2, '0')}}:${{s.toString().padStart(2, '0')}}`;
  }}
  return `${{m}}:${{s.toString().padStart(2, '0')}}`;
}}

function loadState() {{
  try {{
    const raw = localStorage.getItem(STORAGE_KEY);
    const base = raw ? JSON.parse(raw) : {{}};
    return {{
      aliases: base.aliases || {{}},
      flags: base.flags || {{}},
      notes: base.notes || {{}},
      fileNotes: base.fileNotes || {{}},
      expandedFolders: base.expandedFolders || {{}},
    }};
  }} catch (e) {{
    return {{ aliases: {{}}, flags: {{}}, notes: {{}}, fileNotes: {{}}, expandedFolders: {{}} }};
  }}
}}

function saveState(state) {{
  try {{
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }} catch (e) {{
    console.warn('Failed to save audit state to localStorage:', e);
  }}
}}

class App {{
  constructor() {{
    this.data = EMBEDDED_DATA;
    this.state = loadState();
    this.filterText = '';
    this.filterStatus = 'all';
    this.filterMaterial = 'all';
    this.filterSpeaker = 'all';
    this.readerHideShort = true;
    this.bubbleMode = false;
    this.selectedFile = null;
    this.audio = new Audio();
    this.audio.addEventListener('timeupdate', () => this.onTimeUpdate());
    this.audio.addEventListener('ended', () => this.onAudioEnded());
    this.audio.addEventListener('loadedmetadata', () => this.renderAudioControls());
    this.currentTurnId = null;
    this.playRangeEnd = null;
    this.init();
  }}

  init() {{
    this.renderStats();
    this.renderFileList();
    this.bindFilters();
    this.bindClicks();
    this.bindInputs();
    const urlFile = new URLSearchParams(location.search).get('file');
    if (urlFile && this.data.files.some(f => f.stem === urlFile)) {{
      this.selectFile(urlFile);
    }}
  }}

  bindFilters() {{
    document.querySelectorAll('#filter-row-status .filter-chip').forEach(chip => {{
      chip.addEventListener('click', () => {{
        document.querySelectorAll('#filter-row-status .filter-chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        this.filterStatus = chip.dataset.filterStatus;
        this.renderFileList();
      }});
    }});
    document.querySelectorAll('#filter-row-material .filter-chip').forEach(chip => {{
      chip.addEventListener('click', () => {{
        document.querySelectorAll('#filter-row-material .filter-chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        this.filterMaterial = chip.dataset.filterMaterial;
        this.renderFileList();
      }});
    }});
    document.querySelectorAll('#filter-row-speaker .filter-chip').forEach(chip => {{
      chip.addEventListener('click', () => {{
        document.querySelectorAll('#filter-row-speaker .filter-chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        this.filterSpeaker = chip.dataset.filterSpeaker;
        this.renderFileList();
      }});
    }});
  }}

  bindClicks() {{
    document.addEventListener('click', (e) => {{
      const target = e.target.closest('[data-action]');
      if (!target) return;
      const action = target.dataset.action;
      const stem = target.dataset.stem;
      const turnId = target.dataset.turnId;
      const idx = target.dataset.turnIdx ? parseInt(target.dataset.turnIdx, 10) : null;
      const time = target.dataset.time ? parseFloat(target.dataset.time) : null;

      if (action === 'selectFile') {{
        e.preventDefault();
        this.selectFile(stem);
      }} else if (action === 'toggleFolder') {{
        this.toggleFolder(target.dataset.folder);
      }} else if (action === 'exportReport') {{
        this.exportReport();
      }} else if (action === 'refresh') {{
        this.refresh();
      }} else if (action === 'closeExport') {{
        this.closeExport();
      }} else if (action === 'copyExport') {{
        this.copyExport();
      }} else if (action === 'downloadExport') {{
        this.downloadExport();
      }} else if (action === 'toggleReaderShowShort') {{
        this.readerHideShort = !target.checked;
        document.body.classList.toggle('reader-hide-short', this.readerHideShort);
      }} else if (action === 'toggleBubbleMode') {{
        this.bubbleMode = target.checked;
        document.body.classList.toggle('bubble-mode', this.bubbleMode);
      }} else if (action === 'togglePlay') {{
        this.togglePlay();
      }} else if (action === 'rewind') {{
        this.rewind();
      }} else if (action === 'forward') {{
        this.forward();
      }} else if (action === 'seek') {{
        this.seek(e);
      }} else if (action === 'seekTo') {{
        if (time !== null) this.seekTo(time);
      }} else if (action === 'playTurn') {{
        if (idx !== null) this.playTurn(idx);
      }} else if (action === 'toggleFlag') {{
        this.toggleFlag(turnId);
      }} else if (action === 'toggleNote') {{
        this.toggleNote(turnId);
      }}
    }});
  }}

  bindInputs() {{
    document.addEventListener('input', (e) => {{
      const target = e.target.closest('[data-action]');
      if (!target) return;
      const action = target.dataset.action;
      if (action === 'filter') {{
        this.filter();
      }}
    }});
    document.addEventListener('change', (e) => {{
      const target = e.target.closest('[data-action]');
      if (!target) return;
      const action = target.dataset.action;
      const stem = target.dataset.stem;
      const turnId = target.dataset.turnId;
      const speaker = target.dataset.speaker;
      if (action === 'setRate') {{
        this.setRate(target.value);
      }} else if (action === 'setFlagReason') {{
        this.setFlagReason(turnId, target.value);
      }} else if (action === 'setAlias') {{
        this.setAlias(stem, speaker, target.value);
      }} else if (action === 'setFileNote') {{
        this.setFileNote(stem, target.value);
      }} else if (action === 'setNote') {{
        this.setNote(turnId, target.value);
      }}
    }});
  }}

  filter() {{
    this.filterText = document.getElementById('search-input').value.toLowerCase();
    this.renderFileList();
  }}

  renderStats() {{
    const stats = document.getElementById('header-stats');
    const d = this.data;
    stats.innerHTML = `
      <div class="stat"><div class="stat-value">${{d.total_files}}</div><div class="stat-label">文件总数</div></div>
      <div class="stat"><div class="stat-value">${{d.done_files}}</div><div class="stat-label">已处理</div></div>
      <div class="stat"><div class="stat-value">${{d.processing_files}}</div><div class="stat-label">处理中</div></div>
      <div class="stat"><div class="stat-value">${{d.pending_files}}</div><div class="stat-label">待处理</div></div>
      <div class="stat"><div class="stat-value">${{formatDurationTotal(d.total_duration_seconds)}}</div><div class="stat-label">总时长</div></div>
    `;
  }}

  matchesFilters(f) {{
    if (this.filterStatus === 'done' && f.status !== 'done') return false;
    if (this.filterStatus === 'processing' && f.status !== 'processing') return false;
    if (this.filterStatus === 'pending' && f.status !== 'pending') return false;
    if (this.filterStatus === 'flagged') {{
      const flagged = Object.keys(this.state.flags).some(key => key.startsWith(f.stem + '::'));
      if (!flagged) return false;
    }}
    if (this.filterMaterial !== 'all' && f.material_type !== this.filterMaterial) return false;
    if (this.filterSpeaker === 'single' && f.speaker_count !== 1) return false;
    if (this.filterSpeaker === 'multi' && f.speaker_count <= 1) return false;
    if (this.filterText) {{
      const text = (f.filename + ' ' + f.rel_path + ' ' + f.material_type).toLowerCase();
      if (!text.includes(this.filterText)) return false;
    }}
    return true;
  }}

  issueCount(stem) {{
    return Object.keys(this.state.flags).filter(k => k.startsWith(stem + '::')).length;
  }}

  speakerLabel(f) {{
    if (!f.speakers || f.speakers.length === 0) return '未识别';
    const display = f.speakers.slice(0, 3).join(' · ');
    return f.speakers.length > 3 ? `${{display}}…` : display;
  }}

  renderFileList() {{
    const list = document.getElementById('file-list');
    if (!this.data.folders || !this.data.folders.length) {{
      list.innerHTML = '<div class="empty-state-small">暂无文件</div>';
      return;
    }}
    list.innerHTML = this.data.folders.map(node => this.renderFolder(node)).join('');
  }}

  renderFolder(node) {{
    const folderExpanded = this.state.expandedFolders[node.path] !== false;
    const matchingFiles = node.files.filter(f => this.matchesFilters(f));
    const matchingChildren = node.children.map(child => this.renderFolder(child)).filter(s => s.trim());
    const hasMatch = matchingFiles.length > 0 || matchingChildren.length > 0;
    if (!hasMatch && !this.filterText && this.filterStatus === 'all' && this.filterMaterial === 'all' && this.filterSpeaker === 'all') {{
      // show empty folders too when no filters
    }} else if (!hasMatch) {{
      return '';
    }}

    const stats = node.stats || {{ total: 0, done: 0, processing: 0, pending: 0, failed: 0 }};
    const progress = stats.total ? Math.round((stats.done / stats.total) * 100) : 0;
    const duration = formatDurationTotal(stats.duration_seconds);

    const childrenHtml = matchingChildren.length ? `<div class="folder-children ${{folderExpanded ? '' : 'collapsed'}}">${{matchingChildren.join('')}}</div>` : '';
    const filesHtml = matchingFiles.length ? `<div class="folder-files ${{folderExpanded ? '' : 'collapsed'}}">${{matchingFiles.map(f => this.renderFileItem(f)).join('')}}</div>` : '';

    const toggleIcon = folderExpanded ? '▼' : '▶';
    const fileCount = stats.total === 1 ? '1 个文件' : `${{stats.total}} 个文件`;

    return `
      <div class="folder-node" data-folder="${{this.escapeHtml(node.path)}}">
        <div class="folder-header ${{node.level > 0 ? 'folder-level-' + node.level : ''}}" data-action="toggleFolder" data-folder="${{this.escapeHtml(node.path)}}">
          <div class="folder-header-main">
            <span class="folder-toggle">${{toggleIcon}}</span>
            <span class="folder-name">${{this.escapeHtml(node.name)}}</span>
            <span class="folder-count">${{fileCount}}</span>
            <span class="folder-duration">${{duration}}</span>
          </div>
          <div class="folder-progress-wrap">
            <div class="folder-progress-bar">
              <div class="folder-progress-fill" style="width:${{progress}}%"></div>
            </div>
            <span class="folder-progress-text">${{stats.done}}/${{stats.total}}</span>
          </div>
        </div>
        ${{childrenHtml}}
        ${{filesHtml}}
      </div>
    `;
  }}

  renderFileItem(f) {{
    const issueCount = this.issueCount(f.stem);
    const materialClass = f.material_type === '成片' ? 'material-final' : (f.material_type === '粗剪' ? 'material-rough' : 'material-raw');
    const speakerClass = f.speaker_count === 1 ? 'speaker-single' : 'speaker-multi';
    return `
      <div class="file-item ${{this.selectedFile === f.stem ? 'active' : ''}} ${{f.status}}" data-action="selectFile" data-stem="${{this.escapeHtml(f.stem)}}">
        <div class="file-header">
          <div class="file-name">${{this.escapeHtml(f.filename)}}</div>
          <div class="file-badges">
            <span class="badge badge-${{f.status}}">${{this.statusLabel(f.status)}}</span>
            <span class="badge ${{materialClass}}">${{f.material_type}}</span>
            <span class="badge ${{speakerClass}}">${{this.speakerLabel(f)}}</span>
            ${{issueCount ? `<span class="badge badge-issue">${{issueCount}} 标注</span>` : ''}}
          </div>
        </div>
        <div class="file-meta">
          <span>${{f.duration_formatted}}</span>
          <span>${{f.turn_count}} 轮</span>
        </div>
      </div>
    `;
  }}

  toggleFolder(path) {{
    this.state.expandedFolders[path] = !(this.state.expandedFolders[path] !== false);
    saveState(this.state);
    this.renderFileList();
  }}

  statusLabel(status) {{
    return {{ done: '已处理', processing: '处理中', pending: '待处理', failed: '失败' }}[status] || status;
  }}

  selectFile(stem) {{
    this.selectedFile = stem;
    const file = this.data.files.find(f => f.stem === stem);
    if (!file) return;
    this.renderFileList();
    this.renderViewer(file);
    this.loadAudio(file);
  }}

  renderViewer(file) {{
    const content = document.getElementById('content');
    const aliases = this.state.aliases[file.stem] || {{}};
    const fileNotes = this.state.fileNotes[file.stem] || '';
    const hasAudio = !!file.wav_rel_path;

    content.innerHTML = `
      <div class="viewer">
        <div class="viewer-header">
          <div>
            <div class="viewer-title">${{this.escapeHtml(file.filename)}}</div>
            <div class="viewer-meta">
              <span>时长：${{file.duration_formatted}}</span>
              <span>轮次：${{file.turn_count}}</span>
              <span>说话人：${{file.speaker_count}}</span>
              ${{file.original_rel_path ? `<a href="${{file.original_rel_path}}" target="_blank">打开原始文件</a>` : ''}}
              ${{file.csv_rel_path ? `<a href="${{file.csv_rel_path}}" target="_blank">CSV</a>` : ''}}
              ${{file.txt_rel_path ? `<a href="${{file.txt_rel_path}}" target="_blank">TXT</a>` : ''}}
            </div>
          </div>
        </div>
        ${{hasAudio ? `
        <div class="audio-player">
          <div class="audio-controls">
            <button data-action="togglePlay" id="play-btn">▶ 播放</button>
            <button data-action="rewind">-5s</button>
            <button data-action="forward">+5s</button>
            <div class="spacer"></div>
            <span class="audio-time" id="audio-time">00:00.000 / 00:00.000</span>
            <div class="spacer"></div>
            <label>速率</label>
            <select data-action="setRate">
              <option value="0.5">0.5x</option>
              <option value="0.8">0.8x</option>
              <option value="1.0" selected>1.0x</option>
              <option value="1.2">1.2x</option>
              <option value="1.5">1.5x</option>
            </select>
          </div>
          <div class="timeline" id="timeline" data-action="seek">
            <div class="timeline-progress" id="timeline-progress"></div>
            <div class="timeline-handle" id="timeline-handle"></div>
            <div id="timeline-speakers"></div>
          </div>
        </div>
        ` : `
        <div class="audio-player" style="padding:12px 16px;color:var(--text-muted);font-size:13px;">
          未找到音频文件，仅可审阅转写文本。
        </div>
        `}}
        <div class="viewer-body">
          <div class="transcript-panel" id="transcript-panel">
            <div class="transcript-controls">
              <label class="short-toggle">
                <input type="checkbox" data-action="toggleReaderShowShort" ${{this.readerHideShort ? '' : 'checked'}}>
                显示短回应
              </label>
              <label class="short-toggle">
                <input type="checkbox" data-action="toggleBubbleMode" ${{this.bubbleMode ? 'checked' : ''}}>
                气泡模式
              </label>
            </div>
            ${{file.rows.length ? file.reader_html : '<div class="empty-state"><div class="empty-state-icon">📝</div><div>无转写数据</div></div>'}}
          </div>
          <div class="side-panel">
            <div class="panel-section">
              <div class="panel-title">说话人映射</div>
              <div class="speaker-list">
                ${{file.speakers.map(s => `
                  <div class="speaker-row">
                    <div class="speaker-color" style="background:${{getSpeakerColor(s)}}"></div>
                    <input class="speaker-input" type="text" value="${{this.escapeHtml(aliases[s] || '')}}" placeholder="${{this.escapeHtml(s)}}" data-action="setAlias" data-stem="${{this.escapeHtml(file.stem)}}" data-speaker="${{this.escapeHtml(s)}}">
                  </div>
                `).join('')}}
              </div>
            </div>
            ${{Object.keys(file.speaker_names || {{}}).length ? `
            <div class="panel-section">
              <div class="panel-title">声纹识别映射</div>
              <div class="speaker-list">
                ${{Object.entries(file.speaker_names).map(([orig, name]) => `
                  <div class="speaker-row">
                    <div class="speaker-color" style="background:${{getSpeakerColor(name)}}"></div>
                    <div style="font-size:13px;flex:1;">${{this.escapeHtml(orig)}} → ${{this.escapeHtml(name)}}</div>
                  </div>
                `).join('')}}
              </div>
            </div>
            ` : ''}}
            <div class="panel-section">
              <div class="panel-title">文件备注</div>
              <textarea class="note-input" placeholder="整文件备注…" data-action="setFileNote" data-stem="${{this.escapeHtml(file.stem)}}">${{this.escapeHtml(fileNotes)}}</textarea>
            </div>
            <div class="panel-section">
              <div class="panel-title">快捷键</div>
              <div style="font-size:12px;color:var(--text-muted);line-height:1.8;">
                空格：播放/暂停<br>
                ← / →：快退/快进 5s<br>
                点击时间戳：跳转<br>
                点击播放按钮：播放该句
              </div>
            </div>
          </div>
        </div>
      </div>
    `;

    this.renderTimelineSpeakers(file);
    this.applyTranscriptState(file);
  }}

  applyTranscriptState(file) {{
    const aliases = this.state.aliases[file.stem] || {{}};
    // Apply aliases to speaker names
    document.querySelectorAll('[data-speaker]').forEach(el => {{
      const speaker = el.dataset.speaker;
      const alias = aliases[speaker] || speaker;
      if (el.classList.contains('speaker-name') || el.classList.contains('short-speaker')) {{
        el.textContent = alias;
      }}
    }});

    // Apply flags and notes to each segment/short-tag
    document.querySelectorAll('.segment, .short-tag').forEach(el => {{
      el.classList.remove('flagged');
      const turnId = el.dataset.turnId;
      const extras = document.getElementById(`audit-extras-${{turnId}}`);
      if (extras) {{
        extras.classList.add('hidden');
        const flagSelect = extras.querySelector('select');
        const notePreview = extras.querySelector('.note-preview');
        const noteTextarea = extras.querySelector('textarea');
        if (flagSelect) flagSelect.value = '';
        if (notePreview) {{
          notePreview.textContent = '';
          notePreview.classList.add('hidden');
        }}
        if (noteTextarea) noteTextarea.value = '';
      }}
    }});

    for (const [turnId, reason] of Object.entries(this.state.flags)) {{
      if (!turnId.startsWith(file.stem + '::')) continue;
      const escapedId = cssEscape(turnId);
      const el = document.querySelector(`.segment[data-turn-id="${{escapedId}}"], .short-tag[data-turn-id="${{escapedId}}"]`);
      if (el) el.classList.add('flagged');
      const extras = document.getElementById(`audit-extras-${{turnId}}`);
      if (extras) {{
        extras.classList.remove('hidden');
        const select = extras.querySelector('select');
        if (select) select.value = reason;
      }}
    }}
    for (const [turnId, note] of Object.entries(this.state.notes)) {{
      if (!turnId.startsWith(file.stem + '::')) continue;
      const extras = document.getElementById(`audit-extras-${{turnId}}`);
      if (extras) {{
        extras.classList.remove('hidden');
        const preview = extras.querySelector('.note-preview');
        const textarea = extras.querySelector('textarea');
        if (preview) {{
          preview.textContent = note;
          preview.classList.remove('hidden');
        }}
        if (textarea) textarea.value = note;
      }}
    }}

    // Apply body toggles
    document.body.classList.toggle('reader-hide-short', this.readerHideShort);
    document.body.classList.toggle('bubble-mode', this.bubbleMode);
  }}

  renderTimelineSpeakers(file) {{
    const container = document.getElementById('timeline-speakers');
    if (!container) return;
    const duration = file.duration_seconds > 0 ? file.duration_seconds : 1;
    container.innerHTML = file.rows.map(row => {{
      const left = (row.start / duration) * 100;
      const width = ((row.end - row.start) / duration) * 100;
      const color = getSpeakerColor(row.speaker);
      return `<div class="timeline-speaker" style="left:${{left}}%;width:${{width}}%;background:${{color}}"></div>`;
    }}).join('');
  }}

  loadAudio(file) {{
    if (file.wav_rel_path) {{
      this.audio.src = file.wav_rel_path;
      this.audio.load();
    }}
  }}

  togglePlay() {{
    if (this.audio.paused) {{
      this.audio.play();
    }} else {{
      this.audio.pause();
    }}
  }}

  rewind() {{
    this.audio.currentTime = Math.max(0, this.audio.currentTime - 5);
  }}

  forward() {{
    this.audio.currentTime = Math.min(this.audio.duration || Infinity, this.audio.currentTime + 5);
  }}

  setRate(rate) {{
    this.audio.playbackRate = parseFloat(rate);
  }}

  seekTo(seconds) {{
    if (this.audio && this.audio.src) {{
      this.audio.currentTime = seconds;
      this.audio.play();
    }}
  }}

  seek(event) {{
    const timeline = document.getElementById('timeline');
    const rect = timeline.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
    if (this.audio.duration) {{
      this.audio.currentTime = ratio * this.audio.duration;
    }}
  }}

  playTurn(idx) {{
    const file = this.data.files.find(f => f.stem === this.selectedFile);
    if (!file || !file.rows[idx]) return;
    const row = file.rows[idx];
    this.playRangeEnd = row.end;
    this.audio.currentTime = row.start;
    this.audio.play();
  }}

  onTimeUpdate() {{
    const current = this.audio.currentTime;
    const duration = this.audio.duration || 0;
    const timeEl = document.getElementById('audio-time');
    if (timeEl) {{
      timeEl.textContent = `${{formatTime(current)}} / ${{formatTime(duration)}}`;
    }}

    const progress = document.getElementById('timeline-progress');
    const handle = document.getElementById('timeline-handle');
    if (progress && duration) {{
      const ratio = (current / duration) * 100;
      progress.style.width = `${{ratio}}%`;
      handle.style.left = `${{ratio}}%`;
    }}

    if (this.playRangeEnd && current >= this.playRangeEnd) {{
      this.audio.pause();
      this.playRangeEnd = null;
    }}

    this.highlightTurn(current);
  }}

  onAudioEnded() {{
    this.playRangeEnd = null;
  }}

  highlightTurn(currentTime) {{
    const file = this.data.files.find(f => f.stem === this.selectedFile);
    if (!file) return;
    const idx = file.rows.findIndex(r => r.start <= currentTime && r.end >= currentTime);
    if (idx === -1 || idx === this.currentTurnId) return;
    this.currentTurnId = idx;

    document.querySelectorAll('.segment.current, .short-tag.current').forEach(el => el.classList.remove('current'));
    const el = document.querySelector(`.segment[data-turn-idx="${{idx}}"], .short-tag[data-turn-idx="${{idx}}"]`);
    if (el) {{
      el.classList.add('current');
      el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
    }}
  }}

  renderAudioControls() {{
    const btn = document.getElementById('play-btn');
    if (!btn) return;
    btn.textContent = this.audio.paused ? '▶ 播放' : '⏸ 暂停';
  }}

  toggleFlag(turnId) {{
    if (this.state.flags[turnId]) {{
      delete this.state.flags[turnId];
    }} else {{
      this.state.flags[turnId] = 'other';
    }}
    saveState(this.state);
    this.renderFileList();
    const file = this.data.files.find(f => f.stem === this.selectedFile);
    if (file) this.applyTranscriptState(file);
  }}

  setFlagReason(turnId, reason) {{
    if (!reason) {{
      delete this.state.flags[turnId];
    }} else {{
      this.state.flags[turnId] = reason;
    }}
    saveState(this.state);
    this.renderFileList();
    const file = this.data.files.find(f => f.stem === this.selectedFile);
    if (file) this.applyTranscriptState(file);
  }}

  toggleNote(turnId) {{
    const extras = document.getElementById(`audit-extras-${{turnId}}`);
    if (!extras) return;
    extras.classList.remove('hidden');
    const noteSection = extras.querySelector('.note-section');
    if (noteSection) {{
      noteSection.classList.toggle('hidden');
      const textarea = noteSection.querySelector('textarea');
      if (!noteSection.classList.contains('hidden') && textarea) {{
        textarea.focus();
      }}
    }}
    // If hiding and no note or flag, collapse audit-extras
    if (noteSection.classList.contains('hidden') && !this.state.flags[turnId] && !this.state.notes[turnId]) {{
      extras.classList.add('hidden');
    }}
  }}

  setNote(turnId, value) {{
    const trimmed = value.trim();
    if (trimmed) {{
      this.state.notes[turnId] = trimmed;
    }} else {{
      delete this.state.notes[turnId];
    }}
    saveState(this.state);
    const file = this.data.files.find(f => f.stem === this.selectedFile);
    if (file) this.applyTranscriptState(file);
  }}

  setAlias(stem, speaker, value) {{
    if (!this.state.aliases[stem]) this.state.aliases[stem] = {{}};
    if (value.trim()) {{
      this.state.aliases[stem][speaker] = value.trim();
    }} else {{
      delete this.state.aliases[stem][speaker];
    }}
    saveState(this.state);
    const file = this.data.files.find(f => f.stem === stem);
    if (file && this.selectedFile === stem) {{
      this.applyTranscriptState(file);
    }}
  }}

  setFileNote(stem, value) {{
    if (value.trim()) {{
      this.state.fileNotes[stem] = value.trim();
    }} else {{
      delete this.state.fileNotes[stem];
    }}
    saveState(this.state);
  }}

  exportReport() {{
    const report = {{
      generated_at: new Date().toISOString(),
      data_generated_at: this.data.generated_at,
      total_files: this.data.total_files,
      state: this.state,
      flagged_turns: []
    }};
    for (const [turnId, reason] of Object.entries(this.state.flags)) {{
      const parsed = parseTurnId(turnId);
      if (!parsed) continue;
      const {{ stem, idx }} = parsed;
      const file = this.data.files.find(f => f.stem === stem);
      const row = file ? file.rows[idx] : null;
      if (row) {{
        report.flagged_turns.push({{
          file: file.filename,
          rel_path: file.rel_path,
          stem: stem,
          turn_index: idx,
          start: row.start,
          end: row.end,
          speaker: row.speaker,
          speaker_alias: (this.state.aliases[stem] || {{}})[row.speaker] || row.speaker,
          text: row.text,
          reason: reason,
          note: this.state.notes[turnId] || ''
        }});
      }}
    }}
    const json = JSON.stringify(report, null, 2);
    document.getElementById('export-textarea').value = json;
    document.getElementById('export-modal').classList.add('visible');
  }}

  closeExport() {{
    document.getElementById('export-modal').classList.remove('visible');
  }}

  copyExport() {{
    const textarea = document.getElementById('export-textarea');
    textarea.select();
    document.execCommand('copy');
  }}

  downloadExport() {{
    const json = document.getElementById('export-textarea').value;
    const blob = new Blob([json], {{ type: 'application/json' }});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `asr-audit-report-${{new Date().toISOString().slice(0,19).replace(/:/g,'-')}}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }}

  refresh() {{
    location.reload();
  }}

  escapeHtml(text) {{
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }}
}}

const app = new App();

window.addEventListener('keydown', e => {{
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
  if (e.code === 'Space') {{
    e.preventDefault();
    app.togglePlay();
  }} else if (e.code === 'ArrowLeft') {{
    app.rewind();
  }} else if (e.code === 'ArrowRight') {{
    app.forward();
  }}
}});
</script>
</body>
</html>
"""
    return html_out


def main():
    ap = argparse.ArgumentParser(description="Generate self-contained HTML audit page for ASR transcripts")
    ap.add_argument("project_dir", type=Path, help="Directory containing CSV/TXT/diarization outputs")
    ap.add_argument("--output", type=Path, default=None, help="HTML output path (default: PROJECT_DIR/audit/index.html)")
    ap.add_argument("--csv-dir", type=Path, default=None, help="Directory containing CSV files (default: PROJECT_DIR)")
    ap.add_argument("--txt-dir", type=Path, default=None, help="Directory containing TXT files (default: PROJECT_DIR)")
    ap.add_argument("--diarization-dir", type=Path, default=None, help="Directory containing diarization JSON files (default: PROJECT_DIR)")
    ap.add_argument("--audio-dir", type=Path, default=None, help="Directory containing audio files (default: PROJECT_DIR)")
    ap.add_argument("--original-dir", type=Path, default=None, help="Directory containing original media (optional)")
    ap.add_argument("--manifest", type=Path, default=None, help="Optional JSON manifest with file metadata")
    ap.add_argument("--title", default="ASR 转写审核", help="Page title")
    ap.add_argument("--subtitle", default="Qwen3-ASR + pyannote 说话人分割 · 本地审核", help="Page subtitle")
    ap.add_argument("--storage-key", default=None, help="localStorage key prefix")
    ap.add_argument("--known-speaker", action="append", default=[], help='Known speaker color mapping, e.g. "张三=#0d6efd" or just "张三" (auto-color)')
    ap.add_argument("--material-final", action="append", default=[], help="Folder-name keywords treated as 成片")
    ap.add_argument("--material-rough", action="append", default=[], help="Folder-name keywords treated as 粗剪")
    args = ap.parse_args()

    known_speakers = {}
    fallback_idx = 0
    for mapping in args.known_speaker:
        if "=" in mapping:
            name, color = mapping.split("=", 1)
        else:
            name = mapping
            color = FALLBACK_PALETTE[fallback_idx % len(FALLBACK_PALETTE)]
            fallback_idx += 1
        name = name.strip()
        if not name:
            continue
        known_speakers[name] = normalize_color(color.strip())

    storage_key = args.storage_key or f"asr-audit-{args.project_dir.name.replace(' ', '_')[:20]}-v1"

    global CONFIG
    CONFIG = Config(
        project_dir=args.project_dir,
        output_path=args.output,
        csv_dir=args.csv_dir,
        txt_dir=args.txt_dir,
        diarization_dir=args.diarization_dir,
        audio_dir=args.audio_dir,
        original_dir=args.original_dir,
        manifest_path=args.manifest,
        title=args.title,
        subtitle=args.subtitle,
        storage_key=storage_key,
        material_final=args.material_final,
        material_rough=args.material_rough,
        known_speakers=known_speakers,
    )

    files = gather_files()
    html_out = build_html(files)
    CONFIG.output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG.output_path, "w", encoding="utf-8") as f:
        f.write(html_out)
    print(f"Generated: {CONFIG.output_path}")
    print(f"Files: {len(files)} (done={sum(1 for f in files if f['status'] == 'done')}, "
          f"processing={sum(1 for f in files if f['status'] == 'processing')}, "
          f"pending={sum(1 for f in files if f['status'] == 'pending')})")


if __name__ == "__main__":
    main()
