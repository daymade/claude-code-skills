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
#   branches  -> branches.bundle           selected branch history, verified
#   all refs  -> all-refs.bundle           every current ref, including stash,
#                                          hidden backup refs, and linked-worktree
#                                          HEADs; truly dangling objects must be
#                                          pinned first.
#
# Usage:
#   git_export_before_drop.sh [--out DIR] [--all-stashes] [--stash N]... [--branch NAME]... [--all-refs]
#   git_export_before_drop.sh --verify-current BUNDLE
#
#   --out DIR       output directory (default: ~/.git-backups/<date>-<repo>)
#   --all-stashes   export every stash in `git stash list`
#   --stash N       export stash@{N} (repeatable)
#   --branch NAME   include NAME in branches.bundle (repeatable)
#   --all-refs      create all-refs.bundle from `git bundle create --all`; use before
#                   repo/worktree convergence. Mutually exclusive with --branch.
#   --verify-current BUNDLE
#                   fail if any ref recorded in BUNDLE is now missing or points to
#                   a different object. Run immediately before the destructive step;
#                   a mismatch means the ref set moved and the bundle must be rebuilt.
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
ALL_REFS=0
VERIFY_CURRENT=""
STASH_ARGS=()
BRANCH_ARGS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --out)          OUT="${2:?--out needs a directory}"; shift 2 ;;
    --all-stashes)  ALL_STASHES=1; shift ;;
    --stash)        STASH_ARGS+=("${2:?--stash needs an index}"); shift 2 ;;
    --branch)       BRANCH_ARGS+=("${2:?--branch needs a name}"); shift 2 ;;
    --all-refs)     ALL_REFS=1; shift ;;
    --verify-current)
                    [ -z "$VERIFY_CURRENT" ] || die "--verify-current may be passed only once"
                    VERIFY_CURRENT="${2:?--verify-current needs a bundle path}"; shift 2 ;;
    -h|--help)      grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)              die "unknown argument: $1 (see --help)" ;;
  esac
done

if [ -n "$VERIFY_CURRENT" ]; then
  if [ "$ALL_STASHES" = 1 ] || [ "$ALL_REFS" = 1 ] || [ ${#STASH_ARGS[@]} -gt 0 ] || [ ${#BRANCH_ARGS[@]} -gt 0 ] || [ -n "$OUT" ]; then
    die "--verify-current is a standalone read-only mode; do not combine it with export options"
  fi

  git bundle verify "$VERIFY_CURRENT" >/dev/null || die "bundle verification failed: $VERIFY_CURRENT"
  HEAD_LIST=$(git bundle list-heads "$VERIFY_CURRENT") || die "cannot list bundle refs: $VERIFY_CURRENT"
  [ -n "$HEAD_LIST" ] || die "bundle records no refs: $VERIFY_CURRENT"

  CHECKED=0
  MOVED=0
  while read -r EXPECTED REF_NAME; do
    [ -n "${EXPECTED:-}" ] || continue
    CHECKED=$((CHECKED+1))
    if CURRENT=$(git rev-parse -q --verify "$REF_NAME" 2>/dev/null); then
      if [ "$CURRENT" = "$EXPECTED" ]; then
        echo "UNCHANGED $REF_NAME $EXPECTED"
      else
        echo "MOVED $REF_NAME expected=$EXPECTED current=$CURRENT"
        MOVED=$((MOVED+1))
      fi
    else
      echo "MISSING $REF_NAME expected=$EXPECTED"
      MOVED=$((MOVED+1))
    fi
  done <<EOF
$HEAD_LIST
EOF

  if [ "$MOVED" -gt 0 ]; then
    echo "REFSET_CHANGED checked=$CHECKED changed=$MOVED — rebuild and re-verify the bundle before deletion" >&2
    exit 1
  fi
  echo "REFS_UNCHANGED checked=$CHECKED bundle=$VERIFY_CURRENT"
  exit 0
fi

if [ "$ALL_REFS" = 1 ] && [ ${#BRANCH_ARGS[@]} -gt 0 ]; then
  die "--all-refs and --branch are mutually exclusive"
fi

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

if [ "$ALL_REFS" = 1 ]; then
  bundle="$OUT/all-refs.bundle"
  git bundle create "$bundle" --all
  git bundle verify "$bundle" >/dev/null
  echo "exported: $bundle (verified; all current refs, including worktree HEADs)"
  EXPORTED=$((EXPORTED+1))
elif [ ${#BRANCH_ARGS[@]} -gt 0 ]; then
  bundle="$OUT/branches.bundle"
  git bundle create "$bundle" "${BRANCH_ARGS[@]}"
  git bundle verify "$bundle" >/dev/null
  echo "exported: $bundle (verified; branches: ${BRANCH_ARGS[*]})"
  EXPORTED=$((EXPORTED+1))
fi

if [ "$EXPORTED" = 0 ]; then
  echo "nothing selected — pass --all-stashes, --stash N, --branch NAME, or --all-refs (see --help)"
  exit 1
fi

echo
echo "backup dir: $OUT"
echo "verify the exports above, then perform your drops/deletes."
echo "(drop stashes from the HIGHEST index down to keep numbering stable)"
