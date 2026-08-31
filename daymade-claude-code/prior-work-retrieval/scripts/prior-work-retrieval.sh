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
PYTHON_BIN="${PRIOR_WORK_PYTHON_BIN:-${HOME:-}/.local/bin/python3.12}"

case "$PYTHON_BIN" in
  /*) ;;
  *)
    echo "prior-work hook: direct Python runtime must be an absolute path" >&2
    exit 2
    ;;
esac

if [ ! -x "$PYTHON_BIN" ]; then
  echo "prior-work hook: direct Python runtime missing" >&2
  exit 2
fi

# This synchronous hook is intentionally package-manager-free. A missing fixed
# runtime fails closed instead of falling back to PATH-based environment
# dispatch, which could reintroduce a shared package-manager cache lock.
exec "$PYTHON_BIN" "$SCRIPT_DIR/prior_work_hook.py" "$@"
