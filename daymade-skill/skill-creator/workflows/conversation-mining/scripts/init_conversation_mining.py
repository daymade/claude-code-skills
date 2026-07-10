#!/usr/bin/env python3
"""
Bootstrap the subagent mining phase of the conversation-mining workflow.

Reads chunked, redacted conversation snippets from an enrich directory and
produces per-agent prompt files. Also supports a synthesize step that merges
per-agent outputs into one canonical outline.

Usage:
  python workflows/conversation-mining/scripts/init_conversation_mining.py \
      --enrich-dir <skill>/.enrich/<timestamp> \
      --agent patterns war-stories query-guide usage-patterns

  python workflows/conversation-mining/scripts/init_conversation_mining.py \
      --enrich-dir <skill>/.enrich/<timestamp> \
      --synthesize
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional


AGENT_PROMPTS = {
    "patterns": """You are a knowledge-distillation editor. Read the redacted conversation snippets below and extract recurring patterns, rules, workflows, or code idioms that should live in a skill reference file.

Output rules:
- Use only generic examples. Replace any remaining project-specific names, person names, or instance nicknames with placeholders like `<project-name>` or `<instance>`.
- Do not quote the user verbatim unless the verbatim line is itself a reusable rule.
- Group findings under clear headings.
- Return a markdown outline suitable for a `references/` file. Do not write a full reference file with frontmatter yet.
- If a snippet contains no reusable patterns, say "NO_PATTERNS_FOUND".
""",
    "war-stories": """You are a post-mortem editor. Read the redacted conversation snippets and extract concrete failures, mistakes, or near-misses and the fix that was applied.

Output rules:
- Each war story must have: **Loss**, **What happened**, **Fix**, **Lesson**.
- Use generic placeholders for private names, projects, and instances.
- Do not include raw stack traces longer than 5 lines; summarize the root cause instead.
- If a snippet contains no failure/lesson, say "NO_WAR_STORIES_FOUND".
""",
    "query-guide": """You are a FAQ editor. Read the redacted conversation snippets and build a "Question → Answer → Gotcha" table for the most common questions the user or their team asked during the sessions.

Output rules:
- One question per row. Answers should be actionable and short.
- Mark any answer that is an inference or guess with `[inferred]`.
- Use generic placeholders for private names and projects.
- If a snippet contains no user questions, say "NO_QUERIES_FOUND".
""",
    "usage-patterns": """You are an architecture-pattern editor. Read the redacted conversation snippets and extract operational patterns, design decisions, or workflow conventions that emerged from the conversation.

Output rules:
- Each pattern should have: **Name**, **When to use**, **How it works**, **Consequences**.
- Use generic placeholders for private names, projects, and instances.
- Do not write code unless the pattern is specifically about a command/configuration snippet.
- If a snippet contains no patterns, say "NO_PATTERNS_FOUND".
""",
    "code-assets": """You are a tooling editor. Read the redacted conversation snippets and find code the session had to WRITE to get the job done — helper scripts, injected snippets, renderers, converters, query templates. Anything written once here will be rewritten by every future session, so it belongs in the skill's `scripts/` directory, not in prose.

