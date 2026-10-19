#!/usr/bin/env bash
# git_loss_audit.sh — report what local Git work is at risk of loss. NON-DESTRUCTIVE.
#
# Answers the authoritative "would I actually lose anything?" questions across EVERY local place
# work hides — not just branches:
#   1. LOCAL-ONLY commits — reachable from the current HEAD, any linked-worktree HEAD, a local
#      branch, a tag, or ANY OTHER local ref that holds a commit (tool-created namespaces,
#      backup refs, notes, ...), but on NO remote. Enumerating every worktree HEAD catches
#      detached commits in another checkout that `git log HEAD --branches --tags` misses;
#      enumerating every other commit-holding ref catches commits a branch/tag-only scan misses —
#      and which `git fsck --dangling` never reports either, because the ref keeps them referenced.
#      A commit pinned only by a non-standard ref falls through BOTH nets without this scan.
#   2. WORKTREES — every checkout is inspected for tracked and untracked changes. A clean branch
#      does not make a dirty linked worktree safe to remove.
#   3. STASHES — `git stash` entries are local-only by nature and a classic loss vector.
#   4. DANGLING commits — orphaned objects (dropped stashes, rebase leftovers, abandoned resets).
#      No refs or reflogs retain them; eligible for `git gc`. (git fsck --dangling)
#   5. REFLOG-ONLY commits — retained only by a reflog, including linked-worktree HEAD logs.
#      Default fsck treats reflogs as roots, so these need a separate read-only scan.
#
# It refreshes remote-tracking refs with `fetch`, then only inspects repository/worktree state. It
# never changes working files, commits, branches, stashes, or user-authored refs.
#
# Usage (run from anywhere inside the repo):
#   git_loss_audit.sh [remote]        # remote defaults to "origin"
# Caller boundary: this script has no exclusions and inspects every linked worktree, local
# ref, reflog, stash, and dangling commit. Run it only when that whole evidence surface is in scope.
#
# Exit code: 0 if nothing is at surprising risk, 1 if LOCAL-ONLY commits or dirty/inaccessible
# worktrees exist, or the ref/worktree/commit/stash/object scans are incomplete. Failed scans
# and Git diagnostics are reported, never treated as clean. 2 if outside a Git repository.
# Stashes, reflog-only and dangling commits stay exit 0 (known/recoverable, not a surprise).
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

# Tracks incomplete content scans; the verdict must never claim "clean" over them.
AUDIT_INCOMPLETE=0
AUDIT_DIAGNOSTICS="$(mktemp "${TMPDIR:-/tmp}/git-loss-audit.XXXXXX")"
trap 'rm -f "$AUDIT_DIAGNOSTICS"' EXIT

# Git can exit 0 while warning that it skipped a broken ref. Capture diagnostics as well as
# status for the content scans; a partial listing is not evidence that no work exists.
audit_read() {
  local result_name="$1" label="$2" command_output command_status
  shift 2
  if command_output="$("$@" 2>"$AUDIT_DIAGNOSTICS")"; then
    command_status=0
  else
    command_status=$?
  fi
  printf -v "$result_name" '%s' "$command_output"
  if [ -s "$AUDIT_DIAGNOSTICS" ]; then
    cat "$AUDIT_DIAGNOSTICS" >&2
  fi
  if [ "$command_status" -ne 0 ] || [ -s "$AUDIT_DIAGNOSTICS" ]; then
    echo "  ERROR: $label is INCOMPLETE (Git exit $command_status); status is UNKNOWN."
    AUDIT_INCOMPLETE=1
    return 1
  fi
  return 0
}

echo "=== Other local refs (non-standard commit refs and refs holding non-commit objects) ==="
# A commit reachable ONLY from a non-standard ref is invisible to a branch/tag scan, and the ref
# keeps it out of the dangling set too — a double blind spot. Peel every such ref here:
# commit-holding tips join the local-only reachability roots below. Check object types in
# standard namespaces too: Git's commit walk can silently skip a tag holding a tree/blob.
# Non-commit refs need manual object-preservation review; unreadable refs fail the audit.
OTHER_REF_COUNT=0
OTHER_COMMIT_COUNT=0
NONCOMMIT_REF_COUNT=0
OTHER_COMMIT_TIPS=()
OTHER_REFS_COMPLETE=1
if ! audit_read OTHER_REFS "local ref enumeration" git for-each-ref --format='%(refname)'; then
  OTHER_REFS_COMPLETE=0
