#!/usr/bin/env python3
"""PeerMessage-owned native PreToolUse validator. No send, permission allow or daemon."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid

_spec = importlib.util.spec_from_file_location("native_guard_peer", Path(__file__).with_name("peer.py"))
peer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(peer)

CODEX_SEND = "mcp__codex_tui__send_message_to_thread"
CODEX_SEND_TOOLS = frozenset((CODEX_SEND, "codex_tui.send_message_to_thread", "send_message_to_thread"))
NATIVE_TOOLS = CODEX_SEND_TOOLS | {"SendMessage"}


def internal_claude_target(target, event, home):
    """Use an actual current-session relationship, not a model supplied kind."""
    if target == "main":
        return True  # reserved native parent address
    session_id = str(uuid.UUID(event.get("session_id")))
    transcript = event.get("transcript_path")
    if isinstance(transcript, str):
        path = Path(transcript)
        if path.stem == session_id and path.parent.parent == home / "projects":
            agents = path.parent / session_id / "subagents"
            if agents.is_dir() and any(p.name == f"agent-{target}.jsonl" for p in agents.iterdir()):
                return True
    # Only team manifests; never read transcript bodies or enumerate other histories.
    teams = home / "teams"
    if teams.is_dir():
        for path in teams.glob("*/config.json"):
            value = peer.read_json(path)
            if value and value.get("leadSessionId") == session_id:
                if any(isinstance(m, dict) and target in (m.get("name"), m.get("agentId"))
                       for m in value.get("members", [])):
                    return True
    return False


def check(event, *, root=None, claude_home=None):
    """Return None off-scope, checked on success; raise on relevant unknown/deny."""
    if not isinstance(event, dict):
        raise ValueError("hook event must be an object")
    name = event.get("tool_name")
    if name not in NATIVE_TOOLS:
        return None
    if event.get("hook_event_name") != "PreToolUse":
        raise ValueError("native guard requires PreToolUse")
    args = event.get("tool_input")
    if not isinstance(args, dict):
        raise ValueError("native send arguments unavailable")
    session_id = str(uuid.UUID(event.get("session_id")))
    if name in CODEX_SEND_TOOLS:
        target = "codex:" + str(uuid.UUID(args.get("threadId")))
        sender = "codex:" + session_id
        body = args.get("prompt")
        if not isinstance(body, str) or len(body.encode()) > 1000:
            raise ValueError("native Codex prompt must be text within the host size cap")
    else:
        target = peer.coordination.nonblank(args.get("to", args.get("recipient")), "to")
        home = Path(claude_home or peer.default_claude_home()).expanduser()
        if internal_claude_target(target, event, home):
            return None
        body = args.get("message", args.get("content"))
        # A pure native idle subscription sends no message and does not wake the peer.
        if "message" not in args and "content" not in args and args.get("notify_when_idle") is True:
            return None
        entry = peer.resolve_claude(target, home)
        target = "claude:" + str(uuid.UUID(entry.get("sessionId")))
        sender = "claude:" + session_id
    board = peer.coordination.Board(root or peer.coordination.default_root())
    try:
        return board.claim_native(body, sender, target, name, event.get("tool_use_id"))
    finally:
        board.close()


def installed_check(event):
    if isinstance(event, dict) and event.get("tool_name") not in NATIVE_TOOLS:
        return None
    if isinstance(event, dict) and event.get("tool_name") == "SendMessage":
        args = event.get("tool_input")
        if isinstance(args, dict) and internal_claude_target(
                args.get("to", args.get("recipient")), event, peer.default_claude_home()):
            return None
    config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "peer-message/native-guard.json"
    manifest = json.loads(config.read_text())
    if manifest.get("schema") != 1 or not Path(manifest["python"]).is_absolute():
        raise ValueError("native guard binding unavailable")
    return check(event)


def main():
    event = None
    try:
        event = json.load(sys.stdin)
        installed_check(event)
    except Exception:
        # Fixed text: never leak private content, recipient paths or hook inputs.
        target = ""
        if isinstance(event, dict) and event.get("tool_name") == "SendMessage" \
                and isinstance(event.get("tool_input"), dict):
            target = str(event["tool_input"].get("to") or event["tool_input"].get("recipient") or "")
        if target.startswith("codex:"):
            # SendMessage resolves Claude sessions only, so a codex: target has no
            # prepare-then-native-send path; preparing would only orphan a reserved row.
            print("BLOCKED (PeerMessage): SendMessage resolves Claude sessions only; a codex: target "
                  "is unreachable this way and has no prepare-then-native-send path. Do not run coord "
                  "prepare for it — the reserved row it creates would later suppress this Skill's "
                  "scripts/peer.py send as suppressed_pending. Send directly: scripts/peer.py send "
                  "'codex:<thread-id>' <body-file>. If coord prepare already ran for this target, "
                  "close the orphan row first: coord commit --message-id <id> --outcome not_sent.",
                  file=sys.stderr)
        else:
            print("BLOCKED (PeerMessage): native coordination is unprepared, expired, changed, repeated, "
                  "or unavailable. Run this installed Skill's scripts/peer.py coord prepare with the exact "
                  "recipient and original deadline, send its body unchanged once, then coord commit. "
                  "Reconcile an earlier reserved/unknown attempt before retry; do not switch transport.", file=sys.stderr)
        return 2
    return 0  # no permissionDecision=allow; preserve every other permission/deny


if __name__ == "__main__":
    raise SystemExit(main())
