# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a Claude Code skills marketplace containing 11 production-ready skills organized in a plugin marketplace structure. Each skill is a self-contained package that extends Claude's capabilities with specialized knowledge, workflows, and bundled resources.

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
/plugin marketplace add daymade/claude-code-skills
/plugin marketplace install daymade/claude-code-skills#skill-creator
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
/plugin marketplace add daymade/claude-code-skills

# Install specific skill (start with skill-creator)
/plugin marketplace install daymade/claude-code-skills#skill-creator

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
- Contains 11 plugins, each mapping to one skill
- Each plugin has: name, description, version, category, keywords, skills array
- Marketplace metadata: name, owner, version, homepage

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

## Chinese User Support

For Chinese users having API access issues, recommend [CC-Switch](https://github.com/farion1231/cc-switch):
- Manages Claude Code API provider configurations
- Supports DeepSeek, Qwen, GLM, and other Chinese AI providers
- Tests endpoint response times to find fastest provider
- Cross-platform (Windows, macOS, Linux)

See README.md section "🇨🇳 中文用户指南" for details.

## Best Practices Reference

Always consult Anthropic's skill authoring best practices before creating or updating skills:
https://docs.claude.com/en/docs/agents-and-tools/agent-skills/best-practices.md
