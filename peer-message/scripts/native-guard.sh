#!/bin/bash
# Plugin PreToolUse entry. The installer owns the fixed interpreter binding.
set -uo pipefail
trap 'rc=$?; case "$rc" in 0|2) ;; *) echo "BLOCKED (PeerMessage): native guard failed; no send authorized." >&2; exit 2;; esac' EXIT
entry="${XDG_STATE_HOME:-$HOME/.local/state}/peer-message/native-guard-entry.sh"
if [ ! -f "$entry" ]; then
  echo 'BLOCKED (PeerMessage): native guard not initialized. Run scripts/install_native_guard.py with the installer-owned fixed Python entry; do not switch transport.' >&2
  exit 2
fi
/bin/bash "$entry" "$(cd "$(dirname "$0")" && pwd)/native_guard.py"
exit $?
