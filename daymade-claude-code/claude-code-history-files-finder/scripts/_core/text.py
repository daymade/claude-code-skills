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
import os
import re
import shutil
import subprocess
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


def iter_jsonl(
    path: Path,
    *,
    bounded: bool = False,
    line_keywords: Optional[list[str]] = None,
) -> Iterator[dict[str, Any]]:
    """Yield each JSONL record as a dict.

    ``line_keywords`` is an optional cheap pre-check: when given, a line is
    only handed to ``json.loads`` if it contains at least one of these
    strings as a raw substring (case-insensitive — callers pass already
    case-folded keywords and this function case-folds the line to match).
    This exists because ``json.loads`` plus walking the resulting structure
    is the expensive part of a keyword search, and file-level filtering
    (skip whole files with no occurrence anywhere) turned out not to be
    enough on its own: a keyword common across a user's session history
    (e.g. "embedding") can appear in most FILES while still appearing in
    only a small fraction of the LINES within each one, so ruling out
    individual non-matching lines before parsing them is where the real
    remaining cost lives.

    Like the file-level pre-filter in ``files_possibly_matching``, this is
    an over-approximation: a line can pass this check and still turn out to
    have no *matchable* record once parsed (the keyword landed in a raw
    JSON key/structural byte rather than an actual field value, or in a
    field the structured extractor deliberately excludes). It must never be
    an under-approximation — never skip a line that a full parse would have
    matched — which is what makes it safe to use as a pure speedup.

    Only pass this from a call site that has independently confirmed
    skipping unselected lines cannot corrupt some other accounting the
    caller performs across every record (see ``search_sessions``'s
    ``use_prefilter`` docstring for the specific case this codebase hit —
    date-window "excluded because untimed" counts must see every record).
    """
    consumed = 0
    lines = 0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                consumed += len(line.encode("utf-8", errors="replace"))
                lines += 1
                if bounded and (consumed > MAX_PREFIX_BYTES or lines > MAX_PREFIX_LINES):
                    return
                if line_keywords is not None:
                    haystack = line.casefold()
                    if not any(kw in haystack for kw in line_keywords) and not any(
                        marker in line for marker in _UNSCANNABLE_MARKERS
                    ):
                        # Same over-approximation as the file-level filter: a
                        # line holding a fold-equivalent character or a \u
                        # escape may still match once parsed, so never skip it.
                        continue
                try:
                    value = json.loads(line)
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(value, dict):
                    yield value
    except (OSError, UnicodeError):
        return


# Every character a JSON writer may store as something other than itself:
# the two mandatory escapes (" and \), the optional one (/), and all control
# characters. Enumerated from the JSON grammar rather than from observed
# escapes — an earlier version listed only control chars and "/", which
# covered a case Python never even produces while missing the two that every
# writer produces.
_JSON_ESCAPED_CHAR_RE = re.compile(r'["\\/\x00-\x1f]')

# The guard above can only inspect the KEYWORD. The other half of the problem
# is invisible to it: an all-ASCII keyword can legitimately match non-ASCII
# CONTENT, because Python's casefold() does *full* folding. Searching
# "financial" must match a transcript containing "ﬁnancial" (U+FB01, which
# arrives whenever someone pastes from a PDF) — the real matcher does, a byte
# scanner does not.
#
# Enumerated from Python's own casefold table rather than written by hand:
# every non-ASCII code point whose casefold is pure ASCII. There are exactly
# 11 (ß ſ ẞ K and the ff/fi/fl/ffi/ffl/st ligatures). A hand-written list
# drafted for this fix had 17 entries, several of which do not actually fold
# to ASCII — which is the argument for deriving it.
_FOLDS_TO_ASCII = tuple(
    chr(cp)
    for cp in range(0x80, 0x11000)
    if chr(cp).casefold() != chr(cp)
    and chr(cp).casefold().isascii()
    and chr(cp).casefold().strip()
)

# Any of these in a file/line means a byte scan cannot rule it out:
#   - the fold-equivalent characters above
#   - a "\u" escape: content written with ensure_ascii=True stores non-ASCII
#     that way, and some writers (Go's encoding/json) escape even ASCII
#     "<" ">" "&" as </>/&
_UNSCANNABLE_MARKERS = _FOLDS_TO_ASCII + ("\\u",)


