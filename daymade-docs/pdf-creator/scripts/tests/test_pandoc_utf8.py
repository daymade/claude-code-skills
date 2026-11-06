#!/usr/bin/env python3
"""Keep the actual pandoc pipe boundary lossless on non-UTF-8 hosts."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import md_to_pdf  # noqa: E402


@pytest.mark.parametrize("host_encoding", ["cp936", "cp1252"])
def test_pandoc_pipe_preserves_unicode_on_non_utf8_hosts(tmp_path, host_encoding):
    source = "中文内容保持完整。 café 日本語"
    markdown = tmp_path / "unicode.md"
    markdown.write_text(source, encoding="utf-8")
    real_run = subprocess.run

    def run_utf8_peer(_args, **kwargs):
        # A real child consumes/emits UTF-8 bytes, like pandoc. Reuse the
        # caller's pipe options so system-default encoding can still fail.
        peer = (
            "import sys; "
            "s=sys.stdin.buffer.read().decode('utf-8'); "
            "sys.stdout.buffer.write(('<p>'+s+'</p>').encode('utf-8'))"
        )
        return real_run([sys.executable, "-c", peer], **kwargs)

    with patch.object(md_to_pdf.shutil, "which", return_value=sys.executable), \
         patch.object(subprocess, "_text_encoding", return_value=host_encoding), \
         patch.object(md_to_pdf.subprocess, "run", side_effect=run_utf8_peer):
        assert md_to_pdf._md_to_html(str(markdown)) == "<p>" + source + "</p>"
