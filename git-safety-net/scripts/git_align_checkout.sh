#!/usr/bin/env bash
# git_align_checkout.sh — bring a checkout's on-disk content up to a target commit WITHOUT
# creating a throwaway snapshot branch and WITHOUT moving HEAD. Two modes:
#
#   --preview --target SHA
#       Read-only. Shows what --apply WOULD touch: which tracked-at-target paths differ on
#       disk, which are missing from the working tree, and which paths on disk are not part
#       of target at all (never touched by --apply). Uses a throwaway GIT_INDEX_FILE, so the
#       repository's REAL index is never read or written.
#
#   --apply --target SHA --source-worktree PATH --backup-manifest FILE
#       Materializes target's content for exactly the differing/missing paths, copying bytes
#       from a second, already-clean worktree that is checked out AT target. Every file is
#       verified safe to overwrite before it is touched (see below); anything that cannot be
#       proven safe is skipped, not overwritten on a guess. Never deletes a file, never moves
#       HEAD, never writes the real index — it only writes the working-tree files themselves.
#
# WHY THIS EXISTS instead of "snapshot the old state to a branch, then checkout target": that
# pattern works, but the snapshot branch it creates is now its own cleanup obligation — one
# more ref someone has to remember is disposable and eventually retire. This script gets the
# same safety property (nothing is lost) a different way: prove every byte about to be
# overwritten is already reproducible from target's own history or an external backup
# manifest, so there is nothing left that NEEDS a snapshot ref to recover.
#
# ORDER MATTERS: this script writes CONTENT first and deliberately leaves moving HEAD to the
# operator as a separate, later step (the trailing message tells them how). If a bystander
# process makes a bulk commit in the window between --apply finishing and HEAD actually
# moving, that commit lands on the checkout's CURRENT (still old) branch — a normal commit
# on the wrong-but-real branch, trivially recoverable. Reverse the order (move HEAD first,
# materialize content after) and the same bystander commit would land on TARGET's branch
# instead, silently reintroducing old content as a "new" commit on the branch everyone is
# about to trust. Content-then-HEAD makes the failure mode boring; HEAD-then-content makes
# it a silent regression.
#
# SAFETY-TO-OVERWRITE, checked per file before any byte is copied (--apply only):
#   1. Only regular files (mode 100644/100755 in target's tree). A symlink or submodule
#      entry is skipped and reported — those need the immutable-entry route described in
#      SKILL.md's Mode D, not a byte copy.
#   2. The CURRENT on-disk path, if it exists, must not itself be a symlink (copying bytes
#      onto whatever a symlink points at is not what this script is for).
#   3. The content about to be overwritten must be PROVEN reproducible: either its sha256
#      matches an entry in --backup-manifest (format: `sha256sum`/`shasum -a 256` output,
#      i.e. "<hash>  <relative-path>" — build one with `shasum -a 256 path... > manifest`),
#      or its current blob hash appears somewhere in target's OWN history at that exact path
#      (`git log <target> --raw -- <path>`). A path that does not yet exist on disk needs no
#      such proof — creating a new file cannot destroy anything.
# Any file failing 1-3 is skipped (not aborted): the run continues, and the final line
# reports how many were skipped. Exit is non-zero whenever anything was skipped or a
# post-write readback mismatch was found — 0 means every touched path now byte- and
# mode-matches target, verified by re-reading it, not by trusting the copy succeeded.
#
# Usage:
#   git_align_checkout.sh --preview --target SHA
#   git_align_checkout.sh --apply --target SHA --source-worktree PATH --backup-manifest FILE
#
# Hard preconditions for --apply (checked once, up front — any failure aborts the WHOLE run,
# because an unclean or wrong-HEAD source means nothing it offers can be trusted):
#   - --source-worktree's HEAD must equal --target exactly
#   - --source-worktree must be clean (`git status --porcelain=v1 --untracked-files=all` empty)
#   - --backup-manifest must exist (an empty file is valid — it just means no manifest-based
#     exceptions, only the target-history proof applies)
#
# Exit codes: 0 = preview printed, or apply completed with zero skips and zero mismatches;
# 1 = apply completed but skipped at least one file or found a mismatch on readback;
# 2 = usage/precondition error.
set -uo pipefail

die() { echo "error: $*" >&2; exit 2; }

MODE=""
TARGET=""
SOURCE_WORKTREE=""
BACKUP_MANIFEST=""
while [ $# -gt 0 ]; do
  case "$1" in
    --preview)          MODE="preview"; shift ;;
    --apply)            MODE="apply"; shift ;;
    --target)           TARGET="${2:?--target needs a commit-ish}"; shift 2 ;;
    --source-worktree)  SOURCE_WORKTREE="${2:?--source-worktree needs a path}"; shift 2 ;;
    --backup-manifest)  BACKUP_MANIFEST="${2:?--backup-manifest needs a file path}"; shift 2 ;;
    -h|--help)          grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)                  die "unknown argument: $1 (see --help)" ;;
  esac
