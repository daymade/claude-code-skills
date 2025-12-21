# Claude Code Skills Marketplace

<div align="center">

[![English](https://img.shields.io/badge/Language-English-blue)](./README.md)
[![简体中文](https://img.shields.io/badge/语言-简体中文-red)](./README.zh-CN.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Skills](https://img.shields.io/badge/skills-25-blue.svg)](https://github.com/daymade/claude-code-skills)
[![Version](https://img.shields.io/badge/version-1.18.0-green.svg)](https://github.com/daymade/claude-code-skills)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-2.0.13+-purple.svg)](https://claude.com/code)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](./CONTRIBUTING.md)
[![Maintenance](https://img.shields.io/badge/Maintained%3F-yes-green.svg)](https://github.com/daymade/claude-code-skills/graphs/commit-activity)

</div>

Professional Claude Code skills marketplace featuring 25 production-ready skills for enhanced development workflows.

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
All plugin commands should use `claude plugin ...` (there is no `/plugin` command).

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

Converts documents to markdown with Windows/WSL path handling and Obsidian integration.

**When to use:**
- Converting .doc/.docx/PDF/PPTX to markdown
- Processing Confluence exports
- Handling Windows/WSL path conversions
- Working with markitdown utility

**Key features:**
- Multi-format document conversion
- Confluence export processing
- Windows/WSL path automation
- Obsidian vault integration
- Helper scripts for path conversion

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
- Android client workaround for nsig extraction issues (automatic)
- Audio-only download with MP3 conversion
- Format listing and custom format selection
- Output directory customization
- Network error handling for proxy/restricted environments
- Availability check for yt-dlp dependency

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

## 🎬 Interactive Demo Gallery

Want to see all demos in one place with click-to-enlarge functionality? Check out our [interactive demo gallery](./demos/index.html) or browse the [demos directory](./demos/).

## 🎯 Use Cases

### For GitHub Workflows
Use **github-ops** to streamline PR creation, issue management, and API operations.

### For Documentation
Combine **markdown-tools** for document conversion and **mermaid-tools** for diagram generation to create comprehensive documentation. Use **llm-icon-finder** to add brand icons.

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
- **pdf-creator**: See `pdf-creator/SKILL.md` for PDF conversion and font setup
- **claude-md-progressive-disclosurer**: See `claude-md-progressive-disclosurer/SKILL.md` for CLAUDE.md optimization workflow
- **skills-search**: See `skills-search/SKILL.md` for CCPM CLI commands and registry operations
- **promptfoo-evaluation**: See `promptfoo-evaluation/references/promptfoo_api.md` for evaluation patterns
- **iOS-APP-developer**: See `iOS-APP-developer/references/xcodegen-full.md` for XcodeGen options and project.yml details

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
- **asciinema** (optional, for cli-demo-generator interactive recording)
- **ccusage** (optional, for statusline cost tracking)
- **pandas & matplotlib** (optional, for ppt-creator chart generation)
- **Marp CLI** (optional, for ppt-creator Marp PPTX export): `npm install -g @marp-team/marp-cli`
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

Last updated: 2025-12-20 | Marketplace version 1.18.0
