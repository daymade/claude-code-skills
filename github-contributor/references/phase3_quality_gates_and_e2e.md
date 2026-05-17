# Phase 3 — Quality Gates and End-to-End Verification

Detailed playbook for proving your change works before asking a maintainer to trust your word. Covers the automated checks every PR needs, the GUI E2E pattern for desktop apps, and the self-audit step that prevents fabricated test claims.

## 1. Automated checks (every PR)

Run the project's full lint + test suite locally. The exact commands come from CONTRIBUTING.md. Examples from real projects:

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
pnpm test:unit 2>&1 | tee /tmp/test-unit.log
```

### 1.1 If a check fails

Do not push. Fix the failure locally. Common categories:

- **Format failure**: run the formatter (`pnpm format`, `cargo fmt`, `ruff format`). Re-run `--check`.
- **Lint failure**: fix the lint or, if the project allows, add a documented ignore at the call site. Avoid global ignore unless the project's own config does it.
- **Type failure**: fix the type. Avoid `// @ts-ignore`, `// nolint`, `// type: ignore` unless the project uses them elsewhere for the same pattern.
- **Test failure**: if the failing test is one you didn't touch, suspect your change broke something unrelated. Run `git stash && <test command>` to confirm whether `main` is also broken.

### 1.2 If CI runs additional checks the project's CONTRIBUTING.md doesn't list

Inspect `.github/workflows/` for the project's actual CI matrix. Some projects only document the headline checks in CONTRIBUTING.md but enforce additional ones in CI (e.g., integration tests, Docker builds, security scans). Running these locally is optional but increases first-push success.

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

If the project has **no** test hook, the safest path is:

- Back up your real data first (`cp -a ~/.appname ~/.appname.bak`).
- Open an issue suggesting adding a test hook (it costs the maintainer ~5 lines).
- Use a pre-built isolated VM/container if the project provides one (less common).

Never attempt to "just be careful" with your real data. You will eventually clobber it.

### 2.2 Real example: cc-switch

cc-switch hardcodes its data directory but provides `CC_SWITCH_TEST_HOME`:

```rust
// src-tauri/src/config.rs (paraphrased)
pub fn get_home_dir() -> PathBuf {
    if let Ok(home) = std::env::var("CC_SWITCH_TEST_HOME") {
        let trimmed = home.trim();
        if !trimmed.is_empty() {
            return PathBuf::from(trimmed);
        }
    }
    dirs::home_dir().unwrap_or_default()
}
```

Usage:

```bash
mkdir -p /tmp/cc-switch-e2e/.cc-switch
CC_SWITCH_TEST_HOME=/tmp/cc-switch-e2e pnpm tauri dev
```

The dev binary now reads/writes `/tmp/cc-switch-e2e/.cc-switch/cc-switch.db`, never touching `~/.cc-switch/`.

Confirm isolation worked by reading the dev log on startup:

```
[INFO] MCP table empty, importing from live configurations...
[INFO] Prompts table empty, importing from live configurations...
[INFO] No Claude MCP servers found to import
```

These "empty" / "no servers found" messages indicate a fresh database. If you see "imported 47 sessions from existing data", isolation failed — kill the binary and investigate.

## 3. Triggering features without polluting the system

For URL-scheme features (deeplinks), the temptation is to type `open ccswitch://...` in the terminal. **Do not** — macOS LaunchServices routes the URL to the installed `.app`, not your dev binary. You'll modify your real user data.

### 3.1 Tauri 2 single-instance forward

Tauri 2's `single_instance` plugin lets you re-launch the binary with the URL as `argv[1]`. The running dev instance receives the URL through its `single_instance` callback:

```bash
CC_SWITCH_TEST_HOME=/tmp/cc-switch-e2e \
  ./src-tauri/target/debug/cc-switch "ccswitch://v1/import?resource=provider&app=claude&..."
```

This bypasses LaunchServices entirely and routes the URL to your specific dev binary instance.

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

To get the window ID for your dev app:

```bash
osascript -e 'tell application "System Events" to get id of front window of (first process whose name is "<app-name>")'
```

### 5.2 Bring the app to the front before capturing

```bash
osascript -e 'tell application "System Events" to set frontmost of (first process whose name is "<app-name>") to true'
```

In some setups osascript focus calls are unreliable (the terminal can steal focus back). A more reliable trigger is the app's own focus call — e.g., for cc-switch, re-running the binary triggers the single-instance callback which calls `window.set_focus()` internally.

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
- "No production data was touched" → evidence: I used CC_SWITCH_TEST_HOME the entire time
- "Screenshot 1: import dialog" → evidence: /tmp/e2e/screenshot_1_import_dialog.png
- "Screenshot 2: env block" → evidence: /tmp/e2e/screenshot_2_env_block.png
```

For each claim, can you produce the evidence in 5 seconds? If not, the claim is at risk of being fabrication. Either run the test now or remove the claim from the PR body.

**Why this matters**: the single fastest way to lose maintainer trust is to claim something you didn't actually do, and have the maintainer try to reproduce it. Maintainers have long memories about contributors who waste their time.

This is also why screenshots are valuable — they're evidence the GUI behavior you describe actually exists. Prose alone is not evidence.
