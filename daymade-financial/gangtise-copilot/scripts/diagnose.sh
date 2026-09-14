#!/usr/bin/env bash
#
# diagnose.sh — Read-only health check for Gangtise Copilot installs.
#
# Prints one status line per check, then a summary.
#
# Exit codes:
#   0 — all checks passed
#   1 — one or more issues need user action
#   2 — diagnostic itself failed (network error, missing tooling)
#
# This script is strictly read-only. It never modifies files.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
CLASSIFIER="${SCRIPT_DIR}/classify_response.py"

CANONICAL_ROOT="${GANGTISE_COPILOT_HOME:-$HOME/.local/share/gangtise-copilot}"
CANONICAL_SKILLS_DIR="${CANONICAL_ROOT}/skills"
XDG_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/gangtise"
AUTH_FILE="${XDG_CONFIG_DIR}/authorization.json"
RUNTIME_TOKEN_FILE="$HOME/.GTS_AUTHORIZATION"

AUTH_ENDPOINT="https://open.gangtise.com/application/auth/oauth/open/loginV2"
RAG_ENDPOINT="https://open.gangtise.com/application/open-data/ai/search/knowledge_base"

PASS=0; WARN=0; FAIL=0
DIAG_ERROR=0

status_ok()   { echo "✅ $1"; PASS=$((PASS + 1)); }
status_warn() { echo "⚠️  $1"; WARN=$((WARN + 1)); }
status_fail() { echo "❌ $1"; FAIL=$((FAIL + 1)); }
status_diag_fail() { echo "❌ $1"; FAIL=$((FAIL + 1)); DIAG_ERROR=1; }
status_info() { echo "ℹ️  $1"; }

diagnostic_fields() {
  local http_status="$1" code="$2" error_type="$3" trace_id="$4"
  local fields="http_status=${http_status}"
  [ "$code" = "-" ] || fields="${fields} code=${code}"
  [ "$error_type" = "-" ] || fields="${fields} errorType=${error_type}"
  [ "$trace_id" = "-" ] || fields="${fields} traceId=${trace_id}"
  printf '%s' "$fields"
}

echo "=== Gangtise Copilot diagnostic report ==="
echo

# ============================================================================
# Prerequisites
# ============================================================================

echo "--- Prerequisites ---"
for tool in curl; do
  if command -v "$tool" >/dev/null 2>&1; then
    status_ok "$tool installed"
  else
    status_fail "$tool NOT installed — Gangtise skills need this to call the API"
  fi
done

HAS_PYTHON=0
if command -v python3 >/dev/null 2>&1; then
  HAS_PYTHON=1
  status_ok "python3 installed ($(python3 --version 2>&1))"
else
  status_warn "python3 NOT installed — Gangtise skills use python scripts; install python3"
fi

echo

# ============================================================================
# Canonical install location
# ============================================================================

echo "--- Canonical install ---"
if [ -d "$CANONICAL_SKILLS_DIR" ]; then
  installed_count=$(find "$CANONICAL_SKILLS_DIR" -maxdepth 1 -type d -name "gangtise-*" 2>/dev/null | wc -l | tr -d ' ')
  status_ok "Canonical skills dir: $CANONICAL_SKILLS_DIR ($installed_count skill(s))"
else
  status_fail "Canonical skills dir not found: $CANONICAL_SKILLS_DIR"
  status_info "Run: bash install_gangtise.sh"
fi

echo

# ============================================================================
# Per-agent symlinks — which agents have been configured
# ============================================================================

echo "--- Agent installs ---"

AGENTS=()
[ -d "$HOME/.claude/skills" ]   && AGENTS+=("claude-code:$HOME/.claude/skills")
[ -d "$HOME/.agents/skills" ]   && AGENTS+=("codex:$HOME/.agents/skills")

for openclaw_path in "$HOME/.openclaw/skills" "$HOME/.config/openclaw/skills" "$HOME/.local/share/openclaw/skills"; do
  if [ -d "$openclaw_path" ]; then
    AGENTS+=("openclaw:$openclaw_path")
    break
  fi
done

