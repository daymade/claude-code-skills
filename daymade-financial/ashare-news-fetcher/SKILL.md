---
name: ashare-news-fetcher
description: >-
  抓取 A 股消息面情报：从财联社、华尔街见闻、金十、新浪 7x24、东财快讯、
  证监会/央行/上交所/财政部政策公告、东方财富股吧等公开来源抓取与股票相关的
  新闻、政策、情绪，输出结构化 JSON 或 Markdown。
  当用户提到“A 股消息面”、“抓新闻”、“个股消息”、“政策监管”、“股吧情绪”、
  “财联社”、“东财快讯”、“市场情绪”或需要把某只股票相关的公开情报聚合出来时
  触发。也适用于“帮我看看 000001 最近有什么消息”这类口语化请求。
argument-hint: "[--sources <groups>] [--symbols <codes>] [--limit <n>]"
---

# A 股消息面抓取

从多个公开中文财经/政策/社交来源抓取 A 股相关情报，输出结构化条目。

## 这个 skill 做什么

1. 抓取中文财经快讯（财联社、华尔街见闻、金十、新浪 7x24、东财快讯）
2. 抓取监管政策公告（证监会、央行、上交所、财政部）
3. 抓取东方财富股吧的个股情绪指标
4. 从标题/摘要中提取相关 A 股代码
5. 输出 JSON 或 Markdown，方便后续分析、存档或喂给 LLM

## 能力边界

**能做的：**
- 输入股票代码（如 `000001,600519`）抓取该股股吧情绪
- 不输入代码时抓取全市场财经/政策快讯
- 按关键词过滤结果
- 输出 JSON（结构化）或 Markdown（可读）

**不能做的：**
- 不抓取付费/登录墙后的内容
- 不保证实时性（来源本身是公开聚合，可能有分钟级延迟）
- 不抓取交易所 L1/L2 行情（这是新闻/情绪抓取，不是行情接口）
- 不替代合规投顾研究，输出仅作信息聚合参考

## 前置条件

- Python 3.10+
- `requests`（必须）
- `beautifulsoup4`（可选，只有抓取政策来源时才需要）
- `akshare`（可选，用于名称→代码匹配；没有时只用正则提取代码）
- `jieba`（可选，安装后名称匹配使用分词，降低误匹配）
- 环境变量 `JIN10_APP_ID`（金十数据接口需要；未设置时会跳过该来源，不影响其他 `cn` 来源）

最简安装：

```bash
pip install requests
# 如需政策来源：
pip install beautifulsoup4
# 如需名称匹配：
pip install akshare
# 如需更精确的名称匹配：
pip install jieba
```

## 使用方式

### 方式 1：对话里直接调用

```
/ashare-news-fetcher 000001,600519 cn,guba
```

参数说明（都是可选的）：
- 第一个参数：股票代码，逗号分隔，例如 `000001,600519`
- 第二个参数：来源组，逗号分隔，可选 `cn`（中文快讯）、`policy`（政策）、`guba`（股吧）
- 不传参数时默认 `--sources cn --limit 30`

### 方式 2：直接运行脚本

```bash
python scripts/fetch_intel.py --sources cn,policy --limit 20
python scripts/fetch_intel.py --symbols 000001,600519 --sources guba
python scripts/fetch_intel.py --sources cn --keywords 降准,降息 --format markdown
```

常用选项：
- `--sources`：来源组，默认 `cn`
- `--symbols`：股票代码，用于 `guba`
- `--keywords`：关键词过滤，逗号分隔
- `--limit`：每组最多返回条数，默认 30
- `--format`：`json` 或 `markdown`，默认 `json`
- `--output`：输出到文件；省略则打印到 stdout
- `--verbose`：打印调试日志

## 信源说明

| 来源组 | 来源 | 内容类型 | 是否需要 bs4 |
|---|---|---|---|
| `cn` | 财联社、华尔街见闻、金十、新浪 7x24、东财快讯 | 市场快讯 | 否 |
| `policy` | 证监会、央行、上交所、财政部 | 政策/监管公告 | 是（证监会除外） |
| `guba` | 东方财富股吧 | 个股散户情绪 | 否 |

详细 API 端点和解析方式见 `references/source_apis.md`。

## 测试

测试说明与运行方式见 `references/testing.md`。

## 输出格式

### JSON

每个 item 的结构见 `references/output_schema.md`。示例：

```json
{
  "item_id": "4ffde7bc7b18b55e",
  "source_id": "cn_sina",
  "source_name": "sina",
  "title": "...",
  "summary": "...",
  "url": "...",
  "category": "market",
  "priority": "normal",
  "tags": ["公司", "市场"],
  "related_symbols": ["000001"],
  "published_at": "2026-06-25 17:50:41",
  "fetched_at": "2026-06-25 09:50:52",
  "extra": {}
}
```

### Markdown

按时间倒序排列，每条展示来源、时间、分类、相关代码、标签、链接和摘要。

## 注意事项

- 公开接口可能随时变化；脚本会跳过失败的来源，不影响其他来源。
- 如果在国内网络环境遇到请求失败，确认系统 HTTP_PROXY/HTTPS_PROXY 已指向可用代理。
- `guba` 来源对反爬较敏感，建议单次不要请求过多股票，代码之间已有 0.5s 请求间隔。
- 使用金十数据（`jin10`）前，建议在环境变量中配置 `JIN10_APP_ID`；未配置时该来源会自动跳过，不影响财联社、华尔街见闻、新浪、东财等其他 `cn` 来源。
  ```bash
  export JIN10_APP_ID="your-app-id"
  ```

## Next Step

拿到结构化情报后，常见的下一步是交给分析 skill 做总结或生成日报：

> 要不要把这些消息总结一下，生成一份 A 股消息日报？

- A) 生成 Markdown 简报（推荐）
- B) 只做情绪/关键词聚合
- C) 不需要，当前输出已足够
