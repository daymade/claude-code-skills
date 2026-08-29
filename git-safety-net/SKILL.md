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

## Outcome contract — keep the safety net subordinate to the user's job

Before Mode B/E or any command that writes a ref or backup, state four lines in the conversation
(do not create another file):

- **Outcome:** the user-visible end state, in the user's words.
- **Current phase:** what is authorized now. "Later" work is not authorized in this phase.
- **Authorized targets:** named objects this phase may inspect, plus the subset it may change.
- **Stop condition:** observable facts that end the task.

Then enforce these boundaries:

- **Evidence scope is not action scope.** A read-only audit may discover another clone, ref,
   repository, or dangling object. That discovery may widen the report; it does not authorize
   preserving, uploading, merging, deleting, or otherwise changing the newly found object.
- **Authorization is object-specific, not repository-wide by implication.** "Take over",
   "continue", or "finish the cleanup" applies only to the checkout/ref/PR the user identified.
   A collaborator-owned worktree, branch, or PR discovered later stays report-only until the user
   names it as a change target. If the user says to leave it alone, record that exclusion and do
   not inspect its working-tree contents, back it up, merge it, unlock/remove it, or mutate its refs.
- **Preserve the smallest set threatened by the next authorized destructive action.** If the
   current phase is only commit/push/verify and no deletion, reset, gc, history rewrite, or
   worktree removal is authorized, do not create an all-refs bundle or pin every dangler.
- **Classify an artifact before choosing its transport.** Durable project source follows the
   repository's normal Git/LFS policy. A temporary recovery artifact (bundle, working-tree diff,
   snapshot, transport chunk) belongs in a repository-external backup directory. Do not stage,
   commit, push, or route it through Git LFS merely to make the backup remote; Git LFS is for
   durable versioned project binaries, not a fallback transport for temporary recovery material.
- **Treat a new storage or execution surface as a scope change.** A second repository, new
   remote, cloud upload, Git LFS, or full-history export requires re-planning and explicit authority
   when the stated outcome actually depends on it. Do not solve a transport problem the user did
   not ask to create.
- **Prove completion in the user's world.** A remote containing the intended commit, preserved
   WIP, and the requested branch/worktree state are outcomes. Bundle counts, checksums, upload
   receipts, and audit breadth are supporting evidence, never substitutes for that outcome. Stop
   when the contract is satisfied; record unrelated findings separately without acting on them.

## Entry router — pick the mode from what the user is worried about

| The user says / needs… | Go to |
|---|---|
| "I think I lost a commit / branch / stash", "recover the deleted X", "git reflog" | **Mode A — Recover** |
| "did I lose anything?", "what worktrees/stashes/branches remain?", after a messy session | **Mode B — Audit & preserve** |
| "is everything merged?", "what's still not on main?", before deleting old branches | **Mode C — Verify merged** |
| "so this never happens again", starting parallel/multi-branch work | **Mode D — Prevent** |
| "clean up worktrees/stashes/branches", "converge everything onto main", "only keep one main branch" | **Mode E — Retire safely** |
| "an audit already said it's clean, but is anything *else* lost?", "check again" | **Mode B, starting at Step 0** — a repeat request usually means the first pass had the wrong scope, not that it looked carelessly |

When in doubt, run the **smallest read-only probe that selects a mode**. Use Mode B Step 0's
machine-wide discovery only when the outcome is an exhaustive loss audit or the target checkout is
unknown. A named repository/branch/worktree task stays named; findings outside that target are
report-only until the user expands the authorized targets.

## The six load-bearing rules (internalize these; the modes apply them)

