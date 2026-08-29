# Dictionary, identity, and domain-context workflow

Read this file before adding reusable corrections, resolving names, editing the people roster, or maintaining a domain context file.

## Contents

- Dictionary-addition decision matrix and corpus probes
- Project-domain isolation
- People-roster precedence and variant families
- Domain correction contexts

### Dictionary Addition After Fixing

After native AI correction, review all applied fixes and decide which to save. Use this decision matrix:

| Pattern type | Example | Action |
|-------------|---------|--------|
| Non-word → correct term | 克劳锐→Claude, cloucode→Claude Code | ✅ Add (zero false positive risk) |
| Rare word → correct term | 拉行链→LangChain, 哈金费斯→Hugging Face | ✅ Add (verify it's not a real word first) |
| Person/company name ASR error | 卡帕西→Karpathy, Anthropics→Anthropic | For an **important recurring** person/entity and a recurring deterministic garble, use the **people roster** or `--add --domain` as described below. A one-off or rare sentence-local name error is a file-only edit; do not create a reusable rule. |
| Common word → context word | 争→蒸, 减→剪, affect→effect | ❌ Never add as a rule — record the trap + its disambiguating cue in the domain's context file instead (see "Domain Correction Contexts") |
| Real brand → different brand | Xcode→Claude Code, Clover→Claude | ❌ Skip (real words in other contexts) |
| Real name → different real name | `李明`→`黎明` (two real people in different projects) | ❌ Never a rule — same hazard as real brand → brand, but it corrupts a real person's name. Domain context trap with a disambiguating cue instead (see [native_ai_full_workflow.md](native_ai_full_workflow.md)) |

**The middle path, and it applies to exactly one of the ❌ rows.** The
*common word → context word* row (`争`→`蒸`) forbids a **bare** common word as a
rule, because it fires everywhere the word is legitimately used. It does not
forbid the same fix carried by enough surrounding text that the phrase only
occurs in the mishearing — `村里商量` → `<name>商量` is defensible where bare
`村里` would be reckless. **The *real name → different real name* row is not
relaxed by this and never anchored into the dictionary**: keep it in the domain
context file as the row itself says.

That exclusion holds because **the validator cannot be trusted either way on a
person's name.** `--add` runs a jieba check that warns when the FROM side
decomposes into all-known words, and whether a name counts as "known" is an
accident of jieba's dictionary: measured, `李娜商量` warns (`李娜` has frequency
438) while `张伟商量` is silent (`张伟` is out-of-vocabulary, frequency 0). So a
name-anchored rule that passes quietly tells you nothing, and one that warns
tells you nothing either. With no reliable signal on the class whose blast radius
is a real person's name in every future transcript, the row stays out. (The same
reasoning excludes the *real brand → different brand* row: `Xcode`→`Claude Code`
is right in one project and destroys a build log in the next, and no validator
knows which one you are in.)

**Warning versus error, because they end differently.** A `valid_phrase` warning
means *review this by hand*, **not** *it was rejected* — the rule is added and
`--add` exits 0. `common_word` and `both_common` are **errors**: `--add` exits 1
and writes nothing, and `--force` is the only way past. `substring_collision`
is *both*, depending on which branch fires — a hit against the curated collision
map is an error, while the broader dynamic check is only a warning and the rule
lands. So read the exit status rather than the noise: a loud add may have
succeeded, and a rule you believe you saved may not be in the database at all.
Reach for `--force` only after reading *which* check objected, since it silences
the blocking ones too.

One caveat decides whether an anchored rule is worth adding: anchor to a
**recurring collocation**, not to a one-off sentence fragment. A snippet of one
particular sentence never matches again — it costs a dictionary row, compounds
nothing, and dead rows are what make a domain slow to load and hard to audit.
When even a collocation would be too narrow, the trap belongs in the domain
context file with its disambiguating cue.

**Measure the corpus before you add — the validators can't see your project.**
The built-in safety checks answer "is this a real word in Chinese"; they cannot
answer the question that actually decides a project-domain rule: *"when this
word appears in THIS project's transcripts, is it ever the real meaning?"* That
is empirical, and the evidence is one command away:

