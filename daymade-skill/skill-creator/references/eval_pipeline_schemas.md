# Eval Pipeline JSON Schemas

This document defines the JSON schemas used by skill-creator's evaluation pipeline (evals, grading, benchmark, feedback).

**Coverage rule:** when a new pipeline artifact is introduced — or an existing one gains a second consumer — pin its canonical location and each consumer's lookup behavior here. Two scripts relying on an undocumented location convention is a bug waiting for a user report (#443: the aggregator and the viewer disagreed on `eval_metadata.json`'s directory level until the convention was pinned in this document).

## Contents

- **evals.json** — test case definitions (prompts, expected output, assertions)
- **eval_metadata.json** — per-eval-case prompt/metadata consumed by both the aggregator and the viewer
- **history.json** — description optimization loop history
- **grading.json** — per-run assertion results (viewer depends on exact field names)
- **metrics.json** — per-run quantitative metrics
- **timing.json** — token/duration data captured from task notifications
- **benchmark.json** — aggregated cross-configuration comparison (viewer input)
- **comparison.json** — blind A/B comparison verdicts
- **analysis.json** — analyst-pass observations over benchmark data

---

## evals.json

Defines the evals for a skill. Located at `evals/evals.json` within the skill directory.

```json
{
  "skill_name": "example-skill",
  "evals": [
    {
      "id": 1,
      "prompt": "User's example prompt",
      "expected_output": "Description of expected result",
      "files": ["evals/files/sample1.pdf"],
      "expectations": [
        "The output includes X",
        "The skill used script Y"
      ]
    }
  ]
}
```

**Fields:**
- `skill_name`: Name matching the skill's frontmatter
- `evals[].id`: Unique integer identifier
- `evals[].prompt`: The task to execute
- `evals[].expected_output`: Human-readable description of success
- `evals[].files`: Optional list of input file paths (relative to skill root)
- `evals[].expectations`: List of verifiable statements

---

## eval_metadata.json

Per-test-case prompt and metadata for one eval directory. Located at `<workspace>/iteration-N/eval-<name>/eval_metadata.json` — write exactly one copy, at the eval-directory level.

**Consumers (which script reads it where):**
- `scripts/aggregate_benchmark.py` reads it at the eval-directory level only (`eval_dir / "eval_metadata.json"`).
- `eval-viewer/generate_review.py` probes `<run-dir>/eval_metadata.json`, then `<run-dir>/../eval_metadata.json`, then the eval-directory level, using the first candidate that yields a prompt. The documented paired-pipeline layout needs only the eval-directory copy; a run whose prompt shows `(No prompt found)` got no prompt from any of the three levels (and its `transcript.md` fallback also came up empty).

```json
{
  "eval_id": 0,
  "eval_name": "descriptive-name-here",
  "prompt": "The user's task prompt",
  "assertions": []
}
```

**Fields:**
- `eval_id`: Integer identifier. When the file or field is missing, the aggregator derives an id from the `eval-<N>` directory name or enumeration order, and the viewer sorts such runs last
- `eval_name`: Descriptive name for the eval directory and viewer labels
- `prompt`: The task prompt shown in the viewer
- `assertions`: List of verifiable statements; may be written empty at run time and filled in while runs are in progress

---

## history.json

Tracks version progression in Improve mode. Located at workspace root.

```json
{
  "started_at": "2026-01-15T10:30:00Z",
  "skill_name": "pdf",
  "current_best": "v2",
  "iterations": [
    {
      "version": "v0",
      "parent": null,
      "expectation_pass_rate": 0.65,
      "grading_result": "baseline",
      "is_current_best": false
    },
    {
      "version": "v1",
      "parent": "v0",
      "expectation_pass_rate": 0.75,
      "grading_result": "won",
      "is_current_best": false
    },
    {
      "version": "v2",
      "parent": "v1",
      "expectation_pass_rate": 0.85,
      "grading_result": "won",
      "is_current_best": true
    }
  ]
}
```

**Fields:**
- `started_at`: ISO timestamp of when improvement started
- `skill_name`: Name of the skill being improved
- `current_best`: Version identifier of the best performer
- `iterations[].version`: Version identifier (v0, v1, ...)
- `iterations[].parent`: Parent version this was derived from
- `iterations[].expectation_pass_rate`: Pass rate from grading
- `iterations[].grading_result`: "baseline", "won", "lost", or "tie"
- `iterations[].is_current_best`: Whether this is the current best version

---

## grading.json

Output from the grader agent. Located at `<run-dir>/grading.json`.

