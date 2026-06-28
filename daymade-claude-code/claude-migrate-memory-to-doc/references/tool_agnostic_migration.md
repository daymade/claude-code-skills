# Tool-Agnostic Migration — the architecture in detail

## Directory layout (hub-and-spoke)

```
~/.claude/references/
├── user-profile.md          # HUB: one-liner + condensed core + INDEX of children
└── user/
    ├── background-and-skills.md
    ├── values-and-decisions.md
    ├── personal-affairs.md            # privacy-marked
    ├── operating-entity.md            # legal/identity facts, if any
    └── collaboration-and-methodology.md   # how to work with the user + their principles
```

(File names above are **illustrative** — name them whatever fits the user's content; the real ones may be in any language.) Group memory content **by theme**, not one-file-per-memory. Start each file with a provenance line: `source: original memory <name>, migrated <YYYY-MM-DD>`. Keep references **one level deep** — Claude and Codex both read a directly-linked file completely, but may only partial-read a file reached through another reference.

## The hub (`user-profile.md`)

Holds: a one-liner, the **condensed** core (a few sentences per theme), and an **index** linking every child. The hub's core is a navigational summary; the child files are the SSOT.

**Keep the index complete.** Forgetting to index a child you created later is the single most common self-inflicted bug — that child becomes unreachable from the entry point. When you add a child file, add its index line in the same edit.

## Inline the hardcore into CLAUDE.md (the guaranteed-hit layer)

Add a short `# User context` section near the **top** of `~/.claude/CLAUDE.md`. Put **only** the few facts that must hold every single turn — because references are on-demand and may not be read by either tool. Everything else stays a pointer.

A good hardcore set is **3–6 bullets**: how to address/talk to the user, the one or two hard preferences that ruin the interaction if missed, the single most important identity/entity fact, the resource/scope stance.

**State in that section WHY it's inlined** ("inlined because references are on-demand and not guaranteed to load") so a future editor doesn't "deduplicate" it away thinking it's redundant with the references. A deliberate, documented inline is not drift.

## Symlink for Codex's global layer

```bash
mkdir -p ~/.codex                       # ln fails if ~/.codex doesn't exist yet (Codex never run)
TARGET="$HOME/.claude/CLAUDE.md"
if [ -L ~/.codex/AGENTS.md ]; then
  # already a symlink — but a STALE one pointing elsewhere won't self-heal; repoint it
  [ "$(readlink ~/.codex/AGENTS.md)" = "$TARGET" ] || ln -sf "$TARGET" ~/.codex/AGENTS.md
elif [ -s ~/.codex/AGENTS.md ]; then
  echo "~/.codex/AGENTS.md is a real non-empty file — do NOT clobber it."
  echo "To keep BOTH: merge its content into ~/.claude/CLAUDE.md, then replace it with the symlink;"
  echo "or leave it as-is and accept that Codex's global layer won't pick up CLAUDE.md."
else
  rm -f ~/.codex/AGENTS.md; ln -s "$TARGET" ~/.codex/AGENTS.md   # absent or 0-byte placeholder
fi
```

This makes Codex's **global** instruction layer inject the exact same file Claude Code reads. (Codex resolves docs along `~/.codex → git-root → cwd`; `~/.codex/AGENTS.md` is the global slot.)

## config.toml — defeat the 32 KiB truncation

Codex's `project_doc_max_bytes` is **one combined budget across the whole AGENTS.md hierarchy** (not per-file), defaulting to **32768** (32 KiB). A global CLAUDE.md larger than that loses its **tail** in Codex (silently) — and also starves any repo-level `AGENTS.md` of budget. Add to `~/.codex/config.toml` (**create the file if absent**; if the key is already set to a smaller value, **raise** it):

```toml
project_doc_max_bytes = 98304   # 96 KiB, or larger than your CLAUDE.md
```

**If CLAUDE.md is already < 32 KiB**, skip this step (and the Phase 5 back-half grep) — there's no tail to lose. Either way, keep the `# User context` section within the first 32 KiB so even an unconfigured Codex still gets the hardcore.

## Fix the governance rule (don't leave it contradicting itself)

If a CLAUDE.md "where does knowledge go" rule says "user preferences → memory", it now contradicts this migration. Update it to add the tool-agnostic tier:

> Cross-tool user profile / preferences / methodology → `~/.claude/references/user/` (tool-agnostic, Codex reads it via the symlink). Temporary handoff → memory.

When you edit the **table row**, also fix the **judgment sentence** in the same section (the "ask: would a teammate need it? yes→docs, no→memory" prose). They drift apart if you only touch the obvious one — grep the whole section after editing.
