#!/usr/bin/env bash
# git_export_before_drop.sh — export stashes and/or branches to durable backup
# files BEFORE you drop/delete them, so destruction is always reversible.
#
# Additive only: writes files into the output directory. Never mutates the
# repository (no drop, no branch -d, no gc) — you run the destructive step
# yourself afterwards, once the exports are verified.
#
# What it captures (per object):
#   stash N   -> stashN-<msg>.patch        full diff incl. binary (parents 1+2)
#             -> stashN-untracked.tar      the often-forgotten THIRD parent:
#                                          untracked files carried by
#                                          `git stash -u` / `-a`. `git stash
#                                          show -p` does NOT display these, so
#                                          a patch alone silently loses them.
#   branches  -> branches.bundle           full history, verified with
#                                          `git bundle verify` before we report
#                                          success.
#
# Usage:
#   git_export_before_drop.sh [--out DIR] [--all-stashes] [--stash N]... [--branch NAME]...
#
#   --out DIR       output directory (default: ~/.git-backups/<date>-<repo>)
#   --all-stashes   export every stash in `git stash list`
#   --stash N       export stash@{N} (repeatable)
#   --branch NAME   include NAME in branches.bundle (repeatable)
#
# Recovery later:
#   patch:     git apply <file>.patch            (or `git am` for mail-format)
#   untracked: tar -xf stashN-untracked.tar      (extracts into CWD)
#   bundle:    git fetch <file>.bundle <branch>:restored/<branch>
#
# Note on stash numbering: indices shift as stashes are dropped. Export FIRST,
# then drop from the HIGHEST index down (drop stash@{2} before stash@{1}), so
# the numbers you exported still mean what you think they mean.

set -euo pipefail

die() { echo "error: $*" >&2; exit 2; }

git rev-parse --git-dir >/dev/null 2>&1 || die "not inside a git repository"

REPO_NAME=$(basename "$(git rev-parse --show-toplevel)")
OUT=""
ALL_STASHES=0
STASH_ARGS=()
BRANCH_ARGS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --out)          OUT="${2:?--out needs a directory}"; shift 2 ;;
    --all-stashes)  ALL_STASHES=1; shift ;;
    --stash)        STASH_ARGS+=("${2:?--stash needs an index}"); shift 2 ;;
    --branch)       BRANCH_ARGS+=("${2:?--branch needs a name}"); shift 2 ;;
    -h|--help)      grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)              die "unknown argument: $1 (see --help)" ;;
  esac
done

[ -z "$OUT" ] && OUT="$HOME/.git-backups/$(date +%Y-%m-%d)-$REPO_NAME"
mkdir -p "$OUT"

# Collect stash indices.
STASH_LIST=()
if [ "$ALL_STASHES" = 1 ]; then
  n=$(git stash list | wc -l | tr -d ' ')
  i=0
  while [ "$i" -lt "$n" ]; do STASH_LIST+=("$i"); i=$((i+1)); done
elif [ ${#STASH_ARGS[@]} -gt 0 ]; then
  STASH_LIST=("${STASH_ARGS[@]}")
fi

EXPORTED=0

for i in "${STASH_LIST[@]}"; do
  ref="stash@{$i}"
  git rev-parse -q --verify "$ref" >/dev/null || die "$ref does not exist"
  # Slug from the stash message, safe for filenames.
  msg=$(git stash list --format='%gs' | sed -n "$((i+1))p" | tr -cs '[:alnum:]._-' '-' | cut -c1-60)
  patch="$OUT/stash$i-${msg:-wip}.patch"
  git stash show -p --binary "$ref" > "$patch"
  echo "exported: $patch ($(wc -l < "$patch" | tr -d ' ') lines)"
  EXPORTED=$((EXPORTED+1))
  # Third parent = untracked files (stash -u / -a). Invisible to `show -p`.
  if git rev-parse -q --verify "$ref^3" >/dev/null 2>&1; then
    tarball="$OUT/stash$i-untracked.tar"
    git archive "$ref^3" -o "$tarball"
    echo "exported: $tarball (untracked third parent — files 'show -p' does not display)"
  fi
done

if [ ${#BRANCH_ARGS[@]} -gt 0 ]; then
  bundle="$OUT/branches.bundle"
  git bundle create "$bundle" "${BRANCH_ARGS[@]}"
  git bundle verify "$bundle" >/dev/null
  echo "exported: $bundle (verified; branches: ${BRANCH_ARGS[*]})"
  EXPORTED=$((EXPORTED+1))
fi

if [ "$EXPORTED" = 0 ]; then
  echo "nothing selected — pass --all-stashes, --stash N, or --branch NAME (see --help)"
  exit 1
fi

echo
echo "backup dir: $OUT"
echo "verify the exports above, then perform your drops/deletes."
echo "(drop stashes from the HIGHEST index down to keep numbering stable)"
