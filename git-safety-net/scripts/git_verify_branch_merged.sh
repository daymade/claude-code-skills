#!/usr/bin/env bash
# git_verify_branch_merged.sh — is a branch's CONTENT already on the base? READ-ONLY.
#
# Commit counts lie: after a squash-merge, `main..branch` shows all the branch's original commits
# as "unmerged" even though every line is on main. This judges by CONTENT instead, so you can
# safely decide whether a branch is deletable or still holds unmerged work.
#
# It runs only fetch/diff/log/cat-file/merge-base/rev-parse against explicit refs — no checkout,
# no mutation — so it's safe in a dirty tree and alongside other agents.
#
# Usage (run from anywhere inside the repo):
#   git_verify_branch_merged.sh <branch> [base]     # base defaults to origin/main
#
# <branch> may be a local name (resolved to origin/<branch> if that exists) or an explicit ref.
# Exit code: 0 = MERGED (content on base, deletable), 1 = UNMERGED (has content base lacks),
# 2 = usage/repo error.
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "usage: git_verify_branch_merged.sh <branch> [base]   (base defaults to origin/main)" >&2
  exit 2
fi
BRANCH_ARG="$1"
BASE="${2:-origin/main}"

if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
  echo "ERROR: not inside a Git repository." >&2
  exit 2
fi
cd "$(git rev-parse --show-toplevel)"

# Best-effort refresh so we compare against current remote state (offline → cached refs).
git fetch --all --prune --quiet 2>/dev/null || echo "note: fetch failed; comparing against cached refs." >&2

# Resolve the branch to a concrete ref. Prefer the remote-tracking copy (origin/<branch>) because
# that's the shared truth; fall back to whatever the user passed if it resolves.
resolve_ref() {
  local arg="$1"
  if git rev-parse --verify --quiet "origin/$arg" >/dev/null; then echo "origin/$arg"; return; fi
  if git rev-parse --verify --quiet "$arg" >/dev/null; then echo "$arg"; return; fi
  return 1
}
BRANCH_REF="$(resolve_ref "$BRANCH_ARG")" || { echo "ERROR: cannot resolve branch ref '$BRANCH_ARG'." >&2; exit 2; }
if ! git rev-parse --verify --quiet "$BASE" >/dev/null; then
  echo "ERROR: cannot resolve base ref '$BASE'." >&2; exit 2
fi

echo "Verifying '$BRANCH_REF'  vs base '$BASE'  (by content, not commit count)"
echo ""

# --- Check 4 first: is the branch literally an ancestor of base? (fully merged, no rewrite) ---
if git merge-base --is-ancestor "$BRANCH_REF" "$BASE"; then
  echo "  ✓ MERGED (ancestor) — '$BRANCH_REF' is in '$BASE' history. Safe to delete."
  exit 0
fi

# Not an ancestor → could be squash/rebase-merged (content on base, new shas) OR genuinely unmerged.
# --- Check 1: whole files the branch ADDS that the base lacks. A truly-unmerged new module/skill
#     surfaces here. ---
ADDED_ABSENT=""
while read -r f; do
  [ -z "$f" ] && continue
  # Is this path genuinely absent from base? (Not just moved — we check the exact path.)
  if ! git cat-file -e "$BASE:$f" 2>/dev/null; then
    ADDED_ABSENT+="$f"$'\n'
  fi
done < <(git diff "$BASE" "$BRANCH_REF" --diff-filter=A --name-only 2>/dev/null || true)

# --- Checks 2+3: for files the branch MODIFIES, is the branch's version identical to base, or at
#     least present somewhere in base's history (superseded)? If neither, it's real unmerged content. ---
MODIFIED_UNMERGED=""
while read -r f; do
  [ -z "$f" ] && continue
  # Skip files absent from base (handled above as adds/renames).
  git cat-file -e "$BASE:$f" 2>/dev/null || continue
  # Check 2: byte-identical on both sides → nothing to merge for this file.
  if git diff --quiet "$BRANCH_REF:$f" "$BASE:$f" 2>/dev/null; then
    continue
  fi
  # Check 3: does the branch's exact blob appear anywhere in base's history? If so, base passed
  # through this content and moved on (superseded old version) — not missing.
  blob="$(git rev-parse "$BRANCH_REF:$f" 2>/dev/null || true)"
  if [ -n "$blob" ] && [ -n "$(git log "$BASE" --oneline --find-object="$blob" 2>/dev/null | head -1)" ]; then
    continue
  fi
  MODIFIED_UNMERGED+="$f"$'\n'
done < <(git diff "$BASE" "$BRANCH_REF" --diff-filter=M --name-only 2>/dev/null || true)

ADDED_COUNT="$(printf '%s' "$ADDED_ABSENT" | grep -c . || true)"
MOD_COUNT="$(printf '%s' "$MODIFIED_UNMERGED" | grep -c . || true)"

if [ "$ADDED_COUNT" -eq 0 ] && [ "$MOD_COUNT" -eq 0 ]; then
  echo "  ✓ STALE-SQUASH (merged by content) — no file the branch adds is missing from base, and"
  echo "    every file it modifies is either identical to base or a superseded older version whose"
  echo "    exact content is in base's history. The 'commits ahead' count is a squash/rebase artifact."
  echo "    Safe to delete."
  exit 0
fi

echo "  ✗ UNMERGED — '$BRANCH_REF' has content that is NOT on '$BASE':"
if [ "$ADDED_COUNT" -gt 0 ]; then
  echo ""
  echo "    New files present on branch, absent from base:"
  printf '%s' "$ADDED_ABSENT" | sed 's/^/      + /'
fi
if [ "$MOD_COUNT" -gt 0 ]; then
  echo ""
  echo "    Modified files whose branch content is neither on base nor in base's history:"
  printf '%s' "$MODIFIED_UNMERGED" | sed 's/^/      ~ /'
  echo ""
  echo "    Inspect a specific one with:"
  FIRST="$(printf '%s' "$MODIFIED_UNMERGED" | head -1)"
  echo "      git diff $BASE:$FIRST $BRANCH_REF:$FIRST"
fi
echo ""
echo "    NOTE (per merge_verification.md): a false UNMERGED wastes a re-merge; verify the specific"
echo "    hunk is behavior base truly lacks before landing it — main may have evolved past the branch."
exit 1
