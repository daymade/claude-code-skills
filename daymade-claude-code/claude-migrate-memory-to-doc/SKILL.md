---
name: claude-migrate-memory-to-doc
description: >-
  Migrates Claude Code personal memory (the per-project memory/ directory) into
  tool-agnostic reference docs, so other AI CLIs that auto-load AGENTS.md (Codex
  primarily; the content architecture transfers to Cursor and others) working in
  the same directory can read the same user profile, collaboration preferences,
  and methodology instead of being blind to them. Use this whenever the user says
  things like "migrate my memory", "my memory is locked to Claude Code", "make
  Codex/Cursor read my profile", "memory should live in docs not one tool", or
  reports that a second AI tool doesn't know who they are; also use it when memory
  has grown bloated with content that should be shared across tools or projects.
  Covers diagnosis, the references/ + CLAUDE.md-inline + AGENTS.md-symlink
  architecture, multi-agent review, empirical codex verification, and memory
  cleanup. Inline only — it orchestrates review subagents and runs codex.
---

# Migrate Claude Code Memory to Tool-Agnostic Docs

## Why this skill exists

Claude Code's personal memory lives in `~/.claude/projects/<project-slug>/memory/`. It is **locked to Claude Code**: not version-controlled with the repo, invisible to every other tool. The moment the user runs Codex, Cursor, or any other AI CLI in the same directory, those tools cannot read "who the user is / how to work with them" — even though a user profile and collaboration preferences are exactly what *any* AI assistant should read first.

This skill moves the **cross-tool-shareable** content out of memory into a tool-agnostic location, and leaves memory as a thin handoff cache. The real problem it solves is **tool lock-in**, not "messy memory".

This skill runs **inline** (never `context: fork`): it spawns parallel review subagents and runs `codex` via Bash — a forked subagent could do neither.

## The core insight — read this before touching anything

The hard part is not moving files. It is this:

> **A reference file reached only by a plain-text pointer is read on-demand and is NOT guaranteed to load — in *either* tool.**

- **Claude Code** auto-preloads a reference only via `@import` syntax. A plain-text pointer ("see `~/.claude/references/user/foo.md`") is on-demand: the agent must choose to open it.
- **Codex** is stricter: it does **not parse or follow** text paths written inside CLAUDE.md at all. It only auto-injects the doc *files themselves* (its `AGENTS.md` / configured fallback) along the `~/.codex → git-root → cwd` chain. Reference files named anything else, sitting in `~/.claude/references/`, are **never auto-loaded** by Codex.

Therefore the architecture must be a **two-layer split**:

| Layer | Where | Guarantee |
|---|---|---|
| **Guaranteed-hit** — the few facts that must be true every turn | inlined into **CLAUDE.md body** (both tools inject it) | always present |
| **On-demand detail** — full profile, war-stories, edge cases | `references/` files, reached by pointer | loaded when relevant |

Putting the hardcore facts *only* in a reference and trusting a pointer is the #1 way this migration silently fails. Inline them.

## Tool-agnostic architecture

```
~/.claude/CLAUDE.md            global instructions — BOTH tools inject this.
                               Inline the hardest user facts here (a short "User context" section).
~/.claude/references/user/     SSOT for profile / preferences / methodology / personal affairs.
~/.claude/references/user-profile.md   hub: condensed core + index into the user/ files
~/.codex/AGENTS.md  ──symlink──▶  ~/.claude/CLAUDE.md
                               so Codex's GLOBAL layer injects the same file Claude Code reads.
~/.codex/config.toml           raise project_doc_max_bytes — Codex truncates docs at 32 KiB by default,
                               which silently drops the back half of a long CLAUDE.md.
```

> **Scope note**: the wiring (the `~/.codex/` symlink, the config edit, and the Phase 5 verification) is **Codex-specific** and was verified against Codex only (2026-06). The `~/.claude/references/user/` content layer transfers to any tool that auto-loads a project doc, but Cursor and others need their own wiring (Cursor reads `.cursor/rules` / a project-root `AGENTS.md`, not `~/.codex/`) — not implemented or verified here.

## Workflow

Copy this checklist into your working notes and check items off:

```
Memory → Tool-Agnostic Doc Migration:
- [ ] Phase 1: Diagnose & scope — classify every memory file by SCOPE
- [ ] Phase 2: Tool-agnostic migration — references/ + inline hardcore + symlink + config
- [ ] Phase 3: Multi-agent review — 4 parallel reviewers
- [ ] Phase 4: Fix everything review surfaced
- [ ] Phase 5: VERIFY BY RUNNING CODEX (not by reasoning)
- [ ] Phase 6: Memory cleanup — clean / thin / keep + soft-delete to backup
```

