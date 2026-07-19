#!/usr/bin/env bash
# validate_changed_skills.sh — run quick_validate on the skills this change touches.
#
# WHY ONLY THE TOUCHED ONES, AND WHY A RATCHET:
#   Two skills on main do not pass quick_validate today (one references files that are
#   deliberately gitignored, one has a stray frontmatter key). Gating the whole repo would
#   therefore fail every pull request for reasons its author did not cause — the fastest
#   way to teach people that a red check means nothing.
#
#   So this compares against the base: a skill is only reported as broken when it passed
#   BEFORE the change and fails after. Pre-existing breakage is printed as a known issue
#   and does not fail the run. That makes the check self-maintaining — no allow-list to go
#   stale — and it still blocks any newly introduced breakage.
#
# Run locally: scripts/ci/validate_changed_skills.sh [base-ref]     # base defaults to origin/main

set -uo pipefail

cd "$(dirname "$0")/../.." || exit 1

BASE_REF="${1:-origin/main}"
VALIDATOR="daymade-skill/skill-creator/scripts/quick_validate.py"

[ -f "$VALIDATOR" ] || { echo "FAIL: validator missing at $VALIDATOR"; exit 1; }

if ! git rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
  echo "FAIL: base ref '$BASE_REF' is unknown here — fetch it first (a stale or missing base"
  echo "      makes every verdict below meaningless)"
  exit 1
fi

MERGE_BASE="$(git merge-base "$BASE_REF" HEAD)" || { echo "FAIL: no merge base with $BASE_REF"; exit 1; }

# PREFLIGHT — prove the validator can actually run before trusting a single verdict.
#
# quick_validate exits 0 (valid), 1 (invalid), or 2 (it could not run at all, e.g. PyYAML
# missing). Without this check a missing dependency makes every skill fail identically, so
# the ratchet below sees "fails now, failed at base too", files every genuine regression as
# pre-existing, and exits 0. That is a gate reporting success exactly when it is broken —
# worse than no gate, because the green tick is now evidence of nothing. Caught by a test
# where a deliberately broken skill sailed through.
if ! python3 -c 'import yaml' >/dev/null 2>&1; then
  echo "FAIL: quick_validate needs PyYAML and it is not importable here."
  echo "      Install it (pip install pyyaml) — refusing to report a verdict the validator"
  echo "      cannot actually produce."
  exit 1
fi

# Walk up from each changed file to the directory that owns a SKILL.md.
skills="$(
  git diff --name-only "$MERGE_BASE"...HEAD | while IFS= read -r path; do
    dir="$(dirname "$path")"
    while [ "$dir" != "." ] && [ "$dir" != "/" ]; do
      [ -f "$dir/SKILL.md" ] && { echo "$dir"; break; }
      dir="$(dirname "$dir")"
    done
  done | sort -u
)"

if [ -z "$skills" ]; then
  echo "OK: this change touches no skill directory"
  exit 0
fi

# Returns 0 = valid, 1 = invalid. Any other code means the validator itself failed, which
# must never be silently read as "invalid" — that is what turns a broken instrument into a
# confident verdict.
validate() {
  python3 "$VALIDATOR" "$1" >/dev/null 2>&1
  local code=$?
  case "$code" in
    0|1) return "$code" ;;
    *)
      echo "FAIL: validator exited $code on '$1' — it could not run, so no verdict is possible."
      exit 1
      ;;
  esac
}

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

regressions=0
preexisting=0
checked=0

while IFS= read -r skill; do
  [ -n "$skill" ] || continue
  checked=$((checked + 1))

  if validate "$skill"; then
    echo "  ok        $skill"
    continue
  fi

  # It fails now. Did it also fail at the base? Then it is not this change's doing.
  base_copy="$workdir/$(echo "$skill" | tr '/' '_')"
  mkdir -p "$base_copy"
  if git archive "$MERGE_BASE" "$skill" 2>/dev/null | tar -x -C "$base_copy" 2>/dev/null \
     && [ -f "$base_copy/$skill/SKILL.md" ] \
     && ! validate "$base_copy/$skill"; then
    echo "  known     $skill (already failing on $BASE_REF — not caused by this change)"
    preexisting=$((preexisting + 1))
    continue
  fi

  echo "  BROKEN    $skill"
  python3 "$VALIDATOR" "$skill" 2>&1 | sed 's/^/              /'
  regressions=$((regressions + 1))
done <<EOF
$skills
EOF

echo
if [ "$regressions" -gt 0 ]; then
  echo "FAIL: $regressions of $checked touched skill(s) newly fail validation"
  exit 1
fi

echo "OK: $checked touched skill(s) validated ($preexisting pre-existing issue(s) carried, not introduced here)"
