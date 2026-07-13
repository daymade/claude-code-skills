# Merge Verification — prove content is merged without being fooled by counts

## Contents
- Why commit counts lie (the squash-merge illusion)
- The content-level toolkit (five checks)
- Per-branch verdict procedure
- "Superseded old version" vs "genuinely missing" — don't confuse them
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

The only trustworthy question is: **is the branch's file content present on the base?**

## The content-level toolkit (five checks)

Run these with explicit refs (`origin/main`, `origin/<branch>`) — no checkout needed.

1. **Whole files the branch adds that the base lacks** (an unmerged *new* skill/module shows here):
   ```bash
   git diff origin/main origin/<branch> --diff-filter=A --name-only
   ```
   Empty = the branch introduces no file absent from main. Non-empty → inspect each: is it truly
   absent (`git cat-file -e origin/main:<path>` fails) or just moved/renamed on main?

2. **Per-file blob identity** (is this file byte-identical on both sides?):
   ```bash
   git diff --quiet origin/<branch>:<file> origin/main:<file> && echo IDENTICAL || echo DIFFERS
   ```

3. **Is this exact file version anywhere in the base's history** (proves main passed through it and
   moved on — i.e. superseded, not missing):
   ```bash
   blob=$(git rev-parse origin/<branch>:<file>)
   git log origin/main --oneline --find-object="$blob" | head
   ```
   A hit means main once held this exact content, then rewrote it → superseded, safe.

4. **True ancestor** (the branch is literally in main's history — fully merged, deletable):
   ```bash
   git merge-base --is-ancestor origin/<branch> origin/main && echo MERGED-ANCESTOR
   ```

5. **Patch-equivalence for a single commit** (did this commit's change land under a different sha?):
   ```bash
   git cherry origin/main <sha>       # '-' prefix = already in main; '+' = not
   ```

## Per-branch verdict procedure

For each branch, decide among three outcomes:

- **MERGED (ancestor)** — check 4 passes → in main's history, delete freely.
- **STALE-SQUASH (merged by content)** — check 1 empty (no unmerged new files) and every modified
  file resolves via check 2 (identical) or check 3 (superseded old version on main). Content is on
  main; the commit count is an artifact. Deletable.
- **UNMERGED** — check 1 lists a file genuinely absent from main, **or** a modified file has branch
  content that is *not* identical and *not* found in main's history (check 3 empty) and represents
  real behavior main lacks. Report the specific `file` (and ideally the specific hunk/function).

`scripts/git_verify_branch_merged.sh <branch> [base]` automates checks 1–4 and prints the verdict.

## "Superseded old version" vs "genuinely missing" — don't confuse them

The subtle error is seeing a modified file "differs from main" and calling the branch UNMERGED,
when in fact **main evolved *past* the branch** (has everything the branch had, plus more). Two
tells that main is ahead, not behind:

- The base file is **larger / a superset**: `git show origin/main:<file> | wc -l` ≫
  `git show origin/<branch>:<file> | wc -l`, and the branch's distinctive symbols all appear in
  main (`git show origin/main:<file> | grep -F '<branch-only-symbol>'`).
- The branch's exact blob appears in main's history (check 3 above) — main held it, then rewrote it.

Only when the branch has a symbol/function/behavior that is **nowhere in main's current file and
nowhere in main's history** is it genuinely unmerged. When unsure, quote the specific missing line
and let the human confirm — a false "unmerged" wastes a re-merge; a false "merged" loses the work.

## Adversarial multi-agent verification (for a whole repo of branches)

A single reviewer scanning a dozen branches reliably misses one real gap (it happened in the
session this skill was distilled from: a solo pass mis-judged a genuine 2-line fix as "already
merged" by matching the wrong call site; a fan-out of independent agents caught it). For a
high-stakes "is *everything* merged?" verdict, fan out:

1. **Partition** the branches across N agents (e.g. large feature-adding branches, small fix
   branches, local-only-history branches, plus one agent that independently re-runs the loss
   check and re-derives the "should this old branch be merged?" verdict from content).
2. **Frame each agent adversarially**: "Default to the assumption that these branches still have
   unmerged unique content, and try to *prove* it. Judge by content (checks above), never by
   commit count. Report per branch: MERGED / STALE-SQUASH / **UNMERGED (with file:line evidence)**."
3. **Lock them read-only** (see rules below) so concurrent agents don't corrupt each other's tree.
4. **Counter-review every finding yourself.** An agent's "UNMERGED" is a *hypothesis*: re-run the
   specific blob/line check before believing it (agents produce false positives too). An agent's
   "all merged" is only as good as its method — spot-check that it judged by content, not counts.
5. **Converge**: everything merged across all agents = strong confirmation; any single content-backed
   UNMERGED finding = a real gap to land.

This is inline orchestration (the skill spawns the agents), so `git-safety-net` must run inline —
a subagent cannot spawn subagents.

## Rules for the verification agents

Put these in every agent's prompt — they are what make parallel verification safe and correct:

- **Read-only, always.** Only `fetch --quiet`, `diff`, `log`, `show`, `cat-file`, `rev-list`,
  `merge-base`, `ls-tree`, `for-each-ref`, `branch -r --contains`. **Never** `checkout`, `switch`,
  `reset`, `rebase`, `commit`, `push`, `update-ref`, or `gc`. Multiple agents share one working
  tree; a single `checkout` corrupts everyone else's run.
- **Explicit refs only** (`origin/main`, `origin/<branch>`) so nothing depends on the current
  checkout.
- **Judge by content, not counts** — restate checks 1–5 in the prompt.
- **Return structured per-branch verdicts with file:line evidence for any UNMERGED**, not prose.
