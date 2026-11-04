# Growth Attribution — what has been filling the disk lately

Read this when the question is about **change**, not size: "what has been taking
space these past weeks", "I had 200 GB free last month", "free space dropped overnight",
or when an older disk-scan export exists. A size ranking answers "what is big". It does
not answer "what grew", and the largest directories are often old, stable content.

Everything here is Phase 1 (read-only). Any deletion that follows still goes through the
Phase 2 entry gate in SKILL.md.

## Output shape

A delta table: directory, baseline size, current size, delta, window, **evidence type**
(baseline diff or timestamp estimate), and the owner or writer when known. Keep these
kinds of row apart. Directories that grew, directories absent from the baseline because
they were **not scanned**, and directories that shrank. Rows that shrank explain where
earlier free space came from.

## 1. Find a baseline before estimating

A measured baseline beats any estimate. In order:

1. A before-snapshot from this skill's `scripts/cleanup_report.py` (under `~/.macos-cleaner`).
2. A disk-visualizer export the user saved. The one calibrated for this reference is
   **GrandPerspective's "Export as text"**. It is a tab-separated file whose first line is
   `Path	Filename	Size	Type	Created	Modified	Accessed`, one row per file.
   GrandPerspective can also save scan data as `.gpscan`, but this reference was not
   calibrated on that format.
3. Earlier `du` output kept in a session's scratch files.

For a claim such as “the last cleanup freed hundreds of GiB,” first recover the
actual same-host, same-volume `df` readings and their timestamps. **Free after
cleanup**, **net free-space increase**, and **sum of removed path sizes** are
different values. A high after-reading alone cannot establish how much was freed.
Compare all relevant measured checkpoints in the requested window rather than
selecting the first convenient search hit. Keep estimates and missing readings
unknown. For session evidence, use the owning history reader's index or a named,
time-bounded session; never scan the full raw history to find a baseline.

**Finding an export.** The app may not record where the user saved it. GrandPerspective
is sandboxed, and its preferences and recent-documents list can hold nothing about
exports. Locate exports by name (`*.gpscan*`, `*grandperspective*`) or by the header
line above. Search only roots the user has authorized. Personal folders (Downloads,
Documents, Desktop) need the user's permission; when a search is refused, ask for that
permission rather than asking the user to run the search.

No baseline at all → go to section 3 and label every number as an estimate.

## 2. Diff a baseline export against the current disk

1. **Aggregate the export by directory prefix** up to a fixed depth, streaming it line by
   line rather than loading the full export into memory.
2. **Measure the same paths now** with `du -skx` at matching depths.
3. **Calibrate the size semantic before trusting any delta.** Pick one directory you know
   has not changed since the export and compare the export's sum with `du` for it. If they
   disagree, the export measured a different size (logical vs allocated), and every delta
   carries that bias.
4. **Treat absent or near-zero baseline rows as "not scanned", never as "new".** An export
   silently omits whatever the scanner could not read or skipped: privacy-protected folders
   when the app lacked Full Disk Access, other apps' sandbox containers, and sometimes whole
   hidden directories. A small baseline row can represent only the previously readable
   subset; check scan coverage before treating the difference as growth.
5. **Confirm every large delta with the timestamp estimate** (section 3) before calling it
   growth.

**Checking whether content that vanished from a directory was moved or deleted:** the
export lists every file's path and size. Compare that list **by relative path and size**
against the suspected destination (another volume, a NAS). Do not match by file name alone.
Camera names like `IMG_0306.MOV` collide across folders. In a default UTF-8 locale on
macOS, `sort -u` and `uniq` compare by collation, so distinct non-Latin names can be
merged away and show up as false "missing" files.

## 3. Timestamp estimate

Sum **allocated** bytes (`st_blocks × 512`) per directory for files whose timestamp falls
in the window. Which timestamp matters:

