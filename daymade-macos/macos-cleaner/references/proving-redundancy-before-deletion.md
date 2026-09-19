# Proving Redundancy Before Deletion — large data folders

The caches this skill normally handles have a rebuild path built in. **Large data
folders** (project asset libraries, video material, dataset directories) do not:
deleting them is a user-data decision, and the only defensible way to propose it
is an evidence chain that proves the content is redundant *and* that nothing
alive consumes the copy being removed.

This reference exists because of a 2026-09-19 session that proposed deleting a
109 GB folder from a folder name and a file comparison — and was correctly
challenged with "how do you prove it was never used?". The name-based inference
was wrong in principle: a folder called `X-交付` ("delivery") tells you nothing
about its role. What replaced it, below, is the method.

## The wrong question, and the right one

**"Was it ever used?" is unprovable and the wrong target.** File atime is dead on
modern macOS (APFS mounts `noatime` by default — access does not update
timestamps), and a human opening files in Finder leaves no log. No evidence can
support "never used."

**"Was it ever used as a DATA SOURCE?" is answerable.** Agent-executed usage
(Bash commands, Read/Write/Edit tool calls, pipeline code, scripts) lives in
session transcripts and in the repo. Census that, and the residual — purely
manual usage — shrinks to a traceable surface (.DS_Store, below). The evidence
ladder climbs from provable to bounded:

## The ladder (each rung is a command, not an impression)

### 0. Target identity — the candidate is local disk, and you have df'd it

Before anything else: `df <candidate-path>` — the Filesystem column must show
the local data volume (`/dev/disk…`), **not a network mount** (`//host/share`,
`nfs`, `afp`). A 2026-09-19 disk-accounting session walked `du` **without `-x`**
into `/Volumes/homes` — an SMB-mounted NAS — and surfaced 837 GB of remote NAS
content as a candidate "big item" on the local disk. It was neither local nor
one item: it was other people's data on other people's disks, and the whole
"270 GB accounting gap" that motivated the walk was manufactured by the
measurement itself.

Two rules this rung enforces: any path under `/Volumes/` is suspect until df'd,
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
# identical size AND identical mtime = same file (copy), not independently
# created content
```

Then compare directory-level structure (per-subdirectory `du -sk`): matching
subdirectory names with similar sizes across the copies is the duplication
signature; divergent names mean different content and the ladder stops here.

### 2. Origin — was the candidate *created from* the canonical copy?

The strongest single piece of evidence: find the session or script that created
the candidate. A creation command naming the other copy as source settles the
relationship permanently:

```text
rm -rf "<candidate>" && mkdir "<candidate>" && SRC="<canonical>" && for d in ...; do cp ...
```

Search session history for the folder name (see rung 4) and read the creation
commands verbatim. "Created by copying from X" means the candidate is derived,
not source — source lives at X.

### 3. Reference check — does anything alive point at the candidate?

Grep project trees, skill configs, and scripts for the folder name/path. Two
traps that both cost time on 2026-09-19:

- **Unbounded grep over a project tree times out** (media files are huge).
  Restrict to text carriers: `--include="*.md" --include="*.json"
  --include="*.yaml" --include="*.yml" --include="*.sh" --include="*.py"
  --include="*.txt" --exclude-dir={node_modules,.venv,.git}`.
- **`mdfind` is a fuzzy match, not a literal one.** Spotlight tokenizes:
  searching `素材库-交付` returns every document containing 素材库 *and* 交付
  separately. Every mdfind hit must be re-checked with a literal `grep` in the
  file before it counts (all 8 hits on 2026-09-19 were false).

A hit is only evidence if the referencing thing is **alive**: a pipeline script
(`LIB="~/Downloads/<candidate>"` in a corpus builder) makes the folder
load-bearing infrastructure; a doc sentence describing it makes it a *subject*,
not a dependency. Read the actual lines — never classify from the file list.

### 4. Session-history census — was it ever READ from?

This is the rung that answered the 2026-09-19 question, and it is a
mechanical sweep, not a search:

```bash
# Claude (all sources incl. archives) + Codex rollouts, bounded by date,
# excluding the current session
<read-claude-code-history>/scripts/analyze_sessions.py search \
  --all-projects --exclude-session <CURRENT_SESSION_ID> --codex \
  --from-date <YYYY-MM-DD> '<folder-name-1>' '<folder-name-2>'
```

Read the **label census** per matched session (`tool_input:Bash` /
`tool_input:Read` / `tool_result` / `message` …). Then classify the actual tool
calls: **read/process from the candidate** (cp FROM it, Read of files inside,
scripts consuming it) vs **write/create into it** vs **audit only** (du/ls/find
— measuring is not using). On 2026-09-19 this produced the decisive line: 300
matched session files across 3 months, **zero** read/process operations, only
the creation command (rung 2) and du audits.

Two coverage facts to state in any report: Kimi sessions are a separate store
(`--kimi` widens the search) — if the project's work spanned Kimi, include it;
and this census covers agent-executed work only. Manual usage is rung 5.

### 5. .DS_Store — the last manual-usage trace

Finder creates `.DS_Store` in every folder a human opens. The newest
`.DS_Store` mtime inside the candidate = the last time a human browsed it:

```bash
find "<candidate>" -name .DS_Store -newermt "<suspect-date>" 2>/dev/null
find "<candidate>" -type f -newermt "<date>" | head    # what else was touched
```

A folder whose only recent activity is `.DS_Store` was *looked at*, not *used*.
Anything beyond Finder (QuickTime, dragging into an app) leaves no trace —
report that boundary honestly rather than papering over it.

### 6. The project's own decision records

Before proposing anything, read the owning project's `log.md` and
`_decisions/` for entries about these folders. Original records outrank every
inference above: on 2026-09-19 the project's own ledger labelled the candidate
"分类库交付孪生" (delivery twin of the working library) and its decision log
recorded "本地分发线废除" (local distribution line abolished) — both from the
user's own earlier decisions, weeks before this investigation existed.

## The evidence table — the deliverable

Present every rung as a row with its verdict, and let the unprovable row stay
unprovable:

| Proposition | Evidence | Verdict |
|---|---|---|
| Content duplicated in canonical copy | name+size+mtime triple, structure match | proven |
| Candidate was created FROM canonical | creation command verbatim | proven |
| Zero agent read/process operations | 300 sessions censused, label-classified | proven (scope: Claude+Codex, since <date>) |
| Project's own decision record | log.md / _decisions quote | proven |
| Manual usage | .DS_Store newest mtime = <date> | bounded: browsed at most |
| Non-agent manual use beyond Finder | — | unprovable — user's knowledge only |

**Deletion is proposable when rungs 1-3 are proven and rungs 5-6 bound the
residue.** The final gate is still the user's: they are the only one who can
close the last row.

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
