---
name: git-safety-net
description: >-
  Audits, preserves, recovers, and safely retires local Git state: unpushed or
  wrong-branch commits, dirty or detached worktrees, orphaned/dropped stashes,
  dangling commits, stale branches, and squash/rebase merge uncertainty. Use when
  the user fears work was lost; asks to recover a commit, branch, stash, or reflog
  state; asks whether a worktree can be deleted; wants all valuable state converged
  onto main; or needs proof that cleanup/rebase/branch deletion will not drop work.
  Triggers on "did I lose work", "is everything merged", "safe to delete this
  worktree", "clean up old branches/stashes/worktrees", "git reflog", "dangling
  commits", "分支灾难", "误删分支/commit", "worktree 能删吗", "确认全部合并了".
  Covers local-Git forensics, not GitHub PR/API operations or routine repository sync.
---

# Git Safety Net

Prevent losing work in a tangle of branches/stashes/rebases, and recover it forensically
when something already went sideways. The commands here are all **non-destructive or additive**
until a step is explicitly labeled destructive — recovery must never make the loss worse.

## Entry router — pick the mode from what the user is worried about

| The user says / needs… | Go to |
|---|---|
| "I think I lost a commit / branch / stash", "recover the deleted X", "git reflog" | **Mode A — Recover** |
| "did I lose anything?", "what worktrees/stashes/branches remain?", after a messy session | **Mode B — Audit & preserve** |
| "is everything merged?", "what's still not on main?", before deleting old branches | **Mode C — Verify merged** |
| "so this never happens again", starting parallel/multi-branch work | **Mode D — Prevent** |
| "clean up worktrees/stashes/branches", "converge everything onto main" | **Mode E — Retire safely** |

When in doubt, **run Mode B first** (`git_loss_audit.sh`) — it is cheap, non-destructive, and tells
you whether anything is actually at risk before you decide what to do.

## The five load-bearing rules (internalize these; the modes apply them)

1. **Run `git_loss_audit.sh` for the authoritative "what would be lost" check.** It compares the
   current HEAD, every linked-worktree HEAD, local branches, and tags against every remote, then
   inspects each worktree for tracked/untracked changes plus stashes and dangling commits. The
   shorter `git log HEAD --branches --tags --not --remotes` misses a detached HEAD in a different
   worktree and all uncommitted files. Ahead/behind counts do **not** answer this.
2. **`git reflog` is the first move for "I lost a commit," not `fsck`.** Reflog records every
   HEAD position (commits, checkouts, resets, rebases) for ~90 days and the lost commit is
   usually in its top few lines. `git fsck` is the deeper net for commits reflog can't reach.
3. **Preserve before you clean up.** Pin at-risk/dangling commits somewhere garbage collection
   can't reach them *before* deleting a branch, running `gc`, or force-pushing. Cleanup is
   reversible only while a ref (or the reflog window) still points at the work.
4. **Verify "merged" by CONTENT, never by commit count.** After a squash-merge, `main..branch`
   shows the branch's original commits as "unmerged" even though their content is on main —
   often 100+ phantom commits. Judge with file/blob comparison, not counts (Mode C).
5. **For a high-stakes "is everything merged?" call, verify adversarially — ideally with a
   fan-out of independent agents each trying to *disprove* it.** One reviewer (human or model)
   scanning many branches reliably misses a real gap; independent cross-checks catch it.

## Mode A — Recover lost work

A commit/branch/stash that "disappeared" is almost always still in the object store for ~90 days.
Full ladder (reflog → fsck → dangling) with exact commands and the canonical Git facts:
**[references/recovery_playbook.md](references/recovery_playbook.md)**. The 30-second version:

```bash
git reflog --date=iso | head -40          # find the lost HEAD position (most recoveries are here)
git show <sha>                            # CONFIRM it's the right commit before acting
git switch -c rescue/<name> <sha>         # recover onto a NEW branch — never reset onto live work
```

If reflog doesn't show it (e.g. a dropped stash, an orphan from a rebase), fall through to
`git fsck --dangling` — see the playbook.

## Mode B — Audit what's at risk, then preserve it

**Step 1 — audit (non-destructive).** What, if anything, is at risk of loss right now:

```bash
scripts/git_loss_audit.sh          # defaults to remote "origin"; pass a remote name to override
```

Expected output: every worktree with branch/detached state and cleanliness, plus counts of
**local-only commits**, **dirty/unavailable worktrees**, **stashes**, and **dangling commits**.
Exit is 1 when commits exist on no remote or a worktree is dirty/uninspectable; stashes and
danglers remain visible but do not alone make the audit fail. Exit 0 is therefore not permission
to delete a visible stash/dangler: triage or preserve every reported item. Do not claim cleanup is
safe until the named worktree is clean and its HEAD is proven contained or deliberately preserved.

**Step 2 — preserve (additive, gc-proof).** If anything showed up, make it un-loseable *before*
touching branches or running gc:

