---
name: local-codex
description: "Launch and manage OpenAI Codex CLI (local agent) as a non-interactive coding sub-agent. Use when the user wants to delegate coding tasks to Codex, run code reviews, generate or refactor code, or use Codex GPT-5.5 agent capabilities through local CLI. Triggers on phrases like 'codex', 'run codex', 'codex exec', 'code review with codex', 'delegate to codex', 'use codex for coding', or any request to invoke the local Codex CLI agent. Uses ChatGPT Pro OAuth (flat-rate, no API charges) via ~/.codex/auth.json. Never uses API keys."
---

# Local Codex

Delegate coding tasks to the local OpenAI Codex CLI agent using your ChatGPT Pro subscription (OAuth, no API charges).

## When to Use

- User wants to generate, refactor, or review code via Codex
- User wants to run `codex exec` for non-interactive tasks
- User wants to use Codex's GPT-5.5 agent capabilities
- User mentions "codex", "run codex", "delegate to codex"

## Authentication (OAuth / ChatGPT Pro)

**CRITICAL**: This skill uses OAuth authentication from `~/.codex/auth.json` (ChatGPT Pro flat-rate subscription). **Do NOT set `OPENAI_API_KEY` or pass API keys** — that would switch to pay-per-use billing.

- Codex desktop app and CLI share the same auth cache
- If auth fails, run `codex login` in terminal (browser OAuth flow)
- For auth issues, see [references/oauth-guide.md](references/oauth-guide.md)

## Codex CLI Path

The skill auto-detects Codex CLI in this order:
1. `/Applications/Codex.app/Contents/Resources/codex` (desktop app)
2. `/usr/local/bin/codex` (npm global)
3. `/opt/homebrew/bin/codex` (Homebrew)
4. `~/.npm-global/bin/codex`
5. `which codex` fallback

## Usage Patterns

### 1. Basic exec (single task)

```bash
python3 scripts/codex_wrapper.py exec "<prompt>" [<workdir>] [<model>] [<sandbox>] [<timeout>]
```

Example:
```bash
python3 scripts/codex_wrapper.py exec \
  "Write a Python function to calculate fibonacci" \
  /tmp \
  gpt-5.5 \
  workspace-write \
  300
```

### 2. Code review

```bash
python3 scripts/codex_wrapper.py review [<workdir>] [<model>] [uncommitted:true] [<timeout>]
```

Example:
```bash
python3 scripts/codex_wrapper.py review \
  /path/to/repo \
  gpt-5.5 \
  true \
  300
```

### 3. Check status

```bash
python3 scripts/codex_wrapper.py status
```

## Output Format

The wrapper returns JSON with:
- `success`: bool
- `exit_code`: int
- `elapsed_seconds`: float
- `stdout`: raw output
- `stderr`: error stream (truncated)
- `parsed_jsonl`: parsed JSONL events (if --json)
- `final_message`: extracted assistant text (if available)

## Parameters

| Parameter | Default | Options |
|-----------|---------|---------|
| model | `gpt-5.5` | `gpt-5.5`, `gpt-5.5-pro`, `o4-mini`, etc. |
| sandbox | `workspace-write` | `read-only`, `workspace-write`, `danger-full-access` |
| timeout | 300 | seconds (increase for large tasks) |
| json_output | true | always true (wrapper parses JSONL) |

## Safety Notes

- `sandbox=read-only` for analysis/review tasks (no file writes)
- `sandbox=workspace-write` for code generation (writes to working dir)
- `sandbox=danger-full-access` only when explicitly needed (full system access)
- Always use `--skip-git-repo-check` when running outside git repos
- Use `--ephemeral` for one-off tasks (no session persistence)

## Session Management

For multi-step tasks, Codex supports session resume:
```bash
# First step
codex exec --ephemeral "Step 1..."
# Later
codex exec resume --last "Step 2..."
```

The wrapper currently runs single-shot exec. For multi-step workflows, use raw `codex exec` commands.

## Limitations

- Desktop app must be running for OAuth token refresh (or token must be fresh)
- `codex doctor` is buggy in current version (alpha), avoid using
- Environment variables are NOT inherited into Codex's sandbox; pass via config or prompt
- Large file operations may need increased timeout
