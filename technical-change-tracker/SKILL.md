---
name: technical-change-tracker
description: Track code changes with structured JSON records and accessible HTML output for AI session continuity. When a bot session expires, the next one picks up exactly where it left off. Features state machine enforcement, test cases with evidence, append-only revision history, and WCAG AA+ accessible dark-theme HTML dashboard.
---

# Technical Change (TC) Tracker

Track every code change with structured JSON records and accessible HTML output.
Enables seamless AI bot session handoff across projects.

## Install

```bash
git clone https://github.com/Elkidogz/technical-change-skill.git
```

## Commands

| Command | Description |
|---------|-------------|
| `/tc init` | Initialize TC tracking in current project |
| `/tc create <name>` | Create a new TC record |
| `/tc update <tc-id>` | Update a TC (status, files, tests) |
| `/tc status [tc-id]` | View TC status |
| `/tc resume <tc-id>` | Resume from previous session handoff |
| `/tc close <tc-id>` | Deploy and close a TC |
| `/tc export` | Regenerate all HTML from JSON |
| `/tc dashboard` | Regenerate dashboard |

## Features

- **JSON records** with append-only revision history and field-level change tracking
- **State machine**: Planned > In Progress > Blocked > Implemented > Tested > Deployed
- **Test cases** with log snippet evidence and manual approval
- **AI session handoff**: progress, next steps, blockers, key context, decisions
- **WCAG AA+ HTML**: dark theme, rem-based fonts, CSS-only dashboard filters
- **Zero dependencies**: Python stdlib only

## Repository

https://github.com/Elkidogz/technical-change-skill

MIT License.
