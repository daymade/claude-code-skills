#!/usr/bin/env bash
# git_verify_branch_merged.sh — is a branch's CONTENT already on the base? READ-ONLY.
#
# Commit counts lie: after a squash-merge, `main..branch` shows all the branch's original commits
# as "unmerged" even though every line is on main. This judges by CONTENT using Git's own merge
# machinery, so you can safely decide whether a branch is deletable or still holds unmerged work.
#
# It is SAFETY-BIASED: it only says "safe to delete" when it can PROVE the branch is contained in
# the base. Anything it cannot prove contained is reported UNMERGED / NEEDS REVIEW — because a
# false "merged" loses work, while a false "unmerged" only costs a second look.
#
# Method (sound, not heuristic):
#   1. If the branch is an ancestor of base  -> MERGED (already in history).
#   2. Else do a trial 3-way merge of the branch INTO the base (git merge-tree, in memory, no
#      checkout). If merging changes nothing (result tree == base tree), the branch adds nothing
#      the base lacks -> MERGED (content contained) — this is what defeats the squash-merge count.
#   3. Otherwise -> UNMERGED / NEEDS REVIEW, listing the branch's contribution to inspect.
#
# It runs only fetch/merge-base/merge-tree/rev-parse/diff against explicit refs — no checkout, no
# mutation — so it is safe in a dirty tree and alongside other agents.
#
# Usage (run from anywhere inside the repo):
#   git_verify_branch_merged.sh <branch> [base]     # base defaults to origin/main
#
# <branch> resolves to your LOCAL branch of that name if it exists (that is what you would delete,
# and it is the superset of any unpushed work), else a bare ref, else origin/<branch>.
# Exit code: 0 = MERGED (safe to delete), 1 = UNMERGED / needs review, 2 = usage/repo error.
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

# Resolve the branch. Prefer the LOCAL branch of that name: it is what `git branch -D` would
# delete, and it is the superset of any commits not yet pushed to origin/<branch>. Only fall back
# to the remote-tracking copy when no local branch exists.
resolve_ref() {
  local arg="$1"
  if git rev-parse --verify --quiet "refs/heads/$arg" >/dev/null; then echo "refs/heads/$arg"; return; fi
  if git rev-parse --verify --quiet "$arg" >/dev/null;            then echo "$arg";            return; fi
  if git rev-parse --verify --quiet "origin/$arg" >/dev/null;     then echo "origin/$arg";     return; fi
  return 1
}
BRANCH_REF="$(resolve_ref "$BRANCH_ARG")" || { echo "ERROR: cannot resolve branch ref '$BRANCH_ARG'." >&2; exit 2; }
if ! git rev-parse --verify --quiet "$BASE" >/dev/null; then
  echo "ERROR: cannot resolve base ref '$BASE'." >&2; exit 2
fi

echo "Verifying '$BRANCH_REF'  vs base '$BASE'  (by content, not commit count)"
# If a local branch and its remote-tracking copy disagree, say which one we judged (the local one,
# which may hold unpushed commits) so the verdict is not silently about the wrong ref.
if [ "$BRANCH_REF" = "refs/heads/$BRANCH_ARG" ] && git rev-parse --verify --quiet "origin/$BRANCH_ARG" >/dev/null; then
  if [ "$(git rev-parse "refs/heads/$BRANCH_ARG")" != "$(git rev-parse "origin/$BRANCH_ARG")" ]; then
    echo "  (local 'refs/heads/$BRANCH_ARG' differs from 'origin/$BRANCH_ARG' — judging the LOCAL branch, the superset)"
  fi
fi
echo ""

# --- Step 1: ancestor? (fully merged into base's history, no rewrite) ---
if git merge-base --is-ancestor "$BRANCH_REF" "$BASE"; then
  echo "  ✓ MERGED (ancestor) — '$BRANCH_REF' is in '$BASE' history. Safe to delete."
  exit 0
fi

# --- Step 2: content-contained? Trial 3-way merge of branch INTO base, in memory. If merging the
#     branch changes nothing, the branch adds nothing base lacks (the classic squash/rebase case
#     where the count says "ahead" but the content is already upstream). This is sound: it is
#     exactly Git's merge, so a revert/edit the base lacks WOULD change the tree and fail this. ---
BASE_TREE="$(git rev-parse "$BASE^{tree}")"
MERGED_TREE="$(git merge-tree --write-tree "$BASE" "$BRANCH_REF" 2>/dev/null | head -1)"
MT_RC="${PIPESTATUS[0]}"
if [ "$MT_RC" -ge 128 ]; then
  # `git merge-tree --write-tree` needs git >= 2.38. Older git can't prove containment, so stay
  # safe: fall through to UNMERGED / NEEDS REVIEW rather than guess "merged".
  echo "  note: 'git merge-tree --write-tree' unavailable (git < 2.38); cannot prove content" >&2
  echo "        containment — reporting NEEDS REVIEW conservatively. Upgrade git for a MERGED verdict." >&2
elif [ "$MT_RC" -eq 0 ] && [ "$MERGED_TREE" = "$BASE_TREE" ]; then
  echo "  ✓ MERGED (content contained) — a trial merge of '$BRANCH_REF' into '$BASE' changes"
  echo "    nothing: every change the branch carries is already on base. The 'commits ahead'"
  echo "    count is a squash/rebase artifact. Safe to delete."
  exit 0
fi

# --- Step 3: cannot prove contained → report for review, listing the branch's own contribution
#     (three-dot: what the branch changed since it diverged from base). core.quotePath=false so
#     CJK/Unicode paths display correctly; --no-renames so a rename shows as add+delete; `--`
#     so a branch named like a path (e.g. `docs`) can never be mistaken for a pathspec. ---
echo "  ✗ UNMERGED / NEEDS REVIEW — a trial merge of '$BRANCH_REF' into '$BASE' would change base,"
echo "    so the branch carries content base does not already have. Its contribution to review:"
echo ""
CONTRIB="$(git -c core.quotePath=false diff --no-renames --name-status "$BASE...$BRANCH_REF" -- 2>/dev/null || true)"
if [ -n "$CONTRIB" ]; then
  printf '%s\n' "$CONTRIB" | sed 's/^/      /'
else
  echo "      (no path-level diff on the branch side; the divergence may be a merge/history"
  echo "       difference — inspect with: git log $BASE..$BRANCH_REF)"
fi
echo ""
echo "    Inspect the full contribution with:  git diff $BASE...$BRANCH_REF"
echo "    NOTE (per merge_verification.md): this is the SAFE direction — a false UNMERGED costs"
echo "    only a second look, whereas a false MERGED loses work. If base merely evolved past the"
echo "    branch, confirm the specific lines are truly redundant before deleting."
exit 1
