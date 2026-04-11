---
name: gangtise-copilot
description: One-stop installer and companion for the full Gangtise (岗底斯投研) OpenAPI skill suite — 19 official skills covering data retrieval (OHLC 行情, 财务, 估值, 研报, 首席观点, 会议纪要, 调研纪要), research workflows (个股研究 L1-L4, 观点 PK 对抗性分析, 主题研究, 事件复盘), and utility (股票池管理, 公开网页搜索). Zero-config install to Claude Code / OpenClaw / Codex with 4 preset modes (full / workshop / minimal / custom), guides accessKey + secretAccessKey setup with a live validation call against open.gangtise.com, and ships a read-only diagnostic script. Use this skill whenever the user mentions Gangtise, 岗底斯, gangtise-data, gangtise-kb, gangtise-file, gangtise-data-client, gangtise-kb-client, gangtise-file-client, gangtise-stock-research, gangtise-opinion-pk, installing any gangtise-* skill, configuring its credentials, or reports errors like 'token is invalid', '接口地址错误', 'the uri can't be accessed'. This is a wrapper around Gangtise's official skills — it installs and orchestrates them rather than replacing them.
---

# Gangtise Copilot

One-command installer, credential configurator, and diagnostic layer for the full Gangtise (岗底斯投研) OpenAPI skill suite.

## Overview

Gangtise is a Chinese professional investment-research data platform. It publishes an OpenAPI that covers research reports, company announcements, meeting summaries, chief analyst opinions, financial statements, valuation metrics, OHLC market data, shareholder data, industry indicators, and a catalog of pre-built research workflow skills (individual stock research, adversarial opinion analysis, thematic research, etc.). The underlying API is well-designed, but the skill ecosystem is **not discoverable**: there is no public manifest listing the 19 skills that exist, the skills are distributed as independent ZIP files on a Huawei Cloud OBS bucket with listing permission disabled, and the skills live in two parallel naming conventions (`gangtise-<name>` for the minimal line, `gangtise-<name>-client` for the full-capability line) that carry different feature sets. A first-time user has to reverse-engineer the complete skill inventory before they can install it.

Gangtise Copilot solves this in one command:

1. Installs all 19 official Gangtise skills to Claude Code, OpenClaw, and Codex via a single bundled-download + distribute pipeline.
2. Walks the user through accessKey + secretAccessKey setup with a live authentication call against `open.gangtise.com/application/auth/oauth/open/loginV2`.
3. Provides a read-only diagnostic script that reports which skills are installed, which credentials are valid, and which capability tiers are reachable.
4. Exposes preset install modes so a workshop learner gets a 7-skill minimal install while a power user can get the full 19-skill catalog.

## Architectural principles (do not violate)

This skill is a **wrapper layer** around the Gangtise OpenAPI skill suite. The wrapper contract is non-negotiable:

- **Never vendor upstream files.** This skill directory contains no copy, fork, or excerpt of any Gangtise skill content. When Gangtise ships a new release, users get the new release without any interference from this wrapper — the installer re-downloads from the canonical OBS URL every run.
- **Repairs (if any arise) happen at runtime, not at ship time.** This wrapper was distilled from a session that encountered no actual upstream bugs — the friction was discoverability and install orchestration, not broken files. If future upstream bugs arise, they will be added to `references/known_issues.md` with runtime repair instructions, not patched at ship time.
- **Always ask before touching upstream files.** Modifying any installed `gangtise-*` skill directory requires explicit user consent via AskUserQuestion.
- **Teach rather than hide.** Every installation step shows the user exactly which skills were downloaded, from where, and where the credential file was saved. This is how users learn to maintain their own installs.

## What this skill does

| Capability | Entry point | Detail |
|---|---|---|
| 1. Install Gangtise skills (full / workshop / minimal / custom) | `scripts/install_gangtise.sh` | See `references/installation_flow.md` |
| 2. Configure accessKey + secretAccessKey credentials | `scripts/configure_auth.sh` | See `references/credentials_setup.md` |
| 3. Diagnose install state, credential validity, and capability tiers | `scripts/diagnose.sh` | See `references/known_issues.md` |
| 4. Look up which Gangtise skill answers a specific data question | Skill registry below + `references/skill_registry.md` | — |

