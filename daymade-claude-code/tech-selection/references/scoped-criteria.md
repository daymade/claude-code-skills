---
name: scoped-criteria
description: >-
  13 narrower tech-selection criteria (items 14-26), each tagged with evidence
  scope (cross-scenario / single-scenario / teaching-scenario) and class
  (A common sense / B preference / C paranoid). Load at Step 3 as a supplement
  to decision-axes.md, and before quoting any of these as settled truth:
  cross-scenario items may serve as default gates, teaching-scenario items may
  never be used as the user's own selection constant, and C-class items are not
  default gates at all — output them as "declared preference + needs his
  confirmation" branches. The Chinese quotes are the load-bearing evidence; do
  not paraphrase them into stronger claims.
---

# Scoped Criteria — 13 Narrower Filters (Items 14–26)

## How to Read This File

The 13 axes in `references/decision-axes.md` are cross-scenario decision spines and
work as default gates. The 13 criteria here are narrower: most come from a teaching
moment (he was teaching a client, not selecting for himself) or from a single
project. Mixing the two files promotes a situational preference into a universal
law — that is the failure mode this file exists to prevent.

Distribution in this file: **A=1 / B=6 / C=6**. Across the full 26 (this file plus
`decision-axes.md`) it is A=6 / B=11 / C=9.

Every item carries two leading labels.

**Scope — what evidence supports it.**

| Tag | Evidence | What it licenses |
|---|---|---|
| `[跨场景]` cross-scenario | Reproduced in ≥2 independent scenarios (different project, or different time) | May serve as a default gate |
| `[单场景]` single-scenario | Evidence from one project only | Scenario-specific branch; the branch must name its scenario |
| `[教学场景]` teaching-scenario | From a workshop, course, or onboarding session — he was teaching someone else, not selecting for himself | **Cannot be used as his selection constant** |

Two items (18, 24) carry `+` after the tag: a second source where he was stating his
own practice rather than teaching. That corroboration lifts them above pure teaching
evidence, but they remain C-class — the class label, not the scope label, decides
whether the item is a default gate.

**Class — how unique the criterion is.**

| Tag | Meaning | How to use it |
|---|---|---|
| `A` common sense | Industry-wide, no conflict with standard practice | Default gate |
| `B` preference | His stated preference | Default gate, but attributed to him |
| `C` paranoid | Uniquely his, narrow evidence | **Not a default gate.** Output as the branch "he has declared this preference + needs his confirmation" |

The review's meta-finding: uniqueness and evidence width are negatively correlated
— the cross-scenario items are almost all A/B, the single-scenario ones almost all
C. A C-class tag combined with a `[单场景]` or `[教学场景]` tag is the combination
that must never be applied silently.

Three rules that follow:

1. Never quote a C-class item as settled truth, not even in prose that reads decisively.
2. Never use a `[教学场景]` item as his personal constant — the audience was being taught; he was not choosing.
3. A `[单场景]` branch must name the scenario it came from, or it becomes untraceable.

Use these as **supplementary axes at Step 3**: apply them after the 13 core axes,
give the same three-value verdict (`pass` / `fail` / `unknown`), and let their
verdicts feed Step 4's survivor triage like any other axis.

---

### 14 · `[单场景]` · `C` — AI-produced architecture and stack selection is untrusted by default

Architecture decisions and tech selection are the one category he explicitly carved
out of delegation. Writing code is freely delegated; picking the stack is not. The
reason is experiential — years of engineering let him recognize garbage — not a
procedural re-review, so the gate cannot be satisfied by adding a review step.

> 「当 AI 给你写一个，画一个架构图的时候，你大概率能发现，这画的就是垃圾。就是你拿你这么多年的程序的经验，让 AI 给你出这些架构图、或者是架构决策、技术选型的时候。他出的还是垃圾。」

**Use.** Not a default gate. Its consequence for this skill is structural, not
behavioral: every selection this skill produces carries the Step 5 self-defense
slot, and that slot must be independently checkable — the skill does not stamp its
own approval. A recommendation phrased as settled ("use X") is the failure mode
here, no matter how many axes passed.

