#!/usr/bin/env python3
"""
Correction Service - Business Logic Layer

SINGLE RESPONSIBILITY: Implement business rules and validation

Orchestrates repository operations with comprehensive validation,
error handling, and business logic enforcement.
"""

from __future__ import annotations

import re
import os
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from .correction_repository import (
    CorrectionRepository,
    ValidationError,
    DatabaseError
)

logger = logging.getLogger(__name__)


@dataclass
class ValidationRules:
    """Validation rules configuration"""
    max_text_length: int = 1000
    min_text_length: int = 1
    max_domain_length: int = 50
    # Support Chinese, Japanese, Korean characters in domain names
    # \u4e00-\u9fff: CJK Unified Ideographs (Chinese)
    # \u3040-\u309f: Hiragana, \u30a0-\u30ff: Katakana (Japanese)
    # \uac00-\ud7af: Hangul Syllables (Korean)
    allowed_domain_pattern: str = r'^[\w\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af-]+$'
    max_confidence: float = 1.0
    min_confidence: float = 0.0


class CorrectionService:
    """
    Service layer for correction management.

    Responsibilities:
    - Input validation and sanitization
    - Business rule enforcement
    - Conflict detection and resolution
    - Statistics and reporting
    - Integration with repository layer
    """

    def __init__(self, repository: CorrectionRepository, rules: Optional[ValidationRules] = None):
        """
        Initialize service with repository.

        Args:
            repository: Data access layer
            rules: Validation rules (uses defaults if None)
        """
        self.repository = repository
        self.rules = rules or ValidationRules()
        self.db_path = repository.db_path
        logger.info("CorrectionService initialized")

    def initialize(self) -> None:
        """
        Initialize database (already done by repository, kept for API compatibility).
        """
        # Database is auto-initialized by repository on first access
        logger.info(f"✅ Database ready: {self.db_path}")

    # ==================== Validation Methods ====================

    def validate_correction_text(self, text: str, field_name: str = "text") -> None:
        """
        Validate correction text with comprehensive checks.

        Args:
            text: Text to validate
            field_name: Field name for error messages

        Raises:
            ValidationError: If validation fails
        """
        # Check not None or empty
        if not text:
            raise ValidationError(f"{field_name} cannot be None or empty")

        # Check not only whitespace
        if not text.strip():
            raise ValidationError(f"{field_name} cannot be only whitespace")

        # Check length constraints
        if len(text) < self.rules.min_text_length:
            raise ValidationError(
                f"{field_name} too short: {len(text)} chars (min: {self.rules.min_text_length})"
            )

        if len(text) > self.rules.max_text_length:
            raise ValidationError(
                f"{field_name} too long: {len(text)} chars (max: {self.rules.max_text_length})"
            )

        # Check for control characters (except newline and tab)
        invalid_chars = [c for c in text if ord(c) < 32 and c not in '\n\t']
        if invalid_chars:
            raise ValidationError(
                f"{field_name} contains invalid control characters: {invalid_chars}"
            )

        # Check for NULL bytes
        if '\x00' in text:
            raise ValidationError(f"{field_name} contains NULL bytes")

    def validate_domain_name(self, domain: str) -> None:
        """
        Validate domain name to prevent path traversal and injection.

        Args:
            domain: Domain name to validate

        Raises:
            ValidationError: If validation fails
        """
        if not domain:
            raise ValidationError("Domain name cannot be empty")

        if len(domain) > self.rules.max_domain_length:
            raise ValidationError(
                f"Domain name too long: {len(domain)} chars (max: {self.rules.max_domain_length})"
            )

        # Check pattern: only alphanumeric, underscore, hyphen
        if not re.match(self.rules.allowed_domain_pattern, domain):
            raise ValidationError(
                f"Domain name contains invalid characters: {domain}. "
                f"Allowed pattern: {self.rules.allowed_domain_pattern}"
            )

        # Check for path traversal attempts
        if '..' in domain or '/' in domain or '\\' in domain:
            raise ValidationError(f"Domain name contains path traversal: {domain}")

        # Reserved names
        reserved = ['con', 'prn', 'aux', 'nul', 'com1', 'lpt1']  # Windows reserved
        if domain.lower() in reserved:
            raise ValidationError(f"Domain name is reserved: {domain}")

    def validate_confidence(self, confidence: float) -> None:
        """Validate confidence score."""
        if not isinstance(confidence, (int, float)):
            raise ValidationError(f"Confidence must be numeric, got {type(confidence)}")

        if not (self.rules.min_confidence <= confidence <= self.rules.max_confidence):
            raise ValidationError(
                f"Confidence must be between {self.rules.min_confidence} "
                f"and {self.rules.max_confidence}, got {confidence}"
            )

    def validate_source(self, source: str) -> None:
        """Validate correction source."""
        valid_sources = ['manual', 'learned', 'imported']
        if source not in valid_sources:
            raise ValidationError(
                f"Invalid source: {source}. Must be one of: {valid_sources}"
            )

    # ==================== Correction Operations ====================

    def add_correction(
        self,
        from_text: str,
        to_text: str,
        domain: str = "general",
        source: str = "manual",
        confidence: float = 1.0,
        notes: Optional[str] = None
    ) -> int:
        """
        Add a correction with full validation.

        Args:
            from_text: Original (incorrect) text
            to_text: Corrected text
            domain: Correction domain
            source: Origin of correction
            confidence: Confidence score
            notes: Optional notes

        Returns:
            ID of inserted correction

        Raises:
            ValidationError: If validation fails
        """
        # Comprehensive validation
        self.validate_correction_text(from_text, "from_text")
        self.validate_correction_text(to_text, "to_text")
        self.validate_domain_name(domain)
        self.validate_source(source)
        self.validate_confidence(confidence)

        # Business rule: from_text and to_text should be different
        if from_text.strip() == to_text.strip():
            raise ValidationError(
                f"from_text and to_text are identical: '{from_text}'"
            )

        # Get current user
        added_by = os.getenv("USER") or os.getenv("USERNAME") or "unknown"

        try:
            correction_id = self.repository.add_correction(
                from_text=from_text,
                to_text=to_text,
                domain=domain,
                source=source,
                confidence=confidence,
                added_by=added_by,
                notes=notes
            )

            logger.info(
                f"Successfully added correction ID {correction_id}: "
                f"'{from_text}' → '{to_text}' (domain: {domain})"
            )
            return correction_id

        except DatabaseError as e:
            logger.error(f"Failed to add correction: {e}")
            raise

    def get_corrections(self, domain: Optional[str] = None) -> Dict[str, str]:
        """
        Get corrections as a dictionary for processing.

        Args:
            domain: Optional domain filter

        Returns:
            Dictionary of corrections {from_text: to_text}
        """
        if domain:
            self.validate_domain_name(domain)
            return self.repository.get_corrections_dict(domain)
        else:
            # Get all domains
            all_corrections = self.repository.get_all_corrections(active_only=True)
            return {c.from_text: c.to_text for c in all_corrections}

    def remove_correction(
        self,
        from_text: str,
        domain: str = "general"
    ) -> bool:
        """
        Remove a correction (soft delete).

        Args:
            from_text: Text to remove
            domain: Domain

        Returns:
            True if removed, False if not found
        """
        self.validate_correction_text(from_text, "from_text")
        self.validate_domain_name(domain)

        deleted_by = os.getenv("USER") or os.getenv("USERNAME") or "unknown"

        success = self.repository.delete_correction(from_text, domain, deleted_by)

        if success:
            logger.info(f"Removed correction: '{from_text}' (domain: {domain})")
        else:
            logger.warning(f"Correction not found: '{from_text}' (domain: {domain})")

        return success

    # ==================== Import/Export Operations ====================

    def import_corrections(
        self,
        corrections: Dict[str, str],
        domain: str = "general",
        merge: bool = True,
        validate_all: bool = True
    ) -> Tuple[int, int, int]:
        """
        Import corrections with validation and conflict resolution.

        Args:
            corrections: Dictionary of corrections to import
            domain: Target domain
            merge: If True, merge with existing; if False, replace
            validate_all: If True, validate all before import (safer but slower)

        Returns:
            Tuple of (inserted_count, updated_count, skipped_count)

        Raises:
            ValidationError: If validation fails (when validate_all=True)
        """
        self.validate_domain_name(domain)

        if not corrections:
            raise ValidationError("Cannot import empty corrections dictionary")

        # Pre-validation (if requested)
        if validate_all:
            logger.info(f"Pre-validating {len(corrections)} corrections...")
            invalid_count = 0
            for from_text, to_text in corrections.items():
                try:
                    self.validate_correction_text(from_text, "from_text")
                    self.validate_correction_text(to_text, "to_text")
                except ValidationError as e:
                    logger.error(f"Validation failed for '{from_text}' → '{to_text}': {e}")
                    invalid_count += 1

            if invalid_count > 0:
                raise ValidationError(
                    f"Pre-validation failed: {invalid_count}/{len(corrections)} corrections invalid"
                )

        # Detect conflicts if merge mode
        if merge:
            existing = self.repository.get_corrections_dict(domain)
            conflicts = self._detect_conflicts(corrections, existing)

            if conflicts:
                logger.warning(
                    f"Found {len(conflicts)} conflicts that will be overwritten"
                )
                for from_text, (old_val, new_val) in conflicts.items():
                    logger.debug(f"Conflict: '{from_text}': '{old_val}' → '{new_val}'")

        # Perform import
        imported_by = os.getenv("USER") or os.getenv("USERNAME") or "unknown"

        try:
            inserted, updated, skipped = self.repository.bulk_import_corrections(
                corrections=corrections,
                domain=domain,
                source="imported",
                imported_by=imported_by,
                merge=merge
            )

            logger.info(
                f"Import complete: {inserted} inserted, {updated} updated, "
                f"{skipped} skipped (domain: {domain})"
            )

            return (inserted, updated, skipped)

        except DatabaseError as e:
            logger.error(f"Import failed: {e}")
            raise

    def export_corrections(self, domain: str = "general") -> Dict[str, str]:
        """
        Export corrections for sharing.

        Args:
            domain: Domain to export

        Returns:
            Dictionary of corrections
        """
        self.validate_domain_name(domain)

        corrections = self.repository.get_corrections_dict(domain)

        logger.info(f"Exported {len(corrections)} corrections (domain: {domain})")

        return corrections

    # ==================== Statistics and Reporting ====================

    def get_statistics(self, domain: Optional[str] = None) -> Dict[str, any]:
        """
        Get correction statistics.

        Args:
            domain: Optional domain filter

        Returns:
            Dictionary of statistics
        """
        if domain:
            self.validate_domain_name(domain)
            corrections = self.repository.get_all_corrections(domain=domain, active_only=True)
        else:
            corrections = self.repository.get_all_corrections(active_only=True)

        # Calculate statistics
        total = len(corrections)
        by_source = {'manual': 0, 'learned': 0, 'imported': 0}
        total_usage = 0
        high_confidence = 0

        for c in corrections:
            by_source[c.source] = by_source.get(c.source, 0) + 1
            total_usage += c.usage_count
            if c.confidence >= 0.9:
                high_confidence += 1

        stats = {
            'total_corrections': total,
            'by_source': by_source,
            'total_usage': total_usage,
            'average_usage': total_usage / total if total > 0 else 0,
            'high_confidence_count': high_confidence,
            'high_confidence_ratio': high_confidence / total if total > 0 else 0
        }

        logger.debug(f"Statistics for domain '{domain}': {stats}")

        return stats

    # ==================== Helper Methods ====================

    def _detect_conflicts(
        self,
        incoming: Dict[str, str],
        existing: Dict[str, str]
    ) -> Dict[str, Tuple[str, str]]:
        """
        Detect conflicts between incoming and existing corrections.

        Returns:
            Dictionary of conflicts {from_text: (existing_to, incoming_to)}
        """
        conflicts = {}

        for from_text in set(incoming.keys()) & set(existing.keys()):
            if existing[from_text] != incoming[from_text]:
                conflicts[from_text] = (existing[from_text], incoming[from_text])

        return conflicts

    def load_context_rules(self) -> List[Dict]:
        """
        Load active context-aware regex rules.

        Returns:
            List of rule dictionaries with pattern, replacement, description
        """
        try:
            with self.repository._pool.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT pattern, replacement, description
                    FROM context_rules
                    WHERE is_active = 1
                    ORDER BY priority DESC
                """)

                rules = []
                for row in cursor.fetchall():
                    rules.append({
                        "pattern": row[0],
                        "replacement": row[1],
                        "description": row[2]
                    })

                logger.debug(f"Loaded {len(rules)} context rules")
                return rules

        except Exception as e:
            logger.error(f"Failed to load context rules: {e}")
            return []

    def save_history(self, filename: str, domain: str, original_length: int,
                    stage1_changes: int, stage2_changes: int, model: str,
                    changes: List[Dict]) -> None:
        """
        Save correction run history for learning.

        Args:
            filename: File that was corrected
            domain: Correction domain
            original_length: Original file length
            stage1_changes: Number of Stage 1 changes
            stage2_changes: Number of Stage 2 changes
            model: AI model used
            changes: List of individual changes
        """
        try:
            with self.repository._transaction() as conn:
                # Insert history record
                cursor = conn.execute("""
                    INSERT INTO correction_history
                    (filename, domain, original_length, stage1_changes, stage2_changes, model)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (filename, domain, original_length, stage1_changes, stage2_changes, model))

                history_id = cursor.lastrowid

                # Insert individual changes
                for change in changes:
                    conn.execute("""
                        INSERT INTO correction_changes
                        (history_id, line_number, from_text, to_text, rule_type, context_before, context_after)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        history_id,
                        change.get("line_number"),
                        change.get("from_text", ""),
                        change.get("to_text", ""),
                        change.get("rule_type", "dictionary"),
                        change.get("context_before"),
                        change.get("context_after")
                    ))

                logger.info(f"Saved correction history for {filename}: {stage1_changes + stage2_changes} total changes")

        except Exception as e:
            logger.error(f"Failed to save history: {e}")

    def close(self) -> None:
        """Close underlying repository."""
        self.repository.close()
        logger.info("CorrectionService closed")
