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

**Why the description is so long**: Claude's skill selector is pattern matching on the description field. A 3-sentence description gets triggered 30% of the time it should; an 8-sentence description with literal error strings gets triggered 95% of the time. The cost of false positives (skill fires when it isn't needed) is much lower than the cost of false negatives (user hits an error this skill could have fixed but the skill didn't fire). Err on the verbose side.

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

# Require basic tools
for tool in curl unzip npx; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "✗ Required tool not found on PATH: $tool" >&2
    exit 1
  fi
done

echo "▶ Staging upstream <tool> v${<TOOL>_VERSION}"
mkdir -p "$STAGING_DIR"

<download and extract>

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
  echo "⚠ No supported agent detected. Defaulting to claude-code." >&2
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

- **`command -v` prerequisite check**: if any of `curl`, `unzip`, `npx` is missing, the script fails fast with a specific message, not after half the work is done.
- **Root SKILL.md detection prefers a known layout first, then falls back to the shallowest match**. This is a real bug discovered during ima-copilot dogfood: a naive `find` returned `ima-skill/notes/SKILL.md` as "first match" and the installer then tried to install from the `notes/` subdirectory, which failed because that file has no frontmatter. The fix is to bias the search toward known layouts.
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
- **One `scan_issue_NNN` function per known issue**: keeps the main loop clean and lets you add new issues by adding one function and one line in `scan_agent`.
- **`set -uo pipefail` (not `-e`)**: the diagnostic itself should not exit on the first command failure — it should continue and report all issues. `-u` and `-o pipefail` still catch real bugs in the script.

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

**Status**: Open in upstream v<version>.
**Symptom**: <literal error message from the session>
**Root cause**: <what was discovered>
**Impact**: <what the user sees if unfixed>

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
# Use `command cp` / `command mv` to bypass any user-defined shell aliases.
# Interactive-mode aliases will otherwise hang the script on an "overwrite?" prompt.

# 1. Back up originals (each cp is guarded so reruns don't emit "file not found")
BACKUP="/tmp/<wrapper-skill-name>-backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP"
[ -f "<install>/<file-1>" ] && \
  command cp "<install>/<file-1>" "$BACKUP/<file-1-flat>"
# ... more guarded backup lines ...
echo "backup saved to: $BACKUP"

# 2. Apply the fix (idempotent)
<fix commands, all using `command cp`, `command mv`, etc.>
```

**Rollback**:

```bash
command cp "$BACKUP/<file-1-flat>" "<install>/<file-1>"
# ... more rollback lines ...
```

**Pros**: <why this strategy is good>
**Cons**: <why you might not pick it>

#### Strategy B — <alternative>

...

## Adding new issues to this file

When you discover a new upstream bug worth capturing:

1. Assign the next sequential `ISSUE-<NNN>` number.
2. Fill in the same template: symptom, root cause, impact, plain-language explanation, at least one strategy with idempotent + reversible commands.
3. Update `scripts/diagnose.sh` to detect it (still read-only) and print a line with the same issue ID.
4. **Do not** add the fix commands into any shipped script — keep them in this file so the agent reads and executes them at runtime under user consent.
```

**Concrete version**: `ima-copilot/references/known_issues.md`.

**Why every command needs `command` prefix**: a user's shell may alias `mv` to `mv -i` or `cp` to `cp -i`. In interactive shells, this is helpful; in scripts, it makes the command block on a TTY prompt that the script cannot answer. Using `command mv` / `command cp` bypasses the alias entirely. This was discovered during ima-copilot dogfood when a hidden `mv -i` alias caused the repair to hang.

**Why every fix backs up before modifying**: trust. A user running a wrapper skill for the first time wants to know "what did this skill change, and how do I undo it?". The backup path printed to stdout answers both questions without requiring the user to read the wrapper's source.

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
3. **Liveness check** documented with the exact request (URL + method + body) and the success indicator (response field to look for).
4. **Rotation procedure** showing `printf '%s' "<new value>" > ~/.config/<tool>/client_id` followed by a re-run of the liveness check.

Do not make the template literal — credential setup varies a lot by tool. Use the pattern as a checklist when writing `credentials_setup.md` for your specific wrapper, not as a copy-paste target.

**Concrete version**: `ima-copilot/references/api_key_setup.md`.
