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

Skills use progressive loading:
1. **Metadata** (name + description in YAML frontmatter) - Advertised according to the host's discovery policy and catalog budget; verify the fresh host rather than assuming every description is present
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

Use [skill-creator](daymade-skill/skill-creator/SKILL.md) before creating or
changing a skill. It owns change classification, evidence selection, regression
review, validation, initialization, and packaging.

Treat [packaging_policy.py](daymade-skill/skill-creator/scripts/packaging_policy.py)
as the canonical inclusion policy for packaging, security attestation, source
audits, and version checks. Keep consumers on this shared implementation. Preserve the recorded policy
when verifying an existing baseline; consult
[source snapshot archives](daymade-skill/skill-creator/references/source-snapshot-archives.md)
before archiving or restoring it.

For hook loop and reminder semantics, load
`daymade-claude-code:claude-code-hooks` and follow rule 7. Keep recurring
advisory injectors available for the whole session, using cadence/hysteresis
and reset semantics to limit frequency; never add a lifetime session cap.
Reserve repetition budgets for blocking remediation loops whose capped exit is
explicitly blocked, unshipped, or pending. Test advisory liveness across later
fully-due windows, and leave current thresholds in the owning implementation
rather than copying them into this file.

Synchronous Claude Code/Codex lifecycle hooks and background services
(LaunchAgents included) must call a fixed direct interpreter **owned by the
installer that writes it**. Do not register a Python entry point through a
package manager, generic interpreter dispatcher, or `.py` shebang lookup: a
shared environment/cache lock can stall every prompt or tool boundary, and a
bare `python3` resolves under launchd's minimal PATH to the Developer Tools
stub, which is old enough to reject syntax the script was written in. The
opposite error costs the same: resolving `sys.executable` bakes in a versioned
path another product owns, so the job dies silently when that product upgrades.
Own the literal path, the way `SYSTEM_GIT` is owned. Explicit maintenance,
retrieval, validation, and test commands may still use their declared `uv`
project; the runtime boundary is the rule. The concrete prior-work wrapper and
profile-converger registration live in their respective Skills rather than
being copied here.

Treat `daymade-skill/skill-creator` as a locked uv project. Run its bundled Python tools from that directory with `uv run --frozen`; the project-local `.venv` is isolated from caller projects while uv's shared cache supplies the pinned packages. Do not reintroduce per-call `--with` overlays for dependencies already in its `pyproject.toml`.

From the repository root, enter the locked tool project once and validate the
selected skill (replace `<skill-path>` with its absolute path):

```bash
cd daymade-skill/skill-creator
uv run --frozen python -m scripts.quick_validate <skill-path> --audience public
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

### Transcript Correction

Use [transcript-fixer](daymade-audio/transcript-fixer/SKILL.md) for transcript
correction. Its Native checklist owns the correction and finalization order;
[Native review packets](daymade-audio/transcript-fixer/references/native_review_packets.md)
owns split, batch, and resumed review instructions. Keep CLI parameters and
validation behavior in
[native_review.py](daymade-audio/transcript-fixer/scripts/native_review.py), and
queue anchor behavior in
[review_queue.py](daymade-audio/transcript-fixer/scripts/core/review_queue.py).
When changing these paths, update their owning instructions together; keep
review coverage, unresolved verdicts, and repository publication distinct.

### Prior Work Retrieval Boundary

`prior-work-retrieval` creates an obligation only for an explicit prior-work,
reuse, or history request. Ordinary implementation, reports, and read-only
inspection do not arm it; PreToolUse and Stop may enforce only a requirement
already created by the current prompt. Detailed retrieval mechanics remain in
`daymade-claude-code/prior-work-retrieval/SKILL.md`.

### Local Agent Messaging

For `peer-message`, treat `peer-message/scripts/peer.py` as the executable
contract and `peer-message/SKILL.md` as the runtime router and owner of stable
runtime prerequisites plus the peer-cannot-authorize safety boundary. Reply lookup,
transport and discovery details belong in `peer-message/references/protocol-and-discovery.md`;
current product availability, provenance, and inbound-control mechanics belong in
`peer-message/references/official-feature.md`; reply addressing, payload structure,
delivery-status language, what to do when you find another session's in-flight work on a
shared resource, and the verification contracts that decide what a peer assertion or a
peer denial is worth belong in
`peer-message/references/coordination-and-learning-loop.md`. Keep implementation, CLI help,
tests, and those owners aligned; README and changelog entries should point to
them instead of restating volatile protocol facts. The repository-wide
local-source activation contract below still applies—never hand-create Codex
Skill links.

### Codex Quota and Account Checks

For Codex reset announcements or account quota questions, enter
[tibo-reset-codex](tibo-reset-codex/SKILL.md). Follow its
[account usage SOP](tibo-reset-codex/references/account-usage.md) for authentication,
per-account verification and browser restoration. Treat
[query_usage.py](tibo-reset-codex/scripts/query_usage.py) as the executable authority
for query parameters, supported response fields and exit behavior. Keep detailed
commands and changing account state out of this file.

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

For maintainer source-backed activation, follow
[Local Source Sync Architecture](daymade-claude-code/claude-switch-models-setup/references/local-source-sync-architecture.md).
That reference owns the activation-manifest contract, host-specific selection,
legacy compatibility, and repair workflow. An approved whole-marketplace policy
includes newly registered members; a source checkout or registration alone does
not establish that policy. Do not hand-create user Skill links.

When delivery includes local availability, finish the source owner's dry-run/apply
and the [newly registered Skill gate](daymade-skill/skill-governance/references/skill-surface-governance.md#14-verify-a-newly-registered-skill).
Take expected identities from the requested change, not from links or a whitelist
that may already omit the new Skill. Keep installation/catalog evidence separate
from actual task results. A daemon using a pinned plugin copy also needs the
[pin-update workflow](daymade-claude-code/claude-switch-models-setup/references/troubleshooting.md#advance-the-pin).
Do not treat a merged source change as proof that this runtime advanced.

The syncer's managed marketplace identities, conventional checkout candidates,
and generated watch paths are owned by `sync-local-skill-sources.py`; derive them
from its constants/functions and `--print-watch-paths` output instead of copying
their current members or counts into instructions or references.

For context-window setting changes, keep the executable configuration and the
[context request probe](daymade-claude-code/claude-switch-models-setup/references/context-window-config.md)
aligned. That reference owns the request fields and probe commands.

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
git diff --cached --name-status       # every staged entry (`D` lines included) must be one you intended; a `D` you never made = drift from a parallel session's index-bypassing commit — see git-safety-net Mode D
git commit -m "message"
git push
```

