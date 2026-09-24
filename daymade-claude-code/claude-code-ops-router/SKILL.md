---
name: claude-code-ops-router
description: >-
  Routes Claude Code setup: plugin/Skill repair, marketplace, statusline, model
  profiles/source sync, usage/quota reset ping, memory→docs, .txt export repair.
  Reads one bundled specialist; history, hooks, and Lark keep their own entries.
---

# Claude Code operations router

Choose the one specialist that owns the requested operation. Locate **this
loaded** `claude-code-ops-router/SKILL.md` in the active catalog or invocation,
follow symlinks to its canonical path, and verify its parent is
`claude-code-ops-router`. Its parent's parent is the suite root. Resolve the
selected relative path against that directory and verify it is a direct
sibling `SKILL.md` inside the root. Never anchor resolution to the task's
working directory or a remembered plugin cache. `${CLAUDE_PLUGIN_ROOT}` may
help in Claude Code, but it is absent in Codex. Stop if the active router path
cannot be identified unambiguously.

Read the selected child `SKILL.md` **in full** before acting. Continue a
truncated read and load its task-required references. Its instructions,
scripts, and assets remain installed; only its automatic catalog entry is
hidden. Claude users retain the original manual commands named by each child's
frontmatter. The export-repair directory `claude-export-txt-better` exposes
`/daymade-claude-code:fixing-claude-export-conversations`.

| Requested operation | Read this exact file |
|---|---|
| Repair a Claude Code plugin or Skill that is installed but missing, disabled, or failing to activate | `../claude-skills-troubleshooting/SKILL.md` |
| Install, change, or repair the Claude Code statusline | `../statusline-generator/SKILL.md` |
| Repair line wrapping, tables, paths, or tool output in an exported Claude Code `.txt` conversation | `../claude-export-txt-better/SKILL.md` |
| Create or maintain a Claude Code plugin marketplace, suite membership, or marketplace manifest | `../marketplace-dev/SKILL.md` |
| Analyze Claude Code/Desktop Code token use, cost, cache, quota burn, or 5-hour blocks | `../claude-usage-analyst/SKILL.md` |
| Configure isolated Claude Code model-provider profiles, aliases, or source-backed Claude/Codex Skill activation | `../claude-switch-models-setup/SKILL.md` |
| Migrate existing Claude personal memory into tool-agnostic AGENTS.md reference documents | `../claude-migrate-memory-to-doc/SKILL.md` |
| Set a one-shot local ping after a Claude subscription quota reset to start the next usage window | `../claude-code-ping-start-5h-quota/SKILL.md` |

Route by the requested operation, not by the word “Claude.” For example,
usage diagnosis selects `claude-usage-analyst`; a requested future reset ping
selects `claude-code-ping-start-5h-quota`. A Skill count, discovery-policy
audit, or cold-catalog change belongs to `skill-governance` when installed;
plugin activation repair is the narrower troubleshooting row here.

This router does not replace the direct entries for conversation-history
reading and continuation, prior-work retrieval, hooks, CLAUDE.md editing,
Lark, Claude.ai web-conversation export, terminal color screenshots, relayed
web-search repair, or technology selection. Do not use it to handle those
requests merely because Claude Code is mentioned. Selecting a child does not
authorize an external installation, credential operation, or scheduled job;
follow the selected child's instructions and the user's authorization.
