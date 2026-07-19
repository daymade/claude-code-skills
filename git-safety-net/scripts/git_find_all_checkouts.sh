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
# THE SECOND AXIS — FRESHNESS:
#   `unpushed` below is measured against this checkout's `origin/*` refs, which are a CACHED
#   SNAPSHOT from its last fetch, not the remote. So every checkout also reports how long ago
#   it last heard from its remote, and a stale one is called out explicitly.
#
#   Read the number in the right direction. For "what would be lost" a stale cache is safe:
#   it can only over-report unpushed work, never hide it. For "is this already upstream?" it
#   fails the other way — work the remote already has reads as unique, and re-shipping it can
#   revert whatever was built on top of it in the meantime. Fetch before that second question.
#
# NON-DESTRUCTIVE: runs only `find` plus read-only Git queries. Repository-provided
# fsmonitor commands are disabled and optional index refreshes are suppressed before
# inspecting discovered checkouts. It never fetches, writes refs, stages, or touches a
# file. Safe to run in a dirty tree and alongside other agents.
#
# USAGE:
#   scripts/git_find_all_checkouts.sh [search-root ...]
#
#   With no arguments it searches the parent and grandparent of this repository — where
#   sibling clones actually accumulate (`~/workspace/js/repo` plus `~/workspace/repo-hotfix`).
#   Pass explicit roots to widen (`~`) or narrow the sweep. Set DEPTH=<n> to change how deep
#   each root is scanned (default 4; raise it for deeply nested layouts). Set STALE_AFTER=<s>
#   to change when a checkout's cached remote refs are called stale (default 3600 seconds).
#
# EXIT: 0 when no OTHER checkout holds at-risk work; 1 when any other checkout has
# uncommitted changes, untracked files, or unpushed commits; 2 if not run inside a Git repo.

set -uo pipefail

DEPTH="${DEPTH:-4}"
STALE_AFTER="${STALE_AFTER:-3600}"

safe_git() {
  GIT_OPTIONAL_LOCKS=0 git --no-pager \
    -c core.fsmonitor=false \
    -c core.untrackedCache=false \
    -c status.submoduleSummary=false \
    "$@"
}

canonical_dir() {
  (cd "$1" 2>/dev/null && pwd -P)
}

# BSD (macOS) and GNU stat disagree on the mtime flag, and they disagree destructively:
# to GNU, `-f` means --file-system, so `stat -f %m` does not simply fail there. It dumps
# filesystem info to stdout *and then* exits nonzero, so a plain `A || B` fallback returns
# that dump concatenated with B's answer — a multi-line string that blows up the arithmetic
# downstream. Validate that what came back is actually an integer, on every branch.
file_mtime() {
  local mtime
  mtime="$(stat -f %m "$1" 2>/dev/null)"
  case "$mtime" in ''|*[!0-9]*) mtime="$(stat -c %Y "$1" 2>/dev/null)" ;; esac
  case "$mtime" in ''|*[!0-9]*) return 1 ;; esac
  printf '%s\n' "$mtime"
}

