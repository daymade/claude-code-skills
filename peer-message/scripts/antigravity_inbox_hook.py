#!/usr/bin/env python3
"""Compatibility forwarder shim: delegates to agent-message/scripts/antigravity_inbox_hook.py."""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _compat_forward  # noqa: E402


def __getattr__(name: str):
    return getattr(_compat_forward.load_target_module("antigravity_inbox_hook.py", __file__), name)


if __name__ == "__main__":
    _compat_forward.exec_target("antigravity_inbox_hook.py", __file__)