done

[ -n "$MODE" ] || die "pass exactly one of --preview or --apply (see --help)"
[ -n "$TARGET" ] || die "--target is required"

git rev-parse --show-toplevel >/dev/null 2>&1 || die "not inside a Git repository."
cd "$(git rev-parse --show-toplevel)"
git rev-parse --verify --quiet "${TARGET}^{commit}" >/dev/null || die "--target '$TARGET' does not resolve to a commit."

TMPD="$(mktemp -d "${TMPDIR:-/tmp}/git_align_checkout.XXXXXX")" || die "mktemp -d failed"
trap 'rm -rf "$TMPD"' EXIT
TMP_INDEX="$TMPD/index"

# Load target's tree into a THROWAWAY index. GIT_INDEX_FILE scopes every command below to
# this temp file; the repository's real .git/index is never opened.
GIT_INDEX_FILE="$TMP_INDEX" git read-tree "$TARGET" || die "git read-tree $TARGET failed"

# `git diff` (no --cached) with the temp index active compares the WORKING TREE against
# that index — i.e. against target, entirely ignoring the real index and HEAD. `--no-renames`
# is load-bearing, not cosmetic: without it, rename detection depends on the running
# environment's `diff.renames` config, and a renamed-and-edited path could pair up as `R`
# and never hit the `M`/`D` cases below — decomposing every rename into add+delete instead
# means status is always one of the letters this function actually understands.
#
# `M` = content differs, `D` = target has it but the working tree does not (MISSING). Any
# OTHER status (`T` type-change — e.g. a symlink now sits where target wants a regular file;
# or anything else git diff can report) is deliberately folded into DIFFERS too, never
# dropped: the per-file safety checks downstream (regular-file-mode-only, no on-disk
# symlink) are what actually decide whether to touch it, and they can only run on a path
# that reaches them. A status this function silently ignored would be invisible to --apply
# AND to --preview alike — proven by a real fixture: a plain `case` matching only M/D once
# let a symlinked path sail through as if it did not exist at all.
compute_differs_and_missing() {
  GIT_INDEX_FILE="$TMP_INDEX" git -c core.quotePath=false diff --no-color --no-renames --name-status -- |
    while IFS=$'\t' read -r status path; do
      case "$status" in
        M) printf 'DIFFERS\t%s\n' "$path" ;;
        D) printf 'MISSING\t%s\n' "$path" ;;
        *) printf 'DIFFERS\t%s\n' "$path" ;;
      esac
    done
}

if [ "$MODE" = "preview" ]; then
  echo "# preview: current working tree vs target $TARGET"
  echo "## content-different (present in target, differs on disk)"
  compute_differs_and_missing | awk -F'\t' '$1=="DIFFERS"{print $2}'
  echo
  echo "## missing (present in target, absent from the working tree)"
  compute_differs_and_missing | awk -F'\t' '$1=="MISSING"{print $2}'
  echo
  echo "## worktree-only (on disk, not part of target — --apply never touches these)"
  GIT_INDEX_FILE="$TMP_INDEX" git ls-files --others --exclude-standard --
  exit 0
fi

# --- --apply ---
[ -n "$SOURCE_WORKTREE" ] || die "--apply requires --source-worktree"
[ -n "$BACKUP_MANIFEST" ] || die "--apply requires --backup-manifest"
[ -d "$SOURCE_WORKTREE" ] || die "--source-worktree does not exist: $SOURCE_WORKTREE"
[ -f "$BACKUP_MANIFEST" ] || die "--backup-manifest file not found: $BACKUP_MANIFEST"

SRC_HEAD="$(git -C "$SOURCE_WORKTREE" rev-parse HEAD 2>/dev/null)" || die "cannot resolve HEAD in --source-worktree: $SOURCE_WORKTREE"
TARGET_COMMIT="$(git rev-parse "${TARGET}^{commit}")"
[ "$SRC_HEAD" = "$TARGET_COMMIT" ] || die "--source-worktree HEAD ($SRC_HEAD) is not --target ($TARGET_COMMIT); refusing to trust its content"
SRC_STATUS="$(git -C "$SOURCE_WORKTREE" status --porcelain=v1 --untracked-files=all)"
[ -z "$SRC_STATUS" ] || die "--source-worktree is not clean; refusing to trust its content:
$SRC_STATUS"

TOUCHED="$TMPD/touched"
compute_differs_and_missing > "$TOUCHED"

