# Domain Context Guide

Format and template for per-domain correction context files — the third layer of
the correction system, alongside the dictionary (deterministic replacements) and
the people roster (person names).

## What problem this solves

Three kinds of ASR errors, three homes:

| Error class | Example | Home | Why |
|---|---|---|---|
| Deterministic, non-word | `克劳锐`→`Claude` | Dictionary (`--add --domain`) | Zero false-positive risk; a rule fires the same way every time |
| Person names | garbled coworker/client names | People roster (`people.md`) | Names need relationship context and survive DB resets |
| **Context-dependent homophones** | `减`→`剪` only when discussing clip production | **Domain context file** | A rule would corrupt other sentences (`减少` is real); only in-context judgment can decide |

The third class is invisible to Stage 1 by design and *undercorrected* by a
generic AI pass: without a domain prior, the AI suspects the error but won't
touch it — the fix falls to the human, every time it recurs. The context file
supplies that prior once, and every future native run on this domain benefits.

## Location

One file per domain, in user space next to `corrections.db` and `people.md`:

```
~/.transcript-fixer/contexts/<domain>.md
```

`<domain>` matches the `--domain` name you already use for the dictionary
(e.g. a project slug). If you relocate the config dir via
`TRANSCRIPT_FIXER_CONFIG_DIR`, contexts live under that dir's `contexts/`.

Never put context files inside the skill bundle — skill installs are wiped on
update, and domain knowledge is often private to a project.

## Format

Free markdown, but keep it short (aim under ~80 lines — it's read at the start
of every native session on this domain) and cover three sections:

```markdown
# <domain> — correction context

## Business context (1-3 lines)
What recordings in this domain are about; the vocabulary universe.

## Homophone traps (the core section)
For each trap:
- **<wrong> → <right>** — the disambiguating cue: WHEN is the right reading
  intended? Add a dated real example if you have one.
- Order by frequency; prune entries that stop recurring.

## Authoritative name sources (pointers, not copies)
- Where the project's alias ledger lives (path + section)
- Which people-roster sections apply
- Existing dictionary domains to query first
```

## Worked example (generic)

```markdown
# clip-production — correction context

## Business context
Weekly production meetings for a short-video team: clip output quotas,
editing assignments, per-channel performance reviews.

## Homophone traps
- **减 → 剪** — when the sentence is about producing/editing N clips
  ("每天剪 5 条", "剪出来", "剪到 N 条"), 剪 is almost always intended;
  减 is correct only for genuine decrease ("减少预算"). Seen 4x on 2026-07-10.
- **美佳 → 每家** — this project compares multiple franchise stores, so
  "每家" (each store) is frequent; ASR hears it as the given name 美佳.
  Cue: the sentence assigns tasks to or compares stores.

(Counter-example of what does NOT belong here: 云条→语音条 — 云条 is not a
word, so it's a deterministic fix and went to the dictionary via
`--add "云条" "语音条" --domain clip-production` instead. Only entries whose
"from" side is real text in some other reading stay in this file.)

## Authoritative name sources
- Alias ledger: <project-repo>/context.md §speaker-alias-table
- People roster: ~/.transcript-fixer/people.md (team section)
- Dictionary: corrections.db domain `clip-production` (query before adding)
```

## Rules

1. **Cues, not rules.** Every entry must state the contextual condition under
   which the correction applies. An entry without a cue is a dictionary rule in
   disguise — and common-word rules are exactly what corrupts transcripts.
2. **The file primes judgment; it never authorizes blind replacement.** Every
   fix still goes through the native workflow's confidence triage. If the cue
   doesn't clearly hold for a given sentence, the occurrence stays untouched
   and goes to the needs-checking list.
3. **Point to name sources, don't copy them.** Copied name tables drift; the
   alias ledger and roster stay the SSOT.
4. **Maintain it like the dictionary.** After a native session, recurring
   context-dependent fixes get appended here (with their cue and date);
   deterministic fixes keep going to `--add`; names go to the roster. If an
   entry stops matching reality, delete it — a stale prior misleads the AI
   the same way a bad rule does.
5. **Private stays private.** These files may name real people and projects.
   They live in user space precisely so they never ship with the skill; don't
   paste their contents into public repos or shared docs.
