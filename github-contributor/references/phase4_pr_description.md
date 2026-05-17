# Phase 4 — Writing the PR Description

Detailed playbook for the PR description: structure, the test-coverage-matrix pattern, the AI-Assisted Disclosure block, and screenshot embedding without polluting the repo.

## 1. What the PR description is for

The PR description has three jobs, in order of importance:

1. **Let the maintainer decide in 30 seconds** whether this is worth merging.
2. **Give reviewers everything they need to verify** without DM'ing you.
3. **Create a written record** that survives team turnover.

A PR description optimizes for the reviewer's time, not yours. Write longer if the change is non-trivial — but every paragraph must earn its place.

## 2. Body skeleton

```markdown
## Summary / 概述
<2 sentences max — what changed, why it matters>

## What / 变更内容
<bulleted list of commits OR files, with their purpose>

## Why / 动机
<the problem this solves; if no prior issue, justify the change in 1 paragraph>

## Test Plan / 测试计划
<exact commands a maintainer can run; coverage matrix for non-trivial changes>

## How to verify locally / 如何本地验证
<copy-pasteable commands that produce the evidence>

## Backward Compatibility / 向后兼容
<state explicitly; don't make the maintainer infer>

## Security Considerations
<only if the change touches auth, untrusted input, or shared state>

## Screenshots / 截图
<placeholder for the user to drag images into the GitHub web UI>

## Related Issue
<Fixes #N, or explain why no issue exists>

## Checklist
<copy of the project's PR template checklist, with real evidence per box>

## AI-Assisted Disclosure
<if CONTRIBUTING.md mentions AI contributions — see section 5>
```

Bilingual headings are optional but appreciated by international projects with mixed-language maintainers. Use them if the project's own commit messages or issue templates are bilingual.

## 3. The Summary section

Two sentences. The first describes what changed; the second describes why it matters or what enables.

Good:

> Adds an optional `extraEnv` Base64-encoded JSON parameter to provider deeplinks. This lets distributors ship pre-configured providers in a single click instead of asking users to manually flip UI toggles after import.

Bad:

> This PR adds a new feature for deeplinks. It's been a long process but I finally figured it out. Hopefully this is useful.

The first version answers "what" and "why" with concrete nouns. The second answers neither.

## 4. The Test Plan section

### 4.1 Test coverage matrix

When your PR adds more than 2-3 tests, present them as a table. The maintainer can scan the table once instead of reading test code.

```markdown
| Layer | Test | What it proves |
|---|---|---|
| URL parsing | `test_parse_provider_with_extra_env` | `extraEnv` query param extracted to `Option<String>` |
| Build (happy path) | `test_build_claude_settings_with_extra_env` | Claude `env` block merged correctly |
| Build (backward compat) | `test_extra_env_does_not_break_without_value` | Absent `extraEnv` → unchanged behavior |
| Build (error tolerance) | `test_extra_env_ignores_invalid_base64` | Garbage Base64 → logged, skipped, import continues |
| Security | `test_extra_env_stringifies_scalars_and_skips_invalid_values` | Bools/numbers stringified; null/array/object dropped |
| Integration | `deeplink_import_claude_provider_persists_to_db` | Full DB round-trip with `extraEnv` |
```

### 4.2 Verified-locally checklist with real output

Include the exact commands you ran and a short proof:

```markdown
### Verified on this branch tip (\`<commit-sha>\`):

\```bash
$ cd src-tauri && cargo test --lib deeplink
test result: ok. 40 passed; 0 failed; 0 ignored

$ cargo test --test deeplink_import
test result: ok. 5 passed; 0 failed; 0 ignored

$ pnpm test:unit
Test Files  36 passed (36)
     Tests  223 passed (223)

$ cargo clippy --all-targets   # clean
$ cargo fmt --check            # clean
$ pnpm typecheck               # clean
$ pnpm format:check            # clean
\```
```

This is short, copy-pasteable, and a reviewer can reproduce it in one minute.

## 5. AI-Assisted Disclosure block

