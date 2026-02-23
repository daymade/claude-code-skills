# Codex CLI Integration Patterns

How to use OpenAI Codex CLI for cross-model parallel analysis.

## Basic Invocation

```bash
codex -m o4-mini \
  -c model_reasoning_effort="high" \
  --full-auto \
  "Your analysis prompt here"
```

## Flag Reference

| Flag | Purpose | Values |
|------|---------|--------|
| `-m` | Model selection | `o4-mini` (fast), `gpt-5.3-codex-spark` (deep) |
| `-c model_reasoning_effort` | Reasoning depth | `low`, `medium`, `high`, `xhigh` |
| `-c model_reasoning_summary_format` | Summary format | `experimental` (structured output) |
| `--full-auto` | Skip all approval prompts | (no value) |
| `--dangerously-bypass-approvals-and-sandbox` | Legacy full-auto flag | (no value, older versions) |

## Recommended Configurations

### Fast Scan (quick validation)
```bash
codex -m o4-mini \
  -c model_reasoning_effort="medium" \
  --full-auto \
  "prompt"
```

### Deep Analysis (thorough investigation)
```bash
codex -m o4-mini \
  -c model_reasoning_effort="xhigh" \
  -c model_reasoning_summary_format="experimental" \
  --full-auto \
  "prompt"
```

## Parallel Execution Pattern

Launch multiple Codex analyses in background using Bash tool with `run_in_background: true`:

```bash
# Dimension 1: Frontend
codex -m o4-mini -c model_reasoning_effort="high" --full-auto \
  "Analyze frontend navigation: count interactive elements, find duplicate entry points, assess cognitive load for new users. Give file paths and counts."

# Dimension 2: User Journey
codex -m o4-mini -c model_reasoning_effort="high" --full-auto \
  "Analyze new user experience: what does empty state show? How many steps to first action? Count clickable elements competing for attention. Give file paths."

# Dimension 3: Backend API
codex -m o4-mini -c model_reasoning_effort="high" --full-auto \
  "List all API endpoints. Identify unused endpoints with no frontend consumer. Check error handling consistency. Give router file paths."
```

## Output Handling

Codex outputs to stdout. When run in background:
1. Use Bash `run_in_background: true` to launch
2. Use `TaskOutput` to retrieve results when done
3. Parse the text output for findings

## Cross-Model Value

The primary value of Codex in this workflow is **independent perspective**:
- Different training data may surface different patterns
- Different reasoning approach may catch what Claude misses
- Agreement across models = high confidence
- Disagreement = worth investigating manually

## Limitations

- Codex CLI must be installed and configured (`codex` command available)
- Requires OpenAI API key configured
- No MCP server access (only filesystem tools)
- Output is unstructured text (needs parsing)
- Rate limits apply per OpenAI account
