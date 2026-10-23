# Recovery Playbook — get lost work back, then make it un-loseable

## Blocked local snapshots

Use this for an existing local repository with a committed HEAD when an application's
data writes succeed but its Git snapshots fail. The operator needs Git, read access
to the exact repository and its hook owner, and a private recovery directory outside
the checkout. Resolve a linked worktree's actual index and lock with
`git -C <repo> rev-parse --path-format=absolute --git-path index` and the same command
for `index.lock`; do not assume they live under `<repo>/.git/`.

1. **Bind the target and authority.** Record the application's snapshot status,
   current branch and full HEAD, exact snapshot paths, staged paths and resolved
   index/lock paths. Use `git --no-optional-locks -C <repo> status --porcelain=v1
   --untracked-files=all` for the initial status. Reuse verified prior authorization
   only for its actual objects, action and destination. Inspection alone does not
   authorize moving a lock, accepting guard findings or changing staged content.
   Keep unrelated files and writers outside the recovery action.
2. **Establish writer ownership before touching the lock.** Inspect the owning
   application's run/mutex state, relevant process/open-file evidence and any
   registered writer or shared-filesystem owner. Coordinate release with a live
   owner; do not terminate it. Lock age, unchanged metadata, an empty `lsof` result
   or a process-name miss alone proves neither abandonment nor permission. An
   unknown owner, incomplete occupancy check or writer conflict stops lock mutation;
   report that specific gap and continue independent read-only diagnosis.
3. **Preserve the threatened state.** In the private recovery directory, copy the
   complete original snapshot files, current index and existing lock, preserving
   metadata and relative paths. Record hashes, types, inode/mtime/size and HEAD;
   independently compare source and backup bytes. Never print secret-bearing
   contents. A lock may contain a newer index rather than an empty sentinel: inspect
   a *backup copy* with `GIT_INDEX_FILE=<absolute-backup-lock> git -C <repo> ls-files
   --stage`. If it parses, preserve its referenced staged blobs as well; copying an
   index alone does not preserve Git objects. If it cannot be interpreted, retain
   it as opaque evidence; do not replace the current index with it. Unsupported
   file types, unpreserved staged objects or changing inputs stop mutation.
4. **Preflight the next layer before releasing the lock.** Read the actual hook
   dispatcher and its owner contract. If running it is authorized and its side
   effects are understood, create a unique temporary index outside the checkout
   from the preserved current index (or committed HEAD when no index exists), stage
   only the approved snapshot paths into that index, inspect its staged diff/stat,
   then run the original `git hook run pre-commit` with that child-only
   `GIT_INDEX_FILE`. This isolates index changes; it does **not** isolate hook writes
   to the working tree, network or processes. An unsafe/unavailable hook preflight
   remains unverified. Never disable hooks or change the exposure tier to obtain a
   green result. A refusal is a separate cause from the index lock: resolve it
   through the hook owner's existing correction/acceptance procedure and verified
   authorization, then preflight again. Review the scanner's actual matched text:
   a prefix exception covers later suffix changes in that file, not one complete
   path literal. Missing authority leaves that finding blocked; do not rewrite
   append-only originals or invent a baseline exception.
5. **Recover only the authorized abandoned lock.** Proceed only after the writer
   has released it or its owner has confirmed abandonment, and existing task
   authorization covers this exact recovery action. Recheck HEAD, index, originals,
   lock identity/hashes and occupancy immediately before mutation. A changed or
   re-created lock ends this attempt. Acquire the application's recovery mutex
   when available, move the exact lock to a new non-overwriting quarantine path,
   and independently verify its preserved bytes and the source-path absence.
   Release a mutex the normal snapshot command needs before invoking that command.
   Do not install automatic lock deletion. A rollback must not overwrite a newly
   created lock/index or undo completed commits; retain the quarantine and let the
   owner select the recovery when state has advanced.
6. **Resume and verify the real result.** Use the application's existing explicit
   snapshot retry, keeping its original hooks and path scope. Read every command
   to a terminal result. Independently query snapshot health and compare each
   approved original file with both its pre-recovery hash and committed HEAD blob.
   Confirm unrelated staged paths survived. A successful commit alone does not
   prove all snapshot files caught up. New concurrent data ends the frozen
   comparison: preserve it and resume from its current state, never restore old
   bytes to force a match. Stop when the requested files are snapshotted, originals
   are unchanged and quarantine remains recoverable, or report the exact remaining
   ownership, permission or hook failure without repeating an unchanged attempt.

## Mental model: nothing is gone until gc runs

A commit is an immutable object in `.git/objects`. Deleting a branch, `reset --hard`, a bad
rebase, or `stash drop` only removes a *reference* to the commit — the object itself survives
until `git gc` prunes unreachable objects. The reflog keeps a ref alive for **~90 days**
(reachable) / **~30 days** (already unreachable), which is why same-day recovery almost always
works. So the recovery mindset is: **find the dangling object, point a ref at it, done.** The
one thing that permanently loses work is `gc` running while nothing references it — which is why
"preserve before cleanup" (below) matters.

