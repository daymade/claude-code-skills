"""Shared text / title / JSONL parsing helpers for the local-history skills.

These turn raw session content into a readable one-line title and iterate JSONL
transcripts safely. Both the Claude and Codex providers use them, so they live in
the shared core (SSOT: `daymade-claude-code/_conversation_core/`, bundled into
each skill's `scripts/_core/` by `sync_core.py`). Keeping them here lets the Codex
provider and `continue-codex-work` reuse one implementation instead of
re-deriving title/noise heuristics that would drift apart.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

from .parse import looks_like_windows_path

MAX_PREFIX_BYTES = 2 * 1024 * 1024
MAX_PREFIX_LINES = 5000
NOISE_PREFIXES = (
    "# agents.md instructions for ",
    "<app-context",
    "<collaboration_mode",
    "<command-message",
    "<command-name",
    "<codex_internal_context",
    "<environment_context",
    "<local-command-caveat",
    "<local-command-stdout",
    "<permissions instructions",
    "<recommended_plugins",
    "<system-reminder",
)
AUTOMATED_TITLE_RE = re.compile(
    r"^(?:reply|respond|return|print)\s+(?:with\s+)?exactly\b", re.IGNORECASE
)
ATTACHMENT_IMAGE_RE = re.compile(
    r"^(?:<image\b|\[Image\s+#\d+\])", re.IGNORECASE
)
FILE_SUFFIX_RE = re.compile(r"\.[A-Za-z0-9]{1,16}$")
SLASH_COMMAND_RE = re.compile(r"^/[A-Za-z0-9_:-]+(?:[ \t].*)?$")


@dataclass(frozen=True)
class SearchSegment:
    """One searchable text field with its semantic provenance."""

    source: str
    text: str


def looks_like_attachment_prefix(value: str) -> bool:
    """Recognize attachment metadata without guessing from prompt length."""
    stripped = value.strip()
    if ATTACHMENT_IMAGE_RE.match(stripped):
        return True
    if "\n" in stripped:
        return False
    candidate = stripped.strip("`'\"")
    path_like = candidate.startswith(("/", "~/")) or looks_like_windows_path(
        candidate
    )
    return path_like and bool(FILE_SUFFIX_RE.search(candidate))


def strip_structural_metadata_lines(value: str) -> tuple[str, bool]:
    """Remove attachment and slash-command wrapper lines around a request."""
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    removed_attachment = False
    while lines:
        if looks_like_attachment_prefix(lines[0]):
            removed_attachment = True
            lines.pop(0)
            continue
        if SLASH_COMMAND_RE.fullmatch(lines[0]):
            lines.pop(0)
            continue
        break
    while lines and SLASH_COMMAND_RE.fullmatch(lines[-1]):
        lines.pop()
    return "\n".join(lines).strip(), removed_attachment


def iter_jsonl(path: Path, *, bounded: bool = False) -> Iterator[dict[str, Any]]:
    consumed = 0
    lines = 0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                consumed += len(line.encode("utf-8", errors="replace"))
                lines += 1
                if bounded and (consumed > MAX_PREFIX_BYTES or lines > MAX_PREFIX_LINES):
                    return
                try:
                    value = json.loads(line)
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(value, dict):
                    yield value
    except (OSError, UnicodeError):
        return


def extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") in {"text", "input_text"} and isinstance(
            item.get("text"), str
        ):
            parts.append(item["text"])
    return " ".join(parts)


def _flatten_search_strings(value: Any) -> Iterator[str]:
    """Yield string values while excluding structural/signature metadata."""
    if isinstance(value, str):
        if value:
            yield value
        return
    if isinstance(value, list):
        for item in value:
            yield from _flatten_search_strings(item)
        return
    if not isinstance(value, dict):
        return
    for key, child in value.items():
        if key in {"type", "id", "tool_use_id", "signature"}:
            continue
        yield from _flatten_search_strings(child)


def searchable_segments(record: dict[str, Any]) -> list[SearchSegment]:
    """Extract user-visible/search-relevant fields from one Claude event.

    Raw JSON serialization is intentionally not searched: keys, UUIDs, and
    cryptographic thinking signatures create false positives. Instead this
    covers message text, thinking text, tool inputs/results, queue content,
    last-prompt/system summaries, and attachment payloads with a source label for
    every segment.
    """
    segments: list[SearchSegment] = []

    def add(source: str, value: Any) -> None:
        for text_value in _flatten_search_strings(value):
            segments.append(SearchSegment(source=source, text=text_value))

    event_type = record.get("type")
    message = record.get("message")
    content: Any
    if isinstance(message, dict):
        content = message.get("content", [])
    elif isinstance(message, str):
        content = message
    elif event_type in {"user", "assistant"} or record.get("role") in {
        "user",
        "assistant",
    }:
        content = record.get("content", [])
    else:
        content = []

    if isinstance(content, str):
        add("message", content)
    elif isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type in {"text", "input_text"}:
                add("message", block.get("text"))
            elif block_type == "thinking":
                add("thinking", block.get("thinking"))
            elif block_type == "tool_use":
                tool_name = block.get("name")
                source = (
                    f"tool_input:{tool_name}"
                    if isinstance(tool_name, str) and tool_name
                    else "tool_input"
                )
                add(source, block.get("input"))
            elif block_type == "tool_result":
                add("tool_result", block.get("content"))
            else:
                # Preserve textual payloads of future/older block types without
                # indexing structural keys or binary image data.
                add("message", {key: block.get(key) for key in ("text", "content")})

    if event_type == "queue-operation":
        add("queue-operation", record.get("content"))
    elif event_type == "attachment":
        attachment = record.get("attachment")
        if isinstance(attachment, dict):
            add(
                "attachment",
                {
                    key: attachment.get(key)
                    for key in (
                        "content",
                        "prompt",
                        "path",
                        "displayPath",
                        "command",
                        "stdout",
                        "stderr",
                    )
                },
            )
    elif event_type == "last-prompt":
        add("last-prompt", record.get("lastPrompt"))
    elif event_type == "system":
        add("system", record.get("content"))
    elif event_type == "summary":
        add("summary", {"content": record.get("content"), "summary": record.get("summary")})
    elif event_type == "custom-title":
        add(
            "custom-title",
            {"title": record.get("title"), "customTitle": record.get("customTitle")},
        )

    # Some event variants mirror the same payload in more than one compatible
    # field. Count each semantic source/text pair once per record.
    return list(dict.fromkeys(segments))


def is_noise_text(text: str) -> bool:
    lowered = text.lstrip().casefold()
    return not lowered or any(lowered.startswith(prefix) for prefix in NOISE_PREFIXES)


def clean_title(text: str, max_chars: int) -> str:
    separator_parts = re.split(r"(?:^|\n)\s*-{4,}\s*(?:\n|$)", text)
    if len(separator_parts) > 1:
        raw_candidates = [part.strip() for part in separator_parts if part.strip()]
        processed_candidates = [
            strip_structural_metadata_lines(part) for part in raw_candidates
        ]
        attachment_requests = [
            candidate
            for candidate, removed_attachment in processed_candidates
            if candidate and removed_attachment
        ]
        candidates = [candidate for candidate, _ in processed_candidates if candidate]
        candidates = candidates or raw_candidates
        if attachment_requests:
            text = attachment_requests[-1]
        elif candidates:
            prefix = candidates[0]
            tail = candidates[-1]
            text = tail if len(tail) >= 20 else prefix
    text = re.sub(r"^<image\b[^>]*>\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</?image>\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\[Image\s+#\d+\]\s*", "", text, flags=re.IGNORECASE)
    home = str(Path.home())
    for home_variant in {home, home.replace("\\", "/"), home.replace("/", "\\")}:
        if home_variant:
            text = text.replace(home_variant, "~")
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def is_automated_title(title: str) -> bool:
    return bool(AUTOMATED_TITLE_RE.match(title.strip()))


def first_meaningful_title(
    candidates: Iterable[Any], max_chars: int
) -> Optional[str]:
    short_candidate: Optional[str] = None
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        cleaned = clean_title(candidate, max_chars)
        if is_noise_text(cleaned):
            continue
        if len(cleaned) >= 4:
            return cleaned
        if cleaned and short_candidate is None:
            short_candidate = cleaned
    return short_candidate