def keywords_are_raw_byte_safe(keywords: Iterable[str]) -> bool:
    """Can a literal byte scan of the physical file stand in for matching
    against the parsed strings?

    Pass the **original** keywords, never case-folded ones. ``"ß".casefold()``
    is ``"ss"`` — pure ASCII — so folding first makes this function answer
    "safe" for exactly the input that motivated rule 2 below, silently
    re-opening the hole it exists to close.

    Only when every keyword's bytes are *guaranteed* to appear verbatim in the
    file, and a byte scanner's notion of "equal" matches Python's. Three shapes
    break that guarantee, and each one silently loses matches rather than
    reporting an error — so all three fall back to full parsing:

    1. **Characters JSON is required to escape**: control characters, ``"``,
       and ``\\``. An embedded newline is stored as the two bytes ``\\n``, a
       quote as ``\\"``, a backslash as ``\\\\`` — so a literal search for the
       raw character cannot find the escaped form actually sitting in the
       file. This is not a quirk of some serializers; every conforming JSON
       writer does it, including the one that produced these transcripts.
       Quoted error fragments (``Error: "ENOENT"``), config snippets
       (``"model": "opus"``), and Windows paths are exactly the sort of thing
       people search history for.

    2. **Non-ASCII.** Two independent failures. (a) ``json.dumps`` defaults to
       ``ensure_ascii=True``, which stores ``café`` as ``caf\\u00e9`` — the
       UTF-8 bytes are simply not in the file. Claude Code's own writer does
       not do this, but archives rewritten by other tooling do. (b) Even in
       raw UTF-8, case-insensitive folding disagrees across implementations:
       measured on this corpus's tooling, Python ``casefold()`` does *full*
       folding (``straße`` == ``STRASSE``), ``rg -i`` does only *simple*
       folding (matches ``STRAẞE`` but not ``STRASSE``), and ``/usr/bin/grep
       -i`` matches neither. A pre-filter that disagrees with the real matcher
       drops sessions, and it would drop *different* ones depending on whether
       ``rg`` happens to be installed.

    3. **A literal ``/``.** Optional in JSON — Python does not escape it — but
       some writers emit ``\\/``, so it is excluded for the same reason.

    Falling back is always the safe direction: it costs speed, never a missed
    match. The cost is real and worth naming — a non-ASCII query (any CJK one)
    gets no pre-filter at all and pays the full parse. Correctness first: this
    tool's callers are told they may conclude a topic is absent from a
    no-match result.
    """
    return all(
        kw.isascii()
        and not _JSON_ESCAPED_CHAR_RE.search(kw)
        for kw in keywords
    )


