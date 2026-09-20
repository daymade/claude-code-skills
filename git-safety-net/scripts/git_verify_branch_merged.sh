#!/usr/bin/env bash
# git_verify_branch_merged.sh — is a branch's CONTENT already on the base? NON-DESTRUCTIVE.
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
#   3. Else, if --merge-commit was given, try that rung (see below) before giving up.
#   4. Otherwise -> UNMERGED / NEEDS REVIEW, listing the branch's contribution to inspect.
#
# By default it refreshes remote-tracking refs, then runs merge-base/merge-tree/rev-parse/diff
# against explicit refs. It never changes working files, commits, branches, stashes, or
# user-authored refs.
#
# Usage (run from anywhere inside the repo):
#   git_verify_branch_merged.sh <branch> [base] [options]   # base defaults to origin/main
#
# <branch> resolves to your LOCAL branch of that name if it exists (that is what you would delete,
# and it is the superset of any unpushed work), else a bare ref, else origin/<branch>. This
# positional form is unchanged from every earlier version of this script.
#
# Options (may appear anywhere on the command line, mixed with the positionals):
#   --no-fetch            skip the remote-tracking refresh entirely (fully offline; no network
#                          attempt at all, not even one that could fail and fall back)
#   --base REF-OR-SHA      same effect as the second positional argument; use when driving this
#                          script from another tool with named flags. Conflicts with also passing
#                          a second positional argument — pass base exactly one way.
#   --merge-commit SHA     an extra rung tried only when Step 1 (ancestor) and Step 2 (trial merge
#                          into the CURRENT base) both fail to prove MERGED. Requires SHA to be an
#                          ancestor of base (refused otherwise — see below), then trial-merges the
#                          branch into SHA instead of into base. If that merge changes nothing
#                          (result tree == SHA^{tree}), the branch's content was already complete
#                          AT THAT HISTORICAL MERGE COMMIT. This is the rung for exactly the case
#                          Step 2 cannot clear: a squash-merge landed the branch, and base later
#                          changed the SAME LINES again (the next version bump, a rewritten entry)
#                          such that a trial merge against the CURRENT base now conflicts instead
#                          of reproducing its tree. An edit elsewhere — another file, or other
#                          lines of the same file — does not trigger this; Step 2 alone still
#                          proves containment there, and this rung is never reached. The
#                          typical caller is a hosting platform's "merged PR" record: pass the
#                          PR's own merge-commit SHA once you have independently confirmed the
#                          branch's tip equals that PR's head and the PR's state is MERGED — this
#                          script does not query any hosting API itself.
#                          BOUNDARY, printed in the verdict: this rung proves containment AT THE
#                          MERGE COMMIT. It does NOT prove the CURRENT base still contains the
#                          content — base may have reverted or overwritten it since. For "does base
#                          contain it RIGHT NOW", trust Step 2 (trial merge into the current base),
#                          not this rung; see references/merge_verification.md for the two-question
#                          split ("landed once" vs "still there now") and its own investigation
#                          procedure for the case where they disagree.
#
# Exit code: 0 = MERGED (safe to delete), 1 = UNMERGED / needs review, 2 = usage/repo error
# (includes: unresolvable branch/base, base-is-the-target, and a --merge-commit that is not an
# ancestor of base — all refused rather than guessed at).
set -euo pipefail

usage() {
  echo "usage: git_verify_branch_merged.sh <branch> [base] [--no-fetch] [--base REF] [--merge-commit SHA]" >&2
  echo "       (base defaults to origin/main; see the script header for option semantics)" >&2
}

