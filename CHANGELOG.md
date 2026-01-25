# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- None

## [1.27.0] - 2026-01-25

### Added
- **Enhanced Skill**: markdown-tools v1.2.0 - Multi-tool orchestration with Heavy Mode
  - Dual mode architecture: Quick Mode (fast) and Heavy Mode (best quality)
  - New `convert.py` - Main orchestrator with tool selection matrix
  - New `merge_outputs.py` - Segment-level multi-tool output merger
  - New `validate_output.py` - Quality validation with HTML reports
  - Enhanced `extract_pdf_images.py` - Image extraction with metadata (page, position, dimensions)
  - PyMuPDF4LLM integration for LLM-optimized PDF conversion
  - pandoc integration for DOCX/PPTX structure preservation
  - Quality metrics: text retention, table retention, image retention
  - New references: heavy-mode-guide.md, tool-comparison.md

### Changed
- Updated marketplace version from 1.26.0 to 1.27.0
- Updated markdown-tools plugin version from 1.1.0 to 1.2.0

## [1.26.0] - 2026-01-25

### Added
- **New Skill**: deep-research - Format-controlled research reports with evidence mapping
  - Report spec and format contract workflow
  - Multi-pass parallel drafting with UNION merge
  - Evidence table with source quality rubric
  - Citation verification and conflict handling
  - Bundled references: report template, formatting rules, research plan checklist, source quality rubric, completeness checklist

### Changed
- Updated marketplace skills count from 33 to 34
- Updated marketplace version from 1.25.0 to 1.26.0
- Updated README.md badges (skills count, version)
- Updated README.md to include deep-research in skills listing
- Updated README.zh-CN.md badges (skills count, version)
- Updated README.zh-CN.md to include deep-research in skills listing
- Updated CLAUDE.md skills count from 33 to 34
- Added deep-research use case section to README.md
- Added deep-research use case section to README.zh-CN.md
- Added deep-research documentation quick link to README.md
- Added deep-research documentation quick link to README.zh-CN.md

## [1.25.0] - 2026-01-24

### Added
- **New Skill**: meeting-minutes-taker - Transform meeting transcripts into structured minutes
  - Multi-pass parallel generation with UNION merge strategy
  - Evidence-based recording with speaker quotes
  - Mermaid diagrams for architecture discussions
  - Iterative human-in-the-loop refinement workflow
  - Bundled references: template and completeness checklist

### Changed
- Updated marketplace skills count from 32 to 33
- Updated marketplace version from 1.24.0 to 1.25.0
- Updated skill-creator to v1.3.0:
  - Added Step 5: Sanitization Review (Optional)
  - New references/sanitization_checklist.md with 8 categories of content to sanitize
  - Automated grep scan commands for detecting sensitive content
  - 3-phase sanitization process and completion checklist

## [1.24.0] - 2026-01-22

