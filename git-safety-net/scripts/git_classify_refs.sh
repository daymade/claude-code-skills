#!/usr/bin/env bash
# git_classify_refs.sh — batch content-level classification of every local/remote-tracking
# branch against ONE frozen base. Never fetches or changes refs, index, or working files.
# Trial merges can write unreferenced objects into the Git object database.
#
# Runs the same ladder git_verify_branch_merged.sh runs one branch at a time (ancestor ->
# trial merge into base), for enumerated branches or a bound target set in one pass.
# The script resolves --base to one commit at entry. For an agreed or delegated batch,
# the caller must pin that SHA before dispatch so every receiver uses the agreed snapshot.
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
#   ERROR-rcN              — a Git merge/count measurement failed (git too old, or a genuine
#                            repository problem) — never silently folded into another verdict
#   NOT-A-COMMIT           — a non-branch ref does not peel to a commit (report-only)
#
# Columns (tab-separated): verdict, files-changed (0 for ANCESTOR/MERGED-CONTENT/
# LANDED-AT-MERGE; -1 for ERROR/NOT-A-COMMIT; otherwise the path count a trial merge into
# base would touch), sha (12-char by default, full in bound mode), refname, detail. Detail is
# empty except: NEEDS-REVIEW-CLEAN/CONFLICT rows stay empty (the verdict itself already says
# which); LANDED-AT-MERGE rows carry "pr=#N merge-commit=<sha> current-base=<shape>", where
# <shape> is "conflict" (base changed the same lines again since the merge — routine, nothing
# missing) or "clean-changes:<n>" (the base trial merge succeeds cleanly but would still change
# <n> files — a candidate loss, NOT routine; see references/merge_verification.md's "Landed,
# then lost" before concluding anything).
#
# Usage:
#   git_classify_refs.sh --base <sha> [--pr-map <path.json>] [--all-namespaces]
#   git_classify_refs.sh --base <sha> --expected-common-dir <path> --target-manifest <path.tsv>
#                        [--pr-map <path.json>]
#
# Binding mode requires BOTH new options. The manifest is non-empty TSV with exactly two
# columns per line: a full refname and its expected full 40-hex object ID. Canonicalize and
# compare the repository common directory before reading any target ref, then require every
# target to exist at its frozen OID. Bound rows print full OIDs and the summary distinguishes
# classification coverage from merge/retirement completion. Any missing, moved, malformed,
# unreadable, duplicate, or empty target input fails closed. With neither option the legacy
# enumeration, 12-character SHA column, and exit contract remain unchanged.
# Bound-mode exits: 0 = every named object classified (NEEDS-REVIEW may remain),
# 1 = classification incomplete, 2 = invalid input or repository/ref snapshot mismatch.
# None of these verdicts proves that keeper changes were adopted or targets were retired.
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
EXPECTED_COMMON_DIR=""
TARGET_MANIFEST=""
SHA_WIDTH=12
while [ $# -gt 0 ]; do
  case "$1" in
    --base)           BASE="${2:?--base needs a commit-ish}"; shift 2 ;;
    --pr-map)         PR_MAP="${2:?--pr-map needs a file path}"; shift 2 ;;
    --expected-common-dir)
      [ $# -ge 2 ] || die "--expected-common-dir needs a directory path"
      [ -n "$2" ] || die "--expected-common-dir must not be empty"
      EXPECTED_COMMON_DIR="$2"; shift 2 ;;
    --target-manifest)
      [ $# -ge 2 ] || die "--target-manifest needs a file path"
      [ -n "$2" ] || die "--target-manifest must not be empty"
      TARGET_MANIFEST="$2"; shift 2 ;;
    --all-namespaces) ALL_NAMESPACES=1; shift ;;
    -h|--help)        grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)                die "unknown argument: $1 (see --help)" ;;
  esac
done
[ -n "$BASE" ] || die "--base is required"
if [ -n "$EXPECTED_COMMON_DIR" ] || [ -n "$TARGET_MANIFEST" ]; then
  [ -n "$EXPECTED_COMMON_DIR" ] && [ -n "$TARGET_MANIFEST" ] || \
    die "--expected-common-dir and --target-manifest must be supplied together"
  SHA_WIDTH=40
fi

canonical_dir() {
  (cd "$1" 2>/dev/null && pwd -P)
}

