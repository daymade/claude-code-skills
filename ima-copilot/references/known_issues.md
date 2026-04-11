# Known Issues in Upstream ima-skill

This file is the **source of truth** for every upstream bug that ima-copilot can detect and help repair. Each issue has a stable ID, a plain-language explanation, at least one repair strategy, and exact commands the agent can execute on user consent.

## How the agent should use this file

When `scripts/diagnose.sh` reports a `⚠️` line that mentions `ISSUE-<NNN>`, look up that issue below, then:

1. Explain to the user — in plain language — what's broken and why it matters to them.
2. If the issue has more than one repair strategy, use **AskUserQuestion** to present the choices. Describe each option by its outcome, not its mechanism.
3. After the user picks a strategy, execute the exact commands under that strategy. Every command backs up the original file to `/tmp/ima-copilot-backups/<timestamp>/<relative-path>` first.
4. Re-run `diagnose.sh` and show the before/after. The warning should flip to ✅.
5. Remind the user that upstream upgrades replace these files, so reruns after an upgrade are expected — and safe.

## Issue registry

### ISSUE-001 — Submodule SKILL.md files missing YAML frontmatter

**Status**: Observed on recent upstream releases. No public issue tracker for the upstream package, so there's no link to watch. When the `diagnose.sh` scanner stops flagging this issue against a freshly-installed upstream release, it has been fixed upstream and this entry can be closed.

**Symptom**: Running an ima-skill-enabled session on Codex produces:

```
⚠ Skipped loading 2 skill(s) due to invalid SKILL.md files.
⚠ <path>/ima-skill/notes/SKILL.md: missing YAML frontmatter delimited by ---
⚠ <path>/ima-skill/knowledge-base/SKILL.md: missing YAML frontmatter delimited by ---
```

Claude Code's skill loader is more permissive and usually does not emit a warning, but the files still violate the documented SKILL.md format and will fail under any stricter loader that enters the ecosystem.

**Root cause**: The upstream package ships `ima-skill/notes/SKILL.md` and `ima-skill/knowledge-base/SKILL.md` that begin directly with `# Notes (笔记)` and `# Knowledge Base (知识库)` — no `---` YAML frontmatter block.

**Original design intent**: Read the root `ima-skill/SKILL.md`. Its "模块决策表" explicitly says `读取 notes/SKILL.md` or `读取 knowledge-base/SKILL.md` — the upstream author meant these files as *module documentation referenced from the root*, not as independently-loadable skills. The problem is simply that they chose `SKILL.md` as the filename, which any standard skill loader recursively discovers and tries to register.

**Impact if left unfixed**:
- On Codex and other strict loaders: submodule content is silently dropped from the loaded skill, so note-search and knowledge-base-search instructions never reach the agent at runtime.
- On Claude Code: usually no user-visible error, but the skill directory still contains two files that violate the published SKILL.md format.

**Why upstream probably hasn't fixed it**: The upstream package is developed primarily against OpenClaw's loader, which appears to tolerate the missing frontmatter. The bug is invisible from the upstream maintainer's primary testing platform.

**How to explain it to the user** (plain language):

> The official IMA skill package has two helper files inside (one for notes, one for knowledge base) that are missing a small technical header. On Codex, this makes the whole note-search and knowledge-base-search features silently fail to load — you won't see an error in your workflow, you'll just notice searches not working. On Claude Code it usually just prints a warning at startup. We can fix this in one of two ways; both are reversible.

**Important — symlink sharing across agents**:

`npx skills add` in its default mode installs to the first detected agent as a canonical directory and symlinks the remaining agents to it. `scripts/diagnose.sh` detects this sharing automatically and reports `ℹ️ claude-code and codex share the same install via symlink (canonical: ...)`. When this happens:

- **Only run the repair once**, against any one of the shared agent paths. The fix propagates through the symlink graph to every other agent instantly.
- The diagnose report groups its ISSUE lines by canonical directory, so you'll see 2 warnings (one per submodule file), not 4.
- The backup step saves the canonical files once — restoring from backup also propagates to every agent via the same symlink graph.

If `npx skills add` was run with `--copy` (or if the user manually desynced the installs), each agent has its own copy and the repair must be applied separately to each. Diagnose will report this by showing the ISSUE lines without a prior "share via symlink" line.

**Repair strategies**:

#### Strategy A — Rename submodule files to `MODULE.md` (recommended)

Respects the upstream design intent ("these are module documentation, not sub-skills") by renaming them so no loader tries to register them as independent skills. Requires a one-line patch to the root `SKILL.md` so its internal references still resolve.

**What this strategy changes**:
- `<install>/notes/SKILL.md` → `<install>/notes/MODULE.md`
- `<install>/knowledge-base/SKILL.md` → `<install>/knowledge-base/MODULE.md`
- `<install>/SKILL.md` — one `sed` to rewrite internal references from `notes/SKILL.md` → `notes/MODULE.md` and `knowledge-base/SKILL.md` → `knowledge-base/MODULE.md`

**Commands** (agent executes after user consent; replace `<install>` with the specific agent path from `diagnose.sh`):

