# Growth Attribution — what has been filling the disk lately

Read this when the question is about **change**, not size: "what has been taking
space these past weeks", "I had 200 GB free last month", "free space dropped overnight",
or when an older disk-scan export exists. A size ranking answers "what is big". It does
not answer "what grew", and the largest directories are often old, stable content.

Everything here is Phase 1 (read-only). Any deletion that follows still goes through the
Phase 2 entry gate in SKILL.md.

## Contents

- Output shape
- 1. Find a baseline before estimating
- 2. Diff a baseline export against the current disk
- 3. Timestamp estimate
- 4. Reconcile against free space
- 5. Name the writer
- 6. Disk-full emergencies still enter through here
- Stop condition

## Output shape

A delta table: directory, baseline size, current size, delta, window, **evidence type**
(baseline diff or timestamp estimate), and the owner or writer when known. Keep three
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
   line. A whole-disk export runs to millions of lines and about 1 GB.
2. **Measure the same paths now** with `du -skx` at matching depths.
3. **Calibrate the size semantic before trusting any delta.** Pick one directory you know
   has not changed since the export and compare the export's sum with `du` for it. If they
   disagree, the export measured a different size (logical vs allocated), and every delta
   carries that bias.
4. **Treat absent or near-zero baseline rows as "not scanned", never as "new".** An export
   silently omits whatever the scanner could not read or skipped: privacy-protected folders
   when the app lacked Full Disk Access, other apps' sandbox containers, and sometimes whole
   hidden directories. Observed: one baseline showed a sandboxed messaging app's container
   at 2 GiB against 108 GiB now, yet only 1.4 GiB of its files had arrived after the
   baseline date. A naive diff reported 106 GiB of growth that never happened.
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
blocks are shared: APFS clones (see SKILL.md safety rule 11 and
`references/chromium_code_sign_clones.md`), and caches whose contents are cloned or
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

**A clonefile snapshot's cost is delayed, not zero.** Deleting a full-clonefile
snapshot releases ≈0 at deletion time, but the cost lands later: as the live tree
churns, blocks shared with the snapshot get pinned and gradually turn real —
measured 2026-10-21, a snapshot already held files that no longer existed in live
(`raw/codex/history.jsonl`, `generated_images/*.png`), i.e. it was already the sole
owner of deleted content, and two same-day incremental snapshots' state DBs had
fully diverged into ~3 G of real bytes. Two consequences: the snapshot directory's
size root is the *live home it captures* (here `~/.codex` 108 G / `~/.claude` 20 G),
so governing the snapshot directory without governing the live source solves
nothing; and as an emergency-reclaim target a clonefile snapshot is a complete
miss — it frees ≈0 today while its real cost accrues tomorrow. Attribution rows
for snapshot directories must name the live source as the writer, not the capture
script.

### Internal clone-stream bounds

Keep three accounting layers separate: path-accounted bytes, native allocation
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
  necessarily a PID. Map it contemporaneously through native `proc_pidinfo`
  `PROC_PIDLISTTHREADS`, then bind the parent process's argv and start identity.
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

**Multiple independent growth engines mean a one-off cleanup is a recurring crisis, not
a fix.** Measured 2026-10-21, one disk held at least five mutually independent engines,
each with its own writer and none with retention/TTL: a package cache fed by ~2,800
scheduled tool invocations/day plus 48-58 new ephemeral environments/day (~2.6 GB/day);
an agent session home whose October volume alone was 29 GiB (screenshot-heavy
computer-use sessions double-writing tool outputs); a releases directory whose retention
had been silently blocked since install (18 G, only grows); a deliveries directory with
no retention; a snapshot pipeline still capturing while publishing was broken, plus a
12 G gate-artifacts directory with no TTL still being written. Cleaning the stock
without designing retention into each writer repeats the same crisis monthly — the
09-19 prune to 10-21 full disk was one complete measured cycle. The delta table's owner
column is therefore the deliverable, not decoration: every top row needs either a
retention design routed to its owning pipeline, or an explicit "accepted, will refill"
note. Related trap: when the volume is concentrated in the recent window, age-based
heuristics ("keep latest N") cannot hold the bulk — retention design starts from the
volume distribution and the reference graph (see proving-redundancy-before-deletion.md
rung 3b).

## 6. Disk-full emergencies still enter through here

A 100%-full disk does not suspend this reference; it makes it mandatory. Measured
2026-10-21: an emergency run that skipped growth attribution and ranked targets by
nominal `du` picked phantom targets three times in one day (a 123 G cache that released
~38 GiB; a 108 G clonefile snapshot that released ≈0; a backup set with the same
structure), while the largest real growth engine (`~/.codex` sessions, 76 G and
+29 GiB/month) sat outside the governed scope entirely until a late attribution pass
found it. In an emergency, order targets by *attributed recent physical growth* — the
section-3 ctime/allocated-bytes estimate and the section-4 `df` reconciliation — not by
nominal size. A full per-file census also beats briefing arithmetic: the briefing's
"38.25 GiB / 52 files / avg 753 MB" implied a >500 MB big-file strategy with a 6.9 G
ceiling; the 15,202-thread census (0 missing, du and stat in agreement) showed the real
mean is ~5 MB across a long tail, and the big-file strategy was correctly rejected.
Emergency or not: no df readback, no claimed release; no growth attribution, no target
ranking.

## Stop condition

Stop when the attributed rows, plus the non-directory consumers from section 4, cover the
`df` change within a residual you report explicitly. Each top row carries an evidence type
and an owner or writer. A table without owners answers "what" but not "what next".
