#!/usr/bin/env bash
# git_classify_refs.sh — batch content-level classification of every local/remote-tracking
# branch against ONE frozen base. READ-ONLY, never fetches, never writes a ref, never checks
# out anything.
#
# Runs the same ladder git_verify_branch_merged.sh runs one branch at a time (ancestor ->
# trial merge into base), for the WHOLE repository in one pass, against a base the caller has
# already pinned to a SHA. Pin it once with `git rev-parse origin/main` before the run — never
# pass a moving name like `origin/main` directly, or a ref that advances mid-batch (someone
# else pushing) silently changes what "already merged" means partway through the report.
#
# Verdicts (TSV column 1):
#   ANCESTOR              — branch is in base's history already
#   MERGED-CONTENT         — a trial merge of the branch into base changes nothing (the
#                            squash/rebase case; same meaning as git_verify_branch_merged.sh's
#                            "MERGED (content contained)")
#   LANDED-AT-MERGE        — only with --pr-map: a MERGED PR's own merge commit proves
#                            containment the way git_verify_branch_merged.sh's --merge-commit
#                            rung does, for a ref the base trial merge alone could not clear.
#                            The detail column keeps the SHAPE of that base trial-merge failure
#                            (see Columns below) — a conflict is the routine case (base moved
#                            the same lines again); "clean-changes" is a candidate regression —
#                            see references/merge_verification.md's "Landed, then lost".
#   NEEDS-REVIEW-CLEAN     — trial merge into base succeeds but changes base's tree
#   NEEDS-REVIEW-CONFLICT  — trial merge into base reports a real conflict
#   ERROR-rcN              — merge-tree returned an unexpected code (git too old, or a genuine
#                            repository problem) — never silently folded into another verdict
#   NOT-A-COMMIT           — (--all-namespaces section only) the ref does not peel to a commit
#
# Columns (tab-separated): verdict, files-changed (0 for ANCESTOR/MERGED-CONTENT/
# LANDED-AT-MERGE; -1 for ERROR/NOT-A-COMMIT; otherwise the path count a trial merge into
# base would touch), sha (12-char), refname (full, e.g. refs/heads/foo), detail. Detail is
# empty except: NEEDS-REVIEW-CLEAN/CONFLICT rows stay empty (the verdict itself already says
# which); LANDED-AT-MERGE rows carry "pr=#N merge-commit=<sha> current-base=<shape>", where
# <shape> is "conflict" (base changed the same lines again since the merge — routine, nothing
# missing) or "clean-changes:<n>" (the base trial merge succeeds cleanly but would still change
# <n> files — a candidate loss, NOT routine; see references/merge_verification.md's "Landed,
# then lost" before concluding anything).
#
# Usage:
#   git_classify_refs.sh --base <sha> [--pr-map <path.json>] [--all-namespaces]
#
# --pr-map <path.json> overlays the git_verify_branch_merged.sh --merge-commit rung across the
# whole batch. Expected shape — `gh pr list --json number,state,headRefName,headRefOid,
# mergeCommit --state all > path.json` produces this directly:
#   [{"number": 42, "state": "MERGED", "headRefName": "feat-x",
#     "headRefOid": "<sha the PR's head pointed at when merged>",
#     "mergeCommit": {"oid": "<the merge commit's sha>"}}, ...]
# A ref only gets the LANDED-AT-MERGE upgrade when: (a) it was NEEDS-REVIEW-* against base;
# (b) some entry's headRefName matches the ref's bare branch name (the remote prefix is
# stripped before matching, so refs/remotes/origin/feat-x matches "feat-x") AND headRefOid
# equals the ref's CURRENT sha exactly — a record for an old tip is ignored, never guessed at;
# (c) state is exactly "MERGED"; (d) mergeCommit.oid is an ancestor of --base and a trial merge
# of the ref into it reproduces that commit's tree — the identical precondition
# git_verify_branch_merged.sh's --merge-commit enforces, applied here at batch scale. JSON
# parsing uses `python3 -m json` inline rather than jq, so this script adds no CLI dependency
# beyond what every Python-based consumer of this repository already requires.
#
# --all-namespaces additionally lists every ref OUTSIDE refs/heads/* and refs/remotes/*/* —
# tags, refs/stash, refs/dangling-backup/*, refs/recovery/*, anything else this repository
# happens to use — in a SEPARATE report-only section below the main table. Off by default:
# most of that namespace is not "a branch that might need merging", and folding it into the
# same table would misrepresent a tag or a backup pin as an ordinary merge candidate.
set -uo pipefail

