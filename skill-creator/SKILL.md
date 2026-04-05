---
name: skill-creator
description: Create new skills, modify and improve existing skills, and measure skill performance. Use when users want to create a skill from scratch, edit, or optimize an existing skill, run evals to test a skill, benchmark skill performance with variance analysis, or optimize a skill's description for better triggering accuracy.
license: Complete terms in LICENSE.txt
---

# Skill Creator

A skill for creating new skills and iteratively improving them.

At a high level, the process of creating a skill goes like this:

- Decide what you want the skill to do and roughly how it should do it
- Write a draft of the skill
- Create a few test prompts and run claude-with-access-to-the-skill on them
- Help the user evaluate the results both qualitatively and quantitatively
  - While the runs happen in the background, draft some quantitative evals if there aren't any (if there are some, you can either use as is or modify if you feel something needs to change about them). Then explain them to the user (or if they already existed, explain the ones that already exist)
  - Use the `eval-viewer/generate_review.py` script to show the user the results for them to look at, and also let them look at the quantitative metrics
- Rewrite the skill based on feedback from the user's evaluation of the results (and also if there are any glaring flaws that become apparent from the quantitative benchmarks)
- Repeat until you're satisfied
- Expand the test set and try again at larger scale

Your job when using this skill is to figure out where the user is in this process and then jump in and help them progress through these stages. So for instance, maybe they're like "I want to make a skill for X". You can help narrow down what they mean, write a draft, write the test cases, figure out how they want to evaluate, run all the prompts, and repeat.

On the other hand, maybe they already have a draft of the skill. In this case you can go straight to the eval/iterate part of the loop.

Of course, you should always be flexible and if the user is like "I don't need to run a bunch of evaluations, just vibe with me", you can do that instead.

Then after the skill is done (but again, the order is flexible), you can also run the skill description improver, which we have a whole separate script for, to optimize the triggering of the skill.

Cool? Cool.

## Communicating with the user

The skill creator is liable to be used by people across a wide range of familiarity with coding jargon. If you haven't heard (and how could you, it's only very recently that it started), there's a trend now where the power of Claude is inspiring plumbers to open up their terminals, parents and grandparents to google "how to install npm". On the other hand, the bulk of users are probably fairly computer-literate.

So please pay attention to context cues to understand how to phrase your communication! In the default case, just to give you some idea:

- "evaluation" and "benchmark" are borderline, but OK
- for "JSON" and "assertion" you want to see serious cues from the user that they know what those things are before using them without explaining them

It's OK to briefly explain terms if you're in doubt, and feel free to clarify terms with a short definition if you're unsure if the user will get it.

### Using AskUserQuestion (Critical — Read This)

**Use the AskUserQuestion tool aggressively at every decision point.** Do not ask open-ended text questions in conversation when structured choices exist. This is the single biggest UX improvement you can make — users juggle multiple windows and may not have looked at this conversation in 20 minutes.

**Every AskUserQuestion MUST follow this structure:**

1. **Re-ground**: State the skill name, current phase, and what just happened (1-2 sentences). The user may have context-switched away.
2. **Simplify**: Explain the decision in plain language. No function names or internal jargon. Say what it DOES, not what it's called.
3. **Recommend**: Lead with your recommendation and a one-line reason why. If options involve effort, show both scales: `(human: ~X min / Claude: ~Y min)`.
4. **Options**: Provide 2-4 concrete, lettered choices. Each option should be a clear action, not an abstract concept.

**Rules:**
- One decision per question — never batch unrelated choices
- Provide an escape hatch ("Other" is always implicit in AskUserQuestion)
- Accept the user's choice — nudge on tradeoffs but never refuse to proceed
- Skip the question if there's an obvious answer with no tradeoffs (just state what you'll do)

---

## Creating a skill

### Capture Intent

Start by understanding the user's intent. The current conversation might already contain a workflow the user wants to capture (e.g., they say "turn this into a skill"). If so, extract answers from the conversation history first — the tools used, the sequence of steps, corrections the user made, input/output formats observed. The user may need to fill the gaps, and should confirm before proceeding to the next step.

1. What should this skill enable Claude to do?
2. When should this skill trigger? (what user phrases/contexts)
3. What's the expected output format?
4. Should we set up test cases to verify the skill works? Skills with objectively verifiable outputs (file transforms, data extraction, code generation, fixed workflow steps) benefit from test cases. Skills with subjective outputs (writing style, art) often don't need them. Suggest the appropriate default based on the skill type, but let the user decide.

After extracting answers from conversation history (or asking questions 1-3), use **AskUserQuestion** to confirm the skill type and testing strategy:

```
Creating skill "[name]" — here's what I understand so far:
- Purpose: [1-sentence summary]
- Triggers on: [key phrases]
- Output: [format]

RECOMMENDATION: [Objective/Subjective/Hybrid] skill → [suggested testing approach]

Options:
A) Objective output (files, code, data) — set up automated test cases (Recommended if output is verifiable)
B) Subjective output (writing, design) — qualitative human review only
C) Hybrid — automated checks for structure, human review for quality
D) Skip testing for now — just build the skill and iterate by feel
```

This upfront classification drives the entire evaluation strategy downstream. Get it right here to avoid wasted effort later.

### Prior Art Research (Do Not Skip)

The user's private methodology — their domain rules, workflow decisions, competitive edge — is what makes a skill valuable. No public repo can provide that. But the user shouldn't waste time reinventing infrastructure (API clients, auth flows, rate limiting) when mature tools exist. Prior art research finds building blocks for the infrastructure layer so the skill can focus on encoding the user's unique methodology.

**Search these channels in order** (use subagents for 4-8 in parallel):

| Priority | Channel | What to search | How |
|----------|---------|---------------|-----|
| 1 | **Conversation history** | User's proven workflows, verified API patterns, corrections made during debugging | Grep recent conversations for the service/API name |
| 2 | **Local documents & SOPs** | User's private methodology, runbooks, existing skills | Search project directory, `~/.claude/CLAUDE.md`, `~/.claude/references/` |
| 3 | **Installed plugins & MCPs** | Already-integrated tools | Check `~/.claude/plugins/`, parse `installed_plugins.json`; check `~/.claude.json` for configured MCP servers |
| 4 | **skills.sh** | Community skills | `WebFetch https://skills.sh/?q=<keyword>` |
| 5 | **Anthropic official plugins** | Official/partner plugins | `WebFetch https://github.com/anthropics/claude-plugins-official/tree/main/plugins` and `external_plugins` directory |
| 6 | **MCP servers on GitHub** | Existing MCP servers for the same API | `WebSearch "<service-name> MCP server site:github.com"` |
| 7 | **Official API docs** | The target service's own documentation | `WebSearch "<service-name> API documentation"` or `WebFetch` the docs URL |
| 8 | **npm / PyPI** | SDK or CLI packages | `npm search <keyword>` or `curl https://pypi.org/pypi/<name>/json` |

