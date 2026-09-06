#!/usr/bin/env python3
"""
Dictionary Processor - Stage 1: Dictionary-based Text Corrections

SINGLE RESPONSIBILITY: Apply dictionary and regex-based corrections to text

Features:
- Apply simple dictionary replacements
- Apply context-aware regex rules
- Track all changes for history
- Case-sensitive and insensitive matching
"""

from __future__ import annotations

import re
import sys
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional, TypeAlias
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.common_words import ALL_COMMON_WORDS, is_likely_valid_phrase
from core.protected_spans import mask_speaker_labels, restore_speaker_labels

logger = logging.getLogger(__name__)

# Word-boundary segmenter for match-time safety check 3 (see straddles_word_boundary).
# jieba is already a declared dependency of the Stage 1 entrypoint (the 4+ char
# real-word guard uses it), so this adds no install cost; it is loaded lazily
# because building its prefix dictionary costs about a second and --list/--add
# never need it.
_SEGMENTER = None
_SEGMENTER_UNAVAILABLE = False
# Characters of context handed to the segmenter on each side of a match: wide
# enough for the longest ordinary word to complete on either side, narrow
# enough that a distant garble cannot reshape the tokens around this one.
_STRADDLE_WINDOW = 8


def _get_segmenter():
    """Lazy jieba loader; None when jieba is not importable (the check then no-ops)."""
    global _SEGMENTER, _SEGMENTER_UNAVAILABLE
    if _SEGMENTER is None and not _SEGMENTER_UNAVAILABLE:
        try:
            import jieba
            jieba.setLogLevel(logging.ERROR)  # silence "Building prefix dict..."
            _SEGMENTER = jieba
        except ImportError:
            _SEGMENTER_UNAVAILABLE = True
    return _SEGMENTER


def straddles_word_boundary(text: str, pos: int, match: str) -> bool:
    """True when the match at ``pos`` is a fragment of real words, not a mishearing.

    Two rules, chosen by script. For a pure-ASCII match (letters, digits,
    spaces or punctuation — ``Cloud Code`` included) the question is the
    classic word boundary: an ASCII *letter* immediately before or after
    the match means the match is inside a longer word (``Cloud`` in ``iCloud``,
    ``Joe`` in ``Joey``); digits do not count, so ``cloud3`` and ``fiber5``
    still correct. For anything containing CJK, a dictionary-only jieba cut of
    the neighbourhood (HMM off, so nothing is invented) decides: the match is
    refused only when EVERY segment overlapping it is a multi-character
    dictionary word AND at least one of them crosses a match boundary — 新一
    inside 更新|一下, 下电 inside 楼下|电动车, 问题记 inside 问题|记录, 同龄
    inside 同龄人. One single-character segment anywhere under the match
    (巨|神智|能, 章|伟大|概, 叫|新|一下|单) is what an unknown fragment looks
    like, so those pass through to risk scoring unchanged; so does a match that
    is exactly one segment. The remaining blind spot is a real mishearing whose
    neighbours complete whole words on both sides; safe mode only ever deferred
    that class, the native read-through still owns it, and ``--apply-all``
    switches the check off. A context rule skips the check but is still risk
    scored, so in safe mode it is deferred rather than applied.
    """
    if not match:
        return False
    if match.isascii():
        before = text[pos - 1] if pos > 0 else ""
        after = text[pos + len(match)] if pos + len(match) < len(text) else ""
        return before.isascii() and before.isalpha() or after.isascii() and after.isalpha()
    seg = _get_segmenter()
    if seg is None:
        return False
    start = max(0, pos - _STRADDLE_WINDOW)
    end = min(len(text), pos + len(match) + _STRADDLE_WINDOW)
    window = text[start:end]
    rel_start = pos - start
    rel_end = rel_start + len(match)
    cursor = 0
    crossing = False
    for token in seg.lcut(window, HMM=False):
        token_end = cursor + len(token)
        overlaps = cursor < rel_end and token_end > rel_start
        if overlaps:
            if len(token) < 2:
                return False
            if cursor < rel_start or token_end > rel_end:
                crossing = True
        cursor = token_end
        if cursor >= rel_end:
            break
    return crossing


