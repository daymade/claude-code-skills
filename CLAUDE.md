# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a Claude Code skills marketplace containing production-ready skills organized in a plugin marketplace structure. Most plugins expose one skill for narrow installs; suite plugins expose related skills under shared namespaces for combined installation workflows.

**Essential Skill**: `skill-creator` is the most important skill in this marketplace - it's a meta-skill that enables users to create their own skills. Always recommend it first for users interested in extending Claude Code.

## Skills Architecture

### Directory Structure

Each skill follows a standard structure:
```
skill-name/
├── SKILL.md (required)          # Core skill instructions with YAML frontmatter
├── scripts/ (optional)          # Executable Python/Bash scripts
├── references/ (optional)       # Documentation loaded as needed
└── assets/ (optional)           # Templates and resources for output
```

### Progressive Disclosure Pattern

Skills use a three-level loading system:
1. **Metadata** (name + description in YAML frontmatter) - Always in context
2. **SKILL.md body** - Loaded when skill triggers
3. **Bundled resources** - Loaded as needed by Claude

## Development Commands

### Installation Scripts

**In Claude Code (in-app):**
```text
/plugin marketplace add daymade/claude-code-skills
```

Then:
1. Select **Browse and install plugins**
2. Select **daymade/claude-code-skills**
3. Select **daymade-skill**
4. Select **Install now**

**From your terminal (CLI):**
```bash
# Automated installation (macOS/Linux)
curl -fsSL https://raw.githubusercontent.com/daymade/claude-code-skills/main/scripts/install.sh | bash

# Automated installation (Windows PowerShell)
iwr -useb https://raw.githubusercontent.com/daymade/claude-code-skills/main/scripts/install.ps1 | iex

# Manual installation
claude plugin marketplace add https://github.com/daymade/claude-code-skills
# Marketplace name: daymade-skills (from marketplace.json)
claude plugin install daymade-skill@daymade-skills
```

### Skill Validation and Packaging

Behavior evaluation is risk-scaled by `daymade-skill:skill-creator`: bounded fixes use targeted deterministic checks and narrow instruction changes use at most one or two sampled replays. Tier 3 classifies broad/high-risk work but does not authorize paired baselines, agent fan-out, grading, benchmarking, or a viewer; an explicit user request or a decision-bearing plan plus opt-in passes the separate evidence-budget gate without changing the risk tier. A request to "optimize" an existing skill and a long preceding conversation do not by themselves trigger Tier 3 or conversation-mining. Before editing, classify each delta: only behavior-equivalent relocation/deduplication is compression; retirement, scope narrowing, workflow/safety redesign, and bug fixes are separate changes. Existing-skill regression, one bounded fresh-context review with a declared stopping rule, and packaging gates remain separate.

Treat `daymade-skill/skill-creator/scripts/packaging_policy.py` as the shipping-policy SSOT. Add or remove shipping exclusions only there, require every consumer to import it, and do not copy its directory list into documentation or consumer-specific filters.

```bash
# Quick validation of a skill
cd daymade-skill/skill-creator && uv run --with PyYAML python -m scripts.quick_validate ../skill-name

# Existing-skill old-vs-new audit (use git-ref:<ref> for a Git-reconstructed baseline)
cd daymade-skill/skill-creator && uv run --with PyYAML python -m scripts.audit_skill_regression snapshot --source ../skill-name --output <old-bundle>
cd daymade-skill/skill-creator && uv run --with PyYAML python -m scripts.audit_skill_regression compare --before <old-bundle> --after ../skill-name --output <review.json> --baseline-origin pre-edit-snapshot
cd daymade-skill/skill-creator && uv run --with PyYAML python -m scripts.audit_skill_regression verify --before <old-bundle> --after ../skill-name --review <review.json>

# Package a skill (every existing skill requires the completed review; marker alone is insufficient)
cd daymade-skill/skill-creator && uv run --with PyYAML python -m scripts.package_skill ../skill-name [output-dir] [--regression-review <review.json>]

# Initialize a new skill from template
uv run python daymade-skill/skill-creator/scripts/init_skill.py <skill-name> --path <output-directory>
```

### Automated Test Suites (CI)

A `tests/` directory under a skill does **not** automatically run in CI. The
"Registered test suites (Linux)" GitHub Actions job only runs directories
explicitly listed in `scripts/ci/test-suites.txt` — that file's header is the
SSOT for the admission criteria (stdlib-only, no network/credentials,
deterministic, Linux-verified) and the runner types (`python-unittest` via
`unittest discover`, `node-test`). Adding a test file to an unregistered
`tests/` directory gives you a suite you can run locally, not CI coverage —
check the registry before assuming otherwise, and note `unittest discover`
only collects `unittest.TestCase` subclasses, not bare pytest-style functions.

