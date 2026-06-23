# Push-Time Gotchas

A PR can look perfect locally and still fail at the last meter. These are the failures that happen **after** the code is written and tested — when you push, when GitHub evaluates mergeability, or when your own security hooks reject the commit.

## Git remote URL rewrites can silently break push

A global `.gitconfig` URL rewrite can turn an SSH push into HTTPS, or route it through a stale endpoint, producing errors like `503` or `unable to access` even though `git remote -v` looks correct.

**Detection:**

```bash
git config --global --get-regexp url
```

**If you see a rewrite that affects this repo**, remove it for the current push or globally:

```bash
git config --global --unset url."https://github.com/".insteadOf
git config --global --unset url."https://".insteadOf
```

Then verify with `git remote -v` and a test fetch:

```bash
git fetch origin
git push fork <branch>
```

## Local PII / secret hooks may reject upstream commits

If the project uses local pre-commit/pre-push hooks (gitleaks, custom PII guards), an innocent rebase can surface test fixtures, sample paths, or documentation emails from upstream history that the hooks flag.

**Do not bypass with `--no-verify`.** The correct fixes are, in order:

1. **Add an allowlist entry** for obviously public fixture content (sample paths, upstream maintainer email in `README_DE.md`, etc.).
2. **Tune the rule** if it is producing false positives (e.g., adding word boundaries to a phone-number regex).
3. **Sanitize the commit** only if the flagged content is actually yours and should not be public.

Keep the allowlist change in a separate commit or in your local guard config — do not commit `.pii-patterns` to the upstream repo unless the project specifically supports it.

## Verify mergeability before declaring "ready"

`git push` succeeding does not mean the PR is mergeable. Always check:

```bash
gh pr view <pr-number> --repo <owner>/<repo> --json mergeable,mergeStateStatus
```

A `mergeable` value of `CONFLICTING` means the GitHub merge algorithm still sees a conflict even if local `git merge` appeared clean (this can happen with rename/add conflicts or protected-file checks). Fix locally and push again.

## Use `--force-with-lease`, but know what it does not protect

`--force-with-lease` aborts if the remote ref has moved since you last fetched. It does **not** protect:

- Review threads on lines you are about to rewrite (they will be marked outdated).
- Bot comments that reference a specific commit hash.
- CI runs that are in progress on the old tip.

So only force-push after you have addressed the feedback that caused the rewrite, and mention the rewrite in a PR comment if maintainers are mid-review.

## Checklist before every push

```bash
# 1. Visibility and target correctness
gh repo view <owner>/<repo> --json visibility,isPrivate,defaultBranchRef

# 2. Local checks (use the project's own commands)
<project test/lint commands from CONTRIBUTING.md>

# 3. Mergeability after push
gh pr view <pr-number> --repo <owner>/<repo> --json mergeable,mergeStateStatus
```
