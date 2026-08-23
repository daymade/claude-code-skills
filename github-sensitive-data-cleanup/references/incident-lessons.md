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

## Lesson 7: Commit Messages Leak Too — Blob-Only Rewrite and Verify Both Missed Them

**What happened:** A cleanup replaced leaked entities in file content across
history, but the commit messages kept naming the same entities — including
the squash-merge message on `main` itself. `rewrite_history.py` only ran
`--replace-text` (blob content), and `verify_cleanup.py` only ran
`git grep` over commit trees, which also covers blobs only. Both layers
agreed the repo was clean while the entity sat in `git log` output.

**Why it matters:** Two checks that share a blind spot read as independent
confirmation. A rewrite is only as complete as its narrowest channel, and
commit messages are a first-class leak channel — search engines index them.

**Prevention:**

- `rewrite_history.py --message-replacements <file>` runs
  `git filter-repo --replace-message` in the same pass; the same replacements
  file usually covers both channels.
- `verify_cleanup.py` now greps commit messages (`git log` over all refs,
  hash-annotated) in addition to blob content, so a message-only leak fails
  verification.

## Lesson 8: The Clean-Working-Tree Check Blocks Rewrites on Shared Checkouts

**What happened:** A rewrite had to run while untracked directories owned by
other active sessions sat in the working tree. `rewrite_history.py` aborts on
any `git status --short` output, and the foreign files could neither be
committed (not the rewriter's work) nor moved (active writers).

**Why it matters:** The check protects against losing uncommitted tracked
changes during the post-rewrite checkout, but untracked files are not touched
by a ref rewrite or by the final `reset --hard` — blocking on them conflates
two different risks and can stall an urgent cleanup.

**Prevention:** If the tree is clean except foreign-owned untracked paths,
run the script's exact steps manually (backup bundle, `git filter-repo`,
verify) and document the deviation — never delete or stash another session's
files to satisfy the check.

## Lesson 9: The Tooling Crashed on Exactly the Repos It Cleans

**What happened:** Independent review of the Lesson 7 fixes found that the
tooling itself broke on realistic inputs: `verify_cleanup.py` decoded
`git log` output with strict UTF-8, so one GBK/legacy-encoded commit message
crashed verification with an uncaught `UnicodeDecodeError` — no report at
all. The SKILL.md rewrite command blocks (Step 4 and the script-reference
section) omitted `--yes`, so following the documentation verbatim exited
before the backup was even created.
`rewrite_history.py` ran `git bundle verify` without `-C <repo>`, crashing
when invoked from a non-git directory, and the resulting `RuntimeError`
escaped the `except` clause. A FAILED message check reported only a hit
count, leaving the operator to hand-grep `git log` for the offending
commits.

A documentation-round review then found the same crash class still open in
the blob channel (`git grep` decode in `grep_all_commits`) — the
prescription below had been written before the class was fully closed. It
was fixed by hardening every subprocess decode in all four scripts, and the
fix was verified against a GBK-encoded source file containing a leak:
verification now reports the leak from both channels instead of dying.

**Why it matters:** A repo being cleaned is by definition a repo with
hygiene problems — legacy encodings included — so the verification tooling
must be more robust than the code it inspects; a verifier that crashes
instead of reporting converts "leak still present" into "tool broken" at
the worst possible moment. And a documented command that cannot be run
verbatim trains operators to improvise, which is how steps like backups
get silently skipped.

**Prevention:**

- Decode git output with `errors="replace"` when the goal is detection, not
  fidelity — this now holds for every subprocess decode in all four scripts,
  both channels. Report `commit_message_commits` hashes (first 10) so a
  FAILED check locates commits instead of just counting hits. Boundary:
  `errors="replace"` prevents the crash but cannot make a UTF-8 pattern
  match GBK-encoded CJK bytes — non-UTF-8 content belongs to the Layer 4
  semantic review, not regex.
- Test every documented command block verbatim — copy-paste from the doc
  into a shell — before shipping the doc.
- Pass `-C <repo>` to every git invocation; scripts must behave identically
  from any working directory.

## When to Escalate to a Human

Stop and ask the user before proceeding if:

- The repo has more than 50 forks and the leak includes live credentials.
- The leaked data includes PII of third parties.
- You are not the repository owner or do not have force-push permission.
- The backup step fails for any reason.
- The scanner finds live secrets and the user has not confirmed rotation.
