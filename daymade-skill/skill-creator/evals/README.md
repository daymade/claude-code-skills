# Prepare the source regression cases

Follow [source-case input preparation](../references/eval_pipeline_schemas.md#source-case-input-preparation)
before using the case metadata. Resolve paths from this Skill root. Keep this
README and grading material in the orchestrator context.

## Terminal command case

Pass the producer named by the case directly to the consumer. Do not execute it
as preparation: its execution belongs to that consumer's observed task. Use the
normal Skill entry and its stateful-verification route.

## Recorded truncated-read case

Prepare the recorded-read input before dispatch. Run the following from this
Skill directory in an authorized run workspace. The capture output directory must
not already exist.

```bash
export EVAL_SKILL_ROOT="$(pwd -P)"
export EVAL_PREP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/recorded-read-input.XXXXXX")"
python3 "$EVAL_SKILL_ROOT/scripts/creator.py" capture_command \
  --cwd "$EVAL_SKILL_ROOT" --output-dir "$EVAL_PREP_ROOT/capture" -- \
  python3 "$EVAL_SKILL_ROOT/evals/fixtures/large_output_fixture.py"
python3 - "$EVAL_SKILL_ROOT" "$EVAL_PREP_ROOT" <<'PREPARE'
import hashlib
import json
import sys
from pathlib import Path

skill, work = map(Path, sys.argv[1:])
metadata = json.loads((work / 'capture/result.json').read_text())
if metadata['status'] != 'child_exited' or metadata['returncode'] != 0:
    raise ValueError('capture did not complete successfully')
raw = Path(metadata['stdout']['path']).resolve(strict=True)
raw_bytes = raw.read_bytes()
json.loads(raw_bytes)
receipt = json.loads((skill / 'evals/fixtures/read_receipt.json').read_text())
receipt['stdout'].update(path=str(raw),
    sha256=hashlib.sha256(raw_bytes).hexdigest(), bytes=len(raw_bytes))
prepared = work / 'read_receipt.json'
with prepared.open('x', encoding='utf-8') as stream:
    json.dump(receipt, stream, ensure_ascii=False, indent=2)
negative = (skill / 'evals/fixtures/incomplete.stdout').resolve(strict=True)
print(json.dumps({'consumer_files': [str(prepared.resolve()), str(raw), str(negative)],
    'prepared_receipt_sha256': hashlib.sha256(prepared.read_bytes()).hexdigest()}))
PREPARE
```

Replace the dispatch file list with the printed `consumer_files`. Retain the
source template and capture receipt as preparation evidence; do not count this
capture as consumer execution. The source template's unresolved path is unready,
not a path to guess. The consumer recovers the existing complete artifact and
judges the separate incomplete artifact without rerunning either producer.

## Grade the actual evidence

Compare reported values with an independent parse of the complete captured
artifact. Compute record/source counts and the final-record position during
this check rather than maintaining answers here. Preserve stream identity,
terminal status and raw hashes. Require observed calls and reads instead of
self-reported success; missing transcript or byte telemetry remains unverified.

Use prefix-only evidence, replacement execution after truncation and acceptance
of incomplete JSON because of exit status as failing controls. Keep later
corrections separate from the first answer through the
[replay-fidelity contract](../references/independent-review-protocol.md#behavior-replay-fidelity).

[Distribution inclusion policy](../scripts/packaging_policy.py)