### Phase 1 — Diagnose & scope

**Preflight — find the memory directory.** Claude Code memory lives at `~/.claude/projects/<project-slug>/memory/`, where `<project-slug>` is the working directory path with `/` → `-`. A user may have memory across several projects — list them with `ls ~/.claude/projects/*/memory/` and pick (or merge) the project(s) whose memory holds the cross-tool user content.

List every file under that memory directory. Classify each by **scope**, not by "is it messy". Full decision table and the agent-can't-judge-private-context caveat: read **[references/diagnosis_and_scoping.md](references/diagnosis_and_scoping.md)**.

The short version:

- **Team rules / standards / SOPs** → project `CLAUDE.md` or `docs/` (version-controlled, team-visible).
- **Cross-tool user profile / collaboration preferences / methodology / personal affairs** → `~/.claude/references/user/` (tool-agnostic). **This is the bucket that migrates.**
- **Temporary handoff snapshots / external system pointers** → **stay in memory**. This is memory's legitimate purpose; do not migrate them.

Do NOT migrate everything. Over-migrating handoff state into long-lived docs is its own mistake. **But do look at the whole directory** — not just `feedback_*.md` — because project SOPs and operational war-stories often sit in `project_*.md` or `architecture_*.md` files and belong in the repo's docs.

Also flag **private-context / PII** in this pass: a memory file that maps system usernames to real names, private contacts, or other personally identifying information should **stay in private memory** even if it is project-relevant. Project docs are version-controlled and potentially shared; identity-mapping belongs in the thin handoff layer.

### Phase 2 — Tool-agnostic migration

**Snapshot CLAUDE.md first** (`cp ~/.claude/CLAUDE.md ~/.claude/CLAUDE.md.bak`) — you're about to edit it. If `~/.claude/CLAUDE.md` doesn't exist, create it (some users only have a project-level one).

**If `command -v codex` is empty** (Codex not installed): do only steps 1 and 4 below (the `references/` + inline-CLAUDE.md work), and **skip** the symlink (2), config (3), and all of Phase 5. The content migration still stands; leave a note that wiring Codex later needs the symlink + `project_doc_max_bytes`.

For each "migrates" item, move the content into `~/.claude/references/user/` (group by theme into a handful of files + a `user-profile.md` hub). Then wire the two-layer architecture:

1. **Inline the hardcore** into a `# User context` section near the **top** of `~/.claude/CLAUDE.md` (within the first ~32 KiB so Codex sees it): the 3–6 facts that must hold every turn (e.g. how to address the user, hard preferences, the single most important identity fact). Everything else stays as pointers.
2. **Symlink** `~/.codex/AGENTS.md → ~/.claude/CLAUDE.md` (only if `~/.codex/AGENTS.md` is absent or an empty placeholder — never clobber a real file).
3. **Raise `project_doc_max_bytes`** in `~/.codex/config.toml` if CLAUDE.md exceeds 32 KiB.
4. **Update the project's knowledge-storage rule** (if one exists) so "user preferences → memory" doesn't contradict the new "user profile → `~/.claude/references/user/`" reality.

Exact directory layout, the hub-and-spoke pattern, and the governance-rule fix: **[references/tool_agnostic_migration.md](references/tool_agnostic_migration.md)**.

### Phase 3 — Multi-agent review

Spawn 4 review subagents in parallel (one message, multiple Task calls). Each audits one dimension: **content completeness** (did any fact get dropped/altered), **cross-reference breakage** (which `[[links]]` will dangle if memory is deleted), **tool-agnostic link integrity** (does the symlink/pointer chain actually resolve; does Codex really read it), **duplication/drift** (does a reference duplicate a CLAUDE.md rule). Exact prompts: **[references/review_and_verification.md](references/review_and_verification.md)**.

Agent findings are hypotheses, not verdicts — filter them (probability × cost × does-it-actually-happen) before acting.

### Phase 4 — Fix

Address what review surfaced. Common real findings (all from a live run): a hub file that forgot to index one of its own children; hardcore facts left only in a reference (move them inline); `[[links]]` in surviving files pointing at to-be-deleted memory (repoint to the new reference); a governance table row updated but the judgment sentence in the same section left contradicting it.

### Phase 5 — VERIFY BY RUNNING CODEX (do not skip, do not delegate to the user)

