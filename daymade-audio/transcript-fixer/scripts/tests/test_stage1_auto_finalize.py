#!/usr/bin/env python3
"""
Unit Tests for Stage 1 Auto-Finalize

Tests the _auto_finalize_stage1 helper that promotes *_stage1.md to the input
file and cleans up sidecars on re-run.
"""

import os
import shutil
import sys
import tempfile
import unittest
import argparse
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import cli.commands as commands_module
from cli.commands import STAGE1_SIDECAR_SUFFIXES, _auto_finalize_stage1, cmd_run_correction


class TestStage1AutoFinalize(unittest.TestCase):
    """Test suite for _auto_finalize_stage1"""

    def setUp(self):
        """Create a fresh temporary directory for each test."""
        self.test_dir = Path(tempfile.mkdtemp(prefix="tf_auto_finalize_"))
        self.input_file = self.test_dir / "meeting.md"
        self.input_file.write_text("original text\n", encoding="utf-8")

    def tearDown(self):
        """Remove the temporary directory and all its contents."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def _write_sidecars(self, stem="meeting"):
        """Create all known intermediate sidecars except *_stage1.md."""
        for suffix in STAGE1_SIDECAR_SUFFIXES:
            if suffix == "_stage1.md":
                continue
            (self.test_dir / f"{stem}{suffix}").write_text("sidecar\n", encoding="utf-8")

    def _make_stage1_newer(self, stage1: Path, input_path: Path):
        """Set stage1 mtime strictly newer than input_path using explicit timestamps."""
        now = 1_700_000_000
        os.utime(input_path, (now, now))
        os.utime(stage1, (now + 60, now + 60))

    def test_no_stage1_file_returns_false(self):
        """If no *_stage1.md exists, finalize does nothing."""
        result = _auto_finalize_stage1(self.input_file, self.test_dir)
        self.assertFalse(result)
        self.assertEqual(self.input_file.read_text(encoding="utf-8"), "original text\n")

    def test_stage1_older_than_input_is_skipped(self):
        """If input is newer than *_stage1.md, do not overwrite manual edits."""
        stage1 = self.test_dir / "meeting_stage1.md"
        stage1.write_text("corrected text\n", encoding="utf-8")
        now = 1_700_000_000
        os.utime(self.input_file, (now + 60, now + 60))
        os.utime(stage1, (now, now))

        result = _auto_finalize_stage1(self.input_file, self.test_dir)
        self.assertFalse(result)
        self.assertEqual(self.input_file.read_text(encoding="utf-8"), "original text\n")
        self.assertTrue(stage1.exists())

    def test_stage1_equal_mtime_is_skipped(self):
        """If stage1 and input have identical mtime, do not promote."""
        stage1 = self.test_dir / "meeting_stage1.md"
        stage1.write_text("corrected text\n", encoding="utf-8")
        now = 1_700_000_000
        os.utime(self.input_file, (now, now))
        os.utime(stage1, (now, now))

        result = _auto_finalize_stage1(self.input_file, self.test_dir)
        self.assertFalse(result)
        self.assertEqual(self.input_file.read_text(encoding="utf-8"), "original text\n")
        self.assertTrue(stage1.exists())

    def test_stage1_newer_promotes_and_cleans_sidecars(self):
        """If *_stage1.md is newer, promote it and remove sidecars."""
        stage1 = self.test_dir / "meeting_stage1.md"
        stage1.write_text("corrected text\n", encoding="utf-8")
        self._write_sidecars()
        self._make_stage1_newer(stage1, self.input_file)

        result = _auto_finalize_stage1(self.input_file, self.test_dir)
        self.assertTrue(result)
        self.assertEqual(self.input_file.read_text(encoding="utf-8"), "corrected text\n")
        self.assertFalse(stage1.exists())
        for suffix in STAGE1_SIDECAR_SUFFIXES:
            if suffix == "_stage1.md":
                continue
            self.assertFalse(
                (self.test_dir / f"meeting{suffix}").exists(),
                f"sidecar {suffix} should be removed",
            )

    def test_dry_run_does_not_modify_files(self):
        """Dry-run mode reports but does not touch files."""
        stage1 = self.test_dir / "meeting_stage1.md"
        stage1.write_text("corrected text\n", encoding="utf-8")
        self._write_sidecars()
        self._make_stage1_newer(stage1, self.input_file)
        original_content = self.input_file.read_text(encoding="utf-8")

        result = _auto_finalize_stage1(self.input_file, self.test_dir, dry_run=True)
        self.assertTrue(result)
        self.assertEqual(self.input_file.read_text(encoding="utf-8"), original_content)
        self.assertTrue(stage1.exists())
        for suffix in STAGE1_SIDECAR_SUFFIXES:
            if suffix == "_stage1.md":
                continue
            self.assertTrue(
                (self.test_dir / f"meeting{suffix}").exists(),
                f"sidecar {suffix} should remain in dry-run",
            )

    def test_dry_run_older_stage1_returns_false(self):
        """Dry-run does nothing when stage1 is not newer than input."""
        stage1 = self.test_dir / "meeting_stage1.md"
        stage1.write_text("corrected text\n", encoding="utf-8")
        now = 1_700_000_000
        os.utime(self.input_file, (now + 60, now + 60))
        os.utime(stage1, (now, now))
        self._write_sidecars()

        result = _auto_finalize_stage1(self.input_file, self.test_dir, dry_run=True)
        self.assertFalse(result)
        self.assertEqual(self.input_file.read_text(encoding="utf-8"), "original text\n")
        self.assertTrue(stage1.exists())

    def test_promotion_preserves_stage1_content(self):
        """Promoted file content matches the previous Stage 1 output."""
        stage1 = self.test_dir / "meeting_stage1.md"
        corrected = "line one\nline two\nClaude Code\n"
        stage1.write_text(corrected, encoding="utf-8")
        self._make_stage1_newer(stage1, self.input_file)

        _auto_finalize_stage1(self.input_file, self.test_dir)
        self.assertEqual(self.input_file.read_text(encoding="utf-8"), corrected)

    def test_no_sidecars_still_promotes(self):
        """Promotion works even when only *_stage1.md exists."""
        stage1 = self.test_dir / "meeting_stage1.md"
        stage1.write_text("only stage1\n", encoding="utf-8")
        self._make_stage1_newer(stage1, self.input_file)

        result = _auto_finalize_stage1(self.input_file, self.test_dir)
        self.assertTrue(result)
        self.assertEqual(self.input_file.read_text(encoding="utf-8"), "only stage1\n")
        self.assertFalse(stage1.exists())

    def test_missing_input_file_returns_false(self):
        """If the input file is gone, finalize does nothing."""
        stage1 = self.test_dir / "meeting_stage1.md"
        stage1.write_text("corrected text\n", encoding="utf-8")
        self.input_file.unlink()

        result = _auto_finalize_stage1(self.input_file, self.test_dir)
        self.assertFalse(result)
        self.assertTrue(stage1.exists())

    def test_multi_dot_filename_promotes(self):
        """Files with dots in the stem (e.g., 2026-07-07.meeting.md) are handled correctly."""
        input_file = self.test_dir / "2026-07-07.meeting.md"
        input_file.write_text("original text\n", encoding="utf-8")
        stage1 = self.test_dir / "2026-07-07.meeting_stage1.md"
        stage1.write_text("corrected text\n", encoding="utf-8")
        self._make_stage1_newer(stage1, input_file)

        result = _auto_finalize_stage1(input_file, self.test_dir)
        self.assertTrue(result)
        self.assertEqual(input_file.read_text(encoding="utf-8"), "corrected text\n")
        self.assertFalse(stage1.exists())

    def test_cross_filesystem_fallback(self):
        """If os.replace fails (e.g., cross-filesystem), copy+unlink fallback is used."""
        stage1 = self.test_dir / "meeting_stage1.md"
        stage1.write_text("corrected text\n", encoding="utf-8")
        self._write_sidecars()
        self._make_stage1_newer(stage1, self.input_file)

        original_replace = os.replace

        def failing_replace(_src, _dst):
            if Path(_src) == stage1:
                raise OSError(18, "Invalid cross-device link")
            return original_replace(_src, _dst)

        os.replace = failing_replace
        try:
            result = _auto_finalize_stage1(self.input_file, self.test_dir)
            self.assertTrue(result)
            self.assertEqual(self.input_file.read_text(encoding="utf-8"), "corrected text\n")
            self.assertFalse(stage1.exists())
        finally:
            os.replace = original_replace

    def test_cross_filesystem_copy_failure_preserves_input(self):
        """Fallback copies to a temp file so a failed copy cannot corrupt input."""
        stage1 = self.test_dir / "meeting_stage1.md"
        stage1.write_text("corrected text\n", encoding="utf-8")
        self._make_stage1_newer(stage1, self.input_file)

        original_replace = os.replace
        original_copy2 = commands_module.shutil.copy2

        def cross_device_then_normal(_src, _dst):
            if Path(_src) == stage1:
                raise OSError(18, "Invalid cross-device link")
            return original_replace(_src, _dst)

        def failing_copy2(_src, dst):
            Path(dst).write_text("partial copy\n", encoding="utf-8")
            raise OSError("copy failed")

        os.replace = cross_device_then_normal
        commands_module.shutil.copy2 = failing_copy2
        try:
            with self.assertRaises(OSError):
                _auto_finalize_stage1(self.input_file, self.test_dir)

            self.assertEqual(self.input_file.read_text(encoding="utf-8"), "original text\n")
            self.assertTrue(stage1.exists())
            temp_files = list(self.test_dir.glob(f".{self.input_file.name}.*.tmp"))
            self.assertEqual(temp_files, [])
        finally:
            commands_module.shutil.copy2 = original_copy2
            os.replace = original_replace

    def test_cmd_stage1_finalize_returns_without_recreating_sidecars(self):
        """A stage-1 rerun should finalize and stop, not run Stage 1 again."""
        stage1 = self.test_dir / "meeting_stage1.md"
        stage1.write_text("corrected text\n", encoding="utf-8")
        changes = self.test_dir / "meeting_changes.md"
        changes.write_text("old changes\n", encoding="utf-8")
        self._make_stage1_newer(stage1, self.input_file)

        cmd_run_correction(argparse.Namespace(
            input=str(self.input_file),
            output=None,
            stage=1,
            domain=None,
            dry_run=False,
            apply_all=False,
            changes_file=False,
            people_roster=None,
        ))

        self.assertEqual(self.input_file.read_text(encoding="utf-8"), "corrected text\n")
        self.assertFalse(stage1.exists())
        self.assertFalse(changes.exists())

    def test_cmd_apply_all_ignores_stale_stage1_and_runs_corrections(self):
        """--apply-all must run corrections, not promote a stale sidecar.

        Regression: a previous safe-mode run leaves _stage1.md behind (possibly
        with ZERO corrections applied — safe mode defers medium/high rules).
        An explicit --apply-all is a request to run corrections at every risk
        level; if the auto-finalize promote guard fires first, it promotes the
        stale 0-correction sidecar, prints "Finalize complete", and the
        requested correction run never happens — the ASR errors stay in the
        file. This is the exact failure observed on 2026-07-10 with a real
        meeting transcript (13 high-risk name fixes silently skipped).
        """
        stage1 = self.test_dir / "meeting_stage1.md"
        # Simulate a safe-mode leftover: identical to input (0 applied).
        stage1.write_text("original text\n", encoding="utf-8")
        self._make_stage1_newer(stage1, self.input_file)

        cmd_run_correction(argparse.Namespace(
            input=str(self.input_file),
            output=None,
            stage=1,
            domain="zzz_test_empty_domain",
            dry_run=False,
            apply_all=True,
            changes_file=False,
            people_roster=None,
        ))

        # Input must be untouched by promotion (corrections ran; with an empty
        # domain nothing applies, so the input stays as-is rather than being
        # replaced by the stale sidecar).
        self.assertEqual(self.input_file.read_text(encoding="utf-8"), "original text\n")
        # The stale sidecar must NOT have been promoted (i.e. not consumed by
        # os.replace into the input). A 0-correction apply-all run also must
        # not rewrite it — meaning the correction pipeline actually executed.
        self.assertTrue(
            stage1.exists(),
            "--apply-all must not consume _stage1.md via the promote path",
        )

    def test_cmd_stage1_zero_corrections_writes_no_sidecars(self):
        """A 0-correction run must not leave _stage1.md / _changes.md.

        On a clean transcript (or a native re-run after the agent already edited
        the input), there is nothing to apply, so stage1_text == original_text.
        Writing _stage1.md would duplicate the input and _changes.md would say
        "No corrections applied" — pure noise that never auto-finalizes (the
        promote guard skips when the input is newer, which is exactly the native
        case) and forces a manual `rm`. This is the gap the no-op skip closes.
        """
        # Use a domain with no rules so 0 corrections are guaranteed regardless
        # of the user's real dictionary contents — the suite runs against the
        # live ~/.transcript-fixer/corrections.db, like the other cmd tests.
        cmd_run_correction(argparse.Namespace(
            input=str(self.input_file),
            output=None,
            stage=1,
            domain="zzz_test_empty_domain",
            dry_run=False,
            apply_all=False,
            changes_file=False,
            people_roster=None,
        ))

        self.assertFalse(
            (self.test_dir / "meeting_stage1.md").exists(),
            "0-correction run must not write _stage1.md (byte-copy of input = noise)",
        )
        self.assertFalse(
            (self.test_dir / "meeting_changes.md").exists(),
            "0-correction run must not write _changes.md ('no corrections' = noise)",
        )


if __name__ == "__main__":
    unittest.main()
