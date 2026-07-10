#!/usr/bin/env python3
"""
Mine local Claude Code / Codex conversation histories for reusable skill references.

Deterministic phases:
  1. Discover sources from a manifest.
  2. Parse role=user / role=assistant messages.
  3. Drop system-injection noise.
  4. Redact secrets, tokens, emails, and user paths.
  5. Score relevance against a topic spec.
  6. Partition into token-sized chunks.
  7. Emit reproducible artifacts under <target-skill>/.enrich/<timestamp>/.

This script does NOT run the LLM mining agents. It prepares the redacted, chunked
materials that the agents consume. See workflows/conversation-mining/ for the
full orchestration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

# Allow script to be run as `python -m scripts.mine_conversation` or directly.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from utils import parse_skill_md  # noqa: E402


# ---------------------------------------------------------------------------
# Token counting
# ---------------------------------------------------------------------------

def get_token_counter(encoding_model: str):
    """Return a function that counts tokens in a string.

    Fail closed if tiktoken or the requested encoding is unavailable.
    """
    try:
        import tiktoken
    except ImportError as exc:
        raise RuntimeError(
            "tiktoken is required for deterministic conversation chunking; "
            "run with `uv run --with tiktoken ...`"
        ) from exc
    enc = tiktoken.get_encoding(encoding_model)
    return lambda text: len(enc.encode(text))


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

DEFAULT_REDACTION_PATTERNS = [
    {
        "id": "llm_provider_keys",
        "pattern": r"(?:sk-or-|sk-ant-|sk-kimi-|sk-proj-|sk-svcacct-|sk-)[A-Za-z0-9_-]+",
        "placeholder": "<REDACTED-key>",
    },
    {
        "id": "bearer_tokens",
        "pattern": r"Bearer\s+([A-Za-z0-9_\-.]+)",
        "allowlist_group": 1,
        "placeholder": "Bearer <REDACTED-token>",
    },
    {
        "id": "authorization_header",
        "pattern": r"((?i:Authorization):\s*)([A-Za-z0-9_\-.]+)",
        "allowlist_group": 2,
        "placeholder": r"\1<REDACTED-token>",
    },
    {
        "id": "key_value_tokens",
        "pattern": r"((?i:access[_-]?token|api[_-]?key|token)\s*[:=]\s*)([A-Za-z0-9_\-.]+)",
        "allowlist_group": 2,
        "placeholder": r"\1<REDACTED-token>",
    },
    {
        "id": "email_addresses",
        "pattern": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        "placeholder": "<REDACTED-email>",
    },
    {
        "id": "chinese_mobile_numbers",
        "pattern": r"\b1[3-9]\d{9}\b",
        "placeholder": "<REDACTED-phone>",
    },
    {
        "id": "macos_user_paths",
        "pattern": r"/Users/[A-Za-z][A-Za-z0-9_-]+/[^\s,;\"'\)]*",
        "placeholder": "/Users/<REDACTED-USER>/...",
    },
    {
        "id": "linux_user_paths",
        "pattern": r"/home/[A-Za-z][A-Za-z0-9_-]+/[^\s,;\"'\)]*",
        "placeholder": "/home/<REDACTED-USER>/...",
    },
    {
        "id": "windows_user_paths",
        "pattern": r"C:\\Users\\[A-Za-z][A-Za-z0-9_-]+\\[^\s,;\"'\)]*",
        "placeholder": "C:\\Users\\<REDACTED-USER>\\...",
    },
]


class Redactor:
    """Stateful redactor that applies patterns and tracks counts."""

    def __init__(self, allowlist: Optional[Iterable[str]] = None, extra_patterns: Optional[list] = None):
        self.exact_allowlist: set[str] = set()
        self.prefix_allowlist: set[str] = set()
        for raw_value in allowlist or []:
            if not isinstance(raw_value, str) or not raw_value:
                raise ValueError("redaction allowlist entries must be non-empty strings")
            value = raw_value.lower()
            if "*" not in value:
                self.exact_allowlist.add(value)
                continue
            if value == "*" or value.count("*") != 1 or not value.endswith("*"):
                raise ValueError(
                    "redaction allowlist wildcard is allowed only once at the end of a non-empty prefix"
                )
            self.prefix_allowlist.add(value[:-1])
        self.patterns = list(DEFAULT_REDACTION_PATTERNS)
        if extra_patterns:
            self.patterns.extend(extra_patterns)
        self.counts: Counter = Counter()
        self.by_file: dict[str, Counter] = defaultdict(Counter)

    def _is_allowlisted(self, value: str) -> bool:
        lower = value.lower()
        return lower in self.exact_allowlist or any(
            lower.startswith(prefix) for prefix in self.prefix_allowlist
        )

    def redact(self, text: str, source_hint: str = "") -> str:
        """Apply redaction patterns. Returns redacted text."""
        result = text
        for rule in self.patterns:
            regex = re.compile(rule["pattern"])
            placeholder = rule["placeholder"]

            def _repl(match: re.Match) -> str:
                matched = match.group(0)
                allowlist_value = match.group(rule.get("allowlist_group", 0))
                if self._is_allowlisted(allowlist_value):
                    return matched
                self.counts[rule["id"]] += 1
                if source_hint:
                    self.by_file[source_hint][rule["id"]] += 1
                return match.expand(placeholder)

            result = regex.sub(_repl, result)
        return result

    def report(self) -> dict[str, Any]:
        return {
            "total_replacements": sum(self.counts.values()),
            "by_pattern": dict(self.counts),
            "by_file": {k: dict(v) for k, v in self.by_file.items()},
        }


# ---------------------------------------------------------------------------
# Message parsing
# ---------------------------------------------------------------------------

def _extract_text_from_message(message: Any) -> str:
    """Extract plain text from a Claude/Codex message object."""
    if isinstance(message, str):
        return message
    if not isinstance(message, dict):
        return ""

    content = message.get("content", "")
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "thinking":
                    # thinking blocks are useful for debugging reasoning but can be
                    # very long; include them truncated later via chunk budget.
                    parts.append(block.get("thinking", ""))
                elif block.get("type") == "tool_result":
                    # Tool results can be enormous. Keep only a short prefix.
                    output = block.get("output") or block.get("content") or ""
                    if isinstance(output, str):
                        parts.append(output[:2000])
                    elif isinstance(output, list):
                        parts.append(json.dumps(output, ensure_ascii=False)[:2000])
        return "\n".join(parts)

    return ""


def _parse_iso_timestamp(ts: Any) -> Optional[str]:
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        # ms or s? Treat > 1e11 as ms.
        if ts > 1e11:
            dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        else:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.isoformat()
    if isinstance(ts, str):
        try:
            # Try parsing ISO format
            if ts.endswith("Z"):
                ts = ts[:-1] + "+00:00"
            return datetime.fromisoformat(ts).isoformat()
        except (TypeError, ValueError):
            return None
    return None


def _parse_claude_project_jsonl(path: Path) -> Iterator[dict]:
    """Parse a Claude Code project session JSONL file."""
    text = path.read_text(encoding="utf-8", errors="replace")
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue

        msg_type = record.get("type")
        if msg_type not in ("user", "assistant"):
            continue

        message = record.get("message") or {}
        if not isinstance(message, dict):
            continue

        role = message.get("role")
        if role not in ("user", "assistant"):
            continue

        text = _extract_text_from_message(message)
        if not text.strip():
            continue

        yield {
            "role": role,
            "timestamp": _parse_iso_timestamp(record.get("timestamp")) or _parse_iso_timestamp(message.get("timestamp")),
            "text": text,
            "source_line": line_no,
        }


def _parse_claude_command_history_jsonl(path: Path) -> Iterator[dict]:
    """Parse ~/.claude/history.jsonl — each line is a user prompt."""
    text = path.read_text(encoding="utf-8", errors="replace")
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue

        display = record.get("display", "")
        if not isinstance(display, str) or not display.strip():
            continue

        yield {
            "role": "user",
            "timestamp": _parse_iso_timestamp(record.get("timestamp")),
            "text": display,
            "source_line": line_no,
        }


def _parse_codex_transcription_jsonl(path: Path) -> Iterator[dict]:
    """Parse ~/.codex/transcription-history.jsonl — each line is a user text."""
    text = path.read_text(encoding="utf-8", errors="replace")
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue

        text = record.get("text", "")
        if not isinstance(text, str) or not text.strip():
            continue

        yield {
            "role": "user",
            "timestamp": _parse_iso_timestamp(record.get("createdAtMs")),
            "text": text,
            "source_line": line_no,
        }


def _parse_codex_history_jsonl(path: Path) -> Iterator[dict]:
    """Parse ~/.codex/history.jsonl — each line is a user prompt with session_id/ts/text."""
    text = path.read_text(encoding="utf-8", errors="replace")
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue

        text = record.get("text", "")
        if not isinstance(text, str) or not text.strip():
            continue

        yield {
            "role": "user",
            "timestamp": _parse_iso_timestamp(record.get("ts")),
            "text": text,
            "source_line": line_no,
        }


def _parse_manual_export(path: Path) -> Iterator[dict]:
    """Best-effort parser for a user-provided JSONL or text file."""
    if path.suffix == ".jsonl":
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_no, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                # Treat non-JSON lines as plain text user messages.
                record = {"text": line}
            if not isinstance(record, dict):
                continue

            text_value = record.get("text", "")
            if isinstance(record, dict):
                for key in ("content", "display", "message"):
                    if key in record and isinstance(record[key], str):
                        text_value = record[key]
                        break
            if not isinstance(text_value, str) or not text_value.strip():
                continue
            yield {
                "role": record.get("role", "user"),
                "timestamp": _parse_iso_timestamp(record.get("timestamp") or record.get("ts") or record.get("createdAtMs")),
                "text": text_value,
                "source_line": line_no,
            }
    else:
        # Plain text: one message per paragraph, all user.
        text = path.read_text(encoding="utf-8", errors="replace")
        for idx, paragraph in enumerate(text.split("\n\n"), start=1):
            if paragraph.strip():
                yield {
                    "role": "user",
                    "timestamp": None,
                    "text": paragraph.strip(),
                    "source_line": idx,
                }


# ---------------------------------------------------------------------------
# Source discovery
# ---------------------------------------------------------------------------

def _expand_path(value: str, manifest_dir: Path) -> Path:
    """Resolve a declared source path relative to the input manifest."""
    expanded = Path(os.path.expanduser(value)).expanduser()
    if not expanded.is_absolute():
        expanded = manifest_dir / expanded
    return expanded.resolve()


def _discover_files(manifest: dict, manifest_dir: Path) -> list[dict]:
    """Return a list of source file descriptors from the manifest."""
    sources = manifest.get("sources", {})
    discovered: list[dict] = []

    # Claude Code project sessions
    cc = sources.get("claude_code_sessions", {})
    for root in cc.get("roots", []):
        root_path = _expand_path(root, manifest_dir)
        if root_path.is_dir():
            for file_path in sorted(root_path.rglob("*.jsonl")):
                discovered.append({
                    "type": "claude_project_session",
                    "path": str(file_path),
                    "mtime": file_path.stat().st_mtime,
                })
        elif root_path.is_file():
            discovered.append({
                "type": "claude_project_session",
                "path": str(root_path),
                "mtime": root_path.stat().st_mtime,
            })
        else:
            raise FileNotFoundError(f"declared Claude session source does not exist: {root}")

    # Claude command history
    hist = sources.get("claude_command_history", {})
    if hist.get("path"):
        p = _expand_path(hist["path"], manifest_dir)
        if not p.is_file():
            raise FileNotFoundError(
                f"declared Claude command history does not exist: {hist['path']}"
            )
        discovered.append({"type": "claude_command_history", "path": str(p), "mtime": p.stat().st_mtime})

    # Codex transcripts
    codex = sources.get("codex_transcripts", {})
    if codex.get("path"):
        p = _expand_path(codex["path"], manifest_dir)
        if not p.is_file():
            raise FileNotFoundError(
                f"declared Codex transcript does not exist: {codex['path']}"
            )
        discovered.append({"type": "codex_transcription", "path": str(p), "mtime": p.stat().st_mtime})

    # Manual exports
    for manual in sources.get("manual_exports", []):
        p = _expand_path(manual, manifest_dir)
        if not p.is_file():
            raise FileNotFoundError(f"declared manual export does not exist: {manual}")
        discovered.append({"type": "manual_export", "path": str(p), "mtime": p.stat().st_mtime})

    # Deduplicate by path
    seen_paths = set()
    deduped: list[dict] = []
    for s in discovered:
        if s["path"] not in seen_paths:
            seen_paths.add(s["path"])
            deduped.append(s)
    discovered = deduped

    if not discovered:
        raise ValueError("no conversation source files were discovered")

    return discovered


def _parse_time_window(source_config: dict) -> tuple[Optional[datetime], Optional[datetime]]:
    """Parse the optional message-level window for Claude project sessions."""
    def parse_boundary(value: Any, field: str) -> Optional[datetime]:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(f"{field} must be an ISO 8601 string with an explicit timezone")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{field} must be a valid ISO 8601 timestamp") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError(f"{field} must include an explicit timezone")
        return parsed.astimezone(timezone.utc)

    since_dt = parse_boundary(source_config.get("since"), "since")
    until_dt = parse_boundary(source_config.get("until"), "until")
    if since_dt is not None and until_dt is not None and since_dt > until_dt:
        raise ValueError("since must be earlier than or equal to until")
    return since_dt, until_dt


def _message_in_window(message: dict, since: Optional[datetime], until: Optional[datetime]) -> bool:
    """Return whether a message is inside an explicit time window.

    When a window is present, messages without a parseable timestamp are
    excluded rather than guessed into scope.
    """
    if since is None and until is None:
        return True
    timestamp = message.get("timestamp")
    if not timestamp:
        return False
    try:
        message_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    if message_dt.tzinfo is None or message_dt.utcoffset() is None:
        return False
    message_dt = message_dt.astimezone(timezone.utc)
    if since is not None and message_dt < since:
        return False
    if until is not None and message_dt > until:
        return False
    return True


# ---------------------------------------------------------------------------
# Relevance scoring
# ---------------------------------------------------------------------------

def _build_keyword_scorer(topic_spec: dict):
    keywords = topic_spec.get("keywords", [])
    exclude = topic_spec.get("exclude_keywords", [])

    def score(text: str) -> float:
        lower = text.lower()
        total = 0.0
        for kw in keywords:
            total += lower.count(kw.lower())
        for kw in exclude:
            total -= lower.count(kw.lower()) * 0.5
        return total

    return score


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def _chunk_messages(messages: list[dict], chunk_tokens: int, counter) -> list[dict]:
    """Greedy packing of messages into token-sized chunks."""
    chunks: list[dict] = []
    current: list[dict] = []
    current_tokens = 0
    current_sources: set[str] = set()
    start_idx = 0

    for idx, msg in enumerate(messages):
        msg_tokens = counter(msg["text"])
        # If a single message exceeds the chunk, split it.
        if msg_tokens > chunk_tokens:
            if current:
                chunks.append(_make_chunk(current, start_idx, idx - 1, current_tokens, current_sources))
                current = []
                current_tokens = 0
                current_sources = set()
                start_idx = idx

            for part in _split_text_by_token_budget(msg["text"], chunk_tokens, counter):
                part_msg = {**msg, "text": part, "chunk_part": True}
                part_tokens = counter(part)
                chunks.append(_make_chunk([part_msg], idx, idx, part_tokens, {msg["source"]}))
            continue

        if current_tokens + msg_tokens > chunk_tokens and current:
            chunks.append(_make_chunk(current, start_idx, idx - 1, current_tokens, current_sources))
            current = []
            current_tokens = 0
            current_sources = set()
            start_idx = idx

        current.append(msg)
        current_tokens += msg_tokens
        current_sources.add(msg["source"])

    if current:
        chunks.append(_make_chunk(current, start_idx, len(messages) - 1, current_tokens, current_sources))

    return chunks


def _split_text_by_token_budget(text: str, chunk_tokens: int, counter) -> list[str]:
    """Split text losslessly so every part satisfies the real token counter."""
    parts: list[str] = []
    start = 0
    while start < len(text):
        remaining = text[start:]
        if counter(remaining) <= chunk_tokens:
            parts.append(remaining)
            break

        low, high, best = 1, len(remaining), 0
        while low <= high:
            mid = (low + high) // 2
            tokens = counter(remaining[:mid])
            if tokens <= chunk_tokens:
                best = mid
                low = mid + 1
            else:
                high = mid - 1

        if best == 0:
            raise ValueError(
                "partitioning.chunk_tokens is too small to encode one character losslessly"
            )
        part = remaining[:best]
        if counter(part) > chunk_tokens:
            raise ValueError("internal chunking error: token budget exceeded")
        parts.append(part)
        start += best

    return parts


def _make_chunk(messages: list[dict], start_idx: int, end_idx: int, tokens: int, sources: set[str]) -> dict:
    return {
        "messages": messages,
        "start_idx": start_idx,
        "end_idx": end_idx,
        "tokens": tokens,
        "sources": sorted(sources),
    }


# ---------------------------------------------------------------------------
# File hashing and manifest
# ---------------------------------------------------------------------------

def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _public_source_descriptor(source: dict) -> dict:
    """Return source metadata safe to persist in local artifacts."""
    return {
        "source_id": source["source_id"],
        "type": source["type"],
        "sha256": source["sha256"],
        "size_bytes": source["size_bytes"],
    }


def _protect_enrichment_artifacts(output_dir: Path) -> None:
    """Keep local conversation-mining artifacts out of version control.

    The input manifest can contain local transcript paths, while persisted run
    artifacts use opaque source IDs. When output lives below a directory named
    ``.enrich``, ensure every generated artifact stays out of version control.
    Outputs elsewhere are left untouched.
    """
    enrich_root = next(
        (candidate for candidate in (output_dir, *output_dir.parents)
         if candidate.name == ".enrich"),
        None,
    )
    if enrich_root is None:
        return

    enrich_root.mkdir(parents=True, exist_ok=True)
    ignore_file = enrich_root / ".gitignore"
    existing = ignore_file.read_text(encoding="utf-8") if ignore_file.exists() else ""
    rules = {line.strip() for line in existing.splitlines()}
    if "*" not in rules:
        prefix = existing.rstrip()
        content = f"{prefix}\n*\n" if prefix else "*\n"
        ignore_file.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Mine conversation histories for skill references")
    parser.add_argument("--manifest", required=True, type=Path, help="Path to conversation_history_manifest.json")
    parser.add_argument("--output", required=True, type=Path, help="Enrichment output directory (e.g. <skill>/.enrich/<timestamp>)")
    parser.add_argument("--discover-only", action="store_true", help="Only discover sources and write manifest, no chunks")
    parser.add_argument("--verbose", action="store_true", help="Print progress")
    args = parser.parse_args(argv)

    if not args.manifest.exists():
        print(f"Manifest not found: {args.manifest}", file=sys.stderr)
        return 1
    _protect_enrichment_artifacts(args.manifest.parent)

    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Invalid manifest: {exc}", file=sys.stderr)
        return 1
    topic_spec = manifest.get("topic_spec", {})
    redaction_cfg = manifest.get("redaction", {})
    partitioning_cfg = manifest.get("partitioning", {})
    chunk_tokens = partitioning_cfg.get("chunk_tokens", 12000)
    encoding_model = partitioning_cfg.get("encoding_model", "cl100k_base")

    if isinstance(chunk_tokens, bool) or not isinstance(chunk_tokens, int) or chunk_tokens <= 0:
        print("Invalid manifest: partitioning.chunk_tokens must be a positive integer", file=sys.stderr)
        return 1
    if not isinstance(encoding_model, str) or not encoding_model:
        print("Invalid manifest: partitioning.encoding_model must be a non-empty string", file=sys.stderr)
        return 1

    try:
        since_dt, until_dt = _parse_time_window(
            manifest.get("sources", {}).get("claude_code_sessions", {})
        )
        redactor = Redactor(
            allowlist=redaction_cfg.get("allowlisted_placeholders"),
            extra_patterns=redaction_cfg.get("extra_patterns"),
        )
    except (TypeError, ValueError) as exc:
        print(f"Invalid manifest: {exc}", file=sys.stderr)
        return 1

    try:
        counter = get_token_counter(encoding_model)
    except (RuntimeError, ValueError) as exc:
        print(f"Invalid token counter configuration: {exc}", file=sys.stderr)
        return 1
    scorer = _build_keyword_scorer(topic_spec)

    try:
        sources = _discover_files(manifest, args.manifest.resolve().parent)
    except (OSError, TypeError, ValueError) as exc:
        print(f"Invalid manifest sources: {exc}", file=sys.stderr)
        return 1

    output_dir = args.output
    output_dir.mkdir(parents=True, exist_ok=True)
    _protect_enrichment_artifacts(output_dir)
    if args.verbose:
        print(f"Discovered {len(sources)} source files")

    # Hash sources and enrich descriptors
    for index, s in enumerate(sources, start=1):
        p = Path(s["path"])
        s["source_id"] = f"source-{index:03d}"
        s["sha256"] = _hash_file(p)
        s["size_bytes"] = p.stat().st_size
    public_sources = [_public_source_descriptor(source) for source in sources]
    manifest_hash = _hash_file(args.manifest)

    if args.discover_only:
        discovery_manifest = {
            "version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "discover-only",
            "manifest_sha256": manifest_hash,
            "target_skill": manifest.get("target_skill"),
            "topic_spec": topic_spec,
            "sources": public_sources,
        "message_time_window": {
            "since": since_dt.isoformat() if since_dt else None,
            "until": until_dt.isoformat() if until_dt else None,
        },
        }
        (output_dir / "manifest.json").write_text(json.dumps(discovery_manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        if args.verbose:
            print(f"Discovery manifest written to {output_dir / 'manifest.json'}")
        return 0

    chunks_dir = output_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = output_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    all_messages: list[dict] = []
    parser_map = {
        "claude_project_session": _parse_claude_project_jsonl,
        "claude_command_history": _parse_claude_command_history_jsonl,
        "codex_transcription": _parse_codex_transcription_jsonl,
        "codex_history": _parse_codex_history_jsonl,
        "manual_export": _parse_manual_export,
    }
    for source in sources:
        parser = parser_map[source["type"]]
        path = Path(source["path"])
        try:
            for msg in parser(path):
                msg["source_type"] = source["type"]
                msg["source"] = source["source_id"]
                if source["type"] == "claude_project_session" and not _message_in_window(
                    msg, since_dt, until_dt
                ):
                    continue
                all_messages.append(msg)
        except Exception as e:
            print(f"Failed to parse declared source {source['source_id']}: {e}", file=sys.stderr)
            return 1

    # Sort by timestamp if available; otherwise keep source order
    all_messages.sort(key=lambda m: (m.get("timestamp") or "", m.get("source_line", 0)))

    # Redact and score
    retained_messages = []
    min_score = topic_spec.get("min_relevance_score", 0.0)
    for msg in all_messages:
        redacted_text = redactor.redact(msg["text"], source_hint=msg["source"])
        msg["text"] = redacted_text
        msg["relevance_score"] = scorer(redacted_text)
        if msg["relevance_score"] >= min_score:
            retained_messages.append(msg)

    if args.verbose:
        print(f"Parsed {len(all_messages)} messages; retained {len(retained_messages)} with relevance >= {min_score}")

    try:
        chunks = _chunk_messages(retained_messages, chunk_tokens, counter)
    except ValueError as exc:
        print(f"Chunking failed: {exc}", file=sys.stderr)
        return 1
    if args.verbose:
        print(f"Partitioned into {len(chunks)} chunks")

    # Write chunks
    for idx, chunk in enumerate(chunks):
        chunk_file = chunks_dir / f"chunk-{idx:03d}.json"
        chunk_file.write_text(json.dumps(chunk, indent=2, ensure_ascii=False), encoding="utf-8")

    # Write manifest
    run_manifest = {
        "version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "full",
        "manifest_sha256": manifest_hash,
        "target_skill": manifest.get("target_skill"),
        "topic_spec": topic_spec,
        "partitioning": partitioning_cfg,
        "sources": public_sources,
        "message_counts": {
            "parsed": len(all_messages),
            "retained": len(retained_messages),
        },
        "chunk_count": len(chunks),
        "redaction_report": redactor.report(),
    }
    (output_dir / "manifest.json").write_text(json.dumps(run_manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    # Write redaction report separately as well
    (output_dir / "redaction_report.json").write_text(json.dumps(redactor.report(), indent=2, ensure_ascii=False), encoding="utf-8")

    # Write a simple log
    log_path = logs_dir / "mine.log"
    log_path.write_text(
        f"mine_conversation run at {datetime.now(timezone.utc).isoformat()}\n"
        f"sources: {len(sources)}\n"
        f"messages parsed: {len(all_messages)}\n"
        f"messages retained: {len(retained_messages)}\n"
        f"chunks emitted: {len(chunks)}\n"
        f"redactions: {sum(redactor.counts.values())}\n",
        encoding="utf-8",
    )

    if args.verbose:
        print(f"Artifacts written to {output_dir}")
        print(f"Redactions: {sum(redactor.counts.values())}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
