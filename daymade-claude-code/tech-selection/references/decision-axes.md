---
name: decision-axes
description: >-
  The 13 core filter axes for tech-selection Step 3, each with a trigger, an
  executable criterion, the failure mode it kills, and its evidence scope. Read
  when filtering candidates — never when ranking them, and never before Step 0
  has named a business result.
---

# Decision Axes — 13 Core Filters

Every axis carries four fields:

- **Trigger** — the moment the axis activates
- **Criterion** — how to decide, mechanically
- **Kills** — the failure mode a violator is killed for
- **Scope** — how strong the evidence behind the axis is

An axis never ranks. It returns `pass` / `fail` (named failure mode) / `unknown`
(needs probe), and `unknown` is not `pass`.

**Scope legend** — read this before treating an axis as a default gate:

- **Cross-scenario** — reproduced in ≥2 independent scenarios. Usable as a default gate.
- **Single-scenario** — one scenario only. Use as a scoped branch; never let it raise the global standard.
- **Teaching-scenario** — said while teaching or coaching someone else. He was instructing, not selecting for himself. Cannot be treated as his own selection constant.

Criteria are written as imperatives with decidable steps. "Keep it simple" and
"industry best practice" are not criteria — they are the shape this file refuses.

---

### Axis 1 · Business result first; proxy metrics are a silent substitution

- **Trigger**: Any candidate is proposed, and any statement of "done" is judged.
- **Criterion**: Before comparing candidates, write two lines: ① the **named business result** this choice serves; ② the **falsifiable failure phenomenon** that would prove it wrong. Then audit every completion claim: does the thing being measured equal line ①, or is it an easier-to-measure neighbour (tests green, coverage, pipeline complete, link works)? Measured object ≠ line ① → `fail`; rewrite line ①. "Tests pass" offered as evidence of "the business got better" is the one unacceptable substitution form.
- **Kills**: Candidates whose acceptance is process completeness, test-green, or artifact count. Any acceptance plan whose metric is a proxy for the real goal.
- **Scope**: Cross-scenario.

> 「不要把"流程看起来完整"当成了"业务结果更好"……更不要把更容易证明的代理指标，偷偷替换成真实目标」
> 「你只是完成了这个任务，完成了一个过程指标或者代理指标，而不是完成了我们的业务目标」
> 「从价值出发，从第一性原理出发」

---

### Axis 2 · Inventory what exists before building anything

- **Trigger**: Every "should we build this" need — including the moment before hand-rolling a tool, script, format, or framework.
- **Criterion**: Inventory three layers in fixed order, and tag each candidate with the layer it came from: ① internal/paid assets (existing credentials, paid-service capability catalogues, existing skills, existing pipelines in this repo) → ② external world-class + community solutions → ③ build from scratch. If the final recommendation lands on layer ③, state what was searched in layers ①–② **and** whether it was searched by structural token or by remembered name — a zero hit by remembered name does not mean absence. An adequate existing solution wins without a head-to-head comparison; "adequate" means it covers the current need, not that it is the performance ceiling. An internal asset wins by being owned.
- **Kills**: A layer-③ recommendation with no search record for layers ①–② (闭门造车). Skipping the inventory because "I'd control it better." Treating a single name-recall search as proof an asset does not exist.
- **Scope**: Cross-scenario.

> 「你不应该闭门造车，你应该找到成熟的方案，世界级的……站在巨人的肩膀上，而不是你从零开始造一个很挫很挫的轮子」
> 「不要自己去闭门造车。要先找到别人做得好的事情，我不相信这个事情没有人做过」
> 「我们手上有一个那个 tiktok……既然能采别人，那肯定可以采自己的」

---

### Axis 3 · Boring tech beats latest versions

