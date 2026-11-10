#!/usr/bin/env python3
"""Check local continuation context before a new dispatch; never call a provider."""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

BEGIN = "<!-- research-continuation:v1 -->"
END = "<!-- /research-continuation:v1 -->"
DISPOSITIONS = {"carry", "correct", "unknown", "excluded"}
REOPEN_KINDS = {"freshness", "counterevidence", "user-correction", "scope-change"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value


def reason(value, label):
    nonempty(value, label)
    if value.strip().casefold() in {"yes", "no", "true", "false", "unknown", "pending", "是", "否", "有", "无"}:
        raise ValueError(f"{label} needs a concrete explanation, not a yes/no flag")
    return value


def objects(value, label):
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(f"{label} must be a list of objects")
    return value


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def claims_at(path, content=None):
    result = {}
    for line in (path.read_text(encoding="utf-8") if content is None else content).splitlines():
        if not line.strip():
            raise ValueError(f"blank claim record: {path}")
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"claim record must be an object: {path}")
        key = row.get("claim_id")
        if not isinstance(key, str) or not re.fullmatch(r"C[0-9]+", key) or key in result:
            raise ValueError(f"invalid or duplicate claim ID in {path}")
        for field in ("text", "boundary"):
            nonempty(row.get(field), f"{path}:{key}.{field}")
        if row.get("status") not in {"supported", "contested", "unknown"}:
            raise ValueError(f"invalid claim status: {path}:{key}")
        result[key] = row
    return result


def study_lane(directory, lane_id):
    study = read_json(directory / "study.json")
    if not isinstance(study, dict):
        raise ValueError("study.json must be an object")
    if type(study.get("schema_version")) is not int or study["schema_version"] != 2:
        raise ValueError("new dispatch requires schema 2; historical reads need no continuation upgrade")
    lanes = objects(study.get("lanes"), "lanes")
    found = [row for row in lanes if row.get("lane_id") == lane_id]
    if len(found) != 1:
        raise ValueError(f"unknown or duplicate lane: {lane_id}")
    nonempty(found[0].get("prompt"), "lane.prompt")
    qids = set()
    for question in objects(study.get("decision_questions"), "decision_questions"):
        qid = nonempty(question.get("id"), "decision question id")
        nonempty(question.get("question"), "decision question text")
        if qid in qids:
            raise ValueError("duplicate decision question id")
        qids.add(qid)
    if found[0].get("task_id") not in qids:
        raise ValueError("lane references missing decision question")
    return study, found[0]


def prior_inputs(directory):
    """Follow only recorded locators, without scanning history or research trees."""
    required = set()
    current = directory / "claims.jsonl"
    if current.is_file() and claims_at(current):
        required.add(current.resolve())
    receipt = directory / "prior-research.json"
    if not receipt.exists():
        return required, None
    raw = receipt.read_bytes()
    prior = json.loads(raw.decode("utf-8"))
    if not isinstance(prior, dict):
        raise ValueError("prior-research.json must be an object")
    for row in objects(prior.get("matches"), "prior-research.matches"):
        if row.get("decision") not in {"reuse", "adapt", "reject"}:
            raise ValueError(f"undecided prior study: {row.get('study_id', '?')}")
        reason(row.get("reason"), "prior decision reason")
        if row["decision"] == "reject":
            continue
        catalog = Path(nonempty(prior.get("catalog"), "prior catalog"))
        if not catalog.is_absolute():
            catalog = directory / catalog
        target = (catalog.parent / nonempty(row.get("path"), "prior study path")).resolve()
        claims = target / "claims.jsonl"
        # Legacy reports remain leads; their quoted text must be bound explicitly.
        required.add(claims if claims.is_file() else target / "report.md")
    return required, digest(raw)


