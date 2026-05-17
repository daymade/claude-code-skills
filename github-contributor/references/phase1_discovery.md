# Phase 1 — Pre-PR Discovery

Detailed playbook for the discovery phase: reading CONTRIBUTING.md as a contract, sizing your PR against the project's actual baseline, and writing a scope contract before opening your editor.

## 1. Reading CONTRIBUTING.md as a contract

Open the file and read it linearly the first time. On the second pass, extract a checklist of the rules that bind your PR. Pay attention to:

### 1.1 The AI-Assisted Contributions section (if it exists)

Common patterns in projects that have one:

- "You must be able to explain every line." — Implication: no copy-pasted code you can't justify. If a reviewer asks why a line is the way it is and your answer is "Claude wrote it like that", the PR is likely closed.
- "One issue, one PR." — Implication: scope creep is a hard reject. Split before submitting.
- "Open an issue first." — Implication: a same-day issue created right before the PR is better than no issue, but the most respectful path is to file the issue, wait for a maintainer reaction, then PR.
- "Maintainers may close without explanation." — Implication: assume the reviewer is busy and won't engage with a flawed PR. Make it impossible to dismiss.

If the project has such a section, add an "AI-Assisted Disclosure" block to your PR body (see [`phase4_pr_description.md`](phase4_pr_description.md)).

### 1.2 The PR checklist

Most CONTRIBUTING.md files end with a checklist like:

```
- [ ] pnpm typecheck passes
- [ ] pnpm format:check passes
- [ ] cargo clippy passes (if Rust code changed)
- [ ] Updated i18n files if user-facing text changed
```

Every unchecked box that applies to your change is a reason for the maintainer to send the PR back. Run the exact commands from CONTRIBUTING.md (not your IDE's variant) and check each box only when you have evidence in front of you.

### 1.3 Issue templates

If the project uses GitHub issue templates and you're filing an issue first, use the template — don't fill in a freeform issue. Maintainers will close mis-formatted issues faster than they'll close mis-formatted PRs.

### 1.4 Conventional Commits requirement

Many projects enforce `feat(scope): description` style via a CI hook. If CONTRIBUTING.md mentions Conventional Commits, audit your local commits before pushing:

```bash
git log origin/main..HEAD --format=%s
```

Each line should match `^(feat|fix|docs|refactor|test|chore|ci|perf|build|revert)(\(.+\))?: .+`. Reword commits with `git commit --amend` or `git rebase -i` before pushing.

## 2. Sizing your PR against the project's baseline

A "small PR" is relative to the project. Some projects routinely merge 1000-line refactors; others reject anything over 200 lines without prior discussion.

### 2.1 Run the baseline query

```bash
gh pr list --repo <owner>/<repo> --state merged --limit 10 \
  --json number,title,author,additions,deletions,mergedAt \
  --jq '.[] | "#\(.number) +\(.additions)/-\(.deletions) by \(.author.login): \(.title)"'
```

Extend to 20 PRs if the recent 10 look unusually skewed (e.g., a single dependabot dominates).

### 2.2 Interpret the distribution

| Your PR size vs. project's recent maximum | Signal |
|---|---|
| Under or equal to the recent max | Green — submit as planned |
| 1.5–3× the recent max | Yellow — justify the size in the PR body's "Why" section. Maintainer will scrutinize but probably engage. |
| 5–10× the recent max | Red — split before submitting. If you can't split, declare in the PR body that you're aware of the size and offer to split on request. |
| >10× | Stop. Open an issue first, get explicit consent for the PR size, then proceed. |

### 2.3 How to split a too-large PR

If your work spans multiple logical changes, split along these natural seams:

- **Refactor before feature.** PR 1: extract or rename interfaces so the feature can land cleanly. PR 2: the feature itself.
- **Tests before fix.** PR 1: add the failing regression test (skip-marked). PR 2: the fix that unskips it. Easier to review than a single PR with both.
- **Backend before frontend.** PR 1: API + tests. PR 2: UI consumption.
- **Per-AppType / per-module.** If your change touches three providers, three PRs are easier to merge than one.

## 3. The scope contract

Write this paragraph **to yourself**, before opening your editor:

```
Goal: <one sentence — what user-visible behavior changes or what specific bug is fixed>
In scope:
  - <bullet — be specific>
  - <bullet>
  - <bullet>
Explicitly out of scope:
  - <bullet — list the temptations you will resist>
  - <bullet>
```

The "Explicitly out of scope" section is the most useful one. Anticipate the temptations:

- "While I'm in this file I'll fix this unrelated typo." → out of scope.
- "These other 3 functions have the same anti-pattern, I'll fix them too." → out of scope; file a separate issue.
- "I noticed an outdated comment, let me update it." → out of scope.
- "The CI config uses old action versions, let me bump them." → out of scope.

The reason for ruthlessness: every "while I'm here" addition gives a reviewer a new reason to push back, and any one of those reasons can sink the merge.

### 3.1 Scope contract template

Keep the contract somewhere you'll re-read it — in a `SCOPE.md` in your worktree, as the body of your draft PR description, or as a sticky note. Re-read it before every commit. If you find yourself making an edit that's not on the "In scope" list, stop and either (a) add it to the list with justification, or (b) revert the edit.

## 4. Project health quick-check (when choosing what to work on)

If you're picking a project rather than fixing a problem you already have, validate the project is alive before investing time:

```bash
gh repo view <owner>/<repo> \
  --json updatedAt,stargazerCount,issues,pullRequests,defaultBranchRef \
  --jq '{
    lastUpdate: .updatedAt,
    stars: .stargazerCount,
    openIssues: .issues.totalCount,
    openPRs: .pullRequests.totalCount,
    defaultBranch: .defaultBranchRef.name
  }'
```

Red flags:

- `lastUpdate` more than 6 months ago.
- Many open PRs that haven't been reviewed in months — your PR will sit too.
- Maintainer hostility in recent issue comments.
- No CONTRIBUTING.md at all (some good projects skip it, but it's a yellow flag).

Green flags:

- `good first issue` label maintained.
- Regular releases (check `gh release list`).
- Maintainer replies on issues within a week.
- Multiple active maintainers (check `gh api repos/<owner>/<repo>/contributors --jq '.[0:5][].login'`).

See [`project_evaluation.md`](project_evaluation.md) for the full rubric.

## 5. Fork hygiene

Always work from upstream `main`, never from your fork's stale `main`:

```bash
# Inside an existing clone of your fork:
git remote get-url origin   # should be your fork
git remote add upstream https://github.com/<owner>/<repo>.git  # add upstream if missing
git fetch upstream
git switch -c feat/short-name upstream/main
```

If you've been working on a feature branch for a while and upstream has advanced:

```bash
git fetch upstream
git rebase upstream/main
# resolve conflicts, then:
git push origin <branch> --force-with-lease  # never plain --force
```

See [`phase5_post_submission.md`](phase5_post_submission.md) for the full rebase recipe including conflict-resolution patterns.