def files_possibly_matching(
    paths: Iterable[Path], keywords: Iterable[str], *, case_sensitive: bool = False
) -> Optional[set[Path]]:
    """Raw-byte pre-filter: which of ``paths`` could possibly contain any of
    ``keywords``, without paying per-line ``json.loads`` + structured
    extraction on files that plainly cannot match?

    This exists because the natural way to search this corpus — open every
    session file, ``json.loads`` every line, extract the searchable text, and
    substring-match keywords against it — parses every byte of every file
    even when the overwhelming majority contain none of the keywords at all.
    On a single project of 294 files / 1.6GB that pure-Python loop measured
    3.5+ minutes of CPU time without completing; ``rg``/``grep`` scan the same
    bytes at native speed and can usually rule out most files in well under a
    second, letting the expensive path run only on the handful of files that
    are actually candidates.

    Deliberately an OVER-approximation, never an under-approximation: keys
    excluded from search on purpose (``id``, ``tool_use_id``, ``signature`` —
    see ``_flatten_search_strings``) can still contain a keyword's raw bytes,
    so a small number of files this returns as "possible" will turn out to
    have no real match once fully parsed. That costs a little wasted parsing,
    which is fine. What must never happen is the reverse — silently ruling
    out a file that genuinely contains a matchable occurrence — because
    completeness is this tool's whole reason to exist (see the "Completeness
    invariant" in the finder skill's own SKILL.md). So every failure mode
    below degrades to "don't filter" rather than to "filter more":

    - No keywords, or a keyword containing a raw control character (the
      JSON-escaping mismatch above): returns ``None``.
    - Neither ``rg`` nor ``grep`` is on PATH: returns ``None``.
    - The scanner subprocess itself errors or times out: returns ``None``.

    ``None`` means "no filtering information — treat every path as a
    candidate", which is exactly the pre-existing behavior before this
    function existed. Callers must check for ``None`` and fall through to
    scanning everything, not treat it as an empty result.
    """
    path_list = list(paths)
    keyword_list = list(keywords)
    if not path_list or not keyword_list or not keywords_are_raw_byte_safe(keyword_list):
        return None
    exe = shutil.which("rg") or shutil.which("grep")
    if not exe:
        return None
    # -a/--text: never let the binary-content heuristic skip a JSONL file that
    #   happens to contain a byte sequence that looks binary.
    # -F: keywords are literal substrings everywhere else in this codebase
    #   (Python's str.count(), not a regex) — a raw scan must match the same
    #   semantics, not treat a keyword like "a.b" as a wildcard pattern.
    # -l: list matching filenames only; we don't need line numbers here.
    # Two scans, unioned — they need opposite case settings.
    #
    # Pass 1 matches the keywords the way the real matcher does (folded, unless
    # the caller asked for case-sensitive).
    #
    # Pass 2 looks for content the byte scanner cannot reason about at all
    # (fold-equivalent characters, "\u" escapes) and MUST be case-sensitive.
    # Handing those characters to a "-i" scan is self-defeating: "-i" folds the
    # *pattern* too, so `ſ` matches a plain `s` and `K` (U+212A) matches `k` —
    # every file with an "s" or a "k" in it becomes a candidate and the filter
    # stops filtering. (Caught by the pre-existing unit tests, which is exactly
    # what they are for.)
    kw_scan = [exe, "-a", "-F", "-l"]
    if not case_sensitive:
        kw_scan.append("-i")
    for kw in keyword_list:
        kw_scan += ["-e", kw]
    kw_scan.append("--")

    marker_scan = [exe, "-a", "-F", "-l"]
    for marker in _UNSCANNABLE_MARKERS:
        marker_scan += ["-e", marker]
    marker_scan.append("--")

    # Batch the paths: one exec per ~half of ARG_MAX. Passing every path in a
    # single argv fails with E2BIG once the corpus is large enough — measured
    # here at 7819 files needing 1,181,495 bytes against an ARG_MAX of
    # 1,048,576. That failure degrades safely (OSError -> return None -> no
    # filtering), but it means the speedup silently switched itself off in
    # exactly the "tens of thousands of files" case that motivated it.
    try:
        arg_max = os.sysconf("SC_ARG_MAX")
    except (ValueError, OSError):
        arg_max = 256 * 1024
    matched: set[Path] = set()

    def run_batch(scan_prefix: list[str], paths_chunk: list[str]) -> bool:
        """Returns False if the scanner failed — caller degrades to no filter."""
        try:
            result = subprocess.run(
                scan_prefix + paths_chunk, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        # Both rg and grep: 0 = matches found, 1 = no matches (not an error).
        # Any other code (bad invocation, I/O error) is a scanner failure ->
        # degrade to "don't filter" rather than trust a broken result.
        if result.returncode not in (0, 1):
            return False
        matched.update(Path(line) for line in result.stdout.splitlines() if line)
        return True

    def scan_all(scan_prefix: list[str]) -> bool:
        fixed = sum(len(a.encode("utf-8", "replace")) + 1 for a in scan_prefix)
        chunk_budget = max(arg_max // 2 - fixed, 64 * 1024)
        batch: list[str] = []
        used = 0
        for path in path_list:
            text = str(path)
            size = len(text.encode("utf-8", "replace")) + 1
            if batch and used + size > chunk_budget:
                if not run_batch(scan_prefix, batch):
                    return False
                batch, used = [], 0
            batch.append(text)
            used += size
        return not batch or run_batch(scan_prefix, batch)

    if not scan_all(kw_scan) or not scan_all(marker_scan):
        return None
    return matched


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