- **Trigger**: Choosing a library, framework, SDK, or pinning a dependency version.
- **Criterion**: The candidate's API must be stable enough that an AI coding assistant uses it reliably, the way it would use an experienced colleague. Verify by probe, not by doc: ① count breaking changes across the last several published releases (changelog); ② make one real call and observe whether it behaves as claimed — a library the assistant cannot call correctly without reading docs fails. Separately: call the framework's native mechanism instead of hand-rolling an equivalent.
- **Kills**: Candidates on latest/RC/canary or with frequent breaking changes. Hand-rolled equivalents of a native SDK mechanism. Any API shape the assistant cannot invoke correctly.
- **Scope**: Cross-scenario.

> 「use boring techs, do not use latest versions of the libraries, AI works well like your experienced colleagues」
> 「你需要使用成熟稳定的方案」

---

### Axis 4 · Long-term maintainability is a second, independent gate

- **Trigger**: After any "it works / it's fixed" verdict, and whenever a temporary solution is on the table.
- **Criterion**: Decide two gates separately and never merge them. Gate A — "does it work now" (end-to-end probe passes). Gate B — "will it stay correct", decided by counting: ① how many new concepts, configuration surfaces, or state locations the solution adds (locations where new entropy lands); ② whether the same class of problem can recur — is the prevention encoded in a mechanism or does it depend on someone remembering; ③ does anyone have to hand-maintain an index, inventory, or rule set (yes → not maintainable). A passing with B undecided is not a delivery.
- **Kills**: Candidates that clear A with B never judged. Solutions that add configuration surface, state locations, or hand-maintained indexes. Prevention that lives in human memory instead of a mechanism.
- **Scope**: Cross-scenario.

> 「但是你要去看一下什么是长期可维护的手段……不要去增加新的熵」
> 「做长期的可维护性方案吧，要最佳的工程实践，不要过度工程」
> 「用长期可维护的方式，在未来避免类似的问题再次发生」

---

### Axis 5 · Data structure is load-bearing: design it first; algorithm is replaceable

- **Trigger**: Any decision touching persisted data, field definitions, export formats, or storage medium.
- **Criterion**: ① Design the data structure — fields and types written down — before choosing algorithm or model. ② Run a swap test: replace the algorithm or model with another implementation; does the data structure have to change? Yes → the structure encodes an algorithm assumption → `fail`. ③ Over-building is countable too: any field, abstraction, or extension built for a hypothetical future consumer is deleted unless it has a consumer today. The decidable line is "reserve extensibility ≠ pre-construct": an extension point is a defined insertion slot; pre-construction is an implementation with no consumer.
- **Kills**: Algorithm-before-schema ordering. Data structures that hard-code algorithm assumptions so the model cannot be swapped. Fields and abstraction layers built for imagined requirements.
- **Scope**: Cross-scenario.

> 「提前设计好数据结构的话，数据结构是最重要的。算法是另外的……你如果数据结构一开始没设计好，那后面你会花很多的精力……但是你也不要去过度工程，要去设计一个可迭代的、长期可维护的技术方案」
> 「我写需求，数据结构你来定」

---

### Axis 6 · End-to-end usable beats polishing one link

- **Trigger**: Any multi-stage solution, and any progress claim of the form "this stage is done."
- **Criterion**: Acceptance requires one run of the complete link, observed — not each stage passing separately. Three checks: ① does a single execution record exist from entry to user-visible result; ② does every stage appear inside that one record (not "each was tested on its own"); ③ is half-delivery named as such — "done halfway" is a forbidden delivery form, not a progress state.
- **Kills**: Candidates whose stages pass individually but were never chained into one execution. Deliveries shaped as "core done, periphery pending." Candidates with no complete-link run record.
- **Scope**: Cross-scenario.

> 「我们的目的就是真的端到端可用，而不是在某一个单点的环节来打转」
> 「你自己决定，端到端交付，不要给我做到一半」
> 「端到端的去测试，这是不能接受的失误」

---

### Axis 7 · The operator's skill floor is a design constraint

