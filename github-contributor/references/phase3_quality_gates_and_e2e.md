# Phase 3 — Quality Gates and End-to-End Verification

Detailed playbook for proving your change works before asking a maintainer to trust your word. Covers the automated checks every PR needs, the GUI E2E pattern for desktop apps, and the self-audit step that prevents fabricated test claims.

## 1. Automated checks (every PR)

Read CONTRIBUTING.md and the current CI workflow for the required commands and matrix. Bind results to the tested commit/tree and environment. Reuse successful checks on unchanged inputs rather than repeating the same suite locally after exact-content CI passed. Run missing or affected checks after a change. Examples from real projects:

```bash
# Node / TypeScript projects
pnpm typecheck
pnpm format:check
pnpm lint
pnpm test:unit

# Rust projects
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test

# Python projects
ruff check .
ruff format --check
pytest

# Go projects
gofmt -l .
go vet ./...
go test ./...
```

Run each command individually and **capture the output**. If a command takes more than ~30 seconds, save the output to a file so you can paste it into the PR body later:

```bash
set -o pipefail
pnpm test:unit 2>&1 | tee /tmp/test-unit.log
```

### 1.1 If a check fails

Preserve the command, exit status and first relevant error. Establish whether the failure is introduced by this PR before choosing the repair. Common categories:

- **Format failure**: run the formatter (`pnpm format`, `cargo fmt`, `ruff format`). Re-run `--check`.
- **Lint failure**: fix the lint or, if the project allows, add a documented ignore at the call site. Avoid global ignore unless the project's own config does it.
- **Type failure**: fix the type. Avoid `// @ts-ignore`, `// nolint`, `// type: ignore` unless the project uses them elsewhere for the same pattern.
- **Test failure**: run the same command on the immutable current-base commit in a separate worktree, with the same relevant environment. Do not stash, reset or switch a shared checkout to manufacture the control. If a port is held by another session, identify its owner and keep it running; use an authorized isolated runner. Record base failures and environment blocks separately from PR regressions.

### 1.2 If CI runs additional checks the project's CONTRIBUTING.md doesn't list

Inspect `.github/workflows/` for the project's actual CI matrix. Its required integration tests, builds and platform checks still need evidence even when CONTRIBUTING.md lists only headline checks. A fork run on the exact head supplies separate evidence; it does not turn upstream `action_required` or pending review into approval.

## 2. The isolated-home pattern for desktop apps

Desktop apps (Tauri, Electron, Cocoa, Qt, GTK) almost always read configuration and data from a fixed location like `~/.appname/` or `~/Library/Application Support/com.app.id/`. Running the dev binary will read **your real user data**.

The pattern:

1. **Find the project's test hook** that overrides the data directory.
2. **Point the test hook at `/tmp/`** before launching the dev binary.
3. **Trigger the feature** through whatever real interface a user would use.
4. **Verify by reading the persisted state directly** (SQLite, JSON files), not just by visual inspection.

### 2.1 Finding the test hook

Common naming patterns:

- `<APPNAME>_TEST_HOME`, `<APPNAME>_DATA_DIR`, `<APPNAME>_CONFIG_DIR`
- `XDG_DATA_HOME`, `XDG_CONFIG_HOME` (Linux-style, sometimes honored on macOS too)
- A config file flag (`--data-dir=`, `--profile=`)

Grep for the candidate names in the project's source:

```bash
rg -i 'TEST_HOME|TEST_DIR|test_home|test_dir|DATA_DIR' --type rust --type ts
rg 'env::var\(' src-tauri/  # Rust: env reads
rg 'process\.env\.' src/    # Node: env reads
```

If you find a function like `get_home_dir()` that reads an environment variable as an override, that's your hook.

If the project has **no** test hook, use an already authorized isolated VM/container
and verify its consumer-data paths before input. A backup does not isolate a test
from production data. Propose an isolation hook only within the contribution's scope.

Never attempt to "just be careful" with your real data. You will eventually clobber it.

### 2.2 Real example: cc-switch

For cc-switch, inspect `src-tauri/src/config.rs` in the tested commit for
`CC_SWITCH_TEST_HOME` and its current path-resolution behavior. Use the executable
implementation rather than a copied resolver as the isolation authority.

Usage:

```bash
mkdir -p /tmp/cc-switch-e2e/.cc-switch
CC_SWITCH_TEST_HOME=/tmp/cc-switch-e2e pnpm tauri dev
```

Before input, identify the binary, bundle and PID, then derive and verify its effective database and consumer-data paths from the tested resolver. A home override alone does not prove the effective application-data path. Give the test bundle a separate identity so an existing production instance cannot receive its single-instance messages.

Fresh-start logs can corroborate isolation:

```
[INFO] MCP table empty, importing from live configurations...
[INFO] Prompts table empty, importing from live configurations...
[INFO] No Claude MCP servers found to import
```

These messages prove neither which instance received input nor which paths it uses; a real installation may also be empty. Unexpected imported data is a reason to stop input and inspect the exact instance and paths. Quit only the task-owned test instance through its normal lifecycle; never terminate a name-matched production process.

## 3. Triggering features without polluting the system

For URL-scheme features (deeplinks), the temptation is to type `open ccswitch://...` in the terminal. **Do not** — macOS LaunchServices routes the URL to the installed `.app`, not your dev binary. You'll modify your real user data.

### 3.1 Tauri 2 single-instance forward

Tauri 2's `single_instance` plugin lets you re-launch the binary with the URL as `argv[1]`. The running dev instance receives the URL through its `single_instance` callback:

```bash
CC_SWITCH_TEST_HOME=/tmp/cc-switch-e2e \
  ./src-tauri/target/debug/cc-switch "ccswitch://v1/import?resource=provider&app=claude&..."
```

