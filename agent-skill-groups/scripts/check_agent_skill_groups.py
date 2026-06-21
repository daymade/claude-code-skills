#!/usr/bin/env python3
"""Read-only checker for the agent-skill-groups CLI."""

from __future__ import print_function

import argparse
import os
import shutil
import subprocess
import sys


def run_command(command):
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    stdout, stderr = process.communicate()
    return process.returncode, stdout.strip(), stderr.strip()


def print_block(title, text):
    print("\n== {} ==".format(title))
    if text:
        print(text)
    else:
        print("(no output)")


def main():
    parser = argparse.ArgumentParser(
        description="Check whether agent-skill-groups is installed and usable."
    )
    parser.add_argument(
        "--runtime",
        default="claude-code",
        help="Runtime preset to validate against, default: claude-code",
    )
    parser.add_argument(
        "--config",
        help="Optional groups.json path. When provided, validate and show status.",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Also run a read-only inventory analysis for the selected runtime.",
    )
    args = parser.parse_args()

    executable = shutil.which("agent-skill-groups")
    if not executable:
        print("agent-skill-groups was not found on PATH.")
        print("")
        print("Install one of these ways:")
        print("  pipx install git+https://github.com/go165/agent-skill-groups.git")
        print("  python -m pip install git+https://github.com/go165/agent-skill-groups.git")
        return 2

    print("agent-skill-groups executable: {}".format(executable))

    checks = [
        [executable, "--help"],
        [executable, "runtimes"],
    ]

    if args.analyze:
        checks.append([executable, "analyze", "--runtime", args.runtime])

    if args.config:
        config_path = os.path.abspath(args.config)
        checks.extend(
            [
                [
                    executable,
                    "validate",
                    "--config",
                    config_path,
                    "--runtime",
                    args.runtime,
                ],
                [
                    executable,
                    "status",
                    "--config",
                    config_path,
                    "--runtime",
                    args.runtime,
                    "--details",
                ],
            ]
        )

    failed = 0
    for command in checks:
        code, stdout, stderr = run_command(command)
        print_block(" ".join(command), stdout)
        if stderr:
            print_block("stderr", stderr)
        if code != 0:
            failed = code or 1

    if failed:
        print("\nOne or more checks failed.")
        return failed

    print("\nAll read-only checks completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
