#!/usr/bin/env python3
"""
Unit Tests for Correction Service

Tests business logic, validation, and service layer functionality.
"""

import unittest
import tempfile
import shutil
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.correction_repository import CorrectionRepository
from core.correction_service import CorrectionService, ValidationError


class TestCorrectionService(unittest.TestCase):
    """Test suite for CorrectionService"""

    def setUp(self):
        """Create temporary database for each test."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.db_path = self.test_dir / "test.db"
        self.repository = CorrectionRepository(self.db_path)
        self.service = CorrectionService(self.repository)

    def tearDown(self):
        """Clean up temporary files."""
        self.service.close()
        shutil.rmtree(self.test_dir)

    # ==================== Validation Tests ====================

    def test_validate_empty_text(self):
        """Test rejection of empty text."""
        with self.assertRaises(ValidationError):
            self.service.validate_correction_text("", "test_field")

    def test_validate_whitespace_only(self):
        """Test rejection of whitespace-only text."""
        with self.assertRaises(ValidationError):
            self.service.validate_correction_text("   ", "test_field")

    def test_validate_too_long(self):
        """Test rejection of text exceeding max length."""
        long_text = "A" * 1001
        with self.assertRaises(ValidationError):
            self.service.validate_correction_text(long_text, "test_field")

    def test_validate_control_characters(self):
        """Test rejection of control characters."""
        with self.assertRaises(ValidationError):
            self.service.validate_correction_text("test\x00text", "test_field")

    def test_validate_valid_text(self):
        """Test acceptance of valid text."""
        # Should not raise
        self.service.validate_correction_text("valid text", "test_field")
        self.service.validate_correction_text("有效文本", "test_field")

    def test_validate_domain_path_traversal(self):
        """Test rejection of path traversal in domain."""
        with self.assertRaises(ValidationError):
            self.service.validate_domain_name("../etc/passwd")

    def test_validate_domain_invalid_chars(self):
        """Test rejection of invalid characters in domain."""
        with self.assertRaises(ValidationError):
            self.service.validate_domain_name("invalid/domain")

    def test_validate_domain_reserved(self):
        """Test rejection of reserved domain names."""
        with self.assertRaises(ValidationError):
            self.service.validate_domain_name("con")  # Windows reserved

    def test_validate_valid_domain(self):
        """Test acceptance of valid domain."""
        # Should not raise
        self.service.validate_domain_name("general")
        self.service.validate_domain_name("embodied_ai")
        self.service.validate_domain_name("test-domain-123")

    def test_validate_chinese_domain(self):
        """Test acceptance of Chinese domain names."""
        # Should not raise - Chinese characters are valid
        self.service.validate_domain_name("火星加速器")
        self.service.validate_domain_name("具身智能")
        self.service.validate_domain_name("中文域名-123")
        self.service.validate_domain_name("混合domain中文")

    # ==================== Correction Operations Tests ====================

    def test_add_correction(self):
        """Test adding a correction."""
        correction_id = self.service.add_correction(
            from_text="错误",
            to_text="正确",
            domain="general"
        )
        self.assertIsInstance(correction_id, int)
        self.assertGreater(correction_id, 0)

        # Verify it was added
        corrections = self.service.get_corrections("general")
        self.assertEqual(corrections["错误"], "正确")

    def test_add_identical_correction_rejected(self):
        """Test rejection of from_text == to_text."""
        with self.assertRaises(ValidationError):
            self.service.add_correction(
                from_text="same",
                to_text="same",
                domain="general"
            )

    def test_add_duplicate_correction_updates(self):
        """Test that duplicate from_text updates existing."""
        # Add first
        self.service.add_correction("错误", "正确A", "general")

        # Add duplicate (should update)
        self.service.add_correction("错误", "正确B", "general")

        # Verify updated
        corrections = self.service.get_corrections("general")
        self.assertEqual(corrections["错误"], "正确B")

    def test_get_corrections_multiple_domains(self):
        """Test getting corrections from different domains."""
        self.service.add_correction("test1", "result1", "domain1")
        self.service.add_correction("test2", "result2", "domain2")

        domain1_corr = self.service.get_corrections("domain1")
        domain2_corr = self.service.get_corrections("domain2")

        self.assertEqual(len(domain1_corr), 1)
        self.assertEqual(len(domain2_corr), 1)
        self.assertEqual(domain1_corr["test1"], "result1")
        self.assertEqual(domain2_corr["test2"], "result2")

    def test_remove_correction(self):
        """Test removing a correction."""
        # Add correction
        self.service.add_correction("错误", "正确", "general")

        # Remove it
        success = self.service.remove_correction("错误", "general")
        self.assertTrue(success)

        # Verify removed
        corrections = self.service.get_corrections("general")
        self.assertNotIn("错误", corrections)

    def test_remove_nonexistent_correction(self):
        """Test removing non-existent correction."""
        success = self.service.remove_correction("nonexistent", "general")
        self.assertFalse(success)

    # ==================== Import/Export Tests ====================

    def test_import_corrections(self):
        """Test importing corrections."""
        import_data = {
            "错误1": "正确1",
            "错误2": "正确2",
            "错误3": "正确3"
        }

        inserted, updated, skipped = self.service.import_corrections(
            corrections=import_data,
            domain="test_domain",
            merge=True
        )

        self.assertEqual(inserted, 3)
        self.assertEqual(updated, 0)
        self.assertEqual(skipped, 0)

        # Verify imported
        corrections = self.service.get_corrections("test_domain")
        self.assertEqual(len(corrections), 3)

    def test_import_merge_with_conflicts(self):
        """Test import with merge mode and conflicts."""
        # Add existing correction
        self.service.add_correction("错误", "旧值", "test_domain")

        # Import with conflict
        import_data = {
            "错误": "新值",
            "新错误": "新正确"
        }

        inserted, updated, skipped = self.service.import_corrections(
            corrections=import_data,
            domain="test_domain",
            merge=True
        )

        self.assertEqual(inserted, 1)  # "新错误"
        self.assertEqual(updated, 1)   # "错误" updated

        # Verify updated
        corrections = self.service.get_corrections("test_domain")
        self.assertEqual(corrections["错误"], "新值")
        self.assertEqual(corrections["新错误"], "新正确")

    def test_export_corrections(self):
        """Test exporting corrections."""
        # Add some corrections
        self.service.add_correction("错误1", "正确1", "export_test")
        self.service.add_correction("错误2", "正确2", "export_test")

        # Export
        exported = self.service.export_corrections("export_test")

        self.assertEqual(len(exported), 2)
        self.assertEqual(exported["错误1"], "正确1")
        self.assertEqual(exported["错误2"], "正确2")

    # ==================== Statistics Tests ====================

    def test_get_statistics_empty(self):
        """Test statistics for empty domain."""
        stats = self.service.get_statistics("empty_domain")

        self.assertEqual(stats['total_corrections'], 0)
        self.assertEqual(stats['total_usage'], 0)

    def test_get_statistics(self):
        """Test statistics calculation."""
        # Add corrections with different sources
        self.service.add_correction("test1", "result1", "stats_test", source="manual")
        self.service.add_correction("test2", "result2", "stats_test", source="learned")
        self.service.add_correction("test3", "result3", "stats_test", source="imported")

        stats = self.service.get_statistics("stats_test")

        self.assertEqual(stats['total_corrections'], 3)
        self.assertEqual(stats['by_source']['manual'], 1)
        self.assertEqual(stats['by_source']['learned'], 1)
        self.assertEqual(stats['by_source']['imported'], 1)


class TestValidationRules(unittest.TestCase):
    """Test validation rules configuration."""

    def test_custom_validation_rules(self):
        """Test service with custom validation rules."""
        from core.correction_service import ValidationRules

        custom_rules = ValidationRules(
            max_text_length=100,
            min_text_length=3
        )

        test_dir = Path(tempfile.mkdtemp())
        db_path = test_dir / "test.db"
        repository = CorrectionRepository(db_path)
        service = CorrectionService(repository, rules=custom_rules)

        # Should reject short text
        with self.assertRaises(ValidationError):
            service.validate_correction_text("ab", "test")  # Too short

        # Should reject long text
        with self.assertRaises(ValidationError):
            service.validate_correction_text("A" * 101, "test")  # Too long

        # Clean up
        service.close()
        shutil.rmtree(test_dir)


if __name__ == '__main__':
    unittest.main()