if [ ${#AGENTS[@]} -eq 0 ]; then
  status_warn "No supported agent skills directory detected"
  status_info "Supported: ~/.claude/skills (Claude Code), ~/.openclaw/skills (OpenClaw), ~/.agents/skills (Codex)"
fi

for entry in "${AGENTS[@]}"; do
  agent="${entry%%:*}"
  skills_dir="${entry#*:}"
  linked_count=0
  broken_count=0
  for link in "$skills_dir"/gangtise-*; do
    [ -e "$link" ] || continue
    if [ -L "$link" ]; then
      target=$(readlink "$link" 2>/dev/null || echo "")
      if [ -d "$target" ]; then
        linked_count=$((linked_count + 1))
      else
        broken_count=$((broken_count + 1))
      fi
    else
      # Non-symlink install — either a manual install or a pre-wrapper install
      linked_count=$((linked_count + 1))
    fi
  done
  if [ "$linked_count" -gt 0 ]; then
    status_ok "$agent: $linked_count Gangtise skill(s) at $skills_dir"
  else
    status_warn "$agent: no Gangtise skills installed at $skills_dir"
  fi
  if [ "$broken_count" -gt 0 ]; then
    status_fail "$agent: $broken_count broken symlink(s) — re-run install_gangtise.sh to repair"
  fi
done

echo

# ============================================================================
# Credentials file
# ============================================================================

echo "--- Credentials ---"

if [ ! -f "$AUTH_FILE" ]; then
  status_fail "Credential file missing: $AUTH_FILE"
  status_info "Run: bash configure_auth.sh"
else
  mode=""
  if stat -f '%Lp' "$AUTH_FILE" >/dev/null 2>&1; then
    mode=$(stat -f '%Lp' "$AUTH_FILE")
  else
    mode=$(stat -c '%a' "$AUTH_FILE" 2>/dev/null || echo "?")
  fi
  if [ "$mode" = "600" ]; then
    status_ok "Credential file present with mode 600: $AUTH_FILE"
  else
    status_warn "Credential file has mode $mode (expected 600): $AUTH_FILE"
    status_info "Fix: chmod 600 $AUTH_FILE"
  fi

  # Verify the credential file structure
  if [ "$HAS_PYTHON" -eq 1 ]; then
    shape=$(python3 -c "
import json, sys
try:
    d = json.load(open('$AUTH_FILE'))
    if 'long-term-token' in d:
        print('long-term-token')
    elif 'accessKey' in d and 'secretAccessKey' in d:
        print('accessKey+secretAccessKey')
    else:
        print('unknown')
except Exception as e:
    print('invalid')
" 2>/dev/null || echo "invalid")
    case "$shape" in
      long-term-token)
        status_ok "Credential shape: long-term-token"
        ;;
      accessKey+secretAccessKey)
        status_ok "Credential shape: accessKey + secretAccessKey"
        ;;
      invalid)
        status_fail "Credential file is not valid JSON — fix with 'configure_auth.sh'"
        ;;
      unknown)
        status_warn "Credential file has unknown shape (neither long-term-token nor accessKey/secretAccessKey)"
        ;;
    esac
  fi
fi

echo

# ============================================================================
# Runtime token file used by upstream CLI scripts
# ============================================================================

echo "--- Runtime token file ---"

if [ -f "$RUNTIME_TOKEN_FILE" ]; then
  mode=""
  if stat -f '%Lp' "$RUNTIME_TOKEN_FILE" >/dev/null 2>&1; then
    mode=$(stat -f '%Lp' "$RUNTIME_TOKEN_FILE")
  else
    mode=$(stat -c '%a' "$RUNTIME_TOKEN_FILE" 2>/dev/null || echo "?")
  fi
  if [ "$mode" = "600" ]; then
    status_ok "Runtime token file present with mode 600: $RUNTIME_TOKEN_FILE"
  else
    status_warn "Runtime token file has mode $mode (expected 600): $RUNTIME_TOKEN_FILE"
    status_info "Fix: chmod 600 $RUNTIME_TOKEN_FILE"
  fi
else
  status_warn "Runtime token file missing: $RUNTIME_TOKEN_FILE"
  status_info "Run: bash configure_auth.sh --verify-only"
fi

echo

# ============================================================================
# Per-skill .authorization symlink integrity
# ============================================================================

echo "--- Per-skill .authorization symlinks ---"