**Deleting a branch is the exception to that rule.** `git branch -D <name>` deletes the branch's own
reflog (`logs/refs/heads/<name>`) along with the ref, so the "~90 days" window quoted above does
**not** cover the deleted branch's tip. What keeps it alive afterwards is only whatever *other* reflog
happens to mention it — HEAD's own, or a checkout record — and that is luck, not a window you can
plan around. Measured 2026-09-22 on a scratch repo: after deleting a checked-out branch,
`git gc --prune=now` still kept the tip (HEAD's reflog was a reachability root), and only
`git reflog expire --expire-unreachable=now --all` followed by `gc --prune=now` took it.
**So "gc has not taken it yet" is not a safety signal — the object is one expire away.**
**Criterion: before `-D`, capture the tip with `git rev-parse <branch>` and run
`git cat-file -e "<sha>^{commit}"`; 0 means the object is in the local store, and that is the case worth
preserving.** Non-zero is genuinely ambiguous *for this form*, so do not read it as a verdict either
way: its stderr is always `fatal: Not a valid object name <whatever-you-typed>^{commit}`, so a
mistyped SHA and an object `gc` already collected print the same words (measured 2026-09-22). What
settles it in practice — if the SHA came straight from `git rev-parse` moments ago, non-zero means the
local object is already gone and the only copies left are whatever you pinned or pushed earlier.
**Which is why the pin/push below happens *before* the delete, not after reading this probe.** (The
`… -e <branch>:<path>` form has the richer stderr — it distinguishes a missing path from a bad branch
— but it answers a different question; see [../SKILL.md](../SKILL.md) § Troubleshooting.) Nor are a
successful probe plus a completed preserve deletion authority: worktree-removal authority does not
authorize branch deletion ([merge_verification.md](merge_verification.md) § Worktree retirement) —
`-D` still needs the verified backup and explicit authorization.

## The authoritative "is anything at risk" check

Before anything else, answer the only question that matters — *is any committed or uncommitted
state present only locally?* When every worktree/ref/tag/reflog/stash/dangler enumerated by the full audit
is inside the declared evidence scope, check every place local work hides:

```bash
scripts/git_loss_audit.sh
```

If any enumerated surface is excluded, the script is out of scope because it has no exclusion flag.
Use the authorized checkout/ref's own `status`, `HEAD`, `git log HEAD --not --remotes`, and exact
remote-ref lookup instead, and state that other worktrees/refs/tags/reflogs/stashes/danglers were not audited.

- **The zero-risk verdict requires completed scans and no pending local state.** That means no
  local-only commits, dirty/unavailable worktrees, stashes, reflog-only/dangling commits, or non-commit refs
  awaiting manual object-preservation review. An incomplete scan cannot establish this verdict.
- **Any reported item = inspect it before cleanup.** Local-only commits and dirty/unavailable
  worktrees, failed content scans, and Git scan diagnostics make the script exit 1;
  stashes, reflog-only/dangling commits and non-commit refs stay exit 0 but still need triage or preservation before
  branch, stash, or worktree deletion.

The audit reads every worktree's reflogs as well as its current HEAD. Default `fsck --dangling`
does not report commits retained only by reflogs. Preserve an authorized reflog-only SHA with the
targeted pin below before expiring its log or retiring worktree metadata; the whole-set
`git_preserve_danglers.sh` helper scans true danglers only and does not pin reflog-only commits.

Why the script instead of only `git log HEAD --branches --tags --not --remotes`: that command
catches the current detached HEAD and tag-only commits, but misses a detached HEAD in a different
linked worktree and every uncommitted tracked/untracked file. The script enumerates all worktree
HEADs and inspects each checkout directly.

Do **not** substitute `git status` or ahead/behind counts for this — they answer different
questions. To confirm a single commit is safe on a remote:

```bash
git branch -r --contains <sha>       # lists remote branches that contain it (empty = local-only)
```

## Linked worktrees and detached worktree HEADs

Treat each authorized path from `git worktree list --porcelain` as a separate working tree. Run
status with `git -C <path>` only against paths inside the evidence scope. A detached linked worktree
can carry a unique commit even when every named branch is on a remote; the full loss audit includes
those HEADs explicitly, so do not run it when another linked path is excluded.

Before removal, require empty tracked/untracked status **and a separate ignored-file inventory**,
exact HEAD capture, content containment proof against a fresh base, a verified targeted bundle of
the worktree's branch or collision-checked recovery ref, and current-session deletion authority.
Only then try normal `git worktree remove`, followed by path/registration/ref postcondition
checks. Its clean-submodule exception in the complete gate below permits one force flag only after
a specific submodule refusal and independent module preservation; it does not permit removal of
dirty, unknown, locked, occupied or incompletely preserved state. The bundle preserves the
superproject's objects, not module-private objects or ignored files; copy any ignored item that is not
proven reproducible and verify it against a recorded pre-removal
content hash. Freeze the complete ignored path/type/hash-or-link-target manifest, including
disposable entries. After authority, repeat both status checks and rebuild that manifest; any
added, missing, or changed entry aborts, and the removal command must come next. Recheck every
surviving copy afterward. The complete gate lives in
[merge_verification.md](merge_verification.md) § Worktree retirement.

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

**The third parent — untracked files a stash silently carries.** A stash made with
`git stash -u` (or `-a`) stores untracked files in a **third parent commit** (`stash@{N}^3`),
and `git stash show -p` **does not display them** — it only shows the tracked diff. Two
consequences that bite in real recoveries:

- **Inspecting**: judging a stash by `stash show -p` alone under-reports what it holds. Check for
  the third parent explicitly, and list what's inside:

  ```bash
  git rev-parse -q --verify 'stash@{0}^3' && git ls-tree -r --name-only 'stash@{0}^3'
  ```

- **Exporting**: a `.patch` backup of the stash loses the untracked half. Export both parts —
  patch for the tracked diff, `git archive` for the third-parent tree:

  ```bash
  git stash show -p --binary 'stash@{0}' > stash0.patch
  git archive 'stash@{0}^3' -o stash0-untracked.tar     # only if ^3 exists
  ```

  `scripts/git_export_before_drop.sh` does both automatically for every stash it exports.
  (Real case: a "finish later" stash carried 10 untracked files — 929 insertions including a
  545-line test file — that a patch-only backup would have dropped without a word.)

**Index-shift trap when dropping several stashes**: indices renumber on every drop —
after `drop stash@{0}`, the old `stash@{1}` *becomes* `stash@{0}`. Drop from the **highest
index down** so each name still means what your backups say it means.

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

**One more place to check before declaring a deleted branch gone: the hosting platform, not
just this local clone.** If the branch had an open or merged pull request, GitHub keeps that
PR's head addressable at `refs/pull/<N>/head` even after the source branch itself is deleted
(verified on a real repository: `refs/pull/<N>/head` still resolved to the original head SHA
after the branch was deleted). Check read-only first, then fetch and recover:

```bash
git ls-remote origin "refs/pull/<N>/head"                  # read-only: does it still resolve?
git fetch origin "refs/pull/<N>/head"
git branch restored/pr-<N> FETCH_HEAD
```

Other hosting platforms expose this under different ref names — check what the platform
actually serves before assuming this exact path works there too.

## Preserve: pin authorized danglers so gc can never take them

Dangling commits are recoverable **only until gc runs**. For a specific inspected commit that is
inside the preservation scope, pin exactly that SHA under a hidden ref namespace—a referenced
object is never collected:

```bash
git update-ref refs/dangling-backup/<sha> <sha> 0000000000000000000000000000000000000000
git show refs/dangling-backup/<sha>       # confirm the exact object that was pinned
```

Use `scripts/git_preserve_danglers.sh` only when the Outcome contract explicitly includes every
dangling commit it will enumerate; it is a whole-set helper, not the default. Why a hidden
`refs/dangling-backup/*` and not `git stash store`? These refs don't appear in `git branch` or
`git stash list`, so they protect the authorized objects without turning branch/stash lists into
noise, and you can delete them once their content is verified safe elsewhere.

Bundling that same commit needs a ref too — `git bundle create` refuses a bare SHA with
`fatal: Refusing to create empty bundle` even though the commit exists (measured). Bundle the
`refs/dangling-backup/<sha>` ref just pinned above by name; a commit with no ref at all needs one
created first (`git update-ref refs/backup/<name> <sha>`) before it can be bundled.

**The same error string names more than one cause, and one of them is a trap.** Above: "the positive
revision has no ref" (a bare SHA) — create a ref first. Below: "the negation range is empty", meaning
`<sha>`'s content is **already in** the ref you excluded and there is no increment to preserve; measured
2026-09-22 across three repos, it fired on exactly the branches the patch-id set comparison had already
confirmed contained. The trap: `git bundle create out.bundle ^<ref> <bare-sha-not-in-<ref>>` prints the
*identical* message while the real cause is still "no ref" — building that SHA into a ref first makes
the bundle succeed. **Criterion: never branch on the error string. Create the ref first
(`git update-ref refs/backup/<name> <sha>`), retry, and only an empty result *then* means "nothing to
preserve". The cross-check is `git format-patch <merge-base>..<head>`, read as "no output **and exit
0**" — an empty stdout with a non-zero exit is a malformed range, not containment.**

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
- Git `worktree` documentation: <https://git-scm.com/docs/git-worktree>
- Git `bundle` documentation: <https://git-scm.com/docs/git-bundle>
- Git `merge-tree` documentation: <https://git-scm.com/docs/git-merge-tree>
