#!/usr/bin/env python3
"""Read one explicitly selected Codex account without changing its login state.

Run with Python 3.10+ (standard library only). Tokens stay in memory and are
sent only to the fixed official usage endpoint. No refresh or redemption occurs.
"""

import argparse
import base64
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import re
import time
from datetime import datetime, timezone
import urllib.error
import urllib.request


USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"


class UsageError(Exception):
    """A public error message which never contains credential values."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise UsageError("redirect_refused: open the official Usage page instead")


def nonnegative_int(value):
    return value if type(value) is int and value >= 0 else None


def normalize_usage(data, expected_account_id, expected_email=None):
    if not isinstance(data, dict):
        raise UsageError("invalid_response: expected a JSON object")
    if data.get("account_id") != expected_account_id:
        raise UsageError("identity_mismatch: response belongs to another account")
    email = data.get("email")
    if not isinstance(email, str) or not email:
        raise UsageError("identity_unknown: response has no account email")
    if expected_email and email.casefold() != expected_email.casefold():
        raise UsageError("identity_mismatch: expected email does not match")

    notes = []
    windows = []
    seen_durations = set()
    duplicate_durations = set()
    rate_limit = data.get("rate_limit")
    rate_limit = rate_limit if isinstance(rate_limit, dict) else {}
    for slot in ("primary_window", "secondary_window"):
        window = rate_limit.get(slot)
        if window is None:
            continue
        if not isinstance(window, dict):
            notes.append(f"{slot}: unknown window shape")
            continue
        seconds = nonnegative_int(window.get("limit_window_seconds"))
        if seconds not in (604800, 18000):
            notes.append(f"{slot}: unrecognized window duration; quota unknown")
            continue
        if seconds in seen_durations:
            duplicate_durations.add(seconds)
            notes.append(f"duplicate {seconds}-second windows; quota unknown")
        seen_durations.add(seconds)
        used = window.get("used_percent")
        if (not seconds or type(used) not in (int, float)
                or not math.isfinite(used) or not 0 <= used <= 100):
            notes.append(f"{slot}: invalid duration or percentage")
            continue
        reset_at = nonnegative_int(window.get("reset_at"))
        reset_utc = None
        if reset_at is not None:
            try:
                reset_utc = datetime.fromtimestamp(reset_at, timezone.utc).isoformat()
            except (ValueError, OverflowError, OSError):
                notes.append(f"{slot}: invalid reset timestamp")
        else:
            notes.append(f"{slot}: reset timestamp unknown")
        windows.append({
            "window_seconds": seconds,
            "used_percent": used,
            "remaining_percent": 100 - used,
            "reset_at_utc": reset_utc,
        })

    windows = [w for w in windows if w["window_seconds"] not in duplicate_durations]

    banked = data.get("rate_limit_reset_credits")
    banked = banked if isinstance(banked, dict) else {}
    available = nonnegative_int(banked.get("available_count"))
    applicable = nonnegative_int(banked.get("applicable_available_count"))
    if available is None:
        notes.append("banked reset count unknown; inspect Usage limit resets on web")
    if applicable is None:
        notes.append("currently applicable reset count unknown")
    if not windows:
        notes.append("quota windows unknown; an empty result does not mean full quota")
    credits = data.get("credits")
    credits = credits if isinstance(credits, dict) else {}
    return {
        "status": "partial" if notes else "ok",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": USAGE_URL,
        "email": email,
        # Pseudonymous handle for journals: findings must not hold emails, but
        # banked counts are only comparable between reads of the same account.
        # Unsalted and short, so a known email can be matched to it: a pseudonym,
        # not anonymization.
        "account_ref": hashlib.sha256(email.casefold().encode()).hexdigest()[:8],
        "plan_type": data.get("plan_type"),
        "windows": windows,
        "banked_resets_available": available,
        "banked_resets_applicable_now": applicable,
        "purchased_credits_balance": credits.get("balance"),
        "notes": notes,
    }


def read_auth(path):
    try:
        auth = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise UsageError("auth_unavailable: cannot read the selected auth JSON") from None
    if not isinstance(auth, dict) or auth.get("auth_mode") != "chatgpt":
        raise UsageError("unsupported_auth: select a ChatGPT login, not an API key")
    tokens = auth.get("tokens")
    if not isinstance(tokens, dict):
        raise UsageError("auth_incomplete: missing tokens object")
    if any(not isinstance(tokens.get(k), str) or not tokens[k]
           for k in ("access_token", "account_id")):
        raise UsageError("auth_incomplete: missing access token or account identity")
    # Claims are only a local cross-check, not a replacement for server identity.
    email = None
    try:
        payload = tokens["id_token"].split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        email = claims.get("email")
    except (KeyError, IndexError, ValueError, TypeError, AttributeError):
        pass
    return tokens, email if isinstance(email, str) else None


def query(path, expected_email=None):
    tokens, login_email = read_auth(path)
    if expected_email and login_email and expected_email.casefold() != login_email.casefold():
        raise UsageError("identity_mismatch: selected auth file is not the requested account")
    request = urllib.request.Request(USAGE_URL, headers={
        "Authorization": "Bearer " + tokens["access_token"],
        "ChatGPT-Account-Id": tokens["account_id"],
        "User-Agent": "codex-cli",
        "Accept": "application/json",
    }, method="GET")
    opener = urllib.request.build_opener(NoRedirect())
    for attempt in range(3):
        try:
            with opener.open(request, timeout=15) as response:
                data = json.load(response)
            return normalize_usage(data, tokens["account_id"], expected_email or login_email)
        except urllib.error.HTTPError as error:
            if error.code in (401, 403):
                raise UsageError(f"authentication_failed: HTTP {error.code}; use browser login; quota unknown") from None
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise UsageError(f"usage_unavailable: HTTP {error.code}; quota unknown") from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            if attempt == 2:
                raise UsageError("usage_unavailable: network or JSON failure after 3 attempts") from None
        time.sleep(1)
    raise UsageError("usage_unavailable")


def private_reading(result):
    """Allowlist non-sensitive normalized readings; never serialize the response wholesale."""
    reading = {key: result[key] for key in (
        "status", "checked_at_utc", "source", "account_ref", "windows",
        "banked_resets_available", "banked_resets_applicable_now", "notes")}
    plan = result.get("plan_type")
    reading["plan_type"] = plan if plan in (
        "free", "plus", "pro", "team", "business", "enterprise", "edu") else None
    balance = result.get("purchased_credits_balance")
    reading["purchased_credits_balance"] = balance if (
        (type(balance) in (int, float) and math.isfinite(balance) and balance >= 0)
        or (isinstance(balance, str) and re.fullmatch(r"\d+(?:\.\d+)?", balance))) else None
    return reading


def validate_output_dir(path):
    if not path.is_absolute() or not path.parent.is_dir():
        raise UsageError("output_invalid: use an absolute new directory with an existing parent")
    if path.exists() or path.is_symlink():
        raise UsageError("output_exists: refusing to overwrite an existing path")


def save_usage(result, output_dir, finding_state_dir=None, *, git_snapshot=True):
    """Persist this exact query once, optionally appending via the existing finding owner."""
    validate_output_dir(output_dir)
    reading = private_reading(result)
    output_dir.mkdir(mode=0o700)
    path = output_dir / "usage.json"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(reading, ensure_ascii=False, allow_nan=False, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    receipt = {"status": result["status"], "checked_at_utc": reading["checked_at_utc"],
               "account_ref": reading["account_ref"], "usage_file": str(path), "saved": True}
    if finding_state_dir is not None:
        spec = importlib.util.spec_from_file_location("tibo_forecast_log", Path(__file__).with_name("forecast_log.py"))
        log = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(log)
        target = finding_state_dir / "findings.jsonl"
        row = log.append_finding(target, {"invocation": "account",
            "query": "Read the explicitly selected Codex account's current usage and banked resets",
            "endpoints": [USAGE_URL], "readings": {"query_usage": reading}})
        snap = log.snapshot(finding_state_dir, target.name, "finding", enabled=git_snapshot)
        receipt["finding"] = log.append_receipt(row, target, snap)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--auth-file", type=Path,
                        default=Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "auth.json",
                        help="Explicit ChatGPT auth file; defaults to CODEX_HOME/auth.json or ~/.codex/auth.json")
    parser.add_argument("--expected-email", help="Refuse to report a different account")
    parser.add_argument("--output-dir", type=Path,
                        help="Save email-free usage.json in this absolute NEW private directory; stdout becomes a receipt")
    parser.add_argument("--finding-state-dir", type=Path,
                        help="Also append this same reading to the explicit local finding journal; requires --output-dir")
    parser.add_argument("--no-git", action="store_true", help="Skip the optional finding journal's git snapshot")
    args = parser.parse_args()
    try:
        if args.finding_state_dir is not None and args.output_dir is None:
            raise UsageError("output_required: --finding-state-dir requires --output-dir")
        if args.finding_state_dir is not None and not args.finding_state_dir.is_absolute():
            raise UsageError("state_invalid: --finding-state-dir must be absolute")
        if args.output_dir is not None:
            validate_output_dir(args.output_dir)
        result = query(args.auth_file.expanduser(), args.expected_email)
        output = save_usage(result, args.output_dir, args.finding_state_dir,
                            git_snapshot=not args.no_git) if args.output_dir is not None else result
    except (UsageError, OSError, ValueError, KeyError, TypeError) as error:
        # OS exception text can contain private paths; keep the failure public and
        # preserve a successfully written usage file for independent recovery.
        message = str(error) if isinstance(error, UsageError) else "persistence_failed: " + type(error).__name__
        failure = {"status": "error", "error": message}
        if args.output_dir is not None and (args.output_dir / "usage.json").is_file():
            failure["usage_file"] = str(args.output_dir / "usage.json")
        print(json.dumps(failure, ensure_ascii=False))
        return 1
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
