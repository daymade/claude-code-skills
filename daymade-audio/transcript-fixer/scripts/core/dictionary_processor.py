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
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.common_words import ALL_COMMON_WORDS, is_likely_valid_phrase

logger = logging.getLogger(__name__)


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
                 correction_meta: Optional[Dict[str, Dict]] = None):
        """
        Initialize processor with corrections and rules

        Args:
            corrections: Dictionary of {wrong: correct} pairs
            context_rules: List of context-aware regex rules
            correction_meta: Optional metadata per correction key,
                e.g. {"wrong": {"confidence": 0.95, "notes": "..."}}
        """
        self.corrections = corrections
        self.context_rules = context_rules
        self.correction_meta = correction_meta or {}

    def process(self, text: str, review_mode: bool = False) -> Tuple[str, List[Change]]:
        """
        Apply all corrections to text.

        Args:
            text: Input text
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
        corrected_text = text
        all_changes = []

        # Step 1: Apply context rules (more specific, higher priority)
        corrected_text, context_changes = self._apply_context_rules(corrected_text, review_mode=review_mode)
        all_changes.extend(context_changes)

        # Step 2: Apply dictionary replacements (more general)
        corrected_text, dict_changes = self._apply_dictionary(corrected_text, review_mode=review_mode)
        all_changes.extend(dict_changes)

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
                risk = self._assess_risk(matched, replacement)
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

    def _apply_dictionary(self, text: str, review_mode: bool = False) -> Tuple[str, List[Change]]:
        """
        Apply dictionary replacements with substring safety checks.

        Safety layers (applied in order at each match site):
        1. Superset check: if to_text already exists at the match position,
           skip to prevent duplication (e.g., "金流"→"现金流" inside "现金流").
           This applies to ALL rules regardless of length.
        2. Boundary check (short rules only, <=3 chars): if the match is inside
           a longer common word, skip to prevent collateral damage.
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
                review_mode=review_mode,
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
    ) -> Tuple[str, List[Change]]:
        """
        Apply replacement at each match position with safety layers.

        1. Superset check (all rules): When to_text contains from_text
           (e.g., "金流"→"现金流"), check if the surrounding text already
           forms to_text. If so, skip — the text is already correct.

        2. Boundary check (short rules only): Check if the match is inside
           a longer common word (e.g., "天差" inside "天差地别").

        3. Risk classification: low/medium/high based on confidence and
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
        from_len = len(from_text)

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

    def _assess_risk(self, wrong: str, correct: str) -> str:
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
        """
        meta = self.correction_meta.get(wrong, {})
        confidence = meta.get("confidence", 1.0)

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
            "context_rule_changes": sum(1 for c in changes if c.rule_type == "context_rule")
        }
        return summary
