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
cp "$SCRIPT_DIR/claude-plugins-sync.py" "$CONFIG_DIR/claude-plugins-sync.py"
chmod +x "$CONFIG_DIR/claude-profiles.sh"
chmod +x "$CONFIG_DIR/claude-plugins-sync.py"

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
echo "3. Create provider settings (REQUIRED) — one JSON per provider in ~/.claude/settings/:"
echo "   e.g. ~/.claude/settings/kimi.json with env { ANTHROPIC_AUTH_TOKEN, ANTHROPIC_BASE_URL, ANTHROPIC_MODEL }."
echo "   Templates live in the skill's assets/templates/ dir. claude-profiles-init creates"
echo "   exactly one profile per *.json file here — with none, it creates 0 profiles."
echo ""
echo "4. (Optional) Install statusline-generator for per-profile status bars:"
echo "   https://github.com/daymade/claude-code-skills/tree/main/daymade-claude-code/statusline-generator"
echo "   claude-profiles-init will auto-wire it if present."
echo ""
echo "5. Run: claude-profiles-init"
echo ""
echo "6. Launch a profile: csk"
