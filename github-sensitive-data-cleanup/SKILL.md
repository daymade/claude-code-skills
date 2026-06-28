---
name: github-sensitive-data-cleanup
description: >-
  Scan and remove sensitive data (secrets, API keys, private domains/IPs, PII)
  from GitHub repository history. Use this skill whenever the user says
  "scan sensitive data", "clean git history", "remove secrets from repo",
  "sanitize GitHub history", "清理敏感数据", "历史重写", "force push",
  "泄露", or needs to repair a public repo after accidental secret/private
  context leakage. Also use before any force push to a public repository to
  verify visibility, backup, and scan results.
---

# GitHub Sensitive Data Cleanup

## Overview

This skill guides you through safely removing sensitive data from a Git
repository's history and pushing the cleaned history to GitHub. It encodes the
hard-won lessons from real incidents: scan first, backup before rewriting,
verify after rewriting, and never force-push to a public repo without checking
its visibility and fork count.

The bundled scripts automate the mechanical parts:

- `scripts/scan_repo.py` — scan the repo for secrets and private context.
- `scripts/rewrite_history.py` — create a backup and rewrite history with
  `git-filter-repo`.
- `scripts/verify_cleanup.py` — confirm the sensitive content is gone.
- `scripts/safe_push.py` — verify repo visibility and push safely.

**This skill is conservative by design.** If any safety check fails, it stops
and asks for human confirmation rather than continuing.

## When to Use This Skill

Trigger this skill when the user:

- Says "scan sensitive data", "扫描敏感信息", "看看仓库有没有泄露".
- Wants to "clean git history", "sanitize history", "rewrite history",
  "remove secrets from history".
- Has accidentally pushed a secret, private domain, internal IP, or PII to a
  public repository.
- Is about to force-push to a public repository (even without sensitive data).
- Mentions `git filter-repo`, `BFG`, `git-filter-branch`, or history rewrite.

## Prerequisites

Install these tools once per machine:

```bash
# git-filter-repo (modern replacement for git-filter-branch)
brew install git-filter-repo

# gitleaks (secret scanner)
brew install gitleaks

# GitHub CLI
brew install gh
```

The scripts assume `git-filter-repo` and `gitleaks` are on `PATH`. The skill
will check this before running destructive operations.

## Safety Rules (Non-Negotiable)

1. **Scan before you decide.** Never rewrite history based on a hunch.
2. **Create a backup before rewriting.** Use `git bundle` or a fresh bare clone.
3. **Verify repo visibility with `gh repo view` before any push.** Do not infer
   public/private from the URL or directory name.
4. **Never use `--no-verify` to bypass hooks.** If the PII Guard hook fails,
   fix the underlying issue or add an allowlist; do not bypass.
5. **Use `--force-with-lease` first.** Fall back to `--force` only if the
   remote ref is stale because of the rewrite itself.
6. **Verify after rewriting.** A clean `git log` is not enough; re-run the
   scanner and do an AI semantic review.
7. **Public repos with forks need extra care.** Every fork keeps a copy of the
   old history. Coordinate with fork owners if the leaked data is high-risk.

## Workflow

### Step 0: Confirm the repo path and current branch

```bash
cd /path/to/repo
git status --short
git remote -v
```

### Step 1: Scan for sensitive data

Run the scanner to find what needs to be removed:

```bash
uv run --with gitpython scripts/scan_repo.py --repo /path/to/repo --output /tmp/scan-report.json
```

The scanner auto-loads repo-specific patterns from `.pii-patterns` in the repo
root. If that file contains real private domains, **do not commit it** — add it
to `.gitignore` or keep it outside the repo. `rewrite_history.py` will abort if
the working tree has untracked files.

To enable Layer 3 (private infrastructure context from your gitleaks config and
an optional identities file):

```bash
uv run --with gitpython scripts/scan_repo.py \
  --repo /path/to/repo \
  --gitleaks-config ~/scripts/git-pii-guard/gitleaks.toml \
  --identities-file ~/.config/github-sensitive-data-cleanup/identities.txt \
  --output /tmp/scan-report.json
```

The `--gitleaks-config` flag reads `private-domain-context` and
`private-ip-context` rules from your private gitleaks config. The real patterns
stay in your private config; nothing is copied into this public skill.

Review `/tmp/scan-report.json`. It includes:

- `gitleaks` findings (secrets, API keys, tokens).
- Custom pattern matches (internal IPs, phone numbers, PII).
- Layer 3 context matches (private domains, IPs, identities from your config).
- A reminder to do an AI semantic review for content that regex cannot catch.

If nothing sensitive is found, **stop**. Do not rewrite history.

### Step 1.5: AI semantic review (Layer 4)

Regex scanners (Layers 1-3) cannot catch novel private context: real names,
project codenames, transcript snippets, internal meeting references, or
architecture descriptions. You must do an AI semantic review.

Use the prompt in `references/ai_semantic_review_prompt.md` on the flagged
commits. Re-run the review until no new private context is found.

If you skip this step, you may push private context that gitleaks never knew to
look for.

### Step 2: Classify findings and choose a remediation

For each finding, decide:

- **Rotate the credential** (always do this for live secrets first).
- **Remove from history** (for private domains/IPs, PII, or already-rotated
  secrets that still reveal internal context).
- **Add to `.gitignore` or allowlist** (for false positives only).

**Live secrets must be rotated before history cleanup.** Removing history does
not invalidate a secret that has already been exposed.