if [ -d "$CANONICAL_SKILLS_DIR" ]; then
  correct=0
  missing=0
  wrong_target=0
  for skill_dir in "$CANONICAL_SKILLS_DIR"/gangtise-*; do
    [ -d "$skill_dir" ] || continue
    scripts_dir="$skill_dir/scripts"
    [ -d "$scripts_dir" ] || continue
    auth_link="$scripts_dir/.authorization"

    if [ -L "$auth_link" ]; then
      target=$(readlink "$auth_link" 2>/dev/null || echo "")
      if [ "$target" = "$AUTH_FILE" ]; then
        correct=$((correct + 1))
      else
        wrong_target=$((wrong_target + 1))
      fi
    elif [ -f "$auth_link" ]; then
      # Manual file — not managed by wrapper, but functional
      correct=$((correct + 1))
    else
      missing=$((missing + 1))
    fi
  done

  if [ "$correct" -gt 0 ]; then
    status_ok "$correct skill(s) have .authorization configured"
  fi
  if [ "$missing" -gt 0 ]; then
    status_warn "$missing skill(s) missing .authorization — run configure_auth.sh"
  fi
  if [ "$wrong_target" -gt 0 ]; then
    status_warn "$wrong_target skill(s) point at the wrong auth file — run configure_auth.sh to refresh"
  fi
else
  status_info "Skip (canonical install missing)"
fi

echo

# ============================================================================
# Liveness check 1: OAuth endpoint (proves credentials are valid)
# ============================================================================

echo "--- Live credential verification ---"

if [ ! -f "$AUTH_FILE" ]; then
  status_info "Skip (credential file missing)"
elif [ "$HAS_PYTHON" -ne 1 ]; then
  status_info "Skip (python3 not available — cannot parse credential file)"
