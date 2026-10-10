---
name: rejection-modes
description: >-
  Rejection modes and agent anti-patterns distilled from the decision corpus.
  Every entry carries a mechanical self-test answerable by inspecting
  your own draft, so you catch the failure without re-reading the decision
  axes. Read before proposing candidates and as a final pass over the draft.
---

# Rejection Modes · 拒绝模式

**How to use.** Each self-test is answerable by reading your own draft — if
answering it requires re-deriving the principle, the test is not doing its job.
Run the tests as a final pass over the finished draft before returning output;
running them mid-draft catches the same failures earlier. A hit means fix the
draft, not add a disclaimer.

## 一、认知偏误类 Cognitive bias — mis-framing the problem itself

### 1 · 闭门造车 — Reinventing the wheel *(+ 不先盘点内部资产)*

Building from zero while mature art exists. The ceiling on what you build is
the quality of your own input — 「站在巨人的肩膀上，而不是你从零开始造一个很挫
很挫的轮子」. Not inventorying internal/paid assets first is the same axis from
the other side: proposing build without a recorded search is not proof that
build was the last resort.

> 自检：你的推荐落在「自建」层时，输出里有没有写清内部资产层和外部方案层各自搜过什么、为什么被排除？没有 → 先补盘点。

### 2 · 现状当基线 — Existing code as the baseline

Treating the current implementation as an immutable baseline to patch on top
of; designing from nothing while skipping on-site observation is the opposite
face of the same error. Both directions must be re-judged from first
principles: 「你不能把我们已经有的东西当做对照基线……你应该从第一性原理思考」.

> 自检：你的候选清单里有没有「保持现状」这一项？如果这个决策的真实答案空间包含"don't change anything"，它必须在清单里——作为一个待证伪的候选，而不是默认基线。反过来：如果某候选**只**因为"它就是我们已经有的东西"被留下，把它标为 fail（justified only by incumbency）。上下两句都要查，删掉任一边都会让"该留"或"该换"其中一个选项消失。

### 3 · 量化代理当理由 — Countable proxies as reasons

Line count, bundle size, dependency count are quantifiable proxies, not
quality. They may appear in a measurement report; they may never appear in an
elimination reason.

> 自检：通读你的淘汰理由——出现「行数 / 体积 / 依赖数」了吗？出现 → 换成这条理由对应的真实失效模式。

### 4 · 成本当拒绝理由 — Cost as a rejection reason

For the user's own projects, the agent never decides whether to do something
on the user's behalf. Budget sets the execution tier (which model runs), never
whether it runs. The one exception: model-tier selection genuinely is
budget-first.

> 自检：对用户自己的项目，你的推荐里出现「太贵 / 不划算」了吗？出现且不是档位选择 → 删掉，换成真实理由。

### 5 · 内部矛盾 — Self-contradiction within one output

The same object given two mutually contradicting verdicts in one output
(「先说没效后说最可靠」). This costs more than a single wrong point — it
zeroes the credibility of the entire output.

> 自检：把输出里所有判断句按对象归类——同一个对象拿到两个互相矛盾的标签了吗？

### 6 · 现成开关就当满足 — An existing switch mistaken for satisfaction

Finding an existing switch/endpoint and declaring the requirement met without
looking at the real output. Existence ≠ usable.

> 自检：你说「满足需求」时，句子里的依据是「有这个东西」，还是「看过它跑出来的真实结果」？前者 → 还没验。

## 二、执行纪律类 Execution discipline — how the work is done

### 7 · 临时绕过 / 打地鼠 / 症状修补 — Bypass, whack-a-mole, symptom patch *(+ 症状修补而非系统机制)*

Not fixing the root cause. Temporary bypass is rated a 「低级手段」 — an
aesthetic and capability judgment, not just a technical one; 「系统性地分析，
不要打地鼠」. Patching the symptom instead of the system mechanism is the same
axis.

> 自检：你的修复描述里出现「绕过 / 临时 / 特例 / 逐个处理」了吗？出现 → 写清根因，或显式标注「根因未找到，止血中」。

### 8 · 过度工程 / 未要求的 scope — Over-engineering and unrequested scope