### Prior Work Retrieval Boundary

`prior-work-retrieval` creates an obligation only for an explicit prior-work,
reuse, or history request. Ordinary implementation, reports, and read-only
inspection do not arm it; PreToolUse and Stop may enforce only a requirement
already created by the current prompt. Detailed retrieval mechanics remain in
`daymade-claude-code/prior-work-retrieval/SKILL.md`.

### WeCom Send Boundary

WeCom sender skills must read an explicit target class. `self` may send to the
user's own delivery channel without authorization; `others` requires the exact
label and message at a human confirmation gate. Unknown target identity fails
fast. Automatic self delivery also requires the config-bound sender path and
digest; a matching basename is not identity. A pending item is not a delivery
receipt, and an automatic outbox path gets one non-retrying HTTP attempt.

### Testing Skills Locally

Test from the canonical checkout, not from a mutable direct copy. Use the current
`claude-switch-models-setup` local-source workflow for this maintainer machine,
and use `daymade-skill:skill-governance` to verify source, installed state,
discovery policy, and the fresh model-visible catalog. Do not blindly remove and
re-add a marketplace: removing it uninstalls plugins installed from that
marketplace. Do not `cp -r` a second Skill tree into a user Skill directory; that
copy immediately creates an independent drift owner.

Marketplace source inventory is not Codex activation policy. On a maintainer
machine, the explicit selection in
`~/.config/claude-switch-models-setup/codex-active-skills.json` is the SSOT for
source Skills linked into `~/.agents/skills`; `~/.codex/skills` is only a bounded
legacy-compatibility surface. Change the manifest and run the bundled syncer—do
not restore bulk links in either user root. Detailed topology and recovery rules
remain in
`daymade-claude-code/claude-switch-models-setup/references/local-source-sync-architecture.md`.

In Claude Code, use `/plugin ...` slash commands. In your terminal, use `claude plugin ...`.

### Source Location Guard for Skill Edits

Before editing an existing skill, verify the **source** path, not just the path currently loaded by Codex / Claude Code.

Treat these as installed copies unless proven otherwise:
- `~/.codex/skills/<skill-name>`
- `~/.claude/skills/<skill-name>`
- `~/.agents/skills/<skill-name>`
- `~/.claude/plugins/cache/...`
- `~/.codex/plugins/cache/...`

The source for this marketplace is this repository. For single-skill plugins, edit:
```bash
<repo-root>/<skill-name>/SKILL.md
```

For suite skills, edit:
```bash
<repo-root>/<suite-name>/<skill-name>/SKILL.md
```

Required workflow before any skill edit:
```bash
pwd
git rev-parse --show-toplevel
rg -n '"name": "<skill-or-suite-name>"' .claude-plugin/marketplace.json
find . -path '*/SKILL.md' -maxdepth 4 | rg '(^|/)<skill-name>/SKILL.md$'
```

If the user gives a source path, use that path. If the available skill list points to a different installed copy, update the source first, then sync the installed copy only if the user explicitly needs the current session to use the new version immediately.

### Git Operations

This repository uses standard git workflow, but **always stage files by name**,
never `git add -A` / `git add .`. Multiple agents may have unstaged changes in
the same worktree — a blanket stage piggybacks their work into your commit:

```bash
git status
git add path/to/file1 path/to/file2   # specific files only
git commit -m "message"
git push
```

For recovery or repository convergence under concurrent work, treat
`git-safety-net/SKILL.md` as the canonical authorization and evidence router. It owns the
change-authorized / inspect-only / excluded partition and the scoped-vs-exhaustive audit boundary;
do not copy its detailed commands here or treat a visible collaborator ref/worktree as a cleanup
target merely because it appears in the inventory.

