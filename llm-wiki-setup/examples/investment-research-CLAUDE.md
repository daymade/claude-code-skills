<!--
⚠️ 这是一份【参考样例】，不是模板，禁止照抄。
这是「一个看卖方研报的机构投资者」把他的投资大脑写成 CLAUDE.md 后长成的样子，
给你看「一份投研 wiki 可以长成什么样」——它的层级、维度、规则都是【那个人的】偏好。
你的 CLAUDE.md 应该用【你自己的语言、你自己的关注点】写（见 templates/CLAUDE-skeleton.md）：
  · 你不看卖方研报？删掉「分析师归属」整层。
  · 你只关心高管语气？加一条这里没有的「管理层 sentiment」维度。
  · 你要三行结论不要长报告？规则就该这么写。
挑你真在乎的，能砍就砍。照抄 = 又变成「别人的模板」，背叛了「每个人建自己的」。
-->

# CLAUDE.md — 投研 LLM Wiki（参考样例 · 某机构投资者版）

这是一个 **金融投研 LLM Wiki**，instantiate 自 Karpathy 的 gist
（<https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f>）。
纯 markdown + `[[wikilink]]` + grep，无 RAG/向量库/embedding——Karpathy 原意，别加检索层。

> 下面 H1-H11 是【这位机构投资者】选择的规则。它们**不是 LLM Wiki 的「标准」**，
> 是「看卖方研报、追踪分析师、按季报节奏复盘」这套工作方式的显性化。
> 你的工作方式不同，规则就该不同——用 templates/CLAUDE-skeleton.md 写你自己的。

- 覆盖领域：AI 算力价值链（GPU/ASIC/光通信/存储 + hyperscaler 买方）
- 数据来源：卖方深度研报 / 财报电话会 / SEC filing / 行业数据库

---

## H1 — 三级骨架 hard rule

每一篇 wiki 页必须明确归属到下列**且仅下列**三个层级之一：

- `wiki/macro/` — 宏观（货币政策、利率、流动性、汇率、地缘、政策）
- `wiki/industries/` — 中观（行业、赛道、产业链、供需）
- `wiki/companies/` — 微观（个股、上市公司、私人公司）

辅助层（**不是**骨架，是横切关注点）：
- `wiki/analysts/` — 分析师档案 + 历史预测准确度
- `wiki/themes/` — 跨行业主题（如「AI 算力」「国产替代」）
- `wiki/synthesis/` — 跨源对比、跨时点对比、矛盾归档

**禁止把 macro 内容写进 companies/，反之亦然。** 一篇研报涉及多个层级时，必须**分别**更新对应页，并通过 `[[wikilink]]` 互联。

## H2 — 分析师归属（analyst attribution）是一等公民

每一条**观点 / 预测 / 评级**必须挂在分析师名下。frontmatter 必须包含 `analysts:` 字段，且每个分析师在 `wiki/analysts/` 下必须有对应页面记录其历史预测准确度。

任意 entity 页（macro / industries / companies）的「观点」段落必须使用以下格式：

```markdown
- **[[analysts/<分析师姓名>]] (<券商>, <YYYY-MM-DD>)**: 上调评级至「买入」，目标价 <币种><价>（当前 <币种><价>，上行空间 +<N>%）。理由：Q1 营收 +<N>% YoY，超预期 <N>pp。 [来源：[[raw/<source-file>#p3]]]
```

**禁止匿名观点**（「市场认为」「机构普遍预期」）。如果源文档没说是谁说的，标 `[[analysts/_anonymous]]` 并在 lint 时降权。

> 这是本 skill 相对通用 LLM Wiki 的核心差异：通用版只有一个 `sources` 字段，记不下「谁说的 + 他过去准不准」。投研的 alpha 恰恰在分析师的判断力和历史命中率上。

## H3 — 时点快照（point-in-time snapshot）

研报世界的核心时间结构是 **半年报 / 年报 / 季频 / 临时事件**。Karpathy 默认的 `created/updated` 不够。每篇 entity 页必须维护一个 `## 时点视图历史` section，结构如下：

```markdown
## 时点视图历史

### <YYYY-MM-DD>（Q1 财报后）
- 共识评级：买入（<N> 家覆盖）
- 共识目标价：<币种><价> ± <币种><价>
- 关键变化 vs 上期：上调 EPS 预测 +<N>%，主因 <驱动>
- 关键风险：<风险，如客户集中度（前 3 大客户占 <N>%）>

### <YYYY-MM-DD>（Q1 业绩快报前）
- 共识评级：增持（<N> 家覆盖）
- 共识目标价：<币种><价> ± <币种><价>
- 关键变化 vs 上期：行业 beta 上调
```

**所有 wiki 页都必须有这个 section，即使只有 1 个时点。** 这让「今天 vs 一个月前对比」成为零成本 query。

