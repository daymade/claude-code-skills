---
name: materialization-budget
description: >-
  Prepare selected immutable Git inputs, run evaluation commands under one cumulative
  disk budget, and explicitly retire consumed rebuildable outputs while retaining
  changed work and evidence. Read before isolated input copies or task-output cleanup.
---

# Budgeted input copies, runs and output retirement

For read-only work that needs no input copy, read the required objects directly
with `git show <commit>:<path>`.

For Agent calls, use `python3 "<skill-creator-path>/scripts/creator.py" materialize_agent`
with the absolute skill-creator path; see the [fixed entry](fixed-command-entry.md).
It runs the existing `scripts/materialize.py` owner on POSIX with Python 3.10+ and
Git. That owner uses the standard library and local Git object reads. It creates
no Git history, background service, system hook or periodic deletion job.

## Declare scope before preparation

Supply a JSON object with every required field below. The byte limits are choices
for this task, not defaults. Derive them from the selected inputs, planned outputs
and the available disk reserve. Include metadata and logs in the allowance.

| Field | Contract |
|---|---|
| `source_repo` | Existing local Git repository path |
| `source_ref` | Full immutable 40-hex commit SHA; resolve the chosen ref, never substitute current HEAD |
| `paths` | Nonempty list of exact repository-relative files/directories needed by this task |
| `arms` | Unique names such as `with_skill`, `old_skill`; each gets the selected inputs |
| `max_total_bytes` | Positive integer; one cumulative allowance across all arms, retries, receipts, logs and evidence |
| `minimum_free_bytes` | Positive integer; caller's minimum available filesystem bytes after estimated input export and during execution |
| `owner` | Nonblank caller session identifier; use the same value on every subsequent command |
| `materialize_lfs` | Optional boolean, false when omitted; true permits only already-present local LFS objects |
| `capacity_config` | Optional absolute physical JSON file whose positive integer `minimum_free_bytes` adds a selected reserve |

Empty, missing, null and nonpositive required values fail. Whole-repository `.` or
empty path lists, traversal, absolute paths, Git pathspec magic, `.git`, symlinks
and submodules are unsupported and rejected. A named directory includes its tracked
descendants; select a narrower path when those descendants are unnecessary.

`prepare` checks the chosen commit's blobs and multiplies the estimate by every
arm. It checks the destination filesystem's allocation unit and free space before
creating the root, then measures after each input export. A later failure can leave
a partial root; its receipt still names the rebuildable inputs for `finish`.
Only listed Git objects are exported through `ls-tree`/`cat-file`; working-tree
changes, untracked dependencies and repository history are not imported.

LFS pointers stay pointers unless `materialize_lfs` is true. Local materialization
checks the object's SHA-256 and declared size; an unavailable or mismatched object
fails. The runner does not fetch, download, invoke smudge filters or borrow an
external LFS cache.
Git object reads disable lazy promisor fetches and remote protocols, so a missing
partial-clone object fails instead of silently downloading into a shared cache.

### Bind an optional capacity reserve

Select a configuration explicitly in the manifest or with
`prepare --capacity-config /absolute/capacity.json`. The JSON must contain a
positive integer `minimum_free_bytes`; other fields do not affect this runner.
No machine configuration is discovered automatically. Omit the binding to retain
the existing caller-only reserve.

The receipt freezes the selected path and the greatest configured reserve seen.
Execution uses the maximum of the caller's reserve, that frozen reserve and the
current selected value. Raising the configuration takes effect on the next
measurement; lowering it does not lower an existing task's reserve. The path
cannot be replaced for that task. Missing, malformed or invalid selected
configuration refuses new input export or child launch. Use a regular physical
file without symlink components.

Use `run --capacity-config /absolute/capacity.json` to bind an existing unbound
root before its next child. A wrapper holding the root lock can call
`resolve_capacity_limits(record, capacity_config)` to adopt the selection, then
use the existing `measure` and `save` functions. The helper returns the effective
`max_total_bytes` and `minimum_free_bytes`; it does not persist the record itself.
Use a runner supporting this interface for bound roots; older runners do not
enforce this optional binding. `finish` and `recover` never read the configuration
or require available space above the reserve, so an unavailable configuration or
low disk space does not prevent safe cleanup of declared inputs.

