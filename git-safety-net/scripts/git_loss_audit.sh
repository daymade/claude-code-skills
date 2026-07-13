#!/usr/bin/env bash
# git_loss_audit.sh — report what local Git work is at risk of loss. READ-ONLY.
#
# Answers the authoritative "would I actually lose anything?" questions across EVERY local place
# work hides — not just branches:
#   1. LOCAL-ONLY commits — reachable from HEAD, a local branch, or a tag, but on NO remote. This
#      is the true loss set: a dead disk loses exactly these. Using HEAD (not just --branches)
#      catches DETACHED-HEAD commits; --tags catches tag-only commits — both invisible to a plain
#      `git log --branches --not --remotes`. (git log HEAD --branches --tags --not --remotes)
#   2. STASHES — `git stash` entries are local-only by nature and a classic loss vector.
#   3. DANGLING commits — orphaned objects (dropped stashes, rebase leftovers, abandoned resets).
#      Reflog-reachable now, but eligible for `git gc` later. (git fsck --dangling)
#
# It never mutates anything (only fetch/log/stash-list/fsck/rev-parse), so it is safe in a dirty
# tree or alongside other agents.
#
# Usage (run from anywhere inside the repo):
#   git_loss_audit.sh [remote]        # remote defaults to "origin"
#
# Exit code: 0 if nothing is at surprising risk, 1 if LOCAL-ONLY commits exist (the actionable
# case), 2 if not run inside a Git repository. Stashes and dangling commits are reported but stay
# exit 0 (known/recoverable, not a surprise) so exit 1 keeps meaning "unexpected work off-remote."
set -euo pipefail

REMOTE="${1:-origin}"

# Must be inside a work tree; fail clearly rather than emitting confusing git errors.
if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
  echo "ERROR: not inside a Git repository." >&2
  exit 2
fi
cd "$(git rev-parse --show-toplevel)"

# Refresh remote-tracking refs so the local-only check is accurate. Best-effort: if the remote is
# unreachable (offline / proxy), keep going with cached refs rather than aborting.
if git remote get-url "$REMOTE" >/dev/null 2>&1; then
  if ! git fetch "$REMOTE" --prune --quiet 2>/dev/null; then
    echo "note: could not fetch '$REMOTE' (offline?); auditing against cached remote refs." >&2
  fi
else
  echo "note: no remote named '$REMOTE'; every local commit will count as local-only." >&2
fi
# If more than one remote exists, remote-tracking refs of the OTHER remotes also suppress the
# local-only check; a stale tracking ref there could mask real loss. Flag it rather than hide it.
REMOTE_COUNT="$(git remote | grep -c . || true)"
if [ "$REMOTE_COUNT" -gt 1 ]; then
  echo "note: $REMOTE_COUNT remotes configured; only '$REMOTE' was refreshed. Stale tracking refs" >&2
  echo "      on the others could hide local-only work — 'git fetch --all --prune' to be sure." >&2
fi

echo "=== Local-only commits (reachable from HEAD / a local branch / a tag, on NO remote) ==="
# HEAD covers detached-HEAD work; --tags covers tag-only commits; both are missed by --branches.
LOCAL_ONLY="$(git log HEAD --branches --tags --not --remotes --oneline --decorate 2>/dev/null || true)"
if [ -n "$LOCAL_ONLY" ]; then
  echo "$LOCAL_ONLY" | sed 's/^/  /'
else
  echo "  (none)"
fi
LOCAL_ONLY_COUNT="$(printf '%s' "$LOCAL_ONLY" | grep -c . || true)"

echo ""
echo "=== Stashes (local-only by nature — a dead disk loses these too) ==="
STASHES="$(git stash list 2>/dev/null || true)"
STASH_COUNT="$(printf '%s' "$STASHES" | grep -c . || true)"
if [ "$STASH_COUNT" -gt 0 ]; then
  printf '%s\n' "$STASHES" | sed 's/^/  /'
else
  echo "  (none)"
fi

echo ""
echo "=== Dangling commits (orphaned; reflog-reachable now, gc-eligible later) ==="
DANGLING="$(git fsck --dangling 2>/dev/null | awk '/dangling commit/ {print $3}' || true)"
DANGLING_COUNT="$(printf '%s' "$DANGLING" | grep -c . || true)"
if [ "$DANGLING_COUNT" -gt 0 ]; then
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
echo "  local-only: ${LOCAL_ONLY_COUNT}   stashes: ${STASH_COUNT}   dangling: ${DANGLING_COUNT}"
if [ "$LOCAL_ONLY_COUNT" -gt 0 ]; then
  echo "  ⚠ ${LOCAL_ONLY_COUNT} commit(s) exist ONLY locally (no remote has them). Back each up with the"
  echo "    triple-backup — a local branch is not enough, since gc/disk loss can still take it:"
  echo "      git branch backup/<name> <sha> && git push origin backup/<name> && git format-patch -1 <sha> --stdout > <name>.patch"
  echo "    (git_preserve_danglers.sh only covers DANGLING commits, not these branch-reachable ones.)"
fi
if [ "$STASH_COUNT" -gt 0 ]; then
  echo "  • ${STASH_COUNT} stash(es) are local-only; if any is precious, turn it into a commit + push it."
fi
if [ "$DANGLING_COUNT" -gt 0 ]; then
  echo "  • ${DANGLING_COUNT} dangling commit(s) are recoverable now but gc-eligible later — pin past the"
  echo "    gc window with: git_preserve_danglers.sh"
fi
if [ "$LOCAL_ONLY_COUNT" -eq 0 ] && [ "$STASH_COUNT" -eq 0 ] && [ "$DANGLING_COUNT" -eq 0 ]; then
  echo "  ✓ Zero loss risk — every local commit is on a remote, no stashes, no orphaned objects."
fi

# Exit 1 only for the surprising, actionable case (commits off every remote); stashes/dangling are
# known/recoverable and stay exit 0 so a routine stash doesn't cry wolf.
[ "$LOCAL_ONLY_COUNT" -gt 0 ] && exit 1
exit 0
