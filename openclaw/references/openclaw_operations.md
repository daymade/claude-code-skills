# OpenClaw Operations & Troubleshooting

Gateway health, plugin lifecycle, and upgrade diagnosis for an OpenClaw
instance. The skill's config subcommands cover `openclaw.json`; this reference
covers the runtime around it.

## Confirming the installed version

Three sources, read all of them:

```bash
openclaw --version
npm view openclaw dist-tags --json   # latest / beta / extended-stable
openclaw update --dry-run            # validating phase reports install integrity
```

`update --dry-run` prints `Current version`, `Target version`, and the update
channel. When current equals target and the `validating` phase passes, the
install carries no interrupted-upgrade residue.

`npm view` alone is not sufficient: the `latest` dist-tag can lag a GitHub
release. Check GitHub tags when npm and a release note disagree.

**A version question is usually a health question.** When an install "feels
old", verify the version first, then move to gateway and plugin health — the
version number is rarely the defect. Observed 2026-09-21: an instance already
on the latest release had a parked gateway and a broken memory plugin.

## Gateway parked, LaunchAgent disabled

Symptoms:

- `openclaw gateway status` reports `Service: LaunchAgent (not loaded)` on macOS
- `launchctl list | grep openclaw` has no gateway row, and the gateway port has
  no listener
- `openclaw doctor` prints `Gateway LaunchAgent <label> is installed but
  unloaded and disabled in launchd`, plus the note `A terminated update helper
  can leave it disabled across logins. Doctor does not automatically re-enable
  it.`
- the gateway log carries `gateway.maintenance_required` or
  `Legacy session store requires migration`

The launchd-disabled string and the update-helper note are printed by `doctor`
(and by `openclaw triage`, which collects doctor findings) — not by
`gateway status`. Attribute them to `doctor` when quoting them to someone.

Repair order matters:

```bash
openclaw doctor --fix     # migrates legacy sessions.json / pairing store into SQLite
openclaw gateway start    # doctor does NOT re-enable the LaunchAgent
```

`doctor --fix` performs the migration but explicitly does not re-enable the
service. Running it alone leaves a repaired state with a stopped gateway.

Read back with checks that do not depend on the tool's own report:
`launchctl list | grep openclaw` shows a gateway PID, and the port has a
listener.

## Plugin register failure and silently blocked hooks

Log signatures:

- `plugin register must be synchronous`
- `plugin must declare contracts.tools before registering agent tools`
- `typed hook "<name>" blocked because non-bundled plugins must set
  plugins.entries.<id>.hooks.allowConversationAccess=true`

**The dangerous form is silent.** All of the following can be true while a
plugin's automatic behaviour is dead:

- `gateway status` reports `running (state active)` with an ok connectivity
  probe
- the plugin registers successfully and is named in
  `http server listening (...)`
- the status panel shows `Memory: enabled (plugin <id>)`

The reliable check is the blocked count in the log, not the status panel:

```bash
grep -c 'blocked because' ~/Library/Logs/openclaw/gateway.log
openclaw plugins doctor   # discovery, module loading, compatibility, config
```

`plugins doctor` reporting that checks passed is the strongest mechanical
signal that plugin loading is healthy.

## Plugin lifecycle

`plugins update` does not work for plugins that were not installed through
ClawHub. It reports `no authoritative package-owner metadata`, and
`plugins registry --refresh` does not clear that. Use install instead:

```bash
openclaw plugins install <spec> --force --pin --accept-capabilities
```

`--pin` records the exact resolved version, so a later `plugins update` can
recognise the install.

**Diff the capability surface before accepting it.** Fetch the package to a
scratch directory and compare the new `openclaw.plugin.json` against the
installed one:

```bash
npm pack <spec> --silent && tar xzf *.tgz && cat package/openclaw.plugin.json
```

A bump that only adds a `contracts` block declares tools the plugin already
registered implicitly — that is not a widened permission. A bump that adds
capabilities, hooks, or a new `kind` is. Observed 2026-09-21: mem9 0.3.3 →
0.4.15 added only `contracts` and kept `kind: memory` while retaining the
legacy `tenantID` config key, so the upgrade fixed register failures without
changing what the plugin could reach.

### `plugins enable` can be blocked by the allowlist

Enabling a plugin that is installed and valid may still fail with
`plugin "<id>" could not be enabled (blocked by allowlist)`. `plugins.allow` is
a separate gate from `plugins.entries.<id>.enabled`, and it is an array, so
`config patch` replaces it rather than merging — include the existing entries:

