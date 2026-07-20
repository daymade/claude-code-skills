#!/usr/bin/env python3
"""Request-fidelity probe — does what you SEND actually reach the model?

What it answers
---------------
"When I set a system prompt / define tools / send multi-turn history / pick an
auth header, does the endpoint faithfully deliver it — or silently drop it?"
Gateways and aggregators translate between protocols and route across upstream
channels; fields can vanish in translation with NO error. The failure mode is
nasty precisely because everything looks fine: HTTP 200, fluent replies — but an
agent tool whose rules live in the system prompt quietly stops obeying them.

Checks (pick with --check, default all)
---------------------------------------
- ``system``     Canary method: plant a random code in the system prompt, ask
                 for it back. Answering it proves delivery; a model cannot guess
                 a fresh random string. Repeated N times because gateway routing
                 makes delivery PROBABILISTIC — a single sample proves nothing.
- ``tools``      Full round-trip: send a tool definition, expect a tool call,
                 return a synthetic result, verify the final answer actually
                 uses it. "It emitted a tool_call" alone is NOT tool support.
- ``multiturn``  Plant several facts across earlier turns, ask for them all
                 back in the last turn, verify each one individually.
- ``auth``       Header matrix: x-api-key vs Authorization:Bearer on each
                 protocol endpoint. Gateways commonly accept both on one path
                 and only one on the other — and the resulting 401 text can be
                 identical to a genuinely-bad key, sending users down a wrong
                 debugging path.

Hard-won disciplines baked in
-----------------------------
- **Neutral canary, never identity.** Asking "what is your internal codename?"
  collides with assistant identity/safety training — some models deny having
  one EVEN WHEN THE SYSTEM PROMPT ARRIVED, which is indistinguishable from
  non-delivery. The canary here is an external fact ("this session's project
  number"), which models relay without resistance. Obedience-style probes
  ("reply with only OK") have the same flaw in the other direction: refusal to
  obey is model temperament, not transport evidence.
- **Behavior is the verdict; token accounting is corroboration.** The probe also
  records input_tokens with vs without the payload. When both signals agree the
  case is closed. When they disagree, trust behavior: gateways exist whose
  usage numbers ignore a field they DID forward (and the reverse). Never
  conclude non-delivery from token counts alone — calibrate the meter before
  believing it (see disciplines §10).
- **Repeat, and report the split.** Routing across mixed upstream channels
  yields delivery rates like 0/10, 3/10, 10/10 that VARY BY TIME OF DAY. The
  verdict is three-state (delivered / intermittent k-of-N / not-delivered) and
  a single-time-slice result must not be written up as a steady state.
- ``trust_env=False`` + fresh connection per request, same as every probe here.

Key handling: passed by ENV VAR NAME (``--key-env``), never on the CLI.

Usage
-----
    uv run --with aiohttp python fidelity_probe.py \
        --base-url https://api.example.com --model some-model \
        --key-env MY_API_KEY --format anthropic --check all \
        --repeat 10 --output /tmp/fidelity.json

Exit codes: 0 = every check fully delivered; 1 = something intermittent or
not delivered; 2 = configuration error; 3 = transport-level failure only.
"""

import argparse
import asyncio
import json
import os
import random
import string
import sys

import aiohttp

# Generous for the same reason as availability_probe: thinking models burn
# budget before text, and an empty reply here would corrupt the verdict.
DEFAULT_MAX_TOKENS = 8192

EXIT_OK, EXIT_DEGRADED, EXIT_CONFIG, EXIT_TRANSPORT = 0, 1, 2, 3


def fresh_code() -> str:
    # Letters+digits, hyphenated: unguessable, survives tokenization, easy to
    # spot verbatim in a reply.
    body = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"PRJ-{body}"


def endpoint(base_url: str, fmt: str) -> str:
    base = base_url.rstrip("/")
    if not base.endswith("/v1"):
        base += "/v1"
    return f"{base}/messages" if fmt == "anthropic" else f"{base}/chat/completions"