## Reserve storage outside the monitored root

Before preparation, the caller records the whole-task allowance and any external
storage reservation in the existing task plan. Include task-created worktrees,
dependency caches, container images and writable layers that cannot live under
the monitored root. Set `max_total_bytes` to the whole-task allowance minus that
reservation; reject a nonpositive remainder before calling `prepare`. The free-space
reserve remains a separate requirement, not extra spending allowance.

At admission and before a retry that can grow external storage, read the current
local charged bytes and conservatively account for external task allocations.
Keep observed sizes, estimates and unknowns separate; do not count the same shared
image layer twice or claim that logical image sizes measure physical disk release.
For example, a 1 GiB task with 384 MiB reserved externally permits at most 640 MiB
in `max_total_bytes`; 600 MiB charged locally plus 450 MiB externally exceeds the
task allowance even when `run` exits 0. Stop new allocation if external usage
exceeds its reservation, the combined charge exceeds the allowance, or the required
external measurement is unknown. Preserve the evidence and original allowance;
do not reset the root or enlarge its limit to hide an overage.

Report the runner's local result and the caller's combined-budget judgment
separately, naming the external coverage and unresolved estimates. The caller
performs this reconciliation; `materialize.py` does not discover external Docker
or cache usage, enforce this reservation, or stop those external services.

## Runnable small example

`materialize_agent` supplies the existing `--summary` for smaller tool-visible stdout. It adds
the flag after the operation unless already present before the child `--`;
`--summary` after that separator remains a child argument. Missing or unsupported
operations retain the entry's or owner's error behavior.

The summary projects recorded state and byte limits, the full receipt's path, the
latest recorded run state/return code when present, and the pre-finish outcome.
It also projects the selected `capacity_policy` and `capacity` observations when
recorded, without echoing the configuration path.
The complete receipt remains in `root/.materialization.json`; inputs, child argv,
path inventories and cleanup lists are not echoed in summary mode. Child stdout
and stderr remain in `artifacts/run-NNNN/` logs. The original `creator.py materialize`
entry and direct `scripts/materialize.py` invocation still return full JSON by
default; callers can select `--summary` explicitly there. The Python API is
unchanged. Exit codes remain unchanged: a child exiting 7 still
returns 23 from `run`, with 7 in the summary's `last_run.returncode`. A missing
return code stays absent, never an invented success. This mode limits selected
fields, not arbitrary path lengths or results aggregated by an outer tool call.

Run this from the skill-creator directory. The manifest below chooses explicit
limits for a tiny smoke test. Set operational limits from the real task before any larger
run. The root below does not exist when `prepare` creates it.

```bash
materialization_workspace=$(mktemp -d)
export MATERIALIZATION_WORKSPACE="$materialization_workspace"
uv run --frozen python - <<'PY'
import json, os, pathlib, subprocess
repo = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip()
ref = subprocess.check_output(['git', '-C', repo, 'rev-parse', 'HEAD'], text=True).strip()
manifest = {
    'source_repo': repo,
    'source_ref': ref,
    'paths': ['daymade-skill/skill-creator/SKILL.md'],
    'arms': ['with_skill', 'old_skill'],
    'max_total_bytes': 1048576,
    'minimum_free_bytes': 1,
    'owner': 'smoke-session'
}
path = pathlib.Path(os.environ['MATERIALIZATION_WORKSPACE']) / 'input-manifest.json'
path.write_text(json.dumps(manifest))
PY
python3 scripts/creator.py materialize_agent prepare \
  --manifest "$materialization_workspace/input-manifest.json" \
  --root "$materialization_workspace/task"
materialization_exit=0
python3 scripts/creator.py materialize_agent run \
  --root "$materialization_workspace/task" --owner smoke-session --arm with_skill \
  -- python -c 'from pathlib import Path; print(Path("daymade-skill/skill-creator/SKILL.md").is_file())' \
  || materialization_exit=$?
python3 scripts/creator.py materialize_agent finish \
  --root "$materialization_workspace/task" --owner smoke-session
printf 'run exit: %s\n' "$materialization_exit"
```

