#!/usr/bin/env python3
"""
Regression test for finding a Chromium browser on Windows.

Why this file exists: Windows installs Chrome and Edge under Program Files (or
a per-user LocalAppData install) and registers them only under App Paths, so
neither is on PATH and `shutil.which("chrome")` finds nothing. `_find_chrome`
knew only the macOS app paths and PATH names, so a Windows host with Chrome
and Edge installed still stopped at "No PDF backend found". Edge is Chromium,
takes the same headless --print-to-pdf flags, and ships with Windows 10 and 11.

The candidate tests point the install-root environment variables at temporary
directories, so they run on any OS. The last test drives `_find_chrome` itself
and runs only on Windows, where the macOS paths cannot exist.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

import md_to_pdf  # noqa: E402

ROOTS = ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")
CHROME = ("Google", "Chrome", "Application", "chrome.exe")
EDGE = ("Microsoft", "Edge", "Application", "msedge.exe")


@pytest.fixture
def roots(tmp_path: Path, monkeypatch) -> dict[str, Path]:
    """Empty install roots, with nothing on PATH."""
    made = {}
    for name in ROOTS:
        made[name] = tmp_path / name.replace("(", "_").replace(")", "_")
        made[name].mkdir()
        monkeypatch.setenv(name, str(made[name]))
    monkeypatch.setattr(md_to_pdf.shutil, "which", lambda _name: None)
    return made


def _install(root: Path, parts: tuple[str, ...]) -> str:
    exe = root.joinpath(*parts)
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    return str(exe)


def _first_installed() -> str | None:
    candidates = md_to_pdf._windows_browser_candidates()
    return next((c for c in candidates if c and Path(c).exists()), None)


@pytest.mark.parametrize("root", ROOTS)
def test_chrome_is_found_under_each_install_root(roots, root) -> None:
    chrome = _install(roots[root], CHROME)
    assert _first_installed() == chrome


def test_edge_is_found_when_chrome_is_absent(roots) -> None:
    edge = _install(roots["ProgramFiles(x86)"], EDGE)
    assert _first_installed() == edge


def test_chrome_is_preferred_over_edge(roots) -> None:
    _install(roots["ProgramFiles(x86)"], EDGE)
    chrome = _install(roots["LOCALAPPDATA"], CHROME)
    assert _first_installed() == chrome


def test_missing_install_roots_are_skipped(roots, monkeypatch) -> None:
    for name in ROOTS:
        monkeypatch.delenv(name)
    assert _first_installed() is None


@pytest.mark.skipif(os.name != "nt", reason="exercises the Windows branch of _find_chrome")
def test_find_chrome_returns_edge_on_windows(roots) -> None:
    edge = _install(roots["ProgramFiles(x86)"], EDGE)
    assert md_to_pdf._find_chrome() == edge
