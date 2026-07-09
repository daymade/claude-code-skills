---
name: statusline-generator
description: >
  Installs, configures, customizes, or troubleshoots the Claude Code statusline
  (cwd, model, token counts). Use when the user wants to set up or change the
  statusline, switch minimal vs full layouts, show absolute token counts
  (e.g. ctx 108K / 1M) instead of a percentage, add cost via ccusage or git
  status, dump the stdin JSON Claude Code passes the script, or fix a statusline
  that is blank, silent, stuck, shows "permission denied", or stopped updating
  after a script edit (often a missing chmod +x). Trigger phrases: "configure
  statusline", "statusline blank", "status line not showing", "statusline
  broken", "show token count in statusline", 状态栏, 状态栏不显示, 状态栏空白,
  显示工作目录, 显示 token 数.
---

# Statusline Generator

A single-source-of-truth statusline for Claude Code. One script, two layouts,
end-to-end self-verification.

## Quick health check (start here when something is wrong)

Run this first whenever the statusline misbehaves. It catches the silent failures
that account for most "configured but not working" reports:

```bash
bash scripts/health_check.sh
```

It validates four layers:
1. `~/.claude/statusline.sh` exists and is executable. **Missing `chmod +x` is
   the single most common silent-failure cause** — Claude Code runs the script,
   `exec` fails, statusline goes blank.
2. `~/.claude/settings.json` has a valid `statusLine` block pointing at the script.
3. Mock stdin tests covering complete data, zero tokens, missing fields,
   `$HOME` path shortening, and zero-fork git-branch rendering (via a synthetic
   `.git/HEAD` — no git binary required).
4. Real stdin replay from `/tmp/.claude-statusline-last-stdin.json` if you
   previously ran with `CLAUDE_STATUSLINE_DEBUG=1`.

Each failure prints a one-line fix command — you don't have to read documentation
to recover.

## Quick install

```bash
bash scripts/install_statusline.sh
```

This script:
- Backs up any existing `~/.claude/statusline.sh` and `settings.json`.
- Copies `generate_statusline.sh` to `~/.claude/statusline.sh` and `chmod +x`s it.
- Updates `settings.json` `statusLine` block via `jq` (preserves other settings).
- **Mandatorily runs `health_check.sh` and shows the result** — installation
  is not "complete" until verification passes.

Restart Claude Code (or send any new message) to see the statusline update.

## What you get

### Default — minimal one-line layout

```
~/code/myproject  [main]  Opus 4.7 (1M context)  ctx: 108K / 1M
```

Just the essentials: short path, git branch, model name, absolute token counts.
No colors, no cost, no percentage. The branch is read **zero-fork** — the script
reads `.git/HEAD` as a plain file (with worktree/submodule `gitdir:` indirection
and detached-HEAD short-sha handling) instead of spawning `git`, so it costs
nothing and works even on hosts without a git binary.

### Full — multi-line with cost and git

Set `CLAUDE_STATUSLINE_LAYOUT=full` in your shell profile to enable:

```
alex (Sonnet 4.6) [$0.42/$25.93]  ctx: 108K/1M (11%)
~/code/myproject
[git:main*+]
```

- Line 1: user, model, ccusage session/daily costs, color-coded ctx (green ≤50%,
  yellow 51–80%, red >80%).
- Line 2: short path.
- Line 3: git branch with `*` for modified, `+` for untracked.

## Layouts: how to switch

The script reads layout from environment, not flags (Claude Code passes JSON on stdin,
so flags would conflict). Set in `~/.zshrc` or `~/.bashrc`:

```bash
# Minimal (default — same as not setting it)
export CLAUDE_STATUSLINE_LAYOUT=minimal

# Full
export CLAUDE_STATUSLINE_LAYOUT=full
```

Restart your shell (or `source` the rc file) so Claude Code inherits the change,
then send a message — statusline refreshes within 300ms.

## Debug stdin capture

To see exactly what JSON Claude Code sends your script:

```bash
export CLAUDE_STATUSLINE_DEBUG=1
```

Each invocation writes its stdin to `/tmp/.claude-statusline-last-stdin.json`
(overwriting on every refresh). Inspect with `jq .`. Useful for:

- Diagnosing why a field doesn't render the way you expect.
- Re-running the script against real input: `cat /tmp/.claude-statusline-last-stdin.json | ~/.claude/statusline.sh`.
- Filing bug reports — paste the dump as ground truth.

## Authoring rules (why this skill is shaped this way)

Three production failure modes drove the current design. All are sealed in code,
not just docs:

### Rule 1 — Always `chmod +x`, always verify by running

