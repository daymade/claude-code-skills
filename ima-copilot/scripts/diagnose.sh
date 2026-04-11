#!/usr/bin/env bash
#
# diagnose.sh — Read-only health check for upstream ima-skill installs.
#
# Prints one status line per check, then a summary.
#
# Exit codes:
#   0 — all checks passed
#   1 — one or more issues need user action
#   2 — diagnostic itself failed (network error, missing tooling)
#
# This script is strictly read-only. It will never modify, create, or delete
# any file outside its own stdout. Safe to run as many times as you want.

set -uo pipefail

PASS=0
WARN=0
FAIL=0

status_ok()   { echo "✅ $1"; PASS=$((PASS + 1)); }
status_warn() { echo "⚠️  $1"; WARN=$((WARN + 1)); }
status_fail() { echo "❌ $1"; FAIL=$((FAIL + 1)); }

echo "=== ima-copilot diagnostic report ==="
echo

# ==========================================================================
# 1. Upstream ima-skill install presence
# ==========================================================================

echo "--- Upstream ima-skill installs ---"

# Agent target path resolution. Each agent has a short list of known
# candidate install paths; the first one with a SKILL.md wins.
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

# Resolve a path to its canonical realpath so we can detect when two agent
# entries point at the same underlying directory via symlink. `npx skills add`
# in its default mode promotes the first agent's install to canonical and
# symlinks the rest to it — reporting issues four times when there are only
# two real files is noisy and confuses the repair step counting.
canonical() {
  python3 -c "import os,sys; print(os.path.realpath(sys.argv[1]))" "$1" 2>/dev/null || echo "$1"
}

CLAUDE_PATH=""
CODEX_PATH=""
OPENCLAW_PATH=""
INSTALLED_AGENTS=""

# Claude Code
if CLAUDE_PATH=$(find_install claude-code \
  "$HOME/.claude/skills/ima-skill"); then
  status_ok "ima-skill installed (claude-code) at $CLAUDE_PATH"
  INSTALLED_AGENTS="$INSTALLED_AGENTS claude-code"
else
  status_warn "ima-skill NOT installed (claude-code) — run install_ima_skill.sh"
fi

# Codex
if CODEX_PATH=$(find_install codex \
  "$HOME/.agents/skills/ima-skill" \
  "$HOME/.codex/skills/ima-skill"); then
  status_ok "ima-skill installed (codex) at $CODEX_PATH"
  INSTALLED_AGENTS="$INSTALLED_AGENTS codex"
else
  status_warn "ima-skill NOT installed (codex) — run install_ima_skill.sh"
fi

# OpenClaw — multiple candidate paths because the standard hasn't stabilized
if OPENCLAW_PATH=$(find_install openclaw \
  "$HOME/.openclaw/skills/ima-skill" \
  "$HOME/.config/openclaw/skills/ima-skill" \
  "$HOME/.local/share/openclaw/skills/ima-skill"); then
  status_ok "ima-skill installed (openclaw) at $OPENCLAW_PATH"
  INSTALLED_AGENTS="$INSTALLED_AGENTS openclaw"
else
  status_warn "ima-skill NOT installed (openclaw) — run install_ima_skill.sh"
fi

# Detect whether multiple agents share the same underlying directory via
# symlink. This matters for the issue scanner: we don't want to report the
# same ISSUE-001 four times when there are really only two files behind
# symlinks.
CLAUDE_REAL=""
CODEX_REAL=""
OPENCLAW_REAL=""
[ -n "$CLAUDE_PATH" ]   && CLAUDE_REAL=$(canonical "$CLAUDE_PATH")
[ -n "$CODEX_PATH" ]    && CODEX_REAL=$(canonical "$CODEX_PATH")
[ -n "$OPENCLAW_PATH" ] && OPENCLAW_REAL=$(canonical "$OPENCLAW_PATH")

# Report sharing if any two agents resolve to the same canonical directory
if [ -n "$CLAUDE_REAL" ] && [ -n "$CODEX_REAL" ] && [ "$CLAUDE_REAL" = "$CODEX_REAL" ]; then
  echo "ℹ️  claude-code and codex share the same install via symlink (canonical: $CLAUDE_REAL)"
fi
if [ -n "$CLAUDE_REAL" ] && [ -n "$OPENCLAW_REAL" ] && [ "$CLAUDE_REAL" = "$OPENCLAW_REAL" ]; then
  echo "ℹ️  claude-code and openclaw share the same install via symlink (canonical: $CLAUDE_REAL)"
fi
if [ -n "$CODEX_REAL" ] && [ -n "$OPENCLAW_REAL" ] && [ "$CODEX_REAL" = "$OPENCLAW_REAL" ] && [ "$CODEX_REAL" != "$CLAUDE_REAL" ]; then
  echo "ℹ️  codex and openclaw share the same install via symlink (canonical: $CODEX_REAL)"
fi

if [ -z "$INSTALLED_AGENTS" ]; then
  echo
  echo "No installs found across any supported agent."
  echo "Start with: bash \"\$(dirname \"\$0\")/install_ima_skill.sh\""
  exit 1
fi

echo

# ==========================================================================
# 2. API credentials presence and liveness
# ==========================================================================

echo "--- API credentials ---"

CLIENT_ID="${IMA_OPENAPI_CLIENTID:-}"
API_KEY="${IMA_OPENAPI_APIKEY:-}"