1. **Get the EVIDENCE SCOPE right before you trust any verdict, without silently expanding the
   work scope: every instrument here only sees the repository it runs in.** `git worktree list`,
   `git branch -a`, `git fsck`, `git stash list`,
   `git log --not --remotes` — all of them are structurally blind to an **independent clone** of
   the same repository elsewhere on the machine. A linked worktree (`git worktree add`) has a
   gitlink *file* pointing home, so it shows up; a second `git clone` has its own complete `.git`
   and no back-reference, so it shows up in **nothing**. Run `git_find_all_checkouts.sh` first only
   for an exhaustive audit or unknown target; otherwise audit the named target. Real incident: a
   repository audited clean, every branch pushed, while 440 lines of a working feature sat as
   untracked files in a sibling clone one `rm -rf` from gone.
   **Scope has a second axis: TIME.** Every `origin/*` ref is a cached snapshot from your last
   fetch, not the remote — so `git fetch --all --prune` before you trust any verdict that depends
   on one. Read a stale cache in the right direction: for *"what would be lost"* it errs safe
   (it can over-report unpushed work, never hide it), which is why the scripts here still run
   offline. For *"is this already upstream?"* it fails the other way — work the remote already
   has reads as unique, so you re-ship it, and if the remote improved it meanwhile your "restore"
   silently **reverts** those improvements while looking like a rescue. Real incident: a
   comparison base one day old made an already-merged change look unshipped; the rescue PR would
   have reverted three fixes a later review added on top, one of them a security fix.
   **Scope has a third axis: the REF SET itself moves.** A branch inventory and a verified bundle
   prove what existed at one instant; they do not authorize deletion five minutes later. Immediately
   before deleting, re-enumerate local refs and hosting-service branches, then require every target
   ref to still equal the object recorded in the bundle. A new branch, a moved tip, or a new parallel
   PR reopens classification and requires a new bundle. Do not delete against a stale inventory.
   **Scope has a fourth axis: OWNERSHIP.** Repository visibility does not make every visible object
   part of this task. Partition discovered refs/worktrees/PRs into change-authorized, inspect-only,
   and explicitly excluded sets before acting; compute cleanup success over the authorized set.
2. **Run `git_loss_audit.sh` for the authoritative "what would be lost" check *within a
   checkout*.** It compares the current HEAD, every linked-worktree HEAD, local branches, and tags
   against every remote, then inspects each worktree for tracked/untracked changes plus stashes and
   dangling commits. The shorter `git log HEAD --branches --tags --not --remotes` misses a detached
   HEAD in a different worktree and all uncommitted files. Ahead/behind counts do **not** answer
   this. Run it in the named checkout, and in additional Step 0 checkouts only after each is
   explicitly change-authorized. Run this repository-wide script only when every surface it
   enumerates—linked worktrees, local refs/tags, stashes, and dangling commits—is inside the
   declared evidence scope. It has no exclusion flags. Otherwise limit the claim to the authorized
   checkout/ref and use its own `status`, `HEAD`, upstream/remote identity, and `git log HEAD --not
   --remotes` as scoped evidence; report the other surfaces as not audited.
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
5. **Verify "merged" by CONTENT, never by commit count — and know that most content checks are
   also unsound.** After a squash-merge, `main..branch` shows the branch's original commits as
   "unmerged" even though their content is on main — often 100+ phantom commits. But swapping
   counts for the *nearest* content check is not enough: in one audit, three successive
   "surely this is content-level now" instruments each returned a wrong answer — `git cherry`
   (squash rewrites patch-ids → false UNMERGED), a **three-dot** `diff base...ref` used to ask
   "what does base lack" (three-dot answers a different question and **under-reported missing
   files by 5×**), and a file-level existence check (a file present on base can still be missing
   the ref's lines). Only the trial merge (`git merge-tree`, what `git_verify_branch_merged.sh`
   runs) was right every time. Diff-form and rung-by-rung reliability: **[references/merge_verification.md](references/merge_verification.md)**.
6. **For a high-stakes exhaustive "is everything merged?" call that will authorize deletion,
   verify adversarially.** One independent reviewer is the default. Use multiple reviewers only
   when distinct repositories or evidence axes cannot be covered by one pass and the user has
   authorized that fan-out. Make one pass try to falsify the declared evidence scope (rule 1), but
   keep any newly found target report-only under the Outcome contract.

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

