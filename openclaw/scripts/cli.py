#!/usr/bin/env python3
"""Unified entry point for the openclaw skill."""

from __future__ import annotations

import argparse
import sys

import add_model
import audit
import compare
import copy_provider
import list_models
import switch_model

SUBCOMMANDS = {
    "audit": audit,
    "compare": compare,
    "diff": compare,
    "copy": copy_provider,
    "copy-provider": copy_provider,
    "add-model": add_model,
    "list": list_models,
    "switch": switch_model,
}


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="openclaw",
        description="Manage OpenClaw (龙虾) configs: audit, diff, copy, add-model, list, switch.",
    )
    parser.add_argument(
        "command",
        choices=list(SUBCOMMANDS.keys()),
        help="Subcommand to run",
    )
    parser.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        help="Arguments passed to the subcommand",
    )
    parsed = parser.parse_args()

    module = SUBCOMMANDS[parsed.command]
    return module.main(parsed.args)


if __name__ == "__main__":
    raise SystemExit(main())
