# Wrapper Skill Code Patterns

Copy-pasteable templates for every file a generated wrapper skill ships. Each template has placeholders that need to be filled from the Step 2 mining output. Every template is accompanied by an explanation of why it's shaped that way, and a reference to the concrete version in `ima-copilot/` for comparison.

Rule of thumb: when adapting these templates, remove anything the original session didn't actually need. Don't leave placeholder sections that apply to other wrappers but not yours.

## File: SKILL.md

```markdown
---
name: <wrapper-skill-name>
description: <pushy, trigger-heavy description including tool name, related keywords, literal error strings from Step 2c, and "when to use" signals. 4-8 sentences. Err on side of too many triggers.>
---

# <Wrapper Skill Display Name>

<One sentence: what this skill is and why it exists.>

## Overview

<2-4 sentences describing the upstream tool, the specific friction this wrapper removes, and the scope of its coverage.>

## Architectural principles (do not violate)

This skill is a **wrapper layer** around <upstream-tool>. The wrapper contract is non-negotiable:

- **Never vendor upstream files.** This skill directory does not contain any copy, fork, or excerpt of <upstream-tool>'s own content.
- **Repairs happen at runtime, not at ship time.** If an upstream bug needs patching, this skill carries the *instructions* for how to patch, not the patched files. Running a repair is idempotent.
- **Always ask before touching upstream files.** Modifying installed <upstream-tool> files requires explicit user consent via AskUserQuestion.
- **Teach rather than hide.** Every fix shows the user exactly what changed and where the backup was saved.

## What this skill does

| Capability | Entry point | Detail |
|---|---|---|
| Install upstream <tool> | `scripts/install_<tool>.sh` | See `references/installation_flow.md` |
| Configure credentials | Inline workflow below | See `references/credentials_setup.md` |
| Diagnose and fix known issues | `scripts/diagnose.sh` + workflow below | See `references/known_issues.md` |
| <skill-specific capability 4, if any> | `scripts/<name>` | See `references/<doc>.md` |

## Routing

<Table mapping common user phrasings to capabilities. Include trigger strings from Step 2c if they are common user errors.>

When in doubt, default to Capability 3 (diagnose). It is the only read-only entry point and it surfaces exactly which capabilities are currently blocked and in what order, which is almost always the correct first step when a new user arrives with a vague question. Put a one-line "when in doubt → diagnose" note at the bottom of the routing table so the agent has an unambiguous default.

## Capability 1: Install upstream <tool>

<2-3 paragraph explanation of what the installer does, with a code block showing the one-line invocation. Reference `references/installation_flow.md` for details.>

## Capability 2: Configure credentials

<Brief explanation of credential paths and liveness check. Reference `references/credentials_setup.md`.>

## Capability 3: Diagnose and fix known issues

<This is the agent-instruction section. Walk the agent through the repair flow: run diagnose.sh, parse output, look up each warning in known_issues.md, ask user consent via AskUserQuestion, execute chosen repair commands, re-verify.>

## Capability 4: <skill-specific, if any>

<e.g. personalized search, report generation — anything the session found valuable beyond install+diagnose>

## What this skill refuses to do

- Vendor, fork, or mirror upstream files into this directory
- Pin an upstream version in SKILL.md (installer uses overridable defaults, SKILL.md stays version-agnostic)
- Silently patch upstream files — every modification path requires explicit consent
- Hardcode user-specific values

## File layout

```
<wrapper-skill-name>/
├── SKILL.md                         # This file
├── scripts/
│   ├── install_<tool>.sh            # Download → stage → distribute
│   └── diagnose.sh                  # Read-only health report
├── references/
│   ├── installation_flow.md
│   ├── credentials_setup.md
│   ├── known_issues.md              # Issue registry — source of truth
│   └── best_practices.md
└── config-template/                 # Optional; omit if no per-user config
    └── <tool>.json.example
```
```

**Concrete version**: `ima-copilot/SKILL.md`.