**Step 0 — establish the evidence scope (rule 1).** Run machine-wide checkout discovery only when
the Outcome contract calls for an exhaustive audit or the target checkout is unknown. For a named
target, record that checkout and continue to Step 1 without turning an unrelated clone into work.
When exhaustive discovery is warranted, find every checkout of this repository on the machine,
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
For an inspect-only checkout, stop at discovery: Step 1 fetches and changes its remote-tracking
refs. Run Step 1 only after that checkout is change-authorized; apply Step 2 only to authorized
items. A "nothing at risk" claim covers only the checkouts actually audited.

### Maintainer verification

Run the isolated regression suite after changing checkout discovery:

```bash
uv run python -m unittest discover -s tests -p 'test_*.py'
```

**Step 1 — audit (non-destructive).** What, if anything, is at risk of loss right now:

When every worktree/ref/tag/stash/dangler the script enumerates is inside the declared evidence
scope:

```bash
scripts/git_loss_audit.sh          # defaults to remote "origin"; pass a remote name to override
```

When any surface listed above is excluded, skip that script and collect only checkout/ref-scoped
evidence:

```bash
git status --porcelain=v1 --untracked-files=all
git rev-parse HEAD
git log --oneline HEAD --not --remotes
git ls-remote <remote> <authorized-remote-ref>
```

For the full audit, expected output is every worktree with branch/detached state and cleanliness,
plus counts of
**local-only commits**, **dirty/unavailable worktrees**, **stashes**, and **dangling commits**.
Exit is 1 when commits exist on no remote or a worktree is dirty/uninspectable; stashes and
danglers remain visible but do not alone make the audit fail. Exit 0 is therefore not permission
to delete a visible stash/dangler: triage or preserve every reported item. Do not claim cleanup is
safe until the named worktree is clean and its HEAD is proven contained or deliberately preserved.
The scoped path proves only the authorized checkout/ref; it says nothing about excluded worktrees,
other local refs, stashes, or danglers, which must remain listed as not audited.

**Step 2 — preserve only what the next authorized destructive action threatens (additive,
gc-proof).** A finding alone does not need a backup. If deletion, gc, or history rewriting can make
a reported commit unreachable, preserve that exact commit before the action. Use the whole-set
helper only when every reported dangler is actually in the authorized target set:

```bash
scripts/git_preserve_danglers.sh --patch-dir ~/git-danglers   # pin + export patches
```

This pins every dangling commit under `refs/dangling-backup/<sha>` (garbage collection can never
reach a referenced commit) without cluttering `git branch`, and optionally writes a `.patch` per
non-stash commit. For a *specific* important commit, also give it the full treatment — local
branch **and** a pushed remote branch **and** a `git format-patch` file — so a single disk or a
single `git gc` can't take it. Details + why triple-backup: **[references/recovery_playbook.md](references/recovery_playbook.md)**.

**Untracked files need a different tool — plain copying (rule 4).** Put `<backup>` outside the
target repository and every checkout being retired. Everything above moves *git
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
- **In a shared tree, never aim a destructive command at "the current branch" — name the branch
  explicitly.** `reset --hard`, `merge`, and `rebase` all act on *whatever is checked out at the
  instant they run*, so a branch check is stale the moment it returns: a parallel session can
  `switch` in between, and your command lands on **their** branch. This is the inverse of the
  bullet below (that one protects *your* work from *their* switch; this one protects *theirs*
  from *your* command), and re-checking harder does not fix it — the race is inherent. Use the
  checkout-independent forms instead, which name their target and never touch the working tree:
  ```bash
  git branch -f <branch> <target>          # instead of: switch <branch> && reset --hard <target>
  git fetch origin <branch>:<branch>       # fast-forward a branch you are not on
  git push origin <sha>:refs/heads/<branch>
  ```
  Real incident: a `reset --hard origin/main` issued seconds after `git branch --show-current`
  said `main` landed on a parallel session's feature branch and moved it back two commits; the
  follow-up "repair" then missed *again* because the tree had been switched a second time.
  `git branch -f` fixed both in one shot precisely because it never consults the checkout.