This avoids LaunchServices. Verify the single-instance scope and receiving PID/data path from the current implementation and logs; the binary path alone does not prove which running instance received the URL.

Watch the dev log for confirmation:

```
[INFO] === Single Instance Callback Triggered ===
[INFO] ✓ Deep link URL detected from single_instance args: <url>
[INFO] ✓ Successfully parsed deep link: <details>
```

### 3.2 Generalizing the pattern to other stacks

| Stack | Pattern |
|---|---|
| Electron | App's `second-instance` event handler receives the URL when re-launched with `--args="url"` |
| Cocoa | Send `GURL` Apple Event via `osascript -e 'tell application id "<bundle-id>" to open location "<url>"'` (works only for installed bundles, not bare dev binaries) |
| Linux Qt | Use the project's IPC channel directly (often a Unix socket), or restart with the URL as `argv[1]` if the app supports single-instance |

If the project doesn't have a test-friendly trigger mechanism, file an issue suggesting one (or contribute it as your first PR before the feature PR).

## 4. Direct state verification

Visual inspection of the GUI is necessary but not sufficient. Read the persisted state directly:

### 4.1 SQLite

```bash
sqlite3 /tmp/<isolated-data-dir>/<db-file> ".tables"
sqlite3 /tmp/<isolated-data-dir>/<db-file> "SELECT * FROM <table> WHERE name='<test-record>'"
```

For complex blob columns (JSON in SQLite), pipe through `python3 -c 'import json,sys; print(json.dumps(json.loads(sys.stdin.read()), indent=2))'`.

### 4.2 JSON / TOML / plain files

```bash
cat /tmp/<isolated-data-dir>/settings.json | jq .
```

### 4.3 Verification matrix

For non-trivial changes, build a table of expected vs. actual for every behavior your change affects. Example from cc-switch PR #2634:

| Behavior | Expected | Actual | Pass |
|---|---|---|---|
| `null`-valued protected key | Dropped | Dropped | ✅ |
| Number-valued normal key | Stringified | "30" | ✅ |
| Bool-valued normal key | Stringified | "true" | ✅ |
| Object-valued key | Dropped | Dropped | ✅ |
| String-valued protected key with valid URL | Preserved | Preserved | ✅ |

Paste this matrix into the PR description. It's denser and more verifiable than prose.

## 5. Capturing GUI screenshots

For the PR's "Screenshots" section, capture only what's relevant to your change. Don't paste full-screen screenshots — they contain noise.

### 5.1 macOS

```bash
# Full-screen capture
screencapture -x /tmp/screenshot.png

# Single window (interactive selection)
screencapture -W /tmp/screenshot.png

# Specific area (interactive selection)
screencapture -s /tmp/screenshot.png

# Specific window ID (no interaction)
screencapture -l <window-id> /tmp/screenshot.png
```

Use `daymade-macos:capture-screen` to obtain the Quartz window ID. Match its owner PID
to the verified test executable before using `screencapture -l`; an AX element/index
or application display name is not a Quartz window ID.

### 5.2 Verify target and focus before input

Check user activity and coordinate exclusive access before any foreground action,
within the task's existing authorization. A visible screenshot or successful
activation call does not prove keyboard focus. With multiple copies, bind every
action to the test PID, bundle and executable; do not select the first same-named process.

For macOS local native acceptance, use `macos-app-developer:developing-macos-apps`
and its local-native-acceptance reference when available. It owns the PID-bound
semantic AX recipe. If unavailable, retain the unverified step rather than assume
a driver exists. Prefer a named control action over a global Return; observe the
rendered transition and resulting file/database independently. A blocked action
does not authorize changing tools to evade its restriction.

Inside an authorized foreground interval, the app's own focus path may help: for
cc-switch, re-running the same isolated binary invokes `single_instance` and
`window.set_focus()`. Verify the receiver and actual frontmost PID afterward.

### 5.3 Crop after capturing

Use Python + Pillow to crop noise out of full-screen captures:

```python
from PIL import Image
img = Image.open('/tmp/screenshot.png')
# Detect content bounds by finding white-ish pixels (the app window)
crop = img.crop((<left>, <top>, <right>, <bottom>))
crop.save('/tmp/screenshot_cropped.png', optimize=True)
```

Aim for tight crops that show one piece of UI clearly. A reviewer should be able to understand the screenshot in 2 seconds.

## 6. Self-audit: did you actually do everything you're about to claim?

Before writing the PR description, list every claim you intend to make:

```
Claims I plan to make in the PR body:
- "All unit tests pass" → evidence: `pnpm test:unit` output in /tmp/test-unit.log
- "Lint clean" → evidence: `cargo clippy --all-targets` exited 0
- "Tested end-to-end with isolated home" → evidence: dev log + SQLite dump in /tmp/cc-switch-e2e/
- "Test actions targeted isolated data" → evidence: exact receiving PID/bundle/executable and resolved paths, plus isolated file/database readback
- "Screenshot 1: import dialog" → evidence: /tmp/e2e/screenshot_1_import_dialog.png
- "Screenshot 2: env block" → evidence: /tmp/e2e/screenshot_2_env_block.png
```

For each claim, can you produce the evidence in 5 seconds? If not, the claim is at risk of being fabrication. Either run the test now or remove the claim from the PR body.

**Why this matters**: the single fastest way to lose maintainer trust is to claim something you didn't actually do, and have the maintainer try to reproduce it. Maintainers have long memories about contributors who waste their time.

This is also why screenshots are valuable — they're evidence the GUI behavior you describe actually exists. Prose alone is not evidence.