Channels 1-3 surface the user's own proven patterns and existing integrations. Channels 4-8 find public infrastructure. The user's private SOP always takes precedence — public tools are building blocks, not replacements. In competitive domains (finance, trading, proprietary operations), the valuable methodology will never be public.

**If a public MCP server or skill is found, clone it and verify — don't trust the README:**

1. **Read the actual source code** — many projects have polished READMEs on hollow codebases
2. **Verify auth method** — does it match how the API actually authenticates? (X-Api-Key headers vs Bearer vs OAuth — many get this wrong)
3. **Check test coverage** — zero tests = prototype, not production-grade
4. **Check maintenance** — last commit date, open issue count, response to bug reports
5. **Check environment compatibility** — proxy/network assumptions, hardcoded DNS/IPs, region locks
6. **Check license** — MIT/Apache is fine; GPL/SSPL may conflict with proprietary use
7. **Check dependency weight** — huge dependency trees create conflict and security surface

**Decision matrix:**

| Finding | Action |
|---------|--------|
| Mature MCP/SDK handles the infrastructure | **Adopt it, build on top** — install the MCP, then build the skill as a workflow layer encoding the user's methodology |
| Partial MCP or SDK exists | **Extend** — use for infrastructure, fill gaps in the skill |
| Public skill covers the same domain | **Use for structural inspiration only** — public skills in competitive domains are generic by definition. The user's edge is their private SOP |
| Nothing public exists | **Build from scratch** — validate API access patterns work (auth, endpoints, proxy) before writing the full skill |
| Integration cost > build cost | **Build it** — a 2-hour custom implementation you own beats a "mature" tool with integration friction and upstream risk |

After research completes, present findings via **AskUserQuestion**:

```
Research complete for "[skill-name]". Here's what I found:

[1-2 sentence summary of what exists publicly]

RECOMMENDATION: [ADOPT / EXTEND / BUILD] because [one-line reason]

Options:
A) Adopt [tool/MCP X] for infrastructure, build methodology layer on top (Recommended)
B) Extend [partial tool Y] — use what works, fill gaps in the skill
C) Build from scratch — nothing found matches well enough
D) Show me the detailed findings before I decide
```

When in doubt, bias toward adopting mature infrastructure for the plumbing layer and building custom logic for the methodology layer — that's where the value lives.

### Interview and Research

Proactively ask questions about edge cases, input/output formats, example files, success criteria, and dependencies. Wait to write test prompts until you've got this part ironed out.

Check available MCPs - if useful for research (searching docs, finding similar skills, looking up best practices), research in parallel via subagents if available, otherwise inline. Come prepared with context to reduce burden on the user.

### Write the SKILL.md

Based on the user interview, fill in these components:

- **name**: Skill identifier
- **description**: When to trigger, what it does. This is the primary triggering mechanism - include both what the skill does AND specific contexts for when to use it. All "when to use" info goes here, not in the body. Note: currently Claude has a tendency to "undertrigger" skills -- to not use them when they'd be useful. To combat this, please make the skill descriptions a little bit "pushy". So for instance, instead of "How to build a simple fast dashboard to display internal Anthropic data.", you might write "How to build a simple fast dashboard to display internal Anthropic data. Make sure to use this skill whenever the user mentions dashboards, data visualization, internal metrics, or wants to display any kind of company data, even if they don't explicitly ask for a 'dashboard.'"
- **compatibility**: Required tools, dependencies (optional, rarely needed)
- **the rest of the skill :)**

### Skill Writing Guide

#### Anatomy of a Skill

```
skill-name/
├── SKILL.md (required)
│   ├── YAML frontmatter (name, description required)
│   └── Markdown instructions
└── Bundled Resources (optional)
    ├── scripts/    - Executable code for deterministic/repetitive tasks
    ├── references/ - Docs loaded into context as needed
    └── assets/     - Files used in output (templates, icons, fonts)
```

#### YAML Frontmatter Reference

All frontmatter fields except `description` are optional. Configure skill behavior using these fields between `---` markers:

```yaml
---
name: my-skill
description: What this skill does and when to use it. Use when...
context: fork
agent: general-purpose
argument-hint: [topic]
---
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | No | Display name for the skill. If omitted, uses the directory name. Lowercase letters, numbers, and hyphens only (max 64 characters). |
| `description` | Recommended | What the skill does and when to use it. Claude uses this to decide when to apply the skill. If omitted, uses the first paragraph of markdown content. |
| `context` | No | **Set to `fork` to run in a forked subagent context.** See "Inline vs Fork: Critical Decision" below — choosing wrong breaks your skill. |
| `agent` | No | Which subagent type to use when `context: fork` is set. Options: `Explore`, `Plan`, `general-purpose`, or custom agents from `.claude/agents/`. Default: `general-purpose`. |
| `disable-model-invocation` | No | Set to `true` to prevent Claude from automatically loading this skill. Use for workflows you want to trigger manually with `/name`. Default: `false`. |
| `user-invocable` | No | Set to `false` to hide from the `/` menu. Use for background knowledge users shouldn't invoke directly. Default: `true`. |
| `allowed-tools` | No | Pre-approved tools list. **Recommendation: Do NOT set this field.** Omitting it gives the skill full tool access governed by the user's permission settings. Setting it restricts the skill's capabilities unnecessarily. |
| `model` | No | Model to use when this skill is active. |
| `argument-hint` | No | Hint shown during autocomplete to indicate expected arguments. Example: `[issue-number]` or `[filename] [format]`. |
| `hooks` | No | Hooks scoped to this skill's lifecycle. Example: `hooks: { pre-invoke: [{ command: "echo Starting" }] }`. See Claude Code Hooks documentation. |

**Special placeholder:** `$ARGUMENTS` in skill content is replaced with text the user provides after the skill name. For example, `/deep-research quantum computing` replaces `$ARGUMENTS` with `quantum computing`.

##### Inline vs Fork: Critical Decision

**This is the most important architectural decision when designing a skill.** Choosing wrong will silently break your skill's core capabilities.

**CRITICAL CONSTRAINT: Subagents cannot spawn other subagents.** A skill running with `context: fork` (as a subagent) CANNOT:
- Use the Task tool to spawn parallel exploration agents
- Use the Skill tool to invoke other skills
- Orchestrate any multi-agent workflow

**Decision guide:**

| Your skill needs to... | Use | Why |
|------------------------|-----|-----|
| Orchestrate parallel agents (Task tool) | **Inline** (no `context`) | Subagents can't spawn subagents |
| Call other skills (Skill tool) | **Inline** (no `context`) | Subagents can't invoke skills |
| Run Bash commands for external CLIs | **Inline** (no `context`) | Full tool access in main context |
| Perform a single focused task (research, analysis) | **Fork** (`context: fork`) | Isolated context, clean execution |
| Provide reference knowledge (coding conventions) | **Inline** (no `context`) | Guidelines enrich main conversation |
| Be callable BY other skills | **Fork** (`context: fork`) | Must be a subagent to be spawned |

**Example: Orchestrator skill (MUST be inline):**
```yaml
---
name: product-analysis
description: Multi-path parallel product analysis with cross-model synthesis
---