die() { echo "error: $*" >&2; exit 2; }

BASE=""
PR_MAP=""
ALL_NAMESPACES=0
while [ $# -gt 0 ]; do
  case "$1" in
    --base)           BASE="${2:?--base needs a commit-ish}"; shift 2 ;;
    --pr-map)         PR_MAP="${2:?--pr-map needs a file path}"; shift 2 ;;
    --all-namespaces) ALL_NAMESPACES=1; shift ;;
    -h|--help)        grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)                die "unknown argument: $1 (see --help)" ;;
  esac
done
[ -n "$BASE" ] || die "--base is required"

git rev-parse --show-toplevel >/dev/null 2>&1 || die "not inside a Git repository."
cd "$(git rev-parse --show-toplevel)"
git rev-parse --verify --quiet "${BASE}^{commit}" >/dev/null || die "--base '$BASE' does not resolve to a commit."
BASE_TREE="$(git rev-parse "${BASE}^{tree}")"

PR_MAP_TSV=""
if [ -n "$PR_MAP" ]; then
  [ -f "$PR_MAP" ] || die "--pr-map file not found: $PR_MAP"
  PR_MAP_TSV="$(python3 - "$PR_MAP" <<'PYEOF'
import json
import sys

path = sys.argv[1]
try:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
except (OSError, json.JSONDecodeError) as exc:
    sys.exit(f"{exc}")
if not isinstance(data, list):
    sys.exit("pr-map must be a JSON array of objects")
for entry in data:
    if not isinstance(entry, dict):
        continue
    number = entry.get("number", "")
    state = entry.get("state") or ""
    head_ref = entry.get("headRefName") or ""
    head_oid = entry.get("headRefOid") or ""
    merge_commit = entry.get("mergeCommit")
    merge_oid = ""
    if isinstance(merge_commit, dict):
        merge_oid = merge_commit.get("oid") or ""
    if not head_ref or not head_oid or "\t" in head_ref or "\t" in head_oid:
        continue
    print(f"{head_ref}\t{head_oid}\t{state}\t{merge_oid}\t{number}")
PYEOF
)" || die "--pr-map is not valid JSON matching the documented shape: $PR_MAP"
fi

