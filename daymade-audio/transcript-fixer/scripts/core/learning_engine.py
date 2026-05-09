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

CRITICAL FIX (P1-1): Thread-safe file operations with file locking
- Prevents race conditions in concurrent access
- Atomic read-modify-write operations
- Cross-platform file locking support
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from collections import defaultdict
from contextlib import contextmanager

# CRITICAL FIX: Import file locking
try:
    from filelock import FileLock, Timeout as FileLockTimeout
except ImportError:
    raise ImportError(
        "filelock library required for thread-safe operations. "
        "Install with: uv add filelock"
    )

logger = logging.getLogger(__name__)


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

    # Thresholds for auto-approval (stricter)
    AUTO_APPROVE_FREQUENCY = 5  # Must appear at least 5 times
    AUTO_APPROVE_CONFIDENCE = 0.85  # Must have 85%+ confidence

    def __init__(self, history_dir: Path, learned_dir: Path, correction_service=None):
        """
        Initialize learning engine

        Args:
            history_dir: Directory containing correction history
            learned_dir: Directory for learned suggestions
            correction_service: CorrectionService for auto-adding to dictionary
        """
        self.history_dir = history_dir
        self.learned_dir = learned_dir
        self.pending_file = learned_dir / "pending_review.json"
        self.rejected_file = learned_dir / "rejected.json"
        self.auto_approved_file = learned_dir / "auto_approved.json"
        self.correction_service = correction_service

        # CRITICAL FIX: Lock files for thread-safe operations
        # Each JSON file gets its own lock file
        self.pending_lock = learned_dir / ".pending_review.lock"
        self.rejected_lock = learned_dir / ".rejected.lock"
        self.auto_approved_lock = learned_dir / ".auto_approved.lock"

        # Lock timeout (seconds)
        self.lock_timeout = 10.0

    @contextmanager
    def _file_lock(self, lock_path: Path, operation: str = "file operation"):
        """
        Context manager for file locking.

        CRITICAL FIX: Ensures atomic file operations, prevents race conditions.

        Args:
            lock_path: Path to lock file
            operation: Description of operation (for logging)

        Yields:
            None

        Raises:
            FileLockTimeout: If lock cannot be acquired within timeout

        Example:
            with self._file_lock(self.pending_lock, "save pending"):
                # Atomic read-modify-write
                data = self._load_pending_suggestions()
                data.append(new_item)
                self._save_suggestions(data, self.pending_file)
        """
        lock = FileLock(str(lock_path), timeout=self.lock_timeout)

        try:
            logger.debug(f"Acquiring lock for {operation}: {lock_path}")
            with lock.acquire(timeout=self.lock_timeout):
                logger.debug(f"Lock acquired for {operation}")
                yield
        except FileLockTimeout as e:
            logger.error(
                f"Failed to acquire lock for {operation} after {self.lock_timeout}s: {lock_path}"
            )
            raise RuntimeError(
                f"File lock timeout for {operation}. "
                f"Another process may be holding the lock. "
                f"Lock file: {lock_path}"
            ) from e
        finally:
            logger.debug(f"Lock released for {operation}")

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
        Approve a suggestion (remove from pending).

        CRITICAL FIX: Atomic read-modify-write operation with file lock.

        Args:
            from_text: The 'from' text of suggestion to approve

        Returns:
            True if approved, False if not found
        """
        # CRITICAL FIX: Acquire lock for entire read-modify-write operation
        with self._file_lock(self.pending_lock, "approve suggestion"):
            pending = self._load_pending_suggestions_unlocked()

            for suggestion in pending:
                if suggestion["from_text"] == from_text:
                    pending.remove(suggestion)
                    self._save_suggestions_unlocked(pending, self.pending_file)
                    logger.info(f"Approved suggestion: {from_text}")
                    return True

            logger.warning(f"Suggestion not found for approval: {from_text}")
            return False

    def reject_suggestion(self, from_text: str, to_text: str) -> None:
        """
        Reject a suggestion (move to rejected list).

        CRITICAL FIX: Acquires BOTH pending and rejected locks in consistent order.
        This prevents deadlocks when multiple threads call this method concurrently.

        Lock acquisition order: pending_lock, then rejected_lock (alphabetical).

        Args:
            from_text: The 'from' text of suggestion to reject
            to_text: The 'to' text of suggestion to reject
        """
        # CRITICAL FIX: Acquire locks in consistent order to prevent deadlock
        # Order: pending < rejected (alphabetically by filename)
        with self._file_lock(self.pending_lock, "reject suggestion (pending)"):
            # Remove from pending
            pending = self._load_pending_suggestions_unlocked()
            original_count = len(pending)
            pending = [s for s in pending
                      if not (s["from_text"] == from_text and s["to_text"] == to_text)]
            self._save_suggestions_unlocked(pending, self.pending_file)

            removed = original_count - len(pending)
            if removed > 0:
                logger.info(f"Removed {removed} suggestions from pending: {from_text} → {to_text}")

        # Now acquire rejected lock (separate operation, different file)
        with self._file_lock(self.rejected_lock, "reject suggestion (rejected)"):
            # Add to rejected
            rejected = self._load_rejected_unlocked()
            rejected.add((from_text, to_text))
            self._save_rejected_unlocked(rejected)
            logger.info(f"Added to rejected: {from_text} → {to_text}")

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

    def _load_pending_suggestions_unlocked(self) -> List[Dict]:
        """
        Load pending suggestions from file (UNLOCKED - caller must hold lock).

        Internal method. Use _load_pending_suggestions() for thread-safe access.

        Returns:
            List of suggestion dictionaries
        """
        if not self.pending_file.exists():
            return []

        with open(self.pending_file, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                return []
            return json.loads(content).get("suggestions", [])

    def _load_pending_suggestions(self) -> List[Dict]:
        """
        Load pending suggestions from file (THREAD-SAFE).

        CRITICAL FIX: Acquires lock before reading to ensure consistency.

        Returns:
            List of suggestion dictionaries
        """
        with self._file_lock(self.pending_lock, "load pending suggestions"):
            return self._load_pending_suggestions_unlocked()

    def _save_pending_suggestions(self, suggestions: List[Suggestion]) -> None:
        """
        Save pending suggestions to file.

        CRITICAL FIX: Atomic read-modify-write operation with file lock.
        Prevents race conditions where concurrent writes could lose data.
        """
        # CRITICAL FIX: Acquire lock for entire read-modify-write operation
        with self._file_lock(self.pending_lock, "save pending suggestions"):
            # Read
            existing = self._load_pending_suggestions_unlocked()

            # Modify
            new_suggestions = [asdict(s) for s in suggestions]
            all_suggestions = existing + new_suggestions

            # Write
            # All done atomically under lock
            self._save_suggestions_unlocked(all_suggestions, self.pending_file)

    def _save_suggestions_unlocked(self, suggestions: List[Dict], filepath: Path) -> None:
        """
        Save suggestions to file (UNLOCKED - caller must hold lock).

        Internal method. Caller must acquire appropriate lock before calling.

        Args:
            suggestions: List of suggestion dictionaries
            filepath: Path to save to
        """
        # Ensure parent directory exists
        filepath.parent.mkdir(parents=True, exist_ok=True)

        data = {"suggestions": suggestions}
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_rejected_unlocked(self) -> set:
        """
        Load rejected patterns (UNLOCKED - caller must hold lock).

        Internal method. Use _load_rejected() for thread-safe access.

        Returns:
            Set of (from_text, to_text) tuples
        """
        if not self.rejected_file.exists():
            return set()

        with open(self.rejected_file, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                return set()
            data = json.loads(content)
            return {(r["from"], r["to"]) for r in data.get("rejected", [])}

    def _load_rejected(self) -> set:
        """
        Load rejected patterns (THREAD-SAFE).

        CRITICAL FIX: Acquires lock before reading to ensure consistency.

        Returns:
            Set of (from_text, to_text) tuples
        """
        with self._file_lock(self.rejected_lock, "load rejected"):
            return self._load_rejected_unlocked()

    def _save_rejected_unlocked(self, rejected: set) -> None:
        """
        Save rejected patterns (UNLOCKED - caller must hold lock).

        Internal method. Caller must acquire rejected_lock before calling.

        Args:
            rejected: Set of (from_text, to_text) tuples
        """
        # Ensure parent directory exists
        self.rejected_file.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "rejected": [
                {"from": from_text, "to": to_text}
                for from_text, to_text in rejected
            ]
        }
        with open(self.rejected_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _save_rejected(self, rejected: set) -> None:
        """
        Save rejected patterns (THREAD-SAFE).

        CRITICAL FIX: Acquires lock before writing to prevent race conditions.

        Args:
            rejected: Set of (from_text, to_text) tuples
        """
        with self._file_lock(self.rejected_lock, "save rejected"):
            self._save_rejected_unlocked(rejected)

    def analyze_and_auto_approve(self, changes: List, domain: str = "general") -> Dict:
        """
        Analyze AI changes and auto-approve high-confidence patterns

        This is the CORE learning loop:
        1. Group changes by pattern
        2. Find high-frequency, high-confidence patterns
        3. Auto-add to dictionary (no manual review needed)
        4. Track auto-approvals for transparency

        Args:
            changes: List of AIChange objects from recent AI processing
            domain: Domain to add corrections to

        Returns:
            Dict with stats: {
                "total_changes": int,
                "unique_patterns": int,
                "auto_approved": int,
                "pending_review": int,
                "savings_potential": str
            }
        """
        if not changes:
            return {"total_changes": 0, "unique_patterns": 0, "auto_approved": 0, "pending_review": 0}

        # Group changes by pattern
        patterns = {}
        for change in changes:
            key = (change.from_text, change.to_text)
            if key not in patterns:
                patterns[key] = []
            patterns[key].append(change)

        stats = {
            "total_changes": len(changes),
            "unique_patterns": len(patterns),
            "auto_approved": 0,
            "pending_review": 0,
            "savings_potential": ""
        }

        auto_approved_patterns = []
        pending_patterns = []

        for (from_text, to_text), occurrences in patterns.items():
            frequency = len(occurrences)

            # Calculate confidence
            confidences = [c.confidence for c in occurrences]
            avg_confidence = sum(confidences) / len(confidences)

            # Auto-approve if meets strict criteria
            if (frequency >= self.AUTO_APPROVE_FREQUENCY and
                avg_confidence >= self.AUTO_APPROVE_CONFIDENCE):

                if self.correction_service:
                    try:
                        self.correction_service.add_correction(from_text, to_text, domain)
                        auto_approved_patterns.append({
                            "from": from_text,
                            "to": to_text,
                            "frequency": frequency,
                            "confidence": avg_confidence,
                            "domain": domain
                        })
                        stats["auto_approved"] += 1
                    except Exception as e:
                        # Already exists or validation error
                        pass

            # Add to pending review if meets minimum criteria
            elif (frequency >= self.MIN_FREQUENCY and
                  avg_confidence >= self.MIN_CONFIDENCE):
                pending_patterns.append({
                    "from": from_text,
                    "to": to_text,
                    "frequency": frequency,
                    "confidence": avg_confidence
                })
                stats["pending_review"] += 1

        # Save auto-approved for transparency
        if auto_approved_patterns:
            self._save_auto_approved(auto_approved_patterns)

        # Calculate savings potential
        total_dict_covered = sum(p["frequency"] for p in auto_approved_patterns)
        if total_dict_covered > 0:
            savings_pct = int((total_dict_covered / stats["total_changes"]) * 100)
            stats["savings_potential"] = f"{savings_pct}% of current errors now handled by dictionary (free)"

        return stats

    def _save_auto_approved(self, patterns: List[Dict]) -> None:
        """
        Save auto-approved patterns for transparency.

        CRITICAL FIX: Atomic read-modify-write operation with file lock.
        Prevents race conditions where concurrent auto-approvals could lose data.

        Args:
            patterns: List of pattern dictionaries to save
        """
        # CRITICAL FIX: Acquire lock for entire read-modify-write operation
        with self._file_lock(self.auto_approved_lock, "save auto-approved"):
            # Load existing
            existing = []
            if self.auto_approved_file.exists():
                with open(self.auto_approved_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        data = json.load(json.loads(content) if isinstance(content, str) else f)
                        existing = data.get("auto_approved", [])

            # Append new
            all_patterns = existing + patterns

            # Save
            self.auto_approved_file.parent.mkdir(parents=True, exist_ok=True)
            data = {"auto_approved": all_patterns}
            with open(self.auto_approved_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.info(f"Saved {len(patterns)} auto-approved patterns (total: {len(all_patterns)})")
