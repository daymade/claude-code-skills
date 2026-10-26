#!/usr/bin/env bash
# apt_install_bounded.sh — hosted-runner APT preparation with a wall-clock deadline.
#
# Why this exists: on PR #1218 the "Install registered-suite runtime tools" step twice
# starved to the 20-minute job deadline mid-transfer. /etc/apt/apt-mirrors.txt on the
# hosted image ranks the Azure HTTP mirror first, and APT's mirror method only moves to
# the next mirror when a request FAILS — a slow-but-alive transfer (e.g. libflite1,
# 13.6 MB, minutes per package) never fails, so Acquire::*Timeout=15 never fires and the
# job is canceled with zero tests run. Retrying unchanged was measured worse the second
# time, so the fix changes two things on the one-shot VM only:
#   1. the mirror list is rewritten to the official HTTPS archive first, official HTTPS
#      security second (suites, components, keyrings and signatures are untouched);
#   2. the whole update+install runs under GNU timeout, so a still-slow transfer fails
#     the step loudly instead of eating the job budget.
#
# Scope guards: this must never run on a developer machine or a self-hosted runner. Real
# mode requires GITHUB_ACTIONS=true AND RUNNER_ENVIRONMENT=github-hosted AND Linux/Ubuntu;
# any miss exits nonzero before touching anything. Fixture mode (all CI_APT_FIXTURE_*
# variables set together) bypasses the host guards but also redirects every writable
# path, so a normal parameter or test fixture can never modify the local /etc.
#
# Usage:
#   apt_install_bounded.sh --self-test
#   apt_install_bounded.sh [--deadline SEC] [--grace SEC] PACKAGE...
#
# Fixture overrides (test only; ALL must be set together):
#   CI_APT_FIXTURE_MIRRORS_FILE  path standing in for /etc/apt/apt-mirrors.txt
#   CI_APT_FIXTURE_SOURCES_DIR   dir standing in for /etc/apt/sources.list.d
#   CI_APT_FIXTURE_APT_GET       stub executable standing in for apt-get
#
# Run locally: scripts/ci/apt_install_bounded.sh --self-test
# (needs GNU timeout; the deadline contract is only real where coreutils provides it)

set -eu

script_name="$(basename "$0")"

die() {
  echo "::error::$script_name: $*" >&2
  exit 1
}

# Fail while preserving the underlying exit status (apt's nonzero, or timeout's 124).
fail_with_status() {
  local status="$1"
  shift
  echo "::error::$script_name: $*" >&2
  exit "$status"
}

DEFAULT_DEADLINE=360
DEFAULT_GRACE=15

mirrors_file="/etc/apt/apt-mirrors.txt"
sources_dir="/etc/apt/sources.list.d"
sources_list="/etc/apt/sources.list"

# ---------------------------------------------------------------- argument parsing

mode="install"
deadline="$DEFAULT_DEADLINE"
grace="$DEFAULT_GRACE"
packages=()

while [ "$#" -gt 0 ]; do
  case "$1" in
    --self-test)
      mode="apt-self-test"
      ;;
    --deadline)
      [ "$#" -ge 2 ] || die "--deadline needs a value"
      deadline="$2"
      shift
      ;;
    --grace)
      [ "$#" -ge 2 ] || die "--grace needs a value"
      grace="$2"
      shift
      ;;
    --*)
      die "unknown option $1"
      ;;
    *)
      packages+=("$1")
      ;;
  esac
  shift
done

# ---------------------------------------------------------------- environment binding
# Skipped in self-test mode: the self-test is fixture-only and never runs real APT.

fixture=0
if [ "$mode" != "apt-self-test" ]; then
for var in CI_APT_FIXTURE_MIRRORS_FILE CI_APT_FIXTURE_SOURCES_DIR CI_APT_FIXTURE_APT_GET; do
  if [ -n "${!var:-}" ]; then
    fixture=1
    break
  fi
done

