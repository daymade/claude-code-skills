#!/usr/bin/env python3
"""LLM speed probe — TTFT + thinking-aware decode throughput (OpenAI-compatible endpoints).

Why this exists
---------------
Reasoning models (o1 / DeepSeek-R1 / QwQ / many "flash" variants) stream their
thinking in a separate ``reasoning_content`` delta field, but ``completion_tokens``
counts that thinking too. If you only collect ``content`` yet divide by
``completion_tokens``, the throughput number is badly wrong — in one real run a
~750 tok/s model measured as 4700 tok/s because the thinking tokens arrived in a
burst the naive math attributed to a fraction of a second.

This probe captures reasoning AND content, takes TTFT as the first token of EITHER
kind, and computes decode throughput as ``completion_tokens / (total - ttft)``.

Two further traps this version handles (both cost real measurements before they were fixed)
-------------------------------------------------------------------------------------------
- **Server-reported decode speed wins.** Some endpoints — especially those using
  speculative decoding (e.g. DFlash) — expose a ``pd`` block inside ``usage`` carrying
  the GROUND-TRUTH GPU decode rate (``decode_tokens_per_second``). That is more
  authoritative than ANY client-side timing, because the client only sees when token
  batches *arrive*, not when they were generated. The probe prefers it when present.
- **Batch-flush inflates client throughput.** If the server flushes many tokens per
  SSE chunk (speculative decoding / buffering) instead of one-at-a-time, the
  client-measured ``(total - ttft)`` is compressed and client throughput reads ~2× too
  high. The probe counts tokens-per-chunk and warns when the stream is batch-flushed —
  in that case trust the server value, or fall back to end-to-end throughput.

Two modes (run ``both``):
- ``mixed``  : a few representative tasks — what real usage feels like.
- ``decode`` : forces one long deterministic output to push the sustained ceiling.

Key handling: passed by ENV VAR NAME (``--key-env``), never on the CLI.

Usage
-----
    uv run --with openai python speed_probe.py \
        --base-url https://api.example.com/v1 \
        --model some-model --key-env MY_API_KEY --mode both
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

try:
    from openai import OpenAI
except ImportError:
    sys.exit("Missing dependency. Run via: uv run --with openai python speed_probe.py ...")


DEFAULT_PROMPTS = [
    ("long-form", "Write an ~800-word explainer on how black holes form, their main "
                  "properties, and how they curve nearby spacetime. Clear, well-structured prose.", 2048),
    ("code", "Implement an LRU cache class in Python with O(1) get and put using a "
             "doubly linked list plus a hash map, with a short self-test.", 2048),
    ("reasoning", "Two inlet pipes fill a tank in 4 and 6 hours respectively; a drain "
                  "empties it in 3 hours. All three open at once on an empty tank — how "
                  "long to fill it? Reason step by step and give the answer as a fraction.", 1024),
]

DECODE_PROMPT = ("Throughput test. Output every integer from 1 to 1200 separated by single "
                 "spaces, on one line. No commentary, no line breaks, start at 1 immediately.")


def extract_reasoning(delta) -> str | None:
    rc = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
    if rc is None and getattr(delta, "model_extra", None):
        rc = delta.model_extra.get("reasoning_content") or delta.model_extra.get("reasoning")
    return rc


def extract_server_decode(usage):
    """Some endpoints report ground-truth decode speed in a non-standard `pd` block.
    Returns (decode_tokens_per_second, mean_accept_length) or (None, None)."""
    if not usage:
        return None, None
    pd = getattr(usage, "pd", None)
    if pd is None and getattr(usage, "model_extra", None):
        pd = usage.model_extra.get("pd")
    if isinstance(pd, dict):
        return pd.get("decode_tokens_per_second"), pd.get("mean_accept_length")
    return None, None


def _estimate_tokens(text: str):
    try:
        import tiktoken
        return len(tiktoken.get_encoding("o200k_base").encode(text)), "o200k-est"
    except Exception:
        return int(len(text) / 1.6), "char-est"


def run_one(client, model, prompt, max_tokens, temperature, use_usage):
    t0 = time.perf_counter()
    ttft_any = None
    ttft_content = None
    reasoning_parts, content_parts = [], []
    chunk_count = 0          # content-bearing chunks — reveals batch-flush vs per-token streaming
    usage = None
    kwargs = dict(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    if use_usage:
        kwargs["stream_options"] = {"include_usage": True}

    stream = client.chat.completions.create(**kwargs)
    for chunk in stream:
        now = time.perf_counter()
        if chunk.choices:
            delta = chunk.choices[0].delta
            rc = extract_reasoning(delta)
            if rc:
                if ttft_any is None:
                    ttft_any = now - t0
                reasoning_parts.append(rc)
            if delta and delta.content:
                if ttft_any is None:
                    ttft_any = now - t0
                if ttft_content is None:
                    ttft_content = now - t0
                content_parts.append(delta.content)
            if rc or (delta and delta.content):
                chunk_count += 1
        if getattr(chunk, "usage", None):
            usage = chunk.usage
    t1 = time.perf_counter()

    reasoning = "".join(reasoning_parts)
    content = "".join(content_parts)
    total = t1 - t0
    decode = total - (ttft_any or 0)
    if usage and getattr(usage, "completion_tokens", None):
        out_tok, tok_src = usage.completion_tokens, "usage"
        reasoning_tok = getattr(getattr(usage, "completion_tokens_details", None),
                                "reasoning_tokens", None)
    else:
        out_tok, tok_src = _estimate_tokens(reasoning + content)
        reasoning_tok = None

    server_tps, server_accept = extract_server_decode(usage)
    client_tps = round(out_tok / decode, 1) if (out_tok and decode > 0) else None
    # ~1 tok/chunk = true per-token streaming; >>1 = batch-flush (inflates client_tps)
    tok_per_chunk = round(out_tok / chunk_count, 1) if (out_tok and chunk_count) else None
    batch_flushed = tok_per_chunk is not None and tok_per_chunk > 3

    return {
        "ttft_first_s": round(ttft_any, 3) if ttft_any is not None else None,
        "ttft_content_s": round(ttft_content, 3) if ttft_content is not None else None,
        "total_s": round(total, 3),
        "decode_s": round(decode, 3),
        "output_tokens": out_tok,
        "token_source": tok_src,
        "reasoning_tokens": reasoning_tok,
        "reasoning_chars": len(reasoning),
        "content_chars": len(content),
        "chunks": chunk_count,
        "tokens_per_chunk": tok_per_chunk,
        "batch_flushed": batch_flushed,
        "client_decode_tps": client_tps,
        "server_decode_tps": server_tps,
        "server_mean_accept_length": server_accept,
        # the number to report: server value if available, else client (caveat batch_flushed)
        "decode_tps": server_tps if server_tps else client_tps,
        "e2e_tps": round(out_tok / total, 1) if (out_tok and total > 0) else None,
        "truncated": out_tok is not None and out_tok >= max_tokens,
    }


def detect_usage_support(client, model) -> bool:
    """Probe once whether the endpoint accepts stream_options.include_usage.

    NOTE: this fires one small warm-up call before the real probes — on a hard
    rate-limited endpoint it costs one request slot. It's worth it to avoid a 400 on
    endpoints that reject stream_options.
    """
    try:
        for _ in client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": "hi"}],
            max_tokens=4, stream=True, stream_options={"include_usage": True},
        ):
            pass
        return True
    except Exception as e:
        if "stream_options" in str(e) or "include_usage" in str(e):
            return False
        # Not a stream_options issue (auth/transport/etc.). Warn instead of silently
        # assuming support, so the real cause isn't masked until the first real probe.
        print(f"[warn] usage-support probe hit {type(e).__name__}; assuming usage supported — "
              f"the real probe below will surface any auth/transport problem.")
        return True


def _fmt_line(prefix, r):
    srv = f"  server={r['server_decode_tps']} tok/s" if r["server_decode_tps"] else ""
    flush = f"  ⚠batch-flush({r['tokens_per_chunk']}tok/chunk→client inflated)" if r["batch_flushed"] else ""
    return (f"{prefix} TTFT={r['ttft_first_s']}s  e2e={r['total_s']}s  out={r['output_tokens']}tok  "
            f"client={r['client_decode_tps']} tok/s{srv}{flush}"
            f"{'  [TRUNCATED]' if r['truncated'] else ''}")


def main():
    ap = argparse.ArgumentParser(description="LLM speed probe (TTFT + thinking-aware throughput)")
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--key-env", required=True, help="NAME of the env var holding the API key")
    ap.add_argument("--mode", choices=["mixed", "decode", "both"], default="both")
    ap.add_argument("--repeat", type=int, default=3, help="decode-mode rounds (peak reported)")
    ap.add_argument("--max-tokens", type=int, default=4096, help="decode-mode max_tokens")
    ap.add_argument("--temperature", type=float, default=0.6)
    ap.add_argument("--prompts-file", help="JSON list of [label, prompt, max_tokens] to override mixed tasks")
    ap.add_argument("--timeout", type=float, default=180)
    ap.add_argument("--output", help="write full JSON results here")
    args = ap.parse_args()

    api_key = os.environ.get(args.key_env)
    if not api_key:
        sys.exit(f"Env var {args.key_env} is empty or unset — export your key there first.")

    client = OpenAI(api_key=api_key, base_url=args.base_url, timeout=args.timeout)
    use_usage = detect_usage_support(client, args.model)

    report = {"base_url": args.base_url, "model": args.model, "usage_supported": use_usage,
              "mixed": [], "decode": []}
    print(f"# speed probe  model={args.model}  usage={'native' if use_usage else 'estimated'}\n")

    if args.mode in ("mixed", "both"):
        prompts = DEFAULT_PROMPTS
        if args.prompts_file:
            with open(args.prompts_file) as f:
                prompts = [tuple(x) for x in json.load(f)]
        print("## mixed (representative tasks)")
        for label, prompt, mx in prompts:
            try:
                r = run_one(client, args.model, prompt, mx, args.temperature, use_usage)
            except Exception as e:
                print(f"  {label}: ERROR {type(e).__name__}: {e}")
                report["mixed"].append({"label": label, "error": str(e)})
                continue
            r["label"] = label
            print(_fmt_line(f"  {label:12}", r))
            report["mixed"].append(r)

    if args.mode in ("decode", "both"):
        print("\n## decode (sustained ceiling, peak of N rounds)")
        peaks = []
        for i in range(1, args.repeat + 1):
            try:
                r = run_one(client, args.model, DECODE_PROMPT, args.max_tokens, 0.0, use_usage)
            except Exception as e:
                print(f"  round {i}: ERROR {type(e).__name__}: {e}")
                continue
            print(_fmt_line(f"  round {i}:", r))
            report["decode"].append(r)
            if r["decode_tps"]:
                peaks.append(r["decode_tps"])
        if peaks:
            report["decode_peak_tps"] = max(peaks)
            report["decode_avg_tps"] = round(sum(peaks) / len(peaks), 1)
            print(f"  → decode peak {max(peaks)} / avg {report['decode_avg_tps']} tok/s")

    all_runs = report["mixed"] + report["decode"]
    print("\n# summary")
    srv_vals = [r["server_decode_tps"] for r in all_runs if r.get("server_decode_tps")]
    any_flush = any(r.get("batch_flushed") for r in all_runs)
    if srv_vals:
        print(f"  server-reported decode (authoritative): {min(srv_vals)}–{max(srv_vals)} tok/s")
    if report.get("decode_peak_tps"):
        src = "server" if srv_vals else "client"
        print(f"  sustained decode ceiling ({src}): {report['decode_peak_tps']} tok/s (compare to vendor claim)")
    e2e = [r["e2e_tps"] for r in report["mixed"] if r.get("e2e_tps")]
    if e2e:
        print(f"  end-to-end throughput (what callers feel): {min(e2e)}–{max(e2e)} tok/s")
    ttfts = [r["ttft_first_s"] for r in report["mixed"] if r.get("ttft_first_s")]
    if ttfts:
        print(f"  TTFT (first token): {min(ttfts)}–{max(ttfts)} s")
    if any_flush:
        print("  ⚠ endpoint BATCH-FLUSHES the stream (speculative decoding / buffering):")
        print("    client-side decode tok/s is INFLATED — do NOT report it as the model's speed.")
        if srv_vals:
            print("    → use the server-reported decode value above as the real decode speed.")
        else:
            print("    → no server decode field found; report END-TO-END throughput instead,")
            print("      and treat any client-side 'decode ceiling' as an upper-bound artifact.")
    if any(r.get("reasoning_chars", 0) > 50 for r in report["mixed"]):
        print("  note: model emits thinking — e2e latency includes reasoning time, not just typing")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"  full JSON → {args.output}")


if __name__ == "__main__":
    main()
