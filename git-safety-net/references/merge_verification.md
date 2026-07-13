# Merge Verification — prove content is merged without being fooled by counts

## Contents
- Why commit counts lie (the squash-merge illusion)
- The sound content check (a trial merge, not a heuristic)
- Per-branch verdict procedure
- Why safety-biased: a false "merged" loses work, a false "unmerged" only costs a look
- Manual-only investigation hints (do NOT auto-decide on these)
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
machinery instead of per-file guesses. Two checks, in order:

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
   merged_tree=$(git merge-tree --write-tree origin/main origin/<branch> 2>/dev/null | head -1)
   [ $? -eq 0 ] && [ "$merged_tree" = "$base_tree" ] && echo "MERGED (content contained)"
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
