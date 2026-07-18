# Merge Verification — prove content is merged without being fooled by counts

## Contents
- Why commit counts lie (the squash-merge illusion)
- The sound content check (a trial merge, not a heuristic)
- Per-branch verdict procedure
- Why safety-biased: a false "merged" loses work, a false "unmerged" only costs a look
- Manual-only investigation hints (do NOT auto-decide on these)
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

## Per-branch verdict procedure

For each branch, the script decides among three outcomes:

- **MERGED (ancestor)** — in the base's history. Delete freely.
- **MERGED (content contained)** — a trial merge into the base changes nothing; the "commits
  ahead" count is a squash/rebase artifact. Delete freely.
- **UNMERGED / NEEDS REVIEW** — a trial merge *would* change the base, so the branch carries
  content the base does not already have (a genuinely new/edited/reverted/deleted file). Review
  the listed contribution before deleting.

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

**The label on the leftover is not evidence.** Stash messages and branch names describe intent
*at creation time* ("unfinished", "backup", "wip") — they never get updated when the work later
lands through another path. Judge by content against the current base, never by how urgent the
name sounds.

Same safety bias as everywhere else in this skill: prove supersession per item, or keep the item.

## Worktree retirement — prove the checkout is disposable before removal

A linked worktree is both a checkout and a ref boundary. A clean branch elsewhere does not prove
the worktree itself has no uncommitted files, and a detached worktree HEAD is absent from ordinary
`--branches` checks. Retire one only after this sequence:

1. **Inventory and identify the primary checkout:** run `git worktree list --porcelain`. Keep the
   first/primary checkout; select only the exact linked path the user intends to retire.
2. **Inspect the linked checkout itself:** run `git -C <worktree-path> status --short --branch`.
   Any tracked or untracked output blocks removal. Do not substitute the primary checkout's status.
3. **Record the exact identity:** copy `git -C <worktree-path> rev-parse HEAD` and
   `git -C <worktree-path> branch --show-current`. An empty branch means detached HEAD, not "no
   work". Confirm the recorded HEAD appears in the all-worktree loss audit.
4. **Prove containment:** run `scripts/git_verify_branch_merged.sh <recorded-head> <base>`. An
   ancestor/content-contained verdict proves the committed state is on the base; NEEDS REVIEW
   requires manual supersession triage or preserving the commit under a branch/ref.
5. **Back up before deletion:** pin dangling commits, then run
   `scripts/git_export_before_drop.sh --all-refs --out <backup-dir>` and verify the bundle. `--all`
   includes linked-worktree HEAD refs; truly dangling objects appear only after pinning.
6. **Remove through Git, without force:** run `git worktree remove <absolute-worktree-path>` and
   re-run `git worktree list --porcelain`. Never use `rm -rf` or `git worktree remove --force` to
   make a dirty/uninspectable worktree disappear.
7. **Retire its branch separately:** prefer `git branch -d <branch>`. If Git refuses after a
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