# Frontmatter fields whose values are correction LEDGERS (e.g. `asr_note`
# records the correction history as "旧形→正确形" lists). The old forms quoted
# there are intentional citations, and Stage 1 must not match them — otherwise
# every re-run re-fires on the ledger itself, and each safe-mode deferral
# auto-enqueues a phantom review item whose accept would corrupt the ledger
# (2026-08-17: one asr_note line → 18 phantom matches + 9 phantom enqueues
# that had to be resolved kept_original by hand). Keywords/frontmatter fields
# NOT in this list (e.g. `keywords:`) are still processed — metadata is a
# search surface too.
_LEDGER_FRONTMATTER_KEYS = ("asr_note",)
# Sentinel anchoring contains no matcher-visible padding: a transcript body can
# legitimately contain □ (checkbox glyph / illegible-speech convention), and a
# rule for that symbol must never disable ledger protection.
_LEDGER_PREFIX = "⟪TFLEDGER"
LedgerSpan: TypeAlias = tuple[str, str]


def _mask_ledger_spans(text: str) -> Tuple[str, List[LedgerSpan]]:
    """Mask ledger-field values in a leading YAML frontmatter block.

    Returns (masked_text, [(sentinel, original_value), ...]) in document
    order. Each masked value becomes a unique sentinel. The projection need not
    preserve columns: Change.line_number counts newlines, and restore locates
    the sentinel rather than an absolute offset. Only the value
    portion of a single-line `key: value` is masked. Multi-line YAML values
    (`asr_note: |` / `>` / folded, optionally with a trailing `# comment`)
    are deliberately SKIPPED — no span is recorded and nothing is masked,
    because masking only the 1-char block indicator would be protection
    theatre while the continuation lines stay live; the convention (SKILL.md)
    is single-line ledgers. Text without a leading `---` block (a leading
    UTF-8 BOM is tolerated) returns unchanged with an empty span list.
    """
    lines = text.split("\n")
    if not lines or lines[0].lstrip("﻿").strip() != "---":
        return text, []
    close_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            close_idx = i
            break
    if close_idx is None:
        return text, []
    marker_prefix = _LEDGER_PREFIX
    while marker_prefix in text:
        marker_prefix += "X"
    spans: List[LedgerSpan] = []
    for i in range(1, close_idx):
        line = lines[i]
        m = re.match(r"^([A-Za-z_][\w-]*):\s+(.*)$", line)
        if not m or m.group(1) not in _LEDGER_FRONTMATTER_KEYS:
            continue
        value = m.group(2)
        if not value:
            continue
        # Block-scalar / folded values (any `|`/`>`-led form: bare, chomping
        # or explicit-indent indicators, trailing comments/whitespace) have
        # their ledger on the following indented lines — out of this masker's
        # reach. Skip honestly, with a warning. The match is deliberately
        # over-broad: a single-line value starting with | or > is invalid YAML
        # anyway, and over-skipping degrades protection while under-matching
        # would corrupt the citation — degrading is the safe direction.
        if value[0] in ("|", ">"):
            logger.warning(
                "frontmatter %s uses a multi-line value; ledger masking "
                "skipped for it (single-line convention — see SKILL.md)",
                m.group(1),
            )
            continue
        sentinel = f"{marker_prefix}{len(spans)}⟫"
        masked_value = sentinel
        spans.append((sentinel, value))
        lines[i] = line[: m.start(2)] + masked_value
    if not spans:
        return text, []
    return "\n".join(lines), spans


def _restore_ledger_spans(text: str, spans: List[LedgerSpan]) -> str:
    """Splice masked ledger values back, located by each span's sentinel — not
    by filler runs or absolute position, so natural □ in the body and
    length-changing corrections elsewhere cannot shift the anchor. Fail-
    closed: a missing/damaged sentinel means the pipeline mangled
    the mask, and returning silently would ship a corrupted file."""
    out = text
    # splice from the last span so earlier sentinels keep their positions
    for idx in range(len(spans) - 1, -1, -1):
        sentinel, value = spans[idx]
        occurrences = out.count(sentinel)
        if occurrences != 1:
            raise ValueError(
                "ledger mask restore: sentinel altered or duplicated "
                f"({sentinel!r}: expected once, found {occurrences}) — "
                "refusing to ship a corrupted file"
            )
        pos = out.find(sentinel)
        out = out[:pos] + value + out[pos + len(sentinel) :]
    return out