```json
{
  "expectations": [
    {
      "text": "The output includes the name 'John Smith'",
      "passed": true,
      "evidence": "Found in transcript Step 3: 'Extracted names: John Smith, Sarah Johnson'"
    },
    {
      "text": "The spreadsheet has a SUM formula in cell B10",
      "passed": false,
      "evidence": "No spreadsheet was created. The output was a text file."
    },
    {
      "text": "The extracted names match the supplied source",
      "passed": true,
      "evidence": "Both extracted names match the supplied source records."
    }
  ],
  "summary": {
    "passed": 2,
    "failed": 1,
    "total": 3,
    "pass_rate": 0.67
  },
  "execution_metrics": {
    "tool_calls": {
      "Read": 5,
      "Write": 2,
      "Bash": 8
    },
    "total_tool_calls": 15,
    "total_steps": 6,
    "errors_encountered": 0,
    "output_chars": 12450,
    "transcript_chars": 3200
  },
  "timing": {
    "total_tokens": 84852,
    "time_scope": "executor_and_grader",
    "token_scope": "executor",
    "executor_duration_seconds": 165.0,
    "grader_duration_seconds": 26.0,
    "total_duration_seconds": 191.0
  },
  "claims": [
    {
      "claim": "The form has 12 fillable fields",
      "type": "factual",
      "verified": true,
      "evidence": "Counted 12 fields in field_info.json"
    }
  ],
  "user_notes_summary": {
    "uncertainties": ["Used 2023 data, may be stale"],
    "needs_review": [],
    "workarounds": ["Fell back to text overlay for non-fillable fields"]
  },
  "eval_feedback": {
    "suggestions": [
      {
        "assertion": "The output includes the name 'John Smith'",
        "reason": "A hallucinated document that mentions the name would also pass"
      }
    ],
    "overall": "Assertions check presence but not correctness."
  }
}
```

