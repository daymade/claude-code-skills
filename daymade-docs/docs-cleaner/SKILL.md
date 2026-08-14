---
name: docs-cleaner
description: >-
  Consolidates redundant documentation while preserving all valuable content; keeps a doc
  set truthful after things change. Two modes. (1) POST-CHANGE GOVERNANCE — when code,
  scripts, config, env vars, ports, paths, deployment, auth, tests, or a documented
  procedure changed; also "which docs are now wrong", "check docs for inconsistencies",
  "过时的命令/路径", "文档同步". Use it even when the user mentions only the change and never
  the docs — updating them is part of the change, not optional cleanup.
  (2) CONSOLIDATION — "clean up docs", "documentation bloat", "reduce documentation
  sprawl", "consolidate documentation", "too many doc files", "merge redundant docs",
  "merge these docs", "文档太多/太乱", multiple files covering the same topic, or
  documentation exceeding 500 lines across multiple files on similar topics. Finds stale
  copies of a fact changed in only one place, values that should never have been persisted
  (counts, totals, "N items", restated summaries), rival definitions that drift apart,
  and orphaned cross-references.
---

# Docs Cleaner

Documentation goes wrong in two different ways, and they need different work.

**It rots.** Something changed — a port, a path, a procedure, a decision — and the docs
still describe the old world. The field's name for this is *documentation rot* or *version
drift*: artifacts fall out of sync one at a time until people stop trusting the set.

**It sprawls.** The same topic accumulates three files, each partly right, none
authoritative.

Both trace to one root cause: **a fact was written down in more places than it was
defined.** Everything below follows from fixing that.

## Core principle (governs both modes)

**Critical evaluation before deletion. Never blindly delete.** Analyze each section's
unique value before proposing removal. The goal is reduction without information loss.

This governs every deletion-shaped action in this skill, not just consolidation: archiving
a document, dropping a derived value, and removing a cross-reference are all deletions and
all owe the same analysis first. "It looked redundant" is not that analysis.

## Which mode are you in?

| The user said / the situation | Mode |
|---|---|
| "I changed X" / a diff exists / a procedure was updated | **1 — Post-change governance** |
| "which docs are now wrong", "check for stale commands/paths" | **1 — Post-change governance** |
| "clean up the docs", "too many files on this", "merge these" | **2 — Consolidation** |
| A topic is spread over several files with no clear owner | **2 — Consolidation** |

They share the Drift Test below. When both apply, run Mode 1 first: consolidating docs
that are *also* factually stale just produces one confidently wrong document.

**A note on `CLAUDE.md` / `AGENTS.md`:** both modes apply to them like any other document
— govern them after a change, consolidate them when they duplicate each other. The one job
that belongs elsewhere is *restructuring a single oversized one* — pushing low-frequency
detail down into references while keeping the top level lean. That is what
daymade-claude-code's `claude-md-progressive-disclosurer` skill is built for; prefer it
when the problem is size and layering rather than truth or duplication. If it is not
available, Mode 2 still handles the file — you just do the value analysis by hand.

---

## The Drift Test (the core of both modes)

Before writing any value into a document — and when deciding whether an existing one
earns its place — ask these three questions **in order, and stop at the first hit**:

**1. Can this be computed from details already recorded here or in the authoritative
source?**
→ It is a **derived value**. Do not write it. Compute it when someone asks.
Examples: a count ("6 sections", "N groups covered"), a total, a status summarizing rows
in a table below it, "last updated on" when the log underneath already says.

When you remove one, repair the sentence rather than leaving a hole: "the four checks
below" becomes "the checks below". Deleting the number and leaving dangling grammar is a
different defect, not a fix.

*Exception — generated navigation.* A table of contents restating the headings is a
derived value by this test, and hand-maintained ones should indeed go. But leave it alone
when it is produced by the docs toolchain at build time, or when the platform requires the
marker to render navigation: those are computed on demand, which is what question 1 asks
for. Check for a generator before deleting one.

**2. Not computable, but the same fact is authoritatively defined somewhere else?**
→ It is a **copy**. Link to that definition. Do not restate the value.

**3. Neither — it records what was true at a particular moment?**
→ Now you may write it down. Price history rows, decision log entries, "as of 2026-03 the
vendor required X" — these are the legitimate case, and deleting them destroys an audit
trail.

Question 3 needs care, because *every* stale value was true at some moment — that is what
made it stale. But note what question 3 does and does not decide.

**It decides one thing: this passage is not a drift problem.** It is not a derived value and
not a copy, so none of the drift remedies apply to it — do not recompute it, do not link it
away, do not "update" it to the current value. Whether the passage is worth keeping at all
is a *content-value* question, and it is answered in Mode 2's value analysis with the
document's owner, not here.

**Three earlier drafts of this section tried to decide keep-vs-delete right here, and each
one failed review.** The reason is worth stating so nobody rebuilds it: every version needed
the agent to know something it does not have — whether the content could be regenerated, at
what cost, by whom, or whether the other copy someone believes exists actually does. A
delete authorized on an unverifiable belief is the self-certifying shape this skill exists
to remove, and it would be the only evidence-free deletion in the file.

