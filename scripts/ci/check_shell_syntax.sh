#!/usr/bin/env bash
# check_shell_syntax.sh — parse every shell script in the repository.
#
# Skills ship shell scripts that users execute directly. A syntax error reaches them at
# run time, in their repository, usually while they are already trying to recover from
# something. `bash -n` parses without executing, so this is safe to run anywhere.
#
# Scope note: this catches syntax, not behaviour. Behaviour is covered by the suites in
# scripts/ci/test-suites.txt, which run on Linux precisely because a script can parse
# fine on both platforms and still only work on one.
#
# Run locally: scripts/ci/check_shell_syntax.sh

set -uo pipefail

cd "$(dirname "$0")/../.." || exit 1

total=0
failed=0

while IFS= read -r script; do
  total=$((total + 1))
  if ! output="$(bash -n "$script" 2>&1)"; then
    failed=$((failed + 1))
    echo "FAIL: $script"
    printf '%s\n' "$output" | sed 's/^/    /'
  fi
done < <(
  find . -name '*.sh' -type f \
    -not -path './.git/*' \
    -not -path '*/node_modules/*' \
    -not -path '*/.venv/*' \
    -not -path '*/vendor/*' \
    | sort
)

if [ "$failed" -gt 0 ]; then
  echo
  echo "FAIL: $failed of $total shell script(s) do not parse"
  exit 1
fi

echo "OK: $total shell scripts parse cleanly"
