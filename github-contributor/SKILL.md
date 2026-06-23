---
name: github-contributor
description: End-to-end playbook for shipping high-quality pull requests to open-source projects you don't maintain — discovery, CONTRIBUTING compliance, PR-size check, minimal-diff implementation, PR description with AI-assisted disclosure, conflict resolution, and post-submission maintainer interaction. Use whenever creating, editing, or pushing a PR to a third-party GitHub repo — "submit a PR", "open a PR", "fix this upstream", "rebase against main", "respond to the bot review", an `owner/repo` target, or 提 PR / 上游 PR / 贡献代码 / rebase 冲突 / 回应维护者.
---

# GitHub Contributor

A phase-based playbook for shipping pull requests that maintainers actually want to merge. The skill is structured around the real PR lifecycle — discovery → implementation → quality gates → description → post-submission — because each phase has its own failure modes and the most common mistake is doing the right thing at the wrong phase (e.g., writing the perfect description for a PR that's 10× too large).

## Phase 0 — When to use this skill

Use this skill when **all** of these are true:

- You are contributing to a repo you do **not** maintain (the maintainer can close your PR without explanation).
- The work touches one or more of: source code, tests, docs, build config.
- You want the PR merged, not just submitted.

Do **not** use this for: your own repos, internal team PRs with shared context, hot-fix branches where a maintainer is waiting on you, or trivial single-line changes (one comment is enough).

## Phase 1 — Pre-PR Discovery

The most common reason PRs get closed is a mismatch between what the contributor assumes is acceptable and what the maintainer has already written down. Solve this before writing code.

### Step 1.1 — Read CONTRIBUTING.md as a hard contract

CONTRIBUTING.md is **not** style advice. Treat every numbered rule as a precondition for merge. Pay special attention to:

- **AI-assisted contribution clauses.** Many projects added these in 2024-2026 after the AI PR wave. Typical phrasing: "AI-generated PRs without prior discussion may be closed", "you must be able to explain every line", "one issue, one PR". If this clause exists, you owe the project explicit disclosure (see Phase 4) and you must keep the PR small.
- **Issue-first rules.** Some projects require a feature-request issue to exist before any feature PR is opened.
- **Per-language test commands.** If CONTRIBUTING.md says `pnpm test:unit && cargo test`, those are the commands you run, not whatever your IDE prefers.

If CONTRIBUTING.md is missing, that itself is a red flag — see [`references/project_evaluation.md`](references/project_evaluation.md).

### Step 1.2 — Sanity-check your PR size against the project's baseline

A "small PR" is relative. Before opening a PR, run:

```bash
gh pr list --repo <owner>/<repo> --state merged --limit 10 \
  --json number,title,author,additions,deletions \
  --jq '.[] | "#\(.number) +\(.additions)/-\(.deletions): \(.title)"'
```

This tells you the project's actual merged-PR size distribution. If your PR is **5–10× larger than the biggest recent merge**, that is a red signal — split before submitting. See [`references/phase1_discovery.md`](references/phase1_discovery.md) for the baseline rubric and split heuristics.

### Step 1.3 — Write a one-paragraph scope contract before coding

A scope contract is a single paragraph you write **to yourself** before opening your editor:

> Goal: <one sentence>. In scope: <bullet list, 3–5 items>. Explicitly out of scope: <bullet list — be specific about what you will resist adding when it's tempting>.

Then, every time you make an edit, ask: "Is this in scope?" If you find yourself "while I'm in here…"-ing, stop and revisit the contract. Scope creep is the single biggest source of close-without-merge — see [`references/phase2_implementation.md`](references/phase2_implementation.md) for the scope-discipline section.

## Phase 2 — Implementation

### Step 2.1 — Branch off `main` immediately after fetching upstream

```bash
git fetch origin
git switch -c feat/short-descriptive-name origin/main
```

Always branch from upstream `main` (or the project's default branch), never from your fork's `main`, which may be stale.

### Step 2.2 — Make the smallest diff that solves the problem

Resist any change that is not directly required by your scope contract. In particular:
- Do **not** "while I'm here" refactor surrounding code.
- Do **not** reformat lines you didn't touch (your formatter may differ from the project's, even if both say "Prettier").
- Do **not** rename variables for clarity unless the renaming is the fix.

If a follow-up improvement is genuinely valuable, file a separate issue or open a separate PR after this one is merged.

### Step 2.3 — Conventional Commits, one logical change per commit

Use [Conventional Commits](https://www.conventionalcommits.org/): `<type>(<scope>): <description>` where type is `feat | fix | docs | refactor | test | chore | ci | perf`. Each commit should be reviewable on its own.

When a review prompts a fix, use `git commit --fixup=<sha>` and squash with `git -c sequence.editor=: rebase -i --autosquash origin/main` before pushing — see [`references/phase2_implementation.md`](references/phase2_implementation.md) for the full fixup workflow.

## Phase 3 — Quality Gates

Maintainers' trust is built by evidence, not by claims. The point of this phase is to produce evidence you can paste into the PR.

### Step 3.1 — Run the project's full lint + test suite locally

Read the exact commands from CONTRIBUTING.md. Typical examples (use what your project specifies):

```bash
pnpm typecheck && pnpm format:check && pnpm test:unit
cargo fmt --check && cargo clippy --all-targets && cargo test
```

If any check fails, fix it before continuing. Do not push a PR with red local checks expecting CI to clarify — that wastes maintainer time.

### Step 3.2 — For GUI / desktop apps: run real end-to-end with isolation

For Tauri/Electron/Cocoa apps you almost certainly cannot use `pnpm dev` directly without contaminating your real installation. The pattern is **isolate the data directory first, then run the real binary**:

1. Find the project's test-isolation hook (often `XXX_TEST_HOME`, `XXX_DATA_DIR`, or a config flag in `config.rs` / `paths.go`).
2. Point it at `/tmp/<app-name>-e2e/` before launching.
3. Trigger the feature through whatever real surface the user would (URL scheme, CLI arg, deeplink).
4. Verify by reading the actual persisted state (SQLite, JSON files), not just by visual inspection.
5. Capture screenshots of the GUI for the PR description.

The full isolation recipe, including how to trigger deeplinks via Tauri's single-instance forward without touching macOS LaunchServices, is in [`references/phase3_quality_gates_and_e2e.md`](references/phase3_quality_gates_and_e2e.md).

### Step 3.3 — Self-audit: did you actually do what you're about to claim?

Before writing the PR description, list every "I tested…" / "I verified…" / "I ran…" statement you intend to make. For each one, ask: "What's my evidence?" If the answer is "I think I did" or "it should work", you have not actually done it. Write only what you can defend.

This rule prevents the most damaging trust failure: a maintainer running your "tested" command and finding it doesn't work.

### Step 3.4 — Push-time verification

Local tests passing is not the finish line. Before you call the PR merge-ready, run the push-time checklist:

1. **Visibility check** — confirm the target repo is actually public/private as you assume:
   ```bash
   gh repo view <owner>/<repo> --json visibility,isPrivate,defaultBranchRef
   ```
2. **Security hooks** — if pre-push fails, fix the rule or the content; do not `--no-verify`.
3. **Push succeeds** — if it fails with 503/auth errors, check `git config --global --get-regexp url` for stale URL rewrites.
4. **Mergeability check** — `git push` succeeding does not mean GitHub can merge:
   ```bash
   gh pr view <pr-number> --repo <owner>/<repo> --json mergeable,mergeStateStatus
   ```

Full details (URL rewrites, PII-hook false positives, `--force-with-lease` caveats) are in [`references/push_time_gotchas.md`](references/push_time_gotchas.md).

## Phase 4 — PR Description Writing

A great PR description does three jobs: (1) lets the maintainer decide in 30 seconds whether to merge, (2) gives reviewers everything they need to verify without DM'ing you, (3) creates a written record that survives team turnover.

### Step 4.1 — Structure

Use this skeleton. Detailed templates and a test-coverage-matrix example are in [`references/phase4_pr_description.md`](references/phase4_pr_description.md) and [`references/communication_templates.md`](references/communication_templates.md).

```
## Summary / 概述
<two sentences — what changed and why it matters>

## What / 变更内容
<bulleted list of commits with their purpose, or files with their purpose>

## Why / 动机
<the problem this solves; if no prior issue, briefly justify why>

## Test Plan / 测试计划
<exact commands a maintainer can run; coverage matrix for non-trivial changes>

## Backward Compatibility / 向后兼容
<state explicitly; don't make the maintainer infer>

## Security Considerations
<only if the change touches auth, inputs, or shared state>

## Screenshots / 截图
<for UI changes — see Step 4.3>

## Related Issue
<Fixes #N, or explain why no issue exists>

## Checklist
<the project's PR template checklist, with real evidence of each>

## AI-Assisted Disclosure
<see Step 4.4>
```

### Step 4.2 — Test coverage matrix (for non-trivial changes)

When you've added more than 2 tests, present them as a table mapping each test to the behavior it locks in. This makes review much faster than reading test code:

```markdown
| Layer | Test | What it proves |
|---|---|---|
| URL parsing | `test_parse_provider_with_extra_env` | extraEnv query param extracted |
| Security | `test_extra_env_stringifies_scalars_and_skips_invalid_values` | bool/number stringified; null/array/object dropped |
```

### Step 4.3 — Screenshots without polluting the repo

`gh` CLI does **not** support image attachments to PRs (the underlying upload API at `uploads.github.com` is browser-only and rejects PAT tokens). Three workable approaches:

1. **Preferred — let the user drag images in the GitHub web UI.** Leave clearly marked placeholders in your PR body draft (e.g. `[SCREENSHOT_1_PLACEHOLDER]`). When the user edits the PR on github.com, they drag images into the markdown, GitHub uploads them to `user-images.githubusercontent.com`, and the placeholders are replaced. Zero pollution.
2. **Fallback — orphan branch on your fork.** Create an orphan branch (e.g. named `assets-pr-N-screenshots`), commit images, reference them via `raw.githubusercontent.com`. Pollutes your fork but not the PR diff.
3. **Last resort — third-party image host.** Persistence + privacy are unclear; avoid for anything sensitive.

### Step 4.4 — AI-Assisted Disclosure (when CONTRIBUTING.md or maintainer norms call for it)

If the project's CONTRIBUTING.md mentions AI-assisted PRs, or the maintainer has commented skeptically about AI output on past PRs, add a short disclosure at the bottom of the PR body. Be specific about what you did, not vague reassurances.

```markdown
## AI-Assisted Disclosure

Per CONTRIBUTING.md §N:

1. I have read every line; happy to walk through any function or design choice.
2. Tested locally: <list actual commands you ran with their results>.
3. Single-topic PR scoped to <one sentence>.
4. <opened/will open> Issue #N for discussion.
5. AI tools used: Claude Code for drafting; <list any others>. Final review and decisions are mine.
```

The disclosure is not magic — it doesn't excuse a bad PR. But missing it on a project that asks for it is an instant trust hit.

## Phase 5 — Post-Submission

### Step 5.1 — Respond to automated bot reviews explicitly

Modern projects use Codex, Claude bot, CodeRabbit, etc. for first-pass review. Their comments appear as **review comments on specific lines**, not as PR-level comments. Reply to each finding directly (so maintainers see the resolution next to the finding), citing the commit hash and the function/test that resolves it:

```bash
gh api repos/<owner>/<repo>/pulls/<pr>/comments \
  -X POST \
  -F in_reply_to=<finding_comment_id> \
  -f body="Addressed in commit \`<sha>\`: <function or test name>. <one-sentence explanation>. Thanks for the catch!"
```

`<finding_comment_id>` is the numeric ID from the comment's URL (`#discussion_rXXXXXXXX`). Full bot-reply workflow in [`references/phase5_post_submission.md`](references/phase5_post_submission.md).

### Step 5.2 — Rebase against upstream main without losing review history

When upstream `main` advances and your PR conflicts:

```bash
git fetch origin
git rebase origin/main
# resolve conflicts file by file
git add <files>
git -c sequence.editor=: rebase --continue
git push fork <branch> --force-with-lease
```

Use `--force-with-lease`, never plain `--force`. The `lease` variant aborts if someone else (or a bot) pushed to your branch in between, which prevents you from silently destroying review threads.

If you applied a small post-review cleanup (a `--fixup` commit), squash it into the relevant commit with autosquash so the merged history stays clean. See [`references/phase2_implementation.md`](references/phase2_implementation.md) for the full sequence.

### Step 5.3 — When sub-agent / counter-review surfaces "findings", filter before responding

If you run a counter-review agent (or a maintainer's bot floods you with 20+ findings), don't paste them all into the PR. For each finding ask three questions:

| Filter | Discard if |
|---|---|
| Probability | "Could this actually happen in this codebase?" → No |
| Cost | "Would fixing it cost more than the risk?" → Yes |
| Scenario | "Is this scenario already prevented upstream?" → Yes |

The point of counter-review is to surface things you didn't think of, not to mandate fixing every theoretical concern. Filter ruthlessly, then explain in the PR why you accepted vs. declined each suggestion.

## Reference Files

| File | Use for |
|---|---|
| [`references/phase1_discovery.md`](references/phase1_discovery.md) | CONTRIBUTING.md parsing, PR size baseline rubric, scope-contract templates |
| [`references/phase2_implementation.md`](references/phase2_implementation.md) | Fixup commit + autosquash workflow, scope-discipline anti-patterns |
| [`references/phase3_quality_gates_and_e2e.md`](references/phase3_quality_gates_and_e2e.md) | Isolated-home pattern, single-instance forward, SQLite verification, screencapture + window focus |
| [`references/phase4_pr_description.md`](references/phase4_pr_description.md) | Body skeleton, test-coverage-matrix, AI disclosure templates, screenshot placeholder pattern |
| [`references/phase5_post_submission.md`](references/phase5_post_submission.md) | `gh api in_reply_to` recipe, `--force-with-lease` semantics, counter-review filtering |
| [`references/push_time_gotchas.md`](references/push_time_gotchas.md) | Git remote URL rewrites, PII-hook false positives, mergeability verification, force-push caveats |
| [`references/case_study_cc-switch_pr_2634.md`](references/case_study_cc-switch_pr_2634.md) | Full real-world walkthrough including dev log, SQLite dump, screenshots |
| [`references/case_study_cc-switch_pr_1624.md`](references/case_study_cc-switch_pr_1624.md) | Frontend/state-management rebase case study — async init guards, test coupling, i18n conflicts |
| [`references/pr_checklist.md`](references/pr_checklist.md) | Original consolidated checklist (legacy; phase docs supersede the workflow sections) |
| [`references/project_evaluation.md`](references/project_evaluation.md) | Project health rubric for the discovery step |
| [`references/communication_templates.md`](references/communication_templates.md) | Issue-claim, review-response, and after-merge templates |
| [`references/high_quality_pr_case_study.md`](references/high_quality_pr_case_study.md) | OpenClaw PR #39763 walkthrough — small-fix case study |

## Anti-Patterns to Avoid

These are the failure modes that close PRs even when the underlying code is fine. Each one comes from a real PR.

1. **Fabricated test claims.** Writing "tested locally with `pnpm dev`" when you actually only ran the unit tests. A maintainer will try it and lose trust permanently.
2. **PR 5–10× the project's recent merge baseline.** Even good code at this size signals "AI dump" to many maintainers.
3. **Rebase-time scope creep.** Bringing an unrelated upstream feature into your branch "while resolving conflicts" turns a fix PR into a feature PR with no warning.
4. **Mixing refactors into a fix commit.** Reviewers can't tell which line caused the bug fix; either split or use a `--fixup` commit on the refactor.
5. **Force-pushing without `--lease`** mid-review. Destroys review threads silently.
6. **Ignoring bot review comments.** Even when the bot is wrong, reply explaining why — silence reads as "didn't notice".
7. **Burying the disclosure.** AI-assisted disclosure goes in the PR body, not as a footnote in a commit message no one reads.
8. **Reading CONTRIBUTING.md after writing the PR.** Half of CONTRIBUTING.md rules are about how the PR is structured, not what the code does.
9. **Submitting features without an issue when the project requires one.** Even if the issue is created retroactively the same hour, the timestamp matters to maintainers.
10. **Pasting raw counter-review output.** 20 findings in a PR body looks like noise. Filter, then respond.

## Quick Reference

### Required gh CLI commands

```bash
gh repo view <owner>/<repo> --json visibility,isPrivate,defaultBranchRef
gh pr list --repo <owner>/<repo> --state merged --limit 10
gh pr view <pr-number> --repo <owner>/<repo> --json title,body,commits,mergeable,reviewDecision
gh pr edit <pr-number> --repo <owner>/<repo> --body-file pr_body.md
gh api repos/<owner>/<repo>/pulls/<pr>/comments -X POST -F in_reply_to=<id> -f body="..."
```

### Conventional Commits cheat sheet

```
feat(<scope>): user-visible new behavior
fix(<scope>):  user-visible bug fix
refactor(<scope>): no behavior change
docs(<scope>): documentation only
test(<scope>): tests only
chore(<scope>): tooling / build / housekeeping
perf(<scope>): measurable performance change
ci(<scope>): CI config only
```

### Key metrics for a high-quality PR

Based on successful contributions to active projects:

- Files changed: 1-5 for fixes, up to ~15 for features with tests
- Production code diff: under 200 lines if possible; rest is tests / docs
- PR description: 200-600 lines including evidence; matrix tables welcome
- First-response time to bot/maintainer: under 24h
- CI passing on first push: target

If your PR misses two or more of these by a lot, re-read Phase 1 before submitting.
