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

import difflib
import logging
import re
from dataclasses import dataclass
from typing import List, Tuple, Final

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
    change_type: str     # 'word', 'phrase', 'punctuation'
    confidence: float    # 0.0-1.0 based on context consistency

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
    1. Use difflib.SequenceMatcher for accurate diff
    2. Filter out formatting-only changes
    3. Extract context for confidence scoring
    4. Classify change types
    5. Calculate confidence based on consistency
    """

    def __init__(self, min_change_length: int = 1, max_change_length: int = 50):
        """
        Initialize extractor

        Args:
            min_change_length: Ignore changes shorter than this (chars)
                              - Helps filter noise like single punctuation
                              - Must be >= 1
            max_change_length: Ignore changes longer than this (chars)
                              - Helps filter large rewrites (not corrections)
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

        matcher = difflib.SequenceMatcher(None, original, corrected)
        changes = []

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'replace':  # Actual replacement (from→to)
                from_text = original[i1:i2]
                to_text = corrected[j1:j2]

                # Filter by length
                if not self._is_valid_change_length(from_text, to_text):
                    continue

                # Filter formatting-only changes
                if self._is_formatting_only(from_text, to_text):
                    continue

                # Extract context
                context_before = original[max(0, i1-20):i1]
                context_after = original[i2:min(len(original), i2+20)]

                # Classify change type
                change_type = self._classify_change(from_text, to_text)

                # Calculate confidence (based on text similarity and context)
                confidence = self._calculate_confidence(
                    from_text, to_text, context_before, context_after
                )

                changes.append(ExtractedChange(
                    from_text=from_text.strip(),
                    to_text=to_text.strip(),
                    context_before=context_before,
                    context_after=context_after,
                    position=i1,
                    change_type=change_type,
                    confidence=confidence
                ))

                # CRITICAL FIX: Prevent DoS from excessive changes
                if len(changes) >= MAX_CHANGES:
                    logger.warning(
                        f"Reached maximum changes limit ({MAX_CHANGES}), stopping extraction"
                    )
                    break

        logger.debug(f"Extracted {len(changes)} changes")
        return changes

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

    def _is_valid_change_length(self, from_text: str, to_text: str) -> bool:
        """Check if change is within valid length range"""
        from_len = len(from_text.strip())
        to_len = len(to_text.strip())

        # Both must be within range
        if from_len < self.min_change_length or from_len > self.max_change_length:
            return False
        if to_len < self.min_change_length or to_len > self.max_change_length:
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

    def _classify_change(self, from_text: str, to_text: str) -> str:
        """
        Classify the type of change

        Returns: 'word', 'phrase', 'punctuation', 'mixed'
        """
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