if [ -z "$CLIENT_ID" ] && [ -f "$HOME/.config/ima/client_id" ]; then
  CLIENT_ID=$(tr -d '\n' < "$HOME/.config/ima/client_id")
fi
if [ -z "$API_KEY" ] && [ -f "$HOME/.config/ima/api_key" ]; then
  API_KEY=$(tr -d '\n' < "$HOME/.config/ima/api_key")
fi

if [ -z "$CLIENT_ID" ] || [ -z "$API_KEY" ]; then
  status_fail "API credentials missing (expected env vars or ~/.config/ima/{client_id,api_key})"
else
  status_ok "API credentials present"

  if ! command -v curl >/dev/null 2>&1; then
    status_warn "curl not on PATH — skipping liveness check"
  else
    response=$(curl -sS -X POST "https://ima.qq.com/openapi/wiki/v1/search_knowledge_base" \
      -H "ima-openapi-clientid: $CLIENT_ID" \
      -H "ima-openapi-apikey: $API_KEY" \
      -H "Content-Type: application/json" \
      -d '{"query": "", "cursor": "", "limit": 1}' 2>/dev/null || true)

    if echo "$response" | grep -q '"code"[[:space:]]*:[[:space:]]*0'; then
      status_ok "API credentials verified by live liveness call"
    elif [ -z "$response" ]; then
      status_fail "API liveness call returned no response (network issue?)"
    else
      status_fail "API liveness call failed — server rejected credentials or returned error"
      # Show a short snippet for debugging without dumping everything
      snippet=$(printf '%s' "$response" | head -c 200)
      echo "    response: $snippet"
    fi
  fi
fi

echo

# ==========================================================================
# 3. Known issue scan
# ==========================================================================

echo "--- Known upstream issues ---"

# ISSUE-001 — submodule SKILL.md missing YAML frontmatter
#
# Symptom: loaders like Codex's ~/.agents scanner skip the submodule SKILL.md
# files and log "missing YAML frontmatter delimited by ---". Claude Code is
# more lenient and usually loads them anyway, but the official design intent
# is still that these files are module documentation, and fixing them removes
# the loader warning universally.
#
# The check has to understand three post-install states:
#   - Untouched upstream: SKILL.md exists, starts with "#" (broken) or "---" (fixed upstream).
#   - Strategy A applied: SKILL.md is renamed to MODULE.md, so SKILL.md no longer exists.
#   - Strategy B applied: SKILL.md exists, now begins with "---".
#
# Return codes:
#   0 — OK (either upstream-original good or Strategy B applied)
#   1 — broken (file exists but lacks frontmatter)
#   2 — submodule not present at all (legitimate for a future upstream layout change)
#   3 — Strategy A applied (renamed to MODULE.md)
check_submodule() {
  local dir="$1"
  local skill_md="$dir/SKILL.md"
  local module_md="$dir/MODULE.md"

  if [ -f "$skill_md" ]; then
    local first_line
    first_line=$(head -n 1 "$skill_md" 2>/dev/null || echo "")
    if [ "$first_line" = "---" ]; then
      return 0
    fi
    return 1
  fi

  if [ -f "$module_md" ]; then
    return 3
  fi

  return 2
}

scan_issue_001() {
  local agent="$1"
  local base="$2"
  local sub dir rc
  for sub in notes knowledge-base; do
    dir="$base/$sub"
    check_submodule "$dir"
    rc=$?
    case "$rc" in
      0) status_ok   "ISSUE-001 clear ($agent: $sub/SKILL.md has frontmatter)" ;;
      3) status_ok   "ISSUE-001 clear ($agent: $sub/MODULE.md — Strategy A applied)" ;;
      2) echo "ℹ️  $agent: $sub submodule not present (post-upstream-layout-change?)" ;;
      *) status_warn "ISSUE-001 TRIGGERED ($agent: $sub/SKILL.md missing YAML frontmatter)" ;;
    esac
  done
}

# Scan each unique canonical directory exactly once. When multiple agents
# share the same underlying install via symlink, scanning one represents all.
SCANNED_REALS=""
scan_agent() {
  local agent="$1"
  local path="$2"
  local real="$3"
  if [ -z "$path" ]; then
    return
  fi
  case " $SCANNED_REALS " in
    *" $real "*)
      # Already scanned via another agent entry
      return
      ;;
  esac
  SCANNED_REALS="$SCANNED_REALS $real"
  scan_issue_001 "$agent" "$path"
}

scan_agent "claude-code" "$CLAUDE_PATH"   "$CLAUDE_REAL"
scan_agent "codex"       "$CODEX_PATH"    "$CODEX_REAL"
scan_agent "openclaw"    "$OPENCLAW_PATH" "$OPENCLAW_REAL"

echo

# ==========================================================================
# 4. Summary and exit code
# ==========================================================================

echo "--- Summary ---"
echo "  ✅ ${PASS} pass   ⚠️  ${WARN} warn   ❌ ${FAIL} fail"
echo

if [ "$FAIL" -gt 0 ] || [ "$WARN" -gt 0 ]; then
  echo "Next step: open references/known_issues.md and walk the agent through"
  echo "the warnings above. Each issue ID maps to a concrete repair procedure."
  exit 1
fi

exit 0
