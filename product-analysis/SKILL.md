---
name: product-analysis
description: Multi-path parallel product analysis with cross-model test-time compute scaling. Spawns parallel agents (Claude Code agent teams + Codex CLI) to explore product from multiple perspectives, then synthesizes findings into actionable optimization plans. Can invoke competitors-analysis for competitive benchmarking. Use when "product audit", "self-review", "发布前审查", "产品分析", "analyze our product", "UX audit", or "信息架构审计".
argument-hint: "[scope: full|ux|api|arch|compare]"
---

# Product Analysis

Multi-path parallel product analysis that combines **Claude Code agent teams** and **Codex CLI** for cross-model test-time compute scaling.

**Core principle**: Same analysis task, multiple AI perspectives, deep synthesis.

## How It Works

```
/product-analysis full
         │
         ├─ Step 0: Auto-detect available tools (codex? competitors?)
         │
    ┌────┼──────────────┐
    │    │              │
 Claude Code         Codex CLI (auto-detected)
 Task Agents         (background Bash)
 (Explore ×3-5)      (×2-3 parallel)
    │                   │
    └────────┬──────────┘
             │
      Phase 1.5: rendered UX gate (ux/full)
      frontend-visual-qa
             │
      Synthesis (main context)
             │
      Structured Report
```

## Step 0: Auto-Detect Available Tools

Before launching any agents, detect what tools are available:

```bash
# Check if Codex CLI is installed
which codex 2>/dev/null && codex --version
```

**Decision logic**:
- If `codex` is found: Inform the user — "Codex CLI detected (version X). Will run cross-model analysis for richer perspectives."
- If `codex` is not found: Silently proceed with Claude Code agents only. Do NOT ask the user to install anything.

Also detect the project type to tailor agent prompts:
```bash
# Detect project type
ls package.json 2>/dev/null    # Node.js/React
ls pyproject.toml 2>/dev/null  # Python
ls Cargo.toml 2>/dev/null      # Rust
ls go.mod 2>/dev/null          # Go
```

## Scope Modes

Parse `$ARGUMENTS` to determine analysis scope:

| Scope | What it covers | Typical agents |
|-------|---------------|----------------|
| `full` | UX + API + Architecture + Docs, including the Phase 1.5 rendered UX gate (default) | 5 Claude + Codex (if available) + frontend-visual-qa |
| `ux` | Frontend navigation, information density, user journey, empty state, onboarding, including the Phase 1.5 rendered UX gate | 3 Claude + Codex (if available) + frontend-visual-qa |
| `api` | Backend API coverage, endpoint health, error handling, consistency | 2 Claude + Codex (if available) |
| `arch` | Module structure, dependency graph, code duplication, separation of concerns | 2 Claude + Codex (if available) |
| `compare X Y` | Self-audit + competitive benchmarking (invokes `/competitors-analysis`) | 3 Claude + competitors-analysis |

## Phase 1: Parallel Exploration

Launch all exploration agents simultaneously using Task tool (background mode).

### Claude Code Agents (always)

For each dimension, spawn a Task agent with `subagent_type: Explore` and `run_in_background: true`:

**Agent A — Frontend Navigation & Information Density**
```
Explore the frontend navigation structure and entry points:
1. App.tsx: How many top-level components are mounted simultaneously?
2. Left sidebar: How many buttons/entries? What does each link to?
3. Right sidebar: How many tabs? How many sections per tab?
4. Floating panels: How many drawers/modals? Which overlap in functionality?
5. Count total first-screen interactive elements for a new user.
6. Identify duplicate entry points (same feature accessible from 2+ places).
Give specific file paths, line numbers, and element counts.
```

**Agent B — User Journey & Empty State**
```
Explore the new user experience:
1. Empty state page: What does a user with no sessions see? Count clickable elements.
2. Onboarding flow: How many steps? What information is presented?
3. Prompt input area: How many buttons/controls surround the input box? Which are high-frequency vs low-frequency?
4. Mobile adaptation: How many nav items? How does it differ from desktop?
5. Estimate: Can a new user complete their first conversation in 3 minutes?
Give specific file paths, line numbers, and UX assessment.
```

**Agent C — Backend API & Health**
```
Explore the backend API surface:
1. List ALL API endpoints (method + path + purpose).
2. Trace frontend, CLI, integration and documented external/API consumers. Mark unused only with consumer and lifecycle evidence; otherwise report coverage unknown.
3. Check error handling consistency (do all endpoints return structured errors?).
4. Check authentication/authorization patterns (which endpoints require auth?).
5. Identify any endpoints that duplicate functionality.
Give specific file paths and line numbers.
```

**Agent D — Architecture & Module Structure** (full/arch scope only)
```
Explore the module structure and dependencies:
1. Map the module dependency graph (which modules import which).
2. Identify circular dependencies or tight coupling.
3. Find code duplication across modules (same pattern in 3+ places).
4. Check separation of concerns (does each module have a single responsibility?).
5. Identify dead code or unused exports.
Give specific file paths and line numbers.
```

**Agent E — Documentation & Config Consistency** (full scope only)
```
Explore documentation and configuration:
1. Compare README claims vs actual implemented features.
2. Check config file consistency (base.yaml vs .env.example vs code defaults).
3. Find outdated documentation (references to removed features/files).
4. Check test coverage gaps (which modules have no tests?).
Give specific file paths and line numbers.
```

