#!/usr/bin/env bash
#
# install_gangtise.sh — Install the Gangtise (岗底斯投研) OpenAPI skill suite to
# detected local agents (Claude Code / OpenClaw / Codex).
#
# Flow:
#   1. Parse flags (--preset / --only / --target / --no-openclaw)
#   2. Detect which target agents are installed locally
#   3. Download 4 archives from the official Gangtise OBS bucket:
#        - gangtise-skills-client.zip  (5 skills: data-client, kb-client,
#          file-client, file-client-no-download, stockpool-client)
#        - gangtise-research.zip        (10 research workflow skills)
#        - gangtise-skills.zip          (3 legacy minimal skills)
#        - gangtise-web-client.zip      (1 standalone)
#   4. Extract to a staging directory
#   5. Select the skills the preset / --only list asks for
#   6. For each selected skill, link or copy it into each detected agent's
#      skills directory using a shared canonical install location.
#   7. Clean up the staging dir on exit
#
# Re-run safely — every step is idempotent.
#
# Distilled from a real discovery session (April 2026) that enumerated the
# Gangtise skill ecosystem by hand. There are no upstream bugs to fix — the
# friction this script removes is the 5-round enumeration process required to
# discover all 19 skills in the first place, plus the orchestration work of
# downloading 4 archives and distributing 19 skill directories.

set -euo pipefail

# ============================================================================
# Configuration
# ============================================================================

BASE_URL="https://gts-download.obs.myhuaweicloud.com/skills"
STAGING_ROOT="/tmp/gangtise-copilot-staging"
STAGING_DIR="${STAGING_ROOT}/$(date +%s)-$$"
CANONICAL_ROOT="${GANGTISE_COPILOT_HOME:-$HOME/.local/share/gangtise-copilot}"
CANONICAL_SKILLS_DIR="${CANONICAL_ROOT}/skills"

# ============================================================================
# Bundle map — what each archive contains (canonical source of truth)
# ============================================================================

# Format: <bundle-zip-name>:<skill1>,<skill2>,...
BUNDLES=(
  "gangtise-skills-client:gangtise-data-client,gangtise-file-client,gangtise-file-client-no-download,gangtise-kb-client,gangtise-stockpool-client"
  "gangtise-research:gangtise-announcement-digest,gangtise-data-processor,gangtise-event-review,gangtise-interview-outline,gangtise-opinion-pk,gangtise-opinion-summarizer,gangtise-stock-research,gangtise-stock-selector,gangtise-thematic-research,gangtise-wechat-summary"
  "gangtise-skills:gangtise-data,gangtise-file,gangtise-kb"
  "gangtise-web-client:gangtise-web-client"
)

# Presets — which skills each mode installs
PRESET_FULL="gangtise-data-client gangtise-file-client gangtise-file-client-no-download gangtise-kb-client gangtise-stockpool-client gangtise-announcement-digest gangtise-data-processor gangtise-event-review gangtise-interview-outline gangtise-opinion-pk gangtise-opinion-summarizer gangtise-stock-research gangtise-stock-selector gangtise-thematic-research gangtise-wechat-summary gangtise-data gangtise-file gangtise-kb gangtise-web-client"

PRESET_WORKSHOP="gangtise-data-client gangtise-kb-client gangtise-file-client gangtise-web-client gangtise-stock-research gangtise-opinion-pk gangtise-announcement-digest"

PRESET_MINIMAL="gangtise-data gangtise-file gangtise-kb"

# ============================================================================
# Cleanup trap
# ============================================================================

cleanup() {
  if [ -n "${STAGING_DIR:-}" ] && [ -d "$STAGING_DIR" ]; then
    rm -rf "$STAGING_DIR"
  fi
}
trap cleanup EXIT

# ============================================================================
# Usage
# ============================================================================