Expected: preparation reports `prepared`; run reports `run_succeeded` with child
return code 0; `artifacts/run-0001/stdout.log` contains `True`. Finish reports
`finished` and retains the log files. Read `task/.materialization.json`
independently for the persisted outcome and removed/retained paths. Process exit 0
does not establish business acceptance; inspect the
task's outputs against the user's acceptance criterion.

## Run and account for every retry

Launch an argument vector after `--`; no shell is inserted. The working directory
is `arms/<arm>`. Each attempt gets a new `artifacts/run-NNNN/` containing stdout
and stderr. Call `run` again for a retry under the same root and cumulative budget,
before calling `finish`.
Runs are serialized; another run or finish cannot acquire its active lock.

### Adapt an existing runner for a bounded resume

Prefer the owning runner's native resume or retry entry. When only programmatic
step selection is available, keep one adapter for the entire retry sequence rather
than creating a new temporary driver after each failure. Bind it to the immutable
input ref, stable owner and cumulative budget, with a distinct output root for each
attempt; count the adapter, copies and logs in the same task budget.

Derive the selected steps from the runner's persisted receipt: include only
unfinished checks and explicitly required environment preparation, not steps that
already passed. Treat a `running` step without a command record as unknown unless
the runner's schema proves it was not launched. Reconcile the original attempt
before retrying. The receipt's schema and terminal status are authoritative; finished cleanup or a
shell exit 0 alone is not a passed check.

Propagate a programmatic entry's return code—for example,
`raise SystemExit(main())` when `main()` returns an exit code. After a storage stop,
preserve evidence and remove only verified rebuildable owned inputs before resuming
with the same owner and reserve. Do not lower the reserve, delete evidence, or start
another adapter to manufacture a green run.

The runner samples only its own root and the root filesystem's available space.
It charges the larger of each path's logical or allocated size, including
directory metadata. Per-path observed high-water sizes and charged bytes persist
across runs; deleting a file does not reset the allowance.
This measures observed storage growth, not every byte ever written: same-path
rewrites and creation/deletion entirely between samples can escape cumulative
measurement. Keep retry outputs in distinct paths and preserve evidence.

A child entry or subtree unavailable with ENOENT during traversal is skipped;
sizes already observed in that sample and previously recorded high-water charges
remain. A missing or replaced root, permission/I/O errors, special files, and traversal errors without a named
strict descendant still make measurement unknown. The traversal is not atomic.

Use `run --poll-interval <seconds>` to choose the polling interval; the
[CLI argument parser](../scripts/materialize.py) defines its default.
A write burst can overshoot between samples or during filesystem traversal.
This is a monitored budget, not a hard disk quota or hostile-process sandbox.
Writes outside this root, global dependency caches, and descendants that escape
the created process group are outside its accounting/control boundary. Keep all
task-generated outputs inside the root and prevent dependency installation from
duplicating runtime caches as part of the task plan.

Read `capacity` in the receipt or summary for the first, latest and lowest
observed filesystem-available bytes and their sampling times. Its
`mixed_filesystem_available_space` scope includes unrelated writers and external
caches on that filesystem. A free-space decrease does not identify its owner or
measure the task's complete cumulative allocation. Samples update memory and
persist at the runner's existing receipt-write points; they add no per-sample
write loop and do not recover observations lost in an uncatchable runner death.

On cumulative overage, low free space, unknown measurement, Ctrl-C or CLI SIGTERM, the runner
forcibly stops only the new process group it created. It also checks immediately
after a fast child exits and stops leftover group members after the leader exits.
Existing unrelated processes are not selected or stopped.

