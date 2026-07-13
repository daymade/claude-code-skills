#!/usr/bin/env bash
# git_loss_audit.sh — report what local Git work is at risk of loss. READ-ONLY.
#
# Answers the two authoritative "would I actually lose anything?" questions:
#   1. LOCAL-ONLY commits — reachable from a local branch but on NO remote. This is
#      the true loss set: a dead disk loses exactly these. (git log --branches --not --remotes)
#   2. DANGLING commits — orphaned objects (dropped stashes, rebase leftovers, abandoned
#      resets). Reflog-reachable now, but eligible for `git gc` later. (git fsck --dangling)
#
# It never mutates anything (only fetch/log/fsck/rev-parse), so it is safe in a dirty
# tree or alongside other agents.
#
# Usage (run from anywhere inside the repo):
#   git_loss_audit.sh [remote]        # remote defaults to "origin"
#
# Exit code: 0 if nothing is at risk, 1 if local-only commits exist (the actionable case),
# 2 if not run inside a Git repository. Dangling-only is exit 0 (recoverable, not urgent).
set -euo pipefail

REMOTE="${1:-origin}"

# Must be inside a work tree; fail clearly rather than emitting confusing git errors.
if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
  echo "ERROR: not inside a Git repository." >&2
  exit 2
fi
cd "$(git rev-parse --show-toplevel)"

# Refresh remote-tracking refs so the local-only check is accurate. Best-effort: if the
# remote is unreachable (offline / proxy), keep going with cached refs rather than aborting —
# loss detection still works against whatever remote state we last saw.
if git remote get-url "$REMOTE" >/dev/null 2>&1; then
  if ! git fetch "$REMOTE" --prune --quiet 2>/dev/null; then
    echo "note: could not fetch '$REMOTE' (offline?); auditing against cached remote refs." >&2
  fi
else
  echo "note: no remote named '$REMOTE'; every local commit will count as local-only." >&2
fi

echo "=== Local-only commits (reachable from a local branch, on NO remote) ==="
LOCAL_ONLY="$(git log --branches --not --remotes --oneline --decorate 2>/dev/null || true)"
if [ -n "$LOCAL_ONLY" ]; then
  echo "$LOCAL_ONLY" | sed 's/^/  /'
else
  echo "  (none)"
fi
LOCAL_ONLY_COUNT="$(printf '%s' "$LOCAL_ONLY" | grep -c . || true)"

echo ""
echo "=== Dangling commits (orphaned; reflog-reachable now, gc-eligible later) ==="
DANGLING="$(git fsck --dangling 2>/dev/null | awk '/dangling commit/ {print $3}' || true)"
DANGLING_COUNT="$(printf '%s' "$DANGLING" | grep -c . || true)"
if [ "$DANGLING_COUNT" -gt 0 ]; then
  # Show a short, human-readable sample so the user can eyeball what's orphaned.
  printf '%s\n' "$DANGLING" | head -20 | while read -r sha; do
    [ -n "$sha" ] && printf '  %s %s\n' "$(git log -1 --format='%h' "$sha" 2>/dev/null)" \
      "$(git log -1 --format='%s' "$sha" 2>/dev/null | cut -c1-64)"
  done
  [ "$DANGLING_COUNT" -gt 20 ] && echo "  ... and $((DANGLING_COUNT - 20)) more"
else
  echo "  (none)"
fi

echo ""
echo "=== Verdict ==="
echo "  local-only: ${LOCAL_ONLY_COUNT}   dangling: ${DANGLING_COUNT}"
if [ "$LOCAL_ONLY_COUNT" -gt 0 ]; then
  echo "  ⚠ ${LOCAL_ONLY_COUNT} commit(s) exist ONLY locally. Back them up before any branch cleanup:"
  echo "    git_preserve_danglers.sh   (or branch+push+patch a specific commit — see recovery_playbook.md)"
  exit 1
elif [ "$DANGLING_COUNT" -gt 0 ]; then
  echo "  ${DANGLING_COUNT} dangling commit(s) are recoverable now but gc-eligible later."
  echo "    Pin them past the gc window with: git_preserve_danglers.sh"
  exit 0
else
  echo "  ✓ Zero loss risk — every local commit is on a remote, no orphaned objects."
  exit 0
fi
