#!/usr/bin/env python3
"""Read-only, stack-aware repository capability inventory.

The script detects toolchains only from explicit repository files. It never
installs dependencies, runs a package sync, reads secret values, or assumes that
every repository is Python/video based.

Usage:
    python scripts/check_env.py [--repo PATH] [--json] [--fix]

Exit codes:
    0 - inferred toolchains are available
    1 - one or more inferred toolchains are missing
    2 - the target could not be inspected safely

--fix is retained for CLI compatibility. It prints repair suggestions but does
not mutate the machine.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    message: str
    evidence: str = ""
    repair: str = ""

    @property
    def blocking(self) -> bool:
        return self.status in {"missing", "error"}


@dataclass(frozen=True)
class ToolRequirement:
    command: str
    reason: str


def run_cmd(
    command: list[str], *, cwd: Path, timeout: int = 15
) -> tuple[int, str, str]:
    """Run one read-only command and preserve its three observable outputs."""
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return 127, "", f"command not found: {command[0]}"
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", exc.stderr or "command timed out"
    return completed.returncode, completed.stdout, completed.stderr


def detect_toolchains(repo: Path) -> list[ToolRequirement]:
    """Infer package managers and runtimes from explicit manifests/lockfiles."""
    requirements: list[ToolRequirement] = []

    if (repo / "uv.lock").exists():
        requirements.append(ToolRequirement("uv", "uv.lock"))
    elif (repo / "poetry.lock").exists():
        requirements.append(ToolRequirement("poetry", "poetry.lock"))
    elif (repo / "Pipfile").exists():
        requirements.append(ToolRequirement("pipenv", "Pipfile"))
    elif (repo / "pyproject.toml").exists() or any(repo.glob("requirements*.txt")):
        requirements.append(ToolRequirement("python", "Python manifest"))

    if (repo / "pnpm-lock.yaml").exists():
        requirements.append(ToolRequirement("pnpm", "pnpm-lock.yaml"))
    elif (repo / "yarn.lock").exists():
        requirements.append(ToolRequirement("yarn", "yarn.lock"))
    elif (repo / "bun.lock").exists() or (repo / "bun.lockb").exists():
        requirements.append(ToolRequirement("bun", "Bun lockfile"))
    elif (repo / "package-lock.json").exists() or (repo / "package.json").exists():
        requirements.append(ToolRequirement("npm", "Node manifest"))

    explicit_manifests = (
        ("cargo", "Cargo.toml"),
        ("go", "go.mod"),
        ("bundle", "Gemfile"),
        ("mvn", "pom.xml"),
        ("docker", "compose.yaml"),
        ("docker", "compose.yml"),
        ("docker", "docker-compose.yaml"),
        ("docker", "docker-compose.yml"),
    )
    for command, manifest in explicit_manifests:
        if (repo / manifest).exists():
            requirements.append(ToolRequirement(command, manifest))

    unique: dict[str, ToolRequirement] = {}
    for requirement in requirements:
        unique.setdefault(requirement.command, requirement)
    return list(unique.values())


def inspect_repository(repo: Path) -> tuple[list[CheckResult], list[ToolRequirement]]:
    results: list[CheckResult] = []

    if not repo.exists():
        return (
            [CheckResult("repository", "error", "path does not exist", str(repo))],
            [],
        )
    if not repo.is_dir():
        return (
            [CheckResult("repository", "error", "path is not a directory", str(repo))],
            [],
        )

    if shutil.which("git") is None:
        return (
            [
                CheckResult(
                    "git",
                    "missing",
                    "git is not available",
                    repair="Install Git using the target platform's supported method.",
                )
            ],
            [],
        )

    code, out, err = run_cmd(
        ["git", "-C", str(repo), "rev-parse", "--is-inside-work-tree"],
        cwd=repo,
    )
    if code != 0 or out.strip() != "true":
        message = (err or out or "not a Git work tree").strip()
        return (
            [
                CheckResult(
                    "repository",
                    "error",
                    message,
                    "git rev-parse --is-inside-work-tree",
                )
            ],
            [],
        )
    results.append(
        CheckResult(
            "repository",
            "ok",
            "Git work tree detected",
            "git rev-parse --is-inside-work-tree",
        )
    )

    instruction_files = [
        name
        for name in (
            "AGENTS.override.md",
            "AGENTS.md",
            "CLAUDE.md",
            "ONBOARDING.md",
            "README.md",
        )
        if (repo / name).exists()
    ]
    if instruction_files:
        results.append(
            CheckResult(
                "project instructions",
                "info",
                ", ".join(instruction_files),
                "filesystem",
            )
        )
    else:
        results.append(
            CheckResult(
                "project instructions",
                "warning",
                "no common project instruction or onboarding file found",
                "filesystem",
                "Infer setup from manifests; create durable onboarding only if requested.",
            )
        )

    toolchains = detect_toolchains(repo)
    if not toolchains:
        results.append(
            CheckResult(
                "toolchains",
                "info",
                "no supported package-manager manifest detected",
                "filesystem",
            )
        )

    for requirement in toolchains:
        executable = shutil.which(requirement.command)
        if executable:
            results.append(
                CheckResult(
                    requirement.command,
                    "ok",
                    f"available at {executable}",
                    requirement.reason,
                )
            )
        else:
            results.append(
                CheckResult(
                    requirement.command,
                    "missing",
                    f"required by {requirement.reason}",
                    requirement.reason,
                    f"Install {requirement.command} using the project's documented method.",
                )
            )

    env_examples = [
        name
        for name in (".env.example", ".env.sample", ".env.template")
        if (repo / name).exists()
    ]
    if env_examples:
        if (repo / ".env").exists():
            results.append(
                CheckResult(
                    "local environment",
                    "info",
                    ".env exists; values were not read",
                    ", ".join(env_examples),
                )
            )
        else:
            results.append(
                CheckResult(
                    "local environment",
                    "warning",
                    f"{env_examples[0]} exists but .env does not",
                    env_examples[0],
                    "Confirm whether the project requires a local .env; do not guess values.",
                )
            )

    return results, toolchains


def render_human(repo: Path, results: list[CheckResult], *, show_repairs: bool) -> None:
    labels = {
        "ok": "OK",
        "info": "INFO",
        "warning": "WARN",
        "missing": "MISSING",
        "error": "ERROR",
    }
    print(f"Repository inventory: {repo}")
    for result in results:
        print(f"[{labels[result.status]}] {result.name}: {result.message}")
        if result.evidence:
            print(f"  evidence: {result.evidence}")
        if show_repairs and result.repair:
            print(f"  next: {result.repair}")

    blocking = sum(result.blocking for result in results)
    warnings = sum(result.status == "warning" for result in results)
    print(f"Summary: {blocking} blocking, {warnings} warning")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only, stack-aware repository capability inventory"
    )
    parser.add_argument("--repo", default=".", help="Repository root (default: cwd)")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Compatibility flag: show repair suggestions; never mutate",
    )
    args = parser.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    results, toolchains = inspect_repository(repo)

    if args.json:
        payload = {
            "repository": str(repo),
            "detected_tools": [asdict(item) for item in toolchains],
            "results": [asdict(item) for item in results],
            "summary": {
                "blocking": sum(result.blocking for result in results),
                "warnings": sum(result.status == "warning" for result in results),
            },
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        render_human(repo, results, show_repairs=args.fix)

    if any(result.status == "error" for result in results):
        return 2
    if any(result.status == "missing" for result in results):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
