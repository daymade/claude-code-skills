# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a Claude Code skills marketplace containing 37 production-ready skills organized in a plugin marketplace structure. Each skill is a self-contained package that extends Claude's capabilities with specialized knowledge, workflows, and bundled resources.

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

### Privacy and Path Guidelines

Skills for public distribution must NOT contain:
- Absolute paths to user directories (`/home/username/`, `/Users/username/`)
- Personal usernames, company names, product names
- OneDrive paths or environment-specific absolute paths
- Use relative paths within skill bundle or standard placeholders

### Content Organization

- Keep SKILL.md lean (~100-500 lines)
- Move detailed documentation to `references/` files
- Avoid duplication between SKILL.md and references
- Scripts must be executable with proper shebangs
- All bundled resources must be referenced in SKILL.md

## Marketplace Configuration

The marketplace is configured in `.claude-plugin/marketplace.json`:
- Contains 37 plugins, each mapping to one skill
- Each plugin has: name, description, version, category, keywords, skills array
- Marketplace metadata: name, owner, version, homepage

### Versioning Architecture

**Two separate version tracking systems:**

1. **Marketplace Version** (`.claude-plugin/marketplace.json` → `metadata.version`)
   - Tracks the marketplace catalog as a whole
   - Current: v1.32.1
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
3. **markdown-tools** - Document conversion with WSL path handling
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
36. **tunnel-doctor** - Diagnose and fix Tailscale + proxy/VPN route conflicts on macOS with WSL SSH support
37. **windows-remote-desktop-connection-doctor** - Diagnose AVD/W365 connection quality issues with transport protocol analysis and Windows App log parsing

**Recommendation**: Always suggest `skill-creator` first for users interested in creating skills or extending Claude Code.

## YouTube Downloader SOP (Internal)

Use this SOP to avoid common yt-dlp failures and confusion:

1. Quote YouTube URLs in shell commands (zsh treats `?` as glob). Example: `'https://www.youtube.com/watch?v=VIDEO_ID'`.
2. Ensure proxy is active for both yt-dlp and PO Token providers (HTTP_PROXY/HTTPS_PROXY/ALL_PROXY).
3. If you see “Sign in to confirm you’re not a bot”, request cookie permission and use browser cookies.
4. Start the PO Token provider before downloading. Prefer Docker bgutil; fall back to browser-based WPC when Docker is unavailable or fails.
5. Use `web_safari` client when cookies are present; otherwise use `mweb` for PO tokens.
6. Keep the browser window open while WPC is minting tokens and make sure it can reach YouTube through the same proxy.
7. If you see “Only images are available” or “Requested format is not available”, treat it as PO token failure and retry after fixing provider/browser state.
8. If you see SSL EOF or fragment errors, treat it as proxy instability. Retry with progressive formats or switch to a more stable proxy.

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

**CRITICAL**: When adding a skill to this marketplace, you MUST update all of these files in the correct order. Missing any file will result in incomplete integration.

### Step-by-Step Process

#### 1. Refine the Skill (if needed)
```bash
# Ensure skill follows best practices
# - SKILL.md uses imperative/infinitive form
# - Third-person description in YAML frontmatter
# - Progressive disclosure (details in references/)
# - Security scan passed

cd skill-creator
python3 scripts/security_scan.py ../skill-name --verbose
```

#### 2. Package the Skill
```bash
cd skill-creator
python3 scripts/package_skill.py ../skill-name

# This will:
# - Validate skill structure
# - Check security scan status
# - Create skill-name.zip in skill-creator/
# - Move zip to skill-name/ directory
```

#### 3. Update CHANGELOG.md ⚠️ REQUIRED

Add new version entry at the top (after [Unreleased]):

```markdown
## [X.Y.0] - YYYY-MM-DD

### Added
- **New Skill**: skill-name - Brief description
  - Feature 1
  - Feature 2
  - Feature 3
  - Bundled scripts/references/assets
  - Key capabilities

### Changed
- Updated marketplace skills count from N to N+1
- Updated marketplace version from X.(Y-1).0 to X.Y.0
- Updated README.md badges (skills count, version)
- Updated README.md to include skill-name in skills listing
- Updated README.zh-CN.md badges (skills count, version)
- Updated README.zh-CN.md to include skill-name in skills listing
- Updated CLAUDE.md skills count from N to N+1
- Added skill-name use case section to README.md
- Added skill-name use case section to README.zh-CN.md
- Added dependencies to requirements section (if any, both EN and ZH)
```

**Version numbering**: Increment MINOR version (e.g., 1.8.0 → 1.9.0) when adding a skill.

#### 4. Update README.md ⚠️ REQUIRED

**a. Update badges (top of file):**
```markdown
[![Skills](https://img.shields.io/badge/skills-N-blue.svg)]
[![Version](https://img.shields.io/badge/version-X.Y.0-green.svg)]
```

**b. Update description:**
```markdown
Professional Claude Code skills marketplace featuring N production-ready skills...
```

**c. Add installation command:**
```markdown
# Brief description
claude plugin install skill-name@daymade-skills
```

