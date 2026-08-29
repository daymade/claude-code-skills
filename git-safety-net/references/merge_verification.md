# Merge Verification — prove content is merged without being fooled by counts

## Contents
- Why commit counts lie (the squash-merge illusion)
- The sound content check (a trial merge, not a heuristic)
- Per-branch verdict procedure
- Pick the diff FORM from the question you're asking (two-dot vs three-dot)
- Why safety-biased: a false "merged" loses work, a false "unmerged" only costs a look
- Manual-only investigation hints (do NOT auto-decide on these)
- Converging many branches to one main under active concurrency
- Independent clone retirement — preserve refs, metadata, and borrowed objects
- Worktree retirement — prove the checkout is disposable before removal
- Adversarial multi-agent verification (for a whole repo of branches)
- Rules for the verification agents

## Why commit counts lie (the squash-merge illusion)

When a PR is **squash-merged**, main gets one new commit whose *content* equals the branch, but
whose *sha* is new — the branch's original commits are not ancestors of main. So:

```bash
git rev-list --count origin/main..stale-branch   # → 173  ("173 commits ahead!")
```

…is a lie about merge status. Those 173 commits are the branch's own history; their content is
already on main. **Never conclude "unmerged" (or "safe to keep this branch") from a count.**
The same applies to rebased branches: rebasing rewrites shas, so the pre-rebase commits look
"unmerged" while their content landed long ago.

The only trustworthy question is: **is the branch's content already contained in the base?**

## The sound content check (a trial merge, not a heuristic)

`scripts/git_verify_branch_merged.sh <branch> [base]` answers that question with Git's own merge
machinery instead of per-file guesses. It rejects the base ref itself as a deletion target, then
runs two checks in order:

1. **Ancestor** — the branch is literally in the base's history:
   ```bash
   git merge-base --is-ancestor origin/<branch> origin/main && echo "MERGED (ancestor)"
   ```

2. **Content-contained** — do a trial 3-way merge of the branch *into* the base, in memory, and
   ask whether it changes anything. If merging the branch produces the base's exact tree, the
   branch adds nothing the base lacks — which is precisely the squash/rebase case where the count
   says "ahead" but the content is already upstream:
   ```bash
   base_tree=$(git rev-parse "origin/main^{tree}")
   if merge_output=$(git merge-tree --write-tree origin/main origin/<branch> 2>&1); then
     merged_tree=$(printf '%s\n' "$merge_output" | head -1)
     [ "$merged_tree" = "$base_tree" ] && echo "MERGED (content contained)"
   fi
   ```

This is **sound**, not a heuristic, because it *is* Git's merge: a revert, an edit, or a new file
the base lacks would change the merged tree and fail the equality — so it can never be silently
mistaken for "merged." (`git merge-tree --write-tree` needs git ≥ 2.38; on older git the script
cannot prove containment and falls back to reporting NEEDS REVIEW rather than guessing.)

Everything else is **UNMERGED / NEEDS REVIEW**. To show what to review, list the branch's own
contribution (three-dot = what it changed since diverging), display-safe for Unicode/space paths:

```bash
git -c core.quotePath=false diff --no-renames --name-status origin/main...origin/<branch> --
```

