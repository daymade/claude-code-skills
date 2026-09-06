# Common Issues and Fixes

## Profile fails to launch

Check that `~/.claude/settings/<profile>.json` exists and is valid JSON:

```bash
python3 -m json.tool ~/.claude/settings/kimi.json
```

Also check that the profile directory has `.claude.json`:

```bash
test -f ~/.claude-profiles/kimi/.claude.json
```

`claude.json` is a legacy filename and is not enough for modern Claude Code when `CLAUDE_CONFIG_DIR` points at the profile directory. Re-run `claude-profiles-init` to create missing `.claude.json` files.

## Doctor reports a broken symlink such as `image-cache`

Run:

```bash
claude-profiles-init
```

Profile symlinks intentionally point back into `~/.claude`. Claude Code may create optional runtime directories such as `image-cache/` and later remove them. Current `claude-profiles-init` prunes stale symlinks whose target was under `~/.claude`, then rebuilds the links that still have a real base directory.

## `claude-profile` command not found

The shell function is loaded by sourcing `claude-profiles.sh`. Either:
- Run `source ~/.config/claude-switch-models-setup/claude-profiles.sh`, or
- Open a new terminal so the rc-file source takes effect.

## Third-party model gets Anthropic errors

Make sure the profile's `env` block includes:
```json
{
  "ENABLE_TOOL_SEARCH": "false",
  "DISABLE_GROWTHBOOK": "1",
  "DISABLE_TELEMETRY": "1",
  "DISABLE_AUTOUPDATER": "1"
}
```

These flags prevent Claude Code from trying Anthropic-only features when talking to a third-party endpoint.

Related boundary: `advisorModel` (a top-level settings.json key holding an
Anthropic model name like `"fable"`) is in the converger's DENYLIST alongside
`model` — third-party endpoints cannot serve that literal, so it is treated
as provider identity and never synced. If a profile's settings.json still
carries `advisorModel` from before 2026-08-18 (when it was synced by
mistake), delete the key from that profile's settings.json.

## Subagents use the wrong model

Set `CLAUDE_CODE_SUBAGENT_MODEL` to the same value as `ANTHROPIC_MODEL` in the profile settings. Otherwise subagents may fall back to the default Anthropic model.

## The advisor answers on the same model as the session

Symptom: the session runs on the flagship tier and every advisor call comes
back from that same model — each advisor record in the session JSONL carries
an `advisorModel` equal to the session's `model` string (observed 2026-09-05
on a `claude-fable-5-1` session) — and it looks as if the pairing is
misconfigured.

Cause: an equal pair is allowed and nothing announces it. `advisorModel` is
its own setting; `/model` rewrites `model` and leaves it alone (observed
2026-09-05). The pairing check rejects an advisor that is *less* capable than
the main model or one the main model does not support — those are the only
two `/advisor` warnings in the 2.1.260 binary — so raising the main model to
the advisor's tier silently turns the advisor into a same-model second read.
It still gets the whole transcript as a separate call; it just brings no
stronger reasoning.

Fix — pick one:

- Pin a different advisor: `/advisor <model>`. **It writes the top-level
  `advisorModel` key into the global `~/.claude/settings.json`**, not the
  project's `.claude/settings.json` (observed 2026-08-13: run inside one
  project checkout, the key appeared in the global file), so the choice
  follows every project — and, as a DENYLIST key, reaches no third-party
  profile.
- Turn it off: `/advisor off` removes that key from the same global file
  (observed 2026-09-05: run inside another project, the global file's mtime
  matched the command to the second and the key was gone). It takes effect
  in the session that ran it and in every session started afterwards — that
  session made no further advisor calls, and later sessions on the same
  model carry no `advisorModel` on any record — but a *different* session
  that was already running kept calling the advisor (all observed
  2026-09-05). Restart those windows if the `off` must reach them.
  `CLAUDE_CODE_DISABLE_ADVISOR_TOOL` also exists in the 2.1.260 binary; it
  has not been exercised here.

