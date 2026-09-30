# Goal B — retire auto memory for a project

Use this when the user wants a project to stop using auto memory and have documents own
everything it held. It differs from Goal A in one decisive way: **there is no "stays in
memory" bucket.** Handoff state, external pointers and pending rulings all need a document
home, and at the end the memory directory is empty.

## 1. Scope the switch before touching anything

Auto memory is on per project. Count what else would be affected before choosing where to
turn it off:

```bash
for d in ~/.claude/projects/*/memory; do
  n=$(ls "$d" 2>/dev/null | grep -c '\.md$'); [ "$n" -gt 0 ] && echo "$n $(basename "$(dirname "$d")")"
done | sort -rn
```

Turn it off only for the project being retired. The global switches
(`autoMemoryEnabled` in `~/.claude/settings.json`, or `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`)
silently stop every other project's memory from loading; use them only when the user asks
for all projects.

## 2. The memory directory is shared by every session in that project

Every session started in the project reads and writes the same directory. Other sessions
may be writing to it while you migrate. Before migrating:

- list the live sessions of that project and tell them the directory is being retired and
  where new lessons should go instead;
- record a hash of each memory file at the moment you migrate it;
- immediately before archiving, compare the hashes again and re-migrate any file that changed.

## 3. Inventory: search every place that could already own the content

Most entries in a mature memory directory are already covered somewhere. An entry counts as
covered only when the owning document carries its operative content (conditions, numbers,
commands), not just the same keyword.

Search all of these, and **list them explicitly in any sub-agent prompt** — an agent that is
not told about a root does not search it, and reports "no home" with full confidence:

- the global and project instruction files, and every file under `~/.claude/references/`;
- **every skill source repository**, public and private, plus installed skill directories;
- project documents, decision logs and handover packs;
- hook and script headers, which often carry the rule a memory entry describes.

Before trusting a zero-hit search, run the same command shape on a string you know exists.
An empty result from a command that searched nothing looks identical to a real absence.

## 4. One disposition per file, with evidence

| Disposition | Evidence required |
|---|---|
| Covered | path and line of the owning text |
| Migrate | the owning document and why it owns the content (general knowledge → the skill for that domain; project state → that project's documents; machine facts → the machine reference) |
| Finished | the artifact that shows the work is done (merged PR, shipped file, decision record) |
| Needs ruling | what the user has to decide |

Destinations for the content Goal A would have left in memory:

- **handoff state and open to-dos** → the project's decision log or open-items document, or
  a handover pack if the project keeps them;
- **external pointers** → the project document that uses them;
- **pending rulings** → the project's open-items document, stated as a question.

For entries with real names or other identifying detail, follow the user's existing rulings
on where such content may live. Do not reopen a ruling because the destination looks
different this time. With no ruling, the dated archive in §9 is private and local, so it
satisfies Phase 1's "stay in private memory"; do not move such entries into shared documents.

## 5. Migrate verbatim, then check every line landed

`scripts/migrate_verbatim.py` appends each memory body to its owning document under a dated
section, strips the frontmatter, demotes headings outside code fences so they nest, skips
items already migrated, and fails if any line of the rendered body is missing afterwards.
That check proves the write, not the heading transform: after the run, read the diff of any
entry whose code blocks contain `#` lines. Moving is not the moment
to edit: condensing while migrating is how qualifiers disappear.

## 6. Repoint pointers, but only the ones that send readers somewhere

Search every document, hook and test for the memory file names. Two kinds of mention:

- **jump pointers** — "details in memory X" — send a reader to a file that is about to
  disappear; repoint them to the new location;
- **provenance notes** — "this rule was first written in memory X" — are history; leave them.

When a hook message cites a memory file and its test asserts that citation, update both in
the same change.

## 7. Commit only your own changes

Owning documents often sit in shared working trees where other sessions have uncommitted
edits in the same files. Commit your hunks only and leave theirs uncommitted exactly as you
found them.

## 8. Turn it off, then prove it with a control

Set the project switch in `<project>/.claude/settings.local.json`, the per-user settings
file that is normally not committed (merge the key into the existing object):

```json
{ "autoMemoryEnabled": false }
```

Then check with a fresh headless session, and run the same question in a project that still
has memory on:

```bash
Q='Answer one line: does your context contain an auto memory MEMORY.md index listing memory .md files? YES or NO; if YES quote its first entry file name.'
(cd <retired-project> && claude -p --model sonnet "$Q")   # expect NO
(cd <memory-enabled-project> && claude -p --model sonnet "$Q")   # expect YES and a real file name
```

A NO without the YES proves nothing: a probe that cannot see memory anywhere answers NO too. If no
other project has memory on, create a scratch directory with one memory file under its
`~/.claude/projects/<slug>/memory/` for the YES run, then remove it.

## 9. Archive everything, with an index

Phase 6's **Keep** does not apply here: every file leaves `memory/`.

Move every file out of `memory/`, including `MEMORY.md` and earlier `.archived-*` files, to
a dated sibling directory outside it (`~/.claude/projects/<slug>/.memory-archive-<date>/`).
Write an `INDEX.md` there with one row per file stating where its content now lives. Old
documents will keep mentioning memory file names; the index is how a later reader finds the
current home.