**Source.** 2026-08-16 private-deployment system design discussion transcript line 1447 (discussion with a peer engineer).

---

### 15 · `[跨场景]` · `B` — Match the model and the tool to task shape, not to tier or brand

The unit of choice is the scenario, not the leaderboard. He runs several clients at
once and splits them by capability; models are assigned by work shape (logic
execution vs. large-context rewrite); tier follows budget, and when a model hits a
ceiling he adds thinking before upgrading tier.

> 「每一个模型，每一个客户端有每个客户端的最优，最最适合的场景。」
> 「Claude 3.5 Sonnet → Best for bug-fixing and logic-heavy execution；Gemini 2.5 Pro → Reads huge codebases. Best for refactors/auditing the code for bugs」
> 「如果 Token 够用，那就用Opus，如果不够用就用Sonnet，特别特别难的问题的时候使用那个Fable」
> 「我可以用 Sonnet max，我也可以用 Opus low，但是我推荐用 Sonnet max……你用 Sonnet 去思考多一点，它花的还是 Sonnet 的钱」

**Use.** Default gate — the selection unit is the scenario, so "the best model" is
not an admissible answer without a named task shape. Budget sets tier only; it
never decides whether the work happens (Boundary Quick Reference row 3).
Underperformance at a tier → raise the thinking budget at that tier before
escalating tier.

**Source.** 2026-08-30 workshop line 1365, line 1158; personal curated notes (~2025) (~2025); 2026-05-29 team sharing session line 226.

---

### 16 · `[教学场景]` · `B` — A vendor may own the data, never the workspace

The selection criterion is **architecture position** — not the feature table, not
the price. Losing the choice of client is itself a rejection reason.

> 「很多时候我们是需要有这种厂商的，不能被厂商锁定。我想用Codex，想用 Cloud Code……我只把你当成一个数据的提供商，就是你给我，我想要数据，我想要电话会议，你给我就好了，但是你不要让我在你的那个框架里去工作」

**Use.** Teaching scenario — do not convert it into his personal selection constant.
As a branch: when a candidate is a hosted or managed environment that becomes the
only place the work happens, surface it as a rejection axis (workflow ownership
lost) alongside what that choice buys (the vendor owns the service and the data),
and let him pick the angle. The branch fires on the **only path** property, not on
the word "vendor."

**Source.** 2026-08-30 workshop line 804 — on-the-spot correction after a client adopted a vendor-managed coding environment.

---

### 17 · `[跨场景]` · `B` — Determinism vs. generalization is a ratio, never a binary

He named the failure mode on both sides: AI-driven is unstable and unattributable;
a fixed script is controllable but semantically blind. His answer is hybrid, with
the ratio set by which side's capability the task needs.

> 「AI去测试，AI看你的屏幕，AI去决定，我要点两个按钮，这个是很不稳定的，但是它有很强的泛化性的。而我们预先写好的一些测试脚本……取某一个元素的ID然后去点它，这个是非常可控的。他跑对了就是对了，错了就是错了……所以我们要用两种方式混合，就hybrid的一个方式。」
> 「我们始终是要坚持……方法就是代码加上大模型混合做推理。」

**Use.** Default gate as a binary killer: any proposal that is 100% scripted or 100%
AI-driven fails this axis. The finer rule — let requirement-change frequency decide
which side is load-bearing (stable → fixed code, changes daily → AI generalization
layer) — exists in the corpus only as paraphrase, with no independent quote behind
it. Carry it as an unverified hypothesis, not as a settled criterion.

**Source.** 2025-12-19 automation-testing architecture discussion (recording transcript @37:40); 2026-07-13 vendor-demo retrospective line 198/201.

---

### 18 · `[教学场景]` `+ his own retro` · `C` — Skill-building criteria: 没它不行 + 会重复 + 你每天在用

Publicly he states two: the agent does the task poorly without it, and the skill's
run frequency and business value are high. His own retrospective adds a third — it
must be something you use every day, because the optimization loop comes from usage
frequency.

