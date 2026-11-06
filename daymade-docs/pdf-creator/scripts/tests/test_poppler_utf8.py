#!/usr/bin/env python3
"""Keep optional Unicode PDF lint usable on non-UTF-8 hosts."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import md_to_pdf  # noqa: E402


@pytest.mark.parametrize("host_encoding", ["cp936", "cp1252"])
@pytest.mark.parametrize("unicode_metadata", [False, True])
def test_lint_reads_unicode_metadata_and_text(tmp_path, host_encoding, unicode_metadata):
    real_run = subprocess.run
    outputs = []

    def run_utf8_peer(args, **kwargs):
        if args[0] == "pdfinfo":
            text = "Pages: 1\n"
            if unicode_metadata:
                text += "Title: 中文内容保持完整。\n"
        else:
            text = "中文内容保持完整。\n"
        outputs.append(args[0])
        payload = text.encode("utf-8")
        peer = "import sys;sys.stdout.buffer.write(" + repr(payload) + ")"
        return real_run([sys.executable, "-c", peer], **kwargs)

    with patch.object(md_to_pdf.shutil, "which", return_value="/installed/tool"), \
         patch.object(subprocess, "_text_encoding", return_value=host_encoding), \
         patch.object(md_to_pdf.subprocess, "run", side_effect=run_utf8_peer):
        assert md_to_pdf._lint_pdf_typography(str(tmp_path / "input.pdf")) == []
    assert outputs == ["pdfinfo", "pdftotext"]