ACTUAL_TOP_LEVEL="$(git rev-parse --show-toplevel 2>/dev/null)" || die "not inside a Git repository."
RAW_COMMON_DIR="$(git rev-parse --git-common-dir 2>/dev/null)" || die "cannot resolve Git common directory."
ACTUAL_COMMON_DIR="$(canonical_dir "$RAW_COMMON_DIR")" || die "cannot canonicalize Git common directory: $RAW_COMMON_DIR"
ACTUAL_TOP_LEVEL="$(canonical_dir "$ACTUAL_TOP_LEVEL")" || die "cannot canonicalize Git top-level."
if [ -n "$EXPECTED_COMMON_DIR" ]; then
  [ -d "$EXPECTED_COMMON_DIR" ] || die "--expected-common-dir is not a readable directory: $EXPECTED_COMMON_DIR"
  EXPECTED_COMMON_DIR="$(canonical_dir "$EXPECTED_COMMON_DIR")" || die "cannot canonicalize --expected-common-dir"
  printf '# actual-common-dir=%s actual-top-level=%s expected-common-dir=%s\n' \
    "$ACTUAL_COMMON_DIR" "$ACTUAL_TOP_LEVEL" "$EXPECTED_COMMON_DIR"
  [ "$ACTUAL_COMMON_DIR" = "$EXPECTED_COMMON_DIR" ] || \
    die "repository identity mismatch: actual common-dir '$ACTUAL_COMMON_DIR' != expected '$EXPECTED_COMMON_DIR'"
fi
cd "$ACTUAL_TOP_LEVEL" || die "cannot enter Git top-level: $ACTUAL_TOP_LEVEL"
BASE="$(git rev-parse --verify --quiet "${BASE}^{commit}")" || die "--base does not resolve to a commit."
[ -n "$BASE" ] || die "--base does not resolve to a commit."
BASE_TREE="$(git rev-parse "${BASE}^{tree}")" || die "cannot resolve frozen base tree."

TARGET_REFS=()
TARGET_OIDS=()
CURRENT_OIDS=()
if [ -n "$TARGET_MANIFEST" ]; then
  [ -f "$TARGET_MANIFEST" ] || die "--target-manifest file not found: $TARGET_MANIFEST"
  [ -r "$TARGET_MANIFEST" ] || die "--target-manifest is not readable: $TARGET_MANIFEST"
  [ -s "$TARGET_MANIFEST" ] || die "--target-manifest must not be empty: $TARGET_MANIFEST"
  line_number=0
  while IFS= read -r line || [ -n "$line" ]; do
    line_number=$((line_number + 1))
    case "$line" in
      *$'\t'*) ;;
      *) die "--target-manifest line $line_number must contain full-ref<TAB>full-OID" ;;
    esac
    ref="${line%%$'\t'*}"
    oid="${line#*$'\t'}"
    [[ "$oid" != *$'\t'* ]] || die "--target-manifest line $line_number has extra columns"
    [[ "$ref" =~ ^refs/.+ ]] || die "--target-manifest line $line_number requires a full refname"
    git check-ref-format "$ref" >/dev/null 2>&1 || die "--target-manifest line $line_number has invalid refname: $ref"
    [[ "$oid" =~ ^[0-9a-fA-F]{40}$ ]] || die "--target-manifest line $line_number requires a full 40-hex OID"
    oid="$(printf '%s' "$oid" | tr 'A-F' 'a-f')"
    for existing in ${TARGET_REFS[@]+"${TARGET_REFS[@]}"}; do
      [ "$existing" != "$ref" ] || die "--target-manifest contains duplicate ref: $ref"
    done
    TARGET_REFS+=("$ref")
    TARGET_OIDS+=("$oid")
  done < "$TARGET_MANIFEST"
  [ "${#TARGET_REFS[@]}" -gt 0 ] || die "--target-manifest must contain at least one target"
fi

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
  local ref="$1" sha="$2" short="$3" display_sha
  display_sha="${4:-$sha}"
  local verdict nfiles detail=""

  if git merge-base --is-ancestor "$sha" "$BASE" 2>/dev/null; then
    printf 'ANCESTOR\t0\t%s\t%s\t\n' "${display_sha:0:SHA_WIDTH}" "$ref"
    return
  fi

  local out rc tree
  if out="$(git merge-tree --write-tree "$BASE" "$sha" 2>&1)"; then rc=0; else rc=$?; fi
  tree="$(printf '%s\n' "$out" | head -1)"

  if [ "$rc" -ne 0 ] && [ "$rc" -ne 1 ]; then
    printf 'ERROR-rc%s\t-1\t%s\t%s\tgit merge-tree unavailable or failed\n' "$rc" "${display_sha:0:SHA_WIDTH}" "$ref"
    return
  fi

  if [ "$rc" -eq 0 ] && [ "$tree" = "$BASE_TREE" ]; then
    printf 'MERGED-CONTENT\t0\t%s\t%s\t\n' "${display_sha:0:SHA_WIDTH}" "$ref"
    return
  fi

  # Names differing between base and the trial-merge tree. Safe even on the conflict branch
  # below: a conflicted file differs from base by definition, so it appears in --name-only
  # regardless of whether the tree's bytes for it are real content or conflict markers.
  local diff_output diff_line
  if diff_output="$(git diff --name-only "$BASE_TREE" "$tree")"; then
    nfiles=0
    if [ -n "$diff_output" ]; then
      while IFS= read -r diff_line; do
        nfiles=$((nfiles + 1))
      done <<< "$diff_output"
    fi
  else
    rc=$?
    printf 'ERROR-rc%s\t-1\t%s\t%s\tgit diff failed; changed paths unknown\n' \
      "$rc" "${display_sha:0:SHA_WIDTH}" "$ref"
    return
  fi
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
            "${display_sha:0:SHA_WIDTH}" "$ref" "$pr_number" "${merge_oid:0:SHA_WIDTH}" "$current_base_shape"
          return
        fi
      fi
    fi
  fi

  printf '%s\t%s\t%s\t%s\t%s\n' "$verdict" "$nfiles" "${display_sha:0:SHA_WIDTH}" "$ref" "$detail"
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

