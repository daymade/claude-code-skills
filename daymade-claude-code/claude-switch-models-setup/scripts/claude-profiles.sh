#!/bin/bash
# Claude Code Profile Isolation Manager
# Run different LLM providers in separate Claude Code windows without config bleed.
#
# Design:
# - Auto-discovery: scan ~/.claude/settings/*.json, create one profile per file
# - Idempotent init: safe to run multiple times
# - Shared symlinks: skills, projects, hooks, agents all point back to ~/.claude
#   (exception: plugins/ is NOT shared as a whole — content sub-items are symlinked but
#    known_marketplaces.json is per-profile; see claude-plugins-sync.py for why)
# - Isolated state: each profile has its own .claude.json
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

# Resolve this script's own directory so the helper python (claude-plugins-sync.py)
# is found right next to it — self-contained whether sourced from the skill repo or
# from an installed copy (e.g. ~/.config/claude-switch-models-setup). Override with
# CLAUDE_PROFILES_CONFIG_DIR if you keep the helper somewhere else.
if [ -n "${ZSH_VERSION:-}" ]; then
    # zsh can echo `local name=value` assignments when TYPESET_SILENT is off.
    # This file is usually sourced from ~/.zshrc, so keep helper output clean.
    setopt TYPESET_SILENT 2>/dev/null || true
    _CP_SELF="$(eval 'print -r -- ${(%):-%x}')"
else
    _CP_SELF="${BASH_SOURCE[0]:-$0}"
fi
CLAUDE_PROFILES_CONFIG_DIR="${CLAUDE_PROFILES_CONFIG_DIR:-$(cd "$(dirname "$_CP_SELF")" >/dev/null 2>&1 && pwd)}"

