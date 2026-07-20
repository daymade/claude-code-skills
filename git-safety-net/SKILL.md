---
name: git-safety-net
description: >-
  Audits, preserves, recovers, and safely retires local Git state: unpushed or
  wrong-branch commits, dirty or detached worktrees, forgotten duplicate clones of the
  same repo, untracked work no bundle can back up, orphaned stashes, dangling commits,
  stale branches, and squash/rebase merge uncertainty. Use when the user fears work was
  lost; asks to recover a commit or branch; asks whether a worktree, clone, or scratch
  directory can be deleted; wants everything converged onto one main branch; or
  needs proof that cleanup will not drop work. Use it even after an audit reported clean
  — the usual gap is scope: every in-repo command is blind to a second clone elsewhere
  on disk. Triggers on "did I lose work", "is everything merged", "is anything else
  lost", "safe to delete this clone", "clean up old branches/stashes", "only keep one
  main branch", "git reflog", "dangling commits", "分支灾难", "误删分支/commit",
  "worktree 能删吗", "还有没有丢的东西", "只保留一个主分支".
  Covers local-Git forensics, not GitHub PR/API operations or routine sync.
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
| "clean up worktrees/stashes/branches", "converge everything onto main", "only keep one main branch" | **Mode E — Retire safely** |
| "an audit already said it's clean, but is anything *else* lost?", "check again" | **Mode B, starting at Step 0** — a repeat request usually means the first pass had the wrong scope, not that it looked carelessly |

When in doubt, **run Mode B first**, beginning with `git_find_all_checkouts.sh` (Step 0) and then
`git_loss_audit.sh` in each checkout it finds. Both are cheap and non-destructive, and they answer
"is anything at risk" for the whole machine rather than for whichever directory you started in.

## The six load-bearing rules (internalize these; the modes apply them)

1. **Get the SCOPE right before you trust any verdict: every instrument here only sees the
   repository it runs in.** `git worktree list`, `git branch -a`, `git fsck`, `git stash list`,
   `git log --not --remotes` — all of them are structurally blind to an **independent clone** of
   the same repository elsewhere on the machine. A linked worktree (`git worktree add`) has a
   gitlink *file* pointing home, so it shows up; a second `git clone` has its own complete `.git`
   and no back-reference, so it shows up in **nothing**. Run `git_find_all_checkouts.sh` first —
   otherwise a clean audit means "clean in this one directory," which is not the question the
   user asked. Real incident: a repository audited clean, every branch pushed, while 440 lines of
   a working feature sat as untracked files in a sibling clone one `rm -rf` from gone.
   **Scope has a second axis: TIME.** Every `origin/*` ref is a cached snapshot from your last
   fetch, not the remote — so `git fetch --all --prune` before you trust any verdict that depends
   on one. Read a stale cache in the right direction: for *"what would be lost"* it errs safe
   (it can over-report unpushed work, never hide it), which is why the scripts here still run
   offline. For *"is this already upstream?"* it fails the other way — work the remote already
   has reads as unique, so you re-ship it, and if the remote improved it meanwhile your "restore"
   silently **reverts** those improvements while looking like a rescue. Real incident: a
   comparison base one day old made an already-merged change look unshipped; the rescue PR would
   have reverted three fixes a later review added on top, one of them a security fix.
2. **Run `git_loss_audit.sh` for the authoritative "what would be lost" check *within a
   checkout*.** It compares the current HEAD, every linked-worktree HEAD, local branches, and tags
   against every remote, then inspects each worktree for tracked/untracked changes plus stashes and
   dangling commits. The shorter `git log HEAD --branches --tags --not --remotes` misses a detached
   HEAD in a different worktree and all uncommitted files. Ahead/behind counts do **not** answer
   this. Run it once per checkout that rule 1 turned up, not just in the one you happen to be in.
3. **`git reflog` is the first move for "I lost a commit," not `fsck`.** Reflog records every
   HEAD position (commits, checkouts, resets, rebases) for ~90 days and the lost commit is
   usually in its top few lines. `git fsck` is the deeper net for commits reflog can't reach.
4. **Preserve before you clean up — and know which backup tool can actually reach the work.**
   Pin at-risk/dangling commits somewhere garbage collection can't reach them *before* deleting a
   branch, running `gc`, or force-pushing. Cleanup is reversible only while a ref (or the reflog
   window) still points at the work. **Critical asymmetry: `bundle`, `archive`, and `format-patch`
   can only reach objects git already knows about.** An untracked file that was never `git add`ed
   and never `stash -u`ed is invisible to all three — the copy on disk is the only copy, so
   preserving it means literally copying the file out. Backing up "the repository" and believing
   untracked work came along is how a clean-looking backup silently omits the only thing at risk.