```bash
# Use `command cp` / `command mv` to bypass any user-defined shell aliases
# (e.g. `alias mv='mv -i'`). Interactive-mode aliases will otherwise hang the
# script on an "overwrite?" prompt since this flow runs non-interactively.

# 1. Back up originals (each cp is guarded so reruns don't emit "file not found")
BACKUP="/tmp/ima-copilot-backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP"
[ -f "<install>/SKILL.md" ] && \
  command cp "<install>/SKILL.md" "$BACKUP/SKILL.md"
[ -f "<install>/notes/SKILL.md" ] && \
  command cp "<install>/notes/SKILL.md" "$BACKUP/notes-SKILL.md"
[ -f "<install>/knowledge-base/SKILL.md" ] && \
  command cp "<install>/knowledge-base/SKILL.md" "$BACKUP/knowledge-base-SKILL.md"
echo "backup saved to: $BACKUP"

# 2. Rename submodule files (skip if already renamed — idempotent)
[ -f "<install>/notes/SKILL.md" ] && \
  command mv "<install>/notes/SKILL.md" "<install>/notes/MODULE.md"
[ -f "<install>/knowledge-base/SKILL.md" ] && \
  command mv "<install>/knowledge-base/SKILL.md" "<install>/knowledge-base/MODULE.md"

# 3. Patch root SKILL.md references (idempotent — no-op if already patched).
# `command sed` and `command rm` bypass any user-defined shell aliases like
# `alias sed='sed -i'` or `alias rm='rm -i'` that would otherwise hang the
# script on a prompt or misinterpret the -i flag.
command sed -i.bak \
  -e 's|notes/SKILL\.md|notes/MODULE.md|g' \
  -e 's|knowledge-base/SKILL\.md|knowledge-base/MODULE.md|g' \
  "<install>/SKILL.md"
command rm -f "<install>/SKILL.md.bak"
```

**Rollback** (if the user later wants to undo):

```bash
command cp "$BACKUP/SKILL.md"                   "<install>/SKILL.md"
command cp "$BACKUP/notes-SKILL.md"             "<install>/notes/SKILL.md"
command cp "$BACKUP/knowledge-base-SKILL.md"    "<install>/knowledge-base/SKILL.md"
command rm -f "<install>/notes/MODULE.md" "<install>/knowledge-base/MODULE.md"
```

**Pros**: Honors the upstream author's original design. Minimizes the total set of files in the skill namespace. No risk of loader collision between the root skill and the two submodule "sub-skills".

**Cons**: Diff is slightly larger (3 files touched). If upstream later decides to fix the bug with Strategy B, the user's rename will diverge from upstream's version until the next install.

#### Strategy B — Add minimal frontmatter to the submodule files

Leaves file names alone. Prepends a 4-line YAML frontmatter block to each submodule file so strict loaders accept them. Technically creates two "sub-skills" named `ima-skill-notes` and `ima-skill-knowledge-base` which will appear in some UIs.

**What this strategy changes**:
- `<install>/notes/SKILL.md` — prepend frontmatter
- `<install>/knowledge-base/SKILL.md` — prepend frontmatter

**Commands**:

```bash
# Use `command cp` / `command mv` to bypass interactive-mode shell aliases
# (e.g. `alias mv='mv -i'`) that would otherwise hang the script.
BACKUP="/tmp/ima-copilot-backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP"
[ -f "<install>/notes/SKILL.md" ] && \
  command cp "<install>/notes/SKILL.md" "$BACKUP/notes-SKILL.md"
[ -f "<install>/knowledge-base/SKILL.md" ] && \
  command cp "<install>/knowledge-base/SKILL.md" "$BACKUP/knowledge-base-SKILL.md"
echo "backup saved to: $BACKUP"

# Idempotent prepend — skip if the file already starts with ---
prepend_frontmatter() {
  local file="$1"
  local name="$2"
  local desc="$3"
  if head -n 1 "$file" | grep -q '^---$'; then
    echo "already has frontmatter: $file"
    return 0
  fi
  local tmp
  tmp=$(mktemp)
  {
    printf -- '---\n'
    printf -- 'name: %s\n' "$name"
    printf -- 'description: %s\n' "$desc"
    printf -- '---\n\n'
    cat "$file"
  } > "$tmp"
  command mv "$tmp" "$file"
}

prepend_frontmatter \
  "<install>/notes/SKILL.md" \
  "ima-skill-notes" \
  "IMA notes submodule. Read via the root ima-skill module decision table."

prepend_frontmatter \
  "<install>/knowledge-base/SKILL.md" \
  "ima-skill-knowledge-base" \
  "IMA knowledge-base submodule. Read via the root ima-skill module decision table."
```

**Rollback**:

```bash
command cp "$BACKUP/notes-SKILL.md"          "<install>/notes/SKILL.md"
command cp "$BACKUP/knowledge-base-SKILL.md" "<install>/knowledge-base/SKILL.md"
```

**Pros**: Smallest possible diff. Exact commands that Codex's first-pass fix used. Easiest to recreate from memory if the user loses the script.

**Cons**: Creates two new skill identifiers in the loader's registry. On some agents, those names become visible as separate skills in menus, which can confuse users and — in the worst case — accidentally trigger the submodule on its own instead of going through the root ima-skill flow.

#### Strategy skip — Leave the file alone

Valid when the user is only running on Claude Code and does not care about the startup warning (which is typically invisible without log inspection). Not recommended if the user ever runs the same install on Codex.

## Adding new issues to this file

When we discover a new upstream bug:

1. Assign the next sequential `ISSUE-<NNN>` number.
2. Fill in the same sections: symptom, root cause, impact, plain-language explanation, at least one strategy with idempotent + reversible commands.
3. Update `scripts/diagnose.sh` to detect it (still read-only) and print a line with the same issue ID.
4. **Do not** add the fix commands into any shipped script — keep them in this file so the agent reads and executes them at runtime under user consent. This preserves the contract: we ship instructions, not patches.