def reveal_ledger_values_for_reporting(
    text: str,
    spans: List[LedgerSpan],
) -> str:
    """Reveal ledger markers in a chunk/report without validating position.

    Final output restoration uses the strict checks above. Change extraction
    works on fragments, so it needs a display projection that keeps internal
    markers out of reports, history, and learning examples.
    """
    revealed = text
    for sentinel, value in spans:
        revealed = revealed.replace(sentinel, value)
    return revealed


def project_without_ledger_values(text: str) -> str:
    """Return a scan projection with single-line ledger values removed.

    Matchers that only need line numbers must not scan the ledger's old-form
    citations or Stage 1's reversible sentinel. This
    projection reuses the same frontmatter parser, removes each generated mask
    span entirely, and preserves every newline. Other frontmatter and body
    text remain byte-for-byte visible to the matcher.
    """
    projected, spans = _mask_ledger_spans(text)
    for index in range(len(spans) - 1, -1, -1):
        sentinel, _ = spans[index]
        position = projected.find(sentinel)
        if position == -1:
            raise ValueError(
                f"ledger scan projection: sentinel {sentinel} missing"
            )
        projected = projected[:position] + projected[position + len(sentinel) :]
    return projected


@dataclass
class Change:
    """Represents a single text change"""
    line_number: int
    from_text: str
    to_text: str
    rule_type: str  # "dictionary" or "context_rule"
    rule_name: str
    risk: str = "low"  # "low", "medium", "high"


