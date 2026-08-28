# Domain Context Guide

Format and template for per-domain correction context files — the third layer of
the correction system, alongside the dictionary (deterministic replacements) and
the people roster (person names).

## Contents

- What problem this solves
- Location and format
- Worked example
- Machine-readable grammar and maintenance rules

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
- Wrap an exact multi-word ASR form in backticks, for example
  **`CC 思维链` → 目标术语**. The spaces are part of the literal scan target;
  replace the synthetic target with the domain's intended term.
- Order by frequency; prune entries that stop recurring.
- **Machine-readable vetoes (Stage 1 reads these):** add the literal marker
  `禁裸词` or `禁入词典` to a trap's annotation (**妙计 → 妙记（…，禁裸词）**)
  and any *dictionary rule with the same FROM* defers to review at Stage 1
  instead of auto-applying — use it the moment a real-word pair proves
  context-dependent, so the rule can stay in the dictionary (right in some
  contexts) without firing blindly everywhere. A confirmed-correct record
  (**X = 真实实体，勿修**) demotes rules whose FROM is X. Demotion beats
  `--apply-domain` trust; `--apply-all` still applies by explicit override.
  Two authoring constraints, both from the matcher being a per-bullet-line
  literal substring check: write the marker on the trap's own line (a marker
  on an indented continuation line is silently missed), and never *discuss*
  the marker word in a trap line's prose (「评审后决定不标禁裸词」 still
  triggers the demotion it negates) — debate the marking decision anywhere
  else in the file, just not on a trap bullet line.

## Authoritative name sources (pointers, not copies)
This is a **manifest to be read in full**, not a single hint. A project's people
are almost always split across several tables by role — internal speakers,
external collaborators, client-side, vendor/dealer-side, workshop attendees — so
**enumerate every name-bearing table and read each one completely**. Pointing at
only the table that looks like "the speaker list" is exactly how a real,
documented person gets missed (Rule 6).
- The project's alias ledger — **list every person table it holds** (path + each section), not just the main one
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

## Authoritative name sources  (read ALL of these — names split by role)
- Alias ledger: <project-repo>/context.md — 3 person tables, read every one:
  ① top team directory (internal staff) ② §speaker-alias-table (internal speakers + ASR variants)
  ③ §client-and-vendor-side (client + dealer-side staff — e.g. the editor whose name ASR keeps garbling)
- People roster: ~/.transcript-fixer/people.md (team section)
- Dictionary: corrections.db domain `clip-production` (query before adding)
```

## Rules

0. **The format is machine-read, so write it in the shapes the scanner knows.**
   `--scan-traps` parses every **bullet-line-start** `- **<wrong> → <right>**` entry
   out of this file and locates each variant in the transcript mechanically (see
   the Native correction checklist in SKILL.md). The grammar the parser accepts:
   - **Bullet line start is required.** A `**...→...**` pair sitting mid-line in
     prose is NOT parsed (that shape also matches text caught between two
     unrelated bold spans — banning it is deliberate).
   - **Direction is always left-to-right.** `→` is the canonical separator:
     left is the observed ASR form, right is the intended text. Legacy `≈`
     entries are accepted with the same directional convention so older context
     files do not silently scan zero traps; use `→` for new entries because it
     makes the direction explicit.
   - **FROM side, `/`-separated variants**: `**卡帕西/卡帕希 → Karpathy**`.
   - **Exact FROM phrases containing spaces must be quoted as a whole**:
     use this shape:

     ~~~markdown
     - **`CC 思维链`/`CC 思维连` → 目标术语** — domain-specific cue
     ~~~

     Bare whitespace remains unparseable because it is indistinguishable from
     prose; backticks declare that every internal space belongs to the literal
     scan target.
   - **FROM side, parenthesized**: a `/`-separated list inside parens is a variant
     family — `**升单系（圣诞/上单/生单 → 升单）**` scans only 圣诞/上单/生单, never
     the family-name prefix (it may be a real word). Parens WITHOUT a `/` inside
     are treated as a comment and the scan target is the word outside them —
     write `**减（减少的减） → 剪**` and only 减 is scanned.
   - **TO side**: cut at the first parenthesized annotation (`→ 爆（anchored）`
     displays as 爆).
   - **Confirmed-correct record**: `=` plus a keep-word, e.g.
     `- **Brooklyn = 真实实体，勿修** — 教育博主 IP 名。` — reported as keep-as-is,
     so a later pass stops re-investigating a settled name. The recognized
     keep-words are: `勿修` / `非误识` / `确认正确` / `保留原样` / `不要改` /
     `不用改` / `别改` / `无需修改`.
   A trap the parser can't read is a trap that never gets scanned — when in
   doubt, run `--scan-traps` once and check the entry count in the header.
   The scanner excludes only a single-line value of the leading frontmatter
   field `asr_note`, because that field intentionally cites old forms as
   correction provenance. Multi-line block/folded values are not masked.
   Keywords, titles, and body text remain in scope.
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
6. **The name-source list is a complete manifest, and it self-corrects.** Names
   scatter across role-based tables (internal / external / client / vendor /
   attendees), so the pointer must enumerate *every* table and the reader must
   read *all* of them — stopping at the first "speaker list"–looking table is the
   recurring miss. Make the enforcement structural, not willpower: if you ever
   confirm a project person whose name is NOT reachable from any manifest entry,
   the manifest is incomplete — add the missing table to it before finishing, so
   the next run cannot repeat the miss. (2026-07-15: a context file pointed only
   at one `§speaker-alias-table`; the agent faithfully read that single table and
   flagged a real editor — documented all along in the sibling dealer-side table
   — as "unverifiable".)
