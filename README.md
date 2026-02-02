# Claude Code Skills Marketplace

<div align="center">

[![English](https://img.shields.io/badge/Language-English-blue)](./README.md)
[![简体中文](https://img.shields.io/badge/语言-简体中文-red)](./README.zh-CN.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Skills](https://img.shields.io/badge/skills-35-blue.svg)](https://github.com/daymade/claude-code-skills)
[![Version](https://img.shields.io/badge/version-1.30.0-green.svg)](https://github.com/daymade/claude-code-skills)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-2.0.13+-purple.svg)](https://claude.com/code)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](./CONTRIBUTING.md)
[![Maintenance](https://img.shields.io/badge/Maintained%3F-yes-green.svg)](https://github.com/daymade/claude-code-skills/graphs/commit-activity)

</div>

Professional Claude Code skills marketplace featuring 35 production-ready skills for enhanced development workflows.

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

### Why skill-creator First?

- **🎯 Foundation**: Learn how skills work by creating your own
- **🛠️ Complete Toolkit**: Initialization, validation, and packaging scripts included
- **📖 Best Practices**: Learn from production-ready examples
- **🚀 Quick Start**: Generate skill templates in seconds
- **✅ Quality Assurance**: Built-in validation ensures your skills meet standards

### Quick Install

**In Claude Code / AdaL (in-app):**
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
claude plugin install skill-creator@daymade-skills
```

### What You Can Do

After installing skill-creator, simply ask Claude Code:

```
"Create a new skill called my-awesome-skill in ~/my-skills"

"Validate my skill at ~/my-skills/my-awesome-skill"

"Package my skill at ~/my-skills/my-awesome-skill for distribution"
```

Claude Code, with skill-creator loaded, will guide you through the entire skill creation process - from understanding your requirements to packaging the final skill.

📚 **Full documentation**: [skill-creator/SKILL.md](./skill-creator/SKILL.md)

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
claude plugin install skill-creator@daymade-skills
```

**Install Other Skills:**
```bash
# GitHub operations
claude plugin install github-ops@daymade-skills

# Document conversion
claude plugin install markdown-tools@daymade-skills

# Diagram generation
claude plugin install mermaid-tools@daymade-skills

# Statusline customization
claude plugin install statusline-generator@daymade-skills

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

# Presentation creation
claude plugin install ppt-creator@daymade-skills

# YouTube video/audio downloading
claude plugin install youtube-downloader@daymade-skills

# Secure repomix packaging
claude plugin install repomix-safe-mixer@daymade-skills

# ASR transcript correction
claude plugin install transcript-fixer@daymade-skills

# Video comparison and quality analysis
claude plugin install video-comparer@daymade-skills

# QA testing infrastructure with autonomous execution
claude plugin install qa-expert@daymade-skills

# Prompt optimization using EARS methodology
claude plugin install prompt-optimizer@daymade-skills

# Session history recovery
claude plugin install claude-code-history-files-finder@daymade-skills

# Documentation consolidation
claude plugin install docs-cleaner@daymade-skills

# PDF generation with Chinese font support
claude plugin install pdf-creator@daymade-skills

# CLAUDE.md progressive disclosure optimization
claude plugin install claude-md-progressive-disclosurer@daymade-skills

# CCPM skill registry search and management
claude plugin install skills-search@daymade-skills

# Promptfoo LLM evaluation framework
claude plugin install promptfoo-evaluation@daymade-skills

# iOS app development
claude plugin install iOS-APP-developer@daymade-skills

# Twitter/X content fetching
claude plugin install twitter-reader@daymade-skills

# Skill quality review and improvement
claude plugin install skill-reviewer@daymade-skills

# GitHub contribution strategy
claude plugin install github-contributor@daymade-skills
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

### 2. **markdown-tools** - Document Conversion Suite

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

![Markdown Tools Demo](./demos/markdown-tools/convert-docs.gif)

---

### 3. **mermaid-tools** - Diagram Generation

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

📚 **Documentation**: See [transcript-fixer/references/](./transcript-fixer/references/) for workflow guides, SQL queries, troubleshooting, best practices, team collaboration, and API setup.

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

📚 **Documentation**: See [claude-code-history-files-finder/references/](./claude-code-history-files-finder/references/) for:
- `session_file_format.md` - JSONL structure and extraction patterns
- `workflow_examples.md` - Detailed recovery and analysis workflows

---

### 19. **docs-cleaner** - Documentation Consolidation

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

📚 **Documentation**: See [skills-search/SKILL.md](./skills-search/SKILL.md) for complete command reference

**Requirements**: CCPM CLI (`npm install -g @daymade/ccpm`)

---

### 21. **pdf-creator** - PDF Creation with Chinese Font Support

Create professional PDF documents from markdown with proper Chinese typography using WeasyPrint.

**When to use:**
- Converting markdown to PDF for sharing or printing
- Generating formal documents (legal filings, reports)
- Ensuring correct Chinese font rendering

**Key features:**
- WeasyPrint + Markdown conversion pipeline
- Built-in Chinese font fallbacks
- A4 layout defaults with print-friendly margins
- Batch conversion scripts

**Example usage:**
```bash
uv run --with weasyprint --with markdown scripts/md_to_pdf.py input.md output.pdf
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [pdf-creator/SKILL.md](./pdf-creator/SKILL.md) for setup and workflow details.

**Requirements**: Python 3.8+, `weasyprint`, `markdown`

---

### 22. **claude-md-progressive-disclosurer** - CLAUDE.md Optimization

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

📚 **Documentation**: See [claude-md-progressive-disclosurer/SKILL.md](./claude-md-progressive-disclosurer/SKILL.md).

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
claude plugin install skill-reviewer@daymade-skills

# Self-review your skill
"Validate my skill at ~/my-skills/my-awesome-skill"

# Review external skill repository
"Review the skills at https://github.com/user/skill-repo"

# Auto-PR improvements
"Fork, improve, and submit PR for https://github.com/user/skill-repo"
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [skill-reviewer/references/](./skill-reviewer/references/) for:
- `evaluation_checklist.md` - Complete skill evaluation criteria
- `pr_template.md` - Professional PR description template
- `marketplace_template.json` - Marketplace configuration template

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
# Install the skill
claude plugin install claude-skills-troubleshooting@daymade-skills

# Run diagnostic
python3 scripts/diagnose_plugins.py

# Batch enable missing plugins
python3 scripts/enable_all_plugins.py daymade-skills
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [claude-skills-troubleshooting/SKILL.md](./claude-skills-troubleshooting/SKILL.md) for complete troubleshooting workflow and architecture guidance.

**Requirements**: None (uses Claude Code built-in Python)

---

### 33. **meeting-minutes-taker** - Meeting Minutes Generator

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
# Install the skill
claude plugin install meeting-minutes-taker@daymade-skills

# Then provide a meeting transcript and request minutes
```

**🎬 Live Demo**

*Coming soon*

📚 **Documentation**: See [meeting-minutes-taker/SKILL.md](./meeting-minutes-taker/SKILL.md) for complete workflow and template guidance.

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

## 🎬 Interactive Demo Gallery

Want to see all demos in one place with click-to-enlarge functionality? Check out our [interactive demo gallery](./demos/index.html) or browse the [demos directory](./demos/).

## 🎯 Use Cases

### For GitHub Workflows
Use **github-ops** to streamline PR creation, issue management, and API operations.

### For Documentation
Combine **markdown-tools** for document conversion and **mermaid-tools** for diagram generation to create comprehensive documentation. Use **llm-icon-finder** to add brand icons.

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
Use **ppt-creator** to generate professional slide decks with data visualizations, structured storytelling, and complete PPTX output for pitches, reviews, and keynotes.

### For Video Quality Analysis
Use **video-comparer** to analyze compression results, evaluate codec performance, and generate interactive comparison reports. Combine with **youtube-downloader** to compare different quality downloads.

### For Media & Content Download
Use **youtube-downloader** to download YouTube videos and extract audio from videos with automatic workarounds for common download issues.

### For Transcription & ASR Correction
Use **transcript-fixer** to correct speech-to-text errors in meeting notes, lectures, and interviews through dictionary-based rules and AI-powered corrections with automatic learning.

### For Meeting Documentation
Use **meeting-minutes-taker** to transform raw meeting transcripts into structured, evidence-based minutes. Combine with **transcript-fixer** to clean up ASR errors before generating minutes. Features multi-pass generation with UNION merge to avoid content loss.

### For QA Testing & Quality Assurance
Use **qa-expert** to establish comprehensive QA testing infrastructure with autonomous LLM execution, Google Testing Standards, and OWASP security testing. Perfect for project launches, third-party QA handoffs, and enforcing quality gates (100% execution, ≥80% pass rate, 0 P0 bugs). The master prompt enables 100x faster test execution with zero tracking errors.

### For Prompt Engineering & Requirements Engineering
Use **prompt-optimizer** to transform vague feature requests into precise EARS specifications with domain theory grounding. Perfect for product requirements documents, AI-assisted coding, and learning prompt engineering best practices. Combine with **skill-creator** to create well-structured skill prompts, or with **ppt-creator** to ensure presentation content requirements are clearly specified.

### For Session History & File Recovery
Use **claude-code-history-files-finder** to recover deleted files from previous Claude Code sessions, search for specific implementations across conversation history, or track file evolution over time. Essential for recovering accidentally deleted code or finding that feature implementation you remember but can't locate.

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
Use **twitter-reader** to fetch tweet content without JavaScript rendering or authentication. Perfect for documenting social media discussions, archiving threads, analyzing tweet content, or gathering reference material from Twitter/X. Combine with **markdown-tools** to convert fetched content into other formats, or with **repomix-safe-mixer** to package research collections securely.

### For Skill Quality & Open-Source Contributions
Use **skill-reviewer** to validate your own skills against best practices before publishing, or to review and improve others' skill repositories. Combine with **github-contributor** to find high-impact open-source projects, create professional PRs, and build your contributor reputation. Perfect for developers who want to contribute to the Claude Code ecosystem or any GitHub project systematically.

### For Internationalization & Localization
Use **i18n-expert** to set up complete i18n infrastructure for React/Next.js/Vue applications, audit existing implementations for missing translation keys, and ensure locale parity between en-US and zh-CN. Perfect for teams launching products to global markets, maintaining multi-language UIs, or replacing hard-coded strings with proper i18n keys. Combine with **skill-creator** to create locale-aware skills, or with **docs-cleaner** to consolidate documentation across multiple languages.

### For Plugin & Skill Troubleshooting
Use **claude-skills-troubleshooting** to diagnose and resolve Claude Code plugin and skill configuration issues. Debug why plugins appear installed but don't show in available skills, understand the installed_plugins.json vs settings.json enabledPlugins architecture, and batch-enable missing plugins from a marketplace. Essential for marketplace maintainers debugging installation issues, developers troubleshooting skill activation, or anyone confused by the GitHub #17832 auto-enable bug.

## 📚 Documentation

Each skill includes:
- **SKILL.md**: Core instructions and workflows
- **scripts/**: Executable utilities (Python/Bash)
- **references/**: Detailed documentation
- **assets/**: Templates and resources (where applicable)

### Quick Links

- **github-ops**: See `github-ops/references/api_reference.md` for API documentation
- **markdown-tools**: See `markdown-tools/references/conversion-examples.md` for conversion scenarios
- **mermaid-tools**: See `mermaid-tools/references/setup_and_troubleshooting.md` for setup guide
- **statusline-generator**: See `statusline-generator/references/color_codes.md` for customization
- **teams-channel-post-writer**: See `teams-channel-post-writer/references/writing-guidelines.md` for quality standards
- **repomix-unmixer**: See `repomix-unmixer/references/repomix-format.md` for format specifications
- **skill-creator**: See `skill-creator/SKILL.md` for complete skill creation workflow
- **llm-icon-finder**: See `llm-icon-finder/references/icons-list.md` for available icons
- **cli-demo-generator**: See `cli-demo-generator/references/vhs_syntax.md` for VHS syntax and `cli-demo-generator/references/best_practices.md` for demo guidelines
- **cloudflare-troubleshooting**: See `cloudflare-troubleshooting/references/api_overview.md` for API documentation
- **ui-designer**: See `ui-designer/SKILL.md` for design system extraction workflow
- **ppt-creator**: See `ppt-creator/references/WORKFLOW.md` for 9-stage creation process and `ppt-creator/references/ORCHESTRATION_OVERVIEW.md` for automation
- **youtube-downloader**: See `youtube-downloader/SKILL.md` for usage examples and troubleshooting
- **repomix-safe-mixer**: See `repomix-safe-mixer/references/common_secrets.md` for detected credential patterns
- **video-comparer**: See `video-comparer/references/video_metrics.md` for quality metrics interpretation and `video-comparer/references/configuration.md` for customization options
- **transcript-fixer**: See `transcript-fixer/references/workflow_guide.md` for step-by-step workflows and `transcript-fixer/references/team_collaboration.md` for collaboration patterns
- **qa-expert**: See `qa-expert/references/master_qa_prompt.md` for autonomous execution (100x speedup) and `qa-expert/references/google_testing_standards.md` for AAA pattern and OWASP testing
- **prompt-optimizer**: See `prompt-optimizer/references/ears_syntax.md` for EARS transformation patterns, `prompt-optimizer/references/domain_theories.md` for theory catalog, and `prompt-optimizer/references/examples.md` for complete transformations
- **claude-code-history-files-finder**: See `claude-code-history-files-finder/references/session_file_format.md` for JSONL structure and `claude-code-history-files-finder/references/workflow_examples.md` for recovery workflows
- **docs-cleaner**: See `docs-cleaner/SKILL.md` for consolidation workflows
- **deep-research**: See `deep-research/references/research_report_template.md` for report structure and `deep-research/references/source_quality_rubric.md` for source triage
- **pdf-creator**: See `pdf-creator/SKILL.md` for PDF conversion and font setup
- **claude-md-progressive-disclosurer**: See `claude-md-progressive-disclosurer/SKILL.md` for CLAUDE.md optimization workflow
- **skills-search**: See `skills-search/SKILL.md` for CCPM CLI commands and registry operations
- **promptfoo-evaluation**: See `promptfoo-evaluation/references/promptfoo_api.md` for evaluation patterns
- **iOS-APP-developer**: See `iOS-APP-developer/references/xcodegen-full.md` for XcodeGen options and project.yml details
- **twitter-reader**: See `twitter-reader/SKILL.md` for API key setup and URL format support
- **macos-cleaner**: See `macos-cleaner/references/cleanup_targets.md` for detailed cleanup target explanations, `macos-cleaner/references/mole_integration.md` for Mole visual tool integration, and `macos-cleaner/references/safety_rules.md` for comprehensive safety guidelines
- **skill-reviewer**: See `skill-reviewer/references/evaluation_checklist.md` for complete evaluation criteria, `skill-reviewer/references/pr_template.md` for PR templates, and `skill-reviewer/references/marketplace_template.json` for marketplace configuration
- **github-contributor**: See `github-contributor/references/pr_checklist.md` for PR quality checklist, `github-contributor/references/project_evaluation.md` for project evaluation criteria, and `github-contributor/references/communication_templates.md` for issue/PR templates
- **i18n-expert**: See `i18n-expert/SKILL.md` for complete i18n setup workflow, key architecture guidance, and audit procedures
- **claude-skills-troubleshooting**: See `claude-skills-troubleshooting/SKILL.md` for plugin troubleshooting workflow and architecture
- **fact-checker**: See `fact-checker/SKILL.md` for fact-checking workflow and claim verification process
- **competitors-analysis**: See `competitors-analysis/SKILL.md` for evidence-based analysis workflow and `competitors-analysis/references/profile_template.md` for competitor profile template

## 🛠️ Requirements

- **Claude Code** 2.0.13 or higher
- **Python 3.6+** (for scripts in multiple skills)
- **gh CLI** (for github-ops)
- **markitdown** (for markdown-tools)
- **mermaid-cli** (for mermaid-tools)
- **yt-dlp** (for youtube-downloader): `brew install yt-dlp` or `pip install yt-dlp`
- **FFmpeg/FFprobe** (for video-comparer): `brew install ffmpeg`, `apt install ffmpeg`, or `winget install ffmpeg`
- **weasyprint, markdown** (for pdf-creator)
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

Last updated: 2026-01-22 | Marketplace version 1.23.0
