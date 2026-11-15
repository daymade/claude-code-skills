# Consolidate a completed task's evidence

Use this route when the user wants old task directories resolved into useful
deliverables. The result is implemented work in its maintained repository,
recoverable original evidence, and retirement of confirmed disposable state.
An archive alone does not establish a merge, product acceptance or task completion.

## Select by role before copying

| Contents | Disposition |
|---|---|
| Source edits, commits, worktree metadata | Use Git Safety Net; prove containment and preserve unique Git/ignored state before retiring a checkout |
| Original media, human feedback, unique evidence | Keep the existing authoritative original; consolidate only explicitly selected inactive evidence with a recoverable original-path manifest |
| Rebuildable dependencies, build output, synthetic test databases | Apply [generated-payload facts](generated-payload-plans.md); keep reconstruction inputs and unique logs, without another full backup of disposable bytes |
| Active control inputs, credentials, registered assets, unknown use | Preserve original paths; obtain the exact consumer/owner disposition before moving or deleting |

Ask a current owner for exact paths and consuming jobs, rather than treating a
whole task root as active. A non-use report is evidence, not deletion authority;
the complement of a protection list is unclassified. Check current config,
registries, processes and open files yourself. An old log mentioning a file is
not by itself a live reference. Never include chat-history roots or chat containers.

Long-lived inputs belong at their existing lifecycle's controlled destination.
Change consumer configuration through that owner, verify actual consumption and
failure reporting there, then retire the old path. Do not create a second asset
authority or break a live absolute path to make the task root look empty.

## Exact evidence archive

`scripts/task_evidence_archive.py` supports ordinary, single-link regular files
only. It does not discover files, classify inactivity, preserve a Git repository,
move live consumers or grant deletion permission. Symlinks, hardlinks, directories,
special files and protected targets need another disposition. Prepare/verify use
Python 3.10+ POSIX standard libraries; retirement requires macOS and a successful current
`/usr/sbin/lsof` probe. For each nonempty batch, only exit 1 with stdout and stderr
both empty after stripping whitespace establishes no selected file is open;
all other results refuse retirement.

Before prepare, run the ordinary plan checker and [copy-budget
check](safety_rules.md) against the exact source rows and prepare/verify commands.
Budget source bytes, retained archives and partial retries;
verification streams the archive and needs no extracted copy. Coordinate a single
writer for the selected files throughout prepare and retirement. No name-based
or filename-reference heuristic proves a file is inactive.

Create a private selection JSON with absolute paths. Use the user's existing
authorization and evidence for each classification; the tool only enforces the
declared boundary. The example below is a schema shape; supply real local paths
and keep real credentials out of reports and examples:

```json
{
  "schema": 1,
  "authorization": "Existing user instruction covering this exact consolidation",
  "roots": ["/absolute/task-root"],
  "protected": ["/absolute/task-root/current-input"],
  "files": [
    {"path": "/absolute/task-root/finished-run.log", "role": "evidence", "current_use": "inactive"}
  ]
}
```

Use a private retained destination outside every source root. All output paths
must be distinct and new; existing outputs are never overwritten. Invoke from
the loaded Skill directory, or use absolute script paths from another directory:

```bash
python3 scripts/task_evidence_archive.py prepare \
  --selection /absolute/selection.json \
  --archive /absolute/retained/evidence.tar.gz \
  --manifest /absolute/retained/manifest.json
python3 scripts/task_evidence_archive.py verify \
  --manifest /absolute/retained/manifest.json \
  --receipt /absolute/retained/verified.json
```

Prepare preserves original-path mapping, modes, byte counts and SHA-256 identities
both outside and inside the archive. Verify reads every member without extracting,
rejects extra/missing/duplicate members and binds its receipt to the exact manifest
bytes and archive. Reuse that receipt while its bound inputs remain unchanged.

After independently checking authorization and live consumers, pass the exact
64-character `manifest_sha256` from verification to retirement. First classify
each source against its now-verified retained copy in the retirement table and
rerun `scripts/check_gate_plan.py --table <retirement-table> --plan <retirement-plan>`.
The plan contains the complete command below, its real manifest hash and adjacent
tool-version/source/help observations. The checker reads the bound manifest and
matches every `files[].source` against an eligible table row. Missing or unknown
command coverage stops the pass; a successful copy plan is not retirement approval.

```bash
python3 scripts/task_evidence_archive.py retire \
  --manifest /absolute/retained/manifest.json \
  --receipt /absolute/retained/verified.json \
  --expected-manifest-sha256 <verified-full-sha256> \
  --journal /absolute/retained/retirement.jsonl
```

Retirement checks the entire source selection again after slow probes and before
the first unlink, then checks each file again. It pins and locks the journal's
no-follow file descriptor and rechecks controls before writing an intent.
Missing/empty/changed bindings, changed source metadata or bytes,
changed archive identity and incomplete open-file coverage refuse the operation.
It deletes only selected files; parent directories and unrelated empty directories
are never pruned. No processes, containers or other sessions are stopped.

## Interruption, recovery and completion

Keep partial outputs after an interrupted prepare; original sources remain.
Inspect the exact partial and reuse its copy budget before a separately named
retry. Do not overwrite it or clean the whole destination. A failed verification
does not authorize retirement.

Retirement records and syncs each source intent before unlinking. After an
interruption, rerun the same retirement command and journal: only absent files
with an existing bound intent count as already retired. Newly created/replaced
files, missing files without intent and malformed journals stop recovery. Preserve
the archive, manifest, receipt and journal until the retention owner accepts them.

For recovery, verify the retained archive first and restore selected regular
members to a new private directory; use the manifest's source/member mapping and
SHA-256 to check restored bytes. Never extract over a current working directory.
Recreate an old consumer path only through its owner, preserving any newer work.

Close with one useful entry pointing to maintained implementation and retained
evidence. Read back removed exact paths and protected originals; distinguish
logical bytes from measured physical free space. Name any unmerged candidate,
active input or unknown item and its next action in the existing task state.
Remove this task's disposable analysis copies once their consumers finish.
