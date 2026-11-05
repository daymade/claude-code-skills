#!/usr/bin/env bash
# git_export_before_drop.sh — export stashes and/or branches to durable backup
# files BEFORE you drop/delete them, so destruction is always reversible.
#
# Additive only: writes files into the output directory. Never mutates the
# repository (no drop, no branch -d, no gc) — you run the destructive step
# yourself afterwards, once the exports are verified.
#
# What it captures (per object):
#   stash N   -> stashN-<msg>.patch        full binary base-to-tracked-worktree diff
#             -> stashN-<msg>-index.patch  full binary base-to-original-index diff,
#                                          including mode and rename data
#             -> stashN-<msg>.manifest     frozen commit/tree identities and artifacts
#             -> stashN-<msg>-recover.sh   independent index/worktree restoration with
#                                          exact immutable tree-OID verification
#             -> stashN-untracked.tar      optional THIRD parent from `git stash -u`
#                                          / `-a`; an empty third-parent tree is valid
#   branches  -> branches.bundle           selected refs AND ALL reachable ancestors
#   all refs  -> all-refs.bundle           every current ref, including stash,
#                                          hidden backup refs, and linked-worktree
#                                          HEADs; truly dangling objects must be
#                                          pinned first.
#
# Usage:
#   git_export_before_drop.sh [--out DIR] [--all-stashes] [--stash N]... [--branch REF]... [--all-refs]
#   git_export_before_drop.sh --verify-current BUNDLE
#
#   --out DIR       output directory (default: ~/.git-backups/<date>-<repo>)
#   --all-stashes   export every stash in `git stash list`
#   --stash N       export the stash at index N from the frozen enumeration (repeatable)
#   --branch REF    include one branch or other named ref in branches.bundle (repeatable)
#                   This is a full reachable-history export, not an incremental diff.
#                   Apply the Skill's preservation decision before exporting a merged tip.
#   --all-refs      create all-refs.bundle from `git bundle create --all`; use before
#                   a full-ref-topology operation only when every captured ref is explicitly
#                   authorized. Mutually exclusive with --branch.
#   --verify-current BUNDLE
#                   fail if any ref recorded in BUNDLE is now missing or points to
#                   a different object. Run immediately before the destructive step;
#                   a mismatch means the ref set moved and the bundle must be rebuilt.
#
# Recovery later:
#   stash:     ./stashN-<msg>-recover.sh /path/to/repository /new/recovery/directory
#              The generated script uses separate temporary indexes/worktrees for
#              base->index and base->worktree recovery. It never applies both patches
#              successively to one index, extracts any untracked archive separately,
#              and compares every restored tree with its immutable source tree OID.
#   bundle:    git fetch <file>.bundle <branch>:restored/<branch>
#
# Note on stash numbering: indices shift as stashes are dropped or added. The exporter
# freezes the complete list and full commit OIDs before reading any stash content, then
# uses only those OIDs. Export FIRST, then drop from the HIGHEST index down so the
# numbers you exported still mean what you think they mean.

set -euo pipefail

die() { echo "error: $*" >&2; exit 2; }

require_oid() {
  local value="$1"
  local label="$2"
  case "$value" in
    ''|*[!0-9a-f]*) die "$label is not a full lowercase hexadecimal OID: $value" ;;
  esac
  [ "${#value}" -eq 40 ] || [ "${#value}" -eq 64 ] || \
    die "$label has unsupported OID length ${#value}: $value"
}

tree_for_commit() {
  local commit="$1"
  local label="$2"
  local tree
  local object_type
  tree=$(git rev-parse --verify "${commit}^{tree}") || \
    die "cannot resolve $label tree for commit $commit"
  require_oid "$tree" "$label tree"
  object_type=$(git cat-file -t "$tree") || \
    die "cannot read $label tree object $tree"
  [ "$object_type" = "tree" ] || \
    die "$label object $tree has type $object_type, expected tree"
  TREE_OID="$tree"
}

git rev-parse --git-dir >/dev/null 2>&1 || die "not inside a git repository"