# Orchestrates parallel agents — inline is REQUIRED
1. Auto-detect available tools (which codex, etc.)
2. Launch 3-5 Task agents in parallel (Explore subagents)
3. Optionally invoke /competitors-analysis via Skill tool
4. Synthesize all results
```

**Example: Specialist skill (fork is correct):**
```yaml
---
name: deep-research
description: Research a topic thoroughly using multiple sources
context: fork
agent: Explore
---

Research $ARGUMENTS thoroughly:
1. Find relevant files using Glob and Grep
2. Read and analyze the code
3. Summarize findings with specific file references
```

**Example: Reference skill (inline, no task):**
```yaml
---
name: api-conventions
description: API design patterns for this codebase
---

When writing API endpoints:
- Use RESTful naming conventions
- Return consistent error formats
```

##### Composable Skill Design (Orthogonality)

Skills should be **orthogonal**: each skill handles one concern, and they combine through composition.

**Pattern: Orchestrator (inline) calls Specialist (fork)**
```
product-analysis (inline, orchestrator)
  ├─ Task agents for parallel exploration
  ├─ Skill('competitors-analysis', 'X') → fork subagent
  └─ Synthesizes all results

competitors-analysis (fork, specialist)
  └─ Single focused task: analyze one competitor codebase
```

**Rules for composability:**
1. The **caller** must be inline (no `context: fork`) to use Task/Skill tools
2. The **callee** should use `context: fork` to run in isolated subagent context
3. Each skill has a single responsibility — don't mix orchestration with execution
4. Share methodology via references (e.g., checklists, templates), not by duplicating code

##### Pipeline Handoff (Sequential Skill Chaining)

Beyond orchestrator/specialist composition, skills often form **sequential pipelines** where one skill's output is the next skill's input. Each skill should proactively suggest the logical next step after completing its work.

**Pattern: "Next Step" section at the end of SKILL.md**

```markdown
## Next Step: [Action Description]

After [this skill completes], suggest the natural next skill:

\```
[Summary of what was just accomplished].

Options:
A) [Next skill] — [one-line reason] (Recommended)
B) [Alternative skill] — [when this is better]
C) No thanks — [the current output is sufficient]
\```
```

**Real-world pipeline examples:**

```
youtube-downloader → asr-transcribe-to-text → transcript-fixer → meeting-minutes-taker → pdf-creator
deep-research → fact-checker → ppt-creator
doc-to-markdown → docs-cleaner
claude-code-history-files-finder → continue-claude-work
```

**Rules for pipeline handoff:**
1. Every handoff is **opt-in** via AskUserQuestion — never auto-invoke the next skill without asking
2. Suggest only when the output naturally feeds into another skill — don't force connections
3. Include a "No thanks" option — the user may not need the full pipeline
4. The suggestion should explain **why** the next step helps (e.g., "ASR output typically contains recognition errors")
5. Keep it to 1-2 recommendations max — too many choices cause decision fatigue

**When to add a handoff:** Ask "does this skill's output commonly become another skill's input?" If yes, add a "Next Step" section. If the connection is rare or forced, don't add one.

**Anti-pattern:** Chaining skills that don't share a natural data flow. `pdf-creator → youtube-downloader` makes no sense. The pipeline must follow the user's actual workflow.

##### Auto-Detection Over Manual Flags

**Never add manual flags for capabilities that can be auto-detected.** Instead of requiring users to pass `--with-codex` or `--verbose`, detect capabilities at runtime:

```
# Good: Auto-detect and inform
Step 0: Check available tools
  - `which codex` → If found, inform user and enable cross-model analysis
  - `ls package.json` → If found, tailor prompts for Node.js project
  - `which docker` → If found, enable container-based execution

# Bad: Manual flags
argument-hint: [scope] [--with-codex] [--docker] [--verbose]
```

**Principle:** Capabilities auto-detect, user decides scope. A skill should discover what it CAN do and act accordingly, not require users to remember what tools are installed.

##### Invocation Control

| Frontmatter | You can invoke | Claude can invoke | Subagents can use |
|-------------|----------------|-------------------|-------------------|
| (default) | Yes | Yes | No (runs inline) |
| `context: fork` | Yes | Yes | Yes |
| `disable-model-invocation: true` | Yes | No | No |
| `context: fork` + `disable-model-invocation: true` | Yes | No | Yes (when explicitly delegated) |

#### Progressive Disclosure

Skills use a three-level loading system:
1. **Metadata** (name + description) - Always in context (~100 words)
2. **SKILL.md body** - In context whenever skill triggers
3. **Bundled resources** - As needed (unlimited, scripts can execute without loading)

**Key patterns:**
- SKILL.md length should be driven by **information density**, not a line count target. A 600-line skill with no filler is better than a 200-line skill that omits critical knowledge and forces the model to guess. If the skill is getting long, ask: "Is every section earning its keep?" If yes, keep it. If sections are padded or explain things Claude already knows, trim those — not the useful content. When a skill genuinely covers many domains, split into references by domain rather than artificially cramming everything into a short main file.
- Reference files clearly from SKILL.md with guidance on when to read them
- For large reference files (>300 lines), include a table of contents

**Domain organization**: When a skill supports multiple domains/frameworks, organize by variant:
```
cloud-deploy/
├── SKILL.md (workflow + selection)
└── references/
    ├── aws.md
    ├── gcp.md
    └── azure.md
```
Claude reads only the relevant reference file.

#### Principle of Lack of Surprise

This goes without saying, but skills must not contain malware, exploit code, or any content that could compromise system security. A skill's contents should not surprise the user in their intent if described. Don't go along with requests to create misleading skills or skills designed to facilitate unauthorized access, data exfiltration, or other malicious activities. Things like a "roleplay as an XYZ" are OK though.

#### Writing Patterns

Prefer using the imperative form in instructions.

**Defining output formats** - You can do it like this:
```markdown
## Report structure
ALWAYS use this exact template:
# [Title]
## Executive summary
## Key findings
## Recommendations
```

**Examples pattern** - It's useful to include examples. You can format them like this (but if "Input" and "Output" are in the examples you might want to deviate a little):
```markdown
## Commit message format
**Example 1:**
Input: Added user authentication with JWT tokens
Output: feat(auth): implement JWT-based authentication
```

