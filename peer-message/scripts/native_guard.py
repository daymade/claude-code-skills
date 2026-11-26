#!/usr/bin/env python3
"""Compatibility forwarder shim: delegates to agent-message/scripts/native_guard.py."""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _compat_forward  # noqa: E402


def _target():
    return _compat_forward.load_target_module("native_guard.py", __file__)


def check(*args, **kwargs):
    return _target().check(*args, **kwargs)


def installed_check(*args, **kwargs):
    return _target().installed_check(*args, **kwargs)


def __getattr__(name: str):
    return getattr(_target(), name)


if __name__ == "__main__":
    _compat_forward.exec_target("native_guard.py", __file__)