else
  if [ ! -f "$CLASSIFIER" ]; then
    status_diag_fail "Response classifier missing: $CLASSIFIER"
  fi
  ACCESS_KEY=$(python3 -c "import json; print(json.load(open('$AUTH_FILE')).get('accessKey',''))" 2>/dev/null || echo "")
  SECRET_KEY=$(python3 -c "import json; print(json.load(open('$AUTH_FILE')).get('secretAccessKey',''))" 2>/dev/null || echo "")

  if [ -z "$ACCESS_KEY" ] || [ -z "$SECRET_KEY" ]; then
    status_info "Skip (credential file uses long-term-token shape — cannot re-auth for liveness check)"
  else
    payload=$(printf '{"accessKey":"%s","secretAccessKey":"%s"}' "$ACCESS_KEY" "$SECRET_KEY")
    response=$(curl -sS -X POST "$AUTH_ENDPOINT" \
      -H "Content-Type: application/json" \
      --data "$payload" \
      --max-time 20 \
      -w $'\n__HTTP_STATUS__:%{http_code}' 2>/dev/null)
    curl_rc=$?

    if [ "$curl_rc" -ne 0 ] || [[ "$response" != *$'\n__HTTP_STATUS__:'* ]]; then
      status_diag_fail "Cannot reach Gangtise auth server — network or firewall issue"
    elif [ ! -f "$CLASSIFIER" ]; then
      :
    else
      auth_http="${response##*$'\n__HTTP_STATUS__:'}"
      auth_body="${response%$'\n__HTTP_STATUS__:'*}"
      IFS=$'\t' read -r auth_state auth_category _ auth_code auth_error_type auth_trace_id auth_message _ auth_missing < <(
        printf '%s' "$auth_body" | python3 "$CLASSIFIER" auth --http-status "$auth_http"
      )
    if [ "$auth_state" = "success" ]; then
      status_ok "OAuth liveness (scope: auth) — credentials accepted"
      if [ "$auth_missing" != "-" ]; then
        status_info "Auth response omitted optional headers: $auth_missing (accessToken remains usable)"
      fi

      # Extract token for the next liveness check
      TOKEN=$(printf '%s' "$auth_body" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["data"]["accessToken"])' 2>/dev/null || echo "")
      UID_HEADER=$(printf '%s' "$auth_body" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["data"].get("uid", ""))' 2>/dev/null || echo "")
      TENANT_HEADER=$(printf '%s' "$auth_body" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["data"].get("tenantId", ""))' 2>/dev/null || echo "")
      PRODUCT_HEADER=$(printf '%s' "$auth_body" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["data"].get("productCode", ""))' 2>/dev/null || echo "")

      # ================================================================
      # Liveness check 2: RAG endpoint (proves 'rag' scope works —
      # this is the scope most Gangtise skills need)
      # ================================================================
      if [ -n "$TOKEN" ]; then
        rag_args=(-H "Authorization: $TOKEN" -H "Content-Type: application/json")
        [ -z "$UID_HEADER" ] || rag_args+=(-H "uid: $UID_HEADER")
        [ -z "$TENANT_HEADER" ] || rag_args+=(-H "tenantid: $TENANT_HEADER")
        [ -z "$PRODUCT_HEADER" ] || rag_args+=(-H "productcode: $PRODUCT_HEADER")
        rag_response=$(curl -sS -X POST "$RAG_ENDPOINT" \
          "${rag_args[@]}" \
          --data '{"query":"test","top":1}' \
          --max-time 20 \
          -w $'\n__HTTP_STATUS__:%{http_code}' 2>/dev/null)
        rag_curl_rc=$?

        if [ "$rag_curl_rc" -ne 0 ] || [[ "$rag_response" != *$'\n__HTTP_STATUS__:'* ]]; then
          status_diag_fail "Cannot reach RAG endpoint — network issue on scoped liveness check"
        else
          rag_http="${rag_response##*$'\n__HTTP_STATUS__:'}"
          rag_body="${rag_response%$'\n__HTTP_STATUS__:'*}"
          IFS=$'\t' read -r rag_state rag_category _ rag_code rag_error_type rag_trace_id rag_message rag_empty _ < <(
            printf '%s' "$rag_body" | python3 "$CLASSIFIER" rag --http-status "$rag_http"
          )
          rag_meta=$(diagnostic_fields "$rag_http" "$rag_code" "$rag_error_type" "$rag_trace_id")
          if [ "$rag_state" = "success" ] && [ "$rag_empty" = "true" ]; then
            status_ok "RAG liveness (scope: rag) — reachable; query returned 0 results [$rag_meta]"
          elif [ "$rag_state" = "success" ]; then
            status_ok "RAG liveness (scope: rag) — reachable [$rag_meta]"
          elif [ "$rag_category" = "quota" ]; then
            status_fail "RAG rejected with a quota/entitlement response [$rag_meta]"
          elif [ "$rag_category" = "permission" ]; then
            status_fail "RAG permission denied [$rag_meta]"
          elif [ "$rag_category" = "auth" ]; then
            status_fail "RAG authentication rejected [$rag_meta]"
          else
            status_fail "RAG request failed (category=$rag_category) [$rag_meta]"
          fi
        fi
      fi
    else
      auth_meta=$(diagnostic_fields "$auth_http" "$auth_code" "$auth_error_type" "$auth_trace_id")
      if [ "$auth_category" = "auth" ]; then
        status_fail "Credentials rejected by Gangtise auth server [$auth_meta]"
        status_info "Run: bash configure_auth.sh --verify-only after correcting the credential source"
      elif [ "$auth_category" = "permission" ]; then
        status_fail "Gangtise auth endpoint denied permission [$auth_meta]"
      elif [ "$auth_category" = "response" ]; then
        status_diag_fail "Gangtise auth endpoint returned a malformed response [$auth_meta]"
      else
        status_fail "Gangtise auth request failed (category=$auth_category) [$auth_meta]"
      fi
    fi
    fi
  fi
fi

echo

# ============================================================================
# Summary
# ============================================================================

echo "--- Summary ---"
echo "  ✅ ${PASS} pass   ⚠️  ${WARN} warn   ❌ ${FAIL} fail"
echo

if [ "$DIAG_ERROR" -gt 0 ]; then
  echo "The diagnostic could not complete. Resolve the diagnostic error, then re-run diagnose.sh."
  exit 2
fi

if [ "$FAIL" -gt 0 ]; then
  echo "Next step: fix the ❌ items above, then re-run diagnose.sh."
  echo "If you're not sure what a specific item means, check references/known_issues.md"
  exit 1
fi

if [ "$WARN" -gt 0 ]; then
  echo "Warnings are non-blocking, but the affected capabilities may not work."
  echo "Review the ⚠️ items above and follow the suggested fix, or ignore if you're"
  echo "aware of why they apply to your install."
  exit 1
fi

echo "All checks passed. Gangtise Copilot install is healthy."
exit 0
