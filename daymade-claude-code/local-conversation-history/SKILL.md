---
name: local-conversation-history
description: >-
  Entry point for local AI conversation history across providers. Routes a
  request to the one skill that owns it, by platform (Claude Code, OpenAI Codex,
  Kimi CLI) and action (read evidence vs continue interrupted work), and owns the
  one job none of them own alone: a single inventory spanning all three
  providers. Use when the provider is unknown or plural ("our history", "what
  have I been working on", "which chats did I have"), when the user wants Kimi
  CLI sessions, when it is unclear whether they need evidence or resumption, or
  when they ask for this skill by name. When the platform and the action are
  both already clear, load that executor skill directly instead.
argument-hint: "[keywords | session-id | workspace-path]"
---

# Local Conversation History — router

This skill decides **which** skill runs. It does not parse history itself, does
not own commands for a single provider, and never re-implements what an executor
already does. If you find yourself explaining flags for one provider, you are in
the wrong skill — hand off and stop.

## Route by platform × action

Establish two things before routing: **which platform** the conversation lived
on, and whether the user wants **evidence** (what was said/done) or
**resumption** (take the work forward).

| Platform | Read evidence | Continue the work |
|---|---|---|
| Claude Code | `daymade-claude-code:read-claude-code-history` | `daymade-claude-code:continue-claude-code-work` |
| OpenAI Codex | `daymade-claude-code:read-codex-history` | `daymade-claude-code:continue-codex-work` |
| Kimi CLI | see **Cross-provider inventory** below | no continuation skill exists |

Resumption always follows a read. The continuation skills require a verified
read receipt; routing straight to them without one is a defect, not a shortcut.

## Cross-provider inventory — the job only this entry point routes

"What have I been working on", "list my recent chats", an unknown provider, or
Kimi CLI all need **one inventory across all three providers**. Both readers ship
the same bundled inventory command, and its `--source` already defaults to `all`
— but each reader's own task table pins it to that reader's provider
(`--source claude`, `--source codex`). So a cross-provider inventory does not
happen unless someone asks for it.

Route it to `read-claude-code-history` and state the scope explicitly: run that
skill's bundled inventory with `--source all` (or `--source kimi` for Kimi
alone). Let it resolve its own command; this skill names the scope, not the
path. **Kimi CLI has no other entry anywhere** — no dedicated skill exists, and
its home resolves `--kimi-home` > `KIMI_HOME` > `~/.kimi-code`.

Let the executor own every flag beyond `--source`: scope (`--all-projects`,
`--recursive`), date bounds, `--include-archived`, `--include-subagents`,
`--include-automated`, and output format. This skill names the provider scope
and nothing else.

## Intent decides the route — the word "history" does not

| The user's requested result | Route |
|---|---|
| A list of conversations: titles, dates, session IDs | Cross-provider inventory above, or the matching reader when one platform is named |
| The conversation where a topic, quote, file, or tool result appeared — "find that old chat", "did we ever discuss X" | The matching reader's **search**, not an inventory. When the provider is unknown, the search must cover all three; a Claude-only result cannot support an absence claim |
| Their own raw inputs in chronological order, verbatim | The matching reader's verbatim-input path. Preserve duplicates and session boundaries; duplicates are part of the ledger, not noise |
| Picking work back up from an identified session | The matching continuation skill, after a read |

The requested output wins over the background motivation. If someone explains a
problem and then asks for a window of their own raw inputs, return that window —
the explanation's topic clues do not convert the request into a content search.

## Invariants that survive routing

- **Completeness.** A Claude inventory's source set is indivisible: the
  auto-discovered active homes (`~/.claude`, profile homes, the current
  `CLAUDE_CONFIG_DIR`) **plus** every archive registered in
  `~/.claude/history-sources.json`. Never call a conversation absent unless the
  output shows the registered archives were covered. An unavailable required
  archive is a configuration error, not permission to return a partial answer.
  `--claude-home` is a diagnostic override and can never back a completeness
  claim.
- **Self-match.** The current session records the user's question and this
  agent's own commands, so it matches almost any query about itself. Exclude the
  current session ID before treating a hit as historical evidence.
- **Zero results are not absence.** Ranked recall and a bounded search both
  return nothing for wording that exists under different words. Widen, or say
  what was searched — do not convert an empty result into "it never happened".

## Do not

- Do not run provider-specific parsing, SQLite, `rg`, `jq`, or JSONL pipelines
  here. Every one of those belongs to an executor that already handles its
  store's schema, archives, and failure modes.
- Do not copy an executor's flags into this file beyond `--source`. They change;
  this file would drift silently and then teach the wrong command.
- Do not route to a continuation skill to answer a question about the past.
  Reading is evidence; continuing changes the world.
