#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""List dated Feishu recording candidates through explicitly supplied profiles.

No profile discovery, title filtering, transcript reads or archive writes.
Without explicit full-result intent, read at most 50 items across profiles in
argument order. --all-pages permits concurrent full pagination. Exit 0 means
every requested profile finished pagination, 1 means incomplete coverage, and
2 means invalid command-line input.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import json
import math
import os
import re
import subprocess
from typing import Callable


REFRESH_NOTICE = "[lark-cli] uat-client: token already refreshed by another process"


class PageError(Exception):
    pass


def cli_command(profile: str, start: str, end: str, page_token: str | None,
                page_size: int = 30) -> list[str]:
    command = [
        "lark-cli", "--profile", profile, "minutes", "+search",
        "--start", start, "--end", end, "--as", "user",
        "--page-size", str(page_size), "--format", "json",
    ]
    if page_token is not None:
        command.extend(["--page-token", page_token])
    return command


def query_profile(profile: str, start: str, end: str, *, runner: Callable,
                  timeout: float, max_items: int | None = None) -> dict:
    rows: list[dict] = []
    pages_read = 0
    items_received = 0
    page_token = None
    seen_tokens: set[str] = set()
    stage = "launch"
    env = os.environ.copy()
    env.update({
        "LARK_CLI_NO_PROXY": "1",
        "LARKSUITE_CLI_NO_UPDATE_NOTIFIER": "1",
        "LARKSUITE_CLI_NO_SKILLS_NOTIFIER": "1",
    })
    error = None
    notices: list[str] = []
    stop_reason = None
    try:
        while True:
            if max_items is not None and items_received >= max_items:
                stop_reason = "confirmation_required"
                break
            page_size = 30 if max_items is None else min(30, max_items - items_received)
            stage = "cli"
            response = runner(cli_command(profile, start, end, page_token, page_size),
                              capture_output=True, text=True, encoding="utf-8",
                              env=env, timeout=timeout, check=False)
            if response.returncode != 0:
                detail = (response.stderr or "").strip()[:400]
                raise PageError(f"CLI exit {response.returncode}" +
                                (f": {detail}" if detail else ""))
            stage = "response"
            lines = response.stdout.splitlines(keepends=True)
            # This exact leading notice is emitted by the CLI during normal
            # concurrent token refresh. Unknown output remains a parse error.
            while lines and lines[0].rstrip("\r\n") == REFRESH_NOTICE:
                notices.append(lines.pop(0).rstrip("\r\n"))
            payload = json.loads("".join(lines))
            if not isinstance(payload, dict) or payload.get("ok") is not True:
                raise PageError("response must be an object with ok=true")
            data = payload.get("data")
            if not isinstance(data, dict):
                raise PageError("data must be an object")
            batch = data.get("items")
            if not isinstance(batch, list):
                raise PageError("data.items must be an array (not missing/null)")
            pages_read += 1
            items_received += len(batch)
            invalid_items = []
            for index, item in enumerate(batch):
                if (not isinstance(item, dict) or
                        not isinstance(item.get("token"), str) or
                        not item["token"].strip()):
                    invalid_items.append(index)
                    continue
                metadata = item.get("meta_data")
                url = metadata.get("app_link") if isinstance(metadata, dict) else None
                if not isinstance(url, str) or not url.strip():
                    url = None
                display = item.get("display_info")
                rows.append({"token": item["token"], "profile": profile,
                             "url": url,
                             "display_info": display if isinstance(display, str) else None})
            if invalid_items:
                raise PageError(f"items with missing/invalid token at indexes {invalid_items}")
            stage = "pagination"
            more = data.get("has_more")
            if not isinstance(more, bool):
                raise PageError("data.has_more must be a boolean (not missing/null)")
            if not more:
                break
            next_token = data.get("page_token")
            if not isinstance(next_token, str) or not next_token.strip():
                raise PageError("has_more=true requires a nonblank page_token")
            if next_token in seen_tokens:
                raise PageError("pagination token repeated; coverage is incomplete")
            seen_tokens.add(next_token)
            page_token = next_token
    except Exception as exc:
        # Retain observed candidates from successful pages, including another
        # profile's results. A failed query is never converted to an empty one.
        error = {"stage": stage, "type": type(exc).__name__, "message": str(exc)[:600]}
    if stop_reason is not None:
        status = "partial" if pages_read else "not_queried"
    else:
        status = "complete" if error is None else ("partial" if pages_read else "error")
    return {"profile": profile, "status": status, "pages_read": pages_read,
            "items_received": items_received, "usable_items": len(rows),
            "error": error, "notices": notices, "stop_reason": stop_reason,
            "next_page_token": page_token if stop_reason is not None else None,
            "rows": rows}


