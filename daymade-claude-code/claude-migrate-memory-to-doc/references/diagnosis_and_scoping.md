# Diagnosis & Scoping

## The scope decision table

Classify each memory file by **scope** — who/what needs it — not by "is it messy".

| Memory content | Goes to | Why |
|---|---|---|
| Team rules, coding standards, project SOPs | project `CLAUDE.md` / `docs/` | version-controlled, team-visible, reviewable |
| Project-specific architecture, decisions, war-stories, operational SOPs | project `docs/` (decisions / architecture / references / reports / troubleshooting) | same reasoning as above; these are project artifacts, not user profile |
| User profile, background, values, identity | global `~/.claude/references/user/` | cross-tool + cross-project; any AI should read it first |
| Collaboration preferences / feedback (how to work with this user) | global `~/.claude/references/user/` | cross-tool; not a project artifact |
| User's methodology / principles | global `~/.claude/references/user/` | cross-tool |
| Personal affairs (life facts the AI needs to act correctly) | global `~/.claude/references/user/` | cross-tool, but mark as privacy |
| Temporary handoff snapshot (state for the next session) | **stays in memory** | this is memory's legitimate purpose |
| External system pointer (a ticket, a channel id) | **stays in memory** | personal working context |

## The deciding question (three steps, in order)

1. Would a **teammate** opening this project need this rule/standard? → project `CLAUDE.md` / `docs/`.
2. Else, would **another AI tool** (Codex, Cursor) or **another project** need this user fact/preference? → global `~/.claude/references/user/` (tool-agnostic).
3. Else — it's just a handoff for the next session, or an external pointer? → leave it in `memory/`.

The pre-existing project rule may say "user preferences → memory". That rule predates multi-tool use; this migration supersedes it for the cross-tool bucket. Update the rule (see tool_agnostic_migration.md) so it stops contradicting reality.

## Caveat: agents can't judge private-context data

When deciding keep-vs-delete, content that depends on the user's **private context** (their correction dictionary, their internal naming, their idiosyncratic preferences) **cannot be batch-judged by a subagent** — agents have generic common sense but not "what *this* user actually values". A subagent will confidently flag a context-correct entry as wrong.

So: agents may **surface candidates**, but the user (or you, holding full context) **decides**. Multi-agent workflows are good for **objective** classification (broken links, derived counts, structural matches), not for "is this private fact worth keeping".

## Privacy check: don't migrate PII into shared docs

Some memory contains personally identifying information: real-name-to-username maps, private contacts, home addresses, medical/life details, etc. Even when the *topic* is project-relevant, the *identifying payload* is not a team artifact. Route it like this:

- **Identity mapping / real names** → keep in private memory (thin to a pointer if the SSOT is elsewhere); do not put in project docs.
- **Operational facts that happen to contain a name** (e.g., "ask 星月 for the Alipay key") → de-identify if you migrate them, or leave in memory.
- **PII that is also cross-tool user profile** (rare) → `~/.claude/references/user/` is still private to the user's machine, but mark the file clearly as privacy-sensitive.

## Inline discipline: some rules belong in CLAUDE.md body, not just references/

Even when a rule is about "how to work with the user" (which normally goes to `references/user/`), consider inlining it into `~/.claude/CLAUDE.md` if it governs **every message the agent produces**. Examples:

- Commitment-word discipline ("已修复" must pair with a tool call).
- Tone / language defaults that shape output.
- Private-context correction rules the agent must apply before speaking.

The test is: *if this rule is missed because the agent didn't open the reference, will the user's trust erode immediately?* If yes, inline it.

## Phase 6 cleanup decisions (for memory that did NOT migrate)

- **Clean → archive**: expired (a dated handoff whose event has passed) OR stale derived values (a stored count/total/aggregate that should be computed, not persisted).
- **Thin**: a handoff that restated a SSOT living elsewhere (a repo README, a design doc). Cut the duplicated detail; keep **only** the pointer + the volatile state that isn't in the SSOT (e.g. "the staging instance is still billing — shut it down").
- **Keep**: already a clean pointer, or a genuine live handoff.

### Derived values: not "dedup later", but "never store"

A count, a total, an aggregate status, a "last updated" you could recompute — don't persist it; compute on demand. If you encounter one inside a file you're **already editing**, remove it (SSOT hygiene). Don't open files you aren't otherwise touching just to hunt them — that's unbounded scope creep.
