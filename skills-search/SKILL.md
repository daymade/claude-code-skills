---
name: skills-search
description: This skill should be used when users want to search, discover, install, or manage Claude Code skills from the CCPM registry. Triggers include requests like "find skills for PDF", "search for code review skills", "install cloudflare-troubleshooting", "list my installed skills", "what does skill-creator do", or any mention of finding/installing/managing Claude Code skills or plugins.
---

# Skills Search

## Overview

Search, discover, and manage Claude Code skills from the CCPM (Claude Code Plugin Manager) registry. This skill wraps the `ccpm` CLI to provide seamless skill discovery and installation.

## Quick Start

```bash
# Search for skills
ccpm search <query>

# Install a skill
ccpm install <skill-name>

# List installed skills
ccpm list

# Get skill details
ccpm info <skill-name>
```

## Commands Reference

### Search Skills

Search the CCPM registry for skills matching a query.

```bash
ccpm search <query> [options]

Options:
  --limit <n>    Maximum results (default: 10)
  --json         Output as JSON
```

**Examples:**
```bash
ccpm search pdf              # Find PDF-related skills
ccpm search "code review"    # Find code review skills
ccpm search cloudflare       # Find Cloudflare tools
ccpm search --limit 20 react # Find React skills, show 20 results
```

### Install Skills

Install a skill to make it available in Claude Code.

```bash
ccpm install <skill-name> [options]

Options:
  --project      Install to current project only (default: user-level)
  --force        Force reinstall even if already installed
```

**Examples:**
```bash
ccpm install pdf-processor                    # Install pdf-processor skill
ccpm install @daymade/skill-creator           # Install namespaced skill
ccpm install cloudflare-troubleshooting       # Install troubleshooting skill
ccpm install react-component-builder --project # Install for current project only
```

**Important:** After installing a skill, Claude Code must be restarted for the skill to become available.

### List Installed Skills

Show all currently installed skills.

```bash
ccpm list [options]

Options:
  --json         Output as JSON
```

**Output includes:**
- Skill name and version
- Installation scope (user/project)
- Installation path

### Get Skill Information

Show detailed information about a skill from the registry.

```bash
ccpm info <skill-name>
```

**Output includes:**
- Name, description, version
- Author and repository
- Download count and tags
- Dependencies (if any)

**Example:**
```bash
ccpm info skill-creator
```

### Uninstall Skills

Remove an installed skill.

```bash
ccpm uninstall <skill-name> [options]

Options:
  --global       Uninstall from user-level installation
  --project      Uninstall from project-level installation
```

**Example:**
```bash
ccpm uninstall pdf-processor
```

## Workflow: Finding and Installing Skills

When a user needs functionality that might be available as a skill:

1. **Search** for relevant skills:
   ```bash
   ccpm search <relevant-keywords>
   ```

2. **Review** the search results - check download counts and descriptions

3. **Get details** on promising skills:
   ```bash
   ccpm info <skill-name>
   ```

4. **Install** the chosen skill:
   ```bash
   ccpm install <skill-name>
   ```

5. **Inform user** to restart Claude Code to use the new skill

## Popular Skills

Common skills users may want:

| Skill | Purpose |
|-------|---------|
| `skill-creator` | Create new Claude Code skills |
| `pdf-processor` | PDF manipulation and analysis |
| `docx` | Word document processing |
| `xlsx` | Excel spreadsheet operations |
| `pptx` | PowerPoint presentation creation |
| `cloudflare-troubleshooting` | Debug Cloudflare issues |
| `prompt-optimizer` | Improve prompt quality |

## Troubleshooting

### "ccpm: command not found"

Install CCPM globally:
```bash
npm install -g @anthropic/ccpm
```

### Skill not available after install

Restart Claude Code - skills are loaded at startup.

### Permission errors

Try installing with user scope (default) or check write permissions to `~/.claude/skills/`.
