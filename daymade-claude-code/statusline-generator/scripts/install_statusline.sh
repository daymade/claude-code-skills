#!/usr/bin/env bash
# Install statusline script + wire settings.json + run health check.
#
# After install, the script always finishes with a health_check.sh run so the
# user sees concrete pass/fail evidence (not just "Installation complete").
# This prevents the silent-failure mode where chmod is forgotten or the
# settings.json command points to the wrong path.
#
# Usage:
#   bash install_statusline.sh                    # install to ~/.claude/statusline.sh
#   bash install_statusline.sh /custom/path.sh    # install to custom path

set -e

TARGET_PATH="${1:-$HOME/.claude/statusline.sh}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_SCRIPT="$SCRIPT_DIR/generate_statusline.sh"
HEALTH_CHECK="$SCRIPT_DIR/health_check.sh"
SETTINGS_FILE="$HOME/.claude/settings.json"
TARGET_DIR=$(dirname "$TARGET_PATH")

if [ ! -f "$SOURCE_SCRIPT" ]; then
    echo "ERROR: generate_statusline.sh not found at $SOURCE_SCRIPT" >&2
    exit 1
fi

if [ ! -d "$TARGET_DIR" ]; then
    echo ">> Creating directory: $TARGET_DIR"
    mkdir -p "$TARGET_DIR"
fi

# Backup existing target script if present
if [ -f "$TARGET_PATH" ]; then
    backup="$TARGET_PATH.bak.$(date +%Y%m%d_%H%M%S)"
    echo ">> Backing up existing script: $backup"
    cp "$TARGET_PATH" "$backup"
fi

echo ">> Installing: $SOURCE_SCRIPT -> $TARGET_PATH"
cp "$SOURCE_SCRIPT" "$TARGET_PATH"
chmod +x "$TARGET_PATH"   # critical — silent failure root cause if missed

# Wire settings.json
if [ ! -f "$SETTINGS_FILE" ]; then
    echo ">> Creating new settings.json with statusLine block"
    cat > "$SETTINGS_FILE" <<EOF
{
  "statusLine": {
    "type": "command",
    "command": "$TARGET_PATH",
    "padding": 0
  }
}
EOF
elif command -v jq >/dev/null 2>&1; then
    settings_backup="$SETTINGS_FILE.bak.$(date +%Y%m%d_%H%M%S)"
    cp "$SETTINGS_FILE" "$settings_backup"
    echo ">> Backed up settings.json: $settings_backup"

    tmp=$(mktemp)
    jq --arg cmd "$TARGET_PATH" \
       '.statusLine = {"type":"command","command":$cmd,"padding":(.statusLine.padding // 0)}' \
       "$SETTINGS_FILE" > "$tmp"
    mv "$tmp" "$SETTINGS_FILE"
    echo ">> Updated settings.json statusLine.command -> $TARGET_PATH"
else
    echo "WARN: jq not installed — cannot safely edit settings.json" >&2
    echo "      Manually set statusLine.command to: $TARGET_PATH" >&2
fi

# ---- Mandatory health check (do not let the user discover failures themselves) ----
echo
echo "== Running health check =="
if [ -x "$HEALTH_CHECK" ] || bash "$HEALTH_CHECK" --help >/dev/null 2>&1; then
    bash "$HEALTH_CHECK" "$TARGET_PATH" || {
        echo
        echo "WARN: Health check reported issues. Review the output above." >&2
        echo "      Re-run anytime: bash $HEALTH_CHECK $TARGET_PATH" >&2
        exit 1
    }
else
    echo "WARN: health_check.sh not found or not executable — skipping post-install verification" >&2
fi

echo
echo "Installation complete."
echo
echo "Usage:"
echo "  Default          : minimal one-line layout (cwd + model + ctx tokens)"
echo "  Full layout      : add to ~/.zshrc or ~/.bashrc:"
echo "                       export CLAUDE_STATUSLINE_LAYOUT=full"
echo "                     (multi-line with cost via ccusage + git status + percentage)"
echo "  Debug stdin      : export CLAUDE_STATUSLINE_DEBUG=1"
echo "                     dumps each invocation's stdin to /tmp/.claude-statusline-last-stdin.json"
echo
echo "Verify anytime: bash $HEALTH_CHECK"
