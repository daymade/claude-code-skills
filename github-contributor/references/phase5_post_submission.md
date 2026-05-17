# Phase 5 — Post-Submission

Detailed playbook for what happens after you push: responding to automated bot reviews, resolving conflicts when upstream advances, force-pushing safely, and filtering counter-review noise.

## 1. Responding to bot reviews (Codex, Claude bot, CodeRabbit, etc.)

Modern projects use AI bots for first-pass review. Their comments appear as **review comments on specific lines**, not as PR-level comments. Each finding gets its own thread, and your reply should appear under the finding (not as a separate PR-level comment), so future reviewers see the resolution next to the original concern.

### 1.1 Find the finding's comment ID

A review comment's URL ends in `#discussion_rXXXXXXXX`. The number is the comment ID. Alternatively:

```bash
gh api repos/<owner>/<repo>/pulls/<pr>/comments \
  --jq '.[] | select(.user.login == "chatgpt-codex-connector[bot]") | {id, body: .body[0:80], path, line}'
```

This lists all bot review comments with their IDs and the line they target.

### 1.2 Reply to a specific finding

```bash
gh api repos/<owner>/<repo>/pulls/<pr>/comments \
  -X POST \
  -F in_reply_to=<comment-id> \
  -f body="Addressed in commit \`<sha>\`: <specific change>. Regression locked in by \`<test-name>\`. Thanks for the catch!"
```

The reply appears threaded under the original finding. The maintainer sees the resolution without searching.

### 1.3 Reply template

```markdown
Addressed in commit \`<sha>\`:

- <function or check>: <one-sentence description of what changed>
- Regression locked in by \`<test-name>\`

Thanks for the catch!
```

Be specific. "Fixed in latest" is not enough — the reviewer should be able to verify your claim in 30 seconds by checking the named commit/test.

### 1.4 When the bot is wrong

If the bot's finding is wrong or doesn't apply, **still reply** — don't ignore. Silence reads as "didn't notice". Acceptable replies:

> Not a real issue here — `X` is already validated upstream by `Y`. Leaving as-is.

> The bot is flagging a false positive: this path is only reached when `Z` is true, and we check that two lines up.

> Considered this but decided the fix would be more risky than the issue. Open to changing if you disagree.

A human maintainer reviewing later will see your reasoning and either accept it or push back.

## 2. Rebase when upstream advances

When upstream `main` lands new commits while your PR is open, GitHub may show "This branch is N commits behind". Most of the time you don't need to do anything — GitHub merges your PR onto current `main` at merge time. But if there's a real conflict, you'll see "This branch has conflicts that must be resolved" and you'll need to rebase.

### 2.1 Standard rebase

```bash
git fetch origin
git rebase origin/main
```

If conflicts occur:

```
CONFLICT (content): Merge conflict in <file>
```

Open the file, resolve the conflict markers manually, then:

```bash
git add <resolved-files>
git -c sequence.editor=: rebase --continue
```

(The `-c sequence.editor=:` part skips the commit message editor for the resolved commit, accepting the existing message.)

If you need to abort and start over:

```bash
git rebase --abort
```

### 2.2 Force-push with lease

After a successful rebase, your local branch has a different history from the remote. You must force-push:

```bash
git push origin <branch> --force-with-lease
```

**Why `--force-with-lease` and not `--force`:**

- `--force` overwrites the remote branch unconditionally. If anyone else (or any bot) pushed to your branch since your last fetch, **their commits are lost without warning**.
- `--force-with-lease` aborts if the remote tip has moved since your last fetch. You'll see "stale info" error and know to fetch + investigate.

In a review context, bot reviews (Codex, Claude bot) sometimes push commits to your branch or post commits as comments — you don't always notice. `--force-with-lease` protects against destroying those silently.

If you legitimately need to overwrite even what the bot pushed:

```bash
git fetch origin <branch>
# Inspect the remote tip with: git log origin/<branch> --oneline -5
# Decide if it's safe to discard, then:
git push origin <branch> --force-with-lease=<branch>:<expected-remote-sha>
```

This is the precise form: "Only force-push if the remote tip is exactly `<expected-remote-sha>`."

### 2.3 Handling conflict in code you didn't write

If upstream's new code conflicts with yours, you have to integrate. The minimum integration is to leave the new code as-is and put yours alongside.

