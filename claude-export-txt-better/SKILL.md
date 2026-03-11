---
name: fixing-claude-export-conversations
description: >
  Fixes broken line wrapping in Claude Code exported conversation files (.txt),
  reconstructing tables, paragraphs, paths, and tool calls that were hard-wrapped
  at fixed column widths. Includes an automated validation suite (generic, file-agnostic checks).
  Triggers when the user has a Claude Code export file with broken formatting,
  mentions "fix export", "fix conversation", "exported conversation", "make export
  readable", references a file matching YYYY-MM-DD-HHMMSS-*.txt, or has a .txt
  file with broken tables, split paths, or mangled tool output from Claude Code.
---

# Fixing Claude Code Export Conversations

Reconstruct broken line wrapping in Claude Code exported `.txt` files.

## Quick Start

```bash
# Fix and show stats
uv run <skill-path>/scripts/fix-claude-export.py <export.txt> --stats

# Custom output
uv run <skill-path>/scripts/fix-claude-export.py <export.txt> -o fixed.txt

# Validate the result (53 automated checks)
uv run <skill-path>/scripts/validate-claude-export-fix.py <export.txt> fixed.txt
```

Replace `<skill-path>` with the resolved path to this skill's directory. Find it with:
```bash
find ~/.claude -path "*/fixing-claude-export-conversations/scripts" -type d 2>/dev/null
```

## Workflow

Copy this checklist and track progress:

```
- [ ] Step 1: Locate the exported .txt file
- [ ] Step 2: Run fix script with --stats
- [ ] Step 3: Run validation suite
- [ ] Step 4: Spot-check output (tables, CJK paragraphs, tool results)
- [ ] Step 5: Deliver fixed file to user
```

**Step 1: Locate the file.** Claude Code exports use the naming pattern `YYYY-MM-DD-HHMMSS-<slug>.txt`.

**Step 2: Run the fix script.**
```bash
uv run <skill-path>/scripts/fix-claude-export.py <input.txt> -o <output.txt> --stats
```
Review the stats output — typical results: 20-25% line reduction, 80+ table borders fixed, 160+ table cells fixed.

**Step 3: Run the validation suite.**
```bash
uv run <skill-path>/scripts/validate-claude-export-fix.py <input.txt> <output.txt>
```
All checks must pass. If any fail, investigate before delivering. Use `--verbose` for full details on passing checks too.

**Step 4: Spot-check.** Open the output and verify:
- Tables have intact borders (box-drawing characters on single lines)
- CJK/English mixed text has pangu spacing (`Portal 都需要`, not `Portal都需要`)
- Tool result blocks (`⎿`) have complete content on joined lines
- Diff output within tool results has each line number on its own line

**Step 5: Deliver** the fixed file to the user.

## What Gets Fixed

The script handles 10 content types using a state-machine with next-line look-ahead:

- **User prompts** (`❯` prefix, dw=76 padding) — paragraph joins with pangu spacing
- **Claude responses** (`●` prefix) — narrative, bullet, and numbered list joins
- **Claude paragraphs** (2-space indent) — next-line look-ahead via `_is_continuation_fragment`
- **Tables** — border reconstruction, cell re-padding with pipe-count tracking
- **Tool calls** (`● Bash(` etc.) — path and argument reconstruction
- **Tool results** (`⎿` prefix) — continuation joins including deeper-indented fragments
- **Plan text** (5-space indent) — next-line look-ahead via `_is_plan_continuation_fragment`
- **Agent tree** (`├─`/`└─`) — preserved structure
- **Separators** (`────`, `---`) — never joined
- **Tree connectors** (standalone `│`) — preserved

## Key Design Decisions

**Next-line look-ahead** (not dw thresholds): Instead of asking "was this line wrapped?" (fragile threshold), the script asks "does the next line look like a continuation?" by examining its content patterns — lowercase start, CJK ideograph start, opening bracket, hyphen/slash/underscore continuation.

**Pangu spacing**: Inserts spaces between ASCII alphanumeric characters and CJK ideographs at join boundaries. Also triggers for `%`, `#`, `+`, `:` adjacent to CJK.

**Mid-token detection**: Joins without space when boundaries indicate identifiers (`BASE_` + `URL`), paths (`documents` + `/05-team`), or hyphenated names (`ready` + `-together`). Exception: `--` prefix gets a space (`run` + `--headed`).

## Safety

- Never modifies the original file
- Marker counts verified: `❯`, `●`, `✻`, `⎿`, `…` must match input/output
- Runaway join detection: warns if any line exceeds 500 display-width
- Strict UTF-8 encoding — no silent fallbacks

## Dependencies

Python 3.10+ via `uv run` — zero external packages (stdlib only: `unicodedata`, `argparse`, `re`, `pathlib`, `dataclasses`).