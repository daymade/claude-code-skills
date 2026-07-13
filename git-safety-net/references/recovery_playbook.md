# Recovery Playbook — get lost work back, then make it un-loseable

## Contents
- Mental model: nothing is gone until gc runs
- The authoritative "is anything at risk" check
- Ladder step 1 — `git reflog` (first move, ~90% of recoveries)
- Ladder step 2 — dropped stashes
- Ladder step 3 — detached-HEAD work
- Ladder step 4 — `git fsck` for true orphans
- Preserve: pin danglers so gc can never take them
- Triple-backup a critical commit
- Widen the safety window (config)
- Destructive-operation safety (reset/force-push/rewrite)
- Sources

## Mental model: nothing is gone until gc runs

A commit is an immutable object in `.git/objects`. Deleting a branch, `reset --hard`, a bad
rebase, or `stash drop` only removes a *reference* to the commit — the object itself survives
until `git gc` prunes unreachable objects. The reflog keeps a ref alive for **~90 days**
(reachable) / **~30 days** (already unreachable), which is why same-day recovery almost always
works. So the recovery mindset is: **find the dangling object, point a ref at it, done.** The
one thing that permanently loses work is `gc` running while nothing references it — which is why
"preserve before cleanup" (below) matters.

## The authoritative "is anything at risk" check

Before anything else, answer the only question that matters — *is any commit reachable only
locally, on no remote?* That is the exact at-risk set. Check **every** place local work hides,
not just branches:

```bash
git fetch --all --quiet
git log HEAD --branches --tags --not --remotes --oneline --decorate   # HEAD→detached-HEAD work, --tags→tag-only commits
git stash list                                                         # stashes are local-only too
```

- **All empty = zero loss.** Every local commit is also on a remote; a dead disk loses nothing.
- **Non-empty = those exact commits exist only on this machine.** Back them up (below) before any
  branch cleanup.

Why `HEAD --branches --tags`, not just `--branches`: a plain `git log --branches --not --remotes`
misses a **detached-HEAD** commit (on no branch) and a **tag-only** commit — both classic loss
vectors. `scripts/git_loss_audit.sh` runs exactly this expanded set plus the stash and dangling
checks.

Do **not** substitute `git status` or ahead/behind counts for this — they answer different
questions. To confirm a single commit is safe on a remote:

```bash
git branch -r --contains <sha>       # lists remote branches that contain it (empty = local-only)
```

## Ladder step 1 — `git reflog` (first move)

Any "I lost a commit / reset too far / bad rebase" starts here:

```bash
git reflog --date=iso | head -40
```

Each line is a past HEAD position with its sha and what moved it (`commit`, `checkout`, `reset`,
`rebase -i (finish)`, …). Find the sha of the state you want back, **confirm it**, then recover
onto a *new* branch (never reset your live branch onto it):

```bash
git show <sha>                       # CONFIRM: is this the content you want?
git switch -c rescue/<name> <sha>    # or: git branch rescue/<name> <sha>
```

Branch-specific reflogs exist too: `git reflog show <branch>` recovers where a specific branch
tip used to point (e.g. before a force-push clobbered it).

## Ladder step 2 — dropped stashes

`git stash drop` / `git stash pop` (which drops on success) removes the stash ref but leaves the
underlying commit dangling. `git stash list` won't show it; find it via fsck:

```bash
git fsck --no-reflogs --unreachable | grep commit    # or: git fsck --dangling
git show <stash-sha>                                 # verify it's the stash you lost
git stash apply <stash-sha>                           # re-apply it, or:
git branch rescue/stash <stash-sha>                   # park it on a branch
```

Stash commits have a distinctive message (`WIP on <branch>: …`), which helps identify them among
fsck output.

## Ladder step 3 — detached-HEAD work

Committing while on a detached HEAD (after `git checkout <sha>`), then switching away, orphans
those commits — they belong to no branch. Reflog remembers them:

```bash
git reflog | grep -i 'HEAD@'         # find the detached commits you made
git switch -c saved-work <sha>        # give them a home
```

**Prevent the loss entirely:** the moment you make a commit you care about on a detached HEAD,
`git switch -c <branch> HEAD` before doing anything else.

## Ladder step 4 — `git fsck` for true orphans

When reflog doesn't reach it (reflog expired, or the commit was never HEAD on this clone), fsck
walks the object store directly:

```bash
git fsck --dangling                  # dangling commits/blobs/trees not reachable from any ref
```

Inspect candidates with `git show <sha>`. Dangling *blobs* can be a single lost file:
`git show <blob-sha> > recovered_file`.

## Preserve: pin danglers so gc can never take them

Dangling commits are recoverable **only until gc runs**. To make them permanently safe without
cluttering `git branch`, pin each under a hidden ref namespace — a referenced object is never
collected:

```bash
git fsck --dangling 2>/dev/null | awk '/dangling commit/ {print $3}' | while read sha; do
  git update-ref "refs/dangling-backup/$sha" "$sha"
done
git for-each-ref refs/dangling-backup/   # confirm what's pinned
```

`scripts/git_preserve_danglers.sh` does exactly this (and optional patch export). Why a hidden
`refs/dangling-backup/*` and not `git stash store`? These refs don't appear in `git branch` or
`git stash list`, so they protect the objects without turning your branch/stash lists into noise,
and you can bulk-delete them once you've verified the content is safe elsewhere.

## Triple-backup a critical commit

For a specific commit you must not lose (e.g. real unpushed work found by the at-risk check), one
copy isn't enough — a single disk failure or a single `gc` shouldn't be able to take it. Give it
three independent homes:

```bash
git branch backup/<name> <sha>                                   # 1) local branch
git push origin backup/<name>                                    # 2) remote branch (survives disk loss)
git format-patch -1 <sha> --stdout > <name>.patch                # 3) patch file (survives repo loss)
```

Now the commit survives losing any one of: the working tree, the remote, or the whole repo.

## Widen the safety window (config)

The default reflog window is generous but finite. For repos where recovery matters, extend it:

```bash
git config --global gc.reflogExpire "180 days"
git config --global gc.reflogExpireUnreachable "90 days"
```

## Destructive-operation safety (reset / force-push / rewrite)

Recovery is easiest when the operation that "lost" the work was itself reversible. Prefer:

- **On already-pushed history, `git revert`, not `git reset`.** Revert adds an inverse commit;
  reset abandons commits that teammates may have based work on.
- **If you must force-push, use `git push --force-with-lease`, not `--force`.** `--force-with-lease`
  refuses the push if the remote moved since you last fetched — it won't silently clobber a
  teammate's (or another agent's) commits.
- **Before any history rewrite (`rebase`, `filter-repo`, `reset --hard`), snapshot first:**
  `git branch backup/pre-rewrite` (and run the at-risk check). Ten seconds; fully reversible.

## Sources

- Pro Git — Data Recovery (reflog / fsck / dangling objects): <https://git-scm.com/book/en/v2/Git-Internals-Maintenance-and-Data-Recovery>
- `git reflog` recovery guides (2026): <https://devtoolbox.dedyn.io/blog/git-reflog-recover-lost-commits-guide>, <https://oneuptime.com/blog/post/2026-01-24-git-reflog-recovery/view>
- Detached HEAD recovery: <https://circleci.com/blog/git-detached-head-state/>
