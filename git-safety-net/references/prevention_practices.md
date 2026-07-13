# Prevention Practices — keep a branch tangle from ever stranding work

Each practice below maps to a specific way work actually gets lost. They are cheap habits, not
ceremony; adopt the ones whose failure mode you're exposed to.

## Contents
- Parallel work: worktrees, not stash-juggling
- Push work-in-progress branches early
- Confirm the branch before every commit
- Audit before rebase / branch-delete
- Snapshot before any history rewrite
- Version / lockfile collisions between parallel branches
- Commit-scope hygiene (don't sweep unrelated staged work)
- Set a wider reflog safety window once

## Parallel work: worktrees, not stash-juggling

**Failure mode:** the classic disaster is `git stash` → switch branch → work → `git stash` again →
rebase → switch back. Each `stash` that gets superseded or dropped orphans a commit; after a busy
session you can have dozens of dangling stash states that `git stash list` no longer shows, one
`gc` from gone.

**Prevention:** give each parallel line of work its own checkout with `git worktree`:

```bash
git worktree add ../repo-featureB featureB     # a second working dir on branch featureB
# work in ../repo-featureB with zero stashing; the main checkout stays on your primary branch
git worktree remove ../repo-featureB           # when done
```

Nothing to stash means nothing to drop. This also stops the "another agent switched my branch
underneath me" problem — each agent/task gets its own worktree.

## Push work-in-progress branches early

**Failure mode:** a commit that exists only on a local branch is the *only* thing a dead disk
actually loses. Everything on a remote is safe.

**Prevention:** the moment a WIP branch has a commit worth keeping, push it:

```bash
git push -u origin <wip-branch>
```

It doesn't need to be a PR — just a remote copy. Re-push as you go. Then
`git log HEAD --branches --tags --not --remotes` (the at-risk check) stays empty, which is the
state you want.

## Confirm the branch before every commit

**Failure mode:** committing a fix onto the wrong feature branch (easy when juggling several, or
when an agent left you somewhere unexpected). The commit is then invisible to the PR it belongs
to, and gets deleted along with the wrong branch during cleanup.

**Prevention:** glance at the branch before committing:

```bash
git branch --show-current      # is this where this change belongs?
```

If you commit to the wrong branch anyway, it's recoverable: `git log` the sha, `git branch
correct-branch <sha>`, then remove it from the wrong branch — but confirming up front is free.

## Audit before rebase / branch-delete

**Failure mode:** deleting a branch or rebasing can orphan commits; if any were local-only, they
head toward gc.

**Prevention:** run the ten-second at-risk check first (see recovery_playbook.md):

```bash
git fetch --all --quiet
git log HEAD --branches --tags --not --remotes --oneline   # empty = nothing to lose; act freely
```

Non-empty → preserve those commits (branch/push/patch) before the destructive step.

## Snapshot before any history rewrite

**Failure mode:** `rebase`, `reset --hard`, `filter-repo`, and interactive-rebase mistakes abandon
the pre-rewrite commits.

**Prevention:** a throwaway backup branch makes the whole operation reversible:

```bash
git branch backup/pre-rewrite      # points at the current tip; delete once you're happy
```

If the rewrite goes wrong, `git reset --hard backup/pre-rewrite` restores it exactly.

## Version / lockfile collisions between parallel branches

**Failure mode:** two branches developed in parallel both bump the *same* shared file to the *same*
new value (a package version, a manifest version, a lockfile hash). They merge without a Git
conflict (both wrote the same line), but the second feature now ships under a version number the
first already used — so consumers that pin/refresh by version never see the second change.

**Prevention:** before bumping a shared version, check the base's current value, and bump *above*
whatever is already there:

```bash
git fetch origin --quiet
git show origin/main:<manifest>     # what version is main ALREADY at? bump to strictly higher
```

If a collision already merged, fix it by bumping again above the collided value and re-releasing.

## Commit-scope hygiene (don't sweep unrelated staged work)

**Failure mode:** `git add .` or `git commit -a` sweeps unrelated changes (another task's edits,
generated files) into a commit; later that commit gets reverted/reset and takes the unrelated work
with it.

**Prevention:** stage explicit paths, and verify the staged set before committing:

```bash
git add <the specific paths for THIS change>
git diff --cached --name-only        # confirm ONLY the intended files are staged
```

## Set a wider reflog safety window once

The reflog is your recovery window; widen it once, globally, so a busy repo doesn't age work out:

```bash
git config --global gc.reflogExpire "180 days"
git config --global gc.reflogExpireUnreachable "90 days"
```
