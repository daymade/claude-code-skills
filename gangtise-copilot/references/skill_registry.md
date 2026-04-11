# Gangtise Copilot — Skill Registry Reference

Complete per-skill capability matrix for all 19 Gangtise OpenAPI skills. Read this when you need to look up which skill answers a specific data question, or when you're routing a user request to the right upstream skill.

## How to use this reference

The matrix is organized into 4 tiers:

1. **Data-layer skills (6)** — raw data retrieval: financials, valuations, OHLC quotes, file searches
2. **Web layer (1)** — public web search via Gangtise's own web service
3. **Utility skills (2)** — stock pool CRUD + a no-download file-client variant
4. **Research workflow skills (10)** — higher-order workflows that orchestrate the data layer into end-to-end investment research reports

Each skill row shows the canonical install path, version, script count, and a one-line description of what it's best for. Full script parameters are in the upstream SKILL.md under each skill's own directory.

## Data-layer skills (6)

### `gangtise-data-client` v1.1.2 ⭐ RECOMMENDED

**What it does**: Structured quantitative data retrieval with 9 capabilities. Accepts security names ("宁德时代") or codes ("300750.SZ") and auto-resolves to the correct standard code.

| Capability | Script | Use for |
|---|---|---|
| Security resolution | `security.py` | Look up code + basic info + concepts for a named entity |
| Sector constituents | `block_component.py` | List stocks in a theme or industry (`-k 新能源汽车`) |
| Index catalog | `index.py` | List all indices by category (`-k 行业指数`) |
| Financial statements | `financial.py` | Pull income / balance / cash flow indicators (`--indicators 营业收入,净利润`) |
| Industry indicators | `industry_indicator.py` | Macro data + industry metrics (GDP, CPI, 新能源汽车销量) |
| Main business composition | `main_business.py` | Revenue breakdown by product / industry / region |
| OHLC daily quote | `quote.py` | Historical daily candles (开高低收, 前复权) |
| Shareholder data | `shareholder.py` | Top-10 shareholders + circulating shareholders |
| Valuation metrics | `valuation.py` | PE / PS / PB / PEG / EV + historical percentiles |

### `gangtise-data` v1.2.0 (legacy minimal)

**What it does**: A slimmed-down quantitative data skill with 4 capabilities. Requires strict security codes (`600519.SH` format) — does not resolve names. Output is explicitly CSV-focused for batch quantitative workflows.

| Capability | Script | Use for |
|---|---|---|
| Valuation | `valuation.py` | Same data as data-client, strict code input |
| OHLC quote | `quote.py` | Same data as data-client, supports `--all-market` |
| Main business | `main_business.py` | Same as data-client, requires `--period Q2` or `--period Q4` |
| Financial statements | `financial.py` | Same as data-client, income statement only |

**When to use the minimal line instead**: Batch CSV pipelines where strict code input is a feature (prevents ambiguous name resolution at scale). Not recommended for interactive or workshop use.

### `gangtise-kb-client` v1.1.2 ⭐ RECOMMENDED

**What it does**: Semantic search across Gangtise's internal knowledge base (research reports, chief opinions, meeting summaries, etc.). Returns relevant text chunks, not file IDs.

| Script | Key parameters | Use for |
|---|---|---|
| `kb.py` | `-q 查询语句 --file-types "研究报告,首席观点,会议纪要" --securities "宁德时代" -l 20` | Find what documents actually say about a topic, for a specific security or time range |

**When to use**: When you want to read / cite / summarize the text content of research materials. If you want to list or download specific files instead, use `gangtise-file-client`.

### `gangtise-kb` v1.1.2 (legacy minimal)

Same functionality as `gangtise-kb-client` but without the client-style parameter extensions. Use the client version unless you have a specific reason.

### `gangtise-file-client` v1.1.2 ⭐ RECOMMENDED

**What it does**: File-center search across 10 document types. Returns file IDs + metadata + summaries. This is the richest skill in the catalog at **18 scripts**.

| Script | Use for |
|---|---|
| `report.py` | Research reports by keyword / security / date / broker / industry / rating |
| `foreign_report.py` | Overseas (US/HK listed) research reports |
| `announcement.py` | Company announcements |
| `summary.py` | Meeting minutes (earnings calls, site visits, strategy meetings) |
| `opinion.py` | Chief analyst opinions |
| `investment_calendar.py` | Roadshows, site visits, strategy meetings, forums |
| `chart.py` / `get_chart.py` | ⭐ Chart data (not in the minimal variant) |
| `internal_report.py` + `internal_report_types.py` | ⭐ Internal research reports (not in minimal) |
| `wechat_message.py` + `wechat_message_blocks.py` | ⭐ WeChat messages — group chat content (not in minimal) |
| `opinion_blocks.py` | ⭐ Opinion content blocks (not in minimal) |
| `report_industries.py` / `report_types.py` / `announcement_types.py` / `summary_types.py` / `summary_industries.py` | Enumeration helpers to get valid industry / type values before calling the main scripts |
| `get_file.py` | Download a file by ID to local disk |

