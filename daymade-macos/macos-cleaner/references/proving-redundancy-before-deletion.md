# Proving Redundancy Before Deletion — large data folders

For a user-authorized move to an existing external copy, follow
[copied-directory verification](external-cold-archives.md#verify-an-already-copied-directory-lightly)
and its original-entry cutover. Use that bounded acceptance instead of requiring
historical non-use or full-directory SHA verification from this general redundancy ladder.

The caches this skill normally handles have a rebuild path built in. **Large data
folders** (project asset libraries, video material, dataset directories) do not:
deleting them is a user-data decision, and the only defensible way to propose it
is an evidence chain that proves the content is redundant *and* that nothing
alive consumes the copy being removed.

## The wrong question, and the right one

**Do not claim "never used" from timestamps or missing records.** Filesystem
metadata does not establish a complete history of human or application use.

**"Does the covered evidence show it was used as a DATA SOURCE?" is answerable.**
Agent-executed usage can appear in session transcripts and repo code. Inspect
the original commands and their direction; missing records or search coverage
remain unknown. Manual usage is a separate gap, even when agent evidence is
available. The evidence ladder climbs from provable to bounded:

## The ladder (each rung is a command, not an impression)

### 0. Target identity — the candidate is local disk, and you have df'd it

Before anything else: `df <candidate-path>` — the Filesystem column must show
the local data volume (`/dev/disk…`), **not a network mount** (`//host/share`,
`nfs`, `afp`). Keep disk-accounting walks on that filesystem with `du -x`; remote
NAS contents are not local reclaim candidates.

Any path under `/Volumes/` is suspect until df'd,
and in disk-accounting contexts `du` always carries `-x`. **A candidate that
has not been df'd does not enter the evidence table** — no exceptions for
"the size was just measured."

### 1. File-level duplication — prove the content exists elsewhere

Compare the candidate against the suspected canonical copy: file **name + size +
mtime** triple on a sample (pick a mid-listing file, not the first — sort order
bias):

```bash
stat -f "%z bytes mtime=%Sm" -t "%Y-%m-%d %H:%M" "<copy-A>/<sample-file>"
stat -f "%z bytes mtime=%Sm" -t "%Y-%m-%d %H:%M" "<copy-B>/<sample-file>"
# identical size AND identical mtime = candidate clue only, not proof of
# equal content; compare complete SHA-256 values on both ends
```

Then compare directory-level structure (per-subdirectory `du -sk`): matching
subdirectory names with similar sizes across the copies is the duplication
signature; divergent names mean different content and the ladder stops here.

Choose evidence from the asset's preservation contract. For copied-directory
relocation, use the lightweight route linked above. A complete two-end hash can
establish equality of a selected unique artifact; it is not a universal gate for
retiring a reconstructable directory. Preserve missing or unexplained content.
For an archive container, reconcile its member inventory and parse selected
members before retiring the source. Preserve unique signed artifacts and the
only surviving copy until the owning storage contract is met; rebuilding or
re-signing does not recover the original bytes.

### 2. Origin — was the candidate *created from* the canonical copy?

Use the bounded original-record route in rung 4 to find the creation command or
script when provenance changes the decision. A copy command establishes origin,
not current equivalence, disposability or continuing source ownership. Check
later changes and current consumers before choosing which copy to retain.

### 3. Reference check — does anything alive point at the candidate?

Search project trees, Skill configs and scripts for the exact folder name/path:

- **Unbounded grep over a project tree times out** (media files are huge).
  Restrict to text carriers: `--include="*.md" --include="*.json"
  --include="*.yaml" --include="*.yml" --include="*.sh" --include="*.py"
  --include="*.txt" --exclude-dir={node_modules,.venv,.git}`.
- **Recheck Spotlight hits literally.** An `mdfind` result need not contain the
  exact folder name. Verify the actual referencing text before counting a hit.

A hit is only evidence if the referencing thing is **alive**: a pipeline script
(`LIB="~/Downloads/<candidate>"` in a corpus builder) makes the folder
load-bearing infrastructure; a doc sentence describing it makes it a *subject*,
not a dependency. Read the actual lines — never classify from the file list.

### 3b. Reference and registry checks before retention decisions

Before proposing a retention rule or deletion candidate, check:

1. **Volume distribution over time.** Measure the actual histogram before choosing
   an age or batch threshold, and check committed references to the selected
   batches. An old cutoff can miss the largest occupants while deleting required
   evidence; nominal age is not a retention policy.
2. **The code layer, not just documents.** Pipeline source can hardcode path
   patterns. Search the owning code for the path/pattern before declaring
   "zero references"; a zero-reference deletion claim also needs the
   retirement evidence ring: no launchd entry, no live process, content
   frozen since a stated date.
3. **The referenced path's type, not the referencing file's type.** A
   committed originals record's `release_path` points at a release
   *directory* inside the batch (extensionless, may hold binaries).
   Verifying "references point at text" because the files containing the
   references are text is a different check — and the pilot batch sat
   exactly in that blind spot.
4. **Registries before judgement.** A deletion candidate registered in an
   SSOT is a retained asset until its owner's disposition allows retirement.
   Apply that storage contract and update its record after preservation; a copy
   or checksum does not supersede the registry decision.

Slice disposal candidates by semantic classification (reference status x
retention rule), never by mtime/age/du alone.

### 4. Bounded session evidence — did recorded work READ from it?

Enter the [conversation-history router](../../../daymade-claude-code/local-conversation-history/SKILL.md)
for provider selection, indexed discovery and the selected provider's original-record
reader. Follow that owner's current commands and coverage contract rather than
using a raw history sweep. If the required reader or usable index is unavailable,
leave usage unknown and continue independent evidence checks; a cleanup request
does not itself authorize installation or an unbounded scan.

Classify the original tool calls: **read/process from the candidate** (cp FROM
it, Read of files inside, scripts consuming it) vs **write/create into it** vs
**audit only** (du/ls/find — measuring is not using). Preserve source coordinates
and the covered providers, sessions and time window. An index hit locates a
candidate; verify the original call and result before assigning its role.

No ranked hits means no hits in the stated index coverage, not zero read/process
operations. Missing tool records, unindexed sources and manual use remain gaps;
do not use those gaps as evidence that the candidate is disposable.

### 5. .DS_Store — a metadata clue, not a usage verdict

Treat `.DS_Store` observations as filesystem metadata. Copies and automated
operations can preserve or change mtimes; these fields do not identify a person,
establish the last browse time or rule out application/manual use. Reuse an
existing inventory rather than starting another walk solely for attribution.
Keep usage unknown without an original usage record or the user's knowledge.

### 6. The project's own decision records

Before proposing anything, read the owning project's `log.md` and
`_decisions/` for entries about these folders. Original records outrank every
inference above. Resolve the selected asset's role, retention decision and
authorization from that owner rather than its folder name.

## The evidence table — the deliverable

Present every rung as a row with its verdict, and let the unprovable row stay
unprovable:

| Proposition | Evidence | Verdict |
|---|---|---|
| Required material retained | asset-contract checks with stated inventory/content coverage | relocation acceptance within that coverage; do not claim full byte equality from metadata or samples |
| Candidate was created FROM another copy | original creation command | provenance only; assess later changes and current consumers separately |
| Agent read/process usage in covered records | original calls/results, source coordinates, providers and time window | observed use or no use found in stated coverage; gaps remain unknown |
| Project's own decision record | log.md / _decisions quote | proven |
| Manual usage | metadata clues, original usage records or user knowledge | metadata alone leaves usage unknown |
| Non-agent manual use beyond Finder | — | unprovable — user's knowledge only |

Propose deletion only after duplication, origin and live dependencies are
verified and the usage evidence and remaining gaps have been assessed. Unresolved
usage cannot be converted into a non-use verdict. Apply the
[Safety and authorization contract](../SKILL.md#safety-and-authorization-contract)
to the exact target; a history search does not authorize deletion.

## Anti-patterns this reference exists to kill

- **Folder-name role inference.** "交付" / "final" / "backup" in a name says
  nothing about what the folder is for. The creation command and the decision
  log say everything.
- **Content-match as sufficiency.** Two identical folders prove duplication, not
  that one is safe to remove. Usage is a separate axis (rungs 3-5).
- **Treating du output of a folder as "activity."** Audits measure; they do not
  consume. Classify tool calls by direction (read vs write vs measure).
- **Deleting the newer superset because it is "the copy."** Verify which copy
  the live pipeline actually reads *before* choosing the deletion target — on
  2026-09-19 the newer folder was the load-bearing corpus source and the older
  one was the disposable twin; the sizes alone would not have told you which.
- **Candidate lists that mix consequence classes.** Every candidate must carry
  one of: *deletable with evidence* (this ladder), *user decision* (their data
  or workflow knowledge), *preserve* (never-delete list). A flat list of "large
  items" invites the wrong deletions — the 2026-09-19 user ruled agent session
  history absolutely off-limits only after it appeared in such a list.

## Git work containers (worktree / detached HEAD / bundle-origin)

For Git clones, linked worktrees, detached HEADs or bundle-origin repositories,
enter [Git Safety Net](https://github.com/daymade/claude-code-skills/blob/main/git-safety-net/SKILL.md).
Use that owner for common-store dependencies, local-only refs and uncommitted
work, content containment, recovery carriers and retirement. Keep pathname
cutover with this relocation workflow.

Do not infer containment from symbol/test-name hits or a historical merged PR,
or assume untracked files are build outputs. If the owner's workflow or required
helper is unavailable, preserve the checkout and report that dependency gap.
