#!/usr/bin/env bash
# git_hosted_vs_cached.sh — hosted-authority-first branch inventory. READ-ONLY: never
# fetches, never writes a ref.
#
# `git branch -a` / `git for-each-ref refs/remotes/<remote>` only ever show a CACHED
# snapshot from the last fetch — a second writer's push, a deleted branch, or a new
# branch on the hosting service is invisible until someone runs `git fetch`. This script
# asks the hosting service directly (`git ls-remote --heads <remote>`) and compares that
# answer against the local cache, so the four outcomes below are never confused:
#
#   SAME          — hosted and cached agree (cache is current for this branch)
#   DIFFERENT-SHA — hosted moved since the last fetch (cache is stale for this branch)
#   HOSTED-ONLY   — exists on the hosting service, no local cache entry yet
#   CACHED-ONLY   — local cache still lists it; the hosting service does not (prune candidate)
#
# `git ls-remote` reaching the network is the one thing this script cannot guarantee —
# offline, a dead proxy, or a renamed remote all make it fail. On that failure this
# script does NOT fall back to presenting the cache as if it were hosted truth: it exits
# with a DISTINCT non-zero code (3) and prints, loudly, that authority is unavailable and
# every number that follows is cache-only. Silently downgrading "hosted state" to "what
# the cache last saw" is exactly the mistake SKILL.md's rule 1 (scope has a TIME axis)
# exists to prevent.
#
# CACHED-ONLY is a prune candidate, not a delete target: `git fetch --prune <remote>`
# (or `git remote prune <remote>`) removes the stale remote-tracking ref itself; it does
# not touch any local branch, and it is safe to run alongside another writer, because it
# only rewrites this checkout's own remote-tracking cache. Set `fetch.prune=true` once
# (`git config --global fetch.prune true`) so every future fetch keeps the cache honest
# without a separate prune step.
#
# When reporting branch counts to a human, name the source: a count from this script's
# SAME/DIFFERENT-SHA/HOSTED-ONLY rows is hosting-service truth as of the moment it ran; a
# count read from `git branch -a` or `git for-each-ref` alone is cache-only and may
# already be wrong in either direction (missing a new branch, still listing a deleted one).
#
# WHY ls-remote + for-each-ref, not `git remote show <remote>` or `git fetch --dry-run
# --prune`: both alternatives also contact the network and can report drift, but their
# output is porcelain text meant for a human, not a stable field format — parsing it
# reliably across Git versions is its own hazard. `git ls-remote` is documented as the
# scripting-safe way to query a remote's refs directly, and pairing it with
# `for-each-ref` keeps every command in this script's name provably free of `fetch`,
# which matters for a read-only tool a reader must be able to audit at a glance.
#
# Usage:
#   git_hosted_vs_cached.sh [remote]        # remote defaults to "origin"
#
# Exit codes:
#   0  ran to completion, hosting service reachable (categories may still show drift)
#   2  usage or repository error (not inside a repo, remote not configured)
#   3  `git ls-remote` failed — authority unavailable; only a cache-only listing was printed
set -uo pipefail

die() { echo "error: $*" >&2; exit 2; }

REMOTE="${1:-origin}"

git rev-parse --show-toplevel >/dev/null 2>&1 || die "not inside a Git repository."
cd "$(git rev-parse --show-toplevel)"

git remote get-url "$REMOTE" >/dev/null 2>&1 || die "remote '$REMOTE' is not configured in this repository."

echo "Hosted-vs-cached branch inventory for remote '$REMOTE'  ($(date '+%F %T %z'))"
echo "(read-only: no fetch, no ref writes)"
echo

# --- ask the hosting service directly; never let a network failure masquerade as data ---
if ! HOSTED_RAW="$(git ls-remote --heads "$REMOTE" 2>&1)"; then
  echo "ERROR: 'git ls-remote --heads $REMOTE' failed — hosting service unreachable." >&2
  printf '%s\n' "$HOSTED_RAW" | sed 's/^/  /' >&2
  echo >&2
  echo "AUTHORITY UNAVAILABLE — the following numbers are from the LOCAL CACHE ONLY," >&2
  echo "not a fresh read of the hosting service. Do not treat them as current hosted" >&2
  echo "state; retry once the remote is reachable before trusting a branch count." >&2
  echo >&2
  echo "## cache-only snapshot (refs/remotes/$REMOTE/*, unverified against hosting service)"
  git for-each-ref --format='%(objectname:short)  %(refname:short)' "refs/remotes/$REMOTE" |
    awk -v r="$REMOTE" '$2 != r"/HEAD"'
  exit 3
fi

TMPD="$(mktemp -d "${TMPDIR:-/tmp}/git_hosted_vs_cached.XXXXXX")" || die "mktemp -d failed"
trap 'rm -rf "$TMPD"' EXIT

# hosted map: name sha (full) — `ls-remote --heads` prints "<sha>\trefs/heads/<name>".
printf '%s\n' "$HOSTED_RAW" | awk '{print $2, $1}' | sed 's#^refs/heads/##' | sort -k1,1 > "$TMPD/hosted"

# cached map: name sha (full), from the local remote-tracking namespace ONLY — never
# refs/heads (that is local work, not the cache of the hosting service). Excludes the
# symbolic origin/HEAD entry, which is not an independent branch.
git for-each-ref --format='%(refname:short) %(objectname)' "refs/remotes/$REMOTE" |
  sed "s#^${REMOTE}/##" | awk '$1 != "HEAD"' | sort -k1,1 > "$TMPD/cached"

join -j 1 "$TMPD/hosted" "$TMPD/cached" > "$TMPD/join"       # name hsha csha
join -v 1 -j 1 "$TMPD/hosted" "$TMPD/cached" > "$TMPD/hosted_only"
join -v 2 -j 1 "$TMPD/hosted" "$TMPD/cached" > "$TMPD/cached_only"

echo "## SAME (hosted and cached agree)"
awk '$2==$3 {printf "%s  %s\n", substr($2,1,12), $1}' "$TMPD/join"
SAME=$(awk '$2==$3' "$TMPD/join" | wc -l | tr -d ' ')

echo
echo "## DIFFERENT-SHA (hosted moved since the last fetch — cache is stale here)"
awk '$2!=$3 {printf "hosted=%s cached=%s  %s\n", substr($2,1,12), substr($3,1,12), $1}' "$TMPD/join"
DIFFERENT=$(awk '$2!=$3' "$TMPD/join" | wc -l | tr -d ' ')

echo
echo "## HOSTED-ONLY (on the hosting service, no local cache entry — fetch to see it)"
awk '{printf "%s  %s\n", substr($2,1,12), $1}' "$TMPD/hosted_only"
HOSTED_ONLY=$(wc -l < "$TMPD/hosted_only" | tr -d ' ')

echo
echo "## CACHED-ONLY (local cache still lists it; hosting service does not — prune candidate)"
awk '{printf "%s  %s\n", substr($2,1,12), $1}' "$TMPD/cached_only"
CACHED_ONLY=$(wc -l < "$TMPD/cached_only" | tr -d ' ')

echo
echo "------------------------------------------------------------"
echo "same=$SAME different-sha=$DIFFERENT hosted-only=$HOSTED_ONLY cached-only=$CACHED_ONLY  (source: hosting service, just verified)"
if [ "$CACHED_ONLY" -gt 0 ]; then
  echo "CACHED-ONLY entries are prune candidates: 'git fetch --prune $REMOTE' (or 'git remote prune $REMOTE')"
  echo "removes the stale remote-tracking ref only; it never touches a local branch."
fi
exit 0
