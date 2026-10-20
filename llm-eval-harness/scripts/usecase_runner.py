#!/usr/bin/env python3
"""Use-case runner — collect a model's answers to YOUR accumulated test cases.

This is the COLLECT half of the quality dimension. It reads a use-case library (a
JSON list of prompts you care about, kept OUTSIDE this skill bundle so it survives
skill updates and never leaks to a public repo), asks the model each one, and saves
every answer to a run directory. The JUDGE half is deliberately separate — see the
skill's quality workflow: spawn independent blind judges over these answers rather
than letting one grader (or the model itself) self-assess.

Why collect and judge are split: a single grader anchors. The reliable pattern (proven
on a real image-classification eval) is N independent judges that never see each
other's verdict, then compute precision / agreement across them — and only count an
explicit judgment, never "the judge stayed silent" (silence != consent).

Use-case library format (JSON list); only ``id`` and ``prompt`` are required:
    [
      {"id": "refund-window", "prompt": "...", "rubric": "1.0 if it cites the 30-day window",
       "expected": "optional reference answer", "tags": ["support"]},
      ...
    ]

Key passed by ENV VAR NAME, never on the CLI. thinking-aware: captures reasoning_content
separately so a reasoning model's chain-of-thought does not get mixed into the answer
being judged.

Usage
-----
    uv run --with openai python usecase_runner.py \
        --base-url https://api.example.com/v1 --model some-model --key-env MY_API_KEY \
        --usecases ~/.llm-eval/usecases.json \
        --output-dir ~/.llm-eval/runs/some-model
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from eval_result import capture_input, cli_main, add_result_arguments, execute_probe, unit

try:
    from openai import OpenAI
except ImportError:
    sys.exit("Missing dependency. Run via: uv run --with openai python usecase_runner.py ...")


def get_reasoning(message) -> str | None:
    rc = getattr(message, "reasoning_content", None) or getattr(message, "reasoning", None)
    if rc is None and getattr(message, "model_extra", None):
        rc = message.model_extra.get("reasoning_content") or message.model_extra.get("reasoning")
    return rc


def main():
    ap = argparse.ArgumentParser(description="Collect model answers to a use-case library")
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--key-env", required=True, help="NAME of the env var holding the API key")
    ap.add_argument("--usecases", required=True, help="path to use-case library JSON (keep it outside this bundle)")
    ap.add_argument("--output-dir", required=True, help="where to write answers (e.g. ~/.llm-eval/runs/<model>)")
    ap.add_argument("--max-tokens", type=int, default=2048)
    ap.add_argument("--temperature", type=float, default=0.3)
    ap.add_argument("--timeout", type=float, default=120)
    add_result_arguments(ap)
    args = ap.parse_args()
    if args.max_tokens <= 0 or args.timeout <= 0:
        ap.error("max-tokens and timeout must be positive")

    uc_path = os.path.expanduser(args.usecases)
    if not os.path.exists(uc_path):
        ap.error(f"Use-case library not found: {uc_path}")
    cases, snapshot = capture_input(args.usecases)
    if not isinstance(cases, list) or not cases:
        ap.error("Use-case library must be a non-empty JSON list.")

    if any(not isinstance(case, dict) for case in cases):
        ap.error("each use case must be an object")
    plan = [unit(f"case:{i}", "quality_case", i, case_id=str(case.get("id", i))) for i, case in enumerate(cases)]
    identity = {"model": args.model, "endpoint_kind": "base_url", "endpoint": args.base_url,
                "format": "openai", "auth": "bearer"}
    return execute_probe(args, "quality", identity, plan, lambda writer: collect(args, cases, writer), consumed_inputs={"usecases": snapshot})


def artifact_names(cases):
    """Reserve ordinary unique IDs before allocating collision-free fallback names."""
    ids = [str(case.get("id", i)) for i, case in enumerate(cases)]
    candidates = [f"{cid}.json" if Path(cid).name == cid and cid not in {".", ".."} else None for cid in ids]
    keys = [name.casefold() if name else None for name in candidates]
    reserved = {"_all_answers.json"}
    reserved.update(key for key in keys if key is not None and keys.count(key) == 1)
    assigned = set()
    result = []
    for index, name in enumerate(candidates):
        key = keys[index]
        if key is None or keys.count(key) != 1 or key == "_all_answers.json":
            name = f"case-{index}.json"
            suffix = 0
            while name.casefold() in reserved or name.casefold() in assigned:
                suffix += 1
                name = f"case-{index}-{suffix}.json"
        assigned.add(name.casefold())
        result.append(name)
    return result


def collect(args, cases, writer):
    api_key = os.environ.get(args.key_env, "").strip()
    if not api_key:
        raise ValueError(f"Env var {args.key_env} is empty or unset — export your key there first.")
    writer.redact(api_key)
    out_dir = writer.output_root
    os.makedirs(out_dir, mode=0o700, exist_ok=not bool(writer.path))
    client = OpenAI(api_key=api_key, base_url=args.base_url, timeout=args.timeout)

    print(f"# use-case runner  model={args.model}  cases={len(cases)}  → {out_dir}\n")
    collected = []
    filenames = artifact_names(cases)
    for idx, case in enumerate(cases):
        cid = str(case.get("id", idx))
        filename = filenames[idx]
        prompt = case.get("prompt")
        if not prompt:
            writer.skip_unit(f"case:{idx}")
            print(f"  {cid}: SKIP (no prompt)")
            continue
        uid = f"case:{idx}"
        writer.start_unit(uid)
        try:
            resp = client.chat.completions.create(
                model=args.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=args.max_tokens,
                temperature=args.temperature,
            )
            msg = resp.choices[0].message
            answer = msg.content or ""
            reasoning = get_reasoning(msg) or ""
            rec = {
                "id": cid, "prompt": prompt, "answer": answer,
                "finish_reason": resp.choices[0].finish_reason,
                "reasoning": reasoning,
                "rubric": case.get("rubric"), "expected": case.get("expected"),
                "tags": case.get("tags", []),
                "usage": resp.usage.model_dump() if getattr(resp, "usage", None) else None,
            }
            print(f"  {cid:24} {len(answer)} chars"
                  f"{'  (+reasoning)' if reasoning else ''}")
        except Exception as e:
            rec = {"id": cid, "prompt": prompt, "error": f"{type(e).__name__}: {writer.error_record(e)['message']}"}
            writer.fail_unit(uid, e)
            print(f"  {cid:24} ERROR {type(e).__name__}: {writer.error_record(e)['message']}")
        # Persist and bind bytes before admitting this observation as retained evidence.
        answer_path = out_dir / filename
        with answer_path.open("x" if writer.path else "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
        writer.bind_artifact(answer_path, role="answer", unit_id=uid)
        if "error" not in rec:
            writer.finish_unit(uid, {"case_id": cid, "answer_chars": len(answer),
                                    "reasoning_chars": len(reasoning), "finish_reason": rec["finish_reason"], "artifact": filename})
        collected.append(rec)

    summary_path = os.path.join(out_dir, "_all_answers.json")
    with open(summary_path, "x" if writer.path else "w", encoding="utf-8") as f:
        json.dump({"model": args.model, "base_url": args.base_url,
                   "collected_at": int(time.time()), "answers": collected}, f,
                  ensure_ascii=False, indent=2)
    writer.bind_artifact(summary_path, role="aggregate")
    writer.result["summary"] = {"model": args.model, "cases": len(cases), "collected": sum(bool(r.get("answer")) for r in collected)}
    ok = sum(1 for r in collected if "error" not in r)
    print(f"\n# collected {ok}/{len(collected)} answers → {summary_path}")
    print("# next: judge these with independent blind judges (see the skill's quality workflow),")
    print("#       NOT by asking the same model to grade itself.")


if __name__ == "__main__":
    sys.exit(cli_main(main))