**Why the description is so long**: Claude's skill selector is pattern matching on the description field. A 3-sentence description gets triggered 30% of the time it should; an 8-sentence description with literal error strings gets triggered 95% of the time. The cost of false positives (skill fires when it isn't needed) is much lower than the cost of false negatives (user hits an error this skill could have fixed but the skill didn't fire). Err on the verbose side. Note: there is a hard 1024-character cap on the description field, enforced by `skill-creator/scripts/quick_validate.py`. Run validation before commit to catch overlong descriptions early.

**What to pack into the description** (checklist):

- **Literal error strings from the session** — if the upstream tool emits `Skipped loading skill(s) due to invalid SKILL.md`, that exact phrase goes in the description so a future user hitting the same error triggers this skill automatically. Paraphrases do not match, literal strings do.
- **Tool name in every language the session used**. If the user spoke to you in Chinese, put the Chinese name (`腾讯 IMA`, `知识库搜索`, `笔记搜索`) alongside the English (`Tencent IMA`, `knowledge base search`). Claude's selector is language-agnostic but a monolingual description only triggers on monolingual queries.
- **A self-disambiguation clause** naming the upstream package. The wrapper and the upstream often fight for the same triggers — a user asking "install ima-skill" could route to either this wrapper or to the upstream skill package if both are installed. Put a clause like "This is a wrapper layer around <upstream-name> — it installs and orchestrates <upstream-name> rather than replacing it" so the selector has a distinguishing signal to prefer the wrapper when the user's intent is installation, and defer to the upstream when the user's intent is direct operation.
- **The symptoms that triggered the original session**. If the user came to you because something was broken, put that symptom in the description so a future user with the same symptom gets pushed here.

## File: scripts/install_<tool>.sh

```bash
#!/usr/bin/env bash
#
# install_<tool>.sh — Install upstream <tool> to <supported-agent-list>
#
# Flow:
#   1. Download the official <artifact> from <source-url>
#   2. Stage it in a temp directory
#   3. Detect which of the target agents are installed locally
#   4. Delegate to `npx skills add <local-path>` (vercel-labs/skills) in its
#      default symlink mode so that the agents share one canonical copy
#   5. Clean up the staging dir on exit
#
# Re-run safely — every step is idempotent.

set -euo pipefail

<TOOL>_VERSION="${<TOOL>_VERSION:-<default-version>}"
BASE_URL="<artifact-base-url>"
STAGING_ROOT="/tmp/<wrapper-skill-name>-staging"
STAGING_DIR="${STAGING_ROOT}/$(date +%s)-$$"

cleanup() {
  if [ -n "${STAGING_DIR:-}" ] && [ -d "$STAGING_DIR" ]; then
    rm -rf "$STAGING_DIR"
  fi
}
trap cleanup EXIT

usage() {
  cat <<'EOF'
Usage: install_<tool>.sh [--version <x.y.z>]

<One-paragraph explanation of what this script does and what flags it accepts.>
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --version)     <TOOL>_VERSION="$2"; shift 2 ;;
    --version=*)   <TOOL>_VERSION="${1#*=}"; shift ;;
    -h|--help)     usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 1 ;;
  esac
done

# Require basic tools — fail fast with a specific missing-tool message.
for tool in curl unzip npx; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "✗ Required tool not found on PATH: $tool" >&2
    exit 1
  fi
done

# Require Node.js >= 18 — `npx skills add` from vercel-labs/skills needs a
# modern Node runtime. The error on old Node is otherwise opaque and blames
# the wrong layer (npm cache, package resolution) rather than the version.
if command -v node >/dev/null 2>&1; then
  node_major=$(node --version 2>/dev/null | sed -E 's/^v([0-9]+).*/\1/')
  if [ -n "$node_major" ] && [ "$node_major" -lt 18 ] 2>/dev/null; then
    echo "✗ Node.js 18+ required for 'npx skills add' — found: $(node --version)" >&2
    echo "  Upgrade via your package manager (brew/apt/nvm) and retry." >&2
    exit 1
  fi
fi

echo "▶ Staging upstream <tool> v${<TOOL>_VERSION}"
mkdir -p "$STAGING_DIR"

ZIP_URL="${BASE_URL}/<archive-filename-${<TOOL>_VERSION}.zip>"
ZIP_PATH="${STAGING_DIR}/upstream.zip"

# Download with `--fail` so HTTP errors surface as non-zero exit codes,
# and capture the HTTP code for the error-branch message.
echo "  Downloading ${ZIP_URL}"
http_code=$(curl -sS -L --fail -o "$ZIP_PATH" -w "%{http_code}" "$ZIP_URL" || echo "000")
if [ "$http_code" != "200" ]; then
  echo "" >&2
  echo "✗ Download failed (HTTP ${http_code})" >&2
  echo "" >&2
  echo "If <tool> has released a newer version, pass it explicitly:" >&2
  echo "    <TOOL>_VERSION=x.y.z bash $0" >&2
  echo "" >&2
  echo "or find the latest version at <tool-homepage-url>" >&2
  exit 1
fi

# Size sanity check — a redirect to an HTML error page or a yanked package
# often returns a "success" status with a tiny non-archive body. Reject
# anything below an absolute floor to fail fast before extraction corrupts
# the staging dir.
actual_size=$(wc -c < "$ZIP_PATH" | tr -d ' ')
echo "  Downloaded ${actual_size} bytes"
if [ "$actual_size" -lt 1000 ]; then
  echo "✗ Downloaded file is suspiciously small — aborting before extraction" >&2
  exit 1
fi

echo "  Extracting…"
unzip -q -o "$ZIP_PATH" -d "$STAGING_DIR"

# Locate the root directory inside the extracted archive. Prefer well-known
# layout first, fall back to a recursive scan that picks the shallowest
# SKILL.md — which is the root by construction of every legal SKILL.md tree.
SKILL_SRC=""
if [ -f "$STAGING_DIR/<known-root-layout>/SKILL.md" ]; then
  SKILL_SRC="$STAGING_DIR/<known-root-layout>"
else
  shallowest_depth=999
  while IFS= read -r candidate; do
    rel="${candidate#$STAGING_DIR/}"
    depth=$(awk -F/ '{print NF}' <<< "$rel")
    if [ "$depth" -lt "$shallowest_depth" ]; then
      shallowest_depth="$depth"
      SKILL_SRC=$(dirname "$candidate")
    fi
  done < <(find "$STAGING_DIR" -maxdepth 4 -type f -name SKILL.md -print)
fi

if [ -z "$SKILL_SRC" ]; then
  echo "✗ Could not locate SKILL.md in extracted archive" >&2
  exit 1
fi

# Detect which target agents are installed
AGENTS=()
[ -d "$HOME/.claude" ]  && AGENTS+=("claude-code")
[ -d "$HOME/.agents" ]  && AGENTS+=("codex")
if [ -d "$HOME/.openclaw" ] || command -v openclaw >/dev/null 2>&1; then
  AGENTS+=("openclaw")
fi

if [ ${#AGENTS[@]} -eq 0 ]; then
  # Zero-agents-detected fallback. Three options considered during the
  # ima-copilot session, the selected one documented here:
  #   (a) abort with a "nothing to install into" error — too strict for a
  #       user who just installed claude-code and forgot to restart their
  #       shell between the install and our skill's install.
  #   (b) silently install nothing — most surprising and hardest to debug.
  #   (c) print a warning naming the paths we looked at and default to
  #       claude-code, which is the most common case. ← chosen
  echo "" >&2
  echo "⚠ No supported agent detected." >&2
  echo "  Looked for: ~/.claude (Claude Code), ~/.agents (Codex), openclaw on PATH." >&2
  echo "  Defaulting to claude-code as the most common target." >&2
  echo "" >&2
  AGENTS=("claude-code")
fi

AGENT_FLAGS=()
for a in "${AGENTS[@]}"; do
  AGENT_FLAGS+=("-a" "$a")
done

# Distribute via vercel-labs/skills in default symlink mode — repairs applied
# to any agent propagate to all of them.
if ! npx -y skills add "$SKILL_SRC" -g -y "${AGENT_FLAGS[@]}"; then
  echo "✗ npx skills add failed" >&2
  exit 1
fi

echo ""
echo "✓ Upstream <tool> v${<TOOL>_VERSION} installed"
```

**Concrete version**: `ima-copilot/scripts/install_ima_skill.sh`.

**Lessons baked into this template**:

- **Prerequisite check discipline**: every external tool the script depends on is verified up front. `curl`, `unzip`, `npx` are checked by the `command -v` loop. Node.js is checked separately with a *numeric major-version parse* because `command -v node` only verifies presence and says nothing about version — and `npx skills add` from vercel-labs/skills is known to fail opaquely on Node 16. If any prerequisite is missing or too old, the script fails fast with a specific actionable message, not after half the download.
- **Download integrity defense in depth**: `curl --fail` catches HTTP errors as non-zero exits; `-w "%{http_code}"` captures the code for a specific error message; an explicit `!= "200"` branch gives the user an override hint (`<TOOL>_VERSION=x.y.z bash $0`); and a `wc -c` size check rejects absurdly small downloads *before extraction*. The size check is the one that catches the worst real-world failure mode: an upstream CDN redirects a yanked-version URL to an HTML error page that returns 200, and a naive script then passes the HTML to `unzip` and produces confusing downstream errors. Reject anything below an absolute floor (1 KB works for most archives) and the cause is obvious.
- **Root SKILL.md detection prefers a known layout first, then falls back to the shallowest match**. This is a real bug discovered during ima-copilot dogfood: a naive `find` returned `ima-skill/notes/SKILL.md` as "first match" and the installer then tried to install from the `notes/` subdirectory, which failed because that file has no frontmatter. The fix is to bias the search toward known layouts.
- **Agent-detection philosophy: "only install where the user has opted in"**. The `AGENTS=()` block walks a fixed set of home directories and only installs to the ones that already exist. A missing agent path is treated as "the user did not opt into this agent" — not as a precondition failure. This avoids silently installing into directories that aren't part of the user's setup, which matters when the same machine has been used to experiment with multiple agent products.
- **Zero-agents fallback**: when no target agent is detected, the script prints an explicit "looked for: …" list before defaulting to claude-code. This is the single most-debated branch in the ima-copilot session because all three options (abort / silent-skip / default-to-claude-code) are defensible. The documented choice is to default-to-claude-code because that is the most common case when detection legitimately fails (e.g., user just installed the agent and hasn't restarted their shell). Abort would be hostile; silent-skip would be mystifying.
- **`-g -y` no `--copy`**: vercel's default symlink mode is strictly better for wrapper skills because a repair applied to any agent's install propagates via symlink to all agents. If your upstream tool has a different natural distribution story, reconsider — but the symlink default is correct in the vast majority of cases.
- **`trap cleanup EXIT`**: the staging directory is always removed, even if the script fails midway. No leftover clutter in `/tmp/`.

## File: scripts/diagnose.sh

```bash
#!/usr/bin/env bash
#
# diagnose.sh — Read-only health check for upstream <tool> installs.
#
# Prints one status line per check, then a summary.
#
# Exit codes:
#   0 — all checks passed
#   1 — one or more issues need user action
#   2 — diagnostic itself failed (network error, missing tooling)
#
# This script is strictly read-only.

set -uo pipefail

PASS=0; WARN=0; FAIL=0

status_ok()   { echo "✅ $1"; PASS=$((PASS + 1)); }
status_warn() { echo "⚠️  $1"; WARN=$((WARN + 1)); }
status_fail() { echo "❌ $1"; FAIL=$((FAIL + 1)); }

echo "=== <wrapper-skill-name> diagnostic report ==="
echo

# Agent target path resolution
find_install() {
  local agent="$1"; shift
  local path
  for path in "$@"; do
    if [ -f "$path/SKILL.md" ]; then
      echo "$path"
      return 0
    fi
  done
  return 1
}

# Resolve symlinks to detect shared canonical installs
canonical() {
  python3 -c "import os,sys; print(os.path.realpath(sys.argv[1]))" "$1" 2>/dev/null || echo "$1"
}

# Per-agent install presence
echo "--- Upstream <tool> installs ---"
CLAUDE_PATH=""; CODEX_PATH=""; OPENCLAW_PATH=""

if CLAUDE_PATH=$(find_install claude-code "$HOME/.claude/skills/<tool-dir>"); then
  status_ok "<tool> installed (claude-code) at $CLAUDE_PATH"
else
  status_warn "<tool> NOT installed (claude-code) — run install_<tool>.sh"
fi

if CODEX_PATH=$(find_install codex "$HOME/.agents/skills/<tool-dir>" "$HOME/.codex/skills/<tool-dir>"); then
  status_ok "<tool> installed (codex) at $CODEX_PATH"
else
  status_warn "<tool> NOT installed (codex) — run install_<tool>.sh"
fi

if OPENCLAW_PATH=$(find_install openclaw \
  "$HOME/.openclaw/skills/<tool-dir>" \
  "$HOME/.config/openclaw/skills/<tool-dir>" \
  "$HOME/.local/share/openclaw/skills/<tool-dir>"); then
  status_ok "<tool> installed (openclaw) at $OPENCLAW_PATH"
else
  status_warn "<tool> NOT installed (openclaw) — run install_<tool>.sh"
fi

# Detect shared canonical via symlink
CLAUDE_REAL=$(canonical "${CLAUDE_PATH:-}")
CODEX_REAL=$(canonical "${CODEX_PATH:-}")
OPENCLAW_REAL=$(canonical "${OPENCLAW_PATH:-}")
if [ -n "$CLAUDE_REAL" ] && [ -n "$CODEX_REAL" ] && [ "$CLAUDE_REAL" = "$CODEX_REAL" ]; then
  echo "ℹ️  claude-code and codex share the same install via symlink"
fi

# ... similar for other agent pairs ...

echo

# Credentials
echo "--- Credentials ---"
<credential presence + liveness check, specific to the tool>
echo

# Known issues — one scan function per issue, called for each unique canonical dir
echo "--- Known issues ---"

SCANNED_REALS=""
scan_agent() {
  local agent="$1"
  local path="$2"
  local real="$3"
  [ -z "$path" ] && return
  case " $SCANNED_REALS " in
    *" $real "*) return ;;  # already scanned via another agent
  esac
  SCANNED_REALS="$SCANNED_REALS $real"
  scan_issue_001 "$agent" "$path"
  # scan_issue_002, etc.
}

scan_issue_001() {
  local agent="$1"
  local base="$2"
  <specific check for issue 1 — calls status_ok / status_warn as appropriate>
}

scan_agent "claude-code" "$CLAUDE_PATH"   "$CLAUDE_REAL"
scan_agent "codex"       "$CODEX_PATH"    "$CODEX_REAL"
scan_agent "openclaw"    "$OPENCLAW_PATH" "$OPENCLAW_REAL"

echo

# Summary
echo "--- Summary ---"
echo "  ✅ ${PASS} pass   ⚠️  ${WARN} warn   ❌ ${FAIL} fail"
echo

if [ "$FAIL" -gt 0 ] || [ "$WARN" -gt 0 ]; then
  echo "Next step: open references/known_issues.md and walk the agent through"
  echo "the warnings above. Each issue ID maps to a concrete repair procedure."
  exit 1
fi

exit 0
```

**Concrete version**: `ima-copilot/scripts/diagnose.sh`.

**Lessons baked into this template**:

- **`canonical()` via Python realpath**: detecting symlink-shared installs is essential to avoid reporting the same issue multiple times. Real discovery from ima-copilot dogfood.
- **`SCANNED_REALS` dedup**: only scan each underlying canonical directory once per issue, even if multiple agents point at it.
- **`find_install` takes a *variadic list* of candidate paths**: for each target agent, pass a short ordered list of known install paths and return the first that exists, rather than hardcoding one path. This matters most for agents whose home-directory layout has not stabilized — e.g., OpenClaw in ima-copilot was probed against `~/.openclaw/skills/...`, `~/.config/openclaw/skills/...`, and `~/.local/share/openclaw/skills/...` because the standard wasn't settled. For agents with a firmly-established layout (Claude Code's `~/.claude/skills/`), a one-entry list is fine. Designing the helper as variadic from day one avoids a painful refactor when a second candidate path becomes necessary.
- **One `scan_issue_NNN` function per known issue**: keeps the main loop clean and lets you add new issues by adding one function and one line in `scan_agent`.
- **`set -uo pipefail` (not `-e`)**: the diagnostic itself should not exit on the first command failure — it should continue and report all issues. `-u` and `-o pipefail` still catch real bugs in the script.

### Detection function return-code contract

The single hardest lesson from the ima-copilot session was that a detection function cannot be binary (broken / not-broken). It has to recognize **every post-repair state** the wrapper can produce, because users rerun the repair, restore partial backups, and switch between strategies mid-session. A function that only knows "original broken state" vs "Strategy A applied" will silently misreport anything else.

The contract: **one return code per healthy state, one code per broken state, and one code for the conflicted dual-state that arises when two fix strategies have partially collided**. Spelled out:

```
 0  — OK: original untouched and already valid
       (upstream shipped a fixed version, or the bug never applied to this
       install, or the tool is now at a release where the issue is gone)

 1  — BROKEN: original untouched and still needs repair

 2  — NOT APPLICABLE: the target file doesn't exist at all, because upstream
       changed the layout or the tool moved the affected file elsewhere.
       This is legitimately different from BROKEN (the repair is not the
       right fix because there is nothing to repair) and deserves its own
       status line in the output.

 3  — STRATEGY A APPLIED: the file is in the state that Strategy A's fix
       produces (e.g., SKILL.md renamed to MODULE.md, root references
       patched). This is healthy — do not report as BROKEN.

 3+ — STRATEGY B, C, ... APPLIED: one additional healthy code per strategy
       the known_issues.md file documents. Each strategy that touches a
       different set of files gets its own code.

 4  — DUAL-STATE CONFLICTED: files from more than one strategy exist
       simultaneously (e.g., both SKILL.md and MODULE.md present, or a
       backup restored on top of an in-progress fix). This state is the
       single most important thing a detection function must recognize,
       because reporting it as healthy hides a latent footgun and reporting
       it as BROKEN triggers a fresh repair that will make the conflict
       worse. The correct response is always CONFLICTED with a message
       that names the conflicting files and points the user at the
       rollback block.
```

Add a new healthy code whenever you add a new strategy to `known_issues.md`; add the dual-state code whenever more than one strategy can be applied to the same install. `ima-copilot/scripts/diagnose.sh` `check_submodule` function is the reference implementation — it returns 0/1/2/3/4 and the scan function's `case` statement handles each code distinctly.

**Why this matters**: the dual-state code is the single place a careless author will skip. The symptom is always "my repair worked, but `diagnose.sh` says everything is clean, and now my install is subtly broken in a way neither strategy's repair command will fix". The fix — as simple as adding one `[ -f "$A" ] && [ -f "$B" ]` branch at the top of the check function — prevents that class of failure entirely.

## File: references/known_issues.md

```markdown
# Known Issues in Upstream <tool>

This file is the **source of truth** for every upstream bug that <wrapper-skill-name> can detect and help repair.

## How the agent should use this file

When `scripts/diagnose.sh` reports a `⚠️` line mentioning `ISSUE-<NNN>`:

1. Explain to the user in plain language what's broken and why it matters.
2. If the issue has more than one repair strategy, use **AskUserQuestion** to present the choices.
3. After the user picks, execute the exact commands under that strategy. Every command backs up originals to `/tmp/<wrapper-skill-name>-backups/<timestamp>/` first.
4. Re-run `diagnose.sh` and show the before/after.
5. Remind the user that upstream upgrades replace these files, so reruns after an upgrade are expected — and safe.

## Issue registry

### ISSUE-<NNN> — <short title>

**Status**: <Name the specific loader or runtime producing the symptom, not just "upstream vX.Y.Z". Version-agnostic phrasing is strongly preferred so the entry doesn't go stale when upstream releases a new version — e.g., "Observed on recent upstream releases when loaded by Codex's .agents scanner" is better than "Open in upstream v1.1.2".>
**Symptom**: <literal error message from the session, verbatim — do not paraphrase>
**Root cause**: <what was discovered>
**Impact**: <what the user sees if unfixed>

**Why upstream probably hasn't fixed it**: <one short paragraph. This field matters more than it looks — it tells future readers *why the bug persists*, which is the only reason the wrapper's repair section is still load-bearing. Without this field, a future reader will assume the wrapper is out of date and remove the repair on the next upgrade, which is exactly the wrong reaction. Example shape from ima-copilot: "The upstream package is developed primarily against <loader X>, which tolerates the missing field; the bug is invisible from the upstream maintainer's primary testing platform.">

**How to explain it to the user** (plain language):
> <1-2 sentence, jargon-free>

**Repair strategies**:

#### Strategy A — <name>

<1-paragraph explanation of what this strategy does and why it's labeled as it is>

**What this strategy changes**:
- <file 1>
- <file 2>

**Commands** (agent executes after user consent; replace `<install>` with the specific agent path from `diagnose.sh`):

```bash
# Use `command cp` / `command mv` / `command rm` / `command sed` to bypass
# any user-defined shell aliases. Interactive-mode aliases like `alias mv='mv -i'`
# will otherwise hang the script on an "overwrite?" prompt, and `alias rm='rm -i'`
# will stall cleanup steps.

# 1. Back up originals. Every cp is `[ -f ... ] &&` guarded so that a rerun
#    after partial application (where the source file has already been renamed
#    or deleted by a previous fix run) doesn't print "file not found" errors.
#    The guard is what makes the backup step idempotent across reruns.
BACKUP="/tmp/<wrapper-skill-name>-backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP"
[ -f "<install>/<file-1>" ] && \
  command cp "<install>/<file-1>" "$BACKUP/<file-1-flat>"
# ... more guarded backup lines ...
echo "backup saved to: $BACKUP"

# 2. Apply the fix (idempotent). All sed/rm/cp/mv calls go through `command`.
#    sed -i.bak is the portable form that works on both BSD sed (macOS) and
#    GNU sed (Linux) — a bare `sed -i` fails on BSD and `sed -i ''` fails on
#    GNU. Always `command rm -f *.bak` after the sed to clean up the backup
#    files sed creates, since leaving them around clutters the install dir.
<fix commands, all using `command cp`, `command mv`, `command sed`, `command rm`>
```

**Rollback**:

```bash
command cp "$BACKUP/<file-1-flat>" "<install>/<file-1>"
# ... more rollback lines ...
command rm -f "<install>/<any-files-the-fix-created>"
```

**Pros**: <why this strategy is good>
**Cons**: <why you might not pick it>

#### Strategy B — <alternative>

...

#### Strategy skip — Leave the file alone

Every issue should document a "do nothing" branch explicitly, with the conditions under which it is actually valid. Users who only run the tool on a tolerant platform (e.g., Claude Code's lenient loader for ISSUE-001 in ima-copilot) may legitimately not want the repair. Naming the skip path as a first-class strategy makes it clear that "no action" was considered and the user is choosing it, rather than forgetting. When a strategy-skip branch is valid, the `AskUserQuestion` prompt in the agent's repair flow should list it as option (3) alongside Strategy A and Strategy B.

Shape of the entry:

```
#### Strategy skip — Leave the file alone

Valid when <specific condition — e.g., "the user is only running on loader X
which tolerates this bug">. Not recommended if <condition under which skip
becomes a latent footgun — e.g., "the user ever runs the same install on loader Y">.
```

## Adding new issues to this file

When you discover a new upstream bug worth capturing:

1. Assign the next sequential `ISSUE-<NNN>` number.
2. Fill in the same template: symptom, root cause, impact, plain-language explanation, at least one strategy with idempotent + reversible commands.
3. Update `scripts/diagnose.sh` to detect it (still read-only) and print a line with the same issue ID.
4. **Do not** add the fix commands into any shipped script — keep them in this file so the agent reads and executes them at runtime under user consent.
```

**Concrete version**: `ima-copilot/references/known_issues.md`.

**Why every command needs `command` prefix (including `sed` and `rm`, not just `cp`/`mv`)**: a user's shell may alias any of these to its `-i` variant. `alias mv='mv -i'` is common and was discovered during ima-copilot dogfood when it caused the repair to hang on a TTY prompt. `alias rm='rm -i'` is equally common — it affects the post-sed `.bak` cleanup and the rollback commands. `alias sed='sed -i'` is rarer but exists in some corporate dotfiles. The safe rule: **every cp, mv, rm, and sed in a repair block goes through `command` prefix, no exceptions**.

**Why the `[ -f ... ] &&` guard wraps every backup cp**: without the guard, a rerun of the repair after a partial first run (where some source files have already been renamed or consumed by a previous run) prints "file not found" errors during the backup step. Those errors are cosmetically ugly, but more importantly they break the user's mental model of "the repair completed cleanly". The guard makes the backup step a no-op on files that no longer exist at the expected location, which is the correct behavior across reruns.

**Why every fix backs up before modifying**: trust. A user running a wrapper skill for the first time wants to know "what did this skill change, and how do I undo it?". The backup path printed to stdout answers both questions without requiring the user to read the wrapper's source.

**Backup directory naming convention**: use `/tmp/<wrapper-skill-name>-backups/$(date +%Y%m%d-%H%M%S)`. The `%Y%m%d-%H%M%S` format sorts correctly when a user has multiple backup directories from different runs, and it is human-readable when the user is trying to find the most recent one. If reruns within the same second are possible (rapid test loops, CI), append `$$` (the shell's PID) for sub-second uniqueness: `/tmp/<wrapper-skill-name>-backups/$(date +%Y%m%d-%H%M%S)-$$`.

**Why `sed -i.bak` specifically (and why the `.bak` cleanup)**: `sed -i` has an incompatible argument between BSD sed (macOS default) and GNU sed (Linux default). BSD sed requires `-i ''` (empty string argument naming the backup suffix); GNU sed requires `-i` with no argument. The portable form is `sed -i.bak ...` — both sed variants accept it, and both leave behind a `<file>.bak` backup copy that you then clean up with `command rm -f "<file>.bak"`. Do not try to write a conditional that branches on OS — just use `.bak` unconditionally and clean up after.

**Why idempotency is mandatory**: users re-run the wrapper after upstream upgrades, after system migrations, after their coworker broke something. The repair must tolerate being rerun in any state the user hands it.

## File: config-template/<tool>.json.example

```json
{
  "_comment_<field1>": "<human-readable explanation of what this field does>",
  "<field1>": ["<placeholder-value-1>", "<placeholder-value-2>"],

  "_comment_<field2>": "<explanation>",
  "<field2>": []
}
```

**Concrete version**: `ima-copilot/config-template/copilot.json.example`.

**Why `_comment_*` pseudo-fields**: JSON doesn't support comments, and many wrapper skill config files are read by shells or Python without JSON5 support. The `_comment_*` prefix puts the documentation in the same file as the field it documents without breaking any JSON parser — the loader ignores unknown fields.

**Why placeholder values, not real ones**: a committed template is a shared artifact. Real values leak information about the wrapper's author (what knowledge bases they read, what API endpoints they hit, which projects they work on). Placeholder values protect privacy and keep the template genuinely reusable.

## Credential setup patterns (file content varies)

For `references/credentials_setup.md`, the pattern is:

1. **XDG-style paths** (`~/.config/<tool>/{client_id, api_key}`) with mode `600`.
2. **Env var fallback** (`<TOOL>_OPENAPI_CLIENTID` / `<TOOL>_OPENAPI_APIKEY`) documented as "env vars win over files when both are set".
3. **Scoped liveness check** — see the next section. The liveness call must probe the lowest-privilege operation the skill actually performs, not the easiest API call to make.
4. **Liveness verification by response-body shape, not HTTP status**. Many third-party APIs return HTTP 200 with a JSON body containing an error code (`{"code": 401, "msg": "..."}` style). A liveness check that only looks at `curl --fail` or HTTP 2xx will pass for a credential that will fail the very first real operation. The correct shape check parses the response body and matches on a success-indicator field — for IMA-style APIs, that's `"code"\s*:\s*0`; for OAuth APIs, it's often `"access_token"` present; for REST APIs, it's the presence of an expected data field. Whatever the indicator is, the diagnose step should verify the *body shape*, not just the HTTP layer.
5. **Rotation procedure** showing `printf '%s' "<new value>" > ~/.config/<tool>/client_id` followed by a re-run of the liveness check.

Do not make the template literal — credential setup varies a lot by tool. Use the pattern as a checklist when writing `credentials_setup.md` for your specific wrapper, not as a copy-paste target.

**Concrete version**: `ima-copilot/references/api_key_setup.md`.

## Runtime-logic patterns shared across wrappers

The install / diagnose / known_issues templates above are what make a wrapper *installable*. They are necessary but not sufficient. The three patterns in this section are what make a wrapper *correct at runtime* when it fans out operations across a third-party API, and they are frequently the most transferable insights a wrapper discovers — more transferable than any specific bug fix, because they are structural properties of the class of API the wrapper is talking to.

Every one of these patterns was discovered during the ima-copilot session, lived inside `search_fanout.py`, and applies to a far wider class of tools than IMA. Consider whether your tool has the same failure mode before claiming "this only applies to the reference implementation".

### Capability partitioning — enumerate vs operate

**The problem**: many third-party APIs have a permission model where the set of entities the credential can *list* is strictly larger than the set it can *act on*. A wrapper that fans out an operation across "all listable entities" will hit authorization errors on a large fraction of them, and if those errors are mixed into the primary result, they will drown out the actual successes.

**Examples by tool**:

- **IMA**: `search_knowledge_base` enumerates every KB the user can read, including subscribed public KBs. `search_knowledge` on a subscribed KB returns `code: 220030, msg: 没有权限` because search permission requires ownership. A 12-KB account may have only 2 searchable KBs.
- **GitHub**: `GET /user/repos` lists every repo you can see, including private repos you're a collaborator on. Admin actions (`DELETE /repos/{owner}/{repo}`, `PATCH /repos/.../archive`) require repo-owner privilege and return 403 on collaborators-only entries.
- **Slack**: `conversations.list` returns every channel you're in. `chat.postMessage` can be rejected on channels where the bot lacks the `chat:write` scope or the channel has posting-locked.
- **Aliyun RAM**: RAM users can list resources in an account (`ECS DescribeInstances`) but can't operate on resources outside their policy scope — you see the inventory, you can't touch most of it.
- **Linear**: `workspaces` are viewable; mutation API (issue create/edit) is gated per-workspace on your role.

**The pattern**: partition the fan-out result into four buckets, not one:

```
succeeded — operation returned real output you can render
denied    — entity enumerated fine, but the operation was rejected with
            a permission/scope/role error (NOT a tool bug — an entitlement
            gap in the credential). Collect these for an informational
            footer, do not render them alongside successes.
errored   — a transient/unexpected failure (timeout, 5xx, malformed
            response). These are bugs or service incidents and deserve a
            retry or a loud warning, not silent inclusion in the footer.
empty     — the operation succeeded but returned no output for this
            entity. Silence entirely unless the user asked "why no results".
```

The core idea: **enumerate-ability is not operate-ability**, and the wrapper must surface the gap as a distinct result category so the user can understand why "I have 12 knowledge bases but only 2 searches landed."

**Implementation template** (adapt to your API's error codes):

```python
PERMISSION_DENIED_MARKERS = ["220030", "no_permission", "Forbidden", "403"]

def is_permission_denied(result):
    if result.get("error") is None:
        return False
    err = str(result["error"])
    return any(m in err for m in PERMISSION_DENIED_MARKERS)

def partition(results):
    succeeded, denied, errored, empty = [], [], [], []
    for r in results:
        if is_permission_denied(r):
            denied.append(r)
        elif r["error"]:
            errored.append(r)
        elif r["output"]:
            succeeded.append(r)
        else:
            empty.append(r)
    return succeeded, denied, errored, empty
```

**Render rule**: show successes first, then any `errored` entries with a ⚠️ prefix (user should care), then `denied` entries in a collapsible `ℹ️ N entities returned 'no permission'` footer. Do not show `empty` entries unless the user asked for the full list.

**Concrete reference**: `ima-copilot/scripts/search_fanout.py` lines around the `rank_groups` / `is_permission_denied` functions, and `ima-copilot/references/search_best_practices.md` "Permission model" section.

### Undocumented limit detection

**The problem**: many third-party APIs have undocumented hard limits — a request that says "return all results" actually returns a truncated subset, and the response contains no `is_end`, `next_cursor`, `has_more`, or equivalent signal to tell you the truncation happened. A naive wrapper will silently show the first N results as if they were the complete set, and the user will make decisions based on a lie.

**Examples by tool**:

- **IMA**: `search_knowledge` returns exactly 100 hits per KB on high-frequency queries with no pagination token in the response body. The 100-hit cap is not documented anywhere; the only way to know is to send a query you know matches more than 100 items and observe the exact-100 count.
- **GitHub Search**: `/search/code` caps total results at 1000 but the `total_count` field may report 12000. Without the cap awareness, a wrapper shows "page 10 of 120" and blows up when page 11 returns empty.
- **Notion**: databases with > 100 pages return `has_more: true` correctly for up to ~1000 iterations but silently stop returning new pages around item 2000 on some plans.
- **Google Drive**: `files.list` with a broad query caps at 1000 results per page regardless of `pageSize` parameter, and the `nextPageToken` is omitted — you have to detect the hit-at-1000 as the signal.
- **Confluence / Jira**: `/search` endpoints have per-tenant "result ceiling" configurations that aren't exposed anywhere in the API — you discover them by hitting the wall.

**The pattern**: detect truncation heuristically and surface it as a prominent warning. The detection rule is usually "result count equals a round number like 50, 100, 500, or 1000, AND no pagination signal in the response" — because legit result sets do not coincidentally round to powers of ten.

**Implementation template**:

```python
SUSPICIOUS_ROUND_CAPS = {50, 100, 500, 1000, 10000}

def looks_truncated(response, results):
    """Return True if this response smells like a silent truncation."""
    n = len(results)
    # Did we hit a suspicious round cap?
    if n not in SUSPICIOUS_ROUND_CAPS:
        return False
    # Is there any pagination signal? If yes, we can page through, not a silent cap.
    for key in ("is_end", "next_cursor", "has_more", "nextPageToken", "next"):
        if response.get(key) not in (None, False, "", 0):
            return False
    return True
```

**Render rule**: when `looks_truncated` fires on any branch of the fan-out, append a `⚠️ N entity/entities may have been silently truncated at K results; try a narrower query to see more` block after the results. Do not swallow the signal — the entire point of this pattern is to tell the user about the lie.

**Concrete reference**: `ima-copilot/scripts/search_fanout.py` `HARD_HIT_CAP` constant and the `truncated` flag propagation, and `ima-copilot/references/search_best_practices.md` "Silent 100-result truncation" section.

### Scoped liveness checks

**The problem**: a wrapper's credential-liveness probe usually tests "can I make any authenticated call at all?" — but the credential may have scopes that pass the easy probe and fail the actual operation the skill performs. The user then gets a false ✅ on `diagnose.sh` and a confusing failure later when they try to use the skill's main capability.

**The ima-copilot case**: `diagnose.sh` probes `search_knowledge_base` with empty query, which needs only `list` scope on any one KB. This passes. But `search_fanout.py` actually needs `search` scope, which is a different tier of permission. A user with `list`-only credentials would see diagnose report everything as healthy and then hit 220030 on every single KB when they tried to run a search. (This is latent in the shipped version and is its own small bug.)

**The rule**: the liveness check must probe the **lowest-privilege operation the skill actually performs**, not the first API the credential can hit. If the skill has multiple capabilities with different permission tiers, the check must probe the most restrictive tier. If probing the lowest tier would have side effects (e.g., the lowest-privilege operation in the tool is "create a resource"), use the narrowest read equivalent you can find that still requires the target scope.

**Rule of thumb**:

```
For each capability the skill exposes:
  identify the minimum scope needed for that capability's main API call
  pick the union of all required scopes
  design a liveness probe that requires all scopes in that union
  if no single call requires all scopes, make multiple probes and require them all to pass
```

**Render rule**: `diagnose.sh` should name the scope each probe checks in its output so the user can see which capability is verified. For example:

```
✅ Credentials present
✅ Liveness (scope: list) — can enumerate KBs
✅ Liveness (scope: search) — can search the smallest KB
⚠️  Liveness (scope: write) — tried to add a test note and failed; Capability 4 (note creation) will not work until you regenerate credentials with write scope
```

**Concrete reference**: the corrected scoped-liveness behavior is a future fix for `ima-copilot/scripts/diagnose.sh` (currently only probes `list` scope, known limitation filed as a follow-up).
