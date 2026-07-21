#!/usr/bin/env python3
"""Model availability probe — which model IDs on this endpoint actually work?

What it answers
---------------
"Of these model IDs, which can I actually call right now — and for the ones that
fail, is the ID wrong, the channel missing, or the upstream just wobbling?"
Essential when onboarding a new gateway/vendor, when writing a customer-facing
"supported models" list, or when a previously-working model starts erroring.

Verdicts (per model x format)
-----------------------------
- ``available``       HTTP 200 AND non-empty text content
- ``empty-content``   HTTP 200 but no text — usually NOT "model broken": reasoning
                      models spend the token budget on thinking first, so a small
                      ``max_tokens`` silently produces an empty reply. The probe
                      reports thinking size to make this diagnosis obvious.
- ``no-channel``      4xx "model not found / no available channel" — the ID has no
                      route here. This is only meaningful if the ID is REAL (see
                      the discipline below).
- ``upstream-error``  5xx / gateway "temporarily unavailable" — a route exists but
                      its upstream is failing right now; retry later before
                      concluding anything.
- ``auth-error``      401/403 — key problem, not a model problem.

Hard-won disciplines baked in
-----------------------------
- ``--max-tokens`` defaults to 8192, deliberately generous. A budget of a few
  dozen tokens turns every reasoning model into ``empty-content`` and gets
  misread as "unavailable" (a real customer-facing doc shipped exactly that
  false conclusion before this default existed).
- "My invented ID returned 404" is NOT evidence the vendor lacks a capability.
  Before writing any "unavailable" list, confirm each ID exists in the vendor's
  or the model developer's OFFICIAL docs (suffixes matter: dated variants,
  ``-preview``, tier names). This probe tests IDs; it cannot tell you whether an
  ID was ever real — that check is yours.
- The gateway's ``/v1/models`` listing is not a complete availability source:
  real gateways route models that the listing omits. Probe the IDs you care
  about directly; treat the listing as one input, never the verdict.
- A model's self-reported identity ("I am X, made by Y") is NOT evidence of
  what is actually served — training data makes models mis-identify themselves
  routinely. This probe never asks the model who it is.
- ``trust_env=False`` + a fresh connection per request: ambient proxies and
  keep-alive pinning otherwise contaminate what you measure (see
  references/evaluation_disciplines.md §4-5).
- **Capture and display are separate layers.** Every probe writes the COMPLETE
  request + response (status, ALL headers, full body — secrets masked) to
  ``--raw-dir`` before anything is truncated for display. Terminal output may
  shorten; the evidence files never do. Why this is load-bearing: a forensic
  conclusion once shipped off a hand-rolled curl whose pipeline had
  ``grep -v set-cookie | head -25`` baked in — the "evidence" was pre-filtered
  by its own collection command, and the missing headers were exactly the
  question. Filter the saved file at read time, never the capture at write time.
  Corollary: evidence collected for one question ("does the body match the
  keyword?") must not be reused to answer a different one ("are there ANY
  rate-limit headers?") — when the question changes, re-collect.

Key handling: passed by ENV VAR NAME (``--key-env``), never on the CLI.

Usage
-----
    uv run --with aiohttp python availability_probe.py \
        --base-url https://api.example.com --key-env MY_API_KEY \
        --models model-a model-b vendor/model-c \
        --format both --output /tmp/avail.json

    # IDs from a file (one per line, # comments allowed):
    uv run --with aiohttp python availability_probe.py \
        --base-url https://api.example.com --key-env MY_API_KEY \
        --models @models.txt --format openai

Exit codes: 0 = all probed IDs available; 1 = at least one ID not available;
2 = configuration error (missing key/env); 3 = transport-level failure only.
"""

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone

import aiohttp

# Generous by default: reasoning models spend budget on thinking BEFORE any text.
# Small budgets produce HTTP 200 + empty content, which reads as "broken model"
# but is actually a probe artifact. 8192 clears every mainstream thinking model.
DEFAULT_MAX_TOKENS = 8192

# One short, language-neutral task. Deterministic enough to yield text from any
# working chat model, cheap enough to sweep dozens of IDs.
PROBE_PROMPT = "Reply with one short sentence: what is 2+2?"

EXIT_OK, EXIT_UNAVAILABLE, EXIT_CONFIG, EXIT_TRANSPORT = 0, 1, 2, 3