if [ "$fixture" -eq 1 ]; then
  # Fixture mode: every writable path is redirected, so fixtures can never touch /etc.
  [ -n "$CI_APT_FIXTURE_MIRRORS_FILE" ] || die "fixture mode: CI_APT_FIXTURE_MIRRORS_FILE must be set together with the others"
  [ -n "$CI_APT_FIXTURE_SOURCES_DIR" ] || die "fixture mode: CI_APT_FIXTURE_SOURCES_DIR must be set together with the others"
  [ -n "$CI_APT_FIXTURE_APT_GET" ] || die "fixture mode: CI_APT_FIXTURE_APT_GET must be set together with the others"
  mirrors_file="$CI_APT_FIXTURE_MIRRORS_FILE"
  sources_dir="$CI_APT_FIXTURE_SOURCES_DIR"
  export APT_GET="$CI_APT_FIXTURE_APT_GET"
  sudo_cmd=""
else
  # Real mode: hosted GitHub runner only. Every miss fails before anything is touched.
  [ "${GITHUB_ACTIONS:-}" = "true" ] \
    || die "refusing to run: GITHUB_ACTIONS is not true — this command rewrites APT mirrors and may only run on a GitHub-hosted VM"
  [ "${RUNNER_ENVIRONMENT:-}" = "github-hosted" ] \
    || die "refusing to run: RUNNER_ENVIRONMENT is '${RUNNER_ENVIRONMENT:-unset}', not github-hosted — never run this on a developer machine or self-hosted runner"
  [ "$(uname -s)" = "Linux" ] || die "refusing to run: not Linux"
  grep -q '^ID=ubuntu' /etc/os-release 2>/dev/null \
    || die "refusing to run: /etc/os-release does not identify Ubuntu"
  sudo_cmd="sudo"
fi
fi

# ---------------------------------------------------------------- mirror list rewrite

