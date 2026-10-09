#!/usr/bin/env python3
"""Read back one current GUI launchd job without exposing configuration values."""

import argparse
import json
import math
import os
import plistlib
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


MAX_OUTPUT_BYTES = 1024 * 1024
MATCH_FIELDS = (
    "program_match", "arguments_match", "environment_match",
    "working_directory_match", "stdout_match", "stderr_match",
)
LABEL_PATTERN = re.compile(r"[A-Za-z0-9_.-]+\Z")


@dataclass
class _Block:
    name: str
    indent: int
    lines: list[str] = field(default_factory=list)
    blocks: list["_Block"] = field(default_factory=list)


def _unknown(label: str | None = None) -> dict:
    return {
        "status": "unknown", "label": label, "loaded": None,
        "disabled": None, **{name: None for name in MATCH_FIELDS},
    }


def _text_value(value: object) -> bool:
    # launchctl's human-readable format cannot unambiguously represent these.
    return isinstance(value, str) and not any(c in value for c in "\r\n\x00")


def _validate_expected(expected: object) -> str:
    if not isinstance(expected, dict):
        raise ValueError
    label = expected.get("Label")
    if not isinstance(label, str) or not LABEL_PATTERN.fullmatch(label):
        raise ValueError
    argv = expected.get("ProgramArguments")
    if not isinstance(argv, list) or not argv or not all(_text_value(v) for v in argv):
        raise ValueError
    if any(v != v.strip() or not v or v == "}" or v.endswith(" = {") for v in argv):
        raise ValueError
    if not argv[0].startswith("/"):
        raise ValueError
    env = expected.get("EnvironmentVariables", {})
    if not isinstance(env, dict):
        raise ValueError
    for key, value in env.items():
        if not _text_value(key) or not key or "=>" in key or key != key.strip():
            raise ValueError
        if not _text_value(value) or value != value.strip() or value.endswith(" = {"):
            raise ValueError
    for key in ("Program", "WorkingDirectory", "StandardOutPath", "StandardErrorPath"):
        if key in expected and (not _text_value(expected[key]) or expected[key] != expected[key].strip()):
            raise ValueError
    return label


def _parse(text: str, root_name: str) -> _Block:
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise ValueError
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2 or lines[0].strip() != root_name + " = {":
        raise ValueError
    root_indent = len(lines[0]) - len(lines[0].lstrip())
    root = _Block(root_name, root_indent)
    stack = [root]
    closed = False
    for line in lines[1:]:
        if closed:
            raise ValueError
        indent = len(line) - len(line.lstrip())
        body = line[indent:]
        current = stack[-1]
        if body == "}":
            if indent != current.indent:
                raise ValueError
            stack.pop()
            closed = not stack
            continue
        if indent <= current.indent:
            raise ValueError
        opening = re.fullmatch(r"(.+?) (?:=|=>) \{", body)
        if opening:
            name = opening[1]
            block = _Block(name, indent)
            current.blocks.append(block)
            stack.append(block)
        else:
            current.lines.append(body)
    if not closed:
        raise ValueError
    return root


def _one_block(root: _Block, name: str) -> _Block | None:
    found = [block for block in root.blocks if block.name == name]
    if len(found) > 1:
        raise ValueError
    return found[0] if found else None


def _scalars(root: _Block) -> dict[str, str]:
    result = {}
    for line in root.lines:
        key, sep, value = line.partition(" = ")
        if not sep or key in result:
            raise ValueError
        result[key] = value
    return result


def _environment(block: _Block | None) -> dict[str, str]:
    if block is None:
        return {}
    if block.blocks:
        raise ValueError
    result = {}
    for line in block.lines:
        key, sep, value = line.partition(" =>")
        if not sep or key in result or not key or key != key.strip():
            raise ValueError
        # One separator space is syntax; retain any additional value whitespace.
        if value.startswith(" "):
            value = value[1:]
        elif value:
            raise ValueError
        result[key] = value
    return result


