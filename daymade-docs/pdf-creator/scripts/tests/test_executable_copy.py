#!/usr/bin/env python3
"""Render synthetic shell examples and inspect their actual PDF text.

Run with WeasyPrint, pytest and Poppler installed. These are extraction controls,
not a general command-equivalence validator or a clipboard test for every reader.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from md_to_pdf import _has_weasyprint, markdown_to_pdf  # noqa: E402

LONG_COMMAND = (
    "python3 example-tools/sample_worker.py 12345 2>> sample-command.stderr "
    "| tee -a sample-command.jsonl"
)


def _copied_command(source: str, out: Path) -> str:
    if not _has_weasyprint() or not shutil.which("pdftotext"):
        pytest.skip("Requires WeasyPrint and Poppler")
    md = out.with_suffix(".md")
    md.write_text(f"```sh\n{source}\n```\n", encoding="utf-8")
    markdown_to_pdf(str(md), str(out), theme="cjk-auto",
                    backend="weasyprint", previews=False)
    text = subprocess.check_output(
        ["pdftotext", "-layout", str(out), "-"], text=True,
    )
    # These one-page specimens contain only a code block and a known footer.
    # Keep copied line breaks; joining them would hide the very defect tested.
    lines = [line for line in text.splitlines() if line.strip()]
    assert lines[-1].strip() == "1/1", "Unexpected specimen footer"
    return "\n".join(lines[:-1])


def _syntax_status(command: str) -> int:
    return subprocess.run(
        ["/bin/sh", "-n"], input=command, text=True, capture_output=True,
    ).returncode


def _specimen_tokens(command: str) -> list[str]:
    # Only remove explicit shell continuations, never visual/copied newlines.
    lexer = shlex.shlex(command.replace("\\\n", ""), posix=True,
                        punctuation_chars=True)
    lexer.whitespace_split = True
    return list(lexer)


def test_visual_wrap_can_break_an_otherwise_valid_shell_pipeline(tmp_path):
    assert _syntax_status(LONG_COMMAND) == 0
    copied = _copied_command(LONG_COMMAND, tmp_path / "unsafe.pdf")
    assert "\n|" in copied, f"Specimen no longer wraps before the pipe: {copied!r}"
    assert _syntax_status(copied) != 0


def test_author_continuation_preserves_extracted_pipeline_tokens(tmp_path):
    source = LONG_COMMAND.replace(" 2>>", " \\\n  2>>")
    copied = _copied_command(source, tmp_path / "continued.pdf")
    assert "\\\n" in copied, "The author-written continuation must survive"
    assert _syntax_status(copied) == 0
    assert _specimen_tokens(copied) == _specimen_tokens(source)


def test_short_quoted_command_survives_extraction(tmp_path):
    source = "printf '%s\\n' 'hello world'"
    copied = _copied_command(source, tmp_path / "short.pdf")
    assert _syntax_status(copied) == 0
    assert _specimen_tokens(copied) == _specimen_tokens(source)