def build_request(fmt: str, base_url: str, model: str, key: str, max_tokens: int):
    base = base_url.rstrip("/")
    # Bare-domain base URLs are common in vendor docs; both API styles live
    # under /v1. Appending here means callers can pass either form.
    if not base.endswith("/v1"):
        base += "/v1"
    if fmt == "anthropic":
        return (
            f"{base}/messages",
            {"content-type": "application/json", "anthropic-version": "2023-06-01",
             "x-api-key": key},
            {"model": model, "max_tokens": max_tokens,
             "messages": [{"role": "user", "content": PROBE_PROMPT}]},
        )
    return (
        f"{base}/chat/completions",
        {"content-type": "application/json", "Authorization": f"Bearer {key}"},
        {"model": model, "max_tokens": max_tokens,
         "messages": [{"role": "user", "content": PROBE_PROMPT}]},
    )


def _mask_secrets(headers: dict) -> dict:
    """Auth values never reach disk; keep a 4-char tail for key-identity checks."""
    masked = {}
    for k, v in headers.items():
        if k.lower() in ("authorization", "x-api-key"):
            masked[k] = f"***{v[-4:]}" if len(v) > 12 else "***"
        else:
            masked[k] = v
    return masked


def _dump_raw(raw_dir, model, fmt, record) -> str | None:
    """Write one probe's complete evidence file; returns its path (or None)."""
    if not raw_dir:
        return None
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", f"{model}_{fmt}")
    path = os.path.join(raw_dir, f"{safe}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False, indent=1)
    return path


def extract_text_and_thinking(fmt: str, data: dict):
    if fmt == "anthropic":
        blocks = data.get("content") or []
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        thinking = "".join(b.get("thinking", "") for b in blocks
                           if b.get("type") == "thinking")
        return text.strip(), len(thinking)
    msg = (data.get("choices") or [{}])[0].get("message") or {}
    return (msg.get("content") or "").strip(), len(msg.get("reasoning_content") or "")


def classify_http_error(status: int, body: str) -> str:
    if status in (401, 403):
        return "auth-error"
    low = body.lower()
    if status == 400 or status == 404:
        if "no available channel" in low or "not found" in low or "not exist" in low:
            return "no-channel"
        return "bad-request"
    if status >= 500 or "temporarily unavailable" in low or "upstream" in low:
        return "upstream-error"
    return f"http-{status}"


async def probe_one(session, fmt, base_url, model, key, max_tokens, raw_dir=None):
    url, headers, body = build_request(fmt, base_url, model, key, max_tokens)
    # Forensic layer: capture BEFORE any truncation. The result dict below is
    # the display layer (truncates freely); this record is the evidence layer
    # (complete status + every header + full body) and must stay unfiltered.
    evidence = {"captured_at": datetime.now(timezone.utc).isoformat(),
                "url": url,
                "request_headers": _mask_secrets(headers),
                "request_body": body}
    try:
        async with session.post(url, headers=headers, json=body) as resp:
            raw = await resp.text()
            # list-of-pairs, NOT dict(): HTTP allows repeated header names
            # (multiple Set-Cookie lines) and dict() silently keeps only one —
            # a structural loss the evidence layer must not have.
            evidence.update({"response_status": resp.status,
                             "response_headers": list(resp.headers.items()),
                             "response_body": raw})
            raw_path = _dump_raw(raw_dir, model, fmt, evidence)
            if resp.status != 200:
                verdict = classify_http_error(resp.status, raw)
                return {"model": model, "format": fmt, "verdict": verdict,
                        "http": resp.status, "detail": raw[:160],
                        "raw": raw_path}
            data = json.loads(raw)
            text, thinking_len = extract_text_and_thinking(fmt, data)
            usage = data.get("usage") or {}
            if text:
                return {"model": model, "format": fmt, "verdict": "available",
                        "http": 200, "sample": text[:60],
                        "served_model_field": data.get("model"),
                        "raw": raw_path}
            return {"model": model, "format": fmt, "verdict": "empty-content",
                    "http": 200, "thinking_chars": thinking_len,
                    "usage": usage, "raw": raw_path,
                    "hint": ("thinking consumed the budget — raise --max-tokens"
                             if thinking_len else
                             "no text and no thinking — treat as not usable")}
    except aiohttp.ClientError as exc:
        evidence["transport_error"] = f"{type(exc).__name__}: {exc}"
        raw_path = _dump_raw(raw_dir, model, fmt, evidence)
        return {"model": model, "format": fmt, "verdict": "transport-error",
                "detail": f"{type(exc).__name__}: {exc}"[:160],
                "raw": raw_path}


async def run(args, key):
    formats = ["openai", "anthropic"] if args.format == "both" else [args.format]
    connector = aiohttp.TCPConnector(force_close=True, limit=args.parallel)
    timeout = aiohttp.ClientTimeout(total=args.timeout)
    async with aiohttp.ClientSession(connector=connector, timeout=timeout,
                                     trust_env=False) as session:
        tasks = [probe_one(session, fmt, args.base_url, m, key, args.max_tokens,
                           raw_dir=args.raw_dir)
                 for m in args.model_list for fmt in formats]
        return await asyncio.gather(*tasks)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base-url", required=True,
                    help="Endpoint base, with or without /v1")
    ap.add_argument("--models", nargs="+", required=True,
                    help="Model IDs, or a single @file with one ID per line")
    ap.add_argument("--key-env", required=True,
                    help="NAME of the env var holding the API key")
    ap.add_argument("--format", choices=["openai", "anthropic", "both"],
                    default="both")
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS,
                    help="Keep generous; small values create empty-content "
                         "false negatives on reasoning models")
    ap.add_argument("--parallel", type=int, default=6,
                    help="Concurrent probes; availability sweeps are cheap, "
                         "but stay polite to the gateway")
    ap.add_argument("--timeout", type=float, default=180,
                    help="Per-request total timeout in seconds; reasoning "
                         "models can think for a while before the first token")
    ap.add_argument("--output", help="Write full JSON results here")
    ap.add_argument("--raw-dir", default="availability-raw",
                    help="Directory for per-probe evidence files: complete "
                         "request + response status/headers/body, secrets "
                         "masked, nothing truncated (display output truncates; "
                         "these files are the forensic layer and never do). "
                         "Pass an empty string to disable.")
    args = ap.parse_args()
    args.raw_dir = args.raw_dir or None
    if args.raw_dir:
        os.makedirs(args.raw_dir, exist_ok=True)

    key = os.environ.get(args.key_env)
    if not key:
        print(f"CONFIG: env var {args.key_env} is empty/unset", file=sys.stderr)
        sys.exit(EXIT_CONFIG)

    models: list[str] = []
    for item in args.models:
        if item.startswith("@"):
            with open(item[1:], encoding="utf-8") as fh:
                models += [ln.strip() for ln in fh
                           if ln.strip() and not ln.startswith("#")]
        else:
            models.append(item)
    args.model_list = models

    # Client-side markers (e.g. Claude Code's "[1m]") get parsed and stripped by
    # the CLI locally — they never reach a real endpoint, so a raw probe of the
    # literal string tests something that was never supposed to exist at this
    # layer. A no-channel verdict here proves nothing about the vendor. See
    # references/evaluation_disciplines.md §9 for the full explanation.
    bracket_suffixed = [m for m in models if re.search(r"\[[^\]]+\]$", m)]
    if bracket_suffixed:
        print(f"WARNING: {bracket_suffixed} look like client-side markers "
              f"(bracket suffix), not real API model IDs — e.g. Claude Code's "
              f"[1m] never reaches the wire, it's stripped locally before the "
              f"request is built. Probing it here tests the wrong layer.",
              file=sys.stderr)

    results = asyncio.run(run(args, key))

    by_model: dict[str, list] = {}
    for r in results:
        by_model.setdefault(r["model"], []).append(r)

    width = max(len(m) for m in models) + 2
    print(f"{'model':<{width}}{'format':<11}verdict")
    print("-" * (width + 40))
    any_unavailable = False
    all_transport = bool(results)
    for r in results:
        mark = {"available": "OK ", "empty-content": "?? ",
                "no-channel": "-- ", "upstream-error": "!! ",
                "auth-error": "!! ", "transport-error": "!! "}.get(r["verdict"], "?? ")
        extra = r.get("hint") or r.get("detail") or r.get("sample") or ""
        print(f"{r['model']:<{width}}{r['format']:<11}{mark}{r['verdict']}"
              f"{('  ' + extra) if extra else ''}")
        if r["verdict"] != "available":
            any_unavailable = True
        if r["verdict"] != "transport-error":
            all_transport = False

    print("\nReminders: 'no-channel' on an ID you invented proves nothing — "
          "verify IDs against official docs first. 'empty-content' with "
          "thinking_chars>0 is a max_tokens artifact, not an unavailable model. "
          "A gateway's /v1/models listing routinely omits routable models.")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump({"base_url": args.base_url, "max_tokens": args.max_tokens,
                       "results": results}, fh, ensure_ascii=False, indent=1)
        print(f"\nWrote {args.output}")

    if all_transport:
        sys.exit(EXIT_TRANSPORT)
    sys.exit(EXIT_UNAVAILABLE if any_unavailable else EXIT_OK)


if __name__ == "__main__":
    main()
