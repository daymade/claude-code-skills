#!/usr/bin/env python3
"""LLM concurrency / stability probe — success rate, latency percentiles, concurrency ceiling.

What it answers
---------------
"If N users hit this endpoint at the same instant, how many succeed, how slow does it
get, and where does it break?" Essential before putting a model behind a workshop, a
batch job, or any burst workload — a model that is fast single-threaded can collapse
(429s, TCP drops, silent 20s timeouts) at modest concurrency.

It fires ``concurrency`` requests simultaneously (one asyncio gather), measures each,
then optionally repeats at increasing concurrency levels to find the ceiling — the
point where success rate falls off or latency explodes.

Two hard-won disciplines baked in (both came from a real workshop-readiness benchmark)
-------------------------------------------------------------------------------------
- ``trust_env=False`` on the session: a local HTTP/SOCKS proxy in the environment would
  otherwise route every request through it, and you would measure the proxy's
  concurrency limit, not the model's. This isolates the endpoint.
- ``force_close=True`` (no keep-alive pooling): each request gets its own TCP
  connection, so connection reuse cannot mask the upstream's real per-request behavior.

It also emits a "concurrency proof" — the count of request pairs whose lifetimes
overlapped — so you can confirm the requests actually ran in parallel rather than
being serialized by some layer.

Key handling: passed by ENV VAR NAME (``--key-env``), never on the CLI.

Usage
-----
    uv run --with aiohttp python concurrency_probe.py \
        --url https://api.example.com/v1/chat/completions \
        --model some-model --key-env MY_API_KEY \
        --format openai --concurrency 10 20 40 60

    # Anthropic Messages endpoint:
    uv run --with aiohttp python concurrency_probe.py \
        --url https://api.example.com/v1/messages \
        --model some-model --key-env MY_API_KEY \
        --format anthropic --concurrency 10 30 50
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass

try:
    import aiohttp
except ImportError:
    sys.exit("Missing dependency. Run via: uv run --with aiohttp python concurrency_probe.py ...")


@dataclass
class Result:
    index: int
    status: int
    start: float
    end: float
    duration: float
    text: str

    @property
    def ok(self) -> bool:
        return self.status == 200


def build_request(fmt, model, api_key, index):
    """Return (headers, payload) for a minimal request — small max_tokens keeps it cheap;
    the prompt varies by index only to avoid any prompt-cache short-circuiting."""
    prompt = f"Reply with one word only: ok ({index})"
    if fmt == "anthropic":
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
    else:  # openai
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
    payload = {"model": model, "max_tokens": 16, "messages": [{"role": "user", "content": prompt}]}
    return headers, payload


async def send_one(session, url, fmt, model, api_key, index, t0, timeout):
    headers, payload = build_request(fmt, model, api_key, index)
    start = time.monotonic() - t0
    try:
        async with session.post(url, json=payload, headers=headers,
                                timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            body = await resp.text()
            end = time.monotonic() - t0
            return Result(index, resp.status, start, end, end - start, body[:80].replace("\n", " "))
    except Exception as e:
        end = time.monotonic() - t0
        return Result(index, 0, start, end, end - start, f"ERR:{type(e).__name__}")


async def bench_round(url, fmt, model, api_key, concurrency, timeout):
    # trust_env=False isolates from any ambient proxy; force_close avoids keep-alive pooling
    connector = aiohttp.TCPConnector(limit=0, force_close=True)
    async with aiohttp.ClientSession(connector=connector, trust_env=False) as session:
        t0 = time.monotonic()
        tasks = [send_one(session, url, fmt, model, api_key, i, t0, timeout)
                 for i in range(1, concurrency + 1)]
        results = await asyncio.gather(*tasks)
    return list(results)


def summarize(results, concurrency):
    ok = [r for r in results if r.ok]
    fail = [r for r in results if not r.ok]
    status_429 = sum(1 for r in results if r.status == 429)
    out = {
        "concurrency": concurrency,
        "success": len(ok),
        "total": concurrency,
        "success_rate": round(len(ok) / concurrency, 3),
        "http_429": status_429,
    }
    if ok:
        durs = sorted(r.duration for r in ok)
        out["latency_avg_s"] = round(statistics.mean(durs), 2)
        out["latency_p50_s"] = round(durs[len(durs) // 2], 2)
        out["latency_p90_s"] = round(durs[min(int(len(durs) * 0.9), len(durs) - 1)], 2)
        out["latency_max_s"] = round(durs[-1], 2)
    # concurrency proof: how many request pairs overlapped in time
    overlap = sum(1 for i, a in enumerate(results) for b in results[i + 1:]
                  if a.start < b.end and b.start < a.end)
    out["overlap_pairs"] = overlap
    out["total_pairs"] = concurrency * (concurrency - 1) // 2
    if fail:
        # distinct failure signatures help tell 429-throttle from TCP-drop from 5xx
        sigs = {}
        for r in fail:
            key = f"http{r.status}:{r.text[:30]}"
            sigs[key] = sigs.get(key, 0) + 1
        out["failures"] = sigs
    return out


def main():
    ap = argparse.ArgumentParser(description="LLM concurrency / stability probe")
    ap.add_argument("--url", required=True, help="FULL endpoint URL (…/v1/chat/completions or …/v1/messages)")
    ap.add_argument("--model", required=True)
    ap.add_argument("--key-env", required=True, help="NAME of the env var holding the API key")
    ap.add_argument("--format", choices=["openai", "anthropic"], default="openai")
    ap.add_argument("--concurrency", type=int, nargs="+", default=[10],
                    help="one or more levels, e.g. --concurrency 10 20 40 60 (ramps to find the ceiling)")
    ap.add_argument("--timeout", type=float, default=30)
    ap.add_argument("--output", help="write full JSON results here")
    args = ap.parse_args()

    api_key = os.environ.get(args.key_env)
    if not api_key:
        sys.exit(f"Env var {args.key_env} is empty or unset — export your key there first.")

    print(f"# concurrency probe  model={args.model}  format={args.format}")
    print(f"# isolation: trust_env=False (ambient proxy excluded), force_close=True\n")
    rows = []
    for c in args.concurrency:
        results = asyncio.run(bench_round(args.url, args.format, args.model, api_key, c, args.timeout))
        s = summarize(results, c)
        rows.append(s)
        lat = f"p50={s.get('latency_p50_s','-')}s p90={s.get('latency_p90_s','-')}s" if s["success"] else "—"
        warn = "  ⚠ degraded" if s["success_rate"] < 1.0 else ""
        print(f"  conc={c:>3}  ok={s['success']}/{c} ({int(s['success_rate']*100)}%)  "
              f"429={s['http_429']}  {lat}{warn}")
        if s.get("failures"):
            for sig, n in s["failures"].items():
                print(f"            fail x{n}: {sig}")
        if len(args.concurrency) > 1:
            time.sleep(1)  # brief gap between ramp levels

    # ceiling hint: highest level that still passed 100%
    clean = [r["concurrency"] for r in rows if r["success_rate"] == 1.0]
    print("\n# summary")
    if clean:
        print(f"  highest 100%-success concurrency tested: {max(clean)}")
    degraded = [r["concurrency"] for r in rows if r["success_rate"] < 1.0]
    if degraded:
        print(f"  degradation starts at concurrency: {min(degraded)}")
        print("  ⚠ latency p50/p90 are over SUCCESSFUL requests only — at the breaking point")
        print("    the slow/dropped/timed-out requests are excluded, so latency can look")
        print("    deceptively good as success rate falls. Read the two columns together.")

    if args.output:
        with open(args.output, "w") as f:
            json.dump({"model": args.model, "format": args.format, "levels": rows}, f,
                      ensure_ascii=False, indent=2)
        print(f"  full JSON → {args.output}")


if __name__ == "__main__":
    main()
