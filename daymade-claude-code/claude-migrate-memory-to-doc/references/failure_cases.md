# Failure Cases — the war-stories behind each Do-NOT

Each happened in the live run this skill was distilled from. They are why the rules exist; read them when you doubt whether a rule is worth following.

## 1. "Delete first" was wrong — twice

The first instinct was to delete bloated memory. Then it became "actually, move it". Then "actually, thin it". The correct frame is **migrate / thin / keep / delete**, decided per file by scope. Treating cleanup as "delete the mess" loses both migratable value and legitimate handoffs. Cost: two full reversals before landing on the right model.

## 2. reference + pointer ≠ guaranteed-to-load

The plan was "put the profile in `references/`, point at it from CLAUDE.md — now it's tool-agnostic". Wrong: a plain-text pointer is **on-demand in both tools**; the agent may never open it. The fix was the two-layer split — inline the hardcore into CLAUDE.md body (guaranteed), pointer to the rest. Finding this required actually checking how each tool loads docs, not assuming.

## 3. Codex does not follow text pointers (official-docs-confirmed)

It was assumed Codex would follow "see `~/.claude/references/...`" written inside CLAUDE.md. It does **not** — it only auto-injects the doc files on its directory chain, and treats inline paths as plain text. Verified (2026-06, codex v0.142.3) against Codex's official AGENTS.md docs **and** a real session log. Consequence: the symlink (so the global CLAUDE.md *is* one of those auto-injected files) is load-bearing, and the hardcore must live in that file's body.

## 4. The 32 KiB truncation nobody knew about

Codex's `project_doc_max_bytes` defaults to 32 KiB. A long global CLAUDE.md had its **entire back half silently dropped** in Codex — for however long the user had been running Codex. Only running codex + grepping a back-of-file string revealed it. Fix: raise the limit in `config.toml`, and keep the user-context section near the top regardless.

## 5. Changed the table row, missed the judgment sentence

A governance table's "user preferences → memory" row was updated to "→ references/user/", but the prose "decision method" sentence three lines below still said "→ memory". A row and its surrounding logic drift apart if you only edit the eye-catching one. Rule: after changing one fact, grep/read the **whole section**.

## 6. The hub forgot to index its own child

The hub (`user-profile.md`) was built with an index of 4 children; a 5th child file was created later and never added to the index. From the entry point, the 5th file was unreachable — its whole content effectively invisible. A multi-agent review caught it. Rule: when you add a child, update the hub index in the same breath.

## 7. Deleting would have dangled live links

Before deleting migrated memory, a grep found **surviving** (non-migrating) memory files still `[[linking]]` to them. Deleting first would have left dangling links. Rule: grep cross-references **before** deleting; repoint survivors to the new reference.

## 8. "You can verify it yourself later" — no

After wiring the symlink, the instinct was to tell the user "next time you run Codex, grep the log to confirm". That hands an **agent-doable** verification back to the user. The right move: run codex right now, grep the log, report the proof. Owning the feedback loop is the whole point of the skill.

## 9. (meta) Don't load past-session JSONL into context to "mine history"

When distilling a skill from *prior* sessions, do **not** read the multi-MB transcript JSONL into your own context — it blows the window (one attempt died ~17 tokens over the limit and lost the whole session). Delegate extraction to subagents that parse line-by-line with a script and return only a distilled lessons list. (For this skill the live run was already in-context, so no mining was needed — but the instinct to "just read the history" is the trap.)

## 10. The archive was left inside `memory/`

A soft-delete moved `feedback_*.md` into `memory/archive/2026-07-05/`. Because the memory loader scans the `memory/` tree recursively, those files were still live memory. The fix: move the dated archive to a sibling directory **outside** `memory/` (e.g., `~/.claude/projects/<slug>/.memory-archive-2026-07-05/`) and update the index pointer. Verifying: `grep -R "feedback_" memory/` should only hit the explicit archive pointer or text references, not the archived files.

## 11. "Symlink looks correct" was mistaken for Codex verification

After creating `~/.codex/AGENTS.md → ~/.claude/CLAUDE.md`, the agent stopped there. Later, a live `codex exec` run revealed the global file was loading, but the verification protocol had hardcoded `"User context"` while the actual inlined section was titled `"用户上下文"`, so the heading grep returned `0`. The fix: run `codex exec --skip-git-repo-check`, extract the session id from the header, find the rollout JSONL, and grep for the **actual** heading string plus a back-half string. Only that empirical check is proof.

## 13. Dangling references were hiding in project docs, not just memory (2026-07-06)

A memory file about the prod cutover was referenced by the project's own `CLAUDE.md` and by a handoff doc in `docs/handoff/`. The cross-reference agent had only been asked to grep the memory directory, so those live-doc pointers would have dangled after archival. The fix: extend the pre-archive grep to **project docs, CLAUDE.md, and handoff docs** — anywhere a memory basename might be cited.

## 14. A real-name identity map almost migrated into project docs (2026-07-06)

`project_user_management_sop.md` contained a table mapping `user3 → 慧如` and other real-name-to-system-username pairs. It was project-relevant (useful for ops), but the real names are PII and the mapping is not a team artifact. Migrating it into version-controlled `docs/` would have leaked identifying information. The fix: keep identity-mapping in private memory, thin it to a pointer to the public SOP, and add an explicit privacy check in Phase 1.

## 15. Partial duplicates were overwritten instead of merged (2026-07-06)

Several memory files (`architecture_v2_decision.md`, `cache_regression_2026_04_12.md`, `project_upstream_capture_shipped_2026_05_13.md`) were partial duplicates of existing project docs. The first instinct was to replace the doc with the memory version; that would have lost doc-only updates and formatting. The correct move: diff the two, append the memory's **unique** details to the existing doc, and archive the memory.