def lookup(profiles: list[str], start: str, end: str, *, timeout: float = 60,
           runner: Callable | None = None, all_pages: bool = False) -> dict:
    """Query only these profiles; their ownership/authorization is the caller's job."""
    profiles = list(dict.fromkeys(profiles))
    if not profiles:
        raise ValueError("at least one explicitly authorized profile is required")
    runner = runner or subprocess.run
    if all_pages:
        with ThreadPoolExecutor(max_workers=min(4, len(profiles))) as pool:
            futures = [pool.submit(query_profile, p, start, end, runner=runner,
                                   timeout=timeout) for p in profiles]
            results = [future.result() for future in futures]
    else:
        # A shared, sequential budget keeps the guide's confirmation boundary
        # predictable across profiles. Raw items count even when deduplicated.
        results = []
        remaining = 50
        for profile in profiles:
            result = query_profile(profile, start, end, runner=runner,
                                   timeout=timeout, max_items=max(0, remaining))
            remaining -= result["items_received"]
            results.append(result)
    by_token: dict[str, dict] = {}
    for result in results:
        for row in result["rows"]:
            candidate = by_token.setdefault(row["token"],
                                            {"token": row["token"], "sources": []})
            source = {key: row[key] for key in ("profile", "url", "display_info")}
            if source not in candidate["sources"]:
                candidate["sources"].append(source)
    complete = all(r["status"] == "complete" for r in results)
    status = ("complete" if complete else
              "partial" if any(r["pages_read"] for r in results) else "error")
    coverage = [{k: v for k, v in r.items() if k != "rows"} for r in results]
    return {"schema": 1, "start": start, "end": end,
            "requested_profiles": profiles, "status": status, "complete": complete,
            "all_pages": all_pages,
            "needs_confirmation": any(r["stop_reason"] for r in results),
            "coverage": coverage, "candidates": list(by_token.values())}


def date_argument(value: str) -> str:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise argparse.ArgumentTypeError("use an explicit YYYY-MM-DD date")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return value


def profile_argument(value: str) -> str:
    if not value.strip() or any(ord(c) < 32 for c in value):
        raise argparse.ArgumentTypeError("profile must be nonblank with no control characters")
    return value


def timeout_argument(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timeout must be a positive finite number") from exc
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("timeout must be a positive finite number")
    return number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append", required=True,
                        type=profile_argument,
                        help="Exact already-authorized profile; repeat for multiple profiles.")
    parser.add_argument("--start", required=True, type=date_argument)
    parser.add_argument("--end", required=True, type=date_argument,
                        help="Inclusive date; use the same start/end for one day.")
    parser.add_argument("--all-pages", action="store_true",
                        help="Only when the user explicitly requested all results; bypass the 50-item confirmation boundary.")
    parser.add_argument("--timeout", type=timeout_argument, default=60,
                        help="Per-CLI-call timeout in seconds (default: 60).")
    args = parser.parse_args(argv)
    if args.start > args.end:
        parser.error("start must not be after end")
    result = lookup(args.profile, args.start, args.end, timeout=args.timeout,
                    all_pages=args.all_pages)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
