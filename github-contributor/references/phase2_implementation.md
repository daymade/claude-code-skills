# Phase 2 — Implementation

Detailed playbook for the implementation phase: writing the smallest diff that solves the problem, structuring commits for review, and using the `--fixup` + autosquash workflow to keep history clean.

## 1. The minimal-diff principle

A good PR changes only what's necessary. Every unrelated line you touch increases review surface area and gives a reviewer a new place to push back.

### 1.1 What "necessary" means

A line is necessary if removing your change to it would make your fix incomplete or wrong. Examples:

- ✅ Changing the function body where the bug lives — necessary.
- ✅ Updating a test that asserts the buggy behavior — necessary.
- ✅ Updating the type signature when you added a new parameter — necessary.
- ❌ Reformatting the whole file because your editor saved it — not necessary; revert.
- ❌ Renaming variables for clarity — not necessary unless the rename **is** the fix.
- ❌ Reorganizing imports — not necessary unless the project's linter explicitly requires it.

### 1.2 How to enforce the minimal diff

After writing your change, run `git diff origin/main..HEAD` and read every hunk. For each hunk, ask: "Is this part of the minimal change to ship the feature/fix?" Revert hunks that aren't.

A useful self-check is `git diff --stat origin/main..HEAD` — if the number of files or lines surprises you, you have unintentional changes.

### 1.3 What to do with "improvements" you noticed along the way

Two options:

- **File an issue.** Document the improvement so it isn't lost. Title it clearly: "Refactor: extract X helper" or "Cleanup: rename Y for consistency". Mention it in your PR body as "Noticed during this work, filed as #<issue>".
- **Save it for a follow-up PR.** Once the current PR merges, open a new branch for the improvement.

## 2. Commit structure

Each commit should be reviewable on its own — a reviewer should be able to checkout that commit and have a coherent state.

### 2.1 Conventional Commits

Format: `<type>(<scope>): <description>` where:

| Type | Use for |
|---|---|
| `feat` | User-visible new behavior |
| `fix` | User-visible bug fix |
| `refactor` | No behavior change, code organization only |
| `docs` | Documentation only |
| `test` | Tests only |
| `chore` | Tooling, build, housekeeping |
| `ci` | CI configuration only |
| `perf` | Measurable performance change |
| `build` | Build system changes |
| `revert` | Reverts a previous commit |

The `<scope>` is the project's term for the area you touched (e.g., `auth`, `proxy`, `deeplink`). If unsure, look at recent commits with `git log --format=%s -20`.

The description is **imperative present tense, lowercase, no trailing period**:

- ✅ `feat(deeplink): support extraEnv parameter for provider configuration`
- ❌ `Added extraEnv support to deeplink` (past tense, capitalized)
- ❌ `feat: support extra env` (missing scope, vague description)

### 2.2 One logical change per commit

Examples of well-structured commits:

```
feat(api): add /v1/widgets endpoint
test(api): cover happy-path and validation errors for /v1/widgets
docs(api): document /v1/widgets request/response shape
```

vs. the anti-pattern:

```
feat: add widgets endpoint + tests + docs + fix unrelated typo
```

If you're tempted to make a "various improvements" commit, it's a sign you should split.

### 2.3 Body text in commit messages

For non-trivial commits, write a body that explains **why**:

```
feat(deeplink): support extraEnv parameter for provider configuration

Distributors currently have to ask users to manually flip UI toggles
after importing a provider via deeplink. extraEnv carries a Base64-
encoded JSON object that is merged into settings_config.env, so a
single click can configure the provider end-to-end.

Backward-compatible: extraEnv is optional and serialized with
skip_serializing_if = "Option::is_none". Existing deeplinks parse
unchanged.
```

The body lives forever in `git log`; the PR description body lives in GitHub's UI and may be edited or removed.

## 3. The fixup + autosquash workflow

When a reviewer asks for a change to an existing commit (e.g., "rename this variable" on commit 2 of a 5-commit PR), don't append a "Fix review comments" commit. Instead:

### 3.1 Make a fixup commit

