#!/usr/bin/env python3
"""Tests for scripts/surface_version.py — fingerprint stability and sensitivity."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "surface_version", SKILL_DIR / "scripts" / "surface_version.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SurfaceVersionTests(unittest.TestCase):
    def _tree(self, root: Path) -> None:
        (root / "scripts" / "sub").mkdir(parents=True)
        (root / "scripts" / "a.py").write_text("print('a')\n")
        (root / "scripts" / "sub" / "b.py").write_text("print('b')\n")

    def test_same_tree_twice_same_fingerprint(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._tree(root)
            self.assertEqual(
                MODULE.surface_fingerprint(root), MODULE.surface_fingerprint(root)
            )

    def test_code_change_changes_fingerprint(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._tree(root)
            before = MODULE.surface_fingerprint(root)
            (root / "scripts" / "a.py").write_text("print('changed')\n")
            self.assertNotEqual(before, MODULE.surface_fingerprint(root))

    def test_doc_change_does_not_change_fingerprint(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._tree(root)
            before = MODULE.surface_fingerprint(root)
            (root / "SKILL.md").write_text("# docs\n")
            (root / "references").mkdir()
            (root / "references" / "x.md").write_text("refs\n")
            (root / "scripts" / "notes.txt").write_text("not python\n")
            self.assertEqual(before, MODULE.surface_fingerprint(root))

    def test_real_skill_fingerprint_is_12_hex(self):
        value = MODULE.surface_fingerprint(SKILL_DIR)
        self.assertEqual(len(value), 12)
        int(value, 16)


if __name__ == "__main__":
    unittest.main()