5. **Verify "merged" by CONTENT, never by commit count.** After a squash-merge, `main..branch`
   shows the branch's original commits as "unmerged" even though their content is on main —
   often 100+ phantom commits. Judge with file/blob comparison, not counts (Mode C).
6. **For a high-stakes "is everything merged?" call, verify adversarially — ideally with a
   fan-out of independent agents each trying to *disprove* it.** One reviewer (human or model)
   scanning many branches reliably misses a real gap; independent cross-checks catch it. Give at
   least one agent the explicit job of widening the *scope* (rule 1) rather than re-checking the
   branches already on the table — scope gaps hide from reviewers who accept the given frame.

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

**Step 0 — establish the scope (rule 1).** Find every checkout of this repository on the machine,
including the independent clones no in-repo command can see:

```bash
scripts/git_find_all_checkouts.sh              # defaults to this repo's parent + grandparent
DEPTH=6 scripts/git_find_all_checkouts.sh ~    # widen when clones live far from each other
```

It matches sibling checkouts by normalized remote URL (so the SSH and HTTPS forms of one
repository compare equal), falling back to **any shared commit history** whenever either the current
or a candidate checkout has no `origin`. That history check works for shallow clones that cannot
see the repository's true root. It never matches by directory name, because an independent clone
is usually named differently from the original (`repo` vs `repo-hotfix`), which is exactly when
name matching fails. It canonicalizes path aliases before identifying the current checkout,
disables repository-provided fsmonitor commands while inspecting candidates, and treats commits
reachable from any locally known remote-tracking ref as pushed even when a branch has no upstream.
Exit is 1 when any *other* checkout holds uncommitted, untracked, unpushed, or uninspectable work.
Run Steps 1–2 in **each** checkout it reports, then treat "nothing at risk" as a claim about all of
them, not just this one.

### Maintainer verification

Run the isolated regression suite after changing checkout discovery:

```bash
uv run python -m unittest discover -s tests -p 'test_*.py'
```

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

**Untracked files need a different tool — plain copying (rule 4).** Everything above moves *git
objects*; a file git was never told about is not one. Preserve those explicitly, and keep the
three channels separate so a later reader knows what each restores:

```bash
git -C <checkout> status --porcelain | grep '^??'                     # what is untracked
cp <each-untracked-path> <backup>/                                    # the ONLY copy — plain cp
git -C <checkout> diff > <backup>/uncommitted.diff                    # tracked-but-uncommitted
git -C <checkout> bundle create <backup>/history.bundle origin/main..HEAD   # unpushed commits
git bundle verify <backup>/history.bundle                             # prove it restores
```

Write a one-paragraph `README` beside them saying where they came from, which branch, and when the
session stopped. A backup nobody can interpret six weeks later is only slightly better than none —
and the person reading it will not be the person who made it.

## Mode C — Verify everything is merged (without being fooled by counts)

The trap: a stale branch shows "173 commits ahead of main" yet every line is already on main
(squash-merge artifact). Never conclude "unmerged" from counts. Per-branch content check:

```bash
scripts/git_verify_branch_merged.sh <branch> [<base>]   # base defaults to origin/main
```

