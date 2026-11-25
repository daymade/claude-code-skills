#!/bin/bash
# Compatibility forwarder shim: delegates to agent-message/scripts/native-guard.sh.
set -uo pipefail
trap 'rc=$?; case "$rc" in 0|2) ;; *) echo "BLOCKED (agent-message): native guard forwarder failed; no send authorized." >&2; exit 2;; esac' EXIT

shim_dir="$(cd "$(dirname "$0")" && pwd)"
sibling="$(cd "$shim_dir/../.." && pwd)/agent-message/scripts/native-guard.sh"
if [ -f "$sibling" ]; then
  exec /bin/bash "$sibling" "$@"
fi

skills_target="$HOME/.agents/skills/agent-message/scripts/native-guard.sh"
if [ -f "$skills_target" ]; then
  exec /bin/bash "$skills_target" "$@"
fi

cache_root="$HOME/.claude/plugins/cache/daymade-skills/agent-message"
if [ -d "$cache_root" ]; then
  best=""
  best_ver=""
  for dir in "$cache_root"/*; do
    [ -d "$dir" ] || continue
    ver="$(basename "$dir")"
    [[ "$ver" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || continue
    candidate="$dir/scripts/native-guard.sh"
    [ -f "$candidate" ] || continue
    if [ -z "$best_ver" ] || [ "$(printf '%s\n%s\n' "$best_ver" "$ver" | sort -t. -k1,1n -k2,2n -k3,3n | tail -n1)" = "$ver" ]; then
      best_ver="$ver"
      best="$candidate"
    fi
  done
  if [ -n "$best" ]; then
    exec /bin/bash "$best" "$@"
  fi
fi

echo "BLOCKED (agent-message): peer-message has been replaced by agent-message, but agent-message/scripts/native-guard.sh was not found. Install it with: claude plugin install agent-message@daymade-skills" >&2
exit 2