```bash
# How does this term actually appear across the project's transcripts?
uv run scripts/fix_transcription.py --probe "候选误识词" --corpus /path/to/transcripts/

# Or probe as part of the add itself (prints the evidence before writing):
uv run scripts/fix_transcription.py --add "候选误识词" "正确词" --domain myproject \
  --check-corpus --corpus /path/to/transcripts/
```

The probe prints per-file counts plus sampled context windows, with the
decision rule attached: every sampled occurrence an ASR error → a bare rule is
safe; any real meaning present → anchored form, or don't add (record the trap
in the domain context file instead); zero occurrences → a bare rule is
zero-risk but compounds nothing. The surprise this kills: intuition says "this
is obviously an error form", and a 30-second sweep finds the word carrying
perfectly real meanings all over the corpus — or the reverse, a "real word"
whose every single in-corpus occurrence is the mishearing, making the bare
rule safe where a word-checker would have scared you off it.

Batch add multiple corrections in one session:
```bash
uv run scripts/fix_transcription.py --add "错误1" "正确1" --domain tech
uv run scripts/fix_transcription.py --add "错误2" "正确2" --domain business
# Chain with && for efficiency
```

## Project-Specific & Person-Name Corrections (`--domain` isolation)

The most important pattern for **recurring, project-specific errors** — person names, project jargon, shelf codenames — is the `--domain` flag. It is also the *answer* to the false-positive worry above: a person-name fix that's right **in your project** (a teammate's name the ASR keeps garbling) might collide with a real, differently-spelled person in someone else's transcript — so it must NOT go into the global (`general`) dictionary.

`--domain` makes such rules safe by isolating them:

```bash
# Add the rule under an isolated, project-named domain (not 'general')
uv run scripts/fix_transcription.py --add "<ASR-garbled-name>" "<correct-name>" --domain <project>
# Apply ONLY that domain's rules to this project's transcripts
uv run scripts/fix_transcription.py --input meeting.md --stage 1 --domain <project>
```

A rule added under `--domain <project>` only fires when you pass `--domain <project>` at correction time. Other projects (their own domain, or default `all`) are unaffected — so even a risky short-word / common-word person-name rule is safe, because it only fires inside the project where it's correct.

### Why this beats a one-off script (the core value, do not skip)

Facing a transcript — or a whole batch — full of the same ASR-garbled names, the tempting move is a quick `sed` / `python` find-and-replace. **Don't.** That is the single biggest anti-pattern with this skill:

- A throwaway script fixes *this batch* and the knowledge then evaporates: next batch, next week, next project, you rewrite it from scratch. It does not compound.
- The dictionary **compounds**: `--add` once, and every future transcript auto-corrects via `--stage 1 --domain <project>`. Wire that one command into the project's ingest step and the names are fixed forever, for free.
- The dictionary has false-positive protection (short-word warnings, the `audit` command, `--report-false-positive`); a raw `sed` has none and will silently corrupt look-alike words.

**Rule of thumb: recurring, deterministic project error → `--add ... --domain <project>` (it compounds). Never use a throwaway cross-file sed/python replace.** For a genuinely one-time, never-recurring fix, edit only the exact occurrence in the file and stop; a reusable dictionary row would add blast radius without compounding value.

ASR is especially unstable on Chinese names: one person can shatter into a dozen homophone variants (in one real project a single surname+given-name was seen as 13+ `[姓变体]×[名变体]` combinations). Capture every confirmed **recurring deterministic** variant with `--add --domain <project>` so it collapses to the canonical name on future runs; leave rare sentence-local variants file-only.


### People Roster (long-term person-name SSOT)

For **important recurring people** whose names ASR consistently garbles
(coworkers, clients, family, workshop attendees), maintain a **people roster**
markdown file — the SSOT for person names — rather than adding them one-by-one
to the DB. Transcript-fixer auto-loads person-name corrections from this roster
at Stage 1 time when `people_roster_path` is set in
`~/.transcript-fixer/config.json`.

Auto-loading is only one input to name correction, not an identity verdict.
Before changing any person name, directly read both the configured global
roster and the owning project's explicit person roster or alias ledger. The
project source is never auto-loaded, while a direct global-roster read can
surface suppressed, disabled, relationship-only, and not-yet-variant entries
that Stage 1 does not expose. If either expected source is unavailable or the
sources disagree, leave the token unchanged and enqueue it or ask once. Never
use the most frequent spelling in the transcript as identity evidence.

