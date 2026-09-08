#!/usr/bin/env python3
"""Classify Gangtise auth/RAG responses without printing tokens or response bodies."""

import argparse
import json
import re
import sys
from typing import Any, Dict


def _safe(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return re.sub(r"[\r\n\t]+", " ", str(value))[:160]


def _failure_category(body: Dict[str, Any], http_status: int) -> str:
    code = str(body.get("code", ""))
    error_type = str(body.get("errorType", "")).upper()
    message = str(body.get("msg") or body.get("message") or "").lower()
    if code == "999005" or error_type == "POINT_NOT_ENOUGH" or "积分不足" in message:
        return "quota"
    if code in {"0000001008", "1008"} or "token is invalid" in message:
        return "auth"
    if code in {"0000001009", "1009"} or "uri can't be accessed" in message:
        return "permission"
    if http_status == 401:
        return "auth"
    if http_status == 403:
        return "permission"
    return "upstream"


def classify(kind: str, body: Any, http_status: int) -> Dict[str, str]:
    result = {
        "state": "failure",
        "category": "response",
        "http_status": str(http_status),
        "code": "-",
        "error_type": "-",
        "trace_id": "-",
        "message": "-",
        "empty": "false",
        "missing_optional": "-",
    }
    if not isinstance(body, dict):
        result["message"] = "response is not a JSON object"
        return result

    result.update(
        code=_safe(body.get("code")),
        error_type=_safe(body.get("errorType")),
        trace_id=_safe(body.get("traceId")),
        message=_safe(body.get("msg") or body.get("message")),
    )

    if kind == "auth":
        success = (
            http_status == 200
            and body.get("code") == "000000"
            and body.get("status") is True
        )
    else:
        success = (
            http_status == 200
            and body.get("code") in (200, "200", "000000")
            and body.get("status") is not False
        )
    if not success:
        result["category"] = _failure_category(body, http_status)
        return result

    data = body.get("data")
    if kind == "auth":
        if not isinstance(data, dict):
            result["message"] = "successful auth response has no data object"
            return result
        token = data.get("accessToken")
        if not isinstance(token, str) or not token.strip():
            result["message"] = "successful auth response has no accessToken"
            return result
        missing = [key for key in ("uid", "tenantId", "productCode") if data.get(key) in (None, "")]
        result["missing_optional"] = ",".join(missing) or "-"
    else:
        if not isinstance(data, list):
            result["message"] = "successful RAG response has no data list"
            return result
        result["empty"] = "true" if not data else "false"

    result["state"] = "success"
    result["category"] = "success"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("auth", "rag"))
    parser.add_argument("--http-status", type=int, required=True)
    args = parser.parse_args()
    try:
        body = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        body = None
    result = classify(args.kind, body, args.http_status)
    keys = (
        "state",
        "category",
        "http_status",
        "code",
        "error_type",
        "trace_id",
        "message",
        "empty",
        "missing_optional",
    )
    print("\t".join(result[key] for key in keys))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
