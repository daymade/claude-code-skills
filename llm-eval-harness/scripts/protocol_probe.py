#!/usr/bin/env python3
"""Anthropic Messages protocol-compliance probe — thinking-block trigger rate AND
history-replay acceptance.

What it answers
---------------
Two DIFFERENT, orthogonal compatibility questions about a vendor's Anthropic-compatible
``/v1/messages`` endpoint — a real 2026-07-21 incident showed that passing one says
nothing about the other:

1. **generation** (the original check): does requesting ``thinking: {type: enabled}``
   actually make the endpoint EMIT ``thinking_delta`` / ``signature_delta`` SSE events?
   Many vendors return a 200 and a plausible answer while silently NOT emitting them —
   which breaks every client (Claude Code, Cursor, Cline) that renders or relies on a
   foldable thinking block.
2. **history-replay** (added after the incident below): does the endpoint ACCEPT a
   ``type: "thinking"`` block that already exists in an assistant turn's HISTORY, when
   that history is replayed back on a later turn? This is what every real agentic client
   does on every continuation — Claude Code always resends the full message array,
   thinking blocks included. A vendor can pass check 1 (it emits thinking fine when asked)
   and still hard-reject check 2 (it 400s the instant that same block comes back as
   input) — these are different code paths (response generation vs request validation)
   and testing one tells you nothing about the other.

Real incident that motivated check 2: a Kimi/Moonshot model, accessed through a China
reseller's Anthropic-compatible endpoint, 400'd with "invalid part type: thinking" the
moment a prior assistant turn's thinking block was replayed back — killing every
subsequent request in that session. The determining factor turned out to be a
DOCUMENTED, per-model vendor parameter (Moonshot's own ``preserve_thinking``, default
on/off varies by model) — not the reseller, not the protocol layer in general. See
references/evaluation_disciplines.md for the single-variable-testing methodology that
found this (an earlier, confounded comparison — different model AND different reseller
at once — produced a wrong conclusion first).

The catch, for BOTH checks, is that vendor behavior is often PROBABILISTIC, not binary.
One real vendor returned thinking blocks on only ~13% of generation requests (vs 100%
for two competitors) — a single sample would have called it either "works" or "broken",
both wrong. The same discipline applies to history-replay: don't trust N=1 there either.

Two disciplines that make either verdict trustworthy
------------------------------------------------------
- ``--repeat`` defaults to 10 for both checks. A single probe (``--repeat 1``) cannot
  distinguish "not implemented" from "implemented but probability < 100%". Do not trust
  a verdict from one sample.
- ``Connection: close`` on every request. Without it, HTTP keep-alive can pin all your
  requests to one upstream instance behind the vendor's load balancer, so you sample
  one replica's behavior and miss the real cross-fleet trigger-rate distribution.
  (A real probe saw 0/10 with keep-alive vs 17/90 with close — same endpoint.)

Stdlib only — no pip install needed. Key passed by ENV VAR NAME, never on the CLI.

Usage
-----
    # Both checks (default) — most vendors should run this, not just generation
    uv run python protocol_probe.py \
        --url https://api.example.com/v1/messages \
        --model some-model --key-env MY_API_KEY --repeat 10

    # Just the history-replay check (the one that catches the 2026-07-21-shaped bug)
    uv run python protocol_probe.py \
        --url https://api.example.com/v1/messages \
        --model some-model --key-env MY_API_KEY --check history-replay
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
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


def history_replay_request(url, model, api_key, budget, max_tokens, timeout, proxy):
    """Fire one /v1/messages request whose history ALREADY contains a `type: "thinking"`
    block in a prior assistant turn, then check whether the endpoint accepts it or
    rejects the request outright. This is the request-VALIDATION / multi-turn-continuity
    question — orthogonal to one_request() above, which only tests whether the endpoint
    EMITS thinking deltas when asked. A vendor can pass one and fail the other; see the
    module docstring for the real incident that showed exactly this split.

    The fake `signature` is a plausible-length random hex string, not a human-readable
    placeholder — some vendors may do superficial signature-format checks, and a
    signature that's obviously fake (e.g. the literal string "fake") could trigger a
    different rejection than the one being tested (type-level acceptance)."""
    fake_signature = secrets.token_hex(32)
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "stream": True,
        "thinking": {"type": "enabled", "budget_tokens": budget},
        "messages": [
            {"role": "user", "content": "What is 12 * 7?"},
            {"role": "assistant", "content": [
                {"type": "thinking", "thinking": "12 times 7. 12 * 7 = 84.",
                 "signature": fake_signature},
                {"type": "text", "text": "12 * 7 = 84."},
            ]},
            {"role": "user", "content": "And what about 9 * 8?"},
        ],
    }
    body = json.dumps(payload).encode()
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Accept": "text/event-stream",
        "Connection": "close",
    }
    handlers = [urllib.request.ProxyHandler({} if not proxy else {"http": proxy, "https": proxy})]
    opener = urllib.request.build_opener(*handlers)

    result = {"accepted": None, "http_status": None, "error_text": None,
              "answered_followup": False, "rejects_thinking_type": False}
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with opener.open(req, timeout=timeout) as resp:
            result["http_status"] = resp.status
            text_out = []
            error_event = None
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
                if etype == "error":
                    error_event = evt.get("error", evt)  # some vendors put a 200 + SSE error event
                elif etype == "content_block_delta" and evt.get("delta", {}).get("type") == "text_delta":
                    text_out.append(evt["delta"].get("text", ""))
            if error_event is not None:
                result["accepted"] = False
                result["error_text"] = json.dumps(error_event, ensure_ascii=False)[:300]
            else:
                result["accepted"] = True
                # "72" = 9*8 — proves the endpoint actually PROCESSED the follow-up
                # turn using the replayed history, not just "didn't error".
                result["answered_followup"] = "72" in "".join(text_out)
    except urllib.error.HTTPError as e:
        result["accepted"] = False
        result["http_status"] = e.code
        result["error_text"] = e.read()[:500].decode("utf-8", "replace")
    except Exception as e:
        result["accepted"] = None  # transport failure — not a protocol verdict either way
        result["error_text"] = f"{type(e).__name__}: {e}"

    if result["error_text"]:
        low = result["error_text"].lower()
        result["rejects_thinking_type"] = "thinking" in low and any(
            kw in low for kw in ("invalid", "not support", "unsupported"))
    return result


def run_generation(args, api_key):
    """The original check: does `thinking: {type: enabled}` make the endpoint EMIT
    thinking_delta/signature_delta events? Returns the result dict for --output."""
    checks = ["transport_ok", "http_2xx", "thinking_delta", "signature_delta", "text", "message_stop"]
    counts = {c: 0 for c in checks}
    samples, model_fields = [], set()
    print(f"# generation probe  model={args.model}  N={args.repeat}  Connection: close\n")
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
    mf = ", ".join(repr(x) for x in sorted(model_fields, key=lambda x: (x is None, x)))
    print(f"  model field seen   : {mf or 'none'}")
    print(f"\n# verdict: generation (thinking-delta emission) = {verdict}  (trigger rate {round(rate*100)}%)")
    if 0 < rate < 1:
        print("  → probabilistic compliance: the endpoint sometimes honors `thinking: enabled`")
        print("    and sometimes silently drops it. Clients that need the thinking block will flake.")

    return {"n": n, "counts": counts, "thinking_trigger_rate": rate,
            "verdict": verdict, "samples": samples}


def run_history_replay(args, api_key):
    """The new check: does the endpoint ACCEPT a `type: "thinking"` block already
    present in an assistant turn's history, replayed back on a later turn? This is
    what every real agentic client does on every continuation."""
    n = args.repeat
    print(f"\n# history-replay probe  model={args.model}  N={n}  Connection: close")
    print("# (prior assistant turn carries a `thinking` block; checks whether the")
    print("#  follow-up turn is accepted, and whether it's actually answered using it)\n")
    samples = []
    accepted = rejected_thinking = rejected_other = transport_fail = answered = 0
    for i in range(1, n + 1):
        r = history_replay_request(args.url, args.model, api_key, args.budget,
                                    args.max_tokens, args.timeout, args.proxy)
        samples.append(r)
        if r["accepted"] is True:
            accepted += 1
            if r["answered_followup"]:
                answered += 1
            mark = "✓" if r["answered_followup"] else "~"
        elif r["accepted"] is False:
            if r["rejects_thinking_type"]:
                rejected_thinking += 1
                mark = "✗"
            else:
                rejected_other += 1
                mark = "?"
        else:
            transport_fail += 1
            mark = "!"
        extra = f"  {r['error_text'][:100]}" if r.get("error_text") else ""
        print(f"  {i:>2}/{n} {mark} accepted={r['accepted']}{extra}")
        if args.inter_delay:
            time.sleep(args.inter_delay)

    if rejected_thinking == n:
        verdict = "rejects-thinking-in-history"
    elif accepted == n and answered == n:
        verdict = "accepts-thinking-in-history"
    elif accepted > 0 and rejected_thinking > 0:
        verdict = f"inconsistent (accepted {accepted}/{n}, rejected-as-thinking {rejected_thinking}/{n})"
    elif rejected_other > 0 or transport_fail > 0:
        verdict = (f"inconclusive (rejected_other={rejected_other} transport_fail={transport_fail} "
                   f"— read error_text, may be auth/rate-limit and unrelated to thinking blocks)")
    else:
        verdict = f"accepts-but-followup-unanswered ({accepted}/{n} accepted, only {answered}/{n} correctly continued)"

    print(f"\n# results: accepted={accepted}/{n}  rejected_as_thinking_type={rejected_thinking}/{n}  "
          f"rejected_other={rejected_other}/{n}  transport_fail={transport_fail}/{n}  "
          f"answered_followup={answered}/{n}")
    print(f"# verdict: history-replay = {verdict}")
    if verdict == "rejects-thinking-in-history":
        print("  → every real agentic client (Claude Code, Cursor, Cline) resends full history on")
        print("    every turn, thinking blocks included. This endpoint will 400 and KILL every")
        print("    session the moment a thinking-capable turn happens once. Before concluding this")
        print("    is a blanket vendor/model-family limitation, check for a documented per-model")
        print("    vendor parameter first (e.g. Moonshot's `preserve_thinking`, default varies by")
        print("    model) — see references/evaluation_disciplines.md.")

    return {"n": n, "accepted": accepted, "rejected_as_thinking_type": rejected_thinking,
            "rejected_other": rejected_other, "transport_fail": transport_fail,
            "answered_followup": answered, "verdict": verdict, "samples": samples}


def main():
    ap = argparse.ArgumentParser(
        description="Anthropic protocol probe: thinking-block generation AND history-replay acceptance (N>=10)")
    ap.add_argument("--url", required=True, help="…/v1/messages endpoint")
    ap.add_argument("--model", required=True)
    ap.add_argument("--key-env", required=True, help="NAME of the env var holding the API key")
    ap.add_argument("--check", choices=["generation", "history-replay", "all"], default="all",
                    help="generation = does thinking:enabled emit deltas; history-replay = does "
                         "a thinking block already in history get accepted on a later turn; "
                         "all = both (default — they test different code paths, run both unless "
                         "you already know which one you need)")
    ap.add_argument("--repeat", type=int, default=10, help="sample count — KEEP >=10 for a real verdict")
    ap.add_argument("--budget", type=int, default=2000, help="thinking budget_tokens")
    ap.add_argument("--max-tokens", type=int, default=4000)
    ap.add_argument("--prompt", default="3 ^ 5 = ? Explain your reasoning briefly.",
                    help="prompt for the generation check only")
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

    run_gen = args.check in ("generation", "all")
    run_hist = args.check in ("history-replay", "all")

    output = {"model": args.model}
    ok = True
    if run_gen:
        gen = run_generation(args, api_key)
        output["generation"] = gen
        ok = ok and gen["verdict"] == "fully-implemented"
    if run_hist:
        hist = run_history_replay(args, api_key)
        output["history_replay"] = hist
        ok = ok and hist["verdict"] == "accepts-thinking-in-history"

    if run_gen and run_hist:
        print(f"\n# combined verdict: generation={output['generation']['verdict']}  "
              f"history_replay={output['history_replay']['verdict']}")
        if output["generation"]["verdict"] == "fully-implemented" and \
                output["history_replay"]["verdict"] == "rejects-thinking-in-history":
            print("  → this is the split that motivated adding the history-replay check: the endpoint")
            print("    happily EMITS thinking blocks when asked, but 400s the instant one comes back")
            print("    as input on a later turn. Passing generation tells you nothing about this.")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"  full JSON → {args.output}")

    # exit non-zero if not fully compliant on every check that ran — handy in CI / batch vendor screening
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