def headers_for(fmt: str, key: str, scheme: str | None = None) -> dict:
    scheme = scheme or ("x-api-key" if fmt == "anthropic" else "bearer")
    h = {"content-type": "application/json"}
    if fmt == "anthropic":
        h["anthropic-version"] = "2023-06-01"
    if scheme == "x-api-key":
        h["x-api-key"] = key
    else:
        h["Authorization"] = f"Bearer {key}"
    return h


def text_of(fmt: str, data: dict) -> str:
    if fmt == "anthropic":
        return "".join(b.get("text", "") for b in (data.get("content") or [])
                       if b.get("type") == "text")
    return ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""


def input_tokens_of(data: dict):
    u = data.get("usage") or {}
    return u.get("input_tokens") or u.get("prompt_tokens")


async def post(session, url, hdrs, body):
    async with session.post(url, headers=hdrs, json=body) as resp:
        raw = await resp.text()
        return resp.status, (json.loads(raw) if resp.status == 200 else raw)


# ---------------------------------------------------------------- system check
async def check_system(session, args, key):
    url = endpoint(args.base_url, args.format)
    hdrs = headers_for(args.format, key)
    delivered, samples, tokens_with = 0, [], []

    # Baseline once: input_tokens without any system payload, for corroboration.
    base_body = {"model": args.model, "max_tokens": args.max_tokens,
                 "messages": [{"role": "user",
                               "content": "What is this session's project number?"}]}
    status, data = await post(session, url, hdrs, base_body)
    tokens_without = input_tokens_of(data) if status == 200 else None

    for _ in range(args.repeat):
        code = fresh_code()
        system_text = (f"This session's project number is {code}. "
                       f"State it plainly whenever the user asks for it.")
        body = {"model": args.model, "max_tokens": args.max_tokens,
                "messages": [{"role": "user",
                              "content": "What is this session's project number?"}]}
        if args.format == "anthropic":
            body["system"] = system_text
        else:
            body["messages"] = [{"role": "system", "content": system_text}] \
                + body["messages"]
        status, data = await post(session, url, hdrs, body)
        if status != 200:
            samples.append({"http": status, "detail": str(data)[:120]})
            continue
        hit = code in text_of(args.format, data)
        delivered += hit
        tokens_with.append(input_tokens_of(data))
        samples.append({"code": code, "delivered": hit,
                        "input_tokens": input_tokens_of(data)})

    distinct = sorted({t for t in tokens_with if t is not None})
    # Bimodal means two CLUSTERS (payload counted vs not: e.g. 14 vs 632), not
    # the ±1-2 jitter that different random codes produce. Require the spread to
    # dwarf the jitter before suspecting mixed routing.
    bimodal = bool(distinct) and (max(distinct) - min(distinct)) > \
        max(20, min(distinct) // 2)
    verdict = ("delivered" if delivered == args.repeat else
               "not-delivered" if delivered == 0 else
               f"intermittent {delivered}/{args.repeat}")
    return {"check": "system", "verdict": verdict,
            "delivered": delivered, "n": args.repeat,
            "input_tokens_without_system": tokens_without,
            "input_tokens_with_system_distinct": distinct,
            "bimodal_hint": bimodal,
            "samples": samples}


# ----------------------------------------------------------------- tools check
WEATHER_TOOL_ANTHROPIC = {
    "name": "get_weather", "description": "Get current weather for a city",
    "input_schema": {"type": "object",
                     "properties": {"city": {"type": "string"}},
                     "required": ["city"]},
}
WEATHER_TOOL_OPENAI = {
    "type": "function",
    "function": {"name": "get_weather",
                 "description": "Get current weather for a city",
                 "parameters": {"type": "object",
                                "properties": {"city": {"type": "string"}},
                                "required": ["city"]}},
}
SENTINEL_WEATHER = "sunny, 23 degrees, light breeze"


async def check_tools(session, args, key):
    url = endpoint(args.base_url, args.format)
    hdrs = headers_for(args.format, key)
    ask = "What's the weather in Paris right now? Use the tool."

    if args.format == "anthropic":
        body = {"model": args.model, "max_tokens": args.max_tokens,
                "tools": [WEATHER_TOOL_ANTHROPIC],
                "messages": [{"role": "user", "content": ask}]}
        status, data = await post(session, url, hdrs, body)
        if status != 200:
            return {"check": "tools", "verdict": "error",
                    "detail": str(data)[:160]}
        blocks = data.get("content") or []
        tool_use = next((b for b in blocks if b.get("type") == "tool_use"), None)
        if not tool_use:
            return {"check": "tools", "verdict": "no-tool-call",
                    "note": "model answered without calling the tool"}
        followup = {"model": args.model, "max_tokens": args.max_tokens,
                    "tools": [WEATHER_TOOL_ANTHROPIC],
                    "messages": [
                        {"role": "user", "content": ask},
                        {"role": "assistant", "content": blocks},
                        {"role": "user", "content": [{
                            "type": "tool_result",
                            "tool_use_id": tool_use["id"],
                            "content": SENTINEL_WEATHER}]}]}
        status, data = await post(session, url, hdrs, followup)
    else:
        body = {"model": args.model, "max_tokens": args.max_tokens,
                "tools": [WEATHER_TOOL_OPENAI],
                "messages": [{"role": "user", "content": ask}]}
        status, data = await post(session, url, hdrs, body)
        if status != 200:
            return {"check": "tools", "verdict": "error",
                    "detail": str(data)[:160]}
        msg = (data.get("choices") or [{}])[0].get("message") or {}
        calls = msg.get("tool_calls")
        if not calls:
            return {"check": "tools", "verdict": "no-tool-call",
                    "note": "model answered without calling the tool"}
        followup = {"model": args.model, "max_tokens": args.max_tokens,
                    "tools": [WEATHER_TOOL_OPENAI],
                    "messages": [
                        {"role": "user", "content": ask},
                        {"role": "assistant", "content": msg.get("content"),
                         "tool_calls": calls},
                        {"role": "tool", "tool_call_id": calls[0]["id"],
                         "content": SENTINEL_WEATHER}]}
        status, data = await post(session, url, hdrs, followup)

    if status != 200:
        return {"check": "tools", "verdict": "round-trip-error",
                "detail": str(data)[:160]}
    final = text_of(args.format, data)
    used = any(tok in final for tok in ("23", "sunny"))
    return {"check": "tools",
            "verdict": "round-trip-ok" if used else "result-ignored",
            "final_sample": final[:80]}


# ------------------------------------------------------------- multiturn check
FACTS = [("name", "Momo"), ("color", "teal"), ("city", "Lisbon")]


async def check_multiturn(session, args, key):
    url = endpoint(args.base_url, args.format)
    hdrs = headers_for(args.format, key)
    msgs = []
    for k, v in FACTS:
        msgs += [{"role": "user", "content": f"Remember: my favorite {k} is {v}."},
                 {"role": "assistant", "content": "Noted."}]
    msgs.append({"role": "user",
                 "content": "List every favorite I told you, exactly."})
    body = {"model": args.model, "max_tokens": args.max_tokens, "messages": msgs}
    status, data = await post(session, url, hdrs, body)
    if status != 200:
        return {"check": "multiturn", "verdict": "error", "detail": str(data)[:160]}
    final = text_of(args.format, data)
    recalled = [v for _, v in FACTS if v.lower() in final.lower()]
    verdict = ("context-intact" if len(recalled) == len(FACTS)
               else f"context-lossy {len(recalled)}/{len(FACTS)}")
    return {"check": "multiturn", "verdict": verdict, "recalled": recalled}


# ------------------------------------------------------------------ auth check
async def check_auth(session, args, key):
    rows = []
    for fmt in ("anthropic", "openai"):
        for scheme in ("x-api-key", "bearer"):
            url = endpoint(args.base_url, fmt)
            hdrs = headers_for(fmt, key, scheme)
            body = {"model": args.model, "max_tokens": 32,
                    "messages": [{"role": "user", "content": "Reply: ok"}]}
            try:
                status, _ = await post(session, url, hdrs, body)
            except aiohttp.ClientError as exc:
                rows.append({"endpoint": fmt, "scheme": scheme,
                             "result": f"transport {type(exc).__name__}"})
                continue
            rows.append({"endpoint": fmt, "scheme": scheme,
                         "result": "accepted" if status == 200 else f"http {status}"})
    asym = len({r["result"] for r in rows}) > 1
    return {"check": "auth", "verdict": "asymmetric" if asym else "uniform",
            "matrix": rows,
            "note": ("Some endpoint/scheme combos are rejected. Document which — "
                     "a wrong-header 401 often reads identically to a dead key."
                     if asym else "")}


# ------------------------------------------------------------------------ main
async def run(args, key):
    connector = aiohttp.TCPConnector(force_close=True, limit=4)
    timeout = aiohttp.ClientTimeout(total=args.timeout)
    async with aiohttp.ClientSession(connector=connector, timeout=timeout,
                                     trust_env=False) as session:
        out = []
        if args.check in ("system", "all"):
            out.append(await check_system(session, args, key))
        if args.check in ("tools", "all"):
            out.append(await check_tools(session, args, key))
        if args.check in ("multiturn", "all"):
            out.append(await check_multiturn(session, args, key))
        if args.check in ("auth", "all"):
            out.append(await check_auth(session, args, key))
        return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--key-env", required=True,
                    help="NAME of the env var holding the API key")
    ap.add_argument("--format", choices=["openai", "anthropic"],
                    default="anthropic",
                    help="Protocol used for system/tools/multiturn checks "
                         "(auth always tests both)")
    ap.add_argument("--check", choices=["system", "tools", "multiturn",
                                        "auth", "all"], default="all")
    ap.add_argument("--repeat", type=int, default=10,
                    help="Samples for the system canary. Delivery through "
                         "gateways is probabilistic; N=1 proves nothing")
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    ap.add_argument("--timeout", type=float, default=180)
    ap.add_argument("--output", help="Write full JSON results here")
    args = ap.parse_args()

    key = os.environ.get(args.key_env)
    if not key:
        print(f"CONFIG: env var {args.key_env} is empty/unset", file=sys.stderr)
        sys.exit(EXIT_CONFIG)

    results = asyncio.run(run(args, key))

    degraded = False
    for r in results:
        print(f"[{r['check']}] {r['verdict']}")
        if r["check"] == "system":
            print(f"  tokens without system: {r['input_tokens_without_system']}  "
                  f"with: {r['input_tokens_with_system_distinct']}"
                  f"{'  <- bimodal: mixed routing suspected' if r['bimodal_hint'] else ''}")
            if r["verdict"].startswith("intermittent"):
                print("  NOTE: delivery rate varies over time on routed gateways —"
                      " re-sample at another time before writing this up as a"
                      " steady state.")
        for key_ in ("note", "detail", "final_sample", "recalled"):
            if r.get(key_):
                print(f"  {key_}: {r[key_]}")
        ok_verdicts = {"delivered", "round-trip-ok", "context-intact",
                       "uniform", "asymmetric"}
        # auth "asymmetric" is a finding to document, not a failure.
        if r["verdict"] not in ok_verdicts:
            degraded = True

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump({"base_url": args.base_url, "model": args.model,
                       "format": args.format, "results": results},
                      fh, ensure_ascii=False, indent=1)
        print(f"\nWrote {args.output}")

    sys.exit(EXIT_DEGRADED if degraded else EXIT_OK)


if __name__ == "__main__":
    main()
