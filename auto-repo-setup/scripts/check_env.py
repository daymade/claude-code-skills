#!/usr/bin/env python3
"""环境检查脚本 — 验证代码库运行所需的基础设施。

用法:
    python scripts/check_env.py [--fix]

返回码:
    0 — 全部通过
    1 — 有缺失，但 --fix 未指定
    2 — 修复尝试后仍有失败
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import List


@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str = ""
    fix_cmd: str = ""


def run_cmd(cmd: list[str]) -> tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return r.returncode, r.stdout, r.stderr
    except FileNotFoundError:
        return 127, "", f"command not found: {cmd[0]}"
    except Exception as e:
        return 1, "", str(e)


def check_git() -> CheckResult:
    code, out, err = run_cmd(["git", "--version"])
    if code != 0:
        return CheckResult("git", False, err or "git not found", "brew install git")
    return CheckResult("git", True, out.strip().split("\n")[0])


def check_ffmpeg() -> CheckResult:
    code, out, err = run_cmd(["ffmpeg", "-version"])
    if code != 0:
        return CheckResult(
            "ffmpeg", False, err or "ffmpeg not found", "brew install ffmpeg"
        )
    first = out.strip().split("\n")[0]
    return CheckResult("ffmpeg", True, first)


def check_uv() -> CheckResult:
    code, out, err = run_cmd(["uv", "--version"])
    if code != 0:
        return CheckResult(
            "uv",
            False,
            err or "uv not found",
            "curl -LsSf https://astral.sh/uv/install.sh | sh",
        )
    return CheckResult("uv", True, out.strip())


def check_python_via_uv() -> CheckResult:
    code, out, err = run_cmd(["uv", "run", "python", "--version"])
    if code != 0:
        return CheckResult(
            "python (via uv)",
            False,
            err or "python not available via uv",
            "uv python install",
        )
    return CheckResult("python (via uv)", True, out.strip())


def check_pyproject_deps() -> CheckResult:
    code, out, err = run_cmd(["uv", "sync", "--locked"])
    if code != 0:
        return CheckResult(
            "dependencies (uv sync)",
            False,
            (err or out)[:200],
            "uv sync",
        )
    return CheckResult("dependencies (uv sync)", True, "lockfile satisfied")


def check_dot_env() -> CheckResult:
    import os

    if not os.path.exists(".env"):
        return CheckResult(
            ".env file",
            False,
            ".env not found",
            "cp .env.example .env && edit with real values",
        )
    with open(".env") as f:
        content = f.read()
    placeholders = ["YOUR_KEY_HERE", "REPLACE_ME", "placeholder", "example"]
    found = [p for p in placeholders if p.lower() in content.lower()]
    if found:
        return CheckResult(
            ".env file",
            False,
            f"still contains placeholders: {found}",
            "edit .env with real values",
        )
    return CheckResult(".env file", True, "configured")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check repo environment")
    parser.add_argument("--fix", action="store_true", help="Attempt to auto-fix issues")
    args = parser.parse_args()

    checks: List[CheckResult] = []

    # Ordered: system deps → python env → project deps → config
    checks.append(check_git())
    checks.append(check_ffmpeg())
    checks.append(check_uv())
    checks.append(check_python_via_uv())
    checks.append(check_pyproject_deps())
    checks.append(check_dot_env())

    passed = [c for c in checks if c.passed]
    failed = [c for c in checks if not c.passed]

    print("=" * 50)
    print("Environment Check Report")
    print("=" * 50)

    for c in passed:
        print(f"  ✅ {c.name}: {c.message}")

    for c in failed:
        print(f"  ❌ {c.name}: {c.message}")
        if c.fix_cmd:
            print(f"     Fix: {c.fix_cmd}")

    print("=" * 50)
    print(f"Result: {len(passed)}/{len(checks)} passed")

    if not failed:
        print("🎉 All checks passed! You're ready to go.")
        return 0

    if args.fix:
        print("\n--fix specified, attempting repairs...")
        # In practice, auto-fix is limited — we print suggestions
        for c in failed:
            if c.fix_cmd:
                print(f"  Run: {c.fix_cmd}")
        print("Please re-run after fixing.")
        return 2

    print("\nRun with --fix to see repair commands, or ask Claude Code for help.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
