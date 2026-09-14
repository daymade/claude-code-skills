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
RUNTIME_DIR="$HOME/.config/claude-switch-models-setup/python"
INTERPRETER_FILE="$HOME/.config/claude-switch-models-setup/runtime-python.path"

load_interpreter() {
    if [ ! -f "$INTERPRETER_FILE" ]; then
        echo "Missing owned Python runtime; run $0 --install" >&2
        exit 1
    fi
    IFS= read -r SYNC_PYTHON < "$INTERPRETER_FILE"
    case "$SYNC_PYTHON" in
        "$RUNTIME_DIR"/*/bin/python*) ;;
        *) echo "Runtime interpreter is outside its owned directory" >&2; exit 1 ;;
    esac
    [ -x "$SYNC_PYTHON" ] || { echo "Runtime Python missing: $SYNC_PYTHON" >&2; exit 1; }
}

run_sync() {
    load_interpreter
    # The Python commands serialize through their shared PID-aware lock.
    # A second shell lock used to silently discard a pending registration event.
    "$SYNC_PYTHON" "$SCRIPT_DIR/sync-local-skill-sources.py" --apply --quiet
    if [ -f "$SCRIPT_DIR/claude-plugins-sync.py" ]; then
        "$SYNC_PYTHON" "$SCRIPT_DIR/claude-plugins-sync.py" >/dev/null
    fi
    /bin/date -u '+source-sync verified links and profiles at %Y-%m-%dT%H:%M:%SZ'
}

install_launchagent() {
    mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"
    # Only installation invokes a package manager. Runtime uses an absolute
    # interpreter inside this installer's directory, unaffected by other tools.
    uv python install 3.12 --install-dir "$RUNTIME_DIR" --no-bin
    local owned_python interpreter_temp
    owned_python="$(UV_PYTHON_INSTALL_DIR="$RUNTIME_DIR" uv python find --managed-python 3.12)"
    interpreter_temp="$(mktemp "${INTERPRETER_FILE}.XXXXXX")"
    printf '%s\n' "$owned_python" > "$interpreter_temp"
    mv "$interpreter_temp" "$INTERPRETER_FILE"
    load_interpreter

    local watch_paths
    watch_paths="$HOME/.claude/settings.json
$HOME/.claude/plugins/installed_plugins.json
$("$SYNC_PYTHON" "$SCRIPT_DIR/sync-local-skill-sources.py" --print-watch-paths)"
    if [ -z "$watch_paths" ]; then
        echo "No local marketplace manifests found to watch." >&2
        exit 1
    fi

    WATCH_PATHS="$watch_paths" PLIST_PATH="$PLIST_PATH" SCRIPT_PATH="$SCRIPT_DIR/sync-local-skill-sources-daemon.sh" LOG_DIR="$LOG_DIR" LABEL="$LABEL" "$SYNC_PYTHON" - <<'PY'
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
    "StartInterval": 300,
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