# Internal constants
CLAUDE_JSON=".claude.json"
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
    local repair=false
    while [ $# -gt 0 ]; do
        case "$1" in
            --repair) repair=true ;;
            -h|--help)
                echo "Usage: claude-profiles-init [--repair]"
                echo "  (no flag)  scan + create missing symlinks; report real-dir drift without touching it"
                echo "  --repair   also archive real-dir drift (.pre-symlink-bak-<ts>) and replace with symlinks"
                return 0
                ;;
            *) echo "claude-profiles-init: unknown argument: $1" >&2; return 1 ;;
        esac
        shift
    done

    mkdir -p "$CLAUDE_PROFILES_DIR"

    local count=0
    local skipped=0
    local repaired=0

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

        # Create empty .claude.json if missing. Claude Code reads this file from
        # CLAUDE_CONFIG_DIR; legacy claude.json files are left in place but are not
        # sufficient for modern Claude Code launches.
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

            # plugins/ must NOT be symlinked as a whole: known_marketplaces.json's
            # installLocation is config-dir-specific (Claude validates with path.resolve,
            # which does not resolve symlinks), so a shared copy makes every other profile
            # report "corrupted installLocation". Handled by claude-plugins-sync.py instead:
            # content sub-items symlinked, known_marketplaces.json kept per-profile.
            if [ "$subname" = "plugins" ]; then
                continue
            fi

            local target="$profile_dir/$subname"
            if [ -L "$target" ]; then
                : # already a symlink — correct
            elif [ -e "$target" ]; then
                # Real directory/file residue — the profile predates the symlink-
                # convergence design (or was hand-created). This is silent drift:
                # this profile's $subname diverges from the main ~/.claude copy.
                # 2026-07-21: legacy profiles carried real projects/ dirs this way.
                # Default: WARN only, never touch user data without --repair.
                # --repair: archive to .pre-symlink-bak-<ts>, then symlink.
                if [ "$repair" = true ]; then
                    local bak="$target.pre-symlink-bak-$(date +%Y%m%d-%H%M%S)"
                    mv "$target" "$bak"
                    ln -s "$subdir_path" "$target"
                    echo "[INIT] $profile: REPAIRED $subname (real dir archived → $(basename "$bak"), symlinked)"
                    repaired=$((repaired + 1))
                else
                    echo "[INIT] $profile: WARN $subname is a real dir, not a symlink (run: claude-profiles-init --repair)" >&2
                fi
            else
                ln -s "$subdir_path" "$target"
                echo "[INIT] $profile: symlinked $subname"
            fi
        done

        # Prune obsolete profile links that point back into ~/.claude after the base
        # item has been removed. This keeps doctor useful when Claude Code creates and
        # later removes optional runtime directories such as image-cache/.
        for stale_link in "$profile_dir"/*; do
            [ -L "$stale_link" ] || continue
            [ ! -e "$stale_link" ] || continue

            local stale_target
            stale_target=$(readlink "$stale_link" 2>/dev/null || true)
            case "$stale_target" in
                "$CLAUDE_BASE_DIR"/*)
                    rm "$stale_link"
                    echo "[INIT] $profile: pruned stale symlink $(basename "$stale_link")"
                    ;;
            esac
        done

        # settings/ is shared because the profile JSON files live there
        local settings_target="$profile_dir/$SETTINGS_DIR"
        if [ -L "$settings_target" ]; then
            :
        elif [ -e "$settings_target" ]; then
            if [ "$repair" = true ]; then
                local sbak="$settings_target.pre-symlink-bak-$(date +%Y%m%d-%H%M%S)"
                mv "$settings_target" "$sbak"
                ln -s "$CLAUDE_BASE_DIR/$SETTINGS_DIR" "$settings_target"
                echo "[INIT] $profile: REPAIRED $SETTINGS_DIR (archived → $(basename "$sbak"))"
                repaired=$((repaired + 1))
            else
                echo "[INIT] $profile: WARN $SETTINGS_DIR is a real dir, not a symlink (run: claude-profiles-init --repair)" >&2
            fi
        else
            ln -s "$CLAUDE_BASE_DIR/$SETTINGS_DIR" "$settings_target"
            echo "[INIT] $profile: symlinked $SETTINGS_DIR"
        fi

        # Ensure per-profile settings.json carries statusLine.
        # Claude Code does NOT merge statusLine from the global settings.json into a
        # profile's settings.json; each profile needs its own. The global settings file
        # is ~/.claude/settings.json (NOT settings/settings.json — that subdir only holds
        # per-profile provider JSONs). Paths are passed via argv, never interpolated into
        # the python source, and we do NOT toggle `set -e` (this file is sourced into the
        # user's interactive shell — flipping errexit would leak into their session).
        local profile_settings="$profile_dir/settings.json"
        local global_settings="$CLAUDE_BASE_DIR/settings.json"
        local statusline_cmd=""
        if [ -f "$global_settings" ]; then
            statusline_cmd=$(python3 -c "
import json, sys
try:
    with open(sys.argv[1]) as f:
        cmd = json.load(f).get('statusLine', {}).get('command')
    if cmd:
        print(cmd)
except Exception:
    pass
" "$global_settings" 2>/dev/null || true)
        fi
        if [ -z "$statusline_cmd" ] && [ -x "$HOME/.claude/statusline.sh" ]; then
            statusline_cmd="$HOME/.claude/statusline.sh"
        fi
        if [ -n "$statusline_cmd" ]; then
            if [ ! -f "$profile_settings" ]; then
                echo '{}' > "$profile_settings"
            fi
            if python3 -c "
import json, sys
p, cmd = sys.argv[1], sys.argv[2]
with open(p) as f:
    data = json.load(f)
data.setdefault('statusLine', {})['command'] = cmd
data['statusLine']['type'] = 'command'
data['statusLine'].setdefault('padding', 0)
with open(p, 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write('\n')
" "$profile_settings" "$statusline_cmd" 2>/dev/null; then
                echo "[INIT] $profile: ensured statusLine -> $statusline_cmd"
            else
                echo "[WARN] $profile: failed to inject statusLine" >&2
            fi
        fi

        skipped=$((skipped + 1))
    done

    # Maintainer worktrees: keep Claude/Codex installed copies linked to local source
    # before building per-profile plugin metadata. Ordinary skill edits are live through
    # symlinks; this idempotent pass covers manifest/version/topology changes.
    local source_syncer="$CLAUDE_PROFILES_CONFIG_DIR/sync-local-skill-sources.py"
    if command -v python3 >/dev/null 2>&1 && [ -f "$source_syncer" ]; then
        python3 "$source_syncer" --apply --quiet >/dev/null
    fi

    # plugins: build per-profile structure + per-profile known_marketplaces.json
    # (the whole-dir symlink above deliberately skips plugins)
    local syncer="$CLAUDE_PROFILES_CONFIG_DIR/claude-plugins-sync.py"
    if command -v python3 >/dev/null 2>&1 && [ -f "$syncer" ]; then
        echo ""
        echo "[INIT] syncing per-profile plugin marketplaces ..."
        python3 "$syncer"
    else
        echo "[WARN] plugin sync SKIPPED: python3 or claude-plugins-sync.py missing ($syncer)." >&2
        echo "       per-profile known_marketplaces.json was NOT built — marketplaces may report 'corrupted installLocation'." >&2
    fi

    echo ""
    echo "Done. Initialized/verified $skipped profile(s), created $count new .claude.json${repair:+, repaired $repaired drift item(s)}."
    echo "Profiles directory: $CLAUDE_PROFILES_DIR"
    if [ "$repaired" -gt 0 ] 2>/dev/null; then
        echo "Re-run claude-profiles-doctor to confirm no drift remains."
    fi
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

    # Sync THIS profile's plugin marketplace metadata (root-cause fix; replaces the old
    # fix-marketplace-paths.py, which CAUSED the corruption by rewriting the shared file).
    # --profile limits work + concurrent writes to the profile being launched; stdout is
    # quiet on this hot path, but errors stay on stderr (not /dev/null) so failures show.
    local source_syncer="$CLAUDE_PROFILES_CONFIG_DIR/sync-local-skill-sources.py"
    if command -v python3 >/dev/null 2>&1 && [ -f "$source_syncer" ]; then
        python3 "$source_syncer" --apply --quiet >/dev/null
    fi

    local syncer="$CLAUDE_PROFILES_CONFIG_DIR/claude-plugins-sync.py"
    if command -v python3 >/dev/null 2>&1 && [ -f "$syncer" ]; then
        python3 "$syncer" --profile "$profile" >/dev/null
    else
        echo "[WARN] plugin sync SKIPPED: python3 or claude-plugins-sync.py missing ($syncer) — marketplaces may report 'corrupted installLocation'." >&2
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

        local profile_status="ok"
        if [ ! -f "$profile_dir/$CLAUDE_JSON" ]; then
            profile_status="MISSING_CLAUDE_JSON"
        fi

        printf "  %-20s %s\n" "$profile" "$profile_status"
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

        # Orphan profile: the claude-profiles/ directory exists but there is no
        # settings/<profile>.json to drive it. init only processes profiles with
        # a settings file, so this profile's symlinks are never maintained and
        # `claude-profile <name>` will fail to launch (settings not found).
        # Skip the rest — symlink/drift checks are moot when init won't maintain
        # the profile at all.
        # 2026-07-22: a dead profile carried real data (history/skill-workspaces
        # /usage-data) for months; doctor reported drift but init could never fix
        # it because the profile had no settings file — misleading signal.
        if [ ! -f "$CLAUDE_BASE_DIR/$SETTINGS_DIR/$profile.json" ]; then
            echo "[$profile] WARN: orphan profile — no $SETTINGS_DIR/$profile.json; claude-profile $profile fails. Run: claude-profile-rm $profile (or recreate settings)"
            issues=$((issues + 1))
            continue
        fi

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

        # Drift detection: every shared content subdir (skills/projects/hooks/
        # agents/commands/...) MUST be a symlink back into ~/.claude. A real
        # directory here means the profile predates the symlink-convergence
        # design (or was created by hand) and is silently drifting — its
        # skills/projects/hooks/agents diverge from the main ~/.claude copy,
        # undetectable by the broken-symlink check above.
        # 2026-07-21: legacy profiles carried real projects/ dirs for months;
        # doctor reported "OK" the whole time because this check didn't exist.
        # plugins/ is the one legitimate real dir (per-profile known_marketplaces.json
        # lives inside it; its content sub-items are themselves symlinked).
        for item in "$profile_dir"/*; do
            [ -d "$item" ] || continue
            [ -L "$item" ] && continue
            local dname
            dname=$(basename "$item")
            case "$dname" in
                plugins|plugins.pre-sync-*|*.pre-symlink-bak-*)
                    continue
                    ;;
            esac
            # Only flag as drift when the main ~/.claude actually has this dir to
            # symlink back to. A real dir with NO main counterpart is profile-local
            # data this profile alone produced (a skill workspace, a usage report),
            # not drift — init cannot repair it (no source) and must not touch it.
            [ -e "$CLAUDE_BASE_DIR/$dname" ] || continue
            echo "[$profile] WARN: $dname is a real directory (expected symlink to $CLAUDE_BASE_DIR/$dname) — drift; run: claude-profiles-init --repair"
            profile_issues=$((profile_issues + 1))
        done

        for item in "$profile_dir"/*; do
            [ -e "$item" ] || continue
            local name
            name=$(basename "$item")
            if [ -f "$item" ]; then
                # Expected real files: per-profile state + Claude Code runtime +
                # backups written by this skill's own sync scripts.
                case "$name" in
                    "$CLAUDE_JSON"|claude.json|settings.json|history.jsonl|daemon.log|daemon.lock|daemon.status.json|stats-cache.json|gh-pr-status-cache.json|mcp-needs-auth-cache.json|.last-cleanup|.last-update-result.json|.claude.claude.json.bak-*|settings.json.bak*|settings.json.sync-backup)
                        continue
                        ;;
                esac
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
        echo "Found $issues issue(s). Run: claude-profiles-init --repair to fix drift."
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

        if [ "$name" = "$CLAUDE_JSON" ] || [ "$name" = "claude.json" ]; then
            continue
        fi

        if [ -L "$item" ]; then
            continue
        fi

        # Real files/dirs the per-profile structure legitimately creates:
        #   plugins/      — content symlinks + independent known_marketplaces.json (rebuildable)
        #   settings.json — per-profile statusLine, written by init
        if [ "$name" = "plugins" ] || [ "$name" = "settings.json" ]; then
            continue
        fi
        # pre-sync backups hold a profile's salvaged old real plugins dir — allowed, but
        # surfaced so the user knows this safety copy is removed together with the profile.
        if [[ "$name" == plugins.pre-sync-* ]]; then
            echo "NOTE: will also delete salvaged backup: $name"
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
  claude-profiles-init [--repair]   Initialize/verify profiles; --repair fixes drift
  claude-profile <name>            Launch a profile
  claude-profiles-ls                List profiles
  claude-profiles-doctor            Health check (detects symlink drift)
  claude-profile-rm <name>         Remove a profile's isolation directory
  claude-profiles-help              Show this help

Environment:
  CLAUDE_PROFILES_DIR         Profile isolation root (default: ~/.claude-profiles)
  CLAUDE_BASE_DIR             Main Claude config dir (default: ~/.claude)
  CLAUDE_PROFILES_CONFIG_DIR  Where claude-plugins-sync.py lives
                              (default: ~/.config/claude-switch-models-setup)
  DAYMADE_SKILL_SOURCE_REPOS  Optional colon-separated local source repos

Shell aliases (add to ~/.zshrc or ~/.bashrc):
  alias csk='claude-profile kimi'              # Kimi K3 (1M context)
  alias csks='claude-profile kimi-highspeed'   # Kimi K2.7 highspeed
  alias csd='claude-profile deepseek'
  alias csg='claude-profile glm'
  alias css='claude-profile stepfun'
EOF
}