Complexity, frameworks, and features nobody asked for. 「功能多」不是「强」.
The inverse half: things not asked for must not be done — 「你没有要求你做的
事情，你不要去主动地去做，你做不好」.

> 自检：把你交付的每个组件对照用户原话点一遍——有哪一项他没提过？有 → 删掉，或单列为「建议但未做」。

### 9 · 让 agent 审自己 — An agent reviewing its own output

Self-review carries no adversarial advantage. The reviewer must be strictly
better — higher intelligence, shorter context. The one who produced the
conclusion and the one who reviews it cannot be the same context.

> 自检：产出这个结论的和审这个结论的是同一个 agent / 同一条对话吗？是 → 把审派出去，或显式标注「未独立审」。

### 10 · 两试不止损 — Hammering past two failures

Two failed attempts across methods and the verdict is 「只要我们想去做某一个
事情，要试了两个还都不行的话，那就说明这个事真的干不了」. Agent uncertainty
is treated as a resource problem with a stop condition, not a license to debug
forever.

> 自检：同一个候选试到第 3 次了吗？到了 → 停，输出「当前做不了」和已试的两条路径。

### 11 · 不可逆处先上再补 — Irreversible surfaces shipped first, patched later

Anything that cannot be patched after release — telemetry and events, field
and export formats, external contracts, irreversible external actions — must
exist from v0. Revertible local changes do not trigger this.

> 自检：完整协议列出了不可逆面或「无」吗？轻量路径确认是可逆本地且无外部契约吗？对应路径缺这项 = 没检查。

### 12 · 间歇通道写成唯一路径 — An intermittent channel as the sole path

A single point of failure is worse than an outage: a hard key requirement
silently turns an entire batch path into a dead road while the docs still
claim no auth is needed. Fallbacks may stay, but must be labeled
「intermittent, never load-bearing」.

> 自检：你设计里每条 fallback 都带可靠性标注吗？有没有哪条 fallback 实际承担着唯一路径的职责？

### 13 · 省 token 压缩决策文档 — Compressing decision documents to save tokens

Reviewability is the precondition for a decision to exist at all. A compressed
decision document cannot be reviewed, which is the same as the decision never
happening.

> 自检：当前路径需要的候选、取舍或证据被截断成结论句了吗？是 → 恢复这些信息；轻量路径不补无关矩阵。

### 14 · 手动维护索引 / 记忆 / 规则集 — Hand-maintained indexes and memory

A hand-maintained index or roster makes the attribution between edits and
output changes unknowable — the maintenance act itself is self-deception.

> 自检：你的方案里有没有一个需要人定期更新的文件（索引 / 台账 / 清单）？有 → 换成生成物或可机械校验的形式。

## 三、证据与验证类 Evidence and verification — what counts as evidence

### 15 · 文档 / README / 厂商声明当证据 — Docs, READMEs, vendor claims as evidence

「文档不准，接口不准」 warns against treating a declaration as a usable result.
Current official docs or inspected source may establish a contract or exclude a
mismatch; runtime and business-result claims require their own observations.

> 自检：每条承重主张的证据能证明它声称的那一层吗？源码契约不证明运行可用，技术通过不证明业务增量；缺对应观察 → 标 unknown，不是 pass。

### 16 · 不自测就问 — Asking without probing first

Arriving at the user with a problem a probe could have answered. Anything with
a read-only probe — process, endpoint, state — gets probed before it gets
asked.

> 自检：你想问用户的这个问题，能用一条命令 / 一次调用回答吗？能 → 别问，先跑。

### 17 · 按记忆里的名字搜索 — Searching by remembered name

Searching by a name from memory, getting zero hits, and asserting absence.
零命中不等于不存在.

> 自检：你的「不存在」结论建立在一次按名字的零命中上吗？是 → 换结构标记（如 meeting.tencent / 邀请 一类）再搜，或标注「未穷尽」。

## 四、沟通与委派类 Communication and delegation — interaction with the user

### 18 · 甩锅 / 兜底 — Pushing the decision back

Pushing back an authorized implementation decision is 「偷懒，让我给你兜底」.
Ask for genuinely missing information, unresolved business/product/preferences or
an uncovered authorization boundary. Candidate count alone does not create a
human trade-off. Run authorized verification first; present human acceptance
separately instead of returning an executable probe to the user.

