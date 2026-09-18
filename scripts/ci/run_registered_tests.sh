#!/usr/bin/env bash
# run_registered_tests.sh — run the suites declared in scripts/ci/test-suites.txt.
#
# Nothing is discovered; the registry is the whole list. See that file for why, and for
# the criteria a suite has to meet before it earns a line.
#
# Run locally: scripts/ci/run_registered_tests.sh

set -uo pipefail

cd "$(dirname "$0")/../.." || exit 1

REGISTRY="scripts/ci/test-suites.txt"

if [ ! -f "$REGISTRY" ]; then
  echo "FAIL: $REGISTRY is missing"
  exit 1
fi

total=0
failed=0

while read -r runner target _rest; do
  case "${runner:-}" in ''|'#'*) continue ;; esac

  total=$((total + 1))
  echo "──── $runner  $target"

  if [ ! -d "$target" ]; then
    echo "FAIL: registered suite '$target' does not exist"
    failed=$((failed + 1))
    continue
  fi

  case "$runner" in
    python-unittest) command=(python3 -m unittest discover -s "$target" -v) ;;
    # Bare-directory `node --test <dir>` is broken on Node 22 and 24 alike (dir
    # resolved as a CJS entry → MODULE_NOT_FOUND; measured on 22.23.2 and 24.14.0).
    # Glob conventional test-file names instead;
    # nullglob keeps unmatched patterns from reaching node as literal paths.
    node-test)
      shopt -s nullglob
      _files=( "${target}"/test_*.mjs "${target}"/test-*.mjs "${target}"/*.test.mjs )
      shopt -u nullglob
      if [ ${#_files[@]} -eq 0 ]; then
        echo "FAIL: node-test suite '$target' has no test_*.mjs / test-*.mjs / *.test.mjs files"
        failed=$((failed + 1))
        continue
      fi
      command=(node --test "${_files[@]}") ;;
    *)
      echo "FAIL: unknown runner '$runner' — add it to this script and document it in $REGISTRY"
      failed=$((failed + 1))
      continue
      ;;
  esac

  if "${command[@]}"; then
    echo "PASS: $target"
  else
    echo "FAIL: $target"
    failed=$((failed + 1))
  fi
  echo
done < "$REGISTRY"

if [ "$total" -eq 0 ]; then
  echo "FAIL: the registry declares no suites — CI would report success without testing anything"
  exit 1
fi

if [ "$failed" -gt 0 ]; then
  echo "FAIL: $failed of $total registered suite(s) failed"
  exit 1
fi

echo "OK: $total registered suite(s) passed"
