#!/usr/bin/env python3
"""
Local Codex CLI wrapper for OpenClaw integration.
Uses OAuth auth from ~/.codex/auth.json (ChatGPT Pro subscription).
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

# Codex CLI detection paths (in priority order)
CODEX_PATHS = [
    "/Applications/Codex.app/Contents/Resources/codex",
    "/usr/local/bin/codex",
    "/opt/homebrew/bin/codex",
    os.path.expanduser("~/.npm-global/bin/codex"),
]


def find_codex_binary() -> Optional[str]:
    """Find the Codex CLI binary."""
    for path in CODEX_PATHS:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path

    # Fallback: which codex
    try:
        result = subprocess.run(
            ["which", "codex"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass

    return None


def check_auth_status(codex_path: str) -> dict:
    """Check if Codex OAuth auth is valid."""
    try:
        result = subprocess.run(
            [codex_path, "exec", "--skip-git-repo-check", "echo auth-ok"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "authenticated": result.returncode == 0,
            "exit_code": result.returncode,
            "stderr": result.stderr[:500] if result.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {"authenticated": False, "error": "timeout", "exit_code": -1}
    except Exception as e:
        return {"authenticated": False, "error": str(e), "exit_code": -1}


def exec_codex(
    codex_path: str,
    prompt: str,
    workdir: Optional[str] = None,
    model: str = "gpt-5.5",
    sandbox: str = "workspace-write",
    json_output: bool = True,
    ephemeral: bool = False,
    skip_git_check: bool = False,
    timeout: int = 300,
) -> dict:
    """Execute codex exec with given parameters."""
    cmd = [codex_path, "exec"]

    if model:
        cmd.extend(["-m", model])
    if sandbox:
        cmd.extend(["-s", sandbox])
    if json_output:
        cmd.append("--json")
    if ephemeral:
        cmd.append("--ephemeral")
    # Default to skip git check for OpenClaw integration (often not in git repo)
    cmd.append("--skip-git-repo-check")
    if workdir:
        cmd.extend(["-C", workdir])

    cmd.append(prompt)

    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = time.time() - start_time

        output = {
            "success": result.returncode == 0,
            "exit_code": result.returncode,
            "elapsed_seconds": round(elapsed, 2),
            "stdout": result.stdout,
            "stderr": result.stderr[:2000] if result.stderr else "",
        }

        # Try to parse JSONL output if --json was used
        if json_output and result.stdout:
            try:
                lines = [l for l in result.stdout.strip().split("\n") if l.strip()]
                parsed = []
                for line in lines:
                    try:
                        parsed.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
                output["parsed_jsonl"] = parsed

                # Extract final assistant message
                for item in reversed(parsed):
                    if item.get("type") == "item" and item.get("item", {}).get("type") == "agent_message":
                        output["final_message"] = item["item"].get("text", "")
                        break
            except Exception as e:
                output["parse_error"] = str(e)

        return output

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"timeout after {timeout}s",
            "exit_code": -1,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "exit_code": -1,
        }


def review_codex(
    codex_path: str,
    workdir: Optional[str] = None,
    model: str = "gpt-5.5",
    uncommitted: bool = False,
    timeout: int = 300,
) -> dict:
    """Run codex exec review."""
    cmd = [codex_path, "exec", "-m", model, "--json", "review"]
    if uncommitted:
        cmd.append("--uncommitted")
    if workdir:
        cmd.extend(["-C", workdir])

    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = time.time() - start_time

        output = {
            "success": result.returncode == 0,
            "exit_code": result.returncode,
            "elapsed_seconds": round(elapsed, 2),
            "stdout": result.stdout,
            "stderr": result.stderr[:2000] if result.stderr else "",
        }

        if result.stdout:
            try:
                lines = [l for l in result.stdout.strip().split("\n") if l.strip()]
                parsed = []
                for line in lines:
                    try:
                        parsed.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
                output["parsed_jsonl"] = parsed
            except Exception:
                pass

        return output

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"timeout after {timeout}s",
            "exit_code": -1,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "exit_code": -1,
        }


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: codex_wrapper.py <command> [args...]"}))
        sys.exit(1)

    command = sys.argv[1]

    # Find codex binary
    codex_path = find_codex_binary()
    if not codex_path:
        print(json.dumps({
            "error": "Codex CLI not found",
            "searched_paths": CODEX_PATHS,
        }))
        sys.exit(1)

    if command == "status":
        auth = check_auth_status(codex_path)
        print(json.dumps({
            "codex_path": codex_path,
            **auth,
        }))

    elif command == "exec":
        if len(sys.argv) < 3:
            print(json.dumps({"error": "Usage: codex_wrapper.py exec <prompt> [options]"}))
            sys.exit(1)

        prompt = sys.argv[2]
        workdir = sys.argv[3] if len(sys.argv) > 3 else None
        model = sys.argv[4] if len(sys.argv) > 4 else "gpt-5.5"
        sandbox = sys.argv[5] if len(sys.argv) > 5 else "workspace-write"
        timeout = int(sys.argv[6]) if len(sys.argv) > 6 else 300

        result = exec_codex(
            codex_path=codex_path,
            prompt=prompt,
            workdir=workdir,
            model=model,
            sandbox=sandbox,
            timeout=timeout,
        )
        print(json.dumps(result, ensure_ascii=False))

    elif command == "review":
        workdir = sys.argv[2] if len(sys.argv) > 2 else None
        model = sys.argv[3] if len(sys.argv) > 3 else "gpt-5.5"
        uncommitted = sys.argv[4] == "true" if len(sys.argv) > 4 else False
        timeout = int(sys.argv[5]) if len(sys.argv) > 5 else 300

        result = review_codex(
            codex_path=codex_path,
            workdir=workdir,
            model=model,
            uncommitted=uncommitted,
            timeout=timeout,
        )
        print(json.dumps(result, ensure_ascii=False))

    else:
        print(json.dumps({"error": f"Unknown command: {command}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