## Routing

When this skill is triggered, classify the user's intent and jump to the corresponding capability:

| User says something like… | Go to |
|---|---|
| "装 gangtise"、"install gangtise"、"我想用 gangtise 的数据"、"把 gangtise 的 skill 都装上" | **Capability 1** |
| "配 gangtise 的 key"、"configure gangtise credentials"、"gangtise accessKey"、"secretAccessKey" | **Capability 2** |
| "gangtise 报错"、"token is invalid"、"接口地址错误"、"gangtise skill 加载失败"、"我的 gangtise 装得不对" | **Capability 3** |
| "宁德时代的研报"、"过去 30 天的首席观点"、"OHLC 蜡烛图"、"个股研究报告 L2"、"对宁德时代做观点 PK" | **Capability 4** → skill registry → invoke the matching upstream skill |
| "帮我从头跑一遍 gangtise" | 1 → 2 → 3 → 4 in sequence |

When in doubt, start with Capability 3 (diagnose) — it is the only read-only entry point and it surfaces exactly which installs and credentials are currently blocked. Running it never has a destructive side effect.

## Capability 1: Install Gangtise skills

Gangtise publishes 19 independent skills on a Huawei Cloud OBS bucket. They are organized into 3 bundle ZIPs plus 1 standalone ZIP. The installer downloads the 4 archives, extracts the 19 skill directories, and symlinks each one into the detected agents' skills directories.

### Distribution source

All skills come from the official Gangtise OBS bucket:

```
https://gts-download.obs.myhuaweicloud.com/skills/
```

No mirrors. The installer uses this URL directly.

### Bundle map

| Bundle | Size | Contains |
|---|---|---|
| `gangtise-skills-client.zip` | 160 KB | data-client, kb-client, file-client, **file-client-no-download**, **stockpool-client** |
| `gangtise-research.zip` | 220 KB | stock-research, opinion-pk, thematic-research, stock-selector, event-review, interview-outline, announcement-digest, opinion-summarizer, wechat-summary, data-processor |
| `gangtise-skills.zip` | 118 KB | data (v1.2.0), file, kb — the legacy "minimal" parallel line |
| `gangtise-web-client.zip` | 8 KB | web-client (standalone, not in any bundle) |

**Total**: 4 HTTP requests → 19 skill directories.

Two skills (`gangtise-file-client-no-download` and `gangtise-stockpool-client`) **only exist inside the `gangtise-skills-client` bundle** — they do not have standalone ZIPs. A naive "list the standalone ZIP for each skill" approach would miss them entirely. See `references/known_issues.md` ISSUE-002 for the full explanation.

### One-command install

```bash
bash scripts/install_gangtise.sh
```

Flags:

```bash
bash scripts/install_gangtise.sh --preset workshop   # 7 skills for investor Workshop (Demo 1+2)
bash scripts/install_gangtise.sh --preset minimal    # 3 skills (legacy kb/file/data only)
bash scripts/install_gangtise.sh --preset full       # all 19 skills (default)
bash scripts/install_gangtise.sh --only data-client,kb-client,file-client  # custom subset
bash scripts/install_gangtise.sh --no-openclaw       # skip OpenClaw even if detected
bash scripts/install_gangtise.sh --target claude-code  # force single target
```

### Preset contents

| Preset | Skills | Intended for |
|---|---|---|
| **full** (default) | All 19 skills | Power users, workshops demonstrating the complete catalog, future-proof installs |
| **workshop** | data-client, kb-client, file-client, web-client, stock-research, opinion-pk, announcement-digest | 2026 Q2 investor Workshop — covers Demo 1 (岗底斯日报机器人) + Demo 2 (宁德时代研报时间轴验证) |
| **minimal** | data, file, kb | Legacy minimal line — only install this if the user explicitly wants the smaller footprint with reduced feature set |