`--no-renames` decomposes a rename into add+delete (so a renamed-and-edited file can't hide); the
`--` guarantees a branch named like a path (e.g. `docs`) is never parsed as a pathspec.

Three-dot is correct **here** — the question is "what did this branch contribute", and hiding the
base's parallel work is the point. It is the wrong form for "what does the base lack"; see
[Pick the diff FORM](#pick-the-diff-form-from-the-question-youre-asking-two-dot-vs-three-dot).

## Per-branch verdict procedure

For each branch, the script decides among three outcomes:

- **MERGED (ancestor)** — in the base's history. Delete freely.
- **MERGED (content contained)** — a trial merge into the base changes nothing; the "commits
  ahead" count is a squash/rebase artifact. Delete freely.
- **UNMERGED / NEEDS REVIEW** — a trial merge *would* change the base, so the branch carries
  content the base does not already have (a genuinely new/edited/reverted/deleted file). Review
  the listed contribution before deleting.

## Pick the diff FORM from the question you're asking (two-dot vs three-dot)

`git diff base...ref` and `git diff base ref` answer **different questions**, and reaching for the
wrong one produces a confidently wrong "nothing is missing." Both are content-level, so the usual
"don't judge by counts" instinct does not catch the mistake.

| Question | Form | Why |
|---|---|---|
| "What did this branch *change* since it diverged?" (reviewing a PR's contribution) | **three-dot** `base...ref` | Diffs from the **merge base** to `ref` — deliberately hides everything `base` did in parallel, which is what makes a PR diff readable. |
| "What does `base` **lack** that `ref` has?" (auditing a retired/archived ref for lost work) | **two-dot** `base ref` | Compares the two trees **as they are now**. This is the loss question. |

Three-dot is wrong for the loss question because a file that existed at the merge base and was
later deleted from `base` is *not* part of "what the branch changed" — so it never appears, even
though `base` genuinely lacks it today. Real incident: auditing three archive tags with
`git diff origin/main...<tag> --diff-filter=A` reported **1** file missing from main; the same
audit with the two-dot form reported **5** (the extras included a real 107-line script). The
three-dot answer was not a rounding error — it was a different question, answered correctly.

```bash
# "What would I lose by deleting this ref?" — always two-dot:
git diff <base> <ref> --name-only --diff-filter=A     # files ONLY on <ref>
git diff <base> <ref> --stat | tail -1                # aggregate direction
```

Read the aggregate direction as triage, not verdict: **base-only lines ≫ ref-only lines** is the
fingerprint of "base evolved past this ref" (safe); it does not by itself clear the ref-only lines,
which still need the supersession ladder below. In that same audit the archive tags showed ~58,000
base-only vs ~3,700 ref-only lines — overwhelmingly superseded, yet the ~3,700 still hid the one
file worth investigating.

## Why safety-biased: a false "merged" loses work, a false "unmerged" only costs a look

The two error directions are not symmetric. A false **UNMERGED** wastes a second look; a false
**MERGED** tells you to delete a branch whose work then vanishes. So the check is deliberately
biased: it only says "safe to delete" when it can *prove* containment, and it reports everything
it cannot prove as NEEDS REVIEW. One real consequence: if a branch was squash-merged **and** the
base later edited the same lines, the trial merge no longer reproduces the base tree exactly, so
the script says NEEDS REVIEW rather than MERGED. That over-reporting is the correct trade — you
look, confirm the lines are redundant, and delete; you never lose work to a confident wrong "yes."

## Manual-only investigation hints (do NOT auto-decide on these)

These help a **human** investigate a NEEDS-REVIEW branch, but must never drive an automated
"safe to delete" verdict — each has a false-positive mode that can hide real unmerged work:

- `git log origin/main --oneline --find-object="$blob" -- <path>` — did this exact blob ever
  appear at this path in the base's history? A hit *suggests* the base passed through this content.
  **Unsound for auto-decisions:** it also matches a revert (the base *used* to have it but doesn't
  now — the revert is still unmerged work), so a match does not prove "currently contained."
- `git cherry origin/main origin/<branch>` — marks each branch commit `-` (patch already upstream)
  or `+` (not). Useful for cherry-picked/rebased commits, but a squash-merge combines commits into
  one new patch-id, so cherry shows the originals as `+` even though their content is merged.
- Superset tells (base file is larger and contains the branch's distinctive symbols) — a hint the
  base evolved past the branch, to be **confirmed by eye**, not trusted blindly.

When a hint and the trial merge disagree, trust the trial merge; it is the sound one.

## Supersession triage — "is this leftover a live WIP or a superseded draft?" (Mode E's method)

Retiring old stashes/backup-branches asks a *different* question than "is this branch merged":
the leftover is often an **early draft of work that later landed in a better form**, so a trial
merge can't clear it (its old lines genuinely differ from the base's evolved lines), yet
restoring it would be a regression, not a recovery. Judge supersession by escalating evidence:

1. **`git cherry <base> <branch>`** — patch-content equivalence. Handles rebases/rewords; every
   `-` is proven-on-base. Only the `+` commits proceed to the next rungs. (For a squash-merged
   backup branch, expect all `+` — that's the squash artifact, not evidence of unmerged work;
   compare *statistics per file* next.)
2. **Same-file superset comparison** — for each file the leftover touches, extract both versions
   and compare shape and content:

   ```bash
   git cat-file -p <leftover-ref>:<path> | wc -l     # vs
   git cat-file -p <base>:<path> | wc -l
   diff <(git show <leftover-ref>:<path>) <(git show <base>:<path>) | grep '^<' | head
   ```

   The `^<` lines are what the leftover has that the base lacks. If they are only *older
   signatures* of things the base now does better (e.g. the same function without a parameter
   the base later added), the leftover is a superseded draft. Real case: a stash the author
   had labeled "unfinished development — handle later" held a 1128-line renderer; the base's
   was 1151 lines — every function present *plus* a later-added `base_url` image-rendering
   parameter. The scary label was stale; the stash was an early draft of already-landed work.
3. **Distinctive-marker probe** — grep the base for the leftover's unique additions (new function
   names, constants, error strings). All present → the work was absorbed (perhaps into a
   refactor that moved it to a different file — search repo-wide, not just the original path).
   Real case: a backup branch's hardening (a required-columns check + a `COALESCE` timestamp
   fix) had been absorbed verbatim into a new shared `_core/` module the refactor created;
   the original file was gone but every marker line lived on at the new path.

4. **Ask the base why it removed this — grep for the leftover's own name/path.** Rungs 1–3 all ask
   "is this content somewhere on the base?" and go quiet when the honest answer is *no*. But "the
   base does not have it" has two opposite causes, and only one is a loss:

   ```bash
   git grep -n "<basename-of-the-missing-file>" <base>     # who mentions it now?
   git log <base> --oneline --diff-filter=D -- <path>      # which commit removed it?
   ```

   A replacement usually **documents the supersession in prose**, and that prose is stronger
   evidence than any marker probe because it states intent rather than resemblance. Real case: a
   107-line `fix-marketplace-paths.py` existed on three archive tags and nowhere on the base — by
   rungs 1–3 a textbook "unique work, rescue it." Grepping the base for its filename surfaced its
   successor saying, in comments: *"replaces the old fix-marketplace-paths.py"*, *"made this worse,
   not better"*, and *"CAUSED the corruption by rewriting the shared file."* The script had been
   **deliberately excised because it was harmful** — the corruption it claimed to fix was its own.
   Restoring it would have reintroduced a known bug while looking like a careful rescue.

   Two removal causes, opposite verdicts:

   | The base's history says | Verdict |
   |---|---|
   | A later commit removed it, and something on the base names it as replaced / harmful / merged-in | **Superseded — do not restore.** Restoring reverts a deliberate decision. |
   | Nothing on the base mentions it; it vanished in a bulk rewrite (`filter-repo`, mass revert, history cleanup) with no successor | **Candidate loss — escalate.** Collateral damage looks identical to intentional removal in the tree; only the surrounding evidence separates them. |

   Also classify what the missing file *is* before escalating: **generated artifacts are not
   work.** Scan markers, lockfiles, and build outputs (anything carrying a timestamp + content
   hash of its own inputs) legitimately differ or vanish between refs and are regenerated on
   demand — three of the "missing" files in that same audit were `.security-scan-passed` markers,
   and their skills were all present on the base, one of them simply moved to another suite
   directory. Check for a **relocation** (`git ls-tree -r <base> --name-only | grep <basename>`)
   before concluding a path's absence means the thing is gone.

**The label on the leftover is not evidence.** Stash messages and branch names describe intent
*at creation time* ("unfinished", "backup", "wip") — they never get updated when the work later
lands through another path. Judge by content against the current base, never by how urgent the
name sounds. The same applies in reverse to *size*: a substantial-looking file the base lacks
(rung 4's 107-line script) reads as "obviously valuable" and is exactly the shape of leftover
most likely to be restored on instinct.

Same safety bias as everywhere else in this skill: prove supersession per item, or keep the item.

## Converging many branches to one main under active concurrency

Use this READ-DO sequence when the outcome is not one deletion but a repository-wide convergence:
keep every unique behavior, preserve current WIP, and leave exactly one maintained `main`. A branch
list is a moving snapshot while other sessions are alive, so the start-of-task audit cannot double
as the deletion gate.

The executing agent owns only the explicitly authorized slice of this sequence, not every object
the inventory reveals. `--verify-current` mechanically decides only whether exact ref tips stayed
unchanged; it grants no ownership. Unique-behavior and supersession judgments still require the
content evidence below and have no automatic enforcement.

### 1. Freeze the outcome and the first ref snapshot

Before interpreting the inventory, partition objects into three sets:

- **change-authorized:** exact checkout/ref/PR targets this task may mutate;
- **inspect-only:** objects the evidence question genuinely requires reading but not changing;
- **excluded collaborator resources:** active or user-excluded worktrees/refs/PRs that this task
  may acknowledge by identity but must not inspect internally, back up, publish, merge, unlock,
  remove, or count as its own unfinished cleanup.

Generic phrases such as "take over", "continue", or "finish this" do not move an object between
sets. The user must name the additional object or otherwise make the expansion unambiguous.

Record the exact local and remote-tracking refs, then query the hosting service for its current
branch list and PR heads. Keep the two inventories separate: remote-tracking refs are a Git cache;
the hosting API is authority for branches that exist on the server. Record every exact tip SHA.

Classify each change-authorized non-main ref by content. Use the trial-merge verdict first. For
NEEDS REVIEW refs, walk the supersession ladder above and open distinctive code/tests at authority.
`git cherry` may surface candidates, but every `+` after a squash merge is still only a hypothesis.
Merge or adapt the smallest unique behavior; never merge an old whole branch merely because it has
many `+` commits or a compelling name. Report inspect-only and excluded refs separately without
turning their existence into an action item.

### 2. Build keeper commits without touching a shared writer

When another session is actively changing files, do not switch the shared checkout or use its real
index. Build from the freshly fetched base with Mode D's alternate-index plumbing. Preserve each
candidate as an exact `(mode, object ID, path)` tuple from an immutable commit; copying only blob
bytes can silently strip executable (`100755`), symlink (`120000`), or gitlink (`160000`) behavior.
An owned temporary regular file may be hashed only after its intended `100644`/`100755` mode is
verified explicitly; symlinks and submodules must use the immutable-entry route. Never hash the
shared worktree, which can silently capture someone else's in-progress bytes. Run the candidate's
deterministic tests and the exact hook/security gates that a normal commit would have run before
opening the PR.

After a squash merge, do not compare commit SHAs: GitHub creates a new base-branch commit. If the
base did not otherwise move, equal tree IDs prove byte-identical landing. If it did move, compare
the owned path set or re-run the trial merge so unrelated base work does not manufacture a failure.
GitHub-side duplicate/superseded PR handling belongs to the `github-ops` skill.

### 3. Preserve refs and dirty WIP through different channels

Create a repository-external bundle containing only the branches/refs whose deletion is authorized,
then verify it. The bundle is the ref manifest: immediately before deletion run:

```bash
scripts/git_export_before_drop.sh \
  --branch <authorized-ref-1> --branch <authorized-ref-2> \
  --out <external-backup-dir>
scripts/git_export_before_drop.sh --verify-current <external-backup-dir>/branches.bundle
```

For an authorized linked worktree on a branch, export that branch. For an authorized detached HEAD,
create one collision-checked recovery ref pointing at the recorded HEAD, then export that ref:

```bash
git update-ref refs/recovery/<worktree-id> <recorded-head> 0000000000000000000000000000000000000000
scripts/git_export_before_drop.sh \
  --branch refs/recovery/<worktree-id> --out <external-backup-dir>
```

This pin is part of preserving the named retirement target; it does not authorize pinning other
danglers. Use `--all-refs` only for an explicitly authorized full-ref-topology operation. The
repository-wide loss audit is valid only when every worktree/ref/tag/stash/dangler it enumerates is
inside evidence scope, and the all-refs export only when every ref it captures is change-authorized.
Otherwise use the authorized checkout/ref's own status/HEAD/upstream checks plus targeted exports,
and make only a scoped-cleanup claim.

Bundles cannot preserve untracked bytes. Freeze an explicit dirty-path manifest, save tracked
changes as a binary diff, copy or tar the exact dirty/untracked paths outside the repository, then
extract to a fresh verification directory and byte-compare every declared path. Do not use stash,
a temporary clone, or a worktree as the backup mechanism.

If the new base now tracks a path that was untracked WIP at the first snapshot, it will collide
with checkout materialization. Move that exact path to the verified external backup, update the
clean base, then restore the saved bytes; it should naturally become a tracked modification. Never
drop it because "main now has a file with that name."

If another writer is still active, leave the real HEAD/index/worktree alone and postpone local
branch convergence. Publishing an isolated PR is safe; switching the shared checkout is not. When
an exclusive window exists, update only paths proven clean, or restore the complete verified WIP
set after materializing the new base.

### 4. Re-freeze immediately before deletion

Fetch again, re-query hosting branches/PRs, and re-enumerate local refs. Compare the result with the
bundle heads. A new branch, changed tip, or late PR inside the change-authorized set is new evidence:
stop, classify its unique behavior, and rebuild the bundle. A newly discovered collaborator object
does not silently join that set; record it as inspect-only or excluded and rebuild only if the next
authorized destructive action could reach it. This is not an optional "final check"; it is the only
check that covers work created after the first audit.

Delete only refs whose current SHA still equals the verified snapshot. For remote branch deletion,
query the exact hosted ref one last time; then delete it through the normal push/API route and prune
stale local remote-tracking refs.

### 5. Prove the user-visible terminal state

If every local/hosted branch, associated PR head, and linked worktree path in the convergence set is
explicitly change-authorized, the task is complete only when all are independently true:

- the hosting service lists only the intended maintained branch;
- local `refs/heads/` contains only `main`, and `HEAD`, local `main`, and the refreshed
  `origin/main` resolve to the intended commit;
- `git worktree list --porcelain` registers only the primary worktree, and every authorized linked
  worktree path is absent;
- the index has no staged residue from the convergence;
- every pre-existing WIP path still byte-matches its frozen source/backup, even if Git now reports
  a different tracked/untracked classification;
- the recovery bundle still verifies and lists the retired exact tips.

Tags, stashes, and dangling commits do not block a branch/worktree convergence claim unless the
Outcome contract separately names them as retirement targets; preserve or report them under their
own scope.

When collaborator resources are inspect-only or excluded, do not claim repository-wide one-main
convergence. Report **scoped completion** instead: the authorized refs/PRs are merged or retired,
the maintained main identities agree, and every excluded branch/worktree/PR is listed as untouched.
Those exclusions are not blockers and must not be deleted to make a count reach one. Counts and
checksums support these claims; they do not replace them.

## Independent clone retirement — preserve refs, metadata, and borrowed objects

An independent clone is not a linked worktree. Git has no registry connecting it to the checkout
you intend to keep, so `git worktree list`, the survivor's branch inventory, and the survivor's
loss audit cannot prove that deleting it is safe. A clean `git status` covers only one layer; the
clone can still be the sole owner of a ref name, reflog-only commit, stash, ignored file, hook, or
repository-local configuration.

`git clone --shared` adds one more asymmetry: the clone starts with no objects of its own and reads
the source through `.git/objects/info/alternates`. Git's official `git-clone` documentation calls
this potentially dangerous because source-side maintenance can prune borrowed objects and corrupt
the clone; `git repack -a` is the documented way to break that dependency when the clone will be
kept. For retirement, an empty local object directory is therefore **not** evidence that the clone
contains nothing — its refs remain unique state even while their objects live elsewhere.

Use this READ-DO sequence for one explicitly authorized clone:

1. **Name the survivor, clone, and external backup directory.** The backup must be a fresh absolute
   path outside both repositories; reusing an existing directory can mix two audits while looking
   valid. Confirm the clone has a `.git` directory. A `.git` file is a linked worktree and belongs
   to the worktree-retirement procedure below.
2. **Prepare the recovery set:**

   ```bash
   scripts/git_prepare_clone_retirement.sh \
     --clone <absolute-clone> \
     --survivor <absolute-kept-checkout> \
     --out <new-external-backup-dir>
   ```

   The helper is intentionally non-destructive. It refuses tracked/untracked changes, ignored
   physical files, stashes, reflog commits with no current ref, shallow history, every clone-only
   unreachable object reported by `git fsck`, partial/promisor clones, any attached linked worktree,
   local submodule repositories, and known clone-private Git LFS/annex object stores that require
   their own audit. The promisor check happens before object traversal and the helper exports
   `GIT_NO_LAZY_FETCH=1`, so bundle creation cannot silently hydrate missing objects into the clone
   it promised not to mutate. A repository using another extension-managed object store must name
   and audit that store separately; a core Git bundle cannot prove those bytes exist elsewhere. The
   helper also refuses tracked content filters, repository-local `include.path` / `includeIf`
   config, and local `core.hooksPath` overrides rather than pretending their external processes or
   closure were archived. Every Git call disables repository `core.fsmonitor`, untracked-cache
   refresh, and optional locks. It snapshots every ref tip, every symbolic-ref target, every reflog
   OID, and the default config/hooks/info tree with file types and modes; creates `all-refs.bundle`
   without revision exclusions; runs `git bundle verify`; compares every advertised bundle head
   (including `HEAD`) with the frozen ref set; and binds both the bundle and repository-metadata
   archive to SHA-256 receipts.
   The regression suite also verifies the no-prerequisite bundle from an empty bare repository. A
   successful `READY_TO_QUARANTINE` means the recovery set is
   complete for that instant, not that deletion authority exists.

   A bundle records the OID advertised under each ref name; it does not recreate symbolic-ref
   topology. `symrefs.manifest` is therefore part of the recovery contract. After fetching the
   bundle's refs into a recovery repository, replay each `<name> <target>` line with
   `git symbolic-ref <name> <target>`, then read every target back. A bundle-only restore that turns
   `refs/remotes/origin/HEAD` or another symbolic alias into a direct ref is not complete.
3. **Obtain current-session retirement authority.** A prior cleanup request or a different clone's
   approval does not transfer. Prefer a recoverable OS Trash/quarantine move; permanent deletion
   is a distinct consequence and requires an explicit decision plus the verified bundle.
4. **Freeze the quarantine target, then run process occupancy as a separate probe.** Resolve one
   absolute, unique quarantine/OS Trash destination, prove it does not exist, and select a
   no-clobber move form now. Do not target the clone's parent unless a separate inventory proves
   that parent contains nothing else. Then finish every preliminary Git command.
   On macOS, `/usr/sbin/lsof +D <absolute-clone>` is one available probe; use the platform-native
   equivalent elsewhere. A process result gathered in parallel with another Git probe can be the
   auditor observing its own sibling process, so it cannot authorize a move. Any genuine writer or
   unknown occupant stops the retirement.
5. **Re-freeze, then make the quarantine move the next operation:**

   ```bash
   scripts/git_prepare_clone_retirement.sh --verify-current <external-backup-dir>
   ```

   It fails if refs, reflog identities, metadata bytes/types/modes, physical state, linked-worktree
   or submodule inventory, symbolic-ref topology, unreachable objects, promisor/extension-store
   state, bundle bytes, or source/survivor identity changed. Rebuild the recovery directory on any
   failure; do not edit the receipt. After a successful final verification, move exactly one clone
   to the already-frozen destination with the selected no-clobber form. Do not recheck the
   destination first; the move itself must refuse a race-created destination. This move must be the
   next operation: another probe would
   reopen the very race the final verification closes. No unlocked filesystem sequence can remove
   the last verify-exit-to-move interval; if a writer or automation may still start in that interval,
   stop instead of claiming safety. Treat postconditions—not `mv`'s exit code—as authority: the old
   path must be absent and the quarantine path must contain the clone's `.git` directory. Do not
   target the clone's parent unless a separate inventory proves that parent contains nothing else.
   Keep the external recovery set after the move.
6. **Verify the user-visible result.** The survivor's HEAD/index/worktree must be unchanged; the
   old active path is absent; the quarantine copy or permanent backup is readable; `git bundle
   verify` still succeeds; `git bundle list-heads` still lists the frozen identities; and
   `symrefs.manifest` remains available for topology replay. Report this as scoped clone retirement,
   not as proof that no other checkout exists anywhere.

If the clone must remain active instead of being retired, stop this procedure. For a shared clone,
use the official dissociation path (`git repack -a`) and verify it no longer depends on alternates;
that is a different outcome from clone retirement and should not be smuggled into cleanup.

## Worktree retirement — prove the checkout is disposable before removal

A linked worktree is both a checkout and a ref boundary. A clean branch elsewhere does not prove
the worktree itself has no uncommitted files, and a detached worktree HEAD is absent from ordinary
`--branches` checks. Retire one only after this sequence:

1. **Inventory and identify the primary checkout:** run `git worktree list --porcelain`. Keep the
   first/primary checkout; select only the exact linked path the user intends to retire. A Git
   worktree lock prevents pruning, moving, and deletion; it is not an ownership lease or deletion
   authority. If its reason says the worktree is active, or the user assigns it to another worker,
   stop before inspecting its contents and do not unlock it as a workaround.
2. **Inspect tracked and untracked state in the linked checkout itself:** run
   `git -C <worktree-path> status --porcelain=v1 --untracked-files=all`. The output must be
   empty. Do not substitute the primary checkout's status.
3. **Inventory ignored physical files separately:** run
   `git -C <worktree-path> status --porcelain=v1 --ignored --untracked-files=all` and inspect every
   `!!` path. A normal clean status and `git worktree remove` both ignore this layer, while
   bundle/archive/format-patch cannot reach it. Freeze the complete ignored inventory before
   removal: expand ignored directories to leaf entries and record every relative path and entry
   type, including items classified as disposable. For every regular leaf, record
   `git hash-object --no-filters -- <path>`; for every symlink, record its `readlink` output. Stop on
   an unsupported special-file type. Explicitly classify reproducible caches/build outputs as
   disposable; copy any user-authored or uncertain item outside the worktree first, preserving its
   relative path under the backup. Run the same hash/readlink check on each source and backup copy
   and require equality. Use `git check-ignore -v <path>` when the ignore rule itself is unclear.
4. **Record the exact identity:** copy `git -C <worktree-path> rev-parse HEAD` and
   `git -C <worktree-path> branch --show-current`. An empty branch means detached HEAD, not "no
   work". Confirm the recorded HEAD resolves as a commit; when a branch is present, require that
   branch to resolve to the same SHA. The targeted bundle in step 6 preserves this exact identity.
5. **Prove containment against a fresh base:** fetch the maintained repository, then run
   `scripts/git_verify_branch_merged.sh <recorded-head> <base>`. An
   ancestor/content-contained verdict proves the committed state is on the base; NEEDS REVIEW
   requires manual supersession triage or preserving the commit under a branch/ref.
6. **Back up before deletion:** export the worktree's named branch with `--branch`. For a detached
   HEAD, create one collision-checked `refs/recovery/<worktree-id>` ref at the recorded HEAD and
   export that ref. Verify the targeted bundle; do not pin unrelated danglers or use `--all-refs`
   unless the Outcome contract separately authorizes every captured ref. Keep any ignored-file
   copies from step 3 beside this backup—the bundle does not contain them.
7. **Obtain current-session deletion authority, then remove through Git without force:** run
   the tracked/untracked status check again. Then re-run the exact ignored-inventory command from
   step 3, expand directories the same way, and rebuild the ignored manifest. Its path set, entry
   types, regular-file hashes, and symlink targets must exactly equal the frozen step 3 manifest;
   any added or missing path, type change, content change, or link-target change aborts removal.
   Also require every preserved source and backup copy to match that manifest. Make
   `git worktree remove <absolute-worktree-path>` the next operation—no intervening command may
   reopen the race. Never use `rm -rf` or
   `git worktree remove --force` to make a dirty/uninspectable worktree disappear.
8. **Verify the postconditions independently:** re-run `git worktree list --porcelain`, prove the
   exact path no longer exists, resolve the kept local branch if one exists, and re-run the
   recorded-HEAD containment check (or locate that HEAD in the verified bundle). These observations
   distinguish "checkout removed, history preserved" from a partial cleanup. Re-hash every copied
   ignored file at its backup-relative path and compare it with the pre-removal manifest; merely
   seeing a destination file is not an integrity check.
9. **Retire its branch separately:** prefer `git branch -d <branch>`. Worktree-removal authority
   does not authorize branch deletion. If Git refuses after a
   proven squash/supersession case, require the verified backup and explicit deletion authority
   before `-D`. A worktree removal does not itself prove a remote branch may be deleted.

## Adversarial multi-agent verification (for a whole repo of branches)

A single reviewer scanning a dozen branches reliably misses one real gap (it happened in the
session this skill was distilled from: a solo pass mis-judged a genuine 2-line fix as "already
merged" by matching the wrong call site; a fan-out of independent agents caught it). For a
high-stakes "is *everything* merged?" verdict, fan out:

1. **Partition** the branches across N agents (e.g. large feature-adding branches, small fix
   branches, local-only-history branches, plus one agent that independently re-runs the loss
   check and re-derives the "should this old branch be merged?" verdict from content).
2. **Frame each agent adversarially**: "Default to the assumption that these branches still have
   unmerged unique content, and try to *prove* it. Judge by content (the trial-merge check above),
   never by commit count. Report per branch: MERGED / **UNMERGED / NEEDS REVIEW (with the file(s)
   the trial merge would change)**."
3. **Lock them read-only** (see rules below) so concurrent agents don't corrupt each other's tree.
4. **Counter-review every finding yourself.** An agent's "UNMERGED" is a *hypothesis*: re-run the
   trial-merge / inspect the specific files before believing it (agents produce false positives
   too). An agent's "all merged" is only as good as its method — spot-check that it judged by
   content, not counts.
5. **Converge**: everything merged across all agents = strong confirmation; any single
   content-backed UNMERGED finding = a real gap to land.

This is inline orchestration (the skill spawns the agents), so `git-safety-net` must run inline —
a subagent cannot spawn subagents.

## Rules for the verification agents

Put these in every agent's prompt — they are what make parallel verification safe and correct:

- **Read-only, always.** Only `fetch --quiet`, `merge-base`, `merge-tree`, `diff`, `log`, `show`,
  `cat-file`, `rev-list`, `rev-parse`, `ls-tree`, `for-each-ref`, `branch -r --contains`. **Never**
  `checkout`, `switch`, `reset`, `rebase`, `commit`, `push`, `update-ref`, or `gc`. Multiple agents
  share one working tree; a single `checkout` corrupts everyone else's run.
- **Explicit refs only** (`origin/main`, `origin/<branch>`) so nothing depends on the current
  checkout.
- **Judge by content via the trial merge, not by counts** — restate the check in the prompt.
- **Return structured per-branch verdicts with the file(s) the trial merge would change for any
  UNMERGED**, not prose.