## H4 — 文档类型分流（ingest branching）

raw 目录的源文档必须打上 `doc_type` 标签。**不同 doc_type 触发不同 ingest 分支**：

| doc_type | 典型来源 | ingest 重点 | 触发的 wiki 更新 |
|----------|----------|-------------|------------------|
| `depth_report` | 卖方深度研报（30+ 页） | 完整观点 + 数字 + 估值方法 | macro/industries/companies/analysts 全更新 + synthesis 对比 |
| `market_update` | 早报、晚报、点评（< 5 页） | 仅提取**新增**观点和数字变化 | 仅在变化的 entity 页 append 新时点 |
| `expert_call` | 专家纪要、电话会 | 提取**专家身份 + 立场 + 数字** | 主要更新 industries 和 themes，分析师页不动 |
| `earnings_call` | 业绩说明会 | 提取**管理层指引** vs **分析师 Q&A** | companies 页 + 触发 analysts 历史回测 |
| `regulatory` | 监管文件、政策原文 | 仅提取条款，不评论 | macro 页 + 受影响 industries |

**禁止用同一套模板处理所有文档。** 如果 doc_type 不在上表，停下来问用户。

## H5 — 数字必须保留原文 + 单位 + 时点

任何数字（营收、目标价、EPS、市占率）必须以下列格式落地：

```
营收：<币种><值>（<YYYYQN>，YoY +<N>%，源：[[raw/<source>#p3]]）
```

**禁止把数字孤立写**（「营收 12.3 亿」）。lint 会把孤立数字标 `STALE_NUMBER`。

## H6 — 观点冲突必须显式归档

当两个分析师 / 两份研报对同一 entity 给出冲突观点时（评级冲突、目标价 ±20% 以上、行业判断相反），必须在 `wiki/synthesis/` 下创建专门的对比页。**禁止只在 entity 页悄悄并列**——冲突是信号，必须 surface。

格式：

```markdown
# Synthesis: [[companies/<TICKER>]] 评级分歧 <YYYY-QN>

## 多头视角
- [[analysts/<A>]] (<券商>): 买入，目标价 <币种><价>，理由 ...

## 空头视角
- [[analysts/<B>]] (<券商>): 减持，目标价 <币种><价>，理由 ...

## 关键分歧点
1. 对 <核心驱动> 可持续性的判断（A 认为 <N> 个月强周期，B 认为 <N> 个月透支）
2. ...

## 历史回放
- A 在 <上一类似情境> 的预测：✅ 准（命中目标价 +5% 内）
- B 在 <上一类似情境> 的预测：❌ 偏空 15%
```

## H7 — Lint 规则（金融特化）

> **自动化**：**结构性检查**——wiki 内部断链（`[[X]]` 指向不存在页）+ frontmatter YAML 合法 + CROSS_LEVEL_LINK——已脚本化为 `scripts/lint-vault.py`，挂进 git pre-commit hook：**commit 涉及 vault 文件时自动跑，硬 fail 阻断 commit**，不靠人记忆/自觉。其余**语义类**（STALE_NUMBER / MISSING_ANALYST / 派生值过时副本）lint 抓不到，仍需 LLM / counter-review。

每次 ingest 完后必须跑下列检查（结构类已 hook 自动化，语义类由 LLM 做）：

**硬错（阻断 commit）**：
1. **BROKEN_WIKILINK**：`[[X]]` 指向 vault 内不存在的页
2. **INVALID_YAML**：frontmatter 解析失败（如值含未转义冒号）
3. **CROSS_LEVEL_LINK**：companies 页没有链到任何 industries 或 macro/themes 页（孤立微观信息无价值）

**软警告（提示不阻断）**：
4. **STALE_NUMBER**：超过 90 天没更新的数字标记 `⚠️ STALE`
5. **MISSING_ANALYST**：观点没有 `[[analysts/...]]` 链接
6. **CONFLICT_UNARCHIVED**：同一 entity 页出现冲突观点但没建 synthesis 页
7. **ORPHAN_DOC**：raw 文件没有任何 wiki 页引用
8. **TIMELINE_GAP**：entity 页时点视图历史超过 60 天没更新
9. **OVERSIZED_PAGE**：单页过长（>200 行）建议拆分

## H8 — HITL 卡点（ingest 时必须停下来问的 5 个问题）

ingest 一份新源时，**禁止一气呵成**。必须在以下 5 个卡点跟用户确认：

1. **doc_type 确认**：`这份是 depth_report / market_update / expert_call / earnings_call / regulatory？`
2. **核心 takeaways 确认**：LLM 提 3-5 条，让用户选哪些进 wiki
3. **新建 vs 更新 entity 决策**：`这家公司在 wiki/companies/ 下没有，要新建吗？还是合并到 [[companies/<母公司>]]？`
   - **建页门槛（page threshold）**：一个实体/概念出现在 **2+ 个源**，或对**单个源是 central** 时才建独立页；否则并进已有页的一节，避免页面爆炸。
