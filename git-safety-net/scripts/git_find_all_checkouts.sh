#!/usr/bin/env bash
# git_find_all_checkouts.sh — enumerate EVERY checkout of this repository on this machine,
# including the ones `git worktree list` is structurally blind to.
#
# WHY THIS EXISTS (the blind spot that makes every other audit incomplete):
#   `git worktree list` only knows LINKED worktrees — checkouts made with `git worktree add`,
#   whose `.git` is a gitlink *file* pointing back to this repository. An INDEPENDENT CLONE
#   (a second `git clone` of the same remote, or a copied directory) has its own complete
#   `.git` directory and no back-reference, so it appears in NONE of the usual instruments:
#   not `git worktree list`, not `git branch -a`, not `git fsck`, not `git stash list`,
#   not `git log --not --remotes` — all of those only ever see the repository they run in.
#
#   So an audit that enumerates checkouts via `git worktree list` will confidently report
#   "nothing at risk" while unpushed commits and uncommitted files sit in a sibling clone.
#   Untracked files are the worst case: no bundle, no `git archive`, and no `format-patch`
#   can reach a file git was never told about, so the only copy is the one on disk.
#
#   Real incident: a session stopped mid-flight and left 440 lines of a working feature as
#   untracked files in a sibling clone. The repository's own audit was clean, every branch
#   was pushed, and the work was still one `rm -rf` away from being gone for good.
#
# NON-DESTRUCTIVE: runs only `find`, `git rev-parse`, `git remote`, `git status`,
# `git rev-list`, `git config`. It never fetches, writes refs, stages, or touches a file.
# Safe to run in a dirty tree and alongside other agents.
#
# USAGE:
#   scripts/git_find_all_checkouts.sh [search-root ...]
#
#   With no arguments it searches the parent and grandparent of this repository — where
#   sibling clones actually accumulate (`~/workspace/js/repo` plus `~/workspace/repo-hotfix`).
#   Pass explicit roots to widen (`~`) or narrow the sweep. Set DEPTH=<n> to change how deep
#   each root is scanned (default 4; raise it for deeply nested layouts).
#
# EXIT: 0 when no OTHER checkout holds at-risk work; 1 when any other checkout has
# uncommitted changes, untracked files, or unpushed commits; 2 if not run inside a Git repo.

set -uo pipefail

DEPTH="${DEPTH:-4}"

git rev-parse --git-dir >/dev/null 2>&1 || {
  echo "not inside a Git repository" >&2
  exit 2
}

SELF_ROOT="$(git rev-parse --show-toplevel)"

# Normalize a remote URL so the SSH and HTTPS forms of the same repository compare equal:
#   git@github.com:owner/repo.git  ->  github.com/owner/repo
#   https://github.com/owner/repo  ->  github.com/owner/repo
normalize_remote() {
  printf '%s' "${1:-}" | sed -E 's#^[a-z+]+://##; s#^[^@/]+@##; s#:#/#; s#\.git/?$##; s#/+$##'
}

SELF_REMOTE_RAW="$(git remote get-url origin 2>/dev/null | head -1 || true)"
SELF_REMOTE="$(normalize_remote "$SELF_REMOTE_RAW")"

# Identity fallback: the ROOT COMMIT, never the directory name. Independent clones are
# usually named differently from the original (`repo` vs `repo-hotfix`) — exactly the case
# this script exists to catch — so name matching fails precisely when it matters most.
# Every clone of a repository shares its root commit, whatever the directory is called.
SELF_ROOTCOMMIT="$(git rev-list --max-parents=0 HEAD 2>/dev/null | tail -1 || true)"

if [ -n "$SELF_REMOTE" ]; then
  MATCH_MODE="remote"
  IDENTITY="$SELF_REMOTE"
elif [ -n "$SELF_ROOTCOMMIT" ]; then
  MATCH_MODE="rootcommit"
  IDENTITY="root commit ${SELF_ROOTCOMMIT}"
  echo "note: no 'origin' remote here — identifying sibling checkouts by shared root commit instead."
else
  echo "cannot identify this repository: it has no 'origin' remote and no commits yet." >&2
  exit 2
fi

if [ "$#" -gt 0 ]; then
  ROOTS=("$@")
else
  ROOTS=("$(dirname "$SELF_ROOT")" "$(dirname "$(dirname "$SELF_ROOT")")")
fi

echo "Searching for every checkout of: ${IDENTITY}"
echo "Search roots (depth ${DEPTH}): ${ROOTS[*]}"
echo

