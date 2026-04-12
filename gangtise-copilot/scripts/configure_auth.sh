#!/usr/bin/env bash
#
# configure_auth.sh — Set up Gangtise OpenAPI credentials + verify against
# the live authentication server + symlink each installed skill's
# scripts/.authorization to the shared XDG config file.
#
# Flow:
#   1. Read accessKey + secretAccessKey (from env vars, from flag, or
#      prompt interactively)
#   2. Write to ~/.config/gangtise/authorization.json with mode 600
#   3. Write ~/.GTS_AUTHORIZATION runtime token for upstream CLI scripts
#   4. Perform a live auth call against open.gangtise.com to verify
#      the credentials actually work (body-shape check, not just HTTP code)
#   5. Scan the canonical install location for installed skills
#   6. Create or refresh each skill's scripts/.authorization as a symlink to
#      the shared XDG file
#
# Re-run safely — every step is idempotent.

set -euo pipefail

XDG_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/gangtise"
AUTH_FILE="${XDG_CONFIG_DIR}/authorization.json"
RUNTIME_TOKEN_FILE="$HOME/.GTS_AUTHORIZATION"
CANONICAL_ROOT="${GANGTISE_COPILOT_HOME:-$HOME/.local/share/gangtise-copilot}"
CANONICAL_SKILLS_DIR="${CANONICAL_ROOT}/skills"

AUTH_ENDPOINT="https://open.gangtise.com/application/auth/oauth/open/loginV2"

# ============================================================================
# Usage
# ============================================================================

usage() {
  cat <<'EOF'
Usage: configure_auth.sh [OPTIONS]

Configure Gangtise OpenAPI credentials and verify against the live server.

Options:
  --access-key KEY      Provide accessKey directly (otherwise prompt or env var)
  --secret-key KEY      Provide secretAccessKey directly
  --verify-only         Skip prompt; just re-run the live verification with
                        the credentials already on disk
  --show                Display the current credential file path and shape
                        (does not print the secret)
  -h, --help            Show this help

Environment variables:
  GANGTISE_ACCESS_KEY          If set, used as the default accessKey
  GANGTISE_SECRET_ACCESS_KEY   If set, used as the default secretAccessKey

Where credentials are stored:
  ~/.config/gangtise/authorization.json   (single source of truth, mode 600)
  ~/.GTS_AUTHORIZATION                    (runtime token for upstream CLI scripts, mode 600)
  Each installed Gangtise skill has a symlink at
  <canonical>/scripts/.authorization → this file.

Rotating credentials:
  Edit ~/.config/gangtise/authorization.json directly, then re-run:
    bash configure_auth.sh --verify-only
EOF
}

# ============================================================================
# Parse flags
# ============================================================================

ACCESS_KEY_ARG=""
SECRET_KEY_ARG=""
VERIFY_ONLY=0
SHOW_ONLY=0

while [ $# -gt 0 ]; do
  case "$1" in
    --access-key)      ACCESS_KEY_ARG="$2"; shift 2 ;;
    --access-key=*)    ACCESS_KEY_ARG="${1#*=}"; shift ;;
    --secret-key)      SECRET_KEY_ARG="$2"; shift 2 ;;
    --secret-key=*)    SECRET_KEY_ARG="${1#*=}"; shift ;;
    --verify-only)     VERIFY_ONLY=1; shift ;;
    --show)            SHOW_ONLY=1; shift ;;
    -h|--help)         usage; exit 0 ;;
    *) echo "✗ unknown argument: $1" >&2; usage >&2; exit 1 ;;
  esac
done

# ============================================================================
# Prerequisite checks
# ============================================================================

if ! command -v curl >/dev/null 2>&1; then
  echo "✗ Required tool not found: curl" >&2
  exit 1
fi

# python3 is used only for JSON parsing of the auth response. If not available,
# we fall back to a grep-based shape check.
HAS_PYTHON=0
if command -v python3 >/dev/null 2>&1; then
  HAS_PYTHON=1
fi

# ============================================================================
# --show mode
# ============================================================================

if [ "$SHOW_ONLY" -eq 1 ]; then
  if [ ! -f "$AUTH_FILE" ]; then
    echo "✗ No credential file at $AUTH_FILE"
    echo "  Run: bash $(basename "$0")  (without --show)"
    exit 1
  fi
  echo "Credential file: $AUTH_FILE"
  echo "Mode:            $(stat -f '%Lp' "$AUTH_FILE" 2>/dev/null || stat -c '%a' "$AUTH_FILE" 2>/dev/null || echo "?")"
  echo "Shape:"
  if [ "$HAS_PYTHON" -eq 1 ]; then
    python3 -c "