def inspect_job_print(expected: dict, text: str, uid: int) -> dict:
    """Pure comparison of one launchctl print result; return only safe flags."""
    label = None
    try:
        label = _validate_expected(expected)
        if type(uid) is not int or uid < 0:
            raise ValueError
        root = _parse(text, f"gui/{uid}/{label}")
        scalars = _scalars(root)
        if any(name in scalars for name in ("arguments", "environment")):
            raise ValueError
        argv = _one_block(root, "arguments")
        if argv is None or argv.blocks:
            raise ValueError
        # Only the direct job block called 'environment' is explicit job ENV.
        env = _environment(_one_block(root, "environment"))
        wanted_env = expected.get("EnvironmentVariables", {})
        if "XPC_SERVICE_NAME" not in wanted_env and env.get("XPC_SERVICE_NAME") == label:
            env.pop("XPC_SERVICE_NAME")
        if "OSLogRateLimit" not in wanted_env:
            env.pop("OSLogRateLimit", None)
        result = _unknown(label)
        result["loaded"] = True
        result.update({
            "program_match": scalars.get("program") == expected.get("Program", expected["ProgramArguments"][0]),
            "arguments_match": argv.lines == expected["ProgramArguments"],
            "environment_match": env == wanted_env,
        })
        for plist_key, native_key, flag in (
            ("WorkingDirectory", "working directory", "working_directory_match"),
            ("StandardOutPath", "stdout path", "stdout_match"),
            ("StandardErrorPath", "stderr path", "stderr_match"),
        ):
            if plist_key in expected:
                result[flag] = scalars.get(native_key) == expected[plist_key]
        result["status"] = "mismatch" if any(result[k] is False for k in MATCH_FIELDS) else "match"
        return result
    except (ValueError, TypeError, UnicodeError):
        return _unknown(label)


def inspect_disabled_print(text: str, label: str) -> bool | None:
    """Return an explicit override, False for no override, or None if unreadable."""
    try:
        root = _parse(text, "disabled services")
        if root.blocks:
            raise ValueError
        found = {}
        for line in root.lines:
            match = re.fullmatch(r'"([A-Za-z0-9_.-]+)"\s+=>\s+(true|false|enabled|disabled)', line)
            if not match or match[1] in found:
                raise ValueError
            found[match[1]] = match[2] in ("true", "disabled")
        return found.get(label, False)
    except (ValueError, TypeError, UnicodeError):
        return None


def _read_command(args: list[str], timeout: float, runner: Callable) -> str:
    completed = runner(args, capture_output=True, timeout=timeout, check=False)
    if completed.returncode != 0 or len(completed.stdout) > MAX_OUTPUT_BYTES:
        raise ValueError
    return completed.stdout.decode("utf-8")


def inspect_native_job(plist_path: Path, timeout: float = 5.0, *, runner: Callable = subprocess.run) -> dict:
    """Read the explicit plist and current user's GUI job; never mutate launchd."""
    label = None
    try:
        if not math.isfinite(timeout) or not 0 < timeout <= 30:
            raise ValueError
        with plist_path.open("rb") as stream:
            expected = plistlib.load(stream)
        label = _validate_expected(expected)
        uid = os.getuid()
        text = _read_command(["/bin/launchctl", "print", f"gui/{uid}/{label}"], timeout, runner)
        result = inspect_job_print(expected, text, uid)
        if result["status"] == "unknown":
            return result
        disabled = _read_command(["/bin/launchctl", "print-disabled", f"gui/{uid}"], timeout, runner)
        result["disabled"] = inspect_disabled_print(disabled, label)
        if result["disabled"] is None:
            result["status"] = "unknown"
        elif result["disabled"]:
            result["status"] = "mismatch"
        return result
    except Exception:
        # Parser/OS/runner diagnostics can contain the supplied plist or argv.
        # Preserve unknown without disclosing exception text or native output.
        return _unknown(label)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError


def main(argv: list[str] | None = None) -> int:
    try:
        parser = _Parser(add_help=False)
        parser.add_argument("--plist", type=Path, required=True)
        parser.add_argument("--timeout", type=float, default=5.0)
        args = parser.parse_args(argv)
        result = inspect_native_job(args.plist, args.timeout)
    except (ValueError, TypeError):
        result = _unknown()
    print(json.dumps(result, sort_keys=True))
    return {"match": 0, "mismatch": 1, "unknown": 2}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