# Emit TAB-separated [priority, url, ubuntu-path] for every valid mirror line; exit 1 on
# anything that is not `[priority] http(s)://host/ubuntu[/]`. Called in a command
# substitution, so a failure here only exits the subshell — callers check the status.
read_validated_mirrors() {
  local line prio url host rest count=0
  while IFS= read -r line; do
    line="$(printf '%s' "$line" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
    case "$line" in ''|'#'*) continue ;; esac
    if [[ "$line" =~ ^([0-9]+)[[:space:]]+(https?://[^[:space:]]+)$ ]]; then
      prio="${BASH_REMATCH[1]}"
      url="${BASH_REMATCH[2]}"
    elif [[ "$line" =~ ^(https?://[^[:space:]]+)$ ]]; then
      prio=""
      url="$line"
    else
      echo "::error::$script_name: unexpected mirror-list line '$line' in $mirrors_file — not rewriting; refusing to guess" >&2
      exit 1
    fi
    host="${url#*://}"
    host="${host%%/*}"
    rest="/${url#*://*/}"
    # Known Ubuntu archive hosts only: the official archive/security and their CDN
    # aliases (azure.archive.ubuntu.com). Anything else is not a mirror list this
    # helper is willing to rewrite.
    if [ "$host" != "archive.ubuntu.com" ] \
      && [ "$host" != "security.ubuntu.com" ] \
      && [[ ! "$host" =~ ^[a-z0-9-]+\.archive\.ubuntu\.com$ ]]; then
      echo "::error::$script_name: unexpected mirror host '$host' in $mirrors_file — not rewriting" >&2
      exit 1
    fi
    if ! [[ "$rest" =~ ^(.*/)?ubuntu/?$ ]]; then
      echo "::error::$script_name: unexpected mirror entry '$url' (path does not end in /ubuntu) — not rewriting" >&2
      exit 1
    fi
    count=$((count + 1))
    if [ "$count" -gt 16 ]; then
      echo "::error::$script_name: mirror list in $mirrors_file has too many entries — unexpected shape" >&2
      exit 1
    fi
    printf '%s\t%s\t%s\n' "$prio" "$url" "$rest"
  done < "$mirrors_file"
}

rewrite_mirrors() {
  echo "--- current $mirrors_file:"
  cat "$mirrors_file"

  local entries
  entries="$(read_validated_mirrors)" \
    || die "unexpected mirror-list shape in $mirrors_file — refusing to rewrite (details above)"

  if [ -z "$entries" ]; then
    die "mirror list $mirrors_file is empty — unexpected shape"
  fi

  # awk -F'\t', not read: IFS tab-splitting strips a leading empty priority field.
  local rest suffix had_priority
  rest="$(printf '%s\n' "$entries" | head -n 1 | awk -F'\t' '{print $3}')"
  had_priority="$(printf '%s\n' "$entries" | awk -F'\t' '$1 != "" {found=1} END {print found + 0}')"
  if [[ "$rest" == */ ]]; then
    suffix="$rest"
  else
    suffix="${rest}/"
  fi

  local new_content normalized tmp
  if [ "$had_priority" -eq 1 ]; then
    new_content="$(printf '1 https://archive.ubuntu.com%s\n2 https://security.ubuntu.com%s' "$suffix" "$suffix")"
  else
    new_content="$(printf 'https://archive.ubuntu.com%s\nhttps://security.ubuntu.com%s' "$suffix" "$suffix")"
  fi
  normalized="$(printf '%s\n' "$entries" | awk -F'\t' '{print ($1=="" ? "" : $1" ") $2}')"

  if [ "$normalized" = "$new_content" ]; then
    echo "mirror list already official HTTPS first; no rewrite needed"
    return 0
  fi

  tmp="$(mktemp)"
  trap 'rm -f "$tmp"' EXIT
  printf '%s\n' "$new_content" > "$tmp"
  if [ -n "$sudo_cmd" ]; then
    "$sudo_cmd" cp "$tmp" "$mirrors_file"
  else
    cp "$tmp" "$mirrors_file"
  fi
  rm -f "$tmp"
  trap - EXIT
  echo "--- rewritten $mirrors_file (official HTTPS archive first, security second):"
  cat "$mirrors_file"
}

# ---------------------------------------------------------------- reference check

check_reference() {
  if [ ! -d "$sources_dir" ]; then
    die "sources directory $sources_dir is missing — unexpected shape"
  fi
  local f refs=0
  for f in "$sources_list" "$sources_dir"/*.sources "$sources_dir"/*.list; do
    [ -f "$f" ] || continue
    if grep -Fq "mirror+file:$mirrors_file" "$f"; then
      refs=$((refs + 1))
      echo "--- $f references the mirror list (suites/components/keyring left untouched):"
      cat "$f"
    fi
  done
  if [ "$refs" -eq 0 ]; then
    die "no source file references mirror+file:$mirrors_file — unexpected sources layout; not guessing"
  fi
}

# ---------------------------------------------------------------- bounded run

require_gnu_timeout() {
  if ! command -v timeout >/dev/null 2>&1; then
    die "GNU timeout is not available — refusing to run APT without a wall-clock deadline"
  fi
  if ! timeout --version 2>&1 | grep -q 'GNU coreutils'; then
    die "'timeout' on PATH is not GNU coreutils — refusing a deadline this run cannot enforce"
  fi
}

run_bounded_install() {
  if [ "${#packages[@]}" -eq 0 ]; then
    die "no packages given"
  fi

  check_reference
  rewrite_mirrors
  require_gnu_timeout

  # Keep the original per-request budget visible in the log, as the previous step did.
  if [ "$fixture" -ne 1 ]; then
    apt-config dump Acquire::Retries Acquire::http::Timeout Acquire::https::Timeout
  fi

  local runner
  runner="$(mktemp)"
  trap 'rm -f "$runner"' EXIT
  cat > "$runner" <<'EOF'
set -eu
aptget="${APT_GET:-apt-get}"
opts="-o Acquire::Retries=1 -o Acquire::http::Timeout=15 -o Acquire::https::Timeout=15"
# shellcheck disable=SC2086
"$aptget" $opts update
"$aptget" $opts install -y "$@"
EOF

  local start end rc
  start="$(date +%s)"
  echo "--- bounded apt update+install: deadline=${deadline}s grace=${grace}s packages: $*"
  set +e
  if [ "$fixture" -eq 1 ]; then
    timeout -k "$grace" "$deadline" /bin/sh "$runner" "${packages[@]}"
  else
    sudo timeout -k "$grace" "$deadline" /bin/sh "$runner" "${packages[@]}"
  fi
  rc=$?
  set -e
  end="$(date +%s)"

  rm -f "$runner"
  trap - EXIT

  if [ "$rc" -eq 124 ]; then
    fail_with_status 124 "apt update+install exceeded the ${deadline}s total deadline (elapsed $((end - start))s) — failing this preparation instead of starving the job; not retrying"
  fi
  if [ "$rc" -ne 0 ]; then
    fail_with_status "$rc" "apt update+install failed with exit $rc after $((end - start))s"
  fi
  echo "bounded apt preparation OK in $((end - start))s"
}

# ---------------------------------------------------------------- self-test

self_test() {
  require_gnu_timeout

  local root
  root="$(mktemp -d)"
  trap 'rm -rf "$root"' EXIT

  # A stub apt-get: logs every invocation, configurable install behavior. It receives
  # the same -o options real apt-get does, so it picks its action from the whole arg
  # list instead of $1.
  make_stub() {
    local dir="$1" style="$2" log="$3"
    {
      echo '#!/usr/bin/env bash'
      echo "echo \"stub-apt \$*\" >> $log"
      echo 'action=""'
      echo 'for a in "$@"; do'
      echo '  case "$a" in update|install) action="$a" ;; esac'
      echo 'done'
      echo 'case "$action" in'
      echo '  update) exit 0 ;;'
      echo '  install)'
      if [ "$style" = "hang" ]; then
        echo '    while :; do echo "Get:1 http://slow.example/ubuntu slow.pkg [13.6 MB]"; sleep 0.2; done'
      else
        echo '    echo "stub install done"'
        echo '    exit ${STUB_INSTALL_EXIT:-0}'
      fi
      echo '    ;;'
      echo 'esac'
    } > "$dir/apt-get"
    chmod +x "$dir/apt-get"
  }

  make_env() {
    local dir="$1" ref="$2"
    printf '1 http://azure.archive.ubuntu.com/ubuntu/\n' > "$dir/apt-mirrors.txt"
    mkdir -p "$dir/sources.list.d"
    if [ "$ref" = "yes" ]; then
      printf 'Types: deb\nURIs: mirror+file:%s\nSuites: noble noble-updates\nComponents: main universe\n' \
        "$dir/apt-mirrors.txt" > "$dir/sources.list.d/ubuntu.sources"
    fi
  }

  expect() {
    local what="$1" want="$2" got="$3" out="$4" needle="$5"
    if [ "$got" -ne "$want" ]; then
      echo "SELF-TEST FAIL: $what — expected exit $want, got $got"
      printf '%s\n' "$out" | sed 's/^/    /'
      exit 1
    fi
    if [ -n "$needle" ]; then
      if ! printf '%s\n' "$out" | grep -q "$needle"; then
        echo "SELF-TEST FAIL: $what — output missing '$needle'"
        printf '%s\n' "$out" | sed 's/^/    /'
        exit 1
      fi
    fi
    echo "self-test PASS: $what"
  }

  local dir log out rc

  # 1. health: fixture guards pass, update+install run, mirrors rewritten.
  dir="$root/health"; mkdir -p "$dir"; log="$dir/stub.log"
  make_env "$dir" yes; make_stub "$dir" plain "$log"
  out="$(CI_APT_FIXTURE_MIRRORS_FILE="$dir/apt-mirrors.txt" \
    CI_APT_FIXTURE_SOURCES_DIR="$dir/sources.list.d" \
    CI_APT_FIXTURE_APT_GET="$dir/apt-get" \
    "$0" --deadline 20 --grace 2 ripgrep 2>&1)" && rc=0 || rc=$?
  expect "healthy install succeeds and rewrites mirrors" 0 "$rc" "$out" "bounded apt preparation OK"
  grep -q " update" "$log" || { echo "SELF-TEST FAIL: stub never saw update"; exit 1; }
  grep -q "install -y ripgrep" "$log" || { echo "SELF-TEST FAIL: stub never saw install"; exit 1; }
  grep -q '1 https://archive.ubuntu.com/ubuntu/' "$dir/apt-mirrors.txt" \
    || { echo "SELF-TEST FAIL: mirrors not rewritten to official HTTPS"; exit 1; }
  echo "self-test PASS: stub saw update then install; mirror list now official HTTPS"

  # 2. download/install failure propagates nonzero.
  dir="$root/fail"; mkdir -p "$dir"; log="$dir/stub.log"
  make_env "$dir" yes; make_stub "$dir" plain "$log"
  out="$(STUB_INSTALL_EXIT=42 \
    CI_APT_FIXTURE_MIRRORS_FILE="$dir/apt-mirrors.txt" \
    CI_APT_FIXTURE_SOURCES_DIR="$dir/sources.list.d" \
    CI_APT_FIXTURE_APT_GET="$dir/apt-get" \
    "$0" --deadline 20 --grace 2 ripgrep 2>&1)" && rc=0 || rc=$?
  expect "apt failure exits nonzero" 42 "$rc" "$out" "apt update+install failed with exit 42"

  # 3. the deadline counterexample: continuous output, never finishes -> 124, no OK.
  dir="$root/hang"; mkdir -p "$dir"; log="$dir/stub.log"
  make_env "$dir" yes; make_stub "$dir" hang "$log"
  out="$(CI_APT_FIXTURE_MIRRORS_FILE="$dir/apt-mirrors.txt" \
    CI_APT_FIXTURE_SOURCES_DIR="$dir/sources.list.d" \
    CI_APT_FIXTURE_APT_GET="$dir/apt-get" \
    "$0" --deadline 2 --grace 1 ffmpeg 2>&1)" && rc=0 || rc=$?
  expect "continuous-output transfer is cut by the total deadline" 124 "$rc" "$out" "exceeded the 2s total deadline"
  if printf '%s\n' "$out" | grep -q "bounded apt preparation OK"; then
    echo "SELF-TEST FAIL: deadline hit but a ready marker was printed"
    exit 1
  fi
  echo "self-test PASS: no ready marker after deadline"

  # 4. wrong host shape refuses before any rewrite.
  dir="$root/badhost"; mkdir -p "$dir"; log="$dir/stub.log"
  make_env "$dir" yes; make_stub "$dir" plain "$log"
  printf '1 http://example.com/mirror/ubuntu/\n' > "$dir/apt-mirrors.txt"
  out="$(CI_APT_FIXTURE_MIRRORS_FILE="$dir/apt-mirrors.txt" \
    CI_APT_FIXTURE_SOURCES_DIR="$dir/sources.list.d" \
    CI_APT_FIXTURE_APT_GET="$dir/apt-get" \
    "$0" ripgrep 2>&1)" && rc=0 || rc=$?
  expect "unexpected mirror host refuses to rewrite" 1 "$rc" "$out" "unexpected mirror host"

  # 5. missing mirror+file reference refuses.
  dir="$root/noref"; mkdir -p "$dir"; log="$dir/stub.log"
  make_env "$dir" no; make_stub "$dir" plain "$log"
  out="$(CI_APT_FIXTURE_MIRRORS_FILE="$dir/apt-mirrors.txt" \
    CI_APT_FIXTURE_SOURCES_DIR="$dir/sources.list.d" \
    CI_APT_FIXTURE_APT_GET="$dir/apt-get" \
    "$0" ripgrep 2>&1)" && rc=0 || rc=$?
  expect "missing mirror+file reference refuses" 1 "$rc" "$out" "no source file references"

  # 6. non-GitHub host guards: real mode must refuse before touching anything.
  out="$(env -u GITHUB_ACTIONS -u RUNNER_ENVIRONMENT "$0" ripgrep 2>&1)" && rc=0 || rc=$?
  expect "refuses outside GITHUB_ACTIONS=true" 1 "$rc" "$out" "GITHUB_ACTIONS is not true"
  out="$(GITHUB_ACTIONS=true RUNNER_ENVIRONMENT=self-hosted "$0" ripgrep 2>&1)" && rc=0 || rc=$?
  expect "refuses on self-hosted runner" 1 "$rc" "$out" "not github-hosted"

  trap - EXIT
  rm -rf "$root"
  echo "apt_install_bounded self-test: all cases passed"
}

# ---------------------------------------------------------------- dispatch

case "$mode" in
  apt-self-test) self_test ;;
  install) run_bounded_install ;;
esac
