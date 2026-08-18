#!/usr/bin/env bash
# reference_net.sh — list the PROSE cross-references in what you added, so each can be resolved.
#
# SCOPE — deliberately half of what you might expect, because the other half already has a tool.
#
#   This script finds *prose* pointers: "see rule 8", "discipline #6", "the step 3 above". They have
#   no machine-resolvable target — a numbered item in prose is not an anchor — so no link checker
#   can validate them, and a human or agent has to open each target and read it.
#
#   Machine-resolvable links — `[text](#anchor)`, `[text](path.md)`, URLs — are NOT this script's
#   job. Use `lychee`, which parses Markdown properly and is this repository's house standard for
#   them; daymade-docs/docs-cleaner's SKILL.md carries the invocation and, importantly, its
#   calibration caveats. A hand-rolled link scanner was tried here before and deleted after it
#   misreported 16 of 17 valid links; do not rebuild it inside this one.
#
# WHY THIS IS A SCRIPT AND NOT THE ONE-LINER IT REPLACES
#
#   The prose version of this check accumulated five rounds of patches — anchor the diff to the
#   right base, see staged edits, survive committing, ignore the diff's own `+++` header, drop a
#   misleading `-n` — and *every* patch added one more way for the command to print nothing and
#   exit 0. That output is indistinguishable from "I checked and it was clean", which is precisely
#   the failure the check exists to prevent. Prose cannot validate its own inputs, cannot say which
#   of its outcomes happened, and cannot be tested.
#
#   So the contract here is: **every outcome is named out loud, and bad input fails loudly.** There
#   is no combination of arguments under which this prints nothing and looks successful.
#
# Usage:
#   reference_net.sh <base-ref> <file> [file...]
#
#   <base-ref>  The commit your current work started from. NOT `HEAD` — once you commit, `HEAD`
#               includes your own change, the diff goes empty, and your unresolved pointers sit
#               happily in the file while the check reports nothing to do. Use the SHA you branched
#               from, or `@{u}` / `origin/main` when those genuinely predate your work.
#
# Requires bash. The shebang and the executable bit make the documented bare invocation work;
# running it as `sh reference_net.sh …` will not, because /bin/sh is dash on Debian-family Linux
# and this script uses bash arrays. That is a deliberate dependency, not an oversight — say
# `bash reference_net.sh …` if your caller cannot rely on the shebang.
#
# Known boundary, documented rather than fixed: a submodule bump is reported (measured: the gitlink
# line is counted as one added line and correctly classified `NONE prose-reference-shaped`), but the
# CONTENT behind the new commit is never traversed. So a pointer added inside a submodule is invisible
# here. The gap is inert for this tool's purpose — run the script inside that submodule if you edited
# it — but it is written down instead of discovered later.
#
# Exit codes:
#   0  ran to completion — read the printed verdict, which always says which case you are in
#   2  could not run (unresolvable base ref, untracked or mistyped path, git or parse failure)
#
# `set -e` is deliberately NOT used: `grep` exits 1 on no-match, a legitimate result here, and
# `set -e` would turn "found nothing" into "script crashed".

set -uo pipefail

# Prose pointers only. Markdown links are lychee's job — see SCOPE above.
readonly REFERENCE_PATTERN='(see|per|above|below|§|rule|discipline|step) *#?[0-9]'

usage() {
  echo "usage: $(basename "$0") <base-ref> <file> [file...]" >&2
  echo "  <base-ref> is the commit your work started from — not HEAD." >&2
}

if [ "$#" -lt 2 ]; then
  usage
  exit 2
fi

base=$1
shift

if ! resolved=$(git rev-parse --verify --quiet "${base}^{commit}"); then
  echo "FAIL: base ref '${base}' does not resolve to a commit." >&2
  echo "      Nothing was examined. Pass the SHA your work started from." >&2
  exit 2
fi

# Resolve each argument to a repo-root-relative path and keep it. Two reasons, both measured:
# a bare relative name like SKILL.md resolves against the CALLER'S cwd, and in a repo with many
# same-named files that silently examines a different file than the caller edited while printing a
# clean verdict; and an argument that matches several paths (a directory, a glob) would be reported
# under one heading as if it were one file.
resolved_paths=()
for file in "$@"; do
  # -z, because it is the only form git guarantees is the RAW pathname. Plain `ls-files` C-quotes
  # any name git considers unusual and hands back an escaped *string* — `"\346\226\207..."` for
  # 文档.md, `"foo\"bar.md"` for a plain-ASCII foo"bar.md — which then matches nothing as a diff
  # pathspec, so the file was reported IDENTICAL while real unresolved pointers sat in it
  # (measured, both cases). `core.quotepath=false` is NOT sufficient: quotes, backslashes and
  # control bytes are C-escaped unconditionally, regardless of that setting.
  # The loop reads in THIS shell (process substitution, not a pipe) so the array survives.
  matches=()
  while IFS= read -r -d '' match; do
    matches+=("$match")
  done < <(git ls-files -z --full-name -- "$file" 2>/dev/null)

  if [ "${#matches[@]}" -eq 0 ]; then
    echo "FAIL: '${file}' is not tracked by git — new file you have not \`git add\`ed yet," >&2
    echo "      or a typo, or the wrong directory." >&2
    echo "      Nothing was examined." >&2
    exit 2
  fi
  if [ "${#matches[@]}" -ne 1 ]; then
    echo "FAIL: '${file}' matches ${#matches[@]} tracked paths, not one:" >&2
    printf '%s\n' "${matches[@]}" | sed 's/^/        /' >&2
    echo "      Pass one file at a time so each verdict names the file it is about." >&2
    exit 2
  fi
  resolved_paths+=("${matches[0]}")