### Step 3: Prepare a replacements file

Create a text file with one replacement per line in `git-filter-repo`
`--replace-text` format:

```text
literal:internal.example.com==>example.com
literal:private.example.org==>example.org
literal:sk-example-aaaaaaaaaaaaaaaa==>sk-example-REDACTED
```

Replace these with your actual sensitive strings. Do not commit the real
values; keep the replacements file outside the repository.

Use `literal:` for exact string matches. For regex replacements, use
`regex:` (only if you are confident in the pattern).

Save this file outside the repo, e.g. `/tmp/sensitive-replacements.txt`.

### Step 4: Create a backup

```bash
uv run scripts/rewrite_history.py --repo /path/to/repo \
  --replacements /tmp/sensitive-replacements.txt \
  --backup /tmp/repo-backup.bundle
```

This script:

1. Verifies `git-filter-repo` is installed and executable.
2. Checks that the working tree is clean (no uncommitted changes or untracked
   files). If not, aborts.
3. Creates a `git bundle` backup of the current state.
4. Verifies the backup bundle with `git bundle verify`.
5. Runs `git filter-repo --replace-text`.
6. Reports the old and new commit hashes.

**If the backup or verification step fails, the script stops.** Do not proceed
manually.

### Step 5: Verify the cleanup

```bash
uv run scripts/verify_cleanup.py --repo /path/to/repo --replacements /tmp/sensitive-replacements.txt
```

This re-runs the scanner and also checks that none of the original sensitive
strings remain in any commit. If it finds anything, go back to Step 3.

### Step 6: Check visibility and push

```bash
uv run scripts/safe_push.py --repo /path/to/repo --remote origin --branch main
```

This script:

1. Runs `gh repo view` to confirm `visibility`, `isPrivate`, and `forks`.
2. Warns loudly if the repo is public and has forks.
3. Uses `--force-with-lease` first.
4. Falls back to `--force` only if the remote ref is stale because of the
   local rewrite.
5. Refuses to add `--no-verify`.

If the PII Guard hook fails, fix the issue and re-run. Do not bypass.

### Step 7: Post-push verification

After the push succeeds:

1. Open the repo on GitHub and confirm the sensitive strings are gone from
   commit history.
2. Check that open PRs still target valid commits. Rewriting history may break
   existing PR branches.
3. Notify any fork owners for high-risk leaks.

## What the Bundled Scripts Do

### `scripts/scan_repo.py`

Runs `gitleaks` and a custom bash/grep layer for patterns that gitleaks does
not cover (private domains, internal IPs, Chinese phone numbers, certain PII).
Outputs a JSON report.

```bash
uv run --with gitpython scripts/scan_repo.py --repo /path/to/repo --output /tmp/report.json
```

### `scripts/rewrite_history.py`

Creates a backup bundle and runs `git filter-repo --replace-text`.

```bash
uv run --with gitpython scripts/rewrite_history.py \
  --repo /path/to/repo \
  --replacements /tmp/sensitive-replacements.txt \
  --backup /tmp/repo-backup.bundle
```

### `scripts/verify_cleanup.py`

Re-runs the scanner and greps all commits for the original sensitive strings.

```bash
uv run --with gitpython scripts/verify_cleanup.py \
  --repo /path/to/repo \
  --replacements /tmp/sensitive-replacements.txt
```

### `scripts/safe_push.py`

Checks visibility and pushes safely.

```bash
uv run --with gitpython scripts/safe_push.py --repo /path/to/repo --remote origin --branch main
```

## Handling Special Cases

### The repo has open PRs

Rewriting history invalidates commit refs in open PRs. After push:

1. Ask PR authors to rebase their branches onto the new `main`.
2. If the PR is yours, delete the local branch, fetch the rewritten `main`,
   and cherry-pick the changes as new commits.

### The repo has forks

Public forks retain the old history until their owners sync. For high-risk
leaks (live secrets, production credentials), consider:

1. Rotating the credential immediately (mandatory).
2. Asking GitHub Support to remove cached views of the sensitive data.
3. Notifying fork owners with a brief, factual message.

For lower-risk leaks (internal domain names, placeholder IPs), document the
rewrite and move on.

### `git filter-repo` reports "need a fresh clone"

`git-filter-repo` refuses to run on repos with multiple remotes or non-origin
refs. To fix:

```bash
git clone --mirror /path/to/repo /tmp/repo-mirror.git
cd /tmp/repo-mirror.git
# run rewrite_history.py against the mirror
```

### gitleaks false positives

If gitleaks flags documentation examples or test fixtures, add an allowlist
entry to the repo's `.gitleaks.toml` or `.gitleaksignore` (never use
`--no-verify`). See `references/tooling_notes.md` for allowlist patterns.

## What This Skill Does NOT Do

- It does not rotate live credentials for you. Rotate first, clean history
  second.
- It does not remove data from GitHub's own backups or forks. It only cleans
  the upstream repository history.
- It does not bypass git hooks. If a hook fails, fix the root cause.
- It does not make secret leaks "safe." Once pushed, assume the data was seen.

## References

- `references/incident-lessons.md` — what went wrong in real cleanups and how
  this skill prevents those mistakes.
- `references/tooling_notes.md` — choosing between `git-filter-repo` and BFG,
  allowlist patterns, and common errors.
- `references/ai_semantic_review_prompt.md` — Layer 4 AI semantic review prompt
  for finding private context that regex cannot catch.