- **Trigger**: Any solution someone else will operate (delivered to a client, colleague, or trainee), and any automation that introduces a new operating step.
- **Criterion**: Name the target operator and what they can and cannot do — not the adjective "too complex." ① List the operators and the tool they use today to do this by hand. ② For each operation the new solution requires, does their existing toolchain already contain the matching primitive? ③ What is their fallback if they don't adopt this (no fallback = a named failure mode). ④ Check the quality floor: does the solution trade volume for quality without an explicit per-item threshold?
- **Kills**: Solutions requiring operators to master primitives absent from their toolchain. Solutions that move cognitive load onto the user to buy automation. Targets expressed as daily volume with no per-item quality floor.
- **Scope**: Cross-scenario.

> 「我们没有那个剪辑人员」「他学不会」
> 「你要做成自动化的，不要做成这么复杂的，带来心智负担的，用户也不会用，我也不会用」
> 「我们不要求说一天产个几百条，因为产几百条，那确实是泔水级别的」

---

### Axis 8 · Root cause first; bypasses and heuristic patches are forbidden

- **Trigger**: The moment a bug or anomaly offers a quick path around it, and the moment a repeat fix looks like whack-a-mole.
- **Criterion**: ① Write the root-cause statement ("what causes what") before fixing; cannot write it → not yet in a fixable state. ② Distinguish bypass from fallback: bypass = replacing the main path so the symptom disappears (failure form); fallback = a supplementary channel beside the main path (allowed, and must be labelled for real reliability). ③ Third repair of the same class of problem → declare it symptom-patching, stop, and build the mechanism. ④ Make "分析系统性，不打地鼠" executable: every fix must answer "does this prevent this class, or only this instance."
- **Kills**: Bypasses where the symptom disappears with no root-cause statement. Whack-a-mole repair — the same class fixed twice with still no mechanism. Heuristic rules standing in for root-cause localization.
- **Scope**: Cross-scenario.

> 「你不要做临时的绕过或者是启发式的修复，你还没有找到根本原因呢」
> 「你这是解决根本问题的办法吗？这是一个临时绕过的低级手段」
> 「系统性地分析，不要打地鼠」

---

### Axis 9 · Implementation choice ≠ product justification

- **Trigger**: Any "why this one" argument, and any conclusion that reads technical acceptance as business acceptance.
- **Criterion**: Split the argument into two independent axes and evidence each separately. Axis A — implementation path (is it technically feasible and stable — proven by probe). Axis B — product reason (did the business result improve — proven by a business measurement). Evidence for A may never be cited for B. Decidable form: if the argument contains "it passed technical verification, therefore it is better for the business" → `fail`. This is the mirror of Axis 1 — Axis 1 forbids swapping the measured object; Axis 9 forbids borrowing evidence across axes.
- **Kills**: Candidates justified by technical feasibility, benchmark numbers, or green tests when the claim is business value. "More advanced / more mature" offered as a business reason.
- **Scope**: Cross-scenario.

> 「技术验收也只能证明实现路径，不能证明商业价值」（agent 形式化表述，他采纳——不是口述原话）

---

### Axis 10 · Local-first and machine-searchability are the storage criteria

- **Trigger**: Any decision about where knowledge or data lands — hosted wiki vs local file, managed store vs local store, API retrieval vs file-greppable text.
- **Criterion**: Derive the storage location from the retrieval primitive the actual consumer owns. ① Who or what reads this data, and what retrieval primitive does it have (an agent has only ctrl-F, grep, and filename matching; a human has a UI search box). ② If the consumer is an agent, can it reach the full text by ctrl-F? No → `fail` — "he only reads the filename" is the named failure form. ③ Cloud or hosted convenience never outranks grep-ability unless you name the retrieval channel that consumer actually has. **Caveat**: most of this axis's evidence is teaching- or coaching-scenario. Before using it as a default gate, confirm the consumer really is an agent.
- **Kills**: Data placed where the consumer cannot full-text search it (hosted knowledge bases, cloud docs with UI-only search). Semantic search offered as a replacement for greppable local full text, with no parallel keyword channel.
- **Scope**: Cross-scenario (2 teaching/coaching + 1 self-use). Default gate only when the consumer is an agent.