### Added
- **New Skill**: claude-skills-troubleshooting - Diagnose and resolve Claude Code plugin and skill configuration issues
  - Plugin installation and enablement debugging
  - installed_plugins.json vs settings.json enabledPlugins diagnosis
  - Marketplace cache freshness detection
  - Plugin state architecture documentation
  - Bundled diagnostic script (diagnose_plugins.py)
  - Batch enable script for missing plugins (enable_all_plugins.py)
  - Known GitHub issues tracking (#17832, #19696, #17089, #13543, #16260)
  - Skills vs Commands architecture explanation

### Changed
- Updated marketplace skills count from 31 to 32
- Updated marketplace version from 1.23.0 to 1.24.0
- Updated README.md badges (skills count, version)
- Updated README.md to include claude-skills-troubleshooting in skills listing
- Updated README.zh-CN.md badges (skills count, version)
- Updated README.zh-CN.md to include claude-skills-troubleshooting in skills listing
- Updated CLAUDE.md skills count from 31 to 32
- Added claude-skills-troubleshooting use case section to README.md
- Added claude-skills-troubleshooting use case section to README.zh-CN.md

## [1.23.0] - 2026-01-22

### Added
- **New Skill**: i18n-expert - Complete internationalization/localization setup and auditing for UI codebases
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
  - Scope inputs: framework, existing i18n state, target locales, translation quality needs

### Changed
- Updated marketplace skills count from 30 to 31
- Updated marketplace version from 1.22.0 to 1.23.0
- Updated README.md badges (skills count, version)
- Updated README.md to include i18n-expert in skills listing
- Updated README.zh-CN.md badges (skills count, version)
- Updated README.zh-CN.md to include i18n-expert in skills listing
- Updated CLAUDE.md skills count from 30 to 31
- Added i18n-expert use case section to README.md
- Added i18n-expert use case section to README.zh-CN.md

### Changed
- None

### Deprecated
- None

### Removed
- None

### Fixed
- None

### Security
- None

## [1.22.0] - 2026-01-15

### Added
- **New Skill**: skill-reviewer - Reviews and improves Claude Code skills against official best practices
  - Self-review mode: Validate your own skills before publishing
  - External review mode: Evaluate others' skill repositories
  - Auto-PR mode: Fork, improve, and submit PRs to external repos
  - Automated validation via bundled skill-creator scripts
  - Evaluation checklist covering frontmatter, instructions, and resources
  - Additive-only contribution principle (never delete files)
  - PR guidelines with tone recommendations and templates
  - Self-review checklist for respect verification
  - References: evaluation_checklist.md, pr_template.md, marketplace_template.json
  - Auto-install dependencies: automatically installs skill-creator if missing

- **New Skill**: github-contributor - Strategic guide for becoming an effective GitHub contributor
  - Four contribution types: Documentation, Code Quality, Bug Fixes, Features
  - Project selection criteria with red flags
  - PR excellence workflow with templates
  - Reputation building ladder (Documentation → Bug Fixes → Features → Maintainer)
  - GitHub CLI command reference
  - Conventional commit message format
  - Common mistakes and best practices
  - References: pr_checklist.md, project_evaluation.md, communication_templates.md

### Changed
- Updated marketplace skills count from 28 to 30
- Updated marketplace version from 1.21.1 to 1.22.0
- Updated README.md badges (skills count: 30, version: 1.22.0)
- Updated README.md to include skill-reviewer in skills listing
- Updated README.md to include github-contributor in skills listing
- Updated README.zh-CN.md badges (skills count: 30, version: 1.22.0)
- Updated README.zh-CN.md to include skill-reviewer in skills listing
- Updated README.zh-CN.md to include github-contributor in skills listing
- Updated CLAUDE.md skills count from 28 to 30
- Added skill-reviewer use case section to README.md
- Added github-contributor use case section to README.md
- Added skill-reviewer use case section to README.zh-CN.md
- Added github-contributor use case section to README.zh-CN.md

## [1.21.1] - 2026-01-11

### Changed
- **Updated Skill**: macos-cleaner v1.0.0 → v1.1.0 - Major improvements based on real-world usage
  - Added "Value Over Vanity" principle: Goal is identifying truly useless items, not maximizing cleanup numbers
  - Added "Network Environment Awareness": Consider slow internet (especially in China) when recommending cache deletion
  - Added "Impact Analysis Required": Every cleanup recommendation must explain consequences
  - Added comprehensive "Anti-Patterns" section: What NOT to delete (Xcode DerivedData, npm _cacache, uv cache, Playwright, iOS DeviceSupport, etc.)
  - Added "Multi-Layer Deep Exploration" guide: Complete tmux + Mole TUI navigation workflow
  - Added "High-Quality Report Template": Proven 3-tier classification report format (🟢/🟡/🔴)
  - Added "Report Quality Checklist": 8-point verification before presenting findings
  - Added explicit prohibition of `docker volume prune -f` - must confirm per-project
  - Updated safety principles to emphasize cache value over cleanup metrics

## [1.21.0] - 2026-01-11

### Added
- **New Skill**: macos-cleaner - Intelligent macOS disk space analysis and cleanup with safety-first philosophy
  - Smart analysis of system caches, application caches, logs, and temporary files
  - Application remnant detection (orphaned data from uninstalled apps)
  - Large file discovery with automatic categorization (videos, archives, databases, disk images)
  - Development environment cleanup (Docker, Homebrew, npm, pip, Git repositories)
  - Interactive safe deletion with user confirmation at every step
  - Risk-level categorization (🟢 Safe / 🟡 Caution / 🔴 Keep)
  - Integration guide for Mole visual cleanup tool
  - Before/after cleanup reports with space recovery metrics
  - Bundled scripts: `analyze_caches.py`, `analyze_dev_env.py`, `analyze_large_files.py`, `find_app_remnants.py`, `safe_delete.py`, `cleanup_report.py`
  - Comprehensive safety rules and cleanup target documentation
  - Time Machine backup recommendations for large deletions
  - Professional user experience: analyze first, explain thoroughly, execute with confirmation

### Changed
- Updated marketplace skills count from 27 to 28
- Updated marketplace version from 1.20.0 to 1.21.0
- Updated README.md badges (skills count: 28, version: 1.21.0)
- Updated README.md to include macos-cleaner in skills listing
- Updated README.zh-CN.md badges (skills count: 28, version: 1.21.0)
- Updated README.zh-CN.md to include macos-cleaner in skills listing
- Updated CLAUDE.md skills count from 27 to 28
- Added macos-cleaner use case section to README.md
- Added macos-cleaner use case section to README.zh-CN.md

## [1.20.0] - 2026-01-11

### Added
- **New Skill**: twitter-reader - Fetch Twitter/X post content using Jina.ai API
  - Bypass JavaScript restrictions without authentication
  - Retrieve tweet content including author, timestamp, post text, images, and thread replies
  - Support for individual posts or batch fetching from x.com or twitter.com URLs
  - Bundled scripts: `fetch_tweet.py` (Python) and `fetch_tweets.sh` (Bash)
  - Environment variable configuration for secure API key management
  - Supports both x.com and twitter.com URL formats

### Changed
- Updated marketplace skills count from 26 to 27
- Updated marketplace version from 1.19.0 to 1.20.0
- Updated README.md badges (skills count: 27, version: 1.20.0)
- Updated README.md to include twitter-reader in skills listing
- Updated README.zh-CN.md badges (skills count: 27, version: 1.20.0)
- Updated README.zh-CN.md to include twitter-reader in skills listing
- Updated CLAUDE.md skills count from 26 to 27
- Added twitter-reader use case section to README.md
- Added twitter-reader use case section to README.zh-CN.md

### Security
- **twitter-reader**: Implemented secure API key management using environment variables
  - Removed hardcoded API keys from all scripts and documentation
  - Added validation for JINA_API_KEY environment variable
  - Enforced HTTPS-only URLs in Python script

## [1.18.2] - 2026-01-05

### Changed
- **claude-md-progressive-disclosurer**: Enhanced workflow with safety and verification features
  - Added mandatory backup step (Step 0) before any modifications
  - Added pre-execution verification checklist (Step 3.5) to prevent information loss
  - Added post-optimization testing (Step 5) for discoverability validation
  - Added exception criteria for size guidelines (safety-critical, high-frequency, security-sensitive)
  - Added project-level vs user-level CLAUDE.md guidance
  - Updated references/progressive_disclosure_principles.md with verification methods
- Updated claude-md-progressive-disclosurer plugin version from 1.0.0 to 1.0.1

## [1.18.1] - 2025-12-28

### Changed
- **markdown-tools**: Enhanced with PDF image extraction capability
  - Added `extract_pdf_images.py` script using PyMuPDF
  - Refactored SKILL.md for clearer workflow documentation
  - Updated installation instructions to use `markitdown[pdf]` extra
- Updated marketplace version from 1.18.0 to 1.18.1

## [1.18.0] - 2025-12-20

### Added
- **New Skill**: pdf-creator - Convert markdown to PDF with Chinese font support (WeasyPrint)
- **New Skill**: claude-md-progressive-disclosurer - Optimize CLAUDE.md with progressive disclosure
- **New Skill**: promptfoo-evaluation - Promptfoo-based LLM evaluation workflows
- **New Skill**: iOS-APP-developer - iOS app development with XcodeGen, SwiftUI, and SPM

### Changed
- Updated marketplace skills count from 23 to 25
- Updated marketplace version from 1.16.0 to 1.18.0
- Updated README/README.zh-CN badges, skill lists, use cases, quick links, and requirements
- Updated QUICKSTART docs to clarify marketplace install syntax and remove obsolete links
- Updated CLAUDE.md skill counts and added the new skills to the list

## [1.16.0] - 2025-12-11

### Added
- **New Skill**: skills-search - CCPM registry search and management
  - Search for Claude Code skills in the CCPM registry
  - Install skills by name with `ccpm install <skill-name>`
  - List installed skills with `ccpm list`
  - Get detailed skill information with `ccpm info <skill-name>`
  - Uninstall skills with `ccpm uninstall <skill-name>`
  - Install skill bundles (web-dev, content-creation, developer-tools)
  - Supports multiple installation formats (registry, GitHub owner/repo, full URLs)
  - Troubleshooting guidance for common issues

### Changed
- Updated marketplace skills count from 22 to 23
- Updated marketplace version from 1.15.0 to 1.16.0
- Updated README.md badges (skills count: 23, version: 1.16.0)
- Updated README.md to include skills-search in skills listing (skill #20)
- Updated README.zh-CN.md badges (skills count: 23, version: 1.16.0)
- Updated README.zh-CN.md to include skills-search with Chinese translation
- Updated CLAUDE.md skills count from 22 to 23
- Added skills-search use case section to README.md
- Added skills-search use case section to README.zh-CN.md
- Added installation command for skills-search
- Enhanced marketplace metadata description to include CCPM skill management

## [1.13.0] - 2025-12-09

### Added
- **New Skill**: claude-code-history-files-finder - Session history recovery for Claude Code
  - Search sessions by keywords with frequency ranking
  - Recover deleted files from Write tool calls with automatic deduplication
  - Analyze session statistics (message counts, tool usage, file operations)
  - Batch operations for processing multiple sessions
  - Streaming processing for large session files (>100MB)
  - Bundled scripts: analyze_sessions.py, recover_content.py
  - Bundled references: session_file_format.md, workflow_examples.md
  - Follows Anthropic skill authoring best practices (third-person description, imperative style, progressive disclosure)

- **New Skill**: docs-cleaner - Documentation consolidation
  - Consolidate redundant documentation while preserving valuable content
  - Redundancy detection for overlapping documents
  - Smart merging with structure preservation
  - Validation for consolidated documents

### Changed
- Updated marketplace skills count from 18 to 20
- Updated marketplace version from 1.11.0 to 1.13.0
- Updated README.md badges (skills count: 20, version: 1.13.0)
- Updated README.md to include claude-code-history-files-finder in skills listing (skill 18)
- Updated README.md to include docs-cleaner in skills listing (skill 19)
- Updated README.zh-CN.md badges (skills count: 20, version: 1.13.0)
- Updated README.zh-CN.md to include both new skills with Chinese translations
- Updated CLAUDE.md skills count from 18 to 20
- Added session history recovery use case section to README.md
- Added documentation maintenance use case section to README.md
- Added corresponding use case sections to README.zh-CN.md
- Added installation commands for both new skills
- Added quick links for documentation references
- **skill-creator** v1.2.0 → v1.2.1: Added cache directory warning
  - Added critical warning about not editing skills in `~/.claude/plugins/cache/`
  - Explains that cache is read-only and changes are lost on refresh
  - Provides correct vs wrong path examples
- **transcript-fixer** v1.0.0 → v1.1.0: Enhanced with Chinese domain support and AI fallback
  - Added Chinese/Japanese/Korean character support for domain names (e.g., `火星加速器`, `具身智能`)
  - Added `[CLAUDE_FALLBACK]` signal when GLM API is unavailable for Claude Code to take over
  - Added Prerequisites section requiring `uv` for Python execution
  - Added Critical Workflow section for dictionary iteration best practices
  - Added AI Fallback Strategy section with manual correction guidance
  - Added Database Operations section with schema reference requirement
  - Added Stages table for quick reference (Dictionary → AI → Full pipeline)
  - Added new bundled script: `ensure_deps.py` for shared virtual environment
  - Added new bundled references: `database_schema.md`, `iteration_workflow.md`
  - Updated domain validation from whitelist to pattern matching
  - Updated tests for Chinese domain names and security bypass attempts

## [youtube-downloader-1.1.0] - 2025-11-19

### Changed
- **youtube-downloader** v1.0.0 → v1.1.0: Enhanced with HLS streaming support
  - Added comprehensive HLS stream download support (m3u8 format)
  - Added support for platforms like Mux, Vimeo, and other HLS-based services
  - Added ffmpeg-based download workflow with authentication headers
  - Added Referer header configuration for protected streams
  - Added protocol whitelisting guidance
  - Added separate audio/video stream handling and merging workflow
  - Added troubleshooting for 403 Forbidden errors
  - Added troubleshooting for yt-dlp stuck on cookie extraction
  - Added troubleshooting for expired signatures
  - Added performance tips (10-15x realtime speed)
  - Updated skill description to include HLS streams and authentication
  - Updated "When to Use" triggers to include m3u8/HLS downloads
  - Updated Overview to mention multiple streaming platforms

## [1.11.0] - 2025-11-16

### Added
- **New Skill**: prompt-optimizer - Transform vague prompts into precise EARS specifications
  - EARS (Easy Approach to Requirements Syntax) transformation methodology
  - 6-step optimization workflow: analyze, transform, identify theories, extract examples, enhance, present
  - 5 EARS sentence patterns (ubiquitous, event-driven, state-driven, conditional, unwanted behavior)
  - Domain theory grounding with 10+ categories (productivity, UX, gamification, learning, e-commerce, security)
  - 40+ industry frameworks mapped to use cases (GTD, BJ Fogg, Gestalt, AIDA, Zero Trust, etc.)
  - Role/Skills/Workflows/Examples/Formats prompt enhancement framework
  - Advanced optimization techniques (multi-stakeholder, non-functional requirements, complex logic)
  - Bundled references: ears_syntax.md, domain_theories.md, examples.md
  - Complete transformation examples (procrastination app, e-commerce, learning platform, password reset)
  - Progressive disclosure pattern (metadata → SKILL.md → bundled resources)

### Changed
- Updated marketplace skills count from 17 to 18
- Updated marketplace version from 1.10.0 to 1.11.0
- Updated README.md badges (skills count, version)
- Updated README.md to include prompt-optimizer in skills listing
- Updated README.zh-CN.md badges (skills count, version)
- Updated README.zh-CN.md to include prompt-optimizer in skills listing
- Updated CLAUDE.md skills count from 17 to 18
- Added prompt-optimizer use case section to README.md
- Added prompt-optimizer use case section to README.zh-CN.md
- Enhanced marketplace metadata description to include prompt optimization capability
- **prompt-optimizer v1.1.0**: Improved skill following Anthropic best practices
  - Reduced SKILL.md from 369 to 195 lines (47% reduction) using progressive disclosure
  - Added new reference: advanced_techniques.md (325 lines) for multi-stakeholder, non-functional, and complex logic patterns
  - Added 4th complete example (password reset security) to examples.md
  - Added attribution to 阿星AI工作室 (A-Xing AI Studio) for EARS methodology inspiration
  - Enhanced reference loading guidance with specific triggers for each file
  - Improved conciseness and clarity following skill authoring best practices

## [1.10.0] - 2025-11-10

### Added
- **New Skill**: qa-expert - Comprehensive QA testing infrastructure with autonomous LLM execution
  - One-command QA project initialization with complete templates and tracking CSVs
  - Google Testing Standards implementation (AAA pattern, 90% coverage targets)
  - Autonomous LLM-driven test execution via master prompts (100x speed improvement)
  - OWASP Top 10 security testing framework (90% coverage target)
  - Bug tracking with P0-P4 severity classification
  - Quality gates enforcement (100% execution, ≥80% pass rate, 0 P0 bugs, ≥80% code coverage)
  - Ground Truth Principle for preventing doc/CSV sync issues
  - Day 1 onboarding guide for new QA engineers (5-hour timeline)
  - Bundled scripts: `init_qa_project.py`, `calculate_metrics.py`
  - Bundled references: master_qa_prompt.md, google_testing_standards.md, day1_onboarding.md, ground_truth_principle.md, llm_prompts_library.md
  - Complete test case and bug tracking templates
  - 30+ ready-to-use LLM prompts for QA tasks
  - Progressive disclosure pattern (metadata → SKILL.md → bundled resources)

### Changed
- Updated marketplace skills count from 16 to 17
- Updated marketplace version from 1.9.0 to 1.10.0
- Updated README.md badges (skills count, version)
- Updated README.md to include qa-expert in skills listing
- Updated CLAUDE.md skills count from 16 to 17
- Added qa-expert use case section to README.md
- Enhanced marketplace metadata description to include QA testing capability

## [1.9.0] - 2025-10-29

### Added
- **New Skill**: video-comparer - Video comparison and quality analysis tool
  - Compare original and compressed videos with interactive HTML reports
  - Calculate quality metrics (PSNR, SSIM) for compression analysis
  - Generate frame-by-frame visual comparisons with three viewing modes (slider, side-by-side, grid)
  - Extract video metadata (codec, resolution, bitrate, duration, file size)
  - Multi-platform FFmpeg installation instructions (macOS, Linux, Windows)
  - Bundled Python script: `compare.py` with security features (path validation, resource limits)
  - Comprehensive reference documentation (video metrics interpretation, FFmpeg commands, configuration)
  - Self-contained HTML output with embedded frames (no server required)

### Changed
- Updated marketplace skills count from 15 to 16
- Updated marketplace version from 1.8.0 to 1.9.0
- Updated README.md badges (skills count, version)
- Updated README.md to include video-comparer in skills listing
- Updated CLAUDE.md skills count from 15 to 16
- Added video-comparer use case section to README.md
- Added FFmpeg to requirements section

## [1.6.0] - 2025-10-26

### Added
- **New Skill**: youtube-downloader - YouTube video and audio downloading with yt-dlp
  - Download YouTube videos and playlists with robust error handling
  - Audio-only download with MP3 conversion
  - Android client workaround for nsig extraction issues (automatic)
  - Format listing and custom format selection
  - Network error handling for proxy/restricted environments
  - Bundled Python script: `download_video.py` with yt-dlp availability check
  - Comprehensive troubleshooting documentation for common yt-dlp issues
  - Demo tape file and GIF showing download workflow

### Changed
- Updated marketplace.json from 12 to 13 skills
- Updated marketplace version from 1.5.0 to 1.6.0
- Enhanced marketplace metadata description to include YouTube downloading capability
- Updated CLAUDE.md with complete 13-skill listing
- Updated CLAUDE.md marketplace version to v1.6.0
- Updated README.md to reflect 13 available skills
- Updated README.md badges (skills count, version)
- Added youtube-downloader to manual installation instructions
- Added youtube-downloader use case section in README
- Added youtube-downloader to documentation quick links
- Added yt-dlp to requirements section

## [1.5.0] - 2025-10-26

### Added
- **New Skill**: ppt-creator - Professional presentation creation with dual-path PPTX generation
  - Pyramid Principle structure (conclusion → reasons → evidence)
  - Assertion-evidence slide framework
  - Automatic data synthesis and chart generation (matplotlib)
  - Dual-path PPTX creation (Marp CLI + document-skills:pptx)
  - Complete orchestration: content → data → charts → PPTX with charts
  - 45-60 second speaker notes per slide
  - Quality scoring with auto-refinement (target: 75/100)

### Changed
- Updated marketplace.json from 11 to 12 skills
- Updated marketplace version from 1.4.0 to 1.5.0

## [1.4.0] - 2025-10-25

### Added
- **New Skill**: cloudflare-troubleshooting - API-driven Cloudflare diagnostics and troubleshooting
  - Systematic investigation of SSL errors, DNS issues, and redirect loops
  - Direct Cloudflare API integration for evidence-based troubleshooting
  - Bundled Python scripts: `check_cloudflare_config.py` and `fix_ssl_mode.py`
  - Comprehensive reference documentation (SSL modes, API overview, common issues)
- **New Skill**: ui-designer - Design system extraction from UI mockups and screenshots
  - Automated design system extraction (colors, typography, spacing)
  - Design system documentation generation
  - PRD and implementation prompt creation
  - Bundled templates: design-system.md, vibe-design-template.md, app-overview-generator.md
- Enhanced `.gitignore` patterns for archives, build artifacts, and documentation files

### Changed
- Updated marketplace.json from 9 to 11 skills
- Updated marketplace version from 1.3.0 to 1.4.0
- Enhanced marketplace metadata description to include new capabilities
- Updated CLAUDE.md with complete 11-skill listing
- Updated README.md to reflect 11 available skills
- Updated README.zh-CN.md to reflect 11 available skills

## [1.3.0] - 2025-10-23

### Added
- **New Skill**: cli-demo-generator - Professional CLI demo generation with VHS automation
  - Automated demo generation from command lists
  - Batch processing with YAML/JSON configs
  - Interactive recording with asciinema
  - Smart timing and multiple output formats
- Comprehensive improvement plan with 5 implementation phases
- Automated installation scripts for macOS/Linux (`install.sh`) and Windows (`install.ps1`)
- Complete Chinese translation (README.zh-CN.md)
- Quick start guides in English and Chinese (QUICKSTART.md, QUICKSTART.zh-CN.md)
- VHS demo infrastructure for all skills
- Demo tape files for skill-creator, github-ops, and markdown-tools
- Automated demo generation script (`demos/generate_all_demos.sh`)
- GitHub issue templates (bug report, feature request)
- GitHub pull request template
- FAQ section in README
- Table of Contents in README
- Enhanced badges (Claude Code version, PRs welcome, maintenance status)
- Chinese user guide with CC-Switch recommendation
- Language switcher badges (English/简体中文)

### Changed
- **BREAKING**: Restructured README.md to highlight skill-creator as essential meta-skill
- Moved skill-creator from position #7 to featured "Essential Skill" section
- Updated CLAUDE.md with new priorities and installation commands
- Enhanced documentation navigation and discoverability
- Improved README structure with better organization

### Removed
- skill-creator from "Other Available Skills" numbered list (now featured separately)

## [1.2.0] - 2025-10-22

### Added
- llm-icon-finder skill for AI/LLM brand icons
- Comprehensive marketplace structure with 8 skills
- Professional documentation for all skills
- CONTRIBUTING.md with quality standards
- INSTALLATION.md with detailed setup instructions

### Changed
- Updated marketplace.json to v1.2.0
- Enhanced skill descriptions and metadata

## [1.1.0] - 2025-10-15

### Added
- skill-creator skill with initialization, validation, and packaging scripts
- repomix-unmixer skill for extracting repomix packages
- teams-channel-post-writer skill for Teams communication
- Enhanced documentation structure

### Changed
- Improved skill quality standards
- Updated all skill SKILL.md files with consistent formatting

## [1.0.0] - 2025-10-08

### Added
- Initial release of Claude Code Skills Marketplace
- github-ops skill for GitHub operations
- markdown-tools skill for document conversion
- mermaid-tools skill for diagram generation
- statusline-generator skill for Claude Code customization
- MIT License
- README.md with comprehensive documentation
- Individual skill documentation (SKILL.md files)

---

## Version Numbering

We use [Semantic Versioning](https://semver.org/):

- **MAJOR** version when you make incompatible API changes
- **MINOR** version when you add functionality in a backward compatible manner
- **PATCH** version when you make backward compatible bug fixes

## Release Process

1. Update version in `.claude-plugin/marketplace.json`
2. Update CHANGELOG.md with changes
3. Update README.md version badge
4. Create git tag: `git tag -a v1.x.x -m "Release v1.x.x"`
5. Push tag: `git push origin v1.x.x`

[Unreleased]: https://github.com/daymade/claude-code-skills/compare/v1.10.0...HEAD
[1.10.0]: https://github.com/daymade/claude-code-skills/compare/v1.9.0...v1.10.0
[1.9.0]: https://github.com/daymade/claude-code-skills/compare/v1.8.0...v1.9.0
[1.8.0]: https://github.com/daymade/claude-code-skills/compare/v1.7.0...v1.8.0
[1.7.0]: https://github.com/daymade/claude-code-skills/compare/v1.6.0...v1.7.0
[1.6.0]: https://github.com/daymade/claude-code-skills/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/daymade/claude-code-skills/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/daymade/claude-code-skills/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/daymade/claude-code-skills/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/daymade/claude-code-skills/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/daymade/claude-code-skills/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/daymade/claude-code-skills/releases/tag/v1.0.0
