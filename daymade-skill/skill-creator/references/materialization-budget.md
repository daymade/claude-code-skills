---
name: materialization-budget
description: >-
  Prepare selected immutable Git inputs, run evaluation commands under one cumulative
  disk budget, and retain changed work and evidence during cleanup. Read before
  making isolated input copies for preparation, evaluation arms, or retries.
---

# Budgeted input copies and evaluation runs

For read-only work that needs no input copy, read the required objects directly
with `git show <commit>:<path>`.

Use `scripts/materialize.py` on POSIX with Python 3.10+ and Git. It uses the standard
library and local Git object reads. It creates no Git history, background service,
system hook or periodic deletion job.

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
| `minimum_free_bytes` | Positive integer; minimum available filesystem bytes after estimated input export and during execution |
| `owner` | Nonblank caller session identifier; use the same value on every subsequent command |
| `materialize_lfs` | Optional boolean, false when omitted; true permits only already-present local LFS objects |

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

## Runnable small example

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
uv run --frozen python -m scripts.materialize prepare \
  --manifest "$materialization_workspace/input-manifest.json" \
  --root "$materialization_workspace/task"
materialization_exit=0
uv run --frozen python -m scripts.materialize run \
  --root "$materialization_workspace/task" --owner smoke-session --arm with_skill \
  -- python -c 'from pathlib import Path; print(Path("daymade-skill/skill-creator/SKILL.md").is_file())' \
  || materialization_exit=$?
uv run --frozen python -m scripts.materialize finish \
  --root "$materialization_workspace/task" --owner smoke-session
printf 'run exit: %s\n' "$materialization_exit"
```

Expected: preparation reports `prepared`; run reports `run_succeeded` with child
return code 0; `artifacts/run-0001/stdout.log` contains `True`. Finish reports
`finished`, lists the removed input paths, and retains the log files. Read
`task/.materialization.json` independently to check the persisted outcome and
cleanup paths. Process exit 0 does not establish business acceptance; inspect the
task's outputs against the user's acceptance criterion.

## Run and account for every retry

Launch an argument vector after `--`; no shell is inserted. The working directory
is `arms/<arm>`. Each attempt gets a new `artifacts/run-NNNN/` containing stdout
and stderr. Call `run` again for a retry under the same root and cumulative budget,
before calling `finish`.
Runs are serialized; another run or finish cannot acquire its active lock.

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

On cumulative overage, low free space, unknown measurement, Ctrl-C or CLI SIGTERM, the runner
forcibly stops only the new process group it created. It also checks immediately
after a fast child exits and stops leftover group members after the leader exits.
Existing unrelated processes are not selected or stopped.

| Exit | Meaning |
|---|---|
| `0` | Prepare/finish/recover completed, or the child exited 0 within observed limits |
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
Modified inputs, hard links, unknown files and all `artifacts/` evidence remain,
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
uv run --frozen python -m scripts.materialize recover \
  --root "$materialization_workspace/task" --owner smoke-session
uv run --frozen python -m scripts.materialize finish \
  --root "$materialization_workspace/task" --owner smoke-session
```

`recover` checks the stored lock owner and runner PID, then removes only that stale
lock. It never kills a discovered process. If a PID is still active, ownership is
unknown, the receipt is damaged or a child group remains, preserve the root and
report the unresolved state. Do not edit the receipt to force cleanup. The receipt
is an ownership record for cooperative task processes, not cryptographic isolation
from a process deliberately tampering with it.

## Verification

From the skill-creator directory:

```bash
uv run --frozen python -m unittest tests.test_materialize
```

The tests create isolated small Git repositories and exercise selected-ref export,
all-arm/ref-based preflight, missing and blank limits, LFS pointer/local-only modes,
monitored overage, free/unknown measurements, failed and interrupted runs, stale
lock recovery, disappearing-child races, root identity, retained high-water charges,
and conservative cleanup. No fixture loads the source repository's
history or downloads dependencies/media. The subprocess lifecycle follows Python's
[subprocess contract](https://docs.python.org/3/library/subprocess.html); Git input
selection is explicit rather than the whole-tree default documented by
[git archive](https://git-scm.com/docs/git-archive).