| Exit | Meaning |
|---|---|
| `0` | Prepare/finish/recover/register-output/retire completed, or the child exited 0 within observed limits |
| `2` | Invalid/missing manifest, owner/root mismatch, locked root or unsupported input |
| `20` | Cumulative budget exceeded; evidence remains |
| `21` | Free space below the explicit reserve |
| `22` | Measurement or run I/O unknown; treat as failure |
| `23` | Child failed; its exact return code is in the receipt |
| `130` | Interrupted; evidence remains |

## Finish on success, failure and interruption

Use the same `finish` command after any completed run, including a failed or
interrupted run and partial preparation. It verifies root path, inode and owner,
and refuses an active child group or active lock. It unlinks only declared
rebuildable regular inputs whose content still matches the recorded hash/size.
It refuses symlinks in the input path, checks file identity while hashing and
requires the original permission mode. Permission-only changes remain work.
Modified inputs, hard links, unknown files and all `artifacts/` files remain,
with their paths in `cleanup.retained`; inspect those paths before further work.
`finish` marks the whole root `finished`, not an individual arm. `run` rejects
that state. Complete planned retries before finishing; preserve a finished receipt
rather than editing it or creating a new root to reset the same task's allowance.
Empty directories and the receipt remain. There is no whole-root recursive delete
and no scan/cleanup of unrelated temporary directories.

The receipt records `outcome_before_finish`; `finished` means input cleanup ran,
not that evaluation passed. Cleanup keeps evidence even when the budget is already
exceeded and its small final receipt needs additional bytes. Do not delete evidence
to manufacture a green outcome.

After an uncatchable runner death, a stale lock can remain. Once the recorded
runner PID and child group are confirmed absent, use:

```bash
python3 scripts/creator.py materialize_agent recover \
  --root "$materialization_workspace/task" --owner smoke-session
python3 scripts/creator.py materialize_agent finish \
  --root "$materialization_workspace/task" --owner smoke-session
```

`recover` checks the stored lock owner and runner PID, then removes only that stale
lock. It never kills a discovered process. If a PID is still active, ownership is
unknown, the receipt is damaged or a child group remains, preserve the root and
report the unresolved state. Do not edit the receipt to force cleanup. The receipt
is an ownership record for cooperative task processes, not cryptographic isolation
from a process deliberately tampering with it.

## Register outputs and retire them after consumption

`finish` cleans inputs; it does not retire task-created outputs. Before handing a
build, preview or transport payload to its consumer, classify its exact in-root
path with `register-output`. Use this JSON object for one file or directory:

```json
{
  "path": "artifacts/preview",
  "kind": "rebuildable",
  "consumer": "preview-reader",
  "rebuild_from": "source-ref:<full-commit-sha>; documented preview build command"
}
```

Choose `kind` from `rebuildable`, `transport`, `evidence` or `unique`.
Only `rebuildable` and `transport` authorize retirement; both require nonblank
`rebuild_from` naming the independently retained source and reconstruction route.
Do not classify the sole copy, a human-edited deliverable or necessary review proof
as disposable. `evidence` and `unique` remain even after consumption. Unknown and
unregistered files remain by default. The caller decides the classification and
checks its existing deletion authorization; the helper verifies the exact snapshot,
not whether a prose reconstruction claim is true.

Supply a nonblank `consumer` covering every downstream use of that payload. An
optional positive integer `consumer_pid` also blocks retirement while that PID is
alive. Without a PID the caller must establish that all readers, preview servers,
uploaders and downstream jobs have finished before supplying `--consumed`.
Neither command discovers or stops external processes.