So the test is just the classification:

> **Is this passage describing how things are now?** Then a dated old value in it is a
> question 1 or 2 case wearing a date, and the date does not rescue it.
>
> **Or is it recording what was true at a moment** — a changelog line, a decision log entry,
> a price history row, an incident timeline, a dated measurement, a postmortem? Then it is
> question 3. Leave the value alone.

**Apply this to the passage, not the file** — where *passage* means the unit that would be
read as one thing: **the entry, the table row, the dated note**, the section under one
heading. A how-to guide can contain one genuinely
historical block, and a changelog can carry a current-state summary at the top; a file-level
verdict gets both wrong. But do not run it *below* the passage either — a postmortem's
timeline and its root-cause section are one record, and splitting them so the timeline can
be deleted as "reproducible from logs" destroys the thing whose parts they are.

**Question 3 takes precedence over questions 1 and 2 for these passages, even though it is asked
later.** A changelog line "2026-01-04: raised the upload limit to 50 MB" *does* hit question
2 — the upload limit is authoritatively defined in config — and stopping there would replace
it with a link and destroy the record. Question 1 does the same damage by a different route:
"2026-01-04: added eu-west-3, bringing us to 12 regions" contains a count, and a count is
question 1's own example — but recomputing it yields *today's* region count and rewrites what
that day recorded. The stop-at-first-hit rule is about efficiency, not about routing history
into a link or into a recomputation.

When you cannot tell whether a passage is history or current-state, **ask — do not resolve
it by deleting.** The asymmetry is the reason: deleting a record you mistook for a
current-state restatement destroys the only copy, while keeping a restatement you mistook
for a record costs a few lines. If you are running unattended and cannot ask, leave the
passage untouched and report it.

**Linking only solves case 2.** Pointing a link at a derived value is a category error:
there is no single authoritative cell to point at, so the link becomes scaffolding that
goes stale on its own *and* creates a false impression that the two places are aligned.

**Why this ordering matters:** the mature answer to drift in API documentation is
"generate it from the source, don't hand-copy it" (OpenAPI/Swagger exist for exactly this
reason). Question 1 is that same instinct applied to prose — the surest way to keep a
number correct is for it not to be written down twice.

### Position gives no exemption

A fact is a fact wherever it sits. All of these are body text for the purposes of the test
above, and all of them are where stale values actually survive audits:

frontmatter · YAML/JSON metadata · parenthetical asides · a description column in an index
table · checkbox state · introductory framing before the real content · cross-document
footnotes · an extra column added to a table · commit-message-shaped notes left in prose

### What counts as a fact

Anything that changes over time and has an authoritative definition somewhere: numbers,
status, ownership, relationships, classifications, rules, decision sources, dates, counts.
Business rules count too — "all quotes route through the finance lead" is defined once and
referenced, never restated in each downstream doc.

---

## Mode 1 — Post-change governance

Run these in order. The order is the point: fixing derived docs before establishing what
is authoritative just multiplies the work.

**1. Scope it from the change, not from the repo.**
Enumerate the *facts* this change altered — this port, this path, this procedure name,
this default. That list is what bounds the work. **The list is bounded; the search for
each item on it is not** — a fact's quiet copies live precisely in files the change never
touched, so each fact gets searched repo-wide in step 5. What is forbidden is the other
thing: opening files to look for *unrelated* problems. An unbounded sweep is how a doc task
turns into an unreviewable refactor.

**2. Identify the authoritative source (SSOT) for each affected fact.**
Which file *defines* this port / path / procedure — as opposed to mentioning it? Update
that first. Everything downstream either points at it or is derived from it.

The practical test for "defines" is **where a change has to be made for reality to
change**: the file the deployment actually reads, the schema the code loads, the runbook a
human follows step by step. A file that recites the value while explaining something else
is mentioning it. When two files both look declarative, prefer, in order: the one a machine
consumes over one only humans read; the one nearest the thing it describes; the one other
docs already cite. Then say in your report which you picked and on which of those grounds —
an arbitrary pick becomes permanent once step 2 points everything else at it, so it should
be a stated decision rather than an accident of which file you opened first.

**3. Let the implementation win — as evidence, not as an invitation to edit it.**
Where code, a script, a config file, or an observed run contradicts the docs, the
implementation is the evidence and the doc is the claim. Document what is actually true;
never write documentation describing what you wish the code did.

**If the implementation itself is what is wrong, stop and report it — do not fix code under
this skill.** You cannot tell "the doc is stale" from "the code has a bug" by reading the
disagreement; that judgment needs the intent behind the change, which is the user's. A
documentation pass that silently becomes a code change is the same unbounded-scope failure
step 1 forbids, with worse consequences.

**4. Decide each affected doc's disposition before editing it.**

| The document is… | Do |
|---|---|
| Still actionable; only specific facts drifted | **Update** |
| Built on a premise that no longer holds | **Archive / retire** |

Do not patch a document whose premise is gone — you get something internally consistent
and globally wrong, which is harder to spot than an obviously outdated file.
A "this section is superseded" note left inline is not a third option. Maintainer
bookkeeping does not belong in a reader's path; readers lack the context that makes it
meaningful and only get confused. Move it out.