def compile_context(directory, study, lane):
    required, prior_hash = prior_inputs(directory)
    contract = study.get("continuation")
    if "continuation" not in study:
        if required:
            raise ValueError("continuation required: classify existing claims/prior research before dispatch")
        return None, digest(encoded({"mode": "initial", "prior_sha256": prior_hash,
                                     "task_id": lane.get("task_id")}))
    if not isinstance(contract, dict) or type(contract.get("schema_version")) is not int or contract["schema_version"] != 1:
        raise ValueError("continuation.schema_version must be 1")
    sources, paths, claim_sources = {}, {}, {}
    for row in objects(contract.get("sources"), "continuation.sources"):
        sid = nonempty(row.get("source_id"), "continuation source_id")
        if sid in sources:
            raise ValueError(f"duplicate continuation source_id: {sid}")
        rel = nonempty(row.get("path"), f"source {sid}.path")
        if Path(rel).is_absolute():
            raise ValueError(f"source {sid}.path must be relative to study directory")
        path = (directory / rel).resolve()
        if path in paths:
            raise ValueError(f"duplicate continuation source path: {rel}")
        if not path.is_file():
            raise ValueError(f"continuation source missing or changed: {sid}")
        raw = path.read_bytes()
        if row.get("sha256") != digest(raw):
            raise ValueError(f"continuation source missing or changed: {sid}")
        sources[sid] = {**row, "content": raw.decode("utf-8")}
        paths[path] = sid
        if path.name == "claims.jsonl":
            claim_sources[sid] = claims_at(path, sources[sid]["content"])
    missing = required - set(paths)
    if missing:
        raise ValueError("continuation missing existing source(s): " + ", ".join(str(p) for p in sorted(missing)))

    def quotation(binding, label):
        if not isinstance(binding, dict):
            raise ValueError(f"{label} must bind source_id and quote")
        sid = binding.get("source_id")
        if sid not in sources:
            raise ValueError(f"{label} references missing source")
        quote = nonempty(binding.get("quote"), f"{label}.quote")
        if quote not in sources[sid]["content"]:
            raise ValueError(f"{label} quote absent from source {sid}")
        return {"source_id": sid, "quote": quote}

    facts, seen, covered, used = [], set(), set(), set()
    for row in objects(contract.get("claims"), "continuation.claims"):
        cid = nonempty(row.get("context_id"), "continuation claim context_id")
        if cid in seen:
            raise ValueError(f"duplicate context_id: {cid}")
        seen.add(cid)
        sid = row.get("source_id")
        if sid not in sources:
            raise ValueError(f"context {cid} references missing source")
        action = row.get("disposition")
        if action not in DISPOSITIONS:
            raise ValueError(f"context {cid} missing valid disposition")
        if sid in claim_sources:
            key = row.get("claim_id")
            if key not in claim_sources[sid] or (sid, key) in covered:
                raise ValueError(f"context {cid} has missing or duplicate source claim")
            covered.add((sid, key))
            original = claim_sources[sid][key]
        else:
            quoted = quotation(row, f"context {cid}")
            original = {"text": quoted["quote"], "status": "unverified-lead",
                        "boundary": "Quoted archive text; not verified original-source evidence"}
        if action != "carry":
            reason(row.get("reason"), f"context {cid}.reason")
        if action == "unknown" and original["status"] not in {"unknown", "contested"}:
            raise ValueError(f"context {cid}: supported/legacy text cannot be downgraded to unknown; use evidence-bound correct")
        if action == "excluded":
            continue
        fact = {"context_id": cid, "source_id": sid, "disposition": action, "original": original}
        if action == "correct":
            correction = row.get("correction")
            proof = quotation(correction, f"context {cid}.correction")
            fact["correction"] = {**proof, "text": nonempty(correction.get("text"), f"context {cid}.correction.text")}
            fact["reason"] = row["reason"]
            used.add(proof["source_id"])
        elif action == "unknown":
            fact["reason"] = row["reason"]
        facts.append(fact)
        used.add(sid)
    unclassified = {(sid, key) for sid, rows in claim_sources.items() for key in rows} - covered
    if unclassified:
        raise ValueError("continuation unclassified claim(s): " + ", ".join(f"{sid}/{cid}" for sid, cid in sorted(unclassified)))
    # A selected legacy report cannot be bound by its path/hash alone.
    for path in required:
        sid = paths[path]
        if sid not in claim_sources and not any(row.get("source_id") == sid for row in contract["claims"]):
            raise ValueError(f"continuation needs quoted context from selected prior report: {sid}")

    questions, question_ids = [], set()
    study_questions = {row["id"]: row["question"] for row in objects(study.get("decision_questions"), "decision_questions")}
    for row in objects(contract.get("questions"), "continuation.questions"):
        qid = row.get("task_id")
        if qid not in study_questions or qid in question_ids:
            raise ValueError("continuation question has missing/duplicate task_id")
        question_ids.add(qid)
        if row.get("status") not in {"closed", "unknown"}:
            raise ValueError(f"question {qid} needs status closed or unknown")
        reason(row.get("reason"), f"question {qid}.reason")
        question = {**row, "question": study_questions[qid]}
        if "reopen" in row:
            reopen = row["reopen"]
            proof = quotation(reopen, f"question {qid}.reopen")
            if reopen.get("kind") not in REOPEN_KINDS:
                raise ValueError(f"question {qid} needs a concrete reopening kind")
            nonempty(reopen.get("as_of"), f"question {qid}.reopen.as_of")
            datetime.strptime(reopen["as_of"], "%Y-%m-%d")
            reason(reopen.get("reason"), f"question {qid}.reopen.reason")
            reason(reopen["quote"], f"question {qid}.reopen.quote")
            used.add(proof["source_id"])
        if qid == lane.get("task_id") and row["status"] == "closed" and not row.get("reopen"):
            raise ValueError(f"closed question {qid} cannot be researched again without evidence-bound reopening reason")
        questions.append(question)
    if question_ids != set(study_questions):
        raise ValueError("continuation missing question status: " + ", ".join(sorted(set(study_questions) - question_ids)))
    payload = {"instruction": "Use carried facts and corrections as the prior state. Research only the current unknowns or explicitly reopened question. A carried claim keeps its recorded evidence limits.",
               "task_id": lane["task_id"], "claims": facts, "questions": questions,
               "sources": [{k: v for k, v in sources[sid].items() if k != "content"} for sid in sorted(used)]}
    context_digest = digest(encoded({"continuation": contract, "prior_sha256": prior_hash,
                                     "questions": study_questions, "task_id": lane["task_id"]}))
    block = BEGIN + "\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n" + END
    return block, context_digest