```bash
scripts/git_preserve_danglers.sh --patch-dir ~/git-danglers   # pin + export patches
```

This pins every dangling commit under `refs/dangling-backup/<sha>` (garbage collection can never
reach a referenced commit) without cluttering `git branch`, and optionally writes a `.patch` per
non-stash commit. For a *specific* important commit, also give it the full treatment — local
branch **and** a pushed remote branch **and** a `git format-patch` file — so a single disk or a
single `git gc` can't take it. Details + why triple-backup: **[references/recovery_playbook.md](references/recovery_playbook.md)**.

## Mode C — Verify everything is merged (without being fooled by counts)

The trap: a stale branch shows "173 commits ahead of main" yet every line is already on main
(squash-merge artifact). Never conclude "unmerged" from counts. Per-branch content check:

```bash
scripts/git_verify_branch_merged.sh <branch> [<base>]   # base defaults to origin/main
```

It reports **MERGED (ancestor)** or **MERGED (content contained)** — safe to delete — versus
**UNMERGED / NEEDS REVIEW**, listing the files the branch would still change. The verdict is sound,
not heuristic: it does a trial 3-way merge of the branch *into* the base with `git merge-tree`
(in memory, no checkout) and only says "safe to delete" when that merge changes nothing — so a
squash-merged branch reads MERGED despite a nonzero commit count, while a revert/edit/new-file the
base lacks reads UNMERGED. It is **safety-biased**: anything it can't prove contained is reported
for review, because a false "merged" loses work while a false "unmerged" only costs a look. Full
technique (and why `--find-object`/blob heuristics are unsound for auto-decisions), plus the
**adversarial multi-agent verification** pattern for a whole repo of branches (read-only agents,
one per batch, each told to *falsify* "everything is merged," every finding independently
re-checked): **[references/merge_verification.md](references/merge_verification.md)**.

## Mode D — Prevent the disaster

The habits that keep a branch tangle from ever stranding work:
**[references/prevention_practices.md](references/prevention_practices.md)**. The load-bearing few:

- **Commit before you switch — neither `git stash` nor `git worktree`.** Uncommitted work is what
  gets stranded: a `git stash` you later can't find, or edits a `switch` buries. Commit each line
  of work to its own branch and push it early (a committed, pushed branch can't be orphaned), then
  bring it where you need it *live* by merging — not by stashing, and not by spinning up a second
  `git worktree` checkout (which is one more place to forget work and won't even have your
  gitignored deps). A shared working tree with commit-then-switch discipline is the safe default.
- **Push a work-in-progress branch to a remote early.** The one commit only on a local branch is
  the only commit that a dead laptop actually loses.
- **Confirm the current branch before committing** (`git branch --show-current`) — a fix committed
  onto the wrong feature branch is invisible to its real PR and easy to lose on cleanup.
- **If a parallel session switched the shared tree onto its branch** and stranded your uncommitted
  work there, don't commit onto their branch — carry your edits to a branch off the base
  (`git checkout origin/main -b …`, after `git diff --quiet` proves your files match across bases),
  commit only your explicit paths, then switch the tree back to their branch to restore their state.
- **Before any rebase or branch-delete, run the Mode B audit.** Ten seconds; it's the difference
  between "nothing to lose" and finding out after gc.
- **Before bumping a shared version/lockfile, check the base's current value** so two parallel
  branches don't both claim the same bump (a silent collision that blocks the later change from
  shipping).

## Mode E — Retire worktrees, stashes, and branches safely

The opposite worry from Mode A: not "I lost something" but "these leftovers are piling up —
which can I destroy?" Deleting is trivial; **proving each item is superseded is the work**.
Start with `git_loss_audit.sh` and `git worktree list --porcelain`; treat every checkout as an
independent place where uncommitted or detached work can hide. Then triage, backup, and retire:

**Step 1 — classify each leftover: live WIP, or superseded draft?** Evidence ladder, strongest first:

1. **`git cherry <base> <branch>`** — judges by *patch content*, not message text. Every commit
   showing `-` is already on the base (survives rebases and reworded messages); any `+` needs
   the next rungs. Never grep commit messages to decide this — the same work often lands under
   a different message.
2. **Same-file supersession check** — for a stash or `+` commit touching files that were later
   reworked on the base: extract its version of the file and compare with the base's current
   version (`git show <ref>:<path> | wc -l` vs `git show <base>:<path> | wc -l`, then spot-diff).
   If the base's version is a **superset** (has everything the leftover has, plus later work),
   the leftover is a superseded draft. Real case: a stash labeled "unfinished dev" held a 1128-line
   renderer; main's version was 1151 lines — the same functions *plus* a later feature parameter.
   Restoring that stash would have been a regression, not a recovery.
3. **Function/marker-level probe** — grep the base for the leftover's distinctive additions
   (`def new_helper`, a constant, an error string). All present on the base → superseded.
   This catches "absorbed into a refactor" cases where file shapes changed too much for rung 2.

