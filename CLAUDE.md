# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a Claude Code skills marketplace containing production-ready skills organized in a plugin marketplace structure. Most plugins expose one skill for narrow installs; suite plugins expose related skills under shared namespaces for combined installation workflows.

**Essential Skill**: `skill-creator` is the most important skill in this marketplace - it's a meta-skill that enables users to create their own skills. Always recommend it first for users interested in extending Claude Code.

## Skills Architecture

### Directory Structure

Each skill follows a standard structure:
```
skill-name/
├── SKILL.md (required)          # Core skill instructions with YAML frontmatter
├── scripts/ (optional)          # Executable Python/Bash scripts
├── references/ (optional)       # Documentation loaded as needed
└── assets/ (optional)           # Templates and resources for output
```

### Progressive Disclosure Pattern

Skills use a three-level loading system:
1. **Metadata** (name + description in YAML frontmatter) - Always in context
2. **SKILL.md body** - Loaded when skill triggers
3. **Bundled resources** - Loaded as needed by Claude

## Development Commands

### Installation Scripts

**In Claude Code (in-app):**
```text
/plugin marketplace add daymade/claude-code-skills
```

Then:
1. Select **Browse and install plugins**
2. Select **daymade/claude-code-skills**
3. Select **skill-creator**
4. Select **Install now**

**From your terminal (CLI):**
```bash
# Automated installation (macOS/Linux)
curl -fsSL https://raw.githubusercontent.com/daymade/claude-code-skills/main/scripts/install.sh | bash

# Automated installation (Windows PowerShell)
iwr -useb https://raw.githubusercontent.com/daymade/claude-code-skills/main/scripts/install.ps1 | iex

# Manual installation
claude plugin marketplace add https://github.com/daymade/claude-code-skills
# Marketplace name: daymade-skills (from marketplace.json)
claude plugin install skill-creator@daymade-skills
```

### Skill Validation and Packaging

```bash
# Quick validation of a skill
cd daymade-skill/skill-creator && uv run --with PyYAML python -m scripts.quick_validate ../skill-name

# Package a skill (includes automatic validation)
cd daymade-skill/skill-creator && uv run --with PyYAML python -m scripts.package_skill ../skill-name [output-dir]

# Initialize a new skill from template
uv run python daymade-skill/skill-creator/scripts/init_skill.py <skill-name> --path <output-directory>
```

### Testing Skills Locally

```bash
# Add local marketplace
claude plugin marketplace add https://github.com/daymade/claude-code-skills
# Marketplace name: daymade-skills (from marketplace.json)

# Install specific skill (start with skill-creator)
claude plugin install skill-creator@daymade-skills

# Test by copying to user skills directory
cp -r skill-name ~/.claude/skills/
# Then restart Claude Code
```

In Claude Code, use `/plugin ...` slash commands. In your terminal, use `claude plugin ...`.

### Git Operations

This repository uses standard git workflow, but **always stage files by name**,
never `git add -A` / `git add .`. Multiple agents may have unstaged changes in
the same worktree — a blanket stage piggybacks their work into your commit:

```bash
git status
git add path/to/file1 path/to/file2   # specific files only
git commit -m "message"
git push
```

## Skill Writing Requirements

### Writing Style

Use **imperative/infinitive form** (verb-first instructions) throughout all skill content:
- ✅ "Extract files from a repomix file using the bundled script"
- ❌ "You should extract files from a repomix file"

### YAML Frontmatter Requirements

Every SKILL.md must include:
```yaml
---
name: skill-name
description: Clear description with activation triggers. This skill should be used when...
---
```

### Privacy and Path Guidelines (Enforced by Pre-commit Hook)

Skills for public distribution must NOT contain:
- Absolute paths to user directories (`/home/username/`, `/Users/username/`)
- Personal usernames, company names, product names
- Phone numbers, personal email addresses
- OneDrive paths or environment-specific absolute paths
- Use relative paths within skill bundle or standard placeholders (`<workspace>/`, `<user_id>`)