> 「这两个标准，第一，没有 skill 的时候， agent 能不能很好的完成这个任务，这是一个标准。第二，这个 skill 它以后的运行的次数、频率、产生的业务价值高不高？这是判断我们的应不应该写某一个 skill 的那个两个标准」
> 「如果你想要写一个好的skill，一定是这个 skill 你每天在用的。如果你写完你这个 skill 从来没用过，这个 skill 不可能是一个好的skill。为什么？你每天用一次，你就要优化一次啊。」

**Use.** C-class, and out of this skill's domain — building a skill is not a tech
selection. Owned by `skill-creator`. Kept here only so a selection task never gets
answered with "write a skill for it."

**Source.** 2026-04-16 client workshop (teaching) line 998 (teaching); 2026-05-24 三 session 并行与 workshop 收尾复盘 line 465 (his own use).

---

### 19 · `[教学场景]` · `C` — Two attempts, then stop-loss

Two attempts across models and it still does not work → declare "this can't be
done." He treats agent uncertainty as a resource problem with a stop condition, not
as an infinite debugging budget.

> 「只要我们想去做某一个事情，要试了两个还都不行的话，那就说明这个事真的干不了。」

**Use.** Teaching scenario, C-class. This skill already adopts it as the Step 2
termination clause, bounded to **evidence probes**: two attempts across methods per
candidate, then `unknown`. Do not extend it to abort work already in flight on his
behalf — that is the escalation branch ("declared preference + needs his
confirmation"), not a silent stop.

**Source.** 2026-08-30 workshop line 1158 (same passage as the model-tier quote, item 15).

---

### 20 · `[单场景]` · `A` — Three-way triangle: time / quality / cost

When capability is unstable, he first assumes the team is choosing an angle rather
than shipping a defect. The consequence: when he takes a corner, he names which leg
is being sacrificed.

> 「时间、质量、成本，速度、质量、价格，三个不可能三角。」

**Use.** Single scenario, but common-sense class — usable as a default gate.
Mechanical form: a claim shaped like "X is worse than it should be" must be
rewritten as "which angle is being chosen, and which leg is sacrificed." The gate
fires on unlabeled quality complaints, which are unfalsifiable as written.

**Source.** 2026-09-17 a mentee's first 1-on-1 line 388 (explaining a client's per-iteration quality variance).

---

### 21 · `[跨场景]` · `B` — The current state is an input, not a truth (bidirectional)

Both directions are banned: no designing from imagination without observing the
workspace, and no treating an existing implementation as the correct baseline and
only patching on top of it. Both funnel into a first-principles re-judgment.

> 「你不应该凭空去设计，你应该去看看，看一下我们现在的那个界面是什么，然后有哪些问题，有哪些优化点，而不是凭空去设计」
> 「你不能把我们已经有的东西当做对照基线，你也不能当做……以前写好的东西，你当做绝对正确的东西，然后只在上面修修补补。你应该从第一性原理思考，我们应该怎么样去做」

**Use.** Default gate, and the reason Step 1 (prior-art inventory) and Step 2
(observed-behavior probe) are both mandatory: prior art is read as an input to
re-judge, never as a baseline to extend. A candidate justified only by "it's what we
already have" fails this axis.

**Source.** codex 019c838a line 281 (2026-02-22, UI rework); codex 01a080fc line 203 (2026-09-08, correcting an agent that had treated the old implementation as the baseline).

---

### 22 · `[单场景]` · `C` — Kernel-stripping test

Turns "keep it simple" into an executable falsification test: strip every business
rule and integration away, then ask whether the kernel alone is still useful.

> 「重要的是你这个内核能不能剥去所有的外，那个外面的那一层手脚工具，制定的那些业务相关的规则。之外，我只有一个内核的时候，那个内核能不能有用？」

**Use.** Single scenario, C-class → scenario-specific branch, needs confirmation.
Probe form: on a build-vs-buy call, remove every customer-specific rule and every
integration from both sides and ask what the core still does. If the answer is
"nothing," the candidate is carrying complexity that no named business result
requires.

**Source.** 2026-05-21 team development-process discussion line 54.

---