For recovery or repository convergence under concurrent work, treat
`git-safety-net/SKILL.md` as the canonical authorization and evidence router. It owns the
change-authorized / inspect-only / excluded partition, the scoped-vs-exhaustive audit
boundary, and authorized temporary-backup retirement;
do not copy its detailed commands here or treat a visible collaborator ref/worktree as a cleanup
target merely because it appears in the inventory.

For GitHub-hosted state — PRs, issues, Actions, repository or organization settings, permissions,
and API/UI mutations — treat `github-ops/SKILL.md` as the canonical operating contract. A command
receipt is not completion; use that Skill's operation-specific independent readback. Keep detailed
GitHub SOPs there rather than copying them into this repository-level instruction file.

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
local `main` guarantees divergence the moment its PR merges. These rules keep
`main` clean:

`.githooks/pre-commit` and `.githooks/pre-push` dispatch to
`scripts/git-mainline-guard.mjs`, which rejects direct local-main work and stale
marketplace manifests or reused plugin versions against current main. The
dispatchers preserve the shared PII guard when it is installed. Activate this
repository **from the canonical primary main checkout** with
`git config core.hooksPath "$(pwd -P)/.githooks"`. The absolute path matters:
`core.hooksPath` is shared by linked worktrees, so a relative path would let a
stale feature worktree select its own stale dispatcher. CI and the GitHub main
ruleset independently require the same release checks on every PR.

1. **Never commit directly to local `main`.** All work starts on a feature
   branch (`git checkout -b <topic>`), ships via PR, and lands by squash merge.
2. **After every merge, run the post-merge ritual:** `git checkout main && git pull --ff-only`.
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