# Collect candidate .git entries. A .git DIRECTORY is a full repository (clone); a .git FILE
# is a gitlink — either a linked worktree or a submodule. Both are real checkouts that can
# hold uncommitted work, so both are reported.
CANDIDATES=()
for root in "${ROOTS[@]}"; do
  [ -d "$root" ] || continue
  while IFS= read -r gitpath; do
    [ -n "$gitpath" ] && CANDIDATES+=("$gitpath")
  done < <(
    find "$root" -maxdepth "$DEPTH" -name '.git' \( -type d -o -type f \) \
      -not -path '*/node_modules/*' -not -path '*/.venv/*' \
      -not -path '*/vendor/*' -not -path '*/.terraform/*' 2>/dev/null
  )
done

AT_RISK=0
FOUND=0
SEEN=""

for gitpath in "${CANDIDATES[@]}"; do
  checkout="$(dirname "$gitpath")"

  # De-duplicate: two search roots commonly overlap.
  case "$SEEN" in *"|$checkout|"*) continue ;; esac
  SEEN="$SEEN|$checkout|"

  if [ "$MATCH_MODE" = "remote" ]; then
    other_remote="$(normalize_remote "$(git -C "$checkout" remote get-url origin 2>/dev/null | head -1 || true)")"
    [ "$other_remote" = "$SELF_REMOTE" ] || continue
  else
    other_root="$(git -C "$checkout" rev-list --max-parents=0 HEAD 2>/dev/null | tail -1 || true)"
    [ -n "$other_root" ] && [ "$other_root" = "$SELF_ROOTCOMMIT" ] || continue
  fi

  FOUND=$((FOUND + 1))

  if [ -d "$gitpath" ]; then
    kind="independent clone"
  elif grep -q 'worktrees/' "$gitpath" 2>/dev/null; then
    kind="linked worktree"
  else
    kind="gitlink (submodule?)"
  fi

  branch="$(git -C "$checkout" rev-parse --abbrev-ref HEAD 2>/dev/null | head -1)"
  head_sha="$(git -C "$checkout" rev-parse --short HEAD 2>/dev/null | head -1)"
  modified="$(git -C "$checkout" status --porcelain 2>/dev/null | grep -cv '^??' || true)"
  untracked="$(git -C "$checkout" status --porcelain 2>/dev/null | grep -c '^??' || true)"
  unpushed="$(git -C "$checkout" rev-list --count '@{u}..HEAD' 2>/dev/null | head -1)"
  [ -n "$branch" ] || branch='?'
  [ -n "$head_sha" ] || head_sha='?'
  [ -n "$unpushed" ] || unpushed='no-upstream'

  if [ "$checkout" = "$SELF_ROOT" ]; then
    marker="  (this repository)"
  else
    marker=""
    if [ "${modified:-0}" -gt 0 ] || [ "${untracked:-0}" -gt 0 ] \
       || { [ "$unpushed" != "no-upstream" ] && [ "${unpushed:-0}" -gt 0 ]; } \
       || [ "$unpushed" = "no-upstream" ]; then
      AT_RISK=$((AT_RISK + 1))
      marker="  <-- AT RISK"
    fi
  fi

  echo "${checkout}${marker}"
  echo "    kind:      ${kind}"
  echo "    branch:    ${branch} @ ${head_sha}"
  echo "    modified:  ${modified}   untracked: ${untracked}   unpushed: ${unpushed}"
  if [ "${untracked:-0}" -gt 0 ] && [ "$checkout" != "$SELF_ROOT" ]; then
    echo "    NOTE: untracked files are unreachable by bundle/archive/format-patch."
    echo "          Copy them out directly — that disk copy is the only copy."
  fi
  echo
done

echo "------------------------------------------------------------"
echo "Checkouts found: ${FOUND}    At-risk (excluding this one): ${AT_RISK}"

if [ "$AT_RISK" -gt 0 ]; then
  cat <<'GUIDANCE'

Each AT-RISK checkout holds work that exists nowhere else. Before deleting any of them:
  1. Untracked files      -> copy them out of the tree (nothing in git can reach them).
  2. Uncommitted changes  -> `git -C <checkout> diff > <backup>/uncommitted.diff`.
  3. Unpushed commits     -> `git -C <checkout> bundle create <backup>/history.bundle origin/main..HEAD`
                             (verify it: `git bundle verify <backup>/history.bundle`).
Then judge each item by CONTENT against the surviving repository — a branch name, a commit
message, or "it looks old" is not evidence that the work already landed.
GUIDANCE
  exit 1
fi

if [ "$FOUND" -le 1 ]; then
  echo "Only this checkout exists — no hidden clone is holding work."
fi
exit 0