4. **冲突 surface**：如果发现和已有 wiki 冲突，必须停下来问 `这个冲突要进 synthesis 吗？还是修订旧观点？`
5. **时点快照确认**：`这次 update 的时点 label 是「Q1 财报后」还是「管理层电话会后」还是别的？`

## H9 — 查询模式（query 时的分流）

用户来 query 时，先判断 query 类型：

| Query 类型 | 入口文件 | 是否回填 wiki |
|-----------|---------|---------------|
| 「X 公司最新共识？」 | `wiki/companies/X.md` 的「时点视图历史」最新一条 | 否（read-only） |
| 「分析师 Y 准吗？」 | `wiki/analysts/Y.md` 的历史 track record | 否 |
| 「今天 vs 一个月前？」 | 比较 `wiki/companies/X.md` 时点视图历史的两条 | 否 |
| 「<主题> 谁最看好？」 | `wiki/themes/<主题>.md` 跨 entity 综述 | 是（如发现新连接） |
| 「为什么我没听过 ZZZ 公司？」 | 触发 web search + ingest 流程 | 是（新建 entity） |

**最后一类是 synthesis 回填**——探索的复利。

## H10 — CLAUDE.md 是活文档

每次 ingest 后如果发现现有 schema 不够，**主动提议修订本 CLAUDE.md**。但修订必须经用户确认。**禁止 LLM 自己改 H1-H10。** 可以 append H11、H12……新规则。

## H11 — 财报后兑现复盘 SOP

已 ingest pre-earnings 预判的标的，财报发布后做兑现复盘——这是 vault 复利的核心证据（预测 → 兑现 → 校准）。**这是本 skill 相对通用 LLM Wiki 最大的差异：通用版的「复利」是知识累积，这里的「复利」是判断力校准。**

**触发**：某标的在 `synthesis/<TICKER>-<period>-pre-earnings` 有预判，且该 period 财报已发。

**步骤**：
1. **取真实财报**：多路 fan-out（核心财务 / 分部利润率 / 电话会 / 预期差 / 同行 / vault 基线），每数字带一手出处（官方 filing / transcript）+ ≥2 源交叉验证。**禁凭训练记忆编财报后数字**（财报常在知识截止后）。
2. **建复盘页**：`synthesis/<TICKER>-<period>-results.md`（`doc_type: earnings_call`），不复用 pre-earnings 页。
3. **对账（核心）**：逐条对照 pre-earnings 预判，按 **方向 / 机制 / 阈值** 分层，每条标 ✅验证 / ⚠️偏差 / ❌证伪。引用 pre-earnings 原文 **必带行号**（可现场点回，证明非事后诸葛亮）。
4. **回填**：company 时点视图 append 财报后一条（H3）；相关 analyst track record append datapoint（标 Pending，不提前定中长期输赢）。

**铁律**：
- **押对方向 ≠ 精准命中**：诚实承认阈值偏差 + 指认哪个判断框架被验证、哪个被证伪——比「精准命中」经得起 sophisticated 买方拷问。装「算命准」会被基金经理当场问倒。
- **falsification 必标**：写明「什么结果会让原判断被证伪」（押下行 → 大涨即错），否则是 unfalsifiable 的「怎样都对」。
- **n=1 ≠ alpha 统计证明**：单标的单次兑现是方法论闭环演示，标注清楚，别声称统计显著。
- 复盘页 register 是写给 sophisticated 买方的：让数据 / 对账表自己说话，禁「硬证据 / 精准命中 / X 是 A·Y 是 B 对仗」式灌结论。

---

## 投研偏好（按你的真实偏好填）

- **重视数字** > 形容词。「显著增长」没价值，「+32% YoY」才有价值
- **重视观点** > 信息汇总。研报的价值是分析师的判断，不是公开信息的堆砌
- **重视对比** > 单点描述。「今天比一个月前看多了」比「今天看多」信息密度高一个量级
- **分析师 vs 分析师**：当两个分析师对同一公司分歧时，这是 alpha 的源头
- **今天 vs 一个月前**：当机构集体观点漂移时，这是趋势的源头

---

## 不要做的事（铁律）

- ❌ 不要写「市场认为」「普遍预期」——必须挂分析师名
- ❌ 不要孤立数字——必须带单位 + 时点 + 出处
- ❌ 不要悄悄并列冲突观点——必须建 synthesis 页
- ❌ 不要跨层级写——macro 内容不进 companies 页
- ❌ 不要一次 ingest 一份长研报不停下来问 HITL 5 问
- ❌ 不要相信 doc 扩展名——`file` + 用户确认 doc_type
- ❌ 不要加 RAG / 向量库 / embedding —— 纯 markdown 是本模式的本质，不是限制