usage() {
  cat <<'EOF'
Usage: install_gangtise.sh [OPTIONS]

Install the Gangtise OpenAPI skill suite to detected local agents.

Options:
  --preset MODE       Install preset: full (default) | workshop | minimal
                        full     — all 19 skills
                        workshop — 7 skills for investor Workshop Demo 1+2
                        minimal  — 3 skills from the legacy minimal line
  --only LIST         Comma-separated list of skill names to install (overrides
                      --preset). Example: --only gangtise-data-client,gangtise-kb-client
  --target AGENT      Force a single target agent: claude-code | openclaw | codex
                      Default: install to every detected agent.
  --no-openclaw       Skip OpenClaw even if detected.
  --list-skills       List all known Gangtise skills and exit.
  -h, --help          Show this help and exit.

Examples:
  bash install_gangtise.sh                           # Full install, all detected agents
  bash install_gangtise.sh --preset workshop          # Workshop 7 skills
  bash install_gangtise.sh --only gangtise-data-client,gangtise-kb-client
  bash install_gangtise.sh --target claude-code      # Only Claude Code
EOF
}

# ============================================================================
# Parse flags
# ============================================================================

PRESET="full"
ONLY_LIST=""
FORCE_TARGET=""
SKIP_OPENCLAW=0

while [ $# -gt 0 ]; do
  case "$1" in
    --preset)      PRESET="$2"; shift 2 ;;
    --preset=*)    PRESET="${1#*=}"; shift ;;
    --only)        ONLY_LIST="$2"; shift 2 ;;
    --only=*)      ONLY_LIST="${1#*=}"; shift ;;
    --target)      FORCE_TARGET="$2"; shift 2 ;;
    --target=*)    FORCE_TARGET="${1#*=}"; shift ;;
    --no-openclaw) SKIP_OPENCLAW=1; shift ;;
    --list-skills)
      echo "Known Gangtise skills (19 total):"
      echo
      echo "  Data layer (6):"
      echo "    gangtise-data-client            — Full data skill (9 capabilities, supports 简称)"
      echo "    gangtise-data                   — Legacy minimal data skill (4 capabilities, requires 标准代码)"
      echo "    gangtise-kb-client              — Full knowledge base semantic search"
      echo "    gangtise-kb                     — Legacy minimal KB search"
      echo "    gangtise-file-client            — Full file index (18 scripts)"
      echo "    gangtise-file                   — Legacy minimal file index (11 scripts)"
      echo
      echo "  Web layer (1):"
      echo "    gangtise-web-client             — Gangtise's own public web search"
      echo
      echo "  Utility (2, only distributed inside gangtise-skills-client bundle):"
      echo "    gangtise-stockpool-client       — Stock pool CRUD + constituent management"
      echo "    gangtise-file-client-no-download — file-client variant with downloads disabled"
      echo
      echo "  Research workflows (10):"
      echo "    gangtise-stock-research         — Individual stock research L1-L4"
      echo "    gangtise-opinion-pk             — Adversarial opinion analysis"
      echo "    gangtise-thematic-research      — Sector / theme research"
      echo "    gangtise-stock-selector         — Stock screening methodology"
      echo "    gangtise-event-review           — Market event post-mortem (800-1000 字)"
      echo "    gangtise-interview-outline      — Company interview outline generator"
      echo "    gangtise-announcement-digest    — Announcement tracking + digest"
      echo "    gangtise-opinion-summarizer     — Chief analyst opinion digest"
      echo "    gangtise-wechat-summary         — WeChat group → investment daily"
      echo "    gangtise-data-processor         — Data processing methodology guide"
      exit 0
      ;;
    -h|--help) usage; exit 0 ;;
    *) echo "✗ unknown argument: $1" >&2; usage >&2; exit 1 ;;
  esac
done

# ============================================================================
# Resolve requested skill list
# ============================================================================

if [ -n "$ONLY_LIST" ]; then
  # --only takes precedence over --preset
  REQUESTED=$(echo "$ONLY_LIST" | tr ',' ' ')
else
  case "$PRESET" in
    full)     REQUESTED="$PRESET_FULL" ;;
    workshop) REQUESTED="$PRESET_WORKSHOP" ;;
    minimal)  REQUESTED="$PRESET_MINIMAL" ;;
    *) echo "✗ unknown preset: $PRESET (valid: full, workshop, minimal)" >&2; exit 1 ;;
  esac
fi

REQUESTED=$(echo "$REQUESTED" | tr -s ' ')

# ============================================================================
# Prerequisite checks — fail fast with actionable messages
# ============================================================================

for tool in curl unzip; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "✗ Required tool not found on PATH: $tool" >&2
    echo "  Install via your package manager (brew install $tool, apt install $tool, etc.)" >&2
    exit 1
  fi
