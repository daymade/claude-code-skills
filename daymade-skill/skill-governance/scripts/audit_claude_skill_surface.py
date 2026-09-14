#!/usr/bin/env python3
"""Check a fresh Claude command catalog without submitting a model turn.

Exit 0: requested names found; 1: missing names; 2: invalid/unavailable evidence.
This proves host discovery, not model auto-triggering or skill execution.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


class CatalogError(Exception):
    pass


def parse_catalog(text: str) -> list[dict]:
    catalogs = []
    for line in text.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict) or item.get("type") != "control_response":
            continue
        response = item.get("response", {})
        if not isinstance(response, dict) or response.get("subtype") != "success":
            continue
        body = response.get("response", {})
        if isinstance(body, dict) and "commands" in body:
            catalogs.append(body["commands"])
    if len(catalogs) != 1:
        raise CatalogError("expected exactly one successful initialization command catalog")
    commands = catalogs[0]
    if not isinstance(commands, list) or not commands:
        raise CatalogError("initialization returned an empty or invalid command catalog")
    if any(not isinstance(c, dict) or not isinstance(c.get("name"), str)
           or not c["name"].strip() or not isinstance(c.get("description"), str) for c in commands):
        raise CatalogError("invalid command metadata")
    return commands


def probe(binary: str, cwd: Path, timeout: float) -> str:
    # No user prompt is sent. Also remove provider routing and replace model
    # credentials/endpoint in this child only, so inference cannot spend money.
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("ANTHROPIC_") and k not in {
               "CLAUDECODE", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY",
           }}
    offline = {
        "ANTHROPIC_API_KEY": "catalog-probe-no-credential",
        "ANTHROPIC_AUTH_TOKEN": "catalog-probe-no-credential",
        "ANTHROPIC_BASE_URL": "http://127.0.0.1:9",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    }
    env.update(offline)
    command = [binary, "-p", "--input-format", "stream-json", "--output-format", "stream-json",
               "--verbose", "--no-session-persistence", "--model", "catalog-probe",
               "--settings", json.dumps({"disableAllHooks": True, "env": offline}),
               "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
               "--permission-prompts", "none", "--tools", ""]
    request = {"type": "control_request", "request_id": "skill-catalog", "request": {"subtype": "initialize"}}
    try:
        result = subprocess.run(command, input=json.dumps(request) + "\n", cwd=cwd,
                                env=env, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CatalogError(f"Claude initialization unavailable ({type(exc).__name__})") from exc
    if result.returncode:
        # Runtime stderr can contain account details; do not forward it.
        raise CatalogError(f"Claude initialization exited {result.returncode}")
    return result.stdout


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claude-bin", default="claude")
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--catalog-jsonl", type=Path, help="Read a frozen initialization stream")
    parser.add_argument("--require-visible", action="append", default=[], metavar="NAME")
    parser.add_argument("--require-absent", action="append", default=[], metavar="NAME")
    parser.add_argument("--timeout", type=float, default=45)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        stream = args.catalog_jsonl.read_text() if args.catalog_jsonl else probe(args.claude_bin, args.cwd, args.timeout)
        commands = parse_catalog(stream)
        names = {c["name"] for c in commands}
        missing = sorted(set(args.require_visible) - names)
        unexpected = sorted(set(args.require_absent) & names)
        report = {"schema_version": 1, "kind": "claude_skill_surface_audit",
                  "status": "missing" if missing or unexpected else "present",
                  "evidence_scope": "fresh_host_command_catalog", "model_turn_submitted": False,
                  "hooks_enabled_in_probe": False, "missing": missing, "unexpected": unexpected,
                  "commands": commands}
        code = int(bool(missing or unexpected))
    except (CatalogError, OSError, UnicodeError) as exc:
        report = {"schema_version": 1, "kind": "claude_skill_surface_audit", "status": "invalid", "error": str(exc)}
        code = 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Claude Skill catalog: {report['status']}")
        for key in ("missing", "unexpected", "error"):
            if report.get(key):
                print(f"  {key}: {report[key]}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