- **If a parallel session switched the shared tree onto its branch** and stranded your uncommitted
  work there, don't commit onto their branch — carry your edits to a branch off the base
  (`git checkout origin/main -b …`, after `git diff --quiet` proves your files match across bases),
  commit only your explicit paths, then switch the tree back to their branch to restore their state.
- **If a parallel session is *actively* writing the shared tree** — files keep appearing while you
  work — don't `switch`, `add`, or `reset` at all: each would either strand their uncommitted work
  or trip a worktree guard. When your own change is self-contained (new files, or edits that belong
  on `origin/main` rather than on their in-progress tree), build the commit with plumbing that never
  touches the working tree, then push it to a branch and open a PR. Freeze every candidate as the
  exact Git entry tuple `(mode, object ID, path)` — bytes alone are insufficient because `100755`,
  `120000`, and `160000` carry executable, symlink, and gitlink behavior. The safest source is an
  immutable candidate commit:
  ```bash
  candidate_ref=<immutable-candidate-commit-oid>
  candidate_path=path/to/file
  candidate_entry=$(git ls-tree "$candidate_ref" -- "$candidate_path")
  candidate_mode=$(printf '%s\n' "$candidate_entry" | awk 'NR == 1 { print $1 }')
  candidate_oid=$(printf '%s\n' "$candidate_entry" | awk 'NR == 1 { print $3 }')
  test -n "$candidate_mode" && test -n "$candidate_oid" || exit 1

  candidate_index=$(mktemp /tmp/tinkle_git_index.XXXXXX)
  export GIT_INDEX_FILE="$candidate_index"   # the tree's real index is untouched
  git read-tree origin/main           # start from the pushed base, not the dirty tree
  git update-index --add --cacheinfo "$candidate_mode,$candidate_oid,$candidate_path"
  tree=$(git write-tree)
  commit=$(git commit-tree "$tree" -p origin/main -m "…")   # HEAD does not move
  unset GIT_INDEX_FILE
  rm "$candidate_index"
  git push origin "$commit":refs/heads/<branch>             # open the PR from here
  ```
  For an owned temporary **regular file** that is not yet in an immutable commit, derive its intended
  mode explicitly (`100755` when executable, otherwise `100644`) and hash its bytes; fail instead of
  applying that route to a symlink or submodule. For those entry types, first freeze an immutable
  candidate commit and copy its mode/object tuple as above. Never source an entry from a shared path
  that another session is editing. The sequence reads and writes only the object store and a
  throwaway index, so `git status` in the shared tree is byte-for-byte unchanged. `commit-tree`
  does not run the normal `git commit` hook path: execute the repository's exact pre-commit/security
  gates against the candidate before push, and still let pre-push run. This is the escape hatch for
  when commit-then-switch is off the table because someone else holds the tree.
- **Before any rebase or branch-delete, run the applicable Mode B evidence path.** Use the full
  loss audit only when every worktree/ref/tag/stash/dangler it enumerates is in evidence scope;
  otherwise use the authorized checkout/ref's scoped checks and limit the safety claim accordingly.
- **Before bumping a shared version/lockfile, check the base's current value** so two parallel
  branches don't both claim the same bump (a silent collision that blocks the later change from
  shipping).

## Mode E — Retire worktrees, stashes, and branches safely

