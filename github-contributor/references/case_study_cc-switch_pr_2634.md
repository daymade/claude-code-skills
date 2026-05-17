# Case Study: cc-switch PR #2634 (extraEnv support for deeplinks)

A complete walk-through of a real PR submitted to `farion1231/cc-switch` (a Tauri + React desktop app for switching Claude/Codex/Gemini providers). The PR adds an `extraEnv` parameter to the project's `ccswitch://` deeplink import flow, allowing distributors to ship UI-toggle settings inside the deeplink URL.

This case is preserved as a reference because it touches every phase of the playbook and includes failure modes that the rest of the skill explicitly warns against (fabrication near-miss, scope creep at rebase time, isolated GUI E2E with hardcoded paths).

PR URL: https://github.com/farion1231/cc-switch/pull/2634

## Phase 1 findings that shaped the PR

### CONTRIBUTING.md AI-Assisted clause (most important finding)

The project's `CONTRIBUTING.md` ends with a five-rule AI-Assisted Contributions section. Verbatim summary:

1. You have read and understood your code. You must be able to explain any line.
2. You have tested it yourself. No "looks right".
3. One issue, one PR. Sprawling multi-topic PRs are closed.
4. Open an issue first. Drive-by PRs may be closed.
5. Maintainers may close without explanation. Hallucinated fixes, unnecessary refactors, bulk changes get closed.

Discovering this clause changed the entire PR-writing approach: every claim had to be specifically verifiable, the disclosure block became non-optional, and any temptation to "while I'm here" refactor had to be resisted.

### PR-size baseline check

```bash
gh pr list --repo farion1231/cc-switch --state merged --limit 10 \
  --json number,title,additions,deletions
```

Output (the 10 most recently merged PRs at the time):

| PR | Type | +/- lines |
|---|---|---|
| #2590 | fix | +190/-4 |
| #2543 | feat | +104/-8 |
| #2520 | chore (deps) | +1/-1 |
| #2502 | fix | +7/-1 |
| #2493 | fix | +125/-6 |
| #2485 | fix (proxy) | +60/-20 |
| #2473 | fix (log) | +6/-6 |

Largest recent merge was `+190/-4`. Our PR ended at `+1103/-26`. That's roughly 5–10× the project's normal merge size — a red signal we acknowledged in the PR body upfront and offered to split if the maintainer preferred.

## Phase 2 implementation choices

### Scope contract

> Goal: support a Base64-encoded JSON `extraEnv` parameter in `ccswitch://` deeplinks for Claude and Gemini providers, so distributors can pre-set environment variables that are otherwise UI-only.
>
> In scope: parsing the new query param; merging values into `settings_config.env`; validation/sanitization of injected keys; unit + integration tests; demo update; CHANGELOG entry.
>
> Explicitly out of scope: changing the deeplink scheme; touching providers other than Claude/Gemini; refactoring the existing deeplink parser; UI changes beyond the demo HTML page.

### Two-commit structure

The PR landed as exactly two commits, separated by Codex's automated review:

1. `feat(deeplink): support extraEnv parameter for provider configuration` — added the parameter, merge logic, four tests.
2. `fix(deeplink): harden extraEnv import behavior` — addressed Codex's P1+P2 review findings (described below). The second commit also picked up a small unrelated `code-simplifier` cleanup; this almost violated the scope contract and should have been split out — see "Lessons" below.

### Rebase-time conflict

While the PR was open, upstream `main` landed a separate "ClaudeDesktop provider" feature that touched the same `provider.rs` file. The rebase produced two conflicts in `build_provider_from_request`:

- An import line (`use crate::provider::...`) had grown a new symbol upstream.
- A `match app_type` block had grown a new `ClaudeDesktop` arm upstream.

The conflict was resolved by extending our `extraEnv` support to also cover `ClaudeDesktop` (since the two providers share the same `build_claude_settings` function). This was technically scope creep — the original scope contract said "Claude and Gemini" — but was unavoidable given the file-level overlap. The PR description was updated to acknowledge the additional coverage.

**Lesson**: when rebase forces scope extension, declare it in the PR body. Don't let the maintainer discover it.

## Phase 3 — Isolated GUI end-to-end verification

This is the part the rest of the playbook references most often, because cc-switch hardcodes its data directory:

```rust
// src-tauri/src/config.rs:95
let default_dir = get_home_dir().join(".cc-switch");
```

Changing the Tauri `identifier` or `CFBundleURLSchemes` is therefore **not** enough to isolate from production data. The project does, however, provide a test hook:

```rust
// src-tauri/src/config.rs:23
pub fn get_home_dir() -> PathBuf {
    if let Ok(home) = std::env::var("CC_SWITCH_TEST_HOME") {
        let trimmed = home.trim();
        if !trimmed.is_empty() {
            return PathBuf::from(trimmed);
        }
    }
    dirs::home_dir().unwrap_or_else(|| { ... })
}
```

### Isolation recipe

```bash
# 1. Pre-emptive backup in case anything leaks
cp -a ~/.cc-switch ~/.cc-switch.backup-pre-e2e-$(date +%s)

# 2. Build the dev binary (one-time)
pnpm tauri dev &
# (kill the auto-launched window; we just want the binary built)
pkill -f 'tauri dev'

# 3. Re-launch with isolated home
mkdir -p /tmp/cc-switch-e2e/.cc-switch
CC_SWITCH_TEST_HOME=/tmp/cc-switch-e2e pnpm tauri dev &

# 4. Trigger the deeplink via single-instance forward (does NOT use macOS LaunchServices)
CC_SWITCH_TEST_HOME=/tmp/cc-switch-e2e \
  ./src-tauri/target/debug/cc-switch "ccswitch://v1/import?resource=provider&app=claude&..."
```

