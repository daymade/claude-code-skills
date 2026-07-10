# Conversation-Mining Patterns

Copy-paste templates and agent prompts for the `conversation-mining` workflow.

## Agent prompt: mine patterns

```markdown
You are a knowledge-distillation editor. Read the redacted conversation snippets below and extract recurring patterns, rules, workflows, or code idioms that should live in a skill reference file.

Output rules:
- Use only generic examples. Replace any remaining project-specific names, person names, or instance nicknames with placeholders like `<project-name>` or `<instance>`.
- Do not quote the user verbatim unless the verbatim line is itself a reusable rule.
- Group findings under clear headings.
- Return a markdown outline suitable for a `references/` file. Do not write a full reference file with frontmatter yet.
- If a snippet contains no reusable patterns, say "NO_PATTERNS_FOUND".

Snippets:
{chunk_text}
```

## Agent prompt: mine war stories

```markdown
You are a post-mortem editor. Read the redacted conversation snippets and extract concrete failures, mistakes, or near-misses and the fix that was applied.

Output rules:
- Each war story must have: **Loss**, **What happened**, **Fix**, **Lesson**.
- Use generic placeholders for private names, projects, and instances.
- Do not include raw stack traces longer than 5 lines; summarize the root cause instead.
- If a snippet contains no failure/lesson, say "NO_WAR_STORIES_FOUND".

Snippets:
{chunk_text}
```

## Agent prompt: mine query guide

```markdown
You are a FAQ editor. Read the redacted conversation snippets and build a "Question → Answer → Gotcha" table for the most common questions the user or their team asked during the sessions.

Output rules:
- One question per row. Answers should be actionable and short.
- Mark any answer that is an inference or guess with `[inferred]`.
- Use generic placeholders for private names and projects.
- If a snippet contains no user questions, say "NO_QUERIES_FOUND".

Snippets:
{chunk_text}
```

## Agent prompt: mine usage patterns

```markdown
You are an architecture-pattern editor. Read the redacted conversation snippets and extract operational patterns, design decisions, or workflow conventions that emerged from the conversation.

Output rules:
- Each pattern should have: **Name**, **When to use**, **How it works**, **Consequences**.
- Use generic placeholders for private names, projects, and instances.
- Do not write code unless the pattern is specifically about a command/configuration snippet.
- If a snippet contains no patterns, say "NO_PATTERNS_FOUND".

Snippets:
{chunk_text}
```

## Agent prompt: mine code assets

```markdown
You are a tooling editor. Read the redacted conversation snippets and find code the session had to WRITE to get the job done — helper scripts, injected snippets, renderers, converters, query templates. Anything written once here will be rewritten by every future session, so it belongs in the skill's `scripts/` directory, not in prose.

Output rules:
- For each candidate: **Name** (proposed `scripts/` filename), **What it does** (one line), **Why it recurs** (what future invocations need it for), **Parameterization** (which hardcoded values must become arguments/placeholders), and the code itself in a fenced block.
- Reconstruct the final working version (apply the session's own fixes/edits), not the first draft.
- Replace private names, paths, ids, and project-specific values with placeholders — the code must be generic enough to publish in a public skill.
- Skip throwaway diagnostics that only made sense once (a one-off `ls` probe is not an asset; a JSON-to-markdown renderer is).
- These candidates are NOT reference material — flag them for `scripts/`, separate from the knowledge outline.
- If a snippet contains no reusable code, say "NO_CODE_ASSETS_FOUND".

Snippets:
{chunk_text}
```

## Agent prompt: synthesize reference outline

```markdown
You are a senior technical writer. You have received mining outputs from several subagents working over the same set of redacted conversation snippets.

Your job is to produce one canonical outline for a new `references/` file. The outline must:
- Merge duplicate findings.
- Remove contradictions by favoring the most recent or most specific source.
- Fit into the canonical reference file structure (frontmatter, H1, numbered sections, tables, code blocks, `相关文件` cross-links).
- Be generic enough to publish in a public skill.

Inputs:
{aggregated_mining_outputs}

Output only the outline, not the full prose. Use this format:

```
# Title
- H1 summary line
- Section 1: ...
- Section 2: ...
- Section 3: ...
- Related files: ...
```
```

