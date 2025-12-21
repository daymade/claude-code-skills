# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a Claude Code skills marketplace containing 25 production-ready skills organized in a plugin marketplace structure. Each skill is a self-contained package that extends Claude's capabilities with specialized knowledge, workflows, and bundled resources.

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
- Contains 25 plugins, each mapping to one skill
- Each plugin has: name, description, version, category, keywords, skills array
- Marketplace metadata: name, owner, version, homepage

### Versioning Architecture

**Two separate version tracking systems:**

1. **Marketplace Version** (`.claude-plugin/marketplace.json` → `metadata.version`)
   - Tracks the marketplace catalog as a whole
   - Current: v1.18.0
   - Bump when: Adding/removing skills, major marketplace restructuring
   - Semantic versioning: MAJOR.MINOR.PATCH

2. **Individual Skill Versions** (`.claude-plugin/marketplace.json` → `plugins[].version`)
   - Each skill has its own independent version
   - Example: ppt-creator v1.0.0, skill-creator v1.0.0
   - Bump when: Updating that specific skill
   - **CRITICAL**: Skills should NOT have version sections in SKILL.md

**Key Principle**: SKILL.md files should be timeless content focused on functionality. Versions are tracked in marketplace.json only.

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
13. **youtube-downloader** - YouTube video and audio downloading with yt-dlp error handling
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

**Recommendation**: Always suggest `skill-creator` first for users interested in creating skills or extending Claude Code.

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