| Timestamp | What it means here | Misleads when |
|---|---|---|
| **ctime** (inode change) | When the file last changed *on this disk*. It is the best "arrived here" signal: a copy from another disk or a NAS gets a fresh ctime even when the copy preserves birth and modification times | **Over-counts** after renames and `chmod`, which update ctime. **Under-counts** content moved within the same volume: `mv` of a directory leaves its children's ctime unchanged, so data moved in from elsewhere on this disk looks old |
| **birthtime** (`st_birthtime`) | When the file was created | Unreliable for copied content: `cp -p` and Finder copies keep the source's birth time. Good for "generated here since X" (build output, caches, scratch directories) |
| **mtime** (modification) | Last content write | Counts a continuously rewritten file at full size in every window: a VM or container disk image (one large sparse file) is always "modified in the last hour" |

Useful shapes:

- **Per-directory ctime histogram by month** to separate "arrived after the baseline" from
  old content. This is how the not-scanned rows from section 2 are resolved.
- **Birthtime since a fixed moment** (for example last night's free-space reading) to find
  what was generated since then.

Verified on APFS: moving a parent directory kept a child's ctime; renaming the file and
`chmod` both updated it; `cp -p` produced a new ctime with the original birth time.

## 4. Reconcile against free space

Directory deltas are path-accounted, while free space is physical. They diverge whenever
blocks are shared: APFS clones (see [the allocation contract](../SKILL.md#safety-and-authorization-contract) and
[code-sign clones](chromium_code_sign_clones.md)), and caches whose contents are cloned or
hard-linked into project environments. Deleting such a cache can shrink `du` by tens of GiB
and free almost nothing.

The acceptance check is that attributed physical growth roughly matches the `df` change
over the same window. Before calling the gap unexplained, check the consumers that are not
directories:

- **Measurement continuity.** Record `date` and `sysctl kern.boottime vm.swapusage`
  with each live `df` checkpoint. Split the chronology at a reboot or other observed
  discontinuity. A later free-space jump across that boundary cannot be credited
  to an earlier deletion merely because the directory totals also fell. Without
  intermediate readings, name the combined causes and leave their shares unknown.

- **Swap.** `sysctl vm.swapusage`, and the VM volume's "Capacity Consumed" in
  `diskutil apfs list`. Heavy memory pressure can add tens of GB overnight and gives the
  space back only when pressure falls.
- **Local snapshots.** `tmutil listlocalsnapshots /`.
- **Short-lived copies.** Temporary checkouts or clones created and deleted between two
  readings. Free space that dips and recovers without any directory change is this shape.
  Files that vanish between a `find` and its `stat` point to the same cause.

Report the remainder as **unattributed** rather than forcing it onto the nearest large
directory.

**A clonefile snapshot's allocation can diverge after creation.** A fresh clone
can share most blocks with a retained source. As the live tree changes, the copy
can retain old blocks or acquire private blocks. Account for source churn as well as
the capture job. Aged copies and whole selected cohorts need current allocation
and reference evidence; neither their creation command nor one shared sample
proves zero release. Name the observed writer or source of churn, retaining
unknown when it was not captured. Protected records remain protected.

### Target allocation and mixed free-space windows

Before an authorized retirement, record the exact target identity, deletion
postcondition, target allocation and same-volume free-space timestamps separately.
Use the read-only native allocation helper below for explicitly selected paths.
From this Skill directory, using physical paths without symlink ancestors:

```bash
python3 scripts/measure_apfs_allocation.py /absolute/selected-root --max-seconds 30 --max-files 100000
```

Exit 0 means the selected bounded metadata walk completed, not that any bytes
are disposable. Exit 2 reports invalid, unsupported or partial measurement;
read `status`, errors and known subsets instead of treating null totals as zero.
Run different devices separately. The limits are checked between metadata calls;
they cannot interrupt a blocked syscall or provide an atomic snapshot.
On supported macOS/APFS it queries ordinary files' `ATTR_CMNEXT_PRIVATESIZE`;
a directory's own zero value is not its recursive allocation. Missing support,
permission failures, disappearing files, unstable identities and bounded partial
walks remain unknown. Deduplicate inodes and close hard-link names.

Single-file private allocation is a diagnostic observation, not the exact release
from jointly deleting a clone cohort. Shared blocks can become free only when
their last references disappear. Keep the target observation, the whole-volume
net change and unknown concurrent allocation/deallocation in separate fields.
Do not subtract one from the other to invent an exclusive writer's contribution.

For short-lived exports, observe the existing job's directory identity, current
allocation and process identity, then read them back after natural completion.
A point observation is not the whole run's peak; natural cleanup is not a leak.
Later activity cannot explain an earlier window without overlapping evidence.
Do not stop another job or delete its active export to isolate a measurement.
Use the result cases in `report_templates.md` to reject unsupported attribution.

### Internal clone-stream bounds

Keep these accounting layers separate: path-accounted bytes, native allocation
bounds for a closed set of clone streams, and same-volume host `df` change.
A VM disk allocation decline is a subsystem observation; it need not equal the
host change over a mixed activity window. Do not force the residual onto cleanup.

For an internal-sharing upper bound, group native observations by device and
clone-stream ID, deduplicate inodes, and count allocated bytes once per stream.
Require stable observations, consistent sizes/refcounts and a full-clone reference
count equal to all observed distinct inodes; account for every hard-link path.
External references, missing members, partial sharing or unknown flags stay
excluded/unknown. A stream ID without those conditions cannot establish closure.
This bound does not account for every snapshot/extent interaction and is not a
promise of bytes freed by removing one member.

`scripts/stream_accounting.py /absolute/observations.json` checks supplied records
as a nonempty JSON list. Each record needs `path`, `device`, `inode`, `logical_bytes`,
`allocated_bytes`, `nlink`, `clone_id`, `full_clone_refs`, `extended_flags`, and
`stable`. Collect those fields through a verified native probe at one stable
checkpoint; the calculator does not collect or authenticate evidence. Its
`internal_allocated_upper_bytes` is an upper bound, not deletion authority.

## 5. Name the writer

A growing directory without an owner is an unfinished row. For each top row:

- The numeric suffix on a macOS `fs_usage` process label is a thread ID, not
  necessarily a PID. For each candidate PID, query the observed 64-bit TID through
  native `proc_pidinfo` `PROC_PIDTHREADID64INFO`, then bind that process's argv
  and start identity. `PROC_PIDLISTTHREADS` returns user-thread handles, not these TIDs.
  Missing mappings stay unknown; do not query a same-numbered PID as attribution.
  Writes to `/dev/null` and overwrites do not themselves prove allocated growth.
  Naming a writer does not make its protected records cleanup candidates.

- Trace the writing process: `ps -axo pid,etime,command` for processes whose command
  line or open files point into the directory, then walk `ps -o ppid=` up to the owning
  application or terminal session.
- AI coding agents keep per-session scratch directories under the system temp root
  (for example `/private/tmp/<agent>-<uid>/…/<session-id>/scratchpad`). Mutation tests,
  frame extraction and full repository clones there can reach tens of GiB in a night.
  The owner is the session, so ask it to prune its own output; do not delete another
  session's working files.
- Build and verification pipelines that keep one full artifact per run grow until someone
  adds a retention rule. That fix belongs in the pipeline, not in a one-off cleanup.

**Multiple independent growth engines require their own lifecycle controls.**
Cleaning the stock without addressing each writer can repeat the same crisis.
The delta table's owner
column is therefore the deliverable, not decoration: every top row needs either a
retention design routed to its owning pipeline, or an explicit "accepted, will refill"
note. Related trap: when the volume is concentrated in the recent window, age-based
heuristics ("keep latest N") cannot hold the bulk — retention design starts from the
volume distribution and the reference graph (see proving-redundancy-before-deletion.md
rung 3b).

## 6. Disk-full emergencies still enter through here

A full disk does not suspend attribution or the Skill's scope and authorization
contract. Follow the same baseline, current-allocation and free-space checks;
do not rank by nominal size or an average inferred from a briefing. Inspect the
actual distribution when a size threshold would select the next action.

For cleanup selection, retain the [Phase 2 entry gate](../SKILL.md#phase-2-report-and-resolve-authorization).
An inactive, verified disposable target does not need to be a recent growth source
to qualify. Conversely, recent growth does not make protected records or an active
job's export disposable. No same-volume readback means no claimed release; an
unexplained residual stays unattributed rather than becoming deletion authority.

## Stop condition

Stop when the attributed rows, plus the non-directory consumers from section 4, cover the
`df` change within a residual you report explicitly. Each top row carries an evidence type
and an owner or writer. A table without owners answers "what" but not "what next".
