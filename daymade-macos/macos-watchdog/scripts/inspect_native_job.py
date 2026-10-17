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
SCHEDULE_FIELDS = (
    "start_interval_match", "watch_paths_match",
    "run_at_load_match", "keep_alive_match",
)
LABEL_PATTERN = re.compile(r"[A-Za-z0-9_.-]+\Z")

# Sentinel for a native shape that is neither provably present nor provably
# absent. The launchctl text format is not a stable API: anything ambiguous
# yields unknown for that one check, never a guessed match or mismatch.
_AMBIGUOUS = object()


@dataclass
class _Block:
    name: str
    indent: int
    lines: list[str] = field(default_factory=list)
    blocks: list["_Block"] = field(default_factory=list)


def _unknown(label: str | None = None) -> dict:
    return {
        "status": "unknown", "label": label, "loaded": None,
        "disabled": None, **{name: None for name in MATCH_FIELDS + SCHEDULE_FIELDS},
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
    if "StartInterval" in expected:
        interval = expected["StartInterval"]
        # Strict int only: bool is not an int here, and launchd intervals are positive.
        if type(interval) is not int or interval <= 0:
            raise ValueError
    if "WatchPaths" in expected:
        # An absent key is the empty expectation. A present key must be a
        # nonempty array of absolute single-line paths: an empty array or
        # malformed members are rejected as invalid input (unknown), never
        # treated as absent and never scored as a guessed mismatch.
        paths = expected["WatchPaths"]
        if not isinstance(paths, list) or not paths:
            raise ValueError
        for path in paths:
            if (not _text_value(path) or not path or path != path.strip()
                    or not path.startswith("/") or '"' in path or "\\" in path):
                raise ValueError
    if "RunAtLoad" in expected and type(expected["RunAtLoad"]) is not bool:
        raise ValueError
    keep_alive = expected.get("KeepAlive", False)
    # Unknown dictionary conditions remain a field-level unknown; do not lose
    # independent argv/environment evidence because one condition is unsupported.
    if type(keep_alive) is not bool and not isinstance(keep_alive, dict):
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


def _scalars(root: _Block) -> dict[str, object]:
    result = {}
    for line in root.lines:
        key, sep, value = line.partition(" = ")
        if not sep:
            raise ValueError
        if key in result:
            if key in {"properties", "run interval", "event triggers", "semaphores"}:
                result[key] = _AMBIGUOUS
                continue
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


def _schedule_block(root: _Block, name: str) -> "_Block | None":
    # Unlike _one_block, duplicates degrade only the affected schedule check
    # to unknown instead of discarding every other proven result.
    found = [block for block in root.blocks if block.name == name]
    if len(found) > 1:
        return _AMBIGUOUS
    return found[0] if found else None


def _schedule_scalar(root: _Block, scalars: dict, name: str):
    # A block where a scalar is expected is an unsupported representation,
    # including a simultaneous scalar/block pair; never treat it as absent.
    if any(block.name == name for block in root.blocks):
        return _AMBIGUOUS
    return scalars.get(name)


def _property_flags(root: _Block, scalars: dict) -> "set[str] | None":
    # The trailing scalar "properties = flag | flag | ..."; None when absent.
    value = _schedule_scalar(root, scalars, "properties")
    if value is None:
        return None
    if not isinstance(value, str):
        return _AMBIGUOUS
    tokens = {token.strip() for token in value.split("|")}
    if not tokens or "" in tokens:
        return _AMBIGUOUS
    return tokens


def _run_interval(root: _Block, scalars: dict) -> "int | None":
    # The only provable timer signal is the "run interval = N seconds" scalar.
    value = _schedule_scalar(root, scalars, "run interval")
    triggers = _schedule_block(root, "event triggers")
    if "event triggers" in scalars or triggers is _AMBIGUOUS:
        return _AMBIGUOUS
    if triggers is not None and (triggers.lines or any(
            block.name != "com.apple.launchd.WatchPaths" for block in triggers.blocks)):
        # Older timer descriptors and other unparsed event families cannot
        # establish timer absence from a missing current-format scalar.
        return _AMBIGUOUS
    if value is None:
        return None
    if not isinstance(value, str):
        return _AMBIGUOUS
    match = re.fullmatch(r"([0-9]+) seconds", value)
    if not match or int(match[1]) <= 0:
        return _AMBIGUOUS
    return int(match[1])


def _watch_paths(root: _Block) -> "list[str] | None":
    # Only the indexed quoted descriptor form is supported:
    # event triggers -> com.apple.launchd.WatchPaths -> descriptor ->
    # "WatchPaths" => [ / 0 = "/path" / ... / ]. Anything else is unknown.
    if any(line.partition(" = ")[0] == "event triggers" for line in root.lines):
        return _AMBIGUOUS
    triggers = _schedule_block(root, "event triggers")
    if triggers is None or triggers is _AMBIGUOUS:
        return triggers
    named = [block for block in triggers.blocks if block.name == "com.apple.launchd.WatchPaths"]
    if len(named) > 1:
        return _AMBIGUOUS
    if not named:
        return None
    if triggers.lines:
        return _AMBIGUOUS
    try:
        fields = _scalars(named[0])
    except ValueError:
        return _AMBIGUOUS
    if (fields.get("service") != root.name.rsplit("/", 1)[-1]
            or fields.get("stream") != "com.apple.fsevents.matching"):
        return _AMBIGUOUS
    descriptors = [block for block in named[0].blocks if block.name == "descriptor"]
    if len(descriptors) != 1 or len(named[0].blocks) != 1 or descriptors[0].blocks:
        return _AMBIGUOUS
    lines = descriptors[0].lines
    if len(lines) < 2 or lines[0] != '"WatchPaths" => [' or lines[-1] != "]":
        return _AMBIGUOUS
    paths = []
    for index, line in enumerate(lines[1:-1]):
        entry = re.fullmatch(r'([0-9]+) = "([^"\\]*)"', line)
        if (entry is None or int(entry[1]) != index
                or not entry[2].startswith("/") or entry[2] != entry[2].strip()):
            return _AMBIGUOUS
        paths.append(entry[2])
    # No captured probe shows an empty descriptor; never guess its meaning.
    return paths if paths else _AMBIGUOUS


def _switch_check(wanted: bool, props, token: str, conditional: bool) -> "bool | None":
    # 'props' is None (properties line absent), _AMBIGUOUS, or a set of tokens.
    if props is _AMBIGUOUS:
        return None
    if wanted:
        # Affirmative evidence only: the flag in a present properties line.
        if props is None:
            return None
        return token in props
    if props is not None and token in props:
        return False
    if conditional:
        # A semaphores block proves a conditional KeepAlive: the plain boolean
        # state is then unknown, never a proven false-match.
        return None
    if props is None:
        return None
    return True


def _keep_alive_check(wanted, root: _Block, scalars: dict, props) -> "bool | None":
    semaphores = _schedule_block(root, "semaphores")
    if "semaphores" in scalars:
        return None
    if not isinstance(wanted, dict):
        return _switch_check(wanted, props, "keepalive", semaphores is not None)
    # Supported conditional form is bound to the captured native semaphore.
    # Other conditions, combined conditions and unfamiliar values stay unknown.
    if set(wanted) != {"SuccessfulExit"} or type(wanted["SuccessfulExit"]) is not bool:
        return None
    if props is None or props is _AMBIGUOUS or "keepalive" in props:
        return None
    if semaphores is None:
        return False
    if semaphores is _AMBIGUOUS or semaphores.blocks or len(semaphores.lines) != 1:
        return None
    match = re.fullmatch(r"successful exit => ([01])", semaphores.lines[0])
    if match is None:
        return None
    return bool(int(match[1])) == wanted["SuccessfulExit"]


def _interval_check(expected: dict, interval) -> "bool | None":
    if interval is _AMBIGUOUS:
        return None
    wanted = expected.get("StartInterval")
    if wanted is None:
        # An absent StartInterval is meaningful: any loaded timer is stale.
        return interval is None
    if interval is None:
        return False
    return interval == wanted


def _watch_paths_check(expected: dict, watched) -> "bool | None":
    if watched is _AMBIGUOUS:
        return None
    if "WatchPaths" not in expected:
        return watched is None
    if watched is None:
        return False
    return watched == expected["WatchPaths"]


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
        props = _property_flags(root, scalars)
        interval = _run_interval(root, scalars)
        watched = _watch_paths(root)
        keep_alive_wanted = expected.get("KeepAlive", False)
        result.update({
            "start_interval_match": _interval_check(expected, interval),
            "watch_paths_match": _watch_paths_check(expected, watched),
            "run_at_load_match": _switch_check(expected.get("RunAtLoad", False), props, "runatload", False),
            "keep_alive_match": _keep_alive_check(keep_alive_wanted, root, scalars, props),
        })
        if any(result[name] is False for name in MATCH_FIELDS + SCHEDULE_FIELDS):
            # A definite mismatch on any checked field wins over unrelated unknowns.
            result["status"] = "mismatch"
        elif (any(result[name] is None for name in SCHEDULE_FIELDS)
              or "StartCalendarInterval" in expected):
            result["status"] = "unknown"
        else:
            result["status"] = "match"
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
        if result["loaded"] is not True:
            return result
        # A loaded job with unresolved schedule checks still needs the
        # read-only disabled probe: an explicit disable is a definite mismatch.
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