## Capability 2: Configure credentials

Every Gangtise skill needs an `.authorization` credential file colocated with its Python runtime, in one of two shapes:

**Shape A** — accessKey + secretAccessKey (most common, auto-refreshes tokens):
```json
{
  "accessKey": "<your-accessKey>",
  "secretAccessKey": "<your-secretAccessKey>"
}
```

**Shape B** — long-term token (advanced, for pre-generated long-lived tokens):
```json
{
  "long-term-token": "Bearer <token>"
}
```

Because 19 skills each need the same `.authorization` file, the wrapper stores **one shared file** at `~/.config/gangtise/authorization.json` (XDG standard, mode 600) and symlinks every skill's local credential file to it. Rotating credentials means editing one file, not 19.

Run the configurator:

```bash
bash scripts/configure_auth.sh
```

It will:

1. Prompt for accessKey and secretAccessKey (or read from the `GANGTISE_ACCESS_KEY` / `GANGTISE_SECRET_KEY` environment variables if set).
2. Write to `~/.config/gangtise/authorization.json` with mode 600.
3. Perform a **live authentication call** to `https://open.gangtise.com/application/auth/oauth/open/loginV2` to verify the credentials actually work.
4. Create symlinks from every installed skill's local credential file to the shared XDG file.
5. Report success with the uid + userName returned by the Gangtise auth server.

### Credential rotation

```bash
# Edit one file:
$EDITOR ~/.config/gangtise/authorization.json

# Re-verify against the live server:
bash scripts/configure_auth.sh --verify-only
```

No other files need to change — the symlinks still point at the updated file.

## Capability 3: Diagnose install state

```bash
bash scripts/diagnose.sh
```

The diagnostic script is **strictly read-only**. It checks:

- Which of the 19 skills are present in each detected agent's `skills/` directory
- Whether `~/.config/gangtise/authorization.json` exists with mode 600
- Whether each skill's local credential file is a valid symlink pointing at the shared XDG file
- Whether the stored credentials pass a live authentication call (short probe that only needs `oauth/open/loginV2`)
- Whether the canonical RAG endpoint responds to a minimal query (scoped liveness check — proves the credential has `rag` scope, not just auth scope)

Exit codes:

- `0` — all healthy
- `1` — one or more issues need user action
- `2` — diagnostic itself failed (network error, no internet, etc.)

If diagnose reports issues, cross-reference the output against `references/known_issues.md`. Each reported issue maps to a specific remediation section.

## Capability 4: Skill registry — "which skill answers my data question?"

This is the non-obvious value of the wrapper. Gangtise's 19 skills form a **two-dimensional matrix** (data tier × operation type) that is not clearly documented. Use this table to route a user question to the right skill:

### Data-layer skills (6)

| Want to… | Upstream skill | Invoke |
|---|---|---|
| Query semantic content across knowledge base (reports + opinions + minutes) | gangtise-kb-client | `kb` runner with `-q` query + optional `--file-types` / `--securities` |
| List documents by type + date + security (reports, announcements, summaries, opinions, roadshows) | gangtise-file-client | dedicated runners per document type (report / opinion / summary / announcement / investment_calendar / foreign_report / internal_report / wechat_message) |
| Pull OHLC daily candles for an A-share or HK stock | gangtise-data-client | `quote` runner with `--securities {name}` + `-sd` / `-ed` date range |
| Pull financial statements (income / balance / cash flow indicators) | gangtise-data-client | `financial` runner with `--securities {name}` + `--indicators` |
| Pull valuation metrics (PE / PS / PB / PEG + historical percentiles) | gangtise-data-client | `valuation` runner with `--securities {name}` |
| Pull main business composition (by product / industry / region) | gangtise-data-client | `main_business` runner with `--securities {name}` + `--classify-method` |
| Pull shareholder / top-holder data | gangtise-data-client | `shareholder` runner with `--securities {name}` |
| Pull macro / industry indicators (GDP, CPI, vehicle sales, commodity prices) | gangtise-data-client | `industry_indicator` runner with `-k {keyword}` |
| Look up security standard codes by name | gangtise-data-client | `security` runner with `-k {name}` |
| List sector constituent stocks by theme or industry | gangtise-data-client | `block_component` runner with `-k {theme}` |
| List index members by category | gangtise-data-client | `index` runner with `-k {index type}` |
| Search the open web for public information not in Gangtise's internal KB | gangtise-web-client | `web` runner with `-q {query}` |