### Writing Style

Try to explain to the model why things are important in lieu of heavy-handed musty MUSTs. Use theory of mind and try to make the skill general and not super-narrow to specific examples. Start by writing a draft and then look at it with fresh eyes and improve it.

### Dates and Version References

**Keep factual dates — they tell readers when information was verified.** A skill about Suno v5.5 should say "Suno v5.5 (March 2026)" because without the date, future readers can't judge if the information is still current. Removing dates makes things worse, not better.

What to avoid is **conditional logic based on dates** ("if before August 2025, use the old API") — that becomes wrong the moment the date passes and nobody updates it.

Rules:
- **Release dates, "last verified" dates**: Keep them. They're reference points, not expiration dates
- **Pricing, rankings, legal status**: Include but mark as volatile ("~$0.035/gen as of last check") so readers know to re-verify
- **"Before X date do Y, after X date do Z"**: Don't write this. Pick the current method and optionally document the old one in a collapsed/deprecated section

#### Bundled Resources

##### Scripts (`scripts/`)

Executable code (Python/Bash/etc.) for tasks that require deterministic reliability or are repeatedly rewritten.

- **When to include**: When the same code is being rewritten repeatedly or deterministic reliability is needed
- **Example**: `scripts/rotate_pdf.py` for PDF rotation tasks
- **Benefits**: Token efficient, deterministic, may be executed without loading into context
- **Note**: Scripts may still need to be read by Claude for patching or environment-specific adjustments

##### References (`references/`)

Documentation and reference material intended to be loaded as needed into context to inform Claude's process and thinking.

- **When to include**: For documentation that Claude should reference while working
- **Examples**: `references/finance.md` for financial schemas, `references/mnda.md` for company NDA template
- **Use cases**: Database schemas, API documentation, domain knowledge, company policies, detailed workflow guides
- **Benefits**: Keeps SKILL.md lean, loaded only when Claude determines it's needed
- **Best practice**: If files are large (>10k words), include grep search patterns in SKILL.md
- **Avoid duplication**: Information should live in either SKILL.md or references files, not both

##### Assets (`assets/`)

Files not intended to be loaded into context, but rather used within the output Claude produces.

- **When to include**: When the skill needs files that will be used in the final output
- **Examples**: `assets/logo.png` for brand assets, `assets/slides.pptx` for PowerPoint templates
- **Use cases**: Templates, images, icons, boilerplate code, fonts, sample documents

##### Privacy and Path References

**CRITICAL**: Skills intended for public distribution must not contain user-specific or company-specific information:

- **Forbidden**: Absolute paths to user directories (`/home/username/`, `/Users/username/`)
- **Forbidden**: Personal usernames, company names, product names
- **Forbidden**: Hardcoded skill installation paths like `~/.claude/skills/`
- **Allowed**: Relative paths within the skill bundle (`scripts/example.py`, `references/guide.md`)
- **Allowed**: Standard placeholders (`~/workspace/project`, `username`, `your-company`)

##### Versioning

**CRITICAL**: Skills should NOT contain version history or version numbers in SKILL.md:

- **Forbidden**: Version sections (`## Version`, `## Changelog`) in SKILL.md
- **Correct location**: Skill versions are tracked in marketplace.json under `plugins[].version`
- **Rationale**: Marketplace infrastructure manages versioning; SKILL.md should be timeless content

#### Reference File Naming

Filenames must be self-explanatory without reading contents.

**Pattern**: `<content-type>_<specificity>.md`

**Examples**:
- Bad: `commands.md`, `cli_usage.md`, `reference.md`
- Good: `script_parameters.md`, `api_endpoints.md`, `database_schema.md`

**Test**: Can someone understand the file's contents from the name alone?

### Skill Creation Best Practice

Anthropic has wrote skill authoring best practices, you SHOULD retrieve it before you create or update any skills, the link is https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices.md

#### Development Methodology Reference

Also read [references/skill-development-methodology.md](references/skill-development-methodology.md) before starting — it covers the full 8-phase development process with prior art research, counter review, and real failure case studies. The two references are complementary: the Anthropic doc covers principles, the methodology covers process.

### Test Cases

After writing the skill draft, come up with 2-3 realistic test prompts — the kind of thing a real user would actually say. Present them via **AskUserQuestion**:

```
Skill draft is ready. Here are [N] test cases I'd like to run:

1. "[test prompt 1]" — tests [what aspect]
2. "[test prompt 2]" — tests [what aspect]
3. "[test prompt 3]" — tests [what aspect]

Each test runs the skill + a baseline (no skill) for comparison.
Estimated time: ~[X] minutes total.

RECOMMENDATION: Run all [N] test cases now.

Options:
A) Run all test cases (Recommended)
B) Run test cases, but let me modify them first
C) Add more test cases before running
D) Skip testing — the skill looks good enough to ship
```

Save test cases to `evals/evals.json`. Don't write assertions yet — just the prompts. You'll draft assertions in the next step while the runs are in progress.

```json
{
  "skill_name": "example-skill",
  "evals": [
    {
      "id": 1,
      "prompt": "User's task prompt",
      "expected_output": "Description of expected result",
      "files": []
    }
  ]
}
```