done

# ============================================================================
# Target agent detection
# ============================================================================

AGENTS=()

detect_agents() {
  local a
  if [ -n "$FORCE_TARGET" ]; then
    AGENTS=("$FORCE_TARGET")
    return
  fi
  [ -d "$HOME/.claude" ]   && AGENTS+=("claude-code")
  [ -d "$HOME/.agents" ]   && AGENTS+=("codex")
  if [ "$SKIP_OPENCLAW" -eq 0 ]; then
    if [ -d "$HOME/.openclaw" ] || command -v openclaw >/dev/null 2>&1; then
      AGENTS+=("openclaw")
    fi
  fi
  if [ ${#AGENTS[@]} -eq 0 ]; then
    # Zero-agents fallback — default to claude-code with a loud warning.
    # Alternative strategies considered:
    #   (a) Abort with a "nothing to install into" error — too strict; a user
    #       who just installed Claude Code and hasn't restarted their shell
    #       might hit this and be confused.
    #   (b) Silently install nothing — most surprising, hardest to debug.
    #   (c) Default to claude-code after explaining what we looked for ← chosen
    echo "" >&2
    echo "⚠ No supported agent detected. Looked for:" >&2
    echo "    ~/.claude     (Claude Code)" >&2
    echo "    ~/.openclaw   (OpenClaw)" >&2
    echo "    ~/.agents     (Codex)" >&2
    echo "  Defaulting to claude-code as the most common install target." >&2
    echo "  If claude-code isn't installed either, re-run after installing it, or pass --target <agent>." >&2
    echo "" >&2
    AGENTS=("claude-code")
  fi
}

agent_skills_dir() {
  local agent="$1"
  case "$agent" in
    claude-code) echo "$HOME/.claude/skills" ;;
    codex)       echo "$HOME/.agents/skills" ;;
    openclaw)
      # OpenClaw's skill directory layout has not fully stabilized — try a
      # few candidate paths in order and return the first existing one.
      # If none exist yet, default to ~/.openclaw/skills/ (most common).
      local p
      for p in "$HOME/.openclaw/skills" "$HOME/.config/openclaw/skills" "$HOME/.local/share/openclaw/skills"; do
        if [ -d "$p" ]; then echo "$p"; return; fi
      done
      echo "$HOME/.openclaw/skills"
      ;;
    *) echo "$HOME/.claude/skills" ;;
  esac
}

detect_agents

echo "▶ Target agent(s): ${AGENTS[*]}"
echo "▶ Requested skills (preset=$PRESET): $(echo $REQUESTED | wc -w | tr -d ' ') skill(s)"

# ============================================================================
# Download archives
# ============================================================================

download_bundle() {
  local bundle_name="$1"
  local zip_url="${BASE_URL}/${bundle_name}.zip"
  local zip_path="${STAGING_DIR}/${bundle_name}.zip"

  echo "  ↓ ${bundle_name}.zip"
  local http_code
  http_code=$(curl -sS -L --fail -o "$zip_path" -w "%{http_code}" "$zip_url" 2>/dev/null || echo "000")
  if [ "$http_code" != "200" ]; then
    echo "" >&2
    echo "✗ Download failed (HTTP ${http_code}) for ${zip_url}" >&2
    echo "  This usually means the Gangtise OBS bucket has moved or renamed the file." >&2
    echo "  Report this to the gangtise-copilot maintainer — the bundle list may be out of date." >&2
    return 1
  fi

  # Size sanity check — Huawei Cloud OBS sometimes returns "200" with an HTML
  # error body when authentication/region routing fails. Reject tiny downloads
  # before extraction.
  local actual_size
  actual_size=$(wc -c < "$zip_path" | tr -d ' ')
  if [ "$actual_size" -lt 1000 ]; then
    echo "✗ Downloaded $bundle_name.zip is suspiciously small (${actual_size}B) — aborting" >&2
    return 1
  fi

  unzip -q -o "$zip_path" -d "$STAGING_DIR"
}

mkdir -p "$STAGING_DIR"

echo "▶ Staging to $STAGING_DIR"