This mode is the one direction where a stale base is *unsafe* (rule 1): judged against yesterday's
`origin/main`, a branch whose content landed hours ago still reads UNMERGED, and "rescuing" it
re-applies an older version over whatever was built on top. The script fetches first for exactly
that reason — but if the fetch fails it falls back to cached refs and says so **on stderr only**.
Treat that line as a blocker, not a footnote: rerun once the network is back before acting on the
verdict. Comparing by hand (`git diff origin/main <branch>`, `git log origin/main..<branch>`) has
no such safety net at all — fetch yourself first, every time.

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
- **If you truly need a second checkout, make it a worktree — never a second `git clone`.** Both
  are extra places to forget work, which is why commit-then-switch above is still the default. But
  the failure modes are not equal: a linked worktree announces itself in `git worktree list`, so
  every audit finds it, while an independent clone is invisible to every command run from the
  original repository. Choosing `clone` for a few days of parallel work quietly opts out of all
  the safety tooling. When a clone already exists (a colleague made it, a script made it, you
  inherited it), register it somewhere the team actually reads and retire it the day it's done —
  and until then, treat it as an audit target in its own right, not as a scratch directory.
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
Start with `git_find_all_checkouts.sh` — `git worktree list --porcelain` alone will not show an
independent clone, and those are the leftovers most likely to be forgotten — then `git_loss_audit.sh`
inside each checkout it reports. Treat every checkout as an independent place where uncommitted or
detached work can hide. Then triage, backup, and retire:

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
- **Independent clones: there is no safe git-level command — only `rm -rf`, which git cannot
  undo.** `git worktree remove` does not apply (it isn't a worktree) and refuses to help, so the
  usual "the tool will stop me if it's unsafe" backstop is absent here. Make the check explicit
  instead: gate the deletion on the backup actually existing, so a missing file aborts rather
  than being noticed afterwards.

  ```bash
  for f in <backup>/<untracked-file> <backup>/uncommitted.diff <backup>/history.bundle; do
    [ -s "$f" ] || { echo "MISSING: $f — refusing to delete"; exit 1; }
  done
  rm -rf <clone-path>
  ```

  Prefer deleting one clone at a time with its own verification over a loop across several — a
  glob that deletes five directories has five chances to be wrong and reports none of them.

**Recovery, if you regret it:** patches re-apply with `git apply`; the untracked tar extracts
in place; the bundle restores full history via `git fetch <file>.bundle <branch>:restored/<branch>`.

## Scripts (execute these; they are non-destructive unless noted)

| Script | Does | Mutates? |
|---|---|---|
| `scripts/git_find_all_checkouts.sh [root ...]` | Find every checkout of this repo on the machine — including independent clones invisible to `git worktree list` — and flag those holding uncommitted/untracked/unpushed work, plus how stale each one's cached remote refs are (`STALE_AFTER=<s>`, default 3600) | Nothing (read-only, no fetch) |
| `scripts/git_loss_audit.sh [remote]` | Refresh one remote, then report every worktree, local-only commit, stash, and dangler | Remote-tracking refs only |
| `scripts/git_preserve_danglers.sh [--patch-dir DIR]` | Pin danglers to `refs/dangling-backup/`, optional patches | Adds refs only (never deletes/gc) |
| `scripts/git_verify_branch_merged.sh <branch> [base]` | Refresh remotes, then give a content-level MERGED/UNMERGED verdict | Remote-tracking refs only |
| `scripts/git_export_before_drop.sh [--all-stashes] [--stash N] [--branch B] [--all-refs] [--out DIR]` | Export stashes plus selected branches or every current ref into verified bundles | Writes backup files only (never drops/deletes) |

All five run from the repository root. They only ever `find`, `fetch`, `log`, `diff`, `show`,
`status`, `cat-file`, `rev-list`, `rev-parse`, `fsck`, `for-each-ref`, `remote get-url`,
`stash show`, `archive`, `bundle create/verify`, and (preserve only) `update-ref` — never
`checkout`, `reset`, `push`, `stash drop`, `branch -d`, or `gc`, so they are safe to run in a
dirty tree or alongside other agents. `git_find_all_checkouts.sh` additionally never fetches, so
it works offline and behind a proxy.

## Troubleshooting

- **An audit came back clean but the user still thinks something is missing** — believe them and
  suspect **scope, not thoroughness**. The in-repo instruments were probably all correct about the
  one directory they could see. Run Step 0 (`git_find_all_checkouts.sh`) before re-running anything
  you already ran; repeating a correctly-executed check in the wrong scope returns the same clean
  answer with more confidence behind it, which is worse than the first pass.
- **`git_find_all_checkouts.sh` finds nothing, but you're fairly sure another copy exists** — three
  likely causes, in order: (1) the copy lives outside the default roots (pass an explicit root such
  as `~`, and raise `DEPTH`); (2) it sits under a pruned path — the sweep skips `node_modules`,
  `.venv`, `vendor`, `.terraform`; (3) its `origin` points somewhere else entirely (a fork, or a
  path remote), so remote matching rejects it — check with `git -C <suspect> remote -v` and compare
  root commits by hand: `git rev-list --max-parents=0 HEAD`. A copy made by `cp -r` before the repo
  had any remote will only match on root commit.
- **`git_loss_audit.sh` reports dangling commits that look like old stashes** — expected after
  stash-heavy work. They're reflog-reachable now; pin them with `git_preserve_danglers.sh` if you
  want them past the gc window, then inspect with `git show <sha>` at leisure.
- **A branch shows huge "commits ahead" but you suspect it's merged** — trust
  `git_verify_branch_merged.sh` (content), not the count. See Mode C.
- **`git fetch` in a script hangs behind a proxy / offline** — loss detection still works on
  cached remote refs, because a stale cache can only over-report unpushed work. Merge and
  supersession verdicts (Mode C, Mode E) are the exception and genuinely need a fetch; without
  one, say so in the report rather than presenting the verdict as settled.
- **Your work looks unmerged, but the repository moved while you were working** — check the clock
  before you rescue anything: `git_find_all_checkouts.sh` prints when each checkout last fetched,
  and `git log --oneline <cached-base>..origin/main` after a fresh fetch shows what arrived
  meanwhile. A long session is the risk window — the base you compared against at the start can be
  many hours old by the end. Symptom to recognise: a change you know you committed appears absent
  upstream, so you prepare to re-ship it. Fetch first, then compare by content; if it did land,
  check whether anyone improved it before re-applying your version over theirs.
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