Anything you cannot prove superseded stays alive (same safety bias as Mode C: a false "superseded"
loses work; a false "still live" costs a branch name). One warning that changes verdicts: **the
leftover's label is not evidence** — a stash named "unfinished development" can be a fully-landed
early draft; judge content against the current base, never the name. Worked examples of all three
rungs (including the squash-artifact and absorbed-into-refactor cases):
**[references/merge_verification.md](references/merge_verification.md)** § Supersession triage.

**Step 2 — pin true orphans, then back up every addressable ref:**

```bash
scripts/git_preserve_danglers.sh --patch-dir <backup-dir>/dangling-patches
scripts/git_export_before_drop.sh --all-stashes --all-refs --out <backup-dir>
```

The first command makes unreferenced commits reachable; `--all-refs` then captures branch, stash,
hidden-backup, and linked-worktree HEAD refs in one verified bundle. For a small targeted cleanup,
use repeated `--branch` instead. The exporter never drops or deletes anything.

**Step 3 — destroy, in the safe order:**

- Stashes: drop from the **highest index down** (`drop stash@{2}` before `stash@{1}`) — indices
  shift as you drop, and top-down keeps every number meaning what your backup filenames say.
- Linked worktrees: require a clean `git -C <path> status --short --branch`, record its exact HEAD,
  prove that HEAD is contained/superseded, then use `git worktree remove <absolute-path>` **without
  `--force`** and re-run `git worktree list`. Never remove the primary/current checkout. Follow
  **[references/merge_verification.md](references/merge_verification.md)** § Worktree retirement.
- Local branches: prefer `git branch -d` (refuses unmerged); use `-D` only for items Step 1
  proved superseded, backed up, and the user authorized deleting. Delete remote branches only
  after re-verifying the exact remote and repository visibility/ownership.

**Recovery, if you regret it:** patches re-apply with `git apply`; the untracked tar extracts
in place; the bundle restores full history via `git fetch <file>.bundle <branch>:restored/<branch>`.

## Scripts (execute these; they are non-destructive unless noted)

| Script | Does | Mutates? |
|---|---|---|
| `scripts/git_loss_audit.sh [remote]` | Refresh one remote, then report every worktree, local-only commit, stash, and dangler | Remote-tracking refs only |
| `scripts/git_preserve_danglers.sh [--patch-dir DIR]` | Pin danglers to `refs/dangling-backup/`, optional patches | Adds refs only (never deletes/gc) |
| `scripts/git_verify_branch_merged.sh <branch> [base]` | Refresh remotes, then give a content-level MERGED/UNMERGED verdict | Remote-tracking refs only |
| `scripts/git_export_before_drop.sh [--all-stashes] [--stash N] [--branch B] [--all-refs] [--out DIR]` | Export stashes plus selected branches or every current ref into verified bundles | Writes backup files only (never drops/deletes) |

All four run from the repository root. They only ever `fetch`, `log`, `diff`, `show`,
`cat-file`, `rev-list`, `fsck`, `for-each-ref`, `stash show`, `archive`, `bundle create/verify`,
and (preserve only) `update-ref` — never `checkout`, `reset`, `push`, `stash drop`, `branch -d`,
or `gc`, so they are safe to run in a dirty tree or alongside other agents.

## Troubleshooting

- **`git_loss_audit.sh` reports dangling commits that look like old stashes** — expected after
  stash-heavy work. They're reflog-reachable now; pin them with `git_preserve_danglers.sh` if you
  want them past the gc window, then inspect with `git show <sha>` at leisure.
- **A branch shows huge "commits ahead" but you suspect it's merged** — trust
  `git_verify_branch_merged.sh` (content), not the count. See Mode C.
- **`git fetch` in a script hangs behind a proxy / offline** — the audit still works on cached
  remote refs; pass an already-fetched state or skip the fetch. Loss detection uses local refs.
- **You're on a detached HEAD after checking out a commit** — that commit is safe as long as you
  `git switch -c <branch> HEAD` (or the reflog remembers it for ~90 days). Don't leave important
  new work on a detached HEAD across a `gc`.
- **Only one worktree remains after cleanup** — `git worktree list` always includes the primary
  repository checkout. Do not delete it merely to make the count zero; the goal is one maintained
  checkout, not no checkout.
- **`refs/dangling-backup/*` refs are cluttering things later** — once you've confirmed (Mode C)
  their content is on a remote, delete them with `git for-each-ref --format='%(refname)'
  refs/dangling-backup/ | xargs -n1 git update-ref -d`. Only after you've verified.

## Next step

After recovery/audit, if the repo also needs routine setup, safe commit/push, conflict handling,
or handoff hygiene, that's the `auto-repo-setup` skill's job (invoke `/auto-repo-setup`) — this
skill is the forensic/recovery layer, that one is the routine-workflow layer.