fi
while IFS= read -r other_ref; do
  case "$other_ref" in
    "") continue ;;
  esac
  if other_tip="$(git rev-parse --verify --quiet "$other_ref^{commit}" 2>/dev/null)"; then
    case "$other_ref" in
      refs/heads/* | refs/tags/* | refs/remotes/* | refs/stash) continue ;;
    esac
    OTHER_REF_COUNT=$((OTHER_REF_COUNT + 1))
    OTHER_COMMIT_TIPS+=("$other_tip")
    OTHER_COMMIT_COUNT=$((OTHER_COMMIT_COUNT + 1))
    printf '  %s -> commit %s (included in the local-only scan)\n' "$other_ref" "${other_tip:0:12}"
  elif other_type="$(git cat-file -t "$other_ref" 2>/dev/null)"; then
    OTHER_REF_COUNT=$((OTHER_REF_COUNT + 1))
    NONCOMMIT_REF_COUNT=$((NONCOMMIT_REF_COUNT + 1))
    printf '  %s -> %s (non-commit ref; no commits to scan — review object preservation manually)\n' \
      "$other_ref" "$other_type"
  else
    OTHER_REF_COUNT=$((OTHER_REF_COUNT + 1))
    echo "  $other_ref -> UNREADABLE (resolves to no object; this ref could not be audited)"
    AUDIT_INCOMPLETE=1
  fi
done <<< "$OTHER_REFS"
if [ "$OTHER_REF_COUNT" -eq 0 ] && [ "$OTHER_REFS_COMPLETE" -eq 1 ]; then
  echo "  (none)"
fi

echo ""
echo "=== Local-only commits (reachable from HEAD / any local ref, on NO remote) ==="
# Positive roots: the current HEAD (only when it resolves — an unborn branch has no commit yet
# and must not fail the whole scan), every linked-worktree HEAD, and every commit-holding
# non-standard ref peeled above; --branches/--tags add their namespaces; --not --remotes
# subtracts everything any remote already has. A failure here is reported and fails the audit —
# it must never be printed as "(none)".
HEAD_ROOT=()
if git rev-parse --verify --quiet HEAD >/dev/null 2>&1; then
  HEAD_ROOT+=("HEAD")
else
  echo "  note: HEAD does not resolve to a commit (unborn branch); scanning refs without it."
fi
WORKTREE_LIST=""
if ! audit_read WORKTREE_LIST "worktree enumeration" git worktree list --porcelain; then
  AUDIT_INCOMPLETE=1
fi
WORKTREE_HEADS=()
while IFS= read -r worktree_head; do
  # An unborn worktree HEAD enumerates as all-zeros, which is not a scannable commit.
  case "$worktree_head" in
    "" | 0000000000000000000000000000000000000000) continue ;;
  esac
  WORKTREE_HEADS+=("$worktree_head")
done < <(printf '%s\n' "$WORKTREE_LIST" | sed -n 's/^HEAD //p')
LOCAL_ONLY=""
LOCAL_ONLY_FAILED=0
if ! audit_read LOCAL_ONLY "local-only commit scan" git log ${HEAD_ROOT[@]+"${HEAD_ROOT[@]}"} --branches --tags ${WORKTREE_HEADS[@]+"${WORKTREE_HEADS[@]}"} ${OTHER_COMMIT_TIPS[@]+"${OTHER_COMMIT_TIPS[@]}"} --not --remotes --oneline --decorate; then
  LOCAL_ONLY_FAILED=1
  AUDIT_INCOMPLETE=1
fi
if [ "$LOCAL_ONLY_FAILED" -eq 0 ]; then
  if [ -n "$LOCAL_ONLY" ]; then
    echo "$LOCAL_ONLY" | sed 's/^/  /'
  else
    echo "  (none)"
  fi
fi
LOCAL_ONLY_COUNT="$(printf '%s' "$LOCAL_ONLY" | grep -c . || true)"

echo ""
echo "=== Worktrees (each checkout can hide uncommitted or detached work) ==="
PRIMARY_WORKTREE="$(printf '%s\n' "$WORKTREE_LIST" | sed -n '1s/^worktree //p')"
WORKTREE_COUNT=0
DIRTY_WORKTREE_COUNT=0
UNAVAILABLE_WORKTREE_COUNT=0
while IFS= read -r worktree_path; do
  [ -z "$worktree_path" ] && continue
  WORKTREE_COUNT=$((WORKTREE_COUNT + 1))
  worktree_role="linked"
  [ "$worktree_path" = "$PRIMARY_WORKTREE" ] && worktree_role="primary"

  if [ ! -d "$worktree_path" ]; then
    printf '  %s  (%s, unavailable/prunable)\n' "$worktree_path" "$worktree_role"
    UNAVAILABLE_WORKTREE_COUNT=$((UNAVAILABLE_WORKTREE_COUNT + 1))
    continue
  fi

  if ! worktree_head="$(git -C "$worktree_path" rev-parse --short HEAD 2>/dev/null)"; then
    printf '  %s  (%s, unreadable Git state)\n' "$worktree_path" "$worktree_role"
    UNAVAILABLE_WORKTREE_COUNT=$((UNAVAILABLE_WORKTREE_COUNT + 1))
    continue
  fi
  worktree_branch="$(git -C "$worktree_path" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
  [ -z "$worktree_branch" ] && worktree_branch="detached"
  if ! audit_read worktree_status "worktree status for $worktree_path" git -C "$worktree_path" status --porcelain --untracked-files=all; then
    printf '  %s  (%s, %s@%s, status unavailable)\n' \
      "$worktree_path" "$worktree_role" "$worktree_branch" "$worktree_head"
    UNAVAILABLE_WORKTREE_COUNT=$((UNAVAILABLE_WORKTREE_COUNT + 1))
    continue
  fi
  worktree_dirty_count="$(printf '%s' "$worktree_status" | grep -c . || true)"
  if [ "$worktree_dirty_count" -gt 0 ]; then
    printf '  %s  (%s, %s@%s, DIRTY: %s path(s))\n' \
      "$worktree_path" "$worktree_role" "$worktree_branch" "$worktree_head" "$worktree_dirty_count"
    DIRTY_WORKTREE_COUNT=$((DIRTY_WORKTREE_COUNT + 1))
  else
    printf '  %s  (%s, %s@%s, clean)\n' \
      "$worktree_path" "$worktree_role" "$worktree_branch" "$worktree_head"
  fi
done < <(printf '%s\n' "$WORKTREE_LIST" | sed -n 's/^worktree //p')

echo ""
echo "=== Reflog-only commits (no current ref/worktree HEAD retains them) ==="
# Include all worktree reflogs, then subtract every current ref and the explicit worktree
# HEADs. A detached checkout is live work, not merely a reflog recovery candidate.
if ! audit_read REFLOG_ONLY "reflog-only commit scan" git rev-list --reflog --not --all ${WORKTREE_HEADS[@]+"${WORKTREE_HEADS[@]}"}; then
  AUDIT_INCOMPLETE=1
fi
REFLOG_ONLY_COUNT="$(printf '%s' "$REFLOG_ONLY" | grep -c . || true)"
if [ "$REFLOG_ONLY_COUNT" -gt 0 ]; then
  shown=0
  while IFS= read -r sha; do
    [ "$shown" -ge 20 ] && break
    if audit_read reflog_detail "reflog-only commit inspection for $sha" git log -1 --format='%h %s' "$sha"; then
      printf '  %s\n' "$reflog_detail" | cut -c1-79
    fi
    shown=$((shown + 1))
  done <<< "$REFLOG_ONLY"
  [ "$REFLOG_ONLY_COUNT" -gt 20 ] && echo "  ... and $((REFLOG_ONLY_COUNT - 20)) more"
elif [ "$AUDIT_INCOMPLETE" -eq 0 ]; then
  echo "  (none)"
fi

echo ""
echo "=== Stashes (local-only by nature — a dead disk loses these too) ==="
STASH_SCAN_COMPLETE=1
if ! audit_read STASHES "stash enumeration" git stash list; then
  STASH_SCAN_COMPLETE=0
fi
STASH_COUNT="$(printf '%s' "$STASHES" | grep -c . || true)"
if [ "$STASH_COUNT" -gt 0 ]; then
  printf '%s\n' "$STASHES" | sed 's/^/  /'
elif [ "$STASH_SCAN_COMPLETE" -eq 1 ]; then
  echo "  (none)"
fi

echo ""
echo "=== Dangling commits (no ref/reflog retention; gc-eligible) ==="
OBJECT_SCAN_COMPLETE=1
if ! audit_read OBJECT_SCAN "object scan" git fsck --dangling --no-progress; then
  OBJECT_SCAN_COMPLETE=0
fi
DANGLING="$(printf '%s\n' "$OBJECT_SCAN" | awk '/^dangling commit / {print $3}')"
DANGLING_COUNT="$(printf '%s' "$DANGLING" | grep -c . || true)"
if [ "$DANGLING_COUNT" -gt 0 ]; then
  shown=0
  while IFS= read -r sha; do
    [ "$shown" -ge 20 ] && break
    if audit_read dangling_detail "dangling commit inspection for $sha" git log -1 --format='%h %s' "$sha"; then
      printf '  %s\n' "$dangling_detail" | cut -c1-79
    fi
    shown=$((shown + 1))
  done <<< "$DANGLING"
  [ "$DANGLING_COUNT" -gt 20 ] && echo "  ... and $((DANGLING_COUNT - 20)) more"
elif [ "$OBJECT_SCAN_COMPLETE" -eq 1 ]; then
  echo "  (none)"
fi

echo ""
echo "=== Verdict ==="
echo "  local-only: ${LOCAL_ONLY_COUNT}   worktrees: ${WORKTREE_COUNT} (${DIRTY_WORKTREE_COUNT} dirty, ${UNAVAILABLE_WORKTREE_COUNT} unavailable)"
echo "  stashes: ${STASH_COUNT}   dangling: ${DANGLING_COUNT}"
echo "  reflog-only: ${REFLOG_ONLY_COUNT}"
if [ "$OTHER_REF_COUNT" -gt 0 ]; then
  echo "  other refs: ${OTHER_REF_COUNT} (${OTHER_COMMIT_COUNT} commit-holding, ${NONCOMMIT_REF_COUNT} non-commit)"
fi
if [ "$LOCAL_ONLY_COUNT" -gt 0 ]; then
  echo "  ⚠ ${LOCAL_ONLY_COUNT} commit(s) exist ONLY locally (no remote has them). Back each up with the"
  echo "    triple-backup — a local branch is not enough, since gc/disk loss can still take it:"
  echo "      git branch backup/<name> <sha> && git push origin backup/<name> && git format-patch -1 <sha> --stdout > <name>.patch"
  echo "    (git_preserve_danglers.sh only covers DANGLING commits, not these branch-reachable ones.)"
fi
if [ "$DIRTY_WORKTREE_COUNT" -gt 0 ]; then
  echo "  ⚠ ${DIRTY_WORKTREE_COUNT} worktree(s) contain uncommitted tracked or untracked files."
  echo "    Commit/preserve them and re-establish clean status; never force-remove a dirty worktree."
fi
if [ "$UNAVAILABLE_WORKTREE_COUNT" -gt 0 ]; then
  echo "  ⚠ ${UNAVAILABLE_WORKTREE_COUNT} registered worktree(s) could not be inspected. Resolve or"
  echo "    prove them prunable before cleanup; an unreadable checkout is not evidence of no work."
fi
if [ "$STASH_COUNT" -gt 0 ]; then
  echo "  • ${STASH_COUNT} stash(es) are local-only; if any is precious, turn it into a commit + push it."
fi
if [ "$DANGLING_COUNT" -gt 0 ]; then
  echo "  • ${DANGLING_COUNT} dangling commit(s) are recoverable now but gc-eligible later — pin past the"
  echo "    gc window with: git_preserve_danglers.sh"
fi
if [ "$NONCOMMIT_REF_COUNT" -gt 0 ]; then
  echo "  • ${NONCOMMIT_REF_COUNT} non-commit ref(s) need manual review before cleanup; their object"
  echo "    preservation is outside this commit-reachability audit."
fi
if [ "$REFLOG_ONLY_COUNT" -gt 0 ]; then
  echo "  • ${REFLOG_ONLY_COUNT} commit(s) survive only in reflogs; preserve authorized SHAs before"
  echo "    expiring logs or retiring worktree metadata. Pin one authorized SHA with:"
  echo "    git update-ref refs/dangling-backup/<full-sha> <full-sha> 0000000000000000000000000000000000000000"
  echo "    git_preserve_danglers.sh scans true danglers only; it does not pin reflog-only commits."
fi
if [ "$AUDIT_INCOMPLETE" -gt 0 ]; then
  echo "  ⚠ The audit is INCOMPLETE (see ERROR/UNREADABLE lines above): something that could pin"
  echo "    local work could not be inspected. An incomplete audit is not evidence of no work."
fi
if [ "$LOCAL_ONLY_COUNT" -eq 0 ] && [ "$DIRTY_WORKTREE_COUNT" -eq 0 ] && \
   [ "$UNAVAILABLE_WORKTREE_COUNT" -eq 0 ] && [ "$STASH_COUNT" -eq 0 ] && \
   [ "$DANGLING_COUNT" -eq 0 ] && [ "$REFLOG_ONLY_COUNT" -eq 0 ] && [ "$NONCOMMIT_REF_COUNT" -eq 0 ] && [ "$AUDIT_INCOMPLETE" -eq 0 ]; then
  echo "  ✓ Zero loss risk — every worktree is clean and every local commit is on a remote;"
  echo "    no stashes, reflog-only or dangling commits remain."
fi

# Exit 1 for surprising, actionable state or an incomplete audit. Stashes/dangling stay exit 0 so
# a routine stash does not cry wolf, but a dirty or unreadable worktree — or a scan that could
# not finish — must block claims that cleanup is safe.
if [ "$LOCAL_ONLY_COUNT" -gt 0 ] || [ "$DIRTY_WORKTREE_COUNT" -gt 0 ] || \
   [ "$UNAVAILABLE_WORKTREE_COUNT" -gt 0 ] || [ "$AUDIT_INCOMPLETE" -gt 0 ]; then
  exit 1
fi
exit 0
