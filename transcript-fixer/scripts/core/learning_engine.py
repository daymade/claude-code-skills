#!/usr/bin/env python3
"""
Learning Engine - Pattern Detection from Correction History

SINGLE RESPONSIBILITY: Analyze history and suggest new corrections

Features:
- Analyze correction history for patterns
- Detect frequently occurring corrections
- Calculate confidence scores
- Generate suggestions for user review
- Track rejected suggestions to avoid re-suggesting
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict
from dataclasses import dataclass, asdict
from collections import defaultdict


@dataclass
class Suggestion:
    """Represents a learned correction suggestion"""
    from_text: str
    to_text: str
    frequency: int
    confidence: float
    examples: List[Dict]  # List of {file, line, context}
    first_seen: str
    last_seen: str
    status: str  # "pending", "approved", "rejected"


class LearningEngine:
    """
    Analyzes correction history to suggest new corrections

    Algorithm:
    1. Load all history files
    2. Extract stage2 (AI) changes
    3. Group by pattern (from_text → to_text)
    4. Calculate frequency and confidence
    5. Filter by thresholds
    6. Save suggestions for user review
    """

    # Thresholds for suggesting corrections
    MIN_FREQUENCY = 3  # Must appear at least 3 times
    MIN_CONFIDENCE = 0.8  # Must have 80%+ confidence

    def __init__(self, history_dir: Path, learned_dir: Path):
        """
        Initialize learning engine

        Args:
            history_dir: Directory containing correction history
            learned_dir: Directory for learned suggestions
        """
        self.history_dir = history_dir
        self.learned_dir = learned_dir
        self.pending_file = learned_dir / "pending_review.json"
        self.rejected_file = learned_dir / "rejected.json"

    def analyze_and_suggest(self) -> List[Suggestion]:
        """
        Analyze history and generate suggestions

        Returns:
            List of new suggestions for user review
        """
        # Load all history
        patterns = self._extract_patterns()

        # Filter rejected patterns
        rejected = self._load_rejected()
        patterns = {k: v for k, v in patterns.items()
                   if k not in rejected}

        # Generate suggestions
        suggestions = []
        for (from_text, to_text), occurrences in patterns.items():
            frequency = len(occurrences)

            if frequency < self.MIN_FREQUENCY:
                continue

            confidence = self._calculate_confidence(occurrences)

            if confidence < self.MIN_CONFIDENCE:
                continue

            suggestion = Suggestion(
                from_text=from_text,
                to_text=to_text,
                frequency=frequency,
                confidence=confidence,
                examples=occurrences[:5],  # Top 5 examples
                first_seen=occurrences[0]["timestamp"],
                last_seen=occurrences[-1]["timestamp"],
                status="pending"
            )

            suggestions.append(suggestion)

        # Save new suggestions
        if suggestions:
            self._save_pending_suggestions(suggestions)

        return suggestions

    def approve_suggestion(self, from_text: str) -> bool:
        """
        Approve a suggestion (remove from pending)

        Returns:
            True if approved, False if not found
        """
        pending = self._load_pending_suggestions()

        for suggestion in pending:
            if suggestion["from_text"] == from_text:
                pending.remove(suggestion)
                self._save_suggestions(pending, self.pending_file)
                return True

        return False

    def reject_suggestion(self, from_text: str, to_text: str) -> None:
        """
        Reject a suggestion (move to rejected list)
        """
        # Remove from pending
        pending = self._load_pending_suggestions()
        pending = [s for s in pending
                  if not (s["from_text"] == from_text and s["to_text"] == to_text)]
        self._save_suggestions(pending, self.pending_file)

        # Add to rejected
        rejected = self._load_rejected()
        rejected.add((from_text, to_text))
        self._save_rejected(rejected)

    def list_pending(self) -> List[Dict]:
        """List all pending suggestions"""
        return self._load_pending_suggestions()

    def _extract_patterns(self) -> Dict[tuple, List[Dict]]:
        """Extract all correction patterns from history"""
        patterns = defaultdict(list)

        if not self.history_dir.exists():
            return patterns

        for history_file in self.history_dir.glob("*.json"):
            with open(history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Extract stage2 changes (AI corrections)
            if "stages" in data and "stage2" in data["stages"]:
                changes = data["stages"]["stage2"].get("changes", [])

                for change in changes:
                    key = (change["from"], change["to"])
                    patterns[key].append({
                        "file": data["filename"],
                        "line": change.get("line", 0),
                        "context": change.get("context", ""),
                        "timestamp": data["timestamp"]
                    })

        return patterns

    def _calculate_confidence(self, occurrences: List[Dict]) -> float:
        """
        Calculate confidence score for a pattern

        Factors:
        - Frequency (more = higher)
        - Consistency (always same correction = higher)
        - Recency (recent occurrences = higher)
        """
        # Base confidence from frequency
        frequency_score = min(len(occurrences) / 10.0, 1.0)

        # Consistency: always the same from→to mapping
        consistency_score = 1.0  # Already consistent by grouping

        # Recency: more recent = higher
        # (Simplified: assume chronological order)
        recency_score = 0.9 if len(occurrences) > 1 else 0.8

        # Weighted average
        confidence = (
            0.5 * frequency_score +
            0.3 * consistency_score +
            0.2 * recency_score
        )

        return confidence

    def _load_pending_suggestions(self) -> List[Dict]:
        """Load pending suggestions from file"""
        if not self.pending_file.exists():
            return []

        with open(self.pending_file, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                return []
            return json.loads(content).get("suggestions", [])

    def _save_pending_suggestions(self, suggestions: List[Suggestion]) -> None:
        """Save pending suggestions to file"""
        existing = self._load_pending_suggestions()

        # Convert to dict and append
        new_suggestions = [asdict(s) for s in suggestions]
        all_suggestions = existing + new_suggestions

        self._save_suggestions(all_suggestions, self.pending_file)

    def _save_suggestions(self, suggestions: List[Dict], filepath: Path) -> None:
        """Save suggestions to file"""
        data = {"suggestions": suggestions}
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_rejected(self) -> set:
        """Load rejected patterns"""
        if not self.rejected_file.exists():
            return set()

        with open(self.rejected_file, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                return set()
            data = json.loads(content)
            return {(r["from"], r["to"]) for r in data.get("rejected", [])}

    def _save_rejected(self, rejected: set) -> None:
        """Save rejected patterns"""
        data = {
            "rejected": [
                {"from": from_text, "to": to_text}
                for from_text, to_text in rejected
            ]
        }
        with open(self.rejected_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
