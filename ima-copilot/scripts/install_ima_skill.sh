#!/usr/bin/env bash
#
# install_ima_skill.sh — Install the upstream Tencent ima-skill to Claude Code,
# Codex, and OpenClaw in one shot.
#
# Flow:
#   1. Download the official zip from ima.qq.com
#   2. Stage it in a temp directory
#   3. Detect which of the three target agents are installed locally
#   4. Delegate to `npx skills add <local-path>` (vercel-labs/skills) in its
#      default symlink mode so that the three agents share a single canonical
#      copy — a repair or upgrade applied once propagates to every agent.
#   5. Clean up the staging dir on exit (safe: vercel skills promotes the
#      first agent's install to canonical and symlinks the rest to it,
#      independent of the staging source)
#
# Re-run safely — every step is idempotent. `npx skills add` will overwrite
# existing ima-skill installs with the new version, and the symlink graph
# gets rebuilt on every run.

set -euo pipefail

IMA_VERSION="${IMA_VERSION:-1.1.2}"
BASE_URL="https://app-dl.ima.qq.com/skills"
STAGING_ROOT="/tmp/ima-copilot-staging"
STAGING_DIR="${STAGING_ROOT}/$(date +%s)-$$"

cleanup() {
  if [ -n "${STAGING_DIR:-}" ] && [ -d "$STAGING_DIR" ]; then
    rm -rf "$STAGING_DIR"
  fi
}
trap cleanup EXIT

usage() {
  cat <<'EOF'
Usage: install_ima_skill.sh [--version <x.y.z>]

Downloads the upstream Tencent ima-skill and installs it globally to the
supported coding agents (Claude Code, Codex, OpenClaw) that are detected on
this machine. Uses vercel-labs/skills CLI (`npx skills add`) as the
distribution mechanism, in vercel's default symlink mode so that a repair or
upgrade applied to any one of the three agent directories propagates through
the symlink graph to every other agent automatically.

Environment overrides:
  IMA_VERSION   Upstream version to install (default: 1.1.2)

Examples:
  install_ima_skill.sh
  install_ima_skill.sh --version 1.1.2
  IMA_VERSION=1.2.0 install_ima_skill.sh

Find the latest upstream version at https://ima.qq.com/agent-interface
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --version)
      IMA_VERSION="$2"
      shift 2
      ;;
    --version=*)
      IMA_VERSION="${1#*=}"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

# Require basic tools
for tool in curl unzip npx; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "✗ Required tool not found on PATH: $tool" >&2
    exit 1
  fi
done

# Require Node.js >= 18 — `npx -y skills add` from vercel-labs/skills needs
# a modern Node runtime. The error is otherwise opaque if it fires on an
# ancient Node version.
if command -v node >/dev/null 2>&1; then
  node_major=$(node --version 2>/dev/null | sed -E 's/^v([0-9]+).*/\1/')
  if [ -n "$node_major" ] && [ "$node_major" -lt 18 ] 2>/dev/null; then
    echo "✗ Node.js 18+ required for 'npx skills add' — found: $(node --version)" >&2
    echo "  Upgrade via your package manager (brew/apt/nvm) and retry." >&2
    exit 1
  fi
fi

echo "▶ Staging upstream ima-skill v${IMA_VERSION}"
mkdir -p "$STAGING_DIR"

ZIP_URL="${BASE_URL}/ima-skills-${IMA_VERSION}.zip"
ZIP_PATH="${STAGING_DIR}/ima-skills.zip"

echo "  Downloading ${ZIP_URL}"
http_code=$(curl -sS -L --fail -o "$ZIP_PATH" -w "%{http_code}" "$ZIP_URL" || echo "000")
if [ "$http_code" != "200" ]; then
  echo "" >&2
  echo "✗ Download failed (HTTP ${http_code})" >&2
  echo "" >&2
  echo "If IMA has released a newer version, pass it explicitly:" >&2
  echo "    IMA_VERSION=x.y.z bash $0" >&2
  echo "" >&2
  echo "or find the latest version at https://ima.qq.com/agent-interface" >&2
  exit 1
