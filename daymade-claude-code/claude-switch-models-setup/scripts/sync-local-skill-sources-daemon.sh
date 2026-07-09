#!/bin/bash
# Automatic local source sync runner for maintainer machines.
#
# Default action: run one idempotent sync pass.
# --install: install a per-user macOS LaunchAgent that watches local marketplace
#            manifests and runs this script automatically.
# --uninstall: remove that LaunchAgent.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LABEL="ai.daymade.claude-skill-source-sync"
PLIST_PATH="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG_DIR="$HOME/Library/Logs/claude-switch-models-setup"
LOCK_DIR="${TMPDIR:-/tmp}/${LABEL}.lock"

run_sync() {
    if ! mkdir "$LOCK_DIR" 2>/dev/null; then
        exit 0
    fi
    trap 'rmdir "$LOCK_DIR"' EXIT

    python3 "$SCRIPT_DIR/sync-local-skill-sources.py" --apply --quiet
    if [ -f "$SCRIPT_DIR/claude-plugins-sync.py" ]; then
        python3 "$SCRIPT_DIR/claude-plugins-sync.py" >/dev/null
    fi
}

install_launchagent() {
    mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"

    local watch_paths
    watch_paths="$HOME/.claude/settings.json
$HOME/.claude/plugins/installed_plugins.json
$(python3 "$SCRIPT_DIR/sync-local-skill-sources.py" --print-watch-paths)"
    if [ -z "$watch_paths" ]; then
        echo "No local marketplace manifests found to watch." >&2
        exit 1
    fi

    WATCH_PATHS="$watch_paths" PLIST_PATH="$PLIST_PATH" SCRIPT_PATH="$SCRIPT_DIR/sync-local-skill-sources-daemon.sh" LOG_DIR="$LOG_DIR" LABEL="$LABEL" python3 - <<'PY'
import os
import plistlib
from pathlib import Path

watch_paths = []
for raw in os.environ["WATCH_PATHS"].splitlines():
    path = raw.strip()
    if path and path not in watch_paths:
        watch_paths.append(path)
plist = {
    "Label": os.environ["LABEL"],
    "ProgramArguments": [os.environ["SCRIPT_PATH"]],
    "RunAtLoad": True,
    "WatchPaths": watch_paths,
    "StandardOutPath": str(Path(os.environ["LOG_DIR"]) / "source-sync.out.log"),
    "StandardErrorPath": str(Path(os.environ["LOG_DIR"]) / "source-sync.err.log"),
}
with open(os.environ["PLIST_PATH"], "wb") as fh:
    plistlib.dump(plist, fh)
PY

    local login_uid
    login_uid="$(id -u)"
    launchctl bootout "gui/${login_uid}" "$PLIST_PATH" >/dev/null 2>&1 || true
    launchctl bootstrap "gui/${login_uid}" "$PLIST_PATH"
    launchctl enable "gui/${login_uid}/${LABEL}"
    run_sync
    echo "Installed LaunchAgent: $PLIST_PATH"
}

uninstall_launchagent() {
    local login_uid
    login_uid="$(id -u)"
    launchctl bootout "gui/${login_uid}" "$PLIST_PATH" >/dev/null 2>&1 || true
    rm -f "$PLIST_PATH"
    echo "Removed LaunchAgent: $PLIST_PATH"
}

case "${1:-}" in
    --install)
        install_launchagent
        ;;
    --uninstall)
        uninstall_launchagent
        ;;
    --help|-h)
        echo "Usage: $0 [--install|--uninstall]"
        ;;
    "")
        run_sync
        ;;
    *)
        echo "Unknown argument: $1" >&2
        echo "Usage: $0 [--install|--uninstall]" >&2
        exit 2
        ;;
esac
