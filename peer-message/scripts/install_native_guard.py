#!/usr/bin/env python3
"""Bind PeerMessage's native guard to a fixed, explicitly managed Python entry."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile


def config_path():
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "peer-message/native-guard.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_write(path, body, mode):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(body.encode())
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(mode)
    temporary.replace(path)


def install(python):
    python = Path(python).expanduser().absolute()
    if not python.is_file() or not os.access(python, os.X_OK):
        raise ValueError("managed Python entry is not executable")
    subprocess.run([str(python), "-I", "-c", "import sys; assert sys.version_info >= (3,11)"],
                   check=True, timeout=10, capture_output=True)
    module = Path(__file__).with_name("native_guard.py").absolute()
    # Diagnostic installation hashes; source-backed updates retain the selected path.
    files = {name: digest(module.with_name(name)) for name in
             ("native_guard.py", "peer.py", "coordination.py")}
    root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "peer-message"
    entry = root / "native-guard-entry.sh"
    command = ("#!/bin/bash\nmodule=${1:-" + shlex.quote(str(module)) + "}\nexec " +
               shlex.quote(str(python)) + " \"$module\"\n")
    atomic_write(entry, command, 0o700)
    manifest = {"schema": 1, "module": str(module), "python": str(python), "files": files,
                "entry": str(entry)}
    atomic_write(config_path(), json.dumps(manifest, indent=2) + "\n", 0o600)
    return {"status": "bound", "config": str(config_path()), "entry": str(entry),
            "host_enforcement": "requires trusted matching PreToolUse entry and live denial probe"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True, help="fixed Python 3.11+ entry owned by the runtime installer")
    args = parser.parse_args()
    print(json.dumps(install(args.python)))


if __name__ == "__main__":
    main()
