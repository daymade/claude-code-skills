# Claude Code Skills Marketplace

<div align="center">

[![English](https://img.shields.io/badge/Language-English-blue)](./README.md)
[![简体中文](https://img.shields.io/badge/语言-简体中文-red)](./README.zh-CN.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-2.0.13+-purple.svg)](https://claude.com/code)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](./CONTRIBUTING.md)
[![Maintenance](https://img.shields.io/badge/Maintained%3F-yes-green.svg)](https://github.com/daymade/claude-code-skills/graphs/commit-activity)

</div>

Professional Claude Code skills marketplace featuring production-ready skills for enhanced development workflows.

## 📑 Table of Contents

- [🌟 Essential Skill: skill-creator](#-essential-skill-skill-creator)
- [🚀 Quick Installation](#-quick-installation)
- [🇨🇳 Chinese User Guide](#-chinese-user-guide)
- [📦 Other Available Skills](#-other-available-skills)
- [🎬 Interactive Demo Gallery](#-interactive-demo-gallery)
- [🎯 Use Cases](#-use-cases)
- [📚 Documentation](#-documentation)
- [🛠️ Requirements](#️-requirements)
- [❓ FAQ](#-faq)
- [🤝 Contributing](#-contributing)
- [📄 License](#-license)

---

## 🌟 Essential Skill: skill-creator

**⭐ Start here if you want to create your own skills!**

The `skill-creator` is the **meta-skill** that enables you to build, validate, and package your own Claude Code skills. It's the most important tool in this marketplace because it empowers you to extend Claude Code with your own specialized workflows.

### Why This skill-creator?

This is a **production-hardened fork** of [Anthropic's official skill-creator](https://github.com/anthropics/skills/tree/main/skills/skill-creator), born from building real skills and hitting every wall the official version doesn't warn you about.

**The official skill-creator tells you _what_ to build. Ours also tells you _what not to try_ — and why.**

| You're trying to... | Official | This Fork |
|---------------------|----------|-----------|
| Research before building | "Check available MCPs" | Ordered search protocol with decision matrix: Adopt / Extend / Build |
| Create a skill interactively | Prose-based instructions | Structured AskUserQuestion checkpoints — user never loses context |
| Avoid common mistakes | No guidance | Cache edit warnings, prerequisite checks, security scan gate |
| Know the architecture options | Not mentioned | Inline vs Fork decision guide with examples (choosing wrong silently breaks your skill) |
| Validate before shipping | Basic YAML check | Expanded structural validator plus provenance-checked old-vs-new capability audit; packaging re-verifies the completed review instead of trusting a marker |
| Match validation cost to risk | One full create-test-review loop | Risk tier and evaluation spend are separate: targeted checks first; paired benchmarks require explicit authorization or a decision-bearing evidence plan plus opt-in |
| Catch security issues | No tooling | `security_scan.py` with gitleaks integration — hard gate before packaging |
| Learn from real failures | No failure cases | Battle-tested methodology with documented failure patterns and gotchas |
| Distill past conversations safely | Not covered | Explicit local manifest, message-level time window, redaction, opaque source IDs, ignored `.enrich/` staging, and manual promotion into references/scripts |
| Turn approved artifacts into skill behavior | Not covered | Artifact-corpus distillation workflow: script-measured pattern extraction (≥3-artifact threshold), cataloging≠distillation gate, invariant-vs-register boundary, independent completeness audit |
| Survive concurrent sessions on one skill repo | Not covered | git-ref baselines, re-read-before-write, HEAD check before commit, own-paths-only staging, one-bump-per-outcome versioning |
| Ground knowledge skills in evidence | General advice | Authority ladder from real calls and machine-readable specs through production code, plus executable-example smoke checks and evidence-boundary rules |
| Have both installed at once | Coin flip — the two descriptions are near-identical | Detects the clash on trigger and offers a one-command, reversible SessionStart routing hook (only ever installed when both coexist); the official plugin stays usable by explicit request |
| Your own skill collides with an installed plugin | Not covered | `generate_supersede_kit.py` stamps the same conditional routing kit into your skill, plus a measured precedence decision guide (rename → description tiebreaker → hook → disable) |

> Full methodology: [skill-creator/references/skill-development-methodology.md](./daymade-skill/skill-creator/references/skill-development-methodology.md)

### Quick Install

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
claude plugin marketplace add https://github.com/daymade/claude-code-skills
# Marketplace name: daymade-skills (from marketplace.json)
claude plugin install daymade-skill@daymade-skills
```

### What You Can Do

After installing skill-creator, simply ask Claude Code:

```
"Create a new skill called my-awesome-skill in ~/my-skills"

"Validate my skill at ~/my-skills/my-awesome-skill"

"Package my skill at ~/my-skills/my-awesome-skill for distribution"
```

Claude Code, with skill-creator loaded, will guide you through the entire skill creation process - from understanding your requirements to packaging the final skill.

📚 **Full documentation**: [daymade-skill/skill-creator/SKILL.md](./daymade-skill/skill-creator/SKILL.md)

### Live Demos

**📝 Initialize New Skill**

![Initialize Skill Demo](./demos/skill-creator/init-skill.gif)

**✅ Validate Skill Structure**

![Validate Skill Demo](./demos/skill-creator/validate-skill.gif)

**📦 Package Skill for Distribution**

![Package Skill Demo](./demos/skill-creator/package-skill.gif)

---

## 🚀 Quick Installation

### Install Inside Claude Code (In-App)

```text
/plugin marketplace add daymade/claude-code-skills
```

Then:
1. Select **Browse and install plugins**
2. Select **daymade/claude-code-skills**
3. Select the plugin you want
4. Select **Install now**

### Automated Installation (Recommended)

**macOS/Linux:**
```bash
curl -fsSL https://raw.githubusercontent.com/daymade/claude-code-skills/main/scripts/install.sh | bash
```

**Windows (PowerShell):**
```powershell
iwr -useb https://raw.githubusercontent.com/daymade/claude-code-skills/main/scripts/install.ps1 | iex
```

### Manual Installation

Add the marketplace:
```bash
claude plugin marketplace add https://github.com/daymade/claude-code-skills
```

Marketplace name is `daymade-skills` (from marketplace.json). Use `@daymade-skills` when installing plugins.
Do not use the repo path as a marketplace name (e.g. `@daymade/claude-code-skills` will fail).
In Claude Code, use `/plugin ...` slash commands. In your terminal, use `claude plugin ...`.

**Essential Skill** (recommended first install):
```bash
# skill-creator ships inside the daymade-skill suite
claude plugin install daymade-skill@daymade-skills
```

**Documentation Suite** (shared namespace for document workflows):
```bash
claude plugin install daymade-docs@daymade-skills
```

This suite exposes related skills under one namespace, including:

```text
/daymade-docs:doc-to-markdown
/daymade-docs:mermaid-tools
/daymade-docs:pdf-creator
/daymade-docs:ppt-creator
/daymade-docs:docs-cleaner
/daymade-docs:excel-automation
/daymade-docs:read-docx-review
```

These skills ship as a bundle — there are no separate single-skill plugins. All documentation skills live under `daymade-docs/` and install together from the suite.

**Apple Platform Suite** (shared namespace for macOS and iOS development/operations):
```bash
claude plugin install daymade-macos@daymade-skills
```

```text
/daymade-macos:capture-screen
/daymade-macos:developing-ios-apps
/daymade-macos:macos-cleaner
/daymade-macos:macos-watchdog
```

These skills are bundle-only under `daymade-macos`.

**Codex Suite** (shared namespace for Codex workstation setup, assisted coding, and visual exploration):
```bash
claude plugin install daymade-codex@daymade-skills
```

Codex CLI and Desktop users can install the same suite through Codex's plugin
marketplace:

```bash
codex plugin marketplace add daymade/claude-code-skills
codex plugin add daymade-codex@daymade-skills
```

```text
/daymade-codex:codex-image-gallery
/daymade-codex:local-codex
/daymade-codex:design-style-picker
/daymade-codex:interaction-design-board
/daymade-codex:codex-1m-context-window-setup
```

These skills are bundle-only under `daymade-codex`.

**Claude Code Operations Suite** (shared namespace for Claude Code power-user workflows):
```bash
claude plugin install daymade-claude-code@daymade-skills
```

This suite bundles the skills that extend Claude Code itself — cross-project prior-work retrieval across code, docs, Skills, meetings, WeChat archives, and conversation history; fast local conversation discovery across Claude Code and Codex; session recovery; CLAUDE.md tuning; version-synced Lark CLI routing; troubleshooting; statusline configuration; export repair; marketplace development and suite consolidation; terminal screenshot rendering; usage analysis; and multi-provider model switching:

```text
/daymade-claude-code:local-conversation-history
/daymade-claude-code:read-claude-code-history
/daymade-claude-code:read-codex-history
/daymade-claude-code:continue-claude-code-work
/daymade-claude-code:continue-codex-work
/daymade-claude-code:claude-skills-troubleshooting
/daymade-claude-code:claude-md-progressive-disclosurer
/daymade-claude-code:statusline-generator
/daymade-claude-code:claude-export-txt-better
/daymade-claude-code:marketplace-dev
/daymade-claude-code:terminal-screenshot
/daymade-claude-code:claude-usage-analyst
/daymade-claude-code:claude-switch-models-setup
/daymade-claude-code:read-claude-web-conversation
/daymade-claude-code:claude-migrate-memory-to-doc
/daymade-claude-code:claude-code-hooks
/daymade-claude-code:prior-work-retrieval
/daymade-claude-code:lark-cli-router
/daymade-claude-code:claude-code-ping-start-5h-quota
```

Installed names render as `daymade-claude-code:<skill>` under a single shared namespace. These skills are bundle-only — install the suite to get all members.

**Financial Data Suite** (shared namespace for investment-research and financial data workflows):
```bash
claude plugin install daymade-financial@daymade-skills
```

This suite bundles the skills that fetch and analyze financial data — Bigdata.com (RavenPack) structured financials and sentiment, US equity fundamentals via yfinance, Gangtise (岗底斯) OpenAPI research suite orchestration, A-share news and policy aggregation, A-share pharmaceutical sector daily reporting, structured devil's-advocate pressure-testing of investment theses, and adversarial due diligence on inflated benchmark claims:

```text
/daymade-financial:bigdata-skill
/daymade-financial:financial-data-collector
/daymade-financial:gangtise-copilot
/daymade-financial:ashare-news-fetcher
/daymade-financial:daymade-sector-research
/daymade-financial:pharma-daily-report
/daymade-financial:devils-advocate
/daymade-financial:benchmark-due-diligence
```

Installed names render as `daymade-financial:<skill>` under a single shared namespace. These skills are bundle-only — install the suite to get all members.

**Install Other Skills:**
```bash
# GitHub operations
claude plugin install github-ops@daymade-skills

# Teams communication
claude plugin install teams-channel-post-writer@daymade-skills

# Local Claude/Codex agent messaging
claude plugin install peer-message@daymade-skills

# Repomix extraction
claude plugin install repomix-unmixer@daymade-skills

# AI/LLM icons
claude plugin install llm-icon-finder@daymade-skills

# CLI demo generation
claude plugin install cli-demo-generator@daymade-skills

# Cloudflare diagnostics
claude plugin install cloudflare-troubleshooting@daymade-skills

# UI design system extraction
claude plugin install ui-designer@daymade-skills

# YouTube video/audio downloading
claude plugin install youtube-downloader@daymade-skills

# Secure repomix packaging
claude plugin install repomix-safe-mixer@daymade-skills

# Full audio suite (ASR + transcript correction + meeting minutes + TTS)
claude plugin install daymade-audio@daymade-skills

# Video comparison and quality analysis
claude plugin install video-comparer@daymade-skills

# QA testing infrastructure with autonomous execution
claude plugin install qa-expert@daymade-skills

# Prompt optimization using EARS methodology
claude plugin install prompt-optimizer@daymade-skills

# CCPM skill registry search and management
claude plugin install daymade-skill@daymade-skills

# Promptfoo LLM evaluation framework
claude plugin install promptfoo-evaluation@daymade-skills

# Twitter/X content fetching
claude plugin install twitter-reader@daymade-skills

# Skill quality review and improvement
claude plugin install daymade-skill@daymade-skills

# GitHub contribution strategy
claude plugin install github-contributor@daymade-skills

# Windows Remote Desktop / AVD connection diagnosis
claude plugin install windows-remote-desktop-connection-doctor@daymade-skills

# Product analysis and optimization
claude plugin install product-analysis@daymade-skills

# Scrapling CLI extraction and troubleshooting
claude plugin install scrapling-skill@daymade-skills

# Tencent IMA knowledge base companion and installer
claude plugin install ima-copilot@daymade-skills

# Export Douban (豆瓣) book/movie/music/game collections to CSV
claude plugin install douban-skill@daymade-skills

# Terraform operational traps and multi-environment reliability patterns
claude plugin install terraform-skill@daymade-skills

# Evaluate any LLM endpoint across speed, concurrency, protocol, and quality
claude plugin install llm-eval-harness@daymade-skills
```

Standalone plugins can be installed independently; suite members install together with their suite.

---

## 🇨🇳 Chinese User Guide

**For Chinese users:** We highly recommend using [CC-Switch](https://github.com/farion1231/cc-switch) to manage Claude Code API provider configurations.

CC-Switch enables you to:
- ✅ Quickly switch between different API providers (DeepSeek, Qwen, GLM, etc.)
- ✅ Test endpoint response times to find the fastest provider
- ✅ Manage MCP server configurations
- ✅ Auto-backup and import/export settings
- ✅ Cross-platform support (Windows, macOS, Linux)

**Setup:** Download from [Releases](https://github.com/farion1231/cc-switch/releases), install, add your API configs, and switch via UI or system tray.

### Complete Chinese Documentation

For full documentation in Chinese, see [README.zh-CN.md](./README.zh-CN.md).

---

## 📦 Other Available Skills

### **github-ops** - GitHub Operations Suite

GitHub operations through gh CLI and GitHub APIs, with explicit targets, impact previews, and
independent state verification.

**When to use:**
- Creating, viewing, or managing pull requests
- Managing issues and repository settings
- Managing collaborators, teams, organization permissions, and 2FA enforcement
- Querying GitHub API endpoints
- Working with GitHub Actions workflows
- Automating GitHub operations

**Key features:**
- Verified mutation workflow for PRs, issues, repositories, and Actions
- Parallel and superseded PR convergence
- Organization access, member privileges, and 2FA preflight
- REST, GraphQL, and documented UI-path selection
- Enterprise GitHub support

**🎬 Live Demo**

![GitHub Ops Demo](./demos/github-ops/create-pr.gif)

---

### **doc-to-markdown** - Document Conversion Suite

> **Install**: `claude plugin install daymade-docs@daymade-skills` (suite-only — invoked as `daymade-docs:doc-to-markdown`)

Converts documents to markdown with Windows/WSL path handling and PDF image extraction.

**When to use:**
- Converting .doc/.docx/PDF/PPTX to markdown
- Extracting images from PDF files
- Processing Confluence exports
- Handling Windows/WSL path conversions

**Key features:**
- Multi-format document conversion
- PDF image extraction using PyMuPDF
- Windows/WSL path automation
- Confluence export processing
- Helper scripts for path conversion and image extraction

**🎬 Live Demo**

![Markdown Tools Demo](./demos/doc-to-markdown/convert-docs.gif)

---

### **mermaid-tools** - Diagram Generation

> **Install**: `claude plugin install daymade-docs@daymade-skills` (suite-only — invoked as `daymade-docs:mermaid-tools`)

Extracts Mermaid diagrams from markdown and generates high-quality PNG images.

**When to use:**
- Converting Mermaid diagrams to PNG
- Extracting diagrams from markdown files
- Processing documentation with embedded diagrams
- Creating presentation-ready visuals

**Key features:**
- Automatic diagram extraction
- High-resolution PNG generation
- Smart sizing based on diagram type
- Customizable dimensions and scaling
- WSL2 Chrome/Puppeteer support

**🎬 Live Demo**

![Mermaid Tools Demo](./demos/mermaid-tools/extract-diagrams.gif)

---

### **statusline-generator** - Statusline Customization

> **Install**: `claude plugin install daymade-claude-code@daymade-skills` (suite-only — invoked as `daymade-claude-code:statusline-generator`)

Configures Claude Code statuslines with multi-line layouts and cost tracking.

**When to use:**
- Customizing Claude Code statusline
- Adding cost tracking (session/daily)
- Displaying git status
- Multi-line layouts for narrow screens
- Color customization

**Key features:**
- Multi-line statusline layouts
- ccusage cost integration
- Git branch status indicators
- Customizable colors
- Portrait screen optimization

**🎬 Live Demo**

![Statusline Generator Demo](./demos/statusline-generator/customize-statusline.gif)

---

### **teams-channel-post-writer** - Teams Communication

Creates educational Teams channel posts for internal knowledge sharing.

**When to use:**
- Writing Teams posts about features
- Sharing Claude Code best practices
- Documenting lessons learned
- Creating internal announcements
- Teaching effective prompting patterns

**Key features:**
- Post templates with proven structure
- Writing guidelines for quality content
- "Normal vs Better" example patterns
- Emphasis on underlying principles
- Ready-to-use markdown templates

**🎬 Live Demo**

![Teams Channel Post Writer Demo](./demos/teams-channel-post-writer/write-post.gif)

---

### **peer-message** - Local Claude/Codex Agent Communication

> **Install**: `claude plugin install peer-message@daymade-skills`

Discovers, messages, broadcasts to, and independently verifies local Claude Code sessions and Codex threads through each product's own transport.

**When to use:**
- Asking one terminal's Claude or Codex agent to coordinate with another
- Sending a dependency, pause, handoff, or completion notice across sessions
- Reaching a Claude inbox from a third-party profile or Codex process
- Unblocking messages held for per-message manual approval on an unattended endpoint (`crossSessionInbound`)
- An inbound peer message asserting facts about your session or shared state, or asking you to pause/release — verify the premise against its own authority before acting
- Broadcasting one explicit coordination message to a reviewed target list

📚 **Documentation and commands**: [peer-message/SKILL.md](./peer-message/SKILL.md) owns routing, stable runtime prerequisites, and the peer-cannot-authorize boundary; `peer-message/scripts/peer.py --help` owns CLI syntax; [protocol-and-discovery.md](./peer-message/references/protocol-and-discovery.md) owns addressing, envelopes, and delivery evidence; [official-feature.md](./peer-message/references/official-feature.md) owns volatile product-specific requirements and mechanics; [coordination-and-learning-loop.md](./peer-message/references/coordination-and-learning-loop.md) owns reply addressing, payload and delivery-status language, what an inbound peer assertion and a set of peer denials are each worth, and the evidence-gated improvement loop.

---

### **repomix-unmixer** - Repository Extraction

Extracts files from repomix-packed repositories and restores directory structures.

**When to use:**
- Unmixing repomix output files
- Extracting packed repositories
- Restoring file structures
- Reviewing repomix content
- Converting repomix to usable files

**Key features:**
- Multi-format support (XML, Markdown, JSON)
- Auto-format detection
- Directory structure preservation
- UTF-8 encoding support
- Comprehensive validation workflows

**🎬 Live Demo**

![Repomix Unmixer Demo](./demos/repomix-unmixer/extract-repo.gif)

---

### **llm-icon-finder** - AI/LLM Brand Icon Finder

Access 100+ AI model and LLM provider brand icons from lobe-icons library.

**When to use:**
- Finding brand icons for AI models/providers
- Downloading logos for Claude, GPT, Gemini, etc.
- Getting icons in multiple formats (SVG/PNG/WEBP)
- Building AI tool documentation
- Creating presentations about LLMs

**Key features:**
- 100+ AI/LLM model icons
- Multiple format support (SVG, PNG, WEBP)
- URL generation for direct access
- Local download capabilities
- Searchable icon catalog

**🎬 Live Demo**

![LLM Icon Finder Demo](./demos/llm-icon-finder/find-icons.gif)

---

### **cli-demo-generator** - CLI Demo Generation

Generate professional animated CLI demos and terminal recordings with VHS automation.

**When to use:**
- Creating demos for documentation
- Recording terminal workflows as GIFs
- Generating animated tutorials
- Batch-generating multiple demos
- Showcasing CLI tools

**Key features:**
- Automated demo generation from command lists
- Batch processing with YAML/JSON configs
- Interactive recording with asciinema
- Smart timing based on command complexity
- Multiple output formats (GIF, MP4, WebM)
- VHS tape file templates

**🎬 Live Demo**

![CLI Demo Generator Demo](./demos/cli-demo-generator/generate-demo.gif)

---

### **cloudflare-troubleshooting** - Cloudflare Diagnostics

Investigate and resolve Cloudflare configuration issues using API-driven evidence gathering.

**When to use:**
- Site shows ERR_TOO_MANY_REDIRECTS
- SSL/TLS configuration errors
- DNS resolution problems
- Cloudflare-related issues

**Key features:**
- Evidence-based investigation methodology
- Comprehensive Cloudflare API reference
- SSL/TLS mode troubleshooting (Flexible, Full, Strict)
- DNS, cache, and firewall diagnostics
- Agentic approach with optional helper scripts

**🎬 Live Demo**

![Cloudflare Troubleshooting Demo](./demos/cloudflare-troubleshooting/diagnose-redirect-loop.gif)

---

### **ui-designer** - UI Design System Extractor

Extract design systems from reference UI images and generate implementation-ready design prompts.

**When to use:**
- Have UI screenshots/mockups to analyze
- Need to extract color palettes, typography, spacing
- Building MVP UI matching reference aesthetics
- Creating consistent design systems
- Generating multiple UI variations

**Key features:**
- Systematic design system extraction from images
- Color palette, typography, component analysis
- Interactive MVP PRD generation
- Template-driven workflow (design system → PRD → implementation prompt)
- Multi-variation UI generation (3 mobile, 2 web)
- React + Tailwind CSS + Lucide icons

**🎬 Live Demo**

![UI Designer Demo](./demos/ui-designer/extract-design-system.gif)

---

### **ppt-creator** - Professional Presentation Creation

> **Install**: `claude plugin install daymade-docs@daymade-skills` (suite-only — invoked as `daymade-docs:ppt-creator`)

Create persuasive, audience-ready slide decks from topics or documents with data-driven charts and dual-format PPTX output.

**When to use:**
- Creating presentations, pitch decks, or keynotes
- Need structured content with professional storytelling
- Require data visualization and charts
- Want complete PPTX files with speaker notes
- Building business reviews or product pitches

**Key features:**
- Pyramid Principle structure (conclusion → reasons → evidence)
- Assertion-evidence slide framework
- Automatic data synthesis and chart generation (matplotlib)
- Dual-path PPTX creation (Marp CLI + document-skills:pptx)
- Complete orchestration: content → data → charts → PPTX with charts
- 45-60 second speaker notes per slide
- Quality scoring with auto-refinement (target: 75/100)

**🎬 Live Demo**

![PPT Creator Demo](./demos/ppt-creator/create-presentation.gif)

---

### **youtube-downloader** - YouTube Video & Audio Downloader

Download YouTube videos and audio using yt-dlp with robust error handling and automatic workarounds for common issues.

**When to use:**
- Downloading YouTube videos or playlists
- Extracting audio from YouTube videos as MP3
- Experiencing yt-dlp download failures or nsig extraction errors
- Need help with format selection or quality options
- Working with YouTube content in regions with access restrictions

**Key features:**
- Auto PO Token provider (Docker-first, browser fallback) for high-quality access
- Browser-cookie verification for “not a bot” prompts (privacy-friendly)
- Audio-only download with MP3 conversion
- Format listing and custom format selection
- Output directory customization
- Proxy-aware downloads for restricted environments

**🎬 Live Demo**

![YouTube Downloader Demo](./demos/youtube-downloader/download-video.gif)

---

### **repomix-safe-mixer** - Secure Repomix Packaging

Safely package codebases with repomix by automatically detecting and removing hardcoded credentials before packing.

**When to use:**
- Packaging code with repomix for distribution or sharing
- Creating reference packages from proprietary codebases
- Security concerns about accidentally exposing credentials
- Pre-commit security checks for hardcoded secrets
- Auditing codebases for credential exposure

**Key features:**
- Detects 20+ credential patterns (AWS, Supabase, Stripe, OpenAI, etc.)
- Scan → Report → Pack workflow with automatic blocking
- Standalone security scanner for pre-commit hooks
- Environment variable replacement guidance
- JSON output for CI/CD integration
- Exclude patterns for false positive handling

**🎬 Live Demo**

*Coming soon*

---

### **transcript-fixer** - ASR Transcription Correction

> **Install**: `claude plugin install daymade-audio@daymade-skills` (suite-only — invoked as `daymade-audio:transcript-fixer`)

Correct speech-to-text (ASR/STT) errors with a Stage 1 dictionary pre-filter, a required Native AI whole-transcript pass, and an audio-backed human gate for unresolved wording, names, numbers, and entities.

**When to use:**
- Correcting meeting notes, lecture recordings, or interview transcripts
- Fixing Chinese/English homophone errors and technical terminology
- Reviewing one exact transcript with its original audio instead of searching a global queue
- Improving future transcripts without turning one-off fixes into broad dictionary rules
- Collaborating with teams on shared correction knowledge bases

**Key features:**
- Stage 1 + Native AI correction pipeline; Stage 1 alone is never completion
- Exact-file review queue, deep-linked dashboard, timestamped audio playback, and machine-readable zero-pending readback
- Conservative pattern learning: file-only, dictionary, roster, and context have separate admission rules
- Domain-specific dictionaries (general, embodied_ai, finance, medical)
- SQLite-based correction repository
- Team collaboration with import/export
- GLM API integration for AI corrections
- Cost optimization through dictionary promotion

**Example workflow:**
```bash
# Initialize and add corrections
uv run scripts/fix_transcription.py --init
uv run scripts/fix_transcription.py --add "错误词" "正确词" --domain general

# Run full correction pipeline
uv run scripts/fix_transcription.py --input meeting.md --stage 3

# Open only this transcript's unresolved items and listen before deciding
uv run scripts/review-dashboard/server.py --file "/absolute/meeting.md"

# Read the human verdicts back; pending_total must be 0 before final delivery
uv run scripts/fix_transcription.py \
  --list-review --review-file "/absolute/meeting.md" \
  --review-status all --json
```

📚 **Documentation**: See [daymade-audio/transcript-fixer/references/](./daymade-audio/transcript-fixer/references/) for workflow guides, SQL queries, troubleshooting, best practices, team collaboration, and API setup.

**Requirements**: Python 3.10+ and uv. Native AI correction uses the active agent; an external API key is needed only for the optional agent-less API route.

---

### **video-comparer** - Video Comparison and Quality Analysis

Compare two videos and generate interactive HTML reports with quality metrics and frame-by-frame visual comparisons.

**When to use:**
- Comparing original and compressed videos
- Analyzing video compression quality and efficiency
- Evaluating codec performance or bitrate reduction impact
- Assessing before/after compression results
- Quality analysis for video encoding workflows

**Key features:**
- Quality metrics calculation (PSNR, SSIM)
- Frame-by-frame visual comparison with three viewing modes:
  - Slider mode: Drag to reveal differences
  - Side-by-side mode: Simultaneous display
  - Grid mode: Compact 2-column layout
- Video metadata extraction (codec, resolution, bitrate, duration, file size)
- Self-contained HTML reports (no server required, works offline)
- Security features (path validation, resource limits, timeout controls)
- Multi-platform FFmpeg support (macOS, Linux, Windows)

**Example usage:**
```bash
# Basic comparison
python3 scripts/compare.py original.mp4 compressed.mp4

# Custom output and frame interval
python3 scripts/compare.py original.mp4 compressed.mp4 -o report.html --interval 10

# Batch processing
for original in originals/*.mp4; do
    compressed="compressed/$(basename "$original")"
    output="reports/$(basename "$original" .mp4).html"
    python3 scripts/compare.py "$original" "$compressed" -o "$output"
done
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [video-comparer/references/](./video-comparer/references/) for quality metrics interpretation, FFmpeg commands, and configuration options.

**Requirements**: Python 3.8+, FFmpeg/FFprobe (install via `brew install ffmpeg`, `apt install ffmpeg`, or `winget install ffmpeg`)

---

### **qa-expert** - Comprehensive QA Testing Infrastructure

Establish world-class QA testing processes with autonomous LLM execution, Google Testing Standards, and OWASP security best practices.

**When to use:**
- Setting up QA infrastructure for new or existing projects
- Writing standardized test cases following Google Testing Standards (AAA pattern)
- Implementing security testing (OWASP Top 10 coverage)
- Executing comprehensive test plans with automatic progress tracking
- Filing bugs with proper P0-P4 severity classification
- Calculating quality metrics and enforcing quality gates
- Enabling autonomous LLM-driven test execution (100x speedup)
- Preparing QA documentation for third-party team handoffs

**Key features:**
- **One-command initialization**: Complete QA infrastructure with templates, CSVs, and documentation
- **Autonomous execution**: Master prompt enables LLM to auto-execute all tests, auto-track results, auto-file bugs
- **Google Testing Standards**: AAA pattern compliance, 90% coverage targets, fail-fast validation
- **OWASP security testing**: 90% Top 10 coverage with specific attack vectors
- **Quality gates enforcement**: 100% execution, ≥80% pass rate, 0 P0 bugs, ≥80% code coverage
- **Ground Truth Principle**: Prevents doc/CSV sync issues (test docs = authoritative source)
- **Bug tracking**: P0-P4 classification with detailed repro steps and environment info
- **Day 1 onboarding**: 5-hour guide for new QA engineers
- **30+ LLM prompts**: Ready-to-use prompts for specific QA tasks
- **Metrics dashboard**: Test execution progress, pass rate, bug analysis, quality gates status

**Example usage:**
```bash
# Initialize QA project (creates full infrastructure)
python3 scripts/init_qa_project.py my-app ./

# Calculate quality metrics and gates status
python3 scripts/calculate_metrics.py tests/TEST-EXECUTION-TRACKING.csv

# For autonomous execution, copy master prompt from:
# references/master_qa_prompt.md → paste to LLM → auto-executes 342 tests over 5 weeks
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [qa-expert/references/](./qa-expert/references/) for:
- `master_qa_prompt.md` - Single command for autonomous execution (100x speedup)
- `google_testing_standards.md` - AAA pattern, coverage thresholds, OWASP testing
- `day1_onboarding.md` - 5-hour onboarding timeline for new QA engineers
- `ground_truth_principle.md` - Preventing doc/CSV sync issues
- `llm_prompts_library.md` - 30+ ready-to-use QA prompts

**Requirements**: Python 3.8+

**💡 Innovation**: The autonomous execution capability (via master prompt) enables LLM to execute entire test suites 100x faster than manual execution, with zero human error in tracking. Perfect for third-party QA handoffs - just provide the master prompt and they can start testing immediately.

---

### **prompt-optimizer** - Prompt Engineering with EARS Methodology

Transform vague prompts into precise, well-structured specifications using EARS (Easy Approach to Requirements Syntax) - a methodology created by Rolls-Royce for converting natural language into testable requirements.

**Methodology inspired by:** [阿星AI工作室 (A-Xing AI Studio)](https://mp.weixin.qq.com/s/yUVX-9FovSq7ZGChkHpuXQ), which pioneered combining EARS with domain theory grounding for practical prompt enhancement.

**When to use:**
- Converting loose requirements into structured specifications
- Optimizing prompts for AI code generation or content creation
- Breaking down vague feature requests into atomic, testable statements
- Adding domain theory grounding to technical requirements
- Transforming "build X" requests into detailed implementation specs
- Learning prompt engineering best practices with proven frameworks

**Key features:**
- **EARS transformation**: 5 sentence patterns (ubiquitous, event-driven, state-driven, conditional, unwanted behavior)
- **6-step optimization workflow**: Analyze → Transform → Identify theories → Extract examples → Enhance → Present
- **Domain theory catalog**: 40+ frameworks mapped to 10 domains (productivity, UX, gamification, learning, e-commerce, security)
- **Structured prompt framework**: Role/Skills/Workflows/Examples/Formats template
- **Advanced techniques**: Multi-stakeholder requirements, non-functional specs, complex conditional logic
- **Complete examples**: Procrastination app, e-commerce product page, learning dashboard, password reset
- **Theory grounding**: GTD, BJ Fogg Behavior Model, Gestalt Principles, AIDA, Zero Trust, and more
- **Progressive disclosure**: Bundled references (ears_syntax.md, domain_theories.md, examples.md)

**Example usage:**
```markdown
# Before (vague)
"Build me a password reset feature"

# After EARS transformation (7 atomic requirements)
1. When user clicks "Forgot Password", the system shall display email input field
2. When user submits valid email, the system shall send password reset link valid for 1 hour
3. When user clicks reset link, the system shall verify token has not expired
4. When token is valid, the system shall display password creation form requiring minimum 12 characters, 1 uppercase, 1 number, 1 special character
5. When user submits new password meeting requirements, the system shall hash password with bcrypt and invalidate reset token
6. When user attempts password reset more than 3 times in 1 hour, the system shall block further attempts for 1 hour
7. If reset token has expired, the system shall display error message and option to request new link

# Enhanced with domain theories
- Zero Trust Architecture (verify at each step)
- Defense in Depth (rate limiting + token expiration + password complexity)
- Progressive Disclosure (multi-step UX flow)

# Full prompt includes Role, Skills, Workflows, Examples, Formats
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [prompt-optimizer/references/](./prompt-optimizer/references/) for:
- `ears_syntax.md` - Complete EARS patterns and transformation rules
- `domain_theories.md` - 40+ theories mapped to domains with selection guidance
- `examples.md` - Full transformation examples with before/after comparisons

**💡 Innovation**: EARS methodology eliminates ambiguity by forcing explicit conditions, triggers, and measurable criteria. Combined with domain theory grounding (GTD, BJ Fogg, Gestalt, etc.), it transforms "build a todo app" into a complete specification with behavioral psychology principles, UX best practices, and concrete test cases - enabling test-driven development from day one.

---

### **local-conversation-history** - Cross-Provider History Entry Point

> **Install**: `claude plugin install daymade-claude-code@daymade-skills` (suite-only — invoked as `daymade-claude-code:local-conversation-history`)

The entry point above the four provider-and-action-specific history skills. It
routes a request to whichever one owns it — by platform (Claude Code, OpenAI
Codex, Kimi CLI) and action (read evidence vs continue interrupted work) — and
owns the one job none of them own alone: a single inventory spanning all three
providers.

**When to use:**
- The provider is unknown or plural — "our history", "what have I been working on"
- Listing Kimi CLI sessions, which has no dedicated skill of its own
- It is unclear whether the need is evidence or resumption
- You remember this entry point by name

**When not to use:** the platform *and* the action are both already clear. Load
that executor skill directly instead — this router adds a hop, not information.

**Design**: a thin routing layer. It carries no parsing, no provider-specific
flags beyond `--source`, and no copies of the executors' commands, so it cannot
drift into teaching a stale invocation.

---

### **read-claude-code-history** - Read Local Claude Code History

> **Install**: `claude plugin install daymade-claude-code@daymade-skills` (suite-only — invoked as `daymade-claude-code:read-claude-code-history`)

Read, search, and export Claude Code history across all active config homes and
the long-term archives registered in `~/.claude/history-sources.json`, without
resuming or modifying the old task.

**When to use:**
- Recovering deleted or lost files from previous Claude Code sessions
- Reconstructing one known Session as a chronological user/assistant handoff
- Listing what the human actually typed, including queued mid-turn corrections
- Searching for specific code across conversation history
- Tracking file modifications across multiple sessions
- Finding sessions containing specific keywords or implementations
- Verifying date-bounded topics after a machine migration without trusting mtime

**Key features:**
- **Complete source set**: Search active homes and registered archives by default
- **Provider boundary**: Claude-only by default; Codex requests route to `read-codex-history`
- **Cross-project sweep**: `--all-projects` searches every Claude project when the project is unknown; `--exclude-session` skips self-matches
- **Copy-safe union**: Search distinct records from every copy of a session ID without double-counting identical records
- **Internal-time search**: Filter matching records by JSONL timestamps, never file mtime
- **Structured search**: Cover messages, thinking, tools, results, queues, attachments, summaries, and original file-history paths
- **Exact checkpoint recovery**: Union same-session copies and companion roots, then restore captured bytes after Write/Edit/shell changes, including binaries and pre-deletion checkpoints
- **Fail-visible fidelity**: Label Write-only checkpoints as lower fidelity and abort when exact metadata points to missing bytes instead of silently guessing
- **Statistics analysis**: Message counts, tool usage breakdown, file operations
- **Batch operations**: Process multiple sessions with keyword filtering
- **Streaming processing**: Handle large session files (>100MB) efficiently
- **Read/continue separation**: Produces an evidence receipt and never resumes work itself

**Example usage:**
```bash
# List recent sessions for a project
python3 scripts/analyze_sessions.py list /path/to/project

# Read one Session chronologically, preserving queued human input
python3 scripts/read_claude_session.py --session <session-id> --project /path/to/project --full

# Export recent human wording grouped by Session
python3 scripts/extract_user_messages.py ./user-words --days 7 --group-by session

# Search sessions for keywords
python3 scripts/analyze_sessions.py search /path/to/project \
  "ComponentName" "featureX" --from-date 2026-03-01 --to-date 2026-04-30

# Recover deleted files from the exact path printed by search
python3 scripts/recover_content.py <printed-session-path> -k DeletedComponent -o ./recovered/

# Search every project for multiple vanished job artifacts
python3 scripts/analyze_sessions.py search --all-projects \
  artifact-a.html artifact-b.html \
  --exclude-session <current-session-id>

# Get session statistics
python3 scripts/analyze_sessions.py stats /path/to/session.jsonl --show-files
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [daymade-claude-code/read-claude-code-history/references/](./daymade-claude-code/read-claude-code-history/references/) for:
- `session_file_format.md` - JSONL structure and extraction patterns
- `workflow_examples.md` - Detailed recovery and analysis workflows

---

### **docs-cleaner** - Documentation Consolidation

> **Install**: `claude plugin install daymade-docs@daymade-skills` (suite-only — invoked as `daymade-docs:docs-cleaner`)

Consolidate redundant documentation while preserving all valuable content.

**When to use:**
- Cleaning up documentation bloat across projects
- Merging redundant docs covering the same topics
- Reducing documentation sprawl after rapid development
- Consolidating multiple files into authoritative sources

**Key features:**
- **Content preservation**: Never lose valuable information during cleanup
- **Redundancy detection**: Identify overlapping documentation
- **Smart merging**: Combine related docs while maintaining structure
- **Validation**: Ensure consolidated docs are complete and accurate

**🎬 Live Demo**

*Coming soon*

---

### **skills-search** - CCPM Skill Registry Search

Search, discover, install, and manage Claude Code skills from the CCPM (Claude Code Plugin Manager) registry.

**When to use:**
- Finding skills for specific tasks (e.g., "find PDF skills")
- Installing skills by name
- Listing currently installed skills
- Getting detailed information about a skill
- Managing your Claude Code skill collection

**Key features:**
- **Registry search**: Search CCPM registry with `ccpm search <query>`
- **Skill installation**: Install skills with `ccpm install <skill-name>`
- **Version support**: Install specific versions with `@version` syntax
- **Bundle installation**: Install pre-configured skill bundles (web-dev, content-creation, developer-tools)
- **Multiple formats**: Supports registry names, GitHub owner/repo, and full URLs
- **Skill info**: Get detailed skill information with `ccpm info <skill-name>`

**Example usage:**
```bash
# Search for skills
ccpm search pdf              # Find PDF-related skills
ccpm search "code review"    # Find code review skills

# Install skills
ccpm install skill-creator                # From registry
ccpm install daymade/skill-creator        # From GitHub
ccpm install skill-creator@1.0.0          # Specific version

# List and manage
ccpm list                    # List installed skills
ccpm info skill-creator      # Get skill details
ccpm uninstall pdf-processor # Remove a skill

# Install bundles
ccpm install-bundle web-dev  # Install web development skills bundle
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [daymade-skill/skills-search/SKILL.md](./daymade-skill/daymade-skill/skills-search/SKILL.md) for complete command reference

**Requirements**: CCPM CLI (`npm install -g @daymade/ccpm`)

---

### **pdf-creator** - PDF Creation with Chinese Font Support

> **Install**: `claude plugin install daymade-docs@daymade-skills` (suite-only — invoked as `daymade-docs:pdf-creator`)

Create professional PDF documents from markdown with proper Chinese typography using WeasyPrint.

**When to use:**
- Converting markdown to PDF for sharing or printing
- Generating formal documents (legal filings, reports)
- Ensuring correct Chinese font rendering

**Key features:**
- pandoc + WeasyPrint conversion pipeline (dual backend: WeasyPrint or headless Chrome)
- Built-in Chinese/Japanese/Korean (CJK) font fallbacks with auto CJK code-block rendering
- Theme system (default for formal docs, cjk-auto for content-driven tables, warm-terra for training materials, mobile for phone reading)
- A4 layout defaults with print-friendly margins
- Batch conversion scripts

**Example usage:**
```bash
uv run --with weasyprint scripts/md_to_pdf.py input.md output.pdf
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [daymade-docs/pdf-creator/SKILL.md](./daymade-docs/pdf-creator/SKILL.md) for setup and workflow details.

**Requirements**: Python 3.8+, `pandoc` (system install), `weasyprint` (or Chrome as fallback backend)

---

### **claude-md-progressive-disclosurer** - CLAUDE.md Optimization

> **Install**: `claude plugin install daymade-claude-code@daymade-skills` (suite-only — invoked as `daymade-claude-code:claude-md-progressive-disclosurer`)

Optimize user CLAUDE.md files using progressive disclosure to reduce context bloat while preserving critical rules.

**When to use:**
- CLAUDE.md is too long or repetitive
- Need to move detailed procedures into references
- Want to extract reusable workflows into skills

**Key features:**
- Section classification (keep/move/extract/remove)
- Before/after line-count reporting
- Reference file and pointer formats
- Best-practice optimization workflow

**Example usage:**
```
"Optimize my ~/.claude/CLAUDE.md using progressive disclosure and propose a plan."
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [claude-md-progressive-disclosurer/SKILL.md](./daymade-claude-code/claude-md-progressive-disclosurer/SKILL.md).

---

### **promptfoo-evaluation** - Promptfoo LLM Evaluation

Configure and run LLM evaluations with Promptfoo for prompt testing and model comparisons.

**When to use:**
- Setting up prompt tests and eval configs
- Comparing LLM outputs across providers
- Adding custom assertions or LLM-as-judge grading

**Key features:**
- promptfooconfig.yaml templates
- Python custom assertions
- llm-rubric scoring guidance
- Built-in preview (echo provider) workflows

**Example usage:**
```bash
npx promptfoo@latest init
npx promptfoo@latest eval
npx promptfoo@latest view
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [promptfoo-evaluation/references/promptfoo_api.md](./promptfoo-evaluation/references/promptfoo_api.md).

**Requirements**: Node.js (Promptfoo via `npx promptfoo@latest`)

---

### **developing-ios-apps** - iOS App Development

> **Install**: `claude plugin install daymade-macos@daymade-skills` (suite-only — invoked as `daymade-macos:developing-ios-apps`)

Build, configure, and debug iOS apps with XcodeGen, SwiftUI, and Swift Package Manager.

**When to use:**
- Setting up XcodeGen `project.yml`
- Fixing SPM dependency or embed issues
- Handling code signing and device deployment errors
- Debugging camera/AVFoundation problems

**Key features:**
- XcodeGen project templates
- SPM dynamic framework embedding fixes
- Code signing and provisioning guidance
- Device deployment and troubleshooting checklists

**Example usage:**
```bash
xcodegen generate
xcodebuild -destination 'platform=iOS Simulator,name=iPhone 17' build
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [developing-ios-apps/references/xcodegen-full.md](./daymade-macos/developing-ios-apps/references/xcodegen-full.md).

**Requirements**: macOS + Xcode, XcodeGen

---

### **twitter-reader** - Twitter/X Content Fetching

Fetch Twitter/X post and article content. Single-post text goes through the
fxtwitter mirror API (login-free, key-free, full long-form body); X Articles
with images go through `fetch_article.py`; the Jina API path remains as a
fallback with a known intermittent-ban risk.

**When to use:**
- Retrieving tweet content for analysis or documentation
- Fetching X Articles (long-form) with all images downloaded locally
- Extracting images and media from posts
- Batch downloading multiple tweets for reference

**Key features:**
- Single posts: fxtwitter mirror — no key, no login, full `tweet.text` body including note_tweet long-form
- No JavaScript rendering or browser automation needed
- No Twitter authentication required
- Returns markdown-formatted content with metadata
- Supports both individual and batch fetching
- Includes author, timestamp, post text, images, and replies
- Environment variable configuration for secure API key management

**Example usage:**
```bash
# Single post text (preferred): fxtwitter mirror, no key needed
curl -sS "https://api.fxtwitter.com/USER/status/TWEET_ID" \
  | python3 -c "import json,sys; t=json.load(sys.stdin)['tweet']; print(t['text'])"

# X Article with images (full mode)
uv run --with pyyaml python scripts/fetch_article.py \
  "https://x.com/USER/status/TWEET_ID" ./Clippings

# Jina fallback (intermittent — see SKILL.md risk note)
export JINA_API_KEY="your_api_key_here"
curl "https://r.jina.ai/https://x.com/USER/status/TWEET_ID" \
  -H "Authorization: Bearer ${JINA_API_KEY}"

# Batch fetch multiple tweets
scripts/fetch_tweets.sh \
  "https://x.com/user/status/123" \
  "https://x.com/user/status/456"

# Fetch to file using Python script
python scripts/fetch_tweet.py https://x.com/user/status/123 output.md
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [twitter-reader/SKILL.md](./twitter-reader/SKILL.md) for full details and URL format support.

**Requirements**:
- **curl** (pre-installed on most systems) — single-post path needs nothing else
- **Python 3.6+** (for Python scripts)
- **Jina.ai API key** (only for the Jina fallback; intermittent-ban risk, and the shared repo key is currently out of balance / 402)

---

### **macos-cleaner** - Intelligent macOS Disk Space Recovery

> **Install**: `claude plugin install daymade-macos@daymade-skills` (suite-only — invoked as `daymade-macos:macos-cleaner`)

**The safest way to reclaim disk space on macOS.** Start with targeted read-only diagnosis when a subsystem is already suspect—including Apple Content Caching—then analyze caches, application remnants, large files, and development environments only as needed.

**Why macos-cleaner stands out:**
- **Safety-First Philosophy**: Never deletes without explicit user confirmation. Every operation includes risk assessment (🟢 Safe / 🟡 Caution / 🔴 Keep).
- **Intelligence Over Automation**: Analyzes first, explains thoroughly, then lets you decide. Unlike one-click cleaners that blindly delete, we help you understand what you're removing and why.
- **Developer-Friendly**: Deep analysis of Docker, Homebrew, npm, pip caches - tools that generic cleaners miss.
- **Transparent & Educational**: Every recommendation includes an explanation of what the file is, why it's safe (or not), and what happens if you delete it.
- **Professional Quality**: Built by developers who know the pain of accidentally deleting important files. Includes comprehensive safety checks and Time Machine backup recommendations.

**Our design principles:**
1. **User Control First**: You make the decisions, we provide the insights
2. **Explain Everything**: No mysterious deletions - full transparency on impact
3. **Conservative Defaults**: When uncertain, we preserve rather than delete
4. **Developer Context**: Understand development tool caches, not just system files
5. **Hybrid Approach**: Combine script precision with visual tools (Mole integration)

**When to use:**
- Your Mac is running out of disk space (>80% full)
- You're a developer with Docker/npm/pip/Homebrew caches piling up
- Apple Content Caching reports `Caching needs more space`, an unlimited cache, or unexpectedly high `ActualCacheUsed`
- You want to understand what's consuming space, not just delete blindly
- You need to clean up after uninstalled applications
- You prefer understanding over automation

**Key features:**
- **Smart Cache Analysis**: Categorizes system caches, app caches, logs by safety level
- **Apple Content Caching**: Separates logical `CacheUsed` from physical `ActualCacheUsed`, verifies peers and protected services, and uses Apple's supported limit/deactivate/flush controls
- **Application Remnant Detection**: Finds orphaned data from uninstalled apps with confidence scoring
- **Large & Duplicate File Discovery**: Intelligent categorization plus optional read-only `fdupes` scans inside exact approved paths
- **Development Environment Cleanup**: Docker images/containers/volumes, OrbStack, Homebrew, npm, and pip; Docker build cache is measured but prune-based deletion is out of scope
- **Interactive Safe Deletion**: Batch confirmation, selective deletion, undo-friendly (uses Trash when possible)
- **Before/After Reports**: Track space recovery with detailed breakdown
- **Mole Integration**: Seamless workflow with visual cleanup tool for GUI preferences
- **Risk Categorization**: Every item labeled with safety level and explanation
- **Time Machine Awareness**: Recommends backups before large deletions (>10 GB)

**What makes us different:**
- ✅ **Trust Through Transparency**: Other cleaners hide what they delete. We show everything and explain why.
- ✅ **Developer-Centric**: We clean Docker, not just browser caches. We understand `.git` directories, `node_modules`, and build artifacts.
- ✅ **Safety Checks Built-In**: Protection against deleting system files, user data, credentials, active databases, or files in use.
- ✅ **Educational**: Learn what's safe to delete and why, so you can maintain your Mac confidently.
- ❌ **Not a One-Click Solution**: Nothing changes until you approve a scoped command plan. When you ask Claude to execute it, only those confirmed actions run, followed by before/after verification.

**Example usage:**
```bash
# Install the Apple platform suite
claude plugin install daymade-macos@daymade-skills

# Ask Claude Code to analyze your Mac
"My Mac is running out of space, help me analyze what's using storage"

# Claude will:
# 1. Route a named suspect to targeted read-only diagnosis; scan broadly only if the source is unknown
# 2. Present categorized findings with safety levels
# 3. Explain each category (caches, remnants, large files, dev tools)
# 4. Recommend cleanup approach
# 5. Execute ONLY what you confirm

# Example analysis output:
📊 Disk Space Analysis
━━━━━━━━━━━━━━━━━━━━━━━━
Total:     500 GB
Used:      450 GB (90%)
Available:  50 GB (10%)

🟢 Safe to Clean (95 GB):
  - System caches:     45 GB (apps regenerate automatically)
  - Homebrew cache:     5 GB (reinstalls when needed)
  - npm cache:          3 GB (safe to clear)
  - Old logs:           8 GB (diagnostic data only)
  - Trash:             34 GB (already marked for deletion)

🟡 Review Recommended (62 GB):
  - Large downloads:   38 GB (may contain important files)
  - App remnants:       8 GB (verify apps are truly uninstalled)
  - Docker images:     12 GB (may be in use)
  - Old .git repos:     4 GB (verify project is archived)

🔴 Keep Unless Certain (0 GB):
  - No high-risk items detected

Recommendation: Start with 🟢 Safe items (95 GB), then review 🟡 items together.
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [macos-cleaner/references/](./daymade-macos/macos-cleaner/references/) for:
- `apple_content_caching.md` - Targeted Apple Content Caching diagnosis and supported repair
- `cleanup_targets.md` - Detailed explanations of every cleanup target
- `mole_integration.md` - How to combine scripts with Mole visual tool
- `safety_rules.md` - Comprehensive safety guidelines and what to never delete

**Requirements**:
- **Python 3.6+** (pre-installed on macOS)
- **macOS** (tested on macOS 10.15+)
- **Optional**: [Mole](https://github.com/tw93/Mole) for visual cleanup interface

---

### **fact-checker** - Document Fact-Checking

Verify factual claims in documents using web search and official sources, then propose corrections with user confirmation.

**When to use:**
- Fact-checking documents for accuracy
- Verifying AI model specifications and technical documentation
- Updating outdated information in documents
- Validating statistical claims and benchmarks
- Checking API capabilities and version numbers

**Key features:**
- Web search integration with authoritative sources
- AI model specification verification
- Technical documentation accuracy checks
- Statistical data validation
- Automated correction reports with user confirmation
- Supports general factual statements and technical claims

**Example usage:**
```bash
# Install the skill
claude plugin install fact-checker@daymade-skills

# Fact-check a document
"Please fact-check this section about AI model capabilities"

# Verify technical specs
"Check if these Claude model specifications are still accurate"

# Update outdated info
"Verify and update the version numbers in this documentation"
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [fact-checker/SKILL.md](./fact-checker/SKILL.md) for full workflow and claim types.

**Requirements**:
- Web search access (via Claude Code)

---

### **skill-reviewer** - Skill Quality Review & Improvement

Review and improve Claude Code skills against official best practices with three powerful modes.

**When to use:**
- Validating your own skills before publishing
- Evaluating others' skill repositories
- Contributing improvements to open-source skills via auto-PR
- Ensuring skills follow marketplace standards

**Key features:**
- **Self-review mode**: Run the bundled reviewer backed by canonical skill-creator validation
- **External review mode**: Clone, analyze, and generate improvement reports
- **Auto-PR mode**: Fork → improve → submit PR with additive-only changes
- **Evaluation checklist**: Frontmatter, instructions, resources verification
- **Additive-only principle**: Never delete files when contributing to others
- **PR guidelines**: Tone recommendations and professional templates
- **Reliable automation**: Distinguishes review findings from invocation/runtime failures with structured JSON output

**Example usage:**
```bash
# Install the skill
claude plugin install daymade-skill@daymade-skills

# Self-review your skill
"Validate my skill at ~/my-skills/my-awesome-skill"

# Review external skill repository
"Review the skills at https://github.com/user/skill-repo"

# Auto-PR improvements
"Fork, improve, and submit PR for https://github.com/user/skill-repo"
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [daymade-skill/skill-reviewer/references/](./daymade-skill/skill-reviewer/references/) for:
- `evaluation_checklist.md` - Complete skill evaluation criteria
- `pr_template.md` - Professional PR description template

---

### **github-contributor** - GitHub Contribution Strategy

Strategic guide for becoming an effective GitHub contributor and building your open-source reputation.

**When to use:**
- Looking for projects to contribute to
- Learning contribution best practices
- Building your GitHub presence and reputation
- Understanding how to write high-quality PRs

**Key features:**
- **Four contribution types**: Documentation, Code Quality, Bug Fixes, Features
- **Project selection criteria**: What makes a good first project vs red flags
- **PR excellence workflow**: Before → During → After submission checklist
- **Reputation building ladder**: Documentation → Bug Fixes → Features → Maintainer
- **GitHub CLI commands**: Quick reference for fork, PR, issue operations
- **Conventional commit format**: Type, scope, description structure
- **Common mistakes**: What to avoid and best practices

**Contribution types explained:**
```
Level 1: Documentation fixes (lowest barrier, high impact)
    ↓ (build familiarity)
Level 2: Code quality (medium effort, demonstrates skill)
    ↓ (understand codebase)
Level 3: Bug fixes (high impact, builds trust)
    ↓ (trusted contributor)
Level 4: Feature additions (highest visibility)
    ↓ (potential maintainer)
```

**Example usage:**
```bash
# Install the skill
claude plugin install github-contributor@daymade-skills

# Find good first issues
"Help me find projects with good first issues in Python"

# Write a high-quality PR
"Guide me through creating a PR for this bug fix"

# Build contribution strategy
"Help me plan a contribution strategy for building my GitHub profile"
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [github-contributor/references/](./github-contributor/references/) for:
- `pr_checklist.md` - Complete PR quality checklist
- `project_evaluation.md` - How to evaluate projects for contribution
- `communication_templates.md` - Issue and PR communication templates

---

### **i18n-expert** - Internationalization & Localization

Complete internationalization/localization setup and auditing for UI codebases. Configure i18n frameworks, replace hard-coded strings with translation keys, ensure locale parity between en-US and zh-CN, and validate pluralization and formatting.

**When to use:**
- Setting up i18n for new React/Next.js/Vue applications
- Auditing existing i18n implementations for key parity and completeness
- Replacing hard-coded strings with translation keys
- Ensuring proper error code mapping to localized messages
- Validating pluralization, date/time/number formatting across locales
- Implementing language switching and SEO metadata localization

**Key features:**
- Library selection and setup (react-i18next, next-intl, vue-i18n)
- Key architecture and locale file organization (JSON, YAML, PO, XLIFF)
- Translation generation strategy (AI, professional, manual)
- Routing and language detection/switching
- SEO and metadata localization
- RTL support for applicable locales
- Key parity validation between en-US and zh-CN
- Pluralization and formatting validation
- Error code mapping to localized messages
- Bundled i18n_audit.py script for key usage extraction

**Example usage:**
```bash
# Install the skill
claude plugin install i18n-expert@daymade-skills

# Setup i18n for a new project
"Set up i18n for my React app with English and Chinese support"

# Audit existing i18n implementation
"Audit the i18n setup and find missing translation keys"

# Replace hard-coded strings
"Replace all hard-coded strings in this component with i18n keys"
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [i18n-expert/SKILL.md](./i18n-expert/SKILL.md) for complete workflow and architecture guidance.

**Requirements**:
- **Python 3.6+** (for audit script)
- **React/Next.js/Vue** (framework-specific i18n library)

---

### **claude-skills-troubleshooting** - Plugin & Skill Troubleshooting

> **Install**: `claude plugin install daymade-claude-code@daymade-skills` (suite-only — invoked as `daymade-claude-code:claude-skills-troubleshooting`)

Diagnose and resolve Claude Code plugin and skill configuration issues. Debug plugin installation, enablement, and activation problems with systematic workflows.

**When to use:**
- Plugins installed but not showing in available skills list
- Skills not activating as expected despite installation
- Troubleshooting enabledPlugins configuration in settings.json
- Debugging "plugin not working" or "skill not showing" issues
- Understanding plugin state architecture and lifecycle

**Key features:**
- Quick diagnosis via diagnostic script (detects installed vs enabled mismatch)
- Plugin state architecture documentation (installed_plugins.json vs settings.json)
- Marketplace cache freshness detection and update guidance
- Known GitHub issues tracking (#17832, #19696, #17089, #13543, #16260)
- Batch enable script for missing plugins from a marketplace
- Skills vs Commands architecture explanation
- Comprehensive diagnostic commands reference

**Example usage:**
```bash
# Run diagnostic
python3 scripts/diagnose_plugins.py

# Batch enable missing plugins
python3 scripts/enable_all_plugins.py daymade-skills
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [claude-skills-troubleshooting/SKILL.md](./daymade-claude-code/claude-skills-troubleshooting/SKILL.md) for complete troubleshooting workflow and architecture guidance.

**Requirements**: None (uses Claude Code built-in Python)

---

### **meeting-minutes-taker** - Meeting Minutes Generator

> **Install**: `claude plugin install daymade-audio@daymade-skills` (suite-only — invoked as `daymade-audio:meeting-minutes-taker`)

Transform meeting transcripts into high-fidelity, structured meeting minutes with iterative human review.

**When to use:**
- Meeting transcript provided and minutes/notes/summaries requested
- Multiple versions of meeting minutes need merging without content loss
- Existing minutes need review against original transcript for missing items

**Key features:**
- Multi-pass parallel generation with UNION merge strategy
- Evidence-based recording with speaker quotes
- Mermaid diagrams for architecture discussions
- Iterative human-in-the-loop refinement workflow
- Cross-AI comparison for bias reduction
- Completeness checklist for systematic review

**Example usage:**
```bash
# Install the full audio suite (includes meeting-minutes-taker)
claude plugin install daymade-audio@daymade-skills

# Then provide a meeting transcript and request minutes
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [daymade-audio/meeting-minutes-taker/SKILL.md](./daymade-audio/meeting-minutes-taker/SKILL.md) for complete workflow and template guidance.

**Requirements**: None

---

### **deep-research** - Research Report Generator

Generate format-controlled research reports with evidence tracking and citations.

**When to use:**
- Need a structured research report, literature review, or market/industry analysis
- Require strict section formatting or a template to be enforced
- Need evidence mapping, citations, and source quality review
- Want multi-pass synthesis to avoid missing key findings

**Key features:**
- Report spec and format contract workflow
- Evidence table with source quality rubric
- Multi-pass complete drafting with UNION merge
- Citation verification and conflict handling
- Ready-to-use report template and formatting rules

**Example usage:**
```bash
# Install the skill
claude plugin install deep-research@daymade-skills

# Then provide a report spec or template and request a deep research report
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [deep-research/SKILL.md](./deep-research/SKILL.md) and [deep-research/references/research_report_template.md](./deep-research/references/research_report_template.md) for workflow and structure.

**Requirements**: None

---

### **competitors-analysis** - Evidence-Based Competitor Intelligence

Discover, clone, update, and analyze competitor repositories with evidence-based competitive intelligence. Repository-backed findings must come from local cloned code; market-landscape claims must cite their source and volatility.

**When to use:**
- Track and analyze competitor products or technologies
- Discover GitHub competitors for a product or market
- Create evidence-based competitor profiles
- Generate competitive landscape and opportunity reports
- Check whether competitor code has changed
- Need to document technical decisions with cited sources

**Key features:**
- Durable competitor workspace convention using `$HOME/workspace/competitors/{product}/`
- GitHub discovery workflow for shortlisting relevant repositories
- Repository ingest/update flow with remote + commit recording
- Required source citation format for repository facts (`file:line_number`)
- Landscape synthesis for positioning, strengths, weaknesses, opportunities, and risks
- Tech stack analysis guides for Node.js, Python, Rust projects
- Bundled templates: profile template, analysis checklist
- Management script for discover/clone-url/clone/pull/status operations

**Example usage:**
```bash
# Install the skill
claude plugin install competitors-analysis@daymade-skills

# Then ask Claude to analyze a competitor
"分析竞品 https://github.com/org/repo"
"添加竞品到 flowzero 产品的竞品列表"
"看看 claude-flow-viewer 这个方向最近有哪些竞品更新"
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [competitors-analysis/SKILL.md](./competitors-analysis/SKILL.md) and [competitors-analysis/references/](./competitors-analysis/references/) for templates.

**Requirements**: Git (for cloning repositories)

---

### **tunnel-doctor** - Tailscale + Proxy/VPN Conflict Fixer

Diagnose and fix conflicts when using Tailscale alongside proxy/VPN tools (Shadowrocket, Clash, Surge) on macOS. Covers four independent conflict layers with specific guidance for SSH access to WSL instances.

**When to use:**
- Tailscale ping works but SSH/TCP connections time out
- Proxy tools hijack the Tailscale CGNAT range (100.64.0.0/10)
- Browser returns HTTP 503 but curl and SSH work
- `git push/pull` fails with "failed to begin relaying via HTTP"
- Setting up Tailscale SSH to WSL and encountering `operation not permitted`
- Need to make Tailscale and Shadowrocket/Clash/Surge coexist on macOS

**Key features:**
- Four-layer diagnostic model: route hijacking, HTTP env vars, system proxy bypass, SSH ProxyCommand double tunneling
- Per-tool fix guides for Shadowrocket, Clash, and Surge
- SSH ProxyCommand double tunnel detection and fix (git push/pull failures)
- Tailscale SSH ACL configuration (`check` vs `accept`)
- WSL snap vs apt Tailscale installation (snap sandbox breaks SSH)
- Remote development SOP with proxy-safe Makefile patterns

**Example usage:**
```bash
# Install the skill
claude plugin install tunnel-doctor@daymade-skills

# Then ask Claude to diagnose
"Tailscale ping works but SSH times out"
"Fix Tailscale and Shadowrocket route conflict on macOS"
"git push fails with failed to begin relaying via HTTP"
"Set up Tailscale SSH to my WSL instance"
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [tunnel-doctor/references/proxy_conflict_reference.md](./tunnel-doctor/references/proxy_conflict_reference.md) for per-tool configuration and conflict architecture.

---

### **windows-remote-desktop-connection-doctor** - AVD/W365 Connection Quality Diagnostician

Diagnose Windows App (Microsoft Remote Desktop / Azure Virtual Desktop / W365) connection quality issues on macOS, with focus on transport protocol optimization (UDP Shortpath vs WebSocket fallback).

**When to use:**
- VDI connection is slow with high RTT (>100ms)
- Transport Protocol shows WebSocket instead of UDP
- RDP Shortpath fails to establish
- Connection quality degraded after changing network location
- Need to identify VPN/proxy interference with STUN/TURN

**Key features:**
- 5-step diagnostic workflow from connection info collection to fix verification
- Transport protocol analysis (UDP Shortpath > TCP > WebSocket hierarchy)
- VPN/proxy interference detection (ShadowRocket TUN mode, Tailscale exit node)
- Windows App log parsing for health check failures, certificate errors, FetchClientOptions timeouts
- ISP UDP restriction testing with STUN connectivity checks
- Chinese ISP-specific guidance for UDP throttling issues
- Working vs broken log comparison methodology

**Example usage:**
```bash
# Install the skill
claude plugin install windows-remote-desktop-connection-doctor@daymade-skills

# Then ask Claude to diagnose
"My VDI connection shows WebSocket instead of UDP, RTT is 165ms"
"Diagnose why RDP Shortpath is not working"
"Windows App transport protocol stuck on WebSocket"
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [windows-remote-desktop-connection-doctor/references/](./windows-remote-desktop-connection-doctor/references/) for log analysis patterns and AVD transport protocol details.

---

### **product-analysis** - Multi-Path Product Analysis & Optimization

Run a scalable, evidence-driven product audit using parallel Claude Code agents and optional Codex CLI parallelization. Covers UX, API, architecture, and competitive benchmark workflows with quantified findings and priority recommendations.

**When to use:**
- Product launch readiness reviews
- Multi-perspective codebase and UX audits before release
- API quality checks with endpoint and consumption consistency reviews
- Competitive benchmarking against selected competitor repos

**Key features:**
- Auto-detects tool context (project stack + optional `codex` availability)
- Parallel analysis across dimensions: `full`, `ux`, `api`, `arch`, `compare`
- Multi-agent synthesis with quantified findings and P0/P1/P2 recommendations
- Built-in comparison hooks with `competitors-analysis`
- Cross-validation workflow to reduce overfitting from a single model perspective

**Example usage:**
```bash
# Install the skill
claude plugin install product-analysis@daymade-skills

# Then ask Claude for analysis
"Run product-analysis in full mode for launch audit"
"Do a UX audit and report quantified navigation findings"
"Run API audit and identify unused endpoints"
"Compare this product with our top competitors"
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [product-analysis/SKILL.md](./product-analysis/SKILL.md) and [product-analysis/references/analysis_dimensions.md](./product-analysis/references/analysis_dimensions.md) for dimension definitions and workflow guidance.

**Requirements**: Optional `codex` CLI (for multi-model parallel mode). Skill runs with Claude only if `codex` is not installed.

---

### **financial-data-collector** - Financial Data Collection for US Equities

> **Install**: `claude plugin install daymade-financial@daymade-skills` (suite-only — invoked as `daymade-financial:financial-data-collector`)

Collect real financial data for any US publicly traded company from free public sources (yfinance). Output structured JSON with market data, historical financials (income statement, cash flow, balance sheet), WACC inputs, and analyst estimates - ready for downstream DCF modeling, comps analysis, or earnings review.

**When to use:**
- Collecting structured financial data before building DCF or valuation models
- Pulling market data (price, shares, beta, market cap) for any US equity ticker
- Gathering historical income statement, cash flow, and balance sheet data
- Getting risk-free rate (10Y Treasury) and analyst consensus estimates

**Key features:**
- Robust yfinance field mapping with alias chains (handles API instability across versions)
- NaN year detection and transparent reporting (never fills with estimates)
- 9-check validation: field completeness, market cap cross-check, CapEx sign convention, net debt consistency
- NO FALLBACK principle: missing data returns `null` with `_source` attribution, never default values
- FCF definition mismatch flagging (yfinance FCF ≠ investment bank FCF due to SBC)

**Example usage:**
```bash
# Install the suite
claude plugin install daymade-financial@daymade-skills

# Then ask Claude to collect data
"Collect financial data for META"
"Get financials for AAPL --years 3"
"Pull DCF inputs for NVDA"
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [financial-data-collector/SKILL.md](./daymade-financial/financial-data-collector/SKILL.md), [output-schema.md](./daymade-financial/financial-data-collector/references/output-schema.md), and [yfinance-pitfalls.md](./daymade-financial/financial-data-collector/references/yfinance-pitfalls.md).

**Requirements**: Python 3.11+, `yfinance`, `pandas` (auto-installed via uv inline dependencies).

---

### **excel-automation** - Excel Creation, Parsing, and macOS Control

> **Install**: `claude plugin install daymade-docs@daymade-skills` (suite-only — invoked as `daymade-docs:excel-automation`)

Create professionally formatted Excel files, parse complex `.xlsm` models with stdlib XML/ZIP workflows, and control Microsoft Excel windows on macOS via AppleScript.

**When to use:**
- Building finance-ready spreadsheets with consistent formatting rules
- Parsing complex bank/broker `.xlsm` files that fail in `openpyxl`
- Extracting targeted sheet/cell data without loading huge workbooks
- Automating Excel window operations (zoom, scroll, select) on macOS

**Key features:**
- Production template for formatted workbook generation via `openpyxl`
- Complex workbook parser using `zipfile` + `xml.etree` (no heavy dependencies)
- Corrupted `definedNames` repair workflow for problematic files
- Verified AppleScript command patterns with timeout safeguards
- Bundled formatting reference for colors, number formats, and table patterns

**Example usage:**
```bash
# Install the documentation suite
claude plugin install daymade-docs@daymade-skills

# Then ask Claude to automate Excel workflows
"Create a formatted valuation template workbook"
"Parse this .xlsm and extract the DCF sheet"
"Generate an AppleScript sequence to zoom and scroll Excel before screenshot"
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [excel-automation/SKILL.md](./daymade-docs/excel-automation/SKILL.md) and [formatting-reference.md](./daymade-docs/excel-automation/references/formatting-reference.md).

**Requirements**: Python 3.8+, `uv`, `openpyxl` (auto via `uv run --with openpyxl`), macOS for AppleScript window control.

---

### **capture-screen** - Programmatic macOS Screenshot Capture

> **Install**: `claude plugin install daymade-macos@daymade-skills` (suite-only — invoked as `daymade-macos:capture-screen`)

Capture application windows by CGWindowID with a reliable three-step workflow: discover window IDs via Swift, control app state via AppleScript, and capture outputs with `screencapture`.

**When to use:**
- Automating repeatable screenshot workflows for documentation
- Capturing specific app windows instead of full-screen screenshots
- Producing multi-shot sequences after scripted scroll/zoom changes
- Building visual evidence capture pipelines on macOS

**Key features:**
- Bundled Swift script to resolve accurate window IDs (`CGWindowListCopyWindowInfo`)
- Verified AppleScript patterns for app activation and window preparation
- Window-scoped capture commands with silent mode, delays, and format control
- Multi-shot workflow pattern for section-by-section capture
- Clear anti-pattern notes for methods that fail on macOS

**Example usage:**
```bash
# Install the Apple platform suite
claude plugin install daymade-macos@daymade-skills

# Then ask Claude to capture windows programmatically
"Find the Excel window ID and capture it silently"
"Create a multi-shot capture workflow for this workbook"
"Capture Chrome window sections with scripted scrolling"
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [capture-screen/SKILL.md](./daymade-macos/capture-screen/SKILL.md).

**Requirements**: macOS (Swift + AppleScript + `screencapture`).

---

### **continue-claude-code-work** - Resume Interrupted Claude Work

> **Install**: `claude plugin install daymade-claude-code@daymade-skills` (suite-only — invoked as `daymade-claude-code:continue-claude-code-work`)

Continue a verified Claude Code Session without reopening the old interactive
session. The continuation layer first consumes `read-claude-code-history`, then
reconstructs the original business outcome, unfulfilled requests, corrections,
proven prior assets, and one next action that directly advances the goal.

**When to use:**
- A user provides a Claude session ID and wants the task continued
- You need to inspect local `.claude` JSONL files instead of running `claude --resume`
- A previous session was interrupted and the next concrete step must be reconstructed
- A multi-agent workflow was interrupted and you need to know which subagents completed

**Key features:**
- Requires a chronological read receipt rather than separate user/assistant tail lists
- Restores original outcome, remaining work, rejected routes, and successful assets
- Verifies current files, git state, external writes, and background work before duplicating anything
- Makes the business result—not parser success, review completion, or subprocess exit—the completion unit

**Example usage:**
```bash
# Then ask Claude to resume from local artifacts
"continue work from session 123e4567-e89b-12d3-a456-426614174000"
"don't resume, just read the .claude files and continue"
"check what I was working on in the last session and keep going"
```

📚 **Documentation**: See [continue-claude-code-work/SKILL.md](./daymade-claude-code/continue-claude-code-work/SKILL.md).

**Requirements**: Python 3.8+, `git` for workspace reconciliation.

---

### **scrapling-skill** - Reliable Scrapling CLI Workflows

Install, troubleshoot, and use Scrapling CLI with a verified static-first workflow for extracting HTML, Markdown, or text from webpages. Includes a diagnostic script for broken extras installs, Playwright browser runtime checks, and smoke tests against real URLs.

**When to use:**
- Users mention Scrapling, `uv tool install scrapling`, or `scrapling extract`
- You need to choose between static and browser-backed fetching
- You need to extract article bodies from WeChat public pages (`mp.weixin.qq.com`)
- A Scrapling install works partially but fails on missing extras, browser runtime, or TLS verification

**Key features:**
- Bundled `diagnose_scrapling.py` script for CLI, browser runtime, and live URL smoke tests
- Verified default path: start with `extract get`, escalate to `extract fetch` only when needed
- WeChat extraction pattern using `#js_content` for clean article Markdown
- Troubleshooting guidance for missing `click`, Playwright runtime setup, and `curl: (60)` trust-store failures
- Output validation workflow using file size and content checks instead of exit-code assumptions

**Example usage:**
```bash
# Install the skill
claude plugin install scrapling-skill@daymade-skills

# Then ask Claude to work through Scrapling for you
"Install Scrapling CLI and verify the setup"
"Extract this WeChat article into Markdown with Scrapling"
"Decide whether this page needs static or browser-backed fetching"
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [scrapling-skill/SKILL.md](./scrapling-skill/SKILL.md) and [scrapling-skill/references/troubleshooting.md](./scrapling-skill/references/troubleshooting.md).

**Requirements**: Python 3.6+, `uv`, Scrapling CLI, and Playwright browser runtime for browser-backed fetches.

---

### **ima-copilot** - Tencent IMA Companion & Installer

One-stop wrapper for the official Tencent IMA skill (`ima.qq.com`). Installs upstream `ima-skill` to Claude Code, Codex, and OpenClaw via `npx skills add`, guides API key setup, detects and repairs known upstream issues under user consent, and implements a personalized fan-out search strategy that floats priority knowledge bases to the top.

**When to use:**
- Users mention IMA, 腾讯 IMA, ima.qq.com, or need to install the official ima-skill
- Users report `Skipped loading skill(s) due to invalid SKILL.md` warnings related to ima-skill
- You need to search across IMA knowledge bases with KB-priority boosting
- You need to configure or rotate IMA API credentials
- Upstream ima-skill ships a known issue (e.g., missing YAML frontmatter in submodule files)

**Key features:**
- Zero-config installation to Claude Code / Codex / OpenClaw via [vercel-labs/skills](https://github.com/vercel-labs/skills) with auto-detection and default symlink mode (fix or upgrade once, every agent sees it)
- XDG-style credential management at `~/.config/ima/{client_id, api_key}` with env-var fallback
- `scripts/diagnose.sh` read-only health check (install presence, credential liveness, known issues)
- `scripts/search_fanout.py` client-side cross-KB search with priority lists, subset-skip lists, and 100-hit silent-truncation detection
- Wrapper-only architecture: never vendors upstream files, never forks — every repair is a runtime instruction executed with explicit consent and automatic timestamped backups
- Two user-selectable repair strategies for the frontmatter issue (rename to `MODULE.md` or prepend minimal frontmatter)
- Personalization via `~/.config/ima/copilot.json` with illustrative-only template values

**Example usage:**
```bash
# Install the skill
claude plugin install ima-copilot@daymade-skills

# Then ask Claude to drive the flow
"Install ima-skill and configure my IMA API key"
"Run diagnose on my ima-skill and fix whatever is broken"
"Search my IMA knowledge bases for embedding model comparisons, priority to my curated KB"
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [ima-copilot/SKILL.md](./ima-copilot/SKILL.md) and [ima-copilot/references/known_issues.md](./ima-copilot/references/known_issues.md).

**Requirements**: Node.js 18+ (for `npx skills`), `curl`, `unzip`, Python 3.6+. IMA OpenAPI credentials from [https://ima.qq.com/agent-interface](https://ima.qq.com/agent-interface).

---

### **claude-export-txt-better** - Fix Claude Code Export Formatting

> **Install**: `claude plugin install daymade-claude-code@daymade-skills` (suite-only — invoked as `daymade-claude-code:claude-export-txt-better`)

Reconstruct broken line wrapping in Claude Code exported `.txt` conversation files. Rebuilds tables, paragraphs, paths, and tool calls that were hard-wrapped at fixed column widths, and ships with an automated 53-check validation suite (file-agnostic, catches over- and under-merging regressions).

**When to use:**
- Users have a Claude Code export file where tables, paths, or tool output got mangled by line wrapping
- Users mention "fix export", "fix conversation", "make export readable"
- Users reference a file matching `YYYY-MM-DD-HHMMSS-*.txt`
- Users want to post-process `/export` output before sharing or archiving it

**Key features:**
- Deterministic Python script (`fix-claude-export.py`) with `--stats` mode for before/after metrics
- 53-check automated validator (`validate-claude-export-fix.py`) that catches regressions
- Evals directory with real fixture cases
- No external dependencies beyond `uv` and Python 3.8+

**Example usage:**
```bash
# Fix and show stats
uv run daymade-claude-code/claude-export-txt-better/scripts/fix-claude-export.py broken.txt --stats

# Custom output path
uv run daymade-claude-code/claude-export-txt-better/scripts/fix-claude-export.py broken.txt -o fixed.txt

# Validate the fix
uv run daymade-claude-code/claude-export-txt-better/scripts/validate-claude-export-fix.py broken.txt fixed.txt
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [claude-export-txt-better/SKILL.md](./daymade-claude-code/claude-export-txt-better/SKILL.md) and the bundled `evals/` fixtures.

**Requirements**: Python 3.8+, `uv` package manager.

---

### **douban-skill** - Douban Collection Export & Sync

Export and sync Douban (豆瓣) book / movie / music / game collections to local CSV files via the reverse-engineered Frodo API. Full export covers all history; RSS incremental sync keeps daily updates current. No login, no cookies, no browser — just a user ID and it works.

**When to use:**
- Users want to back up their Douban reading/watching/listening/gaming history
- Users mention 豆瓣, douban, 读书记录, 观影记录, 书影音
- Users need incremental sync of recent Douban activity
- Users want CSV output compatible with Excel (UTF-8 BOM)

**Key features:**
- Full export of all 4 categories (books/movies/music/games) via Frodo API
- RSS incremental sync for daily updates (last ~10 items per feed)
- Pre-flight user-ID validation (fail-fast on wrong ID)
- UTF-8 BOM CSV output, Excel-compatible, cross-platform
- Bundled troubleshooting log documenting 7 tested scraping approaches and why each failed (Douban PoW challenges block every web-scraping approach — only Frodo API works)
- `.gitleaks.toml` allowlist for the public Android APK credentials

**Example usage:**
```bash
# Full export of user's collections
uv run douban-skill/scripts/douban-frodo-export.py <douban-user-id>

# Incremental RSS sync (last ~10 items per category)
uv run douban-skill/scripts/douban-rss-sync.py <douban-user-id>
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [douban-skill/SKILL.md](./douban-skill/SKILL.md) and [douban-skill/references/troubleshooting.md](./douban-skill/references/troubleshooting.md) for the complete failure log of rejected approaches.

**Requirements**: Python 3.8+, `uv` package manager. No login or cookies required.

---

### **terraform-skill** - Terraform Operational Traps

Designs and diagnoses safe Terraform releases as well as the provisioner traps learned from real incidents. It keeps staging and production on one required configuration schema, validates exact candidate bytes + the Compose-rendered environment + the immutable runtime before live mutation, and binds saved plans to staging evidence, source provenance, explicit production authorization, and independent readback.

**When to use:**
- Writing `null_resource` provisioners or `remote-exec` blocks that SSH into fresh instances
- Setting up multi-environment (prod/staging/dev) Terraform with shared modules
- Debugging containers that are Restarting/unhealthy after `terraform apply`
- Hitting "docker: not found" in remote-exec, rsync connection drops in local-exec, or TLS cert errors
- Troubleshooting drift or provisioner failures during re-runs
- Configuring Caddy/gateway resources with Cloudflare credentials
- Reviewing a saved plan or broad deploy resource that may also mutate a shared gateway
- Closing staging/production config drift, receipt, provenance, or production-approval gaps

**Key features:**
- One required-key contract for every environment; values may differ, requiredness may not
- Exact-bundle prevalidation for every normal and recovery writer before any live write/restart
- Saved-plan, staging-receipt, remote-main provenance, production-approval, and live-readback gates
- Corrected provider/provisioner patterns for cloud-init, Docker, DNS, TLS, snapshots, and fresh hosts

**Example usage:**
```bash
# Trigger the skill naturally during Terraform work
"I'm getting 'docker: not found' in my null_resource provisioner after apply"
"My rsync local-exec is failing with 'connection unexpectedly closed'"
"Help me write a multi-env Terraform setup without snapshot cross-contamination"
"Staging has this Caddy variable but production leaves it empty — how do I validate both safely?"
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [terraform-skill/SKILL.md](./terraform-skill/SKILL.md) and the bundled `references/` for detailed remediation patterns.

**Requirements**: None (Terraform-adjacent knowledge only; no runtime dependencies).

---

### **slides-creator** - Narrative-First Slide Deck Creation

Guides users through structured narrative design (ABCDEFG model), then delegates visual generation to `baoyu-slide-deck`. Focuses on what machines can't do — narrative co-design with humans.

**When to use:**
- Creating presentations, slide decks, or PPTs from user content
- Turning articles, transcripts, or notes into visual slides
- Designing narrative arcs for talks and workshops

**Key features:**
- Phase 0: Source material collection (user's own words first)
- Phase 1: Narrative structure discussion using ABCDEFG model
- Phase 2: Content structuring for machine-readable input
- Phase 3-5: Delegates visual generation to baoyu-slide-deck
- Phase 6: Post-processing with directory reorganization and speaker notes extraction

**Example usage:**
```bash
# Trigger the skill naturally
"Help me turn my article into a slide deck"
"Create a presentation from my talk transcript"
"I need a 20-minute deck for a workshop"
```

**Requirements**: baoyu-slide-deck skill for visual generation.

---

### **excalidraw-use** - Place Images onto an Excalidraw Board

Batch-place existing images onto an Excalidraw whiteboard, laid out on a generous grid so nobody has to drag them apart afterwards. Also turns a slide deck into clean per-slide images first, and inspects what is inside a `.excalidraw` file. The available Excalidraw MCP servers and skills cover element CRUD and export but document no image element type, no `dataURL` handling, and no `files` map — embedding your own pictures is the gap this fills.

**When to use:**
- Putting screenshots, a picture library, or deck slides onto a whiteboard
- Spacing many images out so they never need manual adjustment
- Turning a Vite/React slide deck into images you can draw over
- Inspecting a scene file: element mix, embedded payload size, occupied extent

**Key features:**
- Content-hash dedupe and `--exclude` for images already on the board
- `--template-from` copies the image-element field set out of your own board — Excalidraw's published schema stops before `fileId`/`status`/`scale`/`crop`
- Write-back verification: fails on a missing file entry, a distorted aspect ratio, or any overlap
- Deck capture hides presenter chrome, expands staged reveals, and reports fragments that never rendered
- Documents the two silent destroyers: *Open* and drag-and-drop **replace** a scene (only the clipboard merges), and a stale build removes a source feature while `innerText` still reads hidden fragments as present

**Example usage:**
```bash
# Trigger the skill naturally
"Put these screenshots on my Excalidraw board"
"Add my old workshop images to the canvas, spaced out"
"Turn this deck into images I can draw on"
```

**Note**: Not for generating a diagram from a text description — that is a different job.

---

### **debugging-network-issues** - Evidence-Driven Network Investigation

Falsification-first methodology for network, streaming, and protocol-layer bugs where the obvious cause is probably wrong. Built from a real 5-hour SSE incident where assumption-stacking wasted hours that a 10-minute layered experiment would have resolved.

**When to use:**
- Connection resets (`ECONNRESET`, HTTP/2 `RST_STREAM`, `INTERNAL_ERROR`)
- SSE / long-polling stalls or fixed-time drops (60s, 100s, 130s)
- CDN / proxy / CGNAT idle-timeout incidents
- Client-side proxy / VPN / TUN misrouting (e.g. `ERR_CONNECTION_CLOSED`, `SSL_ERROR_SYSCALL`, fake TUN DNS IPs, CNAME-based rule overrides)
- Certificate-verification errors (`UNKNOWN_CERTIFICATE_VERIFICATION_ERROR`, wrong-site certificate)
- Any "works sometimes / fails after N seconds" pattern
- LAN-layer mysteries: unknown devices on the local network, devices silenced by a subnet change, hosts "dead" on one segment but alive on another
- Multi-hop systems (client → CDN → LB → reverse proxy → app → upstream) where a symptom could plausibly come from several layers

**Key features:**
- Layered isolation experiments: run the same logical request through three or more paths differing by exactly one hop
- Env-gated runtime instrumentation patterns (no production-code mutation)
- Counter-review four-question filter to challenge single-cause assumptions
- Bundled probe scripts (`layered-isolation-probe.sh`, `mock-idle-upstream.py`)
- Real case studies: SSE RST_STREAM at 130s caused by CGNAT idle timeout; proxy/TUN CNAME rule override causing `ERR_CONNECTION_CLOSED`

**Requirements**: None (methodology + portable shell/Python probes).

---

### **stepfun-tts** - StepFun StepAudio 2.5 Contextual TTS

> **Install**: `claude plugin install daymade-audio@daymade-skills` (suite-only — invoked as `daymade-audio:stepfun-tts`)

Generate Chinese / Japanese speech with `stepaudio-2.5-tts`. Captures the two non-obvious TTS pitfalls that cost hours otherwise: `voice_label` removal (replaced by natural-language `instruction`) and stricter 2.5-era censorship (死/消失/political terms).

**When to use:**
- Chinese / Japanese TTS with emotional and prosody control (whisper, pause, stress, mid-sentence pivot)
- Batch-generating game / app voice lines with per-line `censorship_block` fallback
- Migration from `step-tts-2` to `stepaudio-2.5-tts` (`voice_label` → `instruction` breaking change)
- Hitting StepFun censorship blocks on previously-fine content

**Key features:**
- `stepaudio-2.5-tts` with `instruction` (≤200 chars natural-language mood) + inline `()` prosody
- Bundled `tts_generate.py` (with `--batch <jsonl>`) and `ab_compare.sh`
- API key resolution: `$STEPFUN_API_KEY` → `${CLAUDE_PLUGIN_DATA}/config.json` fallback
- Censorship rewrite playbook in `references/migration_from_v2.md`

**Requirements**: StepFun API key, "Normal" tier (https://platform.stepfun.com/). For ASR / transcription, use the sibling `stepfun-asr` skill below.

---

### **stepfun-asr** - StepFun StepAudio 2.5 ASR (SSE Endpoint)

> **Install**: `claude plugin install daymade-audio@daymade-skills` (suite-only — invoked as `daymade-audio:stepfun-asr`)

Transcribe Chinese / English audio with `stepaudio-2.5-asr`. Hides the #1 trap of the 2.5 ASR family: it does NOT live on `/v1/audio/transcriptions` — the wrong endpoint returns a misleading `model stepaudio-2.5-asr not supported` error that looks identical to a permission/whitelist failure.

**When to use:**
- Long audio transcription (up to ~30 minutes single-call, 32K context, ~85-101× RTF — no client-side chunking)
- Migration from `step-asr` / `step-asr-1.1` (different endpoint, different body shape, SSE response)
- Hitting the misleading `model stepaudio-2.5-asr not supported` error (= wrong endpoint, not permission)
- Silent 4xx auth failures on audio endpoints (= using a "Plan" key instead of a "Normal" key)

**Key features:**
- `/v1/audio/asr/sse` SSE streaming with base64 audio + nested JSON body (the script handles all four traps)
- Bundled `asr_transcribe.py` — pure-stdlib CLI, auto-detects mp3/wav/ogg/opus/pcm by extension
- Handles SSE `error` events (censorship can fire on ASR side too — rare but real)
- API key resolution: `$STEPFUN_API_KEY` → `${CLAUDE_PLUGIN_DATA}/config.json` fallback
- Suggests `transcript-fixer` (ASR error correction) and `meeting-minutes-taker` (structured minutes) as natural downstream skills

**Requirements**: StepFun API key, "Normal" tier (https://platform.stepfun.com/). Plan keys cannot call audio endpoints.

---

### **auto-repo-setup** - Automated Repository Setup & Environment Repair

Make a repository runnable and handoff-ready without guessing its stack or changing how collaborators normally work. The skill reads project authority first, repairs the verified gap, and treats startup instructions, lifecycle hooks, and Git mutation as different mechanisms with different safety boundaries.

**When to use:**
- Someone says "跑不起来", "怎么启动", "环境怎么配", or "帮我设置代码库"
- Setting up a new machine or creating a durable repository handoff
- Adding routine startup sync for Claude Code/Codex without auto-stashing local work
- Diagnosing repeated SessionStart output before changing hook configuration
- Adding a lifecycle hook only when behavior must occur before the first prompt
- Sanitizing git history after accidental secret/path leaks
- Handling merge conflicts or git push failures with explicit safety gates

**Key features:**
- **Outcome router**: separates environment repair, routine sync, handoff, hook diagnosis, and explicit pre-prompt automation
- **Stack-aware inventory**: `check_env.py` infers only declared toolchains from manifests/lockfiles; it does not assume ffmpeg, uv, Python, or .env
- **Startup boundary**: defaults stable behavior to AGENTS.md/CLAUDE.md or a normal Agent request; the Claude hook manager is guarded, dry-runnable, idempotent, and removable
- **Safety guardrails**: Push Safety (visibility verification before any push), PII Guard (4-layer secret scanning), NO FALLBACK principle for env vars, Git Hook Bypass ban
- **Counter-review boundary**: reserves multi-agent review for material shared-config/security/destructive changes, not ordinary setup checks
- **Bundled scripts**: stack-aware inventory, guarded Claude startup-nudge manager, and read-only history candidate scan

**Example usage:**
```bash
# Install the skill
claude plugin install auto-repo-setup@daymade-skills

# Then ask Claude naturally
"我跑不起来这个仓库"
"帮我设置一下这个项目的环境"
"进入项目先同步远端；本地有改动不要自动 stash"
"为什么同一个 SessionStart 输出了三次？先查清来源"
"只有首条消息前必须注入动态提醒时，才帮我装 hook"
"git push 被拒了"
```

**Requirements**: The guidance itself has no runtime dependency. Bundled Python utilities require Python 3.10+; no external API key is required.

---

### **terminal-screenshot** - See the Real Visual Result of Terminal Output

Render a terminal CLI program's colored output to a PNG so Claude can actually *see* the rendered result — color contrast, alignment, background blocks, highlighting — instead of only reading plain text and raw ANSI escape codes. Reading a hex value is guessing; seeing the rendered contrast on the real terminal background is verification.

**When to use:**
- Right after changing any CLI color config (delta / bat / themes / lazygit pager) to visually confirm the result
- Verifying git diff (delta) add/remove contrast, bat syntax highlighting, starship prompt, eza/ls colors, ripgrep matches
- Any time you need to judge "does this color look right / is the contrast enough" instead of guessing from hex codes

**Key features:**
- **Capture-then-render discipline**: captures full-fidelity ANSI in a normal shell first, then renders — never lets the renderer run complex CLIs (which degrade in a child pty and drop background blocks)
- **freeze-first, zero-dependency fallback**: prefers charmbracelet/freeze for faithful rendering; falls back to a bundled stdlib ANSI→HTML converter + headless Chrome when freeze is unavailable
- **Real terminal background**: renders on the actual terminal background color so dark themes are judged accurately
- **Per-CLI capture recipes**: delta, git, bat, eza, ls, ripgrep, and a generic forced-color path
- **Bundled scripts**: `render_ansi.sh` (freeze/Chrome auto-select), `ansi2html.py` (stdlib renderer)

**Example usage:**
```bash
# terminal-screenshot lives in the daymade-claude-code suite
claude plugin install daymade-claude-code@daymade-skills

# Then ask Claude naturally
"verify my delta diff colors"
"看一下这个终端配色的真实效果"
"is the add/remove contrast in git diff strong enough?"
```

**Requirements**: macOS. `charmbracelet/freeze` (preferred renderer) or Google Chrome (fallback). Python 3 for the fallback renderer.

---

### **pdf-to-html** - Read a PDF as Faithful HTML (with Optional Translation)

Convert a PDF into one self-contained, readable HTML file that preserves images, charts and reading order — optionally translating it into another language while keeping every figure. A PDF is a layout, not just a text stream, so the workflow renders each page for you to *see* before building, and renders the HTML for visual verification before delivery.

**When to use:**
- Reading a PDF as a clean web page or document (especially on a phone)
- Turning a report or whitepaper PDF into styled HTML without losing its figures
- Translating a PDF into another language while keeping its images, charts and tables in place

**Key features:**
- **Structured extraction** (PyMuPDF): text blocks with font sizes + images, with decorative images (footer logos, rules) auto-detected and dropped
- **Data-driven build**: heading levels inferred from font size, content images compressed and base64-inlined into one portable file
- **Optional parallel translation**: a Dynamic Workflow translates pages concurrently, captions data charts, and reconciles terminology — with fidelity rules (never invent a translated name; copy numbers and proper nouns verbatim)
- **Mandatory visual verification**: adaptive headless-Chrome screenshot sliced into readable segments (works around Chrome's ~16384px screenshot cap)
- **Bundled failure-cases reference**: the real traps (verification, rendering limits, fidelity) so they are not re-discovered

**Example usage:**
```bash
# pdf-to-html lives in the daymade-docs suite
claude plugin install daymade-docs@daymade-skills

# Then ask Claude naturally
"把这个 PDF 转成中文网页版"
"make this report readable as HTML"
"translate this PDF to English but keep the charts"
```

**Requirements**: `uv`, Google Chrome or Chromium (visual verification). Python packages (PyMuPDF, Pillow, numpy) auto-install via `uv run --with`.

---

### **asr-transcribe-to-text** - Audio/Video Transcription with Qwen3-ASR

> **Install**: `claude plugin install daymade-audio@daymade-skills` (suite-only — invoked as `daymade-audio:asr-transcribe-to-text`)

Transcribe audio and video files to text using Qwen3-ASR via two interchangeable inference paths: local MLX on macOS Apple Silicon (no API key, 15-27x realtime) or a remote vLLM/OpenAI-compatible API for any platform. Auto-detects the platform and recommends the best path, persisting the choice in `${CLAUDE_PLUGIN_DATA}/config.json`.

**When to use:**
- Transcribing meeting recordings, lectures, interviews, podcasts, or screen recordings
- Converting any audio/video file to text (speech-to-text)
- Local, free transcription on an Apple Silicon Mac, or remote API when local is unavailable
- The first stage of a transcribe → correct → minutes pipeline

**Key features:**
- Dual inference paths — local MLX (15-27x realtime, free) and remote API, with automatic platform detection
- Bundled `transcribe_local_mlx.py` loads the model once and processes files sequentially (no GPU contention)
- Uses low-energy ~20-minute chunks with an 8192-token per-chunk bound, atomic checkpoints/resume, and full process-tree cleanup so one bad chunk cannot become an unbounded GPU job
- Remote fallback `overlap_merge_transcribe.py` splits into 18-minute chunks with 2-minute overlap and fuzzy-merges
- ffmpeg video→16kHz mono WAV extraction, truncation verification, and proxy-bypass handling
- Proactively suggests `transcript-fixer` to clean ASR recognition errors on the output

**Example usage:**
```bash
# asr-transcribe-to-text lives in the daymade-audio suite
claude plugin install daymade-audio@daymade-skills

# Then ask Claude naturally
"transcribe this meeting recording to text"
"把这个录音转成文字"
"convert lecture.mp4 to a transcript"
```

**Requirements**: `uv`, ffmpeg/ffprobe. Local MLX path needs macOS Apple Silicon; remote path needs a reachable vLLM/OpenAI-compatible ASR endpoint. No API key for local mode.

---

### **marketplace-dev** - Skills Repo → Plugin Marketplace

> **Install**: `claude plugin install daymade-claude-code@daymade-skills` (suite-only — invoked as `daymade-claude-code:marketplace-dev`)

Create and maintain Claude Code plugin marketplaces: convert a repository, consolidate standalone skills into a new or existing suite, move skills between suites, validate real installation/cache boundaries, and ship the result through a PR.

**When to use:**
- Making a skills repo installable via `claude plugin install`
- Generating or fixing a `marketplace.json` (plugin distribution, one-click install, auto-update)
- Adding a new plugin to an existing marketplace and bumping the right versions
- Putting existing skills into a suite, moving a skill between suites, or making members suite-only
- Debugging schema rejections like `Unrecognized key: "$schema"` or duplicate plugin names

**Key features:**
- Evidence-intake phase that mines docs and local session history instead of guessing from a template
- Encodes non-obvious schema rules: `$schema` is rejected, `metadata` has only 3 valid fields, `strict: false` semantics, single-skill vs suite `source`/`skills` patterns
- Bundled `check_marketplace.sh` runs four checks (JSON syntax → `claude plugin validate` → source/skills resolution → reverse sync) and exits non-zero on failure
- Installation, cache-footprint, and GitHub-install test recipes to confirm `source` produced the intended snapshot
- Dedicated suite-consolidation workflow covering canonical moves, byte/mode preservation, repository-wide install/path drift, existing-user migration, isolated real installation, and immutable review
- Two PostToolUse hooks (validate on `marketplace.json` edit; warn on un-bumped version when a `SKILL.md` changes) that auto-activate with the plugin

**Example usage:**
```bash
# marketplace-dev lives in the daymade-claude-code suite
claude plugin install daymade-claude-code@daymade-skills

# Then ask Claude naturally
"turn this skills repo into a plugin marketplace"
"generate a marketplace.json for this repo and validate it"
"add my new skill to the marketplace and open a PR"
"move these standalone skills into daymade-macos and make them suite-only"
```

**Requirements**: `claude` CLI (for `claude plugin validate` / install tests), `jq`. Git remotes configured if opening an upstream PR.

---

### **skill-creator** - Create, Improve & Benchmark Skills

> **Install**: `claude plugin install daymade-skill@daymade-skills` (suite-only — invoked as `daymade-skill:skill-creator`)

The essential meta-skill for building your own skills. It scales verification to the change: bounded fixes get targeted checks, narrow behavior changes get sampled replays, and broad/high-risk work becomes eligible for heavier evidence without automatically starting it. Paired baselines, graders, benchmarks, and viewers require explicit authorization or a decision-bearing evidence plan plus opt-in. It also supports explicit benchmarking and optimizes a skill's `description` for better triggering accuracy.

**When to use:**
- Creating a skill from scratch, or editing/optimizing an existing one
- Running evals to test a skill, or benchmarking performance with variance analysis
- Improving a skill's description so Claude triggers it more reliably
- Wrapping a third-party CLI tool you just got working into a reusable companion skill

**Key features:**
- Prior-art research across the live conversation, explicitly approved prior history, local SOPs, installed plugins/MCPs, skills.sh, official plugins, npm/PyPI — to reuse infrastructure and encode only the user's unique methodology
- The inline-vs-`context: fork` decision guide (subagents can't spawn subagents or call skills) and composable/orthogonal skill design
- `init_skill.py` scaffolding, `package_skill.py` (auto-validates), and `security_scan.py` (gitleaks-based secret/PII detection)
- Existing-skill migration gate: tool-attested snapshot or verified Git-commit baseline, runtime-reachability-aware capability audit, explicit dispositions, and package-time re-verification that a clean commit or hand-written marker cannot bypass
- Risk-scaled verification router: Tier 1 targeted checks, Tier 2 sampled behavior replay, and Tier 3 broad/high-risk classification without automatic fan-out
- Separately authorized full-eval harness: with-skill + baseline runs, assertions, grading, benchmark aggregation, and an HTML viewer after an explicit request, or after a decision-bearing evidence plan receives opt-in
- Mandatory sanitization read-through for public skills — catches no-keyword leaks scanners miss
- Description-optimization loop (60/40 train/test split, selects best description by held-out score)

**Example usage:**
```bash
# skill-creator lives in the daymade-skill suite
claude plugin install daymade-skill@daymade-skills

# Then ask Claude naturally
"create a skill that does X"
"improve this skill's description so it triggers more reliably"
"benchmark this skill against a no-skill baseline"
```

**Requirements**: Python 3, `uv`, PyYAML (validation/packaging), gitleaks (security scan). `claude` CLI only for agent evals and description-optimization runs.

---

### **feishu-doc-scraper** - Feishu/Lark → Faithful Markdown + Source-First Archive

Extract Feishu (Lark) Docs, Wiki pages/collections, spreadsheets (including cell-attachment file download), and Minutes (妙记) transcripts into faithful local Markdown. The primary path uses the `lark-cli` API — it extracts the document body programmatically (no model paraphrasing), recursively follows a collection's reference graph, and reads permission boundaries from error codes; a browser-DOM path is the fallback only when lark-cli cannot reach the content.

**When to use:**
- The source is a Feishu/Lark URL and fidelity matters (导出飞书文档/合集/妙记转写)
- Converting a Feishu wiki/knowledge base to Markdown, or archiving a Feishu collection
- Exporting a Feishu Minutes (妙记) transcript
- Converting an owner-exported `.docx` into faithful Markdown with heading/highlight restoration

**Key features:**
- lark-cli API extraction writes the body to disk via `jq` (never retyped by the model — the single most important fidelity rule)
- Recursive reference-graph traversal (BFS) with `feishu_extract_refs.py`, plus a residual rich-media-tag acceptance gate so no referenced doc is silently missed
- Native Minutes transcript export (never re-runs ASR on downloaded media)
- Permission-denied path: owner-exported `.docx` → Markdown with font-size→heading and `w:shd`→highlight restoration, then visual verification
- Source-first artifact manifest + fail-closed validator: structured/searchable derivatives go to Git, raw binaries remain on Feishu or an explicitly chosen object store, and local downloads stay optional caches instead of Git LFS payloads
- `LARK_CLI_NO_PROXY=1` discipline for `*.feishu.cn` (avoids credential leak/DNS hijack) and a U+FFFD encoding-corruption final check
- Works with both Feishu (feishu.cn) and Lark (larkoffice.com)

**Example usage:**
```bash
# Install the skill
claude plugin install feishu-doc-scraper@daymade-skills

# Then ask Claude naturally
"把这个飞书合集导出成 markdown"
"export this Feishu Minutes transcript"
"save this Lark wiki page as Markdown"
```

**Requirements**: `lark-cli` binary (npm `@larksuite/cli`) authenticated to the target tenant; `jq`. Fallback path needs a browser-automation surface; the docx path needs `python-docx` and a docx→md converter (the bundled doc-to-markdown skill or pandoc).

---

### **bigdata-skill** - Bigdata.com (RavenPack) SDK + REST Toolkit

> **Install**: `claude plugin install daymade-financial@daymade-skills` (suite-only — invoked as `daymade-financial:bigdata-skill`)

Pull Bigdata.com (RavenPack) financial and news data through the official `bigdata-client` SDK and its public `/v1/*` REST endpoints — reaching the structured substrate the Bigdata MCP server doesn't hand over. The MCP returns prose chunks and pre-synthesized tearsheets; this toolkit reaches structured financials, prices, analyst estimates, a daily entity-sentiment series, annotated chunk search with sentiment + entity spans, and a screener.

**When to use:**
- Using Bigdata.com / RavenPack and the MCP result feels thin ("where's the sentiment score?", "I need entity-level data", "the calendar")
- Pulling forward/structured financials: analyst estimates, earnings/event calendar, surprises, ratings, price targets, statements, TTM metrics, a company screener
- Wanting annotated news chunks with numeric sentiment + entity spans, a sentiment time series, or a co-mention graph
- Mentions a `bd_v2_` API key, `rp_entity_id`, `query_unit`/chunk cost, `bigdata-client`, or "the bigdata MCP isn't enough"

**Key features:**
- One `BigdataClient` exposing both the SDK (search + knowledge graph) and a REST escape hatch (`bd._api.http`) for every `/v1/*` endpoint the SDK never wrapped
- Routing table mapping each question to the right module; `fields_values_to_records()` to flatten `{fields, values}` responses
- Cost discipline: `1 query_unit = 10 chunks`, only chunk-search billed, `ChunkLimit` (never a bare `int`), rerank thresholds, 50%-cheaper batch search, and a `CostModel`/`CostTracker` budget veto
- The "two data faces" guidance — structured financial (works for A-shares via English name/ISIN) vs unstructured Chinese NLP (a data-source-level dead end)
- `rc()` SSL-retry wrapper for the common first-handshake `SSL: UNEXPECTED_EOF`, plus a known-pitfalls reference with reproductions and fixes
- Fail-fast on a missing `BIGDATA_API_KEY` (no plaintext fallback); read-only, never writes/uploads

**Example usage:**
```bash
# Install the suite
claude plugin install daymade-financial@daymade-skills
export BIGDATA_API_KEY=bd_v2_xxxxxxxx

# Then ask Claude naturally
"pull NVIDIA's forward analyst estimates and last earnings surprise from Bigdata"
"give me a daily entity-sentiment series for this ticker"
"the bigdata MCP only gave me a tearsheet — I need the structured fields"
```

**Requirements**: A `bd_v2_` Bigdata.com API key (env var, never hardcoded), `uv`, the official `bigdata-client` SDK in an isolated venv. Optional outbound/WSS proxy only if your network needs one to reach `api.bigdata.com`.

---

### **gangtise-copilot** - Gangtise Investment-Research Suite Installer

> **Install**: `claude plugin install daymade-financial@daymade-skills` (suite-only — invoked as `daymade-financial:gangtise-copilot`)

One-command installer, credential configurator, and diagnostic layer for the full Gangtise (岗底斯投研) OpenAPI skill suite. Installs all 19 official Gangtise skills (data, research, utility), configures accessKey/secretAccessKey with a live auth check, and runs a read-only health diagnostic — solving the suite's core discoverability problem (no public manifest, listing-disabled OBS bucket, two parallel naming lines).

**When to use:**
- The user mentions Gangtise / 岗底斯, or any `gangtise-*` skill
- Setting up Gangtise credentials (accessKey / secretAccessKey)
- Errors like `token is invalid` / `接口地址错误`, or "my gangtise install is broken"
- Routing a data question (research reports, chief-analyst opinions, OHLC, valuation) to the right Gangtise skill

**Key features:**
- `install_gangtise.sh` downloads 4 OBS bundles → extracts 19 skill directories → symlinks them into detected agent skills dirs (Claude Code, OpenClaw, Codex), with `minimal`/`workshop`/`full`/`--only` presets
- `configure_auth.sh` writes one shared XDG credential file (mode 600), runs a live auth call, and symlinks every skill's `.authorization` to it (rotate one file, not 19)
- Read-only `diagnose.sh` reports install state, credential validity, and scoped capability tiers (auth scope vs RAG scope)
- Skill registry routing a data question across the two-dimensional (data tier × operation type) matrix of 19 skills
- Wrapper contract: never vendors/forks upstream files, always re-downloads the canonical OBS artifact, and asks before touching any installed skill

**Example usage:**
```bash
# Install the suite
claude plugin install daymade-financial@daymade-skills

# Then ask Claude naturally
"装一下 gangtise 的所有 skill 并配置好凭据"
"my gangtise skills report token is invalid — diagnose it"
"宁德时代的研报用哪个 gangtise skill 查"
```

**Requirements**: A Gangtise accessKey + secretAccessKey; `bash`, `curl`, network access to the official OBS bucket and `open.gangtise.com`. Works with Claude Code, OpenClaw, and Codex agent layouts.

---

### **llm-wiki-setup** - Co-Create a Personal Investment-Research LLM Wiki

Co-create a personal investment-research LLM Wiki (Andrej Karpathy's pattern) where the user's OWN analysis framework becomes a living CLAUDE.md — built by interviewing them rather than handing over a template. Pure markdown + `[[wikilinks]]`, NO RAG / vector DB (Karpathy's core idea — do not over-engineer). The value is extracting the user's personal investment preferences into THEIR OWN schema, never imposing a standard one.

**When to use:**
- Building a compounding research knowledge base (投研第二大脑 / 投研知识库 / 个人投研 wiki)
- Instantiating Karpathy's LLM Wiki pattern for finance/investing
- Turning a stock-picking, analyst-tracking, or earnings-watching workflow into a structured markdown vault
- Ingesting research reports / earnings calls / expert notes into an existing wiki, or running post-earnings prediction→fulfillment reviews

**Key features:**
- Sharp mechanism-layer vs rule-layer split: the three-level directory + wikilink + lint + git hook scaffold is copyable; the analysis schema is interview-grown, never templated
- `init_vault.py` scaffolds the mechanism layer only (no schema), then an 8-dimension interview builds the user's own CLAUDE.md in their own words
- Anti-corrosion: git hook + `lint-vault.py` keep the vault consistent and fight derived-value drift
- SOPs for ingesting a real source (HITL 5-checkpoint flow) and post-earnings fulfillment reviews
- Runs inline (calls the `analyst-track-record` skill and Bash) and chains into `analyst-track-record` for analyst back-testing — without rebuilding it

**Example usage:**
```bash
# Install the skill
claude plugin install llm-wiki-setup@daymade-skills

# Then ask Claude naturally
"帮我搭一个投研第二大脑"
"build me a personal investment-research wiki in Karpathy's style"
"ingest this earnings call into my research vault"
```

**Requirements**: Python 3, `uv` (for `init_vault.py` / lint), `git`. Markdown + wikilinks only — no vector DB or embedding service. Pairs with the `analyst-track-record` skill for back-testing.

---

### **benchmark-due-diligence** - Adversarial Teardown of an Envied Benchmark

> **Install**: `claude plugin install daymade-financial@daymade-skills` (suite-only — invoked as `daymade-financial:benchmark-due-diligence`)

Run adversarial due-diligence on a benchmark the user envies — a founder, KOL, company, or product whose claimed success looks inflated — separating marketing bubble from real signal, then mapping the validated playbook onto the user's own resources. The adversarial, decision-oriented cousin of `deep-research`: it assumes the picture is inflated until proven otherwise and ends in "what this means for ME", not a neutral report.

**When to use:**
- Wanting to 尽调/对标/拆解 a competitor or role-model, or 抄/偷师 someone's playbook
- Suspecting 水分/泡沫 in someone's claims (#1 on Product Hunt, 0-to-1M users, funding, 估值几个亿)
- Asking whether wins are 真本事 vs 运气/时机, or saying someone is 太成功了 and wanting the real story
- Preferring a debunk + replicable playbook over `deep-research`'s neutral briefing

**Key features:**
- Two strictly-separated injection channels — public FACTS go to every agent; private COMMISSIONER_CONTEXT reaches only the final mapping agent (so client names never leak into open-web searches)
- Phase 0 foundation-by-evidence: verifies the benchmark's real entity graph and headline-claim attribution before any fan-out (don't reason from names/domains)
- Four-phase orchestration — collect → adversarial verify (L1-L4 grading, `坐实/存疑/证伪-水分` verdicts) → due-diligence conclusion (bubble-busting table + attribution breakdown) → commissioner resource-mapping
- Reuses existing plumbing instead of rebuilding it (`deep-research` fan-out, `osint-investigate` identity checks, the `qcc` family for 工商 data, `agent-reach` for social-platform data)
- Runs inline (it's an orchestrator — `context: fork` would silently break the fan-out)

**Example usage:**
```bash
# Install the financial research suite
claude plugin install daymade-financial@daymade-skills

# Then ask Claude naturally
"帮我尽调一下这个创始人，他到底有没有水分"
"tear down this competitor's playbook and tell me what I can actually copy"
"this KOL claims 0-to-1M users — is that real, and is it replicable for me?"
```

**Requirements**: Web access for the collection/verification agents. Optionally composes with `deep-research`, `osint-investigate`, the `qcc` skill family, and `agent-reach`; renders a shareable report via `pdf-creator`.

---

### **bilibili-source** - Login-Free Bilibili Video Data + Danmaku Fetcher

Fetch real, citable data for any Bilibili (B站) video — title, UP follower count, publish date, tags, partition, per-part cids, live stats (view/like/coin/favorite/share/reply/danmaku), and full danmaku (bullet-comment) text — in one `view/detail` call, login-free. Built so engagement numbers are cheap to fetch and impossible to fake, instead of hand-typed into a doc where they rot.

**When to use:**
- Ingesting a Bilibili video into a knowledge base, or building a "why did this perform" case study
- Verifying a creator's claimed view/like/favorite numbers, or about to write any B站 metric into a document
- Wanting the danmaku text (qualitative audience reactions), not just a reply count
- Pasting a BVID, `av` number, `b23.tv` short link, or full URL — all normalized automatically

**Key features:**
- One `bili-fetch.sh` returns full metadata + live stats + UP fans + tags + every part's cid; metrics carry a `fetched_at` timestamp because they drift in real time
- `bili-danmaku.sh` pulls and decompresses the danmaku full text; `bili-subs.sh` handles the login-gated subtitle track (asks before touching browser cookies)
- `bili-selftest.sh` health-check verifies every endpoint against the live API, so API drift surfaces as one clear FAIL instead of a silent wrong answer
- NO-FABRICATION discipline: an unfetchable number is marked unverified, never estimated
- Strips the local proxy (Bilibili is a domestic CN service), sends UA+Referer (avoids HTTP 412), retries with backoff
- API reference includes the login-gated favorites (收藏夹) enumeration endpoints (`x/v3/fav/*`, verified no-WBI), the verified SESSDATA subtitle path, and the WBI request-signing algorithm for `space/wbi/*` extension

**Example usage:**
```bash
# Install the skill
claude plugin install bilibili-source@daymade-skills

# Then ask Claude naturally
"pull the real view/like/favorite counts for this B站 video so I can cite them"
"这个 B站 视频弹幕里大家在说什么？"
"grab the subtitle transcript from this bilibili video so I can summarize it"
```

**Requirements**: `curl`, `jq`, `python3` (danmaku decompression). `yt-dlp` only for the login-gated subtitle path. No login for stats / metadata / danmaku.

---

### **claude-usage-analyst** - Explain Claude Code Token Usage & Quota Burn

> **Install**: `claude plugin install daymade-claude-code@daymade-skills` (suite-only — invoked as `daymade-claude-code:claude-usage-analyst`)

Turn local `ccusage` data into an evidence-based, human-readable explanation of where your Claude Code / Claude Desktop tokens, cost, and quota went — separating observed numbers from interpretation instead of guessing.

**When to use:**
- Asking why a Claude quota or 5-hour block got exhausted
- Wondering whether a model (`fable` / `opus` / `sonnet`) is unusually expensive for your workload
- Needing today's or a historical window's token/cost breakdown, including cache read/write pressure
- Explaining usage to a non-technical reader without unexplained jargon

**Key features:**
- Bundled `analyze_claude_usage.py` summarizes tokens, cost, input/output, and cache create/read over any date window and timezone
- Model-comparison mode (`--model-a` / `--model-b`) weighs both token volume and estimated cost — a model can be cheap per token but expensive overall
- A 5-hour-block table for quota-exhaustion questions
- Evidence discipline: every numeric claim is grounded in `ccusage` output; cache-read pressure is counted even when you never typed those tokens
- Scope is stated explicitly: `ccusage claude` measures local Claude Code logs, not a full Claude.ai chat bill

**Example usage:**
```bash
# Install the suite
claude plugin install daymade-claude-code@daymade-skills

# Then ask Claude naturally
"why did my Claude quota run out today?"
"is opus more expensive than sonnet for what I'm doing?"
"break down my Claude Code token usage for this month"
```

**Requirements**: `ccusage` (via `npm i -g ccusage` or `npx ccusage@latest`), `python3`.

---

### **marketplace-health-check** - Full 6-Dimension Repo Health Check

```bash
claude plugin install marketplace-health-check@daymade-skills
```

Run a comprehensive, evidence-based health check of this skills marketplace repo with a parallel fan-out Dynamic Workflow — six inspectors cover code/script safety, documentation/SSOT consistency, security/PII leaks, open-PR triage, open-issue triage, and marketplace-manifest integrity at once — then the serious findings are Counter-Reviewed before they reach the report.

**When to use:**
- Before a release, or any time you want a full "is this whole repo OK across the board" sweep
- Checking whether docs/versions are consistent, PRs/issues are triaged, or PII has leaked into a public skill
- 全面体检 / 检查仓库状态 / 审计一下仓库

**Key features:**
- Six parallel inspectors (one per dimension) via a Dynamic Workflow — fast and focused (~15-20 min)
- Counter-Review: every high/critical finding is verified by hand before it reaches the report (agent findings are hypotheses, not conclusions) — catches false alarms AND wrong fixes
- Priority-ranked report: must-fix / backlog / optional / key insights, each item tagged real vs false-alarm
- Bundles the proven workflow script + a methodology reference (anti-target PII rule, working-copy-vs-history, scan-marker necessary-not-sufficient, the broken-install-command bug class)
- Inline orchestrator — drives the Workflow tool, so it never runs forked

**Example usage:**
```bash
# Install
claude plugin install marketplace-health-check@daymade-skills

# Then ask Claude naturally
"do a full health check of this repo before I cut a release"
"audit the marketplace — code, docs, PII, PRs, issues, everything"
"全面体检一下这个仓库"
```

**Requirements**: `gh` CLI (authenticated), `git`, `jq`, `python3`; opt-in to the Workflow tool (asking to run the health check is the opt-in).

---

### **claude-switch-models-setup** - Multi-Provider Claude Code Profiles

```bash
claude plugin install daymade-claude-code@daymade-skills
```

Set up multiple isolated Claude Code CLI profiles so you can run different LLM providers (Kimi, MiniMax, GLM, DeepSeek, StepFun, Anthropic) in separate terminal windows at the same time — each profile gets its own `.claude.json` state while sharing skills, projects, hooks, and agents.

**When to use:**
- You want one terminal with Kimi and another with DeepSeek running side-by-side
- You need to switch between Anthropic and third-party models without config bleed
- You're setting up a post-workshop environment for students who want the same multi-provider workflow

**Key features:**
- One-click installer links its declared runtime scripts into `~/.config/claude-switch-models-setup/` and seeds an empty Codex activation manifest only when none exists
- Includes provider-specific `~/.claude/settings/<provider>.json` templates with required isolation flags
- `claude-profiles-init` creates isolated `~/.claude-profiles/<provider>/` directories with symlinked shared resources
- Profile sync mirrors enabled plugins from the default Claude profile and shares installed plugin state
- Local source sync keeps Claude plugin caches source-backed, but links only the explicit Codex selection into `~/.agents/skills`; a declared active subset may keep legacy `~/.codex/skills` compatibility links
- A maintainer LaunchAgent watches the activation manifest and marketplace/install topology, while reporting non-compatible legacy links for reviewed cleanup instead of deleting them
- Built-in marketplace path pollution fixer runs automatically on every profile launch
- Includes student setup guide and troubleshooting reference

**Example usage:**
```bash
# Install the suite
claude plugin install daymade-claude-code@daymade-skills

# Then ask Claude naturally
"set up Claude Code profiles for Kimi and DeepSeek"
"I want to run Kimi and Anthropic in separate terminals"
"install the multi-provider profile setup from the workshop"
```

**Requirements**: `claude` CLI, `zsh` or `bash`, `python3`, plus API keys for the providers you want to use.

---

### **llm-eval-harness** - Four-Dimension LLM Endpoint Evaluation

```bash
claude plugin install llm-eval-harness@daymade-skills
```

Evaluate any LLM behind an OpenAI- or Anthropic-compatible endpoint across four dimensions — instead of trusting a vendor's headline numbers — and report measured results separately from inferred ones.

**When to use:**
- Benchmarking a model, or verifying a vendor's tokens-per-second claim
- Comparing two models head-to-head under identical conditions
- Vetting a newly released or "Anthropic-compatible" endpoint before adopting it
- Probing concurrency limits before a workshop or batch job

**Key features:**
- **Four dimensions, four scripts**: speed (`speed_probe.py` — TTFT + thinking-aware tokens/sec), concurrency/stability (`concurrency_probe.py` — success rate, p50/p90, breaking point), Anthropic protocol compliance (`protocol_probe.py` — thinking-block trigger rate over N≥10), and quality regression (`usecase_runner.py` + independent blind judges)
- **Thinking-aware throughput**: captures `reasoning_content` separately so reasoning tokens don't inflate tok/s (the trap that once read a ~750 tok/s model as 4700)
- **Probabilistic protocol verdicts**: `fully-implemented` / `intermittent (k/N)` / `not-implemented`, never concluding from a single sample, with `Connection: close` so a load balancer can't pin all samples to one replica
- **Blind-judge quality**: 3 independent judges per case, majority-pass, with per-category precision to surface a systematically weak category
- **Keys via env-var name only** (`--key-env MY_KEY`) — the key never appears in `ps`, shell history, or a saved report
- **Your use-case library lives outside the bundle** (e.g. `~/.llm-eval/usecases.json`) so it survives skill updates and never lands in a public repo

**Example usage:**
```bash
export MY_KEY=sk-...   # the key never appears in a command below

# Speed: real-task throughput + sustained decode ceiling
uv run --with openai python scripts/speed_probe.py \
  --base-url https://api.example.com/v1 --model some-model --key-env MY_KEY --mode both

# Concurrency: ramp until it breaks
uv run --with aiohttp python scripts/concurrency_probe.py \
  --url https://api.example.com/v1/chat/completions --model some-model \
  --key-env MY_KEY --format openai --concurrency 10 20 40 60
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [llm-eval-harness/references/evaluation_disciplines.md](./llm-eval-harness/references/evaluation_disciplines.md) for the reasoning behind each discipline and [llm-eval-harness/references/quality_blind_judge.md](./llm-eval-harness/references/quality_blind_judge.md) for the blind-judge method.

**Requirements**: Python 3.8+, `uv`; `openai` and `aiohttp` (auto-installed via `uv run --with`); an API key for the endpoint under test. Optionally composes with **promptfoo-evaluation** for rubric-based gating.

---

### **read-claude-web-conversation** - Extract Claude.ai Web Conversations

> **Install**: `claude plugin install daymade-claude-code@daymade-skills` (suite-only — invoked as `daymade-claude-code:read-claude-web-conversation`)

Extract the complete active Claude.ai conversation through the Claude Code
operations suite: message text, real tool calls and outputs, uploads, generated
images, and sandbox deliverables. Render faithful Markdown locally, reconstruct
files created through tool calls, or download original bytes through the
logged-in browser session.

**When to use:**
- Reading a Claude.ai web conversation that is not available in local Claude Code logs
- Recovering a full web thread for handoff, audit, or archival
- Comparing browser-visible content with exported or local session artifacts
- Preserving the analysis trace from agent conversations whose tool calls are collapsed in normal exports
- Downloading uploads and assistant-produced files that belong to the active conversation branch
- Using the macOS AppleScript channel when the Chrome extension is paired to a different account

**Requirements**: Installed `daymade-claude-code` suite and a logged-in Chrome
session. The AppleScript fallback requires macOS and one user-enabled Chrome
developer-menu toggle.

---

### **setup-notifications-via-wecom** - Reusable WeCom Notification Setup

```bash
claude plugin install setup-notifications-via-wecom@daymade-skills
```

Set up reusable WeCom (Enterprise WeChat) webhook notifications for technical status reports, alerts, and completion messages. The target is explicitly classified: the user's own channel may send automatically; every other target requires human confirmation.

**When to use:**
- Configuring a reusable 企业微信 / WeCom notification channel
- Sending structured status notifications, backup reports, or alerts
- Turning a one-off webhook into a repeatable notification workflow

**Requirements**: WeCom bot webhook URL and shell access.

---

### **notify-wecom** - One-Off WeCom Message

```bash
claude plugin install notify-wecom@daymade-skills
```

Send a single WeCom group-bot message using the configured target identity: `self` sends directly, while `others` requires human confirmation.

**When to use:**
- `/notify-wecom`
- 临时发一条企业微信 / 企微通知一下
- One-shot alerts that do not need templates or persistent setup

**Requirements**: WeCom bot webhook URL plus the explicit recipient scope/label and canonical sender binding created by the setup command.

---

### **github-sensitive-data-cleanup** - GitHub Sensitive Data Cleanup

```bash
claude plugin install github-sensitive-data-cleanup@daymade-skills
```

Scan and remove sensitive data from GitHub repository history, with backup, visibility checks, and force-push safety gates.

**When to use:**
- A repo leaked secrets, private domains/IPs, API keys, or PII
- Cleaning git history before or after a public exposure
- Verifying safety before any force push to a public repository

**Requirements**: `git`, GitHub access, and the relevant scanning/history-rewrite tools for the target repository.

---

### **codex-image-gallery** - Local Browser for Codex Generated Images

> **Install**: `claude plugin install daymade-codex@daymade-skills` (suite-only — invoked as `daymade-codex:codex-image-gallery`)

Start a self-contained local web gallery for Codex-generated image outputs. The skill bundles its Node server and HTML UI, scans `~/.codex/generated_images` by default, and can point at another folder with `GALLERY_ROOT`.

**When to use:**
- Browsing Codex generated images in a local UI
- Inspecting `~/.codex/generated_images`
- Reviewing a custom image output directory with search, batches, and image detail view

**Key features:**
- Bundled `scripts/server.mjs` and `assets/index.html`
- Dynamic `/api/images` scan; no hardcoded manifest
- `/images/<relative-path>` image route with path traversal protection
- Optional `GALLERY_ROOT`, `PORT`, and `HOST`

**Requirements**: Node.js 18+ and access to the image folder.

### **frontend-visual-qa** - Rendered Frontend and Browser Output Visual QA Gate

```bash
claude plugin install frontend-visual-qa@daymade-skills
```

Audit the UI users can actually see, with explicit evidence levels and no source mutation by default.

**When to use:**
- Auditing an already-rendered web or desktop UI after implementation
- Diagnosing typography, wrapping, clipping, overflow, responsive, route/state, overlay, map, or transient-state defects
- Comparing a rendered artifact with a named visual reference or design-system SSOT
- Verifying export, download, share, popup, print/PDF, or Electron-shell behavior at the evidence level the claim requires
- Complementing `ui-designer`/design work and the broader process managed by `qa-expert`

**Key features:**
- Audit-only default with scoped profiles and verified / partial / blocked outcomes
- A–D evidence ladder that prevents headless, renderer-only, or handler-only checks from masquerading as real GUI proof
- State/viewport-first workflow, including authenticated-but-role-less branches and exact projection/deck canvases, plus inspected screenshots and DOM geometry
- Hardened Playwright-powered sweep for navigation status, effective mobile viewport, overflow, clipping, custom-control focusability, images, and section evidence
- Conditional references for core visual checks, complex journeys/page contracts, and data visualization—including units/source/time/freshness, dense collisions, runtime-label truth, and real file-dialog boundaries
- Public behavior and trigger evals with self-contained fixtures

### **openclaw** - OpenClaw (龙虾) Config Manager

```bash
claude plugin install openclaw@daymade-skills
```

Manage OpenClaw (龙虾/lobster) instance configurations — audit, diff, copy, add-model, list, and switch models across `openclaw.json` files.

**When to use:**
- Managing multiple OpenClaw / Claude Code wrapper instances
- Applying DeepSeek model patches to an instance
- Auditing, diffing, or copying provider/model config between instances
- Managing default models and aliases, or validating config

**Key features:**
- Unified CLI: audit / diff / copy / add-model / list / switch
- Auto-audit on mutating commands with a `--no-audit` escape hatch
- Nickname registry for cross-config operations

### **download-gemini-images** - Download Images from Gemini Conversations

```bash
claude plugin install download-gemini-images@daymade-skills
```

Download images (uploaded files or generated previews) from a Google Gemini conversation page using your logged-in Chrome session, then package them into an ordered ZIP.

**When to use:**
- Saving images from a Gemini chat/app page (uploaded or generated previews)
- Need the larger lightbox image, not the thumbnail
- Renaming downloaded images in order and producing a ZIP archive

**Key features:**
- Lightbox-first download via the Chrome plugin (uses your existing Google session)
- `pageAssets` fallback when lightbox automation fails
- Ordered ZIP packaging with integrity verification

### **wps-doc-scraper** - Archive Public WPS/KDocs Documents

```bash
claude plugin install wps-doc-scraper@daymade-skills
```

Faithfully archive public WPS / KDocs / 金山文档 links — especially embedded ProcessOn mind maps and canvases — as raw source data, original SVG/PNG, and Markdown, without logging in.

**When to use:**
- Given a `kdocs.cn` or `wps.processon.com` link to scrape, save, download, or convert to Markdown
- Archiving an embedded ProcessOn mind map or canvas with source fidelity
- Need the raw payloads + original visual artifact, not just rendered text

**Key features:**
- Unauthenticated data-API-first extraction (no login, no account save)
- Original SVG/PNG capture for canvases and mind maps
- Markdown as a structured representation of the source

### **ashare-news-fetcher** - A-Share Market News & Sentiment Aggregator

> **Install**: `claude plugin install daymade-financial@daymade-skills` (suite-only — invoked as `daymade-financial:ashare-news-fetcher`)

Aggregate A-share (Chinese stock market) news, policy, and sentiment from public sources — 财联社, 华尔街见闻, 金十, 新浪 7x24, 东财快讯, regulator announcements (CSRC / PBoC / SSE), 东方财富股吧 — into structured JSON or Markdown.

**When to use:**
- Need recent news/policy/sentiment for a specific A-share stock or the whole market
- Aggregating 消息面 intel from multiple Chinese financial sources at once
- Producing a structured JSON or Markdown news digest

**Key features:**
- Multi-source public-feed aggregation (no login)
- Per-stock or market-wide filtering
- Structured JSON / Markdown output

### **local-codex** - Local OpenAI Codex CLI Agent

> **Install**: `claude plugin install daymade-codex@daymade-skills` (suite-only — invoked as `daymade-codex:local-codex`)

Delegate coding tasks to the local OpenAI Codex CLI agent using your ChatGPT Pro OAuth flat-rate subscription. Wraps `codex exec` / `codex review` for code generation, refactoring, and review without per-token API charges.

**When to use:**
- Delegating coding tasks to Codex for generation, refactoring, or review
- Running `codex exec` for non-interactive coding tasks
- Using Codex's GPT-5.5 agent capabilities through local CLI

**Key features:**
- ChatGPT Pro OAuth flat-rate billing via `~/.codex/auth.json` (no API keys)
- Auto-detects Codex CLI from desktop app, Homebrew, npm, or PATH
- JSONL output parsing with final assistant message extraction
- Configurable sandbox levels: read-only / workspace-write / danger-full-access

### **openclaw-model-switch** - OpenClaw Model Switcher

```bash
claude plugin install openclaw-model-switch@daymade-skills
```

Switch the default AI model for an OpenClaw instance (e.g., Kimi K2.6 → K2.7) by safely editing `openclaw.json` with automatic backup, model validation, and optional gateway restart.

**When to use:**
- Upgrading to a newly released model
- Switching between models for different tasks
- Rolling back after testing a new model

**Key features:**
- Automatic config backup before changes
- Model validation against provider's model list
- Optional gateway restart after switching
- Supports Kimi K2.x model family with context window specs

### **pharma-daily-report** - A-Share Pharma Sector Daily Report

> **Install**: `claude plugin install daymade-financial@daymade-skills` (suite-only — invoked as `daymade-financial:pharma-daily-report`)

Generate an A-share pharmaceutical sector daily report — pull real-time quotes for core pharma stocks from Sina Finance, rank 7 sub-sectors, top gainers/losers, and estimated fund flow, then optionally push a rich-text report via Feishu.

**When to use:**
- Need a daily snapshot of the A-share pharma sector (quotes, sub-sector ranking, fund flow)
- Want a Feishu rich-text push of pharma market data
- Tracking a configurable watchlist of core pharma stocks

**Key features:**
- Sina Finance real-time quote pipeline (no login)
- 7 sub-sector classification + gainers/losers + fund-flow estimate
- Optional Feishu rich-text delivery; default 20-stock watchlist, customizable

### **gemini-history-analyzer** - Analyze Gemini Conversation History

> **Install**: `claude plugin install gemini-history-analyzer@daymade-skills`

Analyze Google Takeout exports of Gemini conversation history — extract and categorize transcripts and attachments, mine them for domain-specific insights with context-verified keyword search, and optionally distill findings into a personal knowledge base.

**When to use:**
- Have a Gemini Takeout zip and want to know what's in it (topics, conversation type, valuable documents)
- Want to mine Gemini history for a specific domain (finance, legal, etc.) without drowning in keyword false positives
- Distilling Gemini conversation data into project memory or a personal wiki

**Key features:**
- Handles Chinese/Unicode filenames (uses `unar`, not the corrupting macOS `unzip`)
- Meeting-transcript vs prompt-response detection; topic categorization; PII flagging
- Context-verified keyword search (grep is step 1, not the answer) + optional memory-file generation

### **skill-governance** - Real Skill-Surface Governance

> **Install**: `claude plugin install daymade-skill@daymade-skills` (suite-only — invoked as `daymade-skill:skill-governance`)

Govern the Skill surface Claude Code and Codex actually expose without losing cold capability. It separates canonical source, installed inventory, discovery policy, the fresh model-visible catalog, and router-resolved runtime resources.

**When to use:**
- Codex reports many Skills, truncated descriptions, duplicate identities, or a missing router
- A Skill appears stale, missing, duplicated, or installed from an unexpected source/version/scope
- Need to reconcile owned source links under `~/.agents/skills` without treating every disk bundle as active
- A merged suite migration left old standalone plugin identities installed locally
- A third-party bundle must stay on disk for runtime resources while only its router remains visible to Codex

**Key features:**
- Compares the actual fresh Codex prompt with complete metadata from Codex's own `skills/list`, detecting truncation, omitted enabled entries, identity/source collisions, disabled-path drift, scan errors, and missing direct activation entries
- Treats owned source as canonical, plugin caches as derived runtime state, and preserves current install scope
- Routes source-backed activation to its explicit manifest owner instead of mixing third-party inventory into it
- Discovers suites dynamically from the manifest and verifies the replacement suite before retiring standalone installs at their original scopes
- Keeps third-party bundles as cold disk inventory through exact-path Codex discovery policy, then verifies both the clean prompt catalog and preserved runtime resources
- Leaves Claude's versioned orphan-cache lifecycle to Claude; manual cache removal is exceptional, recoverable repair rather than routine cleanup

### **photo-to-scanned-pdf** - Phone Photos to Scanner-Quality PDF

> **Install**: `claude plugin install daymade-docs@daymade-skills` (suite-only;
> invoke as `daymade-docs:photo-to-scanned-pdf`)

Turn phone photos of contracts, receipts, forms, certificates, or handwritten
pages into a clean A4 PDF. The workflow combines perspective correction,
scanner-style background cleanup, colored-paper handling, explicit content-based
page ordering, and a mandatory whole-document contact-sheet check.

### **github-review-pr** - Current-Base Contributor PR Review

```bash
claude plugin install github-review-pr@daymade-skills
```

Review or re-review one named contributor PR—including a closed PR under
reconsideration—or sweep every open PR newest-to-oldest as a repository maintainer,
always against the live base rather than a stale PR snapshot.

**When to use:**
- Main/base changed after an earlier review and the PR needs a fresh decision
- A specifically named closed PR needs a merit review or reconsideration
- Need to distinguish PR-owned defects from pre-existing base debt
- Need to know what the actual three-way merge would land now
- Need a newest-to-oldest decision ledger for the complete open-PR queue
- Need a review-gated repair or merge, with every GitHub write explicitly authorized
- Want the opt-in personal policy to learn from prior closed-PR decisions, enforce the
  maintainer's curation bar, or decide whether worthy original contributor PRs should
  be repaired instead of recreated

**Key features:**
- Separates PR-recorded base, current base, and head OIDs, then rechecks them before the verdict
- Reviews the prospective merge tree when clean, or isolated intent plus conflict stages when no landing tree exists
- Detects ordinary base drift versus history discontinuity, then separates polluted
  branch history from the contributor's verified intended patch
- Can project that verified patch onto current base for analysis while labeling the
  result synthetic and non-landable
- Requires target code, tests, runtime behavior, logs, or repository specification for
  findings; reviewer concurrence raises confidence, not severity
- Attributes every finding as `PR`, `BASE`, or `SHARED` before assigning repair ownership
- Distinguishes a curation `DECLINE` from a fix request or true supersession
- Keeps review read-only by default; repair, review posts, close, merge, admin, auto-merge, and branch deletion remain separate actions
- Treats external-contributor program goals only as a post-merit priority, never a reason to lower the acceptance bar
- Requires one fresh, context-bound confirmation for the single surfaced PR before
  merge; a short affirmative reply is accepted without carrying authority to the next PR

**Example usage:**
```text
/github-review-pr --personal-maintainer https://github.com/<owner>/<repo>/pull/<number>
/github-review-pr --personal-maintainer --all-open
main changed since the last review; tell me what would actually land now
review all of our open PRs newest to oldest and apply my prior maintainer principles
can we merge this contribution and fix the remaining repo bookkeeping ourselves?
```

**Requirements**: authenticated `gh` CLI, `git` with `merge-tree --write-tree`, and `jq`.

### **read-codex-history** - Read Local Codex History

> **Install**: `claude plugin install daymade-claude-code@daymade-skills`
> (suite-only — invoked as `daymade-claude-code:read-codex-history`)

Read, search, and export local Codex history without continuing the old task.
It keeps the prompt ledger, state database, and rollout JSONL as three distinct
evidence surfaces so exact user input, inventory metadata, and Agent behavior are
never silently substituted for one another.

**Key features:**
- Lists Codex sessions with internal time ranges and active/archive provenance
- Extracts exact prompt-ledger inputs newest-first and groups them only by Session
- Reconstructs one rollout as a chronological user/assistant timeline with exact fork byte boundaries and compacted context
- Searches Codex rollouts only; it cannot silently mix Claude matches into a Codex request
- Selects a compatible Codex state database through schema introspection
- Visibly falls back to raw Codex rollout JSONL when the database is unavailable
- Requires internal `session_meta.id` equality and reports fused/missing rollout gaps instead of guessing
- Probes every in-scope Codex session and appends any row whose exact canonical
  writer-lock file is held even beyond the recent-row limit; the marker proves
  lock state, not holder identity or a running agent, and an unmarked row is
  never reported as stopped or safe to retire
- Supports internal-time date windows, custom exact-scope diagnostics, archived
  Codex threads, recursive/all-project scopes, Windows path normalization, and JSON
- Uses Python's standard library only; performs no network requests or writes

**Example usage:**
```text
/daymade-claude-code:read-codex-history
list the recent Codex chats for this folder
show my 200 most recent original Codex inputs, grouped by Session
read Codex Session 01abc... chronologically and show its fork lineage
show which Codex sessions in this workspace have held canonical writer-lock files
show Codex threads including archived conversations as JSON
```

📚 **Documentation**: See
[storage_and_portability.md](./daymade-claude-code/read-codex-history/references/storage_and_portability.md)
for source selection, path normalization, privacy boundaries, and diagnostics.

**Requirements**: Python 3.10+; no third-party packages or network access.

---

### **continue-codex-work** - Resume Interrupted Codex Work

> **Install**: `claude plugin install daymade-claude-code@daymade-skills`
> (suite-only — invoked as `daymade-claude-code:continue-codex-work`)

Continue a prior Codex task without replaying it through `codex resume`.
The Skill first requires `read-codex-history` to prove selected identity, fork
lineage, chronology, compacted context, and gaps; it then rebuilds the original
business outcome, unfulfilled requests, user corrections, proven assets, and one
direct next action before changing the project.
It is for a new/different Agent context taking over an earlier rollout. When
Codex itself natively resumes the same conversation and prior context is already
present, continue directly instead of invoking this Skill.

```text
/daymade-claude-code:continue-codex-work 019f66...
Codex was cut off mid-task; recover that rollout and finish the work
```

📚 **Documentation**: See
[continue-codex-work/SKILL.md](./daymade-claude-code/continue-codex-work/SKILL.md).

**Requirements**: Python 3.10+ and local Codex rollout files.

---

### **git-safety-net** - Prevent & Recover From Local-Git Disasters

> **Install**: `claude plugin install git-safety-net@daymade-skills`

Prevent and recover from the branch/stash/rebase tangles that strand or lose local
commits, detached or dirty worktrees, and answer "is everything actually merged?" with
content-level proof instead of misleading commit counts. Every command is non-destructive or
additive until a step is explicitly labeled destructive.

**Key features:**
- Recovers deleted commits/branches/stashes via `git reflog` and `git fsck` (the ~90-day window)
- Audits every linked worktree HEAD, dirty checkout, local-only commit, stash, and dangling commit
- Pins dangling commits gc-proof under `refs/dangling-backup/` before any cleanup
- Verifies a branch is merged by CONTENT — defeating the squash-merge "100 commits ahead" illusion
- Proves a linked worktree safe before non-forced removal and exports all refs in one verified bundle
- Optional adversarial multi-agent verification for a high-stakes "is everything merged?" call
- Catches another session's commit adopted onto your branch before it ships inside your PR
- Settles "did my push/merge actually land?" by content when the receipt was lost to a flaky network
- Prevention habits: commit before switching, push WIP early, audit every checkout before deletion

**Example usage:**
```text
/git-safety-net
did I lose any commits after all that branch switching?
is everything merged into main, or is something still stranded?
recover the commit I lost after a bad rebase
prove this worktree can be deleted without losing anything
```

📚 **Documentation**: See
[recovery_playbook.md](./git-safety-net/references/recovery_playbook.md),
[merge_verification.md](./git-safety-net/references/merge_verification.md), and
[prevention_practices.md](./git-safety-net/references/prevention_practices.md).

**Requirements**: Git and a standard Bash shell. No third-party packages; current remote status
requires network access, while offline audits use cached remote-tracking refs.

---

### **design-style-picker** - Batch-Compare Visual Design Directions

> **Install**: `claude plugin install daymade-codex@daymade-skills` (suite-only — invoked as `daymade-codex:design-style-picker`)

Turn vague taste into concrete visual choices. Instead of guessing one final design,
batch-generate a structured set of visual directions so the user picks the style they
actually want — the goal is exposing the taste boundary quickly, not reading minds.

**Key features:**
- Batch-generates and compares multiple design directions side by side
- For users who cannot describe an abstract visual style in words
- Works from generated UI / design-system images; rejects "too colorful / too dead / too generic" with more options
- Evolves an existing UI or design system without discarding current assets
- Ships a selection playbook and reusable prompt patterns

**Example usage:**
```text
/daymade-codex:design-style-picker
I can't describe the style I want — show me a batch of options
this draft is too colorful and too generic, generate more directions
evolve our current design system without throwing away existing assets
```

📚 **Documentation**: See [selection-playbook.md](./daymade-codex/design-style-picker/references/selection-playbook.md).

---

### **claude-migrate-memory-to-doc** - Migrate Claude Memory to Tool-Agnostic Docs

> **Install**: `claude plugin install daymade-claude-code@daymade-skills`
> (suite-only — invoked as `daymade-claude-code:claude-migrate-memory-to-doc`)

Migrate Claude Code personal memory (the per-project `memory/` directory) into
tool-agnostic reference docs, so other AI CLIs that auto-load `AGENTS.md` (Codex
primarily; the architecture transfers to Cursor and others) working in the same
directory read the same user profile and collaboration preferences instead of being
blind to them.

**Key features:**
- Solves tool lock-in: memory is not version-controlled and is invisible to every non-Claude tool
- Two-layer architecture: `references/` + CLAUDE.md-inline + AGENTS.md-symlink, designed around
  what each tool actually auto-loads (plain-text pointers are on-demand in both tools)
- Full workflow: diagnosis, multi-agent review, empirical `codex` verification, and memory cleanup
- Leaves memory as a thin handoff cache instead of the SSOT
- Runs inline, orchestrating review subagents and invoking `codex` directly

**Example usage:**
```text
/daymade-claude-code:claude-migrate-memory-to-doc
migrate my memory — Codex doesn't know who I am
my memory is locked to Claude Code, make it tool-agnostic
memory has grown bloated with content that should live in docs
```

---

### **docx-creator** - Produce Production-Grade Word Documents

> **Install**: `claude plugin install daymade-docs@daymade-skills`
> (suite-only — invoked as `daymade-docs:docx-creator`)

A thin incremental layer over `minimax-skills:minimax-docx` — not a document
engine itself. Adds the layer the underlying OpenXML engine doesn't ship: a
verified markdown-to-docx generator for Chinese formal documents, the
alignment-layering rule that stops justified text from stretching 甲方/乙方
info blocks and signature blocks into garbage, per-list numbering restart,
CJK font dual-slot setup, and a mandatory LibreOffice-to-PDF-to-PNG visual
verification chain (qlmanage thumbnails are banned — they hide exactly the
bugs that matter).

**Key features:**
- Division of labor: the OpenXML SDK engine stays in `minimax-docx`; this skill owns Chinese formal-document typography rules and the CLI-vs-C# routing decision
- Verified markdown-to-docx generator (`scripts/Program.cs`) for contracts, agreements, and 公文 with 甲乙方 info blocks, numbered clauses, signature blocks, and tables
- Mandatory real-render visual verification (LibreOffice → PDF → PNG), not a Quick Look thumbnail
- Routes plain prose to the minimax-docx CLI instead of duplicating it

**Example usage:**
```text
/daymade-docs:docx-creator
生成 Word 文档
写合同 docx
把 markdown 转成 Word
give me a Word file for this labor contract
```

---

### **read-docx-review** - Read Word/WPS Review Comments & Tracked Changes

> **Install**: `claude plugin install daymade-docs@daymade-skills`
> (suite-only — invoked as `daymade-docs:read-docx-review`)

Read a reviewed docx (Word/WPS) and extract every comment and tracked change into
a per-item adjudication table (markdown or JSON): who commented, on which
paragraph, what they said, plus revision-mode insertions and deletions.
Revision-aware engine on the OpenXML SDK, so content inserted via track changes
(w:ins) and paragraph-level deletions (w:del) that a bare python-docx read
silently misses are captured. Read-only — never mutates the reviewer's file.

**Key features:**
- Per-item adjudication table with a blank disposition column, built for clause-by-clause triage
- Captures the w:ins / w:del revisions that python-docx silently drops
- WPS reference-only comment anchors get a fallback so every comment stays locatable
- Zero-comment files emit an explicit "no review traces" warning instead of a silent empty table
- Boundary: producing/formatting docx → docx-creator or minimax-docx; PDF annotations out of scope

**Example usage:**
```text
提取这份 docx 的批注
对方批注完的合同回来了，读一下审阅意见
读一下修订，谁批了什么、批在哪
```

---

### **claude-code-hooks** - Write, Test, and Debug Claude Code Hooks

> **Install**: `claude plugin install daymade-claude-code@daymade-skills`
> (suite-only — invoked as `daymade-claude-code:claude-code-hooks`)

How to write, test, register, and debug Claude Code hooks — PreToolUse /
PostToolUse / SessionStart / Stop Bash guards that enforce a rule the model
would otherwise talk itself past. A prose rule in CLAUDE.md is a suggestion
the completion drive can override; a hook is a wall.

**Key features:**
- Five runnable pattern skeletons — PreToolUse block, human-confirmation release gate, SessionStart health check, PostToolUse context injection, and a Stop hook that reacts to the model's own output — plus the shlex command-position walker for token-level command matching
- Four hard-won rules: shlex over awk-splitting so a healthy command is never false-blocked, `bash -n` + real-JSON end-to-end testing before registering, SSOT + symlink so a reinstall can't silently disarm a guard, and per-profile registration convergence with human-confirmation release gates
- Nine cataloged failure modes with symptom → cause → fix, including the UserPromptSubmit-vs-Stop category mistake (only Stop can see what the model itself wrote) and a literal quote/backtick inside a Python comment silently corrupting an embedded `python3 -c` block
- Bundled end-to-end test harness (`scripts/test_hook.sh`)

**Example usage:**
```text
/daymade-claude-code:claude-code-hooks
make a hook that blocks git push --force
turn this rule I keep forgetting into a hard gate
my hook is false-blocking a healthy command
debug this hook that's poisoning my session
```

### **macos-watchdog** - Design & Discipline macOS launchd Watchdogs

> **Install**: `claude plugin install daymade-macos@daymade-skills` (suite-only — invoked as `daymade-macos:macos-watchdog`)

Design, deploy, and discipline macOS launchd watchdogs — LaunchAgents /
LaunchDaemons that detect a recurring problem and auto-remediate it, without
the watchdog itself becoming the disturbance. Distilled from 15 production
watchdogs and their incident history.

**Key features:**
- The quiet-watchdog contract — premise-state self-check (a monitor's lifecycle binds to its premise), patient mode (defer disruption, not detection), escalating auto-cooldown, and never-resurrect-what-the-user-quit
- Deploy mechanics that bite — gui vs system domain, StandardOut/ErrorPath, TCC/FDA on the actual interpreter, and stop semantics (`unload` is deprecated and gets resurrected by `RunAtLoad` — bootout/bootstrap/disable only)
- Batch-loop throttling by default and SRE alert layering (page vs ticket, fatigue numbers)
- Bundles `watchdog-cooldown.sh` (source-able escalating cooldown + manual pause state machine), `new-launchagent.sh` (idempotent installer with validation), and an annotated plist template

**Example usage:**
```text
make a launchd watchdog that reconnects my VPN when it drops
my watchdog keeps re-launching an app I quit — make it stop
audit my existing LaunchAgents for noise and crash loops
```

### **devils-advocate** - Pressure-Test an Investment Thesis

> **Install**: `claude plugin install daymade-financial@daymade-skills`
> (suite-only — invoked as `daymade-financial:devils-advocate`)

Structured devil's-advocate pressure-testing of an investment thesis against
user-supplied evidence materials — evidence-anchored dissent, not role-played
contrarianism (every counterpoint must cite, verbatim).

**Key features:**
- Decomposes the thesis into explicit assertions and implicit assumptions (fact/forecast/mechanism typing, load-bearing test)
- Retrieves counter-evidence per assumption under a source-credibility ladder with verbatim citations, plus a Mauboussin base-rate outside view bounded to your materials
- Emits an auditable findings JSON and a theme-grouped analyst narrative, and converts the critique into a RAND-style signpost monitoring list

**Example usage:**
```text
/daymade-financial:devils-advocate
stress-test my bull case on <stock> against these three research reports
what would have to be true for this thesis to be wrong?
```

### **daymade-sector-research** - A-Share Sector Research Workflow

> **Install**: `claude plugin install daymade-financial@daymade-skills`
> (suite-only — invoked as `daymade-financial:daymade-sector-research`)

A-share (Chinese market) sector research workflow: Top-N gainers across all
sector constituents, announcement-window retrieval, and market-sentiment
judgment with graded evidence — executed by an Agent Team with fresh-context
adversarial verification. All public, no-login data sources.

**Key features:**
- Top-N gainer pipeline across full sector constituent lists (East Money push2 + Sina realtime snapshots, cross-checked)
- Announcement windows per stock (weekly/monthly) from cninfo + East Money, covering Shanghai/Shenzhen/Beijing exchanges
- Sentiment verdicts graded by evidence level — L1 first-hand quotes / L2 timestamped media / L3 unverified headlines — with "rather uncertain than wrong" as the standing discipline

**Example usage:**
```text
/daymade-financial:daymade-sector-research
医药行业今天的 Top 10 标的
这些标的最近一个月发过哪些公告
判断医药板块现在的市场情绪
```

### **kimi-use** - Query Kimi Desktop Data Plugins

Drive the logged-in Kimi desktop app through computer-use to query its built-in
company, financial, market, academic, and legal data plugins without separate
API keys. Results stay source-labeled and must be independently checked before
they become load-bearing data.

**Key features:**
- Routes requests to installed Kimi plugins such as 天眼查, 同花顺 iFinD, SEC, IMF, and academic/legal databases
- Covers both Claude Code computer-use and Codex computer control
- Provides query patterns that require explicit sources and honest unknowns
- Guards against truncated lists, OCR/name errors, and financial-data scope mismatches

**Example usage:**
```text
/kimi-use
用 Kimi 查这家公司的股东和最新财务数据，并逐项标明来源
操作 Kimi 客户端，用已安装插件核对这组市场数据
```

### **tibo-reset-codex** - ChatGPT/Codex 额度重置速查

> **Install**: `claude plugin install tibo-reset-codex@daymade-skills`

查询 ChatGPT/Codex 额度重置时间，解读 Tibo（OpenAI Codex 负责人 @thsottiaux）
的重置公告。别再凭记忆回答「什么时候重置」——用权威追踪站 API 现查。

**Key features:**
- 公告索引 Tibo Radar JSON API 现查；读 X 原帖走 fxtwitter 镜像拿完整长文（30 秒出结果）
- 解读 Tibo 糙时间写法（「14pm PST」混用 24 小时制、常年写 PST 实为 PDT）
- 太平洋时间→北京时间当场实测换算命令，含夏令时跨时令处理
- 本机 `~/.codex` rollout 快照取证：重建周额度曲线、把重置定位到分钟级区间，不必让用户去截图
- 同时查官方故障线（@ChatGPT / status.openai.com）——重置有里程碑与故障补偿两个触发，Radar 只索引前者
- 证据纪律：tracker 标签 ≠ 已到账，官宣 ≠ 你的账户已到账；celebration 帖 = 里程碑重置预告

**Example usage:**
```text
ChatGPT 什么时候重置额度
banked reset 到了吗
Tibo 说的 2pm PST 是北京时间几点
```

### **prior-work-retrieval** - Retrieve Proven Work Before Producing

> **Install**: `claude plugin install daymade-claude-code@daymade-skills`
> (suite-only — invoked as `daymade-claude-code:prior-work-retrieval`)

When the user explicitly asks to reuse or find earlier work, verify successful
code, decisions, Skills/SOPs, meetings, WeChat archives, documents, and
conversation history before producing. References to the current tests, README,
files, implementation, or behavior do not trigger retrieval. Every real run
leaves an auditable reuse/adapt/reject receipt; zero ranked hits never become an
absence claim.

**Key features:**
- Explicit source manifest and per-carrier coverage
- Original-source authority and freshness verification
- Reuse/adapt/reject decisions tied to the current business outcome
- Deterministic receipt check before substantial production

**Example usage:**
```text
/daymade-claude-code:prior-work-retrieval
we solved this before; find the code and successful path before changing anything
don't rebuild the workflow until you have checked our existing Skills and history
```

### **lark-cli-router** - One Version-Synced Lark Router

> **Install**: `claude plugin install daymade-claude-code@daymade-skills`
> (suite-only — invoked as `daymade-claude-code:lark-cli-router`)

Route Feishu/Lark/Doubao requests to the matching guide embedded in the installed
`lark-cli`, instead of loading every Lark domain Skill into the model catalog.
Tencent IMA stays separate under `ima-skill`.

**Key features:**
- Selects the smallest matching domain or workflow guide from `lark-cli skills list`
- Reads version-matched instructions and references through `lark-cli skills read`
- Keeps unembedded scripts/assets reachable with an embedded-vs-disk guide hash gate
- Preserves each domain's auth, confirmation, success, and verification contract

**Example usage:**
```text
读取这个飞书文档
查一下这条妙记的逐字稿
lark-cli says the user identity is missing a scope
```

### **claude-code-ping-start-5h-quota** - Ping Claude After Quota Reset to Start a Fresh 5h Window

> **Install**: `claude plugin install daymade-claude-code@daymade-skills`
> (suite-only — invoked as `daymade-claude-code:claude-code-ping-start-5h-quota`)

Schedule a one-shot local timer (macOS) that sends one minimal `claude -p` message
right after your subscription quota resets, so the next 5-hour usage window starts
counting while you sleep instead of when you wake up. Dual redundancy: the detached
ping survives closing the session, and a live session is re-woken to verify the
`ok` receipt.

**Key features:**
- Cross-midnight absolute-time handling and an explicit minutes→seconds formula with a 5-minute buffer
- `caffeinate -is` holds off idle sleep during the wait; independent `ps` read-back verifies the timer chain
- Persists the trigger time and output path into the conversation, so a lost wake-up notification stays recoverable
- Feature-string `pkill` cancel command (live-verified) — never kill by sleep seconds
- Honest failure reporting: says "cannot confirm locally" instead of guessing

**Example usage:**
```text
还有 1 小时 20 分钟重置额度，帮我定时戳一下 Claude
我去睡觉了，额度重置后帮我 ping 一下开启新窗口
```

### **codex-1m-context-window-setup** - Model-Aware Long Context for Codex

> **Install**: `claude plugin install daymade-codex@daymade-skills`
> (suite-only — invoked as `daymade-codex:codex-1m-context-window-setup`)

Configure the shared Codex CLI/Desktop base config for the largest context window
the selected model actually declares, up to a one-million-token request. The Skill
discovers the live model contract, explains the familiar ~258K default, applies a
60% auto-compaction threshold, preserves unrelated TOML, backs up changed bytes,
and rolls back if Codex strict-config validation fails.

**Key features:**
- Model-aware ceiling instead of a hard-coded 1M claim
- Read-only `doctor`, transactional `apply`, and drift-detecting `verify` modes
- Exact rollback, idempotent no-op behavior, and macOS/Windows support
- Changes only `model_context_window` and `model_auto_compact_token_limit`

**Example usage:**
```text
/daymade-codex:codex-1m-context-window-setup doctor
configure Codex CLI and Desktop for the largest verified context window
verify that my long-context setup still matches the selected model
```

---

### **interaction-design-board** - Runnable Interaction Alternatives Before Implementation

> **Install**: `claude plugin install daymade-codex@daymade-skills`
> (suite-only — invoked as `daymade-codex:interaction-design-board`)

Generate several genuinely different HTML interaction architectures for one bounded
product surface while holding business facts and the current design language constant.
The bundled builder combines the self-contained candidates into a keyboard-accessible
Design Board with Focus/Compare modes, structured task feedback, remix requests, and a
content-bound approval handoff. Product code stays untouched until the user has operated
and approved a direction.

**Key features:**
- Distinguishes interaction architecture from static visual-style exploration
- Keeps one frozen business/task contract across isolated candidate generation
- Rejects byte-identical candidates, path traversal, missing states, and external assets
- Supports gstack's local feedback daemon and direct-file JSON download fallback
- Preserves prototype content identity separately from the runtime Board instance

**Example usage:**
```text
/daymade-codex:interaction-design-board
show me three clickable ways to organize this review workflow before changing the app
the visual style is fine, but compare queue-first, object-first, and ledger-first interactions
use a Design Board so I can try each progressive-disclosure option and request a remix
```

📚 **Documentation**: See
[interaction-design-method.md](./daymade-codex/interaction-design-board/references/interaction-design-method.md)
and [board-contract.md](./daymade-codex/interaction-design-board/references/board-contract.md).

---

## 🎬 Interactive Demo Gallery

Want to see all demos in one place with click-to-enlarge functionality? Check out our [interactive demo gallery](./demos/index.html) or browse the [demos directory](./demos/).

## 🎯 Use Cases

### For GitHub Workflows
Use **github-ops** for verified PR, issue, Actions, repository, organization-access, and API
operations.
Use **github-review-pr** when a maintainer needs a current-base code review, ownership
decision, or review-gated repair/landing for one contributor PR or the complete open
PR queue.

### For Documentation
Combine **doc-to-markdown** for document conversion and **mermaid-tools** for diagram generation to create comprehensive documentation. Use **llm-icon-finder** to add brand icons.

### For Research & Analysis
Use **deep-research** to produce format-controlled research reports with evidence tables and citations. Combine with **fact-checker** to validate claims or with **twitter-reader** for social-source collection.

### For Competitive Intelligence
Use **competitors-analysis** to discover, persist, update, and analyze competitor repositories with evidence-based source citations. Combine with **deep-research** when the landscape also needs broader market, pricing, or narrative research.

### For PDF & Printable Documents
Use **pdf-creator** to convert markdown to print-ready PDFs with proper Chinese font support for formal documents and reports.

### For Team Communication
Use **teams-channel-post-writer** to share knowledge and **statusline-generator** to track costs while working.

### For Local Agent Coordination
Use **peer-message** when Claude Code profiles and Codex threads on the same machine need to exchange targeted handoffs, pause/resume notices, dependency updates, or an explicit multi-target broadcast. It keeps peer input separate from user authorization and independently reads back receiver-side evidence before calling a message delivered.

### For Repository Management & Security
Use **repomix-unmixer** to extract and validate repomix-packed skills or repositories. Use **repomix-safe-mixer** to package codebases securely, automatically detecting and blocking hardcoded credentials before distribution.

### For Skill Development
Use **skill-creator** (see [Essential Skill](#-essential-skill-skill-creator) section above) to build, validate, and package your own Claude Code skills following best practices.

### For Presentations & Business Communication
Use **ppt-creator** to generate professional slide decks with data visualizations, structured storytelling, and complete PPTX output for pitches, reviews, and keynotes. Use **slides-creator** for narrative-first slide design — it guides you through the ABCDEFG storytelling framework, collects your original content first, then delegates visual generation to baoyu-slide-deck. Perfect when you have existing articles, transcripts, or talks that need to become visual slides.

### For Video Quality Analysis
Use **video-comparer** to analyze compression results, evaluate codec performance, and generate interactive comparison reports. Combine with **youtube-downloader** to compare different quality downloads.

### For Media & Content Download
Use **youtube-downloader** to download YouTube videos and extract audio from videos with automatic workarounds for common download issues.

### For Transcription & ASR Correction
Use **transcript-fixer** to correct speech-to-text errors in meeting notes, lectures, and interviews through dictionary-based rules and AI-powered corrections with automatic learning.

### For Financial Data & Investment Research
Use the **daymade-financial** suite for the complete investment-research data pipeline. **bigdata-skill** pulls structured financials and sentiment from Bigdata.com (RavenPack) via the official SDK. **financial-data-collector** gathers US equity fundamentals from yfinance with validation and NO FALLBACK discipline. **gangtise-copilot** installs and orchestrates the full Gangtise (岗底斯) OpenAPI research suite. **ashare-news-fetcher** aggregates A-share news, policy, and sentiment from Chinese public sources. **pharma-daily-report** generates pharmaceutical sector daily reports with real-time quotes and fund-flow analysis.

### For Excel & Financial Modeling Automation
Use **excel-automation** to create formatted workbooks, parse complex `.xlsm` models, and automate Excel window controls for repetitive analyst workflows.

### For Visual Capture Automation on macOS
Use **capture-screen** to script repeatable app-window screenshots. Combine with **excel-automation** to generate report-ready workbook visuals.

### For Meeting Documentation
Use **meeting-minutes-taker** to transform raw meeting transcripts into structured, evidence-based minutes. Combine with **transcript-fixer** to clean up ASR errors before generating minutes. Features multi-pass generation with UNION merge to avoid content loss.

### For QA Testing & Quality Assurance
Use **qa-expert** to establish comprehensive QA testing infrastructure with autonomous LLM execution, Google Testing Standards, and OWASP security testing. Perfect for project launches, third-party QA handoffs, and enforcing quality gates (100% execution, ≥80% pass rate, 0 P0 bugs). The master prompt enables 100x faster test execution with zero tracking errors.

### For Prompt Engineering & Requirements Engineering
Use **prompt-optimizer** to transform vague feature requests into precise EARS specifications with domain theory grounding. Perfect for product requirements documents, AI-assisted coding, and learning prompt engineering best practices. Combine with **skill-creator** to create well-structured skill prompts, or with **ppt-creator** to ensure presentation content requirements are clearly specified.

### For Session History & File Recovery
Use **read-claude-code-history** to recover deleted files from previous Claude Code sessions, search for specific implementations across conversation history, or track file evolution over time. Essential for recovering accidentally deleted code or finding that feature implementation you remember but can't locate.

### For Reusing Existing Work Before Producing
Use **prior-work-retrieval** only when the user explicitly asks to find, reuse, or reconcile earlier work. A mention of current tests, README, files, implementation, behavior, or validation is not enough. For a real prior-work request, it searches the explicit local source manifest across current code, project decisions, Skills/SOPs, meetings, archived WeChat, and conversation history; then requires source verification plus an auditable reuse/adapt/reject receipt. A zero-hit ranked search never becomes an absence claim.

### For Codex Workstation Setup
Use **codex-1m-context-window-setup** when Codex CLI or Desktop shows about 258K
context, compacts too early, or a classroom/workstation needs a reproducible
long-context policy. It reads the selected model's live catalog entry, requests up
to 1M raw tokens, and verifies the exact base-config values without touching the
model, sandbox, approvals, plugins, or other user settings.

### For Resuming Interrupted Claude Sessions
Use **continue-claude-code-work** to recover the last actionable request from local `~/.claude` artifacts and continue implementation without reopening the original session. Combine with **read-claude-code-history** when you need broader cross-session search, statistics, or deleted-file recovery.

For a prior Codex CLI run, use **continue-codex-work** instead; it reconstructs a
briefing from local Codex rollout files without replaying the full session.

### For Local Conversation Evidence
Use **read-claude-code-history** for Claude Code inventory, exact timelines,
queued human input, full-event search, and deleted-file recovery. Use
**read-codex-history** for Codex inventory, exact prompt-ledger inputs, verified
rollout identity, fork/compaction lineage, and Codex-only search. The two readers
remain read-only; move to the matching **continue-claude-code-work** or
**continue-codex-work** only when the user asks to execute the unfinished task.

### For Web Extraction & WeChat Articles
Use **scrapling-skill** to install and validate Scrapling CLI, choose between static and browser-backed fetching, and extract clean Markdown from sites like `mp.weixin.qq.com`. Combine with **deep-research** to turn extracted sources into structured reports or with **docs-cleaner** to normalize captured article content.

### For Documentation Maintenance
Use **docs-cleaner** to consolidate redundant documentation while preserving valuable content. Perfect for cleaning up documentation sprawl after rapid development phases or merging overlapping docs into authoritative sources.

### For CLAUDE.md Optimization
Use **claude-md-progressive-disclosurer** to reduce CLAUDE.md bloat by moving detailed sections into references while keeping core rules visible.

### For Skill Discovery & Management
Use **skills-search** to find, install, and manage Claude Code skills from the CCPM registry. Perfect for discovering new skills for specific tasks, installing skill bundles for common workflows, and keeping your skill collection organized.

### For LLM Evaluation & Model Comparison
Use **promptfoo-evaluation** to set up prompt tests, compare model outputs, and run automated evaluations with custom assertions. Use **llm-eval-harness** to benchmark an endpoint across speed (thinking-aware tok/s), concurrency/stability, Anthropic protocol compliance, and quality regression against your own use cases — verifying a vendor's tokens-per-second claim or vetting a newly released model before adopting it. The two compose: promptfoo for fast per-case rubric gating, llm-eval-harness for blind-judge precision and raw speed/concurrency probing.

### For iOS App Development
Use **developing-ios-apps** to configure XcodeGen projects, resolve SPM dependency issues, and troubleshoot code signing or device deployment.

### For macOS System Maintenance & Disk Space Recovery
Use **macos-cleaner** to diagnose and reclaim disk space on macOS with a safety-first approach. It routes known suspects such as Apple Content Caching to targeted read-only checks before any broad scan, distinguishes logical from physical usage, explains impact and recovery, and requires explicit confirmation before state changes. It also covers Docker/OrbStack, Homebrew/npm/pip, application remnants, large files, and optional Mole exploration.

### For Twitter/X Content Research
Use **twitter-reader** to fetch tweet content without JavaScript rendering or authentication. Perfect for documenting social media discussions, archiving threads, analyzing tweet content, or gathering reference material from Twitter/X. Combine with **doc-to-markdown** to convert fetched content into other formats, or with **repomix-safe-mixer** to package research collections securely.

### For Skill Quality & Open-Source Contributions
Use **skill-reviewer** to validate your own skills against best practices before publishing, or to review and improve others' skill repositories. Combine with **github-contributor** to find high-impact open-source projects, create professional PRs, and build your contributor reputation. Perfect for developers who want to contribute to the Claude Code ecosystem or any GitHub project systematically.

### For Internationalization & Localization
Use **i18n-expert** to set up complete i18n infrastructure for React/Next.js/Vue applications, audit existing implementations for missing translation keys, and ensure locale parity between en-US and zh-CN. Perfect for teams launching products to global markets, maintaining multi-language UIs, or replacing hard-coded strings with proper i18n keys. Combine with **skill-creator** to create locale-aware skills, or with **docs-cleaner** to consolidate documentation across multiple languages.

### For Network & VPN Troubleshooting
Use **tunnel-doctor** to diagnose and fix conflicts between Tailscale and proxy/VPN tools on macOS across multiple independent layers (route hijacking, HTTP env vars, system proxy, SSH ProxyCommand, VM/container proxy propagation, DNS resolver stall). Essential when Tailscale ping works but TCP connections fail, when git push fails with "failed to begin relaying via HTTP", or when setting up Tailscale SSH to WSL instances alongside Shadowrocket, Clash, or Surge. Also covers **TUN measurement contamination** — why raw probes (`nc -z` showing 0.00s, `ping`, a foreign `ip-api` lookup) lie while a global proxy is up, and what to trust instead.

### For Product Audits
Use **product-analysis** for structured pre-release and architecture reviews. It combines UX, API, and architecture analysis into measurable findings with priority-ranked recommendations. Add `compare` mode to benchmark against competitor implementations through evidence-backed reports.

### For Remote Desktop & VDI Optimization
Use **windows-remote-desktop-connection-doctor** to diagnose Azure Virtual Desktop / W365 connection quality issues on macOS. Essential when transport shows WebSocket instead of UDP Shortpath, when RTT is unexpectedly high, or when RDP Shortpath fails after changing network locations. Combines network evidence gathering with Windows App log analysis for systematic root cause identification.

### For Plugin & Skill Troubleshooting
Use **claude-skills-troubleshooting** to diagnose and resolve Claude Code plugin and skill configuration issues. Debug why plugins appear installed but don't show in available skills, understand the installed_plugins.json vs settings.json enabledPlugins architecture, and batch-enable missing plugins from a marketplace. Essential for marketplace maintainers debugging installation issues, developers troubleshooting skill activation, or anyone confused by the GitHub #17832 auto-enable bug.

### For Tencent IMA Knowledge Base Workflows
Use **ima-copilot** to install the official Tencent IMA skill across Claude Code / Codex / OpenClaw, configure API credentials, detect and repair known upstream issues, and run personalized fan-out searches across all your IMA knowledge bases with priority-based boosting. The wrapper architecture means upstream upgrades never collide with your fixes — every repair is a runtime instruction, not a shipped patch. Perfect for IMA power users who switch between multiple coding agents, or for anyone who has hit the "Skipped loading skill(s) due to invalid SKILL.md" warning.

### For Post-Processing Claude Code Exports
Use **claude-export-txt-better** to clean up `/export` output before archiving or sharing. The default export format hard-wraps tables, paths, and tool-call blocks at fixed column widths, which breaks readability in any viewer wider than 80 columns. The skill reconstructs the original structure and validates the fix with 53 automated checks so regressions are caught immediately.

### For Personal Data Backup (Douban)
Use **douban-skill** to back up your Douban 书影音 (book/movie/music/game) history to CSV. Douban has no official export — the public API was shut down in 2018 and all web scraping is blocked by PoW challenges. This skill uses the same Frodo API as the official Android app, so it just works without any login or cookies. Ships with a full failure log of 7 rejected scraping approaches, saving you hours of wasted effort.

### For Terraform & IaC Troubleshooting
Use **terraform-skill** when your `terraform apply` fails at a provisioner step, when fresh instances hit "docker: not found", or when multi-environment setups accidentally share snapshots. Every pattern in the skill is an *exact error → root cause → copy-paste fix* triple drawn from real incidents. Perfect for anyone who has lost a weekend to timing races in cloud-init, rsync connection drops in local-exec, or hardcoded domains in Caddyfiles.

### For Network, Streaming & Protocol-Layer Debugging
Use **debugging-network-issues** when symptoms do not match the obvious cause: HTTP/2 `RST_STREAM`, SSE stalls at exactly 60s/100s/130s, "works sometimes but not always" failures, client-side proxy/VPN/TUN misrouting with `ERR_CONNECTION_CLOSED` or `SSL_ERROR_SYSCALL`, or anything that looks like an idle-timeout or rule-override incident through CDN / proxy / CGNAT / TUN chains. The skill replaces assumption-stacking with **layered isolation experiments** — running the same logical request through three or more paths that differ by one hop — plus a counter-review pattern for shipping fixes only after the hypothesis has been falsified, not just confirmed. The cognitive-trap catalog includes reverse-path / directional asymmetry and proxy-node DNS ≠ client DNS.

### For Chinese TTS (StepFun StepAudio 2.5)
Use **stepfun-tts** for Chinese / Japanese voice synthesis with emotional control via `instruction` + inline `()` prosody. Captures the two breaking changes that ambush new StepAudio 2.5 users: `voice_label` removal and stricter 2.5-era censorship rules. Pair with `step-tts-2` as a per-line fallback for content that triggers censorship.

### For Long-Audio Transcription (StepFun StepAudio 2.5)
Use **stepfun-asr** for transcribing up to 30-minute Chinese / English audio in a single SSE call (32K context, ~85-101× RTF, no client-side chunking). Hides the #1 trap — the model does NOT live on `/v1/audio/transcriptions`; the wrong endpoint returns a misleading "model not supported" error. Combine with **transcript-fixer** for ASR error correction or with **meeting-minutes-taker** to turn long recordings into structured minutes.

## 📚 Documentation

Each skill includes:
- **SKILL.md**: Core instructions and workflows
- **scripts/**: Executable utilities (Python/Bash)
- **references/**: Detailed documentation
- **assets/**: Templates and resources (where applicable)

### Quick Links

- **github-ops**: See `github-ops/references/api_reference.md` for API documentation
- **github-review-pr**: See `github-review-pr/SKILL.md` for the current-base review workflow and `github-review-pr/references/personal_maintainer_context.md` for the explicit personal policy profile
- **doc-to-markdown**: See `daymade-docs/doc-to-markdown/references/conversion-examples.md` for conversion scenarios
- **mermaid-tools**: See `daymade-docs/mermaid-tools/references/setup_and_troubleshooting.md` for setup guide
- **statusline-generator**: See `daymade-claude-code/statusline-generator/references/color_codes.md` for customization
- **teams-channel-post-writer**: See `teams-channel-post-writer/references/writing-guidelines.md` for quality standards
- **peer-message**: See `peer-message/SKILL.md` for routing, stable prerequisites, and the safety boundary; `peer-message/scripts/peer.py --help` for CLI syntax; `peer-message/references/protocol-and-discovery.md` for transport and verification; `peer-message/references/official-feature.md` for volatile product requirements and mechanics; and `peer-message/references/coordination-and-learning-loop.md` for parent/worker handoffs and evidence-gated improvement
- **repomix-unmixer**: See `repomix-unmixer/references/repomix-format.md` for format specifications
- **skill-creator**: See `daymade-skill/skill-creator/SKILL.md` for complete skill creation workflow
- **llm-icon-finder**: See `llm-icon-finder/references/icons-list.md` for available icons
- **cli-demo-generator**: See `cli-demo-generator/references/vhs_syntax.md` for VHS syntax and `cli-demo-generator/references/best_practices.md` for demo guidelines
- **cloudflare-troubleshooting**: See `cloudflare-troubleshooting/references/api_overview.md` for API documentation
- **ui-designer**: See `ui-designer/SKILL.md` for design system extraction workflow
- **ppt-creator**: See `daymade-docs/ppt-creator/references/WORKFLOW.md` for 9-stage creation process and `daymade-docs/ppt-creator/references/ORCHESTRATION_OVERVIEW.md` for automation
- **youtube-downloader**: See `youtube-downloader/SKILL.md` for usage examples and troubleshooting
- **repomix-safe-mixer**: See `repomix-safe-mixer/references/common_secrets.md` for detected credential patterns
- **video-comparer**: See `video-comparer/references/video_metrics.md` for quality metrics interpretation and `video-comparer/references/configuration.md` for customization options
- **transcript-fixer**: See `daymade-audio/transcript-fixer/references/workflow_guide.md` for step-by-step workflows and `daymade-audio/transcript-fixer/references/team_collaboration.md` for collaboration patterns
- **qa-expert**: See `qa-expert/references/master_qa_prompt.md` for autonomous execution (100x speedup) and `qa-expert/references/google_testing_standards.md` for AAA pattern and OWASP testing
- **prompt-optimizer**: See `prompt-optimizer/references/ears_syntax.md` for EARS transformation patterns, `prompt-optimizer/references/domain_theories.md` for theory catalog, and `prompt-optimizer/references/examples.md` for complete transformations
- **read-codex-history**: See `daymade-claude-code/read-codex-history/references/storage_and_portability.md` for local-store selection, cross-platform paths, privacy boundaries, and diagnostics
- **read-claude-code-history**: See `daymade-claude-code/read-claude-code-history/references/session_file_format.md` for JSONL structure and `daymade-claude-code/read-claude-code-history/references/workflow_examples.md` for recovery workflows
- **prior-work-retrieval**: See `daymade-claude-code/prior-work-retrieval/SKILL.md` for the retrieval/verification workflow and `daymade-claude-code/prior-work-retrieval/references/source-manifest.md` for the explicit carrier contract
- **codex-1m-context-window-setup**: See `daymade-codex/codex-1m-context-window-setup/SKILL.md` for the doctor/apply/verify workflow and `daymade-codex/codex-1m-context-window-setup/references/context_window_contract.md` for model-cap, usable-window, and compaction semantics
- **docs-cleaner**: See `daymade-docs/docs-cleaner/SKILL.md` for consolidation workflows
- **deep-research**: See `deep-research/references/research_report_template.md` for report structure and `deep-research/references/source_quality_rubric.md` for source triage
- **pdf-creator**: See `daymade-docs/pdf-creator/SKILL.md` for PDF conversion and font setup
- **claude-md-progressive-disclosurer**: See `daymade-claude-code/claude-md-progressive-disclosurer/SKILL.md` for CLAUDE.md optimization workflow
- **skills-search**: See `daymade-skill/skills-search/SKILL.md` for CCPM CLI commands and registry operations
- **promptfoo-evaluation**: See `promptfoo-evaluation/references/promptfoo_api.md` for evaluation patterns
- **developing-ios-apps**: See `daymade-macos/developing-ios-apps/references/xcodegen-full.md` for XcodeGen options and project.yml details
- **twitter-reader**: See `twitter-reader/SKILL.md` for API key setup and URL format support
- **macos-cleaner**: See `daymade-macos/macos-cleaner/references/apple_content_caching.md` for Apple Content Caching, `daymade-macos/macos-cleaner/references/cleanup_targets.md` for cleanup target semantics, `daymade-macos/macos-cleaner/references/mole_integration.md` for Mole, and `daymade-macos/macos-cleaner/references/safety_rules.md` for safety guidelines
- **skill-reviewer**: See `daymade-skill/skill-reviewer/references/evaluation_checklist.md` for complete evaluation criteria and `daymade-skill/skill-reviewer/references/pr_template.md` for PR templates
- **github-contributor**: See `github-contributor/references/pr_checklist.md` for PR quality checklist, `github-contributor/references/project_evaluation.md` for project evaluation criteria, and `github-contributor/references/communication_templates.md` for issue/PR templates
- **i18n-expert**: See `i18n-expert/SKILL.md` for complete i18n setup workflow, key architecture guidance, and audit procedures
- **claude-skills-troubleshooting**: See `daymade-claude-code/claude-skills-troubleshooting/SKILL.md` for plugin troubleshooting workflow and architecture
- **fact-checker**: See `fact-checker/SKILL.md` for fact-checking workflow and claim verification process
- **competitors-analysis**: See `competitors-analysis/SKILL.md` for the discover/ingest/profile/landscape workflow and `competitors-analysis/references/profile_template.md` for the competitor profile template
- **windows-remote-desktop-connection-doctor**: See `windows-remote-desktop-connection-doctor/references/windows_app_log_analysis.md` for log parsing patterns and `windows-remote-desktop-connection-doctor/references/avd_transport_protocols.md` for transport protocol details
- **product-analysis**: See `product-analysis/SKILL.md` for workflow and `product-analysis/references/synthesis_methodology.md` for cross-agent weighting and recommendation logic
- **excel-automation**: See `daymade-docs/excel-automation/SKILL.md` for create/parse/control workflows and `daymade-docs/excel-automation/references/formatting-reference.md` for formatting standards
- **capture-screen**: See `daymade-macos/capture-screen/SKILL.md` for CGWindowID-based screenshot workflows on macOS
- **continue-claude-code-work**: See `daymade-claude-code/continue-claude-code-work/SKILL.md` for local artifact recovery, drift checks, and resume workflow
- **continue-codex-work**: See `daymade-claude-code/continue-codex-work/SKILL.md` for Codex rollout discovery, end-reason diagnosis, and continuation workflow
- **scrapling-skill**: See `scrapling-skill/SKILL.md` for the CLI workflow and `scrapling-skill/references/troubleshooting.md` for verified Scrapling failure modes
- **ima-copilot**: See `ima-copilot/SKILL.md` for the wrapper architecture and routing, `ima-copilot/references/installation_flow.md` for the install deep dive, `ima-copilot/references/known_issues.md` for the issue registry and repair commands, and `ima-copilot/references/search_best_practices.md` for the fan-out strategy and 100-result truncation details
- **claude-export-txt-better**: See `daymade-claude-code/claude-export-txt-better/SKILL.md` for the workflow, `daymade-claude-code/claude-export-txt-better/scripts/fix-claude-export.py` for the reconstruction algorithm, and `daymade-claude-code/claude-export-txt-better/evals/` for real regression fixtures
- **douban-skill**: See `douban-skill/SKILL.md` for the export workflow and `douban-skill/references/troubleshooting.md` for the complete log of 7 tested scraping approaches and why each failed
- **terraform-skill**: See `terraform-skill/SKILL.md` for the full catalogue of operational traps organised by exact error → root cause → copy-paste fix
- **slides-creator**: See `slides-creator/SKILL.md` for the narrative-first workflow, `slides-creator/references/narrative-design-guide.md` for the ABCDEFG model, and `slides-creator/references/content-creation-first-law.md` for the universal content creation principle
- **debugging-network-issues**: See `debugging-network-issues/SKILL.md` for the falsification-first workflow, `debugging-network-issues/references/layered-isolation-experiment.md` for the multi-hop isolation pattern, `debugging-network-issues/references/case-sse-rst-130s.md` for the SSE production case study, and `debugging-network-issues/references/case-proxy-tun-cname-override.md` for the client-side proxy/TUN CNAME-rule-override case study
- **stepfun-tts**: See `stepfun-tts/SKILL.md` for the Contextual TTS decision tree and `stepfun-tts/references/migration_from_v2.md` for the `voice_label` → `instruction` migration playbook plus the censorship rewrite list
- **stepfun-asr**: See `stepfun-asr/SKILL.md` for the SSE-endpoint workflow and the four ASR-side traps (wrong endpoint, Plan-vs-Normal key, repetition hallucination, SSE `error` event). `stepfun-asr/references/api_reference.md` documents the exact JSON request body and SSE event contract for raw HTTP integration
- **llm-eval-harness**: See `llm-eval-harness/references/evaluation_disciplines.md` for the reasoning behind each discipline (env-var keys, thinking-aware throughput, proxy isolation, probabilistic protocol verdicts) and `llm-eval-harness/references/quality_blind_judge.md` for the independent blind-judge quality method

## 🛠️ Requirements

- **Claude Code** 2.0.13 or higher
- **Codex CLI with `doctor --json` and `debug models` + uv/Python 3.11+** (for codex-1m-context-window-setup)
- **gh CLI** (for github-ops and github-review-pr)
- **git with `merge-tree --write-tree` + jq** (for github-review-pr)
- **markitdown** (for doc-to-markdown)
- **mermaid-cli** (for mermaid-tools)
- **yt-dlp** (for youtube-downloader): `brew install yt-dlp` or `pip install yt-dlp`
- **FFmpeg/FFprobe** (for video-comparer): `brew install ffmpeg`, `apt install ffmpeg`, or `winget install ffmpeg`
- **pandoc + weasyprint** (for pdf-creator): `brew install pandoc` + `pip install weasyprint` (or use Chrome as backend)
- **VHS** (for cli-demo-generator): `brew install vhs`
- **Jina.ai API key** (for twitter-reader): Free tier available at https://jina.ai/
- **asciinema** (optional, for cli-demo-generator interactive recording)
- **ccusage** (optional, for statusline cost tracking)
- **pandas & matplotlib** (optional, for ppt-creator chart generation)
- **Marp CLI** (optional, for ppt-creator Marp PPTX export): `npm install -g @marp-team/marp-cli`
- **Mole** (optional, for macos-cleaner visual cleanup): Download from https://github.com/tw93/Mole
- **repomix** (for repomix-safe-mixer): `npm install -g repomix`
- **CCPM CLI** (for skills-search): `npm install -g @daymade/ccpm`
- **Promptfoo** (for promptfoo-evaluation): `npx promptfoo@latest`
- **macOS + Xcode, XcodeGen** (for developing-ios-apps)
- **Codex CLI** (optional, for product-analysis multi-model mode)
- **uv + openpyxl** (for excel-automation): `uv run --with openpyxl ...`
- **Bigdata.com API key** (for `daymade-financial:bigdata-skill`): `bd_v2_` key from [https://www.bigdata.com/](https://www.bigdata.com/)
- **Gangtise credentials** (for `daymade-financial:gangtise-copilot`): accessKey + secretAccessKey from [https://open.gangtise.com/](https://open.gangtise.com/)
- **macOS** (for capture-screen and excel-automation AppleScript control workflows)
- **Python 3.10+** (for the four local history read/continue skills): bundled standard-library readers and validators
- **uv + Scrapling CLI** (for scrapling-skill): `uv tool install 'scrapling[shell]'` and `scrapling install` for browser-backed fetches
- **Node.js 18+ + curl + unzip** (for ima-copilot): `npx skills` is fetched on demand from the npm registry; IMA OpenAPI credentials from [https://ima.qq.com/agent-interface](https://ima.qq.com/agent-interface)
- **StepFun API key** (for stepfun-tts and stepfun-asr — must be "Normal" tier, Plan keys silently fail on audio endpoints): Available at [https://platform.stepfun.com/](https://platform.stepfun.com/) → API Keys
- **uv + an endpoint API key** (for llm-eval-harness): `openai` and `aiohttp` are auto-installed via `uv run --with`; the key is passed by env-var name only

## ❓ FAQ

### How do I know which skills to install?

Start with **skill-creator** if you want to create your own skills. Otherwise, browse the [Other Available Skills](#-other-available-skills) section and install what matches your workflow.

### Can I use these skills without Claude Code?

Most marketplace skills target Claude Code. Skills in the `daymade-codex` suite
that explicitly document Codex support can also be installed through Codex's
plugin marketplace; check each Skill's requirements before use.

### How do I update skills?

Use the same install command to update:
```bash
claude plugin install skill-name@daymade-skills
```

### Can I contribute my own skill?

Absolutely! See [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines. We recommend using the skill-creator to ensure your skill meets quality standards.

### Are these skills safe to use?

Yes, all skills are open-source and reviewed. The code is available in this repository for inspection.

### How do Chinese users handle API access?

We recommend using [CC-Switch](https://github.com/farion1231/cc-switch) to manage API provider configurations. See the [Chinese User Guide](#-chinese-user-guide) section above.

### What's the difference between skill-creator and other skills?

**skill-creator** is a meta-skill - it helps you create other skills. The other skills are end-user skills that provide specific functionalities (GitHub ops, document conversion, etc.). If you want to extend Claude Code with your own workflows, start with skill-creator.

---

## 🤝 Contributing

This is a curated marketplace of our own skills — see [CONTRIBUTING.md](./CONTRIBUTING.md) for the full policy. In short:

1. **Bug reports and bug-fix PRs are welcome** — open an issue first, then a scoped fix
2. **New-skill PRs are not accepted** — publish your own marketplace instead (the format is open)
3. Feedback on skill quality is always appreciated

### Skill Quality Standards

All skills in this marketplace follow:
- Imperative/infinitive writing style
- Progressive disclosure pattern
- Proper resource organization
- Comprehensive documentation
- Tested and validated

## 📄 License

This marketplace is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⭐ Support

If you find these skills useful, please:
- ⭐ Star this repository
- 🐛 Report issues
- 💡 Suggest improvements
- 📢 Share with your team

## 🔗 Related Resources

- [Claude Code Documentation](https://docs.claude.com/en/docs/claude-code)
- [Agent Skills Guide](https://docs.claude.com/en/docs/claude-code/skills)
- [Plugin Marketplaces](https://docs.claude.com/en/docs/claude-code/plugin-marketplaces)
- [Anthropic Skills Repository](https://github.com/anthropics/skills)

## 📞 Contact

- **GitHub**: [@daymade](https://github.com/daymade)
- **Email**: daymadev89@gmail.com
- **Repository**: [daymade/claude-code-skills](https://github.com/daymade/claude-code-skills)

---

**Built with ❤️ using the skill-creator skill for Claude Code**