```bash
openclaw config patch --stdin <<'JSON'
{ "plugins": { "allow": ["existing-a", "existing-b", "new-plugin"] } }
JSON
openclaw plugins enable new-plugin
```

## Hook permission model

Non-bundled plugins must be granted conversation access explicitly. Two
independent switches, per OpenClaw's own config hints:

- `plugins.entries.<id>.hooks.allowConversationAccess` — whether the plugin may
  read raw conversation content through typed hooks (`before_agent_run`,
  `before_model_resolve`, `before_agent_reply`, `llm_input`, `llm_output`,
  `before_agent_finalize`, `agent_end`).
- `plugins.entries.<id>.hooks.allowPromptInjection` — whether the plugin may
  modify the prompt; setting it false blocks `before_prompt_build`.

A memory plugin typically needs the first, to store and recall, and often the
second, to inject recalled context. Granting neither leaves the plugin
registered but inert.

Read the current value with `openclaw config get plugins.entries.<id>`. Change
it with `openclaw config patch --stdin`, which validates against the schema,
hot-reloads, and writes `openclaw.json.bak`. Do not hand-edit
`~/.openclaw/openclaw.json`.

## `doctor --fix` has side effects

`--fix` does more than repair. Observed side effects:

- creates a heartbeat monitor for the agent
- materialises a legacy `HEARTBEAT.md` workspace file into a cron entry
- merges `TOOLS.md` into `AGENTS.md` and archives the original
- installs shell completion and rewrites the config

Back up before running it: it merges `TOOLS.md` into `AGENTS.md` and archives
the original, and it rewrites the config. Then inventory what it **created**, not
only what it fixed. A newly created automation looks identical to healthy state.

### A legacy heartbeat file becomes an active cron

A workspace left over from an earlier OpenClaw carried a `HEARTBEAT.md` holding
only comments, including the instruction that an empty file skips heartbeat
calls. `doctor --fix` migrated it into a recurring entry. New workspaces differ:
OpenClaw no longer creates `HEARTBEAT.md` and the runtime never reads it, so
this is a migration artefact rather than stock behaviour.

The entry then runs and skips. Observed 2026-09-21, `openclaw cron runs <id>`
returns:

```json
{ "status": "skipped", "error": "heartbeat skipped: empty-heartbeat-file",
  "deliveryStatus": "not-requested" }
```

Those are two separate facts and easy to conflate: `empty-heartbeat-file` is why
the run skipped, while `deliveryStatus: not-requested` is the entry's missing
delivery target — rendered `not requested (not requested)` by `cron list` and
`delivery: not requested (not requested)` by `cron show`.

That entry is a system-owned monitor job: `openclaw cron disable <id>` fails
with `system-owned monitor jobs cannot be edited by cron clients`. Disable the
recurrence instead:

```bash
openclaw config set agents.defaults.heartbeat.every "0m"
```

`openclaw health` then reports `Heartbeat interval: disabled`.

## Skill discovery boundary

OpenClaw scans a fixed set of skill roots and refuses a skill directory whose
symlink resolves outside its root. Observed 2026-09-21, every failure on that
instance carried `source: agents-skills-personal`, which is `~/.agents/skills`:

```
Skipping invalid skill: file=~/.agents/skills/<name>/SKILL.md error=symlink prefix resolves outside the root ancestry: <requested path>
```

That suffix echoes the requested path, not the symlink's real target — the two
are the same string in the message, so do not read it as the resolved target.

The other loader path reports the same failure as
`Skipping escaped skill path outside its configured root: … reason=symlink-escape`
(source-level string, not reproduced on that instance).

`skills` has `additionalProperties: false` and holds `allowBundled`, `load`,
`install`, `limits`, `workshop`, and `entries`. Two switches under `skills.load`
matter, and which one works depends on the root:

- **`skills.load.extraDirs`** — "Additional shared skill roots to scan at lowest
  precedence. Use this for sibling repos or shared skill packs that should be
  available without copying them into the OpenClaw workspace." A sibling repo
  added here is discovered as its own root and the symlink is never traversed.
- **`skills.load.allowSymlinkTargets`** — "Trusted real target roots that skill
  symlinks may resolve into when they sit outside their configured source root.
  Keep this narrow, such as a sibling repo skills directory." Gated in code:
  `shouldUseConfiguredSymlinkTargets` accepts only `openclaw-workspace`,
  `openclaw-extra`, and `agents-skills-project`. It does **nothing** for
  `~/.agents/skills`, which registers as `agents-skills-personal`.

