# Gangtise Copilot — Installation Flow Reference

Deep-dive documentation for `scripts/install_gangtise.sh`. Read this when the installer behaves unexpectedly, when you want to understand why the wrapper downloads 4 archives instead of 19, or when you need to adapt the install flow for a non-standard environment.

## Table of contents

1. [What the installer actually does](#what-the-installer-actually-does)
2. [Why 4 bundles instead of 19 direct downloads](#why-4-bundles-instead-of-19-direct-downloads)
3. [Target agent detection](#target-agent-detection)
4. [Canonical install pattern + symlinks](#canonical-install-pattern--symlinks)
5. [Preset contents](#preset-contents)
6. [Flag reference](#flag-reference)
7. [Idempotency — what happens on re-run](#idempotency--what-happens-on-re-run)
8. [Troubleshooting common install failures](#troubleshooting-common-install-failures)

## What the installer actually does

The installer is a single Bash script that performs these steps in order:

1. **Parse flags** — `--preset`, `--only`, `--target`, `--no-openclaw`.
2. **Prerequisite check** — verifies `curl` and `unzip` are on PATH, fails fast with actionable messages if either is missing.
3. **Detect target agents** — walks `$HOME/.claude`, `$HOME/.openclaw`, `$HOME/.agents` and builds an ordered target list. Honors `--target` and `--no-openclaw` overrides.
4. **Compute required bundle set** — only downloads the bundles that contain at least one skill in the requested list. For example, `--preset minimal` only downloads `gangtise-skills.zip` and skips the other 3 archives entirely.
5. **Download** each required bundle from `https://gts-download.obs.myhuaweicloud.com/skills/<bundle>.zip` into a timestamped staging directory under `/tmp/gangtise-copilot-staging/`. Uses `curl --fail` to surface HTTP errors and a `wc -c` size check to reject suspiciously small downloads (defense against OBS returning a 200 with an HTML error body).
6. **Extract** all bundles into the staging directory. Bundles may deposit skills at the staging root (`gangtise-skills-client.zip` does this) or nested one level deep — the locator function `locate_skill_src` handles both layouts.
7. **Copy each requested skill** from the staging directory into the canonical install location (`$HOME/.local/share/gangtise-copilot/skills/<skill>/`), replacing any existing copy. This is a fresh-each-run copy, not an in-place update — the canonical location is always a faithful mirror of the bundle's current contents.
8. **Create symlinks** in every detected agent's skills directory pointing to the canonical location. Existing non-symlink installs are backed up to `/tmp/gangtise-copilot-backups/<timestamp>/` before being replaced.
9. **Clean up** the staging directory via `trap EXIT`.
10. **Report** which skills were installed, which were skipped (if any), and the next-step commands.

## Why 4 bundles instead of 19 direct downloads

Each skill also exists as a standalone `gangtise-<skill-name>.zip` on the same OBS bucket, so in theory the installer could do 19 direct downloads. It does not, for three reasons:

1. **Two skills are bundle-only.** `gangtise-file-client-no-download` and `gangtise-stockpool-client` do not have standalone ZIPs on the OBS bucket — they are **only** distributed inside `gangtise-skills-client.zip`. A naive "one HTTP request per skill" installer would silently miss them. See `known_issues.md` ISSUE-002 for the discovery story.

2. **4 HTTP requests instead of 19 are faster, more reliable, and easier to retry.** Each additional HTTP request is an additional failure point — network flakiness, OBS throttling, bucket eventual-consistency. Downloading 4 pre-assembled bundles is materially more reliable than downloading 19 independent files, especially over a VPN or a throttled corporate network.

3. **Bundles are the canonical distribution unit.** Gangtise itself maintains `gangtise-skills-client.zip`, `gangtise-research.zip`, and `gangtise-skills.zip` as official aggregate archives. Using them directly means the wrapper never fights with upstream over which-skill-is-in-which-archive — if Gangtise rebalances the bundle contents in a future release, the wrapper picks it up automatically.

The installer computes the minimum bundle set needed to satisfy the `--preset` or `--only` list. A `--preset minimal` install downloads only `gangtise-skills.zip` (3 skills, ~118 KB); a `--preset workshop` install downloads 3 bundles; a full install downloads all 4.

## Target agent detection

The installer walks three candidate directories in order and adds each that exists to its target list:

| Agent | Probe path | Added to target list when |
|---|---|---|
| Claude Code | `$HOME/.claude` | Directory exists |
| Codex | `$HOME/.agents` | Directory exists |
| OpenClaw | `$HOME/.openclaw` OR `openclaw` on PATH | Either condition is true |

**Override flags**:

- `--target <agent>` — install to a single named target, regardless of what's detected. Use this when you have all three agents installed but only want to update one.
- `--no-openclaw` — skip OpenClaw even if detected. Useful when you're maintaining an OpenClaw install separately (e.g., via Gangtise's own installer) and don't want the wrapper to stomp on it.

**Zero-agents fallback**: if none of the three candidates are detected, the installer does not abort. Instead it prints a loud warning naming the paths it looked at and defaults to `claude-code`. Three strategies were considered here:

| Strategy | Behavior | Why rejected |
|---|---|---|
| Abort | Fail with "no target agent found" | Too strict — a user who just installed Claude Code and hasn't restarted their shell hits this and is confused |
| Silent skip | Install nothing, exit 0 | Most surprising behavior; user thinks it worked and then everything is broken |
| **Default to claude-code** ✓ | Install to `~/.claude/skills/` with a warning | Most common case when detection legitimately fails; a loud warning makes it debuggable |

## Canonical install pattern + symlinks

The wrapper uses a **single canonical install + one symlink per agent** layout:

```
~/.local/share/gangtise-copilot/skills/       ← canonical install (real files)
├── gangtise-data-client/
├── gangtise-kb-client/
└── ... (up to 19 skills)

~/.claude/skills/gangtise-data-client         → symlink to canonical
~/.openclaw/skills/gangtise-data-client       → symlink to canonical
~/.agents/skills/gangtise-data-client         → symlink to canonical
```

Benefits:

- **One update, every agent gets it.** When you upgrade a skill (re-run the installer), the canonical location changes and every symlink instantly points at the new version. No per-agent re-install.
- **Credentials propagate automatically.** The shared `.authorization` file (`~/.config/gangtise/authorization.json`) is symlinked from each skill's `scripts/.authorization`. Rotating the credential means editing one file; every skill in every agent picks up the new value on next use.
- **Safer than `cp -r`.** If you re-run the installer with a different `--preset`, the canonical location is rewritten and all symlinks continue to work. A `cp -r`-based install would leave stale copies in each agent's directory.

The canonical root can be overridden with `GANGTISE_COPILOT_HOME` for test isolation:

```bash
GANGTISE_COPILOT_HOME=/tmp/gangtise-test bash install_gangtise.sh
```

## Preset contents

| Preset | Skills | Bundles downloaded | Use case |
|---|---|---|---|
| `full` (default) | All 19 skills (data layer + web + stockpool + file-no-download + 10 research workflows + 3 minimal) | All 4 bundles | Power users, complete catalog demos, future-proof installs |
| `workshop` | data-client, kb-client, file-client, web-client, stock-research, opinion-pk, announcement-digest (7) | skills-client, research, web-client | 2026 Q2 Investor Workshop — Demo 1 (岗底斯日报机器人) + Demo 2 (宁德时代研报时间轴验证) |
| `minimal` | data, file, kb (3, legacy minimal line) | skills | Users who want the smaller footprint and don't need the client-variant's extended capabilities |

Override with `--only` for a custom subset:

```bash
bash install_gangtise.sh --only gangtise-data-client,gangtise-stock-research,gangtise-opinion-pk
```

The `--only` list is taken literally — the installer downloads whichever bundles contain those skills and skips everything else.

## Flag reference

| Flag | Purpose | Default |
|---|---|---|
| `--preset <mode>` | Install preset: `full`, `workshop`, `minimal` | `full` |
| `--only <list>` | Comma-separated skill names. Overrides `--preset`. | none |
| `--target <agent>` | Force single target: `claude-code`, `openclaw`, `codex` | auto-detect all |
| `--no-openclaw` | Skip OpenClaw even if detected | include all detected |
| `--list-skills` | Print the known 19-skill catalog and exit | — |
| `-h` / `--help` | Show usage and exit | — |

## Idempotency — what happens on re-run

Re-running the installer with the same arguments is safe. Every destructive step is guarded:

- **Staging directory** is timestamped + PID-scoped, so concurrent runs don't collide.
- **Canonical install** is rewritten fresh each run — any skill that was previously installed gets replaced, any skill that is no longer in the preset gets left alone (the installer only manages skills it just downloaded).
- **Agent symlinks** use `ln -sfn` which replaces existing links atomically.
- **Non-symlink installations** in agent dirs are backed up to `/tmp/gangtise-copilot-backups/<timestamp>/` before being replaced, not silently deleted.
- **Credential file** is never touched by the installer — that's `configure_auth.sh`'s responsibility.

If you re-run with a smaller preset (e.g., you first ran `--preset full` and now run `--preset workshop`), the extra skills from the first run remain in the canonical location and in the agent directories. The installer only manages skills it's currently installing — it does not remove skills it didn't download this run. To remove skills cleanly, delete the canonical directory and re-run:

```bash
rm -rf ~/.local/share/gangtise-copilot/skills
bash install_gangtise.sh --preset workshop
# Note: agent symlinks to deleted canonical dirs will dangle — diagnose.sh will flag them.
```

## Troubleshooting common install failures

### `Download failed (HTTP 404)`

The OBS bucket layout changed or the bundle was renamed upstream. The installer points at hard-coded bundle names because the OBS LIST permission is disabled — the wrapper can't discover new bundle names automatically. Report the failure as an issue on the gangtise-copilot repo so the bundle list can be updated.

### `Downloaded file is suspiciously small`

OBS returned a "200 OK" with a sub-1KB body. This usually means one of:

- The CDN redirected a yanked-version URL to an HTML error page.
- Huawei Cloud OBS is experiencing an outage.
- Your network is intercepting HTTPS responses (corporate proxy doing TLS inspection).

The installer rejects downloads under 1000 bytes pre-extraction to fail fast here, so you'll see a clear error instead of a confusing `unzip` failure downstream. Retry, and if it persists, check https://status.huaweicloud.com.

### `Could not locate <skill> in downloaded bundles`

This happens when a requested skill name does not appear in any of the downloaded bundles. Causes:

- **Typo in `--only` list.** The installer does not do fuzzy matching — `gangtise-dataclient` (missing hyphen) will not resolve to `gangtise-data-client`. Use `--list-skills` to see the exact names.
- **Skill was moved out of the bundle you expected.** If upstream rebalances `gangtise-skills-client.zip`'s contents, the installer needs updating. Open an issue.

### `No supported agent detected`

None of the three candidate agent directories exist. Most commonly this means Claude Code was just installed and the user hasn't actually opened it yet (the `~/.claude/` directory is created on first launch, not at install time). Open Claude Code once to create the directory, then re-run. Or pass `--target claude-code` to force the install ahead of directory creation.

### Symlink creation fails on macOS System Integrity Protection

If your `$HOME` is on a read-only filesystem or has restricted permissions, the `ln -sfn` may fail. Check the output for "Operation not permitted" — if you see it, run the install with an explicit `--target` and ensure the target agent's `skills/` directory is writable.