NO_FETCH=0
BASE_FLAG=""
MERGE_COMMIT=""
POSITIONAL=()
while [ $# -gt 0 ]; do
  case "$1" in
    --no-fetch)     NO_FETCH=1; shift ;;
    --base)         BASE_FLAG="${2:?--base needs a ref or sha}"; shift 2 ;;
    --merge-commit) MERGE_COMMIT="${2:?--merge-commit needs a sha}"; shift 2 ;;
    -h|--help)      grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    --)             shift; while [ $# -gt 0 ]; do POSITIONAL+=("$1"); shift; done ;;
    -*)             echo "ERROR: unknown option: $1" >&2; usage; exit 2 ;;
    *)              POSITIONAL+=("$1"); shift ;;
  esac
done

if [ "${#POSITIONAL[@]}" -lt 1 ]; then
  usage
  exit 2
fi
BRANCH_ARG="${POSITIONAL[0]}"
if [ -n "$BASE_FLAG" ]; then
  if [ "${#POSITIONAL[@]}" -ge 2 ]; then
    echo "ERROR: base given both positionally ('${POSITIONAL[1]}') and via --base ('$BASE_FLAG'); pass only one." >&2
    exit 2
  fi
  BASE="$BASE_FLAG"
else
  BASE="${POSITIONAL[1]:-origin/main}"
fi

if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
  echo "ERROR: not inside a Git repository." >&2
  exit 2
fi
cd "$(git rev-parse --show-toplevel)"

# Best-effort refresh so we compare against current remote state (offline → cached refs).
# --no-fetch skips this outright — no network attempt at all, for a caller that already knows
# it is offline or is deliberately judging against a frozen cache (e.g. a batch classifier that
# fetched once for the whole batch and does not want N redundant fetches).
if [ "$NO_FETCH" = 1 ]; then
  echo "note: --no-fetch — comparing against whatever refs are already cached, no network attempt made." >&2
else
  git fetch --all --prune --quiet 2>/dev/null || echo "note: fetch failed; comparing against cached refs." >&2
fi

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
BASE_SYMBOLIC="$(git rev-parse --symbolic-full-name "$BASE" 2>/dev/null || true)"
if [ -n "$BASE_SYMBOLIC" ] && [ "$BRANCH_REF" = "$BASE_SYMBOLIC" ]; then
  echo "ERROR: target '$BRANCH_REF' is the base ref itself; refusing to label the base deletable." >&2
  exit 2
fi

# --merge-commit's precondition is checked up front (fail fast on bad input) even though the
# rung itself is only USED later, after Steps 1-2 fail to prove MERGED — a caller who passed a
# bad SHA should see that immediately, not only on the rare branch where the rung would fire.
if [ -n "$MERGE_COMMIT" ]; then
  if ! git rev-parse --verify --quiet "${MERGE_COMMIT}^{commit}" >/dev/null; then
    echo "ERROR: --merge-commit '$MERGE_COMMIT' does not resolve to a commit." >&2
    exit 2
  fi
  if ! git merge-base --is-ancestor "$MERGE_COMMIT" "$BASE"; then
    echo "ERROR: --merge-commit '$MERGE_COMMIT' is not an ancestor of base '$BASE'; refusing to use" >&2
    echo "       it as a landed-at-merge baseline (it could be from an unrelated or reverted line" >&2
    echo "       of history that never reached this base)." >&2
    exit 2
  fi
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
MERGE_OUTPUT=""
# A real conflict makes merge-tree exit 1. Capture that status inside an `if`: unlike a bare
# command substitution, this cannot trigger `set -e` and silently terminate before the script
# prints its conservative NEEDS REVIEW verdict.
if MERGE_OUTPUT="$(git merge-tree --write-tree "$BASE" "$BRANCH_REF" 2>&1)"; then
  MT_RC=0
else
  MT_RC=$?
fi
# First line only, without a pipe: a real conflict can make $MERGE_OUTPUT far larger than the
# pipe buffer (measured: 869 lines / 248KB on one repository's conflicting-branch pair). Piping
# it through `head -1` lets `head` close its read end as soon as it has that line, and the
# `printf` on the write end then gets SIGPIPE on its next write of the remaining buffered output
# — bash reports that as exit 141. This assignment has no enclosing `if`, so under `set -e` that
# 141 terminates the script before it can print the conservative NEEDS REVIEW verdict, turning a
# routine conflict into a silent crash. Parameter expansion never forks a second process, so there
# is no pipe and nothing to receive SIGPIPE.
MERGED_TREE="${MERGE_OUTPUT%%$'\n'*}"
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

