# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a Claude Code skills marketplace containing 43 production-ready skills organized in a plugin marketplace structure. Each skill is a self-contained package that extends Claude's capabilities with specialized knowledge, workflows, and bundled resources.

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
skill-creator/scripts/quick_validate.py /path/to/skill

# Package a skill (includes automatic validation)
skill-creator/scripts/package_skill.py /path/to/skill [output-dir]

# Initialize a new skill from template
skill-creator/scripts/init_skill.py <skill-name> --path <output-directory>
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

This repository uses standard git workflow:
```bash
git status
git add .
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
- Use relative paths within skill bundle or standard placeholders (`~/workspace/`, `<user_id>`)

**Three-layer defense system:**
1. **CLAUDE.md rules** (this section) — Claude avoids generating sensitive content
2. **Pre-commit hook** (`.githooks/pre-commit`) — blocks commits with sensitive patterns
3. **gitleaks** (`.gitleaks.toml`) — deep scan with custom rules for this repo

The pre-commit hook is auto-activated via `git config core.hooksPath .githooks`.
If it fires, fix the issue — do NOT use `--no-verify` to bypass.

### Content Organization

- Keep SKILL.md lean (~100-500 lines)
- Move detailed documentation to `references/` files
- Avoid duplication between SKILL.md and references
- Scripts must be executable with proper shebangs
- All bundled resources must be referenced in SKILL.md

## Marketplace Configuration

The marketplace is configured in `.claude-plugin/marketplace.json`:
- Contains 43 plugins, each mapping to one skill
- Each plugin has: name, description, version, category, keywords, skills array
- Marketplace metadata: name, owner, version, homepage

### Versioning Architecture

**Two separate version tracking systems:**

1. **Marketplace Version** (`.claude-plugin/marketplace.json` → `metadata.version`)
   - Tracks the marketplace catalog as a whole
   - Current: v1.39.0
   - Bump when: Adding/removing skills, major marketplace restructuring
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
36. **tunnel-doctor** - Diagnose and fix Tailscale + proxy/VPN conflicts (four layers: route, HTTP env, system proxy, SSH ProxyCommand) on macOS with WSL SSH support
37. **windows-remote-desktop-connection-doctor** - Diagnose AVD/W365 connection quality issues with transport protocol analysis and Windows App log parsing
38. **product-analysis** - Perform structured product audits across UX, API, architecture, and compare mode to produce prioritized optimization recommendations
39. **financial-data-collector** - Collect real financial data for US public companies via yfinance with validation, NaN detection, and NO FALLBACK principle
40. **excel-automation** - Create formatted Excel files, parse complex xlsm models, and control Excel windows on macOS via AppleScript
41. **capture-screen** - Programmatically capture macOS application windows using Swift window ID discovery and screencapture workflows
42. **continue-claude-work** - Recover local `.claude` session context via compact-boundary extraction, subagent workflow recovery, and session end reason detection, then continue interrupted work without `claude --resume`
43. **scrapling-skill** - Install, troubleshoot, and use Scrapling CLI for static/dynamic web extraction, WeChat article capture, and verified output validation

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
| `README.md` | 7 locations: badges, description, install cmd, skill section, use case, docs link, requirements |
| `README.zh-CN.md` | 7 locations: same as above, translated |
| `CLAUDE.md` | 3 locations: overview count, marketplace config count, Available Skills list |
| `skill-name/` | The actual skill directory + packaged .zip |

**Quick workflow**:
```bash
# 1. Validate & package
cd skill-creator && python3 scripts/security_scan.py ../skill-name --verbose
python3 scripts/package_skill.py ../skill-name

# 2. Update all files listed above (see references/new-skill-guide.md for details)

# 3. Validate, commit, push, release
cd .. && python3 -m json.tool .claude-plugin/marketplace.json > /dev/null
git add -A && git commit -m "Release vX.Y.0: Add skill-name"
git push
gh release create vX.Y.0 --title "Release vX.Y.0: Add skill-name" --notes "..."
```

**Top mistakes**: Forgetting to push to GitHub, forgetting README.zh-CN.md, inconsistent version numbers across files.

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
