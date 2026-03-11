#!/usr/bin/env python3
"""Fix broken line wrapping in Claude Code exported conversation files.

Claude Code exports hard-wrap lines at fixed column widths, breaking tables,
paragraphs, and paths.  This script reconstructs the original logical lines
using a state-machine + lookahead merge approach.

Usage:
    uv run scripts/fix-claude-export.py <input.txt>
    uv run scripts/fix-claude-export.py <input.txt> -o <output.txt>
    uv run scripts/fix-claude-export.py <input.txt> --stats --dry-run
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Display-width helpers
# ---------------------------------------------------------------------------

def display_width(s: str) -> int:
    """Calculate display width accounting for CJK double-width characters."""
    w = 0
    for ch in s:
        eaw = unicodedata.east_asian_width(ch)
        w += 2 if eaw in ("W", "F") else 1
    return w


def is_wide_char(ch: str) -> bool:
    """Return True if *ch* occupies two display columns (CJK full-width)."""
    return unicodedata.east_asian_width(ch) in ("W", "F")


def _is_cjk_ideograph(ch: str) -> bool:
    """Return True if *ch* is a CJK ideograph (not punctuation/symbol).

    CJK ideographs have Unicode category ``Lo`` (Letter, other) — e.g.
    ``你``, ``好``, ``接``.  CJK punctuation (``。，！？；：「」（）``) has
    categories ``Ps``, ``Pe``, ``Po``, etc. and should NOT match.

    This distinction matters for pangu spacing: a space is inserted between
    ASCII alphanumeric characters and CJK ideographs, but NOT between
    CJK punctuation and anything.
    """
    return is_wide_char(ch) and unicodedata.category(ch) == "Lo"


# ---------------------------------------------------------------------------
# Join helpers
# ---------------------------------------------------------------------------

def smart_join(left: str, right_content: str) -> str:
    """Join text with CJK-aware spacing (pangu style).

    Spacing rules at the join boundary:

    - **CJK ↔ CJK**: no space (both characters wide).
    - **ASCII alnum ↔ CJK ideograph**: insert one space.  This is "pangu
      spacing" — the standard practice of separating Han characters from
      Latin letters / digits in mixed CJK/English text.  The original
      content almost always has these spaces; they are lost when Claude
      hard-wraps at the column boundary.
    - **CJK punctuation ↔ anything**: no space.  Punctuation like ``，``
      ``。`` ``）`` ``（`` clings to its neighbor.
    - **ASCII ↔ ASCII**: insert one space (English word boundary).
    """
    left_s = left.rstrip()
    right_s = right_content.lstrip()
    if not left_s or not right_s:
        return left_s + right_s
    last_ch = left_s[-1]
    first_ch = right_s[0]

    last_wide = is_wide_char(last_ch)
    first_wide = is_wide_char(first_ch)

    if last_wide and first_wide:
        # Both CJK — no space.
        return left_s + right_s

    if last_wide or first_wide:
        # Mixed CJK/ASCII boundary — apply pangu spacing.
        # In addition to alnum, certain symbols that attach to numbers
        # or abbreviations (%, #, +, :) also trigger pangu spacing because
        # they're part of the same "token" as the adjacent number/word.
        _PANGU_SYMBOLS = "%#+:"
        if last_wide:
            # CJK → ASCII: space if CJK ideograph + ASCII alnum/symbol.
            if _is_cjk_ideograph(last_ch) and (first_ch.isalnum() or first_ch in _PANGU_SYMBOLS):
                return left_s + " " + right_s
            return left_s + right_s
        else:
            # ASCII → CJK: space if ASCII alnum/symbol + CJK ideograph.
            if (last_ch.isalnum() or last_ch in _PANGU_SYMBOLS) and _is_cjk_ideograph(first_ch):
                return left_s + " " + right_s
            return left_s + right_s

    # Both ASCII — mid-token detection before adding space.
    # Path continuation: alnum + / (e.g., "documents" + "/05-team")
    # Hyphen continuation: alnum + - (e.g., "ready" + "-together")
    # Underscore continuation: _ + alnum (e.g., "BASE_" + "URL")
    # Exception: -- prefix is a CLI flag (e.g., "run" + "--headed").
    if last_ch.isalnum() and first_ch in ("-", "/"):
        if first_ch == "-" and right_s.startswith("--"):
            pass  # fall through to default (add space)
        else:
            return left_s + right_s
    if last_ch in ("-", "/") and first_ch.isalnum():
        return left_s + right_s
    # Underscore at identifier boundary (e.g., "E2E_PO_BASE_" + "URL")
    if last_ch == "_" and first_ch.isalnum():
        return left_s + right_s
    if last_ch.isalnum() and first_ch == "_":
        return left_s + right_s

    # Default: word boundary → add space.
    return left_s + " " + right_s


def raw_join(left: str, right: str) -> str:
    """Strip trailing whitespace from *left*, leading spaces from *right*, concat."""
    return left.rstrip() + right.lstrip()


def _table_cell_content_join(
    left: str, right: str, *, left_filled: bool = False
) -> str:
    """Join two cell-content fragments from a multi-row table cell.

    Claude wraps long cell content across multiple physical rows at fixed
    column widths.  This function reassembles the original content by
    detecting mid-word breaks (e.g. ``Contr`` + ``oller``) vs word
    boundaries (e.g. ``Backend`` + ``Risk``).

    When *left_filled* is True, the left fragment filled its entire column
    (≤1 trailing space before the ``│`` delimiter), meaning the split was
    forced at the column boundary — almost certainly mid-word.  This is the
    strongest signal and overrides other heuristics.

    Heuristic priority:
      1. left_filled → raw join (column-boundary split)
      2. Continuation punctuation at boundary (``-  _ . /``) → raw join
      3. Left ends with letter, right starts with lowercase → mid-word
      4. Left ends with digit, right starts with digit → mid-number
      5. Otherwise → smart_join (CJK-aware spacing)
    """
    left_s = left.rstrip()
    right_s = right.lstrip()
    if not left_s or not right_s:
        return left_s + right_s

    last_ch = left_s[-1]
    first_ch = right_s[0]

    # Continuation punctuation at boundary — usually concatenate directly.
    # Exception: double-hyphen at right boundary (``--flag``) is a CLI
    # argument prefix, not a continuation of the left content.
    if last_ch in ("-", "_", ".", "/") or first_ch in ("-", "_", ".", "/"):
        if first_ch == "-" and right_s.startswith("--"):
            pass  # fall through to other checks
        else:
            return left_s + right_s

    if left_filled:
        # Column-boundary split: content filled the cell width.
        # The break is at a fixed position and likely mid-token, but we
        # verify with character-class checks to avoid false positives
        # like "Behavioral" + "Spec" (complete word at column edge).
        if last_ch.isalpha() and first_ch.islower():
            return left_s + right_s
        if last_ch.isupper() and first_ch.isupper():
            return left_s + right_s
        if last_ch.isdigit() and first_ch.isdigit():
            return left_s + right_s
        if last_ch.isalnum() and first_ch.isdigit():
            return left_s + right_s
        if last_ch.isdigit() and first_ch.islower():
            # Hex hash continuation: c3df79 + b → c3df79b
            return left_s + right_s
        # Filled but no mid-word evidence → fall through to smart_join.

    # Everything else: word-boundary or ambiguous → CJK-aware spacing.
    return smart_join(left_s, right_s)


def table_cell_join(left: str, right: str) -> str:
    """Join table cell continuation, preserving column spacing.

    Unlike raw_join, this strips only the table indent (matching the left
    side's indent) from the right side, keeping internal cell padding.
    It also ensures a space between ``│`` and adjacent cell content.
    """
    ls = left.rstrip()
    if not ls:
        return right.rstrip()
    # Determine indent from left side (typically 5 spaces for plan tables)
    indent = len(ls) - len(ls.lstrip())
    rs = right.rstrip()
    # Strip exactly the indent, keep remaining whitespace (cell padding)
    if len(rs) >= indent and rs[:indent].strip() == "":
        rs = rs[indent:]
    else:
        rs = rs.lstrip()
    if not rs:
        return ls
    # Ensure space between │ and non-│/non-space content
    if ls[-1] == "│" and rs[0] not in " │":
        return ls + " " + rs
    if ls[-1] not in " │" and rs[0] == "│":
        return ls + " " + rs
    return ls + rs


def boundary_aware_join(left: str, right: str) -> str:
    """Join with heuristic for mid-word vs word-boundary splits.

    If *left* had a trailing space before stripping, the hard wrap was at a
    word boundary -- preserve one space.  Otherwise the wrap split mid-word
    -- concatenate directly (no space).
    """
    # Check if left had trailing whitespace (word-boundary wrap).
    left_had_trailing_space = left != left.rstrip()
    left_s = left.rstrip()
    right_s = right.lstrip()
    if not left_s or not right_s:
        return left_s + right_s
    if left_had_trailing_space:
        # Word-boundary wrap: preserve spacing via smart_join which
        # handles pangu spacing (ASCII alnum ↔ CJK ideograph).
        return smart_join(left_s, right_s)
    # Mid-word wrap: no space.
    return left_s + right_s


def _dw_aware_join(left: str, right: str, left_dw: int) -> str:
    """Join with display-width-aware mid-word detection.

    Claude drops the trailing space at wrap points, making it impossible to
    distinguish word-boundary from mid-word breaks by whitespace alone.
    This function uses the display width of the *left* physical line to
    resolve the ambiguity:

    - **dw < 74**: the line ended well below the wrap column (~76) — the
      break was at a natural word boundary → smart_join.
    - **dw >= 75**: the line was forced to break near the column limit.
      Use character-class heuristics: alpha→lower = likely mid-word (raw
      join); all other transitions = word boundary (smart_join).
    """
    if left_dw < 75:
        return smart_join(left, right)

    # Near wrap limit — check trailing space first.
    left_had_trailing = left != left.rstrip()
    left_s = left.rstrip()
    right_s = right.lstrip()
    if not left_s or not right_s:
        return left_s + right_s

    if left_had_trailing:
        return smart_join(left_s, right_s)

    # No trailing space, near wrap limit.
    # Character-class heuristics for mid-word detection.
    last_ch = left_s[-1]
    first_ch = right_s[0]
    # alpha→lower: mid-word (e.g., "Backgrou" + "nd")
    if last_ch.isalpha() and first_ch.islower():
        return left_s + right_s
    # Path/hyphenated-name continuations: slash or hyphen at boundary
    # (e.g., ".claude/skills" + "/generating-..." or "ready" + "-together")
    if last_ch.isalnum() and first_ch in ("-", "/"):
        return left_s + right_s
    if last_ch in ("-", "/") and first_ch.isalnum():
        return left_s + right_s
    # digit→alpha (e.g., "md-e" + "2e-section" — hex/version fragments)
    if last_ch.isalpha() and first_ch.isdigit():
        return left_s + right_s

    # All other cases: treat as word boundary.
    return smart_join(left_s, right_s)


def _bullet_join(left: str, right: str) -> str:
    """Join a bullet line with its wrapped continuation.

    Like smart_join, but with mid-word detection: when left ends with an
    ASCII letter and right (after stripping) starts with a lowercase ASCII
    letter, concatenate directly (the hard-wrap split a word mid-token,
    e.g. ``RiskModelAss`` + ``ignment``).  Otherwise delegate to smart_join
    for CJK-aware spacing.
    """
    left_s = left.rstrip()
    right_s = right.lstrip()
    if not left_s or not right_s:
        return left_s + right_s
    last_ch = left_s[-1]
    first_ch = right_s[0]
    # Mid-word split: left ends with a letter, right starts with lowercase.
    if last_ch.isalpha() and first_ch.islower():
        return left_s + right_s
    # Hyphenated names / paths split at boundary.
    # e.g. "ready" + "-together-project" or "skills" + "/generating"
    if last_ch.isalnum() and first_ch in ("-", "/"):
        return left_s + right_s
    if last_ch in ("-", "/") and first_ch.isalnum():
        return left_s + right_s
    return smart_join(left_s, right_s)


# ---------------------------------------------------------------------------
# Line classification helpers
# ---------------------------------------------------------------------------

# Markers that ALWAYS start a new logical line (never join TO these).
_USER_PROMPT_RE = re.compile(r"^❯ ")
_CLAUDE_ACTION_RE = re.compile(r"^● ")
_THINKING_RE = re.compile(r"^✻ ")
_HR_RE = re.compile(r"^  ---")
_BOX_HR_RE = re.compile(r"^  ────")
_AGENT_TREE_RE = re.compile(r"^   [├└]─")
_TOOL_RESULT_RE = re.compile(r"^  ⎿")
_BULLET_RE = re.compile(r"^  - ")
_NUMBERED_RE = re.compile(r"^  \d+\. ")

# Indented bullets / numbered items inside plan blocks (5-space indent).
_PLAN_BULLET_RE = re.compile(r"^     - ")
_PLAN_NUMBERED_RE = re.compile(r"^     \d+\. ")

# Tool call openers (● ToolName( ...).
_TOOL_CALL_RE = re.compile(
    r"^● (?:Bash|Read|Write|Glob|Grep|Edit|Update|Searched|NotebookEdit)\("
)

# Table box-drawing characters.
_TABLE_CORNERS = set("┐┤┘")


def _is_truly_empty(line: str) -> bool:
    """A truly empty line (zero length after stripping the newline)."""
    return len(line) == 0


def _is_structural_break(line: str) -> bool:
    """Return True if *line* is a structural marker that must never be joined TO."""
    if _is_truly_empty(line):
        return True
    if _USER_PROMPT_RE.match(line):
        return True
    if _CLAUDE_ACTION_RE.match(line):
        return True
    if _THINKING_RE.match(line):
        return True
    if _HR_RE.match(line):
        return True
    if _BOX_HR_RE.match(line):
        return True
    if _AGENT_TREE_RE.match(line):
        return True
    if _TOOL_RESULT_RE.match(line):
        return True
    if _BULLET_RE.match(line):
        return True
    if _NUMBERED_RE.match(line):
        return True
    return False


# Regex for CJK labels like 模块:, 输出文件:, 状态:, 覆盖范围:
_CJK_LABEL_RE = re.compile(r"[\u4e00-\u9fff]{1,6}[:：]")
# Regex for English labelled list items: "Phase 1:", "Step 2:", "Layer 3:"
_LABELLED_ITEM_RE = re.compile(r"[A-Z]\w+ \d+[:.] ")


def _is_continuation_fragment(nl: str, acc: str) -> bool:
    """Return True if *nl* looks like a wrapped continuation of *acc*.

    This is the core predicate for joining 2-space-indented paragraph text.
    Instead of asking "was the current line wrapped?" (fragile dw threshold),
    it asks "does the NEXT line look like a continuation fragment?"

    A continuation fragment has NO structural identity — it is not a new
    bullet, numbered item, labelled field, or structural marker.  It
    typically starts with a lowercase letter, CJK ideograph, or is a short
    uppercase fragment of a sentence that wrapped mid-phrase.
    """
    # Must be 2-space indent (not deeper, not tool result).
    if not nl.startswith("  "):
        return False
    if nl.startswith("     "):  # 5+ space = plan/tool block
        return False
    if nl.startswith("  ⎿"):
        return False
    if _is_structural_break(nl):
        return False

    stripped = nl.lstrip()
    if not stripped:
        return False

    # --- New-item patterns (NOT a continuation) ---
    if stripped.startswith("- "):
        return False
    if re.match(r"\d+[.)] ", stripped):
        return False
    if _LABELLED_ITEM_RE.match(stripped):
        return False
    # CJK labels: 模块:, 输出文件:, 状态:, 覆盖范围: etc.
    if _CJK_LABEL_RE.match(stripped):
        return False
    # Column layout (side-by-side comparison with internal spacing).
    if "        " in stripped:  # 8+ internal spaces
        return False

    nl_dw = display_width(nl.rstrip())
    # A "continuation" line that is itself full-width is likely independent.
    if nl_dw >= 76:
        return False

    first_ch = stripped[0]

    # --- Strong continuation signals ---
    # Lowercase → mid-sentence continuation.
    if first_ch.islower():
        return True
    # CJK ideograph → continuing Chinese text.
    if _is_cjk_ideograph(first_ch):
        return True
    # CJK/fullwidth punctuation → continues previous CJK content.
    if is_wide_char(first_ch) and not _is_cjk_ideograph(first_ch):
        return True
    # Opening bracket → e.g. "(c67e5ded-..." UUID, list in parens.
    if first_ch in ("(", "[", "{", "（", "「", "【"):
        return True
    # Hyphen/slash continuation: acc ends with alnum, next starts with -//.
    # (e.g. "ready" + "-together-project", "skills" + "/generating")
    if first_ch in ("-", "/"):
        _acc_s = acc.rstrip()
        if _acc_s and _acc_s[-1].isalnum():
            return True

    # --- Check if accumulated text signals continuation ---
    acc_stripped = acc.rstrip()
    if acc_stripped:
        last_acc = acc_stripped[-1]
        # Continuation operators at end of acc → next line must continue.
        if last_acc in (",", "+", "→", "=", "&", "|", "、"):
            return True
        # Acc ends with sentence-terminal → next line is a new sentence.
        if last_acc in "。.！!？?；;":
            return False

    # --- Uppercase start: ambiguous ---
    # Short fragment (< 55 dw) is likely a sentence fragment.
    if nl_dw < 55:
        return True
    return False


def _is_plan_continuation_fragment(nl: str, acc: str) -> bool:
    """Return True if *nl* looks like a wrapped continuation in 5-space plan text.

    Same design philosophy as _is_continuation_fragment: examine the NEXT
    line's content to decide if it is a new item or a continuation fragment.
    """
    if not nl.startswith("     "):
        return False
    if nl.startswith("       "):  # 7+ space = deeper indent, separate item
        return False
    if _is_truly_empty(nl):
        return False
    if _is_structural_break(nl):
        return False
    if _is_plan_structural(nl):
        return False

    stripped = nl.lstrip()
    if not stripped:
        return False

    # CJK labels (模块:, 输出文件:, 状态:)
    if _CJK_LABEL_RE.match(stripped):
        return False
    # English labelled items with number (Phase 1:, Step 2:)
    if _LABELLED_ITEM_RE.match(stripped):
        return False
    # English labels without number (Plan:, Context:, Summary:)
    if re.match(r"[A-Z][a-zA-Z]+: ", stripped):
        return False
    # ASCII terminal labels (error:, hint:, remote:)
    if re.match(r"[a-z]+: ", stripped):
        return False
    # Diff output line numbers (e.g., "600  - **Test Data**:")
    # Pattern: 1-5 digits followed by 2+ spaces (diff line number format).
    if re.match(r"\d{1,5}\s{2,}", stripped):
        return False
    # Column layout
    if "        " in stripped:
        return False

    nl_dw = display_width(nl.rstrip())
    if nl_dw >= 76:
        return False

    first_ch = stripped[0]

    # --- New-item patterns that start with lowercase ---
    # ASCII labels like "error:", "hint:", "remote:" are terminal output
    # lines, not continuations.  They start a new message.
    if re.match(r"[a-z]+: ", stripped):
        return False

    # --- Strong continuation signals ---
    if first_ch.islower():
        return True
    if _is_cjk_ideograph(first_ch):
        return True
    if is_wide_char(first_ch) and not _is_cjk_ideograph(first_ch):
        return True
    if first_ch in ("(", "[", "{", "（", "「", "【"):
        return True
    # Hyphen/slash continuation (compound names, paths).
    if first_ch in ("-", "/"):
        _acc_s = acc.rstrip()
        if _acc_s and _acc_s[-1].isalnum():
            return True

    # Non-alnum, non-CJK, non-bracket starts (!, #, >, *, etc.)
    # are structural markers in terminal output, not continuations.
    if not first_ch.isalnum():
        return False

    # --- Check accumulated text ending ---
    acc_stripped = acc.rstrip()
    if acc_stripped:
        last_acc = acc_stripped[-1]
        if last_acc in (",", "+", "→", "=", "&", "|", "、"):
            return True
        if last_acc in "。.！!？?；;":
            return False

    # Uppercase start, ambiguous: short fragment = likely continuation.
    if nl_dw < 55:
        return True
    return False


def _is_plan_structural(line: str) -> bool:
    """Structural markers within 5-space-indented plan blocks."""
    if _PLAN_BULLET_RE.match(line):
        return True
    if _PLAN_NUMBERED_RE.match(line):
        return True
    stripped = line.lstrip()
    if stripped.startswith("##"):
        return True
    # Box-drawing separators within plan blocks (5-space indent).
    # The 2-space variant is caught by _BOX_HR_RE in _is_structural_break,
    # but 5-space-indented ones slip through.
    if stripped.startswith("────"):
        return True
    # Markdown HR within plan blocks (5-space indent).
    if stripped == "---":
        return True
    # Tree connector (standalone │ used in ASCII dependency diagrams).
    # Must not be confused with table data rows (which have 2+ │ chars).
    if stripped == "│":
        return True
    # File-tree lines (├── or └── patterns) within plan blocks.
    if stripped.startswith("├──") or stripped.startswith("└──"):
        return True
    # Expansion indicators ("… +N lines (ctrl+o to expand)").
    if stripped.startswith("…"):
        return True
    return False


def _has_continuation_signal(line: str) -> bool:
    """Detect if *line* was almost certainly hard-wrapped mid-content.

    Lines ending with a trailing comma, a CJK character, or an unclosed
    bracket are continuation signals — they indicate the content continues
    on the next line regardless of how narrow the display width is.
    """
    stripped = line.rstrip()
    if not stripped:
        return False
    last_ch = stripped[-1]
    if last_ch == ",":
        return True
    if is_wide_char(last_ch):
        return True
    if last_ch in ("(", "[", "{"):
        return True
    return False


def _has_unclosed_bracket(line: str) -> bool:
    """Detect if *line* contains an opening bracket with no matching close.

    An unclosed bracket means the parenthetical/list continues on the next
    physical line — a strong continuation signal regardless of display width.
    This catches cases like ``Requirements（P0/P1 分层，每个 Feature`` where
    Claude wraps at a word boundary well below the column limit because the
    remaining CJK text would push past it.
    """
    _PAIRS = (("(", ")"), ("[", "]"), ("{", "}"),
              ("（", "）"), ("「", "」"), ("【", "】"))
    for open_ch, close_ch in _PAIRS:
        if open_ch in line and close_ch not in line:
            return True
    return False


def _looks_like_mid_word(left: str, right: str) -> bool:
    """Heuristic: detect if a tool-call wrap split a token mid-character.

    Returns True when both sides appear to be fragments of one continuous
    filesystem path or identifier.  This is deliberately conservative --
    when in doubt, return False so a space gets inserted.
    """
    if not left or not right:
        return False
    lc = left[-1]
    rc = right[0]
    # Mid-path: one side has '/' at the boundary.
    if lc == "/" or rc == "/":
        return True
    # Mid-word with hyphen/underscore continuation
    # (e.g., "/skills/gener" + "ating-e2e-test-suite").
    # Must distinguish from command-argument boundaries
    # (e.g., "git add" + "test-cases/...") by checking the character
    # preceding the left side's last token.
    if lc.isalpha() and rc.isalpha() and lc.islower() and rc.islower():
        first_token = ""
        for ch in right:
            if ch.isalnum() or ch in "-_.":
                first_token += ch
            else:
                break
        if "-" in first_token or "_" in first_token:
            # Find start of last token on the left side
            last_token_start = len(left)
            while last_token_start > 0 and (
                left[last_token_start - 1].isalnum()
                or left[last_token_start - 1] in "-_."
            ):
                last_token_start -= 1
            # If preceded by '/', it might be mid-path -- but check if the
            # token is a complete filename (has file extension like .md/.py).
            if last_token_start > 0 and left[last_token_start - 1] == "/":
                last_token = left[last_token_start:]
                if re.search(r"\.\w{1,5}$", last_token):
                    return False  # Complete filename, not a fragment
                return True  # Mid-path fragment (e.g., /skills/gener)
            # If preceded by space or start-of-string, it's a word
            # boundary (e.g., "git add" + "test-cases") -> insert space
            return False
    return False


# ---------------------------------------------------------------------------
# Table detection helpers
# ---------------------------------------------------------------------------

def is_table_border_split(current: str, next_line: str) -> bool:
    """Detect a table border that was split across two lines."""
    cs = current.rstrip()
    if not cs or cs[-1] != "─":
        return False
    ns = next_line.lstrip()
    if not ns:
        return False
    return ns[0] == "─" and ns.rstrip()[-1] in _TABLE_CORNERS


def _is_table_border_line(line: str) -> bool:
    """Check if line is a table border (├─, └─, ┌─ patterns)."""
    stripped = line.lstrip()
    if not stripped:
        return False
    return stripped[0] in "├└┌" and "─" in stripped


def _count_expected_pipes(border_line: str) -> int:
    """Count expected │ per data row from a ┌ or ├ border line.

    A border like ``┌──┬──┬──┐`` has 2 ``┬`` → 3 columns → 4 ``│`` per row.
    """
    return border_line.count("┬") + 2


def _parse_column_widths(border_line: str) -> list[int]:
    """Extract column display widths from a ┌ or ├ border line.

    Splits by column separators (┬ or ┼) and counts ``─`` chars per segment.
    Returns a list of column widths (inner content width, not including │).
    """
    stripped = border_line.strip()
    if len(stripped) < 2:
        return []
    inner = stripped[1:-1]  # Remove corner chars (┌/┐ or ├/┤)
    segments = re.split("[┬┼]", inner)
    return [len(seg) for seg in segments]


def _repad_table_row(row: str, col_widths: list[int]) -> str:
    """Re-pad each cell in a table data row to match the column widths.

    Preserves existing left padding and content; only adds right-padding
    so each cell reaches the correct display width from the border.
    """
    parts = row.split("│")
    # parts[0] = indent before first │; parts[-1] = after last │ (empty)
    if len(parts) < 3:
        return row
    indent = parts[0]
    cells = parts[1:-1]
    if len(cells) != len(col_widths):
        return row  # Column count mismatch — leave unchanged
    new_cells = []
    for cell, width in zip(cells, col_widths):
        cell_dw = display_width(cell)
        if cell_dw < width:
            new_cells.append(cell + " " * (width - cell_dw))
        else:
            new_cells.append(cell)
    return indent + "│" + "│".join(new_cells) + "│"


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

@dataclass
class Stats:
    input_lines: int = 0
    output_lines: int = 0
    user_lines_joined: int = 0
    claude_lines_joined: int = 0
    table_borders_fixed: int = 0
    table_cells_fixed: int = 0
    tool_calls_fixed: int = 0
    tool_results_fixed: int = 0
    agent_tree_fixed: int = 0
    bullet_text_joined: int = 0
    plan_text_joined: int = 0
    table_multirow_merged: int = 0
    table_borders_realigned: int = 0
    box_rows_merged: int = 0

    def summary(self) -> str:
        lines = [
            "--- Statistics ---",
            f"  Input lines:          {self.input_lines}",
            f"  Output lines:         {self.output_lines}",
            f"  User lines joined:    {self.user_lines_joined}",
            f"  Claude lines joined:  {self.claude_lines_joined}",
            f"  Table borders fixed:  {self.table_borders_fixed}",
            f"  Table cells fixed:    {self.table_cells_fixed}",
            f"  Table rows merged:    {self.table_multirow_merged}",
            f"  Borders realigned:    {self.table_borders_realigned}",
            f"  Box rows merged:      {self.box_rows_merged}",
            f"  Tool calls fixed:     {self.tool_calls_fixed}",
            f"  Tool results fixed:   {self.tool_results_fixed}",
            f"  Agent tree fixed:     {self.agent_tree_fixed}",
            f"  Bullet text joined:   {self.bullet_text_joined}",
            f"  Plan text joined:     {self.plan_text_joined}",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main processing logic
# ---------------------------------------------------------------------------


def process(lines: list[str], stats: Stats) -> list[str]:
    """Process all *lines* and return the list of fixed output lines."""
    stats.input_lines = len(lines)
    output: list[str] = []
    i = 0
    n = len(lines)

    def peek(offset: int = 1) -> str | None:
        idx = i + offset
        return lines[idx] if idx < n else None

    while i < n:
        line = lines[i]

        # ---------------------------------------------------------------
        # 1) User prompt blocks (❯ at column 0, continuations at dw=76)
        # ---------------------------------------------------------------
        if _USER_PROMPT_RE.match(line):
            i = _process_user_block(lines, i, n, output, stats)
            continue

        # ---------------------------------------------------------------
        # 2) Table border split → join, then enter table region
        # ---------------------------------------------------------------
        next_line = peek()
        if next_line is not None and is_table_border_split(line, next_line):
            acc = raw_join(line, next_line)
            stats.table_borders_fixed += 1
            i += 2
            while i < n and is_table_border_split(acc, lines[i]):
                acc = raw_join(acc, lines[i])
                stats.table_borders_fixed += 1
                i += 1
            output.append(acc)
            # If this was a ┌ border, process the full table body
            if "┌" in acc:
                expected_pipes = _count_expected_pipes(acc)
                col_widths = _parse_column_widths(acc)
                i = _process_table_body(
                    lines, i, n, output, stats, expected_pipes, col_widths,
                )
            continue

        # ---------------------------------------------------------------
        # 2b) Non-split ┌ border → enter table body processor
        # ---------------------------------------------------------------
        stripped_for_border = line.lstrip()
        if (
            stripped_for_border.startswith("┌")
            and "─" in stripped_for_border
            and "┐" in stripped_for_border
        ):
            expected_pipes = _count_expected_pipes(line)
            col_widths = _parse_column_widths(line)
            output.append(line)
            i += 1
            i = _process_table_body(
                lines, i, n, output, stats, expected_pipes, col_widths,
            )
            continue

        # ---------------------------------------------------------------
        # 3) Table cell row (│ in line, outside tracked table region)
        #    Fallback for tables whose ┌ border was not split and was
        #    already emitted before we entered this logic.
        # ---------------------------------------------------------------
        if "│" in line:
            stripped = line.lstrip()
            if stripped.startswith("│") or stripped.endswith("│"):
                # Likely a table row.  Check if PREVIOUS output line was a
                # ┌ or ├ border to determine expected_pipes.
                expected_pipes = 0
                fallback_col_widths: list[int] = []
                for prev in reversed(output):
                    ps = prev.strip()
                    if ps and (ps[0] in "┌├"):
                        expected_pipes = _count_expected_pipes(prev)
                        fallback_col_widths = _parse_column_widths(prev)
                        break
                    if ps and ps[0] not in "│":
                        break
                if expected_pipes > 0:
                    acc = line.rstrip()
                    pipe_count = acc.count("│")
                    i += 1
                    while pipe_count < expected_pipes and i < n:
                        nl = lines[i]
                        if _is_truly_empty(nl):
                            break
                        if _is_table_border_line(nl):
                            break
                        # Check for border split on this line
                        if i + 1 < n and is_table_border_split(nl, lines[i + 1]):
                            break
                        acc = table_cell_join(acc, nl)
                        pipe_count = acc.count("│")
                        stats.table_cells_fixed += 1
                        i += 1
                    if fallback_col_widths:
                        acc = _repad_table_row(acc, fallback_col_widths)
                    output.append(acc)
                    continue

        # ---------------------------------------------------------------
        # 4) Tool call continuation (● Bash(, ● Read(, etc.)
        #    Continuations are 6-space indented.
        # ---------------------------------------------------------------
        if _TOOL_CALL_RE.match(line):
            acc = line
            i += 1
            while i < n:
                nl = lines[i]
                # 6-space continuation (tool call argument wrapping)
                if nl.startswith("      ") and not _is_structural_break(nl):
                    # Strip the 6-char continuation indent, preserving
                    # any additional whitespace from the original.
                    right_part = nl[6:]
                    left_s = acc.rstrip()
                    if right_part and right_part[0] == " ":
                        # Extra space means the original had whitespace
                        # at this position -- preserve it.
                        acc = left_s + right_part
                    elif left_s and _looks_like_mid_word(left_s, right_part):
                        # Mid-word/mid-path split: concatenate directly.
                        acc = left_s + right_part
                    else:
                        # Argument boundary where the space was consumed
                        # by wrapping.  Restore it.
                        acc = left_s + " " + right_part
                    stats.tool_calls_fixed += 1
                    i += 1
                else:
                    break
            output.append(acc)
            continue

        # ---------------------------------------------------------------
        # 5) Tool result continuation (  ⎿  ... at dw>=74)
        # ---------------------------------------------------------------
        if _TOOL_RESULT_RE.match(line):
            last_raw_dw = display_width(line.rstrip())
            acc = line
            i += 1
            # Phase 1: join 5-space continuations of the ⎿ line itself.
            # Only join when the PREVIOUS raw line was near the wrap limit
            # (dw >= 74).  Lines well below the limit ended naturally —
            # subsequent 5-space lines are separate output lines (e.g.
            # git log entries), not wrapped continuations.
            # Character-class check: alpha→lower = mid-word (raw join);
            # all other transitions = word boundary (smart_join).
            while last_raw_dw >= 74 and i < n:
                nl = lines[i]
                if nl.startswith("     ") and not _is_structural_break(nl) and not _is_plan_structural(nl):
                    prev_dw = last_raw_dw
                    last_raw_dw = display_width(nl.rstrip())
                    acc = _dw_aware_join(acc, nl, prev_dw)
                    stats.tool_results_fixed += 1
                    i += 1
                else:
                    break
            # Phase 1 fallback: if ⎿ line ends with trailing space
            # (word-boundary wrap just below the 74 threshold), join
            # short continuation fragments.  This catches lines like
            # "Plan saved to: ... · /plan to " + "edit" (dw=72).
            while i < n and acc != acc.rstrip():
                nl = lines[i]
                if nl.startswith("     ") and not nl.startswith("      "):
                    if _is_plan_continuation_fragment(nl, acc):
                        # Trailing space = word-boundary wrap → smart_join
                        # (not _bullet_join, which would raw-join alpha→lower
                        # like "to" + "edit" → "toedit").
                        acc = smart_join(acc, nl)
                        stats.tool_results_fixed += 1
                        i += 1
                        continue
                break
            output.append(acc)

            # Phase 2: handle remaining tool output lines at 6-space indent.
            # After the ⎿ line, tool output continues at 6-space indent.
            # Each such line may itself be wrapped, with 5-space continuations.
            # We emit each output line individually, joining only its
            # wrapped fragments.
            while i < n:
                nl = lines[i]
                if _is_truly_empty(nl):
                    break
                if _is_structural_break(nl):
                    break
                # Tool output lines use 6-space indent (5-space lines that
                # aren't continuations would be plan text, etc.)
                if not nl.startswith("      ") or nl.startswith("       "):
                    break
                acc2 = nl
                last_raw_dw2 = display_width(nl.rstrip())
                i += 1
                # Join continuations of this output line.
                # Phase 2a: high-dw continuations at 5-6 space indent.
                while last_raw_dw2 >= 74 and i < n:
                    nl2 = lines[i]
                    if nl2.startswith("     ") and not _is_structural_break(nl2) and not _is_plan_structural(nl2):
                        prev_dw2 = last_raw_dw2
                        last_raw_dw2 = display_width(nl2.rstrip())
                        acc2 = _dw_aware_join(acc2, nl2, prev_dw2)
                        stats.tool_results_fixed += 1
                        i += 1
                    else:
                        break
                # Phase 2b: deeper-indented continuations when the
                # output line ends with a continuation signal:
                # - comma (list continuation)
                # - trailing space (word-boundary wrap)
                # - underscore (identifier split, e.g. E2E_PO_BASE_ + URL)
                while i < n:
                    _acc2_s = acc2.rstrip()
                    if not _acc2_s:
                        break
                    _last2 = _acc2_s[-1]
                    _has_trailing = acc2 != _acc2_s
                    if _last2 not in (",", "_") and not _has_trailing:
                        break  # no continuation signal
                    nl2 = lines[i]
                    # Only accept DEEPER-indented continuations (7+ spaces).
                    # Same-indent lines (6 spaces) are sibling entries in the
                    # tool output — e.g. separate diff lines that happen to
                    # have trailing padding spaces.
                    if not nl2.startswith("       ") or _is_structural_break(nl2):
                        break
                    nl2_dw = display_width(nl2.rstrip())
                    if nl2_dw >= 76:
                        break  # full-width = independent line
                    acc2 = smart_join(acc2, nl2)
                    last_raw_dw2 = nl2_dw
                    stats.tool_results_fixed += 1
                    i += 1
                output.append(acc2)
            continue

        # ---------------------------------------------------------------
        # 6) Agent tree continuation (├─ or └─ at 3-space indent)
        # ---------------------------------------------------------------
        if _AGENT_TREE_RE.match(line):
            dw = display_width(line.rstrip())
            acc = line
            i += 1
            if dw >= 70:
                while i < n:
                    nl = lines[i]
                    if _is_structural_break(nl):
                        break
                    nl_stripped = nl.lstrip()
                    # Never join lines that are sub-results (contain ⎿)
                    # or new tree nodes (├─, └─, │)
                    if "⎿" in nl_stripped:
                        break
                    if nl_stripped.startswith("├─") or nl_stripped.startswith("└─"):
                        break
                    if nl_stripped.startswith("│"):
                        break
                    # Same-indent non-structural continuation
                    if nl.startswith("   "):
                        acc = raw_join(acc, nl)
                        stats.agent_tree_fixed += 1
                        i += 1
                    else:
                        break
            output.append(acc)
            continue

        # ---------------------------------------------------------------
        # 7) Claude narrative (● text with dw>=55+, NOT tool call/short marker)
        #    Threshold lowered from 77 to 55 because CJK-heavy lines end
        #    content well before the 77-80 column wrap limit (CJK chars take
        #    2 columns each, so word boundaries fall earlier).
        # ---------------------------------------------------------------
        if _CLAUDE_ACTION_RE.match(line) and not _TOOL_CALL_RE.match(line):
            dw = display_width(line.rstrip())
            acc = line
            i += 1
            if dw >= 55 or _has_continuation_signal(line):
                while i < n:
                    nl = lines[i]
                    if _is_structural_break(nl):
                        break
                    nl_dw = display_width(nl.rstrip())
                    # 2-space continuation, short, not structural
                    if nl.startswith("  ") and not nl.startswith("  ⎿") and nl_dw < 82:
                        nl_stripped = nl.lstrip()
                        if nl_stripped.startswith("- "):
                            break
                        if re.match(r"\d+\. ", nl_stripped):
                            break
                        acc = smart_join(acc, nl)
                        stats.claude_lines_joined += 1
                        i += 1
                    else:
                        break
            output.append(acc)
            continue

        # ---------------------------------------------------------------
        # 7b) Bullet item in Claude response (  - text)
        #     When a bullet line has high dw or ends with a continuation
        #     signal (CJK char, comma, etc.), its wrapped continuation
        #     on the next line (2-space indent, NOT a bullet/numbered)
        #     must be joined.  Uses _bullet_join to handle mid-word
        #     breaks (e.g. "RiskModelAss" + "ignment") correctly.
        # ---------------------------------------------------------------
        if _BULLET_RE.match(line):
            dw = display_width(line.rstrip())
            acc = line
            i += 1
            if dw >= 55 or _has_continuation_signal(line) or _has_unclosed_bracket(line):
                while i < n:
                    nl = lines[i]
                    if not _is_continuation_fragment(nl, acc):
                        break
                    acc = _bullet_join(acc, nl)
                    stats.bullet_text_joined += 1
                    i += 1
            # Peek-ahead for plan-context bullets (5+ space indent).
            # Short plan bullets (dw < 55) whose text wraps to the base
            # 5-space indent won't enter the join loop above.  Check if
            # the next line is a non-structural 5-space continuation.
            elif line.startswith("     ") and i < n:
                nl = lines[i]
                if (
                    nl.startswith("     ")
                    and not _is_structural_break(nl)
                    and not _is_plan_structural(nl)
                ):
                    nl_dw = display_width(nl.rstrip())
                    if nl_dw < 70:
                        acc = smart_join(acc, nl)
                        stats.bullet_text_joined += 1
                        i += 1
            output.append(acc)
            continue

        # ---------------------------------------------------------------
        # 8) Numbered list item in Claude response (  N. text)
        # ---------------------------------------------------------------
        if _NUMBERED_RE.match(line):
            dw = display_width(line.rstrip())
            acc = line
            i += 1
            if dw >= 55 or _has_continuation_signal(line):
                while i < n:
                    nl = lines[i]
                    if _is_structural_break(nl):
                        break
                    # Numbered list continuation is at 2-space indent
                    if nl.startswith("  ") and not nl.startswith("  ⎿"):
                        nl_stripped = nl.lstrip()
                        if nl_stripped.startswith("- "):
                            break
                        if re.match(r"\d+\. ", nl_stripped):
                            break
                        dw_nl = display_width(nl.rstrip())
                        if dw_nl < 82:
                            acc = _bullet_join(acc, nl)
                            stats.claude_lines_joined += 1
                            i += 1
                        else:
                            break
                    else:
                        break
            # Peek-ahead for plan-context numbered items (5+ space indent).
            elif line.startswith("     ") and i < n:
                nl = lines[i]
                if (
                    nl.startswith("     ")
                    and not _is_structural_break(nl)
                    and not _is_plan_structural(nl)
                ):
                    nl_dw = display_width(nl.rstrip())
                    if nl_dw < 70:
                        acc = _bullet_join(acc, nl)
                        stats.claude_lines_joined += 1
                        i += 1
            output.append(acc)
            continue

        # ---------------------------------------------------------------
        # 8c) Claude paragraph text (2-space indent, standalone)
        #     Text paragraphs within Claude response blocks that aren't
        #     preceded by a ● marker — they appear after tables, bullet
        #     lists, or between structural elements.
        #
        #     DESIGN: Instead of measuring the current line's dw to guess
        #     whether it was wrapped (fragile threshold), we examine the
        #     NEXT line via _is_continuation_fragment() to decide whether
        #     it is a new item or a continuation of the current paragraph.
        # ---------------------------------------------------------------
        if line.startswith("  ") and not line.startswith("     "):
            acc = line
            i += 1
            # Skip column-layout lines (side-by-side comparison format).
            _content = line.strip()
            if "        " not in _content:  # 8+ internal spaces = layout
                while i < n:
                    nl = lines[i]
                    if _is_continuation_fragment(nl, acc):
                        acc = _bullet_join(acc, nl)
                        stats.claude_lines_joined += 1
                        i += 1
                    else:
                        break
            output.append(acc)
            continue

        # ---------------------------------------------------------------
        # 9) Plan / indented text (5+ space indent)
        #
        #    DESIGN: Like step 8c, uses next-line look-ahead via
        #    _is_plan_continuation_fragment() instead of dw thresholds.
        #    The join function (_dw_aware_join) still uses the last
        #    segment's dw to decide mid-word vs word-boundary joins.
        # ---------------------------------------------------------------
        if line.startswith("     "):
            acc = line
            last_seg_dw = display_width(line.rstrip())
            i += 1
            while i < n:
                nl = lines[i]
                if _is_plan_continuation_fragment(nl, acc):
                    prev_dw = last_seg_dw
                    last_seg_dw = display_width(nl.rstrip())
                    acc = _dw_aware_join(acc, nl, prev_dw)
                    stats.plan_text_joined += 1
                    i += 1
                else:
                    break
            output.append(acc)
            continue

        # ---------------------------------------------------------------
        # 10) Default: emit as-is
        # ---------------------------------------------------------------
        output.append(line)
        i += 1

    # Post-processing: merge multi-row table cells.
    # After the main loop, each physical data row is complete (correct pipe
    # count, re-padded).  But a single logical row may still span multiple
    # physical rows when Claude wrapped cell content at column width.
    # This pass collapses those into one row per logical cell.
    output = _merge_multirow_table_cells(output, stats)

    # Post-processing: realign table borders.
    # After merging, merged data rows may exceed original column widths.
    # This pass recalculates border widths to match the widest data cells.
    output = _realign_table_borders(output, stats)

    # Post-processing: merge wrapped text within single-column box items.
    # Single-column boxes (exactly 2 │ per row) contain numbered/bulleted
    # items that may wrap across multiple rows.  This pass merges continuation
    # lines back into their parent item.
    output = _merge_singlecol_box_rows(output, stats)

    stats.output_lines = len(output)
    return output


# ---------------------------------------------------------------------------
# Post-processing: multi-row table cell merge
# ---------------------------------------------------------------------------

def _is_table_data_row(stripped: str) -> bool:
    """Check if *stripped* (leading-whitespace-removed) is a multi-column table data row.

    A data row starts and ends with ``│`` and contains no ``─`` (which
    would make it a border row).  Requires at least 3 ``│`` (i.e. 2+
    columns) so that single-column boxes (which have only 2 ``│``)
    are excluded — their rows are independent items, not wrapped cells.
    """
    return (
        len(stripped) >= 5
        and stripped[0] == "│"
        and stripped[-1] == "│"
        and "─" not in stripped
        and stripped.count("│") >= 3
    )


def _merge_multirow_table_cells(lines: list[str], stats: Stats) -> list[str]:
    """Collapse consecutive table data rows into single logical rows.

    Between border/separator rows (``┌├└``), Claude may emit multiple
    physical data rows for one logical row when cell content exceeds the
    column width.  This function detects such groups and merges them,
    joining cell content with ``_table_cell_content_join`` which handles
    mid-word and CJK boundaries.
    """
    result: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.lstrip()

        if not _is_table_data_row(stripped):
            result.append(line)
            i += 1
            continue

        # Collect consecutive data rows (same table region).
        group = [line]
        j = i + 1
        while j < n:
            next_stripped = lines[j].lstrip()
            if _is_table_data_row(next_stripped):
                group.append(lines[j])
                j += 1
            else:
                break

        if len(group) == 1:
            result.append(line)
            i = j
            continue

        # Multiple physical rows → merge into one logical row.
        merged = _merge_row_group(group, stats)
        result.append(merged)
        i = j

    return result


def _merge_row_group(rows: list[str], stats: Stats) -> str:
    """Merge a group of physical table data rows into one logical row."""
    first = rows[0]
    indent = first[: len(first) - len(first.lstrip())]

    # Split each row into cell contents — keep both raw and stripped forms.
    # The raw form preserves trailing spaces, which we use to detect whether
    # the content filled the entire column (≤1 trailing space → mid-word split).
    all_cells: list[list[str]] = []
    all_raw: list[list[str]] = []
    for row in rows:
        parts = row.strip().split("│")
        # parts[0] is empty (before first │), parts[-1] is empty (after last │)
        raw_cells = parts[1:-1]
        cells = [c.strip() for c in raw_cells]
        all_cells.append(cells)
        all_raw.append(raw_cells)

    num_cols = max(len(cells) for cells in all_cells)

    # Merge each column's fragments.
    merged_cells: list[str] = []
    for col_idx in range(num_cols):
        fragments: list[str] = []
        raw_fragments: list[str] = []
        for row_idx, row_cells in enumerate(all_cells):
            if col_idx < len(row_cells) and row_cells[col_idx]:
                fragments.append(row_cells[col_idx])
                raw_fragments.append(all_raw[row_idx][col_idx])

        if not fragments:
            merged_cells.append("")
        elif len(fragments) == 1:
            merged_cells.append(fragments[0])
        else:
            acc = fragments[0]
            for k in range(1, len(fragments)):
                # Determine if the previous fragment filled its column.
                prev_raw = raw_fragments[k - 1]
                trailing_spaces = len(prev_raw) - len(prev_raw.rstrip())
                left_filled = trailing_spaces <= 1
                acc = _table_cell_content_join(
                    acc, fragments[k], left_filled=left_filled
                )
            merged_cells.append(acc)

    # Reconstruct the row with 1-space padding per cell.
    cell_parts = [f" {cell} " if cell else "  " for cell in merged_cells]
    merged = indent + "│" + "│".join(cell_parts) + "│"

    stats.table_multirow_merged += len(rows) - 1
    return merged


# ---------------------------------------------------------------------------
# Post-processing: merge wrapped text within single-column box items
# ---------------------------------------------------------------------------

def _is_singlecol_data_row(line: str) -> bool:
    """Check if *line* is a single-column box data row.

    A single-column data row starts and ends with ``│``, has exactly 2
    ``│`` characters, and contains no ``─`` (which would indicate a border).
    """
    stripped = line.lstrip()
    return (
        len(stripped) >= 3
        and stripped[0] == "│"
        and stripped[-1] == "│"
        and "─" not in stripped
        and stripped.count("│") == 2
    )


def _is_singlecol_border(line: str) -> bool:
    """Check if *line* is a single-column box border (┌─┐, ├─┤, or └─┘)."""
    stripped = line.lstrip()
    if not stripped:
        return False
    return (
        stripped[0] in "┌├└"
        and "─" in stripped
        and stripped[-1] in "┐┤┘"
        and "┬" not in stripped
        and "┼" not in stripped
        and "┴" not in stripped
    )


_ITEM_START_RE = re.compile(r"^\s*\d+\.\s")
_BULLET_START_RE = re.compile(r"^\s*[-*]\s")


def _merge_singlecol_box_rows(lines: list[str], stats: Stats) -> list[str]:
    """Merge wrapped text within single-column box items.

    Single-column boxes (2 ``│`` per row) contain numbered/bulleted items
    that may wrap across multiple rows.  This function merges continuation
    lines back into their parent item while keeping separate items on
    separate rows.

    Title boxes (a single data row between borders) are left untouched.
    """
    result: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        # Look for the start of a single-column box (┌ border with no ┬).
        if not _is_singlecol_border(line) or not line.lstrip().startswith("┌"):
            result.append(line)
            i += 1
            continue

        # Found a ┌ border.  Collect the entire box (border + data + └).
        box_lines: list[str] = [line]
        j = i + 1
        found_close = False
        while j < n:
            if _is_singlecol_data_row(lines[j]):
                box_lines.append(lines[j])
                j += 1
            elif _is_singlecol_border(lines[j]):
                box_lines.append(lines[j])
                if lines[j].lstrip().startswith("└"):
                    found_close = True
                    j += 1
                    break
                elif lines[j].lstrip().startswith("├"):
                    j += 1
                else:
                    j += 1
                    break
            else:
                break  # Non-box line — box ended unexpectedly

        if not found_close:
            # Incomplete box — emit as-is.
            for bl in box_lines:
                result.append(bl)
            i = j
            continue

        # Extract data rows (skip borders).
        data_indices = [
            idx for idx, bl in enumerate(box_lines) if _is_singlecol_data_row(bl)
        ]

        # Title boxes: single data row between borders → skip merging.
        if len(data_indices) <= 1:
            for bl in box_lines:
                result.append(bl)
            i = j
            continue

        # Group data rows into logical items and merge continuations.
        data_rows = [box_lines[idx] for idx in data_indices]
        merged_contents = _merge_box_items(data_rows, stats)

        # Determine whether box borders need to grow.
        indent = line[: len(line) - len(line.lstrip())]

        # Get current box inner width from the ┌ border.
        top_border = line.lstrip()
        border_inner_dw = display_width(top_border) - 2

        # Compute max content width after merge.
        max_content_dw = 0
        for content in merged_contents:
            # Content needs 2 spaces padding (1 left + 1 right minimum).
            content_dw = display_width(content) + 2
            max_content_dw = max(max_content_dw, content_dw)

        new_inner_width = max(border_inner_dw, max_content_dw)

        # Rebuild the box: borders + merged data rows.
        # Emit ┌ border (potentially wider).
        result.append(
            _rebuild_singlecol_border(top_border, new_inner_width, indent)
        )

        # Emit merged data rows.
        for content in merged_contents:
            padded = _pad_singlecol_content(
                " " + content + " ", new_inner_width,
            )
            result.append(indent + "│" + padded + "│")

        # Emit any ├ and └ borders (potentially wider).
        for idx, bl in enumerate(box_lines):
            if idx == 0:
                continue  # Already emitted ┌
            stripped_bl = bl.lstrip()
            if stripped_bl and stripped_bl[0] in "├└" and "─" in stripped_bl:
                result.append(
                    _rebuild_singlecol_border(stripped_bl, new_inner_width, indent)
                )

        i = j

    return result


def _merge_box_items(
    data_rows: list[str], stats: Stats,
) -> list[str]:
    """Merge continuation rows within each logical item of a single-column box.

    Returns a list of merged content strings (one per logical item).
    """
    # Parse content from each row (strip │ and whitespace).
    contents: list[str] = []
    for row in data_rows:
        stripped = row.lstrip()
        inner = stripped[1:-1]  # Remove │ ... │
        contents.append(inner.strip())

    # Group into logical items.
    items: list[list[str]] = []
    for content in contents:
        if _ITEM_START_RE.match(content) or _BULLET_START_RE.match(content):
            items.append([content])
        elif not items:
            items.append([content])
        else:
            items[-1].append(content)

    # Merge fragments within each item.
    merged: list[str] = []
    for fragments in items:
        if len(fragments) == 1:
            merged.append(fragments[0])
        else:
            acc = fragments[0]
            for frag in fragments[1:]:
                acc = _table_cell_content_join(acc, frag)
                stats.box_rows_merged += 1
            merged.append(acc)

    return merged


def _pad_singlecol_content(content: str, inner_width: int) -> str:
    """Pad content to fill *inner_width* display columns inside a box."""
    content_dw = display_width(content)
    if content_dw >= inner_width:
        return content
    return content + " " * (inner_width - content_dw)


def _rebuild_singlecol_border(
    stripped: str, inner_width: int, indent: str,
) -> str:
    """Rebuild a single-column box border to the given inner width.

    Preserves styled headers like ``┌─── Title ───┐`` by detecting
    embedded text and re-centering it.
    """
    left_corner = stripped[0]
    right_corner = stripped[-1]

    # Check for embedded title text (e.g., ┌─── Pre-Suite ───┐).
    inner = stripped[1:-1]
    title_match = re.search(r"([^─]+)", inner)
    if title_match:
        title_text = title_match.group(1).strip()
        if title_text:
            # Styled header border: ─── Title ───
            title_with_spaces = f" {title_text} "
            title_dw = display_width(title_with_spaces)
            remaining = inner_width - title_dw
            left_dashes = max(remaining // 2, 3)
            right_dashes = max(remaining - left_dashes, 3)
            return (
                indent
                + left_corner
                + "─" * left_dashes
                + title_with_spaces
                + "─" * right_dashes
                + right_corner
            )

    # Plain border (all ─).
    return indent + left_corner + "─" * inner_width + right_corner


# ---------------------------------------------------------------------------
# Post-processing: realign table borders after multi-row merge
# ---------------------------------------------------------------------------

def _realign_table_borders(lines: list[str], stats: Stats) -> list[str]:
    """Recalculate border widths to match (potentially wider) merged data rows.

    After ``_merge_multirow_table_cells`` collapses multi-row cells, the
    merged content may exceed the original column widths encoded in the
    border rows.  This pass:

    1. Identifies contiguous table *regions* (runs of border + data rows).
    2. For each region, computes the maximum display-width per column
       across all data rows.
    3. Regenerates every border row with the correct ``─`` widths.
    4. Re-pads every data row so cells align with the new borders.
    """
    result: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.lstrip()

        # Detect start of a table region (┌ border).
        if stripped.startswith("┌") and "─" in stripped and "┐" in stripped:
            # Collect every line in this table region.
            region_start = i
            region: list[str] = [line]
            i += 1
            while i < n:
                s = lines[i].lstrip()
                if _is_table_data_row(s):
                    region.append(lines[i])
                    i += 1
                elif s and s[0] in "├└" and "─" in s:
                    region.append(lines[i])
                    i += 1
                    if s[0] == "└":
                        break  # End of table
                else:
                    break  # Non-table line — region ended unexpectedly

            realigned = _realign_table_region(region, stats)
            result.extend(realigned)
            continue

        result.append(line)
        i += 1

    return result


def _realign_table_region(region: list[str], stats: Stats) -> list[str]:
    """Realign borders and data rows within a single table region."""
    # Separate border and data rows; determine indent from first line.
    first = region[0]
    indent = first[: len(first) - len(first.lstrip())]

    # Collect data rows and their per-cell display widths.
    data_rows: list[tuple[int, list[str]]] = []  # (index, cells)
    border_indices: list[int] = []

    for idx, row in enumerate(region):
        stripped = row.lstrip()
        if _is_table_data_row(stripped):
            parts = stripped.split("│")
            # parts[0] = '' (before first │), parts[-1] = '' (after last │)
            cells = parts[1:-1]
            data_rows.append((idx, cells))
        elif stripped and stripped[0] in "┌├└":
            border_indices.append(idx)

    if not data_rows:
        return region  # No data rows — nothing to realign

    # Determine column count from data rows.
    num_cols = max(len(cells) for _, cells in data_rows)
    if num_cols == 0:
        return region

    # Compute max display-width per column across all data rows.
    # Each cell has 1-space padding on each side, so content width is what
    # we see between the padding.  But we measure the full cell (including
    # padding) to get the column width that the border must span.
    max_widths: list[int] = [0] * num_cols
    for _, cells in data_rows:
        for col_idx, cell in enumerate(cells):
            if col_idx < num_cols:
                cw = display_width(cell)
                if cw > max_widths[col_idx]:
                    max_widths[col_idx] = cw

    # Ensure minimum width of 3 (1 space + 1 char + 1 space).
    max_widths = [max(w, 3) for w in max_widths]

    # Check if any realignment is needed by comparing with current border.
    current_widths = _parse_column_widths(region[border_indices[0]])
    if current_widths == max_widths:
        return region  # Already aligned

    # Rebuild the region.
    rebuilt: list[str] = []
    for idx, row in enumerate(region):
        stripped = row.lstrip()
        if idx in border_indices:
            rebuilt.append(_rebuild_border(stripped[0], stripped[-1], max_widths, indent))
            stats.table_borders_realigned += 1
        elif _is_table_data_row(stripped):
            rebuilt.append(_repad_table_row_to_widths(row, max_widths, indent))
        else:
            rebuilt.append(row)

    return rebuilt


def _rebuild_border(
    left_corner: str, right_corner: str, col_widths: list[int], indent: str,
) -> str:
    """Build a border row from corner chars and column widths.

    Maps corner pairs:
      ┌ ┐ → separator ┬
      ├ ┤ → separator ┼
      └ ┘ → separator ┴
    """
    sep_map = {"┌": "┬", "├": "┼", "└": "┴"}
    separator = sep_map.get(left_corner, "┼")
    segments = ["─" * w for w in col_widths]
    return indent + left_corner + separator.join(segments) + right_corner


def _repad_table_row_to_widths(
    row: str, col_widths: list[int], indent: str,
) -> str:
    """Re-pad a data row so each cell matches the given column widths."""
    stripped = row.lstrip()
    parts = stripped.split("│")
    if len(parts) < 3:
        return row
    cells = parts[1:-1]
    if len(cells) != len(col_widths):
        return row  # Column count mismatch — leave unchanged

    new_cells: list[str] = []
    for cell, width in zip(cells, col_widths):
        # Strip existing padding, then re-pad.
        content = cell.strip()
        content_dw = display_width(content)
        # Target: 1 space left + content + right padding to fill width.
        # Total cell display-width must equal `width`.
        # Cell = " " + content + " " * (width - 1 - content_dw)
        # But if content_dw + 2 > width, just use " content " (overflow).
        if content:
            right_pad = max(width - 1 - content_dw, 1)
            new_cells.append(" " + content + " " * right_pad)
        else:
            new_cells.append(" " * width)

    return indent + "│" + "│".join(new_cells) + "│"


def _process_table_body(
    lines: list[str],
    start: int,
    n: int,
    output: list[str],
    stats: Stats,
    expected_pipes: int,
    col_widths: list[int] | None = None,
) -> int:
    """Process lines inside a table body (after ┌ border, until └ border).

    Uses pipe-count accumulation: each data row is accumulated until the
    ``│`` count reaches *expected_pipes*, then emitted.  Border lines
    (├─, └─) are emitted directly (with split joining if needed).

    When *col_widths* is provided, each completed data row is re-padded
    so every cell matches the column width from the border.

    Returns the next line index to process after the table ends.
    """
    i = start
    while i < n:
        line = lines[i]

        # --- Empty line: table ended unexpectedly ---
        if _is_truly_empty(line):
            break

        # --- Border line (├ or └): join splits, emit, maybe exit ---
        stripped = line.lstrip()
        if stripped and stripped[0] in "├└" and "─" in stripped:
            acc = line
            i += 1
            # Join border split if needed
            if acc.rstrip()[-1] == "─" and i < n:
                nl = lines[i]
                ns = nl.lstrip()
                if ns and ns[0] == "─" and ns.rstrip()[-1] in _TABLE_CORNERS:
                    acc = raw_join(acc, nl)
                    stats.table_borders_fixed += 1
                    i += 1
                    while i < n and is_table_border_split(acc, lines[i]):
                        acc = raw_join(acc, lines[i])
                        stats.table_borders_fixed += 1
                        i += 1
            output.append(acc)
            # └ border: table ends
            if "└" in acc:
                return i
            continue

        # --- Data row: accumulate until pipe count matches ---
        if "│" in line or (stripped and stripped[-1] == "│"):
            acc = line.rstrip()
            pipe_count = acc.count("│")
            i += 1
            while pipe_count < expected_pipes and i < n:
                nl = lines[i]
                if _is_truly_empty(nl):
                    break
                # Stop at border lines
                nl_s = nl.lstrip()
                if nl_s and nl_s[0] in "├└┌" and "─" in nl_s:
                    break
                acc = table_cell_join(acc, nl)
                pipe_count = acc.count("│")
                stats.table_cells_fixed += 1
                i += 1
            # Re-pad cells to match column widths from border
            if col_widths:
                acc = _repad_table_row(acc, col_widths)
            output.append(acc)
            continue

        # --- Non-table line (shouldn't happen but be safe) ---
        output.append(line)
        i += 1

    return i


def _process_user_block(
    lines: list[str],
    start: int,
    n: int,
    output: list[str],
    stats: Stats,
) -> int:
    """Process a user prompt block starting at *start*.

    User blocks begin with ``❯ `` and continue with lines that have
    display_width == 76 (right-padded with trailing spaces).  All content
    lines in the block share this fixed width.

    Within the block:
    - Blank lines (76 spaces) are paragraph separators.
    - Lines whose stripped content starts with ``- `` are bullet items.
    - Lines whose stripped content starts with ``\\d+. `` are numbered items.
    - ````` ``` ````` toggles code-fence mode (content preserved as-is).
    - Everything else is a continuation of the current paragraph/item.

    Returns the index of the first line AFTER the block.
    """
    acc = lines[start]
    i = start + 1

    # Check if the first line itself is at dw=76 (padded).
    first_dw = display_width(lines[start])
    if first_dw != 76:
        # Short user prompt, no wrapping.  Emit as-is.
        output.append(acc)
        return i

    in_code_fence = False

    while i < n:
        line = lines[i]
        dw = display_width(line)

        # The user block boundary: ALL lines inside have dw==76.
        if dw != 76:
            break

        stripped = line.rstrip()

        # --- Code fence toggle ---
        # Detect ``` anywhere in the stripped content.
        if stripped.lstrip().startswith("```"):
            # Flush current accumulator before the fence marker.
            if acc:
                output.append(acc)
                acc = ""
            output.append(line)
            in_code_fence = not in_code_fence
            i += 1
            continue

        # Inside code fences: emit lines as-is (no joining).
        if in_code_fence:
            output.append(line)
            i += 1
            continue

        # --- Blank line (paragraph separator) ---
        if not stripped:
            if acc:
                output.append(acc)
                acc = ""
            output.append("")
            i += 1
            continue

        # --- Structural item detection ---
        content_no_indent = stripped.lstrip()

        # Bullet: stripped content starts with "- "
        is_bullet = content_no_indent.startswith("- ")

        # Numbered list: stripped content starts with digit+". "
        is_numbered = bool(re.match(r"\d+\. ", content_no_indent))

        if is_bullet or is_numbered:
            # Start a new logical line for this item.
            if acc:
                output.append(acc)
            acc = line
            i += 1
            continue

        # --- Normal continuation ---
        if acc:
            # Extract the content portion (skip the 2-space continuation
            # indent that the export prepends).
            join_content = stripped[2:] if stripped.startswith("  ") else stripped
            acc = smart_join(acc, join_content)
            stats.user_lines_joined += 1
        else:
            # After a paragraph break (acc was reset to ""), this is the
            # first line of a new paragraph.
            acc = line
        i += 1

    # Flush remaining accumulated text.
    if acc:
        output.append(acc)

    return i


# ---------------------------------------------------------------------------
# Marker-count verification
# ---------------------------------------------------------------------------

def _count_markers(lines: list[str]) -> dict[str, int]:
    """Count occurrences of structural markers."""
    counts: dict[str, int] = {"●": 0, "❯": 0, "✻": 0}
    for line in lines:
        for marker in counts:
            if line.startswith(marker):
                counts[marker] += 1
    return counts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fix broken line wrapping in Claude Code export files.",
    )
    parser.add_argument("input", type=Path, help="Input .txt file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output path (default: <input-stem>-fixed.txt)",
    )
    parser.add_argument(
        "--stats", action="store_true", help="Print statistics to stderr"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Process without writing output file",
    )
    args = parser.parse_args()

    input_path: Path = args.input.resolve()
    if not input_path.is_file():
        print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    if args.output is not None:
        output_path: Path = args.output.resolve()
    else:
        output_path = input_path.with_stem(input_path.stem + "-fixed")

    if output_path == input_path:
        print(
            "ERROR: Output path must differ from input path. "
            "Use -o to specify a different output file.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Read input (strict UTF-8, no fallback).
    text = input_path.read_text(encoding="utf-8", errors="strict")
    raw_lines = text.split("\n")
    # Remove trailing empty element from final newline (if present).
    if raw_lines and raw_lines[-1] == "":
        raw_lines.pop()

    stats = Stats()
    result = process(raw_lines, stats)

    # ---------------------------------------------------------------
    # Safety: marker-count verification
    # ---------------------------------------------------------------
    input_markers = _count_markers(raw_lines)
    output_markers = _count_markers(result)
    for marker, in_count in input_markers.items():
        out_count = output_markers.get(marker, 0)
        if in_count != out_count:
            print(
                f"WARNING: Marker '{marker}' count mismatch: "
                f"input={in_count}, output={out_count}",
                file=sys.stderr,
            )

    # Safety: runaway join detection
    for idx, line in enumerate(result):
        if display_width(line) > 500:
            print(
                f"WARNING: Line {idx + 1} has display width "
                f"{display_width(line)} (>500) — possible runaway join",
                file=sys.stderr,
            )

    # ---------------------------------------------------------------
    # Output
    # ---------------------------------------------------------------
    if args.dry_run:
        print(
            f"Dry run complete. Would write {len(result)} lines to {output_path}",
            file=sys.stderr,
        )
    else:
        output_path.write_text(
            "\n".join(result) + "\n", encoding="utf-8", errors="strict"
        )
        print(f"Written: {output_path}", file=sys.stderr)

    if args.stats:
        print(stats.summary(), file=sys.stderr)


if __name__ == "__main__":
    main()