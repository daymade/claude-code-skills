# Prevention Practices — keep a branch tangle from ever stranding work

Each practice below maps to a specific way work actually gets lost. They are cheap habits, not
ceremony; adopt the ones whose failure mode you're exposed to.

## Contents
- Choose topology from current authority
- Shared checkout and concurrent sessions: one writer
- Exact-SHA handoff and scoped completion
- Known automated writers are not session-owned WIP
- Parallel / multi-branch work: commit before switching; exceptions follow current authority
- Push work-in-progress branches early
- Confirm the branch before every commit
- Recover stranded work after a parallel session switched the shared tree
- A foreign commit adopted onto your branch (the inverse case)
- Audit before rebase / branch-delete
- Audit every authorized worktree before retirement
- Snapshot before any history rewrite
- Version / lockfile collisions between parallel branches
- Commit-scope hygiene (don't sweep unrelated staged work)
- Set a wider reflog safety window once

## Choose topology from current authority

Before recommending branches, worktrees, or a second checkout, read the current user and project
instructions. Their explicit collaboration and contribution model wins. A generic post-incident
lesson cannot silently replace a user's existing no-worktree decision, a repository's PR-only
flow, or a task registry's single-writer rule.

Default here: keep one maintained checkout and commit before switching. Do **not** turn worktrees
into a standing rule for every concurrent session. When the current authority explicitly approves
a named second checkout and simultaneous writing truly requires it, prefer a linked worktree over
an independent clone because audits can discover it. That exception does not make it independent:
linked worktrees separate working files, `HEAD`, and index, but share refs, stashes, object storage,
config, and hooks; ignored dependencies and local-only assets are not copied.

## Shared checkout and concurrent sessions: one writer

**Failure mode:** separate sessions edit different files and assume they are independent, but they
share the checkout's current branch and index. One session can switch the branch under another;
one bare commit snapshots every staged entry, including another session's work or a phantom `D`
left by an index-bypassing commit. File ownership alone cannot close that race.

**Prevention:** one physical checkout has one writer. Parallel agents or sibling sessions may do
read-only investigation, but they do not mutate files, refs, index, stash, or working-tree state.
Writer ownership comes from the repository's existing task/coordination system. If that authority
is unavailable, another writer is active, or foreign dirty paths cannot be attributed, stop the
write path; do not create a branch, stash the tree, or "just stage your files" as a workaround.

When you hold write ownership, keep the stage-to-commit interval bounded and inspect the complete
index, not merely the paths you just added:

```bash
git -C <absolute-repo> branch --show-current
git -C <absolute-repo> add -- <exact-path-1> <exact-path-2>
git -C <absolute-repo> diff --cached --name-status
git -C <absolute-repo> diff --cached --stat
git -C <absolute-repo> commit -m "<message>"
```

Every staged status letter must match the intended change. In particular, an unfamiliar `D` is a
stop signal, not a harmless leftover. Follow the repository's contribution policy for push/PR;
this prevention Skill does not widen push or merge authority.

Prefer a WIP commit and early remote copy to stash juggling. Do not rewrite an existing narrow
stash exception as an absolute prohibition: if the current contract permits it, only the single
writer may use its exact absolute-repository and explicit-file form, such as
`git -C <absolute-repo> stash push [options] -- <exact-file>...`. An unscoped stash remains invalid.

## Exact-SHA handoff and scoped completion

A branch name is a routing label, not a frozen deliverable. The writer can add another commit after
handoff, and linked worktrees share that ref. A later `merge <topic>` may therefore merge bytes the
integrator never reviewed.

Freeze and read back the handoff:

```bash
topic_branch=$(git -C <absolute-repo> branch --show-current)
topic_sha=$(git -C <absolute-repo> rev-parse HEAD)
remote_sha=$(git -C <absolute-repo> ls-remote origin "refs/heads/$topic_branch" | awk 'NR == 1 {print $1}')
test -n "$remote_sha" && test "$topic_sha" = "$remote_sha"
```

Report the absolute checkout path, branch, and `topic_sha`. Immediately before the merge, the
integrator must re-read the intended remote tip and require it to equal `topic_sha`. A direct merge
names the frozen object, not the branch:

```bash
current_remote_sha=$(git -C <absolute-repo> ls-remote origin "refs/heads/$topic_branch" | awk 'NR == 1 {print $1}')
test -n "$current_remote_sha" && test "$current_remote_sha" = "$topic_sha"
git -C <absolute-repo> merge "$topic_sha"
```

For a hosted PR, use the platform's expected-head-SHA precondition when it exists. Otherwise make a
fresh hosted head-SHA readback the immediately preceding step and abort instead of merging if it no
longer equals `topic_sha`. A moved ref means "handoff expired," not "take whatever is newest."

Completion requires all of these, never an OR between them:

1. every session-owned tracked and untracked byte is present in the handed-off commit;
2. the exact commit is present on the intended remote, proven by independent readback;
3. every residual path in the checkout is enumerated and attributed;
4. no branch, stash, worktree, or remote ref is deleted as an implicit completion step.

The claim is intentionally scoped. A checkout can remain dirty because an authorized automation
writer or another named owner left unrelated paths. That does not make the session incomplete, but
it forbids claiming the **whole repository** is clean or sweeping the residuals into this commit.
Retirement is a separate Mode E task with new authority and fresh evidence.

## Known automated writers are not session-owned WIP

**Failure mode:** an integration session checks that a scheduled writer is idle, then treats the
next few commands as exclusive. The job starts after the check and writes during stage, merge, or
final verification. A process snapshot is an observation, not a lock.

Do not stop, disable, or reconfigure an authorized job merely to make the generic Git routine easy;
that is a new operations decision. A scheduler that can write anywhere in this physical checkout is
still a writer even when its usual paths are disjoint from the current task. Before any Git mutation,
the project's existing coordination mechanism must prove it quiescent and transfer exclusive writer
ownership through commit and final readback. A process snapshot alone cannot do that. Then:

- read the project's owner contract for the generated paths;
- do not manually edit generated files or co-stage them with an unrelated task;
- when the current task explicitly owns one generated batch and exclusive ownership has transferred,
  stage only its exact paths, complete the Git operation, then re-read the working tree after handing
  ownership back because the next batch may already have arrived;
- if no existing mechanism can prove quiescence and transfer ownership, stay read-only, enumerate
  the residual paths, and report the gap rather than treating disjoint paths or an idle check as
  mutual exclusion;
- treat a new lock, lease, pause, or schedule change as a separately authorized design.

## Parallel / multi-branch work: commit before switching; exceptions follow current authority

**Failure mode:** the classic disaster is `git stash` → switch branch → work → `git stash` again →
rebase → switch back. Each `stash` that gets superseded or dropped orphans a commit; after a busy
session you can have dozens of dangling stash states that `git stash list` no longer shows, one
`gc` from gone. The root cause is always the same — **uncommitted work**: a stash that can be
dropped, or edits a `switch` strands.

**Prevention:** never carry uncommitted work across a branch switch. Commit each line of work to
its own branch *before* moving, and push that branch early — a committed, pushed branch cannot be
stashed away or stranded:

```bash
# instead of `git stash` before switching:
git switch -c <branch-for-this-work>              # a branch for this line of work
git add -- <the paths for THIS work>
git diff --cached --name-status                   # inspect the whole shared index
git diff --cached --stat
git commit -m "wip: ..."
git push -u origin <branch-for-this-work>         # early; re-push as you go
git switch <other-branch>                         # nothing left behind — no stash to drop
```

After sole-writer ownership has transferred to the integrator, bring the frozen work back wherever
it is needed **live in the working tree** by merging the reviewed SHA — not by fishing it out of a
stash or following a movable branch name:

```bash
git switch <target-branch>
git merge "$topic_sha"                            # exact reviewed object, not a movable ref
```

**Deliberately avoided here — shortcuts that cause the loss this skill exists to prevent:**

- **`git stash` + switch juggling** — orphans stashes (the failure mode above). Commit instead; a
  commit on a branch never silently disappears from `git stash list`.
- **Defaulting every concurrent session to `git worktree`** — a second checkout is one more place
  to leave work in and forget, it does **not** copy gitignored dependencies (`node_modules`,
  `.venv`), and it still shares refs/stashes/config/hooks. A shared checkout with one writer and
  disciplined *commit-then-switch* is safer unless current authority explicitly approves the named
  worktree exception described above.
- **`git clone --shared` as temporary isolation** — the clone's refs and object ownership split:
  `.git/objects/info/alternates` borrows objects from the source while the clone owns its refs.
  Git's official documentation warns that source maintenance can prune those borrowed objects and
  corrupt the clone. If a truly independent clone must survive, use `--dissociate` at creation or
  run `git repack -a` before relying on it; if it is temporary, retire it through
  `scripts/git_prepare_clone_retirement.sh` rather than inferring “no local objects = no work.”

The safety comes from **committing early**, not from a second checkout. When every
worktree/ref/tag/stash/dangler enumerated by the full audit is in evidence scope, confirm the state
with `scripts/git_loss_audit.sh`: unlike a raw branch-only log, it also inspects detached
linked-worktree HEADs and uncommitted files. Otherwise use only checkout/ref-scoped evidence and do
not make the full-repository claim.

## Push work-in-progress branches early

**Failure mode:** a commit that exists only on a local branch is the *only* thing a dead disk
actually loses. Everything on a remote is safe.

**Prevention:** the moment a WIP branch has a commit worth keeping, push it:

```bash
git push -u origin <wip-branch>
```

It doesn't need to be a PR — just a remote copy. Re-push as you go, then use
`scripts/git_loss_audit.sh` only when every surface it enumerates is in evidence scope; otherwise
verify the current branch against its exact remote ref and leave the broader state unclaimed.

## Confirm the branch before every commit

**Failure mode:** committing a fix onto the wrong feature branch (easy when juggling several, or
when an agent left you somewhere unexpected). The commit is then invisible to the PR it belongs
to, and gets deleted along with the wrong branch during cleanup.

**Prevention:** glance at the branch before committing:

```bash
git branch --show-current      # is this where this change belongs?
```

If you commit to the wrong branch anyway, it's recoverable: `git log` the SHA, then create a
preserving ref with `git branch correct-branch <sha>`. Leave removal from the wrong branch to
separately authorized Mode E retirement; confirming up front is free.

## Recover stranded work after a parallel session switched the shared tree

**Failure mode:** two agents share one working tree. While you were editing, a *parallel* session
ran `git switch` and moved the shared tree onto **its** feature branch — so your uncommitted changes
now sit on top of that branch, mixed with the other session's own uncommitted edits. You never
switched, so "commit before you switch" never got a chance to fire. A naive `git add -A && git
commit` here buries your work inside the other branch's PR (wrong attribution, wrong review) and can
sweep in their file; committing onto their branch also couples your change to their merge.

**Incident-only recovery:** do not run the sequence below while the other writer is active. First
use the repository's coordination system to quiesce that writer, freeze the observed dirty paths,
and transfer exclusive write ownership. If no such authority exists, stop with the evidence intact;
do not treat checkout plumbing as a concurrency loophole.

Once exclusive ownership is established, carry your uncommitted work onto a branch off the base,
commit only your paths, then put the tree back exactly where the other session left it:

```bash
# 1. See what the hijacked branch is, and prove YOUR files are safe to carry across the switch.
git rev-parse --abbrev-ref HEAD                     # you're on their branch, not main
git log --oneline origin/main..HEAD                 # their extra commits — confirm they're unrelated
git diff --quiet origin/main HEAD -- <your-file>    # exit 0 = your file is byte-identical on both
                                                    #   bases, so your edit carries with NO conflict

# 2. Create your branch off the base; the uncommitted edits ride along (no stash, no worktree).
git checkout origin/main -b fix/your-work

# 3. Commit ONLY your explicit paths — never `git add -A`; the other session's file is still here.
git add <your-path-1> <your-path-2>
git diff --cached --name-only                        # verify: only yours, not their file
git commit -m "…"                                    # freeze/push this SHA; never merge the branch name

# 4. Restore the other session's state before handing write ownership back.
git checkout <their-branch>                           # their uncommitted file carries back untouched
```

**Why this and not the alternatives:** `git stash` to move your edits risks the orphaned-stash loss
this skill exists to prevent; a `git worktree` won't have your gitignored deps. Step 1's `git diff
--quiet` is the load-bearing safety check — it proves your files are identical between the hijacked
branch's tip and the base, which is exactly the condition under which `checkout … -b` carries your
uncommitted edits with no conflict (if it reports a difference, stop and resolve it deliberately
rather than forcing the switch). Step 4 is correctness, not just courtesy: the parallel session
expects to find its own branch checked out with its work intact, exactly as it left it.
Branch deletion is not part of this recovery; it requires separately authorized Mode E evidence.
After Step 3, return to **Exact-SHA handoff and scoped completion** above: record the commit as
`topic_sha`, push and read back that exact object, use `git merge "$topic_sha"` for a direct merge,
and require the hosted expected-head-SHA gate (or immediately preceding hosted head readback) for a
PR merge. Any branch-tip drift expires the handoff.

## A foreign commit adopted onto your branch (the inverse case)

**Failure mode:** the mirror image of the section above. There, a parallel session moved the shared
tree and *your uncommitted work* ended up on *their* branch. Here *their commit* ends up in *your
branch's history*: you created a topic branch in a shared checkout, a sibling session committed while
`HEAD` was still on it, and that commit is now a parent of yours. Open a PR and it ships their
in-progress work under your name and your review.

**Why the usual checks miss it.** Every branch-level instrument this skill already tells you to run
reports correctly, and reports green:

| Check | What it says | Why it cannot see this |
|---|---|---|
| `git branch --show-current` | your branch | it *is* your branch — that was never the problem |
| `git status` | clean | their work was committed, so it left the working tree |
| `git diff --cached --name-status` | only your paths | their work left the index too, at commit time |

The foreign commit appears only in the branch's **cumulative range against the base you branched
from** — a comparison none of the above makes. This step is read-only and carries no ownership
precondition:

```bash
base=<the base SHA you recorded when you created the branch>
git rev-parse --verify "$base^{commit}"   # must print a SHA, or everything below is meaningless
git log  --oneline "$base"..HEAD          # every commit here must be yours
git diff --name-only "$base" HEAD         # every path here must be yours
```

Two things this check cannot do for you. If `$base` is **empty** — an unset variable, or a command
substitution that failed — `"$base"..HEAD` degenerates to `HEAD..HEAD`: the `git log` prints nothing
and exits 0, which is exactly what "clean" looks like. A non-empty base that does not resolve is a
different and safer case: it aborts with `fatal: Invalid revision range` at exit 128. Both are
caught by the verify line above, but only the empty one is silent, and silence is what gets missed. And **Git cannot tell you
which commits are yours**: a shared checkout gives both sessions the same author and committer
identity, so no `--author` filter separates them. The answer comes from the SHAs you recorded as you
committed, which is the second reason to record as you go. If you cannot say with certainty which
commits are yours, stop and ask rather than proceed — every step below deletes a commit.

**Record the base SHA at branch creation.** `git merge-base origin/main HEAD` recovers it only from
a *cached* remote ref, and refreshing that cache is a fetch — which **Shared checkout and concurrent
sessions: one writer** and Mode C both gate on exclusive ownership. A stale base widens the range,
which is the safe direction for detection but the dangerous one for the rebase that may follow, and
it is precisely the moment you cannot fetch to fix it. Recording one SHA at the start costs nothing
and removes the dependency.

Run the comparison before every push and before opening any PR from a shared checkout. The signal
that reaches you by accident is a repo validator or CI job reporting a wider blast radius than you
worked on — "2 components changed" when you touched 1. Treat that as this failure mode until proven
otherwise.

**Repair is governed by the rules that already exist here — do not shortcut them.** Finding a
foreign commit is itself evidence that another writer was in this checkout, so the first obligation
is the standing one: stop, and use the repository's coordination system to quiesce that writer and
transfer exclusive ownership. If no such authority exists, stop with the evidence intact and report
it. Nothing below is a concurrency loophole.

Once you are the sole writer, the repair is a history rewrite of your own branch — `git rebase
--onto` checks out the branch it rewrites, so it is checkout-relative mutation — and it runs the
existing sequence in order:

1. **Audit before rebase / branch-delete** (below): select and run the applicable evidence path.
   Local-only commits and dirty authorized worktrees must be preserved before the destructive step.
2. **Snapshot before any history rewrite** (below): `git branch backup/pre-rewrite <your-branch>`.
   This ref points at *your* tip and is what makes the rebase reversible. Nothing else does — after
   `git rebase --onto` your pre-rebase tip is reachable through the reflog only (measured: zero refs
   contain it).
3. **Preserve their commit** — a separate obligation needing its own ref, because the backup above
   points at your tip and the rebase drops *their* commit from your branch:
   ```bash
   git branch rescue/foreign-<short-sha> <foreign-sha>
   ```
   If this exits 128 with `a branch named ... already exists`, do not shrug it off and continue:
   confirm the existing ref points at the same object (`git rev-parse rescue/foreign-<short-sha>`)
   before treating this step as done. A same-named ref at a *different* object means someone else's
   repair is already in flight.
4. **Rebase onto the foreign commit's parent — not onto the base.** `git rebase --onto X Y branch`
   replays `Y..branch`, so `--onto "$base" <foreign-sha>` discards **everything before the foreign
   commit, including your own earlier commits**, and reports success with exit 0. That is only
   harmless when the foreign commit happens to be the first commit after the base. The general form
   drops exactly one commit and keeps yours on both sides of it:
   ```bash
   git rebase --onto "<foreign-sha>^" "<foreign-sha>" <your-branch>
   ```
   Measured on a branch whose history was `A(yours) → F(foreign) → C(yours)`: the `--onto "$base"`
   form left only `C` and silently dropped `A`; the form above kept `A` and `C` and dropped only `F`.
   Bounds: it removes **one non-merge commit**. For several foreign commits, or one that is a merge,
   stop and drop them explicitly through an interactive rebase, re-reading this list first.
   The tree must be clean before you start. If it is not, `git rebase` refuses with
   `error: cannot rebase: You have unstaged changes. / Please commit or stash them.` — and note that
   the second half of Git's own suggestion is the unscoped stash this skill forbids. The correct
   response is that you are not the sole writer yet: go back to the ownership step.
   With `rebase.autoStash` enabled the refusal never happens, and that is worse (measured): the
   rebase silently stashes whatever a sibling session left uncommitted, and if it then **stops on a
   conflict**, their files are gone from the working tree while `git stash list` shows **nothing** —
   an autostash is not a stash entry, so the first check anyone runs comes back empty. Their work is
   at `.git/rebase-merge/autostash`, and in the single `Created autostash: <sha>` line already
   printed. `git rebase --abort` restores it, but only if someone knows to look.
5. **Re-run the detection.** The repair is not verified by the rebase's exit code:
   ```bash
   git log  --oneline "$base"..<your-branch>    # every commit yours — and your earlier ones still here
   git diff --name-only "$base" <your-branch>   # every path yours
   ```
   Check for both failures at once: the foreign commit gone, *and* nothing of yours gone with it.
6. **If the branch was already pushed** — which the incident above describes, since the foreign work
   reached a PR — the rewrite makes your local branch diverge and the next `git push` is rejected
   with `Updates were rejected because the tip of your current branch is behind`. Do not resolve that
   here: force-updating a published ref is governed by **Destructive-operation safety (reset /
   force-push / rewrite)** in [recovery_playbook.md](recovery_playbook.md), which requires
   `--force-with-lease` over `--force`. Anyone else who fetched that branch also needs telling.
7. **Retiring either ref is a Mode E action** under Mode C evidence — the same standard this skill
   applies to every other preserving ref it tells you to create, and no weaker. Do not delete
   `rescue/foreign-<short-sha>` on a heuristic. Note that if step 4 was run in the discarding form, *your* own
   commits are anchored only by the preserving refs — `backup/pre-rewrite` from step 2 and, for
   anything before the foreign commit, `rescue/foreign-<short-sha>` from step 3. Neither is
   retirable until step 5 has passed.

**Why the obvious "did their work survive?" probes mislead.** These are worth knowing before you
reach Mode C, because both look authoritative and both were measured returning the wrong answer on
a real commit whose work had definitively shipped:

- **"No ref contains it" does *not* prove the work is unique.** `git for-each-ref --contains <sha>`
  (or `git branch -a --contains <sha>`) reports **zero** refs for a commit that already merged,
  because a **squash or rebase merge re-writes it under a new SHA** — the original object survives
  only as an unreachable dangler while its content sits in the integration branch. Note that you can no
  longer observe that zero once this procedure is under way: the foreign commit is an ancestor of
  your pre-rebase tip, so **both** preserving refs contain it — `backup/pre-rewrite` from step 2 as
  well as `rescue/foreign-<short-sha>` from step 3 — and the count rises by one at each (measured in step
  order). Exclude both, or the reading is about refs you created a minute ago:
  ```bash
  git for-each-ref --contains <sha> --format='%(refname)' | grep -vE '^refs/heads/(rescue|backup)/'
  ```
  Read the *output*, not the exit code: when the filter removes everything, the pipeline exits 1
  with empty stdout — which is the answer "no external ref contains it", not a failure. Under
  `set -e` or `pipefail` that exit aborts the script instead.
- **Hash-equality comparison of whole files against the integration branch does not prove it
  either.** Hashing `git show <sha>:<path>` against `git show origin/main:<path>` reports
  "different" for every file as soon as the branch moves on; any later commit touching the same
  files is enough. Measured: all five files differed while the work was fully present. (This is not
  the superset-style same-file supersession check in Mode E rung 3, which compares content coverage
  rather than equality.)
- **A string the commit added, grepped against the integration branch, does answer** — with the
  control line that makes it an instrument rather than a guess:
  ```bash
  git show origin/main:<path> >/dev/null   # must succeed first: 128 here means the path moved, and
                                           # then BOTH greps below return 0 and the control passes
  git show <sha> -- <path> | grep '^+' | grep -v '^+++'   # read these; pick one distinctive line
  needle='<that phrase WITHOUT its leading + — diff output carries one, and grep -cF is literal>'
  git show origin/main:<path> | grep -cF "$needle"                  # >0 ⇒ the work is in main
  git show origin/main:<path> | grep -cF 'string-that-cannot-exist' # must be 0, or the probe is broken
  ```
  `origin/main` here is a cached ref. Staleness fails safe in this direction — you read 0, keep the
  rescue ref, and over-preserve — but the `>0` half is a positive verdict off a cache, so fetch
  first if you are the sole writer and can, and otherwise treat `>0` as provisional.
  Both leading-`+` and a renamed path produce the same false negative — 0 hits with the control line
  passing — so neither is caught by the control alone; that is what the first line and the `+` note
  are for. If the file was renamed or moved in the integration branch, this probe cannot answer:
  fall through to Mode E's rung 4 function/marker-level probe, which is
  built for exactly the absorbed-into-a-refactor case.
  Treat the result as an explanation of *why* an ancestry check disagreed, not as deletion
  authority: it reads one string in one file, while Mode C's trial merge is the check this skill
  records as right every time. If the work turns out to exist only on your branch, it was never
  yours to drop — keep the rescue ref, tell the other session where it is, and let them re-land it.

## Audit before rebase / branch-delete

**Failure mode:** deleting a branch or rebasing can orphan commits; if any were local-only, they
head toward gc.

**Prevention:** select the evidence path first (see recovery_playbook.md). With every
worktree/ref/tag/stash/dangler enumerated by the script in scope, run the full at-risk check:

```bash
scripts/git_loss_audit.sh
```

With an excluded worktree, do not run it; use the authorized checkout's scoped status/HEAD/remote
checks. Local-only commits or dirty/unavailable authorized worktrees must be preserved before the
destructive step, and excluded state remains explicitly unaudited.

## Audit every authorized worktree before retirement

**Failure mode:** checking `git status` in the primary checkout and assuming a linked worktree is
also clean. The linked checkout may hold untracked files or a detached commit that no branch names.

**Prevention:** run `git_loss_audit.sh` only when every surface it enumerates is in evidence scope.
Then inspect each selected authorized path with both `git -C <worktree-path> status --porcelain=v1
--untracked-files=all` and the corresponding `--ignored` inventory. Otherwise skip the full script
and inspect only the exact authorized retirement path. The first status must be empty; every ignored
item must be proven reproducible
or copied out with its relative path and verified against a recorded content hash because Git
bundles cannot reach it. Record the exact HEAD, prove containment against
a freshly fetched maintained base, and create a verified targeted bundle from the worktree's branch
or collision-checked recovery ref before current-session authorization and non-forced removal.
Afterwards verify the path/registration disappeared and the recorded HEAD still resolves through a
kept ref/base or the bundle, then recheck every copied
ignored item against its pre-removal hash. Immediately before removal, repeat the worktree status
and source-hash checks and make removal the next operation; otherwise a writer can change ignored
bytes after the early backup check. Never reduce the worktree count
with `rm -rf` or `git worktree remove --force`; the safe target is one maintained primary checkout,
not zero checkouts.

## Snapshot before any history rewrite

**Failure mode:** `rebase`, `reset --hard`, `filter-repo`, and interactive-rebase mistakes abandon
the pre-rewrite commits.

**Prevention:** a throwaway backup branch makes the whole operation reversible:

```bash
git branch backup/pre-rewrite      # points at the current tip; retire later through Mode E
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
with it. On a shared tree the blast radius is wider than your own staging: a bare `git commit`
snapshots the *entire* index, which may hold a parallel session's staged work — or phantom `D`
entries left behind when a commit advanced the branch past the index (`commit-tree` +
`update-ref`), so the files that commit delivered show as staged deletions. Committing then folds
the collaborator's work into your commit, or turns the phantom deletions into real ones — the
delivered files vanish from HEAD while the working tree looks untouched.

**Prevention:** stage explicit paths, then read the *whole* staged set against your intent —
including the lines you did not add:

```bash
git add <the specific paths for THIS change>
git diff --cached --name-status      # FULL staged set == your intent? `D` lines included
```

Use `--name-status` here, not `--name-only`: the status letter is what exposes a phantom `D` for a
file you never deleted. Any entry you don't recognize — a collaborator's staged file, a deletion
you never made — means stop, not commit. And if it was *your* commit that advanced the branch past
the index (plumbing, a temporary `GIT_INDEX_FILE`), re-sync immediately after:
`git restore --staged -- <the paths your commit touched>` until those paths no longer appear in
`git diff --cached` (a parallel session's own staged entries are theirs, not yours to clear).
Leaving the drift in place hands the next bare commit a loaded gun.

## Set a wider reflog safety window once

The reflog is your recovery window; widen it once, globally, so a busy repo doesn't age work out:

```bash
git config --global gc.reflogExpire "180 days"
git config --global gc.reflogExpireUnreachable "90 days"
```
