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
