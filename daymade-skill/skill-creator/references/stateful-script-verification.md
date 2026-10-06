# Stateful script verification

Use these recipes when a change touches persisted formats, partial state updates,
permission-sensitive checks, or output too large for a tool response. Select only the affected recipes. Run
against an isolated state directory with synthetic values; do not mutate live
accounts or journals to obtain test evidence. Stop when the changed contract is
decided by the checks below; the selected verification tier still governs review.

## Persisted-format compatibility

Before editing, name the supported reader versions, files and behaviors. Freeze
the old reader and writer from an immutable release/ref; a new parser with a
`legacy=True` flag is not an independent old reader.

| Writer | Reader | Required observation |
|---|---|---|
| Old | Old | Baseline fixture is valid and produces the expected result |
| Old | New | Historical records retain their identities and business meaning |
| New | New | Changed records produce the intended new behavior |
| New | Old | Still-supported behavior remains usable without crashes or silent reinterpretation |

Write through each version's actual writer into a temporary directory, then close
and reopen the files through the other version's actual reader. Assert counts,
record identities and decisions, not only successful parsing. Exercise the new
record type and an existing resolved record. Compare the old reader's result
before and after the new write.

The last row covers the declared compatibility surface, not features the old
reader never supported. A new sidecar file may be ignored by the old reader;
verify that the shared journal still works. If old readers cannot safely consume
the changed format, publish the approved migration/version boundary rather than
claiming bidirectional compatibility. Keep frozen code as a test-only fixture
with exact ref/path provenance; it is not another runtime implementation.

This matrix follows the mixed-version rollout concern in the
[Protocol Buffers best practices](https://protobuf.dev/best-practices/dos-donts/).
Its binary-format guarantees do not establish compatibility for JSON/JSONL;
exercise the actual format and consumers used by the Skill.

## Partial updates and persisted evidence

List the independent state dimensions and what makes an update explicit. Start
from established values, not only an all-unknown fixture. For an event journal,
use a scored hit, a confirmed event and two distinct accounts with unresolved
arrival gaps; adapt these values to the domain's real states.

1. Capture each dimension's value, identity and deciding record before updating.
2. Update one dimension through the real command. Read persisted data through the
   normal consumer and compare every other dimension with the captured baseline.
   Include updating one entity while a second entity retains its unresolved gap.
3. Separately exercise an explicit correction/retraction of the changed dimension.
   Distinguish omitted fields (no update), explicit unknown, empty and null according
   to the existing contract; do not invent a universal meaning for these inputs.
4. For each changed write branch, supply required evidence fields, including the
   normal and unknown branches. Close the writer, reopen the JSONL/database and
   assert the exact persisted values and the consumer's decision. Inspect both
   storage and projection when the consumer hides fields. Returned objects and
   validation success alone do not prove persistence.
5. Exercise missing keys and empty values separately (and null if accepted by the
   interface). Assert the specified rejection or observable default. On rejection,
   verify that the authoritative records remain intact; an empty file created by
   the command is not itself evidence of data loss.

Prove the regression detects the original failure using the frozen faulty code or
an isolated mutation of the same write/read path. Use synthetic evidence URLs and
account identifiers; do not copy live secrets into fixtures.

## Execution identity and permission fixtures

Before a permission-sensitive check, state which identity the tested behavior
serves and what that identity is expected to be allowed or denied. The verification
agent records the actual test process's effective identity and groups, plus any
elevation, capabilities, ACLs, mount restrictions or sandbox rules that affect
that expectation. Observe the test process itself; the launching terminal's
identity alone does not establish its child's permissions.

Use an isolated temporary fixture and low-level permission probes independent of
the product's logic to confirm both a normally writable control and the expected
permission-denied control. Run these probes in the same test process against the
fixture's actual target paths; do not use the product's own result as the control.
File mode bits alone do not establish rejection: a root or otherwise privileged test context
may bypass a restriction that applies to an ordinary user. When the fixture expects
ordinary-user rejection, run it with that intended identity and restrictions.
For a genuinely privileged runtime branch, retain its real execution identity and
state its expected result separately; do not force every test to run unprivileged.

Only when an independent control disproves the fixture's permission assumption,
report an **environment mismatch** and preserve the failed result. Correct the test
context, then rerun the affected gate unchanged. When the controls match the
assumption but product behavior is wrong, retain the failure as a product defect
or unresolved investigation; do not change the environment to make it pass.
Still complete the repository's required checks. Do not change product
code to satisfy an invalid fixture, broaden permissions on real account data, or
suppress a failed check. Reuse a suitable existing test environment; this recipe
does not require a new container or a blanket identity change for unrelated tests.

## Large command output

When the host returns a running-session or cell identifier, the executing agent
preserves the complete result: output, identifier and available status fields.
Forwarding only the text field discards the handle needed to observe completion.
Resume through that host's documented wait/poll API until a terminal exit status
is received. Partial output without terminal status remains running or unknown.
If the handle is lost, recover the existing run through the host's supported
status/artifact query; leave its outcome unknown when that evidence is unavailable.
Do not repeat a write to replace missing completion evidence.

Before a command expected to produce large output, choose a scratch output path
outside the shipped Skill. Capture raw stdout/stderr and the exit status, then
return a small summary and the path. For example, this stdlib recipe runs an
already-authorized command supplied after the script name:

```python
import subprocess
import sys
import tempfile
from pathlib import Path

with tempfile.NamedTemporaryFile(prefix="skill-output-", suffix=".log", delete=False) as out:
    result = subprocess.run(sys.argv[1:], stdout=out, stderr=subprocess.STDOUT)
    path = Path(out.name)
print(f"exit={result.returncode} bytes={path.stat().st_size} output={path}")
sys.exit(result.returncode)
```

Inspect that file with bounded line ranges or structured-field queries. Preserve
stderr and nonzero status when choosing another capture method. If a response is
already truncated, read the missing evidence from the saved output; if nothing
was saved, rerun only a safe read-only command or retrieve its existing artifact.
Do not rerun a write merely to recapture its output. Truncated responses cannot
establish completeness. File length alone does not justify reorganizing the Skill.

## Complete file reads

Prefer the host's Skill/Read loader. For a shell fallback, first run:

```bash
python3 <skill-creator-path>/scripts/skill_read_plan.py <file> --max-chunk-bytes 12000
```

Choose the byte budget below both the inner tool and outer response limits; 12000
is a starting choice, not a universal safe limit. The plan reports a content hash
and contiguous, nonoverlapping line ranges covering the entire file. Read each
range with a separate literal `sed -n '<start>,<end>p' <file>` or native Read call;
do not aggregate all ranges into one capped response. Track successfully received
ranges against that hash. If either layer truncates, reduce the budget and read
the missing range again. If the file changes, regenerate the plan and load the new
content. An oversized single line requires a byte-range reader or a larger safe
budget. The planner never sets a loaded marker. Reuse verified loading in the same
session instead of repeatedly rereading unchanged text.