Which model answered a given call is on the assistant record itself
(`advisorModel`, next to `effort`) — see
`read-claude-code-history/references/session_file_format.md`.

## Marketplace says "corrupted installLocation"

Each profile needs its OWN `known_marketplaces.json` — its `installLocation` is
config-dir-specific (Claude validates with `path.resolve`, which does NOT resolve
symlinks), so it cannot be shared across profiles. `claude-plugins-sync.py` rebuilds them.
It runs automatically every time `claude-profile` init/launches; to run manually:

```bash
python3 ~/.config/claude-switch-models-setup/claude-plugins-sync.py
```

## Skill is installed in default Claude but missing in a third-party profile

Claude Code stores the enabled plugin map in each config directory's `settings.json`.
Run the profile syncer so every profile mirrors the default profile's `enabledPlugins`:

```bash
python3 ~/.config/claude-switch-models-setup/claude-plugins-sync.py
```

This file-level fix also happens automatically, usually within seconds, when
the `ai.daymade.claude-skill-source-sync` LaunchAgent is installed (see "Local
skill source changes do not appear in Claude Code or Codex" below) — `claude
plugin enable/disable --scope user` writes to `~/.claude/settings.json`, which
is itself a watched path, and the watcher's sync pass calls this same script.
Run the command above manually when the watcher is not installed, or to force
convergence without waiting (verified 2026-08-22: `launchctl`'s per-agent run
counter incremented within 5s of a bare `touch` on the watched file).

Restart the affected Claude Code window after syncing — a running session
does not re-read `enabledPlugins` mid-session, whether the file was synced by
hand or by the watcher.

## Default-profile behavior settings don't reach third-party profiles

Symptom: a behavior preference set on the default profile has no effect in
third-party profiles — e.g. a workflow launched in a Kimi window fans out far
beyond the size guideline you configured on the default profile.

Cause: those settings do not live in `settings.json`. Claude Code keeps a
second per-profile file, and its path is **asymmetric** (verified on disk
2026-08-17): the main profile's is `~/.claude.json` (a sibling of the config
dir), while each third-party profile's is `~/.claude-profiles/<name>/.claude.json`
(inside the config dir). A stale pre-migration copy at `~/.claude/.claude.json`
is not the live file. Nothing in the symlink layout or the settings.json sync
covers this layer, so a key like `workflowSizeGuideline` set on main silently
exists on zero third-party profiles.

Incident that established this (2026-08-17): `workflowSizeGuideline: small`
was set on the default profile; 10/11 third-party profiles had no copy of the
key at all. A Kimi session launched a Dynamic Workflow whose system prompt
therefore contained no size guidance, and fanned out to 30+ agents. Hooks and
every other `settings.json` key were fully converged at the time — the drift
was exclusively in this second layer, invisible to the old sync.

Fix: `sync-profile-settings.py` (2026-08-17 onward) converges an allowlist of
confirmed behavior keys (`BEHAVIOR_KEYS` in the script) into each profile's
`.claude.json` at session start. Manual re-convergence:

```bash
python3 ~/.config/claude-switch-models-setup/sync-profile-settings.py --all
```

Restart the affected window — the harness reads `.claude.json` at startup, so
a sync never changes the running session.

Corrupt files on either layer: a corrupt profile `settings.json` or
`.claude.json` is rebuilt from main with a WARNING line (the original bytes
are retained in `<file>.sync-backup`); a corrupt MAIN file aborts the run —
`--check`/`--all` exit 2, SessionStart prints the warning and exits 0
(session start is never blocked).

**Classifying a NEW key (the tripwire):** when a future Claude Code release
adds a key that differs between main and a profile, the sync prints one line
per profile:

```
[kimi] .claude.json UNCLASSIFIED drift: 'someNewKey' — classify in sync-profile-settings.py: ...
```

(One line per drifted key per run, until classified — a key nobody
classifies keeps reporting at every session start. That persistence is
deliberate: a report that fires once and silences itself is a report that
trains people to wait it out.)

That report is the mechanism working as designed — do not silence it by
ignoring it. Open the script and classify the key:

- It changes behavior and users set it once for all profiles → add to
  `BEHAVIOR_KEYS` (it will sync from now on).
- It is runtime state / a cache / a counter / a migration flag / identity or
  credentials → teach `is_state_key()` a pattern or exact name (never sync;
  syncing `projects`, `oauthAccount`, or migration flags across profiles
  corrupts state or account identity).
- It is known but deliberately per-profile → `GRAY_ACKNOWLEDGED` with the
  reason, so it stays silent.

The classifier was calibrated against the live key census on 2026-08-17:
main's file held 102 top-level keys, classified 7 behavior / 91 state /
4 acknowledged-gray / 0 unclassified (reproduce: classify every top-level
key of `~/.claude.json` with `BEHAVIOR_KEYS` + `is_state_key()` +
`GRAY_ACKNOWLEDGED`). One accepted blind spot, in the fail-safe direction:
a FUTURE behavior key whose name happens to contain a state substring
(`last`/`tip`/`count`/`seen`/`usage`/`token`/...) is classified as state —
silently never synced, and NOT covered by the tripwire report. The backstop
is an occasional manual census (same one-liner as above): eyeball the state
bucket for preference-looking names. Sync writes are backup + atomic
replace (backup chmod 600 regardless of source permissions), and were
verified to survive a live harness session rewriting the file (a marker key
written into an active profile persisted 30+ minutes of harness writes) —
but re-verification is cheap if a future Claude Code release changes write
semantics: write a marker into an active profile's `.claude.json`, keep
using the session, check the marker an hour later.

## Local skill source changes do not appear in Claude Code or Codex

Normal edits should be live because installed locations are symlinks to the source repos.
If they are not live, first check whether the path is still a symlink:

```bash
python3 ~/.config/claude-switch-models-setup/sync-local-skill-sources.py --print-watch-paths
```

For structural changes such as new skill entries, removed skill entries, renamed skills,
or version bumps, the macOS watcher should run automatically:

```bash
launchctl print gui/$(id -u)/ai.daymade.claude-skill-source-sync
```

If the watcher is not installed, install it:

```bash
~/.config/claude-switch-models-setup/sync-local-skill-sources-daemon.sh --install
```

If the watcher is installed, healthy and running, and the change still does not
appear, check whether it is executing an older pinned copy than the source. The
daemon deliberately runs an installed plugin version rather than the checkout, and
nothing advances that pin on its own:

```bash
python3 <this skill>/scripts/skill-install-audit.py --list DAEMON_RUNTIME_LAG SOURCE_CHECKOUT_BEHIND
```

A non-empty `DAEMON_RUNTIME_LAG` names both versions and the commands that advance
the pin. Read the second section before trusting an empty first one: the comparison
is made against a local checkout, so a daemon on the previous release and a checkout
still on it agree with each other, and the lag reads clean while the published source
has moved on. Bring the checkout current, then re-run.

The topology and the reason for the isolation are in
[local-source-sync-architecture.md](local-source-sync-architecture.md).

Manual repair fallback:

```bash
python3 ~/.config/claude-switch-models-setup/sync-local-skill-sources.py --apply
```

At a selected `~/.agents/skills` name, the script replaces only an empty path,
the correct link, or a wrong link that still belongs to a managed source repo;
the last case moves to recoverable backup storage first. A real object,
relative/broken link, or third-party link fails visibly and stays in place. The
script moves stale unselected source-owned links out of the active root, but
never removes entries from legacy `~/.codex/skills`: non-compatible managed
links are reported for reviewed `skill-governance` cleanup, while real
directories, third-party links, malformed foreign links, and `.system` stay
untouched. Restart any already-running Claude Code/Codex sessions after
repairing because Skill metadata is loaded at session start.

## Source sync warns that an active skill name is registered by no checkout

`csk` prints this at launch, and the daemon writes it to `source-sync.err.log`:

```
WARN: <manifest>: 1 active skill name(s) registered by no discovered source checkout; skipped this pass: new-skill
WARN:   scanned <marketplace>: <checkout> (branch feat/other-work)
WARN:   scanned <other marketplace>: <checkout> (branch main)
WARN:   a checkout on a branch that predates the skill links it on the first pass after it catches up; a misspelled or retired name repeats this warning until the manifest is corrected
```

The name is usually right and a checkout is the problem. The manifest is written
against the marketplace as published on `main`; the syncer reads the working tree
of each local checkout, and a checkout parked on a feature branch registers only
what that branch had when it forked. The pass already converged for every other
name, so nothing else is waiting on this. Confirm where each checkout is:

```bash
python3 <this skill>/scripts/skill-install-audit.py --list SOURCE_CHECKOUT_BEHIND
git -C <checkout> status --short --branch
```

What to do depends on who owns that checkout. A clean checkout of your own goes
back with `git checkout main && git pull --ff-only`; the next pass links the name
with no further step. A checkout another session is working on (uncommitted
changes, commits in the last hours) stays as it is: the name links on the first
pass after that work lands and the checkout returns to `main`. Switching,
stashing, or rebasing someone else's working tree to silence a warning destroys
their state.

If every checkout is on a current `main` and the warning persists, the name is
misspelled or the skill was renamed or retired. Correct the manifest.

Before daymade-claude-code v3.15.0 the same condition was a traceback,
`ValueError: unknown active skill name(s)`, that aborted the pass: the daemon
exited 1 on every trigger, and `~/.agents/skills` and the `enabledPlugins` mirror
stayed frozen for every skill (observed 2026-09-05, after a manifest edit made
against a checkout parked on another session's branch). A daemon still printing
that traceback runs a pinned copy older than the fix; advance the pin as the
previous section describes.

## Several profiles launched at once fail with sync tracebacks

This should not happen on current scripts: `sync-local-skill-sources.py` and `claude-plugins-sync.py` share a cross-process lock before writing marketplace JSON, installed plugin metadata, or cache symlinks.

If you still see `FileExistsError` while creating a symlink or `FileNotFoundError` while replacing `known_marketplaces.json`, re-link the installed helper scripts and rerun. The install set and both link layouts (checkout-linked, or pinned plugin copy) are owned by step 2 of the setup workflow in SKILL.md: do not copy the files (a copy forks them and reintroduces the silent drift that step exists to prevent), and do not relink a pinned machine to the checkout.

Then verify with concurrent version probes:

```bash
# adjust the list to the profiles you actually configured
for profile in kimi glm deepseek stepfun anthropic; do
  tmux new-session -d -s "ccver-$profile" \
    "zsh -lc 'source ~/.config/claude-switch-models-setup/claude-profiles.sh; claude-profile $profile --version'"
done
```

## Profile loads skills but model request fails

Run with `--debug-file` and look for the order of events. If the log shows `Loaded ... installed plugins` and `Loaded ... unique skills` before an API error, the skill/profile sync layer is working and the failure is in the provider network/TLS path.

Example failure class: `UNKNOWN_CERTIFICATE_VERIFICATION_ERROR` after all skill-loading lines. Diagnose the configured `ANTHROPIC_BASE_URL` and the local proxy/TLS chain; do not treat that as a missing-skill problem.

## I want to add another provider

1. Copy a template to `~/.claude/settings/<new-provider>.json`.
2. Fill in the API key and base URL.
3. Update the model names to match that provider's Anthropic-compatible model IDs.
4. Run `claude-profiles-init`.
5. Add an alias to your shell rc file if desired.

## I want to remove a provider

Run:

```bash
claude-profile-rm <provider>
```

This deletes only the isolation directory (`~/.claude-profiles/<provider>/`). It does **not** delete `~/.claude/settings/<provider>.json`; remove that manually if you want it gone.