**Roster format** (canonical: `### Name` + `- **ASR 变体**: variant1, variant2`):
```markdown
### Ada Lovelace
- **ASR 变体**: Aida, 艾达

### 小明
- **ASR 变体**: 晓明, 小铭
```

Both example shapes are worth copying. An English given name spoken inside
Chinese speech produces *two* kinds of variant — a misspelling (`Aida`) and a
Chinese transliteration (`艾达`) — and a Chinese name produces homophone
variants (`小铭`). List only the misrecognized name token, not a whole
honorific-bearing form: the `小铭` rule can correct `小铭老师` while preserving
the spoken `老师`; a whole-string `小铭老师` roster entry would wrongly replace
the honorific too. List only forms that actually recurred and are safe to reuse.

**Keep legitimate aliases out of the replacement field.** An English name,
Chinese full name, and nickname may all identify one person while each remains
correct speech. Record that identity relationship in the roster's relationship
context or the owning domain's alias ledger, but put only observed ASR
*misrecognitions* on `ASR 变体`. Do not turn a confirmed English-name / Chinese-name /
nickname relationship into replacement pairs; doing so rewrites words the
speaker actually said. Public examples must stay synthetic rather than copying
a real person's aliases.

**Setup** (once):
```bash
# Edit ~/.transcript-fixer/config.json and add:
#   "paths": { "people_roster_path": "/path/to/people.md" }
```

After this, every `--stage 1` run automatically merges roster corrections
(in-memory only — never written to DB). The DB always wins on conflicts, so the
roster fills gaps without overriding hand-tuned entries. See
`scripts/core/people_roster.py` for the parser.

**Precedence has three layers, and the third one is domain-scoped while the
roster is global** — the asymmetry is what surprises people:

1. A DB rule active in the run's domain wins.
2. Otherwise the roster supplies the pair.
3. **Unless** the pair is disabled in the run's domain — then the roster copy is
   suppressed too, and the run prints `🚫 People roster: N variant(s) suppressed`.

Layer 3 is per-domain, so retiring a pair with `--report-false-positive
--domain A` does **not** retire it under `--domain B`: the roster is global and
nothing vetoes it there, so the rule keeps firing in B. That is intended (a
false positive in one domain is often correct in another), but it means "I
disabled it and it still fires" almost always means *a different domain* —
check that before editing the roster, which stops the pair everywhere at once,
including in other projects sharing the same file. `--report-false-positive`
now names the domains where the pair is still active, and exits `3` (already
disabled here) or `4` (roster-only, no DB row to disable) so automation can
tell those apart from a real failure.

**When to use the roster vs `--add` to DB:**

| Person | Go to | Why |
|--------|-------|-----|
| Long-term recurring (coworker, client, family, workshop attendee) | **people.md** | SSOT with relationship context; survives DB resets |
| One-off / minor name | **Exact transcript file only** | A rare occurrence does not justify reusable state; do not add it to the DB or roster |

**Name-variant explosion — one person, every initial consonant.** A person
whose name a diarizer labels once can still shatter in the body into a whole
family of variants, sometimes across *different initial consonants* (h/f/w/g/zh
all heard for one surname in a single 56-minute call — real case 2026-08-08:
one speaker surfaced under seven different surname-initials). This is not a bug
to chase per-variant; it is the canonical-name problem in disguise. Handle it
as a unit:

1. **Fix the canonical FIRST** — ask the user or use a confirmed
   human-annotated diarization label, settle one spelling, and only then sweep.
   An auto-assigned label, or one whose provenance is unknown, remains a
   candidate and must follow the verification ladder below. A variant family
   resolved without a canonical produces seven half-fixes and a confused roster.
2. **Sweep every variant in the file in ONE pass** (single-file `sed` with all
   variants in one command, then re-grep to zero), not variant-by-variant.
3. **Record the whole family in the roster's `ASR 变体` line** — every form
   you actually saw, including the weird ones. The next transcript will
   produce new members of the family, and the roster is what keeps the
   canonical stable while the family grows.
4. **Preserve honorific forms (`X老师` / `X总`)** — an honorific is what a
   speaker actually said, so never store the whole honorific-bearing phrase as
   a variant that maps to a bare name. Sweep and record only the misrecognized
   name token inside it; that lets Stage 1 correct the name while retaining the
   spoken suffix.

