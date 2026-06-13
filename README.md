# Claude Code Skills Marketplace

<div align="center">

[![English](https://img.shields.io/badge/Language-English-blue)](./README.md)
[![简体中文](https://img.shields.io/badge/语言-简体中文-red)](./README.zh-CN.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Skills](https://img.shields.io/badge/skills-64-blue.svg)](https://github.com/daymade/claude-code-skills)
[![Version](https://img.shields.io/badge/version-1.65.0-green.svg)](https://github.com/daymade/claude-code-skills)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-2.0.13+-purple.svg)](https://claude.com/code)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](./CONTRIBUTING.md)
[![Maintenance](https://img.shields.io/badge/Maintained%3F-yes-green.svg)](https://github.com/daymade/claude-code-skills/graphs/commit-activity)

</div>

Professional Claude Code skills marketplace featuring 64 production-ready skills for enhanced development workflows.

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
| Research before building | "Check available MCPs" (5 lines) | 8-channel search protocol with decision matrix: Adopt / Extend / Build |
| Create a skill interactively | Prose-based instructions | 9 structured AskUserQuestion checkpoints — user never loses context |
| Avoid common mistakes | No guidance | Cache edit warnings, prerequisite checks, security scan gate |
| Know the architecture options | Not mentioned | Inline vs Fork decision guide with examples (choosing wrong silently breaks your skill) |
| Validate before shipping | Basic YAML check | Expanded validator (all frontmatter fields, path reference integrity, whitespace issues) |
| Catch security issues | No tooling | `security_scan.py` with gitleaks integration — hard gate before packaging |
| Learn from real failures | No failure cases | Battle-tested methodology with documented failure patterns and gotchas |

**Quality comparison** (independent audit, 8 dimensions):

| Dimension | Official | This Fork |
|-----------|----------|-----------|
| Actionability | 7 | 9 |
| Error Prevention | 5 | 9 |
| Prior Art Research | 4 | 9 |
| Counter Review Process | 4 | 8 |
| Real-World Lessons | 3 | 8 |
| User Experience | 4 | 9 |
| **Total (out of 80)** | **42** | **65** |

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

📚 **Full documentation**: [daymade-skill/skill-creator/SKILL.md](./daymade-skill/daymade-skill/skill-creator/SKILL.md)

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
```

These skills ship as a bundle — there are no separate single-skill plugins. All documentation skills live under `daymade-docs/` and install together from the suite.

**Claude Code Operations Suite** (shared namespace for Claude Code power-user workflows):
```bash
claude plugin install daymade-claude-code@daymade-skills
```

This suite bundles the skills that extend Claude Code itself — session recovery, CLAUDE.md tuning, troubleshooting, statusline configuration, export repair, and marketplace development:

```text
/daymade-claude-code:claude-code-history-files-finder
/daymade-claude-code:continue-claude-work
/daymade-claude-code:claude-skills-troubleshooting
/daymade-claude-code:claude-md-progressive-disclosurer
/daymade-claude-code:statusline-generator
/daymade-claude-code:claude-export-txt-better
/daymade-claude-code:marketplace-dev
```

Installed names render as `daymade-claude-code:<skill>` under a single shared namespace. These skills are bundle-only — install the suite to get all seven.

**Install Other Skills:**
```bash
# GitHub operations
claude plugin install github-ops@daymade-skills

# Teams communication
claude plugin install teams-channel-post-writer@daymade-skills

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

# iOS app development
claude plugin install iOS-APP-developer@daymade-skills

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

# Financial data collection for US equities
claude plugin install financial-data-collector@daymade-skills

# Excel automation for creation, parsing, and macOS control
claude plugin install excel-automation@daymade-skills

# Programmatic macOS screenshot capture workflows
claude plugin install capture-screen@daymade-skills

# Scrapling CLI extraction and troubleshooting
claude plugin install scrapling-skill@daymade-skills

# Tencent IMA knowledge base companion and installer
claude plugin install ima-copilot@daymade-skills

# Export Douban (豆瓣) book/movie/music/game collections to CSV
claude plugin install douban-skill@daymade-skills

# Terraform operational traps and multi-environment reliability patterns
claude plugin install terraform-skill@daymade-skills
```

Each skill can be installed independently - choose only what you need!

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

### 1. **github-ops** - GitHub Operations Suite

Comprehensive GitHub operations using gh CLI and GitHub API.

**When to use:**
- Creating, viewing, or managing pull requests
- Managing issues and repository settings
- Querying GitHub API endpoints
- Working with GitHub Actions workflows
- Automating GitHub operations

**Key features:**
- PR creation with JIRA integration
- Issue management workflows
- GitHub API (REST & GraphQL) operations
- Workflow automation
- Enterprise GitHub support

**🎬 Live Demo**

![GitHub Ops Demo](./demos/github-ops/create-pr.gif)

---

### 2. **doc-to-markdown** - Document Conversion Suite

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

### 3. **mermaid-tools** - Diagram Generation

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

### 4. **statusline-generator** - Statusline Customization

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

### 5. **teams-channel-post-writer** - Teams Communication

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

### 6. **repomix-unmixer** - Repository Extraction

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

### 7. **llm-icon-finder** - AI/LLM Brand Icon Finder

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

### 8. **cli-demo-generator** - CLI Demo Generation

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

### 9. **cloudflare-troubleshooting** - Cloudflare Diagnostics

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

### 10. **ui-designer** - UI Design System Extractor

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

### 11. **ppt-creator** - Professional Presentation Creation

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

### 12. **youtube-downloader** - YouTube Video & Audio Downloader

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

### 13. **repomix-safe-mixer** - Secure Repomix Packaging

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

### 14. **transcript-fixer** - ASR Transcription Correction

> **Install**: `claude plugin install daymade-audio@daymade-skills` (suite-only — invoked as `daymade-audio:transcript-fixer`)

Correct speech-to-text (ASR/STT) transcription errors through dictionary-based rules and AI-powered corrections with automatic pattern learning.

**When to use:**
- Correcting meeting notes, lecture recordings, or interview transcripts
- Fixing Chinese/English homophone errors and technical terminology
- Building domain-specific correction dictionaries
- Improving transcript accuracy through iterative learning
- Collaborating with teams on shared correction knowledge bases

**Key features:**
- Two-stage correction pipeline (dictionary + AI)
- Automatic pattern detection and learning
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

# Review and approve learned patterns
uv run scripts/fix_transcription.py --review-learned
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [daymade-audio/transcript-fixer/references/](./daymade-audio/transcript-fixer/references/) for workflow guides, SQL queries, troubleshooting, best practices, team collaboration, and API setup.

**Requirements**: Python 3.6+, uv package manager, GLM API key (get from https://open.bigmodel.cn/)

---

### 15. **video-comparer** - Video Comparison and Quality Analysis

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

### 16. **qa-expert** - Comprehensive QA Testing Infrastructure

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

### 17. **prompt-optimizer** - Prompt Engineering with EARS Methodology

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

### 18. **claude-code-history-files-finder** - Session History Recovery

> **Install**: `claude plugin install daymade-claude-code@daymade-skills` (suite-only — invoked as `daymade-claude-code:claude-code-history-files-finder`)

Find and recover content from Claude Code session history files stored in `~/.claude/projects/`.

**When to use:**
- Recovering deleted or lost files from previous Claude Code sessions
- Searching for specific code across conversation history
- Tracking file modifications across multiple sessions
- Finding sessions containing specific keywords or implementations

**Key features:**
- **Session search**: Find sessions by keywords with frequency ranking
- **Content recovery**: Extract files from Write tool calls with deduplication
- **Statistics analysis**: Message counts, tool usage breakdown, file operations
- **Batch operations**: Process multiple sessions with keyword filtering
- **Streaming processing**: Handle large session files (>100MB) efficiently

**Example usage:**
```bash
# List recent sessions for a project
python3 scripts/analyze_sessions.py list /path/to/project

# Search sessions for keywords
python3 scripts/analyze_sessions.py search /path/to/project "ComponentName" "featureX"

# Recover deleted files from a session
python3 scripts/recover_content.py ~/.claude/projects/.../session.jsonl -k DeletedComponent -o ./recovered/

# Get session statistics
python3 scripts/analyze_sessions.py stats /path/to/session.jsonl --show-files
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [daymade-claude-code/claude-code-history-files-finder/references/](./daymade-claude-code/claude-code-history-files-finder/references/) for:
- `session_file_format.md` - JSONL structure and extraction patterns
- `workflow_examples.md` - Detailed recovery and analysis workflows

---

### 19. **docs-cleaner** - Documentation Consolidation

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

### 20. **skills-search** - CCPM Skill Registry Search

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

### 21. **pdf-creator** - PDF Creation with Chinese Font Support

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

### 22. **claude-md-progressive-disclosurer** - CLAUDE.md Optimization

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

### 23. **promptfoo-evaluation** - Promptfoo LLM Evaluation

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

### 24. **iOS-APP-developer** - iOS App Development

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

📚 **Documentation**: See [iOS-APP-developer/references/xcodegen-full.md](./iOS-APP-developer/references/xcodegen-full.md).

**Requirements**: macOS + Xcode, XcodeGen

---

### 25. **twitter-reader** - Twitter/X Content Fetching

Fetch Twitter/X post content using Jina.ai API to bypass JavaScript restrictions without authentication.

**When to use:**
- Retrieving tweet content for analysis or documentation
- Fetching thread replies and conversation context
- Extracting images and media from posts
- Batch downloading multiple tweets for reference

**Key features:**
- No JavaScript rendering or browser automation needed
- No Twitter authentication required
- Returns markdown-formatted content with metadata
- Supports both individual and batch fetching
- Includes author, timestamp, post text, images, and replies
- Environment variable configuration for secure API key management

**Example usage:**
```bash
# Set your Jina API key (get from https://jina.ai/)
export JINA_API_KEY="your_api_key_here"

# Fetch a single tweet
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
- **Jina.ai API key** (get from https://jina.ai/ - free tier available)
- **curl** (pre-installed on most systems)
- **Python 3.6+** (for Python script)

---

### 26. **macos-cleaner** - Intelligent macOS Disk Space Recovery

**The safest way to reclaim disk space on macOS.** Analyze system caches, application remnants, large files, and development environments with intelligent categorization and interactive cleanup.

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
- You want to understand what's consuming space, not just delete blindly
- You need to clean up after uninstalled applications
- You prefer understanding over automation

**Key features:**
- **Smart Cache Analysis**: Categorizes system caches, app caches, logs by safety level
- **Application Remnant Detection**: Finds orphaned data from uninstalled apps with confidence scoring
- **Large File Discovery**: Intelligent categorization (videos, archives, databases, disk images, build artifacts)
- **Development Environment Cleanup**: Docker (images, containers, volumes, build cache), Homebrew, npm, pip, old Git repos
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
- ❌ **Not a One-Click Solution**: We don't delete automatically. If you want "clean everything now", use other tools. We're for users who want control.

**Example usage:**
```bash
# Install the skill
claude plugin install macos-cleaner@daymade-skills

# Ask Claude Code to analyze your Mac
"My Mac is running out of space, help me analyze what's using storage"

# Claude will:
# 1. Run comprehensive disk analysis
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

📚 **Documentation**: See [macos-cleaner/references/](./macos-cleaner/references/) for:
- `cleanup_targets.md` - Detailed explanations of every cleanup target
- `mole_integration.md` - How to combine scripts with Mole visual tool
- `safety_rules.md` - Comprehensive safety guidelines and what to never delete

**Requirements**:
- **Python 3.6+** (pre-installed on macOS)
- **macOS** (tested on macOS 10.15+)
- **Optional**: [Mole](https://github.com/tw93/Mole) for visual cleanup interface

---

### 27. **fact-checker** - Document Fact-Checking

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

### 28. **skill-reviewer** - Skill Quality Review & Improvement

Review and improve Claude Code skills against official best practices with three powerful modes.

**When to use:**
- Validating your own skills before publishing
- Evaluating others' skill repositories
- Contributing improvements to open-source skills via auto-PR
- Ensuring skills follow marketplace standards

**Key features:**
- **Self-review mode**: Run automated validation via skill-creator scripts
- **External review mode**: Clone, analyze, and generate improvement reports
- **Auto-PR mode**: Fork → improve → submit PR with additive-only changes
- **Evaluation checklist**: Frontmatter, instructions, resources verification
- **Additive-only principle**: Never delete files when contributing to others
- **PR guidelines**: Tone recommendations and professional templates
- **Auto-install dependencies**: Automatically installs skill-creator if missing

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

📚 **Documentation**: See [daymade-skill/skill-reviewer/references/](./daymade-skill/daymade-skill/skill-reviewer/references/) for:
- `evaluation_checklist.md` - Complete skill evaluation criteria
- `pr_template.md` - Professional PR description template

---

### 29. **github-contributor** - GitHub Contribution Strategy

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

### 31. **i18n-expert** - Internationalization & Localization

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

### 32. **claude-skills-troubleshooting** - Plugin & Skill Troubleshooting

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

### 33. **meeting-minutes-taker** - Meeting Minutes Generator

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

### 34. **deep-research** - Research Report Generator

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

### 35. **competitors-analysis** - Evidence-Based Competitor Tracking

Analyze competitor repositories with evidence-based approach. All analysis must be based on actual cloned code, never assumptions.

**When to use:**
- Track and analyze competitor products or technologies
- Create evidence-based competitor profiles
- Generate competitive analysis reports
- Need to document technical decisions with cited sources

**Key features:**
- Pre-analysis checklist to ensure repositories are cloned locally
- Forbidden patterns to prevent assumptions ("推测...", "可能...", "应该...")
- Required patterns for source citation (file:line_number format)
- Tech stack analysis guides for Node.js, Python, Rust projects
- Directory structure conventions for organized competitor tracking
- Bundled templates: profile template, analysis checklist
- Management script for batch clone/pull/status operations

**Example usage:**
```bash
# Install the skill
claude plugin install competitors-analysis@daymade-skills

# Then ask Claude to analyze a competitor
"分析竞品 https://github.com/org/repo"
"添加竞品到 flowzero 产品的竞品列表"
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [competitors-analysis/SKILL.md](./competitors-analysis/SKILL.md) and [competitors-analysis/references/](./competitors-analysis/references/) for templates.

**Requirements**: Git (for cloning repositories)

---

### 36. **tunnel-doctor** - Tailscale + Proxy/VPN Conflict Fixer

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

### 37. **windows-remote-desktop-connection-doctor** - AVD/W365 Connection Quality Diagnostician

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

### 38. **product-analysis** - Multi-Path Product Analysis & Optimization

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

### 39. **financial-data-collector** - Financial Data Collection for US Equities

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
# Install the skill
claude plugin install financial-data-collector@daymade-skills

# Then ask Claude to collect data
"Collect financial data for META"
"Get financials for AAPL --years 3"
"Pull DCF inputs for NVDA"
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [financial-data-collector/SKILL.md](./financial-data-collector/SKILL.md), [output-schema.md](./financial-data-collector/references/output-schema.md), and [yfinance-pitfalls.md](./financial-data-collector/references/yfinance-pitfalls.md).

**Requirements**: Python 3.11+, `yfinance`, `pandas` (auto-installed via uv inline dependencies).

---

### 40. **excel-automation** - Excel Creation, Parsing, and macOS Control

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
# Install the skill
claude plugin install excel-automation@daymade-skills

# Then ask Claude to automate Excel workflows
"Create a formatted valuation template workbook"
"Parse this .xlsm and extract the DCF sheet"
"Generate an AppleScript sequence to zoom and scroll Excel before screenshot"
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [excel-automation/SKILL.md](./excel-automation/SKILL.md) and [formatting-reference.md](./excel-automation/references/formatting-reference.md).

**Requirements**: Python 3.8+, `uv`, `openpyxl` (auto via `uv run --with openpyxl`), macOS for AppleScript window control.

---

### 41. **capture-screen** - Programmatic macOS Screenshot Capture

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
# Install the skill
claude plugin install capture-screen@daymade-skills

# Then ask Claude to capture windows programmatically
"Find the Excel window ID and capture it silently"
"Create a multi-shot capture workflow for this workbook"
"Capture Chrome window sections with scripted scrolling"
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [capture-screen/SKILL.md](./capture-screen/SKILL.md).

**Requirements**: macOS (Swift + AppleScript + `screencapture`).

---

### 42. **continue-claude-work** - Resume Interrupted Claude Work

> **Install**: `claude plugin install daymade-claude-code@daymade-skills` (suite-only — invoked as `daymade-claude-code:continue-claude-work`)

Recover actionable context from local `~/.claude` session artifacts and continue implementation without reopening the old interactive session. Uses a bundled Python script for intelligent context extraction.

**When to use:**
- A user provides a Claude session ID and wants the task continued
- You need to inspect local `.claude` JSONL files instead of running `claude --resume`
- A previous session was interrupted and the next concrete step must be reconstructed
- A multi-agent workflow was interrupted and you need to know which subagents completed

**Key features:**
- Compact-boundary-aware extraction — reads Claude's own session compaction summaries as highest-signal context
- Subagent workflow recovery — reports completed vs. interrupted subagents with last outputs
- Session end reason detection — classifies clean exit, interrupted (ctrl-c), error cascade, or abandoned
- Size-adaptive strategy — different reading approaches for small (<500KB) vs. large (>5MB) sessions
- Noise filtering — skips progress/queue-operation/api_error messages (37-53% of session lines)
- Self-session exclusion, stale index fallback, MEMORY.md integration, git workspace state

**Example usage:**
```bash
# Then ask Claude to resume from local artifacts
"continue work from session 123e4567-e89b-12d3-a456-426614174000"
"don't resume, just read the .claude files and continue"
"check what I was working on in the last session and keep going"
```

📚 **Documentation**: See [continue-claude-work/SKILL.md](./daymade-claude-code/continue-claude-work/SKILL.md).

**Requirements**: Python 3.8+, `git` for workspace reconciliation.

---

### 43. **scrapling-skill** - Reliable Scrapling CLI Workflows

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

### 44. **ima-copilot** - Tencent IMA Companion & Installer

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

### 45. **claude-export-txt-better** - Fix Claude Code Export Formatting

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

### 46. **douban-skill** - Douban Collection Export & Sync

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

### 47. **terraform-skill** - Terraform Operational Traps

Failure patterns from real Terraform deployments — every item caused an actual incident. Organized as *exact error → root cause → copy-paste fix*. Covers provisioner timing races, SSH connection conflicts, multi-environment isolation, DNS record duplication, volume permissions, database bootstrap gaps, snapshot cross-contamination, Cloudflare credential format errors, hardcoded domains in Caddyfiles/compose, and init-data-only-on-first-boot pitfalls.

**When to use:**
- Writing `null_resource` provisioners or `remote-exec` blocks that SSH into fresh instances
- Setting up multi-environment (prod/staging/dev) Terraform with shared modules
- Debugging containers that are Restarting/unhealthy after `terraform apply`
- Hitting "docker: not found" in remote-exec, rsync connection drops in local-exec, or TLS cert errors
- Troubleshooting drift or provisioner failures during re-runs
- Configuring Caddy/gateway resources with Cloudflare credentials

**Key features:**
- Copy-paste `.hcl` snippets for each trap, not abstract advice
- Coverage spanning cloud-init, Docker, file provisioners, DNS, TLS, snapshots, and cross-env contamination
- Every pattern tagged with the exact symptom so grep finds it fast

**Example usage:**
```bash
# Trigger the skill naturally during Terraform work
"I'm getting 'docker: not found' in my null_resource provisioner after apply"
"My rsync local-exec is failing with 'connection unexpectedly closed'"
"Help me write a multi-env Terraform setup without snapshot cross-contamination"
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [terraform-skill/SKILL.md](./terraform-skill/SKILL.md) and the bundled `references/` for detailed remediation patterns.

**Requirements**: None (Terraform-adjacent knowledge only; no runtime dependencies).

---

### 48. **slides-creator** - Narrative-First Slide Deck Creation

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

### 49. **debugging-network-issues** - Evidence-Driven Network Investigation

Falsification-first methodology for network, streaming, and protocol-layer bugs where the obvious cause is probably wrong. Built from a real 5-hour SSE incident where assumption-stacking wasted hours that a 10-minute layered experiment would have resolved.

**When to use:**
- Connection resets (`ECONNRESET`, HTTP/2 `RST_STREAM`, `INTERNAL_ERROR`)
- SSE / long-polling stalls or fixed-time drops (60s, 100s, 130s)
- CDN / proxy / CGNAT idle-timeout incidents
- Any "works sometimes / fails after N seconds" pattern
- Multi-hop systems (client → CDN → LB → reverse proxy → app → upstream) where a symptom could plausibly come from several layers

**Key features:**
- Layered isolation experiments: run the same logical request through three or more paths differing by exactly one hop
- Env-gated runtime instrumentation patterns (no production-code mutation)
- Counter-review four-question filter to challenge single-cause assumptions
- Bundled probe scripts (`layered-isolation-probe.sh`, `mock-idle-upstream.py`)
- Real case study: SSE RST_STREAM at 130s caused by CGNAT idle timeout

**Requirements**: None (methodology + portable shell/Python probes).

---

### 50. **stepfun-tts** - StepFun StepAudio 2.5 Contextual TTS

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

### 52. **stepfun-asr** - StepFun StepAudio 2.5 ASR (SSE Endpoint)

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

### 53. **auto-repo-setup** - Automated Repository Setup & Environment Repair

Turn "it won't run" into "it's running" without requiring users to understand git, uv, ffmpeg, or API keys. Designed for non-technical teammates (editors, business, ops) who need to clone a repo and get it working — and for technical users who want standardized, handoff-ready project onboarding.

**When to use:**
- A non-technical user says "跑不起来", "怎么启动", "环境怎么配", or "帮我设置代码库"
- Setting up a new machine or onboarding a teammate to a codebase
- Configuring SessionStart hooks so Claude Code auto-checks environment on entry
- Sanitizing git history after accidental secret/path leaks
- Handling merge conflicts or git push failures for users who don't use git daily

**Key features:**
- **ONBOARDING.md-first workflow**: reads the project's guide, validates each step, fixes gaps iteratively
- **SessionStart hook generator**: one-command `init_session_start_hook.py` sets up auto-environment-check on every Claude Code session entry
- **Safety guardrails**: Push Safety (visibility verification before any push), PII Guard (4-layer secret scanning), NO FALLBACK principle for env vars, Git Hook Bypass ban
- **Counter-review workflow**: multi-agent security/code-quality/devops/doc review for significant changes
- **Bundled scripts**: `check_env.py` (audit git/ffmpeg/uv/python/.env), `sanitize_history.sh` (scan history for secrets/paths/domains), `init_session_start_hook.py`

**Example usage:**
```bash
# Install the skill
claude plugin install auto-repo-setup@daymade-skills

# Then ask Claude naturally
"我跑不起来这个仓库"
"帮我设置一下这个项目的环境"
"初始化 SessionStart hook"
"git push 被拒了"
```

**Requirements**: Python 3.8+, `uv` package manager. No external API keys required for the skill itself.

---

### 54. **terminal-screenshot** - See the Real Visual Result of Terminal Output

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

### 55. **pdf-to-html** - Read a PDF as Faithful HTML (with Optional Translation)

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

### 56. **asr-transcribe-to-text** - Audio/Video Transcription with Qwen3-ASR

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
- Defaults `max_tokens=200000` to defeat the upstream `mlx-audio` 8192-token truncation that silently cuts audio past ~40 minutes
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

### 57. **marketplace-dev** - Skills Repo → Plugin Marketplace

> **Install**: `claude plugin install daymade-claude-code@daymade-skills` (suite-only — invoked as `daymade-claude-code:marketplace-dev`)

Convert any Claude Code skills repository into an official plugin marketplace so users can install skills via `claude plugin marketplace add` and get auto-updates. Generates a spec-conforming `.claude-plugin/marketplace.json`, validates with `claude plugin validate`, tests real installation, and opens an upstream PR — encoding hard-won schema, version, and description anti-patterns.

**When to use:**
- Making a skills repo installable via `claude plugin install`
- Generating or fixing a `marketplace.json` (plugin distribution, one-click install, auto-update)
- Adding a new plugin to an existing marketplace and bumping the right versions
- Debugging schema rejections like `Unrecognized key: "$schema"` or duplicate plugin names

**Key features:**
- Evidence-intake phase that mines docs and local session history instead of guessing from a template
- Encodes non-obvious schema rules: `$schema` is rejected, `metadata` has only 3 valid fields, `strict: false` semantics, single-skill vs suite `source`/`skills` patterns
- Bundled `check_marketplace.sh` runs four checks (JSON syntax → `claude plugin validate` → source/skills resolution → reverse sync) and exits non-zero on failure
- Installation, cache-footprint, and GitHub-install test recipes to confirm `source` produced the intended snapshot
- Two PostToolUse hooks (validate on `marketplace.json` edit; warn on un-bumped version when a `SKILL.md` changes) that auto-activate with the plugin

**Example usage:**
```bash
# marketplace-dev lives in the daymade-claude-code suite
claude plugin install daymade-claude-code@daymade-skills

# Then ask Claude naturally
"turn this skills repo into a plugin marketplace"
"generate a marketplace.json for this repo and validate it"
"add my new skill to the marketplace and open a PR"
```

**Requirements**: `claude` CLI (for `claude plugin validate` / install tests), `jq`. Git remotes configured if opening an upstream PR.

---

### 58. **skill-creator** - Create, Improve & Benchmark Skills

> **Install**: `claude plugin install daymade-skill@daymade-skills` (suite-only — invoked as `daymade-skill:skill-creator`)

The essential meta-skill for building your own skills. Guides the full create → test → review → improve loop: drafts a SKILL.md, generates realistic test prompts, runs the skill against a baseline, helps evaluate results qualitatively and quantitatively, and iterates. Also optimizes a skill's `description` for better triggering accuracy.

**When to use:**
- Creating a skill from scratch, or editing/optimizing an existing one
- Running evals to test a skill, or benchmarking performance with variance analysis
- Improving a skill's description so Claude triggers it more reliably
- Wrapping a third-party CLI tool you just got working into a reusable companion skill

**Key features:**
- Prior-art research across conversation history, local SOPs, installed plugins/MCPs, skills.sh, official plugins, npm/PyPI — to reuse infrastructure and encode only the user's unique methodology
- The inline-vs-`context: fork` decision guide (subagents can't spawn subagents or call skills) and composable/orthogonal skill design
- `init_skill.py` scaffolding, `package_skill.py` (auto-validates), and `security_scan.py` (gitleaks-based secret/PII detection)
- Eval harness: spawn with-skill + baseline runs, draft assertions, grade, aggregate a benchmark, and review in a generated HTML viewer
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

**Requirements**: Python 3, `uv`, PyYAML (validation/packaging), gitleaks (security scan). `claude` CLI for eval/description-optimization runs.

---

### 59. **feishu-doc-scraper** - Feishu/Lark → Faithful Markdown

Extract Feishu (Lark) Docs, Wiki pages/collections, spreadsheets, and Minutes (妙记) transcripts into faithful local Markdown. The primary path uses the `lark-cli` API — it extracts the document body programmatically (no model paraphrasing), recursively follows a collection's reference graph, and reads permission boundaries from error codes; a browser-DOM path is the fallback only when lark-cli cannot reach the content.

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

### 60. **bigdata-skill** - Bigdata.com (RavenPack) SDK + REST Toolkit

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
# Install the skill
claude plugin install bigdata-skill@daymade-skills
export BIGDATA_API_KEY=bd_v2_xxxxxxxx

# Then ask Claude naturally
"pull NVIDIA's forward analyst estimates and last earnings surprise from Bigdata"
"give me a daily entity-sentiment series for this ticker"
"the bigdata MCP only gave me a tearsheet — I need the structured fields"
```

**Requirements**: A `bd_v2_` Bigdata.com API key (env var, never hardcoded), `uv`, the official `bigdata-client` SDK in an isolated venv. Optional outbound/WSS proxy only if your network needs one to reach `api.bigdata.com`.

---

### 61. **gangtise-copilot** - Gangtise Investment-Research Suite Installer

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
# Install the skill
claude plugin install gangtise-copilot@daymade-skills

# Then ask Claude naturally
"装一下 gangtise 的所有 skill 并配置好凭据"
"my gangtise skills report token is invalid — diagnose it"
"宁德时代的研报用哪个 gangtise skill 查"
```

**Requirements**: A Gangtise accessKey + secretAccessKey; `bash`, `curl`, network access to the official OBS bucket and `open.gangtise.com`. Works with Claude Code, OpenClaw, and Codex agent layouts.

---

### 62. **llm-wiki-setup** - Co-Create a Personal Investment-Research LLM Wiki

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

### 63. **benchmark-due-diligence** - Adversarial Teardown of an Envied Benchmark

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
# Install the skill
claude plugin install benchmark-due-diligence@daymade-skills

# Then ask Claude naturally
"帮我尽调一下这个创始人，他到底有没有水分"
"tear down this competitor's playbook and tell me what I can actually copy"
"this KOL claims 0-to-1M users — is that real, and is it replicable for me?"
```

**Requirements**: Web access for the collection/verification agents. Optionally composes with `deep-research`, `osint-investigate`, the `qcc` skill family, and `agent-reach`; renders a shareable report via `pdf-creator`.

---

### 64. **bilibili-source** - Login-Free Bilibili Video Data + Danmaku Fetcher

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
- API reference includes the WBI request-signing algorithm for `space/wbi/*` extension

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

### 65. **claude-usage-analyst** - Explain Claude Code Token Usage & Quota Burn

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

### 66. **marketplace-health-check** - Full 6-Dimension Repo Health Check

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

## 🎬 Interactive Demo Gallery

Want to see all demos in one place with click-to-enlarge functionality? Check out our [interactive demo gallery](./demos/index.html) or browse the [demos directory](./demos/).

## 🎯 Use Cases

### For GitHub Workflows
Use **github-ops** to streamline PR creation, issue management, and API operations.

### For Documentation
Combine **doc-to-markdown** for document conversion and **mermaid-tools** for diagram generation to create comprehensive documentation. Use **llm-icon-finder** to add brand icons.

### For Research & Analysis
Use **deep-research** to produce format-controlled research reports with evidence tables and citations. Combine with **fact-checker** to validate claims or with **twitter-reader** for social-source collection.

### For Competitive Intelligence
Use **competitors-analysis** to track and analyze competitor repositories with evidence-based approach. All findings are sourced from actual code (file:line_number), eliminating speculation. Combine with **deep-research** for comprehensive competitive landscape reports.

### For PDF & Printable Documents
Use **pdf-creator** to convert markdown to print-ready PDFs with proper Chinese font support for formal documents and reports.

### For Team Communication
Use **teams-channel-post-writer** to share knowledge and **statusline-generator** to track costs while working.

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
Use **financial-data-collector** to pull structured financial data for any US public company, then feed the JSON output into DCF modeling, comps analysis, or earnings review workflows.

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
Use **claude-code-history-files-finder** to recover deleted files from previous Claude Code sessions, search for specific implementations across conversation history, or track file evolution over time. Essential for recovering accidentally deleted code or finding that feature implementation you remember but can't locate.

### For Resuming Interrupted Claude Sessions
Use **continue-claude-work** to recover the last actionable request from local `~/.claude` artifacts and continue implementation without reopening the original session. Combine with **claude-code-history-files-finder** when you need broader cross-session search, statistics, or deleted-file recovery.

### For Web Extraction & WeChat Articles
Use **scrapling-skill** to install and validate Scrapling CLI, choose between static and browser-backed fetching, and extract clean Markdown from sites like `mp.weixin.qq.com`. Combine with **deep-research** to turn extracted sources into structured reports or with **docs-cleaner** to normalize captured article content.

### For Documentation Maintenance
Use **docs-cleaner** to consolidate redundant documentation while preserving valuable content. Perfect for cleaning up documentation sprawl after rapid development phases or merging overlapping docs into authoritative sources.

### For CLAUDE.md Optimization
Use **claude-md-progressive-disclosurer** to reduce CLAUDE.md bloat by moving detailed sections into references while keeping core rules visible.

### For Skill Discovery & Management
Use **skills-search** to find, install, and manage Claude Code skills from the CCPM registry. Perfect for discovering new skills for specific tasks, installing skill bundles for common workflows, and keeping your skill collection organized.

### For LLM Evaluation & Model Comparison
Use **promptfoo-evaluation** to set up prompt tests, compare model outputs, and run automated evaluations with custom assertions.

### For iOS App Development
Use **iOS-APP-developer** to configure XcodeGen projects, resolve SPM dependency issues, and troubleshoot code signing or device deployment.

### For macOS System Maintenance & Disk Space Recovery
Use **macos-cleaner** to intelligently analyze and reclaim disk space on macOS with safety-first approach. Unlike one-click cleaners that blindly delete, macos-cleaner explains what each file is, categorizes by risk level (🟢/🟡/🔴), and requires explicit confirmation before any deletion. Perfect for developers dealing with Docker/Homebrew/npm/pip cache bloat, users wanting to understand storage consumption, or anyone who values transparency over automation. Combines script-based precision with optional Mole visual tool integration for hybrid workflow.

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
Use **debugging-network-issues** when symptoms do not match the obvious cause: HTTP/2 `RST_STREAM`, SSE stalls at exactly 60s/100s/130s, "works sometimes but not always" failures, or anything that looks like an idle-timeout incident through CDN / proxy / CGNAT chains. The skill replaces assumption-stacking with **layered isolation experiments** — running the same logical request through three or more paths that differ by one hop — plus a counter-review pattern for shipping fixes only after the hypothesis has been falsified, not just confirmed. The cognitive-trap catalog includes reverse-path / directional asymmetry — measuring from the wrong end (or only one end) systematically misses a directional failure.

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
- **doc-to-markdown**: See `daymade-docs/doc-to-markdown/references/conversion-examples.md` for conversion scenarios
- **mermaid-tools**: See `daymade-docs/mermaid-tools/references/setup_and_troubleshooting.md` for setup guide
- **statusline-generator**: See `daymade-claude-code/statusline-generator/references/color_codes.md` for customization
- **teams-channel-post-writer**: See `teams-channel-post-writer/references/writing-guidelines.md` for quality standards
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
- **claude-code-history-files-finder**: See `daymade-claude-code/claude-code-history-files-finder/references/session_file_format.md` for JSONL structure and `daymade-claude-code/claude-code-history-files-finder/references/workflow_examples.md` for recovery workflows
- **docs-cleaner**: See `daymade-docs/docs-cleaner/SKILL.md` for consolidation workflows
- **deep-research**: See `deep-research/references/research_report_template.md` for report structure and `deep-research/references/source_quality_rubric.md` for source triage
- **pdf-creator**: See `daymade-docs/pdf-creator/SKILL.md` for PDF conversion and font setup
- **claude-md-progressive-disclosurer**: See `daymade-claude-code/claude-md-progressive-disclosurer/SKILL.md` for CLAUDE.md optimization workflow
- **skills-search**: See `daymade-skill/skills-search/SKILL.md` for CCPM CLI commands and registry operations
- **promptfoo-evaluation**: See `promptfoo-evaluation/references/promptfoo_api.md` for evaluation patterns
- **iOS-APP-developer**: See `iOS-APP-developer/references/xcodegen-full.md` for XcodeGen options and project.yml details
- **twitter-reader**: See `twitter-reader/SKILL.md` for API key setup and URL format support
- **macos-cleaner**: See `macos-cleaner/references/cleanup_targets.md` for detailed cleanup target explanations, `macos-cleaner/references/mole_integration.md` for Mole visual tool integration, and `macos-cleaner/references/safety_rules.md` for comprehensive safety guidelines
- **skill-reviewer**: See `daymade-skill/skill-reviewer/references/evaluation_checklist.md` for complete evaluation criteria and `daymade-skill/skill-reviewer/references/pr_template.md` for PR templates
- **github-contributor**: See `github-contributor/references/pr_checklist.md` for PR quality checklist, `github-contributor/references/project_evaluation.md` for project evaluation criteria, and `github-contributor/references/communication_templates.md` for issue/PR templates
- **i18n-expert**: See `i18n-expert/SKILL.md` for complete i18n setup workflow, key architecture guidance, and audit procedures
- **claude-skills-troubleshooting**: See `daymade-claude-code/claude-skills-troubleshooting/SKILL.md` for plugin troubleshooting workflow and architecture
- **fact-checker**: See `fact-checker/SKILL.md` for fact-checking workflow and claim verification process
- **competitors-analysis**: See `competitors-analysis/SKILL.md` for evidence-based analysis workflow and `competitors-analysis/references/profile_template.md` for competitor profile template
- **windows-remote-desktop-connection-doctor**: See `windows-remote-desktop-connection-doctor/references/windows_app_log_analysis.md` for log parsing patterns and `windows-remote-desktop-connection-doctor/references/avd_transport_protocols.md` for transport protocol details
- **product-analysis**: See `product-analysis/SKILL.md` for workflow and `product-analysis/references/synthesis_methodology.md` for cross-agent weighting and recommendation logic
- **excel-automation**: See `excel-automation/SKILL.md` for create/parse/control workflows and `excel-automation/references/formatting-reference.md` for formatting standards
- **capture-screen**: See `capture-screen/SKILL.md` for CGWindowID-based screenshot workflows on macOS
- **continue-claude-work**: See `daymade-claude-code/continue-claude-work/SKILL.md` for local artifact recovery, drift checks, and resume workflow
- **scrapling-skill**: See `scrapling-skill/SKILL.md` for the CLI workflow and `scrapling-skill/references/troubleshooting.md` for verified Scrapling failure modes
- **ima-copilot**: See `ima-copilot/SKILL.md` for the wrapper architecture and routing, `ima-copilot/references/installation_flow.md` for the install deep dive, `ima-copilot/references/known_issues.md` for the issue registry and repair commands, and `ima-copilot/references/search_best_practices.md` for the fan-out strategy and 100-result truncation details
- **claude-export-txt-better**: See `daymade-claude-code/claude-export-txt-better/SKILL.md` for the workflow, `daymade-claude-code/claude-export-txt-better/scripts/fix-claude-export.py` for the reconstruction algorithm, and `daymade-claude-code/claude-export-txt-better/evals/` for real regression fixtures
- **douban-skill**: See `douban-skill/SKILL.md` for the export workflow and `douban-skill/references/troubleshooting.md` for the complete log of 7 tested scraping approaches and why each failed
- **terraform-skill**: See `terraform-skill/SKILL.md` for the full catalogue of operational traps organised by exact error → root cause → copy-paste fix
- **slides-creator**: See `slides-creator/SKILL.md` for the narrative-first workflow, `slides-creator/references/narrative-design-guide.md` for the ABCDEFG model, and `slides-creator/references/content-creation-first-law.md` for the universal content creation principle
- **debugging-network-issues**: See `debugging-network-issues/SKILL.md` for the falsification-first workflow, `debugging-network-issues/references/layered-isolation-experiment.md` for the multi-hop isolation pattern, and `debugging-network-issues/references/case-sse-rst-130s.md` for the real production case study
- **stepfun-tts**: See `stepfun-tts/SKILL.md` for the Contextual TTS decision tree and `stepfun-tts/references/migration_from_v2.md` for the `voice_label` → `instruction` migration playbook plus the censorship rewrite list
- **stepfun-asr**: See `stepfun-asr/SKILL.md` for the SSE-endpoint workflow and the four ASR-side traps (wrong endpoint, Plan-vs-Normal key, repetition hallucination, SSE `error` event). `stepfun-asr/references/api_reference.md` documents the exact JSON request body and SSE event contract for raw HTTP integration

## 🛠️ Requirements

- **Claude Code** 2.0.13 or higher
- **Python 3.6+** (for scripts in multiple skills)
- **gh CLI** (for github-ops)
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
- **macOS + Xcode, XcodeGen** (for iOS-APP-developer)
- **Codex CLI** (optional, for product-analysis multi-model mode)
- **uv + openpyxl** (for excel-automation): `uv run --with openpyxl ...`
- **macOS** (for capture-screen and excel-automation AppleScript control workflows)
- **Python 3.8+** (for continue-claude-work): bundled script for session extraction (no external dependencies)
- **uv + Scrapling CLI** (for scrapling-skill): `uv tool install 'scrapling[shell]'` and `scrapling install` for browser-backed fetches
- **Node.js 18+ + curl + unzip** (for ima-copilot): `npx skills` is fetched on demand from the npm registry; IMA OpenAPI credentials from [https://ima.qq.com/agent-interface](https://ima.qq.com/agent-interface)
- **StepFun API key** (for stepfun-tts and stepfun-asr — must be "Normal" tier, Plan keys silently fail on audio endpoints): Available at [https://platform.stepfun.com/](https://platform.stepfun.com/) → API Keys

## ❓ FAQ

### How do I know which skills to install?

Start with **skill-creator** if you want to create your own skills. Otherwise, browse the [Other Available Skills](#-other-available-skills) section and install what matches your workflow.

### Can I use these skills without Claude Code?

No, these skills are specifically designed for Claude Code. You'll need Claude Code 2.0.13 or higher.

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

Contributions are welcome! Please feel free to:

1. Open issues for bugs or feature requests
2. Submit pull requests with improvements
3. Share feedback on skill quality

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

Last updated: 2026-06-05 | Marketplace version 1.60.1