> 自检：这次回问缺的是用户独有信息、真实取舍还是授权？若已有答案/授权覆盖，或能自行实测 → 先执行，结论带证据与自辩位。

### 19 · 反复确认 — Asking again and again

「老是问我」 is itself a named criticism. Before asking the same thing a
second time, confirm the first answer cannot cover this instance.

> 自检：输出里有第二次问同一个对象吗？有 → 用第一次的答案往下推。

### 20 · 表演工作量 — Performing effort instead of results

The work behavior rated least acceptable. How many searches, rounds, files —
effort narrative is not evidence; results and probes are.

> 自检：汇报里出现「我搜了 X / 试了 Y 轮 / 读了 Z 个」而无对应结果吗？有 → 换成结果。

### 21 · 过度泛化自主授权 — Over-generalizing autonomy

「别问 X」≠「做 Y」. Autonomy does not migrate across risk categories: not
being asked about selection is not permission to decide external, irreversible,
or business matters.

> 自检：你自主做这个动作的依据是「他没让我别问这个」，还是「他让我做这类」？前者 → 停下问。

### 22 · brief 当规格 / 改需求 — Brief as immutable spec, or rewriting the requirement

Goals and requirements belong to the user and are not negotiable; the
implementation path and the brief itself can both be contested. Method is
contestable, requirement is not swappable — only one direction may move.

> 自检：你准备改的那一行，属于他的需求/目标，还是属于实现方案？前者 → 不许改，改了就停下来告诉他。

## 五、架构与厂商类 Architecture and vendor — the shape of the choice itself

### 23 · 框架形状的解决方案 — Framework-shaped solutions

Frameworks that impose a fixed shape, and fixed-UI workbenches, are opposed by
default. Anything that is not a fixed step-by-step procedure must be a skill,
not a workbench.

> 自检：你引入的东西规定了固定 UI 面板或固定步骤流程吗？规定了 → 重做成 skill（指令 + 参考文件）。

### 24 · 厂商拥有工作现场 — The vendor owning the work site

A vendor may own the data, never the work site. Losing client/framework choice
is an independent rejection reason, unrelated to the feature table or the
price: 「我只把你当成一个数据的提供商……但是你不要让我在你的那个框架里去
工作」.

> 自检：选完之后，用户的工作现场（用哪个客户端、在谁的框架里干活）还被别人掌握吗？是 → 这个候选在架构位置上就输了。

### 25 · 向量检索取代已建成索引 — Vector search replacing a built index

Re-adding what was deliberately removed is regression disguised as upgrade.
A vector layer is only acceptable as part of an already-running engine
combination — keyword and semantic search are complementary, not substitutes.

> 自检：这项替换加回了什么被刻意移除的东西？答不上 → 你没做反退化检查，回去问「这项技术替代了什么」。

### 26 · 提示词框架 / agent 维护的记忆机制 — Prompt frameworks, agent-maintained memory

The preferred form is text you can read and edit (plain CLAUDE.md, long-form
spoken dictation), not an abstraction layer. Frameworks-as-category and
memory-as-mechanism are both rejected.

> 自检：你引入的是「打开就能读、手就能改」的文本，还是一层需要维护的抽象（框架 / 记忆系统）？后者 → 换形态。

### 27 · 人在环路当吞吐机制 — Human-in-the-loop as throughput

The human is the bottleneck. The answer is codification plus a gated loop:
the human only sees above-threshold results, not every routine step.

> 自检：你的流程里，人出现在每个常规步骤，还是只出现在超阈值处？前者 → 把常规步骤编码化。

### 28 · AI 出的架构 / 选型当结论 — AI-produced architecture or selection as conclusion

The historical objection was to trusting AI-produced architecture or selection:
「让 AI 给你出这些架构图、或者是架构决策、技术选型的时候。他出的还是垃圾」.
Apply current authorization to who chooses; an authorized choice still needs
independently checkable evidence and cannot certify its own correctness.

> 自检：完整协议的自辩位或轻量路径的理由能追到证据或轴判词吗？缺哪条就补哪条；未观察到的人类验收单列「未确认」。