If CONTRIBUTING.md has an AI-assisted contribution clause (or the project's maintainer has commented skeptically on past AI-assisted PRs), add this block at the bottom of your description. Be specific, not generic.

```markdown
## AI-Assisted Disclosure

Per CONTRIBUTING.md §<section-number>:

1. **I have read every line.** Happy to walk through any function or design choice on request. Specifically: <one example of a non-obvious choice you can defend>.
2. **Tested locally.** <list the actual commands you ran and the actual results — don't be vague>. Cannot personally verify <platform you don't have>; no platform-specific APIs are touched.
3. **Single-topic.** This PR is scoped to <one sentence>. The <name of any tool-assisted cleanup>'s changes are confined to <files> and total <N> lines; if you'd prefer them split out I can do that.
4. **<Issue status>.** <Either: "Fixes #N" / "No prior issue; happy to open one retroactively if you'd prefer that paper trail before merging."> 
5. **AI tools used.** Claude Code for drafting; <list any others, e.g., Codex's automated review, GitHub Copilot>. <Note any specific findings AI tools drove — e.g., "Codex's P1+P2 review directly drove the hardening work in commit 2.">. Final review and decisions are mine.
```

The disclosure does not excuse poor work — but missing it on a project that requires it is an instant trust hit. Treat it as a hard requirement when CONTRIBUTING.md mentions AI contributions.

## 6. Screenshot embedding without polluting the repo

### 6.1 The problem

`gh` CLI does **not** support image attachments to PR descriptions. GitHub's upload endpoint at `uploads.github.com` requires browser session cookies + CSRF tokens, not PAT tokens. Community tools (`gh-attach`, `gh-pic`) reverse-engineer the undocumented API and break intermittently.

### 6.2 The cleanest approach: placeholders + user drag-drop

1. In your local PR draft (e.g., `/tmp/pr_body.md`), leave clearly-named placeholders:

   ```markdown
   ### Screenshot 1: import dialog
   
   [E2E_SCREENSHOT_1_PLACEHOLDER — drag screenshot_1_import_dialog.png here]
   
   ### Screenshot 2: edit provider showing env block
   
   [E2E_SCREENSHOT_2_PLACEHOLDER — drag screenshot_2_env_block.png here]
   ```

2. Push the description: `gh pr edit <pr> --body-file /tmp/pr_body.md`.

3. Tell the user (or do yourself): open the PR in browser, click Edit (pencil icon), find each placeholder, delete it, drag the corresponding image file from Finder into the markdown area. GitHub uploads to `user-images.githubusercontent.com` and replaces the placeholder with `![](url)`.

4. Save.

Zero repo pollution. Images live on GitHub's CDN.

### 6.3 Fallback: orphan branch on your fork

If you can't have a human do the drag-drop step (e.g., automation pipeline):

```bash
# Create an orphan branch holding only screenshots
git worktree add -b assets/pr-<N>-screenshots /tmp/assets-worktree
cd /tmp/assets-worktree
git rm -rf .  # remove everything from the orphan branch
cp /tmp/screenshot_*.png .
git add .
git commit -m "screenshots for PR #<N>"
git push fork assets/pr-<N>-screenshots
cd -
git worktree remove /tmp/assets-worktree
```

Reference in PR body:

```markdown
![](https://raw.githubusercontent.com/<your-fork-user>/<repo>/assets/pr-<N>-screenshots/screenshot_1_import_dialog.png)
```

This pollutes your fork (extra branch) but not the PR diff (the orphan branch is independent).

### 6.4 Last resort: third-party image host

Imgur, Cloudinary, etc. Be aware:

- Privacy of the image is unclear (some hosts make uploads public regardless of "private" flags).
- Persistence is unclear (free hosts may garbage-collect).
- Don't use for anything sensitive (internal URLs, screenshots of UI showing user data).

## 7. Length guidance

There is no fixed maximum. The right length depends on the change's complexity. Rough guidance:

| Change type | Reasonable body length |
|---|---|
| Doc typo fix | 50-150 lines |
| Single-file bug fix with regression test | 100-300 lines |
| Multi-file feature with tests + screenshots | 300-700 lines |
| Major refactor or new module | 500-1500 lines, with table of contents |

If you're past 700 lines, add a `## Table of Contents` at the top so reviewers can jump.

If you're under 50 lines, double-check you've included all the evidence — short PR bodies often miss the Test Plan section.

## 8. Checklist box evidence

The project's PR template likely has a checklist. Don't just tick the boxes — provide one-line evidence for each:

```markdown
## Checklist
- [x] \`pnpm typecheck\` passes — verified (`tsc --noEmit`, clean)
- [x] \`pnpm format:check\` passes — verified (Prettier, clean)
- [x] \`cargo clippy --all-targets\` passes — verified (no warnings)
- [x] \`cargo fmt --check\` passes — verified
- [x] \`cargo test\` passes — verified (40 lib + 5 integration, 0 failures)
- [x] No user-facing strings added; no i18n updates needed
- [x] Conventional Commits format (\`feat(deeplink): …\`, \`fix(deeplink): …\`)
```

The "— verified (...)" suffix turns a checkbox into a verifiable claim. A reviewer can spot-check any one.
