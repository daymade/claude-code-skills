#!/usr/bin/env bash
# reference_net.sh <base-ref> <file>… — list the PROSE cross-references among the lines you added,
# so you can open each target and confirm it says what you claim it says.
#
# SCOPE. Prose pointers only: "see rule 8", "discipline #6", "the step 3 above". These have no
# machine-resolvable target, so no link checker can validate them. Markdown links and URLs are NOT
# this script's job — use `lychee` (this repo's house standard; invocation and calibration caveats
# in daymade-docs/docs-cleaner's SKILL.md). A hand-rolled link scanner was tried here and deleted
# after it misreported 16 of 17 valid links, so do not rebuild one inside this script.
#
# CONTRACT. Every outcome is named out loud, and bad input fails loudly: there is no combination of
# arguments under which this prints nothing and looks successful. That is the whole reason it is a
# script rather than the one-liner it replaces, which found five separate ways to do exactly that.
# (`git log -- <this file>` carries the individual defects; they are not repeated here.)
#
# WHAT TO EXPECT. This is a net, not a proof, and it is deliberately noisy in one direction: it will
# re-surface stable anchors you cite constantly and pointer-shaped strings inside test fixtures or
# worked examples. Most runs legitimately end in "yes, those are all fine". It also cannot see a
# pointer with no number in it ("see the section below"), so read your added lines too.
#
# USAGE. <base-ref> is the commit your work started from. NOT `HEAD` — once you commit, `HEAD`
# contains your own change, the diff goes empty, and unresolved pointers sit in the file while this
# reports nothing to do. Resolve it to a literal SHA before you start editing and reuse that value.
#
# Requires bash (uses arrays), so `sh reference_net.sh …` fails on Debian-family systems where
# /bin/sh is dash. The shebang and executable bit make the bare invocation work.
#
# Known boundary: a submodule bump is reported and correctly classified non-prose, but the content
# behind the new commit is never traversed — run this inside that submodule if you edited it.
#
# Exit codes:
#   0  ran to completion — read the printed verdict, which always says which case you are in
#   2  could not run (unresolvable base ref, untracked or mistyped path, git or parse failure)
#
# `set -e` is deliberately NOT used: `grep` exits 1 on no-match, a legitimate result here.

set -uo pipefail

# Prose pointers only. Markdown links are lychee's job — see SCOPE above.
# The leading `(^|[^[:alnum:]])` is a word boundary written portably — `\b` and `\<` differ across
# BSD and GNU. Without it "whisper9", "paper2" and "upper3" all matched, via the "per" inside them.
readonly REFERENCE_PATTERN='(^|[^[:alnum:]])(see|per|above|below|§|rule|discipline|step) *#?[0-9]'

usage() {
  echo "usage: $(basename "$0") <base-ref> <file> [file...]" >&2
  echo "  <base-ref> is the commit your work started from — not HEAD." >&2
}

if [ "$#" -lt 2 ]; then
  usage
  exit 2
fi

# Both are unset in ordinary use, so this line is silent then. When they ARE set, every git call
# below silently targets another repository and a clean verdict may describe a file the caller never
# edited — so say which repository was actually examined.
if [ -n "${GIT_DIR:-}" ] || [ -n "${GIT_WORK_TREE:-}" ]; then
  if ! env_toplevel=$(git rev-parse --show-toplevel 2>/dev/null); then
    env_toplevel="(no working tree)"
  fi
  echo "NOTE: GIT_DIR/GIT_WORK_TREE is set, so this examined ${env_toplevel} — not necessarily the"
  echo "      repository your current directory is in."
fi

base=$1
shift

if ! resolved=$(git rev-parse --verify --quiet "${base}^{commit}"); then
  echo "FAIL: base ref '${base}' does not resolve to a commit." >&2
  echo "      Nothing was examined. Pass the SHA your work started from." >&2
  exit 2
fi

# Resolve each argument to a repo-root-relative path. A bare relative name resolves against the
# CALLER'S cwd, so in a repo with many same-named files it silently examines a different file while
# printing a clean verdict; and an argument matching several paths would be reported as one file.
resolved_paths=()
for file in "$@"; do
  # -z is the only form git guarantees is the RAW pathname. Plain `ls-files` C-quotes any name git
  # considers unusual and returns an escaped *string*, which then matches nothing as a diff pathspec
  # — the file reads as IDENTICAL with real pointers still in it. `core.quotepath=false` does not
  # cover it: quotes, backslashes and control bytes are escaped regardless of that setting.
  # Process substitution, not a pipe, so the array survives into this shell.
  matches=()
  while IFS= read -r -d '' match; do
    matches+=("$match")
  done < <(git ls-files -z --full-name -- "$file" 2>/dev/null)

  if [ "${#matches[@]}" -eq 0 ]; then
    echo "FAIL: '${file}' is not tracked by git. Causes, likeliest first: a new file you have" >&2
    echo "      not \`git add\`ed yet; a typo or the wrong directory; a name git reads as pathspec" >&2
    echo "      magic (a leading ':') — pass it as './${file}'; or a bare repo, which has no" >&2
    echo "      working tree for anything to be tracked in." >&2
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
  # --no-textconv: a .gitattributes textconv driver makes git diff the FILTERED text, and
  #   --no-ext-diff does not cover that. All three are repo-committable config that changes what the
  #   diff SHOWS without changing what is on disk.
  if ! diff_out=$(git -c core.quotepath=false diff -U0 --no-color --no-ext-diff --no-textconv \
                      "$resolved" -- ":(top)$file" 2>&1); then
    echo "FAIL: git diff failed for '${file}':" >&2
    printf '%s\n' "$diff_out" >&2
    exit 2
  fi

  # Hunk-aware, not prefix-filtered: filtering `^+++` also deletes genuine added lines beginning
  # `++`. Content appears only after an `@@` header — but one invocation can carry several file
  # blocks (git emits two for a typechange), so `h` resets at each, or the second block's own
  # `+++ b/<path>` header is read as content and reported as a pointer nobody wrote.
  # LC_ALL=C makes awk byte-oriented: in a UTF-8 locale one invalid byte aborts it mid-stream
  # (`towc: multibyte conversion failure`, exit 2) and the truncated output reads as "no additions".
  if ! added=$(printf '%s\n' "$diff_out" \
      | LC_ALL=C awk '/^diff --git /{h=0} /^@@/{h=1;next} h && /^\+/{print}'); then
    echo "FAIL: could not parse the diff for '${file}' — awk exited non-zero." >&2
    echo "      Nothing was concluded about this file." >&2
    exit 2
  fi

  if [ -z "$added" ]; then
    # Two realities used to share this verdict, and one involves a lot of content moving: identical
    # to base, versus changed but contributing no ADDED lines (worktree deletion, binary, mode or
    # rename). They are named apart for the same reason the two non-empty cases are.
    if [ -z "$diff_out" ]; then
      # "Nothing changed" and "my base already contains my work" are indistinguishable to the
      # reader, and the second is likelier right after committing. Only it is detectable here.
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
  # LC_ALL=C for the same reason as awk above; the pattern is ASCII plus a literal UTF-8 `§`, both
  # of which match byte-wise.
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
