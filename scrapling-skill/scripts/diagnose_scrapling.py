#!/usr/bin/env python3
"""
Diagnose a local Scrapling CLI installation and optionally run a smoke test.
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable, List, Tuple


def run_command(cmd: List[str]) -> Tuple[int, str, str]:
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


def print_section(title: str) -> None:
    print("")
    print(title)
    print("-" * len(title))


def existing_dirs(paths: Iterable[Path]) -> List[str]:
    return [str(path) for path in paths if path.exists()]


def detect_browser_cache() -> Tuple[List[str], List[str]]:
    roots = [
        Path.home() / "Library" / "Caches" / "ms-playwright",
        Path.home() / ".cache" / "ms-playwright",
    ]
    chromium = []
    headless_shell = []
    for root in roots:
        if not root.exists():
            continue
        chromium.extend(existing_dirs(sorted(root.glob("chromium-*"))))
        headless_shell.extend(existing_dirs(sorted(root.glob("chromium_headless_shell-*"))))
    return chromium, headless_shell


def diagnose_cli() -> bool:
    print_section("CLI")
    scrapling_path = shutil.which("scrapling")
    if not scrapling_path:
        print("status: missing")
        print("fix: install with `uv tool install 'scrapling[shell]'`")
        return False

    print("path: {0}".format(scrapling_path))
    code, stdout, stderr = run_command(["scrapling", "--help"])
    output = (stdout + "\n" + stderr).strip()

    if code == 0:
        print("status: working")
        return True

    print("status: broken")
    if "install scrapling with any of the extras" in output.lower() or "no module named 'click'" in output.lower():
        print("cause: installed without CLI extras")
        print("fix: `uv tool uninstall scrapling` then `uv tool install 'scrapling[shell]'`")
    else:
        print("cause: unknown")

    if output:
        print("details:")
        print(output[:1200])
    return False


def diagnose_browsers() -> None:
    print_section("Browser Runtime")
    chromium, headless_shell = detect_browser_cache()
    print("chromium: {0}".format("present" if chromium else "missing"))
    for path in chromium:
        print("  - {0}".format(path))
    print("chrome-headless-shell: {0}".format("present" if headless_shell else "missing"))
    for path in headless_shell:
        print("  - {0}".format(path))
    if not chromium or not headless_shell:
        print("hint: run `scrapling install` before browser-backed fetches")


def preview_file(path: Path, preview_lines: int) -> None:
    print_section("Smoke Test Output")
    if not path.exists():
        print("status: missing output file")
        return

    size = path.stat().st_size
    print("path: {0}".format(path))
    print("bytes: {0}".format(size))
    if size == 0:
        print("status: empty")
        return

    if path.suffix in (".md", ".txt"):
        print("preview:")
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for index, line in enumerate(handle):
                if index >= preview_lines:
                    break
                print(line.rstrip())


def run_smoke_test(args: argparse.Namespace) -> int:
    print_section("Smoke Test")

    suffix = ".html"
    if args.selector:
        suffix = ".md"

    output_path = Path(tempfile.gettempdir()) / ("scrapling-smoke" + suffix)
    if output_path.exists():
        output_path.unlink()

    cmd = ["scrapling", "extract", "fetch" if args.dynamic else "get", args.url, str(output_path)]
    if args.selector:
        cmd.extend(["-s", args.selector])
    if args.dynamic:
        cmd.extend(["--timeout", str(args.timeout)])
    elif args.no_verify:
        cmd.append("--no-verify")

    print("command: {0}".format(" ".join(cmd)))
    code, stdout, stderr = run_command(cmd)
    if stdout.strip():
        print(stdout.strip())
    if stderr.strip():
        print(stderr.strip())

    preview_file(output_path, args.preview_lines)
    return code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Diagnose Scrapling and run an optional smoke test.")
    parser.add_argument("--url", help="Optional URL for a smoke test")
    parser.add_argument("--selector", help="Optional CSS selector for the smoke test")
    parser.add_argument(
        "--dynamic",
        action="store_true",
        help="Use `scrapling extract fetch` instead of `scrapling extract get`",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Pass `--no-verify` to static smoke tests",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=20000,
        help="Timeout in milliseconds for dynamic smoke tests",
    )
    parser.add_argument(
        "--preview-lines",
        type=int,
        default=20,
        help="Number of preview lines for markdown/text output",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    cli_ok = diagnose_cli()
    diagnose_browsers()

    if not cli_ok:
        return 1

    if not args.url:
        return 0

    return run_smoke_test(args)


if __name__ == "__main__":
    sys.exit(main())
