#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["websockets==15.0.1"]
# ///
"""Deliver advisory peer text via the existing Codex App Server, once.

Run through uv; keep the WebSocket implementation with its upstream owner.
The JSON stdin request contains socket_path, thread_id and envelope. Never
resume a thread, answer a server approval, or retry an uncertain write.
"""

from __future__ import annotations

import json
import re
import sys
import time
from typing import Any


class DeliveryError(RuntimeError):
    def __init__(self, message: str, outcome: str = "not_sent", reason_code: str | None = None):
        super().__init__(message)
        self.outcome = outcome
        self.reason_code = reason_code


def _expected_turn_mismatch(error: object) -> bool:
    if not isinstance(error, dict) or type(error.get("code")) is not int or error["code"] != -32600:
        return False
    message = error.get("message")
    return isinstance(message, str) and re.fullmatch(
        r"expected active turn id [^\s]+ but found [^\s]+", message
    ) is not None


def rpc(connection, request_id: int, method: str, params: dict,
        *, writing: bool = False, timeout: float = 10) -> dict:
    outcome = "unknown" if writing else "not_sent"
    deadline = time.monotonic() + timeout
    try:
        connection.send(json.dumps({"id": request_id, "method": method, "params": params}))
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("response deadline exceeded")
            frame = json.loads(connection.recv(timeout=remaining))
            if not isinstance(frame, dict):
                raise ValueError("response is not an object")
            # Notifications and requests are not this observer's approvals.
            if "method" in frame or frame.get("id") != request_id:
                continue
            if "error" in frame:
                # A write error need not mean no side effect took place. The one
                # exception is the native expected-turn fence's exact mismatch.
                reason_code = "target_changed" if (
                    writing and method == "turn/steer" and _expected_turn_mismatch(frame["error"])
                ) else None
                raise DeliveryError(f"{method} rejected: {frame['error']}",
                                    "not_sent" if reason_code else outcome, reason_code)
            result = frame.get("result")
            if not isinstance(result, dict):
                raise ValueError("response is missing an object result")
            return result
    except DeliveryError:
        raise
    except Exception as exc:
        raise DeliveryError(f"{method}: {exc}", outcome) from exc


def deliver(request: dict, connect=None) -> dict[str, Any]:
    for key in ("socket_path", "thread_id", "envelope"):
        if not isinstance(request.get(key), str) or not request[key].strip():
            raise DeliveryError(f"missing string {key}")
    if connect is None:
        from websockets.sync.client import unix_connect
        connect = unix_connect
    try:
        connection = connect(request["socket_path"], open_timeout=3,
                             close_timeout=.2, max_size=8 * 1024 * 1024,
                             proxy=None, ping_interval=None)
    except Exception as exc:
        raise DeliveryError(f"App Server connection unavailable: {exc}") from exc
    # Closing an observer must not mask an accepted/uncertain send and cause a retry.
    try:
        rpc(connection, 1, "initialize", {
            "clientInfo": {"name": "peer_message_transport", "version": "1"},
            "capabilities": {"experimentalApi": True, "requestAttestation": False},
        })
        connection.send(json.dumps({"method": "initialized"}))
        thread = rpc(connection, 2, "thread/read", {
            "threadId": request["thread_id"], "includeTurns": False,
        }).get("thread")
        if not isinstance(thread, dict) or thread.get("id") != request["thread_id"]:
            raise DeliveryError("thread/read identity mismatch")
        status = thread.get("status")
        state = status.get("type") if isinstance(status, dict) else None
        if state == "notLoaded":
            return {"route": "queue", "reason": "target_not_loaded"}
        if state not in ("idle", "active") or thread.get("canAcceptDirectInput") is not True:
            raise DeliveryError(f"target cannot accept live input: {status!r}")
        if request.get("precise") is True and state == "active":
            turns = rpc(connection, 3, "thread/turns/list", {
                "threadId": request["thread_id"], "limit": 1,
                "sortDirection": "desc", "itemsView": "notLoaded",
            })
            rows = turns.get("data")
            latest = rows[0] if isinstance(rows, list) and rows else None
            if (not isinstance(latest, dict) or latest.get("status") != "inProgress"
                    or not isinstance(latest.get("id"), str) or not latest["id"]
                    or len(latest["id"]) > 128):
                raise DeliveryError("active target has no steerable turn")
            expected_turn = latest["id"]
            result = rpc(connection, 4, "turn/steer", {
                "threadId": request["thread_id"],
                "input": [{"type": "text", "text": request["envelope"]}],
                "expectedTurnId": expected_turn,
            }, writing=True)
            if not isinstance(result.get("turnId"), str) or result["turnId"] != expected_turn:
                raise DeliveryError("turn/steer returned a different turn identity", "unknown")
            return {"route": "app_server_steer", "turn_id": expected_turn,
                    "target_state_before_send": state}
        result = rpc(connection, 3, "turn/start", {
            "threadId": request["thread_id"], "input": [],
            "toolOutput": {"namespace": "peer_message", "name": "delivery",
                           "output": request["envelope"]},
        }, writing=True)
        turn = result.get("turn")
        if not isinstance(turn, dict) or not isinstance(turn.get("id"), str) or not turn["id"]:
            raise DeliveryError("turn/start returned no turn identity", "unknown")
        return {"route": "app_server_tool_output", "turn_id": turn["id"],
                "target_state_before_send": state}
    except DeliveryError:
        raise
    except Exception as exc:
        raise DeliveryError(str(exc)) from exc
    finally:
        try:
            connection.close()
        except Exception:
            pass


def main() -> int:
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise DeliveryError("stdin must be a JSON object")
        result = deliver(request)
        print(json.dumps({"status": "accepted", **result}))
        return 0
    except Exception as exc:
        receipt = {"status": "error", "outcome": getattr(exc, "outcome", "not_sent"),
                   "error": str(exc)}
        reason_code = getattr(exc, "reason_code", None)
        if isinstance(reason_code, str) and reason_code:
            receipt["reason_code"] = reason_code
        print(json.dumps(receipt))
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
