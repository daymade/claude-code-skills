# Conversation-Mining Workflow — Architecture Contract

> Non-negotiable principles for distilling local Claude Code / Codex conversation histories into a skill's `references/`.

## 1. Source is local, immutable, and never modified

The workflow reads from the user's local machine only:

- Claude Code project sessions: `~/.claude/projects/<project-key>/*.jsonl`
- Claude Code command history: `~/.claude/history.jsonl` (declared in `claude_command_history`)
- Codex transcripts: `~/.codex/transcription-history.jsonl` (declared in `codex_transcripts`)
- Codex command history: `~/.codex/history.jsonl` (declared in `manual_exports`)
- Optional: user-provided transcript exports or session JSONL files (declared in `manual_exports`)

These sources are **read-only**. No script writes back to them, renames them, or marks them as processed.

## 2. Discover only through an explicit manifest

Conversations are high-signal but high-risk. The workflow does **not** scan all of `~/.claude/projects` automatically. Instead, a `conversation_history_manifest.json` declares:

- Which project keys / files are in scope
- Time window (optional `since` / `until`)
- Target skill directory
- Topic filter (keywords / regex) for relevance scoring
- Redaction allowlist (explicit placeholder values or prefixes only)

The bundled example manifest is version-controlled; each real run manifest is
local-only because it names private transcript locations. Keep run manifests
outside the repository or below the target skill's ignored `.enrich/`
directory. Never commit or package them. Relative source paths are resolved
from the run manifest's own directory, and every declared source must exist;
missing inputs fail before any output directory is created.

## 3. Redaction is mandatory before any snippet leaves the machine

Every extracted snippet is redacted before it is:

- Written to `.enrich/` artifacts
- Passed to a subagent
- Shown to the user as a candidate for promotion

Redaction targets:

- LLM provider keys: `sk-or-...`, `sk-ant-...`, `sk-kimi-...`, `sk-proj-...`, `sk-svcacct-...`, `sk-...` (generic)
- Bearer / Authorization tokens and cookies
- High-entropy API tokens in `Authorization` headers or query parameters
- Email addresses, phone numbers, Chinese mobile numbers
- Absolute user-profile paths on macOS, Linux, and Windows
- Project-specific private identifiers declared through `extra_patterns`

Redaction is **lossy but safe**: replace the value with a fixed placeholder (`<REDACTED-key>`, `<REDACTED-path>`, etc.). A redaction report is produced so the user can review what was replaced.

## 4. Partition by token budget, not by file count

Agent context windows are expensive. The engine partitions cleaned snippets into chunks that fit a budget:

- Default chunk size: 12,000 tokens (leaves headroom for the prompt and agent response)
- Long messages are split; short messages are merged to reduce overhead
- Each chunk preserves the original message sequence and timestamps
- A chunk manifest records which source files and line ranges contributed

`tiktoken` and the declared encoding are required. If either is unavailable or
invalid, the run fails before creating output; it never guesses a character-to-token ratio.

## 5. System-injection noise is dropped, not summarized

Claude Code and Codex transcripts contain low-signal attachment events:

- Skill listings (`type: attachment` with `skill_listing`)
- Tool listings (`agent_listing_delta`, `deferred_tools_delta`)
- Permission mode changes
- File-history snapshots that only contain system metadata

These are **dropped entirely**. The workflow only retains:

- `user` messages (role: user)
- `assistant` messages (role: assistant)
- High-value attachments that carry real content (pasted files, images with captions, tool outputs with user-facing results)

When in doubt, drop.

## 6. Candidate references are staged, not promoted automatically

The subagent mining output is written to `.enrich/<timestamp>/candidates/`. A candidate is **not** a real `references/` file until the user explicitly approves promotion. The user must review for:

- Business-specific leakage (project names, person names, private instance nicknames)
- Factual accuracy
- Overlap with existing references
- Scope fit (does it belong in this skill or another skill?)

Promotion is a deliberate manual copy with a fresh frontmatter name. The
helper never promotes candidates automatically.

## 7. Each promotion must pass the existing validation gates

Promoted references must:

- Follow the canonical reference file structure (`references/reference_template.md`)
- Pass `scripts/quick_validate.py` on the target skill
- Pass `scripts/security_scan.py` on the target skill
- Pass `scripts/check_references.py --skill <skill> --enrich <enrich-dir>` for link/duplicate/overlap checks

No exception. If a candidate fails, it goes back to the review queue, not to `references/`.

## 8. Mining agents are single-purpose, not multi-hop

Each mining agent is given one of these narrow tasks:

- **Mine patterns**: extract recurring patterns, rules, workflows, or code idioms
- **Mine war stories**: extract failures, fixes, and lessons learned
- **Mine query guide**: map common user questions to answers and checklists
- **Mine usage patterns**: extract architecture/operational patterns
- **Mine code assets**: extract code the session had to write (reusable helpers destined for `scripts/`, not `references/`)
- **Synthesize**: merge the knowledge outputs into a canonical reference file outline (code-assets candidates bypass synthesis and promote to `scripts/` directly)

Agents do not call tools. They receive a redacted chunk and produce structured markdown. The workflow orchestrates them via the skill-creator's normal subagent harness.

## 9. Reproducibility: every run is timestamped and hashable

Every enrichment run produces an artifact directory:

```
<target-skill>/.enrich/<timestamp>/
├── manifest.json          # config, sources, chunks, redaction summary
├── redaction_report.json
├── chunks/
│   ├── chunk-000.json
│   └── chunk-001.json
├── candidates/
│   └── <agent-name>/
└── logs/
    └── mine.log
```

The manifest includes an opaque source ID, file size, and SHA-256 for each
source at the time of mining. It never persists the local source path. The
`.enrich/` root is automatically ignored by Git, and both `.enrich/` and root
`tests/` are excluded from distribution packages.

## 10. Composability: the workflow layers on top of the generic skill flow

Conversation mining is a **specialized entry point**, not a replacement for the generic skill-creation flow. After mining completes, the user returns to:

- `SKILL.md` editing
- `references/` review
- `scripts/quick_validate.py` + `scripts/security_scan.py`
- Packaging and distribution

The mining workflow only answers: "What do my past conversations want this skill to know?"
