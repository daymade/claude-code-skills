# Incident Lessons: GitHub Sensitive Data Cleanup

This reference captures what went wrong in real history-rewrite incidents and
how the `github-sensitive-data-cleanup` skill prevents recurrence.

## Lesson 1: No Backup Before Rewrite

**What happened:** A public repository was rewritten with `git filter-repo` to
remove leaked private infrastructure domains. The operation succeeded, but no
backup (`git bundle`, bare clone, or snapshot) was created first.

**Why it matters:** If the rewrite had corrupted history, deleted wanted
commits, or produced unexpected results, there would have been no clean way to
recover the original state.

**Prevention:** The skill's `rewrite_history.py` creates a `git bundle --all`
backup and refuses to proceed if the backup fails.

## Lesson 2: PII Guard Hook Failed After Rewrite

**What happened:** After rewriting history, the pre-push hook failed because it
referenced an old remote commit range that no longer existed locally. The user
authorized `--no-verify` once, which is acceptable only when the user explicitly
types it.

**Why it matters:** Bypassing hooks is the main way secrets get pushed. The
hook failure was a symptom of stale local state, not a reason to disable
security checks.

**Prevention:**

- The skill never uses `--no-verify` automatically.
- `safe_push.py` uses `--force-with-lease` first and only falls back to
  `--force` when the remote ref is stale because of the rewrite itself.
- The user is told to fix hook failures, not bypass them.

## Lesson 3: Public Repo with Forks Was Treated as Low-Risk

**What happened:** The repository had 195 forks. A force push updates the
upstream history but leaves every fork with the old commits containing the
sensitive data.

**Why it matters:** Forks are silent copies. Once data is public, it exists in
places you do not control.

**Prevention:**

- `safe_push.py` reports fork count explicitly before pushing.
- The skill warns loudly when the repo is public and has forks.
- For high-risk leaks, the workflow includes notifying fork owners and
  rotating credentials.

## Lesson 4: Regex Scanners Miss Semantic Private Context

**What happened:** Multi-layer scanning (gitleaks, path scan, bash grep)
passed, but an AI semantic review caught a real transcript snippet that
contained no keyword or secret pattern.

**Why it matters:** Keyword-based tools only catch things someone has already
listed. They cannot recognize novel private context.

**Prevention:**

- `scan_repo.py` and `verify_cleanup.py` both flag that an AI semantic review
  is required.
- The skill instructions repeat: "Regex scanners miss semantic private
  context."

## Lesson 5: Visibility Was Not Verified Before Push

**What happened:** The repository was assumed to be private based on URL shape
and context. In reality it was public with many stars and forks.

**Why it matters:** Pushing sensitive data to a public repo has much larger
blast radius than pushing to a private repo.

**Prevention:**

- `safe_push.py` calls `gh repo view --json visibility,isPrivate,...` and
  refuses to push if it cannot confirm visibility.
- The skill never infers public/private from the remote URL.

## Lesson 6: Live Secrets Were Not Rotated First

**What happened:** The cleanup focused on removing history, but the leaked
items included infrastructure context rather than live credentials. If they
had been live credentials, history cleanup alone would not have removed the
threat.

**Why it matters:** Once a secret reaches a public repo, assume it has been
seen. History cleanup does not invalidate the secret.

**Prevention:**

- The workflow requires rotating live credentials **before** history cleanup.
- The skill instructions make this explicit: "Live secrets must be rotated
  before history cleanup."

## When to Escalate to a Human

Stop and ask the user before proceeding if:

- The repo has more than 50 forks and the leak includes live credentials.
- The leaked data includes PII of third parties.
- You are not the repository owner or do not have force-push permission.
- The backup step fails for any reason.
- The scanner finds live secrets and the user has not confirmed rotation.