The opposite worry from Mode A: not "I lost something" but "these leftovers are piling up —
which can I destroy?" Deleting is trivial; **proving each item is superseded is the work**.
Start from the Outcome contract. For an exhaustive audit or unknown target, run checkout discovery;
for one named worktree/branch, stay in its owning repository. Run `git_loss_audit.sh` only when all
worktrees/refs/tags/stashes/danglers it enumerates are inside evidence scope; treat inspect-only
objects as report-only, keep explicitly excluded collaborator resources out of both the retirement
plan and its terminal counts, then retire only the named targets. If any enumerated surface is
excluded, do not run the full loss audit or an `--all-refs` export; use checkout/ref-scoped checks
and targeted exports instead:

**Step 1 — classify each leftover: live WIP, or superseded draft?** Evidence ladder, strongest first:

1. **Fresh authority plus trial merge** — refresh the base and exact branch tip, then run
   `scripts/git_verify_branch_merged.sh`. An ancestor/content-contained verdict is deletion-grade
   evidence. If it returns NEEDS REVIEW, continue down this ladder; do not convert uncertainty to
   MERGED with a weaker heuristic.
2. **`git cherry <base> <branch>` is a hint, not a verdict.** A `-` proves that one patch-id is
   upstream; a `+` does not prove missing work because squash merges deliberately create a new
   patch-id. Never rescue or delete a whole branch from this output alone.
3. **Same-file supersession check** — for a stash or `+` commit touching files that were later
   reworked on the base: extract its version of the file and compare with the base's current
   version (`git show <ref>:<path> | wc -l` vs `git show <base>:<path> | wc -l`, then spot-diff).
   If the base's version is a **superset** (has everything the leftover has, plus later work),
   the leftover is a superseded draft. Real case: a stash labeled "unfinished dev" held a 1128-line
   renderer; main's version was 1151 lines — the same functions *plus* a later feature parameter.
   Restoring that stash would have been a regression, not a recovery.
4. **Function/marker-level probe** — grep the base for the leftover's distinctive additions
   (`def new_helper`, a constant, an error string). All present on the base → superseded.
   This catches "absorbed into a refactor" cases where file shapes changed too much for rung 2.

Anything you cannot prove superseded stays alive (same safety bias as Mode C: a false "superseded"
loses work; a false "still live" costs a branch name). One warning that changes verdicts: **the
leftover's label is not evidence** — a stash named "unfinished development" can be a fully-landed
early draft; judge content against the current base, never the name. Worked examples of all three
rungs (including the squash-artifact and absorbed-into-refactor cases):
**[references/merge_verification.md](references/merge_verification.md)** § Supersession triage.

**Step 2 — after deletion authority exists and immediately before deletion, preserve exactly what
that deletion threatens:**

```bash
# Targeted branch cleanup: prefer the narrow export.
scripts/git_export_before_drop.sh --branch <branch> --out <external-backup-dir>
# Pin only an authorized dangling SHA; leave unrelated danglers report-only.
git update-ref refs/dangling-backup/<sha> <sha>
# Full ref topology: only when every captured ref is explicitly authorized.
scripts/git_export_before_drop.sh --all-refs --out <external-backup-dir>
scripts/git_export_before_drop.sh --verify-current <external-backup-dir>/all-refs.bundle
```

The targeted `update-ref` reaches only the authorized dangling commit. If every reported dangler is
in scope, the whole-set `git_preserve_danglers.sh` may replace it. Prefer repeated `--branch` options
for named branch/worktree retirement. `--all-refs` captures branches, tags, stashes, hidden backup
refs, and linked-worktree HEAD refs, so it is valid only when that whole captured set is authorized;
add `--all-stashes` only when stashes are also deletion targets. `--verify-current` is the final
compare-and-swap gate: it exits 1 if any recorded ref moved or disappeared. Refresh remote authority
before it, and rebuild the bundle on any mismatch. Keep backups outside the repository; never turn
one branch into a repo export.

For a multi-branch "only one main" cleanup while other sessions may still commit or open PRs, read
**[references/merge_verification.md](references/merge_verification.md)** § Converging many branches
to one main under active concurrency before Step 3. It adds the moving-ref inventory, dirty-WIP
preservation, immutable-candidate, duplicate-PR, and final branch-count gates that a single-branch
retirement does not need.