# Figure out which bundles we actually need based on REQUESTED
NEEDED_BUNDLES=""
for line in "${BUNDLES[@]}"; do
  local_bundle="${line%%:*}"
  local_contents="${line#*:}"
  local_contents_sp=$(echo "$local_contents" | tr ',' ' ')
  for req in $REQUESTED; do
    for cont in $local_contents_sp; do
      if [ "$req" = "$cont" ]; then
        case " $NEEDED_BUNDLES " in
          *" $local_bundle "*) ;;
          *) NEEDED_BUNDLES="$NEEDED_BUNDLES $local_bundle" ;;
        esac
      fi
    done
  done
done

for b in $NEEDED_BUNDLES; do
  download_bundle "$b"
done

# ============================================================================
# Locate each requested skill in the staging directory
# ============================================================================

# After unzipping, each skill's files live at one of these layouts inside
# $STAGING_DIR (the layout depends on whether the zip is a bundle or a
# standalone):
#   - $STAGING_DIR/<skill-name>/SKILL.md                   (most bundles)
#   - $STAGING_DIR/<bundle-name>/<skill-name>/SKILL.md     (some bundles)
# We scan for SKILL.md files and index them by directory name.

locate_skill_src() {
  local skill_name="$1"
  # Prefer the direct layout first, then fall back to a nested layout.
  if [ -f "$STAGING_DIR/$skill_name/SKILL.md" ]; then
    echo "$STAGING_DIR/$skill_name"
    return 0
  fi
  # Nested fallback — depth-2 find, prefer shallowest match.
  local candidate
  candidate=$(find "$STAGING_DIR" -maxdepth 3 -type d -name "$skill_name" 2>/dev/null | head -1)
  if [ -n "$candidate" ] && [ -f "$candidate/SKILL.md" ]; then
    echo "$candidate"
    return 0
  fi
  return 1
}

# ============================================================================
# Install each requested skill
# ============================================================================

mkdir -p "$CANONICAL_SKILLS_DIR"

INSTALLED=()
SKIPPED=()

for skill in $REQUESTED; do
  src=""
  if src=$(locate_skill_src "$skill"); then
    # Copy to canonical location (fresh each run — idempotent replace)
    canonical_dest="$CANONICAL_SKILLS_DIR/$skill"
    if [ -d "$canonical_dest" ]; then
      command rm -rf "$canonical_dest"
    fi
    command cp -r "$src" "$canonical_dest"

    # For each target agent, create a symlink from its skills/ dir to the
    # canonical location. Using symlinks means credential file rotations and
    # upstream upgrades propagate to all agents automatically.
    for agent in "${AGENTS[@]}"; do
      target_dir=$(agent_skills_dir "$agent")
      mkdir -p "$target_dir"
      link_path="$target_dir/$skill"

      # If an existing non-symlink installation is present, back it up before
      # overwriting — the user may have done a manual install.
      if [ -e "$link_path" ] && [ ! -L "$link_path" ]; then
        backup_dir="/tmp/gangtise-copilot-backups/$(date +%Y%m%d-%H%M%S)"
        mkdir -p "$backup_dir"
        command mv "$link_path" "$backup_dir/$skill"
        echo "  ℹ Backed up pre-existing $agent/$skill → $backup_dir/$skill"
      fi

      # Idempotent symlink creation
      command ln -sfn "$canonical_dest" "$link_path"
    done

    INSTALLED+=("$skill")
  else
    SKIPPED+=("$skill")
  fi
done

# ============================================================================
# Report
# ============================================================================

echo ""
echo "✓ Installed ${#INSTALLED[@]} skill(s) to ${#AGENTS[@]} agent(s):"
for skill in "${INSTALLED[@]}"; do
  echo "    ✓ $skill"
done

if [ ${#SKIPPED[@]} -gt 0 ]; then
  echo ""
  echo "⚠ Skipped (not found in downloaded bundles — likely a typo or the upstream moved):"
  for skill in "${SKIPPED[@]}"; do
    echo "    ✗ $skill"
  done
fi

echo ""
echo "Canonical install: $CANONICAL_SKILLS_DIR"
echo ""
echo "Next steps:"
echo "  1) Configure your Gangtise credentials:"
echo "       bash $(dirname "$0")/configure_auth.sh"
echo "  2) Verify the install:"
echo "       bash $(dirname "$0")/diagnose.sh"
echo ""
