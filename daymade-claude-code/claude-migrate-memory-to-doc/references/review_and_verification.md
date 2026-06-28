# Multi-Agent Review + Empirical Verification

## Phase 3 — four parallel review agents

Spawn all four in **one message** (multiple Task calls) so they run concurrently. Give each: the source memory dir, the new references, and the changed CLAUDE.md. Tell each to **cite real file/line evidence, not guesses**, and that its output is a hypothesis for you to filter.

Copy-pasteable prompt skeletons (fill in `<paths>`):

```
[Content completeness] Read every memory file under <memory-dir> and every new file under ~/.claude/references/user/. Diff them: did any fact (number, date, war-story, how-to-apply item) get dropped or altered in the condensing? Return a coverage matrix (each memory → which reference) + a lost/weakened list with quoted evidence. Cite file:line.

[Cross-reference breakage] grep all of <memory-dir> for [[wikilinks]]. Report only TRUE breaks: a link FROM a file that will survive, pointing AT a file that will be deleted. (Links between two to-be-deleted files vanish together — not a break.) Also verify the new references' internal pointers resolve. Give grep evidence.

[Tool-agnostic link integrity] Verify: (a) readlink ~/.codex/AGENTS.md resolves to ~/.claude/CLAUDE.md and the target exists; (b) the CLAUDE.md "User context" pointer paths all exist; (c) whether Codex actually reads reference CONTENT or only the inlined CLAUDE.md text — check Codex's official AGENTS.md docs + ~/.codex/config.toml. Report what would silently fail to load.

[Duplication / drift] Does any reference duplicate a rule already in CLAUDE.md? Full-text duplication across files is a drift source. A DELIBERATE inline (the hardcore, with a stated reason) is NOT — don't flag it. List each duplication with both locations.
```

**Filter findings** before acting and before reporting to the user: probability × cost × does-this-actually-happen-in-the-user's-setup. Don't forward raw agent output.

## Phase 5 — verify by RUNNING codex (the protocol)

Reasoning "the symlink is correct, so Codex must see it" is **not** verification. Run it. The command block below was empirically verified (2026-06): every line ran clean on a real machine.

**Preconditions**: codex installed and authenticated. If `command -v codex` is empty, **skip Phase 5 entirely** — the `references/` + inline-CLAUDE.md work still stands; just note that wiring Codex later needs the symlink + `project_doc_max_bytes`.

```bash
CODEX=$(command -v codex || echo /Applications/Codex.app/Contents/Resources/codex)  # mac fallback; on Linux/WSL codex is just on PATH, no Codex.app

# Run from ANY dir. --skip-git-repo-check is REQUIRED: codex exec refuses to run outside a
# git repo by default (exit 1: "Not inside a trusted directory"), and migrating GLOBAL memory
# is naturally done from ~ — a non-repo dir. A neutral dir is also the cleaner test (no repo AGENTS.md noise).
"$CODEX" exec --skip-git-repo-check "Reply with exactly: ok. Do not run any tool." 2>&1 | tee /tmp/cx-verify.txt | tail -3

# Extract the session id from the HEADER. It is NOT in the tail — do NOT pipe the capture through `tail`.
# sed is POSIX; avoid grep -P \K (macOS BSD grep has no -P).
SID=$(grep "session id:" /tmp/cx-verify.txt | head -1 | sed -E 's/.*session id: ([0-9a-f-]{36}).*/\1/')

# Match the rollout by FULL UUID — never by `find ... -printf '%T@' | sort` (mtime returns an
# already-open OLDER session, a real trap that wastes a verification cycle).
NEW=$(find ~/.codex/sessions -name "rollout-*$SID*.jsonl")

grep -c "User context" "$NEW"                                  # inlined hardcore section — EXPECT: 1
grep -c "<a string that appears ONLY in your global CLAUDE.md>" "$NEW"   # whole-file injection — EXPECT: 1
# 32 KiB check — ONLY if CLAUDE.md > 32 KiB. Pick a heading you KNOW sits in the file's SECOND half
# (not a fixed line number — that's tied to one file's size):
grep -c "<a heading from the back half of your CLAUDE.md>" "$NEW"   # 0 → truncation; raise project_doc_max_bytes, re-run
```

**What a passing run prints** (so you know success when you see it):

```
1     ← User context inlined section is present
1     ← whole global CLAUDE.md was injected
1     ← back half present  (skip this line entirely if CLAUDE.md < 32 KiB)
```

Interpretation:

| inlined section | back-of-file string | meaning |
|---|---|---|
| 1 | 1 | full injection works — done |
| 1 | 0 | 32 KiB truncation (front survived because the section is near the top). Raise `project_doc_max_bytes`, re-run |
| 0 | 0 | the symlink / global layer isn't wiring up. Re-check `readlink ~/.codex/AGENTS.md`, that the target exists, and that codex's `project_doc_fallback_filenames` includes `CLAUDE.md` |

Caveats:
- **CLAUDE.md < 32 KiB**: skip the back-half grep (there is no back half) and skip the `project_doc_max_bytes` config edit. Only the `User context` check applies.
- **`codex exec --ephemeral`** (or a no-persist config) writes no rollout file → grep finds nothing even on success. Use a normal persisted session.
- Match only with the **full** UUID; a partial id can collide with another session.

This is empirical proof, captured in seconds, that beats any amount of "it should work". Do this yourself — never tell the user "you can check the log next time".

## Note: `project_doc_max_bytes` is a combined budget

It is **one shared budget across the whole AGENTS.md hierarchy** (root → git-root → cwd), decremented file by file and truncating each as the budget runs out — **not** a per-file cap (the official config-reference's "Maximum bytes read from AGENTS.md" wording is misleading; the source is the truth). For the common topology (one big global CLAUDE.md) the practical effect is "its tail is dropped" — but it also means an oversized global file **starves repo-level `AGENTS.md`** of budget entirely. Raising the limit fixes both.