if [ -n "$TARGET_MANIFEST" ]; then
  [ "$ALL_NAMESPACES" = 0 ] || die "--all-namespaces cannot be combined with bound target mode"
  missing=0
  moved=0
  scope_errors=0
  expected_count="${#TARGET_REFS[@]}"
  for ((i = 0; i < expected_count; i++)); do
    ref="${TARGET_REFS[$i]}"
    expected_oid="${TARGET_OIDS[$i]}"
    if ref_records="$(git for-each-ref --format='%(refname) %(objectname)' "$ref" 2>&1)"; then
      rc=0
    else
      rc=$?
    fi
    if [ "$rc" -ne 0 ]; then
      printf '# error ref=%s detail=%s\n' "$ref" "$ref_records"
      scope_errors=$((scope_errors + 1))
      CURRENT_OIDS+=("")
      continue
    fi
    current="$(printf '%s\n' "$ref_records" | awk -v r="$ref" '$1 == r { print $2 }')"
    if [ -z "$current" ]; then
      printf '# missing ref=%s expected-oid=%s\n' "$ref" "$expected_oid"
      missing=$((missing + 1))
      CURRENT_OIDS+=("")
      continue
    fi
    current="$(printf '%s' "$current" | tr 'A-F' 'a-f')"
    CURRENT_OIDS+=("$current")
    if [ "$current" != "$expected_oid" ]; then
      printf '# moved ref=%s expected-oid=%s actual-oid=%s\n' "$ref" "$expected_oid" "$current"
      moved=$((moved + 1))
    fi
  done
  if [ "$missing" -ne 0 ] || [ "$moved" -ne 0 ] || [ "$scope_errors" -ne 0 ]; then
    printf '# summary expected=%s examined=0 missing=%s moved=%s needs-review=0 errors=%s scope_complete=false classification_only=true\n' \
      "$expected_count" "$missing" "$moved" "$scope_errors"
    exit 2
  fi

  echo "## bound targets (non-branch namespaces are report-only)"
  BOUND_ROWS=""
  for ((i = 0; i < expected_count; i++)); do
    ref="${TARGET_REFS[$i]}"
    current="${CURRENT_OIDS[$i]}"
    case "$ref" in
      refs/heads/*|refs/remotes/*)
        row="$(classify_one "$ref" "$current" "$(bare_branch_name "$ref")" "$current")" ;;
      *)
        if commit_sha="$(git rev-parse --verify --quiet "${current}^{commit}" 2>/dev/null)"; then
          row="$(classify_one "$ref" "$commit_sha" "$ref" "$current")"
        else
          row="$(printf 'NOT-A-COMMIT\t-1\t%s\t%s\tnot peelable to a commit; report-only\n' "$current" "$ref")"
        fi ;;
    esac
    BOUND_ROWS="${BOUND_ROWS}${row}"$'\n'
  done
  printf '%s' "$BOUND_ROWS" | sort
  read -r examined needs_review class_errors <<EOF
$(printf '%s' "$BOUND_ROWS" | awk -F '\t' 'NF >= 4 { examined++; if ($1 ~ /^NEEDS-REVIEW-/) review++; if ($1 ~ /^ERROR-/ || $1 == "NOT-A-COMMIT") errors++ } END { printf "%d %d %d\n", examined, review, errors }')
EOF
  scope_complete=true
  [ "$examined" -eq "$expected_count" ] && [ "$class_errors" -eq 0 ] || scope_complete=false
  printf '# summary expected=%s examined=%s missing=0 moved=0 needs-review=%s errors=%s scope_complete=%s classification_only=true\n' \
    "$expected_count" "$examined" "$needs_review" "$class_errors" "$scope_complete"
  [ "$scope_complete" = true ] || exit 1
  exit 0
fi

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
          printf 'NOT-A-COMMIT\t-1\t%s\t%s\tnot peelable to a commit\n' "${sha:0:SHA_WIDTH}" "$refname"
        fi
      done
  } | sort
fi

exit 0