def check_dispatch_context(directory, lane_id, prompt_file=None):
    """Read-only deterministic check; semantic relevance still requires a reader."""
    directory = Path(directory).resolve()
    study, lane = study_lane(directory, lane_id)
    block, context_digest = compile_context(directory, study, lane)
    prompt = lane["prompt"]
    if study.get("dispatch_context") and study["dispatch_context"] not in prompt:
        raise ValueError("lane.prompt omits the study dispatch_context")
    if block is not None and (prompt.count(BEGIN) != 1 or prompt.count(END) != 1 or block not in prompt):
        raise ValueError("lane.prompt missing or stale deterministic continuation body; run dispatch_context.py prepare")
    raw = prompt.encode("utf-8")
    if prompt_file is not None and Path(prompt_file).read_bytes() != raw:
        raise ValueError("--prompt-file bytes differ from exact lane.prompt")
    return {"status": "ready", "lane_id": lane_id, "mode": "continuation" if block else "initial",
            "prompt_sha256": digest(raw), "context_digest": context_digest,
            "semantic_completeness": "requires-original-source-review"}


def assemble_prompt(directory, study, lane):
    block, _ = compile_context(directory, study, lane)
    prompt = lane["prompt"]
    if BEGIN in prompt or END in prompt:
        if prompt.count(BEGIN) != 1 or prompt.count(END) != 1 or prompt.index(BEGIN) > prompt.index(END):
            raise ValueError("malformed existing continuation block")
        prompt = prompt[:prompt.index(BEGIN)].rstrip() + prompt[prompt.index(END) + len(END):]
    return prompt.rstrip() + "\n\n" + block if block else prompt


def render_prompt(directory, lane_id):
    directory = Path(directory).resolve()
    study, lane = study_lane(directory, lane_id)
    return assemble_prompt(directory, study, lane)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "render", "prepare"):
        sub = commands.add_parser(name, help={"check": "verify exact prompt/context; print only hashes",
                                             "render": "write prospective exact UTF-8 prompt to --output",
                                             "prepare": "put deterministic body in lane.prompt before dispatch"}[name])
        sub.add_argument("study_dir", type=Path)
        sub.add_argument("lane_id")
        if name == "check":
            sub.add_argument("--prompt-file", type=Path, help="require these exact UTF-8 bytes to match lane.prompt")
        if name == "render":
            sub.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    directory = args.study_dir.resolve()
    try:
        if args.command == "check":
            result = check_dispatch_context(directory, args.lane_id, args.prompt_file)
        elif args.command == "render":
            raw = render_prompt(directory, args.lane_id).encode("utf-8")
            args.output.write_bytes(raw)
            result = {"status": "rendered", "prompt_sha256": digest(args.output.read_bytes())}
        else:
            events = directory / "run-events.jsonl"
            if events.exists():
                for line in events.read_text(encoding="utf-8").splitlines():
                    event = json.loads(line)
                    if event.get("lane_id") == args.lane_id and event.get("state") in {"submitted", "running", "collected"}:
                        raise ValueError("preserve dispatched prompt; create a new follow-up lane instead")
            before = (directory / "study.json").read_bytes()
            study, lane = study_lane(directory, args.lane_id)
            lane["prompt"] = assemble_prompt(directory, study, lane)
            temp = directory / f".study-context-{os.getpid()}.json"
            try:
                temp.write_text(json.dumps(study, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                if (directory / "study.json").read_bytes() != before:
                    raise ValueError("study.json changed during preparation; reread and retry")
                os.replace(temp, directory / "study.json")
            finally:
                temp.unlink(missing_ok=True)
            result = check_dispatch_context(directory, args.lane_id)
        print(json.dumps(result, ensure_ascii=False))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"invalid dispatch context: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