# How long ago a checkout last heard from its remote. FETCH_HEAD's mtime is the right
# signal: git rewrites it on every fetch even when nothing changed, whereas a
# remote-tracking reflog only gains an entry when the remote actually moved — so a
# reflog-based age reads "old" after a fetch that found no news, which is the opposite
# of what we need. Prints seconds; returns 1 when this checkout has never fetched.
fetch_age_seconds() {
  local gitdir fetch_head mtime
  gitdir="$(safe_git -C "$1" rev-parse --git-dir 2>/dev/null)" || return 1
  case "$gitdir" in /*) ;; *) gitdir="$1/$gitdir" ;; esac
  fetch_head="$gitdir/FETCH_HEAD"
  [ -f "$fetch_head" ] || return 1
  mtime="$(file_mtime "$fetch_head")" || return 1
  [ -n "$mtime" ] || return 1
  echo $(( $(date +%s) - mtime ))
}

human_age() {
  if   [ "$1" -lt 3600 ]  ; then echo "$(( $1 / 60 ))m ago"
  elif [ "$1" -lt 86400 ] ; then echo "$(( $1 / 3600 ))h ago"
  else                           echo "$(( $1 / 86400 ))d ago"
  fi
}

safe_git rev-parse --git-dir >/dev/null 2>&1 || {
  echo "not inside a Git repository" >&2
  exit 2
}

SELF_ROOT_RAW="$(safe_git rev-parse --show-toplevel)"
SELF_ROOT="$(canonical_dir "$SELF_ROOT_RAW")" || {
  echo "cannot resolve this repository's working tree" >&2
  exit 2
}

# Normalize a remote URL so the SSH and HTTPS forms of the same repository compare equal:
#   git@github.com:owner/repo.git  ->  github.com/owner/repo
#   https://github.com/owner/repo  ->  github.com/owner/repo
normalize_remote() {
  printf '%s' "${1:-}" | sed -E 's#^[a-z+]+://##; s#^[^@/]+@##; s#:#/#; s#\.git/?$##; s#/+$##'
}

SELF_REMOTE_RAW="$(safe_git remote get-url origin 2>/dev/null | head -1 || true)"
SELF_REMOTE="$(normalize_remote "$SELF_REMOTE_RAW")"

# Identity fallback: any shared commit, never the directory name. A shallow clone
# cannot see the repository's true root, but it still carries at least its shallow
# boundary and HEAD. Checking the candidate's reachable commits against this
# repository therefore works for full, shallow, detached, and differently named
# copies without trusting a mutable path label.
shares_commit_with_self() {
  local checkout="$1"
  local oid
  while IFS= read -r oid; do
    [ -n "$oid" ] || continue
    if safe_git -C "$SELF_ROOT" cat-file -e "${oid}^{commit}" 2>/dev/null; then
      return 0
    fi
  done < <(safe_git -C "$checkout" rev-list --all HEAD 2>/dev/null)
  return 1
}

SELF_HEAD="$(safe_git rev-parse --verify HEAD 2>/dev/null | head -1 || true)"

if [ -n "$SELF_REMOTE" ]; then
  MATCH_MODE="remote"
  IDENTITY="$SELF_REMOTE"
elif [ -n "$SELF_HEAD" ]; then
  MATCH_MODE="history"
  IDENTITY="history shared with ${SELF_HEAD}"
  echo "note: no 'origin' remote here — identifying sibling checkouts by shared commit history instead."
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
FOUND_SELF=0
STALE_SEEN=0
SEEN=""

for gitpath in "${CANDIDATES[@]}"; do
  checkout_raw="$(dirname "$gitpath")"
  checkout="$(canonical_dir "$checkout_raw")" || continue

  # De-duplicate: two search roots commonly overlap.
  case "$SEEN" in *"|$checkout|"*) continue ;; esac
  SEEN="$SEEN|$checkout|"

  if [ "$MATCH_MODE" = "remote" ]; then
    other_remote="$(normalize_remote "$(safe_git -C "$checkout" remote get-url origin 2>/dev/null | head -1 || true)")"
    if [ -n "$other_remote" ]; then
      [ "$other_remote" = "$SELF_REMOTE" ] || continue
    else
      # A copied checkout may deliberately or accidentally lose its origin. It is
      # still related when it shares any commit, even if it is shallow and cannot
      # see the true root. That is exactly the hidden work this scanner targets.
      shares_commit_with_self "$checkout" || continue
    fi
  else
    shares_commit_with_self "$checkout" || continue
  fi

  FOUND=$((FOUND + 1))

  if [ -d "$checkout/.git" ]; then
    kind="independent clone"
  elif grep -q 'worktrees/' "$checkout/.git" 2>/dev/null; then
    kind="linked worktree"
  else
    kind="gitlink (submodule?)"
  fi

  branch="$(safe_git -C "$checkout" rev-parse --abbrev-ref HEAD 2>/dev/null | head -1)"
  head_sha="$(safe_git -C "$checkout" rev-parse --short HEAD 2>/dev/null | head -1)"
  if status_output="$(safe_git -C "$checkout" status --porcelain=v1 --untracked-files=all --ignore-submodules=all 2>/dev/null)"; then
    modified="$(printf '%s' "$status_output" | grep -cv '^??' || true)"
    untracked="$(printf '%s' "$status_output" | grep -c '^??' || true)"
  else
    modified='unknown'
    untracked='unknown'
  fi
  # Upstream configuration is not a preservation boundary. A detached or
  # no-upstream HEAD is safe when every commit is already reachable from some
  # locally known remote-tracking ref.
  unpushed="$(safe_git -C "$checkout" rev-list --count HEAD --not --remotes 2>/dev/null | head -1)"
  [ -n "$branch" ] || branch='?'
  [ -n "$head_sha" ] || head_sha='?'
  [ -n "$unpushed" ] || unpushed='unknown'

  # Staleness is reported, never escalated to AT RISK: a cached ref can only over-report
  # unpushed work, so flagging it as danger would cry wolf on healthy checkouts and teach
  # people to ignore the marker that does mean something.
  if fetch_age="$(fetch_age_seconds "$checkout")"; then
    freshness="last fetched $(human_age "$fetch_age")"
    if [ "$fetch_age" -gt "$STALE_AFTER" ]; then
      freshness="${freshness}   <-- STALE, fetch before judging 'already merged'"
      STALE_SEEN=$((STALE_SEEN + 1))
    fi
  else
    freshness="never fetched in this checkout"
    STALE_SEEN=$((STALE_SEEN + 1))
  fi

  if [ "$checkout" = "$SELF_ROOT" ]; then
    FOUND_SELF=1
    marker="  (this repository)"
  else
    marker=""
    if [ "$modified" = 'unknown' ] || [ "$untracked" = 'unknown' ] \
       || [ "$unpushed" = 'unknown' ] \
       || [ "${modified:-0}" -gt 0 ] || [ "${untracked:-0}" -gt 0 ] \
       || [ "${unpushed:-0}" -gt 0 ]; then
      AT_RISK=$((AT_RISK + 1))
      marker="  <-- AT RISK"
    fi
  fi

  echo "${checkout}${marker}"
  echo "    kind:      ${kind}"
  echo "    branch:    ${branch} @ ${head_sha}"
  echo "    modified:  ${modified}   untracked: ${untracked}   unpushed: ${unpushed} (vs cached refs)"
  echo "    remote:    ${freshness}"
  if [ "${untracked:-0}" -gt 0 ] && [ "$checkout" != "$SELF_ROOT" ]; then
    echo "    NOTE: untracked files are unreachable by bundle/archive/format-patch."
    echo "          Copy them out directly — that disk copy is the only copy."
  fi
  echo
done

echo "------------------------------------------------------------"
echo "Checkouts found: ${FOUND}    At-risk (excluding this one): ${AT_RISK}"

if [ "$STALE_SEEN" -gt 0 ]; then
  cat <<'FRESHNESS'

FRESHNESS: some checkout above has not fetched recently, so its `unpushed` count was measured
against a cached snapshot of the remote. That direction is safe for "what would be lost" — a
stale cache over-reports unpushed work, it cannot hide it. It is NOT safe for the opposite
question. Before concluding a branch is unmerged, or that local work still needs shipping:

  git fetch --all --prune

Skipping that has a specific failure shape: work the remote already has reads as unique, so it
gets re-shipped — and if the remote improved it in the meantime, the "restore" reverts those
improvements while looking like a rescue.
FRESHNESS
fi

if [ "$AT_RISK" -gt 0 ]; then
  cat <<'GUIDANCE'

Each AT-RISK checkout may hold work that is not proven preserved elsewhere. Before deleting it:
  1. Untracked files      -> copy them out of the tree (nothing in git can reach them).
  2. Uncommitted changes  -> `git -C <checkout> diff > <backup>/uncommitted.diff`.
  3. Unpushed commits     -> `git -C <checkout> bundle create <backup>/history.bundle HEAD --not --remotes`
                             (verify it: `git bundle verify <backup>/history.bundle`).
Then judge each item by CONTENT against the surviving repository — a branch name, a commit
message, or "it looks old" is not evidence that the work already landed.
GUIDANCE
  exit 1
fi

if [ "$FOUND" -eq 0 ]; then
  echo "No matching checkout was found under the requested search roots."
elif [ "$FOUND" -eq 1 ] && [ "$FOUND_SELF" -eq 1 ]; then
  echo "Only this checkout exists — no hidden clone is holding work."
elif [ "$FOUND_SELF" -eq 0 ]; then
  echo "Note: the current repository was outside the requested search roots."
fi
exit 0