```bash
uv run --frozen python - <<'PY'
import html, json, os, pathlib, subprocess
workspace = pathlib.Path(os.environ['MATERIALIZATION_WORKSPACE'])
root = workspace / 'task'
receipt = json.loads((root / '.materialization.json').read_text())
source = subprocess.check_output([
    'git', '-C', receipt['source_repo'], 'show',
    receipt['source_ref'] + ':daymade-skill/skill-creator/SKILL.md'
], text=True)
preview = root / 'artifacts/preview'
preview.mkdir()
(preview / 'page.html').write_text('<pre>' + html.escape(source) + '</pre>')
manifest = {
    'path': 'artifacts/preview', 'kind': 'rebuildable', 'consumer': 'preview-reader',
    'rebuild_from': 'source-ref:' + receipt['source_ref'] + '; HTML-escape selected SKILL.md'
}
(workspace / 'output-manifest.json').write_text(json.dumps(manifest))
PY
python3 scripts/creator.py materialize_agent register-output \
  --root "$materialization_workspace/task" --owner smoke-session \
  --manifest "$materialization_workspace/output-manifest.json"
uv run --frozen python - <<'PY'
import os, pathlib
page = pathlib.Path(os.environ['MATERIALIZATION_WORKSPACE']) / 'task/artifacts/preview/page.html'
assert 'Skill Creator' in page.read_text()
print('preview consumed')
PY
# For a real browser preview, finish every reader and stop its own server first.
python3 scripts/creator.py materialize_agent retire \
  --root "$materialization_workspace/task" --owner smoke-session \
  --consumer preview-reader --consumed
```

This tiny continuation of the earlier smoke reconstructs a preview from the
independently retained Git source after input cleanup. It creates the manifest
after the payload exists, consumes the page and retires its containing directory.
Read back that `task/artifacts/preview` is absent and the receipt/logs remain.

Registration snapshots each physical regular file's hash, permission mode and
identity. It rejects symlinks, hard links, special files and symlinked ancestors.
Paths must be strict descendants of `artifacts/` or a declared `arms/<arm>/`;
declared inputs and disposable `artifacts/run-NNNN/` logs are excluded. A directory
registration freezes its existing descendants; files added later are unknown and
remain. Registrations cannot overlap or be reclassified. Use a new output path
for another build or retry, retaining the original classification and budget.

`retire --consumer <name> --consumed` removes only that consumer's registered,
unchanged `rebuildable`/`transport` regular files. Changed content, mode, identity,
timestamps, links or parent identities preserve the affected path. It removes only
registered empty directory shells with matching identities. It never recursively
deletes a root or follows an external path. Both commands retain the existing
owner/root checks and lock, and refuse an active runner child group. They also
work after `finish`; neither reopens `run` on a finished root.

Read back `output_retirement.complete` and the full receipt's `removed`, `retained`,
`missing` and `directories_removed` lists. A missing path is reported separately
from a verified removal. `complete=false` means a disposable registered path still
needs inspection; exit 0 alone does not mean the directory is empty. Evidence and
unique registrations are expected retentions. Repeated retirement is safe and
reports already-absent files as missing.

Registration charges observed storage and receipt growth without lowering any
high-water mark. It remains available under low space or unavailable capacity
configuration so payloads can be recorded before safe cleanup. It is not permission
for another allocation: reconcile `charged_bytes`, `max_total_bytes` and external
reservations before proceeding. `run` retains its capacity and budget preflight.
Retirement does not require free space above the reserve or a readable capacity
configuration, and never resets the task's charge, limit or run/finish outcome.
Keep this lifecycle in-root; external worktrees, images and caches retain their
owning cleanup procedures and the whole-task reconciliation above.

## Verification

From the skill-creator directory:

```bash
uv run --frozen python -m unittest tests.test_materialize
```

The tests create isolated small Git repositories and exercise selected-ref export,
all-arm/ref-based preflight, missing and blank limits, LFS pointer/local-only modes,
monitored overage, free/unknown measurements, failed and interrupted runs, stale
lock recovery, disappearing-child races, root identity, retained high-water charges,
conservative input cleanup, explicit output classification and consumer completion,
modified/unknown/unique retention, symlink/hard-link escape refusal, and retirement
after finish or a capacity failure. No fixture loads the source repository's
history or downloads dependencies/media. The subprocess lifecycle follows Python's
[subprocess contract](https://docs.python.org/3/library/subprocess.html); Git input
selection is explicit rather than the whole-tree default documented by
[git archive](https://git-scm.com/docs/git-archive).