**Step 3 — destroy, in the safe order:**

- Stashes: drop from the **highest index down** (`drop stash@{2}` before `stash@{1}`) — indices
  shift as you drop, and top-down keeps every number meaning what your backup filenames say.
- Linked worktrees: require an empty `git -C <path> status --porcelain=v1 --untracked-files=all`,
  then inventory ignored paths separately with `--ignored`. A normal clean status hides `!!`
  files, and no bundle can preserve them; copy out anything not proven reproducible, preserve its
  relative path, and verify it against a recorded pre-removal content hash.
  Record the exact HEAD, prove it contained/superseded against a freshly fetched base, export its
  branch or collision-checked recovery ref into a verified targeted bundle, and obtain
  current-session deletion authority. As the final pre-remove gate, re-run the empty status and
  the complete ignored inventory. Require exact equality with the frozen
  pre-removal manifest for every ignored path, entry type, file hash, and symlink target, and
  re-verify each preserved source and backup copy; any difference aborts. Removal must be the next
  operation. Remove only with
  `git worktree remove <absolute-path>` **without `--force`**. Afterwards prove the path and
  registration are gone while the recorded HEAD still resolves through the kept branch/base or the
  verified bundle and every copied ignored item still matches its recorded hash. Never remove the
  primary/current checkout; retire its branch only as a separate,
  separately authorized action. Follow
  **[references/merge_verification.md](references/merge_verification.md)** § Worktree retirement.
- Local branches: prefer `git branch -d` (refuses unmerged); use `-D` only for items Step 1
  proved superseded, backed up, and the user authorized deleting. **A squash-merge is the usual
  reason `-d` refuses a branch whose content is fully merged**: `-d` judges by commit ancestry, and
  the squash replaced the branch's commits with one new-SHA commit, so ancestry is broken even
  though every line landed. That is not license to reach for `-D` reflexively — it means fall back
  to Step 1's *content* check (`git cherry`, superset diff) and only `-D` once that proves
  containment. Delete remote branches only after re-verifying the exact remote and repository
  visibility/ownership.
- **Independent clones need ref-complete preparation before retirement.** A clean worktree says
  nothing about clone-only refs, reflog history, ignored bytes, stashes, hooks/config, or an
  `objects/info/alternates` dependency created by `git clone --shared`. Run
  `scripts/git_prepare_clone_retirement.sh --clone <absolute-clone> --survivor <absolute-kept-checkout> --out <new-external-backup-dir>`;
  it refuses those hidden loss states, every clone-only unreachable Git object, partial/promisor
  clones, attached linked worktrees, local submodule repositories, known Git LFS/annex object stores,
  tracked content filters, and repository-local config/hook indirection that the recovery archive
  cannot resolve safely. It disables repository fsmonitor execution, freezes ref tips plus
  symbolic-ref topology and metadata file types/modes, then creates a self-contained all-refs bundle
  and a content-bound receipt. Finish every preliminary Git probe, freeze the absent quarantine
  target, run process occupancy by itself, then run `--verify-current <backup-dir>` as the final
  probe with the authorized no-clobber quarantine move as the **next operation**. This order keeps
  `lsof` from observing a sibling Git process without opening a larger post-verification gap. Prove
  old-path absence + new-path presence; permanent deletion is a separate explicit decision. Full
  READ-DO sequence and `--shared` boundary:
  **[references/merge_verification.md](references/merge_verification.md)** § Independent clone retirement.

**Step 4 — after the delete, re-check by content, not by filename.** When a cleanup (or a batch of
squash-merges) is already done and the question becomes "did any of it drop work?", the naming-based
check that felt sufficient — `comm` over `git ls-tree` filenames, "every file is still on main" — is
not enough: identical filenames say nothing about identical *content*. A file the deleted branch and
the survivor both have can still differ line-for-line. Re-verify at blob level, and read the diff in
the right direction:

