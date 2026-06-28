# 输出数据结构

`scripts/fetch_intel.py` 输出的每个情报条目都是 `InfoItem` 序列化后的字典。

## InfoItem 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `item_id` | `str` | 由 `source_id:title:url` SHA256 前 16 位生成的确定性 ID |
| `source_id` | `str` | 信源内部 ID，如 `cn_sina`、`policy_csrc`、`guba_000001` |
| `source_name` | `str` | 可读信源名，如 `sina`、`证监会`、`东方财富股吧` |
| `title` | `str` | 标题 |
| `summary` | `str` | 摘要/正文片段 |
| `url` | `str` | 原文链接（可能为空） |
| `category` | `str` | 分类：`market` / `policy` / `global` / `social` |
| `priority` | `str` | 优先级：`breaking` / `high` / `normal` / `low` |
| `tags` | `list[str]` | 来源标签，如板块、话题 |
| `related_symbols` | `list[str]` | 从标题/摘要提取的 6 位 A 股代码 |
| `published_at` | `str` | 发布时间。中文快讯为 `YYYY-MM-DD HH:MM:SS`；政策来源为 `YYYY-MM-DD` 或 `YYYY-MM-DD HH:MM:SS`（视来源而定）；股吧为抓取时间（近似） |
| `fetched_at` | `str` | 抓取时间（UTC） |
| `extra` | `dict` | 额外字段，例如政策 `impact_category`、股吧 `sentiment_score` |

## category 取值

- `market`：中文财经快讯
- `policy`：监管/政策公告
- `global`：新浪 7x24 全球新闻
- `social`：股吧/社交媒体情绪

## priority 取值

- `breaking`：中文快讯来源标记为重要/高优先级
- `high`：政策来源命中高影响关键词
- `normal`：普通条目
- `low`：保留，暂未使用

## extra 示例

### 政策来源

```json
{
  "impact_category": "monetary"
}
```

### 股吧来源

```json
{
  "sentiment": "bullish",
  "sentiment_score": 0.35,
  "post_count_24h": 30
}
```