Output rules:
- For each candidate: **Name** (proposed `scripts/` filename), **What it does** (one line), **Why it recurs** (what future invocations need it for), **Parameterization** (which hardcoded values must become arguments/placeholders), and the code itself in a fenced block.
- Reconstruct the final working version (apply the session's own fixes/edits), not the first draft.
- Replace private names, paths, ids, and project-specific values with placeholders — the code must be generic enough to publish in a public skill.
- Skip throwaway diagnostics that only made sense once (a one-off `ls` probe is not an asset; a JSON-to-markdown renderer is).
- These candidates are NOT reference material — flag them for `scripts/`, separate from the knowledge outline.
- If a snippet contains no reusable code, say "NO_CODE_ASSETS_FOUND".
""",
}

SYNTHESIZE_PROMPT = """You are a senior technical writer. You have received mining outputs from several subagents working over the same set of redacted conversation snippets.

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
"""


def _load_chunks(enrich_dir: Path) -> list[dict]:
    chunks_dir = enrich_dir / "chunks"
    if not chunks_dir.exists():
        return []
    chunks = []
    for path in sorted(chunks_dir.glob("chunk-*.json")):
        chunks.append(json.loads(path.read_text(encoding="utf-8")))
    return chunks


def _chunk_text(chunk: dict) -> str:
    parts = []
    for msg in chunk.get("messages", []):
        role = msg.get("role", "unknown")
        ts = msg.get("timestamp") or ""
        text = msg.get("text", "")
        parts.append(f"[{role}] {ts}\n{text}\n")
    return "\n".join(parts)


def _generate_agent_prompts(enrich_dir: Path, agents: list[str]) -> None:
    chunks = _load_chunks(enrich_dir)
    if not chunks:
        print("No chunks found. Run mine_conversation.py first.", file=sys.stderr)
        sys.exit(1)

    candidates_dir = enrich_dir / "candidates"
    candidates_dir.mkdir(parents=True, exist_ok=True)

    for agent_name in agents:
        if agent_name not in AGENT_PROMPTS:
            print(f"Unknown agent type: {agent_name}", file=sys.stderr)
            sys.exit(1)

        agent_dir = candidates_dir / agent_name
        agent_dir.mkdir(parents=True, exist_ok=True)
        prompt_header = AGENT_PROMPTS[agent_name]

        for idx, chunk in enumerate(chunks):
            prompt_file = agent_dir / f"chunk-{idx:03d}.prompt.md"
            body = prompt_header + "\n\nSnippets:\n\n" + _chunk_text(chunk)
            prompt_file.write_text(body, encoding="utf-8")

        # Write a manifest for orchestration
        manifest = {
            "agent": agent_name,
            "chunk_count": len(chunks),
            "prompt_files": [str(f.name) for f in sorted(agent_dir.glob("chunk-*.prompt.md"))],
        }
        (agent_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        print(f"Generated {len(chunks)} prompts for agent '{agent_name}' in {agent_dir}")


def _synthesize(enrich_dir: Path) -> None:
    candidates_dir = enrich_dir / "candidates"
    if not candidates_dir.exists():
        print("No candidates found. Generate agent prompts first.", file=sys.stderr)
        sys.exit(1)

    outputs: list[str] = []
    for agent_dir in sorted(candidates_dir.iterdir()):
        if not agent_dir.is_dir():
            continue
        if agent_dir.name == "code-assets":
            continue
        # Only consume .md outputs, not .prompt.md inputs
        for output_file in sorted(agent_dir.glob("chunk-*.md")):
            if output_file.name.endswith(".prompt.md"):
                continue
            outputs.append(f"\n---\n# Agent: {agent_dir.name} / {output_file.name}\n\n{output_file.read_text(encoding='utf-8')}")

    if not outputs:
        print("No agent outputs found. Run the agents against the .prompt.md files first.", file=sys.stderr)
        sys.exit(1)

    aggregated = "\n".join(outputs)
    synthesize_prompt = SYNTHESIZE_PROMPT.format(aggregated_mining_outputs=aggregated)

    prompt_file = candidates_dir / "synthesize.prompt.md"
    prompt_file.write_text(synthesize_prompt, encoding="utf-8")
    print(f"Synthesize prompt written to {prompt_file}")
    print("Run this prompt through one writer agent and save its output as synthesized_outline.md.")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap conversation-mining agents")
    parser.add_argument("--enrich-dir", required=True, type=Path)
    parser.add_argument("--agent", nargs="+", choices=list(AGENT_PROMPTS.keys()), help="Generate prompts for these agent types")
    parser.add_argument("--synthesize", action="store_true", help="Generate the synthesize prompt from existing agent outputs")
    args = parser.parse_args(argv)

    if not args.enrich_dir.is_dir():
        print(f"Enrich directory not found: {args.enrich_dir}", file=sys.stderr)
        return 1

    if args.agent:
        _generate_agent_prompts(args.enrich_dir, args.agent)
    elif args.synthesize:
        _synthesize(args.enrich_dir)
    else:
        print("Use --agent or --synthesize", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
