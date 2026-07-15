---
name: git-safety-net
description: >-
  Prevent and recover from local-Git disasters — commits stranded on the wrong or
  unpushed branch, orphaned/dropped stashes, dangling commits about to be
  garbage-collected, work that seems lost after heavy branch/stash/rebase juggling
  or parallel-agent work, and "is everything actually merged?" uncertainty. Use
  whenever the user fears they lost code, asks to recover a deleted commit / branch
  / stash, wonders what is still unmerged, needs to prove nothing was dropped after
  rebasing or deleting branches, resolves a version/lockfile collision between two
  branches, or wants habits so a branch mess never loses work again. Triggers on
  "did I lose work", "recover lost commit", "restore deleted branch", "stash
  disappeared", "is everything merged", "what's not merged", "git reflog", "dangling
  commits", "分支灾难", "误删分支/commit", "stash 丢了", "确认全部合并了". This is
  LOCAL-Git safety and forensics — distinct from GitHub PR/API operations (github-ops)
  and routine repo setup/sync (auto-repo-setup).
---

# Git Safety Net

Prevent losing work in a tangle of branches/stashes/rebases, and recover it forensically
when something already went sideways. The commands here are all **read-only or additive**
until a step is explicitly labeled destructive — recovery must never make the loss worse.

## Entry router — pick the mode from what the user is worried about

| The user says / needs… | Go to |
|---|---|
| "I think I lost a commit / branch / stash", "recover the deleted X", "git reflog" | **Mode A — Recover** |
| "did I lose anything?", after a messy rebase / branch-delete / parallel-agent session | **Mode B — Audit & preserve** |
| "is everything merged?", "what's still not on main?", before deleting old branches | **Mode C — Verify merged** |
| "so this never happens again", starting parallel/multi-branch work | **Mode D — Prevent** |

When in doubt, **run Mode B first** (`git_loss_audit.sh`) — it is cheap, read-only, and tells
you whether anything is actually at risk before you decide what to do.

## The five load-bearing rules (internalize these; the modes apply them)

1. **`git log HEAD --branches --tags --not --remotes` is the authoritative "what would be lost"
   check** (plus `git stash list`). It lists commits reachable locally — from HEAD (catches
   detached-HEAD work), a branch, or a tag — but on *no* remote, the true at-risk set. Plain
   `--branches` misses detached-HEAD and tag-only commits. Empty = zero loss. Ahead/behind counts
   and `git status` do **not** answer this.
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

**Step 1 — audit (read-only).** What, if anything, is at risk of loss right now:

```bash
scripts/git_loss_audit.sh          # defaults to remote "origin"; pass a remote name to override
```

Expected output: counts of **local-only commits** (reachable from HEAD/a branch/a tag but on no
remote — the real loss risk, and it catches detached-HEAD and tag-only work), **stashes**
(local-only by nature), and **dangling commits** (orphaned, reflog-reachable now, gc-eligible
later), plus a one-line verdict. `local-only: 0  stashes: 0  dangling: 0` means nothing is at risk.
Exit is 1 only when local-only commits exist (the surprising, actionable case); stashes and
danglers are reported but stay exit 0 so a routine stash doesn't cry wolf.

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

## Scripts (execute these; they are read-only unless noted)

| Script | Does | Mutates? |
|---|---|---|
| `scripts/git_loss_audit.sh [remote]` | Report local-only + dangling commits; verdict | No (read-only) |
| `scripts/git_preserve_danglers.sh [--patch-dir DIR]` | Pin danglers to `refs/dangling-backup/`, optional patches | Adds refs only (never deletes/gc) |
| `scripts/git_verify_branch_merged.sh <branch> [base]` | Content-level MERGED/UNMERGED verdict for one branch | No (read-only) |

All three run from the repository root. They only ever `fetch`, `log`, `diff`, `show`,
`cat-file`, `rev-list`, `fsck`, `for-each-ref`, and (preserve only) `update-ref` — never
`checkout`, `reset`, `push`, or `gc`, so they are safe to run in a dirty tree or alongside
other agents.

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
- **`refs/dangling-backup/*` refs are cluttering things later** — once you've confirmed (Mode C)
  their content is on a remote, delete them with `git for-each-ref --format='%(refname)'
  refs/dangling-backup/ | xargs -n1 git update-ref -d`. Only after you've verified.

## Next step

After recovery/audit, if the repo also needs routine setup, safe commit/push, conflict handling,
or handoff hygiene, that's the `auto-repo-setup` skill's job (invoke `/auto-repo-setup`) — this
skill is the forensic/recovery layer, that one is the routine-workflow layer.