## Redaction rules

Apply these in order. Replace each match with the corresponding placeholder.

| Pattern | Placeholder | Notes |
|---------|-------------|-------|
| `Bearer\s+[A-Za-z0-9_\-.]+` | `Bearer <REDACTED-token>` | Authorization headers and similar |
| `(sk-or-\|sk-ant-\|sk-kimi-\|sk-proj-\|sk-svcacct-\|sk-)[A-Za-z0-9_-]+` | `<REDACTED-key>` | LLM provider keys |
| `[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z\|a-z]{2,}` | `<REDACTED-email>` | Email addresses |
| `1[3-9]\d{9}` | `<REDACTED-phone>` | Chinese mobile numbers |
| `/Users/[A-Za-z][A-Za-z0-9_-]+/[^\s,;"'\)]*` | `/Users/<REDACTED-USER>/...` | macOS home paths |
| `/home/[A-Za-z][A-Za-z0-9_-]+/[^\s,;"'\)]*` | `/home/<REDACTED-USER>/...` | Linux home paths |
| `C:\\(?:Users)\\[A-Za-z][A-Za-z0-9_-]+\\[^\s,;"'\)]*` | `%USERPROFILE%\...` | Windows home paths |
| `(?i)(Authorization:\s*\|access[_-]?token\s*[:=]\s*\|api[_-]?key\s*[:=]\s*\|token\s*[:=]\s*)[A-Za-z0-9_\-.]+` | `$1<REDACTED-token>` | Header/key-value style tokens |

Use an allowlist only for explicit placeholder values or prefixes (for
example, `sk-example-*` or `your-token-here`). Never allow a value merely
because it contains a word such as `test`, `example`, or `redacted`.

## Candidate file naming convention

The bootstrap script writes one prompt file per chunk and waits for the agent
output beside it:

```
.enrich/<timestamp>/candidates/<agent-name>/
  ├── chunk-000.prompt.md   # input prompt for the agent
  ├── chunk-000.md          # agent output (created after running the agent)
  ├── chunk-001.prompt.md
  ├── chunk-001.md
  └── ...
```

The synthesize bootstrap first writes a writer prompt, and the writer's result
is then saved beside it:

```
.enrich/<timestamp>/candidates/synthesize.prompt.md
.enrich/<timestamp>/candidates/synthesized_outline.md
```

When a candidate is promoted to a real reference, choose a frontmatter `name:` that is:
- Kebab-case
- Unique within the skill's `references/` directory
- Descriptive of the file's domain, not the conversation it came from

Example: `service-usage-patterns`, not `project-session-notes-<date>`.

## Promoting a candidate

1. Copy the candidate markdown into a new file under `references/`.
2. Add the required YAML frontmatter from `references/reference_template.md`.
3. Replace any remaining private names, project names, or instance nicknames with placeholders.
4. Run the three validation gates:
   ```bash
   uv run --with PyYAML python -m scripts.quick_validate <skill-dir>
   python -m scripts.security_scan <skill-dir>
   uv run --with PyYAML python -m scripts.check_references --skill <skill-dir> --enrich <skill-dir>/.enrich/<timestamp>
   ```
5. Only after all gates pass, commit the new reference file.

## Manual fallback when agents are unavailable

If the subagent harness is not available, the human can:

1. Read `chunks/chunk-XXX.json` one at a time.
2. For each chunk, manually answer the five mining questions on scratch paper:
   - What reusable pattern is here?
   - What failure/lesson is here?
   - What question/answer pair is here?
   - What operational pattern is here?
   - What should definitely NOT be captured because it is too project-specific?
3. Aggregate the answers into a single markdown outline.
4. Follow the promotion steps above.