**Fields:**
- `expectations[]`: Graded expectations with evidence
- `summary`: Aggregate pass/fail counts
- `execution_metrics`: Tool usage and output size (from executor's metrics.json)
- `timing`: Wall clock timing (from timing.json)
- `claims`: Extracted and verified claims from the output
- `user_notes_summary`: Issues flagged by the executor
- `eval_feedback`: (optional) Improvement suggestions for the evals, only present when the grader identifies issues worth raising

Recompute `passed`, `failed` and `total` from the non-empty expectations.
Supply boolean verdicts and non-empty `text`/`evidence` strings. Keep `pass_rate`
within 0–1 and equal to `passed/total` (two-decimal rounding is accepted).
The aggregator treats missing, malformed, empty or inconsistent grades as unknown;
it retains their run directories and withholds comparison deltas.

---

## metrics.json

Output from the executor agent. Located at `<run-dir>/outputs/metrics.json`.

```json
{
  "tool_calls": {
    "Read": 5,
    "Write": 2,
    "Bash": 8,
    "Edit": 1,
    "Glob": 2,
    "Grep": 0
  },
  "total_tool_calls": 18,
  "total_steps": 6,
  "files_created": ["filled_form.pdf", "field_values.json"],
  "errors_encountered": 0,
  "output_chars": 12450,
  "transcript_chars": 3200
}
```

**Fields:**
- `tool_calls`: Count per tool type
- `total_tool_calls`: Sum of all tool calls
- `total_steps`: Number of major execution steps
- `files_created`: List of output files created
- `errors_encountered`: Number of errors during execution
- `output_chars`: Total character count of output files
- `transcript_chars`: Character count of transcript

---

## timing.json

Wall clock timing for a run. Located at `<run-dir>/timing.json`.

**How to capture:** Save actual host-reported usage and duration when the host exposes
them. Do not assume every host emits the same task notification or can recover it
later. Keep unavailable fields absent or null; an observed zero is a real measurement.
Create the run directory before execution so an interrupted attempt remains visible.

```json
{
  "total_tokens": 84852,
  "duration_ms": 191000,
  "total_duration_seconds": 191.0,
  "time_scope": "executor_and_grader",
  "token_scope": "executor",
  "executor_start": "2026-01-15T10:30:00Z",
  "executor_end": "2026-01-15T10:32:45Z",
  "executor_duration_seconds": 165.0,
  "grader_start": "2026-01-15T10:32:45Z",
  "grader_end": "2026-01-15T10:33:11Z",
  "grader_duration_seconds": 26.0
}
```

Use `time_scope` to name the measured boundary, for example `executor`,
`executor_and_grader` or `end_to_end`; use `token_scope` for whose actual usage
was counted. Omitted scopes remain `unspecified`, preserving legacy records.
An unspecified duration is not evidence of user end-to-end delivery time.
Record task receipt through the declared completed delivery when claiming that
result; keep evaluation overhead separate. Do not sum overlapping durations or
copy a subagent duration into an end-to-end scope.

The aggregator reads `timing.json` and `grading.json.timing` independently for
`total_tokens` and `total_duration_seconds`. Accept `duration_ms / 1000` only when
that source lacks `total_duration_seconds`. Preserve each metric's source field
and scope; conflicting duplicate observations or scopes become unknown.
Never substitute `output_chars`, `tool_calls` or missing values for token usage.

---

## benchmark.json

Output from Benchmark mode. Located at `benchmarks/<timestamp>/benchmark.json`.

```json
{
  "metadata": {
    "skill_name": "pdf",
    "skill_path": "/path/to/pdf",
    "executor_model": "claude-sonnet-4-20250514",
    "analyzer_model": "most-capable-model",
    "timestamp": "2026-01-15T10:30:00Z",
    "evals_run": [1, 2, 3],
    "runs_per_configuration": 3
  },

  "runs": [
    {
      "eval_id": 1,
      "eval_name": "Ocean",
      "configuration": "with_skill",
      "run_number": 1,
      "result": {
        "pass_rate": 0.85,
        "passed": 6,
        "failed": 1,
        "total": 7,
        "time_seconds": 42.5,
        "tokens": 3800,
        "tool_calls": 18,
        "errors": 0
      },
      "expectations": [
        {"text": "...", "passed": true, "evidence": "..."}
      ],
      "notes": [
        "Used 2023 data, may be stale",
        "Fell back to text overlay for non-fillable fields"
      ]
    }
  ],

  "run_summary": {
    "with_skill": {
      "pass_rate": {"mean": 0.85, "stddev": 0.05, "min": 0.80, "max": 0.90},
      "time_seconds": {"mean": 45.0, "stddev": 12.0, "min": 32.0, "max": 58.0},
      "tokens": {"mean": 3800, "stddev": 400, "min": 3200, "max": 4100}
    },
    "without_skill": {
      "pass_rate": {"mean": 0.35, "stddev": 0.08, "min": 0.28, "max": 0.45},
      "time_seconds": {"mean": 32.0, "stddev": 8.0, "min": 24.0, "max": 42.0},
      "tokens": {"mean": 2100, "stddev": 300, "min": 1800, "max": 2500}
    },
    "delta": {
      "pass_rate": "+0.50",
      "time_seconds": "+13.0",
      "tokens": "+1700"
    }
  },

  "notes": [
    "Assertion 'Output is a PDF file' passes 100% in both configurations - may not differentiate skill value",
    "Eval 3 shows high variance (50% ± 40%) - may be flaky or model-dependent",
    "Without-skill runs consistently fail on table extraction expectations",
    "Skill adds 13s average execution time but improves pass rate by 50%"
  ]
}
```

**Fields:**
- `metadata`: Information about the benchmark run
  - `skill_name`: Name of the skill
  - `timestamp`: When the benchmark was run
  - `evals_run`: List of eval names or IDs
  - `runs_per_configuration`: Number of runs per config (e.g. 3)
- `runs[]`: Individual run results
  - `eval_id`: Numeric eval identifier
  - `eval_name`: Human-readable eval name (used as section header in the viewer)
  - `configuration`: Configuration directory name. Use `with_skill` or `new_skill`
    for the candidate and `old_skill` or `without_skill` for the baseline.
  - `run_number`: Integer run number (1, 2, 3...)
  - `result`: Nested object with `pass_rate`, `passed`, `total`, `time_seconds`, `tokens`, `errors`
- `run_summary`: Statistical aggregates per configuration
  - `with_skill` / `without_skill`: Each contains `pass_rate`, `time_seconds`, `tokens` objects with `mean` and `stddev` fields
  - `delta`: Difference strings like `"+0.50"`, `"+13.0"`, `"+1700"`
- `notes`: Freeform observations from the analyzer

**Important:** The viewer reads these field names exactly. Using `config` instead of `configuration`, or putting `pass_rate` at the top level of a run instead of nested under `result`, will cause the viewer to show empty/zero values. Always reference this schema when generating benchmark.json manually.

### Coverage, roles and unknown values

Retain the numeric legacy fields for healthy data. Use JSON `null` for unknown
run metrics and empty statistical aggregates, not zero. The aggregator adds:

- `runs[].run_id`: Observed run directory relative to the benchmark root.
- `runs[].grading_status`: `graded`, `missing_grading` or `invalid_grading`.
- `runs[].issues`: Missing/invalid input diagnoses; retain these when interpreting results.
- `runs[].metric_sources` / `metric_scopes`: Source fields and boundaries for
  `time_seconds` and `tokens`; use null when the value is unknown.
- `runs[].result.output_chars`: Output characters as a separate measurement.
- `run_summary.<configuration>.<metric>.count` / `total`: Observed values / observed
  attempt directories. Means summarize known values only; report this coverage.
- `metadata.attempts_per_configuration` / `runs_per_eval`: Actual observed directory
  counts. Set `runs_per_configuration` to the common per-eval/configuration count
  only when every observed eval has every configuration with that count; otherwise null.
- `comparison`: Explicit `candidate`, `baseline`, `status` (`complete`, `incomplete`
  or `unbound`), `paired_runs`, `unmatched_runs`, `issues`, and per-metric `status`,
  `paired_count`, `total_pairs`, `scope`.

Bind exactly one known candidate and one known baseline automatically. If role names
are custom or ambiguous, supply both flags to the existing aggregator:

```bash
uv run --frozen python -m scripts.aggregate_benchmark <benchmark-dir> \
  --candidate <candidate-config> --baseline <baseline-config>
```

Match runs by `(eval_id, run_number)`; reject duplicate/invalid identities for
comparison. Compute candidate-minus-baseline deltas from those pairs, never from
directory order or unmatched configuration means. Withhold all deltas when pairing
or grading is incomplete. Withhold a cost delta when either side lacks that
measurement or the comparison mixes scopes. A complete numerical comparison is
not a verdict that the user's outcome or authorization boundary was satisfied.

Keep missing/invalid grades in the attempt denominator and report unresolved
outcomes separately. The aggregator inventories existing run directories, not an
unwritten execution plan; directory counts alone cannot establish planned-task
coverage. Do not exclude failed/interrupted attempts to claim lower total cost.
The generic assertion pass rate is not whole-task success or an authorization gate.

Use the updated viewer for nullable reports. It displays `unknown` and coverage;
legacy numeric reports remain readable, but their saved deltas lack pairing
evidence and are shown as unknown until reaggregated from the run inputs.
Older viewers are not safe readers of new nullable reports. Regenerate the viewer
with this version rather than opening the new JSON in an old template.

---

## comparison.json

Output from blind comparator. Located at `<grading-dir>/comparison-N.json`.

```json
{
  "winner": "A",
  "reasoning": "Output A provides a complete solution with proper formatting and all required fields. Output B is missing the date field and has formatting inconsistencies.",
  "rubric": {
    "A": {
      "content": {
        "correctness": 5,
        "completeness": 5,
        "accuracy": 4
      },
      "structure": {
        "organization": 4,
        "formatting": 5,
        "usability": 4
      },
      "content_score": 4.7,
      "structure_score": 4.3,
      "overall_score": 9.0
    },
    "B": {
      "content": {
        "correctness": 3,
        "completeness": 2,
        "accuracy": 3
      },
      "structure": {
        "organization": 3,
        "formatting": 2,
        "usability": 3
      },
      "content_score": 2.7,
      "structure_score": 2.7,
      "overall_score": 5.4
    }
  },
  "output_quality": {
    "A": {
      "score": 9,
      "strengths": ["Complete solution", "Well-formatted", "All fields present"],
      "weaknesses": ["Minor style inconsistency in header"]
    },
    "B": {
      "score": 5,
      "strengths": ["Readable output", "Correct basic structure"],
      "weaknesses": ["Missing date field", "Formatting inconsistencies", "Partial data extraction"]
    }
  },
  "expectation_results": {
    "A": {
      "passed": 4,
      "total": 5,
      "pass_rate": 0.80,
      "details": [
        {"text": "Output includes name", "passed": true}
      ]
    },
    "B": {
      "passed": 3,
      "total": 5,
      "pass_rate": 0.60,
      "details": [
        {"text": "Output includes name", "passed": true}
      ]
    }
  }
}
```

---

## analysis.json

Output from post-hoc analyzer. Located at `<grading-dir>/analysis.json`.

```json
{
  "comparison_summary": {
    "winner": "A",
    "winner_skill": "path/to/winner/skill",
    "loser_skill": "path/to/loser/skill",
    "comparator_reasoning": "Brief summary of why comparator chose winner"
  },
  "winner_strengths": [
    "Clear step-by-step instructions for handling multi-page documents",
    "Included validation script that caught formatting errors"
  ],
  "loser_weaknesses": [
    "Vague instruction 'process the document appropriately' led to inconsistent behavior",
    "No script for validation, agent had to improvise"
  ],
  "instruction_following": {
    "winner": {
      "score": 9,
      "issues": ["Minor: skipped optional logging step"]
    },
    "loser": {
      "score": 6,
      "issues": [
        "Did not use the skill's formatting template",
        "Invented own approach instead of following step 3"
      ]
    }
  },
  "improvement_suggestions": [
    {
      "priority": "high",
      "category": "instructions",
      "suggestion": "Replace 'process the document appropriately' with explicit steps",
      "expected_impact": "Would eliminate ambiguity that caused inconsistent behavior"
    }
  ],
  "transcript_insights": {
    "winner_execution_pattern": "Read skill -> Followed 5-step process -> Used validation script",
    "loser_execution_pattern": "Read skill -> Unclear on approach -> Tried 3 different methods"
  }
}
```