```bash
# Edit the files to address the review comment
git add <changed-files>
git commit --fixup=<sha-of-the-commit-to-amend>
```

This creates a commit titled `fixup! <original commit subject>`. Don't push it yet.

### 3.2 Autosquash

Once you have all your fixup commits ready:

```bash
git -c sequence.editor=: rebase -i --autosquash origin/main
```

The `--autosquash` flag reorders `fixup!` commits next to their target and marks them as fixups. The `-c sequence.editor=:` part is a trick: it sets the rebase sequence editor to `:` (the no-op shell builtin), which means the rebase plan is accepted as-is without opening an editor. Use this when you trust autosquash to do the right thing automatically.

If you want to inspect or modify the rebase plan first, omit `-c sequence.editor=:` and your normal `$GIT_EDITOR` will open.

### 3.3 Force-push with lease

```bash
git push origin <branch> --force-with-lease
```

`--force-with-lease` fails if the remote has advanced since your last fetch. This prevents you from clobbering someone else's push (including bot pushes that happen during review). **Never use plain `--force`** during review — see [`phase5_post_submission.md`](phase5_post_submission.md) for the full rationale.

## 4. Scope creep — the four anti-patterns

These are the most common ways a focused PR turns into a sprawling one.

### 4.1 "While I'm in here"

You opened `provider.rs` to fix one function, noticed three other things that could be better, and changed all four. Each of those three other things is an independent decision the reviewer now has to evaluate.

**Defense**: re-read your scope contract before each commit. Anything not on the "In scope" list goes in a separate PR.

### 4.2 Rebase-time accidental expansion

While resolving a conflict, you bring in a new feature from upstream that wasn't yours, then "naturally" extend your change to cover it (e.g., upstream added a new enum variant, and you make your code handle it).

**Defense**: when rebase forces you to integrate with new upstream code, the minimum integration is to leave the new code alone. If extending your feature to cover the new code is unavoidable, **declare it in the PR description** so the maintainer isn't surprised.

### 4.3 Tool-assisted "cleanups"

You ran a `code-simplifier` agent or linter --fix and it touched files unrelated to your change. Those changes are now in your diff.

**Defense**: review the agent/linter output as carefully as your own. Revert any changes that aren't part of your scope contract. If a cleanup is genuinely valuable, **commit it separately**, then decide whether it ships in this PR or a follow-up.

In the cc-switch PR #2634 case study, a `code-simplifier` cleanup got bundled into the fix commit. This made the diff harder to review and almost gave the maintainer a reason to push back. The right move would have been to extract the cleanup into a separate `refactor` commit.

### 4.4 Test-coverage expansion

You added one regression test for the bug, then "while I'm at it" added tests for adjacent untested functions. The reviewer now has to evaluate three new tests instead of one.

**Defense**: the regression test for **the bug you fixed** is in scope. Tests for adjacent functions go in a `test(scope): add coverage for X` follow-up PR.

## 5. Conventional Commit cheat sheet

```
feat(auth): add OAuth2 PKCE flow
fix(parser): handle empty Base64 input without panicking
refactor(api): extract pagination helper
docs(readme): document new env vars
test(parser): cover Base64 edge cases (empty, whitespace, padded)
chore(deps): bump tokio to 1.46
ci(release): pin actions/checkout to v5
perf(query): cache parsed results across calls
build(makefile): add release-darwin target
revert: feat(auth): add OAuth2 PKCE flow
```

Scope is optional but recommended. Description is the answer to "If this commit landed, what would change?"

## 6. Pre-push checklist

Before `git push`, run mentally:

- [ ] `git diff --stat origin/main..HEAD` — does the file count and line count match what I intended?
- [ ] `git log --format=%s origin/main..HEAD` — does every commit message follow Conventional Commits?
- [ ] Are there any `console.log`, `dbg!`, debug prints, or commented-out code in the diff?
- [ ] Are there any leftover `TODO` comments unrelated to this PR?
- [ ] Does each commit pass the project's lint + tests on its own (i.e., bisect-friendly)?

If any answer is no, fix locally before pushing.