> 「所有的知识库都应该是本地优先的」
> 「ai 没有办法在本地去直接 ctrl F 去搜到你的飞书里的这些……他没有办法搜」
> 「他只看那个文件名」

---

### Axis 11 · Observed evidence outranks every document

- **Trigger**: Before any judgement of the form "can this be done / how does this API work / what does the vendor claim."
- **Criterion**: The only admissible evidence is behavior you ran and observed. Label every load-bearing claim with a tier: ① measured (called and observed, with an execution record) → ② official API docs or source code (authoritative, not measured) → ③ README, vendor page, or source comments (downgraded; cannot carry a load-bearing claim alone). Rule: a load-bearing claim without ① is marked `unknown`, never `pass`. Search order: run first; read docs only to find where to run; a doc sentence is never a result.
- **Kills**: Candidates supported only by README, vendor page, or source declaration. "The doc says it's supported" reported as "verified." Another party's pass conclusion — including an agent's — offered as evidence.
- **Scope**: Cross-scenario.

> 「文档不准，接口不准」
> 「一切以验证为准」
> 「没有人看 README」
> 「让他真正的把代码搞下来，而不是看他的那个什么宣传的文档」

---

### Axis 12 · Saturate irreversible surfaces from v0

- **Trigger**: Only when the decision touches a surface that cannot be back-filled after release — telemetry and events, field and export formats, external contracts, irreversible external actions.
- **Criterion**: ① Enumerate the irreversible surfaces and list them explicitly (or write "none" — silence is not a check). ② For those surfaces the criterion is "is anything valuable being silently dropped" — saturate rather than miss. ③ **Does not apply** to revertible, re-issuable local changes: there the delegation threshold governs, and this axis must not be used to raise the overall standard by a notch.
- **Kills**: Ship-now-patch-later on telemetry, fields, or external contracts that cannot be added post-release. The inverse error — invoking this axis on revertible local work to justify inflating the global bar.
- **Scope**: Single-scenario. One main thread (a telemetry requirement); no second independent scenario in the corpus reproduces "irreversible → raise the standard."

> 「我们一旦发布了以后，我们就没有办法再给它加这个功能了，所以我们从第 0 天第一个版本就需要支持完善的数据统计……宁可全方位地覆盖饱和式地上报，也不要去漏掉某些日志或者是事件」
> 「我不想有任何有价值的代码被静默地丢弃」（触发条件是「会丢东西」，与「不可逆」形状相邻但不同，不构成第二个独立场景）

---

### Axis 13 · Sufficiency is a dose with an explicit termination clause

- **Trigger**: Every "should we keep polishing / add one more / try another round" node, and any retrieval or quality standard drifting upward without a stop.
- **Criterion**: Every polishing decision carries a decidable stop of the form "reach X, then end." Three executable forms: ① Feature sufficiency — a new capability is added only when without it the task cannot be done; otherwise "a little is enough" is a legitimate termination. ② Cost sufficiency — the number of conversation rounds plus human pick-and-feedback rounds needed to finish one task is itself an evaluation standard, so it is measured and reported. ③ Attempt sufficiency — two failures across methods for one candidate ends it. The per-attempt form lives in `references/scoped-criteria.md`.
- **Kills**: Infinite iteration with no termination condition. Volume-for-quality output whose per-item quality falls below threshold. A third hard attempt after two.
- **Scope**: Cross-scenario (1 self-use + 1 coaching).

> 「加上那个搜索做的好，用一丢丢，我觉得就够了，就是这整个这个事情就结尾了」
> 「你花多少轮的对话，加上你自己的挑选和反馈，才能完成一次任务。这个东西是一个很重要的评估标准」