### `gangtise-file` v1.1.3 (legacy minimal)

Same file-type coverage as `gangtise-file-client` for the 6 core types (reports, opinions, summaries, announcements, etc.) but **missing** 7 scripts: `chart`, `internal_report`, `wechat_message`, `opinion_blocks`, and several enumeration helpers. Use the client version unless you specifically need the smaller footprint.

## Web layer (1)

### `gangtise-web-client` v1.1.2

**What it does**: Public web search via Gangtise's own web search service. Used for information that doesn't exist inside Gangtise's internal knowledge base — breaking news, third-party articles, policy announcements.

| Script | Use for |
|---|---|
| `web.py` | `-q 查询` to search the open web |

**Not a Google wrapper** — this is Gangtise's own indexing service. Returns the same document-chunk shape as the internal RAG.

## Utility skills (2, bundle-only)

### `gangtise-stockpool-client` v1.1.2

**Only distributed inside `gangtise-skills-client.zip`**. Standalone ZIP does not exist.

**What it does**: Stock pool (watchlist) management. List, create, rename, delete pools; add or remove constituent stocks.

| Operation | Use for |
|---|---|
| List pools | See what watchlists your account has |
| Create pool | `scripts/create_stockpool.py --name "新能源车" --stocks "比亚迪,宁德时代"` |
| Add to pool | Append stocks to an existing pool |
| Remove from pool | Remove by code |
| Delete pool | Delete entirely |

### `gangtise-file-client-no-download` v1.1.2

**Only distributed inside `gangtise-skills-client.zip`**. Standalone ZIP does not exist.

**What it does**: Same as `gangtise-file-client` but with the download capability disabled. Use this in read-only or compliance-sensitive environments where users should be able to search documents but not pull them to local disk.

## Research workflow skills (10)

These skills are **business-logic orchestrators**. Each one reads its upstream `SKILL.md`, follows a documented workflow, and invokes the underlying data-layer skills in a prescribed order to produce an end-to-end research deliverable. All 10 produce Markdown + HTML output and enforce Gangtise's compliance guardrails (no "买入 / 卖出 / 目标价 / 加仓 / 梭哈" language).

### `gangtise-stock-research` v1.1.2 ⭐ FLAGSHIP

**Individual stock research report** with 4 depth levels:

| Level | Scope | Triggered by |
|---|---|---|
| L1 | One-page recognition framework | "快速研究", "一页纸", "L1" |
| L2 | Complete investment view | "研究一下", "分析报告", "L2" |
| L3 | Institutional-grade first coverage | "深度报告", "首次覆盖", "L3" |
| L4 | Update on existing report | "财报更新", "跟踪一下", "L4" |

**Data dependencies** (this skill calls all of these):

- `data-client/security.py` — base company data
- `data-client/financial.py` — income statement metrics
- `data-client/main_business.py` — product breakdown
- `data-client/valuation.py` — PE/PS/PB percentiles
- `data-client/quote.py` — past 1-year OHLC
- `kb-client/kb.py` — semantic search of research reports + opinions + minutes
- `file-client/report.py` — last 3 months of reports
- `file-client/opinion.py` — chief opinions

And at L2+, additionally:

- `data-client/shareholder.py` — top-10 holders
- `data-client/industry_indicator.py` — industry metrics
- `file-client/summary.py` — meeting minutes
- `file-client/announcement.py` — past 6 months of announcements

And at L3, additionally:

- `data-client/block_component.py` — sector constituents for comparable analysis
- Comparable company valuation table

### `gangtise-opinion-pk` v1.1.2 ⭐ FLAGSHIP

**Adversarial opinion analysis** — "play devil's advocate" for an investment thesis. 5-step workflow:

1. **Parse user intent** — extract entity, entity type (STOCK / INDUSTRY / MACRO), sentiment (POSITIVE / NEGATIVE / NEUTRAL), rebuttal strategy
2. **Generate ~10 multi-dimensional search queries** tailored to the rebuttal strategy
3. **Fan out data retrieval** across data-client + kb-client + file-client + web-client
4. **Write 4-section adversarial report** (HTML template with dimensions / timeline_items / stress_tests / risk_signals placeholders)
5. **Output MD + HTML**

**When to use**: When the user says "帮我泼泼冷水", "有什么风险", "有什么机会", "对抗分析", "魔鬼代言人", or simply names a stock in neutral context (the workflow defaults to risk-focused analysis for neutral input).

### `gangtise-thematic-research` v1.1.2

Sector / theme research. Covers: theme definition, selection rationale, drivers, performance phases, stock screening, performance verification, strength assessment, risks. Outputs MD + HTML.

### `gangtise-stock-selector` v1.1.2

