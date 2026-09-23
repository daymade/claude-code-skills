---
name: local-conversation-history
description: >-
  Entry point for local AI conversation history across Claude Code, Codex and Kimi CLI: routes each
  request to the reader or continuation skill that owns it and keeps the cross-provider inventory.
  Use when the platform is unknown or plural ("what was I working on", "we discussed this once") and
  for any Kimi CLI history. When platform and action are already clear, load that skill directly.
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
| Kimi CLI | `read-claude-code-history`, with the Kimi scope named — see **Provider scope** | no continuation skill exists |

Resumption always follows a read. The continuation skills require a verified
read receipt; routing straight to them without one is a defect, not a shortcut.

**When the platform is not stated** — a bare session ID, "pick up where we left
off" — do not guess it. Identify it first: try the Claude Code exact-session
lookup in `read-claude-code-history`, then the Codex rollout locator in
`read-codex-history`. Only a lookup that returns a verified identity decides
which continuation skill runs; a plausible-looking ID prefix does not.

## Provider scope — the job only this entry point routes

Each executor defaults to its own provider, so a request that spans providers
never widens by itself. **Naming the scope is this skill's whole job.** It has
two axes, and they use different flags — conflating them is the failure this
section exists to prevent.

| Cross-provider need | Route to | Name this scope |
|---|---|---|
| **Inventory** — "what have I been working on", "list my recent chats", session titles/dates/IDs | Indexed metadata where available, then exact-session readers | Do not use `list_local_history.py --source all`: its date and output limits are applied after Claude session bodies are read. Report a gap if no indexed inventory exists. |
| **Content search** — "did we ever discuss X", find a quote, file, or tool result | `read-claude-code-history`, its indexed recall, then exact-session reader | Select the relevant indexed providers; inspect index coverage and freshness. Open only candidate sessions. |
| **Ranked recall** — wording may have drifted | `read-claude-code-history`, its hybrid recall index | The index states which providers it holds; do not infer coverage for an unindexed provider. |

Indexed recall accepts explicit Claude, Codex, and Kimi provider filters.

**Use supplied clues before broad discovery.** For a pasted quote with a known
project, date, or title, use indexed metadata to narrow candidates, then
verify their original messages. For Codex, follow **Locate a quoted exchange** in
`read-codex-history`. Inventory alone never establishes a content match; if its
candidates miss or its scope is incomplete, report the gap and refine the indexed query.
Keep the current Session excluded. A request for only an ID stops at verified
message evidence; it does not require reconstructing every unrelated conversation.

For this single-ID lookup when the provider is unknown, first probe the Codex
reader's exact-ID locator backed by state-DB metadata when available.
This is a discovery order, not an assumption that the conversation was Codex;
only verified original messages establish that. If no candidate verifies, widen
to the other providers through indexed recall. Do not start this probe
with `--source all`: its Claude inventory reads session bodies before applying
date and output limits. Do not promise exhaustive search or absence when an
index or exact-session read cannot cover the requested records.

**Search history through the index or an exact known session.** A raw sweep of
every conversation is prohibited, including when an output limit or scan timeout
is set. The current raw-search date flags filter after files are read, so they
do not make that command bounded. If the index is missing, stale, or lacks a
provider, report that coverage gap; do not fall back to a corpus scan. Ranked
top-K results cannot support an absence claim.

**Kimi CLI has no other entry anywhere** — no dedicated skill exists for either
axis, so both routes above land in `read-claude-code-history`, which documents
its own Kimi home resolution.

Let the executor own exact-session lookup, indexed provider filters, coverage,
and output format. This skill names which providers are in scope.

## Intent decides the route — the word "history" does not

| The user's requested result | Route |
|---|---|
| A list of conversations: titles, dates, session IDs | The indexed inventory row under **Provider scope**; if unavailable, state the gap |
| The conversation where a topic, quote, file, or tool result appeared — "find that old chat", "did we ever discuss X" | The **indexed content search** row under **Provider scope**; use supplied clues to narrow candidates first. Listing titles alone is not evidence the content exists |
| Their own raw inputs in chronological order, verbatim | The matching reader's verbatim-input path. Preserve duplicates and session boundaries; duplicates are part of the ledger, not noise |
| Picking work back up from an identified session | The matching continuation skill, after a read |

The requested output wins over the background motivation. If someone explains a
problem and then asks for a window of their own raw inputs, return that window —
the explanation's topic clues do not convert the request into a content search.

## Invariants that survive routing

- **Coverage.** Read the index's provider and source scope plus its freshness
  frontier. An archive or provider outside that scope is unknown. A missing
  required source cannot support an absence claim.
- **Self-match.** The current session records the user's question and this
  agent's own commands, so it matches almost any query about itself. Exclude the
  current session ID before treating a hit as historical evidence.
- **Zero results are not absence.** Ranked recall can miss different wording
  and unindexed records. State coverage; do not convert an empty result into
  "it never happened".
- **Ask whether a word is the topic's name or the way you talk about it.** A
  search for `技术选型` over a corpus where the user actually said 用哪个 and
  不要闭门造车 returns almost nothing — measured: 10 hits against 163 real
  occurrences, because a Chinese phrase only matches on a token boundary. When
  searching one person's corpus, search the way they speak: imperatives,
  negations, and concrete scene sentences, not the label a design document would
  give the topic. A zero hit on a topic name cannot support an absence claim;
  widen to the phrasing that person would have used first, and say which forms
  you tried.
- **A zero has three causes and only one of them is "no history".** The other
  two are a home that was never found and a scope that excluded everything, and
  none of the three looks different in an empty table. This bites Kimi hardest:
  its documented default home is not where every install puts it — a desktop
  client can bundle the CLI inside its own runtime and keep sessions there — and
  its sessions belong to their own workspaces, so a default run inside some other
  repository returns nothing on a store full of conversations. Rule out both
  before reporting absence: name the home that was actually read, and say what
  project scope was in effect. The inventory prints a diagnostic line when a home
  is missing, so quote it when it appears — but a **located** home that yields
  zero prints no diagnostic at all, and the search path prints none in either
  case, so never treat a silent empty result as the reader confirming absence.
  `read-claude-code-history` owns how to locate a home and which scope flags the
  inventory needs.

## Do not

- Do not run provider-specific parsing, SQLite, `rg`, `jq`, or JSONL pipelines
  here. Every one of those belongs to an executor that already handles its
  store's schema, archives, and failure modes.
- Do not copy an executor's flags into this file beyond the three that name
  provider scope (`--source`, `--codex`, `--kimi`) — those are this skill's own
  subject. Every other flag changes on the executor's schedule; copying one here
  makes this file drift silently and then teach the wrong command.
- Do not route to a continuation skill to answer a question about the past.
  Reading is evidence; continuing changes the world.
