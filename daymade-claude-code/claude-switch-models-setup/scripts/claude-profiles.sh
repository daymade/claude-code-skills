#!/bin/bash
# Claude Code Profile Isolation Manager
# Run different LLM providers in separate Claude Code windows without config bleed.
#
# Design:
# - Auto-discovery: scan ~/.claude/settings/*.json, create one profile per file
# - Idempotent init: safe to run multiple times
# - Shared symlinks: skills, projects, hooks, agents all point back to ~/.claude
# - Isolated state: each profile has its own claude.json
# - Safe removal: rm only deletes the isolation directory, never shared data
#
# Usage:
#   source ~/.config/claude-switch-models-setup/claude-profiles.sh
#   claude-profiles-init              # one-time init
#   claude-profile kimi               # launch a Kimi window
#   claude-profiles-doctor            # health check
#   claude-profile-rm kimi            # remove a profile

# Override defaults via environment variables
CLAUDE_PROFILES_DIR="${CLAUDE_PROFILES_DIR:-$HOME/.claude-profiles}"
CLAUDE_BASE_DIR="${CLAUDE_BASE_DIR:-$HOME/.claude}"
CLAUDE_PROFILES_CONFIG_DIR="${CLAUDE_PROFILES_CONFIG_DIR:-$HOME/.config/claude-switch-models-setup}"

# Internal constants
CLAUDE_JSON="claude.json"
SETTINGS_DIR="settings"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_profile_dir() {
    local profile="$1"
    echo "$CLAUDE_PROFILES_DIR/$profile"
}

_settings_file() {
    local profile="$1"
    echo "$CLAUDE_BASE_DIR/$SETTINGS_DIR/$profile.json"
}

_is_profile_name_valid() {
    local profile="$1"
    [[ "$profile" =~ ^[a-zA-Z0-9_-]+$ ]]
}

# ---------------------------------------------------------------------------
# Initialize all profiles (idempotent)
# ---------------------------------------------------------------------------

claude-profiles-init() {
    mkdir -p "$CLAUDE_PROFILES_DIR"

    local count=0
    local skipped=0

    for settings_file in "$CLAUDE_BASE_DIR/$SETTINGS_DIR"/*.json; do
        [ -f "$settings_file" ] || continue

        local profile
        profile=$(basename "$settings_file" .json)

        # "default" is reserved for the official default profile
        if [ "$profile" = "default" ]; then
            continue
        fi

        if ! _is_profile_name_valid "$profile"; then
            echo "[SKIP] Invalid profile name: $profile"
            continue
        fi

        local profile_dir
        profile_dir=$(_profile_dir "$profile")
        mkdir -p "$profile_dir"

        # Create empty claude.json if missing
        if [ ! -f "$profile_dir/$CLAUDE_JSON" ]; then
            echo '{}' > "$profile_dir/$CLAUDE_JSON"
            echo "[INIT] $profile: created $CLAUDE_JSON"
            count=$((count + 1))
        fi

        # Symlink every subdirectory of ~/.claude except settings/
        for subdir_path in "$CLAUDE_BASE_DIR"/*/; do
            [ -d "$subdir_path" ] || continue

            local subname
            subname=$(basename "$subdir_path")

            if [ "$subname" = "$SETTINGS_DIR" ]; then
                continue
            fi

            local target="$profile_dir/$subname"
            if [ ! -L "$target" ] && [ ! -e "$target" ]; then
                ln -s "$subdir_path" "$target"
                echo "[INIT] $profile: symlinked $subname"
            fi
        done

        # settings/ is shared because the profile JSON files live there
        local settings_target="$profile_dir/$SETTINGS_DIR"
        if [ ! -L "$settings_target" ] && [ ! -e "$settings_target" ]; then
            ln -s "$CLAUDE_BASE_DIR/$SETTINGS_DIR" "$settings_target"
            echo "[INIT] $profile: symlinked $SETTINGS_DIR"
        fi

        skipped=$((skipped + 1))
    done

    echo ""
    echo "Done. Initialized/verified $skipped profile(s), created $count new claude.json."
    echo "Profiles directory: $CLAUDE_PROFILES_DIR"
}

# ---------------------------------------------------------------------------
# Launch a profile
# ---------------------------------------------------------------------------

claude-profile() {
    local profile="${1:-}"
    shift || true

    if [ -z "$profile" ]; then
        echo "Usage: claude-profile <profile> [extra-args...]" >&2
        echo "Available profiles:" >&2
        claude-profiles-ls >&2
        return 1
    fi

    local profile_dir
    profile_dir=$(_profile_dir "$profile")

    if [ ! -d "$profile_dir" ]; then
        echo "Error: Profile '$profile' not found." >&2
        echo "Run: claude-profiles-init" >&2
        return 1
    fi

    local settings_file
    settings_file=$(_settings_file "$profile")

    if [ ! -f "$settings_file" ]; then
        echo "Error: Settings file not found: $settings_file" >&2
        return 1
    fi

    echo "[LAUNCH] Profile: $profile"
    echo "[LAUNCH] Config dir: $profile_dir"
    echo "[LAUNCH] Settings: $settings_file"
    echo ""

    # Auto-fix marketplace paths polluted by cross-profile updates
    local fixer="$CLAUDE_PROFILES_CONFIG_DIR/fix-marketplace-paths.py"
    if command -v python3 >/dev/null 2>&1 && [ -f "$fixer" ]; then
        python3 "$fixer" >/dev/null 2>&1
    fi

    CLAUDE_CONFIG_DIR="$profile_dir" claude --settings "$settings_file" "$@"
}

