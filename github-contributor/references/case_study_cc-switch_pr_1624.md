# Case Study: cc-switch PR #1624 (protect conversation history)

A companion to the PR #2634 case study. This PR adds a "keep conversation history" setting to `farion1231/cc-switch` that, when enabled, applies transcript-protection settings in Claude's `settings_config.json`. Like PR #2634, it required a long rebase to stay merge-ready; unlike #2634, the hardest problems were in frontend state management and test coupling rather than in Rust parsing.

PR URL: https://github.com/farion1231/cc-switch/pull/1624

## Phase 1 — Scope and baseline

The project's `CONTRIBUTING.md` AI-Assisted clause applied (same five rules as PR #2634). The PR-size baseline was already known from PR #2634; this change was intentionally smaller (+~300/-~50 lines), mostly TypeScript and two small Rust commands.

## Phase 2 — Implementation notes

### Scope contract

> Goal: add a UI toggle that protects or unprotects Claude conversation history by writing/removing `cleanupPeriod: 99999` in `~/.claude/settings.json`.
>
> In scope: the settings toggle, Tauri commands to read/apply/clear protection, frontend state sync, i18n strings.
>
> Explicitly out of scope: changing the default cleanup period for new users; migrating existing history; UI beyond the settings dialog.

### Two-language split

The feature touches both Rust backend commands and React frontend state:

- Rust (`src-tauri/src/claude_mcp.rs`, `src-tauri/src/commands/plugin.rs`) adds `get_cleanup_period_days`, `set_cleanup_period_days`, `clear_cleanup_period_days` and wraps them as Tauri invoke handlers.
- Frontend (`src/hooks/useSettingsForm.ts`, `src/hooks/useSettings.ts`) adds the toggle and syncs it with the actual persisted `settings.json` state.

This split is common in Tauri/Electron apps. The merge gate is that **both sides must stay consistent**: if the UI shows "protected" but `settings.json` says otherwise, the user will lose trust in the toggle.

## Phase 3 — Quality gates and frontend-specific failures

### Clippy

Two `unnecessary_map_or` warnings appeared after the rebase:

```rust
// Before
.map_or(false, |d| d == 99999)
.map_or(false, |days| days > 365)

// After
== Some(99999)
.is_some_and(|days| days > 365)
```

These are small but worth fixing because maintainers notice red CI more than they notice code style.

### React race condition: async init vs. user toggle

`useSettingsForm` loads server settings via React Query, then asynchronously reads the real transcript-protection state from `~/.claude/settings.json`. If the user toggles the switch before that async read returns, the async result must not overwrite the user's explicit choice.

The fix uses two refs:

1. `hasSyncedTranscriptProtectionRef` — ensures the async read happens only once (on initial data load), not on every refetch.
2. `userTouchedTranscriptRef` — if the user has manually changed the toggle, the async result is ignored.

This pattern generalizes: **any async initialization that can return after user interaction needs a "user touched" guard**.

### Test coupling after refactoring

`useSettings.ts` was refactored to extract a shared `syncTranscriptProtection` helper used by both auto-save and explicit save. After the refactor, three SettingsDialog tests failed because the helper called `settingsApi.applyTranscriptProtection()` / `clearTranscriptProtection()` on every save, but the tests only mocked `settingsApi.save()`.

The fix was not to add more mocks. It was to make the helper compare the new value against the **last known persisted value** and only call the protection API when the value actually changed:

```ts
const baseline = lastSyncedKeepConversationHistoryRef.current ?? persistedValue;
if (baseline === nextValue) return;
```

This made the tests pass because most test cases did not change the toggle, so the API was never invoked. More importantly, it made the production behavior correct: no spurious writes to `settings.json`.

**Lesson**: when a refactor breaks tests, first ask whether the refactor introduced unnecessary side effects. Fixing the side effect is usually better than adding mocks.

### i18n conflict resolution

Upstream had added a new "Codex Auth" section to the locale files while the PR added a "keepConversationHistory" section. The rebase conflict was resolved by keeping **both** blocks in the correct order. This is the standard resolution for unrelated additions to the same file: preserve both, in the order the file uses.

## Phase 5 — Post-submission maintenance

The PR sat long enough that upstream `main` advanced. The rebase conflicts were in:

- `src/hooks/useSettingsForm.ts` — upstream added new Codex settings that had to coexist with `keepConversationHistory`.
- `src/i18n/locales/*.json` — upstream added the Codex Auth section.
- `src-tauri/src/deeplink/provider.rs` — upstream refactored Claude env extraction; the transcript-protection PR did not touch this, but a parallel PR (#2634) did, so the combined working tree needed both to compile.

After resolving, the full suite was re-run:

```bash
pnpm typecheck && pnpm test:unit
cargo clippy --all-targets && cargo test
```

## Lessons that became skill rules

1. **Async initialization needs a "user touched" guard** to prevent late-arriving state from overwriting user input.
2. **Refactor-induced test failures often signal a real bug** — prefer removing the spurious side effect over adding mocks.
3. **i18n conflicts from unrelated additions** resolve by keeping both blocks in file order.
4. **Re-run the full suite after every rebase**, even when the conflicts are "just" in TypeScript locale files.
5. **Multi-language PRs** must keep frontend state and backend persisted state consistent; the bug usually appears at the boundary.