**Mid-turn verdicts land immediately — reusability is a separate decision.**
When the user answers a name/number question while you are still working (a
mid-message correction, a one-word answer to your shortlist), fix the file in
the same turn. Then run the destination matrix above. Add only a recurring,
deterministic ASR variant; update relationship context for a confirmed identity;
leave a rare sentence-local mishearing file-only. The user's answer is the
strongest source for what this occurrence says, but it does not prove that the
same from→to pair is safe on future transcripts. A user verdict that
contradicts your search results is still the verdict winning, not an anomaly to
double-check.

## Domain Correction Contexts (per-domain AI priors)

The dictionary handles deterministic replacements; the people roster handles names. A third class of error can't safely live in either: **context-dependent homophones** — words that are only wrong in a particular discussion context. Think `减`→`剪` in a meeting about producing N video clips per day, or a finance call where a common word collides with a ticker nickname. A dictionary rule on a common word silently corrupts every other transcript, and a generic AI pass lacks the domain prior to fix it confidently — it either guesses wrong or leaves it for the human. (Real case: a transcript had four `减到 N 条` occurrences that all meant `剪到`; the AI pass suspected but wouldn't touch them without a domain prior, and the user had to fix them by hand.)

Domain context files close this gap. One markdown file per domain, in **user space** next to your `corrections.db` and `people.md` (never inside the skill bundle — it survives skill updates and keeps project knowledge private):

```
~/.transcript-fixer/contexts/<domain>.md
```

(If you relocated the config dir via `TRANSCRIPT_FIXER_CONFIG_DIR`, contexts live under that dir's `contexts/`.)

During native correction (see [native_ai_full_workflow.md](native_ai_full_workflow.md)), read the transcript's domain context file before triaging. It should contain three things:

1. **One line of business context** — what this domain's recordings are usually about
2. **Known homophone traps** — each with the *contextual cue* that disambiguates it ("when the sentence is about producing/editing clips, `剪` is intended"), optionally with a dated real example
3. **Pointers to authoritative name sources** — the project's alias ledger, the relevant people-roster section, existing DB domains — so the verification ladder in [native_ai_full_workflow.md](native_ai_full_workflow.md) knows where to look first

What must NOT go in a context file: hard replacement rules. `减→剪` as a rule belongs in NEITHER the context file NOR the dictionary — the file primes your judgment with priors and cues; it never authorizes blind replacement. Every fix still goes through the confidence triage in [native_ai_full_workflow.md](native_ai_full_workflow.md).

Maintenance loop (mirrors the dictionary's `--add` habit): when a native session surfaces a **context-dependent** recurring error — you fixed it here, and it'll recur in this domain's future transcripts — append it to the domain's context file with its disambiguating cue. Deterministic non-word/name fixes keep going to `--add --domain` / the roster as before.

**Machine-readable vetoes (consumed by Stage 1, since 2026-08):** two annotation classes in the context file act on the *dictionary*, not just on the reader. ① A trap whose bullet carries the literal marker `禁裸词` or `禁入词典` (**妙计 → 妙记（飞书妙记语境，禁裸词）**) demotes any dictionary rule with the same FROM to safe-mode deferral — the pair may only be corrected with its context judged, exactly the 绿点→绿电 class (a real-word rule right in some contexts, wrong in others). ② A confirmed-correct record (**X = 真实实体，勿修**) demotes any rule whose FROM is that token. Demotion beats `--apply-domain` trust-flattening; `--apply-all` remains the operator's explicit override. Two scope rules: the veto only fires when the domain is named via `--domain` (a whole-library run has no owner to veto with), and in a multi-domain union it applies by FROM across the whole union regardless of which named domain owns the rule. This is how a trap documented *after* a rule was added still stops the rule from firing — before this layer, only `--report-false-positive` (which disables the rule everywhere, including the contexts where it is right) could.

Format and a worked template: [domain_context_guide.md](domain_context_guide.md).

Note: the cue prose itself is consumed by the **native workflow** (the agent reads the file); API mode (`--stage 2/3`, the backup channel) does not inject contexts yet; Stage 1 consumes only the two veto classes above, never the prose.
