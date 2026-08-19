#!/usr/bin/env python3
"""
Change Extractor - Extract Precise From→To Changes

CRITICAL FEATURE: Extract specific corrections from AI results for learning

This enables the learning loop:
1. AI makes corrections → Extract specific from→to pairs
2. High-frequency patterns → Auto-add to dictionary
3. Next run → Dictionary handles learned patterns (free)
4. Progressive cost reduction → System gets smarter with use

CRITICAL FIX (P1-2): Comprehensive input validation
- Prevents DoS attacks from oversized input
- Type checking for all parameters
- Range validation for numeric arguments
- Protection against malicious input
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Tuple, Final

from rapidfuzz.distance import Levenshtein

logger = logging.getLogger(__name__)

# Security limits for DoS prevention
MAX_TEXT_LENGTH: Final[int] = 1_000_000  # 1MB of text
MAX_CHANGES: Final[int] = 10_000  # Maximum changes to extract


class InputValidationError(ValueError):
    """Raised when input validation fails"""
    pass


@dataclass
class ExtractedChange:
    """Represents a specific from→to change extracted from AI results"""
    from_text: str
    to_text: str
    context_before: str  # 20 chars before
    context_after: str   # 20 chars after
    position: int        # Character position in original
    change_type: str     # 'word', 'phrase', 'punctuation', 'insertion', 'deletion'
    confidence: float    # 0.0-1.0 based on context consistency
    learnable: bool = True  # False when no safe replayable FROM→TO pair exists

    def __hash__(self):
        """Allow use in sets for deduplication"""
        return hash((self.from_text, self.to_text))

    def __eq__(self, other):
        """Equality based on from/to text"""
        return (self.from_text == other.from_text and
                self.to_text == other.to_text)


class ChangeExtractor:
    """
    Extract precise from→to changes from before/after text pairs

    Strategy:
    1. Use RapidFuzz's optimized Levenshtein opcodes for accurate bounded diff
    2. Retain formatting-only changes in history but exclude them from learning
    3. Extract context for confidence scoring
    4. Classify change types
    5. Calculate confidence based on consistency
    """

    def __init__(self, min_change_length: int = 1, max_change_length: int = 50):
        """
        Initialize extractor

        Args:
            min_change_length: Minimum replayable learning-pair length
            - Must be >= 1
            max_change_length: Maximum replayable learning-pair length. Larger
                              edits remain in audit history but never auto-learn.
                              - Must be > min_change_length

        Raises:
            InputValidationError: If parameters are invalid

        CRITICAL FIX (P1-2): Added comprehensive parameter validation
        """
        # CRITICAL FIX: Validate parameter types
        if not isinstance(min_change_length, int):
            raise InputValidationError(
                f"min_change_length must be int, got {type(min_change_length).__name__}"
            )

        if not isinstance(max_change_length, int):
            raise InputValidationError(
                f"max_change_length must be int, got {type(max_change_length).__name__}"
            )

        # CRITICAL FIX: Validate parameter ranges
        if min_change_length < 1:
            raise InputValidationError(
                f"min_change_length must be >= 1, got {min_change_length}"
            )

        if max_change_length < 1:
            raise InputValidationError(
                f"max_change_length must be >= 1, got {max_change_length}"
            )

        # CRITICAL FIX: Validate logical consistency
        if min_change_length > max_change_length:
            raise InputValidationError(
                f"min_change_length ({min_change_length}) must be <= "
                f"max_change_length ({max_change_length})"
            )

        # CRITICAL FIX: Validate reasonable upper bounds (DoS prevention)
        if max_change_length > 1000:
            logger.warning(
                f"Large max_change_length ({max_change_length}) may impact performance"
            )

        self.min_change_length = min_change_length
        self.max_change_length = max_change_length

        logger.debug(
            f"ChangeExtractor initialized: min={min_change_length}, max={max_change_length}"
        )

    def extract_changes(self, original: str, corrected: str) -> List[ExtractedChange]:
        """
        Extract all from→to changes between original and corrected text

        Args:
            original: Original text (before correction)
            corrected: Corrected text (after AI processing)

        Returns:
            List of ExtractedChange objects with context and confidence

        Raises:
            InputValidationError: If input validation fails

        CRITICAL FIX (P1-2): Comprehensive input validation to prevent:
        - DoS attacks from oversized input
        - Crashes from None/invalid input
        - Performance issues from malicious input
        """
        # CRITICAL FIX: Validate input types
        if not isinstance(original, str):
            raise InputValidationError(
                f"original must be str, got {type(original).__name__}"
            )

        if not isinstance(corrected, str):
            raise InputValidationError(
                f"corrected must be str, got {type(corrected).__name__}"
            )

        # CRITICAL FIX: Validate input length (DoS prevention)
        if len(original) > MAX_TEXT_LENGTH:
            raise InputValidationError(
                f"original text too long ({len(original)} chars). "
                f"Maximum allowed: {MAX_TEXT_LENGTH}"
            )

        if len(corrected) > MAX_TEXT_LENGTH:
            raise InputValidationError(
                f"corrected text too long ({len(corrected)} chars). "
                f"Maximum allowed: {MAX_TEXT_LENGTH}"
            )

        # CRITICAL FIX: Handle empty strings gracefully
        if not original and not corrected:
            logger.debug("Both texts are empty, returning empty changes list")
            return []

        # CRITICAL FIX: Validate text contains valid characters (not binary data)
        try:
            # Try to encode/decode to ensure valid text
            original.encode('utf-8')
            corrected.encode('utf-8')
        except UnicodeError as e:
            raise InputValidationError(f"Invalid text encoding: {e}") from e

        logger.debug(
            f"Extracting changes: original={len(original)} chars, "
            f"corrected={len(corrected)} chars"
        )

        original_tokens = self._tokenize(original)
        corrected_tokens = self._tokenize(corrected)
        opcodes = self._coalesce_opcodes(Levenshtein.opcodes(
            [token for token, _start, _end in original_tokens],
            [token for token, _start, _end in corrected_tokens],
        ).as_list())
        changes = []
        seen: set[tuple[int, str, str]] = set()

        for tag, i1, i2, j1, j2 in opcodes:
            if tag != 'equal':
                original_start, original_end = self._token_span(
                    original_tokens, i1, i2, len(original)
                )
                corrected_start, corrected_end = self._token_span(
                    corrected_tokens, j1, j2, len(corrected)
                )

                learnable = tag == 'replace'
                if tag == 'insert':
                    (
                        original_start,
                        original_end,
                        corrected_start,
                        corrected_end,
                        learnable,
                    ) = self._anchor_insert(
                        original_tokens,
                        corrected_tokens,
                        i1,
                        j1,
                        j2,
                        original_start,
                        original_end,
                        corrected_start,
                        corrected_end,
                    )
                elif tag == 'delete':
                    (
                        original_start,
                        original_end,
                        corrected_start,
                        corrected_end,
                        learnable,
                    ) = self._anchor_delete(
                        original_tokens,
                        corrected_tokens,
                        i1,
                        i2,
                        j1,
                        original_start,
                        original_end,
                        corrected_start,
                        corrected_end,
                    )

                from_text = original[original_start:original_end]
                to_text = corrected[corrected_start:corrected_end]

                if not self._is_material_change(from_text, to_text):
                    continue
                learnable_length = self._is_learnable_change_length(
                    from_text, to_text
                )

                formatting_only = self._is_formatting_only(from_text, to_text)

                # Extract context
                context_before = original[max(0, original_start-20):original_start]
                context_after = original[
                    original_end:min(len(original), original_end+20)
                ]

                # Classify change type
                change_type = self._classify_change(
                    tag, from_text, to_text, formatting_only=formatting_only
                )

                # Calculate confidence (based on text similarity and context)
                confidence = self._calculate_confidence(
                    from_text, to_text, context_before, context_after
                )

                # Keep the exact bytes of an unexpected whitespace/case edit in
                # history. Ordinary lexical changes still shed boundary space
                # so their replayable dictionary pair is not indentation-bound.
                clean_from = from_text if formatting_only else from_text.strip()
                clean_to = to_text if formatting_only else to_text.strip()
                key = (original_start, clean_from, clean_to)
                if key in seen:
                    continue
                seen.add(key)

                changes.append(ExtractedChange(
                    from_text=clean_from,
                    to_text=clean_to,
                    context_before=context_before,
                    context_after=context_after,
                    position=original_start,
                    change_type=change_type,
                    confidence=confidence,
                    learnable=(
                        learnable
                        and learnable_length
                        and not formatting_only
                        and bool(clean_from)
                        and bool(clean_to)
                        and self._contains_lexical_text(clean_from)
                        and self._contains_lexical_text(clean_to)
                    ),
                ))

                # CRITICAL FIX: Prevent DoS from excessive changes
                if len(changes) > MAX_CHANGES:
                    raise InputValidationError(
                        "Correction produced more than "
                        f"{MAX_CHANGES} auditable changes; refusing to truncate "
                        "history for modified text"
                    )

        logger.debug(f"Extracted {len(changes)} changes")
        return changes

    @staticmethod
    def _coalesce_opcodes(
        opcodes: list[tuple[str, int, int, int, int]],
    ) -> list[tuple[str, int, int, int, int]]:
        """Merge adjacent edit opcodes into one human/replayable change.

        Levenshtein may express one token replacement as an insertion followed
        immediately by a replacement (for example one ASR token becoming two
        words). With no equal material between them, they are one correction.
        """
        merged: list[tuple[str, int, int, int, int]] = []
        pending: tuple[str, int, int, int, int] | None = None

        def flush_pending() -> None:
            nonlocal pending
            if pending is not None:
                merged.append(pending)
                pending = None

        for tag, i1, i2, j1, j2 in opcodes:
            if tag == "equal":
                flush_pending()
                merged.append((tag, i1, i2, j1, j2))
                continue

            if pending is None:
                pending = (tag, i1, i2, j1, j2)
                continue

            _old_tag, old_i1, old_i2, old_j1, old_j2 = pending
            if old_i2 == i1 and old_j2 == j1:
                combined_tag = (
                    "insert" if old_i1 == i2
                    else "delete" if old_j1 == j2
                    else "replace"
                )
                pending = (combined_tag, old_i1, i2, old_j1, j2)
            else:
                flush_pending()
                pending = (tag, i1, i2, j1, j2)

        flush_pending()
        return merged

    @staticmethod
    def _tokenize(text: str) -> list[tuple[str, int, int]]:
        """Tokenize ASCII words as units and keep CJK characters addressable.

        Character-level diffing can represent ``meetng → meeting`` as an empty-
        string insertion and split ``spekarA → Speaker A`` into several
        misleading one-character edits. ASCII word tokens retain the replayable
        ASR pair, while individual CJK characters preserve precise homophone
        replacements. RapidFuzz handles repetitive token sequences without the
        quadratic ``SequenceMatcher(autojunk=False)`` failure mode.
        """
        token_re = re.compile(
            r"[A-Za-z0-9_]+(?:[.'’_-][A-Za-z0-9_]+)*|[\u3400-\u9fff]|.",
            re.DOTALL,
        )
        return [
            (match.group(0), match.start(), match.end())
            for match in token_re.finditer(text)
        ]

    @staticmethod
    def _token_span(
        tokens: list[tuple[str, int, int]],
        start: int,
        end: int,
        text_length: int,
    ) -> tuple[int, int]:
        if start == end:
            position = tokens[start][1] if start < len(tokens) else text_length
            return position, position
        return tokens[start][1], tokens[end - 1][2]

    @staticmethod
    def _is_lexical_token(token: str) -> bool:
        return bool(re.fullmatch(
            r"(?:[A-Za-z0-9_]+(?:[.'’_-][A-Za-z0-9_]+)*)|[\u3400-\u9fff]",
            token,
        ))

    @staticmethod
    def _contains_lexical_text(text: str) -> bool:
        return bool(re.search(r"[A-Za-z0-9_\u3400-\u9fff]", text))

    def _anchor_insert(
        self,
        original_tokens: list[tuple[str, int, int]],
        corrected_tokens: list[tuple[str, int, int]],
        original_index: int,
        corrected_start_index: int,
        corrected_end_index: int,
        original_start: int,
        original_end: int,
        corrected_start: int,
        corrected_end: int,
    ) -> tuple[int, int, int, int, bool]:
        """Attach an insertion to an unchanged lexical neighbour when safe."""
        inserted_is_lexical = any(
            self._contains_lexical_text(token)
            for token, _start, _end in corrected_tokens[
                corrected_start_index:corrected_end_index
            ]
        )
        if original_index > 0 and corrected_start_index > 0:
            original_left = original_tokens[original_index - 1]
            corrected_left = corrected_tokens[corrected_start_index - 1]
            if (
                original_left[0] == corrected_left[0]
                and self._is_lexical_token(original_left[0])
            ):
                return (
                    original_left[1],
                    original_end,
                    corrected_left[1],
                    corrected_end,
                    inserted_is_lexical,
                )

        if (
            original_index < len(original_tokens)
            and corrected_end_index < len(corrected_tokens)
        ):
            original_right = original_tokens[original_index]
            corrected_right = corrected_tokens[corrected_end_index]
            if (
                original_right[0] == corrected_right[0]
                and self._is_lexical_token(original_right[0])
            ):
                return (
                    original_start,
                    original_right[2],
                    corrected_start,
                    corrected_right[2],
                    inserted_is_lexical,
                )

        return (
            original_start,
            original_end,
            corrected_start,
            corrected_end,
            False,
        )

    def _anchor_delete(
        self,
        original_tokens: list[tuple[str, int, int]],
        corrected_tokens: list[tuple[str, int, int]],
        original_start_index: int,
        original_end_index: int,
        corrected_index: int,
        original_start: int,
        original_end: int,
        corrected_start: int,
        corrected_end: int,
    ) -> tuple[int, int, int, int, bool]:
        """Attach a deletion to an unchanged lexical neighbour when safe."""
        deleted_is_lexical = any(
            self._contains_lexical_text(token)
            for token, _start, _end in original_tokens[
                original_start_index:original_end_index
            ]
        )
        if original_start_index > 0 and corrected_index > 0:
            original_left = original_tokens[original_start_index - 1]
            corrected_left = corrected_tokens[corrected_index - 1]
            if (
                original_left[0] == corrected_left[0]
                and self._is_lexical_token(original_left[0])
            ):
                return (
                    original_left[1],
                    original_end,
                    corrected_left[1],
                    corrected_end,
                    deleted_is_lexical,
                )

        if (
            original_end_index < len(original_tokens)
            and corrected_index < len(corrected_tokens)
        ):
            original_right = original_tokens[original_end_index]
            corrected_right = corrected_tokens[corrected_index]
            if (
                original_right[0] == corrected_right[0]
                and self._is_lexical_token(original_right[0])
            ):
                return (
                    original_start,
                    original_right[2],
                    corrected_start,
                    corrected_right[2],
                    deleted_is_lexical,
                )

        return (
            original_start,
            original_end,
            corrected_start,
            corrected_end,
            False,
        )

    def group_by_pattern(self, changes: List[ExtractedChange]) -> dict[Tuple[str, str], List[ExtractedChange]]:
        """
        Group changes by from→to pattern for frequency analysis

        Args:
            changes: List of ExtractedChange objects

        Returns:
            Dict mapping (from_text, to_text) to list of occurrences

        Raises:
            InputValidationError: If input is invalid

        CRITICAL FIX (P1-2): Added input validation
        """
        # CRITICAL FIX: Validate input type
        if not isinstance(changes, list):
            raise InputValidationError(
                f"changes must be list, got {type(changes).__name__}"
            )

        # CRITICAL FIX: Validate list elements
        grouped = {}
        for i, change in enumerate(changes):
            if not isinstance(change, ExtractedChange):
                raise InputValidationError(
                    f"changes[{i}] must be ExtractedChange, "
                    f"got {type(change).__name__}"
                )

            key = (change.from_text, change.to_text)
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(change)

        logger.debug(f"Grouped {len(changes)} changes into {len(grouped)} patterns")
        return grouped

    def calculate_pattern_confidence(self, occurrences: List[ExtractedChange]) -> float:
        """
        Calculate overall confidence for a pattern based on multiple occurrences

        Higher confidence if:
        - Appears in different contexts
        - Consistent across occurrences
        - Not ambiguous (one from → multiple to)

        Args:
            occurrences: List of ExtractedChange objects for same pattern

        Returns:
            Confidence score 0.0-1.0

        Raises:
            InputValidationError: If input is invalid

        CRITICAL FIX (P1-2): Added input validation
        """
        # CRITICAL FIX: Validate input type
        if not isinstance(occurrences, list):
            raise InputValidationError(
                f"occurrences must be list, got {type(occurrences).__name__}"
            )

        # Handle empty list
        if not occurrences:
            return 0.0

        # CRITICAL FIX: Validate list elements
        for i, occurrence in enumerate(occurrences):
            if not isinstance(occurrence, ExtractedChange):
                raise InputValidationError(
                    f"occurrences[{i}] must be ExtractedChange, "
                    f"got {type(occurrence).__name__}"
                )

        # Base confidence from individual changes (safe division - len > 0)
        avg_confidence = sum(c.confidence for c in occurrences) / len(occurrences)

        # Frequency boost (more occurrences = higher confidence)
        frequency_factor = min(1.0, len(occurrences) / 5.0)  # Max at 5 occurrences

        # Context diversity (appears in different contexts = more reliable)
        unique_contexts = len(set(
            (c.context_before, c.context_after) for c in occurrences
        ))
        diversity_factor = min(1.0, unique_contexts / len(occurrences))

        # Combined confidence (weighted average)
        final_confidence = (
            0.5 * avg_confidence +
            0.3 * frequency_factor +
            0.2 * diversity_factor
        )

        return round(final_confidence, 2)

    @staticmethod
    def _is_material_change(from_text: str, to_text: str) -> bool:
        """Return whether the opcode represents any actual mutation."""
        return from_text != to_text and bool(from_text or to_text)

    def _is_learnable_change_length(self, from_text: str, to_text: str) -> bool:
        """Bound dictionary learning without deleting the audit record."""
        from_len = len(from_text.strip())
        to_len = len(to_text.strip())

        # A whitespace-only edit has no stripped length but is still a material
        # transcript mutation that history must expose.
        if from_len == 0 and to_len == 0 and from_text != to_text:
            from_len = len(from_text)
            to_len = len(to_text)

        # History may represent a whole-span insertion/deletion with one empty
        # side. At least one side must contain a bounded material change.
        if from_len == 0 and to_len == 0:
            return False
        for length in (from_len, to_len):
            if length and (
                length < self.min_change_length or length > self.max_change_length
            ):
                return False

        return True

    def _is_formatting_only(self, from_text: str, to_text: str) -> bool:
        """
        Check if change is formatting-only (whitespace, case)

        Returns True if we should ignore this change
        """
        # Strip whitespace and compare
        from_stripped = ''.join(from_text.split())
        to_stripped = ''.join(to_text.split())

        # Same after stripping whitespace = formatting only
        if from_stripped == to_stripped:
            return True

        # Only case difference = formatting only
        if from_stripped.lower() == to_stripped.lower():
            return True

        return False

    def _classify_change(
        self,
        tag: str,
        from_text: str,
        to_text: str,
        *,
        formatting_only: bool = False,
    ) -> str:
        """
        Classify the type of change

        Returns: 'word', 'phrase', 'punctuation', 'mixed', 'insertion',
        'deletion', or 'formatting'
        """
        if formatting_only:
            return 'formatting'
        if tag == 'insert':
            return 'insertion'
        if tag == 'delete':
            return 'deletion'
        # Single character = punctuation or letter
        if len(from_text.strip()) == 1 and len(to_text.strip()) == 1:
            return 'punctuation'

        # Contains space = phrase
        if ' ' in from_text or ' ' in to_text:
            return 'phrase'

        # Single word
        if re.match(r'^\w+$', from_text) and re.match(r'^\w+$', to_text):
            return 'word'

        return 'mixed'

    def _calculate_confidence(
        self,
        from_text: str,
        to_text: str,
        context_before: str,
        context_after: str
    ) -> float:
        """
        Calculate confidence score for this change

        Higher confidence if:
        - Similar length (likely homophone, not rewrite)
        - Clear context (not ambiguous)
        - Common error pattern (e.g., Chinese homophones)

        Returns:
            Confidence score 0.0-1.0

        CRITICAL FIX (P1-2): Division by zero prevention
        """
        # CRITICAL FIX: Length similarity (prevent division by zero)
        len_from = len(from_text)
        len_to = len(to_text)

        if len_from == 0 and len_to == 0:
            # Both empty - shouldn't happen due to upstream filtering, but handle it
            length_score = 1.0
        elif len_from == 0 or len_to == 0:
            # One empty - low confidence (major rewrite)
            length_score = 0.0
        else:
            # Normal case: calculate ratio safely
            len_ratio = min(len_from, len_to) / max(len_from, len_to)
            length_score = len_ratio

        # Context clarity (longer context = less ambiguous)
        context_score = min(1.0, (len(context_before) + len(context_after)) / 40.0)

        # Chinese character ratio (higher = likely homophone error)
        chinese_chars_from = len(re.findall(r'[\u4e00-\u9fff]', from_text))
        chinese_chars_to = len(re.findall(r'[\u4e00-\u9fff]', to_text))

        # CRITICAL FIX: Prevent division by zero
        total_len = len_from + len_to
        if total_len == 0:
            chinese_score = 0.0
        else:
            chinese_ratio = (chinese_chars_from + chinese_chars_to) / total_len
            chinese_score = min(1.0, chinese_ratio * 2)  # Boost for Chinese

        # Combined score (weighted)
        confidence = (
            0.4 * length_score +
            0.3 * context_score +
            0.3 * chinese_score
        )

        return round(confidence, 2)