**Defense layers:**
1. **CLAUDE.md rules** (this section) — Claude avoids generating sensitive content
2. **Global PII Guard pre-commit hook** (`~/scripts/git-pii-guard/pre-commit`) — blocks staged PII/secrets and generated/local artifact paths
3. **Global PII Guard pre-push hook** (`~/scripts/git-pii-guard/pre-push`) — scans commits about to be pushed, catching bad local history before it hits GitHub
4. **gitleaks** (`.gitleaks.toml`) — deep scan with custom rules for this repo
5. **AI semantic read-through** — pattern-based scans only match patterns someone listed, and are blind to private content with **no keyword** — a real name in another language (gitleaks doesn't cover CJK), a verbatim line from a real transcript, a real example dropped into an illustration. Before publishing, **read the whole skill yourself and judge each concrete name/example/snippet semantically** ("generic placeholder / public entity, or lifted from a real project / person / transcript?"). A green scan is **not** a clean bill of health; "grep found nothing" only means your word list didn't fire. Method: [`daymade-skill/skill-creator/references/sanitization_checklist.md`](./daymade-skill/skill-creator/references/sanitization_checklist.md).

Most repositories enable PII Guard via `~/scripts/git-pii-guard/manage.sh enable <repo-path>`. This repository instead points `core.hooksPath` at the canonical primary checkout's absolute `.githooks` directory: its versioned dispatchers run the repository mainline guard and then delegate to the same shared PII guard when installed.
For repo-specific additions:
- `.pii-patterns` — extra content regexes
- `.pii-path-patterns` — extra forbidden path regexes
- `.pii-allowpaths` — explicit path allowlist exceptions
- `.pre-commit-config.yaml` — optional repo-local runner that wires `pre-commit` framework to the same path/content rules for contributors who prefer managed hooks
If it fires, fix the issue — do NOT use `--no-verify` to bypass.

### Content Organization

- Size SKILL.md by information density, not a line-count target
- Move detailed documentation to `references/` files
- Avoid duplication between SKILL.md and references
- Keep `tunnel-doctor` environment-neutral: it may teach discovery and presence checks, but exact private node labels, billing identities, endpoints, credentials, and current chain state remain in the owning private configuration/Skill and must not be copied into this public repository.
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

**Version tracking layers:**

1. **Marketplace Version** (`.claude-plugin/marketplace.json` → `metadata.version`)
   - Tracks the marketplace catalog as a whole
   - Bump when: Adding/removing skills, adding/removing suite plugins, major marketplace restructuring
   - Semantic versioning: MAJOR.MINOR.PATCH

2. **Individual Skill Versions** (`.claude-plugin/marketplace.json` → `plugins[].version`)
   - Each skill has its own independent version
   - Bump when: Updating that specific skill
   - **CRITICAL**: Skills should NOT have version sections in SKILL.md

**Key Principle**: SKILL.md files should be timeless content focused on functionality. Versions are tracked in marketplace.json only.

### ⚠️ Updating Existing Skills (MANDATORY)

Changes to a skill's shipped files require a version bump in
`marketplace.json`.

**Version bump rules:**
- Content/doc updates (new sections, rewritten principles) → bump **MINOR** (1.0.1 → 1.1.0)
- Bug fixes, typo fixes → bump **PATCH** (1.0.1 → 1.0.2)
- Breaking changes (renamed commands, removed features) → bump **MAJOR** (1.0.1 → 2.0.0)

**Pre-commit check:** Before committing, run `git diff --name-only` and verify: for every `skill-name/` directory that appears, `marketplace.json` also has a version bump for that skill's `plugins[].version`.

**Read the baseline version from an immutable ref, never from the working tree.**
In a shared checkout `marketplace.json` may already carry a parallel session's
in-flight bump — staged or merely saved — and `git status` looks normal either
way, so a version computed from the working copy silently inherits their number
as its starting point:

```bash
git show origin/main:.claude-plugin/marketplace.json   # baseline to bump FROM
```

This is what makes the check above decidable. `git diff --name-only` tells you
*which* skills changed; only an immutable ref tells you what their versions were
before anyone started editing. (2026-09-04: a bump computed from the working
tree adopted another session's staged `peer-message` 1.1.1→1.2.0 as its own
baseline. Every status-shaped signal stayed green; a CHANGELOG anchor assertion
was the only thing that caught it.)

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

For changes to scripts, configuration, or operating procedures, use
[docs-cleaner](daymade-docs/docs-cleaner/SKILL.md) for scoped documentation delivery:
resolve implementation intent and authorization before updating the owning SOP,
and validate the delivered command examples. Keep detailed governance in that Skill.

Before submitting or modifying skills:
- Valid YAML frontmatter with required fields
- Description includes clear activation triggers
- All referenced files exist
- Scripts are executable and tested
- No absolute paths or user-specific information
- Comprehensive documentation
- No TODOs or placeholders

## Adding a New Skill to Marketplace

Follow [Adding a New Skill to Marketplace](references/new-skill-guide.md) for
registration, README updates, validation, and publication. Use the existing suite
identity when adding a member; do not introduce a parallel standalone plugin.
The local-availability gate under **Testing Skills Locally** applies when local
use is part of the requested delivery.

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

Infrastructure/SRE operating contracts stay in their owning Skills rather than this repository guide:
`terraform-skill` owns generic Terraform release safety and environment-parity rules; an application's
project-level health-check Skill owns that application's concrete audit facets. Keep those two layers
aligned without copying project hostnames, variable lists, or rollout commands into this file.

## Plugin and Skill Architecture

For full architecture documentation (core concepts, installation flow, data flow, common misconceptions, best practices), see [references/plugin-architecture.md](./references/plugin-architecture.md).

## Plugin and Skill Troubleshooting

For systematic debugging steps (common errors, debugging process, pitfalls, real-world examples), see [references/plugin-troubleshooting.md](./references/plugin-troubleshooting.md).

For maintainer source/install/catalog drift, use **Testing Skills Locally** above.
Identify the failing layer before updating a marketplace or reinstalling a plugin.