See [`references/skill_registry.md`](references/skill_registry.md) for the full per-runner parameter reference and cross-skill composition examples.

### Workflow-layer skills (10) — higher-order research workflows

These skills **orchestrate** the data-layer skills into end-to-end research workflows. They produce Markdown + HTML reports following Gangtise's professional investment-research templates and built-in compliance guardrails (no "买入 / 卖出 / 目标价 / 推荐" language).

| Want to… | Use |
|---|---|
| Generate a stock research report at L1-L4 depth (L1 = 1-page framework, L4 = full institutional coverage) | `gangtise-stock-research` |
| Do adversarial analysis on an investment thesis ("play devil's advocate for this long call") | `gangtise-opinion-pk` |
| Do thematic / sector research (driver analysis, enumeration phase, stock screening, performance check) | `gangtise-thematic-research` |
| Screen stocks based on research criteria | `gangtise-stock-selector` |
| Write an 800-1000 word event review / post-mortem for a market event | `gangtise-event-review` |
| Generate a company-meeting outline (3-step workflow: data → topics → questions) | `gangtise-interview-outline` |
| Track recent announcements for a stock pool and produce a daily digest | `gangtise-announcement-digest` |
| Summarize a chief analyst's recent opinions | `gangtise-opinion-summarizer` |
| Turn a WeChat chat-group discussion log into a structured investment daily | `gangtise-wechat-summary` |
| Get methodology guidance on how to design a custom data-processing workflow | `gangtise-data-processor` |

### Utility skills (3)

| Skill | Purpose |
|---|---|
| `gangtise-stockpool-client` | Create / rename / delete a stock pool; add or remove stocks from it. Only distributed inside `gangtise-skills-client.zip`. |
| `gangtise-file-client-no-download` | Variant of `file-client` that disables the download capability — useful in read-only environments or compliance-sensitive contexts. |
| Legacy `gangtise-data` / `gangtise-file` / `gangtise-kb` | The older minimal parallel line. `data` is v1.2.0 with strictly-typed security codes (no name resolution). Only install if the user wants the smaller feature footprint. |

See `references/skill_registry.md` for the full per-skill script catalog, versions, and capability matrix.

## What this skill refuses to do

- Vendor, fork, or mirror any `gangtise-*` skill's content into this directory — only the canonical OBS URLs are referenced.
- Pin an upstream skill version in SKILL.md — the installer always downloads the current OBS artifact.
- Silently patch upstream files — every modification path (if any are ever added) would require explicit consent via AskUserQuestion.
- Hardcode personal accessKey / secretAccessKey values.
- Make investment recommendations or trading decisions. Gangtise's own skills already enforce these compliance rules; this wrapper strictly delegates.

## File layout

```
gangtise-copilot/
├── SKILL.md                         # This file
├── scripts/
│   ├── install_gangtise.sh          # Download bundles → stage → distribute
│   ├── configure_auth.sh            # Set up + verify credentials
│   └── diagnose.sh                  # Read-only health report
├── references/
│   ├── installation_flow.md         # How the installer works, flag reference, troubleshooting
│   ├── credentials_setup.md         # accessKey / secretAccessKey, XDG paths, liveness check
│   ├── skill_registry.md            # Complete per-skill capability matrix
│   ├── known_issues.md              # Two parallel product lines, bundle-only skills, and other gotchas
│   └── best_practices.md            # How to combine stock-research + opinion-pk + data-client effectively
└── config-template/
    └── authorization.json.example   # Credential file template (placeholder values only)
```

