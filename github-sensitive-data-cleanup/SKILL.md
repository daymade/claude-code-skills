---
name: github-sensitive-data-cleanup
description: >-
  Scans and removes sensitive data (secrets, API keys, private domains/IPs, PII) from GitHub
  repository history, then verifies and force-pushes safely. Use for 清理敏感数据 / 历史重写 / 泄露, "scan
  sensitive data", "clean git history", "remove secrets from repo", or before any force push to a
  public repo. Not for local-only Git recovery (use git-safety-net) or ordinary repository setup
  (use auto-repo-setup).
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
5. **Use one explicit lease bound to the saved remote commit.** A rejected
   lease stops the push; never fall back to `--force` or refresh the expected
   commit to bypass concurrent work.
6. **Verify after rewriting.** A clean `git log` is not enough; re-run the
   scanner and do an AI semantic review.
7. **Public repos with forks need extra care.** Forks and clones may retain old
   history. Verify the named exposure and ownership before choosing a route;
   contact owners only within the authorized recipient/message scope.

## Workflow

### Step 0: Confirm the repo path and current branch

```bash
cd /path/to/repo
git status --short
git remote -v
```

Use an exact repository root. Scan and verification accept ordinary, linked
worktree and bare roots. Rewrite requires an independent clone: linked roots
and ordinary or bare repositories with attached worktrees are refused. A bare
mirror has no working-tree status to check; verify its Git identity instead.

### Step 0.5: Bind each exposed surface

The acting agent records the known finding's exact public locations and the authorized
remediation scope in private task evidence. Follow the finding, not an unbounded inventory
of every repository. Keep these surfaces distinct:

| Surface | Deciding evidence and remediation owner |
|---|---|
| Current files and hosted publication text | Read the named published files, PR title/body or other affected text. Ordinary corrections close only these current values; use `github-ops` for hosted edits. |
| Git objects and refs | Bind file blobs, commit messages and the affected branch/tag history to immutable objects. This Skill owns an explicitly authorized rewrite and exact-ref readback. A clean tip does not prove clean ancestry or removal of an old object. |
| PR body edit history | Inspect revisions of the named PR even when its current body is corrected. Use `github-ops`'s **PR body edit-history cleanup** in its Pull Request Operations reference; it owns exact revision selection, private backup, deletion authorization and preservation readback. |
| Cached views, PR Git references, forks and clones | Check the known locators and ownership separately. Git rewrite or branch deletion does not establish erasure here; third-party copies and GitHub-controlled references may require a separate route. |

Distinguish an object retained in a private backup from one still publicly obtainable.
When claiming anonymous access, test the exact locator without authentication and compare
the returned content with the intended immutable object; an authenticated read, error page
or redirect alone does not prove anonymous exposure or removal. Include releases, attachments
or logs only when the finding points to them, and leave uninspected surfaces unverified.

For each named surface, report what was inspected, what the result proves, and what remains
public or unverified. The bundled Git scanners do not inspect hosted PR revision history or
prove removal from caches/forks. No finding within a completed scope means stop that audit;
it does not convert excluded or unknown surfaces into clean ones. Once the approved changes
are verified, report residuals rather than silently expanding into a rewrite, deletion or
external message.

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

Check that the scan completed successfully before interpreting its findings.
An execution error leaves the scan incomplete. Zero findings still proceeds to
Step 1.5; it does not authorize a clean result or a history rewrite.

### Step 1.5: AI semantic review (Layer 4)

Regex scanners (Layers 1-3) cannot catch novel private context: real names,
project codenames, transcript snippets, internal meeting references, or
architecture descriptions. You must do an AI semantic review.

Use the prompt in `references/ai_semantic_review_prompt.md` on the frozen refs
and file set for this task, including material with no scanner hits. Scanner
findings prioritize inspection; they do not define its coverage. Record inspected
items, findings and unreviewed coverage outside the public repository.

If the completed scan and semantic review find nothing sensitive in that scope,
**stop**. Do not rewrite history. Incomplete coverage remains unverified, not clean.

If you skip this step, you may push private context that gitleaks never knew to
look for.

### Step 2: Classify findings and choose a remediation

For each finding, decide:

- **Rotate the credential** (always do this for live secrets first).
- **Remove from history** (for private domains/IPs, PII, or already-rotated
  secrets that still reveal internal context).
- **Add to `.gitignore` or allowlist** (for false positives only).