### Codex CLI Agents (auto-detected)

If Codex CLI was detected in Step 0, launch parallel Codex analyses via background Bash.

Each Codex invocation gets the same dimensional prompt but from a different model's perspective:

```bash
codex -m o4-mini \
  -c model_reasoning_effort="high" \
  --full-auto \
  "Analyze the frontend navigation structure of this project. Count all interactive elements visible to a new user on first screen. Identify duplicate entry points where the same feature is accessible from 2+ places. Give specific file paths and counts."
```

Run 2-3 Codex commands in parallel (background Bash), one per major dimension.

**Important**: Codex runs in the project's working directory. It has full filesystem access. The `--full-auto` flag (or `--dangerously-bypass-approvals-and-sandbox` for older versions) enables autonomous execution.

## Phase 1.5: Rendered UX Gate (`ux` and `full` scopes)

After source exploration and before synthesis, use the Skill tool to invoke `/frontend-visual-qa` against the canonical rendered artifact. This gate is required for `ux` and `full`; it does not apply to `api` or `arch`.

Give `frontend-visual-qa` a bounded audit contract that names:

- the canonical target identity, actor, conditional state, and representative data;
- the declared viewport matrix, including wide and narrow desktop widths when both are supported;
- the key journeys and states needed to test the UX claims, such as first run or empty state, the primary task, error and recovery, and navigation return paths;
- the required evidence level and the read-only or fix authority.

Return its current-render status, findings with viewport/state/reproduction, verified journeys, delivery readback, and unverified surfaces into synthesis as a distinct evidence stream. Missing or blocked rendered evidence is a gap in the UX/full audit; do not replace it with source inspection.

**Division of labor**:

- `product-analysis` owns multi-perspective product judgment: combining source and rendered evidence, resolving scope differences, assigning P0/P1/P2 priorities, and proposing changes.
- `frontend-visual-qa` owns rendered evidence: pixel and layout inspection, responsive viewports, state and journey exercise, and canonical-target/delivery readback.

Source files, component existence, DOM geometry, build success, and static interaction traces can generate hypotheses or support diagnosis, but they do not satisfy this gate. Pixel-level composition and real interaction/journey evidence must come from the rendered product.

## Phase 2: Competitive Benchmarking (compare scope only)

When scope is `compare`, invoke the competitors-analysis skill for each competitor:

```
Use the Skill tool to invoke: /competitors-analysis {competitor-name} {competitor-url}
```

This delegates to the orthogonal `competitors-analysis` skill which handles:
- Repository cloning and validation
- Evidence-based code analysis (file:line citations)
- Competitor profile generation

## Phase 3: Synthesis

After all agents complete, synthesize findings in the main conversation context.

### Cross-Validation

Use [the synthesis method](references/synthesis_methodology.md) to compare findings
across agents. Treat agreement and disagreement as review leads; verify material
claims against original sources or reproducible observations of the relevant
consumer. Base confidence on measurement validity, scope coverage and evidence
independence, rather than votes or model identity. Reconcile different scopes
before combining counts. Use counts to locate possible task friction; verify the
task effect before claiming usability or business impact.

### Quantification

Extract hard numbers from agent reports:

| Metric | What to measure |
|--------|----------------|
| First-screen interactive elements | Total count of buttons/links/inputs visible to new user |
| Feature entry point duplication | Number of features with 2+ entry points |
| API consumer coverage | Routes with observed consumers, verified unused routes and unknown coverage, including CLI/integration/external clients |
| Onboarding steps to first value | Steps from launch to first successful action |
| Module coupling score | Number of circular or bi-directional dependencies |

### Structured Output

Produce a layered optimization report:

```markdown
## Product Analysis Report

### Executive Summary
[1-2 sentences: key finding]

### Quantified Findings
| Metric | Value | Assessment |
|--------|-------|------------|
| ... | ... | ... |

### P0: Critical (block launch)
[Issues that prevent basic usability]

### P1: High Priority (launch week)
[Issues that significantly degrade experience]

### P2: Medium Priority (next sprint)
[Issues worth addressing but not blocking]

### Cross-Model Insights
[Findings that only one model identified — worth investigating]

### Competitive Position (if compare scope)
[How we compare on key dimensions]
```

## Workflow Checklist

- [ ] Parse `$ARGUMENTS` for scope
- [ ] Auto-detect Codex CLI availability (`which codex`)
- [ ] Auto-detect project type (package.json / pyproject.toml / etc.)
- [ ] Launch Claude Code Explore agents (3-5 parallel, background)
- [ ] Launch Codex CLI commands (2-3 parallel, background) if detected
- [ ] Invoke `/competitors-analysis` if `compare` scope
- [ ] Collect all source-agent results
- [ ] For `ux`/`full`, invoke `/frontend-visual-qa` on the canonical render with declared viewports and key journeys
- [ ] Record rendered status, verified journeys, delivery readback, and unverified surfaces separately from source findings
- [ ] Cross-validate findings
- [ ] Quantify metrics
- [ ] Generate structured report with P0/P1/P2 priorities

## References

- [references/analysis_dimensions.md](references/analysis_dimensions.md) — Detailed audit dimension definitions and prompts
- [references/synthesis_methodology.md](references/synthesis_methodology.md) — How to weight and merge multi-agent findings
- [references/codex_patterns.md](references/codex_patterns.md) — Codex CLI invocation patterns and flag reference
