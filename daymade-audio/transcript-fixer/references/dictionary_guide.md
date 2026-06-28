# 纠错词典配置指南（Dictionary Configuration）

> 词典是 **SQLite 数据库**（`~/.transcript-fixer/corrections.db`），通过 `--add` 命令维护——**不是**硬编码在 `fix_transcription.py` 里。早期版本曾用代码内的 `CORRECTIONS_DICT` / `CONTEXT_RULES` 常量，现已全部迁入 db；本指南只描述当前的 db 机制。（旧的「编辑 CORRECTIONS_DICT」流程已废弃，勿再照做。）

## 词典存储

- **位置**：`~/.transcript-fixer/corrections.db`（home 相对路径，skill 更新/迁移不丢用户数据；可用 `TRANSCRIPT_FIXER_DB_PATH` 覆盖）
- **核心表**：`active_corrections`，列名是 `from_text` / `to_text` / `domain`（不直观——写自定义 SQL 前先读 `database_schema.md`）
- **查看**：`uv run scripts/fix_transcription.py --list [--domain <d>]`

## 添加规则：`--add`

```bash
uv run scripts/fix_transcription.py --add "错误词" "正确词" [--domain <domain>]
```

- `--domain` 决定规则归属（默认 `general`）。**项目特定的词（人名 / 项目黑话 / 产品代号）务必用项目专属 domain**，不要进 `general`——否则会污染别项目的转写。详见 SKILL.md「Project-Specific & Person-Name Corrections」。
- 应用时 `--stage 1 --domain <domain>` **只用该 domain 的规则**；`--domain all`（默认）用所有 domain。这就是隔离机制：`--domain <项目>` 的人名规则不会作用于别项目转写。

## 两类规则

### 1. 简单字符串替换（大多数情况）
`--add "巨升智能" "具身智能"` —— 全局子串替换。适合非词的 ASR garbling（克劳锐→Claude）、专有名词、人名。

### 2. 上下文规则（需要周边文字判断）
当一个词只在特定上下文才错（如「争」→「蒸」只在蒸馏讨论里），简单替换会误伤正常用法。这类应作为 context rule（带正则 pattern + 周边短语）维护，而非全局替换。规则结构与维护见 `database_schema.md` / `sql_queries.md`。优先级：context rule 先于简单替换应用。

## False Positive 防范（加规则前必读）

加错规则会**静默污染**未来所有转写。`--add` 对高风险词会警告（但不阻止）：

- **短词（≤2 字）**：作为子串匹配，易命中更长的词。一个 2 字人名 / 词的纠错（`--add "<2字错写>" "<2字正确>"`）会触发 short-text 警告——2 字词容易作为子串命中更长的词，而且某项目里要纠的词在别项目可能是正常词的一部分。**解法：用项目 `--domain`**，规则只在该项目应用，别项目不受影响。
- **真实词 → 另一个词**：如果「错写」端本身是个真实存在的词（常见姓氏、地名、普通词汇），放进 `general` 会误伤别的语境里这个词的正常用法。同样靠 `--domain` 隔离到项目内。
- 完整判断标准见 `false_positive_guide.md`。

## 维护命令

| 命令 | 作用 |
|---|---|
| `--list [--domain <d>]` | 列出规则 |
| `--audit [--domain <d>]` | 体检词典，报告可疑规则（短词 / 冲突等） |
| `--report-false-positive "错" "对" -d <d>` | 停用一条误报规则、降低其置信度 |
| `--load-presets <domain>` | 导入某 domain 的预置规则集（如 `tech`） |

## 学习闭环（AI → 词典自动晋升）

Stage 2（AI 纠错）确认的修正会记入 db；同一模式出现 ≥3 次、置信 ≥80% 会从「AI 建议」自动晋升为词典规则（`--review-learned` 查看、`--approve` 人工批准）。这让词典随使用越来越准——**这正是「复利」的来源**：一次确认，未来同类转写自动纠，无需重写脚本。
