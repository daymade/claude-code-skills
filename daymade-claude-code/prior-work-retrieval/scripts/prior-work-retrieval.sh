#!/usr/bin/env bash
# Claude/Codex hook entrypoint for prior-work-retrieval.
# SSOT lives beside this wrapper; a deployed symlink resolves back here.
set -uo pipefail

SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
  SOURCE_DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  TARGET="$(readlink "$SOURCE")"
  case "$TARGET" in
    /*) SOURCE="$TARGET" ;;
    *) SOURCE="$SOURCE_DIR/$TARGET" ;;
  esac
done
SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
PYTHON_BIN="${PRIOR_WORK_PYTHON_BIN:-}"

if [ -z "$PYTHON_BIN" ]; then
  if [ -x "$HOME/.local/bin/python3.12" ]; then
    PYTHON_BIN="$HOME/.local/bin/python3.12"
  else
    PYTHON_BIN="$(command -v python3 2>/dev/null || true)"
  fi
fi

if [ -z "$PYTHON_BIN" ] || [ ! -x "$PYTHON_BIN" ]; then
  echo "prior-work hook: direct Python runtime missing" >&2
  exit 2
fi

# This synchronous hook is intentionally package-manager-free. On the maintainer
# machine the generic `python3 <file.py>` wrapper enters `uv run`, whose shared
# cache lock can stall every PreToolUse hook during cache maintenance.
exec "$PYTHON_BIN" "$SCRIPT_DIR/prior_work_hook.py" "$@"