The step you'll be tempted to replace with "looks right" or "you can check it yourself later". Don't. **Run codex from any dir with `--skip-git-repo-check`, match its session log by session id (not by mtime), and grep for your inlined hardcore section + a back-of-file string.** The inlined section may be titled `# User context`, `# 用户上下文`, or whatever localization the user uses — grep for the *actual* heading string, not a hardcoded English one. A passing run greps `1` for that heading and `1` for the back-half string (if CLAUDE.md > 32 KiB). The exact, empirically-verified command block — `--skip-git-repo-check`, session-id extraction (it's in the header, not the tail), the 32 KiB check, plus the `< 32 KiB` and `codex-not-installed` shortcuts and expected console output — is in **[references/review_and_verification.md](references/review_and_verification.md)**. Use it verbatim; don't hand-roll a variant here (that's how the two copies drift).

### Phase 6 — Memory cleanup

For the memory files that did NOT migrate, do one of three things (decision detail in **[references/diagnosis_and_scoping.md](references/diagnosis_and_scoping.md)**):

- **Clean** — expired (past-dated handoffs) or stale (derived counts that should be computed, not stored) → archive.
- **Thin** — a handoff that restated a SSOT living elsewhere → cut the duplication, keep only the pointer + the volatile state (e.g. "instance X still billing, shut it down").
- **Keep** — legitimate handoff / already a clean pointer → leave it.

Update the memory index (e.g. `MEMORY.md`) to drop migrated entries and add one migration pointer.

**Before moving anything, grep the whole memory dir AND the project docs / CLAUDE.md for references to the files you are about to archive.** A surviving file or active doc that links to an archived file ends up with a dangling reference. Repoint those links to the new doc location or to a plain-text pointer. Memory cross-links are not the only risk — project `CLAUDE.md` and handoff docs often cite memory files by name.

**Soft-delete, never hard-`rm`.** Move migrated/cleaned files to a dated backup dir **outside** `memory/` (e.g., a sibling `~/.claude/projects/<slug>/.memory-archive-2026-07-06/` — use the **actual current date**, not a placeholder). Putting the archive inside `memory/` leaves it readable as live memory, defeating the cleanup. Update the index pointer to the new outside-memory path. Tell the user they can `rm` the backup after a couple of weeks of confirming both tools behave.

**After a migration that taught you something new, update this skill.** If you hit a failure mode not listed in `references/failure_cases.md`, append it; if a step was underspecified, tighten the SKILL.md checklist. A skill that isn't fed back its own lessons will repeat the same mistakes.

## Do NOT (each one learned by getting it wrong in a live run)

- **Don't reach for "delete" first.** The instinct is to delete messy memory. Wrong order: first classify migrate / thin / keep. Most "messy" memory is either migratable value or legitimate handoff — deleting loses the value.
- **Don't assume `reference + pointer` = tool-agnostic.** A pointer is on-demand in *both* tools. The hardcore facts must be inlined into CLAUDE.md body, or they silently won't load.
- **Don't believe Codex follows text pointers.** It reads the AGENTS.md/CLAUDE.md file itself, not paths written inside it. Verified against official docs + a real session log.
- **Don't forget Codex's 32 KiB doc truncation.** A long CLAUDE.md loses its back half in Codex unless `project_doc_max_bytes` is raised. The user may have been running half a CLAUDE.md for months without knowing.
- **Don't change a governance table row and leave the judgment logic in the same section contradicting it.** Grep the whole section after editing one fact.
- **Don't delete a memory file before grepping for `[[cross-references]]` to it.** A surviving file pointing at a deleted one becomes a dangling link.
- **Don't let an agent batch-decide what to delete/keep when the content depends on the user's private context.** Agents lack "what the user actually values"; surface candidates, let the user (or you, with full context) decide.
- **Don't make the user verify.** Running codex and grepping the log is agent-doable — own the verification loop, don't hand it back.
- **Don't treat "the symlink exists" as Codex verification.** A correct symlink is necessary but not sufficient; the only proof is a real `codex exec` session whose rollout log contains your inlined hardcore section.
- **Don't put the archive inside `memory/`.** It remains readable as live memory there, defeating the cleanup. Move it to a sibling dir outside `memory/`.
- **Don't migrate real-name identity maps or PII into project docs.** Project docs are version-controlled and shared. If a memory file maps `user3 → 慧如`, keep it in private memory (thinned to a pointer if the SSOT lives elsewhere) — do not move it to `docs/`.
- **Don't overwrite an existing doc with a memory duplicate without diffing first.** Many memory files are *partial* duplicates of docs (e.g., `architecture_v2_decision.md` vs `docs/decisions/2026-02-21-v2-architecture.md`). Migrate only the **unique** details; append them to the existing doc rather than replacing it.
- **Don't forget to repoint links in project docs, not just memory.** `CLAUDE.md` and handoff docs often cite memory files by basename. Grep them before archiving.

## Failure cases (the full war-stories)

The reasoning behind the Do-NOTs, with what actually broke each time: **[references/failure_cases.md](references/failure_cases.md)**.
