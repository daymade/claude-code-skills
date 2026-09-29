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

- **Swap.** `sysctl vm.swapusage`, and the VM volume's "Capacity Consumed" in
  `diskutil apfs list`. Heavy memory pressure can add tens of GB overnight and gives the
  space back only when pressure falls.
- **Local snapshots.** `tmutil listlocalsnapshots /`.
- **Short-lived copies.** Temporary checkouts or clones created and deleted between two
  readings. Free space that dips and recovers without any directory change is this shape.
  Files that vanish between a `find` and its `stat` point to the same cause.

Report the remainder as **unattributed** rather than forcing it onto the nearest large
directory.

## 5. Name the writer

A growing directory without an owner is an unfinished row. For each top row:

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

## Stop condition

Stop when the attributed rows, plus the non-directory consumers from section 4, cover the
`df` change within a residual you report explicitly. Each top row carries an evidence type
and an owner or writer. A table without owners answers "what" but not "what next".