**Anti-pattern**: extending your feature to "naturally" cover the new upstream code. That's scope creep at rebase time — see [`phase2_implementation.md`](phase2_implementation.md) §4.2.

If extension is unavoidable (e.g., upstream added an enum variant your match statement must handle), **declare it in the PR description**:

```markdown
## Note on rebase

Upstream landed <feature> in [#NNNN](link) during this PR's review. The rebase
required extending <my-feature> to cover the new variant. The diff for that
integration is in commit <sha>; happy to split into a separate PR if you'd prefer.
```

The maintainer is much more receptive to a declared scope expansion than a discovered one.

## 3. Force-push during active review

If your PR is in active review (a maintainer or bot has left comments), avoid force-pushing if possible. Reasons:

- Some review comments are anchored to specific commits; force-push can orphan them.
- The reviewer's mental model is "I last reviewed at commit X" — if you replace history, they have to re-orient.
- It looks evasive ("did the contributor delete my comment thread?").

Prefer **appending fixup commits** during active review:

```bash
# After review comment, edit files
git add <changed>
git commit -m "fix review: handle empty case"  # or use --fixup= for autosquash later
git push origin <branch>  # no force needed
```

Once review is complete and the maintainer is ready to merge, you can rebase + autosquash to clean up the history if the project's CI requires it (some projects squash-merge anyway).

## 4. Filtering counter-review output

If you run a counter-review agent (or get flooded with 20+ bot findings), don't paste them all into the PR. Filter ruthlessly using three lenses:

| Lens | Discard a finding if... |
|---|---|
| Probability | "In this codebase's actual usage, could this scenario realistically occur?" → No |
| Cost | "Would fixing it cost more (review surface, test surface, regression risk) than the issue's expected damage?" → Yes |
| Existing defense | "Is this scenario already prevented upstream or by some invariant I can name?" → Yes |

For each finding that survives the filter, address it (in code or with a reply explaining why you accepted vs. declined). Discard the rest silently — they're noise, not signal.

### 4.1 What "noise" looks like in practice

- Type-system over-defense: "Wrap this `unwrap()` in a `match` even though the input is statically known to be `Some`."
- Premature optimization: "Cache this lookup that runs once per program startup."
- Style preferences disguised as bugs: "Reorder these arguments alphabetically."
- Spec-mismatch where the spec is yours: "This doesn't match the standard X" — when the project deliberately diverges from X.

A good counter-review agent surfaces things you missed. A mediocre one floods you with low-value findings. Don't reward the latter by treating every finding as actionable.

## 5. Responding to a maintainer's substantive review

Different from bot review: a human maintainer's comment is a signal of engagement. Reply quickly (within 24h is ideal) and constructively.

### 5.1 Accepting a change request

```markdown
Good point — updated in <sha>: <one-line summary of what changed>.
```

### 5.2 Explaining a deliberate choice

```markdown
I chose this approach because <reason 1>, <reason 2>. The tradeoff is <X>, but I weighed it against <Y> and went this way. Open to switching if you'd prefer <alternative>.
```

### 5.3 Requesting clarification

```markdown
Thanks for the feedback — could you clarify what you mean by "<quote>"? I want to make sure I address the right concern.
```

### 5.4 Disagreeing respectfully

```markdown
I see your point about <X>. The current approach was chosen because <reason>, but I understand the concern.

Would a middle-ground like <alternative> work for you? It addresses <maintainer's concern> while keeping <my benefit>.
```

The pattern: acknowledge → reason → offer compromise. Never escalate to "you're wrong".

See [`communication_templates.md`](communication_templates.md) for more response templates.

## 6. After merge

Once your PR merges, send a brief thank-you and close the loop:

```markdown
Thanks for the review and merge! Learned <one specific thing> from the feedback — will apply that in future contributions.
```

This:

- Closes the conversation politely.
- Signals you read and absorbed the feedback (not just complied).
- Builds a reputation for future PRs.

Then:

- Delete your local feature branch: `git branch -d <branch>`.
- Delete your fork's feature branch (GitHub UI offers a button after merge).
- Update your fork's `main`: `git fetch upstream && git switch main && git merge upstream/main && git push origin main`.

You're ready for the next PR.