### 23 · `[单场景]` · `C` — Intermittent is not load-bearing

Single-point-of-failure elimination as an architecture principle, plus a precise
reliability vocabulary: a channel may be kept as a fallback, but it must be labeled
by **measured** behavior — `never load-bearing`. The failure mode he flagged is
worse than downtime: a hard key requirement silently turns an entire batch path
into a dead end while the docs still claim no auth is needed.

> 「intermittent, never load-bearing」

**Use.** Single scenario, C-class → branch, needs confirmation. Two mechanical
rules: (1) a fallback is allowed and must never be the only path; (2) every
load-bearing claim must name the probe that measured it. Bypass and fallback are
different acts — see Boundary Quick Reference row 1.

**Evidence note.** This sentence comes from a skill audit record (twitter-reader
v1.2.0 fix log), authored by an agent and adopted by him. Cite it as his
engineering norm, not as his spoken judgment.

**Source.** claude session 3f54f19e (pkm, twitter-reader skill v1.2.0, 2026-08-30).

---

### 24 · `[教学场景]` `+ his own working contract` · `C` — Context is not compressed and does not rot

His objection to 1M → 256K is epistemological, not economic: compression is lossy
and you cannot see what was lost, so a guarantee that was declared silently becomes
false. The three acceptance properties are 短、完整、精确.

> 「要不要把 100 万降到 256 K？不要，因为我们现在大部分的人，他的业务复杂度已经是 256K 完全承载不了的一个东西了。而如果我们把它降到256K，它就会不停地在压缩，而一旦压缩就会失去了我们一开始说的那个短、完整、精确，因为它一压缩就丢了。」
> 「如果你获取不到足够的，完整的，精确的，不腐烂的上下文。那么你就没有办法去完整的理解我们的业务背景和我们当前要做的事」

**Use.** Teaching scenario, C-class → branch, needs confirmation. Fires when someone
proposes trimming context to save budget: surface the epistemological objection (the
declared property 完整 goes silently false) rather than compressing quietly. This
skill governs "don't compress during selection"; host auto-compaction is a different
actor — see Boundary Quick Reference row 4.

**Source.** 2026-09-06 client onboarding session (teaching) line 982 (teaching); 2026-09-02 acceptance-mechanism onboarding session line 344 (his own working contract).

---

### 25 · `[单场景]` · `B` — The user's choice is a supervision signal

Real usage is the training signal. He derives the labeling rule on the spot: the
round that got used is the positive sample, the discarded rounds are negative
samples. He states the first-move gap plainly — there are no negative samples yet,
so start from the positive ones.

> 「他生成了 10 轮，最后用了第八轮的标题……那么我们是不是可以认为这个第八次的标题是一个正样本，其他的 9 次标题是负样本？」
> 「我们训练的时候不管是训练模型还是训练 skill……都是需要正负样本的，但现在我们没有负样本，那我们就先从正样本入手」

**Use.** Single scenario → branch. Note the first quote is a question he raised, not
a settled rule: the positive/negative convention is his proposal, so a selection
task must not retro-label discarded candidates as "rejected for cause" without
asking. The part usable today: when the user has already kept one of several
generated options, that pick is the only labeled evidence available — read it before
proposing a new one.

**Source.** 2026-09-17 a mentee's first 1-on-1 (improving their own product from a client's 10-round generation log).

---

### 26 · `[教学场景]` · `B` — Agent cluster size is a triangle, not a best practice

He teaches fan-out as an explicit ledger for the audience to choose their own point
on, never as a prescribed count: speedup up, information loss up, tokens up,
delivery time down.

> 「你开的 agent 越多，你的加速比越高，你的信息损失越多，你花的 token 越多，但是你的时间节省的越多，它会更快的给你结果。」

**Use.** Teaching scenario → not his personal constant. Where this skill does need a
number, it uses task shape (the four orchestration questions) with an 8–10
concurrency ceiling, not a fan-out default. Present the ledger when the user is
choosing a fan-out level; do not hand them a count.

**Source.** 2026-05-22 team sharing session (trial lecture) line 496 (on when to use a subagent).
