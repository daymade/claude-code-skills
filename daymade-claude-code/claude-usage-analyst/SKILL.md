---
name: claude-usage-analyst
description: Analyze Claude Code and Claude Desktop Code token usage, cost, quota burn, model mix, cache read/write, and 5-hour block consumption using ccusage evidence. Use when the user asks why Claude quota was exhausted, whether a model such as fable/opus/sonnet is unusually expensive, how many tokens were spent today or historically, or needs a human-friendly explanation of local Claude Code CLI/Desktop usage.
---

# Claude Usage Analyst

## Overview

Use this skill to produce evidence-based usage explanations from local `ccusage` data. Separate observed numbers from interpretation, and explain quota burn in human terms.

## Workflow

1. Verify `ccusage` is available:
   ```bash
   ccusage --version
   ```
   If missing, install or update with `npm install -g ccusage@latest` or run with `npx ccusage@latest`.

2. Run the bundled analyzer for the requested window:
   ```bash
   python3 /path/to/claude-usage-analyst/scripts/analyze_claude_usage.py \
     --since YYYY-MM-DD --until YYYY-MM-DD --timezone Asia/Shanghai
   ```
   Default `--since/--until` is today in the selected timezone.
   For historical comparison, set `--since` to an earlier date such as the first day of the month; otherwise rank/median fields only describe the single target day.

3. If the user asks about a specific model comparison, pass aliases:
   ```bash
   python3 scripts/analyze_claude_usage.py --model-a fable --model-b opus-4-8
   ```

4. Read `references/explanation-guide.md` when writing the final answer.

## Evidence Rules

- Base numeric claims on `ccusage` output or the bundled analyzer output.
- State the scope: `ccusage claude` measures local Claude Code usage logs, including Claude Desktop's Claude Code sessions when those local logs exist. It is not a complete ordinary Claude.ai chat bill.
- Report dates with timezone.
- Explain cache clearly: cache read tokens are still usage/quota pressure even though the user did not type those words.
- Do not infer Anthropic plan quota rules from local token counts unless the user provides plan details. Say "quota-like pressure" or "ccusage estimated cost/token burn" when exact plan accounting is unknown.
- When comparing models, compare both token volume and estimated cost. A model can have similar token volume but higher cost.

## Output Shape

Use this structure unless the user asks otherwise:

1. Short conclusion in plain language.
2. Evidence table: total tokens, cost, input, output, cache create, cache read.
3. Model comparison table.
4. 5-hour block table when quota exhaustion is discussed.
5. Explanation of why the burn happened.
6. Confidence and caveats.

Keep the answer readable for non-technical users. Avoid unexplained terms like "cache read" without a one-sentence translation.
