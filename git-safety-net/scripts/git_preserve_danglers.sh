#!/usr/bin/env bash
# git_preserve_danglers.sh — make orphaned commits un-loseable BEFORE any cleanup. Additive-only.
#
# Dangling commits (dropped stashes, rebase leftovers, abandoned resets, detached-HEAD work) are
# recoverable ONLY until `git gc` runs. This pins each one under a hidden ref namespace
# refs/dangling-backup/<sha> — a referenced object is never garbage-collected — so they survive
# gc without cluttering `git branch` or `git stash list`. Optionally exports a .patch per commit.
#
# It only ever runs read-only git plus `git update-ref` to ADD refs. It never deletes a ref,
# never checks out, never resets, never runs gc — so it cannot make a loss worse.
#
# Usage (run from anywhere inside the repo):
#   git_preserve_danglers.sh                       # pin all dangling commits
#   git_preserve_danglers.sh --patch-dir DIR       # pin AND write DIR/<shortsha>-<slug>.patch each
#
# After running, `git for-each-ref refs/dangling-backup/` lists what was pinned. To unpin later
# (only once you've confirmed the content is safe on a remote), see the SKILL.md troubleshooting.
set -euo pipefail

PATCH_DIR=""
while [ $# -gt 0 ]; do
  case "$1" in
    --patch-dir)
      PATCH_DIR="${2:-}"
      if [ -z "$PATCH_DIR" ]; then echo "ERROR: --patch-dir needs a directory argument." >&2; exit 2; fi
      shift 2 ;;
    -h|--help)
      grep '^# ' "$0" | sed 's/^# //'; exit 0 ;;
    *)
      echo "ERROR: unknown argument '$1' (expected --patch-dir DIR)." >&2; exit 2 ;;
  esac
done

if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
  echo "ERROR: not inside a Git repository." >&2
  exit 2
fi
cd "$(git rev-parse --show-toplevel)"

if [ -n "$PATCH_DIR" ]; then
  mkdir -p "$PATCH_DIR"
fi

# Collect dangling commit shas. `git fsck --dangling` also reports dangling blobs/trees; we only
# pin commits (a whole recoverable state). Blobs/trees are reachable from a pinned commit anyway.
DANGLING="$(git fsck --dangling 2>/dev/null | awk '/dangling commit/ {print $3}' || true)"

if [ -z "$DANGLING" ]; then
  echo "No dangling commits — nothing to preserve. (If you expected some, they may already be"
  echo "pinned, or reachable from a branch. Run git_loss_audit.sh for the full picture.)"
  exit 0
fi

PINNED=0
PATCHED=0
while read -r sha; do
  [ -z "$sha" ] && continue
  # Pin it. refs/dangling-backup/<full-sha> is unique per commit and invisible to `git branch`.
  git update-ref "refs/dangling-backup/$sha" "$sha"
  PINNED=$((PINNED + 1))

  SUBJECT="$(git log -1 --format='%s' "$sha" 2>/dev/null | cut -c1-64)"
  printf '  pinned %s  %s\n' "$(git rev-parse --short "$sha")" "$SUBJECT"

  if [ -n "$PATCH_DIR" ]; then
    # Stash commits (subject "WIP on …") are diffs against their parent and don't format-patch
    # cleanly as a standalone commit; skip patch export for them but keep them pinned (the pin is
    # the real safety). For normal commits, a single-commit patch is a repo-independent backup.
    if git log -1 --format='%s' "$sha" 2>/dev/null | grep -q '^WIP on '; then
      printf '    (stash-like commit — pinned only, no patch)\n'
    else
      SHORT="$(git rev-parse --short "$sha")"
      SLUG="$(git log -1 --format='%f' "$sha" 2>/dev/null | cut -c1-40)"
      OUT="$PATCH_DIR/${SHORT}-${SLUG}.patch"
      if git format-patch -1 "$sha" --stdout > "$OUT" 2>/dev/null; then
        PATCHED=$((PATCHED + 1))
      else
        rm -f "$OUT"
        printf '    (could not format-patch %s — pinned only)\n' "$SHORT"
      fi
    fi
  fi
done <<< "$DANGLING"

echo ""
echo "=== Preserved ==="
echo "  pinned:  $PINNED commit(s) under refs/dangling-backup/"
[ -n "$PATCH_DIR" ] && echo "  patched: $PATCHED patch file(s) in $PATCH_DIR"
echo ""
echo "  Verify:  git for-each-ref refs/dangling-backup/"
echo "  Inspect: git show <sha>       (each pinned commit is now gc-proof)"
echo "  These pins protect the objects; they do NOT put the work on a remote. For a commit you"
echo "  truly can't lose, also push a branch + keep a patch (triple-backup — see recovery_playbook.md)."