Select the route for the observed surface: correct current hosted text or clear approved
PR body revisions through `github-ops`; use Steps 3–7 only for the separately authorized
Git rewrite. A PR revision-content approval is not permission to rewrite branches or tags.

**Live secrets must be rotated before history cleanup.** Removing history does
not invalidate a secret that has already been exposed.

**Verify ownership claims before choosing a route.** The route depends on who
controls the resource: a fork/branch/document you control allows self-serve
deletion; a third party's forces the GitHub Support / owner-cooperation route.
Treat an audit report's annotation of who owns an account, fork, or document as
an unverified claim, however confidently it is written — check
`gh api repos/<owner>/<repo>`, `gh auth status`, or ask the user. (2026-09-18:
an inherited report labeled an external contributor's fork as the user's own
agent account, silently downgrading the route from "support ticket" to
"delete it yourself" — it would have failed at execution time.)

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

### Step 4: Save the publication target, then back up and rewrite

Before rewriting, save these observed values in the existing task state outside
the repository: the selected remote name and verified transport configuration,
the fully qualified GitHub target (`HOST/OWNER/REPO`), the exact destination
branch ref, and its full remote commit SHA. Keep credentials out of this state;
retain the configured credential mechanism. Resolve the selected remote's single
push URL, including configured push URLs and URL rewrites. Reject URLs containing
credentials before passing them to another command or saving them; keep
authentication in the existing credential mechanism. Check that the verified
credential-free URL resolves unchanged before querying its branch. A changed
resolution is unknown and stops the snapshot. A plain `ls-remote origin` can
follow a different fetch URL:

```bash
git -C /path/to/repo remote get-url --push --all origin
git -C /path/to/repo ls-remote --get-url '<verified-push-url>'
git -C /path/to/repo ls-remote --refs '<verified-push-url>' refs/heads/main
```

Require one verified push URL and a successful ref query with exactly one
matching full SHA/ref row. An absent
branch or failed query is not a saved preimage. Do not derive this value from
the rewritten local branch or a stale remote-tracking ref. If this task resumes
after rewriting, reuse the saved target/preimage; missing state stops the push.

`--yes` confirms the displayed rewrite target and backup paths. It does not
authorize rewriting shared history or bypassing git-filter-repo's native
fresh-clone checks. Preserve pending work in the original checkout and use the
independent clone route below when necessary.

```bash
uv run scripts/rewrite_history.py --repo /path/to/repo \
  --replacements /tmp/sensitive-replacements.txt \
  --backup /tmp/repo-backup.bundle \
  --yes

# Entity leaks live in commit MESSAGES too, not just file content. Cover both:
uv run scripts/rewrite_history.py --repo /path/to/repo \
  --replacements /tmp/sensitive-replacements.txt \
  --message-replacements /tmp/sensitive-replacements.txt \
  --backup /tmp/repo-backup.bundle \
  --yes
```

This script:

1. Verifies an independent repository with no attached worktrees.
2. Verifies `git-filter-repo` is installed and executable. For an
   ordinary clone, requires a successful clean-status query; for a bare mirror,
   uses the verified no-working-tree layout. A failed query stops the rewrite.
3. Creates a `git bundle` backup of the current state.
4. Verifies the backup bundle with `git bundle verify`.
5. Runs `git filter-repo --replace-text` without bypassing its native safety
   checks. When `--message-replacements` is
   given, it also runs `--replace-message` so commit messages are rewritten,
   not just file blobs — a cleanup that only covers blobs can leave the
   entity naming itself in a commit message.
6. Reports the old and new commit hashes.

**If the backup or verification step fails, the script stops.** Do not proceed
manually.

### Step 5: Verify the cleanup

```bash
uv run scripts/verify_cleanup.py --repo /path/to/repo --replacements /tmp/sensitive-replacements.txt
```

This re-runs the scanner and also checks that none of the original sensitive
strings remain in any commit. If it finds anything, go back to Step 3.
Repeat Step 1.5 against the rewritten refs within the same task scope before
pushing; successful pattern checks alone do not complete semantic verification.
After both checks pass, resolve and save the exact local commit that was
verified for the selected branch:

```bash
git -C /path/to/repo rev-parse refs/heads/main^{commit}
```

A later local change invalidates that verification binding. Recheck the changed
candidate before choosing a new verified local SHA.

### Step 6: Check visibility and push

git-filter-repo may remove `origin`. If the saved named remote is absent,
restore it using the previously verified transport configuration and existing
credential mechanism; do not guess a URL or credential. If the remote exists
but differs, stop and reconcile the target. A clone made from a local source
does not make that local source URL the authorized GitHub destination.

