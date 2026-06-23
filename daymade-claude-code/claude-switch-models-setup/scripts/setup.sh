#!/bin/bash
# One-click installer for Claude Code multi-provider profiles.
# This script copies the profile manager into place and prints the remaining
# manual steps (adding API keys and sourcing the shell integration).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${HOME}/.config/claude-switch-models-setup"
CLAUDE_SETTINGS_DIR="${HOME}/.claude/settings"

mkdir -p "$CONFIG_DIR"
mkdir -p "$CLAUDE_SETTINGS_DIR"

echo "Installing Claude Code profile manager..."
cp "$SCRIPT_DIR/claude-profiles.sh" "$CONFIG_DIR/claude-profiles.sh"
cp "$SCRIPT_DIR/fix-marketplace-paths.py" "$CONFIG_DIR/fix-marketplace-paths.py"
chmod +x "$CONFIG_DIR/claude-profiles.sh"
chmod +x "$CONFIG_DIR/fix-marketplace-paths.py"

echo ""
echo "✅ Installed to: $CONFIG_DIR"
echo ""
echo "Next steps:"
echo ""
echo "1. Add this line to your shell config (~/.zshrc or ~/.bashrc):"
echo "   source ${CONFIG_DIR}/claude-profiles.sh"
echo ""
echo "2. Add aliases (also in ~/.zshrc or ~/.bashrc):"
echo "   alias csk='claude-profile kimi'"
echo "   alias csd='claude-profile deepseek'"
echo "   alias csg='claude-profile glm'"
echo "   alias css='claude-profile stepfun'"
echo ""
echo "3. Create provider settings files in ~/.claude/settings/"
echo "   Use the templates from the skill's templates/ directory."
echo ""
echo "4. Run: claude-profiles-init"
echo ""
echo "5. Launch a profile: csk"
