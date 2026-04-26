#!/usr/bin/env bash

# Install statusline script to Claude Code configuration directory
# Usage: ./install_statusline.sh [target_path]

set -e

# Determine target path
if [ -n "$1" ]; then
    TARGET_PATH="$1"
else
    TARGET_PATH="$HOME/.claude/statusline.sh"
fi

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_SCRIPT="$SCRIPT_DIR/generate_statusline.sh"

# Check if source script exists
if [ ! -f "$SOURCE_SCRIPT" ]; then
    echo "❌ Error: generate_statusline.sh not found at $SOURCE_SCRIPT"
    exit 1
fi

# Create .claude directory if it doesn't exist
CLAUDE_DIR=$(dirname "$TARGET_PATH")
if [ ! -d "$CLAUDE_DIR" ]; then
    echo "📁 Creating directory: $CLAUDE_DIR"
    mkdir -p "$CLAUDE_DIR"
fi

# Copy the script
echo "📋 Copying statusline script to: $TARGET_PATH"
cp "$SOURCE_SCRIPT" "$TARGET_PATH"
chmod +x "$TARGET_PATH"

# Update settings.json
SETTINGS_FILE="$HOME/.claude/settings.json"

if [ ! -f "$SETTINGS_FILE" ]; then
    echo "⚠️  Warning: settings.json not found at $SETTINGS_FILE"
    echo "   Please create it manually or restart Claude Code"
    exit 0
fi

# Check if statusLine already configured
if grep -q '"statusLine"' "$SETTINGS_FILE"; then
    echo "✅ statusLine already configured in settings.json"
    echo "   Current configuration will use the updated script"
else
    echo "📝 Adding statusLine configuration to settings.json"

    # Backup settings.json
    cp "$SETTINGS_FILE" "$SETTINGS_FILE.backup"

    # Add statusLine configuration using jq
    jq '. + {"statusLine": {"type": "command", "command": "bash '"$TARGET_PATH"'", "padding": 0}}' "$SETTINGS_FILE.backup" > "$SETTINGS_FILE"

    echo "✅ statusLine configuration added"
    echo "   Backup saved to: $SETTINGS_FILE.backup"
fi

echo ""
echo "🎉 Installation complete!"
echo ""
echo "Next steps:"
echo "  1. Restart Claude Code to see your new statusline"
echo "  2. The statusline will show:"
echo "     Line 1: username (model) [session_cost/daily_cost]"
echo "     Line 2: current_path"
echo "     Line 3: [git:branch]"
echo ""
echo "Note: Cost information requires ccusage to be installed and accessible"