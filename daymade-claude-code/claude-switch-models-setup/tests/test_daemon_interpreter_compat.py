"""The daemon's scripts must import under the interpreter launchd actually hands them.

`sync-local-skill-sources-daemon.sh` invokes its Python scripts as a bare `python3`.
Under launchd's minimal PATH that resolves to the Developer Tools stub, which on
macOS has been Python 3.9 — old enough to evaluate a PEP 604 annotation (`str | None`)
at definition time and raise TypeError before the module finishes importing.

`claude-plugins-sync.py` carried exactly that shape and crashed on every daemon run
from 2026-07-04 until this test was added, while its sibling survived only because it
already declared `from __future__ import annotations`. Nothing surfaced the crash: the
daemon runs the scripts unconditionally and discards their output.
"""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
FUTURE_IMPORT = "annotations"


def _annotation_nodes(tree: ast.AST):
    """Every expression that Python evaluates as an annotation at import time."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            for arg in (
                *args.posonlyargs,
                *args.args,
                *args.kwonlyargs,
                args.vararg,
                args.kwarg,
            ):
                if arg is not None and arg.annotation is not None:
                    yield arg.annotation
            if node.returns is not None:
                yield node.returns
        elif isinstance(node, ast.AnnAssign) and node.annotation is not None:
            yield node.annotation


def _uses_pep604_union(tree: ast.AST) -> bool:
    for annotation in _annotation_nodes(tree):
        for node in ast.walk(annotation):
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
                return True
    return False


def _declares_future_annotations(tree: ast.AST) -> bool:
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            if any(alias.name == FUTURE_IMPORT for alias in node.names):
                return True
    return False


class DaemonInterpreterCompatTest(unittest.TestCase):
    def test_scripts_dir_is_present(self) -> None:
        """Guard the guard: an empty glob would make every assertion below vacuous."""
        self.assertTrue(SCRIPTS_DIR.is_dir(), f"missing scripts dir: {SCRIPTS_DIR}")
        self.assertTrue(
            list(SCRIPTS_DIR.glob("*.py")), f"no Python scripts under {SCRIPTS_DIR}"
        )

    def test_pep604_annotations_require_future_import(self) -> None:
        offenders = []
        for script in sorted(SCRIPTS_DIR.glob("*.py")):
            tree = ast.parse(script.read_text(encoding="utf-8"), filename=str(script))
            if _uses_pep604_union(tree) and not _declares_future_annotations(tree):
                offenders.append(script.name)
        self.assertEqual(
            [],
            offenders,
            "these scripts evaluate `X | Y` annotations at import time and will "
            "raise TypeError under the Developer Tools Python the daemon gets; add "
            f"`from __future__ import annotations`: {offenders}",
        )

    def test_detector_actually_fires(self) -> None:
        """Calibrate against a known-bad input, so a broken detector cannot report green."""
        bad = ast.parse("def f(x: str | None): pass\n")
        self.assertTrue(_uses_pep604_union(bad))
        self.assertFalse(_declares_future_annotations(bad))

        good = ast.parse(
            "from __future__ import annotations\ndef f(x: str | None): pass\n"
        )
        self.assertTrue(_uses_pep604_union(good))
        self.assertTrue(_declares_future_annotations(good))

        unrelated = ast.parse("def f(x: int): return x | 1\n")
        self.assertFalse(
            _uses_pep604_union(unrelated),
            "a bitwise-or in the function BODY must not be mistaken for an annotation",
        )


if __name__ == "__main__":
    unittest.main()
