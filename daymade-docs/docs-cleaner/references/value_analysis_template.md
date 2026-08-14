# Value Analysis Template

Use this template for section-by-section documentation analysis.

## Document Analysis Table

| Section | Lines | Value | Reason |
|---------|-------|-------|--------|
| Example Section | 25 | Keep | Contains unique troubleshooting steps not documented elsewhere |
| Another Section | 40 | Delete | Duplicates content in CLAUDE.md |
| Technical Details | 60 | Condense | Valuable but verbose; can be reduced to 15 lines |
| Setup Instructions | 30 | Keep | Essential for onboarding |

## Value Categories

### Keep (Green)
- Unique information not found elsewhere
- Essential procedures (setup, troubleshooting, constraints)
- Frequently referenced content
- Technical debt / roadmap items

### Condense (Yellow)
- Valuable but overly verbose
- Contains redundant examples
- Can be expressed more concisely

### Delete (Red)
- Duplicates existing documentation
- One-time material with no continuing reader and no moment attached to it — a pasted copy of
  a tool's `--help` text, a duplicated third-party quickstart. Note what this bullet's example
  is *not*: "a pasted test run's output" would be a **dated measurement**, which the carve-out
  below excludes — an example that its own exception swallows is worse than no example.
  **⚠️ Never a passage that records what was true at a moment** (changelog, decision log,
  incident timeline, dated measurement, postmortem). That class is the Drift Test's question
  3; it may still be deleted, but only as a **named proposal to the owner with your reason**,
  never as a quiet Delete row. When you cannot tell, ask; do not resolve it by deleting.
- Self-evident information (code already documents this)
- Outdated or superseded content — **but "superseded" is a Delete only for content that was
  describing the current state.** A document whose *premise* is dead (the design notes for a
  cancelled system, a postmortem for a service since retired) is not stale current-state; it
  is the record of a decision, and it goes to **Archive / retire** — moved out of the
  reader's path, not destroyed. Without this split, the same dead-project postmortem gets
  Deleted by one reader for being superseded and Kept by another for being a record.

## Before proposing deletions

These are observations to produce, not boxes to tick. A tick is written by the same party
that wants the deletion approved, so it can never come back negative; each line below asks
instead for something a reader could check.

| Question | What to show |
|---|---|
| Which files hold related content? | The search boundary you used and the command that produced the file list |
| Where do they overlap? | The heading → files-that-also-cover-it table |
| What is unique to each? | Per file, the sections no other file covers |
| Which location becomes authoritative? | The chosen file, and why that one |
| What references will need updating? | The list of inbound references found, per file being removed |

## Applying the Drift Test to a row

Run the SKILL.md Drift Test over every row. It settles one of the two disposition questions
and deliberately leaves the other to you.

**It does decide "this is a derived value":** a section can be well-written, unique to this
file, and still not belong anywhere — if its content is computable from details recorded
elsewhere (a count, a total, a restated summary), it is a derived value and the disposition
is Delete regardless of quality.

**It does not decide keep-or-delete for historical passages.** When question 3 fires — the
row records what was true at a moment — all it establishes is that no drift remedy applies:
do not recompute it, do not link it away, do not update it to the current value. The value
judgment stays on this table, and if it comes out Delete, it goes to the owner as a named
proposal with your reason rather than a quiet Delete row.

## Output Format

After analysis, produce:

1. **Value Analysis Table** - Per-section breakdown with keep/condense/delete
2. **Consolidation Plan** - Target structure with line count estimates
3. **Before/After Comparison** - Total lines and percentage reduction
4. **Preservation evidence** - One entry per load-bearing item (each gotcha, constraint,
   snippet, URL — not one per category), showing where that item now lives. Anything you
   cannot point to is a deletion and gets reported as one.