fi

actual_size=$(wc -c < "$ZIP_PATH" | tr -d ' ')
echo "  Downloaded ${actual_size} bytes"
if [ "$actual_size" -lt 1000 ]; then
  echo "✗ Downloaded file is suspiciously small — aborting before extraction" >&2
  exit 1
fi

echo "  Extracting…"
unzip -q -o "$ZIP_PATH" -d "$STAGING_DIR"

# Locate the root ima-skill directory inside the extracted archive.
#
# This matters more than it looks. The upstream 1.1.2 archive contains SKILL.md
# at three depths (root, notes/, knowledge-base/) because ISSUE-001 exists —
# notes/SKILL.md and knowledge-base/SKILL.md are documented as "module files"
# but happen to use the same filename as the real root. A naive "first SKILL.md
# we find" strategy will pick up the shallowest one if we're lucky and a
# submodule if we're not, breaking the install non-deterministically.
#
# Resolution: prefer the well-known layout (<staging>/ima-skill/SKILL.md), and
# only fall back to a recursive scan if that layout has changed in a future
# release. The fallback picks the shallowest candidate, which is the root by
# construction of every legal SKILL.md tree.
SKILL_SRC=""
if [ -f "$STAGING_DIR/ima-skill/SKILL.md" ]; then
  SKILL_SRC="$STAGING_DIR/ima-skill"
else
  shallowest_depth=999
  while IFS= read -r candidate; do
    # Count slashes in the relative portion to compare depths uniformly
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
  echo "  Archive contents:" >&2
  find "$STAGING_DIR" -maxdepth 4 -type f -print >&2 || true
  exit 1
fi

echo "  Found root SKILL.md at: ${SKILL_SRC}"

# Detect which target agents are installed. Being present is a proxy for
# "the user wants things installed here"; absence means skip silently rather
# than install anywhere they haven't opted in.
AGENTS=()
[ -d "$HOME/.claude" ]  && AGENTS+=("claude-code")
[ -d "$HOME/.agents" ]  && AGENTS+=("codex")
if [ -d "$HOME/.openclaw" ] || command -v openclaw >/dev/null 2>&1; then
  AGENTS+=("openclaw")
fi

if [ ${#AGENTS[@]} -eq 0 ]; then
  echo "" >&2
  echo "⚠ No supported agent detected on this machine." >&2
  echo "  Looked for: ~/.claude (Claude Code), ~/.agents (Codex), openclaw command." >&2
  echo "  Defaulting to claude-code as the most common case." >&2
  echo "" >&2
  AGENTS=("claude-code")
fi

echo "▶ Targeting agents: ${AGENTS[*]}"

AGENT_FLAGS=()
for a in "${AGENTS[@]}"; do
  AGENT_FLAGS+=("-a" "$a")
done

echo "  Running: npx -y skills add \"${SKILL_SRC}\" -g -y ${AGENT_FLAGS[*]}"
if ! npx -y skills add "$SKILL_SRC" -g -y "${AGENT_FLAGS[@]}"; then
  echo "✗ npx skills add failed" >&2
  echo "  Make sure Node.js is installed and the npm registry is reachable." >&2
  exit 1
fi

echo ""
echo "✓ Upstream ima-skill v${IMA_VERSION} installed successfully"
echo ""
echo "Next steps:"
echo "  1. Configure API credentials"
echo "     Save your Client ID and API Key from https://ima.qq.com/agent-interface"
echo "     into ~/.config/ima/client_id and ~/.config/ima/api_key (mode 600)."
echo ""
echo "  2. Run the diagnostic"
echo "     bash \"\$(dirname \"\$0\")/diagnose.sh\""
echo ""
echo "  3. Let the agent drive repairs"
echo "     The diagnostic flags known upstream issues — rerun via your agent"
echo "     and it will walk you through the fixes, asking consent for each."
