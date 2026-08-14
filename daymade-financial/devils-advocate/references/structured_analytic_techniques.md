# 方法论谱系：结构化异议的原始步骤与实证依据

「魔鬼代言人」不是 LinqAlpha 发明的。本文收录本 skill 直接借用的原始方法步骤（逐字引用保留英文）
与关键实证结果，供执行时需要更深依据、或向使用者解释设计理由时加载。

词源：天主教会 1587 年设立 Promoter of the Faith（俗称 Advocatus Diaboli），职责是在封圣程序中
系统性质疑候选人的证据。后续一切世俗实践都是这套程序的改编。

## 1. CIA Devil's Advocacy 六步（Tradecraft Primer, 2009，逐字）

1. "Outline the mainline judgment and key assumptions and characterize the evidence supporting that current analytic view."
2. "Select one or more assumptions — stated or not — that appear the most susceptible to challenge."
3. "Review the information used to determine whether any is of questionable validity, whether deception is possibly indicated, or whether major gaps exist."
4. "Highlight the evidence that could support an alternative hypothesis or contradicts the current thinking."
5. "Present to the group the findings that demonstrate there are flawed assumptions, poor quality evidence, or possible deception at work."
6. "Consider drafting a separate contrarian paper that lays out the arguments for a different analytic conclusion if the review uncovers major analytic flaws."

使用时机（原文）："most effective when used to challenge an analytic consensus or a key
assumption regarding a critically important intelligence question."

## 2. CIA Key Assumptions Check 四步（同上，逐字）

1. "Review what the current analytic line on this issue appears to be; write it down for all to see."
2. "Articulate all the premises, both stated and unstated in finished intelligence, which are accepted as true for this analytic line to be valid."
3. "Challenge each assumption, asking why it 'must' be true and whether it remains valid under all conditions."
4. "Refine the list of key assumptions to contain only those that 'must be true' to sustain your analytic line; consider under what conditions or in the face of what information these assumptions might not hold."

价值（原文）：暴露有缺陷的逻辑，并 "Identify developments that would cause you to abandon
an assumption"——本 skill 的信号标清单直接落实这一句。

## 3. ACH（Analysis of Competing Hypotheses）要点

Heuer（CIA，1970 年代开发，1999 年成书）。本 skill 借用其两个核心机制：

- **证伪优先**："Focus on disproving hypotheses rather than proving one."（证据逐条拿去
  「不一致」计数，不一致最少的假设才最强——对抗确认偏误的关键反转。）
- **缺席证据之问**："Ask what evidence is not being seen but would be expected for a given
  hypothesis to be true."——Step 2 第二问的出处。

已知弱点（诚实记录）：耗时；把假设当扁平列表、无法表达层级；且「ACH 能克服认知偏误」
本身缺乏强实证支持（Wikipedia 引述的学界评估）。本 skill 只取其两个机制，不照搬全矩阵。

## 4. RAND Assumption-Based Planning 五步（1993/2002）

1. 识别重要假设——假设 = "An assertion about some characteristic of the future that underlies
   the current operations or plans of an organization."；「重要」的判据 = "Its negation would
   lead to significant changes in the current operations or plans of an organization."（负重测试的出处）。
2. 识别假设脆弱性。
3. **定义信号标（signpost）**："an event or threshold that clearly indicates the changing
   vulnerability of an assumption."——把「这条假设何时会被证伪」变成可持续监测的具体事件/阈值。
4. 塑造行动（主动让假设保持为真）。
5. 对冲行动（为假设失效备好退路）。

本 skill 的 Step 5（信号标清单）是 ABP 第 3 步的直接应用；ABP 第 4/5 步属于使用者的决策域，skill 不代做。

## 5. 外部视角 / 基础比率（Mauboussin & Callahan, The Base Rate Book, 2016）

- Inside view：聚焦本案独特性、按经验外推——"commonly leads to a forecast that is too optimistic."
- Outside view：把预测放进参考类，问 "What happened when others were in this situation?"
- 四步：选参考类（够大且够贴）→ 看结果分布 → 结合两种视角给区间 → 可靠性低时向均值大幅回归。
- 技能主导的领域可偏内部视角，运气成分大的领域必须加重外部视角。

这是叙事式反证之外一条独立的统计反证来源，也是被复刻产品公开架构里没有的一层。
没有参考类数据时诚实置空——编造基础比率比不写更糟。

## 6. 为什么必须证据锚定：Nemeth 反面证据

Nemeth, Brown & Rogers (2001), European Journal of Social Psychology：

> "The authentic minority was superior to all three forms of 'devil's advocate,' again
> underscoring the value and importance of authenticity and the difficulty in cloning such
> authenticity by role-playing techniques."

后续（Nemeth 2018, In Defense of Troublemakers）：不真实的异见"can cause people to become
more entrenched in their original beliefs"——指派型唱反调可能适得其反。

**对本 skill 的直接含义**：自由发挥式的抬杠被禁止；每条反证锚定到真实材料的具体位置，
是在用「真实证据」替代「真实异议者」。同理，制度设计上更强的形态是让双方都真信自己立场
（CIA Team A/Team B 的双队对抗 + 独立陪审），以及真实持有反方利益的人（伯克希尔 2013 年起
邀请做空者 Doug Kass 上股东会质询）。本 skill 是这个谱系里的自动化近似，不是终点。

## 7. LLM 侧的实证

- **为什么模型不会自发唱反调**：RLHF 后的模型系统性迎合用户信念（Sharma et al.,
  "Towards Understanding Sycophancy in Language Models," ICLR 2024）。
- **显式反方人设的量化增益**：DEBATE（ACL Findings 2024）的 Commander/Scorer/Critic 三角色中，
  Critic 显式扮演 devil's advocate，相对此前最优方法在 SummEval/Topical-Chat 上提升
  6.4-12.5 个百分点的相关系数；论文明确指出反方人设显著优于中立多 agent 基线。
- **多个中立 agent 会互相强化错误共识**：Du et al.（2023）观察到"Despite answers being
  incorrect, language models would confidently affirm that their answer is correct and
  consistent with all other agent responses."——数字版团体迷思，正是需要显式反方角色的理由。
- **人机协同侧**：LLM 反方能促进群体对 AI 建议形成「恰当依赖」（Chiang et al., IUI 2024，
  随机对照人类被试实验；效应量数字本次溯源未获取到——论文全文在付费墙后）。

## 8. 制度化异议的历史教训（一条警示）

以色列军情局按阿格拉纳特委员会（1973 年赎罪日战争调查）的建议设立常设「魔鬼代言人」部门（Ipcha Mistabra），
2023 年 10 月 7 日仍未能阻止战略预警失败——公开复盘指出其隶属于被监督体系、规模萎缩、
只看加工后产品而非原始情报。**制度化本身不保效果**：异议渠道若没有独立性、没有触达原始
证据的权限，就会退化成走过场。对应到本 skill：反证检索必须直接读原始材料，不能只读别人
的摘要；产出必须交到有权改变决策的人手里，而不是归档了事。