written=0
skipped=0
> "$TMPD/written_paths"

while IFS=$'\t' read -r kind path; do
  [ -n "$path" ] || continue

  mode="$(git ls-tree "$TARGET" -- "$path" | awk '{print $1}')"
  if [ "$mode" != "100644" ] && [ "$mode" != "100755" ]; then
    echo "SKIP(non-regular mode=${mode:-absent-from-target}) $path"
    skipped=$((skipped + 1))
    continue
  fi
  if [ -L "$path" ]; then
    echo "SKIP(current path is a symlink on disk) $path"
    skipped=$((skipped + 1))
    continue
  fi

  safe=""
  if [ -e "$path" ]; then
    cur_hash="$(git hash-object -- "$path" 2>/dev/null)"
    if [ -n "$cur_hash" ]; then
      # Manifest format is exactly `shasum -a 256` / `sha256sum` output: "<hash>  <path>".
      manifest_hash="$(awk -v f="$path" '{h=$1; s=$0; sub(/^[^ ]+  */,"",s); if (s==f) print h}' "$BACKUP_MANIFEST" | head -1)"
      if [ -n "$manifest_hash" ]; then
        actual_sha256="$(shasum -a 256 -- "$path" 2>/dev/null | awk '{print $1}')"
        [ "$actual_sha256" = "$manifest_hash" ] && safe="backup-manifest"
      fi
      if [ -z "$safe" ] && git log "$TARGET" --raw --no-abbrev --format= -- "$path" 2>/dev/null |
           awk -v h="$cur_hash" '$3==h || $4==h {found=1} END {exit !found}'; then
        safe="target-history"
      fi
    fi
  else
    # Nothing on disk yet at this path — creating it cannot destroy anything.
    safe="not-present-yet"
  fi

  if [ -z "$safe" ]; then
    echo "SKIP(content not proven safe to overwrite) $path"
    skipped=$((skipped + 1))
    continue
  fi

  src_path="$SOURCE_WORKTREE/$path"
  if [ ! -e "$src_path" ]; then
    echo "SKIP(missing in --source-worktree, expected at $src_path) $path"
    skipped=$((skipped + 1))
    continue
  fi
  mkdir -p "$(dirname "$path")" || { echo "FAIL(mkdir -p) $path"; skipped=$((skipped + 1)); continue; }
  if ! cp -p "$src_path" "$path"; then
    echo "FAIL(cp) $path"
    skipped=$((skipped + 1))
    continue
  fi
  if [ "$mode" = "100755" ]; then chmod +x -- "$path"; else chmod -x -- "$path" 2>/dev/null || true; fi
  echo "WROTE(${safe}) $path"
  printf '%s\n' "$path" >> "$TMPD/written_paths"
  written=$((written + 1))
done < "$TOUCHED"

# Readback: every touched path must now byte- and mode-match target. Trust this, not the
# copy's own exit code — `cp` can succeed while writing through a stale symlink or onto an
# unexpected filesystem quirk.
mismatches=0
while IFS= read -r path; do
  [ -n "$path" ] || continue
  want_blob="$(git rev-parse "${TARGET}:${path}" 2>/dev/null)"
  got_blob="$(git hash-object -- "$path" 2>/dev/null)"
  want_mode="$(git ls-tree "$TARGET" -- "$path" | awk '{print $1}')"
  if [ -x "$path" ]; then got_mode="100755"; else got_mode="100644"; fi
  if [ "$want_blob" != "$got_blob" ] || [ "$want_mode" != "$got_mode" ]; then
    echo "MISMATCH $path want=$want_blob/$want_mode got=$got_blob/$got_mode"
    mismatches=$((mismatches + 1))
  fi
done < "$TMPD/written_paths"

echo
echo "written=$written skipped=$skipped mismatches=$mismatches"

if [ "$written" -gt 0 ] || [ "$skipped" -gt 0 ]; then
  echo
  echo "Content now matches target for every WROTE path above (verified by readback, not by"
  echo "trusting the copy). This script never moved HEAD and never touched the real index."
  echo "To finish, review and stage exactly the touched paths (never a blanket 'git add .' or"
  echo "'-A' — see SKILL.md's commit-scope hygiene), then commit or move HEAD as intended, e.g.:"
  echo "  git add -- <the paths listed as WROTE above>"
  echo "  git diff --cached --name-status      # every entry must be one you intended"
  echo "  git commit -m '...'"
  echo "or, to fast-forward this checkout's branch onto target without an intervening commit:"
  echo "  git branch -f <this-checkout-s-branch> $TARGET   # then switch/checkout as usual"
fi

[ "$skipped" -eq 0 ] && [ "$mismatches" -eq 0 ]
