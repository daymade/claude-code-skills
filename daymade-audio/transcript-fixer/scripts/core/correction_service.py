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
import sys
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass

from .correction_repository import (
    CorrectionRepository,
    ValidationError,
    DatabaseError,
    normalize_domains,
)

# Import safety check for common words
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.common_words import (check_correction_safety, audit_corrections, SafetyWarning,
                                UNFORCEABLE_CATEGORIES, unforceable_shape)

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
        notes: Optional[str] = None,
        force: bool = False,
        update_existing: bool = True,
    ) -> int:
        """
        Add a correction with full validation and safety checks.

        Safety checks detect common Chinese words and substring collision
        risks that would cause false positives. Pass force=True to bypass
        (errors become warnings printed to stderr).

        Args:
            from_text: Original (incorrect) text
            to_text: Corrected text
            domain: Correction domain
            source: Origin of correction
            confidence: Confidence score
            notes: Optional notes
            force: If True, downgrade safety errors to warnings
            update_existing: Whether an existing active mapping may be updated

        Returns:
            ID of inserted correction

        Raises:
            ValidationError: If validation or safety check fails
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

        # Safety check: detect common words and substring collisions
        safety_warnings = check_correction_safety(from_text, to_text, strict=True)

        if safety_warnings:
            errors = [w for w in safety_warnings if w.level == "error"]
            warns = [w for w in safety_warnings if w.level == "warning"]

            unforceable = [w for w in errors if w.category in UNFORCEABLE_CATEGORIES]
            if unforceable:
                # Not a judgement call --force can take: the shape is wrong for
                # every transcript, so the mapping belongs in a context trap.
                raise ValidationError(
                    f"Safety check BLOCKED adding '{from_text}' -> '{to_text}':\n"
                    + "\n".join(f"[{w.category}] {w.message}\n  Suggestion: {w.suggestion}"
                                for w in unforceable)
                    + "\n\nThis shape cannot be forced; scope it as a context-file trap."
                )

            if errors and not force:
                # Block the addition
                msg_parts = []
                for w in errors:
                    msg_parts.append(f"[{w.category}] {w.message}")
                    msg_parts.append(f"  Suggestion: {w.suggestion}")
                raise ValidationError(
                    f"Safety check BLOCKED adding '{from_text}' -> '{to_text}':\n"
                    + "\n".join(msg_parts)
                    + "\n\nUse --force to override (at your own risk)."
                )

            # Print warnings (errors downgraded by --force, or genuine warnings)
            all_to_print = errors + warns if force else warns
            if all_to_print:
                for w in all_to_print:
                    prefix = "FORCED" if w.level == "error" else "WARNING"
                    logger.warning(
                        f"[{prefix}] [{w.category}] {w.message} | {w.suggestion}"
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
                notes=notes,
                force=force,
                update_existing=update_existing,
            )

            logger.info(
                f"Successfully added correction ID {correction_id}: "
                f"'{from_text}' → '{to_text}' (domain: {domain})"
            )
            return correction_id

        except DatabaseError as e:
            logger.error(f"Failed to add correction: {e}")
            raise

    def get_corrections_with_metadata(
        self, domain: Optional[Union[str, List[str]]] = None
    ) -> Tuple[Dict[str, str], Dict[str, Dict]]:
        """
        Get corrections as a dictionary plus per-rule metadata.

        `domain` accepts one name or a list (CLI comma-separated --domain); a
        list loads the union of those domains. Each rule's metadata carries
        its own `domain` so multi-domain runs never lose track of which
        project a rule came from.

        Returns:
            Tuple of (corrections_dict, metadata_dict) where metadata_dict
            maps from_text -> {"confidence": float, "notes": str, "domain": str}
        """
        domains = normalize_domains(domain)
        if domains:
            for d in domains:
                self.validate_domain_name(d)
            corrections = self.repository.get_all_corrections(domain=domains, active_only=True)
        else:
            corrections = self.repository.get_all_corrections(active_only=True)

        # Cross-domain from_text collisions resolve deterministically: when
        # several named domains carry the same from_text, the EARLIEST domain
        # in the caller's list wins (the CLI documents the first --domain
        # entry as primary). Without this, the winner fell out of SQLite's
        # scan order — a rule's target could flip with no visible cause, and
        # --apply-domain would then trust and auto-apply an arbitrary winner.
        # Single-domain and no-filter paths keep their historical behavior.
        corrections_dict: Dict[str, str] = {}
        metadata: Dict[str, Dict] = {}
        priority = {d: i for i, d in enumerate(domains)} if domains else {}
        for c in corrections:
            existing = metadata.get(c.from_text)
            if existing is not None and priority:
                if priority.get(c.domain, len(priority)) >= priority.get(existing["domain"], len(priority)):
                    continue  # earlier-named domain already claimed this key
            corrections_dict[c.from_text] = c.to_text
            metadata[c.from_text] = {"confidence": c.confidence, "notes": c.notes or "", "domain": c.domain}
        return corrections_dict, metadata

    def get_disabled_pairs(self, domain: Optional[Union[str, List[str]]] = None) -> set:
        """(from_text, to_text) pairs a human has explicitly disabled.

        Needed because disabling is not the end of a rule's life. Three sources
        feed Stage 1 — this DB, the people roster, and (as priors only) the
        domain context file — and the roster merge fills gaps by asking "is this
        from_text absent from the loaded corrections?". A disabled rule IS
        absent, because loading filters on is_active. So `--report-false-positive`
        removes a rule from the DB and the roster silently puts it straight back
        on the next run, with no way to disable it again: the report command sees
        no *active* row, prints "No active rule" and exits 1, while the rule is
        demonstrably still firing.

        Pairs, not bare from_texts: a domain may disable X→Y precisely to retarget
        X→Z, and vetoing on from_text alone would also suppress a roster entry
        that is correct — trading a visible wrong replacement for an invisible
        missing one, which is harder to notice.
        """
        corrections = self.repository.get_all_corrections(
            domain=normalize_domains(domain) or None, active_only=False)
        return {(c.from_text, c.to_text) for c in corrections if not getattr(c, "is_active", True)}

    def get_corrections(self, domain: Optional[Union[str, List[str]]] = None) -> Dict[str, str]:
        """
        Get corrections as a dictionary for processing.

        Args:
            domain: Optional domain filter — one name or a list (list loads
                the union, matching the CLI's comma-separated --domain)

        Returns:
            Dictionary of corrections {from_text: to_text}
        """
        domains = normalize_domains(domain)
        if domains:
            for d in domains:
                self.validate_domain_name(d)
            corrections = self.repository.get_all_corrections(domain=domains, active_only=True)
            # Same deterministic collision rule as get_corrections_with_metadata:
            # earliest-named domain wins a from_text tie; no-filter keeps the
            # historical last-writer behavior.
            priority = {d: i for i, d in enumerate(domains)}
            out: Dict[str, str] = {}
            owners: Dict[str, str] = {}
            for c in corrections:
                if c.from_text in owners and priority.get(c.domain, len(priority)) >= priority.get(owners[c.from_text], len(priority)):
                    continue
                owners[c.from_text] = c.domain
                out[c.from_text] = c.to_text
            return out
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
                # Shapes no rule may carry are refused here too: this import
                # path bypasses check_correction_safety, and such a rule would
                # silently auto-apply under a trusted domain. Same predicate as
                # add time (utils/common_words.py) and the roster loader.
                shape = unforceable_shape(from_text)
                if shape:
                    logger.error(
                        f"Validation failed for '{from_text}' → '{to_text}': "
                        + ("bare numeric FROM can never be a rule; use a context-file trap"
                           if shape == "numeric_text" else
                           "a single surname + honorific names everyone with that surname; "
                           "use a context-file trap")
                    )
                    invalid_count += 1
                    continue
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

    def get_domain_stats(self) -> Dict[str, int]:
        """Get count of active corrections per domain."""
        all_corrections = self.repository.get_all_corrections(active_only=True)
        stats: Dict[str, int] = {}
        for c in all_corrections:
            stats[c.domain] = stats.get(c.domain, 0) + 1
        return stats

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

    # ==================== Audit Operations ====================

    def audit_dictionary(
        self,
        domain: Optional[str] = None,
    ) -> Dict[str, List[SafetyWarning]]:
        """
        Audit all active corrections for safety issues.

        Scans every rule and flags:
        - from_text that is a common Chinese word (false positive risk)
        - from_text that is <= 2 characters (high collision risk)
        - from_text that appears as substring in common words (collateral damage)
        - Both from_text and to_text being common words (bidirectional risk)

        Args:
            domain: Optional domain filter (None = all domains)

        Returns:
            Dict mapping from_text to list of SafetyWarnings.
            Only entries with issues are included.
        """
        corrections = self.get_corrections(domain)
        return audit_corrections(corrections)

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

    def load_context_rules(self, domains: Optional[List[str]] = None) -> List[Dict]:
        """
        Load active context-aware regex rules.

        A rule with domain = NULL is global and always loads; a rule with a
        named domain only loads when that domain is in `domains`. Passing no
        filter (None) keeps the legacy union behavior and loads every active
        rule — mirroring how corrections load without --domain.

        On a database not yet migrated to v2.4 there IS no domain column, and
        by construction no rule could have been added with a domain — so every
        rule is global and the legacy query is the correct one.

        Args:
            domains: Active domain names, or None for no filter

        Returns:
            List of rule dictionaries with pattern, replacement, description
        """
        try:
            with self.repository._pool.get_connection() as conn:
                has_domain_col = any(
                    row[1] == "domain"
                    for row in conn.execute("PRAGMA table_info(context_rules)")
                )
                if has_domain_col and domains:
                    placeholders = ", ".join("?" for _ in domains)
                    cursor = conn.execute(
                        f"""
                        SELECT pattern, replacement, description
                        FROM context_rules
                        WHERE is_active = 1
                          AND (domain IS NULL OR domain IN ({placeholders}))
                        ORDER BY priority DESC
                        """,
                        domains,
                    )
                else:
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

    def add_context_rule(
        self,
        pattern: str,
        replacement: str,
        domain: Optional[str] = None,
        description: Optional[str] = None,
        priority: int = 0,
        added_by: Optional[str] = None,
    ) -> int:
        """
        Add a context-aware regex rule.

        Args:
            pattern: Regex pattern matched against the transcript text
            replacement: Replacement text for each match
            domain: Scope the rule to one domain; None = global (applies to
                every domain)
            description: Human-readable rule name (used as the change's
                rule_name in reports)
            priority: Higher priority rules apply first
            added_by: Provenance label

        Returns:
            ID of the inserted rule

        Raises:
            ValidationError: On empty pattern/replacement, a bad regex, a
                malformed domain, a duplicate pattern, or a database not yet
                migrated to v2.4 (domain column missing).
        """
        if not pattern or not pattern.strip():
            raise ValidationError("context rule pattern must not be empty")
        if not replacement or not replacement.strip():
            raise ValidationError("context rule replacement must not be empty")
        import re as _re
        try:
            _re.compile(pattern)
        except _re.error as e:
            raise ValidationError(f"invalid context rule pattern {pattern!r}: {e}")
        if domain is not None:
            self.validate_domain_name(domain)

        with self.repository._pool.get_connection() as conn:
            has_domain_col = any(
                row[1] == "domain"
                for row in conn.execute("PRAGMA table_info(context_rules)")
            )
            if not has_domain_col:
                raise ValidationError(
                    "context_rules has no domain column — migrate the "
                    "database to v2.4. Canonical path: fix_transcription.py "
                    "--migration migrate. If that runner reports version 0.0 "
                    "on this DB (a pre-existing runner issue on schema.sql-"
                    "built databases), apply the additive column directly "
                    "instead: sqlite3 <db> \"ALTER TABLE context_rules "
                    "ADD COLUMN domain TEXT\""
                )
            duplicate = conn.execute(
                "SELECT id FROM context_rules WHERE pattern = ?", (pattern,)
            ).fetchone()
            if duplicate:
                raise ValidationError(
                    f"context rule pattern already exists (id {duplicate[0]}): {pattern!r}"
                )
            cursor = conn.execute(
                """
                INSERT INTO context_rules
                    (pattern, replacement, description, priority, added_by, domain)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (pattern, replacement, description, priority, added_by, domain),
            )
            rule_id = cursor.lastrowid
            conn.execute(
                """
                INSERT INTO audit_log (action, entity_type, entity_id, details)
                VALUES ('add_context_rule', 'context_rules', ?, ?)
                """,
                (rule_id, f"{pattern!r} -> {replacement!r} (domain: {domain or 'global'})"),
            )
            conn.commit()
            logger.info(f"Added context rule {rule_id}: {pattern!r} (domain: {domain or 'global'})")
            return rule_id

    def list_context_rules(
        self, domain: Optional[str] = None, include_inactive: bool = False
    ) -> List[Dict]:
        """
        List context rules, optionally filtered to one domain plus globals.

        Args:
            domain: Show global rules plus rules of this domain; None lists
                every rule regardless of domain
            include_inactive: Also list disabled rules

        Returns:
            List of rule dicts with id/pattern/replacement/description/
            priority/domain/is_active
        """
        with self.repository._pool.get_connection() as conn:
            has_domain_col = any(
                row[1] == "domain"
                for row in conn.execute("PRAGMA table_info(context_rules)")
            )
            domain_expr = "domain" if has_domain_col else "NULL AS domain"
            sql = f"""
                SELECT id, pattern, replacement, description, priority,
                       {domain_expr}, is_active
                FROM context_rules
            """
            params: list = []
            clauses = []
            if not include_inactive:
                clauses.append("is_active = 1")
            if domain is not None and has_domain_col:
                clauses.append("(domain IS NULL OR domain = ?)")
                params.append(domain)
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)
            sql += " ORDER BY priority DESC, id"
            cursor = conn.execute(sql, params)
            return [
                {
                    "id": row[0],
                    "pattern": row[1],
                    "replacement": row[2],
                    "description": row[3],
                    "priority": row[4],
                    "domain": row[5],
                    "is_active": bool(row[6]),
                }
                for row in cursor.fetchall()
            ]

    def save_history(self, filename: str, domain: str, original_length: int,
                    stage1_changes: int, stage2_changes: int, model: str,
                    changes: List[Any], *, success: bool = True,
                    error_message: Optional[str] = None) -> int:
        """
        Save correction run history for learning.

        Args:
            filename: File that was corrected
            domain: Correction domain
            original_length: Original file length
            stage1_changes: Number of Stage 1 changes
            stage2_changes: Number of Stage 2 changes
            model: AI model used
            changes: List of individual changes (dict or dataclass: Change / AIChange)
            success: False when any API chunk degraded to retained source text
            error_message: Durable explanation for a degraded run

        Returns:
            The committed correction_history row ID.

        Raises:
            DatabaseError: If history or any detail row cannot be persisted.
        """
        def _normalize_change(change):
            """Extract standard fields from dict or dataclass (Change / AIChange)."""
            if isinstance(change, dict):
                rule_type = change.get("rule_type", "dictionary")
                if rule_type == "context_rule":
                    rule_type = "context"
                return {
                    "line_number": change.get("line_number"),
                    "from_text": change.get("from_text", ""),
                    "to_text": change.get("to_text", ""),
                    "rule_type": rule_type,
                    "context_before": change.get("context_before"),
                    "context_after": change.get("context_after"),
                    "change_type": change.get("change_type", "unknown"),
                    "learnable": bool(change.get("learnable", True)),
                    "confidence": change.get("confidence"),
                    "model": change.get("model"),
                }
            # Dataclass fallback: Change has line_number/rule_type;
            # AIChange has chunk_index/change_type instead.
            line_number = getattr(change, "line_number", None)
            if line_number is None:
                line_number = getattr(change, "chunk_index", None)

            rule_type = getattr(change, "rule_type", None)
            if rule_type is None:
                change_type = getattr(change, "change_type", "ai")
                # DB CHECK constraint only allows context/dictionary/ai
                rule_type = change_type if change_type in ("context", "dictionary", "ai") else "ai"
            elif rule_type == "context_rule":
                rule_type = "context"

            return {
                "line_number": line_number,
                "from_text": getattr(change, "from_text", ""),
                "to_text": getattr(change, "to_text", ""),
                "rule_type": rule_type,
                "context_before": getattr(change, "context_before", None),
                "context_after": getattr(change, "context_after", None),
                "change_type": getattr(change, "change_type", "unknown"),
                "learnable": bool(getattr(change, "learnable", True)),
                "confidence": getattr(change, "confidence", None),
                "model": getattr(change, "model", None),
            }

        with self.repository._transaction() as conn:
            # Insert history record
            cursor = conn.execute("""
                INSERT INTO correction_history
                (filename, domain, original_length, stage1_changes, stage2_changes,
                 model, success, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                filename, domain, original_length, stage1_changes,
                stage2_changes, model, int(success), error_message,
            ))

            history_id = cursor.lastrowid

            # Insert individual changes
            for change in changes:
                normalized = _normalize_change(change)
                conn.execute("""
                    INSERT INTO correction_changes
                    (history_id, line_number, from_text, to_text, rule_type,
                     context_before, context_after, change_type, learnable,
                     confidence, model)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    history_id,
                    normalized["line_number"],
                    normalized["from_text"],
                    normalized["to_text"],
                    normalized["rule_type"],
                    normalized["context_before"],
                    normalized["context_after"],
                    normalized["change_type"],
                    int(normalized["learnable"]),
                    normalized["confidence"],
                    normalized["model"],
                ))

            logger.info(f"Saved correction history for {filename}: {stage1_changes + stage2_changes} total changes")

        assert history_id is not None
        return int(history_id)

    def report_false_positive(
        self,
        from_text: str,
        to_text: str,
        domain: str = "general",
        reported_by: Optional[str] = None
    ) -> bool:
        """
        Report a Stage 1 false positive.

        Action: lower confidence and mark inactive. The rule is not deleted
        so the audit trail is preserved, but it will no longer be applied.

        Returns:
            True if a matching active rule was found and disabled.
        """
        self.validate_correction_text(from_text, "from_text")
        self.validate_domain_name(domain)

        if reported_by is None:
            reported_by = os.getenv("USER") or os.getenv("USERNAME") or "unknown"

        correction = self.repository.get_correction(from_text, domain)
        if correction is None or correction.to_text != to_text:
            logger.warning(
                f"No active rule '{from_text}' -> '{to_text}' in domain '{domain}'"
            )
            return False

        # Disable the rule and append a false-positive note
        note_suffix = f"[FALSE POSITIVE reported by {reported_by}]"
        new_notes = f"{correction.notes or ''}\n{note_suffix}".strip()

        with self.repository._transaction() as conn:
            conn.execute("""
                UPDATE corrections
                SET is_active = 0,
                    confidence = 0.1,
                    notes = ?
                WHERE from_text = ? AND domain = ? AND is_active = 1
            """, (new_notes, from_text, domain))

            self.repository._audit_log(
                conn,
                action="report_false_positive",
                entity_type="correction",
                entity_id=correction.id,
                user=reported_by,
                details=f"Disabled '{from_text}' -> '{to_text}' (domain: {domain}) due to false positive"
            )

        logger.info(f"Disabled false-positive rule: '{from_text}' -> '{to_text}'")
        return True

    def load_presets(self, domain: str, loaded_by: Optional[str] = None) -> int:
        """
        Load preset corrections for a domain.

        Returns:
            Number of rules added or updated.
        """
        self.validate_domain_name(domain)

        if loaded_by is None:
            loaded_by = os.getenv("USER") or os.getenv("USERNAME") or "unknown"

        sys.path.insert(0, str(Path(__file__).parent.parent))
        from data.tech_presets import get_preset_rules

        rules = get_preset_rules(domain)
        added = 0
        for from_text, to_text, confidence, notes in rules:
            try:
                self.add_correction(
                    from_text=from_text,
                    to_text=to_text,
                    domain=domain,
                    source="imported",
                    confidence=confidence,
                    notes=f"preset: {notes}",
                    force=True,
                )
                added += 1
            except Exception as e:
                logger.warning(f"Skipping preset rule '{from_text}' -> '{to_text}': {e}")

        logger.info(f"Loaded {added} preset rules for domain '{domain}'")
        return added

    def close(self) -> None:
        """Close underlying repository."""
        self.repository.close()
        logger.info("CorrectionService closed")