**Five-layer defense system:**
1. **CLAUDE.md rules** (this section) — Claude avoids generating sensitive content
2. **Global PII Guard pre-commit hook** (`~/scripts/git-pii-guard/pre-commit`) — blocks staged PII/secrets and generated/local artifact paths
3. **Global PII Guard pre-push hook** (`~/scripts/git-pii-guard/pre-push`) — scans commits about to be pushed, catching bad local history before it hits GitHub
4. **gitleaks** (`.gitleaks.toml`) — deep scan with custom rules for this repo
5. **AI semantic read-through** (the gate the other four structurally cannot be) — layers 1-4 are keyword/regex/gitleaks: they only match patterns someone listed, and are blind to private content with **no keyword** — a real name in another language (gitleaks doesn't cover CJK), a verbatim line from a real transcript, a real example dropped into an illustration. Before publishing, **read the whole skill yourself and judge each concrete name/example/snippet semantically** ("generic placeholder / public entity, or lifted from a real project / person / transcript?"). A green scan is **not** a clean bill of health; "grep found nothing" only means your word list didn't fire. Method: [`daymade-skill/skill-creator/references/sanitization_checklist.md`](./daymade-skill/skill-creator/references/sanitization_checklist.md).

PII Guard is enabled via `~/scripts/git-pii-guard/manage.sh enable <repo-path>`, which sets `core.hooksPath` to `~/scripts/git-pii-guard`.
For repo-specific additions:
- `.pii-patterns` — extra content regexes
- `.pii-path-patterns` — extra forbidden path regexes
- `.pii-allowpaths` — explicit path allowlist exceptions
- `.pre-commit-config.yaml` — optional repo-local runner that wires `pre-commit` framework to the same path/content rules for contributors who prefer managed hooks
If it fires, fix the issue — do NOT use `--no-verify` to bypass.

### Content Organization

- Keep SKILL.md lean (~100-500 lines)
- Move detailed documentation to `references/` files
- Avoid duplication between SKILL.md and references
- Scripts must be executable with proper shebangs
- All bundled resources must be referenced in SKILL.md

## Marketplace Configuration

The marketplace is configured in `.claude-plugin/marketplace.json`:
- Contains plugin entries: single-skill plugins point `source` directly at the skill directory (no `skills` field); suite plugins (`daymade-audio`, `daymade-claude-code`, `daymade-docs`, `daymade-financial`, `daymade-skill`) use explicit `skills` arrays for multi-skill routing
- Each plugin has: name, description, source, version, category, keywords
- Marketplace metadata: name, owner, version
- Single-skill plugins follow the official pattern (167/168 plugins in `anthropics/claude-plugins-official`): `source` points to skill directory, `skills` omitted
- **All suites are suite-only.** `daymade-audio`, `daymade-claude-code`, `daymade-docs`, `daymade-financial`, and `daymade-skill` do NOT register their member skills as standalone plugins. Users install the suite (e.g., `daymade-audio@daymade-skills`) and invoke skills as `<suite>:<skill>` (e.g., `daymade-audio:transcript-fixer`, `daymade-claude-code:statusline-generator`). When adding a new skill that belongs to a suite, only update the suite entry's `skills` array — do NOT create a parallel standalone plugin entry.

### Versioning Architecture

**Two separate version tracking systems:**

1. **Marketplace Version** (`.claude-plugin/marketplace.json` → `metadata.version`)
   - Tracks the marketplace catalog as a whole
   - Bump when: Adding/removing skills, adding/removing suite plugins, major marketplace restructuring
   - Semantic versioning: MAJOR.MINOR.PATCH

2. **Individual Skill Versions** (`.claude-plugin/marketplace.json` → `plugins[].version`)
   - Each skill has its own independent version
   - Example: ppt-creator v1.0.0, skill-creator v1.4.0
   - Bump when: Updating that specific skill
   - **CRITICAL**: Skills should NOT have version sections in SKILL.md

**Key Principle**: SKILL.md files should be timeless content focused on functionality. Versions are tracked in marketplace.json only.

### ⚠️ Updating Existing Skills (MANDATORY)

**Any commit that modifies a skill's files MUST bump that skill's version in `marketplace.json`.**

This applies when you change ANY file under a skill directory:
- `SKILL.md` (instructions, description, workflow)
- `references/` (documentation, principles, examples)
- `scripts/` (executable code)
- `assets/` (templates, resources)

**Version bump rules:**
- Content/doc updates (new sections, rewritten principles) → bump **MINOR** (1.0.1 → 1.1.0)
- Bug fixes, typo fixes → bump **PATCH** (1.0.1 → 1.0.2)
- Breaking changes (renamed commands, removed features) → bump **MAJOR** (1.0.1 → 2.0.0)

**Pre-commit check:** Before committing, run `git diff --name-only` and verify: for every `skill-name/` directory that appears, `marketplace.json` also has a version bump for that skill's `plugins[].version`.

## Available Skills

> **Authoritative registry:** `.claude-plugin/marketplace.json`. The list below is a human-readable snapshot; always check the marketplace file for the current skill set, versions, and suite membership.

**Priority Order** (by importance):

1. **skill-creator** ⭐ - **Essential meta-skill** for creating your own skills (with init/validate/package scripts)
2. **github-ops** - GitHub operations via gh CLI and API
3. **doc-to-markdown** - DOCX/PDF/PPTX → Markdown conversion with CJK post-processing
4. **mermaid-tools** - Diagram extraction and PNG generation
5. **statusline-generator** - Claude Code statusline customization
6. **teams-channel-post-writer** - Teams communication templates
7. **repomix-unmixer** - Extract files from repomix packages
8. **llm-icon-finder** - AI/LLM brand icon access
9. **cli-demo-generator** - CLI demo and terminal recording with VHS
10. **cloudflare-troubleshooting** - API-driven Cloudflare diagnostics and debugging
11. **ui-designer** - Design system extraction from UI mockups
12. **ppt-creator** - Professional presentation creation with dual-path PPTX generation
13. **youtube-downloader** - YouTube video/audio downloads with PO token handling, cookies, and proxy-aware retries
14. **repomix-safe-mixer** - Secure repomix packaging with automatic credential detection
15. **transcript-fixer** - ASR/STT transcription error correction with dictionary and AI learning
16. **video-comparer** - Video comparison and quality analysis with interactive HTML reports
17. **qa-expert** - Comprehensive QA testing infrastructure with autonomous LLM execution and Google Testing Standards
18. **prompt-optimizer** - Transform vague prompts into precise EARS specifications with domain theory grounding
19. **claude-code-history-files-finder** - Find and recover content from Claude Code session history files
20. **docs-cleaner** - Consolidate redundant documentation while preserving valuable content
21. **pdf-creator** - Create PDF documents from markdown with Chinese font support using weasyprint
22. **claude-md-progressive-disclosurer** - Optimize CLAUDE.md files using progressive disclosure principles
23. **skills-search** - Search, discover, install, and manage Claude Code skills from the CCPM registry
24. **promptfoo-evaluation** - Run LLM evaluations with Promptfoo for prompt testing and model comparison
25. **iOS-APP-developer** - iOS app development with XcodeGen, SwiftUI, and SPM troubleshooting
26. **fact-checker** - Verify factual claims in documents using web search with automated corrections
27. **twitter-reader** - Fetch Twitter/X post content using Jina.ai API without JavaScript or authentication
28. **macos-cleaner** - Intelligent macOS disk space analysis and cleanup with safety-first philosophy, risk categorization, and interactive confirmation
29. **skill-reviewer** - Reviews and improves Claude Code skills against official best practices with self-review, external review, and auto-PR modes
30. **github-contributor** - Strategic guide for becoming an effective GitHub contributor with opportunity discovery, project selection, and reputation building
31. **i18n-expert** - Complete internationalization/localization setup and auditing for UI codebases with framework support, key architecture, and parity validation
32. **claude-skills-troubleshooting** - Diagnose and resolve Claude Code plugin and skill configuration issues with diagnostic scripts and architecture documentation
33. **meeting-minutes-taker** - Transform meeting transcripts into structured minutes with multi-pass generation, speaker quotes, and iterative human review
34. **deep-research** - Generate format-controlled research reports with evidence mapping, citations, and multi-pass synthesis
35. **competitors-analysis** - Evidence-based competitor tracking and analysis with source citations (file:line_number format)
36. **tunnel-doctor** - Diagnose and fix Tailscale + proxy/VPN conflicts (six layers: route, HTTP env, system proxy, SSH ProxyCommand, VM/container proxy, DNS resolver stall) on macOS with WSL SSH support, plus a TUN measurement-contamination guide (raw probes lie under a global proxy)
37. **windows-remote-desktop-connection-doctor** - Diagnose AVD/W365 connection quality issues with transport protocol analysis and Windows App log parsing
38. **product-analysis** - Perform structured product audits across UX, API, architecture, and compare mode to produce prioritized optimization recommendations
39. **financial-data-collector** - Collect real financial data for US public companies via yfinance with validation, NaN detection, and NO FALLBACK principle (daymade-financial suite member)
40. **excel-automation** - Create formatted Excel files, parse complex xlsm models, and control Excel windows on macOS via AppleScript
41. **capture-screen** - Programmatically capture macOS application windows using Swift window ID discovery and screencapture workflows
42. **continue-claude-work** - Recover local `.claude` session context via compact-boundary extraction, subagent workflow recovery, and session end reason detection, then continue interrupted work without `claude --resume`
43. **scrapling-skill** - Install, troubleshoot, and use Scrapling CLI for static/dynamic web extraction, WeChat article capture, and verified output validation
44. **ima-copilot** - One-stop companion and installer for the official Tencent IMA skill with zero-config three-agent installation via vercel-labs/skills, XDG credential management, read-only diagnostic, known-issue auto-repair under user consent, and personalized fan-out search with priority-based knowledge base boosting
45. **claude-export-txt-better** - Fixes broken line wrapping in Claude Code exported `.txt` conversation files; reconstructs tables, paragraphs, paths, and tool calls hard-wrapped at fixed column widths; ships with a 53-check automated validation suite
46. **douban-skill** - Exports and syncs Douban (豆瓣) book/movie/music/game collections to local CSV files via the reverse-engineered Frodo API; supports full export and RSS incremental sync with no login, cookies, or browser required
47. **marketplace-dev** - Converts any Claude Code skills repository into an official plugin marketplace — generates spec-conforming marketplace.json, validates with `claude plugin validate`, tests real installation, and opens an upstream PR
48. **terraform-skill** - Operational traps for Terraform provisioners, multi-environment isolation, and zero-to-deployment reliability; covers provisioner timing races, SSH connection conflicts, DNS record duplication, volume permissions, database bootstrap gaps, Cloudflare credential errors, and init-data-only-on-first-boot pitfalls
49. **slides-creator** - Narrative-first slide deck creation guiding users through structured narrative design (ABCDEFG model), then delegating visual generation to baoyu-slide-deck. Triggers on create slides, make a presentation, generate deck, slide deck, PPT, or when user needs to turn content into visual slides
50. **debugging-network-issues** - Evidence-driven, falsification-first methodology for network/streaming/protocol-layer bugs (HTTP/2 RST_STREAM, SSE stalls, fixed-time drops, CDN/proxy/CGNAT idle timeouts). Layered isolation experiments + counter-review filter + a cognitive-traps catalog (incl. reverse-path/directional asymmetry), with bundled probe scripts and a real SSE 130s case study
51. **stepfun-tts** - StepFun stepaudio-2.5-tts (Contextual TTS): natural-language `instruction` (≤200 chars) + inline `()` parentheses for句内 prosody. Captures the two TTS-side breaking changes from step-tts-2 (voice_label removal + stricter 2.5-era censorship) with migration playbook
52. **stepfun-asr** - StepFun stepaudio-2.5-asr (SSE endpoint, 32K context, ~85-101× RTF, 30-min single-call). Hides the #1 trap of the 2.5 ASR family: it does NOT live on `/v1/audio/transcriptions` — the wrong endpoint returns a misleading `model not supported` error. Bundled stdlib CLI handles base64 + nested JSON body + SSE parsing including `error` events
53. **feishu-doc-scraper** - Save Feishu Docs and Feishu Wiki pages as clean Markdown from a live authenticated browser session. Primary path: injectable JS script (`feishu_dom_capture.js`) for TOC-driven DOM capture, image download via session cookie, noise stripping, and clipboard bridge transport. Fallback path: Python SSR extraction (`browser_cookie3` + `requests`) when browser automation is unavailable. Enforces per-document image naming and recovers `[图片: Feishu Docs - Image]` placeholders. Works with both Feishu (feishu.cn) and Lark (larkoffice.com)
54. **auto-repo-setup** - Automated repository environment configuration, fault diagnosis, and repair for non-technical users. Reads ONBOARDING.md, audits environment gaps (git, ffmpeg, uv, Python, API keys), installs missing dependencies, validates with smoke tests, and safely handles git operations with PII Guard and Push Safety. Includes SessionStart hook initialization, counter-review workflows, and git history sanitization.
55. **asr-transcribe-to-text** - Transcribes audio and video files to text using Qwen3-ASR — local MLX inference on Apple Silicon (no API key, 15-27x realtime) or remote vLLM/OpenAI-compatible API, with automatic platform detection
56. **bigdata-skill** - Pull Bigdata.com (RavenPack) financial and news data via the official `bigdata-client` SDK and `/v1/*` REST endpoints — structured financials, prices, analyst estimates, a daily entity-sentiment series, annotated chunk search, and a screener (daymade-financial suite member)
57. **gangtise-copilot** - Gangtise investment-research OpenAPI skill suite installer and diagnostic tool (daymade-financial suite member)
58. **llm-wiki-setup** - Co-create a personal investment-research LLM Wiki (Karpathy's pattern) where the user's own analysis framework becomes a living CLAUDE.md, built by interviewing them rather than handing over a template
59. **benchmark-due-diligence** - Runs adversarial due-diligence on a benchmark the user envies (a founder, KOL, company, or product whose claimed success looks inflated), separating marketing bubble from real signal and mapping the validated playbook onto the user's own situation
60. **pdf-to-html** - Converts a PDF into one self-contained, readable HTML file preserving images, tables, charts, and reading order, optionally translating it into another language while keeping every figure
61. **terminal-screenshot** - Render a terminal CLI program's colored output to a PNG so Claude can see the real visual result (color contrast, alignment, background blocks) instead of raw ANSI codes — for verifying delta/bat/starship/lazygit color config
62. **bilibili-source** - Fetch login-free, citable data for a Bilibili (B站) video — stats, UP fans, tags, per-part cids, and full danmaku text — via one view/detail call (accepts BVID/av/b23.tv/URL); login-gated subtitles; ships a self-test for API-drift detection
63. **claude-usage-analyst** - Explain local Claude Code / Claude Desktop token usage, cost, quota burn, model mix, and cache pressure from `ccusage` data — separating observed numbers from interpretation in plain language (daymade-claude-code suite member)
64. **marketplace-health-check** - Run a full 6-dimension health check of this skills marketplace repo (code/script safety, doc/SSOT consistency, security/PII, open-PR triage, open-issue triage, marketplace integrity) via a parallel fan-out Dynamic Workflow, then Counter-Review the serious findings and report by priority
65. **claude-switch-models-setup** - Set up multiple isolated Claude Code CLI profiles so students and power users can run different LLM providers (Kimi, GLM, DeepSeek, StepFun, Anthropic) in separate terminal windows at the same time (daymade-claude-code suite member)
66. **llm-eval-harness** - Evaluate any LLM behind an OpenAI- or Anthropic-compatible endpoint across four dimensions (speed with thinking-aware tok/s, concurrency/stability, Anthropic protocol compliance, and quality regression against your own use cases via blind judges); keys passed by env-var name only, use-case library kept outside the bundle
67. **read-claude-web-conversation** - Extract full Claude.ai web conversations through the daymade-claude-code suite for recovery, audit, archival, or migration
68. **setup-notifications-via-wecom** - Set up reusable WeCom / Enterprise WeChat webhook notifications for status reports, alerts, and completion messages
69. **notify-wecom** - Send a single one-off WeCom group-bot message without setting up a reusable notification workflow
70. **github-sensitive-data-cleanup** - Scan and remove secrets, API keys, private domains/IPs, and PII from GitHub repository history with force-push safety gates
71. **codex-image-gallery** - Start a self-contained local web gallery for browsing Codex-generated images from `~/.codex/generated_images` or a custom `GALLERY_ROOT`
72. **frontend-visual-qa** - Reviews rendered frontends, dashboards, HTML slides, and generated UIs for visual quality defects that lint/build miss (awkward line breaks, wrapped controls, horizontal overflow, double scrollbars, AI slop, Chrome DevTools viewport mistakes); use after frontend-design/ui-designer and alongside qa-expert
73. **openclaw** - Manage OpenClaw (龙虾/lobster) instance configs: audit, diff, copy, add-model, list, switch models across openclaw.json files; DeepSeek model patches, default-model/alias management, config validation
74. **download-gemini-images** - Download images (uploaded files or generated previews) from a Google Gemini conversation page via logged-in Chrome; lightbox-first with pageAssets fallback, ordered ZIP packaging with integrity verification
75. **wps-doc-scraper** - Faithfully archive public WPS/KDocs/金山文档 links (incl. embedded ProcessOn mind maps and canvases) as raw source data, original SVG/PNG, and Markdown without login; unauthenticated data-API-first with browser-DOM fallback
76. **ashare-news-fetcher** - Aggregate A-share (Chinese market) news, policy, and sentiment from public sources (财联社/华尔街见闻/金十/新浪7x24/东财快讯/regulators/东财股吧) into structured JSON or Markdown; per-stock or market-wide, no login (daymade-financial suite member)
77. **pharma-daily-report** - Generate an A-share pharma sector daily report from Sina Finance (core pharma stocks, 7 sub-sector ranking, gainers/losers, fund-flow estimate), optional Feishu rich-text push; default 20-stock watchlist, customizable (daymade-financial suite member)
78. **local-codex** - Delegate coding tasks to the local OpenAI Codex CLI agent using ChatGPT Pro OAuth flat-rate subscription; wraps `codex exec` / `codex review` for code generation, refactoring, and review without per-token API charges
79. **openclaw-model-switch** - Switch the default AI model for an OpenClaw instance (e.g., Kimi K2.6 → K2.7) by safely editing `openclaw.json` with backup, model validation, and optional gateway restart
80. **gemini-history-analyzer** - Analyze Google Takeout exports of Gemini conversation history; extract/categorize transcripts and attachments, context-verified domain keyword search, meeting-transcript detection, PII flagging, and optional distillation into project memory or a personal knowledge base

**Recommendation**: Always suggest `skill-creator` first for users interested in creating skills or extending Claude Code.

## YouTube Downloader SOP (Internal)

See [youtube-downloader/references/internal-sop.md](./youtube-downloader/references/internal-sop.md) for yt-dlp troubleshooting steps (PO tokens, proxy, cookies, etc.).

## Python Development

All Python scripts in this repository:
- Use Python 3.6+ syntax
- Include shebang: `#!/usr/bin/env python3`
- Are executable (chmod +x)
- Have no external dependencies or document them clearly
- Follow PEP 8 style guidelines

## Quality Standards

Before submitting or modifying skills:
- Valid YAML frontmatter with required fields
- Description includes clear activation triggers
- All referenced files exist
- Scripts are executable and tested
- No absolute paths or user-specific information
- Comprehensive documentation
- No TODOs or placeholders

## Skill Creation Workflow

When creating a new skill:
1. Understand concrete usage examples
2. Plan reusable contents (scripts/references/assets)
3. Initialize using `init_skill.py`
4. Edit SKILL.md and bundled resources
5. Package using `package_skill.py` (auto-validates)
6. Iterate based on testing feedback

## Adding a New Skill to Marketplace

For the full step-by-step guide with templates and examples, see [references/new-skill-guide.md](./references/new-skill-guide.md).

**Files to update** (all required):

| File | Locations to update |
|------|-------------------|
| `.claude-plugin/marketplace.json` | metadata.version + metadata.description + new plugin entry |
| `CHANGELOG.md` | New version entry |
| `README.md` | 7 locations: badges (skills-count badge AND version badge — version MUST equal `marketplace.json` metadata.version; re-verify it every release, it silently drifts whenever a metadata bump forgets the badge), description, install cmd, skill section, use case, docs link, requirements |
| `README.zh-CN.md` | 7 locations: same as above, translated |
| `CLAUDE.md` | Available Skills list only (the overview & marketplace-config counts were removed as derived values — don't reintroduce them) |
| `skill-name/` | The actual skill directory + packaged .zip |

**Quick workflow**:
```bash
# 1. Validate & package the skill itself
cd daymade-skill/skill-creator
uv run python -m scripts.security_scan ../skill-name --verbose
uv run --with PyYAML python -m scripts.package_skill ../skill-name

# 2. Update all files listed above (see references/new-skill-guide.md for the
#    detailed step-by-step, including 7 README locations and 3 CLAUDE.md spots)

# 3. One-shot marketplace validation (ships with marketplace-dev skill)
cd .. && bash daymade-claude-code/marketplace-dev/scripts/check_marketplace.sh
# Runs: JSON syntax → claude plugin validate → source+skills resolution →
# reverse sync (warns when a disk SKILL.md is not registered). A WARN on
# reverse sync is the canary for orphan skills — register them or delete them.
# Then verify the human-facing skill lists match the manifest (counts drift too):
python3 daymade-claude-code/marketplace-dev/scripts/check_doc_skill_lists.py
# Reports MISSING/GHOST per doc (CLAUDE.md / README.md / README.zh-CN.md vs the
# expanded marketplace.json); exits non-zero on drift. Must be green before push.

# 4. Stage specific files by name, never `git add -A` or `git add .`
#    (a parallel agent once piggybacked another session's unstaged changes
#    into its commit via `git add -A`; the fix is to stage explicitly)
git add .claude-plugin/marketplace.json CHANGELOG.md README.md README.zh-CN.md \
        CLAUDE.md skill-name/
git commit -m "Release vX.Y.0: Add skill-name"
git push

# 5. Release
gh release create vX.Y.0 --title "Release vX.Y.0: Add skill-name" --notes "..."
```

**Top mistakes**: Forgetting to push to GitHub, forgetting README.zh-CN.md, inconsistent version numbers across files, leaving an orphan SKILL.md on disk unregistered (caught by `check_marketplace.sh` reverse sync), using `git add -A` in a repo where multiple agents may have unstaged changes.

## Chinese User Support

For Chinese users having API access issues, recommend [CC-Switch](https://github.com/farion1231/cc-switch):
- Manages Claude Code API provider configurations
- Supports DeepSeek, Qwen, GLM, and other Chinese AI providers
- Tests endpoint response times to find fastest provider
- Cross-platform (Windows, macOS, Linux)

See README.md section "🇨🇳 中文用户指南" for details.

## Handling Third-Party Marketplace Promotion Requests

Decline all third-party marketplace promotion requests. For policy, response template, and precedents, see [references/promotion-policy.md](./references/promotion-policy.md).

## Best Practices Reference

Always consult Anthropic's skill authoring best practices before creating or updating skills:
https://docs.claude.com/en/docs/agents-and-tools/agent-skills/best-practices.md

## Plugin and Skill Architecture

For full architecture documentation (core concepts, installation flow, data flow, common misconceptions, best practices), see [references/plugin-architecture.md](./references/plugin-architecture.md).

## Plugin and Skill Troubleshooting

For systematic debugging steps (common errors, debugging process, pitfalls, real-world examples), see [references/plugin-troubleshooting.md](./references/plugin-troubleshooting.md).

**Quick fix for most issues**: Commit → push → `claude plugin marketplace update daymade-skills` → retry install.