import json, sys
with open('$AUTH_FILE') as f:
    d = json.load(f)
for k in d:
    v = d[k]
    if isinstance(v, str) and len(v) > 8:
        v = v[:4] + '...' + v[-4:]
    print(f'  {k}: {v}')
" 2>/dev/null || cat "$AUTH_FILE"
  else
    cat "$AUTH_FILE"
  fi
  exit 0
fi

# ============================================================================
# Gather credentials (flag → env var → interactive prompt)
# ============================================================================

if [ "$VERIFY_ONLY" -eq 1 ]; then
  if [ ! -f "$AUTH_FILE" ]; then
    echo "✗ --verify-only requires $AUTH_FILE to already exist" >&2
    exit 1
  fi
  ACCESS_KEY=""
  SECRET_KEY=""
  # Extract from existing file
  if [ "$HAS_PYTHON" -eq 1 ]; then
    ACCESS_KEY=$(python3 -c "import json; print(json.load(open('$AUTH_FILE')).get('accessKey',''))" 2>/dev/null || true)
    SECRET_KEY=$(python3 -c "import json; print(json.load(open('$AUTH_FILE')).get('secretAccessKey',''))" 2>/dev/null || true)
  fi
  if [ -z "$ACCESS_KEY" ] || [ -z "$SECRET_KEY" ]; then
    echo "✗ Could not extract accessKey/secretAccessKey from $AUTH_FILE" >&2
    echo "  The file may use the long-term-token shape, which can't be verified by re-auth." >&2
    exit 1
  fi
else
  ACCESS_KEY="${ACCESS_KEY_ARG:-${GANGTISE_ACCESS_KEY:-}}"
  SECRET_KEY="${SECRET_KEY_ARG:-${GANGTISE_SECRET_ACCESS_KEY:-}}"

  if [ -z "$ACCESS_KEY" ]; then
    echo "▶ Enter your Gangtise accessKey:"
    echo "  (Get this from your Gangtise account administrator or the Gangtise OpenAPI portal.)"
    read -r ACCESS_KEY
  fi
  if [ -z "$SECRET_KEY" ]; then
    echo "▶ Enter your Gangtise secretAccessKey:"
    # Hide input — the secret should not be echoed to the terminal.
    stty -echo 2>/dev/null || true
    read -r SECRET_KEY
    stty echo 2>/dev/null || true
    echo
  fi

  if [ -z "$ACCESS_KEY" ] || [ -z "$SECRET_KEY" ]; then
    echo "✗ Both accessKey and secretAccessKey are required" >&2
    exit 1
  fi
fi

# ============================================================================
# Live authentication call — verify credentials actually work
# ============================================================================
# This probes the OAuth endpoint, which is the lowest-privilege operation in
# the Gangtise OpenAPI. Passing this proves the keys exist and are valid, but
# does NOT prove the account has `rag` / `data` / `file` scopes. Those are
# checked separately in diagnose.sh.

echo "▶ Verifying credentials against $AUTH_ENDPOINT"

payload=$(printf '{"accessKey":"%s","secretAccessKey":"%s"}' "$ACCESS_KEY" "$SECRET_KEY")

response=$(curl -sS -X POST "$AUTH_ENDPOINT" \
  -H "Content-Type: application/json" \
  --data "$payload" \
  --max-time 20 2>&1) || {
  echo "✗ Network error calling $AUTH_ENDPOINT" >&2
  echo "  Response: $response" >&2
  exit 1
}

# Shape check: Gangtise returns 200 HTTP with a JSON body whose `code` field
# is "000000" on success and something else on failure. Matching on body shape
# (not HTTP status) is the only reliable check because the server returns 200
# even for invalid credentials.
success=0
user_name=""
uid=""
access_token=""