# ---------------------------------------------------------------------------
# List profiles
# ---------------------------------------------------------------------------

claude-profiles-ls() {
    if [ ! -d "$CLAUDE_PROFILES_DIR" ]; then
        echo "No profiles initialized yet."
        return 0
    fi

    for profile_dir in "$CLAUDE_PROFILES_DIR"/*/; do
        [ -d "$profile_dir" ] || continue

        local profile
        profile=$(basename "$profile_dir")

        local status="ok"
        if [ ! -f "$profile_dir/$CLAUDE_JSON" ]; then
            status="MISSING_CLAUDE_JSON"
        fi

        printf "  %-20s %s\n" "$profile" "$status"
    done
}

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

claude-profiles-doctor() {
    if [ ! -d "$CLAUDE_PROFILES_DIR" ]; then
        echo "No profiles directory found. Run: claude-profiles-init"
        return 1
    fi

    local issues=0

    for profile_dir in "$CLAUDE_PROFILES_DIR"/*/; do
        [ -d "$profile_dir" ] || continue

        local profile
        profile=$(basename "$profile_dir")
        local profile_issues=0

        if [ ! -f "$profile_dir/$CLAUDE_JSON" ]; then
            echo "[$profile] ERROR: Missing $CLAUDE_JSON"
            profile_issues=$((profile_issues + 1))
        fi

        for link in "$profile_dir"/*; do
            [ -L "$link" ] || continue
            if [ ! -e "$link" ]; then
                echo "[$profile] ERROR: Broken symlink: $link"
                profile_issues=$((profile_issues + 1))
            fi
        done

        for item in "$profile_dir"/*; do
            [ -e "$item" ] || continue
            local name
            name=$(basename "$item")
            if [ -f "$item" ] && [ "$name" != "$CLAUDE_JSON" ]; then
                echo "[$profile] WARN: Unexpected real file: $name"
            fi
        done

        if [ $profile_issues -eq 0 ]; then
            echo "[$profile] OK"
        else
            issues=$((issues + profile_issues))
        fi
    done

    echo ""
    if [ $issues -eq 0 ]; then
        echo "All profiles healthy."
    else
        echo "Found $issues issue(s). Run: claude-profiles-init to fix."
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Safe removal
# ---------------------------------------------------------------------------

claude-profile-rm() {
    local profile="${1:-}"

    if [ -z "$profile" ]; then
        echo "Usage: claude-profile-rm <profile>" >&2
        return 1
    fi

    local profile_dir
    profile_dir=$(_profile_dir "$profile")

    if [ ! -d "$profile_dir" ]; then
        echo "Error: Profile '$profile' not found."
        return 1
    fi

    local has_real_files=false
    for item in "$profile_dir"/*; do
        [ -e "$item" ] || continue
        local name
        name=$(basename "$item")

        if [ "$name" = "$CLAUDE_JSON" ]; then
            continue
        fi

        if [ -L "$item" ]; then
            continue
        fi

        has_real_files=true
        echo "WARN: Unexpected real file found: $name"
    done

    if [ "$has_real_files" = true ]; then
        echo ""
        echo "ABORT: Profile directory contains unexpected real files."
        echo "Manual inspection required: $profile_dir"
        return 1
    fi

    echo "Profile directory contents:"
    ls -la "$profile_dir"
    echo ""
    read -rp "Confirm deletion of '$profile' isolation directory? [y/N] " confirm

    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo "Cancelled."
        return 1
    fi

    rm -rf "$profile_dir"
    echo "Removed profile isolation directory: $profile"
}

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

claude-profiles-help() {
    cat <<'EOF'
Claude Code Profile Isolation Manager

Commands:
  claude-profiles-init              Initialize/verify all profiles
  claude-profile <name>            Launch a profile
  claude-profiles-ls                List profiles
  claude-profiles-doctor            Health check
  claude-profile-rm <name>         Remove a profile's isolation directory
  claude-profiles-help              Show this help

Environment:
  CLAUDE_PROFILES_DIR         Profile isolation root (default: ~/.claude-profiles)
  CLAUDE_BASE_DIR             Main Claude config dir (default: ~/.claude)
  CLAUDE_PROFILES_CONFIG_DIR  Where fix-marketplace-paths.py lives
                              (default: ~/.config/claude-switch-models-setup)

Shell aliases (add to ~/.zshrc or ~/.bashrc):
  alias csk='claude-profile kimi'
  alias csd='claude-profile deepseek'
  alias csg='claude-profile glm'
  alias css='claude-profile stepfun'
EOF
}