class DictionaryProcessor:
    """
    Stage 1 Processor: Apply dictionary-based corrections

    Process:
    1. Apply context-aware regex rules first (more specific)
    2. Apply simple dictionary replacements (more general)
    3. Track all changes for learning
    """

    def __init__(self, corrections: Dict[str, str], context_rules: List[Dict],
                 correction_meta: Optional[Dict[str, Dict]] = None,
                 speaker_labels: Optional[set[str]] = None):
        """
        Initialize processor with corrections and rules

        Args:
            corrections: Dictionary of {wrong: correct} pairs
            context_rules: List of context-aware regex rules
            correction_meta: Optional metadata per correction key,
                e.g. {"wrong": {"confidence": 0.95, "notes": "..."}}
            speaker_labels: Explicit bare labels from a roster/manifest. Use
                this for aliases whose text is indistinguishable from prose.
        """
        self.corrections = corrections
        self.context_rules = context_rules
        self.correction_meta = correction_meta or {}
        self.speaker_labels = speaker_labels or set()
        # (line_number, from_text, to_text, snippet) for every dictionary match
        # the word-boundary check refused in the last process() call. Reported,
        # not silently dropped: a caller comparing runs must be able to see why
        # a deferral disappeared.
        self.boundary_skips: List[Tuple[int, str, str, str]] = []

    def process(self, text: str, review_mode: bool = False,
                boundary_check: bool = True) -> Tuple[str, List[Change]]:
        """
        Apply all corrections to text.

        Args:
            text: Input text
            boundary_check: Refuse dictionary matches that straddle word
                boundaries (match-time safety check 3). The CLI switches it off under
                --apply-all, the operator's explicit "apply every match" override.
            review_mode: If True, only apply low-risk corrections; medium/high
                are tracked but not applied. NOTE: this engine-level default is
                False (apply everything) so the function stays a pure
                transformer, but the CLI deliberately defaults it to True (safe
                mode) in commands.cmd_run_correction. New direct callers should
                pass review_mode explicitly rather than assume the safe default
                applies at this layer.

        Returns:
            (corrected_text, list_of_changes)
        """
        # Mask correction-ledger frontmatter fields (asr_note) so the verbatim
        # old forms they cite never match; spliced back before returning.
        masked_text, ledger_spans = _mask_ledger_spans(text)
        masked_text, speaker_spans = mask_speaker_labels(
            masked_text, self.speaker_labels
        )
        corrected_text = masked_text
        all_changes = []
        self.boundary_skips = []

        # Step 1: Apply context rules (more specific, higher priority)
        corrected_text, context_changes = self._apply_context_rules(corrected_text, review_mode=review_mode)
        all_changes.extend(context_changes)

        # Step 2: Apply dictionary replacements (more general)
        corrected_text, dict_changes = self._apply_dictionary(
            corrected_text, review_mode=review_mode, boundary_check=boundary_check)
        all_changes.extend(dict_changes)

        if speaker_spans:
            corrected_text = restore_speaker_labels(corrected_text, speaker_spans)
        if ledger_spans:
            corrected_text = _restore_ledger_spans(corrected_text, ledger_spans)
        return corrected_text, all_changes

    def _apply_context_rules(self, text: str, review_mode: bool = False) -> Tuple[str, List[Change]]:
        """
        Apply context-aware regex rules.

        Like the dictionary path, in review_mode only low-risk matches are
        applied; medium/high-risk matches are tracked as changes but left in
        place (for *_needs_review.md). Without this gate, safe mode would apply
        every context rule unconditionally regardless of risk, and the run
        summary would mis-count a change as "skipped" while it was already
        mutated into the output.
        """
        changes = []
        corrected = text

        for rule in self.context_rules:
            pattern = rule["pattern"]
            replacement = rule["replacement"]
            description = rule.get("description", "")

            # Position-aware rebuild so risky matches can be selectively kept.
            result_parts = []
            search_start = 0
            for match in re.finditer(pattern, corrected):
                matched = match.group(0)
                line_num = corrected[:match.start()].count('\n') + 1
                # Use the same risk classifier as dictionary rules so context
                # rules do not bypass the common-word / length safety layers.
                # Trap demotion is excluded: the pattern IS the context.
                risk = self._assess_risk(matched, replacement,
                                         allow_trap_demotion=False)
                changes.append(Change(
                    line_number=line_num,
                    from_text=matched,
                    to_text=replacement,
                    rule_type="context_rule",
                    rule_name=description or pattern,
                    risk=risk,
                ))
                result_parts.append(corrected[search_start:match.start()])
                if review_mode and risk in ("medium", "high"):
                    result_parts.append(matched)       # keep original (deferred to needs_review)
                else:
                    result_parts.append(replacement)   # apply
                search_start = match.end()
            result_parts.append(corrected[search_start:])
            corrected = "".join(result_parts)

        return corrected, changes

    def _apply_dictionary(self, text: str, review_mode: bool = False,
                          boundary_check: bool = True) -> Tuple[str, List[Change]]:
        """
        Apply dictionary replacements with substring safety checks.

        Safety layers (applied in order at each match site):
        1. Superset check: if to_text already exists at the match position,
           skip to prevent duplication (e.g., "金流"→"现金流" inside "现金流").
           This applies to ALL rules regardless of length.
        2. Boundary check (short rules only, <=3 chars): if the match is inside
           a longer common word, skip to prevent collateral damage.
        3. Word-boundary straddle check (every rule): if the match is a
           fragment of real words by script (see straddles_word_boundary),
           skip and count it; --apply-all switches this check off.
        These are the match-time layer of references/false_positive_guide.md.
        """
        changes = []
        corrected = text

        for wrong, correct in self.corrections.items():
            if wrong not in corrected:
                continue

            # All rules go through position-aware replacement to get
            # the superset check. Short rules additionally get the
            # boundary check against common words.
            needs_boundary_check = len(wrong) <= 3
            corrected, new_changes = self._apply_with_safety_checks(
                corrected, wrong, correct, needs_boundary_check,
                review_mode=review_mode, straddle_check=boundary_check,
            )
            changes.extend(new_changes)

        return corrected, changes

    def _find_occurrences(self, text: str, target: str) -> List[int]:
        """Find all line numbers where target appears in text."""
        occurrences = []
        start = 0
        while True:
            pos = text.find(target, start)
            if pos == -1:
                break
            line_num = text[:pos].count('\n') + 1
            occurrences.append(line_num)
            start = pos + len(target)
        return occurrences

    def _apply_with_safety_checks(
        self,
        text: str,
        wrong: str,
        correct: str,
        check_boundaries: bool,
        review_mode: bool = False,
        straddle_check: bool = True,
    ) -> Tuple[str, List[Change]]:
        """
        Apply replacement at each match position with safety layers.

        1. Superset check (all rules): When to_text contains from_text
           (e.g., "金流"→"现金流"), check if the surrounding text already
           forms to_text. If so, skip — the text is already correct.

        2. Boundary check (short rules only): Check if the match is inside
           a longer common word (e.g., "天差" inside "天差地别").

        3. Word-boundary straddle check (every rule): a fragment of real
           words by script is skipped and counted (see straddles_word_boundary).
        4. Risk classification: low/medium/high based on confidence and
           common-word membership. In review_mode, high/medium changes are
           tracked but not applied.
        """
        changes = []
        result_parts = []
        search_start = 0

        while search_start < len(text):
            pos = text.find(wrong, search_start)
            if pos == -1:
                result_parts.append(text[search_start:])
                break

            # Safety layer 1: superset check.
            # If to_text contains from_text, the replacement could create
            # duplication. Check if to_text already exists at this position.
            if self._already_corrected(text, pos, wrong, correct):
                result_parts.append(text[search_start:pos + len(wrong)])
                search_start = pos + len(wrong)
                logger.debug(
                    f"Skipped '{wrong}' at pos {pos}: "
                    f"already corrected ('{correct}' present)"
                )
                continue

            # Safety layer 2: boundary check (short rules only).
            if check_boundaries and self._is_inside_longer_word(
                text, pos, wrong
            ):
                result_parts.append(text[search_start:pos + len(wrong)])
                search_start = pos + len(wrong)
                logger.debug(
                    f"Skipped '{wrong}' at pos {pos}: part of longer word"
                )
                continue

            # Safety layer 3: word-boundary straddle check (every rule).
            # The curated common-word list above only catches a match sitting
            # INSIDE one listed word; most real false positives cut ACROSS two
            # ordinary words instead (新一 in 更新|一下), and safe mode used to
            # defer every one of them into the review sidecar and queue on
            # every rerun. A dictionary-only segmentation decides that case.
            if straddle_check and straddles_word_boundary(text, pos, wrong):
                result_parts.append(text[search_start:pos + len(wrong)])
                search_start = pos + len(wrong)
                self.boundary_skips.append((
                    text[:pos].count('\n') + 1, wrong, correct,
                    text[max(0, pos - 6):pos + len(wrong) + 6],
                ))
                logger.debug(
                    f"Skipped '{wrong}' at pos {pos}: straddles a word boundary"
                )
                continue

            # Safe to replace (or record for review)
            line_num = text[:pos].count('\n') + 1
            risk = self._assess_risk(wrong, correct)

            changes.append(Change(
                line_number=line_num,
                from_text=wrong,
                to_text=correct,
                rule_type="dictionary",
                rule_name="corrections_dict",
                risk=risk,
            ))

            if review_mode and risk in ("medium", "high"):
                # Track but do not apply
                result_parts.append(text[search_start:pos + len(wrong)])
                search_start = pos + len(wrong)
                continue

            result_parts.append(text[search_start:pos])
            result_parts.append(correct)
            search_start = pos + len(wrong)

        return "".join(result_parts), changes

    @staticmethod
    def _already_corrected(
        text: str, pos: int, from_text: str, to_text: str
    ) -> bool:
        """
        Check if to_text already exists at the match position, meaning
        the text is already in the corrected form.

        This catches the case where from_text is a substring of to_text
        (e.g., "金流" is inside "现金流"). If the surrounding text already
        forms "现金流", replacing "金流" would produce "现现金流".

        Returns True if the replacement should be skipped.
        """
        if from_text not in to_text:
            # to_text doesn't contain from_text, so no superset risk.
            return False

        to_len = len(to_text)

        # Find all positions where from_text appears inside to_text.
        # For each, check if the surrounding text matches to_text.
        offset = 0
        while True:
            idx = to_text.find(from_text, offset)
            if idx == -1:
                break

            # If to_text were at text position (pos - idx), from_text at pos
            # would be the substring starting at idx within to_text.
            candidate_start = pos - idx
            candidate_end = candidate_start + to_len

            if (candidate_start >= 0
                    and candidate_end <= len(text)
                    and text[candidate_start:candidate_end] == to_text):
                return True

            offset = idx + 1

        return False

    @staticmethod
    def _is_inside_longer_word(text: str, pos: int, match: str) -> bool:
        """
        Check if the match at `pos` is embedded inside a longer common word.

        Looks at a window around the match and checks all possible substrings
        of that window against the common words set.
        """
        match_len = len(match)
        # Check windows of 2 to 5 characters that overlap with the match
        max_word_len = 5
        window_start = max(0, pos - (max_word_len - 1))
        window_end = min(len(text), pos + match_len + (max_word_len - 1))
        window = text[window_start:window_end]

        # Position of the match within the window
        match_offset = pos - window_start

        # Check all substrings that contain the match position
        for length in range(match_len + 1, min(max_word_len + 1, len(window) + 1)):
            for start in range(max(0, match_offset + match_len - length),
                               min(match_offset + 1, len(window) - length + 1)):
                substr = window[start:start + length]
                if substr != match and substr in ALL_COMMON_WORDS:
                    return True

        return False

    def _assess_risk(self, wrong: str, correct: str, *,
                     allow_trap_demotion: bool = True) -> str:
        """
        Classify a dictionary change as low/medium/high risk.

        High risk:
        - from_text is a known common Chinese word
        - from_text length <= 2
        - confidence metadata is below 0.7

        Medium risk:
        - confidence metadata is 0.7-0.9
        - from_text is 3 characters and looks like a real word fragment
        - from_text is 4+ characters and jieba identifies it as a likely valid
          Chinese phrase (e.g. 济南大学, 关税证明), unless the rule is highly
          trusted (confidence >= 0.95 and length >= 5).

        Low risk:
        - Non-word garbled text (e.g., 克劳锐 -> Claude)
        - High confidence (>= 0.95), length >= 5, and not identified as a
          likely valid Chinese phrase

        `allow_trap_demotion` is False only for context rules: a context rule
        carries its own context in the pattern, so the trap demotion (which
        exists to stop context-free bare-word rules) must not fire on it —
        otherwise a lookahead pattern like 妙计(?=比) whose match text equals
        a demoted FROM would inherit the demotion and the documented escape
        channel (--add-context-rule) would silently stop working.
        """
        meta = self.correction_meta.get(wrong, {})
        confidence = meta.get("confidence", 1.0)

        # Trap-demoted: the named domain's context file marks this pair
        # 禁裸词/禁入词典, or the FROM side as confirmed-correct (勿修) — the
        # pair may only be corrected with its context judged by the native
        # pass, so it never auto-applies in safe mode, trusted domain or not.
        # --apply-all remains the operator's explicit override (review_mode
        # off applies every level). See cmd Stage 1 demotion wiring.
        if allow_trap_demotion and meta.get("demoted_by_trap"):
            return "medium"

        # --apply-domain marked this rule as belonging to the domain the user
        # explicitly asserted for this transcript; domain match = trust, so it
        # auto-applies even in safe mode (see cmd Stage 1 setup).
        if meta.get("trusted_domain"):
            return "low"

        if wrong in ALL_COMMON_WORDS:
            return "high"

        if len(wrong) <= 2:
            return "high"

        if confidence < 0.7:
            return "high"

        if confidence < 0.9:
            return "medium"

        # 4+ char real-word guard: if jieba thinks this is a valid Chinese
        # phrase, defer it in safe mode unless the rule is highly trusted
        # (confidence >= 0.95 and length >= 5).
        if len(wrong) >= 4 and is_likely_valid_phrase(wrong):
            if not (confidence >= 0.95 and len(wrong) >= 5):
                return "medium"

        # Short but not common words are still somewhat risky
        if len(wrong) <= 3:
            return "medium"

        return "low"

    def get_summary(self, changes: List[Change]) -> Dict[str, int]:
        """Generate summary statistics"""
        summary = {
            "total_changes": len(changes),
            "dictionary_changes": sum(1 for c in changes if c.rule_type == "dictionary"),
            "context_rule_changes": sum(1 for c in changes if c.rule_type == "context_rule"),
            "boundary_skips": len(self.boundary_skips)
        }
        return summary