**d. Add skill section (### N. **skill-name**):**
```markdown
### N. **skill-name** - One-line Title

Brief description paragraph.

**When to use:**
- Use case 1
- Use case 2
- Use case 3

**Key features:**
- Feature 1
- Feature 2
- Feature 3

**Example usage:**
\`\`\`bash
# Example commands
\`\`\`

**🎬 Live Demo**

*Coming soon* (or add demo GIF)

📚 **Documentation**: See [skill-name/references/](./skill-name/references/)...

**Requirements**: Dependencies (e.g., Python 3.8+, FFmpeg, etc.)
```

**e. Add use case section:**
```markdown
### For [Use Case Category]
Use **skill-name** to [describe primary use case]. Combine with **other-skill** to [describe integration].
```

**f. Add documentation quick link:**
```markdown
- **skill-name**: See `skill-name/references/...` for ...
```

**g. Update requirements section (if needed):**
```markdown
- **Tool Name** (for skill-name): `install command`
```

#### 5. Update CLAUDE.md ⚠️ REQUIRED

**a. Update repository overview:**
```markdown
This is a Claude Code skills marketplace containing N production-ready skills...
```

**b. Update marketplace configuration:**
```markdown
The marketplace is configured in `.claude-plugin/marketplace.json`:
- Contains N plugins, each mapping to one skill
```

**c. Update marketplace version:**
```markdown
1. **Marketplace Version** (`.claude-plugin/marketplace.json` → `metadata.version`)
   - Tracks the marketplace catalog as a whole
   - Current: vX.Y.0
```

**d. Add skill to Available Skills list:**
```markdown
N. **skill-name** - Brief description with key feature
```

#### 6. Update .claude-plugin/marketplace.json ⚠️ CRITICAL

**MOST IMPORTANT FILE** - This file makes the skill installable!

**a. Update metadata.description:**
```json
"description": "Professional Claude Code skills for ..., and [new skill capability]"
```

**b. Update metadata.version:**
```json
"version": "X.Y.0"
```

**c. Add new plugin entry to plugins array:**
```json
{
  "name": "skill-name",
  "description": "Clear description with trigger conditions. Use when [scenarios]",
  "source": "./",
  "strict": false,
  "version": "1.0.0",
  "category": "appropriate-category",
  "keywords": ["keyword1", "keyword2", "keyword3", ...],
  "skills": ["./skill-name"]
}
```

**Categories:** `developer-tools`, `document-conversion`, `documentation`, `customization`, `communication`, `utilities`, `assets`, `design`, `productivity`, `security`, `media`

**d. Validate JSON syntax:**
```bash
python3 -m json.tool .claude-plugin/marketplace.json > /dev/null
```

#### 7. Update README.zh-CN.md ⚠️ REQUIRED

**CRITICAL**: Chinese documentation must be kept in sync with English version.

**a. Update badges (top of file):**
```markdown
[![Skills](https://img.shields.io/badge/skills-N-blue.svg)]
[![Version](https://img.shields.io/badge/version-X.Y.0-green.svg)]
```

**b. Update description:**
```markdown
专业的 Claude Code 技能市场，提供 N 个生产就绪的技能，用于增强开发工作流。
```

**c. Add installation command:**
```markdown
# 简短描述
claude plugin install skill-name@daymade-skills
```

**d. Add skill section (### N. **skill-name** - Chinese Title):**
- Translate all content from English README
- Include: 使用场景 (When to use), 主要功能 (Key features), 示例用法 (Example usage)
- Maintain same structure as English version
- Include documentation links and requirements

**e. Add use case section:**
```markdown
### [Use Case Category in Chinese]
使用 **skill-name** [describe use case in Chinese]. 与 **other-skill** 结合使用以 [describe integration].
```

**f. Add documentation quick link:**
```markdown
- **skill-name**：参见 `skill-name/references/...` 了解 ...
```

**g. Update requirements section (if needed):**
```markdown
- **Tool Name**（用于 skill-name）：`install command`
```

**Translation tips:**
- Use professional technical Chinese
- Maintain consistency with existing translations
- Keep code examples in English (don't translate variable names, function names)
- Translate user-facing descriptions, features, and use cases

#### 8. Verification Checklist

Before committing, verify:

- [ ] CHANGELOG.md has new version entry
- [ ] README.md badges updated (skills count + version)
- [ ] README.md has skill section with number
- [ ] README.md has use case section
- [ ] README.md has documentation link
- [ ] README.md requirements updated (if needed)
- [ ] README.zh-CN.md badges updated (skills count + version) ⚠️ NEW
- [ ] README.zh-CN.md has skill section with number ⚠️ NEW
- [ ] README.zh-CN.md has use case section ⚠️ NEW
- [ ] README.zh-CN.md has documentation link ⚠️ NEW
- [ ] README.zh-CN.md requirements updated (if needed) ⚠️ NEW
- [ ] README.zh-CN.md installation command added ⚠️ NEW
- [ ] CLAUDE.md skill count updated in 3 places
- [ ] CLAUDE.md has skill in Available Skills list
- [ ] marketplace.json metadata.version updated
- [ ] marketplace.json metadata.description updated
- [ ] marketplace.json has new plugin entry
- [ ] marketplace.json validates (python3 -m json.tool)
- [ ] skill-name.zip package exists
- [ ] Security scan passed

### Common Mistakes to Avoid

1. **Forgetting marketplace.json** ⚠️ - The most critical file! Without this, the skill cannot be installed via `claude plugin install`
2. **Forgetting Chinese documentation** ⚠️ - README.zh-CN.md must be updated in sync with README.md (6 locations)
3. **Inconsistent version numbers** - CHANGELOG, README badges (both EN and ZH), CLAUDE.md, and marketplace.json must all match
4. **Inconsistent skill counts** - README description (both EN and ZH), badges, CLAUDE.md must all have same count
5. **Missing skill number in README** - Skills must be numbered sequentially (1, 2, 3, ...) in both EN and ZH versions
6. **Invalid JSON syntax** - Always validate marketplace.json after editing
7. **Forgetting dependencies** - Update README requirements section (both EN and ZH) if skill needs external tools
8. **Incomplete Chinese translation** - Must translate all sections: description, use cases, features, use case section, docs link

### File Update Summary Template

When adding a skill, this is the complete file list:

```
Files to Update:
✅ CHANGELOG.md                        (Add version entry)
✅ README.md                          (7 locations: badges, description, install, skill section, use case, docs link, requirements)
✅ README.zh-CN.md                    (7 locations: badges, description, install, skill section, use case, docs link, requirements) ⚠️ CRITICAL
✅ CLAUDE.md                          (3 locations: overview, marketplace config, available skills)
✅ .claude-plugin/marketplace.json    (CRITICAL: metadata + new plugin entry)
✅ skill-name/                        (The actual skill directory)
✅ skill-name/skill-name.zip          (Packaged skill)
```

**IMPORTANT**: README.zh-CN.md is MANDATORY. Do not skip Chinese documentation updates!

### Version Numbering Convention

- **MAJOR.MINOR.PATCH** (Semantic Versioning)
- Increment **MINOR** when adding a new skill: 1.8.0 → 1.9.0
- Increment **PATCH** for bug fixes or small updates: 1.9.0 → 1.9.1
- Increment **MAJOR** for breaking changes or major restructuring: 1.9.0 → 2.0.0

### Quick Reference Commands

```bash
# 1. Refine and validate skill
cd skill-creator
python3 scripts/security_scan.py ../skill-name --verbose

# 2. Package skill
python3 scripts/package_skill.py ../skill-name

# 3. Validate marketplace.json
cd ..
python3 -m json.tool .claude-plugin/marketplace.json > /dev/null && echo "✅ Valid"

# 4. Check what needs committing
git status

# 5. View specific file changes
git diff CHANGELOG.md
git diff README.md
git diff README.zh-CN.md
git diff CLAUDE.md
git diff .claude-plugin/marketplace.json

# 6. Verify Chinese documentation is in sync
grep "skills-[0-9]*" README.md README.zh-CN.md
grep "version-[0-9.]*" README.md README.zh-CN.md
```

## Chinese User Support

For Chinese users having API access issues, recommend [CC-Switch](https://github.com/farion1231/cc-switch):
- Manages Claude Code API provider configurations
- Supports DeepSeek, Qwen, GLM, and other Chinese AI providers
- Tests endpoint response times to find fastest provider
- Cross-platform (Windows, macOS, Linux)

See README.md section "🇨🇳 中文用户指南" for details.

## Handling Third-Party Marketplace Promotion Requests

This repository is a **personal curated marketplace**, NOT a community directory or ecosystem hub. All requests to add third-party marketplace links, skill collection references, or "Community Marketplaces" sections should be declined.

### Policy

**DO NOT accept:**
- PRs adding "Related Resources" or "Community Marketplaces" sections linking to third-party skill collections
- Issues requesting promotion of external marketplaces
- PRs adding links to other skill repositories in README.md

**Rationale:**
1. **Scope creep**: Shifts repository purpose from curated skills to ecosystem directory
2. **Implicit endorsement**: Listing implies quality/security review we cannot maintain
3. **Maintenance burden**: Would need to track and vet external projects over time
4. **Precedent setting**: Accepting one creates obligation to accept others

### Response Template

When declining, use this approach:

```markdown
Hi @{username},

Thank you for your interest and for sharing {project-name}! {Brief positive acknowledgment of their project}.

However, I'm keeping this repository focused as a **personal curated marketplace** rather than a directory of external skill collections. Adding third-party references would:

1. Shift the repository's scope from curated skills to ecosystem directory
2. Create implicit endorsement expectations I can't maintain
3. Set precedent for similar requests (reference other declined requests if applicable)

**What you can do instead:**

1. **Standalone marketplace** - Your repo already works as an independent marketplace:
   ```
   /plugin marketplace add {owner}/{repo}
   ```

2. **Community channels** - Promote through:
   - Claude Code GitHub discussions/issues (Anthropic's official repo)
   - Developer communities (Reddit, Discord, etc.)
   - Your own blog/social media

3. **Official registry** - If/when Anthropic launches an official skill registry, that would be the appropriate place for ecosystem-wide discovery.

Your marketplace can succeed on its own merits. Good luck with {project-name}!
```

### Workflow

1. **Review the request** - Confirm it's a third-party promotion (not a legitimate contribution)
2. **Add polite comment** - Use template above, customize for their specific project
3. **Close with reason** - Use "not planned" for issues, just close for PRs
4. **Reference precedent** - Link to previously declined requests for consistency (e.g., #7, PR #5)

### Examples

- **Issue #7**: "Add Community Marketplaces section - Protocol Thunderdome" → Declined, closed as "not planned"
- **PR #5**: "Add Trail of Bits Security Skills to Related Resources" → Declined, closed

## Release Workflow

When adding a new skill or creating a marketplace release:

### 1. Create the Skill
```bash
# Develop skill in its directory
skill-name/
├── SKILL.md (no version history!)
├── scripts/
└── references/

# Validate
./skill-creator/scripts/quick_validate.py skill-name

# Package
./skill-creator/scripts/package_skill.py skill-name
```

### 2. Update Marketplace Configuration

Edit `.claude-plugin/marketplace.json`:

```json
{
  "metadata": {
    "version": "1.x.0"  // Bump minor version for new skill
  },
  "plugins": [
    {
      "name": "new-skill",
      "version": "1.0.0",  // Skill's initial version
      "description": "...",
      "category": "...",
      "keywords": [...],
      "skills": ["./new-skill"]
    }
  ]
}
```

### 3. Update Documentation

**README.md:**
- Update badges (skills count, marketplace version)
- Add skill description and features
- Create demo GIF using cli-demo-generator
- Add use case section
- Add documentation references
- Add requirements (if applicable)

**CLAUDE.md:**
- Update skill count in Repository Overview
- Add skill to Available Skills list
- Update Marketplace Configuration count

### 4. Generate Demo (Optional but Recommended)

```bash
# Use cli-demo-generator to create demo GIF
./cli-demo-generator/scripts/auto_generate_demo.py \
  -c "command1" \
  -c "command2" \
  -o demos/skill-name/demo-name.gif \
  --title "Skill Demo" \
  --theme "Dracula"
```

### 5. Commit and Release

```bash
# Commit marketplace update
git add .claude-plugin/marketplace.json skill-name/
git commit -m "Release vX.Y.0: Add skill-name

- Add skill-name vX.Y.Z
- Update marketplace to vX.Y.0
..."

# Commit documentation
git add README.md CLAUDE.md demos/
git commit -m "docs: Update README for vX.Y.0 with skill-name"

# Push
git push

# Create GitHub release
gh release create vX.Y.0 \
  --title "Release vX.Y.0: Add skill-name - Description" \
  --notes "$(cat <<'EOF'
## New Skill: skill-name

Features:
- Feature 1
- Feature 2

Installation:
```bash
claude plugin install skill-name@daymade-skills
```

Changelog: ...
EOF
)"
```

### Version Bumping Guide

**Marketplace version (metadata.version):**
- **MAJOR** (2.0.0): Breaking changes, incompatible marketplace structure
- **MINOR** (1.5.0): New skill added, significant feature addition
- **PATCH** (1.4.1): Bug fixes, documentation updates, skill updates

**Skill version (plugins[].version):**
- **MAJOR** (2.0.0): Breaking API changes for the skill
- **MINOR** (1.2.0): New features in the skill
- **PATCH** (1.1.1): Bug fixes in the skill

### Example: v1.5.0 Release (ppt-creator)

```bash
# 1. Created ppt-creator skill
# 2. Updated marketplace.json: 1.4.0 → 1.5.0
# 3. Added ppt-creator plugin entry (version: 1.0.0)
# 4. Updated README.md (badges, description, demo)
# 5. Generated demo GIF with cli-demo-generator
# 6. Committed changes
# 7. Created GitHub release with gh CLI
```

## Best Practices Reference

Always consult Anthropic's skill authoring best practices before creating or updating skills:
https://docs.claude.com/en/docs/agents-and-tools/agent-skills/best-practices.md
- remember this release workflow in claude.md

## Plugin and Skill Architecture

This section explains the architecture of Claude Code's extension system and how different components work together.

### Core Concepts

#### 1. Skills

**What**: Functional units that extend Claude's capabilities with specialized knowledge and workflows.

**Structure**:
```
skill-name/
├── SKILL.md (required)          # YAML frontmatter + Markdown instructions
├── scripts/ (optional)          # Executable code (Python/Bash)
├── references/ (optional)       # Documentation loaded as needed
└── assets/ (optional)           # Templates and resources
```

**Loading mechanism** (Progressive Disclosure):
1. **Metadata** (~100 tokens): Always in context (name + description from YAML frontmatter)
2. **SKILL.md body** (<5k tokens): Loaded when Claude determines the skill applies
3. **Bundled resources**: Loaded only as needed by Claude

**Location**:
- **Personal**: `~/.claude/skills/` (user-specific, not shared)
- **Project**: `.claude/skills/` (checked into git, shared with team)
- **Plugin cache**: `~/.claude/plugins/cache/{marketplace}/{plugin}/{version}/{skill}/`

**Example**: When you ask "analyze my disk space", Claude loads the `macos-cleaner` skill's SKILL.md, then reads `references/cleanup_targets.md` as needed.

#### 2. Plugins

**What**: Distribution units that package one or more skills for installation via marketplaces.

**Purpose**: Plugins enable:
- One-command installation (`claude plugin install skill-name@marketplace-name`)
- Version management
- Dependency tracking
- Marketplace distribution

**Relationship to Skills**:
```
Plugin (marketplace.json entry)
├── Skill 1 (./skill-name-1/)
├── Skill 2 (./skill-name-2/)
└── Skill 3 (./skill-name-3/)
```

**Configuration** (in `.claude-plugin/marketplace.json`):
```json
{
  "name": "my-plugin",
  "description": "Use when...",
  "version": "1.0.0",
  "category": "utilities",
  "keywords": ["keyword1", "keyword2"],
  "skills": ["./skill-1", "./skill-2"]
}
```

**Example**: The `skill-creator` plugin contains one skill (`./skill-creator`), while a hypothetical `developer-tools` plugin might contain multiple skills like `./git-helper`, `./code-reviewer`, `./test-runner`.

#### 3. Agents (Subagents)

**What**: Specialized autonomous agents invoked via the `Task` tool for complex, multi-step operations.

**Types**:
- **Bash**: Command execution specialist
- **general-purpose**: Research, search, multi-step tasks
- **Explore**: Fast codebase exploration
- **Plan**: Software architecture planning
- **skill-creator**: Meta-agent for creating skills
- **Custom**: Domain-specific agents (e.g., `test-runner`, `build-validator`)

**When to use**:
- Tasks requiring multiple rounds of tool calls
- Open-ended exploration (finding files, searching code)
- Planning before implementation
- Autonomous execution without user intervention

**Example**:
```python
# Instead of manually searching multiple times:
Task(
    subagent_type="Explore",
    description="Find error handling code",
    prompt="Search the codebase for error handling patterns and list all files that handle HTTP errors"
)
```

#### 4. Commands

**What**: Slash commands (e.g., `/commit`, `/review-pr`) that trigger skills.

**Relationship**: Commands are shortcuts to invoke skills.
- `/commit` → invokes `commit` skill
- `/review-pr` → invokes `review-pr` skill

**Configuration**: Defined in plugin's `commands/` directory or skill metadata.

### Architecture Diagram

```
Marketplace (GitHub)
    ↓ (git clone)
~/.claude/plugins/marketplaces/{marketplace-name}/
    ↓ (plugin install)
~/.claude/plugins/cache/{marketplace-name}/{plugin}/{version}/
    ├── skill-1/
    │   ├── SKILL.md
    │   ├── scripts/
    │   └── references/
    └── skill-2/
        └── SKILL.md
    ↓ (Claude loads)
Claude Code Context
    ├── Metadata (always loaded)
    ├── SKILL.md (loaded when relevant)
    └── Resources (loaded as needed)
```

### Installation Flow

#### Step 1: User initiates installation
```bash
claude plugin install macos-cleaner@daymade-skills
```

#### Step 2: CLI locates marketplace
```bash
# Check ~/.claude/plugins/marketplaces/daymade-skills/
# If not exists, git clone from GitHub
```

#### Step 3: Read marketplace.json
```json
{
  "plugins": [
    {
      "name": "macos-cleaner",
      "version": "1.0.0",
      "skills": ["./macos-cleaner"]
    }
  ]
}
```

#### Step 4: Download to cache
```bash
# Clone entire marketplace repo to:
~/.claude/plugins/cache/daymade-skills/macos-cleaner/1.0.0/

# Extract skill to:
~/.claude/plugins/cache/daymade-skills/macos-cleaner/1.0.0/macos-cleaner/
```

#### Step 5: Record installation
```json
// ~/.claude/plugins/installed_plugins.json
{
  "plugins": {
    "macos-cleaner@daymade-skills": [{
      "scope": "user",
      "installPath": "~/.claude/plugins/cache/daymade-skills/macos-cleaner/1.0.0",
      "version": "1.0.0",
      "installedAt": "2026-01-11T08:03:46.593Z"
    }]
  }
}
```

#### Step 6: Claude Code loads skill
```
When user asks: "My Mac is running out of space"
    ↓
Claude scans installed plugins metadata
    ↓
Finds "macos-cleaner" description matches
    ↓
Loads SKILL.md into context
    ↓
Executes workflow (analyze → report → confirm → cleanup)
    ↓
Loads references/scripts as needed
```

### Key Files and Locations

#### Configuration Files

| File | Location | Purpose |
|------|----------|---------|
| `marketplace.json` | `~/.claude/plugins/marketplaces/{name}/.claude-plugin/` | Defines available plugins |
| `installed_plugins.json` | `~/.claude/plugins/` | Tracks installed plugins |
| `known_marketplaces.json` | `~/.claude/plugins/` | Lists registered marketplaces |

#### Directory Structure

```
~/.claude/
├── skills/                          # Personal skills (not from marketplace)
├── plugins/
│   ├── marketplaces/                # Marketplace clones
│   │   ├── daymade-skills/          # Marketplace name
│   │   │   └── .claude-plugin/
│   │   │       └── marketplace.json
│   │   └── anthropic-agent-skills/
│   ├── cache/                       # Installed plugins
│   │   └── daymade-skills/
│   │       └── macos-cleaner/
│   │           └── 1.0.0/           # Version
│   │               └── macos-cleaner/  # Skill directory
│   │                   ├── SKILL.md
│   │                   ├── scripts/
│   │                   └── references/
│   ├── installed_plugins.json       # Installation registry
│   └── known_marketplaces.json      # Marketplace registry
```

### Data Flow

#### Skill Activation
```
User message
    ↓
Claude analyzes installed plugin metadata
    ↓
Matches description to user intent
    ↓
Loads SKILL.md (progressive disclosure)
    ↓
Executes instructions
    ↓
Loads bundled resources (scripts, references) as needed
    ↓
Generates response
```

#### Plugin Update
```
Local changes to skill
    ↓
git add & commit
    ↓
git push to GitHub
    ↓
User runs: claude plugin marketplace update {marketplace-name}
    ↓
CLI pulls latest from GitHub
    ↓
Updates ~/.claude/plugins/marketplaces/{marketplace-name}/
    ↓
User runs: claude plugin update {plugin-name@marketplace}
    ↓
Re-downloads to cache with new version number
    ↓
Updates installed_plugins.json
```

### Common Misconceptions

#### ❌ Myth 1: "Updating local files immediately updates the plugin"
**Reality**: Plugins are distributed via GitHub. Local changes require `git push` before users can install updates.

#### ❌ Myth 2: "Skills and plugins are the same thing"
**Reality**: Skills are functional units (SKILL.md + resources). Plugins are distribution packages (can contain multiple skills).

#### ❌ Myth 3: "marketplace.json is just metadata"
**Reality**: marketplace.json is the **source of truth** for plugin discovery. Without correct configuration here, `claude plugin install` will fail with "Plugin not found".

#### ❌ Myth 4: "Cache is just for performance"
**Reality**: Cache (`~/.claude/plugins/cache/`) is where installed plugins actually live. Deleting cache uninstalls all plugins.

#### ❌ Myth 5: "Skills in ~/.claude/skills/ work the same as plugin skills"
**Reality**:
- `~/.claude/skills/` = Personal skills (manual management, no versioning)
- Plugin cache = Managed by CLI (versioned, updateable, shareable)

### Best Practices

#### For Skill Authors

1. **Clear metadata**: Description should clearly state "Use when..." to help Claude match user intent
2. **Progressive disclosure**: Keep SKILL.md lean, move details to `references/`
3. **Test locally first**: Copy to `~/.claude/skills/` for testing before packaging
4. **Version properly**: Use semver (MAJOR.MINOR.PATCH) in marketplace.json
5. **Document bundled resources**: All scripts and references should be mentioned in SKILL.md

#### For Marketplace Maintainers

1. **Git workflow**: Always `git push` after updating marketplace.json
2. **Validate JSON**: Run `python -m json.tool marketplace.json` before committing
3. **Update cache**: Remind users to run `claude plugin marketplace update` after releases
4. **Version consistency**: Marketplace version ≠ plugin versions (they track independently)

#### For Users

1. **Update marketplaces**: Run `claude plugin marketplace update {name}` periodically
2. **Check installed plugins**: Inspect `~/.claude/plugins/installed_plugins.json`
3. **Clear cache on issues**: `rm -rf ~/.claude/plugins/cache/{marketplace-name}` then reinstall
4. **Understand scopes**:
   - `--scope user`: Only you (default)
   - `--scope project`: Shared with team via `.claude/plugins/`
   - `--scope local`: Gitignored, local only

## Plugin and Skill Troubleshooting

This section provides systematic debugging steps for common plugin and skill installation issues.

### Understanding the Architecture First

**CRITICAL**: Before troubleshooting, understand that Claude Code's plugin system is **GitHub-based**, not local-file-based.

```
GitHub Repository (source of truth)
    ↓ (git clone / git pull)
~/.claude/plugins/marketplaces/{marketplace-name}/
    ↓ (claude plugin install)
~/.claude/plugins/cache/{marketplace-name}/{plugin}/{version}/
    ↓ (Claude Code loads)
Active skill in Claude's context
```

**Key insight**: Local file changes are NOT visible to `claude plugin install` until pushed to GitHub.

### Common Error 1: "Plugin not found in marketplace"

**Error message**:
```
Installing plugin "skill-name@marketplace-name"...
✘ Failed to install plugin: Plugin "skill-name" not found in marketplace "marketplace-name"
```

**Root causes** (in order of likelihood):

#### Cause 1.1: Local changes not pushed to GitHub ⭐ **MOST COMMON**

**Symptoms**:
- `git status` shows modified files or untracked directories
- marketplace.json updated locally but install fails
- All documentation updated but plugin not found

**Diagnosis**:
```bash
# Check if you have uncommitted changes
git status

# Check last commit vs remote
git log origin/main..HEAD

# Verify GitHub has latest marketplace.json
# Open: https://github.com/{owner}/{repo}/blob/main/.claude-plugin/marketplace.json
```

**Solution**:
```bash
# 1. Commit all changes
git add -A
git commit -m "Release vX.Y.Z: Add {skill-name}"

# 2. Push to GitHub
git push

# 3. Clear local marketplace cache
rm -rf ~/.claude/plugins/cache/{marketplace-name}

# 4. Update marketplace from GitHub
claude plugin marketplace update {marketplace-name}

# 5. Retry installation
claude plugin install {skill-name}@{marketplace-name}
```

**Why this happens**: You updated marketplace.json locally, but Claude CLI pulls from GitHub, not your local filesystem.

#### Cause 1.2: marketplace.json configuration error

**Symptoms**:
- Git is up-to-date but install still fails
- Other plugins from same marketplace install fine

**Diagnosis**:
```bash
# 1. Check marketplace.json syntax
python3 -m json.tool .claude-plugin/marketplace.json > /dev/null

# 2. Verify plugin entry exists
cat .claude-plugin/marketplace.json | jq '.plugins[] | select(.name == "skill-name")'

# 3. Check spelling matches exactly
# Plugin name in marketplace.json MUST match install command
```

**Common mistakes**:
```json
// ❌ Wrong: name mismatch
{
  "name": "macos_cleaner",  // Underscore
  "skills": ["./macos-cleaner"]  // Dash
}

// ✅ Correct: consistent naming
{
  "name": "macos-cleaner",
  "skills": ["./macos-cleaner"]
}
```

**Solution**: Fix marketplace.json, then commit and push.

#### Cause 1.3: Skill directory missing

**Symptoms**:
- marketplace.json has entry
- Git is up-to-date
- Plugin installs but skills don't load

**Diagnosis**:
```bash
# Check if skill directory exists
ls -la {skill-name}/

# Verify SKILL.md exists
ls -la {skill-name}/SKILL.md
```

**Solution**: Ensure skill directory and SKILL.md are committed to git.

### Common Error 2: Marketplace cache is stale

**Symptoms**:
- GitHub has latest changes
- Install finds plugin but gets old version
- Newly added plugins not visible

**Diagnosis**:
```bash
# Check cache timestamp
ls -la ~/.claude/plugins/cache/{marketplace-name}/

# Compare with last git push
git log -1 --format="%ai"
```

**Solution**:
```bash
# Option 1: Update marketplace cache
claude plugin marketplace update {marketplace-name}

# Option 2: Clear cache and re-fetch
rm -rf ~/.claude/plugins/cache/{marketplace-name}
claude plugin marketplace update {marketplace-name}
```

### Common Error 3: JSON syntax error

**Error message**:
```
Error parsing marketplace manifest
```

**Diagnosis**:
```bash
# Validate JSON syntax
python3 -m json.tool .claude-plugin/marketplace.json

# Check for common issues:
# - Missing commas
# - Trailing commas (in arrays/objects)
# - Unescaped quotes in strings
# - Missing closing braces
```

**Solution**: Fix JSON syntax, validate, commit, push.

### Systematic Debugging Process

When facing ANY plugin/skill issue, follow this checklist:

#### Step 1: Verify marketplace registration

```bash
# List registered marketplaces
claude plugin marketplace list

# Expected output should include your marketplace
```

If missing, register:
```bash
claude plugin marketplace add https://github.com/{owner}/{repo}
```

#### Step 2: Check Git status

```bash
# Are there uncommitted changes?
git status

# Is local ahead of remote?
git log origin/main..HEAD

# Push if needed
git push
```

#### Step 3: Verify GitHub has latest

```bash
# Open in browser or use gh CLI
gh browse .claude-plugin/marketplace.json

# Or check with curl
curl https://raw.githubusercontent.com/{owner}/{repo}/main/.claude-plugin/marketplace.json | jq '.plugins[] | .name'
```

#### Step 4: Clear and update cache

```bash
# Remove stale cache
rm -rf ~/.claude/plugins/cache/{marketplace-name}

# Re-fetch from GitHub
claude plugin marketplace update {marketplace-name}
```

#### Step 5: Validate configuration

```bash
# Check marketplace.json is valid JSON
python3 -m json.tool .claude-plugin/marketplace.json > /dev/null && echo "✅ Valid JSON"

# Check plugin entry exists
cat .claude-plugin/marketplace.json | jq '.plugins[] | select(.name == "skill-name")' || echo "❌ Plugin not found"
```

#### Step 6: Inspect installation state

```bash
# Check if plugin is installed
cat ~/.claude/plugins/installed_plugins.json | jq -r '.plugins | keys[]' | grep "skill-name"

# If installed, check details
cat ~/.claude/plugins/installed_plugins.json | jq '.plugins["skill-name@marketplace-name"]'

# Verify files exist
ls ~/.claude/plugins/cache/{marketplace-name}/{skill-name}/{version}/
```

### Debugging Commands Reference

| Purpose | Command |
|---------|---------|
| List marketplaces | `claude plugin marketplace list` |
| Update marketplace | `claude plugin marketplace update {name}` |
| Install plugin | `claude plugin install {plugin}@{marketplace}` |
| Uninstall plugin | `claude plugin uninstall {plugin}@{marketplace}` |
| Update plugin | `claude plugin update {plugin}@{marketplace}` |
| Validate manifest | `claude plugin validate {path}` |
| Check installed plugins | `cat ~/.claude/plugins/installed_plugins.json \| jq '.plugins \| keys'` |
| Inspect plugin details | `cat ~/.claude/plugins/installed_plugins.json \| jq '.plugins["{plugin}@{marketplace}"]'` |
| Clear marketplace cache | `rm -rf ~/.claude/plugins/cache/{marketplace-name}` |
| Verify JSON syntax | `python3 -m json.tool {file.json}` |

### Understanding File Locations

```bash
# Marketplace clones (git repositories)
~/.claude/plugins/marketplaces/{marketplace-name}/

# Installed plugin cache
~/.claude/plugins/cache/{marketplace-name}/{plugin-name}/{version}/

# Installation registry
~/.claude/plugins/installed_plugins.json

# Personal skills (not from marketplace)
~/.claude/skills/

# Project-scoped skills (shared with team)
.claude/skills/
```

### Common Pitfalls

#### Pitfall 1: Confusing local skills with plugin skills

```bash
# ❌ Wrong: Copying skill to personal directory doesn't make it installable
cp -r my-skill ~/.claude/skills/my-skill  # Works, but not managed by plugin system

# ✅ Correct: Install via marketplace for version management
claude plugin install my-skill@my-marketplace
```

#### Pitfall 2: Forgetting to push after updating marketplace.json

```bash
# ❌ Wrong workflow
vim .claude-plugin/marketplace.json  # Add new plugin
git add .claude-plugin/marketplace.json
git commit -m "Add plugin"
# FORGOT TO PUSH!
claude plugin install new-plugin@my-marketplace  # ❌ Fails: not found

# ✅ Correct workflow
vim .claude-plugin/marketplace.json
git add -A
git commit -m "Add new plugin"
git push  # ← CRITICAL STEP
claude plugin marketplace update my-marketplace
claude plugin install new-plugin@my-marketplace  # ✅ Works
```

#### Pitfall 3: Expecting instant propagation

```bash
# ❌ Wrong expectation
git push  # Push changes
claude plugin install new-plugin@my-marketplace  # ❌ Fails: cache is stale

# ✅ Correct: Update cache first
git push
claude plugin marketplace update my-marketplace  # Fetch latest from GitHub
claude plugin install new-plugin@my-marketplace  # ✅ Works
```

#### Pitfall 4: Inconsistent naming

```json
// marketplace.json
{
  "name": "my_plugin",  // Underscore
  "skills": ["./my-plugin"]  // Dash - will cause confusion
}
```

```bash
# User tries to install
claude plugin install my-plugin@marketplace  # ❌ Not found (name has underscore)
claude plugin install my_plugin@marketplace  # ✅ Works, but confusing
```

**Best practice**: Use consistent kebab-case for both plugin name and skill directory.

### Real-World Example: macos-cleaner Installation Issue

**Scenario**: After creating macos-cleaner skill and updating all documentation, `claude plugin install macos-cleaner@daymade-skills` failed with "Plugin not found".

**Investigation**:
```bash
# 1. Check git status
git status
# Output: 16 modified/untracked files

# 2. Check marketplace cache
ls -la ~/.claude/plugins/cache/daymade-skills/
# Output: Last modified Dec 20 (weeks old!)

# 3. Check GitHub
# marketplace.json on GitHub: version 1.20.0 (old)
# Local marketplace.json: version 1.21.0 (new)
```

**Root cause**: Local changes weren't pushed to GitHub. CLI was pulling from GitHub, not local files.

**Solution**:
```bash
# 1. Commit and push
git add -A
git commit -m "Release v1.21.0: Add macos-cleaner"
git push

# 2. Update marketplace
claude plugin marketplace update daymade-skills

# 3. Install
claude plugin install macos-cleaner@daymade-skills
# ✔ Successfully installed plugin: macos-cleaner@daymade-skills
```

**Verification**:
```bash
cat ~/.claude/plugins/installed_plugins.json | jq '.plugins["macos-cleaner@daymade-skills"]'
# Output: Installation details with correct version

ls ~/.claude/plugins/cache/daymade-skills/macos-cleaner/1.0.0/
# Output: All skill files present
```

**Lesson**: Always remember the GitHub-based architecture. Local changes are invisible until pushed.

### Advanced: Manual Cache Inspection

If automated commands don't reveal the issue, manually inspect:

```bash
# 1. Check marketplace clone
cat ~/.claude/plugins/marketplaces/{marketplace-name}/.claude-plugin/marketplace.json | jq '.metadata.version'

# 2. Check what's in cache
ls -R ~/.claude/plugins/cache/{marketplace-name}/

# 3. Compare with GitHub
curl -s https://raw.githubusercontent.com/{owner}/{repo}/main/.claude-plugin/marketplace.json | jq '.metadata.version'

# 4. Check installation record
cat ~/.claude/plugins/installed_plugins.json | jq '.plugins' | grep -i "{skill-name}"
```

### When All Else Fails

1. **Complete cache reset**:
   ```bash
   rm -rf ~/.claude/plugins/cache/*
   claude plugin marketplace update {marketplace-name}
   ```

2. **Re-register marketplace**:
   ```bash
   # Remove marketplace
   # (No direct command, manual edit ~/.claude/plugins/known_marketplaces.json)

   # Re-add
   claude plugin marketplace add https://github.com/{owner}/{repo}
   ```

3. **Check Claude Code version**:
   ```bash
   claude --version
   # Plugins require Claude Code v2.0.12+
   ```

4. **Enable verbose logging** (if available):
   ```bash
   CLAUDE_DEBUG=1 claude plugin install {plugin}@{marketplace}
   ```

### Getting Help

If you're still stuck:

1. **Check GitHub issues**: https://github.com/anthropics/claude-code/issues
2. **Verify marketplace.json**: Run `claude plugin validate .claude-plugin/marketplace.json`
3. **Compare with working marketplace**: Study anthropic's official marketplace structure
4. **Document your debugging**: Include output from all diagnostic commands above

For this project specifically, refer to:
- [Plugin and Skill Architecture](#plugin-and-skill-architecture) - Architecture overview (this document)
- [skill-creator/SKILL.md](./skill-creator/SKILL.md) - Skill creation guide
- [CONTRIBUTING.md](./CONTRIBUTING.md) - Development workflow
