#!/bin/bash
# One-click installer for Claude Code multi-provider profiles.
# This script links the profile manager into place and prints the remaining
# manual steps (adding API keys and sourcing the shell integration).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${HOME}/.config/claude-switch-models-setup"
CLAUDE_SETTINGS_DIR="${HOME}/.claude/settings"
ACTIVE_SKILLS_MANIFEST="${CONFIG_DIR}/codex-active-skills.json"
ACTIVE_SKILLS_TEMPLATE="${SCRIPT_DIR}/../assets/templates/codex-active-skills.json"
ACTIVE_SKILLS_SEEDER="${SCRIPT_DIR}/seed-codex-active-skills.py"

mkdir -p "$CONFIG_DIR"
mkdir -p "$CLAUDE_SETTINGS_DIR"

echo "Installing Claude Code profile manager..."

# Symlink rather than copy. $CONFIG_DIR is what actually runs — the LaunchAgent
# and claude-profile invoke these by that path — while this checkout holds the
# source, and a copy is indistinguishable from its source by looking at it. Both
# directions of drift have happened here for real: a lock-placement fix sat in
# the repo for 26 days while the deployed copy kept running the bug, and two
# cleanup routines written straight into a deployed copy never reached version
# control at all. This installer runs FROM the checkout, so the source is
# guaranteed present and there is no reason to duplicate it.
#
# sync-profile-settings.py was missing from this list while step 6 of the skill
# depends on it, so a machine set up by this script had no settings converger.
#
# A machine whose LaunchAgent runs the PINNED plugin copy (references/
# local-source-sync-architecture.md, "pinned plugin copy") points these links at
# a .../plugins/cache/<marketplace>/<plugin>/<version>/... directory and moves
# them only when the pin is advanced. Relinking such a machine to this checkout
# would make the daemon and claude-profile follow whatever branch the checkout
# sits on, so refuse unless the operator says so explicitly.
for f in claude-profiles.sh \
         claude-plugins-sync.py \
         sync-local-skill-sources.py \
         sync-local-skill-sources-daemon.sh \
         sync-profile-settings.py; do
    existing="$CONFIG_DIR/$f"
    [ -L "$existing" ] || continue
    target="$(readlink "$existing")"
    case "$target" in
        */plugins/cache/*)
            if [ "${CSMS_SETUP_RELINK_TO_CHECKOUT:-}" != "1" ]; then
                echo "Refusing to relink: $existing -> $target is a pinned plugin copy." >&2
                echo "This machine advances these links with the pin (references/troubleshooting.md, 'advance the pin')." >&2
                echo "Set CSMS_SETUP_RELINK_TO_CHECKOUT=1 to link into this checkout anyway." >&2
                exit 1
            fi
            ;;
    esac
done
for f in claude-profiles.sh \
         claude-plugins-sync.py \
         sync-local-skill-sources.py \
         sync-local-skill-sources-daemon.sh \
         sync-profile-settings.py; do
    ln -sf "$SCRIPT_DIR/$f" "$CONFIG_DIR/$f"
done

# This file is user-owned activation policy, not deployed program code. The
# helper writes a complete private temp file and publishes it with os.link(),
# whose destination is exact and no-overwrite even if a directory appears.
python3 "$ACTIVE_SKILLS_SEEDER" "$ACTIVE_SKILLS_TEMPLATE" "$ACTIVE_SKILLS_MANIFEST"

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
echo ""
echo "7. (Maintainers only) Select Codex user Skills in:"
echo "   ${ACTIVE_SKILLS_MANIFEST}"
echo "   An empty active_skills list intentionally activates no marketplace source Skills."
echo "   legacy_codex_compat_skills is an optional active_skills subset for long-lived"
echo "   hooks or processes that still hold a legacy ~/.codex/skills path."
echo ""
echo "8. (Maintainers only) Link selected local Skill sources into ~/.agents/skills:"
echo "   python3 ${CONFIG_DIR}/sync-local-skill-sources.py --apply"
echo ""
echo "9. (Maintainers only, macOS) Install automatic source-sync watcher:"
echo "   ${CONFIG_DIR}/sync-local-skill-sources-daemon.sh --install"
