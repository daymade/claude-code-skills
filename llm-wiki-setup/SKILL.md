---
name: llm-wiki-setup
description: Co-create a personal investment-research LLM Wiki (Andrej Karpathy's pattern) where the user's OWN analysis framework becomes a living CLAUDE.md — by interviewing them, NOT by handing them a template. Use whenever the user wants to build a compounding research knowledge base, 投研第二大脑, 投研知识库, or 个人投研 wiki; instantiate Karpathy's LLM Wiki gist for finance/investing; turn their stock-picking, analyst-tracking, or earnings-watching workflow into a structured markdown vault; or build a wiki tracking companies / industries / macro / analysts over time. Pure markdown + wikilinks, NO RAG / vector DB (Karpathy's core idea — do not over-engineer). Also triggers for ingesting research reports / earnings calls / expert notes into an existing wiki, and for post-earnings prediction→fulfillment reviews. Core value = extracting the user's personal investment preferences into THEIR OWN schema, never imposing a standard one.
---

# LLM Wiki Setup（投研第二大脑共创）

帮用户搭一个**金融投研专用 LLM Wiki**（Karpathy 模式）：纯 markdown 文件 + `[[wikilink]]` 互联 + LLM 维护，知识随用复利。

**但核心不是给一份投研模板——是引导用户把他自己的投资判断方式，提炼成他专属的 CLAUDE.md。**

## ★ 先读这一条（这个 skill 的灵魂）

**每个人用自己的语言、自己的投资偏好，建自己的 CLAUDE.md。**

两个投资者看同一家公司，关注点可能完全不同——一个看「下季度订单能否超市场预期」，另一个看「管理层电话会上的语气和信心」。**给他们同一份模板，就抹掉了让 wiki 有用的那个东西。**

- ✅ 你的工作 = 访谈用户 → 提炼他的关注维度 → 用**他的话**写进 CLAUDE.md
- ❌ 你的失败 = 套一份「标准投研 schema」让他填空，或让他照抄 `examples/`

`examples/investment-research-CLAUDE.md` 是**一个人长成的样子**，给用户看可能性，**禁止照抄**。它像模板一样被搬走，这个 skill 就失败了。

## 不碰的红线（Karpathy 原意，别 over-engineer）

纯 markdown + wikilink + grep。**不加 RAG / 向量库 / embedding。** 知识靠预编译进结构化页「复利」，不是每次 query 重新检索原始文档——这是本模式相对 RAG 的根本区别，也是 Karpathy 的核心 idea。别加回任何检索层，别加 knowledge graph / 自动 health-check 之类机制（社区有些版本加了，那是 over-engineer）。

## 机制层 vs 规则层（贯穿全程的区分）

| | 内容 | 处置 |
|---|---|---|
| **机制层** | 三层目录 + wikilink + lint + git hook | ✅ 通用工程结构，`scripts/init_vault.py` 直接装 |
| **规则层** | 看哪些维度 / 怎么记观点 / 要不要分析师归属 / 怎么复盘 / 要长报告还是三行 | ❌ 用户的投资大脑，**访谈长出来**，绝不给模板 |

机制层照抄没问题（它是 Karpathy 模式的工程卫生，跟「你怎么投资」无关）。规则层照抄 = 背叛方法论。

## 工作流

### Phase 0 — 判断意图
- **新建 vault** → Phase 1
- 已有 vault，**ingest 一份源** → 直接读 `references/ingest_sop.md`
- 已有 vault，**财报后复盘某标的** → `references/fulfillment_sop.md`
- **query** → 读 vault 的 `index.md` + 相关页，带 citation 综合答；好答案回填 synthesis

### Phase 1 — scaffold 机制层
```bash
python scripts/init_vault.py <目标目录>
```
建空骨架（三层目录 + lint + hook 占位 + 空 index/log + CLAUDE 骨架）。**这一步只装机制层，不写任何 schema。**

### Phase 2 — 访谈共创 CLAUDE.md ★核心步骤
**读 `references/interview.md`，按它的 8 个维度一条条访谈用户**，把回答用**他自己的话**写进 `<vault>/CLAUDE.md` 规则层的占位。

- 一次问一个维度，别一口气灌
- 用户不在乎的维度**直接砍**（极简 > 全面）
- 卡住才翻 `examples/` 给灵感，明说「别抄，挑你戳中的」
- 自检：写好的 CLAUDE.md 像不像「这个人」？**像通用模板就重来**

### Phase 3 — 启用防腐
```bash
cd <vault> && git init
git config core.hooksPath .githooks   # local 配置，换机/重 clone 要重设
PYTHONUTF8=1 uv run --no-project --with pyyaml python3 scripts/lint-vault.py wiki  # 确认绿灯
```

### Phase 4 — 首次 ingest 演示
拿用户**一份真实的源**（研报 / 电话会 / 纪要），按 `references/ingest_sop.md` 走一遍 HITL 5 卡点，让他亲眼看到 wiki 怎么从源长出来。**用用户自己的素材，不要用 examples。**

## 后续运营（按需读 references）

| 场景 | 读 |
|---|---|
| ingest 新源 | `references/ingest_sop.md`（doc_type 用用户自己定的分类） |
| 财报后复盘 | `references/fulfillment_sop.md`（分析师回测调 `analyst-track-record` skill，别重造） |
| vault 卫生（派生值漂移） | `references/prune_discipline.md` |
| 复盘页对抗审查 | `references/counter_review.md` |
| 怎么访谈提炼用户的投资大脑 | `references/interview.md`（Phase 2 的完整方法） |

## 为什么这个 skill 是 inline（不设 context: fork）

它要调 `analyst-track-record` skill（复盘回测）、跑 Bash（scaffold / lint）、可能并行 Task 取财报数据——subagent 不能调 skill 或 spawn subagent，所以必须 inline。

## Next Step

vault 搭好、用户开始 ingest 卖方研报后，如果他想回测某分析师过去准不准 → 建议接 `analyst-track-record` skill（双维度命中率，有 validated 脚本）。