```bash
git diff <survivor-ref> <deleted-or-merged-tip>    # survivor first, the gone thing second
```

Lines marked `-` are on the survivor but not the tip → the survivor is a **superset** (safe: it has
everything the tip had, and more). Lines marked `+` are on the tip but not the survivor → **candidate
loss** — run each through Step 1's ladder: is that symbol on the survivor under a different shape (a
rename or refactor, not a deletion)? A diff that is mostly `-` with a few `+` is the fingerprint of
"the survivor moved on and the deleted branch was an older version" — a merge that succeeded, not
work lost. Apply the same test to any preserved backup: byte-identical or survivor-superset is safe;
a line the survivor genuinely lacks anywhere is the one to escalate.

**Recovery, if you regret it:** patches re-apply with `git apply`; the untracked tar extracts
in place; the bundle restores full history via `git fetch <file>.bundle <branch>:restored/<branch>`.

## Scripts (execute these; they are non-destructive unless noted)

| Script | Does | Mutates? |
|---|---|---|
| `scripts/git_find_all_checkouts.sh [root ...]` | Find every checkout of this repo on the machine — including independent clones invisible to `git worktree list` — and flag uncommitted/untracked/unpushed work, remote-cache age, and borrowed alternates object stores | Nothing (read-only, no fetch) |
| `scripts/git_loss_audit.sh [remote]` | Refresh one remote, then report every worktree, local ref/tag, stash, and dangler; no exclusions, so the whole evidence surface must be in scope | Remote-tracking refs only |
| `scripts/git_preserve_danglers.sh [--patch-dir DIR]` | Pin every dangling commit to `refs/dangling-backup/`, optional patches; whole-set only | Adds refs only (never deletes/gc) |
| `scripts/git_verify_branch_merged.sh <branch> [base]` | Refresh remotes, then give a content-level MERGED/UNMERGED verdict | Remote-tracking refs only |
| `scripts/git_export_before_drop.sh [export options]` | Export stashes plus selected branches or every current ref into verified bundles | Writes backup files only (never drops/deletes) |
| `scripts/git_export_before_drop.sh --verify-current BUNDLE` | Fail if any bundled ref moved or disappeared since export | Nothing (read-only) |
| `scripts/git_prepare_clone_retirement.sh --clone PATH --survivor PATH --out DIR` | Refuse hidden/unhandled clone state, then freeze every ref tip, symbolic-ref target, reflog identity, and scoped config/hooks/info metadata into a self-contained recovery set; after freezing an absent no-clobber destination and process occupancy, `--verify-current DIR` is the final probe and the move must be the next operation | Writes only the new external backup directory; disables lazy fetch/fsmonitor and refuses tracked content filters; never moves/deletes or changes refs |

All six run from the repository root. They use read-only enumeration/configuration commands such as
`find`, `config`, `symbolic-ref`, `submodule status`, `status`, `cat-file`, `rev-list`, `rev-parse`,
`fsck`, `for-each-ref`, and `remote get-url`; plus scoped `fetch`, `archive`, `bundle create/verify`,
metadata hashing/archive, and (preserve only) `update-ref` where each script's table row says so — never
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
  stash-heavy work. They're reflog-reachable now; pin one authorized SHA with targeted `update-ref`,
  or use `git_preserve_danglers.sh` only when every reported dangler is in scope, then inspect with
  `git show <sha>` at leisure.
- **A branch shows huge "commits ahead" but you suspect it's merged** — trust
  `git_verify_branch_merged.sh` (content), not the count. See Mode C.
- **A recovery artifact becomes unexpectedly large, or an upload/LFS transfer stalls** — stop
  retrying and re-run the Outcome contract. This is a scope/placement signal, not a transport
  puzzle. If no authorized imminent deletion threatens the data, the backup was premature. If the
  backup is necessary, keep and verify it in the external backup directory; remote transport is a
  separate decision, not an automatic fallback.
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
