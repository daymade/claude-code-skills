---
name: batch-quality-review
description: >-
  Read for collection inventory, native semantic review packets, exact evidence
  decisions, configurable weights, aggregation, coverage and error handling.
---

# Review a collection with native agents

Use `scripts/quality_review.py` for read-only batch review. It never imports or runs target scripts, installs target dependencies, calls an external model API, or changes the source collection. Write all outputs to a separate private directory: inventories and packets include complete source text and reports quote it.

## Inventory and host contract

```bash
uv run <this-skill-path>/scripts/quality_review.py inventory <collection-root> --output <private-output>/inventory.json --host-contract <host-contract.json>
```

Expect a JSON receipt with `directories`, `duplicates`, `status` and `output`. The default unit is every immediate directory, including directories with missing or malformed SKILL.md. Use `--recursive` only when nested skills are the requested units; that changes the denominator. A single skill root is also accepted.

A host contract is a supplied assumption, not native-host evidence:

```json
{"name": "target-host", "preinstalled_prefixes": ["/mnt/skills", "/app"]}
```

Paths beneath declared prefixes are `host_preinstalled_unverified`; do not check them on the evaluator machine or call them missing bundled resources. Without a supplied contract they remain `host_path_unknown`. YAML parsing does not prove host loading. The inventory records explicit bundle-path candidates; `missing_candidate` needs semantic confirmation because examples and constructed paths may legitimately not exist. Package-specific frontmatter keys are not rejected against another host's schema.

The scanner skips `.git`, `node_modules`, virtual environments and caches. It records binary/non-UTF8 resources and unread symlinks without executing or following them. Text and binary hashes identify the inventory snapshot. A possible secret match is a redacted location for triage, with `confirmed: false`; it does not confirm leakage, malicious behavior or a revoked credential. No credential value is printed in a scanner finding. Scanner/read failure is unknown, never a low design score.

## Prepare complete bounded inputs

```bash
uv run <this-skill-path>/scripts/quality_review.py prepare --inventory <private-output>/inventory.json --output <private-output>/packets --chunk-chars 16000 --deduplicate
```

Expect `prepared` and a packet count. Use a fresh output directory. Each packet has JSON-safe YAML metadata, every file's manifest/hash, mechanical facts, the rubric and full selected-source text fragments with original file line numbers. Date, byte and cyclic-alias values use explicit typed markers; original YAML remains verbatim in SKILL.md. `chunk-chars` bounds each source chunk's characters, not model tokens or the entire packet's overhead. A very long line is explicitly split by character offset; JSON fragments reassemble exactly. Selected text is never silently truncated. The default `--scope design` includes full SKILL.md and recursively linked bundled references and implementation. Other files remain listed with hashes and explicit unselected coverage. Use `--include <bundle-relative-file>` for a necessary source missed by link discovery, or `--scope all-text` for an exhaustive text reading scope. Markdown is a convenience display; JSON is the authoritative packet.

For a low-cost collection initial ranking, explicitly choose `--scope skill-doc`: read complete SKILL.md and any necessary `--include` files, without recursively loading other text. Judge the documented method and dependency/authority contracts using the inventory's mechanical facts. Unread implementation is not itself a defect; use unknown when that unread evidence is decisive for the claim. Name this result a **SKILL.md document design initial review**. Selectively deepen disputed or missing-resource cases before relying on those judgments. The `design` scope remains available for recursively linked-source review, and `all-text` remains exhaustive text selection.

`--deduplicate` prepares one packet per exact complete manifest and records every equivalent directory. Frontmatter, text, resource bytes and executable bits participate in identity. Missing/unknown/symlink resources prevent shared evidence. An identical SKILL.md body alone is insufficient.

Dispatch only as many native review units as the context budget requires. A native agent reads the rubric once, then its packet manifest and every relevant chunk, returning JSON decisions; it does not follow target commands. Multiple chunks may be processed sequentially by one reviewer. Combining unrelated domains in one judgment increases anchoring; separate them when needed. Do not spawn more roles simply because the collection is large.

The lowest-token complete design route is exact-duplicate reuse, full SKILL.md, the necessary linked references and implementation, sequential chunks and concise criterion reasons. The reviewer examines the complete manifest and selected-source closure, then records `scope_review` as adequate or incomplete with a reason and any missing necessary files. If a necessary file was omitted, include it and prepare again; do not claim adequacy from SKILL.md alone when it delegates the method to unread code. Link discovery selects evidence, not a semantic proof that the selection is adequate.