REPO_ROOT=$(git rev-parse --show-toplevel)
REPO_NAME=$(basename "$REPO_ROOT")
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

# Freeze the complete stash enumeration before reading messages, parents, trees,
# patches, or archives. Every later stash read uses the selected immutable OID.
STASH_LIST=()
STASH_OIDS=()
FROZEN_STASH_OIDS=()
if [ "$ALL_STASHES" = 1 ] || [ ${#STASH_ARGS[@]} -gt 0 ]; then
  STASH_ENUMERATION=$(git stash list --format='%H') || die "cannot enumerate stashes"
  while IFS= read -r oid; do
    [ -n "$oid" ] || continue
    require_oid "$oid" "enumerated stash commit"
    FROZEN_STASH_OIDS+=("$oid")
  done <<EOF
$STASH_ENUMERATION
EOF

  if [ "$ALL_STASHES" = 1 ]; then
    for i in "${!FROZEN_STASH_OIDS[@]}"; do
      STASH_LIST+=("$i")
      STASH_OIDS+=("${FROZEN_STASH_OIDS[$i]}")
    done
  else
    for raw_index in "${STASH_ARGS[@]}"; do
      case "$raw_index" in
        ''|*[!0-9]*) die "--stash index must be a non-negative integer: $raw_index" ;;
      esac
      normalized_index="$raw_index"
      while [ "${#normalized_index}" -gt 1 ] && [ "${normalized_index#0}" != "$normalized_index" ]; do
        normalized_index="${normalized_index#0}"
      done
      [ "${#normalized_index}" -le 9 ] || die "--stash index is out of range: $raw_index"
      i=$((10#$normalized_index))
      [ "$i" -lt "${#FROZEN_STASH_OIDS[@]}" ] || \
        die "--stash index $raw_index is out of range; frozen stash count is ${#FROZEN_STASH_OIDS[@]}"
      STASH_LIST+=("$i")
      STASH_OIDS+=("${FROZEN_STASH_OIDS[$i]}")
    done
  fi
fi

EXPORTED=0

for position in "${!STASH_LIST[@]}"; do
  i="${STASH_LIST[$position]}"
  stash_oid="${STASH_OIDS[$position]}"
  require_oid "$stash_oid" "selected stash commit"

  parents_line=$(git rev-list --parents -n 1 "$stash_oid") || \
    die "cannot read parents for frozen stash commit $stash_oid"
  read -r -a parent_parts <<< "$parents_line"
  [ "${#parent_parts[@]}" -ge 3 ] || \
    die "stash commit $stash_oid has fewer than two parents"
  [ "${#parent_parts[@]}" -le 4 ] || \
    die "stash commit $stash_oid has more than three parents"
  [ "${parent_parts[0]}" = "$stash_oid" ] || \
    die "stash identity changed while reading $stash_oid"
  base_oid="${parent_parts[1]}"
  index_oid="${parent_parts[2]}"
  require_oid "$base_oid" "stash $i base commit"
  require_oid "$index_oid" "stash $i index commit"
  tree_for_commit "$stash_oid" "stash $i worktree"
  stash_tree="$TREE_OID"
  tree_for_commit "$base_oid" "stash $i base"
  base_tree="$TREE_OID"
  tree_for_commit "$index_oid" "stash $i index"
  index_tree="$TREE_OID"
  worktree_oid="$stash_oid"
  worktree_tree="$stash_tree"
  untracked_oid="-"
  untracked_tree="-"
  HAS_UNTRACKED=0
  if [ "${#parent_parts[@]}" -eq 4 ]; then
    untracked_oid="${parent_parts[3]}"
    require_oid "$untracked_oid" "stash $i untracked commit"
    tree_for_commit "$untracked_oid" "stash $i untracked"
    untracked_tree="$TREE_OID"
    HAS_UNTRACKED=1
  fi

  message=$(git show -s --format=%s "$stash_oid") || \
    die "cannot read message for frozen stash commit $stash_oid"
  slug=$(printf '%s\n' "$message" | LC_ALL=C tr -cs '[:alnum:]._-' '-' | LC_ALL=C cut -c1-60) || \
    die "cannot create a filename for frozen stash commit $stash_oid"
  slug="${slug:-wip}"
  patch_name="stash$i-$slug.patch"
  index_patch_name="stash$i-$slug-index.patch"
  manifest_name="stash$i-$slug.manifest"
  recovery_name="stash$i-$slug-recover.sh"
  patch="$OUT/$patch_name"
  index_patch="$OUT/$index_patch_name"

  # Preserve the original base-to-worktree artifact and add an independent
  # base-to-index artifact. Empty diffs are valid and must remain empty files.
  git diff --binary --full-index --find-renames --no-ext-diff --no-textconv \
    --no-color --no-relative --src-prefix=a/ --dst-prefix=b/ \
    "$base_oid" "$worktree_oid" -- > "$patch" || \
    die "cannot export base-to-worktree patch for frozen stash commit $stash_oid"
  echo "exported: $patch ($(wc -l < "$patch" | tr -d ' ') lines; base to original tracked worktree)"
  git diff --binary --full-index --find-renames --no-ext-diff --no-textconv \
    --no-color --no-relative --src-prefix=a/ --dst-prefix=b/ \
    "$base_oid" "$index_oid" -- > "$index_patch" || \
    die "cannot export base-to-index patch for frozen stash commit $stash_oid"
  echo "exported: $index_patch ($(wc -l < "$index_patch" | tr -d ' ') lines; base to original index)"

  tarball_name="-"
  if [ "$HAS_UNTRACKED" = 1 ]; then
    tarball_name="stash$i-untracked.tar"
    git -C "$REPO_ROOT" archive --format=tar "$untracked_oid" > "$OUT/$tarball_name" || \
      die "cannot archive untracked parent $untracked_oid for stash $i"
    echo "exported: $OUT/$tarball_name (untracked third parent, including a valid empty tree)"
  fi

  recovery="$OUT/$recovery_name"
  cat > "$recovery" <<EOF
#!/usr/bin/env bash
# Restore stash $i from immutable artifacts without mixing its two patch states.
set -euo pipefail
BASE_COMMIT="$base_oid"
BASE_TREE="$base_tree"
INDEX_TREE="$index_tree"
WORKTREE_TREE="$worktree_tree"
INDEX_PATCH_NAME="$index_patch_name"
WORKTREE_PATCH_NAME="$patch_name"
HAS_UNTRACKED="$HAS_UNTRACKED"
UNTRACKED_TREE="$untracked_tree"
UNTRACKED_ARCHIVE_NAME="$tarball_name"
STASH_INDEX="$i"
EOF
  cat >> "$recovery" <<'RECOVERY'
die() { echo "error: $*" >&2; exit 2; }
[ "$#" -eq 2 ] || die "usage: $0 /path/to/repository /new/recovery/directory"
REPO="$1"
DESTINATION="$2"
[ ! -e "$DESTINATION" ] || die "recovery destination already exists: $DESTINATION"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd) || die "cannot locate recovery artifacts"
REPO=$(CDPATH= cd -- "$REPO" && pwd) || die "cannot enter repository: $REPO"
mkdir -p "$DESTINATION" || die "cannot create recovery destination: $DESTINATION"
DESTINATION=$(CDPATH= cd -- "$DESTINATION" && pwd) || die "cannot resolve recovery destination"
git -C "$REPO" rev-parse --git-dir >/dev/null 2>&1 || die "not a Git repository: $REPO"
REPO_GIT_DIR=$(git -C "$REPO" rev-parse --absolute-git-dir) || die "cannot resolve repository Git directory"
git -C "$REPO" cat-file -e "${BASE_COMMIT}^{commit}" || die "base commit is unavailable: $BASE_COMMIT"

# ORIGINAL INDEX: use a dedicated index and worktree. Never apply the worktree
# patch here. The base and patch alone reconstruct the original index state.
INDEX_ROOT="$DESTINATION/original-index"
INDEX_FILE="$INDEX_ROOT/index"
INDEX_WORKTREE="$INDEX_ROOT/worktree"
mkdir -p "$INDEX_WORKTREE"
GIT_INDEX_FILE="$INDEX_FILE" GIT_WORK_TREE="$INDEX_WORKTREE" \
  git -C "$REPO" read-tree "$BASE_COMMIT" || die "cannot seed temporary index from $BASE_COMMIT"
if [ -s "$SCRIPT_DIR/$INDEX_PATCH_NAME" ]; then
  GIT_INDEX_FILE="$INDEX_FILE" GIT_WORK_TREE="$INDEX_WORKTREE" \
    git -C "$REPO" apply --cached --binary --whitespace=nowarn "$SCRIPT_DIR/$INDEX_PATCH_NAME" || \
    die "cannot apply original-index patch"
fi
ACTUAL_INDEX_TREE=$(GIT_INDEX_FILE="$INDEX_FILE" GIT_WORK_TREE="$INDEX_WORKTREE" \
  git -C "$REPO" write-tree) || die "cannot write recovered original-index tree"
[ "$ACTUAL_INDEX_TREE" = "$INDEX_TREE" ] || \
  die "original-index tree mismatch: expected=$INDEX_TREE actual=$ACTUAL_INDEX_TREE"
printf 'VERIFIED original index tree=%s\n' "$ACTUAL_INDEX_TREE"

# ORIGINAL TRACKED WORKTREE: start again from the base with a second temporary
# index and a separate worktree. Do not reuse or increment the original-index state.
WORKTREE_ROOT="$DESTINATION/original-worktree"
WORKTREE_INDEX="$WORKTREE_ROOT/index"
WORKTREE_FILES="$WORKTREE_ROOT/files"
mkdir -p "$WORKTREE_FILES"
GIT_INDEX_FILE="$WORKTREE_INDEX" GIT_WORK_TREE="$WORKTREE_FILES" \
  git -C "$REPO" read-tree "$BASE_COMMIT" || die "cannot seed temporary worktree index from $BASE_COMMIT"
GIT_INDEX_FILE="$WORKTREE_INDEX" GIT_WORK_TREE="$WORKTREE_FILES" \
  git -C "$REPO" checkout-index -a -u || die "cannot materialize base worktree"
if [ -s "$SCRIPT_DIR/$WORKTREE_PATCH_NAME" ]; then
  GIT_INDEX_FILE="$WORKTREE_INDEX" GIT_WORK_TREE="$WORKTREE_FILES" \
    git -C "$WORKTREE_FILES" --git-dir="$REPO_GIT_DIR" --work-tree="$WORKTREE_FILES" \
    apply --binary --whitespace=nowarn "$SCRIPT_DIR/$WORKTREE_PATCH_NAME" || \
    die "cannot apply original-worktree patch to temporary files"
  GIT_INDEX_FILE="$WORKTREE_INDEX" GIT_WORK_TREE="$WORKTREE_FILES" \
    git -C "$REPO" apply --cached --binary --whitespace=nowarn "$SCRIPT_DIR/$WORKTREE_PATCH_NAME" || \
    die "cannot apply original-worktree patch to its temporary index"
fi
ACTUAL_WORKTREE_TREE=$(GIT_INDEX_FILE="$WORKTREE_INDEX" GIT_WORK_TREE="$WORKTREE_FILES" \
  git -C "$REPO" write-tree) || die "cannot write recovered original-worktree tree"
[ "$ACTUAL_WORKTREE_TREE" = "$WORKTREE_TREE" ] || \
  die "original-worktree tree mismatch: expected=$WORKTREE_TREE actual=$ACTUAL_WORKTREE_TREE"

# Verify the materialized worktree bytes and modes as well as its patch-updated
# index. A fresh index avoids mistaking index-only equality for file recovery.
WORKTREE_CONTENT_INDEX="$WORKTREE_ROOT/worktree-content.index"
GIT_INDEX_FILE="$WORKTREE_CONTENT_INDEX" GIT_WORK_TREE="$WORKTREE_FILES" \
  git -C "$REPO" read-tree --empty || die "cannot create worktree-content verification index"
GIT_INDEX_FILE="$WORKTREE_CONTENT_INDEX" GIT_WORK_TREE="$WORKTREE_FILES" \
  git -C "$REPO" add -A -f || die "cannot hash recovered worktree content"
ACTUAL_WORKTREE_CONTENT_TREE=$(GIT_INDEX_FILE="$WORKTREE_CONTENT_INDEX" GIT_WORK_TREE="$WORKTREE_FILES" \
  git -C "$REPO" write-tree) || die "cannot write worktree-content verification tree"
[ "$ACTUAL_WORKTREE_CONTENT_TREE" = "$WORKTREE_TREE" ] || \
  die "materialized worktree mismatch: expected=$WORKTREE_TREE actual=$ACTUAL_WORKTREE_CONTENT_TREE"
printf 'VERIFIED original tracked worktree tree=%s\n' "$ACTUAL_WORKTREE_CONTENT_TREE"

# UNTRACKED THIRD PARENT: extract into independent state. An absent third parent
# and a present third parent whose tree is empty are both valid, distinct cases.
if [ "$HAS_UNTRACKED" = 1 ]; then
  UNTRACKED_ROOT="$DESTINATION/original-untracked"
  UNTRACKED_INDEX="$UNTRACKED_ROOT/index"
  UNTRACKED_FILES="$UNTRACKED_ROOT/files"
  mkdir -p "$UNTRACKED_FILES"
  tar -xf "$SCRIPT_DIR/$UNTRACKED_ARCHIVE_NAME" -C "$UNTRACKED_FILES" || \
    die "cannot extract original-untracked archive"
  GIT_INDEX_FILE="$UNTRACKED_INDEX" GIT_WORK_TREE="$UNTRACKED_FILES" \
    git -C "$REPO" read-tree --empty || die "cannot create untracked verification index"
  GIT_INDEX_FILE="$UNTRACKED_INDEX" GIT_WORK_TREE="$UNTRACKED_FILES" \
    git -C "$REPO" add -A -f || die "cannot hash recovered untracked content"
  ACTUAL_UNTRACKED_TREE=$(GIT_INDEX_FILE="$UNTRACKED_INDEX" GIT_WORK_TREE="$UNTRACKED_FILES" \
    git -C "$REPO" write-tree) || die "cannot write recovered untracked tree"
  [ "$ACTUAL_UNTRACKED_TREE" = "$UNTRACKED_TREE" ] || \
    die "original-untracked tree mismatch: expected=$UNTRACKED_TREE actual=$ACTUAL_UNTRACKED_TREE"
  printf 'VERIFIED original untracked tree=%s\n' "$ACTUAL_UNTRACKED_TREE"
fi
printf 'RECOVERED stash_index=%s original_index_tree=%s original_worktree_tree=%s original_untracked_tree=%s destination=%s\n' \
  "$STASH_INDEX" "$INDEX_TREE" "$WORKTREE_TREE" "$UNTRACKED_TREE" "$DESTINATION"
RECOVERY
  chmod +x "$recovery" || die "cannot make recovery script executable: $recovery"
  echo "exported: $recovery (independent recovery with exact tree-OID verification)"

  manifest="$OUT/$manifest_name"
  cat > "$manifest" <<EOF
format_version=1
stash_index=$i
stash_commit=$stash_oid
stash_tree=$stash_tree
base_commit=$base_oid
base_tree=$base_tree
index_commit=$index_oid
index_tree=$index_tree
worktree_commit=$worktree_oid
worktree_tree=$worktree_tree
untracked_commit=$untracked_oid
untracked_tree=$untracked_tree
worktree_patch=$patch_name
index_patch=$index_patch_name
untracked_archive=$tarball_name
recovery_script=$recovery_name
EOF
  echo "exported: $manifest (frozen stash/base/index/worktree identities and trees)"
  EXPORTED=$((EXPORTED+1))
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
  echo "nothing selected — pass --all-stashes, --stash N, --branch REF, or --all-refs (see --help)"
  exit 1
fi

echo
echo "backup dir: $OUT"
echo "verify the exports above, then perform your drops/deletes."
echo "(drop stashes from the HIGHEST index down to keep numbering stable)"
