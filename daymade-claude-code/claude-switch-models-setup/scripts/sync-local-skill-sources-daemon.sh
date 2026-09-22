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
import sys
from pathlib import Path

script_path = os.environ["SCRIPT_PATH"]
ABSENT = object()


def installed_program_arguments(plist_path):
    """The plist's ProgramArguments, or ABSENT when there is no entry to read.

    ABSENT is spelled for exactly four cases: no plist, an unreadable plist, a
    plist that is not a dict, and a dict without the ProgramArguments key. Those
    four mean nothing was ever configured, so they stay silent. A present but
    unusable entry is returned as it stands, because the caller has to name what
    it replaced: silently rewriting anything an operator configured is the very
    shape this branch exists to stop.

    Known trade-off, not a regression from this change: an OpenStep/NeXTSTEP ASCII
    plist passes `plutil -lint` but plistlib cannot read it (InvalidFileException),
    so such a plist lands here and is overwritten silently. Before this fix every
    install overwrote unconditionally, so that case is no worse off.
    """
    try:
        with open(plist_path, "rb") as fh:
            data = plistlib.load(fh)
    except Exception:
        return ABSENT
    if not isinstance(data, dict) or "ProgramArguments" not in data:
        return ABSENT
    return data["ProgramArguments"]


installed = installed_program_arguments(os.environ["PLIST_PATH"])
if installed is ABSENT:
    # Nothing was ever configured: first install, and nothing to explain.
    program_arguments = [script_path]
elif not (isinstance(installed, list) and installed and isinstance(installed[0], str)):
    # An entry exists but carries no usable element 0 (not a list, empty, or a
    # non-string first element, including the None arm the plist format cannot
    # actually write). Replacing it is correct; doing it quietly is not.
    program_arguments = [script_path]
    print(
        f"Existing ProgramArguments was {installed!r}, which has no usable entry 0; "
        f"resetting ProgramArguments to this script: {script_path}",
        file=sys.stderr,
    )
elif os.path.realpath(installed[0]) == os.path.realpath(script_path):
    # The same file, however it was spelled. This is what covers the mirror case:
    # the entry holds the plugin-cache path while the run goes through the
    # ~/.config symlink into that same cache copy, so the two strings differ while
    # the files are one. A literal comparison calls that a foreign wrapper.
    # It deliberately cannot make a source checkout equal to a cached plugin copy:
    # those are two different inodes, and no path comparison will ever join them.
    if not installed[1:]:
        # Repeat install: overwrite in place, explain nothing.
        program_arguments = [script_path]
    else:
        # Same entry, extra arguments. This installer owns none of them, and
        # dropping them quietly is the exact shape being fixed here.
        extra = installed[1:]
        program_arguments = [script_path]
        print(
            f"Existing ProgramArguments {installed!r} ran this script with extra "
            f"arguments {extra!r}, which this installer does not set; resetting "
            f"ProgramArguments to this script and dropping them: {script_path}",
            file=sys.stderr,
        )
elif os.path.isfile(installed[0]) and os.access(installed[0], os.X_OK):
    # A different executable owns this job. Leave the whole array exactly as found
    # -- arguments included, since a wrapper may take some -- but say which kind of
    # "different" it is, because they need different follow-up reading. Neither
    # message claims to know WHO put it there: a failed install cannot see that,
    # and asserting it produces a false negative (an operator's own fork that
    # happens to carry this script's name) or a false positive (a differently
    # named symlink pointing at another copy).
    program_arguments = installed
    if os.path.basename(installed[0]) == os.path.basename(script_path):
        # Same NAME, different file: another checkout, or another cached plugin
        # version (every version's cache directory ships a file of this name).
        # realpath cannot join those -- two inodes -- and basename must never be
        # used to decide "this is me" for exactly that reason. It only decides how
        # this message reads: another file with this name, not this script.
        print(
            f"Preserving existing ProgramArguments {installed!r} as found: it points "
            f"at a different file carrying this script's name ({installed[0]}) — "
            "another checkout, or another cached plugin version. Two files with "
            "this name are still two files, so this is not this script. Whether "
            "somebody put it there is not something this installer can tell, so the "
            "entry is left exactly as found. Repoint it by running --uninstall and "
            "then --install.",
            file=sys.stderr,
        )
    else:
        # The failure recorder scripts/sync-daemon-recorder.sh is the case this
        # whole change exists for: it works only by being ProgramArguments[0], and
        # every --install used to detach it, making failing passes invisible again.
        print(
            f"Preserving existing ProgramArguments {installed!r} as found: it points "
            f"at an executable other than this script ({installed[0]}), so this "
            "LaunchAgent stays wrapped. This installer does not own that choice and "
            "has no evidence for who made it, so the entry is left exactly as "
            "found. Repoint it by running --uninstall and then --install.",
            file=sys.stderr,
        )
else:
    # A foreign path that is gone or not usable. Replacing it is correct; replacing
    # it silently is what hid this class of mistake.
    program_arguments = [script_path]
    if not installed[0].strip():
        # An empty entry names nothing, so echoing it back says nothing. Say the
        # shape instead of printing a blank where the path belongs.
        print(
            "Existing ProgramArguments[0] is an empty path, which names nothing; "
            f"resetting ProgramArguments to this script: {script_path}",
            file=sys.stderr,
        )
    else:
        # "does not exist" would be false for a directory, a FIFO or a dangling
        # symlink: those exist, they are just not an executable regular file, which
        # is what launchd can actually run.
        print(
            f"Existing ProgramArguments[0] {installed[0]} is not a usable executable "
            "file — it does not exist, or it is not an executable regular file; "
            f"resetting ProgramArguments to this script: {script_path}",
            file=sys.stderr,
        )

watch_paths = []
for raw in os.environ["WATCH_PATHS"].splitlines():
    path = raw.strip()
    if path and path not in watch_paths:
        watch_paths.append(path)
plist = {
    "Label": os.environ["LABEL"],
    "ProgramArguments": program_arguments,
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