Stock screening methodology. Supports 4 common patterns (financial quality, growth, value, event-driven). Produces a screened list with scoring.

### `gangtise-event-review` v1.1.2

Market event post-mortem — 800-1000 word professional investment-research style report on a news event / policy change / earnings announcement / site visit.

### `gangtise-interview-outline` v1.1.2

Company-meeting interview outline generator. 3-step workflow: information gathering → topic classification → question list. Used before a site visit or management meeting.

### `gangtise-announcement-digest` v1.1.2 ⭐ RECOMMENDED FOR DEMO 1

Announcement tracking + digest. Takes a stock pool (Excel / CSV / code list) as input and produces a daily digest with two sections: (1) announcements relevant to your pool in the past 3 days, and (2) market-wide important announcements with type breakdown. Output is structured, conclusion-first, with drill-down links.

### `gangtise-opinion-summarizer` v1.1.2

Chief analyst opinion summarizer. Aggregates recent opinions from a named analyst, a named broker, or a named security / industry and produces a structured summary with per-opinion attribution.

### `gangtise-wechat-summary` v1.1.2 (oldest skill — 3/23 timestamp)

WeChat group chat → investment daily. Takes raw group chat export, classifies messages, tags them, and produces a structured investment daily in MD + HTML.

**Interesting metadata**: This skill has a Last-Modified timestamp of 2026-03-23 on the Gangtise OBS bucket, while every other skill in the catalog shows 2026-04-10. It is the oldest skill in the collection and likely the origin point of the workflow-skill pattern Gangtise later generalized into the 10-skill research suite.

### `gangtise-data-processor` v1.1.2

Meta-skill — provides methodology guidance for designing custom data-processing workflows. Does not itself call any data APIs; instead, it teaches the agent how to assemble the other skills into a custom pipeline (e.g., "get a sector list, rank by a metric, filter by another metric, output a report").

## Cross-skill composition examples

The real power of the catalog comes from combining skills. Here are three concrete compositions:

### Composition 1: Flagship workshop demo (Demo 2 in the 2026 Q2 Investor Workshop)

```
User: "Research 宁德时代 at L2 depth"
 └── gangtise-stock-research (workflow)
      ├── gangtise-data-client/security.py
      ├── gangtise-data-client/financial.py
      ├── gangtise-data-client/main_business.py
      ├── gangtise-data-client/valuation.py
      ├── gangtise-data-client/quote.py
      ├── gangtise-data-client/shareholder.py
      ├── gangtise-data-client/industry_indicator.py
      ├── gangtise-kb-client/kb.py  (×20 queries)
      ├── gangtise-file-client/report.py
      ├── gangtise-file-client/opinion.py
      ├── gangtise-file-client/summary.py
      └── gangtise-file-client/announcement.py
 └── Output: 宁德时代_研究_2026-04-11.md + 宁德时代_研究_2026-04-11.html
```

### Composition 2: Adversarial review of your own thesis (Demo 2 extension)

```
User: "I'm long 宁德时代 because of CapEx discipline. Find risks."
 └── gangtise-opinion-pk (workflow)
      ├── Parse: entity=宁德时代, type=STOCK, sentiment=POSITIVE, strategy=FIND_RISKS
      ├── Generate 10 risk-focused queries
      ├── gangtise-data-client/security.py + financial.py + valuation.py + quote.py
      ├── gangtise-kb-client/kb.py (for each of 10 queries, file-types=研究报告,首席观点,会议纪要)
      ├── gangtise-file-client/report.py + opinion.py
      └── gangtise-web-client/web.py (for public-web counterpoints)
 └── Output: 宁德时代_观点PK_2026-04-11.md + 宁德时代_观点PK_2026-04-11.html
             (with risk signals, timeline, stress tests, core contradiction)
```

### Composition 3: Daily digest machine (Demo 1 in the 2026 Q2 Investor Workshop)

```
User: "Watch my portfolio daily"
 └── gangtise-announcement-digest (workflow)
      ├── Read stock pool from Excel
      ├── gangtise-file-client/announcement.py (×N stocks, past 3 days)
      ├── Classify announcements by importance
      └── Generate daily digest MD + HTML
 └── Output pushed to Feishu Bot via webhook (not part of Gangtise itself — wire up via a separate flow)
```

## Compliance notes

Every workflow skill enforces these hard rules, copied from Gangtise's own compliance policy:

- **Forbidden language**: "推荐", "买入", "卖出", "目标价", "加仓", "潜伏", "建仓", "重仓", "梭哈"
- **Required substitutions**: 买入 → "关注" / "拥抱"; 卖出 → "警惕" / "风险释放"
- **No stock-price predictions** — analysis is limited to business-relevant factors
- **Disclaimer required**: "本分析基于公开数据，不构成投资建议"

If you're using these skills for a client-facing workshop, leave the compliance rules alone — they exist for good regulatory reasons.