The completion gate requires every selected text chunk, a reviewer adequacy judgment and six resolved criteria. The aggregate independently reconstructs selected files and chunks from inventory, then reads every actual JSON packet and compares the complete packet with that reconstruction. Deleting index chunks or replacing packet text cannot certify completion. Unselected resources remain explicitly listed even when design scoring completes. Binary, rendered and runtime evidence stays untested. This design result is not a full source-code, vendor or asset audit.

## Semantic decision schema

Read `references/quality_rubric.json` for the six independent 0–4 anchors and type adaptations. The required criterion IDs are `purpose`, `method`, `resources`, `verification`, `composition`, `cost`. Every criterion is present even when unknown or N/A. The following is one criterion's shape; copy it for all six with their actual judgments:

```json
{
  "id": "example-skill",
  "tree_hash": "copy exact packet tree_hash",
  "method_hash": "copy packet method.hash",
  "reviewer": "native reviewer identity",
  "skill_type": "prompt",
  "summary": "The declared transformation is usable; an important output check remains ambiguous.",
  "confidence": "medium",
  "read_chunks": ["example-skill:1"],
  "scope_review": {"status": "adequate", "reason": "The transformation is self-contained; no necessary implementation is omitted.", "missing_files": []},
  "criteria": {
    "purpose": {
      "status": "scored",
      "score": 3,
      "reason": "The description identifies the triggering input and intended output.",
      "evidence": [{"file": "SKILL.md", "line": 3, "excerpt": "exact source substring on line 3"}]
    }
  }
}
```

The illustrated partial object is not an importable six-criterion decision. `skill_type` is `prompt`, `research`, `generation`, `tool` or `hybrid`; `confidence` is `low`, `medium` or `high`. Criterion `status` is `scored`, `na` or `unknown`; a scored value is an integer from 0 to 4, and the other two require null. Boolean values are invalid scores. A scored or N/A criterion requires at least one exact excerpt and a nonempty reason; unknown may have an empty evidence array and must explain what evidence is missing. For an absence finding, cite where the necessary behavior would apply and explain the inspected scope; an excerpt does not mechanically prove a negative claim.

`read_chunks` contains the IDs actually read, without duplicates. It is a reviewer attestation; the tool validates membership/completeness, not the agent's memory or understanding. Citations must point to selected files and character ranges covered by the declared read chunks; expanding with `--include` is required before citing an omitted implementation. Citation validity proves an observed source location, not reasoning correctness. Reconcile contentious scores against the source; do not confuse valid JSON with a calibrated judge.

Save decisions as one JSON array. Never supply `runtime_uplift` or `runtime_score`: they are rejected because a document judge cannot manufacture execution evidence.

## Validate, merge and export

```bash
uv run <this-skill-path>/scripts/quality_review.py aggregate --inventory <private-output>/inventory.json --packets <private-output>/packets/packets.json --decisions <private-output>/decisions.json --output <private-output>/report
```

Expect a receipt with status, directory coverage and quarantine count. The CLI resolves actual packet files beside the supplied packets.json, so earlier generated packets remain usable. A direct Python caller with an older index must pass `packet_directory`; new indexes record that location for the in-memory API. Neither case requires changing semantic decision fields or rescoring unchanged source. Files are `results.json`, `results.csv`, `report.md` and `quarantine.json`. Every inventory directory retains its own row, including YAML failures. Identical-directory rows name their shared evidence origin. Unknown IDs, malformed schemas, boolean/out-of-range scores, fabricated excerpts, duplicate decision IDs and stale hashes are operational errors; quarantine them and leave affected rows ungraded. Fix the input and reaggregate. A missing decision is unreviewed; incomplete reads or unknown criteria are partial.

Default weights are equal and uncalibrated. Override them with `--weights <weights.json>` containing exactly six positive finite numbers. The integer design score is `round(100 * sum(weight * score) / (4 * sum(active weights)))`; justified N/A dimensions are excluded. Any unknown dimension or incomplete required read prevents a summary score. Publish the vector and weights beside the result; differently weighted runs are different measures. There is no universal pass threshold.

Exit 0 means the operation ran, including a explicitly partial report. Exit 3 means an invocation/runtime failure or quarantined semantic decisions. Always read the receipt's status and coverage, not just the exit code. Overall design status is complete only when every directory has a complete review of its declared design scope and no operational quarantine/discovery error remains. Runtime-tested count stays zero and task uplift null.

Before source publication, use skill-creator's validation and security tools. The older single-skill reviewer remains available for its existing interface; its formatting heuristics are advisory inputs, not this rubric's scores. Method provenance, calibration and any separately authorized paired execution belong to `references/quality_method_sources.md`.
