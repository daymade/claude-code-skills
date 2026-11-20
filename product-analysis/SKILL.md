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

For `ux` and `full`, also verify that the `frontend-visual-qa@daymade-skills`
companion is present in the host's current Skill catalog. Do not infer availability
from a repository path, an old session, or this marketplace's manifest. If it is
missing, report Phase 1.5 as **blocked — required companion not installed** and
give the user this installation command; do not substitute source inspection or
guess that installation/fix authority was granted:

```bash
claude plugin install frontend-visual-qa@daymade-skills
```

`api` and `arch` do not require the companion.

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
5. Estimate the total first-screen interactive elements for a new user and label the result as a source estimate.
6. Identify duplicate entry points (same feature accessible from 2+ places).
Give specific file paths, line numbers, element counts, and which values require rendered verification.
```

**Agent B — User Journey & Empty State**
```
Explore the new user experience:
1. Empty state page: What does a user with no sessions see? Count clickable elements.
2. Onboarding flow: How many steps? What information is presented?
3. Prompt input area: How many buttons/controls surround the input box? Which are high-frequency vs low-frequency?
4. Mobile adaptation: How many nav items? How does it differ from desktop?
5. Estimate the launch-to-first-successful-action steps and label the result as a source estimate.
6. Estimate whether a new user can complete their first conversation in 3 minutes; do not present the estimate as a rendered measurement.
Give specific file paths, line numbers, UX assessment, and which claims require rendered journey verification.
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

After source exploration and before synthesis, use the Skill tool to invoke `/frontend-visual-qa` against the canonical rendered artifact. This gate is required for `ux` and `full`; it does not apply to `api` or `arch`. If Step 0 found the companion missing, stop this phase as **blocked** rather than pretending source evidence is rendered evidence.

Give `frontend-visual-qa` a bounded audit contract that names:

- the canonical target identity, actor, conditional state, and representative data;
- whether freshness/deployment identity is in scope; if not, delivery status is `not applicable`;
- the declared viewport/device matrix. It must cover every viewport-dependent claim; include mobile and relevant device profiles whenever mobile or adaptive surfaces are in scope;
- the key journeys and states needed to test the UX claims, such as first run or empty state, the primary task, error and recovery, and navigation return paths;
- the required evidence level;
- three independent authority fields, each with an explicit value:
  - **Source authorization:** `audit-only` (default) or `fix-and-verify`;
  - **Interaction/action authority:** `read-only navigation` (default), `fixture-safe state changes`, or named actions;
  - **Target mutation authority:** `none` (default), `isolated diagnostic`, `local target`, or `deploy <named environment>`.

Return its current-render status, findings with viewport/state/reproduction, verified journeys, conditional delivery status/identity, and unverified surfaces into synthesis as a distinct evidence stream. Missing or blocked rendered evidence is a gap in the UX/full audit; do not replace it with source inspection.

Keep source estimates separate from rendered-verified metrics. When first-screen density or time-to-first-value is in scope, the rendered stream must report the first-screen control count and launch-to-first-value step count for the declared actor/state/viewports. A source-derived number may remain a hypothesis, but it must not be relabeled as rendered-verified.

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

Keep each number's evidence basis visible. Source exploration can produce an
**estimate**; only the rendered stream can produce a **rendered-verified** UX
metric. Never merge the two into one unqualified value.

| Metric | Source estimate | Rendered-verified value | Required rendered scope |
|--------|-----------------|-------------------------|-------------------------|
| First-screen interactive elements | Allowed, labeled `source estimate` | Count of actually visible controls | Required when first-screen density is in scope; report actor, state and every viewport used for a viewport claim |
| Feature entry point duplication | Allowed, with file:line evidence | Journey-verified duplicate paths | When duplication affects a user claim |
| API consumer coverage | Routes with observed consumers, verified unused routes and unknown coverage, including CLI/integration/external clients | Not applicable | Not applicable |
| Onboarding steps to first value | Allowed, labeled `source estimate` | Count of launch-to-first-successful-action steps | Required when onboarding/time-to-value is in scope; report the exercised journey and viewports |
| Module coupling score | Number of circular or bi-directional dependencies | Not applicable | Not applicable |

If a required rendered metric was not exercised, write `unverified` and explain
the missing state, viewport, journey or blocked companion. Do not fill it with the
source estimate.

### Structured Output

Produce a layered optimization report:

```markdown
## Product Analysis Report

### Executive Summary
[1-2 sentences: key finding]

### Audit Status
Current-render status: verified | partial | blocked | not applicable
Delivery status: matched | mismatched | unprovable | not applicable
Delivery identity: <only when freshness/deployment is in scope; otherwise "not applicable">

### Quantified Findings
| Metric | Source estimate | Rendered-verified value | Assessment |
|--------|-----------------|-------------------------|------------|
| ... | ... | ... | ... |

### Rendered Evidence
[For ux/full: viewport/device matrix, first-screen control count and launch-to-first-value steps when in scope, exercised journeys/states, findings tied to viewport/state/reproduction, and unverified surfaces. For api/arch: "not applicable."]

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
- [ ] For `ux`/`full`, verify `frontend-visual-qa@daymade-skills` is in the current host catalog; block Phase 1.5 if missing
- [ ] Launch Claude Code Explore agents (3-5 parallel, background)
- [ ] Launch Codex CLI commands (2-3 parallel, background) if detected
- [ ] Invoke `/competitors-analysis` if `compare` scope
- [ ] Collect all source-agent results
- [ ] For `ux`/`full`, invoke `/frontend-visual-qa` on the canonical render with declared viewports, key journeys and all three authority fields
- [ ] Record rendered status, viewport coverage, verified journeys, conditional delivery readback, and unverified surfaces separately from source findings
- [ ] Keep source estimates separate from rendered-verified first-screen control counts and launch-to-first-value steps
- [ ] Cross-validate findings
- [ ] Quantify metrics with evidence basis and scope
- [ ] Generate structured report with P0/P1/P2 priorities and a distinct Rendered Evidence section

## References

- [references/analysis_dimensions.md](references/analysis_dimensions.md) — Detailed audit dimension definitions and prompts
- [references/synthesis_methodology.md](references/synthesis_methodology.md) — How to weight and merge multi-agent findings
- [references/codex_patterns.md](references/codex_patterns.md) — Codex CLI invocation patterns and flag reference