done

for file in "${resolved_paths[@]}"; do
  # --no-color: a user with color.diff=always gets ANSI codes that make every content line fail a
  #   `^\+` match, so the script reported NOTHING ADDED for every file (measured).
  # --no-ext-diff: an external differ (difftastic/delta) replaces the unified format entirely.
  # --no-textconv: a .gitattributes `diff=<driver>` whose driver defines a textconv filter makes
  #   git diff the FILTERED text rather than the real bytes, and --no-ext-diff does not cover that
  #   (measured: a real `see discipline #6` became invisible). All three are repo-committable
  #   config that changes what the diff SHOWS without changing what is on disk.
  if ! diff_out=$(git -c core.quotepath=false diff -U0 --no-color --no-ext-diff --no-textconv \
                      "$resolved" -- ":(top)$file" 2>&1); then
    echo "FAIL: git diff failed for '${file}':" >&2
    printf '%s\n' "$diff_out" >&2
    exit 2
  fi

  # Hunk-aware, not prefix-filtered. `grep -v '^+++'` also deleted genuine added lines whose own
  # text begins with `++` (measured: an added line `++ see rule 5` vanished and the file reported
  # NOTHING ADDED). Content lines only ever appear after an `@@` hunk header — but ONE invocation
  # can carry several file blocks (git emits two for a typechange, e.g. regular file -> symlink),
  # and with no reset the second block's own `+++ b/<path>` header was swept in as content and
  # reported as a prose reference no human ever wrote (measured). Hence the `diff --git` reset.
  # LC_ALL=C makes awk byte-oriented. In a UTF-8 locale a single invalid byte anywhere in the
  # added lines aborts awk mid-stream (`towc: multibyte conversion failure`, exit 2) — after which
  # the script printed "contributed no ADDED lines" at exit 0, naming a wrong cause, while a real
  # `see rule 8` sat unresolved in the file (measured on /usr/bin/awk).
  if ! added=$(printf '%s\n' "$diff_out" \
      | LC_ALL=C awk '/^diff --git /{h=0} /^@@/{h=1;next} h && /^\+/{print}'); then
    echo "FAIL: could not parse the diff for '${file}' — awk exited non-zero." >&2
    echo "      Nothing was concluded about this file." >&2
    exit 2
  fi

  if [ -z "$added" ]; then
    # Two different realities used to share one verdict here, and one of them involves a lot of
    # content moving: a file identical to base, versus a file that changed substantially but
    # contributed no ADDED lines (deleted from the worktree, binary, mode/rename only). Naming
    # them apart is the same guarantee the suite already enforces for the two non-empty cases.
    if [ -z "$diff_out" ]; then
      # "Nothing changed" and "my base ref already contains my work" print the same thing, and the
      # second is the likelier one right after committing. Only the second is detectable here, so
      # say it rather than leaving the reader to tell two identical lines apart.
      note=""
      if head_commit=$(git rev-parse --verify --quiet HEAD 2>/dev/null); then
        if [ "$head_commit" = "$resolved" ]; then
          note=" NOTE: ${base} is also your current HEAD, so if you have already committed this"
          note="${note} work, that is why this looks clean — re-run against the commit you started from."
        fi
      fi
      echo "${file}: IDENTICAL to ${base} — no diff at all, nothing to check.${note}"
    else
      echo "${file}: CHANGED versus ${base} but contributed no ADDED lines" \
           "(deletion, binary, mode or rename only) — nothing to check, and worth a glance if you" \
           "expected additions here."
    fi
    continue
  fi

  added_count=$(printf '%s\n' "$added" | wc -l | tr -d ' ')
  # LC_ALL=C for the same reason as awk above; the pattern is ASCII plus a literal UTF-8 `§`,
  # both of which match byte-wise, so nothing is lost by dropping locale-aware collation.
  hits=$(printf '%s\n' "$added" | LC_ALL=C grep -Ei "$REFERENCE_PATTERN")

  if [ -z "$hits" ]; then
    echo "${file}: ${added_count} added line(s), NONE prose-reference-shaped — nothing to resolve here."
    continue
  fi

  hit_count=$(printf '%s\n' "$hits" | wc -l | tr -d ' ')
  echo "${file}: ${hit_count} prose reference(s) in ${added_count} added line(s)."
  echo "         Open each target and confirm it says what you claim it says:"
  printf '%s\n' "$hits" | sed 's/^/         /'
done

exit 0