# --- Step 3: the --merge-commit rung, only reached because Steps 1-2 could not prove MERGED
#     against the CURRENT base. Trial-merge the branch into the historical merge commit instead
#     — this is what still says LANDED when a squash landed the branch and base later changed the
#     same lines, which is exactly the shape Step 2 cannot clear (see the option's doc comment
#     above). Step 2's own MT_RC/MERGED_TREE (still in scope) tell us WHICH shape Step 2 failed
#     with — a conflict (base moved the same lines forward again, nothing missing) reads very
#     differently from a clean merge that would still change base (base dropped the content after
#     landing it) — so that shape is reported alongside the verdict instead of only "could not
#     prove this", which collapses the two into one indistinguishable message. ---
if [ -n "$MERGE_COMMIT" ]; then
  if [ "$MT_RC" -ge 128 ]; then
    CURRENT_BASE_SHAPE="unknown (git merge-tree unavailable against current base)"
  elif [ "$MT_RC" -eq 0 ]; then
    # Step 2 already returned above when MT_RC=0 and trees matched, so reaching this line means
    # they did not: a clean merge that still changes base.
    CB_NFILES="$(git diff --name-only "$BASE_TREE" "$MERGED_TREE" 2>/dev/null | wc -l | tr -d ' ')"
    CURRENT_BASE_SHAPE="clean-changes:${CB_NFILES}"
  else
    CURRENT_BASE_SHAPE="conflict"
  fi

  MC_TREE="$(git rev-parse "${MERGE_COMMIT}^{tree}")"
  MC_OUTPUT=""
  if MC_OUTPUT="$(git merge-tree --write-tree "$MERGE_COMMIT" "$BRANCH_REF" 2>&1)"; then
    MC_RC=0
  else
    MC_RC=$?
  fi
  # Same SIGPIPE hazard as $MERGED_TREE above, and the same fix: no pipe, no early-closing reader.
  MC_MERGED_TREE="${MC_OUTPUT%%$'\n'*}"
  if [ "$MC_RC" -eq 0 ] && [ "$MC_MERGED_TREE" = "$MC_TREE" ]; then
    echo "  ✓ LANDED AT MERGE ${MERGE_COMMIT:0:12} — a trial merge of '$BRANCH_REF' into that merge"
    echo "    commit changes nothing: the branch's content was fully present there. The CURRENT"
    echo "    base trial merge (Step 2) could not prove this — current-base shape: $CURRENT_BASE_SHAPE."
    echo "    BOUNDARY: this proves containment AT THAT MERGE COMMIT, not that '$BASE' still"
    echo "    contains it now."
    case "$CURRENT_BASE_SHAPE" in
      clean-changes:*)
        echo "    The current-base merge was CLEAN but would still change base — that shape, not a"
        echo "    conflict, is the candidate-regression fingerprint: see"
        echo "    references/merge_verification.md's 'Landed, then lost' investigation before"
        echo "    concluding whether this is actually missing now."
        ;;
      conflict)
        echo "    The current-base merge CONFLICTED — base changed the same lines again (e.g. a"
        echo "    later version bump); that is the routine case this rung exists for, not evidence"
        echo "    of anything missing."
        ;;
    esac
    exit 0
  fi
  echo "  (--merge-commit ${MERGE_COMMIT:0:12} also does not prove containment: a trial merge of" >&2
  echo "   '$BRANCH_REF' into it still changes that commit's tree — falling through to NEEDS REVIEW.)" >&2
fi

# --- Step 4: cannot prove contained → report for review, listing the branch's own contribution
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
