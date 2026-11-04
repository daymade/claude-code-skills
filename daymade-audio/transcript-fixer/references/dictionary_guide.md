# 纠错词典配置指南（Dictionary Configuration）

词典保存在 SQLite 数据库中，通过 `--add` 命令维护。

## 词典存储

- [数据库位置与配置优先级](../scripts/utils/config.py)
- **核心表**：`active_corrections`，列名是 `from_text` / `to_text` / `domain`（不直观——写自定义 SQL 前先读 `database_schema.md`）
- **查看**：`uv run scripts/fix_transcription.py --list [--domain <d>]`

## 添加规则：`--add`

```bash
uv run scripts/fix_transcription.py --add "错误词" "正确词" [--domain <domain>]
```

- `--domain` 决定规则归属（默认 `general`）。**项目特定的词（人名 / 项目黑话 / 产品代号）务必用项目专属 domain**，不要进 `general`——否则会污染别项目的转写。详见 [dictionary_identity_and_context.md](dictionary_identity_and_context.md) 的「Project-Specific & Person-Name Corrections」。
- 应用时 `--stage 1 --domain <domain>` 使用该命名 domain 的简单替换规则，并加载 SQL `NULL` 全局 context rules 与该命名 domain 的 context rules 的并集；`--domain all`（默认）用所有 domain。命名 domain 的人名替换规则不会作用于别项目转写。

## 两类规则

### 1. 简单字符串替换（大多数情况）
`--add "巨升智能" "具身智能"` —— 全局子串替换。适合非词的 ASR garbling（克劳锐→Claude）、专有名词、人名。

### 2. 上下文规则（需要周边文字判断）
当一个词只在特定上下文才错（如「争」→「蒸」只在蒸馏讨论里），简单替换会误伤正常用法。这类应作为 context rule（带正则 pattern + 周边短语）维护，而非全局替换。规则结构与维护见 `database_schema.md` / `sql_queries.md`。优先级：context rule 先于简单替换应用。

## False Positive 防范（加规则前必读）

添加前按 [Dictionary Addition After Fixing](dictionary_identity_and_context.md#dictionary-addition-after-fixing) 判定是否可复用，并区分命令的警告与拒绝；误报检查细节见 [False Positive Prevention Guide](false_positive_guide.md)。

## 维护命令

| 命令 | 作用 |
|---|---|
| `--list [--domain <d>]` | 列出规则 |
| `--audit [--domain <d>]` | 体检词典，报告可疑规则（短词 / 冲突等） |
| `--report-false-positive "<from>" "<to>" -d <d>` | 停用一条误报规则、降低其置信度。**两个参数是规则在词典里存的 from→to 对**（照 `*_changes.md` 的 From/To 抄），不是「错词→对词」语义——详见 [native_ai_full_workflow.md](native_ai_full_workflow.md) step 2；只管理 `corrections` |
| `--disable-context-rule` / `--enable-context-rule` | 停用或恢复 context rule；检查目标库、执行及审计读回均按 [CLI reference](script_parameters.md#fix_transcriptionpy) |
| `--load-presets <domain>` | 导入某 domain 的预置规则集（如 `tech`） |

## 学习闭环（AI → 词典自动晋升）

学习候选与自动批准条件见 [learning engine](../scripts/core/learning_engine.py)；用 `--review-learned` 查看建议、`--approve` 人工批准。
