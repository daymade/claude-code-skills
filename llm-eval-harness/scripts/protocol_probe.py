#!/usr/bin/env python3
"""Anthropic Messages protocol-compliance probe — thinking-block trigger rate.

What it answers
---------------
When a vendor advertises an Anthropic-compatible ``/v1/messages`` endpoint, does it
ACTUALLY implement the ``thinking`` block protocol? Many vendors return a 200 and a
plausible answer while silently NOT emitting the ``thinking_delta`` / ``signature_delta``
events the protocol requires — which breaks every client (Claude Code, Cursor, Cline)
that renders or relies on a foldable thinking block.

The catch is that compliance is often PROBABILISTIC, not binary. One real vendor
returned thinking blocks on only ~13% of requests (vs 100% for two competitors) — a
single sample would have called it either "works" or "broken", both wrong.

Two disciplines that make the verdict trustworthy
-------------------------------------------------
- ``--repeat`` defaults to 10. A single probe (``--repeat 1``) cannot distinguish
  "not implemented" from "implemented but probability < 100%". Do not trust a verdict
  from one sample.
- ``Connection: close`` on every request. Without it, HTTP keep-alive can pin all your
  requests to one upstream instance behind the vendor's load balancer, so you sample
  one replica's behavior and miss the real cross-fleet trigger-rate distribution.
  (A real probe saw 0/10 with keep-alive vs 17/90 with close — same endpoint.)

Stdlib only — no pip install needed. Key passed by ENV VAR NAME, never on the CLI.

Usage
-----
    uv run python protocol_probe.py \
        --url https://api.example.com/v1/messages \
        --model some-model --key-env MY_API_KEY --repeat 10
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request


def one_request(url, model, api_key, prompt, budget, max_tokens, timeout, proxy):
    """Fire one streaming /v1/messages request with thinking enabled; return which
    protocol features were observed in the SSE stream."""
    payload = json.dumps({
        "model": model,
        "max_tokens": max_tokens,
        "stream": True,
        "messages": [{"role": "user", "content": prompt}],
        "thinking": {"type": "enabled", "budget_tokens": budget},
    }).encode()
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Accept": "text/event-stream",
        "Connection": "close",  # critical: defeat LB sticky-routing of keep-alive
    }
    # Default to a direct connection (no ambient proxy); honor --proxy if given.
    handlers = [urllib.request.ProxyHandler({} if not proxy else {"http": proxy, "https": proxy})]
    opener = urllib.request.build_opener(*handlers)

    seen = {"transport_ok": False, "http_2xx": False, "thinking_delta": False,
            "signature_delta": False, "text": False, "message_stop": False,
            "model_field": None, "error": None}
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with opener.open(req, timeout=timeout) as resp:
            seen["transport_ok"] = True
            seen["http_2xx"] = 200 <= resp.status < 300
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data in ("", "[DONE]"):
                    continue
                try:
                    evt = json.loads(data)
                except json.JSONDecodeError:
                    continue
                etype = evt.get("type")
                if etype == "message_start":
                    seen["model_field"] = evt.get("message", {}).get("model")
                elif etype == "content_block_delta":
                    d = evt.get("delta", {})
                    dt = d.get("type")
                    if dt == "thinking_delta":
                        seen["thinking_delta"] = True
                    elif dt == "signature_delta":
                        seen["signature_delta"] = True
                    elif dt in ("text_delta", "input_json_delta"):
                        seen["text"] = True
                elif etype == "message_stop":
                    seen["message_stop"] = True
    except urllib.error.HTTPError as e:
        seen["error"] = f"HTTP {e.code}: {e.read()[:120].decode('utf-8', 'replace')}"
    except Exception as e:
        seen["error"] = f"{type(e).__name__}: {e}"
    return seen


def main():
    ap = argparse.ArgumentParser(description="Anthropic thinking-block protocol probe (N>=10)")
    ap.add_argument("--url", required=True, help="…/v1/messages endpoint")
    ap.add_argument("--model", required=True)
    ap.add_argument("--key-env", required=True, help="NAME of the env var holding the API key")
    ap.add_argument("--repeat", type=int, default=10, help="sample count — KEEP >=10 for a real verdict")
    ap.add_argument("--budget", type=int, default=2000, help="thinking budget_tokens")
    ap.add_argument("--max-tokens", type=int, default=4000)
    ap.add_argument("--prompt", default="3 ^ 5 = ? Explain your reasoning briefly.")
    ap.add_argument("--inter-delay", type=float, default=0.0, help="seconds between requests")
    ap.add_argument("--timeout", type=float, default=90)
    ap.add_argument("--proxy", default=None, help="optional proxy URL (default: direct)")
    ap.add_argument("--output", help="write full JSON results here")
    args = ap.parse_args()

    api_key = os.environ.get(args.key_env)
    if not api_key:
        sys.exit(f"Env var {args.key_env} is empty or unset — export your key there first.")

    if args.repeat < 10:
        print(f"⚠ --repeat {args.repeat} is below 10; a verdict from <10 samples is unreliable "
              f"for a probabilistic feature. Proceeding, but treat the result as indicative only.\n")

    checks = ["transport_ok", "http_2xx", "thinking_delta", "signature_delta", "text", "message_stop"]
    counts = {c: 0 for c in checks}
    samples, model_fields = [], set()
    print(f"# protocol probe  model={args.model}  N={args.repeat}  Connection: close\n")
    for i in range(1, args.repeat + 1):
        s = one_request(args.url, args.model, api_key, args.prompt, args.budget,
                        args.max_tokens, args.timeout, args.proxy)
        samples.append(s)
        for c in checks:
            if s[c]:
                counts[c] += 1
        if s["model_field"] is not None:
            model_fields.add(s["model_field"])
        mark = "✓" if s["thinking_delta"] else ("·" if s["http_2xx"] else "✗")
        extra = f"  {s['error']}" if s["error"] else ""
        print(f"  {i:>2}/{args.repeat} {mark} thinking={s['thinking_delta']} "
              f"text={s['text']} stop={s['message_stop']}{extra}")
        if args.inter_delay:
            time.sleep(args.inter_delay)

    n = args.repeat
    rate = counts["thinking_delta"] / n if n else 0.0
    if rate == 1.0:
        verdict = "fully-implemented"
    elif rate == 0.0:
        verdict = "not-implemented"
    else:
        verdict = f"intermittent ({counts['thinking_delta']}/{n})"

    print("\n# results (hits / N)")
    for c in checks:
        print(f"  {c:18} {counts[c]}/{n}  ({round(counts[c]/n*100)}%)")
    # empty model field on non-stream paths is a known compatibility bug worth surfacing
    mf = ", ".join(repr(x) for x in sorted(model_fields, key=lambda x: (x is None, x)))
    print(f"  model field seen   : {mf or 'none'}")
    print(f"\n# verdict: thinking-block protocol = {verdict}  (trigger rate {round(rate*100)}%)")
    if 0 < rate < 1:
        print("  → probabilistic compliance: the endpoint sometimes honors `thinking: enabled`")
        print("    and sometimes silently drops it. Clients that need the thinking block will flake.")

    if args.output:
        with open(args.output, "w") as f:
            json.dump({"model": args.model, "n": n, "counts": counts,
                       "thinking_trigger_rate": rate, "verdict": verdict,
                       "samples": samples}, f, ensure_ascii=False, indent=2)
        print(f"  full JSON → {args.output}")

    # exit non-zero if not fully compliant — handy in CI / batch vendor screening
    sys.exit(0 if verdict == "fully-implemented" else 1)


if __name__ == "__main__":
    main()