That gating matters before diagnosing anything: for `agents-skills-personal`,
`shouldEnforceConfiguredSkillRootContainment` returns false, so root-level
containment is bypassed entirely and the refusal happens later, when the skill
file is read. An allowlist set on the wrong root looks configured and changes
nothing.

Prefer `extraDirs` for a sibling repo. Replacing the symlink with a real copy
also makes the skill loadable, but it desynchronises that skill from whatever
maintains the link — a copy is the last resort, taken only when no root can be
granted.

### `extraDirs` needs the canonical path, not the typed one

macOS filesystems are case-insensitive but preserve the on-disk casing, and the
two Node resolution calls disagree about which form they return. Measured on a
box whose home really contains `Workspace` (capital W) while everyone types
`workspace`:

```js
fs.realpathSync('~/workspace/repo')        // -> ~/workspace/repo  (input casing kept)
fs.realpathSync.native('~/workspace/repo') // -> ~/Workspace/repo  (canonical)
```

OpenClaw resolves the configured root with `realpathSync` and the candidate
skill path with `realpathSync.native`, so a root written with the typed casing
compared against a canonical candidate never matches. The failure reads
`resolved path escapes skill root` and the skill is skipped — after the config
change appears to have been applied. Resolve the directory first and paste what
`realpathSync.native` returns:

```bash
node -e "console.log(require('fs').realpathSync.native('/path/to/skills'))"
```

Note that `git rev-parse --show-toplevel` and `python3 -c 'os.path.realpath'`
both report the typed casing on this platform, so neither is evidence of the
canonical form. `.agents/skills` failures for skills that are also present under
an `extraDirs` root are harmless — the same content loads from the extra root.

## A working plugin can still have a dead backend

The strongest signal in this reference is `plugins doctor` reporting checks
passed, and that is exactly where one failure hides: plugin loading is healthy
while the provider behind it rejects every call.

Observed 2026-09-21 on mem9 0.4.15 with permissions granted and hooks unblocked.
`plugins doctor` passed, `gateway status` was active, `Memory` showed
`enabled (plugin mem9)` — and every call failed with:

```
[mem9] before_prompt_build failed: Mem9HttpError: tenant schema incompatible
with embedding mode: sessions.embedding is a regular vector column, but
MNEMO_EMBED_AUTO_MODEL is enabled; disable Auto Embed or migrate/recreate this
tenant schema
```

That setting lives on the provider side. The plugin's `configSchema` carries no
embedding key and the bundle contains no `MNEMO_EMBED_AUTO_MODEL` reference, so
nothing in OpenClaw can change it. Both remedies the error names are
provider-side, and recreating a tenant schema can destroy stored memories — not
a repair to make unilaterally.

`openclaw doctor`'s Memory search note degrades in the same direction: it first
reports the memory plugin disabled, then, once the plugin is enabled, reports
that the provider does not support protected private transcript recall. Read the
note as a symptom of the provider, not of the plugin.

## Verification ladder

Ordered strongest to weakest, for claiming an OpenClaw repair worked:

1. **`openclaw plugins doctor` reports checks passed, *and* the gateway log's
   `blocked because` count is 0 after the fix.** These two are peers, not a
   ranking: `plugins doctor` checks discovery, loading, compatibility, and
   configuration, and its own output defers runtime state to `openclaw health`
   — while the blocked count is runtime evidence for exactly the silent-hook
   failure this reference is about.
2. `openclaw health` → event loop ok, probe duration, session store entries
3. `openclaw gateway status` → running / active, port listening
4. `openclaw status` panels (`Memory: enabled (plugin ...)`)

Steps 3 and 4 stay green while step 1 fails. A claim that something is fixed
needs step 1, not steps 3 or 4.

**An agent's own report of a tool call is not evidence.** `openclaw agent
--json` returns a `toolSummary` shaped like `{ "calls": 1, "tools":
["memory_store"], "failures": 0 }`. Observed 2026-09-21, that block claimed a
successful store while the gateway log recorded the provider rejecting it, and
the agent then "confirmed" the stored value by reading it back out of the
conversation context. A round trip through one session proves the session, not
the backend. Verify against the log, or against a fresh session.

What this ladder does not cover: whether a memory plugin actually stores and
recalls. That needs one real agent turn, and writing test data into a memory
backend to check is an external write — report the gap instead of claiming it.
