---
name: financial-router
description: >-
  Routes finance: Bigdata/RavenPack, US fundamentals/yfinance, A-share news,
  sector Top N/公告, pharma/医药板块/日报/飞书, Gangtise/岗底斯 setup. Reads one bundled
  specialist. General investment analysis and
  adversarial argument review keep their own entries.
---

# Financial data router

Choose a specialist only when the requested result matches a row below. Find
the path of **this loaded** `financial-router/SKILL.md` in the active catalog or
invocation, follow symlinks to its canonical path, and verify its parent is
`financial-router`. Its parent's parent is the suite root. Resolve the selected
relative path against the router directory and verify it is a direct sibling
`SKILL.md` inside that root. Do not use the task's working directory or a
remembered plugin cache path. Claude Code may provide `${CLAUDE_PLUGIN_ROOT}`;
the route must also work without it in Codex. If the loaded path is ambiguous,
stop instead of guessing which installation to read.

Read the selected child `SKILL.md` **in full** before acting. Continue any
truncated read, then read the references that child requires for this task.
The children remain installed but are absent from automatic discovery; open
their files directly. Claude users can still invoke the original
`/daymade-financial:<child>` commands manually.

| Requested result | Read this exact file |
|---|---|
| Use Bigdata.com/RavenPack's SDK or REST API for structured financials, prices, analyst estimates, sentiment, search, or screeners | `../bigdata-skill/SKILL.md` |
| Collect US company fundamentals and market data from free public sources into structured JSON for downstream analysis | `../financial-data-collector/SKILL.md` |
| Install or diagnose the Gangtise official Skill suite, configure its credentials, or repair Gangtise authentication | `../gangtise-copilot/SKILL.md` |
| Collect A-share company news, policy announcements, or stock-forum sentiment as sourced data | `../ashare-news-fetcher/SKILL.md` |
| Produce an A-share sector's board-wide Top N gainers, recent announcements, and evidence-graded market-sentiment report | `../daymade-sector-research/SKILL.md` |
| Produce an A-share pharmaceutical daily report, analyze today's 医药板块 snapshot, or send the pharma data to Feishu when authorized | `../pharma-daily-report/SKILL.md` |

Decide from the requested output and named provider. A sector Top N plus
announcement analysis selects `daymade-sector-research`; a news/policy feed
selects `ashare-news-fetcher`. Gangtise research **use** belongs to an
installed Gangtise runtime specialist or `gangtise-router`; the copilot row is
for setup and diagnosis. Generic equity analysis does not silently switch to
Bigdata, yfinance, or Gangtise. Use the installed market-research owner and
ask for a source preference only when it changes the result and none is given.

`devils-advocate` and `benchmark-due-diligence` are general reasoning
workflows, so they retain their direct automatic entries and are not routed
through this finance-only table. Selecting a child does not authorize a paid
API call, credential change, or delivery of a pharma report; follow the
selected child's gates and the user's authorization.