Supply the saved publication target and old remote SHA, plus the local SHA
verified in Step 5. Keep the remote name so its ordinary hooks still run:

```bash
uv run scripts/safe_push.py --repo /path/to/repo --remote origin --branch main \
  --expected-repository '<saved-host/owner/repo>' \
  --expected-remote-sha '<saved-full-remote-sha>' \
  --verified-local-sha '<verified-full-local-sha>' \
  --yes
```

This script:

1. Binds the selected push URL to the saved repository target, then validates
   that target's visibility and fork metadata.
2. Warns loudly if the repo is public and has forks.
3. Checks the local candidate equals the verified SHA.
4. Makes one push with an explicit expected-commit lease to the saved remote
   branch. A lease or hook rejection stops; there is no force fallback.
5. Refuses to add `--no-verify`.

If the PII Guard hook fails, fix the issue and re-run. Do not bypass.

Migration: callers supplying only `--repo`, `--remote` and `--branch` now fail
closed. Capture the remote target/preimage before rewrite and add all three
binding arguments above. `--yes` cannot fill missing evidence. The existing
backup, replacement and optional message-replacement arguments remain supported.

### Step 7: Post-push verification

After the push succeeds:

1. Read back the exact published refs and the named content covered by the rewrite.
   A verified local candidate alone does not prove the hosted objects changed.
2. Check affected open PRs still target valid commits. Rewriting history may break
   their branches; do not repair unrelated PRs or discard their work implicitly.
3. Revisit the exposed surfaces recorded in Step 0.5. Report Git verification separately
   from PR revision cleanup, cached-object access and third-party copies. Keep unavailable
   checks unverified, even if the Git scanner is clean.

## What the Bundled Scripts Do

### `scripts/scan_repo.py`

Runs `gitleaks` and a custom bash/grep layer for patterns that gitleaks does
not cover (private domains, internal IPs, Chinese phone numbers, certain PII).
Outputs a JSON report.

```bash
uv run --with gitpython scripts/scan_repo.py --repo /path/to/repo --output /tmp/report.json
```

### `scripts/rewrite_history.py`

Creates a backup bundle and runs `git filter-repo --replace-text`. Pass
`--message-replacements <file>` to also rewrite commit messages via
`--replace-message` (the same replacements file usually covers both).

```bash
uv run --with gitpython scripts/rewrite_history.py \
  --repo /path/to/repo \
  --replacements /tmp/sensitive-replacements.txt \
  --message-replacements /tmp/sensitive-replacements.txt \
  --backup /tmp/repo-backup.bundle \
  --yes
```

### `scripts/verify_cleanup.py`

Re-runs the scanner and greps all commits for the original sensitive strings,
covering both blob content (`git grep` over every commit) and commit messages
(`git log` over all refs with a hash-annotated record format), so a rewrite
that missed `--replace-message` still fails verification.

```bash
uv run --with gitpython scripts/verify_cleanup.py \
  --repo /path/to/repo \
  --replacements /tmp/sensitive-replacements.txt
```

### `scripts/safe_push.py`

Checks visibility and pushes safely.

```bash
uv run --with gitpython scripts/safe_push.py --repo /path/to/repo --remote origin --branch main \
  --expected-repository '<saved-host/owner/repo>' \
  --expected-remote-sha '<saved-full-remote-sha>' \
  --verified-local-sha '<verified-full-local-sha>' \
  --yes
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

Route Support requests and fork-owner communications through `github-ops`'s authorization
contract; rewrite approval alone does not authorize them. GitHub Support's acceptance is
conditional, not a guaranteed purge. See the
[official removal limits](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository).
For lower-risk findings, document any retained or unverified exposure and the chosen
boundary; do not report a rewrite as complete erasure.

### `git filter-repo` reports "need a fresh clone"

Keep the native refusal. Preserve the original checkout and create a fresh
independent mirror; `--no-local` avoids the local-clone object-sharing shortcut:

```bash
git clone --mirror --no-local /path/to/repo /tmp/repo-mirror.git
```

After the clone succeeds, run the bundled `rewrite_history.py` with
`--repo /tmp/repo-mirror.git` from its Skill directory.
Save the approved publication target/preimage before this route and retain it
through the rewrite. Do not add `--force` to bypass the fresh-clone guard or
delete another session's work to satisfy it.

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
