# Machine results and interrupted runs

Use the optional receipt interface when a launcher must decide whether a probe
actually measured its requested units. Keep ordinary CLI text and the existing
`--output` JSON or quality answer files for inspection. A zero process exit by
itself does not establish a measurement.

Supply `--result-json <fresh-path> --run-id <new-uuid>` together on speed,
protocol, concurrency or usecase_runner. Create a new receipt path for every
child. The writer refuses an existing file or symlink before reading credentials
or sending requests. Keep the receipt separate from `--output`.

```bash
uv run --with openai python scripts/speed_probe.py \
  --base-url https://api.example.com/v1 --model example-model --key-env MY_KEY \
  --mode both --result-json ./run/speed-result.json \
  --run-id 2ecdd678-0ab4-45db-a86e-e3e6a7e9efce
```

Prepare the parent directory first and generate a new UUID for a real run. The
example ID is synthetic. This command sends actual model requests; inspect route
and funding authorization in the owning launcher before executing it. This
generic engine does not select credentials, authorize funding or replace a
registry policy.

Read receipts with the bundled stdlib-only `scripts/eval_result.py` from the
explicitly trusted engine installation. Import `RESULT_API_VERSION`,
`invocation_digest`, `read_result` and `ResultContractError`. Bind the actual
probe argv, fresh run ID, probe name and observed child return code:

```python
digest = invocation_digest(probe_argv)  # excludes interpreter/script filename
result = read_result(
    receipt_path, expected_run_id=run_id, expected_probe="speed",
    expected_invocation_sha256=digest, child_returncode=child.returncode,
    expected_identity=identity,  # optional exact route-fact comparison
)
```

Load this module from the configured engine scripts root, rather than a directory
derived from a data/registry file. Refuse an absent/incompatible helper before a
launcher starts work. The reader returns a plain dict and raises
`ResultContractError` for missing, stale, malformed, contradictory or unfinalized
evidence. Use its validated state/counters; do not copy its predicates into a
second checker or search console text for a success marker.

## State and exit contract

Machine mode uses these exits across all four probes:

| State | Verdict | Exit |
|---|---|---|
| completed | observed speed, collected quality (`not_judged`), or compliant | 0 |
| completed | noncompliant protocol or degraded concurrency | 10 |
| partial | some usable evidence, requested units missing/failed/skipped | 11 |
| no_measurement | no usable primary evidence | 12 |
| execution_error | local input, dependency, instrument or output failure | 2 |
| cancelled | interrupted; acquired evidence retained | 130 |

Keep execution state separate from capability and quality. An all-429 concurrency
run is a completed negative stability observation. An all-transport-failed
protocol run has no capability measurement. A quality run collects answers;
`not_judged` never means its answers passed their rubrics. Reasoning-only output
remains valid speed evidence when its stream completed and token/timing evidence
is usable. Empty quality answers do not count as collected answers.

Require a nonempty terminal `finish_reason` before treating an OpenAI speed stream
as complete. EOF after output preserves `partial_output` and timings, but supplies
no usable complete speed sample and does not enter throughput summaries. Keep
signature-validation errors in replay tests inconclusive: rejecting a fabricated
thinking signature does not prove rejection of the thinking block type. An
explicit `invalid part type: thinking` response remains valid negative evidence.

Legacy invocation without the two receipt arguments retains its existing modes
and successful-run exit behavior: protocol returns 1 for noncompliance;
concurrency can return 0 while reporting degradation. Do not feed legacy exit
codes to the machine receipt reader.

## Evidence and progress

The receipt binds `run_id`, `probe`, invocation digest and route `identity`
(model, endpoint kind/value, format and auth mode). It contains typed `units`,
derived `counts`, state/verdict, derived summary and an optional run error.
Counter names are planned/attempted/finished/usable/errors/skipped. They count
primary benchmark units, not HTTP requests, SDK retries or billable calls.
Speed's usage-support warm-up is a retained optional setup unit.

Use unique occurrence ordinals for repeated labels, cases or concurrency levels.
Reserve ordinary unique case filenames before assigning fallback names, including
names that resemble those fallbacks. The quality reader rejects duplicate usable
artifact references; distinct unit IDs alone cannot prove distinct answer files.
Speed units retain timings, content/reasoning sizes, throughput provenance and
partial stream errors. Protocol records both generation and history replay,
including completion and HTTP/error evidence. Concurrency records each timed
request outcome and keeps success-only latency summaries in the legacy output.
Quality records answer/reasoning sizes and finish reason; inspect its existing
answer artifacts for the full answer and rubric.

Validate numeric metrics against the per-unit field schemas in
`scripts/eval_result.py`, including error-unit partial metrics and derived summary
types. Reject negative, nonfinite or wrongly typed values; retain nullable values
and zero only where the declared metric permits them. HTTP status codes keep
their protocol meaning rather than being treated as latency or throughput.

The writer atomically saves a running snapshot before acquisition and after each
unit. Concurrency saves each result when it completes rather than waiting for a
whole ramp level. The writer finalizes ordinary errors and Python cancellation;
an abrupt process kill may leave only a running snapshot. Preserve that partial
evidence and report interruption, never terminal success. No terminal-write
guarantee is possible after a hard kill.

## Consumed inputs and answer artifacts

Readiness depends on compatibility with the API 2/schema 2 receipt contract. The reader
explicitly refuses schema 1 because it cannot establish consumed-input and retained
answer-byte bindings; it does not silently upgrade an old receipt to current proof.
Legacy invocations without machine arguments keep their existing collection modes.

Read a quality usecase library or custom speed prompts exactly once before
acquisition. The producer parses those same bytes and retains their base64 snapshot,
SHA256 and source pointer in `consumed_inputs`. Built-in speed prompts are captured
as a value snapshot. The reader derives the plan from these bound snapshots, without
reopening the user-maintained library. Later edits, deletion or same-count changes
to that source therefore do not invalidate its earlier partial/negative evidence.
Already consumed inputs also remain in receipts for credential/instrument errors
and cancellation after preflight.

For machine quality collection, pass a previously nonexistent `--output-dir`.
Reuse is an explicit pre-acquisition error, including an existing empty directory;
choose a new run directory to resume. Ordinary legacy collection can still reuse a
directory. Such a later legacy overwrite invalidates earlier machine evidence if
it changes a bound answer, rather than silently changing what an old receipt means.

Write each answer before admitting its observation and bind its exact retained
bytes, filename and unit owner to the receipt. Bind `_all_answers.json` as well.
The reader reads those retained files and checks size/SHA256; missing or changed
bytes refuse validation. Preserve the captured artifact directory with the receipt.
This detects supported output reuse or changed evidence; it is not a filesystem
sandbox against an adversarial same-OS writer rewriting the receipt and artifacts.

Use `--auth x-api-key|bearer` for Anthropic protocol/concurrency requests. The
default remains x-api-key, and the setting applies to both protocol generation
and history replay. OpenAI concurrency uses Bearer. Speed and quality accept an
SDK base URL; a launcher owning a different explicit operation URL must refuse
those unsupported dimensions before launching instead of silently ignoring it.

Run the offline regression suite with
`python3 -m unittest discover -s llm-eval-harness/tests -v` from the repository
root. The suite uses synthetic SDK/HTTP responses and child stubs, including
positive, negative, partial, cancelled, stale and malformed receipt cases; it
does not verify a live provider or authorize paid probes.
