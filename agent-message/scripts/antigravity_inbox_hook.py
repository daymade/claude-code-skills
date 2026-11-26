#!/usr/bin/env python3
"""Opt-in Antigravity lifecycle hook that injects queued peer-message envelopes.

Registered in ~/.gemini/config/hooks.json under flat arrays for:
  - SessionStart   (injectSteps)
  - PreInvocation  (injectSteps)
  - Stop           (decision="continue" only when terminationReason=="NO_TOOL_CALL"
                    and continuationActive is not True)

Runs synchronously inside the owning live Antigravity LS so injected steps are
persisted cleanly without competing LS processes or .pb corruption.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid

_transport_spec = importlib.util.spec_from_file_location(
    "peer_antigravity_transport", Path(__file__).with_name("antigravity_transport.py")
)
antigravity_transport = importlib.util.module_from_spec(_transport_spec)
_transport_spec.loader.exec_module(antigravity_transport)


def default_state_dir() -> Path:
    for env_key in ("AGENT_MESSAGE_STATE_DIR", "PEER_MESSAGE_STATE_DIR"):
        override = os.environ.get(env_key)
        if override:
            return Path(override).expanduser()
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "peer-message"


def handle_event(payload: object, *, state_dir: Path | None = None) -> dict:
    """Process one Antigravity hook stdin JSON payload and return the hook response dict."""
    if not isinstance(payload, dict):
        return {}
    raw_id = payload.get("conversationId")
    if not isinstance(raw_id, str) or not raw_id.strip():
        return {}
    try:
        conversation_id = str(uuid.UUID(raw_id.strip()))
    except ValueError:
        return {}

    event_name = payload.get("hookEventName")
    if event_name not in ("SessionStart", "PreInvocation", "Stop"):
        return {}

    if event_name == "Stop":
        if payload.get("terminationReason") != "NO_TOOL_CALL":
            return {}
        if payload.get("continuationActive"):
            return {}

    root = state_dir if state_dir is not None else default_state_dir()
    items = antigravity_transport.drain_inbox(root, conversation_id)
    if not items:
        return {}

    if event_name == "Stop":
        return {
            "decision": "continue",
            "reason": "\n\n".join(item["envelope"] for item in items),
        }

    return {
        "injectSteps": [
            {"systemMessage": {"systemMessage": item["envelope"]}} for item in items
        ],
        "terminationBehavior": "",
    }


def main() -> int:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            print("{}")
            return 0
        payload = json.loads(raw)
        response = handle_event(payload)
        print(json.dumps(response, ensure_ascii=False))
    except Exception as exc:
        print(f"agent-message antigravity inbox hook warning: {exc}", file=sys.stderr)
        print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
