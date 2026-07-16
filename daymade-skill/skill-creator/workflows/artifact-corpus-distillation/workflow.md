# Artifact-Corpus Distillation Workflow

A retrospective distillation workflow for turning a corpus of **user-approved artifacts** (HTML report pages, generated documents, designs, decks — finished products the user has explicitly endorsed) into a skill's **decision rules**: explicit principles, quantified parameters, and vocabulary that change how the skill behaves next time.

This is the third distillation source, parallel to the other two specialized workflows:

| Workflow | Source material | What it extracts |
|---|---|---|
| wrapper-skill | The live install/debug session | Install flow, fixes, error→remedy pairs |
| conversation-mining | Past session transcripts | Knowledge, pitfalls, decision rules from dialogue |
| **artifact-corpus-distillation (this)** | **Approved finished artifacts** | **The user's actual preferences/taste, made executable** |

Use this when the user points at a batch of finished products and says something like:

- "这些都是我认可的样例,你来学到底什么是我想要的"
- "把我认可的这几张页面的风格沉淀进 skill"
- "extract my real preferences from these approved examples"
- "why do my approved reports look consistent? make the skill know it"

It is **not** a generic skill-creation flow. It feeds the generic flow: after distillation completes, return to the normal skill-creator steps (regression audit, validate, version bump).

## The core discipline: cataloging ≠ distillation(登记≠提炼)

This workflow exists because of a failure mode that feels like success (methodology Case 15): given approved samples, the natural move is to **catalog** them — register each in a corpus reference with a name, a path, and a list of its components. That produces a beautiful table and changes **nothing** about how the skill behaves.

**The test, applied to every addition:** *does this change any decision rule the skill will follow next time?*

- A corpus row("样例 X · register Y · 教的组件 Z")→ changes nothing by itself = **cataloging**. Useful only as an index, and only if the skill says when to open it.
- A principle("报告页基底恒为暖纸族 #FAF8F3–#FCFBF8,accent 随受众品牌换")→ directly constrains the next generation = **distillation**.

Cataloging is still worth doing (the corpus is calibration material and the evidence base), but **a session that only catalogs is not done** — the user's reaction to catalog-only work was, verbatim: "你不能只加示例吧。你得去提取出来我真正的喜好是什么,然后把它放到 Skill 里来。"

## Step 1: Corpus inventory and the admission gate

1. Confirm every artifact in the batch is **personally approved by the user** (their message listing the samples usually *is* the approval — record the verbatim phrase). Approved-corpus purity = calibration trustworthiness; a beautiful but un-endorsed sample poisons the baseline.
2. Diff against any existing corpus reference: which samples are already registered, which are new.
3. Check artifact locations: anything living in volatile paths (`/tmp`, `~/Downloads`, job scratch dirs) gets copied into `assets/examples/` **with its referenced resources** (images break otherwise — verify by rendering after copy). Oversized artifacts (embedded media, >1MB) stay in place; register the path instead.

## Step 2: Quantitative horizontal extraction — scripts, not impressions

Extract the same measurable facts from **every** artifact with a script, into one comparison table. Eyeballing three samples and generalizing is exactly how fake patterns get written. What to extract depends on the artifact type; for HTML pages this meant:

- **Style tokens**: CSS variables (colors), font stacks, base font-size / line-height, max-width, border-radius values, box-shadow count, dashed-border count, letter-spacing values.
- **Behavior**: `<script>` count, interaction primitives (hash routing, sliders, event listeners).
- **Language layer**: `<title>`/h1/h2/kicker/lead texts, dumped side by side.
- **Marker counts**: arrows (→), separator conventions (·), state-word vocabulary.

Two thresholds keep the induction honest:

- **A pattern needs ≥3 independent artifacts** to count (one page's quirk is not a preference).
- **A claimed constant needs a checked exception list** — "warm-paper base in 13/13 report pages, the only exceptions are pure tool pages that mimic their data source" is a finding; "usually warm paper" is an impression.

## Step 3: Layered induction with evidence anchors

Group findings into layers so the write-up lands in the right file. The layer set that worked for the report-page skill of Case 15 (adapt per domain):

1. **Cognitive** (how the user reads): e.g. deltas beat snapshots (A→B pairs everywhere), every page ends on a punchline.
2. **Language** (title/lead grammar): e.g. takeaway titles carrying data judgments; register exceptions (decision pages keep questions open).
3. **Structural** (section rhythm, navigation, footer contracts).
4. **Visual-semantic** (color = state language; dashed = absence; left-border = verdict channel).
5. **Quantified parameters** (the actual numbers: font sizes, densities, widths — so the next generation doesn't guess).
6. **Interaction** (when scripts are allowed at all).
7. **Honesty mechanics** (how uncertainty/pending states are displayed).

Every induced rule carries: the artifact names it appears in (≥3), one verbatim user quote if any exists ("这个洞察很好,继续保持"), and — where the rule corrects an existing skill statement — the old wording it replaces.

## Step 4: Write to the decision-rule layer

- **Principles reference** gets the induced rules — placed *inside the existing principle structure* (extend the matching section; append new numbered sections rather than renumbering, because other files cite section numbers).
- **Corpus reference** gets the catalog rows (register × path × what it teaches) and any new component vocabulary.
- **SKILL.md** gets at most pointer lines at the workflow step where the rule must fire (a principle that only loads at the final gate is useless if it constrains skeleton-building).
- Separate **invariants from register-dependent variables** explicitly. The highest-value finding of Case 15 was precisely a boundary correction: "the skin varies by register" was too loose — quantification showed the *base* never varies, only the accent does. State both halves as a table if needed.
- An induced rule may **contradict an existing skill statement**. That is a finding, not a conflict: fix the old statement (it was an impression; you now have measurements), and record the correction in the regression review as intentional.

## Step 5: Independent completeness audit, then filter

Your induction ran on your own compression model — it systematically misses whole *types* of patterns (standing discipline #5). Before shipping:

1. Spawn a fresh subagent with: the raw artifacts (all of them, both CSS and copy layers), the finished references, and the instruction to list patterns **appearing in ≥3 artifacts but absent from the references**, each with concrete class-name/copy evidence, ranked by load-bearingness, explicitly told which patterns are already covered (so it doesn't re-report them) and that the audit is read-only.
2. Filter its findings with the counter-review discipline (probability × cost × verify yourself — findings are hypotheses). In the Case 15 run the auditor returned 7 findings, all real, including one **systematic correction** to a rule written hours earlier (decision-page titles must stay questions; the fresh rule would have forced them into answers) and one house style that contradicted a library default the skill was delegating to.
3. Fold accepted findings back into Step 4's files, then run the normal regression audit.

## What this workflow does NOT cover

- Judging whether the user's taste is *good* — the corpus is ground truth here, not a debate.
- Distilling from rejected/corrected artifacts (那是 conversation-mining 的事故/纠正挖掘,信号是对话里的纠正原话,不是产物本身).
- AI-slop detection on the corpus itself (never sub-agent that; the admission gate is the user's own approval).

## Deliverable checklist

- [ ] Volatile-path artifacts copied into `assets/examples/` with resources, render-verified
- [ ] One quantitative comparison table produced by script (kept in the session workspace, not the skill)
- [ ] Corpus reference updated (catalog layer)
- [ ] Principles reference updated (decision-rule layer) — every rule with ≥3-artifact evidence + quotes
- [ ] Invariant vs register-variable boundary stated explicitly
- [ ] Independent completeness audit run and filtered
- [ ] Regression audit passed; corrections to old statements recorded as intentional
- [ ] Version bumped once for the whole distillation (not per round)