The fourth step is the part that bypasses macOS scheme handler registration. Tauri 2 ships a `single_instance` plugin: when you launch the binary a second time with a URL as `argv[1]`, the running instance receives it through the single-instance callback. This is the cleanest way to test deeplinks on dev binaries (which aren't real `.app` bundles and therefore can't register URL schemes).

### Verification matrix actually run

The test payload had 10 `extraEnv` keys, four of which were designed to trigger Codex's P1/P2 hardening:

| Key | Value | Expected behavior |
|---|---|---|
| `ANTHROPIC_AUTH_TOKEN` | `null` | dropped — protected env field must be non-empty string |
| `CLAUDE_CODE_TIMEOUT_SECONDS` | `30` (number) | stringified to `"30"` |
| `CLAUDE_CODE_DEBUG_MODE` | `true` (bool) | stringified to `"true"` |
| `CLAUDE_CODE_BAD_OBJECT` | `{nested: "value"}` | dropped — arrays/objects not valid env values |
| (other 6 strings) | various | preserved |

### Real dev-log captured (redacted)

```
[INFO] === Single Instance Callback Triggered ===
[INFO] ✓ Deep link URL detected from single_instance args: ccswitch://v1/import?[keys:apiKey,app,enabled,endpoint,extraEnv,model,name,resource]
[INFO] ✓ Successfully parsed deep link: resource=provider, app=Some("claude"), name=Some("e2e-test-extraenv")
[INFO] ✓ Emitted deeplink-import event to frontend
[INFO] Importing provider resource from deep link
[WARN] Skipping extra_env key 'ANTHROPIC_AUTH_TOKEN': protected env fields must be non-empty strings
[WARN] Skipping extra_env key 'CLAUDE_CODE_BAD_OBJECT': arrays/objects are not valid env values
[INFO] Provider 'e2e-test-extraenv-1778611889499' set as current for Claude
```

### SQLite verification

After import, query the isolated database directly:

```bash
sqlite3 /tmp/cc-switch-e2e/.cc-switch/cc-switch.db \
  "SELECT settings_config FROM providers WHERE name='e2e-test-extraenv'" | \
  python3 -c "import json,sys; print(json.dumps(json.loads(sys.stdin.read()), indent=2))"
```

Result confirmed all 11 expected behaviors (6 strings preserved, 2 scalars stringified, `null`-override dropped, object dropped).

### Cleanup

```bash
pkill -f 'target/debug/cc-switch'
git checkout HEAD -- src-tauri/tauri.conf.json src-tauri/Info.plist  # in case configs were touched
rm -rf /tmp/cc-switch-e2e
# Keep the backup ~/.cc-switch.backup-pre-e2e-* for a few days, then delete
```

## Phase 4 — PR description structure used

The actual body that was submitted (paraphrased headers):

```
## Summary / 概述
## What / 变更内容          ← two commits with their roles
## Why / 动机
## Test Plan / 测试计划      ← coverage matrix of 21 tests
## How to verify locally    ← exact reproducible commands
## Backward Compatibility / 向后兼容
## Security Considerations  ← references Codex P1/P2 findings + how they were fixed
## Screenshots / 截图        ← with placeholder text the user replaced via drag-and-drop
## Related Issue            ← "no prior issue; happy to retro-file if preferred"
## Checklist / 检查清单      ← each box with actual evidence
## AI-Assisted Disclosure
```

The description landed at roughly 600 lines including evidence and matrices. This is large relative to the production diff but defensible because most of it is **evidence**, not narration.

## Phase 5 — Bot review handling

Codex left two review comments on the first commit:

- P1: `ANTHROPIC_AUTH_TOKEN` could be overwritten by `extraEnv` with `null`/non-string.
- P2: `merge_extra_env` should validate value types.

Both were addressed in commit 2 (`fix(deeplink): harden extraEnv import behavior`). Replies were posted directly under each finding via the GitHub API:

```bash
gh api repos/farion1231/cc-switch/pulls/2634/comments \
  -X POST \
  -F in_reply_to=3225389962 \
  -f body="Addressed in commit \`bade3de1\`: \`is_protected_env_key\` now blocks non-string overrides of protected keys. \`normalize_extra_env_value\` enforces the type discipline. Regression locked in by \`test_extra_env_stringifies_scalars_and_skips_invalid_values\`. Thanks for the catch!"
```

Replying as a comment (not in PR body) means the resolution appears next to the finding for any future reviewer.

## Lessons that became skill rules

1. **CONTRIBUTING.md `AI-Assisted` clauses are merge gates** — they shaped the entire PR strategy.
2. **PR size sanity check** before submission catches "too big" before the maintainer has to point it out.
3. **Isolated GUI E2E with the project's own test hook** beats trying to override `identifier` / scheme.
4. **Fabrication near-miss**: the first draft of the PR body said "tested with `pnpm dev` and `deplink.html` flow" — but the manual GUI flow had not actually been run yet. Caught during self-audit; rewritten to list only what was real. This is now a Phase 3 rule.
5. **Rebase-time scope creep should be acknowledged** in the body, not hidden.
6. **Bot reply via `gh api in_reply_to`** keeps the resolution next to the finding.
7. **Screenshot placeholders > image hosting hacks**. The clean path is to leave `[SCREENSHOT_N_PLACEHOLDER]` in the PR body and let the user drag images into the GitHub web editor.
8. **`code-simplifier` cleanups should be a separate commit** (or a separate PR) — bundling them into a fix commit makes review harder and risks scope creep.
9. **`--force-with-lease`, never plain `--force`** — review threads are too easy to destroy.
10. **Self-audit "what's my evidence?" pass** before publishing the PR body catches fabrication-by-default.
