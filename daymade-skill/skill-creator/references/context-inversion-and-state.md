---
name: context-inversion-and-state
description: >-
  Design self-contained reusable Skills that invert missing domain or project
  context onto explicit user/workspace inputs and persist reusable profiles
  outside the Skill bundle. Read when authoring or refactoring a reusable
  methodology Skill that needs brand, project, compliance, or workspace facts
  without hardcoding private repos or repeating onboarding every session.
---

# Context inversion and persistent local state

Apply this contract when a Skill bundles **reusable domain methodology** (such as
copywriting, security/compliance review, proposal drafting, or operational audits)
that must work across different brands, projects, teams, or workspaces without
hardcoding private repositories or forcing the user to re-paste the same context
every session.

Skip this contract for pure stateless transforms (format conversion, single-file
linting) or software/account setup flows:

- For tool installation, login, running services, or human consent steps, use
  [first use and recovery](first-use-and-resume.md).
- For user-approved recurring visual report forms, use
  [report-template approval](authoring-and-reuse.md#show-the-result-not-just-the-work).

## 1. Invert domain context instead of hardcoding it

Keep the Skill bundle **self-contained in methodology** and **agnostic to any one
customer, product, or private repository**:

| Layer | Where it lives | Examples | Rule |
|---|---|---|---|
| **Reusable methodology** | Inside the Skill bundle (`SKILL.md`, `references/`, `scripts/`, `assets/`) | Decision trees, domain frameworks, quality gates, scoring rubrics, mode switches, deterministic helpers | Must run out of the box once required context slots are supplied; never depend on an author's private repo path, client name, or hardcoded SKU |
| **Injected domain context** | Supplied at runtime by the user, workspace, or a persisted local profile | Brand/product facts, target audience, offer boundaries, compliance red lines, local SSOT file pointers | Depend on an abstract **Context Contract** (named slots), not on concrete files or entities |
| **Task-scoped firsthand input** | Supplied per run in the current conversation | Today's topic, specific incident log, firsthand customer quote, current batch files | Ask per task when blocking; do not silently overwrite durable profile slots with one-off task notes |

When retiring or consolidating a narrow, customer-specific Skill into a unified
reusable Skill, preserve reusable domain methodology inside the unified bundle,
extract customer-specific facts into an injected context contract, and store
recurring user/project facts in local profile state rather than branching the
Skill by customer name.

## 2. Classify every context slot explicitly

Declare each slot's missing-value behavior before writing generation instructions:

| Slot class | Missing behavior | Example |
|---|---|---|
| **Blocking** | **Stop before production.** Do not fabricate load-bearing facts or silently substitute generic filler | Core product/offer truth, mandatory compliance rules, authoritative pricing/terms |
| **Optional** | Degrade cleanly to built-in Skill defaults and state which default was applied | Secondary tone preferences, optional formatting nuances, supplementary references |
| **Conditional escalation** | Optional in baseline mode; **escalates to blocking** when the user selects a higher-risk mode or claim | Firsthand customer story or live warranty terms: optional in a generic explainer, blocking when drafting an authentic operator case study or real-lead commercial reply |

**Explicit placeholder-skeleton escape hatch:** Never silently guess blocking
facts to appear helpful. If the user explicitly asks to proceed before supplying
blocking slots, emit a clearly labeled **structure-only skeleton** with explicit
`[TBD: <missing-slot>]` markers and an unverified-gaps list, marked not
publish-ready.

## 3. Execute the Resolve → Diff → Ask Once → Persist loop

Put this loop in the Skill's ordinary entry before any content generation or
external action:

1. **Resolve non-interactively first.** Gather context in precedence order:
   (a) explicit values/paths supplied in the current turn, (b) matching saved
   local profile (by explicit `--profile <slug>`, alias match, or current
   workspace root `cwd`), and (c) declared workspace-local files when bound.
   Handle multi-profile ties **fail-closed**: if two or more saved profiles match
   an unqualified alias or workspace with equal rank, return `ambiguous` with
   candidate slugs and ask the user to pick one rather than guessing.
2. **Verify live local pointers and compute coverage.** If a saved profile
   references local file or directory pointers (`source_paths`), check that each
   pointer still exists and is readable right now. Compute `present`,
   `missing_blocking`, `missing_optional`, and `missing_local_sources` for the
   selected execution mode.
   - **Liveness invariant:** `ready` must be `false` whenever **either**
     `missing_blocking` or `missing_local_sources` is non-empty—consistently
     across every read command (`resolve`, `show`, `list`). Never return
     `status=needs_context` alongside `ready=true`, and never treat a cached
     profile as live without re-checking local paths.
3. **Ask Once when incomplete.** If `ready` is `false`, halt production and emit
   one consolidated **Missing-Context Card** containing:
   - which profile/workspace matched (or none),
   - which durable slots are already satisfied (reused, not re-asked),
   - only the remaining missing blocking slots or disappeared local paths, with
     one-line examples of acceptable answers (inline facts or local file paths),
   - the optional placeholder-skeleton opt-in if the user wants structure only.
4. **Persist durable slots outside the Skill bundle.** Once the user provides
   reusable profile-scoped context (or asks to save/update it), save it in a
   stable user-machine location outside the update-owned Skill bundle:
   - Default root: `${XDG_CONFIG_HOME:-~/.config}/<skill-name>/profiles/<slug>.json`
     (support an explicit env override such as `<SKILL_NAME>_CONTEXT_DIR` for
     isolated tests).
   - Never write profiles into the Skill directory, plugin cache, or source
     repository: Skill updates replace bundles, and public repos must not absorb
     user data.
   - Never persist passwords, API keys, OAuth tokens, or private credentials in
     context profiles; keep secrets with their dedicated auth owner.
5. **Reuse automatically on later runs.** On subsequent invocations—including
   from unrelated working directories—resolve the saved profile, re-check local
   pointer liveness, inject all satisfied slots without re-asking, and prompt
   only for task-scoped or newly missing blocking slots.

## 4. Local profile-store engineering contract

When a Skill ships a deterministic local helper (for example
`<skill-dir>/scripts/context_store.py`) to implement the loop above, enforce these
invariants:

- **Deterministic exit codes and streams:**
  - `0`: resolved and ready, or non-interactive read/write completed.
  - `2`: invalid arguments, unsafe slug/path, symlink violation, or malformed
    stored profile; emit structured JSON error on `stderr`, never an unhandled
    traceback.
  - `3`: valid execution where context is incomplete (`needs_context`) or
    multiple profiles tie (`ambiguous`); emit structured JSON payload on `stdout`
    naming exact missing slots, missing paths, or candidate slugs.
- **Slug, symlink, and permission hygiene:** Validate slugs with a strict
  allowlist (e.g. `^[a-z0-9][a-z0-9._-]{0,63}$`), verify resolved target paths
  remain inside the profiles directory, reject symlinked profile files on read
  and write, and enforce restrictive permissions (`0o700` directory, `0o600`
  profile file).
- **Atomic writes and partial-update merge:** Write via a same-directory
  temporary file plus atomic `os.replace()` so interrupted writes never corrupt
  the prior profile. Saving one slot must merge into the existing profile without
  wiping untouched slots; clearing a slot requires an explicit `--clear-slot`
  flag, and deleting a profile requires an explicit `--confirm` flag.
- **Defensive read validation:** Catch `OSError`, `UnicodeDecodeError`, and
  `json.JSONDecodeError`. Validate required schema fields and container types
  (`slug` non-empty string, `slots` mapping, `aliases`/`workspace_roots`/
  `source_paths` lists of non-empty strings) before computing coverage; reject
  corrupted files with exit `2` rather than raising `KeyError` or silently
  dropping invalid elements.
- **Schema versioning:** Record `schema_version` in every saved profile; pair
  any format change with
  [persisted-format compatibility](stateful-script-verification.md#persisted-format-compatibility).

## 5. Verify the inversion and persistence contract

Select the affected controls below in an isolated temporary directory (using the
store's env override or isolated `HOME`—never mutate live user profiles). Pair
deterministic store tests with output-level behavior replays for agent routing:

| Case | Falsifiable observation |
|---|---|
| Empty store + bare request | Helper exits `3` (`needs_context`); agent stops before generation and emits one consolidated Ask-Once card with zero fabricated blocking facts |
| Explicit skeleton opt-in | Agent emits `[TBD: <missing-slot>]` markers and an unverified-gaps list, explicitly labeled not publish-ready |
| Save once + resolve from another `cwd` | Baseline mode exits `0` (`ready`) with zero re-prompting; conditional mode reuses saved durable slots and asks only for the newly blocking task-scoped slot |
| Partial update, clear, and delete guards | Updating slot B preserves slot A after close/reopen; `--clear-slot` clears only the named slot; `delete` without `--confirm` refuses and leaves the file intact |
| Stale local source path | Deleting or moving a saved `source_paths` entry sets `ready=false` consistently across `resolve`, `show`, and `list`, and names the missing path |
| Malformed, non-UTF-8, or symlinked state | Corrupted JSON, invalid UTF-8 bytes, wrong field types (such as a scalar `aliases`), missing required keys, and symlinked profile files all exit `2` with structured JSON error and zero raw traceback |
| Ambiguous multi-profile tie | Two profiles matching the same alias or workspace exit `3` (`ambiguous`) and list candidates without silently picking one |

Reuse [stateful-script-verification.md](stateful-script-verification.md) for
mixed-version compatibility roundtrips, partial-update evidence checks, and
isolated test-harness hygiene. Stop once the affected cases and output-level
replays clear; do not build a profile database or generic framework for a Skill
that has no recurring user/project context.
