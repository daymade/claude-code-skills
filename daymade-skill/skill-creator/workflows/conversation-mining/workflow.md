# Conversation-Mining Workflow

A retrospective distillation workflow for turning explicitly approved local Claude Code / Codex history files into a skill's `references/`.

Use this only when the user explicitly asks to read local/past conversation history or names prior sessions as source material, for example:

- "mine my chat history for the patterns we just figured out"
- "turn my earlier sessions into a skill reference"
- "distill what we learned in my earlier sessions into the skill"
- "enrich <skill> from my recent transcripts"

It is **not** a generic skill-creation flow and is not implied by a long live conversation. When the relevant evidence is already in the current context, use the normal existing-skill update path without history discovery, chunking, or mining agents. After an explicitly requested mining run completes, return to the normal skill-creator steps (edit `SKILL.md`, validate, scan, package).

## Prerequisites

- The target skill exists and has a valid `SKILL.md`.
- You can read local conversation history files (`~/.claude/projects/...`, `~/.claude/history.jsonl`, `~/.codex/...`).
- The user is okay with you reading their local transcripts. If they hesitate, stop and use the manual fallback in `patterns.md`.

## Step 1: Confirm the target skill and topic

Infer the target skill/topic when unambiguous, but obtain explicit user scope for the history sources:

1. Which skill should receive the mined knowledge?
2. What topic / knowledge gap are we mining for? (e.g., "API cost control", "Debian packaging pitfalls", "Astro SSR edge cases")
3. Which local sessions are in scope? (project name or time window)
4. Any sources that are **out of scope**? (private conversations, unrelated projects)

Write the answers into a local-only `conversation_history_manifest.json` for
this run. Use the bundled example as a template, but never commit a real run
manifest: it contains local transcript locations. Put it outside the
repository or below the target skill's `.enrich/` directory.

## Step 2: Discover sources

Run the discovery phase:

```bash
uv run --with PyYAML --with tiktoken python -m scripts.mine_conversation \
  --manifest <manifest.json> \
  --discover-only \
  --output <target-skill>/.enrich/<timestamp>
```

This hashes and inventories the declared files without parsing message bodies.
It produces opaque source IDs, source types, byte sizes, SHA-256 values, the
target/topic configuration, and the configured message time window. Redaction
counts and token totals are available only after Step 3 actually parses the
messages.

Review the discovery output. If too many files are selected, narrow the manifest's `since`/`until` or keywords. If too few, broaden them.

## Step 3: Clean, redact, and chunk

Run the preparation phase:

```bash
uv run --with PyYAML --with tiktoken python -m scripts.mine_conversation \
  --manifest <manifest.json> \
  --output <target-skill>/.enrich/<timestamp>
```

This writes:

```
<target-skill>/.enrich/<timestamp>/
├── manifest.json
├── redaction_report.json
├── chunks/
│   ├── chunk-000.json
│   ├── chunk-001.json
│   └── ...
└── logs/
    └── mine.log
```

### What happens inside the script

1. **Parse**: reads each JSONL file and extracts role=user / role=assistant messages.
2. **Filter**: drops system/injection noise (skill listings, tool listings, permission-mode events).
3. **Redact**: replaces secrets, tokens, emails, paths, and high-entropy identifiers.
4. **Score**: computes a simple relevance score against the topic keywords.
5. **Chunk**: partitions the remaining messages into token-sized chunks.
6. **Emit**: writes each chunk as a JSON file with metadata (`source` as an opaque ID, `source_line`, `messages`, `relevance_score`). Local source paths are never persisted.

## Step 4: Select the minimum mining pass

The available prompt types are a menu, not a mandatory agent package. Inspect the redacted manifest and chunk count before choosing any agent:

- For one or two small chunks and one bounded topic, read the **redacted** chunk in the main context and produce the candidate outline inline. Default agent count: zero.
- If one specialist view is genuinely useful, choose the single matching prompt below.
- Add another role only when it owns a distinct output that the first pass cannot produce. Do not split one coherent question across roles merely because templates exist.
- Multi-role fan-out requires the main SKILL.md heavy-eval/agent-budget gate. A request to "optimize a skill" is not authorization.

Role count and execution-unit count are different. One selected role may emit one prompt per chunk; those same-role prompts are necessary corpus shards, not new specialist roles. Process shards serially by default. If bounded concurrency is useful, first state the exact shard count, maximum concurrent units, and why recombining them would exceed the declared chunk budget. Same-role sharding never justifies adding another role.

Use the prompts in `workflows/conversation-mining/patterns.md`:

- `patterns` → `candidates/patterns/chunk-000.md`
- `war-stories` → `candidates/war-stories/chunk-000.md`
- `query-guide` → `candidates/query-guide/chunk-000.md`
- `usage-patterns` → `candidates/usage-patterns/chunk-000.md`
- `code-assets` → `candidates/code-assets/chunk-000.md`

Each selected agent prompt should include the redacted chunk text. The agent returns markdown.

The first four prompts mine **knowledge** (destined for `references/`). Use
`code-assets` only when the redacted source actually contains reusable code the
session had to write; do not launch it as an empty precaution. A main-context
inline pass must still ask the code-assets question once, then record "none"
when no recurring helper exists.

A helper script generates one prompt file per chunk per agent:

```bash
uv run python workflows/conversation-mining/scripts/init_conversation_mining.py \
  --enrich-dir <target-skill>/.enrich/<timestamp> \
  --agent <selected-role> [<second-role-if-justified>]
```

This writes `candidates/<agent-name>/chunk-XXX.prompt.md` files and a `manifest.json`
per agent. If the orchestrator is unavailable, run the agents manually using the
prompts in `patterns.md` and save each output as `chunk-XXX.md` beside the prompt.

## Step 5: Synthesize only when there is something to merge

If two or more knowledge-mining outputs exist, generate the writer prompt:

```bash
uv run python workflows/conversation-mining/scripts/init_conversation_mining.py \
  --enrich-dir <target-skill>/.enrich/<timestamp> \
  --synthesize
```

This command excludes `code-assets/` and writes a prompt for one writer agent:

```
<target-skill>/.enrich/<timestamp>/candidates/synthesize.prompt.md
```

Run that prompt through one writer agent only when the outputs materially
overlap or contradict. Otherwise merge them in the main context. When Step 4
already produced one inline outline, skip the writer entirely and save it as
`candidates/synthesized_outline.md`. The outline follows
`references/reference_template.md` but does not yet include frontmatter.

## Step 6: Review and sanitize

This is the most important gate. Read the synthesized outline and then read every candidate output. Ask the semantic question from `references/sanitization_checklist.md`:

> "Does this read like a generic placeholder or a public entity, or like it was lifted from a real project / person / transcript?"

Replace anything in the second category. Pay special attention to:

- Project and product codenames
- Person names (including CJK names)
- Private instance nicknames (CJK pet names are invisible to scanners)
- Business-specific entity names and field names
- Internal folder structures and absolute paths
- Verbatim spoken lines from a transcript

Run the automated scan as a secondary check:

```bash
uv run --with PyYAML python -m scripts.security_scan <target-skill> --verbose
```

A green scan does **not** mean the content is clean. The manual read-through is the real gate.

## Step 7: Promote the candidate to `references/`

Once the outline is clean, create the real reference file:

1. Choose a unique kebab-case `name:` for the frontmatter.
2. Copy the sanitized outline into `references/<name>.md`.
3. Add a `description:` and the rest of the frontmatter.
4. Update the `相关文件` section with real cross-links to other references in the skill.
5. Run validation:
   ```bash
   uv run --with PyYAML python -m scripts.quick_validate <target-skill>
   uv run --with PyYAML python -m scripts.security_scan <target-skill>
   uv run --with PyYAML python -m scripts.check_references --skill <target-skill> --enrich <target-skill>/.enrich/<timestamp>
   ```

If any gate fails, fix the candidate in `.enrich/` and re-promote. Do not commit a partially clean file.

**Promoting `code-assets` candidates** goes to `scripts/`, not `references/`:
take each surviving candidate's final code, apply its Parameterization notes
(hardcoded values → arguments), save as `scripts/<name>`, and syntax-check it
(`uv run python -m py_compile` / `node --check` / a no-arg dry run). Then point the
docs at the script instead of restating its logic — scripts carry the
execution, docs carry the understanding. The same sanitization gate applies:
re-read the code for private values; a green scanner is not a pass.

## Step 8: Update `SKILL.md`

The mined knowledge is only useful if the skill knows to load it. Add a section to `SKILL.md` that points to the new reference file and explains when to read it. Keep it short.

Example:

```markdown
## Conversation-Mined Knowledge

This skill also includes patterns distilled from real debugging sessions:

- `references/service-usage-patterns.md` — architecture and operational patterns
- `references/service-war-stories.md` — failures and lessons learned
- `references/service-query-guide.md` — common question → answer paths
```

Run `quick_validate` again after the edit.

## Verification

After the workflow completes, the following must be true:

- [ ] The `.enrich/` directory exists and is reproducible from the manifest and source hashes.
- [ ] `.enrich/.gitignore` contains `*`, and neither `.enrich/` nor root `tests/` appears in the packaged archive.
- [ ] The redaction report lists every replacement made.
- [ ] No raw secrets, paths, or personal identifiers appear in the candidate files.
- [ ] The promoted reference file has valid YAML frontmatter.
- [ ] `quick_validate` passes on the target skill.
- [ ] `security_scan` passes on the target skill.
- [ ] `check_references` reports no broken internal links or severe overlaps.
- [ ] `SKILL.md` cross-references the new reference file.

## Common pitfalls

| Pitfall | Why it happens | Fix |
|---------|---------------|-----|
| Mining too broad a topic | Manifest keywords are too generic | Narrow keywords and add exclude_keywords |
| Promoting a verbatim line | Agent copies a real spoken example | Replace with generic summary |
| Overlap with existing reference | New file duplicates `service_cli.md` | Merge into existing file or split by domain |
| Missing `相关文件` | Hurts discoverability | Add cross-links before promotion |
| Giant assistant tool dumps | Chunker included 10k-line tool output | Lower `chunk_tokens` and truncate tool outputs |

## When not to use this workflow

- The conversation is mostly private (family, health, legal).
- The skill is brand-new and there is no prior conversation to mine.
- The user wants a fully automated skill from a single prompt. Use the generic skill-creation flow instead.
- The mined content would be better as a one-time note in `memory/` rather than a reusable reference file.
