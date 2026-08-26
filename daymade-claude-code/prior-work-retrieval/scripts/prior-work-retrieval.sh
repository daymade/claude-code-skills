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
UV_BIN="${PRIOR_WORK_UV_BIN:-$HOME/.local/bin/uv}"

if [ ! -x "$UV_BIN" ]; then
  echo "prior-work hook: uv missing at $UV_BIN" >&2
  exit 2
fi
exec "$UV_BIN" run --no-project python "$SCRIPT_DIR/prior_work_hook.py" "$@"