See `references/schemas.md` for the full schema (including the `assertions` field, which you'll add later).

## Running and evaluating test cases

This section is one continuous sequence — don't stop partway through. Do NOT use `/skill-test` or any other testing skill.

Put results in `<skill-name>-workspace/` as a sibling to the skill directory. Within the workspace, organize results by iteration (`iteration-1/`, `iteration-2/`, etc.) and within that, each test case gets a directory (`eval-0/`, `eval-1/`, etc.). Don't create all of this upfront — just create directories as you go.

### Step 1: Spawn all runs (with-skill AND baseline) in the same turn

For each test case, spawn two subagents in the same turn — one with the skill, one without. This is important: don't spawn the with-skill runs first and then come back for baselines later. Launch everything at once so it all finishes around the same time.

**With-skill run:**

```
Execute this task:
- Skill path: <path-to-skill>
- Task: <eval prompt>
- Input files: <eval files if any, or "none">
- Save outputs to: <workspace>/iteration-<N>/eval-<ID>/with_skill/outputs/
- Outputs to save: <what the user cares about — e.g., "the .docx file", "the final CSV">
```

**Baseline run** (same prompt, but the baseline depends on context):
- **Creating a new skill**: no skill at all. Same prompt, no skill path, save to `without_skill/outputs/`.
- **Improving an existing skill**: the old version. Before editing, snapshot the skill (`cp -r <skill-path> <workspace>/skill-snapshot/`), then point the baseline subagent at the snapshot. Save to `old_skill/outputs/`.

Write an `eval_metadata.json` for each test case (assertions can be empty for now). Give each eval a descriptive name based on what it's testing — not just "eval-0". Use this name for the directory too. If this iteration uses new or modified eval prompts, create these files for each new eval directory — don't assume they carry over from previous iterations.

```json
{
  "eval_id": 0,
  "eval_name": "descriptive-name-here",
  "prompt": "The user's task prompt",
  "assertions": []
}
```

### Step 2: While runs are in progress, draft assertions

Don't just wait for the runs to finish — you can use this time productively. Draft quantitative assertions for each test case and explain them to the user. If assertions already exist in `evals/evals.json`, review them and explain what they check.

Good assertions are objectively verifiable and have descriptive names — they should read clearly in the benchmark viewer so someone glancing at the results immediately understands what each one checks. Subjective skills (writing style, design quality) are better evaluated qualitatively — don't force assertions onto things that need human judgment.

Update the `eval_metadata.json` files and `evals/evals.json` with the assertions once drafted. Also explain to the user what they'll see in the viewer — both the qualitative outputs and the quantitative benchmark.

### Step 3: As runs complete, capture timing data

When each subagent task completes, you receive a notification containing `total_tokens` and `duration_ms`. Save this data immediately to `timing.json` in the run directory:

```json
{
  "total_tokens": 84852,
  "duration_ms": 23332,
  "total_duration_seconds": 23.3
}
```

This is the only opportunity to capture this data — it comes through the task notification and isn't persisted elsewhere. Process each notification as it arrives rather than trying to batch them.

### Step 4: Grade, aggregate, and launch the viewer

Once all runs are done:

1. **Grade each run** — spawn a grader subagent (or grade inline) that reads `agents/grader.md` and evaluates each assertion against the outputs. Save results to `grading.json` in each run directory. The grading.json expectations array must use the fields `text`, `passed`, and `evidence` (not `name`/`met`/`details` or other variants) — the viewer depends on these exact field names. For assertions that can be checked programmatically, write and run a script rather than eyeballing it — scripts are faster, more reliable, and can be reused across iterations.

2. **Aggregate into benchmark** — run the aggregation script from the skill-creator directory:
   ```bash
   python -m scripts.aggregate_benchmark <workspace>/iteration-N --skill-name <name>
   ```
   This produces `benchmark.json` and `benchmark.md` with pass_rate, time, and tokens for each configuration, with mean +/- stddev and the delta. If generating benchmark.json manually, see `references/schemas.md` for the exact schema the viewer expects.
Put each with_skill version before its baseline counterpart.

3. **Do an analyst pass** — read the benchmark data and surface patterns the aggregate stats might hide. See `agents/analyzer.md` (the "Analyzing Benchmark Results" section) for what to look for — things like assertions that always pass regardless of skill (non-discriminating), high-variance evals (possibly flaky), and time/token tradeoffs.

4. **Launch the viewer** with both qualitative outputs and quantitative data:
   ```bash
   nohup python <skill-creator-path>/eval-viewer/generate_review.py \
     <workspace>/iteration-N \
     --skill-name "my-skill" \
     --benchmark <workspace>/iteration-N/benchmark.json \
     > /dev/null 2>&1 &
   VIEWER_PID=$!
   ```
   For iteration 2+, also pass `--previous-workspace <workspace>/iteration-<N-1>`.

   **Cowork / headless environments:** If `webbrowser.open()` is not available or the environment has no display, use `--static <output_path>` to write a standalone HTML file instead of starting a server. Feedback will be downloaded as a `feedback.json` file when the user clicks "Submit All Reviews". After download, copy `feedback.json` into the workspace directory for the next iteration to pick up.

Note: please use generate_review.py to create the viewer; there's no need to write custom HTML.

5. **Tell the user** via **AskUserQuestion**:

```
Results are ready! I've opened the eval viewer in your browser.

- "Outputs" tab: click through each test case, leave feedback in the textbox
- "Benchmark" tab: quantitative comparison (pass rates, timing, tokens)

Take your time reviewing. When you're done, come back here.

Options:
A) I've finished reviewing — read my feedback and improve the skill
B) I have questions about the results before giving feedback
C) Results look good enough — skip iteration, let's package the skill
D) Results need major rework — let's discuss before iterating
```

### What the user sees in the viewer

The "Outputs" tab shows one test case at a time:
- **Prompt**: the task that was given
- **Output**: the files the skill produced, rendered inline where possible
- **Previous Output** (iteration 2+): collapsed section showing last iteration's output
- **Formal Grades** (if grading was run): collapsed section showing assertion pass/fail
- **Feedback**: a textbox that auto-saves as they type
- **Previous Feedback** (iteration 2+): their comments from last time, shown below the textbox

The "Benchmark" tab shows the stats summary: pass rates, timing, and token usage for each configuration, with per-eval breakdowns and analyst observations.

Navigation is via prev/next buttons or arrow keys. When done, they click "Submit All Reviews" which saves all feedback to `feedback.json`.

### Step 5: Read the feedback

When the user tells you they're done, read `feedback.json`:

```json
{
  "reviews": [
    {"run_id": "eval-0-with_skill", "feedback": "the chart is missing axis labels", "timestamp": "..."},
    {"run_id": "eval-1-with_skill", "feedback": "", "timestamp": "..."},
    {"run_id": "eval-2-with_skill", "feedback": "perfect, love this", "timestamp": "..."}
  ],
  "status": "complete"
}
```

Empty feedback means the user thought it was fine. Focus your improvements on the test cases where the user had specific complaints.

Kill the viewer server when you're done with it:

```bash
kill $VIEWER_PID 2>/dev/null
```

---

## Improving the skill

This is the heart of the loop. You've run the test cases, the user has reviewed the results, and now you need to make the skill better based on their feedback.

### How to think about improvements

1. **Generalize from the feedback.** The big picture thing that's happening here is that we're trying to create skills that can be used a million times (maybe literally, maybe even more who knows) across many different prompts. Here you and the user are iterating on only a few examples over and over again because it helps move faster. The user knows these examples in and out and it's quick for them to assess new outputs. But if the skill you and the user are codeveloping works only for those examples, it's useless. Rather than put in fiddly overfitty changes, or oppressively constrictive MUSTs, if there's some stubborn issue, you might try branching out and using different metaphors, or recommending different patterns of working. It's relatively cheap to try and maybe you'll land on something great.

2. **Keep the prompt lean.** Remove things that aren't pulling their weight. Make sure to read the transcripts, not just the final outputs — if it looks like the skill is making the model waste a bunch of time doing things that are unproductive, you can try getting rid of the parts of the skill that are making it do that and seeing what happens.

3. **Explain the why.** Try hard to explain the **why** behind everything you're asking the model to do. Today's LLMs are *smart*. They have good theory of mind and when given a good harness can go beyond rote instructions and really make things happen. Even if the feedback from the user is terse or frustrated, try to actually understand the task and why the user is writing what they wrote, and what they actually wrote, and then transmit this understanding into the instructions. If you find yourself writing ALWAYS or NEVER in all caps, or using super rigid structures, that's a yellow flag — if possible, reframe and explain the reasoning so that the model understands why the thing you're asking for is important. That's a more humane, powerful, and effective approach.

4. **Look for repeated work across test cases.** Read the transcripts from the test runs and notice if the subagents all independently wrote similar helper scripts or took the same multi-step approach to something. If all 3 test cases resulted in the subagent writing a `create_docx.py` or a `build_chart.py`, that's a strong signal the skill should bundle that script. Write it once, put it in `scripts/`, and tell the skill to use it. This saves every future invocation from reinventing the wheel.

This task is pretty important (we are trying to create billions a year in economic value here!) and your thinking time is not the blocker; take your time and really mull things over. I'd suggest writing a draft revision and then looking at it anew and making improvements. Really do your best to get into the head of the user and understand what they want and need.

After analyzing feedback, present your improvement plan via **AskUserQuestion**:

```
I've read the feedback from [N] test cases. [X] had specific complaints, [Y] looked good.

Key issues:
- [Issue 1]: [plain-language summary]
- [Issue 2]: [plain-language summary]

RECOMMENDATION: [strategy] because [reason]

Options:
A) Iterative refinement — targeted fixes for the specific issues above (Recommended)
B) Structural redesign — the core approach needs rethinking
C) Bundle a script — I noticed all test runs independently wrote similar code for [X]
D) Expand test set first — add [N] more test cases to avoid overfitting to these examples
```

### The iteration loop

After improving the skill:

1. Apply your improvements to the skill
2. Rerun all test cases into a new `iteration-<N+1>/` directory, including baseline runs. If you're creating a new skill, the baseline is always `without_skill` (no skill) — that stays the same across iterations. If you're improving an existing skill, use your judgment on what makes sense as the baseline: the original version the user came in with, or the previous iteration.
3. Launch the reviewer with `--previous-workspace` pointing at the previous iteration
4. Wait for the user to review and tell you they're done
5. Read the new feedback, improve again, repeat

At the end of each iteration, use **AskUserQuestion** as a checkpoint:

```
Iteration [N] complete. Results: [pass_rate]% assertions passing, [delta vs previous].

Options:
A) Continue iterating — I see more room for improvement
B) Accept this version — it's good enough, let's move to packaging
C) Revert to previous iteration — this round made things worse
D) Run blind comparison — rigorously compare this version vs the previous one
```

Keep going until:
- The user says they're happy
- The feedback is all empty (everything looks good)
- You're not making meaningful progress

---

## Advanced: Blind comparison

For situations where you want a more rigorous comparison between two versions of a skill (e.g., the user asks "is the new version actually better?"), there's a blind comparison system. Read `agents/comparator.md` and `agents/analyzer.md` for the details. The basic idea is: give two outputs to an independent agent without telling it which is which, and let it judge quality. Then analyze why the winner won.

This is optional, requires subagents, and most users won't need it. The human review loop is usually sufficient.

---

## Description Optimization

The description field in SKILL.md frontmatter is the primary mechanism that determines whether Claude invokes a skill. After creating or improving a skill, offer to optimize the description for better triggering accuracy.

### Step 1: Generate trigger eval queries

Create 20 eval queries — a mix of should-trigger and should-not-trigger. Save as JSON:

```json
[
  {"query": "the user prompt", "should_trigger": true},
  {"query": "another prompt", "should_trigger": false}
]
```

The queries must be realistic and something a Claude Code or Claude.ai user would actually type. Not abstract requests, but requests that are concrete and specific and have a good amount of detail. For instance, file paths, personal context about the user's job or situation, column names and values, company names, URLs. A little bit of backstory. Some might be in lowercase or contain abbreviations or typos or casual speech. Use a mix of different lengths, and focus on edge cases rather than making them clear-cut (the user will get a chance to sign off on them).

Bad: `"Format this data"`, `"Extract text from PDF"`, `"Create a chart"`

Good: `"ok so my boss just sent me this xlsx file (its in my downloads, called something like 'Q4 sales final FINAL v2.xlsx') and she wants me to add a column that shows the profit margin as a percentage. The revenue is in column C and costs are in column D i think"`

For the **should-trigger** queries (8-10), think about coverage. You want different phrasings of the same intent — some formal, some casual. Include cases where the user doesn't explicitly name the skill or file type but clearly needs it. Throw in some uncommon use cases and cases where this skill competes with another but should win.

For the **should-not-trigger** queries (8-10), the most valuable ones are the near-misses — queries that share keywords or concepts with the skill but actually need something different. Think adjacent domains, ambiguous phrasing where a naive keyword match would trigger but shouldn't, and cases where the query touches on something the skill does but in a context where another tool is more appropriate.

The key thing to avoid: don't make should-not-trigger queries obviously irrelevant. "Write a fibonacci function" as a negative test for a PDF skill is too easy — it doesn't test anything. The negative cases should be genuinely tricky.

### Step 2: Review with user

Present the eval set to the user for review using the HTML template:

1. Read the template from `assets/eval_review.html`
2. Replace the placeholders:
   - `__EVAL_DATA_PLACEHOLDER__` → the JSON array of eval items (no quotes around it — it's a JS variable assignment)
   - `__SKILL_NAME_PLACEHOLDER__` → the skill's name
   - `__SKILL_DESCRIPTION_PLACEHOLDER__` → the skill's current description
3. Write to a temp file (e.g., `/tmp/eval_review_<skill-name>.html`) and open it: `open /tmp/eval_review_<skill-name>.html`
4. The user can edit queries, toggle should-trigger, add/remove entries, then click "Export Eval Set"
5. The file downloads to `~/Downloads/eval_set.json` — check the Downloads folder for the most recent version in case there are multiple (e.g., `eval_set (1).json`)

This step matters — bad eval queries lead to bad descriptions.

### Step 3: Run the optimization loop

Tell the user: "This will take some time — I'll run the optimization loop in the background and check on it periodically."

Save the eval set to the workspace, then run in the background:

```bash
python -m scripts.run_loop \
  --eval-set <path-to-trigger-eval.json> \
  --skill-path <path-to-skill> \
  --model <model-id-powering-this-session> \
  --max-iterations 5 \
  --verbose
```

Use the model ID from your system prompt (the one powering the current session) so the triggering test matches what the user actually experiences.

While it runs, periodically tail the output to give the user updates on which iteration it's on and what the scores look like.

This handles the full optimization loop automatically. It splits the eval set into 60% train and 40% held-out test, evaluates the current description (running each query 3 times to get a reliable trigger rate), then calls Claude to propose improvements based on what failed. It re-evaluates each new description on both train and test, iterating up to 5 times. When it's done, it opens an HTML report in the browser showing the results per iteration and returns JSON with `best_description` — selected by test score rather than train score to avoid overfitting.

### How skill triggering works

Understanding the triggering mechanism helps design better eval queries. Skills appear in Claude's `available_skills` list with their name + description, and Claude decides whether to consult a skill based on that description. The important thing to know is that Claude only consults skills for tasks it can't easily handle on its own — simple, one-step queries like "read this PDF" may not trigger a skill even if the description matches perfectly, because Claude can handle them directly with basic tools. Complex, multi-step, or specialized queries reliably trigger skills when the description matches.

This means your eval queries should be substantive enough that Claude would actually benefit from consulting a skill. Simple queries like "read file X" are poor test cases — they won't trigger skills regardless of description quality.

### Step 4: Apply the result

Take `best_description` from the JSON output and update the skill's SKILL.md frontmatter. Show the user before/after and report the scores.

---

## CRITICAL: Edit Skills at Source Location

**NEVER edit skills in `~/.claude/plugins/cache/`** — that's a read-only cache directory. All changes there are:
- Lost when cache refreshes
- Not synced to source control
- Wasted effort requiring manual re-merge

**ALWAYS verify you're editing the source repository:**
```bash
# WRONG - cache location (read-only copy)
~/.claude/plugins/cache/daymade-skills/my-skill/1.0.0/my-skill/SKILL.md

# RIGHT - source repository
/path/to/your/claude-code-skills/my-skill/SKILL.md
```

**Before any edit**, confirm the file path does NOT contain `/cache/` or `/plugins/cache/`.

---

## Skill Creation Process (Step-by-Step)

When creating or updating a skill, follow these steps in order. Skip steps only when clearly not applicable.

### Step 0: Prerequisites Check

Before starting any skill work, auto-detect all dependencies and proactively install anything missing. Discovering a missing tool mid-workflow (e.g., gitleaks at packaging time, PyYAML at validation) wastes time and breaks flow.

Run the quick check from [references/prerequisites.md](references/prerequisites.md), auto-install what you can, and present the user a summary checklist. Only proceed when all blocking dependencies are satisfied.

Key blockers: Python 3, PyYAML (validation/packaging), gitleaks (security scan), claude CLI (evals). All scripts must be invoked via `python3 -m scripts.<name>` from the skill-creator root directory — direct `python3 scripts/<name>.py` fails due to relative imports.

### Step 1: Understanding the Skill with Concrete Examples

Skip this step only when the skill's usage patterns are already clearly understood.

To create an effective skill, clearly understand concrete examples of how the skill will be used. This understanding can come from either direct user examples or generated examples that are validated with user feedback.

For example, when building an image-editor skill, relevant questions include:

- "What functionality should the image-editor skill support? Editing, rotating, anything else?"
- "Can you give some examples of how this skill would be used?"
- "What would a user say that should trigger this skill?"

To avoid overwhelming users, avoid asking too many questions in a single message.

### Step 2: Planning the Reusable Skill Contents

Analyze each example by:

1. Considering how to execute on the example from scratch
2. Determining the appropriate level of freedom for Claude
3. Identifying what scripts, references, and assets would be helpful when executing these workflows repeatedly

**Match specificity to task risk:**
- **High freedom (text instructions)**: Multiple valid approaches exist
- **Medium freedom (pseudocode with parameters)**: Preferred patterns exist with acceptable variation
- **Low freedom (exact scripts)**: Operations are fragile, consistency critical

### Step 3: Initializing the Skill

Skip this step if the skill already exists.

When creating a new skill from scratch, always run the `init_skill.py` script:

```bash
scripts/init_skill.py <skill-name> --path <output-directory>
```

The script creates a template skill directory with proper frontmatter, resource directories, and example files.

### Step 4: Edit the Skill

When editing, remember that the skill is being created for another instance of Claude to use. Focus on information that would be beneficial and non-obvious to Claude.

**When updating an existing skill**: Scan all existing reference files to check if they need corresponding updates.

**Pipeline check**: Consider whether this skill's output naturally feeds into another skill. If so, add a "Next Step" handoff section (see "Pipeline Handoff" in the Skill Writing Guide). Also check if any existing skill should chain *into* this one.

### Step 5: Sanitization Review (Optional)

Use **AskUserQuestion** before executing this step:

```
This skill appears to contain content from a real project.
Before distribution, I should check for business-specific details
(company names, internal paths, product names) that shouldn't be public.

RECOMMENDATION: Run selective sanitization — review each finding before removing.

Options:
A) Full sanitization — automatically remove all business-specific content
B) Selective sanitization — show me each finding and let me decide (Recommended)
C) Skip — this is for internal use only, no sanitization needed
```

Skip if: skill was created from scratch for public use, user declines, or skill is for internal use.

**Sanitization process:**

1. **Load the checklist**: Read [references/sanitization_checklist.md](references/sanitization_checklist.md) for detailed guidance
2. **Run automated scans** to identify potential sensitive content
3. **Review and replace** each category (product names, person names, entity names, paths, jargon)
4. **Verify completeness**: Re-run patterns, read through skill, confirm functionality

### Step 6: Security Review

Before packaging or distributing a skill, run the security scanner to detect hardcoded secrets and personal information:

```bash
# Required before packaging
python scripts/security_scan.py <path/to/skill-folder>

# Verbose mode includes additional checks for paths, emails, and code patterns
python scripts/security_scan.py <path/to/skill-folder> --verbose
```

**Detection coverage:**
- Hardcoded secrets (API keys, passwords, tokens) via gitleaks
- Personal information (usernames, emails, company names) in verbose mode
- Unsafe code patterns (command injection risks) in verbose mode

**First-time setup:** Install gitleaks if not present:

```bash
# macOS
brew install gitleaks

# Linux/Windows - see script output for installation instructions
```

**Exit codes:**
- `0` - Clean (safe to package)
- `1` - High severity issues
- `2` - Critical issues (MUST fix before distribution)
- `3` - gitleaks not installed
- `4` - Scan error

**If issues are found**, present them via **AskUserQuestion**:

```
Security scan found [N] issues in "[skill-name]":
- [SEVERITY] [file]: [description]
- ...

RECOMMENDATION: Fix automatically — these look like [accidental leaks / false positives].

Options:
A) Fix all issues automatically (Recommended)
B) Review each finding — let me decide per-item (some may be intentional)
C) Override and proceed — I accept the risk for internal distribution
```

### Step 7: Packaging a Skill

Once the skill is ready, package it into a distributable file:

```bash
scripts/package_skill.py <path/to/skill-folder>
```

Optional output directory:

```bash
scripts/package_skill.py <path/to/skill-folder> ./dist
```

The packaging script will:

1. **Validate** the skill automatically (YAML frontmatter, naming conventions, path reference integrity)
2. **Verify security scan** (content hash must match last scan)
3. **Package** the skill into a distributable archive

If validation fails, the script reports errors and exits without creating a package.

### Step 8: Update Marketplace

After packaging, update the marketplace registry to include the new or updated skill.

**For new skills**, add an entry to `.claude-plugin/marketplace.json`:

```json
{
  "name": "skill-name",
  "description": "Copy from SKILL.md frontmatter description",
  "source": "./",
  "strict": false,
  "version": "1.0.0",
  "category": "developer-tools",
  "keywords": ["relevant", "keywords"],
  "skills": ["./skill-name"]
}
```

**For updated skills**, bump the version in `plugins[].version` following semver.

### Step 9: Ship or Iterate

After completing the skill, use **AskUserQuestion** to determine next steps:

```
Skill "[name]" is complete. Security scan passed, marketplace updated.

Options:
A) Package and export as .skill file for distribution
B) Run description optimization — improve auto-triggering accuracy (~5 min)
C) Expand test set and iterate more — add edge cases before shipping
D) Done for now — I'll test it manually and come back if needed
```

After testing the skill, users may request improvements. Often this happens right after using the skill, with fresh context of how the skill performed.

**Refinement filter:** Only add what solves observed problems. If best practices already cover it, don't duplicate.

---

### Package and Present (only if `present_files` tool is available)

Check whether you have access to the `present_files` tool. If you don't, skip this step. If you do, package the skill and present the .skill file to the user:

```bash
python -m scripts.package_skill <path/to/skill-folder>
```

After packaging, direct the user to the resulting `.skill` file path so they can install it.

---

## Claude.ai-specific instructions

In Claude.ai, the core workflow is the same (draft -> test -> review -> improve -> repeat), but because Claude.ai doesn't have subagents, some mechanics change. Here's what to adapt:

**Running test cases**: No subagents means no parallel execution. For each test case, read the skill's SKILL.md, then follow its instructions to accomplish the test prompt yourself. Do them one at a time. This is less rigorous than independent subagents (you wrote the skill and you're also running it, so you have full context), but it's a useful sanity check — and the human review step compensates. Skip the baseline runs — just use the skill to complete the task as requested.

**Reviewing results**: If you can't open a browser (e.g., Claude.ai's VM has no display, or you're on a remote server), skip the browser reviewer entirely. Instead, present results directly in the conversation. For each test case, show the prompt and the output. If the output is a file the user needs to see (like a .docx or .xlsx), save it to the filesystem and tell them where it is so they can download and inspect it. Ask for feedback inline: "How does this look? Anything you'd change?"

**Benchmarking**: Skip the quantitative benchmarking — it relies on baseline comparisons which aren't meaningful without subagents. Focus on qualitative feedback from the user.

**The iteration loop**: Same as before — improve the skill, rerun the test cases, ask for feedback — just without the browser reviewer in the middle. You can still organize results into iteration directories on the filesystem if you have one.

**Description optimization**: This section requires the `claude` CLI tool (specifically `claude -p`) which is only available in Claude Code. Skip it if you're on Claude.ai.

**Blind comparison**: Requires subagents. Skip it.

**Packaging**: The `package_skill.py` script works anywhere with Python and a filesystem. On Claude.ai, you can run it and the user can download the resulting `.skill` file.

- **Updating an existing skill**: The user might be asking you to update an existing skill, not create a new one. In this case:
  - **Preserve the original name.** Note the skill's directory name and `name` frontmatter field — use them unchanged. E.g., if the installed skill is `research-helper`, output `research-helper.skill` (not `research-helper-v2`).
  - **Copy to a writeable location before editing.** The installed skill path may be read-only. Copy to `/tmp/skill-name/`, edit there, and package from the copy.
  - **If packaging manually, stage in `/tmp/` first**, then copy to the output directory — direct writes may fail due to permissions.

---

## Cowork-Specific Instructions

If you're in Cowork, the main things to know are:

- You have subagents, so the main workflow (spawn test cases in parallel, run baselines, grade, etc.) all works. (However, if you run into severe problems with timeouts, it's OK to run the test prompts in series rather than parallel.)
- You don't have a browser or display, so when generating the eval viewer, use `--static <output_path>` to write a standalone HTML file instead of starting a server. Then proffer a link that the user can click to open the HTML in their browser.
- For whatever reason, the Cowork setup seems to disincline Claude from generating the eval viewer after running the tests, so just to reiterate: whether you're in Cowork or in Claude Code, after running tests, you should always generate the eval viewer for the human to look at examples before revising the skill yourself and trying to make corrections, using `generate_review.py` (not writing your own boutique html code). Sorry in advance but I'm gonna go all caps here: GENERATE THE EVAL VIEWER *BEFORE* evaluating inputs yourself. You want to get them in front of the human ASAP!
- Feedback works differently: since there's no running server, the viewer's "Submit All Reviews" button will download `feedback.json` as a file. You can then read it from there (you may have to request access first).
- Packaging works — `package_skill.py` just needs Python and a filesystem.
- Description optimization (`run_loop.py` / `run_eval.py`) should work in Cowork just fine since it uses `claude -p` via subprocess, not a browser, but please save it until you've fully finished making the skill and the user agrees it's in good shape.
- **Updating an existing skill**: The user might be asking you to update an existing skill, not create a new one. Follow the update guidance in the claude.ai section above.

---

## Reference files

The agents/ directory contains instructions for specialized subagents. Read them when you need to spawn the relevant subagent.

- `agents/grader.md` — How to evaluate assertions against outputs
- `agents/comparator.md` — How to do blind A/B comparison between two outputs
- `agents/analyzer.md` — How to analyze why one version beat another

The references/ directory has additional documentation:
- `references/schemas.md` — JSON structures for evals.json, grading.json, benchmark.json, etc.
- `references/sanitization_checklist.md` — Checklist for sanitizing business-specific content before public distribution

---

Repeating one more time the core loop here for emphasis:

- Figure out what the skill is about
- Draft or edit the skill
- Run claude-with-access-to-the-skill on test prompts
- With the user, evaluate the outputs:
  - Create benchmark.json and run `eval-viewer/generate_review.py` to help the user review them
  - Run quantitative evals
- Repeat until you and the user are satisfied
- Package the final skill and return it to the user.

Please add steps to your TodoList, if you have such a thing, to make sure you don't forget. If you're in Cowork, please specifically put "Create evals JSON and run `eval-viewer/generate_review.py` so human can review test cases" in your TodoList to make sure it happens.

Good luck!