**Closing a PR unmerged (declined, or superseded by another PR) → delete its head
branch in the same action.** `gh pr merge --delete-branch` only covers merged PRs.
⚠️ Deleting the branch does NOT remove `refs/pull/<N>/head` — GitHub keeps serving
that ref, so the commits remain publicly fetchable by anyone who fetches it, and the
branch listing (plus the weekly `stale-branch-watch`, which only sees branch refs)
loses sight of the residue. Branch deletion closes the *discoverable* surface, which
is still worth doing at close time. But if the content needs **sanitizing**, branch
deletion alone is cosmetic — first move the pull ref to a sanitized commit (reopen
the PR → push the fix → close again; pushes do not move a *closed* PR's ref), then
delete the branch, and accept that the old SHAs stay addressable from GitHub's object
cache until GC — a guaranteed purge requires a GitHub support ticket. (2026-08-17: a
closed-superseded PR's branch carried an unsanitized fixture for 13 days after the
fix was written; the pull ref had to be moved via the reopen dance before deletion.)

### Local `main` Is a Read-Only Mirror

Squash-merged PRs rewrite commits under new SHAs, so every direct commit to
local `main` guarantees divergence the moment its PR merges. Two rules keep
`main` clean:

1. **Never commit directly to local `main`.** All work starts on a feature
   branch (`git checkout -b <topic>`), ships via PR, and lands by squash merge.
2. **After every merge, run the 30-second ritual:** `git checkout main && git pull --ff-only`.
   A successful ff-only pull proves nobody broke rule 1. If it fails, someone
   committed to local `main` — inspect `git log origin/main..main` and rebase
   the stray commits onto a feature branch; do not merge or force-push `main`.
3. **If step 2's `git checkout main` itself refuses** ("local changes would be
   overwritten") while you're still on your feature branch: this is not
   automatically the divergence case above. Check whether local `main` is
   merely **stale** (nobody committed to it, it just never got its ref
   updated after a previous merge) before assuming divergence — `git diff
   HEAD origin/main -- <the-file>` from your feature branch; empty output
   means your branch's committed content already matches `origin/main`
   exactly, and the checkout conflict is purely local `main`'s ref being
   behind. Fix without touching the working tree or any other session's
   uncommitted changes: `git fetch origin main:main` (updates the ref
   directly, no checkout needed), then retry `git checkout main`. Only fall
   through to the divergence procedure below if the diff is non-empty.

If local `main` has already diverged: do not `reset --hard` until every stray
commit is proven superseded — mechanical test: cherry-pick them onto
`origin/main` resolving conflicts toward the upstream version; an empty net
result means the content already shipped. Back up first
(`git bundle create /tmp/main-backup.bundle main` and verify it restores).

## Skill Writing Requirements

### Writing Style

Use **imperative/infinitive form** (verb-first instructions) throughout all skill content:
- ✅ "Extract files from a repomix file using the bundled script"
- ❌ "You should extract files from a repomix file"

### YAML Frontmatter Requirements

Every SKILL.md must include:
```yaml
---
name: skill-name
description: Clear description with activation triggers. This skill should be used when...
---
```

### Privacy and Path Guidelines (Enforced by Pre-commit Hook)

Skills for public distribution must NOT contain:
- Absolute paths to user directories (`/home/username/`, `/Users/username/`)
- Personal usernames, company names, product names
- Phone numbers, personal email addresses
- OneDrive paths or environment-specific absolute paths
- Use relative paths within skill bundle or standard placeholders (`<workspace>/`, `<user_id>`)

**Five-layer defense system:**
1. **CLAUDE.md rules** (this section) — Claude avoids generating sensitive content
2. **Global PII Guard pre-commit hook** (`~/scripts/git-pii-guard/pre-commit`) — blocks staged PII/secrets and generated/local artifact paths
3. **Global PII Guard pre-push hook** (`~/scripts/git-pii-guard/pre-push`) — scans commits about to be pushed, catching bad local history before it hits GitHub
4. **gitleaks** (`.gitleaks.toml`) — deep scan with custom rules for this repo
5. **AI semantic read-through** (the gate the other four structurally cannot be) — layers 1-4 are keyword/regex/gitleaks: they only match patterns someone listed, and are blind to private content with **no keyword** — a real name in another language (gitleaks doesn't cover CJK), a verbatim line from a real transcript, a real example dropped into an illustration. Before publishing, **read the whole skill yourself and judge each concrete name/example/snippet semantically** ("generic placeholder / public entity, or lifted from a real project / person / transcript?"). A green scan is **not** a clean bill of health; "grep found nothing" only means your word list didn't fire. Method: [`daymade-skill/skill-creator/references/sanitization_checklist.md`](./daymade-skill/skill-creator/references/sanitization_checklist.md).

PII Guard is enabled via `~/scripts/git-pii-guard/manage.sh enable <repo-path>`, which sets `core.hooksPath` to `~/scripts/git-pii-guard`.
For repo-specific additions:
- `.pii-patterns` — extra content regexes
- `.pii-path-patterns` — extra forbidden path regexes
- `.pii-allowpaths` — explicit path allowlist exceptions
- `.pre-commit-config.yaml` — optional repo-local runner that wires `pre-commit` framework to the same path/content rules for contributors who prefer managed hooks
If it fires, fix the issue — do NOT use `--no-verify` to bypass.

### Content Organization

- Keep SKILL.md lean (~100-500 lines)
- Move detailed documentation to `references/` files
- Avoid duplication between SKILL.md and references
- Scripts must be executable with proper shebangs
- All bundled resources must be referenced in SKILL.md

## Marketplace Configuration

The marketplace is configured in `.claude-plugin/marketplace.json`:
- Contains plugin entries: single-skill plugins point `source` directly at the skill directory (no `skills` field); any plugin entry with a non-empty `skills` array is a suite and uses those relative paths for multi-skill routing
- Each plugin has: name, description, source, version, category, keywords
- Marketplace metadata: name, owner, version
- Single-skill plugins follow the official pattern: `source` points to the Skill directory and `skills` is omitted
- **All suite plugins are suite-only.** Derive the current suite set from non-empty `plugins[].skills`; do not maintain another name list here. Users install the suite and invoke members as `<suite>:<skill>`. When adding a member, update only the suite entry's `skills` array — do NOT create a parallel standalone plugin entry.

### Versioning Architecture

**Two separate version tracking systems:**

1. **Marketplace Version** (`.claude-plugin/marketplace.json` → `metadata.version`)
   - Tracks the marketplace catalog as a whole
   - Bump when: Adding/removing skills, adding/removing suite plugins, major marketplace restructuring
   - Semantic versioning: MAJOR.MINOR.PATCH

2. **Individual Skill Versions** (`.claude-plugin/marketplace.json` → `plugins[].version`)
   - Each skill has its own independent version
   - Example: ppt-creator v1.0.0, skill-creator v1.4.0
   - Bump when: Updating that specific skill
   - **CRITICAL**: Skills should NOT have version sections in SKILL.md

**Key Principle**: SKILL.md files should be timeless content focused on functionality. Versions are tracked in marketplace.json only.

### ⚠️ Updating Existing Skills (MANDATORY)

**Any commit that modifies a skill's files MUST bump that skill's version in `marketplace.json`.**

This applies when you change ANY file under a skill directory:
- `SKILL.md` (instructions, description, workflow)
- `references/` (documentation, principles, examples)
- `scripts/` (executable code)
- `assets/` (templates, resources)

**Version bump rules:**
- Content/doc updates (new sections, rewritten principles) → bump **MINOR** (1.0.1 → 1.1.0)
- Bug fixes, typo fixes → bump **PATCH** (1.0.1 → 1.0.2)
- Breaking changes (renamed commands, removed features) → bump **MAJOR** (1.0.1 → 2.0.0)

**Pre-commit check:** Before committing, run `git diff --name-only` and verify: for every `skill-name/` directory that appears, `marketplace.json` also has a version bump for that skill's `plugins[].version`.

## Available Skills

Current plugin names, versions, sources, and suite membership are defined only
in `.claude-plugin/marketplace.json`. Use README.md / README.zh-CN.md for the
human-readable capability guide; do not maintain another numbered Skill snapshot
in this model-loaded file.

## YouTube Downloader SOP (Internal)

See [youtube-downloader/references/internal-sop.md](./youtube-downloader/references/internal-sop.md) for yt-dlp troubleshooting steps (PO tokens, proxy, cookies, etc.).

## Python Development

All Python scripts in this repository:
- Use Python 3.10+ syntax
- Include shebang: `#!/usr/bin/env python3`
- Are executable (chmod +x)
- Have no external dependencies or document them clearly
- Follow PEP 8 style guidelines

## Quality Standards

Before submitting or modifying skills:
- Valid YAML frontmatter with required fields
- Description includes clear activation triggers
- All referenced files exist
- Scripts are executable and tested
- No absolute paths or user-specific information
- Comprehensive documentation
- No TODOs or placeholders

## Skill Creation Workflow

When creating a new skill:
1. Understand concrete usage examples
2. Plan reusable contents (scripts/references/assets)
3. Initialize using `init_skill.py`
4. Edit SKILL.md and bundled resources
5. Package using `package_skill.py` (auto-validates)
6. Iterate based on testing feedback

## Adding a New Skill to Marketplace

For the full step-by-step guide with templates and examples, see [references/new-skill-guide.md](./references/new-skill-guide.md).

**Files to update** (all required):

| File | Locations to update |
|------|-------------------|
| `.claude-plugin/marketplace.json` | metadata.version + metadata.description + new plugin entry |
| `CHANGELOG.md` | New version entry |
| `README.md` | Review the user-facing surfaces for this skill: description, install command, unnumbered skill section, use case, docs link, requirements. Do not persist marketplace-version, skill-count, or catalog-position values; derive them from the manifest when needed. |
| `README.zh-CN.md` | Same as above, translated |
| `CLAUDE.md` | Stable manifest/README authority pointer only; do not reintroduce a numbered Skill snapshot |
| `<skill-directory>/` | Canonical Skill source; disposable `.skill` packages stay outside the source tree |

**Quick workflow**:
```bash
# 1. Validate & package the skill itself
SKILL_DIR="<repo-root>/<skill-directory>"
cd <repo-root>/daymade-skill/skill-creator
uv run --with PyYAML python -m scripts.security_scan "$SKILL_DIR" --verbose
uv run --with PyYAML python -m scripts.package_skill "$SKILL_DIR" <output-dir>

# 2. Update all files listed above (see references/new-skill-guide.md for the
#    detailed step-by-step)

# 3. One-shot marketplace validation (ships with marketplace-dev skill)
cd <repo-root>
bash daymade-claude-code/marketplace-dev/scripts/check_marketplace.sh .
# Runs: JSON syntax → claude plugin validate → source+skills resolution →
# reverse sync (warns when a disk SKILL.md is not registered). A WARN on
# reverse sync is the canary for orphan skills — register them or delete them.
# Then verify the human-facing README catalogs and CLAUDE.md authority pointer:
python3 daymade-claude-code/marketplace-dev/scripts/check_doc_skill_lists.py
# Rejects missing/ghost README entries, numbered headings, copied version badges,
# and a model-loaded CLAUDE.md Skill snapshot.

# 4. Stage specific files by name, never `git add -A` or `git add .`
#    (a parallel agent once piggybacked another session's unstaged changes
#    into its commit via `git add -A`; the fix is to stage explicitly)
git add .claude-plugin/marketplace.json CHANGELOG.md README.md README.zh-CN.md \
        CLAUDE.md <skill-directory>/
git commit -m "Release vX.Y.0: Add skill-name"
git push

# 5. Release
gh release create vX.Y.0 --title "Release vX.Y.0: Add skill-name" --notes "..."
```

**Top mistakes**: Forgetting to push to GitHub, forgetting README.zh-CN.md, inconsistent version numbers across files, leaving an orphan SKILL.md on disk unregistered (caught by `check_marketplace.sh` reverse sync), using `git add -A` in a repo where multiple agents may have unstaged changes.

## Chinese User Support

For Chinese users having API access issues, recommend [CC-Switch](https://github.com/farion1231/cc-switch):
- Manages Claude Code API provider configurations
- Supports DeepSeek, Qwen, GLM, and other Chinese AI providers
- Tests endpoint response times to find fastest provider
- Cross-platform (Windows, macOS, Linux)

See README.md section "🇨🇳 中文用户指南" for details.

## Handling Third-Party Marketplace Promotion Requests

Decline all third-party marketplace promotion requests. For policy, response template, and precedents, see [references/promotion-policy.md](./references/promotion-policy.md).

## External Contributor PRs (Curation Policy)

**Policy SSOT: [CONTRIBUTING.md](./CONTRIBUTING.md)** — this is a curated marketplace of our own skills; bug fixes are welcome, new-skill PRs are not accepted.

Agent rules when an external PR appears:

- **Never merge external PRs unilaterally.** Every external-PR merge decision goes to the user first, no matter how small or obviously-correct the fix looks. (2026-07-19: an agent batch-merged 4 external PRs under an ambiguous "merge what's left" instruction, including a whole new contributor skill the policy would never have accepted — it had to be reverted. Ambiguous instruction + other people's work = ask first, always.)
- **Bug-fix PRs** (after the user approves): land the repo bookkeeping as a maintainer follow-up — version bump in `marketplace.json`, CHANGELOG entry, README sync where applicable. Contributor PRs usually lack these.
- **New-skill PRs**: close with the standing message in CONTRIBUTING.md.

## Best Practices Reference

Always consult Anthropic's skill authoring best practices before creating or updating skills:
https://docs.claude.com/en/docs/agents-and-tools/agent-skills/best-practices.md

## Plugin and Skill Architecture

For full architecture documentation (core concepts, installation flow, data flow, common misconceptions, best practices), see [references/plugin-architecture.md](./references/plugin-architecture.md).

## Plugin and Skill Troubleshooting

For systematic debugging steps (common errors, debugging process, pitfalls, real-world examples), see [references/plugin-troubleshooting.md](./references/plugin-troubleshooting.md).

**Quick fix for most issues**: Commit → push → `claude plugin marketplace update daymade-skills` → retry install.