**"Archive" means: out of the reader's path, still in history.** Concretely: look for a
convention the project already has (`_archive/`, `archive/`, `deprecated/`, or whatever it
uses) and follow it; if there is none, create `_archive/` at the same level as the file.
Either way move it with `git mv` so history follows, then repoint or remove every inbound
reference. Do **not** delete it outright, and do not settle for adding `status: deprecated`
frontmatter while leaving the file where readers still find it — a retired document still
in the reader's path is still being read.

Ask before archiving anything you did not create, for the same reason step 3 of Phase 4
needs agreement. **Running unattended and cannot ask: leave the document untouched and
report it as needing retirement.** Do not patch it instead — a document whose premise died
gets more misleading, not less, when you update its facts.

**5. Find every copy of each changed fact — before you change it.**
This is the step that gets skipped, and it is where the classic failure lives: the obvious
occurrence gets updated and three quiet ones do not. See *Verifying* below for the exact
commands.

The highest-risk shape is **renumbering or inserting an item into a sequence**, because
you are not changing one fact but a whole family of mutually-referencing ones: body text
saying "see step 7", cross-references in sibling files, and — the nastiest — prose that
baked the count into a sentence ("the four checks below"). That last one contains none of
the numbers you are searching for, so a search by step number will never surface it.

**There is no mechanical sweep for this, and you should not pretend otherwise.** Two obvious
scopings were measured and both fail:

- *Search count words repo-wide* → 224,330 lines / ~550 MB on a real documentation repo
  (17.7 MB scoped to a single project directory). Nobody runs that, and an instruction that
  guarantees its own bypass is worse than no instruction.
- *Search count words only in files that mention the subject* → bounded, but **wrong in the
  direction that matters**. Prose that bakes a count into a sentence is exactly the prose
  that refers to the subject by alias, translation, pronoun, or bare link — "the four checks
  below", 「预检有四个检查」 — and never by its title. Measured: a file containing a genuine
  stale count matched *zero* searches for the subject's name or filename. The filter is
  anti-correlated with the target.

So do this instead, and report what it does not cover:

1. **Read the file you renumbered, in full.** Most stale self-references live in it.
2. **Build the file list, then search count words inside it.** Nothing earlier in Mode 1
   produced this list — do not reach for the inbound-reference search in *Updating
   references*, which belongs to Mode 2 and answers a different question ("what pointed at
   this **file**", not "what discusses this **subject**"). Produce it here:

   ```bash
   ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || { echo "not in a git repo — pass the docs root explicitly" >&2; exit 1; }
   rg -l -F "<the subject's name>" "$ROOT" --no-ignore --hidden -g '!.git'
   ```

   That gives you files naming the subject outright; step 3 covers the ones that do not.
   It is a small set, so name the files
   directly rather than piping a list into `xargs` (an empty list makes GNU `xargs` run the
   search with no path at all, which searches the current directory instead — a wrong scope
   that looks like output):

   ```bash
   rg -n -i -H \
     -e '\b(one|two|three|four|five|six|seven|eight|nine|ten|both) [a-z]+\b' \
     -e '[一二三四五六七八九十两](个|条|步|项|点)' -e '[0-9]+(个|条|步|项|点)' \
     -e '\b[0-9]+ [a-z]+\b' \
     path/to/one.md path/to/two.md
   ```
   Two details, both measured: `-H` because `rg` omits the filename when given exactly one
   file, and "which file" is the entire answer here. And the pattern deliberately takes *any*
   following word rather than a list of nouns — a list will not contain the noun your project
   uses ("four **gates**", "three **lanes**") and the miss is silent. Over a handful of files
   the extra noise is cheap; the missed line is not.
3. **List the subject's aliases yourself and search those**, then the count words in whatever
   that turns up. This is the step no tool does for you.

Then say what you checked: *"read the renumbered file; searched count words in the N files
that reference it by name; prose referring to it by other names was not mechanically
covered."* That sentence is worth more than a green check mark that quietly meant one of
the two failures above.

**6. Clean derived values you meet along the way — but only in files you were already
editing.**
Removing a stale count in a file you have open is hygiene, not scope creep. Opening
unrelated files to hunt for more is scope creep. That boundary is what keeps this a
reviewable change.

**7. Report what you did** in the structure under *What to report*.

---

## Mode 2 — Consolidation

Consolidate redundant documentation while preserving all valuable content. The *Core
principle* above governs every deletion in this mode.

### Phase 1: Discovery

1. **Identify all documentation files covering the topic**, and state the boundary you
   searched within (a directory, a suite, one project) before you search — the same
   bounded-scope rule Mode 1 step 1 uses. Two agents given "the docs" and no boundary
   consolidate different file sets. A topic-keyword sweep inside that boundary is the
   usual method — note `-F`, since topic terms like `C++`, `.NET` or `v1.0.0` are literals
   and as patterns they match almost everything:
   `rg -l -i -F -e '<topic term>' -e '<synonym>' <boundary> --no-ignore --hidden -g '!.git'`
   This list scopes the entire consolidation, so a garbage list means a garbage analysis.
2. **Count total lines across files** — `wc -l` over the list from step 1
3. **Map content overlap**: for each heading in each file, note which other files cover the
   same ground. The artifact is a table of heading → files-that-also-cover-it; sections
   appearing in more than one file are the consolidation candidates. This step decides
   **overlap only** — it does not decide keep-or-delete. A unique section can still be
   dropped in Phase 2 for a reason that has nothing to do with duplication (self-evident,
   superseded, a byproduct), so read this as *"nothing here licenses deleting a unique
   section as redundant"*, not as *"unique means it survives"*.

### Phase 2: Value analysis

For each document, build a section-by-section table:

| Section | Lines | Value | Reason |
|---------|-------|-------|--------|
| API Reference | 25 | Keep | Unique endpoint documentation |
| Setup Steps | 40 | Condense | Verbose but essential |
| Env Var Table | 30 | Delete | Duplicates the table in `README.md`, which is authoritative |

Note what the Delete example is *not*: a dated test run, a meeting note, an incident
timeline. Those look like the easiest deletions in any document and they are the one class
this skill will not let you delete quietly — see the rule three paragraphs down. The
example above is a Delete because a named file holds the same content, which is the only
Delete you can justify by pointing at something.

- **Keep** — unique, essential, frequently referenced
- **Condense** — valuable but verbose
- **Delete** — duplicate, one-time, self-evident, outdated
- **Archive** — a whole document whose *premise* is dead (a cancelled system's design notes,
  a retired service's postmortem). It is not stale current-state to be corrected and not
  duplicate content to be dropped. Without this category, "superseded" and "it is a record"
  pull the same document in opposite directions and whichever you read last wins.

  A premise-dead **section** inside a live document is the same problem one level down, and
  Archive does not accept it — it is defined over whole documents. Treat it as a Delete whose
  reason is the dead premise, and name it in the Phase 3 plan rather than deciding it
  yourself: "the Kafka migration section, for a migration that was cancelled" is exactly the
  kind of call the owner may answer with "actually we still reference that".

  **An Archive verdict removes that document from this consolidation.** It does not go on to
  Phase 3 or Phase 4 — there is nothing to merge and nothing to condense. Handle it with
  Mode 1's archive procedure — the paragraph under **Mode 1 — Post-change governance** that
  begins `"Archive" means: out of the reader's path, still in history` — say in your report
  that you did, and carry on
  consolidating the rest. Do not put it in the Phase 3 line-count plan either: it is leaving
  intact, so counting its lines as "reduction" would claim a saving you did not make.

Run the Drift Test over every row as you go, and let it override the categories in **both**
directions:

- A section that only restates values computable from elsewhere is a **Delete** regardless
  of how well written it is (question 1).
- A section **recording what was true at a moment** — a changelog, a decision log, an
  incident timeline, a dated measurement, a postmortem — is question 3, and question 3 says
  only that drift remedies do not apply to it. Its keep-or-delete verdict is a value
  judgment you make here, on this table, like any other row. **The one thing you may not do
  is delete it as a "one-time record" without saying so out loud**: it is the class the
  Drift Test warns is an audit trail, so it goes to the owner as a named proposed deletion
  with your reason, never as a quiet Delete row.

Detailed criteria: `references/value_analysis_template.md`.

### Phase 3: Consolidation plan

Propose the target structure with real numbers, and present it for agreement — this is the
plan Phase 4 asks you to get signed off before anything is deleted:

```
Before: 726 lines (3 files, high redundancy)
After:  ~100 lines (1 file + a pointer from the project's main doc)
Reduction: 86%
Value preserved: pending — established by the preservation check after execution
```

The line counts and the reduction are measurements you can take now. **"Value preserved" is
not**: at plan time it would be the deleting party asserting its own deletion was harmless,
which is the self-certifying shape this skill exists to remove.

It is filled in after Phase 4 step 7, and it is **not a percentage** — a percentage of what
would have to be invented. It is a count against a stated denominator: *"all 34 items on
the step-1 inventory survived"*, or *"31 of 34"* naming the three and where each went.

**The denominator is the Keep and Condense items only.** The step-1 inventory deliberately
also covers Delete sections, and those items are *supposed* to be absent from the
consolidated file — counting them here would make "all survived" unreachable by
construction, and a target nobody can hit is one people stop aiming at. They are accounted
for on their own line: *"and 6 items from Delete sections, each named with where its copy
survives or why it is going"*. Two numbers, two questions, neither one hiding in the other.
Write the denominator, not just the verdict — *"every item I checked survived"* is true of
one item as easily as thirty-four, so it reports your diligence rather than the document's
fate. Anything short of all is a finding to report, never a number to round up, and never a
reason to undo your own condensation so the report reads better.

### Phase 4: Execution

**Deleting someone's documentation is irreversible from the reader's side even when git can
undo it. Present the Phase 3 plan and get agreement before step 3.** Phase 3 says "propose"
for a reason; the Core Principle governs how carefully you analyze, not whether you are
authorized. If you are running unattended and cannot ask, do steps 1–2, stop, and report
what you would delete.

1. **Extract the preservation evidence first — before you write a single line of the
   consolidated document.** The order is what makes the check mean anything: a claim list
   written after the rewrite is a list of what you happened to carry over, so it always
   matches. Written before, it is a specification the rewrite has to satisfy.

   Be honest about what enforces that: nothing in the finished artifact distinguishes a list
   written before from one derived after, so this is a convention, not a gate. Give it the
   only teeth available — **emit the list before you start step 2**, into the report or a
   scratch file. A list that exists in writing before the rewrite can be checked against it;
   one that appears afterwards cannot be told from a transcription of the result.

   **The unit is one entry per load-bearing item, not per section and not per category.**
   How finely to cut is a judgment call and two careful agents will land on different counts
   — that is tolerable. What is not tolerable is which clauses go missing when someone cuts
   coarsely, so two of them get their own entry no matter how you are counting:

   - **The consequence clause.** "Roll back before retrying" is an instruction; "retrying on
     a half-applied migration corrupts the `events` table and there is nothing that repairs
     it automatically" is the reason anyone obeys it. Coarse lists keep the instruction and
     drop the consequence, which is the half that makes it survive a skim.
   - **The symptom → cause mapping.** "A 401 from the deploy step means the token lapsed,
     not that the account is wrong" cannot be re-derived from "the token expires every 90
     days". It is the troubleshooting content, and it is one line long, so it disappears
     first.

   **Those two are a floor, not the boundary of what matters.** They are named because they
   are the clauses coarse lists drop most reliably — not because a clause outside them is
   safe. Three that fall through and are worth checking for by hand: **ordering constraints**
   ("apply the migration before restarting the workers" — no consequence stated, so the first
   rule does not reach it), **scope qualifiers** ("this applies to the `staging` cluster
   only"), and **thresholds buried in prose** ("backs off up to 5 attempts"). Each is one
   clause long, each changes what the reader does, and none announces itself.

   Go through **every** section — including the ones marked Delete — and write down, from
   the source:
   - Keep → one distinctive verbatim line per item in it (each gotcha, each constraint,
     each snippet — a section holding three gotchas owes three lines, not one)
   - Condense → each load-bearing claim: every constraint, number, condition, warning
   - **Delete-as-duplicate → the items in it, and for each, where the surviving copy is.**
     This is the step most likely to be skipped and the one that catches the worst failure:
     Phase 1 maps overlap **by heading**, so a section can be marked duplicate on its title
     while holding one gotcha no other file has. Skip the inventory and that gotcha is
     invisible to every later check — it was never on the list, so step 7 reports "every
     item survived" and means it.
   - Delete for any other reason → the items in it and why each one is going. A deletion you
     can name is a decision; one you cannot is an accident you have not noticed yet.
   - All of the above → every URL, verbatim

   **What this list can and cannot do.** It catches *recall* failures — you meant to carry
   something over and did not. It cannot catch *judgment* failures: if you decided at Phase 2
   that something did not matter, it never enters the list, and step 7 will happily pass
   without it. **That gap is real and nothing in this procedure closes it.** The Phase 3 plan
   goes to a human, but it carries target structure and line counts — not this list — so it
   cannot catch a misjudged item either; it is a check on the shape of the result, not on
   what went into it. Do not report step 7 passing as evidence that nothing valuable was
   lost — report it as what it is, a check that everything you *identified* was carried over.
   If you want the judgment reviewed too, the only thing that does it is showing the item
   list to someone who did not write it.

   One sanity check before continuing: does the item count look like the source material? A
   three-page runbook that yields four items means you skimmed it — and a thin list is
   exactly the list that will later pass.
2. Create the consolidated document, carrying every item on that list
3. Delete the redundant source files
4. Update every reference to them (`CLAUDE.md` / the project's main doc, README, imports)
5. **Leave a pointer to the new location** in the main doc or README — create one if none
   existed. Consolidation moves content to a place nobody has a path to yet; without this
   step the work is discoverable only by whoever did it.
6. Verify no broken links (see *Updating references* below — grepping the bare filename is
   not enough)
7. **Before calling it finished, run the preservation check below**, using the list from
   step 1. It is a gate on this phase, not an optional appendix.

   If you skipped step 1 and the sources were tracked in git, they are still recoverable —
   but mind which ref: **before the deletion is committed** the content is at
   `git show HEAD:<path>`; **once it is committed** that path no longer exists in HEAD and
   you need `git show HEAD~1:<path>` (or the commit before the deletion). The path is
   repo-root-relative, so from a subdirectory use `git show HEAD:./<path>`. Both wrong forms
   fail loudly with `fatal: path ... does not exist`, so you will know. What you must never
   do is take the expected strings from the consolidated file — that measures it against
   itself.

---

## Verifying

Two properties make a documentation check trustworthy: it must match **literally** (facts
contain characters a regex engine reads as wildcards — searched as a pattern, `v1.0.0`
also matches `v1X0X0`, and `[2026-08-13]` aborts as an invalid character range), and it
must match **contiguously** (a fact spanning two lines is one fact, not two).

`ripgrep` gives you both: `-F` matches literally, `-U` lets a match span lines.

**Always pass an explicit path.** This is not a style preference: with no path argument and
a non-interactive stdin — which is what an agent's shell has — `rg` searches *stdin*
instead of your files. Which of two symptoms you get depends on that stdin, and both are
measured:

- **stdin is closed or an exhausted pipe** → exit 1, no output. Byte-identical to "the
  string does not appear anywhere", so the mistake reads as a clean pass. In a directory
  where four files contained the string, the pathless form reported nothing.
- **stdin is inherited and never reaches EOF** → the command **hangs** until something
  kills it. If a search inexplicably hangs, check for a missing path argument before
  concluding the filesystem is slow.

Two flags belong on **every search that walks a directory**, for the reason spelled out under
*What makes this check honest*: `rg` skips VCS-ignored files *and* hidden ones by default,
and `.github/` — full of documented commands — is hidden. A search without them is looking
at a strict subset of the docs (measured: 4 files instead of 6). Searches that name their
files explicitly do not need them — `rg` reads a path you hand it regardless of ignore or
hidden rules — which is why the per-item checks later in this file omit them.

Set the search root once, and make it fail loudly rather than quietly shrinking:

```bash
ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || { echo "not in a git repo — set ROOT to the docs root by hand" >&2; exit 1; }
```

Do not write `|| echo .` here. A silent fallback to `.` scopes the search to whatever
directory you happen to be in and still exits 0 — so "repo-wide" quietly becomes "this
subtree", and a fact living one level up reports as absent (measured). If you are not in a
repo, set `ROOT` to the docs root by hand; the point is that you chose it.

```bash
# Every copy of a fact, before you change it. Path and both flags are load-bearing.
rg -U -F "the exact fact string" "$ROOT" --no-ignore --hidden -g '!.git'

# Per-file counts — the artifact you paste into your report.
rg -U -F --count-matches "the exact fact string" "$ROOT" --no-ignore --hidden -g '!.git'

# Multi-line facts: the newline has to be a real newline. In bash/zsh that means $'...';
# "\n" inside double quotes is a literal backslash-n and matches nothing (measured).
rg -U -F $'first line of the fact\nsecond line of it' "$ROOT" --no-ignore --hidden -g '!.git'
```

`-g '!.git'` is not optional once `--no-ignore` is on: without it the search reports hits in
`.git/COMMIT_EDITMSG` and `.git/logs/HEAD` — the commit messages that *describe* your change
— as surviving copies. Those can never be "cleaned", so a check that counts them trains you
to wave off count mismatches, which disarms it for the real ones. `--no-ignore` also
restores `node_modules/` and other vendored trees; exclude those the same way when they
appear.

**Write down the expected counts before you search, not after.** A count you decide once
you have seen the output cannot fail. State which files should still contain the value and
which should not, then run:

```bash
rg -U -F --count-matches "the old value" "$ROOT" --no-ignore --hidden -g '!.git'
rg -U -F --count-matches "the new value" "$ROOT" --no-ignore --hidden -g '!.git'
```

Compare each result against your list as **set equality**, in both directions: a file that
appears and should not is a leftover, and a file on your list that does *not* appear is
equally a failure — `--count-matches` omits zero-match files from its output entirely, so a
document that was supposed to receive the new value and silently did not looks exactly like
a clean run.

What makes this check honest:

- **The old value does not always go to zero.** A changelog entry, a decision log, or an
  "as of <date> this was X" sentence records history and legitimately keeps the old value
  (Drift Test question 3). Deleting those so a count reaches zero destroys an audit trail
  in order to satisfy a check. Name the historical files in advance; anything *outside*
  that list is a leftover.
- **`--no-ignore --hidden` is on purpose, and they are not the same flag.** By default `rg`
  skips both VCS-ignored files *and* hidden ones. `--no-ignore` only restores the first
  group; without `--hidden` the search still never opens `.github/`, which is where
  contributing guides, issue templates, and workflows full of documented commands live
  (measured: adding `--hidden` took a sample search from 4 files to 6). A convergence gate
  that cannot see those directories goes green over a surviving stale copy. Include them
  and judge the extra hits rather than assuming they do not matter.

**Calibrate before you trust a zero — whichever tool you used.** A search returning nothing
has two causes: the fact is gone, or the command is wrong. They look identical. Before
reporting "no remaining copies", run the same command shape against a string you *know* is
present. If that also returns nothing, the instrument is broken, not the docs. This is the
direct antidote to the pathless-`rg` failure above, and it costs one line.

### Without ripgrep

`git grep -nF "fact" -- .` works in any git repo and is one implementation across platforms
(unlike `grep`, whose recursion and symlink behavior differ between BSD, GNU, and drop-in
replacements). It has these limits, all measured, all of which produce a confident wrong
answer rather than an error:

> **It searches tracked files only.** The consolidated document you just wrote in Mode 2 is
> new and untracked — so a preservation check run through `git grep` reports its content
> missing and you "restore" what was never lost. `git add` it first, or read that file
> directly.

> **`-F` with a multi-line string silently degrades to matching the lines independently.**
> A file that kept only the first line of a two-line fact still reports a hit — so a lossy
> move gets certified as "the content is still there", the one error a preservation check
> exists to catch. True of both `grep` and `git grep`.

With neither tool available, a contiguous check runs anywhere Python does:

```bash
python3 -c 'import sys, pathlib
# .rstrip("\n") matters: your editor adds a trailing newline to needle.txt, and a fact
# sitting at a file'"'"'s end has none — without the strip, that copy is silently missed.
needle = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").rstrip("\n")
for f in sys.argv[2:]:
    n = pathlib.Path(f).read_text(encoding="utf-8").count(needle)
    if n: print(f, n)' needle.txt doc1.md doc2.md
```

### Updating references to a file you moved or deleted

Searching the bare filename finds some inbound links and misses the rest, then reports
"verified". A file is referenced in more shapes than one:

```bash
BASE=old-doc            # filename without extension
rg -n -F -e "$BASE.md" -e "[[$BASE" -e "($BASE" -e "/$BASE" "$ROOT" --no-ignore --hidden -g '!.git'
```

That covers Markdown links, wiki-style `[[old-doc]]`, bare paths, and imports. What it will
not do for you:

- **Relative paths break when a file changes directory depth.** `../guide.md` from one
  level is `../../guide.md` from another. Grepping the filename finds the line; whether the
  path still resolves is a separate question, per link.
- **"Verify no broken links" has two directions, and Phase 4 only owes you one of them.**
  *Inbound* — "does anything still point at what I removed?" — is what consolidation can
  break, and the search above answers it. Do that one; it is the step's actual obligation.

  *Outbound* — "does every link in these files still resolve?" — is a general docs-QA job,
  not something to hand-roll here. Use a real link checker:

  ```bash
  lychee --offline --root-dir "$PWD" docs/   # local paths only, no network
  lychee docs/                               # also checks external URLs (slow, fails for unrelated reasons)
  ```

  `--root-dir` is not optional if the docs use root-relative links (`/docs/x.md` — the
  normal style under mkdocs, Docusaurus, GitHub Pages): without it lychee reports every one
  of them as an error, which is the same false-flagging the paragraph below says to avoid.
  Anchors (`x.md#section`) are not checked unless you add `--include-fragments`.

  **`0 Total` is not a pass — calibrate before you believe it.** Measured (lychee 0.24.2): a
  path that does not exist fails loudly with exit 1, but a directory that exists and holds
  no Markdown prints `🔍 0 Total … ✅ 0 OK 🚫 0 Errors` and **exits 0** — identical to a
  clean run. Point it one directory too high or too deep and you get a green check that
  looked at nothing. Read the `Total` count: if it is 0, either confirm the files genuinely
  contain no links, or you searched the wrong place. (Files whose links are all in inline
  code or fenced blocks legitimately total 0 — lychee skips both, correctly.)

  `lychee` (`brew install lychee` / `cargo install lychee`) parses Markdown properly, which
  a shell pipeline does not: angle-bracket links `[x](<my file.md>)`, titled links
  `[x](y.md "Title")`, nested parens, reference-style `[x][ref]`, and links inside fenced
  code blocks all break a regex-and-`test -e` approach, in both directions — silently
  missing real breakage and falsely flagging valid links. If no link checker is available,
  say the outbound check was not run rather than substituting a hand-rolled one.

### Preservation check (Mode 2)

The old form of this check was a list of things to tick off — "essential procedures
preserved", "gotchas preserved". The person who deleted them ticks the boxes, so it can
never fail. Replace self-assessment with evidence: name each specific item and show where it
now lives. The categories further down are a checklist of *kinds* to sweep for, not the unit
the evidence is counted in.

Use the list you built in Phase 4 step 1 — one entry per load-bearing item, written before
the rewrite. (Missed that step? Phase 4 step 7 says how to recover the sources from git and
which ref to use.) What you must never do is take the expected strings from the consolidated
file: that only proves the file matches itself.

**The method depends on the disposition, and using the wrong one produces a false
deletion report.** A section marked Keep should survive word for word; a section marked
Condense was *supposed* to be rewritten, so a verbatim search for its old sentence
correctly returns nothing — that is the condensation working, not content loss.

| Disposition | How to show it survived |
|---|---|
| **Keep**, carried over as-is | Per saved item: `rg -U -F "<saved distinctive line>" <consolidated file>` → a hit |
| **Keep**, merged with another section — **only if the merge was recorded before the rewrite** (in the Phase 3 plan or the step-1 inventory) | A verbatim search will miss — merging two sections that state the same constraint in different words produces a third phrasing, and that is the point of Mode 2. Use the Condense method below. **Do not paste the original sentences back in to make the search go green**: that reinstates the duplication you were removing. |

**Which of those two rows applies is decided before the rewrite, never at check time.** If you
cannot point at a plan or inventory line saying this section was being merged, the row above
applies and a miss is a miss. This is not bookkeeping: letting the agent whose search just
failed pick which row it is graded by converts a hard verbatim gate into a soft one, and it
converts it *only in the cases where it just caught something*. The failure it lets through
is not merging — it is a plain Keep section quietly reworded during the rewrite, its
consequence clause dropped, relabelled "merged" so the softer method returns a hit on the
weakened sentence.
| **Condense** | Per saved claim (each constraint, number, condition, warning): quote the line in the consolidated file that carries it. A claim you cannot point to was dropped, whatever the prose length says. |
| **Delete** | Per saved item: where the surviving copy is, or — if there is none — the reason it is going. "It looked redundant" is not a reason; naming what was in it is. |

The categories below are a **recall prompt, not the unit** — they exist so you notice a class
you forgot, and each one still resolves to per-item evidence from the table above. Six ticked
categories is not six pieces of evidence.

| Category (applies to Keep and Condense alike) | Evidence to produce |
|---|---|
| Essential procedures (setup, configuration) | per the disposition row above |
| Key constraints and gotchas | same, one per gotcha — these are the load-bearing claims a condensation most often drops |
| Troubleshooting guidance | same |
| Technical debt / roadmap items | same |
| External links and references | each URL saved from a **Keep or Condense** section appears verbatim in the new file (string presence, not an HTTP request). URLs survive condensation intact or they were dropped — there is no "shorter URL". URLs saved from a Delete section follow the Delete row instead: say where the link survives, or that it is going and why. **Do not paste one back into the consolidated file to make this line green** — that reinstates content you decided to drop |
| Debug tips and code snippets | same; code is verbatim even inside a condensed section |

**A hit proves the string is in the file; it does not prove it is in the right place.** A
staging-only warning that landed under a "Production" heading, or a constraint moved out
from under the conditional that scoped it, passes this check while now saying something
false. When an item's meaning depends on where it sits, read the surrounding lines rather
than stopping at the match — the same reason a lossy multi-line move can be certified as
"still there".

Anything you cannot produce a hit for was not preserved — it was deleted. That may be the
right call, but it belongs in the report as a deletion, not inside a checkmark.

**A zero-deletion outcome is a legitimate result.** If the value analysis says every
section earns its place, report "nothing to consolidate" and stop. The reduction percentage
in Phase 3 is a measurement, never a target — an agent that deletes something in order to
have a number to report has inverted the whole point.

---

## What to report

State each of these explicitly. Silence on any of them reads as "nothing to say", which is
rarely true:

1. **Inconsistencies found** — what disagreed with what
2. **Authoritative source used** — which file you treated as defining each fact, and on
   which ground you picked it when more than one looked declarative
3. **Files changed and why** — one line each
4. **Derived values and redundant references removed** — where each one was, and why it
   qualified as derived rather than as a fact worth keeping
5. **Search evidence** — the commands you ran and their counts, so every claim above is
   checkable rather than asserted. This is the same artifact listed under *Output
   artifacts*; both lists mean one report, not two.
6. **The corrected procedure**, end to end, if a procedure changed
7. **What is still unresolved** — untouched exceptions, known-stale areas out of scope,
   risks you could not close

In Mode 2 this report also carries the value-analysis table and the before/after metrics.

Point 4 is the one that gets dropped, and it is the one that compounds: naming a removed
derived value teaches the reader why it should not come back.

---

## Anti-patterns

| Pattern | Problem | Instead |
|---|---|---|
| Blind deletion | Loses information | Section-by-section value analysis first |
| Keeping everything | No reduction achieved | Apply the value criteria strictly |
| Multiple sources of truth | Guaranteed future divergence | One authoritative location, others link |
| Orphaned references | Broken links | Update every reference after moving content |
| Persisting a derived value | Goes stale silently; nothing flags it | Drift Test question 1 — do not write it |
| Linking a derived value | Scaffolding that also goes stale, plus false confidence the two are aligned | Same — the value should not exist |
| Patching a doc whose premise died | Internally consistent, globally wrong | Archive it (disposition, step 4) |
| Updating the obvious occurrence only | Quiet copies survive and contradict it later | Search before editing (step 5) |
| Documenting intended behavior | Doc and reality diverge from day one | Implementation wins (step 3) |
| Unbounded "while I'm here" sweeps | Unreviewable diff; real changes get lost in it | Bounded cleanup (step 6) |

---

## Output artifacts

A successful pass produces:

1. **The corrected documents** — with a single authoritative location per fact
2. **Value analysis** (Mode 2) — section-by-section justification
3. **Before/after metrics** (Mode 2) — lines reduced, value preserved
4. **Search evidence** — the commands run and their counts, so the claims are checkable
5. **Updated references** — a pointer to the new location exists in the main doc or
   README, and every pointer to moved content resolves

## Next Step

After the docs are consistent, the natural follow-ons:

```
Docs are now consistent — [N] files updated, [M] derived values removed.

Options:
A) Convert the recurring parts into a project rule — if the same drift keeps
   recurring, the fix is a rule in the project's main doc, not another cleanup pass
B) Render or publish the result — if these docs have a build/publish step
C) Nothing further — the docs are the deliverable
```
