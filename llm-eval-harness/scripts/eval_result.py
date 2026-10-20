#!/usr/bin/env python3
"""Versioned, credential-free machine receipts for the four evaluation probes.

The writer and reader share evidence predicates and derived terminal decisions.
Callers must bind a fresh run ID, exact invocation digest and actual child exit.
"""
from __future__ import annotations

import copy
import asyncio
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import uuid

RESULT_API_VERSION = 1
SCHEMA_VERSION = 1
PROBES = {"speed", "protocol", "concurrency", "quality"}
KINDS = {"speed": {"speed_mixed", "speed_decode", "speed_setup"},
         "protocol": {"protocol_generation", "protocol_history"},
         "concurrency": {"concurrency_request"}, "quality": {"quality_case"}}


class ResultContractError(ValueError):
    """An absent, stale, contradictory or unsupported receipt is not success."""


def _invocation_args(argv):
    kept = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--result-json", "--run-id"):
            if i + 1 >= len(argv):
                raise ResultContractError(f"missing value for {arg}")
            i += 2
            continue
        if arg.startswith(("--result-json=", "--run-id=")):
            i += 1
            continue
        kept.append(arg)
        i += 1
    return kept


def invocation_digest(argv):
    """Hash actual probe arguments, excluding only the two receipt arguments."""
    return hashlib.sha256(json.dumps(_invocation_args(argv), ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _validate_plan(probe, units, argv):
    """Bind the recorded occurrences to actual requested modes/counts/input files."""
    parser = argparse.ArgumentParser(add_help=False, exit_on_error=False)
    parser.add_argument("--mode", default="both")
    parser.add_argument("--repeat", type=int, default=3 if probe == "speed" else 10)
    parser.add_argument("--check", default="all")
    parser.add_argument("--concurrency", type=int, nargs="+", default=[10])
    parser.add_argument("--prompts-file")
    parser.add_argument("--usecases")
    try:
        if not isinstance(units, list) or not all(isinstance(u, dict) for u in units):
            raise ResultContractError("invalid unit plan")
        args, _ = parser.parse_known_args(argv)
        expected = []
        if probe == "speed":
            expected.append(("setup", "speed_setup", 0, False))
            if args.mode in ("mixed", "both"):
                prompts = json.loads(Path(args.prompts_file).read_text()) if args.prompts_file else [None] * 3
                expected += [(f"mixed:{i}", "speed_mixed", i, True) for i in range(len(prompts))]
            if args.mode in ("decode", "both"):
                expected += [(f"decode:{i}", "speed_decode", i, True) for i in range(1, args.repeat + 1)]
        elif probe == "protocol":
            if args.check in ("generation", "all"):
                expected += [(f"generation:{i}", "protocol_generation", i, True) for i in range(1, args.repeat + 1)]
            if args.check in ("history-replay", "all"):
                expected += [(f"history:{i}", "protocol_history", i, True) for i in range(1, args.repeat + 1)]
        elif probe == "concurrency":
            expected += [(f"level:{level}:request:{i}", "concurrency_request", i, True)
                         for level, c in enumerate(args.concurrency) for i in range(1, c + 1)]
        else:
            cases = json.loads(Path(args.usecases).expanduser().read_text())
            expected += [(f"case:{i}", "quality_case", i, True) for i in range(len(cases))]
        actual = [(u.get("unit_id"), u.get("kind"), u.get("ordinal"), u.get("required")) for u in units]
        if not any(x[3] for x in expected) or actual != expected:
            raise ResultContractError("recorded unit plan differs from requested invocation")
    except (OSError, ValueError, TypeError, argparse.ArgumentError) as exc:
        raise ResultContractError(f"cannot bind requested plan: {type(exc).__name__}") from exc


def add_result_arguments(parser):
    parser.add_argument("--result-json", help="fresh machine receipt path (requires --run-id)")
    parser.add_argument("--run-id", help="caller-generated UUID (requires --result-json)")


def auth_headers(fmt, key, auth=None):
    """Resolve wire authentication without exposing the key in the receipt."""
    if fmt not in {"openai", "anthropic"}:
        raise ValueError("unsupported wire format")
    auth = auth or ("bearer" if fmt == "openai" else "x-api-key")
    if auth not in ("bearer", "x-api-key") or (fmt == "openai" and auth != "bearer"):
        raise ValueError("OpenAI requires bearer; Anthropic supports x-api-key or bearer")
    out = {"Content-Type": "application/json"}
    out["Authorization" if auth == "bearer" else "x-api-key"] = f"Bearer {key}" if auth == "bearer" else key
    if fmt == "anthropic":
        out["anthropic-version"] = "2023-06-01"
    return out


def unit(unit_id, kind, ordinal, *, required=True, **parameters):
    return {"unit_id": unit_id, "kind": kind, "ordinal": ordinal, "required": required,
            "parameters": parameters, "state": "pending", "usable": False, "data": None, "error": None}


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _integer(value):
    return type(value) is int and value >= 0


SPEED_METRICS = {
    "ttft_first_s": ("number", True), "ttft_content_s": ("number", True),
    "total_s": ("number", False), "decode_s": ("number", False),
    "output_tokens": ("integer", False), "reasoning_tokens": ("integer", True),
    "reasoning_chars": ("integer", False), "content_chars": ("integer", False),
    "chunks": ("integer", False), "tokens_per_chunk": ("number", True),
    "client_decode_tps": ("number", True), "server_decode_tps": ("number", True),
    "server_mean_accept_length": ("number", True), "decode_tps": ("number", True),
    "e2e_tps": ("number", True),
}
CONCURRENCY_METRICS = {
    "index": ("integer", False), "status": ("integer", False),
    "start": ("number", False), "end": ("number", False), "duration": ("number", False),
}
QUALITY_METRICS = {"answer_chars": ("integer", False), "reasoning_chars": ("integer", False)}


def _validate_metrics(kind, data, *, partial=False):
    """Validate only metric fields owned by this unit type, including partial data."""
    if kind in {"speed_mixed", "speed_decode"}:
        schema = SPEED_METRICS
    elif kind == "concurrency_request":
        schema = CONCURRENCY_METRICS
    elif kind == "quality_case":
        schema = QUALITY_METRICS
    elif kind == "protocol_history":
        schema = {"http_status": ("integer", True)}
    else:
        schema = {}
    for field, (value_type, nullable) in schema.items():
        if partial and field not in data:
            continue
        if field not in data:
            raise ResultContractError(f"missing {kind} metric {field}")
        value = data[field]
        if value is None and nullable:
            continue
        valid = _integer(value) if value_type == "integer" else _number(value)
        if not valid or (field in {"status", "http_status"} and value > 599):
            raise ResultContractError(f"invalid {kind} metric {field}")


def thinking_rejection(text):
    low = (text or "").lower()
    # A fabricated/rejected signature says nothing about acceptance of the block TYPE.
    if "thinking" not in low or "signature" in low:
        return False
    return any(re.search(pattern, low) for pattern in (
        r"\b(?:invalid|unsupported|unknown|unrecognized)\s+(?:(?:part|content|block)\s+)*type\b[^\n]{0,80}\bthinking\b",
        r"\bthinking\s+(?:(?:content|part)\s+)?(?:block(?:\s+type)?|type)s?\b[^\n]{0,40}\b(?:unsupported|not supported|not allowed)\b",
        r"\b(?:unsupported|not supported|not allowed)\b[^\n]{0,40}\bthinking\s+blocks?\b",
        r"\b(?:does not support|do not support|cannot accept|can't accept)\b[^\n]{0,40}\bthinking\s+blocks?\b",
    ))


def history_rejection(data):
    return data.get("http_status") in {200, 400, 422} and thinking_rejection(data.get("error_text"))


def _evidence(kind, data):
    if not isinstance(data, dict):
        return False
    if kind == "speed_setup":
        return type(data.get("usage_supported")) is bool
    if kind.startswith("speed_"):
        return (data.get("stream_complete") is True and _number(data.get("total_s"))
                and isinstance(data.get("finish_reason"), str) and bool(data["finish_reason"].strip())
                and _number(data.get("ttft_first_s"))
                and data["total_s"] >= data["ttft_first_s"]
                and _number(data.get("output_tokens")) and data["output_tokens"] > 0
                and _integer(data.get("content_chars")) and _integer(data.get("reasoning_chars"))
                and data["content_chars"] + data["reasoning_chars"] > 0)
    if kind == "protocol_generation":
        return (data.get("transport_ok") is True and data.get("http_2xx") is True and data.get("message_stop") is True
                and not data.get("error") and (data.get("text") is True or data.get("thinking_delta") is True))
    if kind == "protocol_history":
        rejected = data.get("accepted") is False and history_rejection(data)
        return bool(rejected or (data.get("accepted") is True and data.get("message_stop") is True
                                and type(data.get("http_status")) is int and 200 <= data["http_status"] < 300
                                and not data.get("error_text")))
    if kind == "concurrency_request":
        return (_integer(data.get("status")) and data["status"] <= 599
                and all(_number(data.get(k)) for k in ("start", "end", "duration"))
                and data["end"] >= data["start"])
    if kind == "quality_case":
        return _integer(data.get("answer_chars")) and data["answer_chars"] > 0
    return False


def _validate_data(kind, data):
    if not isinstance(data, dict):
        raise ResultContractError("observed unit requires typed data")
    _validate_metrics(kind, data)
    def booleans(keys):
        return all(type(data.get(k)) is bool for k in keys)
    if kind == "speed_setup":
        ok = booleans(["usage_supported"])
    elif kind.startswith("speed_"):
        ok = ({"stream_complete", "finish_reason", "content_chars", "reasoning_chars", "ttft_first_s", "total_s", "output_tokens"} <= set(data)
              and (data["finish_reason"] is None or isinstance(data["finish_reason"], str))
              and booleans(["stream_complete"]) and all(_integer(data.get(k)) for k in ("content_chars", "reasoning_chars"))
              and all(data.get(k) is None or _number(data[k]) for k in ("ttft_first_s", "total_s", "output_tokens")))
    elif kind == "protocol_generation":
        ok = ("error" in data and (data["error"] is None or isinstance(data["error"], str))
              and booleans(["transport_ok", "http_2xx", "thinking_delta", "signature_delta", "text", "message_stop"]))
    elif kind == "protocol_history":
        ok = {"accepted", "answered_followup", "rejects_thinking_type", "message_stop", "http_status", "error_text"} <= set(data)
        ok = ok and (data.get("accepted") is None or type(data["accepted"]) is bool)
        ok = ok and booleans(["answered_followup", "rejects_thinking_type", "message_stop"])
        ok = ok and (data.get("http_status") is None or _integer(data["http_status"]))
        ok = ok and (data.get("error_text") is None or isinstance(data["error_text"], str))
        ok = ok and data["rejects_thinking_type"] == history_rejection(data)
    elif kind == "concurrency_request":
        ok = _evidence(kind, data)
    else:
        artifact = data.get("artifact")
        ok = (_integer(data.get("answer_chars")) and _integer(data.get("reasoning_chars"))
              and isinstance(artifact, str) and bool(artifact) and Path(artifact).name == artifact
              and artifact not in {".", "..", "_all_answers.json"})
    if not ok:
        raise ResultContractError(f"malformed {kind} observation")


def _summary(probe, units):
    observed = [u for u in units if u["required"] and u["usable"]]
    out = {"usable_units": len(observed)}
    if probe in {"protocol", "concurrency"}:
        out["noncompliant_units"] = [u["unit_id"] for u in observed if not _compliant(u)]
    if probe == "speed":
        out["output_tokens"] = sum(u["data"]["output_tokens"] for u in observed)
    elif probe == "quality":
        out["answer_chars"] = sum(u["data"]["answer_chars"] for u in observed)
    elif probe == "concurrency":
        out["http_200"] = sum(u["data"]["status"] == 200 for u in observed)
    else:
        out["thinking_samples"] = sum(u["kind"] == "protocol_generation" and u["data"]["thinking_delta"] for u in observed)
        out["history_followups"] = sum(u["kind"] == "protocol_history" and u["data"]["answered_followup"] for u in observed)
    return out


def _compliant(u):
    d = u["data"]
    if u["kind"] == "protocol_generation":
        return d.get("thinking_delta") is True
    if u["kind"] == "protocol_history":
        return d.get("accepted") is True and d.get("answered_followup") is True
    if u["kind"] == "concurrency_request":
        return d["status"] == 200
    return True


def _check_json(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ResultContractError("nonfinite JSON number")
    if isinstance(value, dict):
        for v in value.values():
            _check_json(v)
    elif isinstance(value, list):
        for v in value:
            _check_json(v)


def _derive(result, *, terminal=True):
    probe = result.get("probe")
    if probe not in PROBES or not isinstance(result.get("units"), list):
        raise ResultContractError("invalid probe or units")
    ids = set()
    artifacts = set()
    for u in result["units"]:
        if not isinstance(u, dict) or not isinstance(u.get("unit_id"), str) or not u["unit_id"] or u["unit_id"] in ids:
            raise ResultContractError("missing/duplicate unit identity")
        ids.add(u["unit_id"])
        if not {"unit_id", "kind", "ordinal", "required", "parameters", "state", "usable", "data", "error"} <= set(u):
            raise ResultContractError("unit is missing required fields")
        if (u.get("kind") not in KINDS[probe] or not _integer(u.get("ordinal"))
                or type(u.get("required")) is not bool or type(u.get("usable")) is not bool
                or not isinstance(u.get("parameters"), dict)):
            raise ResultContractError("invalid typed unit")
        state = u.get("state")
        if state not in {"pending", "running", "observed", "error", "skipped"}:
            raise ResultContractError("invalid unit state")
        if state == "observed":
            _validate_data(u["kind"], u.get("data"))
            if u["kind"] == "concurrency_request" and u["data"]["index"] != u["ordinal"]:
                raise ResultContractError("concurrency result index differs from its planned ordinal")
        elif state == "error" and u.get("data") is not None:
            if not isinstance(u["data"], dict):
                raise ResultContractError("partial unit evidence must be an object")
            _validate_metrics(u["kind"], u["data"], partial=True)
        usable = state == "observed" and _evidence(u["kind"], u.get("data"))
        if u["usable"] != usable:
            raise ResultContractError("claimed usable evidence disagrees with typed data")
        if u["kind"] == "quality_case" and usable:
            artifact = u["data"]["artifact"].casefold()
            if artifact in artifacts:
                raise ResultContractError("usable quality units share an answer artifact")
            artifacts.add(artifact)
        if state == "error":
            if not isinstance(u.get("error"), dict) or not all(isinstance(u["error"].get(k), str) for k in ("code", "type", "message")):
                raise ResultContractError("missing unit error")
        elif u.get("error") is not None:
            raise ResultContractError("unexpected unit error")
        if state in {"pending", "running", "skipped"} and u.get("data") is not None:
            raise ResultContractError("unfinished unit carries a completed observation")
    primary = [u for u in result["units"] if u["required"]]
    counts = {"planned": len(primary),
              "attempted": sum(u["state"] in {"running", "observed", "error"} for u in primary),
              "finished": sum(u["state"] in {"observed", "error"} for u in primary),
              "usable": sum(u["usable"] for u in primary),
              "errors": sum(u["state"] == "error" for u in primary),
              "skipped": sum(u["state"] == "skipped" for u in primary)}
    error = result.get("error")
    if error is not None:
        if not isinstance(error, dict) or not all(isinstance(error.get(k), str) for k in ("code", "type", "message")):
            raise ResultContractError("invalid run error")
        state = "cancelled" if error["code"] == "CANCELLED" else "execution_error"
    elif not terminal:
        state = "running"
    elif not primary:
        raise ResultContractError("empty primary plan cannot complete")
    elif counts["usable"] == 0:
        state = "no_measurement"
    elif counts["usable"] != len(primary) or counts["finished"] != len(primary):
        state = "partial"
    else:
        state = "completed"
    verdict = "inconclusive"
    if state == "completed":
        verdict = {"speed": "observed", "quality": "not_judged"}.get(probe, "compliant")
        if probe in {"protocol", "concurrency"} and not all(_compliant(u) for u in primary):
            verdict = "noncompliant"
    code = {"running": None, "partial": 11, "no_measurement": 12,
            "execution_error": 2, "cancelled": 130}.get(state)
    if state == "completed":
        code = 10 if verdict == "noncompliant" else 0
    return counts, state, verdict, code


def read_result(path, *, expected_run_id, expected_probe, expected_invocation_sha256, child_returncode,
                expected_identity=None):
    """Return the validated dict; every disagreement raises ResultContractError."""
    try:
        result = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ResultContractError(f"result unavailable: {type(exc).__name__}") from exc
    if not isinstance(result, dict) or type(result.get("schema_version")) is not int or result["schema_version"] != SCHEMA_VERSION:
        raise ResultContractError("unsupported result schema")
    if not {"schema_version", "run_id", "probe", "invocation_sha256", "invocation", "identity", "state", "verdict", "counts", "units", "summary", "error"} <= set(result):
        raise ResultContractError("result is missing required fields")
    _check_json(result)
    for k, expected in (("run_id", expected_run_id), ("probe", expected_probe), ("invocation_sha256", expected_invocation_sha256)):
        if not expected or result.get(k) != expected:
            raise ResultContractError(f"result {k} mismatch")
    if (not isinstance(result.get("invocation"), list) or not all(isinstance(x, str) for x in result["invocation"])
            or invocation_digest(result["invocation"]) != expected_invocation_sha256):
        raise ResultContractError("recorded invocation mismatch")
    _validate_plan(result["probe"], result.get("units", []), result["invocation"])
    identity = result.get("identity")
    if (not isinstance(identity, dict) or set(identity) != {"model", "endpoint_kind", "endpoint", "format", "auth"}
            or not all(isinstance(identity.get(k), str) and identity[k] for k in ("model", "endpoint", "format", "auth"))
            or identity.get("endpoint_kind") != ("base_url" if expected_probe in {"speed", "quality"} else "request_url")
            or identity.get("format") not in {"openai", "anthropic"}
            or identity.get("auth") not in {"x-api-key", "bearer"}
            or (identity.get("format") == "openai" and identity.get("auth") != "bearer")):
        raise ResultContractError("invalid result identity")
    if expected_identity is not None and identity != expected_identity:
        raise ResultContractError("result identity mismatch")
    counts, state, verdict, code = _derive(result, terminal=result.get("state") != "running")
    if (result.get("counts") != counts or not isinstance(result.get("counts"), dict)
            or any(type(v) is not int for v in result["counts"].values())
            or result.get("state") != state or result.get("verdict") != verdict):
        raise ResultContractError("result terminal fields/counters contradict units")
    if state == "running" or type(child_returncode) is not int or child_returncode != code:
        raise ResultContractError("child exit does not match a terminal receipt")
    expected_summary = _summary(result["probe"], result["units"])
    summary = result.get("summary")
    if (not isinstance(summary, dict) or summary.keys() != expected_summary.keys()
            or any(type(summary[k]) is not type(v) or summary[k] != v for k, v in expected_summary.items())):
        raise ResultContractError("summary contradicts typed evidence")
    return result


class ResultWriter:
    def __init__(self, path, run_id, probe, invocation_argv, identity, plan):
        if bool(path) != bool(run_id):
            raise ResultContractError("--result-json and --run-id must be supplied together")
        if run_id:
            try:
                uuid.UUID(run_id)
            except (ValueError, AttributeError) as exc:
                raise ResultContractError("--run-id must be a UUID") from exc
        self.path = Path(path) if path else None
        self.secrets = []
        self.result = {"schema_version": SCHEMA_VERSION, "run_id": run_id or str(uuid.uuid4()),
                       "probe": probe, "invocation_sha256": invocation_digest(invocation_argv),
                       "invocation": _invocation_args(invocation_argv),
                       "identity": identity, "units": copy.deepcopy(plan), "summary": {}, "error": None}
        if not any(u.get("required") for u in plan):
            raise ResultContractError("evaluation requires at least one primary unit")
        _validate_plan(probe, plan, self.result["invocation"])
        _derive(self.result, terminal=False)
        if self.path:
            # Refuse stale files/symlinks atomically; later writes replace only our reserved file.
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
        self._save(False)

    def redact(self, secret):
        if secret:
            self.secrets.append(secret)

    def error_record(self, exc, code="ERROR"):
        message = str(exc)
        for secret in self.secrets:
            message = message.replace(secret, "<redacted>")
        return {"code": code, "type": type(exc).__name__, "message": message[:500]}

    def _unit(self, unit_id):
        return next(u for u in self.result["units"] if u["unit_id"] == unit_id)

    def start_unit(self, unit_id):
        u = self._unit(unit_id)
        if u["state"] != "pending":
            raise ResultContractError("unit may only start once")
        u["state"] = "running"
        self._save(False)

    def finish_unit(self, unit_id, data):
        u = self._unit(unit_id)
        if u["state"] != "running":
            raise ResultContractError("observation requires a running unit")
        data = self._safe_data(data)
        u.update(state="observed", data=data, usable=_evidence(u["kind"], data))
        self._save(False)

    def fail_unit(self, unit_id, exc, *, data=None):
        u = self._unit(unit_id)
        if u["state"] != "running":
            raise ResultContractError("unit failure requires a running unit")
        u.update(state="error", data=self._safe_data(data), usable=False, error=self.error_record(exc))
        self._save(False)

    def skip_unit(self, unit_id):
        u = self._unit(unit_id)
        if u["state"] != "pending":
            raise ResultContractError("only a pending unit can be skipped")
        u["state"] = "skipped"
        self._save(False)

    def _safe_data(self, value):
        if isinstance(value, str):
            for secret in self.secrets:
                value = value.replace(secret, "<redacted>")
        elif isinstance(value, dict):
            value = {k: self._safe_data(v) for k, v in value.items()}
        elif isinstance(value, list):
            value = [self._safe_data(v) for v in value]
        return value

    def _save(self, terminal):
        counts, state, verdict, code = _derive(self.result, terminal=terminal)
        self.result.update(counts=counts, state=state, verdict=verdict)
        self.result["summary"] = _summary(self.result["probe"], self.result["units"])
        _check_json(self.result)
        if self.path:
            fd, tmp = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self.result, f, ensure_ascii=False, allow_nan=False, indent=2)
                    f.write("\n")
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, self.path)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
        return code

    def finish(self):
        return self._save(True)

    def abort(self, exc, *, cancelled=False):
        for u in self.result["units"]:
            if u["state"] == "running":
                u.update(state="error", usable=False, data=self._safe_data(getattr(exc, "partial_result", None)),
                         error=self.error_record(exc, "CANCELLED" if cancelled else "ERROR"))
        self.result["error"] = self.error_record(exc, "CANCELLED" if cancelled else "EXECUTION_ERROR")
        return self._save(True)


def execute_probe(args, probe, identity, plan, callback, *, argv=None):
    """Execute one acquisition lifecycle; callback returns its legacy exit code."""
    writer = None
    try:
        writer = ResultWriter(args.result_json, args.run_id, probe,
                              sys.argv[1:] if argv is None else argv, identity, plan)
        legacy_exit = callback(writer) or 0
        code = writer.finish()
        return code if args.result_json else legacy_exit
    except (KeyboardInterrupt, asyncio.CancelledError) as exc:
        if writer:
            writer.abort(exc, cancelled=True)
        return 130
    except Exception as exc:
        record = writer.error_record(exc) if writer else {"message": str(exc)[:500]}
        print(f"ERROR {type(exc).__name__}: {record['message']}", file=sys.stderr)
        if writer:
            try:
                writer.abort(exc)
            except Exception:
                pass  # The caller sees nonzero + missing/unfinalized receipt, never success.
        return 2


def cli_main(main):
    """Normalize preflight failures that occur before a writer can be initialized."""
    try:
        return main()
    except (KeyboardInterrupt, asyncio.CancelledError):
        return 130
    except Exception as exc:
        print(f"ERROR {type(exc).__name__}: {str(exc)[:500]}", file=sys.stderr)
        return 2
