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
from typing import Dict, List, Tuple
from dataclasses import dataclass


@dataclass
class Change:
    """Represents a single text change"""
    line_number: int
    from_text: str
    to_text: str
    rule_type: str  # "dictionary" or "context_rule"
    rule_name: str


class DictionaryProcessor:
    """
    Stage 1 Processor: Apply dictionary-based corrections

    Process:
    1. Apply context-aware regex rules first (more specific)
    2. Apply simple dictionary replacements (more general)
    3. Track all changes for learning
    """

    def __init__(self, corrections: Dict[str, str], context_rules: List[Dict]):
        """
        Initialize processor with corrections and rules

        Args:
            corrections: Dictionary of {wrong: correct} pairs
            context_rules: List of context-aware regex rules
        """
        self.corrections = corrections
        self.context_rules = context_rules

    def process(self, text: str) -> Tuple[str, List[Change]]:
        """
        Apply all corrections to text

        Returns:
            (corrected_text, list_of_changes)
        """
        corrected_text = text
        all_changes = []

        # Step 1: Apply context rules (more specific, higher priority)
        corrected_text, context_changes = self._apply_context_rules(corrected_text)
        all_changes.extend(context_changes)

        # Step 2: Apply dictionary replacements (more general)
        corrected_text, dict_changes = self._apply_dictionary(corrected_text)
        all_changes.extend(dict_changes)

        return corrected_text, all_changes

    def _apply_context_rules(self, text: str) -> Tuple[str, List[Change]]:
        """Apply context-aware regex rules"""
        changes = []
        corrected = text

        for rule in self.context_rules:
            pattern = rule["pattern"]
            replacement = rule["replacement"]
            description = rule.get("description", "")

            # Find all matches with their positions
            for match in re.finditer(pattern, corrected):
                line_num = corrected[:match.start()].count('\n') + 1
                changes.append(Change(
                    line_number=line_num,
                    from_text=match.group(0),
                    to_text=replacement,
                    rule_type="context_rule",
                    rule_name=description or pattern
                ))

            # Apply replacement
            corrected = re.sub(pattern, replacement, corrected)

        return corrected, changes

    def _apply_dictionary(self, text: str) -> Tuple[str, List[Change]]:
        """Apply simple dictionary replacements"""
        changes = []
        corrected = text

        for wrong, correct in self.corrections.items():
            if wrong not in corrected:
                continue

            # Find all occurrences
            occurrences = []
            start = 0
            while True:
                pos = corrected.find(wrong, start)
                if pos == -1:
                    break
                line_num = corrected[:pos].count('\n') + 1
                occurrences.append(line_num)
                start = pos + len(wrong)

            # Track changes
            for line_num in occurrences:
                changes.append(Change(
                    line_number=line_num,
                    from_text=wrong,
                    to_text=correct,
                    rule_type="dictionary",
                    rule_name="corrections_dict"
                ))

            # Apply replacement
            corrected = corrected.replace(wrong, correct)

        return corrected, changes

    def get_summary(self, changes: List[Change]) -> Dict[str, int]:
        """Generate summary statistics"""
        summary = {
            "total_changes": len(changes),
            "dictionary_changes": sum(1 for c in changes if c.rule_type == "dictionary"),
            "context_rule_changes": sum(1 for c in changes if c.rule_type == "context_rule")
        }
        return summary
