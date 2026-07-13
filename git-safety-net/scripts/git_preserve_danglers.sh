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

# Resolve --patch-dir to an ABSOLUTE path against the caller's CWD BEFORE we cd to the repo root,
# so a relative --patch-dir means what the user expects (their current directory, not the repo top).
if [ -n "$PATCH_DIR" ]; then
  case "$PATCH_DIR" in
    /*) : ;;                            # already absolute
    *)  PATCH_DIR="$PWD/$PATCH_DIR" ;;  # relative → anchor to the caller's CWD
  esac
fi

cd "$(git rev-parse --show-toplevel)"

# Create the patch dir, but never let a patch-export problem abort the PRIMARY job (pinning). If
# the directory can't be made, warn and disable patch export; the pinning below still runs.
if [ -n "$PATCH_DIR" ]; then
  if ! mkdir -p "$PATCH_DIR" 2>/dev/null; then
    echo "warning: cannot create --patch-dir '$PATCH_DIR'; pinning only, skipping patch export." >&2
    PATCH_DIR=""
  fi
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
    # A stash commit (and any merge) has >=2 parents; `git format-patch -1` cannot represent a
    # merge and will SILENTLY emit a different commit's patch (exit 0), so we would write a wrong
    # backup and report it as success. Detect by PARENT COUNT, not by the "WIP on " subject —
    # a `git stash push -m msg` stash reads "On <branch>: msg" (would slip through the old check),
    # and a real commit titled "WIP on …" would have been wrongly skipped. rev-list --parents
    # prints "<sha> <parent1> <parent2>…", so >2 tokens means >=2 parents. The pin already made
    # the object gc-proof; we only skip the (impossible) patch for merges.
    PARENTS="$(git rev-list --parents -n1 "$sha" 2>/dev/null | wc -w | tr -d ' ')"
    if [ "${PARENTS:-1}" -gt 2 ]; then
      printf '    (merge/stash commit — pinned only, no patch)\n'
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