The single biggest silent-failure cause of any statusline is a script without
the executable bit: Claude Code's `exec` fails silently and the bar goes blank
with no error. `install_statusline.sh` always `chmod +x`s; `health_check.sh`
flags the bit if missing. **If you hand-write or hand-edit a statusline script,
mock-test it before declaring done:** `echo '{}' | bash your-script.sh`.

### Rule 2 — "Configuration complete" is meaningless without evidence

"Wrote the file and updated settings.json" is not the same as "the script runs
and produces the expected output." `install_statusline.sh` therefore always
runs `health_check.sh` at the end and exits non-zero if any check fails.
Treat any "complete!" report from any agent that lacks evidence as suspect.

### Rule 3 — The statusline is a hot path: budget subprocesses, not just correctness

A statusline script looks like UI polish, but it executes on **every refresh in
every concurrent agent session**. Whatever it spawns gets multiplied by refresh
rate × number of live sessions, all day. Measured on a machine running many
concurrent sessions: a package-runner statusline (`bunx <pkg>@latest`-style,
which re-resolves the registry and re-writes a lockfile per refresh, then runs
`git status` + `git branch`) cost ~0.4s CPU per refresh; this script costs
~0.01s. Across many sessions that difference is a measurable share of
machine-wide process churn, heat, and battery — the statusline was one of the
top contributors found in a real battery-drain investigation (2026-07).

Concretely:
- **Never resolve packages at refresh time.** No `bunx`/`npx` `@latest` in
  `statusLine.command` — pin and install once, or use a local script.
- **Don't spawn `git` for the branch.** Read `.git/HEAD` as a file (see
  `git_branch_fast` in the script) — same answer, zero subprocesses.
- **Treat `git status` (dirty state) as a luxury.** It walks the worktree on
  every refresh; only the full layout runs it, and only when explicitly enabled.
- **Budget: a statusline refresh should cost single-digit milliseconds and
  a handful of forks at most** (one `jq` + one `awk` here).

For field-level traps (`used_percentage` null at session start, `total_input_tokens`
semantics across Claude Code versions, hardcoded `context_window_size`), see
[`references/context-window-schema.md`](references/context-window-schema.md).

## Customization

For colors, custom segments (hostname, time, etc.), and disabling cost tracking,
see [`references/customization.md`](references/customization.md).

## Dependencies

The script auto-detects available tools and degrades gracefully:

| Tool | Required for | Fallback |
|------|-------------|----------|
| `jq` | JSON parsing (preferred) | falls back to `python3` |
| `python3` | JSON parsing fallback | bare `cwd` only |
| `awk` | token K/M formatting | required by both layouts |
| `git` | dirty-state `*`/`+` markers (full layout only — minimal reads the branch from `.git/HEAD` without git) | silent skip if missing or not in repo |
| `ccusage` | cost (full layout) | silent skip if missing |

Install on macOS: `brew install jq`. On Debian/Ubuntu: `apt install jq`.

## Troubleshooting

For symptom-by-symptom diagnostics, see
[`references/troubleshooting-decision-tree.md`](references/troubleshooting-decision-tree.md).
It walks through:

1. Statusline blank or never updates (chmod cause)
2. ctx segment missing or wrong (field traps)
3. Want token counts not percentages (layout switch)
4. Colors render as raw escape codes (terminal compatibility)
5. Git segment missing (full layout)
6. Cost segment missing (ccusage / cache)
7. Edits have no effect (path mismatch)
8. Slow refresh (jq vs python3)

## Resources

| File | Purpose |
|------|---------|
| `scripts/generate_statusline.sh` | The statusline script. Single source of truth. Two layouts via `CLAUDE_STATUSLINE_LAYOUT`. |
| `scripts/install_statusline.sh` | Idempotent installer. Backs up, copies, chmods, wires `settings.json`, runs health check. |
| `scripts/health_check.sh` | Four-layer verification: file perms, settings.json wiring, mock stdin tests, real stdin replay. |
| `references/troubleshooting-decision-tree.md` | Symptom-driven diagnostic flowchart. Load when statusline misbehaves. |
| `references/customization.md` | Color changes, custom segments, threshold tuning, single-line full layout. Load when user wants to modify how the statusline looks. |
| `references/context-window-schema.md` | Claude Code statusline JSON schema. Documents every field plus `current_usage` vs `total_input_tokens` semantics across versions. |
| `references/color_codes.md` | ANSI color codes reference. Load for color customization. |
| `references/ccusage_integration.md` | ccusage integration deep-dive: caching, JSON shape, troubleshooting. Load for cost-related issues. |