# --- classify ONE ref: emits "verdict\tnfiles\tsha\trefname\tdetail" ---
classify_one() {
  local ref="$1" sha="$2" short="$3"
  local verdict nfiles detail=""

  if git merge-base --is-ancestor "$sha" "$BASE" 2>/dev/null; then
    printf 'ANCESTOR\t0\t%s\t%s\t\n' "${sha:0:12}" "$ref"
    return
  fi

  local out rc tree
  if out="$(git merge-tree --write-tree "$BASE" "$sha" 2>&1)"; then rc=0; else rc=$?; fi
  tree="$(printf '%s\n' "$out" | head -1)"

  if [ "$rc" -ge 128 ]; then
    printf 'ERROR-rc%s\t-1\t%s\t%s\tgit merge-tree unavailable or failed\n' "$rc" "${sha:0:12}" "$ref"
    return
  fi

  if [ "$rc" -eq 0 ] && [ "$tree" = "$BASE_TREE" ]; then
    printf 'MERGED-CONTENT\t0\t%s\t%s\t\n' "${sha:0:12}" "$ref"
    return
  fi

  # Names differing between base and the trial-merge tree. Safe even on the conflict branch
  # below: a conflicted file differs from base by definition, so it appears in --name-only
  # regardless of whether the tree's bytes for it are real content or conflict markers.
  nfiles=$(git diff --name-only "$BASE_TREE" "$tree" 2>/dev/null | wc -l | tr -d ' ')
  if [ "$rc" -eq 0 ]; then verdict="NEEDS-REVIEW-CLEAN"; else verdict="NEEDS-REVIEW-CONFLICT"; fi

  # --pr-map overlay: only for a ref this ladder could not already clear, and only on an
  # EXACT (bare-name, current-sha) match to a MERGED PR record — a stale record for an old
  # tip must never upgrade today's tip.
  if [ -n "$PR_MAP_TSV" ]; then
    local match merge_oid pr_number
    match="$(printf '%s\n' "$PR_MAP_TSV" | awk -F'\t' -v n="$short" -v s="$sha" '$1==n && $2==s && $3=="MERGED" {print; exit}')"
    if [ -n "$match" ]; then
      merge_oid="$(printf '%s' "$match" | awk -F'\t' '{print $4}')"
      pr_number="$(printf '%s' "$match" | awk -F'\t' '{print $5}')"
      if [ -n "$merge_oid" ] && git rev-parse --verify --quiet "${merge_oid}^{commit}" >/dev/null 2>&1 \
         && git merge-base --is-ancestor "$merge_oid" "$BASE" 2>/dev/null; then
        local mc_tree mc_out mc_rc mc_merged
        mc_tree="$(git rev-parse "${merge_oid}^{tree}")"
        if mc_out="$(git merge-tree --write-tree "$merge_oid" "$sha" 2>&1)"; then mc_rc=0; else mc_rc=$?; fi
        mc_merged="$(printf '%s\n' "$mc_out" | head -1)"
        if [ "$mc_rc" -eq 0 ] && [ "$mc_merged" = "$mc_tree" ]; then
          # Keep the SHAPE of the base trial-merge failure we already computed above ($rc/
          # $nfiles from the NEEDS-REVIEW classification this upgrade replaces) — a conflict
          # (base moved the same lines again) reads very differently from a clean merge that
          # would still change base (a candidate "landed, then lost" regression), and folding
          # both into one LANDED-AT-MERGE row with no detail would erase that distinction.
          local current_base_shape
          if [ "$rc" -eq 0 ]; then current_base_shape="clean-changes:${nfiles}"; else current_base_shape="conflict"; fi
          printf 'LANDED-AT-MERGE\t0\t%s\t%s\tpr=#%s merge-commit=%s current-base=%s\n' \
            "${sha:0:12}" "$ref" "$pr_number" "${merge_oid:0:12}" "$current_base_shape"
          return
        fi
      fi
    fi
  fi

  printf '%s\t%s\t%s\t%s\t%s\n' "$verdict" "$nfiles" "${sha:0:12}" "$ref" "$detail"
}

# Strip a ref down to the bare branch name a hosting platform's headRefName would carry:
# refs/heads/foo -> foo ; refs/remotes/origin/foo -> foo (the remote name is not part of a
# PR's head ref name, so it must come off before matching --pr-map).
bare_branch_name() {
  case "$1" in
    refs/heads/*)   printf '%s\n' "${1#refs/heads/}" ;;
    refs/remotes/*) local rest="${1#refs/remotes/}"; printf '%s\n' "${rest#*/}" ;;
    *)              printf '%s\n' "$1" ;;
  esac
}

echo "# base=$BASE tree=$BASE_TREE  ($(date '+%F %T %z'))"
[ -n "$PR_MAP_TSV" ] && echo "# pr-map: $PR_MAP (overlaying the merge-commit rung)"
echo "## refs/heads and refs/remotes/*"
{
  git for-each-ref --format='%(refname) %(objectname) %(symref)' refs/heads refs/remotes |
    while read -r refname sha symref; do
      [ -z "$symref" ] || continue   # skip symbolic refs, e.g. refs/remotes/origin/HEAD
      classify_one "$refname" "$sha" "$(bare_branch_name "$refname")"
    done
} | sort

if [ "$ALL_NAMESPACES" = 1 ]; then
  echo
  echo "## other namespaces (report-only: tags, stash, backup pins, anything else)"
  {
    git for-each-ref --format='%(refname) %(objectname) %(symref)' |
      awk '$1 !~ /^refs\/(heads|remotes)\//' |
      while read -r refname sha symref; do
        [ -z "$symref" ] || continue
        if commit_sha="$(git rev-parse --verify --quiet "${sha}^{commit}" 2>/dev/null)"; then
          classify_one "$refname" "$commit_sha" "$refname"
        else
          printf 'NOT-A-COMMIT\t-1\t%s\t%s\tnot peelable to a commit\n' "${sha:0:12}" "$refname"
        fi
      done
  } | sort
fi

exit 0
