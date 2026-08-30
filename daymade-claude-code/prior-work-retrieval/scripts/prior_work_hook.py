#!/usr/bin/env python3
"""Claude/Codex hooks for the Prior Work Retrieval receipt contract.

The hook makes the cheap, mechanical decision only: is this prompt/action a
substantial production attempt, and is the current prompt's receipt present?
The Skill and human/agent judgment decide which prior work is actually useful.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import stat
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import prior_work

RECEIPT_MAX_AGE_SECONDS = 24 * 60 * 60
# Strong signals name prior work outright ("我们之前…", "复用", "reuse"). They
# arm the gate on their own.
PRIOR_WORK_STRONG_SIGNAL = re.compile(
    r"(?:我们之前|以前|之前做过|之前(?:用|跑|做|配|装|搭|建|写)|"
    # Bare 已有/现有/既有 used to arm ordinary references to the current
    # checkout ("现有测试或 README 如果冲突才同步"). Existing work must name a
    # reusable asset; current tests/files/behavior are not a history request.
    r"(?:已有|既有)(?:\s*的)?\s*"
    r"(?:(?:[一二两三四五六七八九十百千万0-9]+|好?几|多|若干)\s*)?"
    r"(?:个|套|份|条|版|组|批|项|段)?\s*"
    r"(?:代码|脚本|方案|资产|成果|SOP|流程|做法|工具|模板|系统)|"
    r"历史经验|历史决策|以前的代码|已有代码|"
    # 成功的经验 — the 的 particle broke the literal 成功经验.
    r"成功(?:的)?经验|"
    # 不希望你重新造轮子 — the literal 不要重新/不要重造/别重复 missed every
    # natural phrasing of the same ask.
    r"(?:别|不要|不想|不希望)(?:你)?\s*(?:重复|重新|重造|再造)|"
    r"复用|重用|沿用|类似的问题|类似问题|当时用的|"
    r"什么来着|叫什么来着|哪个来着|用的是?哪个|"
    r"项目最近进展|会议逐字稿|微信记录|prior work|previous work|existing code|"
    r"reuse|did this before|"
    # `history` only counts with a carrier in front of it. Bare `history`
    # matched `git history`, `browser history`, and this repo's own
    # read-claude-code-history skill name.
    r"(?:chat|conversation|session|work|project|prior|previous)\s+history)",
    re.IGNORECASE,
)
# Weak signals are hedge/recall phrasing ("好像是", "上次", "记不清"). They are
# the skill's core recall use-case but fire on ordinary speech too, so each
# needs a concrete work noun nearby before it arms anything.
PRIOR_WORK_WEAK_SIGNAL = re.compile(
    r"(?:上次|我记得是|好像是|记不清)",
    re.IGNORECASE,
)
_WORK_NOUN_INNER = (
    r"(?:代码|脚本|方案|框架|配置|文档|流程|做法|工具|库|项目|接口|命令|模板|"
    r"仓库|分支|函数|模块|服务|规则|SOP|skill|agent|prompt|hook|schema)"
)
WORK_NOUN = re.compile(_WORK_NOUN_INNER, re.IGNORECASE)
# The weak tier needs the noun to point AWAY from the current object. 这个脚本
# is the script in front of us ("这个脚本好像是死循环" is a bug report); 那个/某个/
# 哪个 script is one being recalled. Distal and indefinite determiners are the
# grammatical marker for that, so the weak tier keys on them rather than on the
# bare noun.
DISTAL_WORK_NOUN = re.compile(
    r"(?:那|某|哪)(?:[一二三四五六七八九十]+)?[个种份条次回台款道位家份套版]?\s*"
    + _WORK_NOUN_INNER,
    re.IGNORECASE,
)
# Not the user talking: Claude Code's own internal templates (safety
# classifier, suggestion generator), sub-agent role prompts, and pasted
# transcript fragments all arrive through UserPromptSubmit and each opened
# its own gated session.
NON_USER_PROMPT = re.compile(
    r"\A\s*(?:"
    r"You are (?:a|an|the)\b"
    r"|#\s*Overview\s*$"
    # Harness-generated envelopes, not typed by anyone: <agent-message …>,
    # <task-notification …> (a background workflow finishing reaches the same
    # handler), <system-reminder …>.
    r"|<[a-z][a-z0-9-]*-(?:message|notification|reminder)\b"
    r"|⏺\s"
    # Another hook's block message echoed back as a prompt:
    # "• UserPromptSubmit (blocked) says: …". This hook's own guidance is
    # already excluded by HOOK_GUIDANCE_MARKER; every other hook's was not.
    r"|•\s*\w+\s*\(blocked\)\s+says:"
    r")",
    re.IGNORECASE | re.MULTILINE,
)
# "不要复用 X" is a decision against reuse, not a request to retrieve it.
# Excised before signal matching so a same-sentence genuine ask still counts.
# Deliberately excludes 重复造轮子/重造/重新造, which ask FOR reuse.
NEGATED_PRIOR_SIGNAL = re.compile(
    r"(?:不要|不用|无需|不需要|不必|别|勿)\s*(?:再\s*)?(?:去\s*)?"
    r"(?:复用|重用|沿用|参考(?:以前|之前|历史|已有))[^\n，,。；;]{0,60}"
    r"|(?:不要|不用|无需|不需要|不必|别|勿)\s*(?:再\s*)?(?:用|看|查|翻)\s*"
    r"(?:以前|之前|历史|旧)(?:的)?"
    r"|(?:don't|do not|no need to|stop)\s+(?:reuse|reusing|referencing)"
    r"[^\n,.!?;]{0,60}",
    re.IGNORECASE,
)
# "这些 Skill 也是很久之前写的" dates something to argue it is stale — the
# opposite of asking to go find it. Excised like a negation.
STALE_AGE_IDIOM = re.compile(r"(?:很久|太久|好久|老早|早就)\s*(?:以前|之前)")
# 「我们这个对话最开始是想要干什么来着」/「我们的主线任务是什么来着」ask what the
# CURRENT session is about. The answer is the conversation already in front of the
# executor: no carrier to search, no candidate to verify, and no artifact produced —
# so the gate can only add friction, and a gate that misfires on healthy input is
# how an operator learns to bypass it reflexively.
#
# This is the same distinction the weak tier already draws with 这个脚本 (the script
# in front of you) vs 那个脚本 (one being recalled), but 什么来着 sits in the strong
# tier and so arms with no distal requirement. Demoting it to the weak tier is the
# wrong fix: 「上次做的方案叫什么来着？」 is a genuine recall and carries no distal
# determiner, so it would stop arming. Excising the proximal construct instead
# leaves every distal phrasing untouched.
#
# The excised span MUST include the recall idiom itself — excising only 这个对话
# leaves 什么来着 behind and the strong tier still matches it.
CURRENT_SESSION_RECALL = re.compile(
    r"(?:这个|这次|本次|当前|我们这)\s*(?:对话|会话|session)[^\n。；;，,]{0,30}"
    r"(?:什么来着|想(?:要)?干什么|要干什么|是要做什么)"
    r"|(?:主线|当前|本次)\s*(?:任务|目标)\s*(?:是)?\s*什么来着",
    re.IGNORECASE,
)
HOOK_GUIDANCE_MARKER = "Prior Work Retrieval is required before substantial production"
USER_OPTOUT = re.compile(
    r"(?:不用|不要|无需|跳过).{0,12}(?:查历史|检索历史|已有工作检索|prior work|历史检索)"
    # Recorded sub-agent prompts said "Do NOT perform prior-work retrieval" and
    # "The user explicitly opts out of prior-work retrieval" and were gated
    # anyway: the old pattern only accepted skip/disable, and only the
    # space-separated spelling.
    r"|(?:skip|disable|opts?\s+out\s+of|opting\s+out\s+of|"
    r"do\s+not\s+(?:perform|use|load|run|invoke)|don't\s+(?:perform|use|load|run|invoke))"
    r"[^\n]{0,24}(?:prior[-\s]work|history retrieval)",
    re.IGNORECASE,
)
# A prompt that forbids its executor from reading skills or running the shell
# has removed the very capabilities completing a receipt requires. Gating it
# cannot be satisfied — it only blocks work. Recorded scope-restricted
# sub-agent prompts did exactly this and were gated for it.
INCAPABLE_EXECUTOR = re.compile(
    r"(?:do\s+not|don't|never)\s+(?:read|load|use|execute|inspect|run)"
    r"[^\n]{0,90}(?:SKILL\.md|skills?/|\.claude/|\.agents/|\.codex/)",
    re.IGNORECASE,
)
SHELL_WRITE_SIGNAL = re.compile(
    r"(?:tools\.apply_patch|\bapply_patch\b|\.write_(?:text|bytes)\s*\(|"
    r"\bopen\s*\([^\n)]*,\s*['\"](?:w|a|x)|\b(?:tee|touch|mkdir|install|cp|mv|rsync)\b|"
    r"\b(?:sed|perl)\b[^\n]*(?:\s-i\b|\s-pi\b)|"
    r"\bgit\s+(?:add|commit|push|merge|rebase|tag|checkout|switch|reset|clean)\b)",
    re.IGNORECASE | re.MULTILINE,
)
SHELL_UNKNOWN_EXECUTOR = re.compile(
    # The lookbehind keeps file-suffix collisions out: `report.sh` is a path
    # argument to read, not the interpreter `sh` — a dot (or word char)
    # immediately before the token means it is a filename component.
    r"(?<![\w.])(?:python(?:3)?|node|bash|zsh|sh)\b",
    re.IGNORECASE,
)
SHELL_READ_ONLY_EXECUTOR = re.compile(
    r"(?:--help\b|\s-m\s+unittest\b|\bpytest\b|\bruff\s+check\b|"
    r"\b(?:status|validate|check)(?:\s|\(|\b))",
    re.IGNORECASE,
)
RETRIEVAL_ROUTES = {
    "prior_work.py": {"validate-manifest", "retrieve", "complete", "check"},
    "history_index.py": {"recall", "status"},
    "analyze_sessions.py": {"search", "locate-codex"},
    "read_chat.py": None,
}
DIRECT_EXEC_WRITE_SIGNAL = re.compile(r"\b(?:tools\.)?apply_patch\s*\(")
EXEC_COMMAND_LITERAL = re.compile(
    r"\b(?:cmd|command)\s*:\s*([\"'`])(?P<body>.*?)(?<!\\)\1",
    re.DOTALL,
)
FILE_REDIRECTION = re.compile(
    r"(?<![<>=])(?:1|2|&)?(?:>>|>)(?![=&])\s*(?P<target>[^\s;|]+)"
)


def _manifest() -> dict[str, Any]:
    return prior_work.load_manifest(prior_work.default_manifest_path().resolve())


def classify_prompt(prompt: str, receipt_valid: bool = False) -> str:
    """Classify one UserPromptSubmit body.

    `receipt_valid` says this session already holds a receipt that passes
    check_receipt. Hedge-phrased recall is then already covered, so it must
    not mint a fresh requirement and strand the completed one.
    """
    text = prompt.strip()
    if not text:
        return "none"
    if HOOK_GUIDANCE_MARKER in text:
        return "none"
    if NON_USER_PROMPT.search(text):
        return "none"
    if INCAPABLE_EXECUTOR.search(text):
        return "none"
    if USER_OPTOUT.search(text):
        return "opt_out"
    scannable = CURRENT_SESSION_RECALL.sub(
        " ", STALE_AGE_IDIOM.sub(" ", NEGATED_PRIOR_SIGNAL.sub(" ", text))
    )
    if PRIOR_WORK_STRONG_SIGNAL.search(scannable):
        return "required_prior_signal"
    if PRIOR_WORK_WEAK_SIGNAL.search(scannable) and DISTAL_WORK_NOUN.search(scannable):
        return "none" if receipt_valid else "required_prior_signal"
    return "none"


def _tool_name(event: dict[str, Any]) -> str:
    value = event.get("tool_name")
    return value if isinstance(value, str) else ""


def _tool_input(event: dict[str, Any]) -> dict[str, Any]:
    value = event.get("tool_input")
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return {"input": value}
    return {}


def _base_tool_name(event: dict[str, Any]) -> str:
    return _tool_name(event).rsplit("__", 1)[-1].rsplit(".", 1)[-1]


def _tool_payload_text(event: dict[str, Any]) -> str:
    tool_input = _tool_input(event)
    for key in ("command", "cmd", "input", "code", "source"):
        value = tool_input.get(key)
        if isinstance(value, str):
            return value
    return ""


def _shell_fragments(event: dict[str, Any]) -> list[str]:
    payload = _tool_payload_text(event)
    if _tool_name(event).endswith("functions.exec"):
        return [match.group("body") for match in EXEC_COMMAND_LITERAL.finditer(payload)]
    return [payload]


def _shell_segments(fragment: str) -> list[str]:
    """Split a shell fragment on command separators outside quotes.

    Single pass, quote state only — no parallel arrays. Substitution bodies
    ($(...) and backticks) are deliberately not parsed; the write-signal scan
    already treats their contents as plain text.
    """
    segments: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    i = 0
    while i < len(fragment):
        ch = fragment[i]
        if quote == '"':
            if ch == "\\" and i + 1 < len(fragment) and fragment[i + 1] in '"\\$`':
                buf.append(fragment[i : i + 2])
                i += 2
                continue
            if ch == '"':
                quote = None
            buf.append(ch)
            i += 1
            continue
        if quote == "'":
            if ch == "'":
                quote = None
            buf.append(ch)
            i += 1
            continue
        if ch in {'"', "'"}:
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch == "\\" and i + 1 < len(fragment):
            # Outside quotes, a backslash escapes the next byte. In particular,
            # `\;` is argument data, not a command separator.
            buf.append(fragment[i : i + 2])
            i += 2
            continue
        if fragment.startswith("&&", i) or fragment.startswith("||", i):
            segments.append("".join(buf))
            buf = []
            i += 2
            continue
        if ch == "&" and not (i > 0 and fragment[i - 1] in "><"):
            segments.append("".join(buf))
            buf = []
            i += 1
            continue
        if ch in ";|\n":
            segments.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    segments.append("".join(buf))
    return segments


def _segment_is_retrieval_route(segment: str) -> bool:
    """True when the segment's main command is a whitelisted retrieval tool.

    Its arguments are data, so prose tokens there (e.g. a --reject reason
    quoting "cp→symlink") must not trip the write signal. Stay closed when a
    real write hides around the retrieval token: a write command in the
    prefix (git commit -m "prior_work.py complete ...") or a command
    substitution in the arguments (which the shell would really execute).
    """
    try:
        words = shlex.split(segment, posix=True)
    except ValueError:
        return False
    substitution_tokens = ("$(", "`", "<(", ">(", "=(")
    if not words or any(
        token in word for word in words for token in substitution_tokens
    ):
        return False

    assignment = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$", re.DOTALL)
    index = 0
    while index < len(words) and assignment.match(words[index]):
        index += 1

    if index < len(words) and Path(words[index]).name == "env":
        index += 1
        while index < len(words):
            word = words[index]
            if word in {"-u", "--unset"}:
                index += 2
            elif word.startswith("-") or assignment.match(word):
                index += 1
            else:
                break

    if index < len(words) and words[index] == "command":
        index += 1
        while index < len(words) and words[index].startswith("-"):
            index += 1

    if index < len(words) and Path(words[index]).name == "uv":
        index += 1
        if index >= len(words) or words[index] != "run":
            return False
        index += 1
        uv_value_options = {
            "--with", "--with-editable", "--project", "--directory",
            "--python", "--index", "--default-index", "--find-links",
            "--env-file",
        }
        while index < len(words) and words[index].startswith("-"):
            option = words[index].split("=", 1)[0]
            index += 1
            if option in uv_value_options and "=" not in words[index - 1]:
                if index >= len(words):
                    return False
                index += 1

    if index < len(words) and re.fullmatch(r"python(?:3(?:\.\d+)?)?", Path(words[index]).name):
        index += 1
        # `python -c '...prior_work.py...'` is arbitrary code, not a route.
        if index < len(words) and words[index].startswith("-"):
            return False

    if index >= len(words):
        return False
    script = Path(words[index]).name
    subcommands = RETRIEVAL_ROUTES.get(script)
    if script not in RETRIEVAL_ROUTES:
        return False
    if subcommands is None:
        return True
    return index + 1 < len(words) and words[index + 1] in subcommands


def _strip_quoted_text(fragment: str) -> str:
    """Blank out quoted regions so argument data is not scanned as redirection.

    A prose token like '未合并>7天' inside a quoted retrieval-route argument is
    data, not `> 7天...` redirection. Unquoted `>` survives the strip, so real
    redirections — including one chained after a route command — stay gated.
    """
    out: list[str] = []
    quote: str | None = None
    i = 0
    while i < len(fragment):
        ch = fragment[i]
        if quote == '"':
            if ch == "\\" and i + 1 < len(fragment) and fragment[i + 1] in '"\\$`':
                out.append("  ")
                i += 2
                continue
            if ch == '"':
                quote = None
            out.append(" ")
            i += 1
            continue
        if quote == "'":
            if ch == "'":
                quote = None
            out.append(" ")
            i += 1
            continue
        if ch in {'"', "'"}:
            quote = ch
            out.append(" ")
            i += 1
            continue
        if ch == "\\" and i + 1 < len(fragment):
            out.append(fragment[i : i + 2])
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _has_formal_file_redirection(event: dict[str, Any]) -> bool:
    for fragment in _shell_fragments(event):
        for match in FILE_REDIRECTION.finditer(_strip_quoted_text(fragment)):
            target = match.group("target").strip("\"'")
            if target in {"/dev/null", "&1", "&2"}:
                continue
            return True
    return False


def substantial_tool_use(event: dict[str, Any]) -> tuple[bool, str]:
    base = _base_tool_name(event)
    tool_input = _tool_input(event)
    path_value = tool_input.get("file_path") or tool_input.get("path")
    if base == "Write":
        content = tool_input.get("content")
        target = Path(path_value).expanduser() if isinstance(path_value, str) else None
        event_cwd = event.get("cwd")
        if target is not None and not target.is_absolute() and isinstance(event_cwd, str):
            target = Path(event_cwd).expanduser() / target
        new_file = bool(target and not target.exists())
        size = len(content) if isinstance(content, str) else 0
        return new_file or size >= 120, f"Write:new={new_file}:chars={size}"
    if base in {"Edit", "MultiEdit", "NotebookEdit"}:
        strings = []
        for key in ("new_string", "new_source", "content"):
            value = tool_input.get(key)
            if isinstance(value, str):
                strings.append(value)
        edits = tool_input.get("edits")
        if isinstance(edits, list):
            for edit in edits:
                if isinstance(edit, dict):
                    value = edit.get("new_string")
                    if isinstance(value, str):
                        strings.append(value)
        size = sum(len(value) for value in strings)
        lines = sum(value.count("\n") + 1 for value in strings)
        return size >= 200 or lines >= 6, f"{base}:chars={size}:lines={lines}"
    if base == "apply_patch":
        patch = next(
            (
                value
                for key in ("patch", "input", "text")
                if isinstance((value := tool_input.get(key)), str)
            ),
            "",
        )
        added_lines = sum(
            1
            for line in patch.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )
        new_file = "*** Add File:" in patch
        return new_file or added_lines >= 5, (
            f"apply_patch:new={new_file}:added_lines={added_lines}"
        )
    if base in {"Agent", "Task", "spawn_agent"}:
        prompt = tool_input.get("prompt") or tool_input.get("message")
        size = len(prompt) if isinstance(prompt, str) else 0
        return size >= 240, f"{base}:prompt_chars={size}"
    if base in {"Bash", "exec", "exec_command"}:
        payload = _tool_payload_text(event)
        if DIRECT_EXEC_WRITE_SIGNAL.search(payload):
            return True, f"{base}:write_signal"
        fragments = _shell_fragments(event)
        # functions.exec can carry either JavaScript orchestration or a plain
        # command string. With no cmd/command literal, treat the payload itself
        # as the command so direct retrieval calls keep working.
        if not fragments:
            fragments = [payload]
        segments = [
            segment
            for fragment in fragments
            for segment in _shell_segments(fragment)
            if segment.strip()
        ]
        route_flags = [_segment_is_retrieval_route(segment) for segment in segments]
        gated = [segment for segment, is_route in zip(segments, route_flags) if not is_route]
        if any(SHELL_WRITE_SIGNAL.search(s) for s in gated):
            return True, f"{base}:write_signal"
        if _has_formal_file_redirection(event):
            return True, f"{base}:write_signal"
        if any(
            SHELL_UNKNOWN_EXECUTOR.search(segment)
            and not SHELL_READ_ONLY_EXECUTOR.search(segment)
            for segment in gated
        ):
            return True, f"{base}:unknown_executor"
        if any(route_flags):
            return False, f"{base}:retrieval_route"
        return False, f"{base}:read_only"
    return False, "unsupported_tool"


def _pretool_deny(reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def _stop_block(reason: str) -> dict[str, Any]:
    return {"decision": "block", "reason": reason, "systemMessage": reason}


def _inject(message: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": message,
        }
    }


def _hook_command(wrapper: Path) -> str:
    return shlex.quote(str(wrapper.resolve()))


def desired_hook_groups(wrapper: Path, host: str) -> dict[str, dict[str, Any]]:
    command = _hook_command(wrapper)
    base: dict[str, Any] = {"type": "command", "command": command, "timeout": 15}
    matcher = (
        "Write|Edit|MultiEdit|NotebookEdit|Agent|Task|Bash"
        if host == "claude"
        else "^(apply_patch|Write|Edit|MultiEdit|NotebookEdit|spawn_agent|exec|exec_command|functions\\.exec)$"
    )
    return {
        "UserPromptSubmit": {
            "hooks": [{**base, "statusMessage": "Checking prior-work retrieval scope"}]
        },
        "PreToolUse": {
            "matcher": matcher,
            "hooks": [{**base, "statusMessage": "Checking prior-work receipt"}],
        },
        "Stop": {
            "hooks": [{**base, "statusMessage": "Checking prior-work completion"}]
        },
    }


def merged_hooks(
    current: dict[str, Any],
    wrapper: Path,
    host: str,
    *,
    remove_legacy_recall: bool,
) -> dict[str, Any]:
    result = json.loads(json.dumps(current))
    hooks = result.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise prior_work.PriorWorkError("hook config top-level hooks must be an object")
    for event_name, desired_group in desired_hook_groups(wrapper, host).items():
        groups = hooks.setdefault(event_name, [])
        if not isinstance(groups, list):
            raise prior_work.PriorWorkError(f"hooks.{event_name} must be an array")
        cleaned = []
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                cleaned.append(group)
                continue
            kept = []
            for handler in group["hooks"]:
                command = handler.get("command") if isinstance(handler, dict) else None
                command_parts = []
                if isinstance(command, str):
                    try:
                        command_parts = shlex.split(command)
                    except ValueError:
                        command_parts = []
                command_path = Path(command_parts[0]) if len(command_parts) == 1 else None
                ours = bool(command_path and command_path == wrapper.resolve())
                legacy = (
                    remove_legacy_recall
                    and event_name == "UserPromptSubmit"
                    and command_path is not None
                    and command_path.name == "recall-first-evidence.sh"
                )
                if not ours and not legacy:
                    kept.append(handler)
            if kept:
                next_group = dict(group)
                next_group["hooks"] = kept
                cleaned.append(next_group)
        cleaned.append(desired_group)
        hooks[event_name] = cleaned
    return result


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    old_mode = None
    try:
        old_mode = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        pass
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        if old_mode is not None:
            os.fchmod(descriptor, old_mode)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _load_hook_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"hooks": {}}
    payload = prior_work._read_json(path)
    if not isinstance(payload, dict):
        raise prior_work.PriorWorkError(f"Hook config must be an object: {path}")
    return payload


def install_hooks(*, check_only: bool, remove_legacy_recall: bool) -> bool:
    source_wrapper = Path(__file__).with_name("prior-work-retrieval.sh").resolve()
    claude_link = Path.home() / ".claude" / "hooks" / "prior-work-retrieval.sh"
    if check_only:
        if not claude_link.is_symlink() or claude_link.resolve() != source_wrapper:
            return False
    else:
        claude_link.parent.mkdir(parents=True, exist_ok=True)
        if claude_link.exists() or claude_link.is_symlink():
            if not claude_link.is_symlink() or claude_link.resolve() != source_wrapper:
                raise prior_work.PriorWorkError(
                    f"Refusing to replace unrelated hook path: {claude_link}"
                )
        else:
            claude_link.symlink_to(source_wrapper)
    targets = [
        (
            Path.home() / ".claude" / "settings.json",
            claude_link,
            "claude",
        ),
        (
            Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
            / "hooks.json",
            source_wrapper,
            "codex",
        ),
    ]
    all_current = True
    for config_path, wrapper, host in targets:
        current = _load_hook_config(config_path)
        desired = merged_hooks(
            current,
            wrapper,
            host,
            remove_legacy_recall=remove_legacy_recall and host == "claude",
        )
        if desired != current:
            all_current = False
            if not check_only:
                _atomic_text(
                    config_path,
                    json.dumps(desired, ensure_ascii=False, indent=2) + "\n",
                )
    return all_current if check_only else True


def _receipt_error(manifest: dict[str, Any], session_id: str) -> str | None:
    try:
        prior_work.check_receipt(
            manifest, session_id, RECEIPT_MAX_AGE_SECONDS
        )
    except prior_work.PriorWorkError as error:
        return str(error)
    return None


def _guidance(reason: str, session_id: Any = None) -> str:
    text = (
        "Prior Work Retrieval is required before substantial production. "
        f"Trigger: {reason}. Load the prior-work-retrieval Skill, run "
        "scripts/prior_work.py retrieve with one --business-outcome sentence, "
        "artifact/event --outcome-term values, and separate implementation terms "
        "across the explicit manifest; open and "
        "verify candidates, then complete a reuse/adapt/no-reuse receipt for this "
        "session. Read-only discovery remains allowed."
    )
    if isinstance(session_id, str) and session_id:
        text += (
            f" Pass exactly this id to retrieve, complete, and check: "
            f"--session-id '{session_id}'. validate-manifest has no session-id option. "
            "The receipt filename in Trigger is its sha256, not the id itself."
        )
    return text


def handle_user_prompt(event: dict[str, Any]) -> dict[str, Any] | None:
    prompt = event.get("prompt")
    session_id = event.get("session_id")
    if not isinstance(prompt, str) or not prompt.strip():
        return None
    if not isinstance(session_id, str) or not session_id:
        if classify_prompt(prompt) == "required_prior_signal":
            return _inject(
                "Prior-work retrieval applies, but this hook event has no session_id; "
                "do not produce until the session identity and receipt can be recorded."
            )
        return None
    try:
        manifest = _manifest()
        current = prior_work.load_requirement(manifest, session_id)
    except prior_work.PriorWorkError as error:
        if classify_prompt(prompt) == "required_prior_signal":
            return _inject(
                f"Prior-work manifest is unavailable ({error}). Fix the explicit "
                "manifest before substantial production; do not silently fall back."
            )
        return None
    receipt_valid = current is not None and _receipt_error(manifest, session_id) is None
    classification = classify_prompt(prompt, receipt_valid)
    if classification == "none":
        return None
    required = classification != "opt_out"
    requirement = prior_work.mark_requirement(
        manifest,
        session_id,
        prompt=prompt,
        trigger=classification,
        required=required,
    )
    if not required:
        return None
    return _inject(_guidance(requirement["trigger"], session_id))


def handle_pre_tool(event: dict[str, Any]) -> dict[str, Any] | None:
    session_id = event.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return None
    try:
        manifest = _manifest()
        requirement = prior_work.load_requirement(manifest, session_id)
        if requirement is None or not requirement.get("required"):
            return None
    except prior_work.PriorWorkError:
        # This feature is explicit-only. If no readable requirement can prove
        # that the current prompt opted into prior-work retrieval, an ordinary
        # write must not be converted into a global production gate.
        return None
    substantial, reason = substantial_tool_use(event)
    if not substantial:
        return None
    error = _receipt_error(manifest, session_id)
    if error is not None:
        return _pretool_deny(_guidance(f"{reason}; receipt: {error}", session_id))
    return None


def handle_stop(event: dict[str, Any]) -> dict[str, Any] | None:
    if event.get("stop_hook_active") is True:
        return None
    session_id = event.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return None
    try:
        manifest = _manifest()
        requirement = prior_work.load_requirement(manifest, session_id)
        if requirement is None or not requirement.get("required"):
            return None
        error = _receipt_error(manifest, session_id)
    except prior_work.PriorWorkError as error:
        return _stop_block(
            f"Prior Work Retrieval configuration/state failed: {error}. "
            "Repair it before finishing this substantial response."
        )
    if error is not None:
        return _stop_block(_guidance(f"final response; receipt: {error}", session_id))
    return None


def handle_event(event: dict[str, Any]) -> dict[str, Any] | None:
    event_name = event.get("hook_event_name")
    if event_name == "UserPromptSubmit":
        return handle_user_prompt(event)
    if event_name == "PreToolUse":
        return handle_pre_tool(event)
    if event_name == "Stop":
        return handle_stop(event)
    return None


def selftest() -> None:
    with tempfile.TemporaryDirectory(prefix="prior-work-hook-") as name:
        root = Path(name)
        source = root / "source"
        source.mkdir()
        (source / "known.md").write_text("known existing contract\n", encoding="utf-8")
        manifest_path = root / "manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "state_dir": str(root / "state"),
                    "sources": [
                        {
                            "id": "docs",
                            "carrier": "docs",
                            "mode": "filesystem",
                            "root": str(source),
                            "includes": ["**/*.md"],
                            "authority": "project_ssot",
                            "required": True,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        old_manifest = os.environ.get("PRIOR_WORK_MANIFEST")
        os.environ["PRIOR_WORK_MANIFEST"] = str(manifest_path)
        try:
            prompt_event = {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "selftest-session",
                "prompt": "以前做过类似系统，复用已有代码实现这个功能",
            }
            assert handle_event(prompt_event) is not None
            write_event = {
                "hook_event_name": "PreToolUse",
                "session_id": "selftest-session",
                "tool_name": "Write",
                "tool_input": {
                    "file_path": str(root / "formal.py"),
                    "content": "x = 1\n" * 30,
                },
            }
            assert handle_event(write_event) is not None
            manifest = _manifest()
            run = prior_work.retrieve(
                manifest,
                "Reuse the verified existing contract before writing new code.",
                ["known existing"],
                "reuse known contract",
                ["known existing"],
                "selftest-session",
            )
            candidate = run["candidates"][0]
            prior_work.complete(
                manifest,
                run["run_id"],
                "selftest-session",
                [f"{candidate['candidate_id']}=reuse verified existing contract"],
                [],
                [],
                [],
                None,
            )
            assert handle_event(write_event) is None
            opt_out = {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "selftest-session",
                "prompt": "这次不用查历史，跳过已有工作检索",
            }
            assert handle_event(opt_out) is None
            assert handle_event(write_event) is None
            stop_event = {
                "hook_event_name": "Stop",
                "session_id": "new-session",
                "stop_hook_active": False,
                "last_assistant_message": "- item\n" * 100,
            }
            # No requirement yet: Stop must not invent one from a long,
            # list-shaped final message.
            assert handle_event(stop_event) is None
            prior_work.mark_requirement(
                manifest,
                "new-session",
                prompt="Produce the requested implementation",
                trigger="required_prior_signal",
                required=True,
            )
            assert handle_event(stop_event) is not None
            stop_event["stop_hook_active"] = True
            assert handle_event(stop_event) is None
        finally:
            if old_manifest is None:
                os.environ.pop("PRIOR_WORK_MANIFEST", None)
            else:
                os.environ["PRIOR_WORK_MANIFEST"] = old_manifest
    print("prior-work hook selftest: OK")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--selftest", action="store_true")
    modes.add_argument("--install", action="store_true")
    modes.add_argument("--check-install", action="store_true")
    parser.add_argument(
        "--keep-legacy-recall-hook",
        action="store_true",
        help="Do not remove the superseded recall-first-evidence handler",
    )
    args = parser.parse_args(argv)
    if args.selftest:
        selftest()
        return 0
    if args.install:
        install_hooks(
            check_only=False,
            remove_legacy_recall=not args.keep_legacy_recall_hook,
        )
        print(
            "Installed prior-work hooks for Claude and Codex. Run the profile "
            "settings synchronizer, then review/trust new Codex hook definitions "
            "once with /hooks."
        )
        return 0
    if args.check_install:
        current = install_hooks(
            check_only=True,
            remove_legacy_recall=not args.keep_legacy_recall_hook,
        )
        if current:
            print("Prior-work hook configuration is current.")
            return 0
        print("Prior-work hook configuration is missing or stale.", file=sys.stderr)
        return 1
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            raise TypeError("hook input must be a JSON object")
    except (json.JSONDecodeError, OSError, TypeError) as error:
        print(f"prior-work hook invalid input: {error}", file=sys.stderr)
        return 2
    output = handle_event(event)
    if output is not None:
        print(json.dumps(output, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