if echo "$response" | grep -q '"code":"000000"'; then
  success=1
  if [ "$HAS_PYTHON" -eq 1 ]; then
    user_name=$(python3 -c "
import json, sys
try:
    d = json.loads('''$response''')
    print(d.get('data',{}).get('userName',''))
except Exception:
    pass
" 2>/dev/null || true)
    uid=$(python3 -c "
import json, sys
try:
    d = json.loads('''$response''')
    print(d.get('data',{}).get('uid',''))
except Exception:
    pass
" 2>/dev/null || true)
    access_token=$(python3 -c "
import json, sys
try:
    d = json.loads('''$response''')
    token = d.get('data',{}).get('accessToken','')
    print(token.replace('Bearer ', '', 1))
except Exception:
    pass
" 2>/dev/null || true)
  fi
fi

if [ "$success" -ne 1 ]; then
  echo "✗ Authentication rejected by Gangtise server" >&2
  echo "" >&2
  echo "Server response:" >&2
  echo "  $response" >&2
  echo "" >&2
  echo "Common causes:" >&2
  echo "  - accessKey typo (most common)" >&2
  echo "  - secretAccessKey typo" >&2
  echo "  - Keys revoked or expired on the Gangtise side" >&2
  echo "  - Account suspended / not provisioned for OpenAPI" >&2
  exit 1
fi

echo "✓ Authentication successful"
[ -n "$user_name" ] && echo "  userName: $user_name"
[ -n "$uid" ]       && echo "  uid:      $uid"

# ============================================================================
# Write the runtime token file expected by upstream CLI scripts
# ============================================================================

if [ -n "$access_token" ]; then
  tmp_runtime=$(mktemp "${RUNTIME_TOKEN_FILE}.XXXXXX")
  printf "%s" "$access_token" > "$tmp_runtime"
  command mv "$tmp_runtime" "$RUNTIME_TOKEN_FILE"
  chmod 600 "$RUNTIME_TOKEN_FILE"
  echo "✓ Runtime token written to $RUNTIME_TOKEN_FILE (mode 600)"
else
  echo "⚠ Could not extract accessToken for $RUNTIME_TOKEN_FILE; CLI scripts may fail" >&2
fi

# ============================================================================
# Write the shared credential file (mode 600, XDG location)
# ============================================================================

if [ "$VERIFY_ONLY" -eq 0 ]; then
  mkdir -p "$XDG_CONFIG_DIR"
  chmod 700 "$XDG_CONFIG_DIR"

  # Idempotent write — use a temp file so partial writes don't corrupt an
  # existing credential file.
  tmpfile=$(mktemp "${AUTH_FILE}.XXXXXX")
  cat > "$tmpfile" <<EOF
{
  "accessKey": "$ACCESS_KEY",
  "secretAccessKey": "$SECRET_KEY"
}
EOF
  command mv "$tmpfile" "$AUTH_FILE"
  chmod 600 "$AUTH_FILE"

  echo "✓ Credentials written to $AUTH_FILE (mode 600)"
fi

# ============================================================================
# Symlink every installed Gangtise skill's scripts/.authorization
# ============================================================================

if [ ! -d "$CANONICAL_SKILLS_DIR" ]; then
  echo ""
  echo "⚠ No canonical skill install found at $CANONICAL_SKILLS_DIR"
  echo "  Run install_gangtise.sh first to install Gangtise skills, then re-run this." >&2
  exit 0
fi

linked_count=0
for skill_dir in "$CANONICAL_SKILLS_DIR"/gangtise-*; do
  [ -d "$skill_dir" ] || continue
  scripts_dir="$skill_dir/scripts"
  if [ ! -d "$scripts_dir" ]; then
    # Some bundle-only skills may not have a scripts/ subdirectory.
    continue
  fi

  auth_link="$scripts_dir/.authorization"

  # Idempotent replace — always remove any existing file/symlink before
  # creating a fresh link. This handles the case where the user manually
  # wrote an .authorization file and now wants the wrapper to manage it.
  if [ -e "$auth_link" ] || [ -L "$auth_link" ]; then
    # Back up non-symlink files before replacing.
    if [ ! -L "$auth_link" ]; then
      backup_dir="/tmp/gangtise-copilot-backups/$(date +%Y%m%d-%H%M%S)"
      mkdir -p "$backup_dir"
      command cp "$auth_link" "$backup_dir/$(basename "$skill_dir")-authorization.bak"
      echo "  ℹ Backed up manual $(basename "$skill_dir")/.authorization → $backup_dir"
    fi
    command rm -f "$auth_link"
  fi

  command ln -s "$AUTH_FILE" "$auth_link"
  linked_count=$((linked_count + 1))
done

echo "✓ Symlinked $linked_count skill(s) to shared credential file"
echo ""
echo "Next step: verify the full install with"
echo "  bash $(dirname "$0")/diagnose.sh"
