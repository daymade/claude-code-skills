#!/usr/bin/env bash
# apt_install_bounded.sh — hosted-runner APT preparation with a wall-clock deadline.
#
# Why: on the hosted image the mirror list can rank a slow HTTP mirror first, and
# APT's mirror method only moves on when a request FAILS — a slow-but-alive
# transfer never trips Acquire::*Timeout and starves the job. This helper:
#   1. rewrites the mirror list to official HTTPS archive first, official HTTPS
#      security second (suites, components, keyrings and signatures untouched);
#   2. runs update+install under GNU timeout, so a still-slow transfer fails the
#      step loudly instead of eating the job budget.
#
# Scope: real mode writes only the one-shot GitHub-hosted Ubuntu VM's APT config.
# Every host miss exits nonzero before touching anything. Fixture mode (all three
# CI_APT_FIXTURE_* variables set together) exists for --self-test and redirects
# every writable path; those paths must share one private temporary fixture root
# (see validate_fixture_root) — the interface is not a license to write arbitrary
# files.
#
# Usage:
#   apt_install_bounded.sh --self-test
#   apt_install_bounded.sh [--deadline SEC] [--grace SEC] PACKAGE...
#
# Fixture overrides (test only; ALL must be set together, all inside one private
# temporary fixture root owned by the current UID):
#   CI_APT_FIXTURE_MIRRORS_FILE  path standing in for /etc/apt/apt-mirrors.txt
#   CI_APT_FIXTURE_SOURCES_DIR   dir standing in for /etc/apt/sources.list.d
#   CI_APT_FIXTURE_APT_GET       stub executable standing in for apt-get
#
# Mirror-list grammar (official runner-images shape): one entry per line, either
# a bare http(s) URL or `URL<TAB>priority:N`. Rewrite emits the same shape —
# never a leading bare integer.
#
# Dependencies: bash, GNU timeout (coreutils), python3 (stdlib only; path
# validation). Real mode additionally needs apt-get and sudo.
#
# Run locally: scripts/ci/apt_install_bounded.sh --self-test

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

# GNU timeout treats zero as "no deadline"; this interface only permits
# positive whole seconds so callers cannot accidentally disable either bound.
[[ "$deadline" =~ ^[1-9][0-9]*$ ]] || die "--deadline must be positive integer seconds"
[[ "$grace" =~ ^[1-9][0-9]*$ ]] || die "--grace must be positive integer seconds"

# ---------------------------------------------------------------- fixture path validation
# Path checks use python3 stdlib only (os/stat/tempfile). No third-party imports.

validate_fixture_root() {
  if ! command -v python3 >/dev/null 2>&1; then
    die "python3 is required for fixture path validation (stdlib only; no extra package dependencies)"
  fi
  python3 - "$CI_APT_FIXTURE_MIRRORS_FILE" "$CI_APT_FIXTURE_SOURCES_DIR" "$CI_APT_FIXTURE_APT_GET" <<'PY'
import os, stat, sys, tempfile

def fail(msg):
    sys.stderr.write("::error::fixture path validation: %s\n" % msg)
    sys.exit(1)

def is_under(path, root):
    path = os.path.abspath(path)
    root = os.path.abspath(root)
    return path == root or path.startswith(root + os.sep)

def under_etc(path):
    for p in (os.path.abspath(path), os.path.realpath(path)):
        if p == "/etc" or p.startswith("/etc/") or p == "/private/etc" or p.startswith("/private/etc/"):
            return True
    return False

def is_private_owned_dir(path, uid):
    try:
        st = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        return False
    if st.st_uid != uid:
        return False
    return (stat.S_IMODE(st.st_mode) & 0o077) == 0

def main():
    if len(sys.argv) != 4:
        fail("internal error: expected 3 fixture paths")
    mirrors_file, sources_dir, apt_get = sys.argv[1:4]
    uid = os.getuid()
    targets = [
        ("CI_APT_FIXTURE_MIRRORS_FILE", mirrors_file, "file"),
        ("CI_APT_FIXTURE_SOURCES_DIR", sources_dir, "dir"),
        ("CI_APT_FIXTURE_APT_GET", apt_get, "exec"),
    ]

    real = []
    for name, p, kind in targets:
        if not p:
            fail("%s is empty" % name)
        if under_etc(p):
            fail("%s=%s points at the real /etc — refused" % (name, p))
        if os.path.islink(p):
            fail("%s=%s is a symlink — fixture paths must be real files/dirs inside one fixture root" % (name, p))
        rp = os.path.realpath(p)
        if under_etc(rp):
            fail("%s=%s resolves under the real /etc — refused" % (name, p))
        real.append((name, p, kind, rp))

    try:
        common = os.path.commonpath([rp for _n, _p, _k, rp in real])
    except ValueError:
        fail("fixture paths do not share a common ancestor directory")

    # The shared container must itself be a private, current-UID-owned fixture root
    # strictly under the system temp dir — not $TMPDIR itself (which is private on
    # some hosts and would otherwise absorb unrelated foreign temp files).
    temp_root = os.path.realpath(tempfile.gettempdir())
    root = None
    cur = common
    while True:
        if cur and cur != temp_root and is_under(cur, temp_root) and is_private_owned_dir(cur, uid):
            root = cur
            break
        if cur in ("", os.sep, temp_root):
            break
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    if root is None:
        fail("no private fixture root under the system temp dir contains all three CI_APT_FIXTURE_* paths")

    for name, p, kind, rp in real:
        if not is_under(rp, root):
            fail("%s=%s escapes fixture root %s" % (name, p, root))
        try:
            st = os.lstat(p)
        except OSError as e:
            fail("%s=%s cannot be stat'ed: %s" % (name, p, e))
        if st.st_uid != uid:
            fail("%s=%s is not owned by uid %d" % (name, p, uid))
        if kind == "dir":
            if not stat.S_ISDIR(st.st_mode):
                fail("%s=%s is not a directory" % (name, p))
        else:
            if not stat.S_ISREG(st.st_mode):
                fail("%s=%s is not a regular file" % (name, p))
        if kind == "exec" and not (st.st_mode & stat.S_IXUSR):
            fail("%s=%s is not owner-executable" % (name, p))

if __name__ == "__main__":
    main()
PY
}

# ---------------------------------------------------------------- environment binding
# Skipped in self-test mode: the self-test is fixture-only and never runs real APT.

fixture=0
if [ "$mode" != "apt-self-test" ]; then
  # Any of the three being set (even to an empty string) selects fixture mode.
  if [ -n "${CI_APT_FIXTURE_MIRRORS_FILE+set}" ] \
    || [ -n "${CI_APT_FIXTURE_SOURCES_DIR+set}" ] \
    || [ -n "${CI_APT_FIXTURE_APT_GET+set}" ]; then
    fixture=1
  fi

  if [ "$fixture" -eq 1 ]; then
    # Missing keys and explicit empty values both fail here, with a name — never
    # as a set -u unbound-variable abort later.
    if [ "${CI_APT_FIXTURE_MIRRORS_FILE+set}" != "set" ]; then
      die "fixture mode: CI_APT_FIXTURE_MIRRORS_FILE is missing; set all three CI_APT_FIXTURE_* variables together"
    fi
    if [ -z "$CI_APT_FIXTURE_MIRRORS_FILE" ]; then
      die "fixture mode: CI_APT_FIXTURE_MIRRORS_FILE is set but empty; refusing"
    fi
    if [ "${CI_APT_FIXTURE_SOURCES_DIR+set}" != "set" ]; then
      die "fixture mode: CI_APT_FIXTURE_SOURCES_DIR is missing; set all three CI_APT_FIXTURE_* variables together"
    fi
    if [ -z "$CI_APT_FIXTURE_SOURCES_DIR" ]; then
      die "fixture mode: CI_APT_FIXTURE_SOURCES_DIR is set but empty; refusing"
    fi
    if [ "${CI_APT_FIXTURE_APT_GET+set}" != "set" ]; then
      die "fixture mode: CI_APT_FIXTURE_APT_GET is missing; set all three CI_APT_FIXTURE_* variables together"
    fi
    if [ -z "$CI_APT_FIXTURE_APT_GET" ]; then
      die "fixture mode: CI_APT_FIXTURE_APT_GET is set but empty; refusing"
    fi

    validate_fixture_root || die "fixture path validation failed (details above)"

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

# Emit TAB-separated [priority-token, url, ubuntu-path] for every valid mirror line.
# Accepted grammar (official runner-images configure-apt-sources.sh output):
#   URL
#   URL <ws> priority:N
# where URL is http(s) and N is digits. Anything else exits 1. Called in a command
# substitution, so a failure here only exits the subshell — callers check the status.
read_validated_mirrors() {
  local line prio url host rest count=0
  while IFS= read -r line; do
    line="$(printf '%s' "$line" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
    case "$line" in ''|'#'*) continue ;; esac
    if [[ "$line" =~ ^(https?://[^[:space:]]+)$ ]]; then
      prio=""
      url="$line"
    elif [[ "$line" =~ ^(https?://[^[:space:]]+)[[:space:]]+priority:([0-9]+)$ ]]; then
      url="${BASH_REMATCH[1]}"
      prio="priority:${BASH_REMATCH[2]}"
    else
      echo "::error::$script_name: unexpected mirror-list line '$line' in $mirrors_file — expected 'URL' or 'URL<TAB>priority:N'; not rewriting; refusing to guess" >&2
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

  # Keep the input's URL+metadata shape: bare URL in, bare URL out;
  # URL+priority:N in, URL+priority:N out (archive/security ranked 1 then 2).
  # Never emit a leading bare integer.
  local new_content normalized tmp
  if [ "$had_priority" -eq 1 ]; then
    new_content="$(printf 'https://archive.ubuntu.com%s\tpriority:1\nhttps://security.ubuntu.com%s\tpriority:2' "$suffix" "$suffix")"
  else
    new_content="$(printf 'https://archive.ubuntu.com%s\nhttps://security.ubuntu.com%s' "$suffix" "$suffix")"
  fi
  normalized="$(printf '%s\n' "$entries" | awk -F'\t' '{if ($1 == "") print $2; else print $2 "\t" $1}')"

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

  # Default mirror list = frozen official sample: actions/runner-images
  # configure-apt-sources.sh printf output (URL + TAB + priority:N). That is the
  # shape a real GitHub-hosted runner writes — not a self-invented leading-integer
  # line. Overridden per-case where a test needs a different shape.
  make_env() {
    local dir="$1" ref="$2"
    printf 'http://azure.archive.ubuntu.com/ubuntu/\tpriority:1\nhttps://archive.ubuntu.com/ubuntu/\tpriority:2\nhttps://security.ubuntu.com/ubuntu/\tpriority:3\n' > "$dir/apt-mirrors.txt"
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

  local dir log out rc foreign

  for option in --deadline --grace; do
    for value in 0 -1 ''; do
      out="$("$0" "$option" "$value" ripgrep 2>&1)" && rc=0 || rc=$?
      expect "$option rejects nonpositive/empty seconds ($value)" 1 "$rc" "$out" "positive integer seconds"
    done
    out="$("$0" "$option" 2>&1)" && rc=0 || rc=$?
    expect "$option rejects a missing value" 1 "$rc" "$out" "needs a value"
  done

  # 1. health: official URL+priority:N grammar, rewrite keeps URL+metadata shape.
  dir="$root/health"; mkdir -p "$dir"; log="$dir/stub.log"
  make_env "$dir" yes; make_stub "$dir" plain "$log"
  out="$(CI_APT_FIXTURE_MIRRORS_FILE="$dir/apt-mirrors.txt" \
    CI_APT_FIXTURE_SOURCES_DIR="$dir/sources.list.d" \
    CI_APT_FIXTURE_APT_GET="$dir/apt-get" \
    "$0" --deadline 20 --grace 2 ripgrep 2>&1)" && rc=0 || rc=$?
  expect "healthy install succeeds and rewrites mirrors" 0 "$rc" "$out" "bounded apt preparation OK"
  grep -q " update" "$log" || { echo "SELF-TEST FAIL: stub never saw update"; exit 1; }
  grep -q "install -y ripgrep" "$log" || { echo "SELF-TEST FAIL: stub never saw install"; exit 1; }
  grep -q $'https://archive.ubuntu.com/ubuntu/\tpriority:1' "$dir/apt-mirrors.txt" \
    || { echo "SELF-TEST FAIL: mirrors not rewritten to official HTTPS archive first"; exit 1; }
  grep -q $'https://security.ubuntu.com/ubuntu/\tpriority:2' "$dir/apt-mirrors.txt" \
    || { echo "SELF-TEST FAIL: mirrors not rewritten to official HTTPS security second"; exit 1; }
  if grep -qE '^[0-9]+ https?://' "$dir/apt-mirrors.txt"; then
    echo "SELF-TEST FAIL: rewrite emitted leading-integer URL form"
    exit 1
  fi
  echo "self-test PASS: stub saw update then install; mirror list now official URL+priority:N"

  # 1b. health (bare URL grammar): accepted, rewritten in the same bare shape.
  dir="$root/health-bare"; mkdir -p "$dir"; log="$dir/stub.log"
  make_env "$dir" yes; make_stub "$dir" plain "$log"
  printf 'http://azure.archive.ubuntu.com/ubuntu/\n' > "$dir/apt-mirrors.txt"
  out="$(CI_APT_FIXTURE_MIRRORS_FILE="$dir/apt-mirrors.txt" \
    CI_APT_FIXTURE_SOURCES_DIR="$dir/sources.list.d" \
    CI_APT_FIXTURE_APT_GET="$dir/apt-get" \
    "$0" --deadline 20 --grace 2 ripgrep 2>&1)" && rc=0 || rc=$?
  expect "bare-URL mirror list rewrites without inventing metadata" 0 "$rc" "$out" "bounded apt preparation OK"
  grep -q '^https://archive.ubuntu.com/ubuntu/$' "$dir/apt-mirrors.txt" \
    || { echo "SELF-TEST FAIL: bare-URL rewrite did not emit bare archive URL"; exit 1; }
  grep -q '^https://security.ubuntu.com/ubuntu/$' "$dir/apt-mirrors.txt" \
    || { echo "SELF-TEST FAIL: bare-URL rewrite did not emit bare security URL"; exit 1; }
  echo "self-test PASS: bare-URL grammar preserved"

  # 1c. already-rewritten list is a no-op (pandoc step reuse).
  dir="$root/idempotent"; mkdir -p "$dir"; log="$dir/stub.log"
  make_env "$dir" yes; make_stub "$dir" plain "$log"
  printf 'https://archive.ubuntu.com/ubuntu/\tpriority:1\nhttps://security.ubuntu.com/ubuntu/\tpriority:2\n' > "$dir/apt-mirrors.txt"
  out="$(CI_APT_FIXTURE_MIRRORS_FILE="$dir/apt-mirrors.txt" \
    CI_APT_FIXTURE_SOURCES_DIR="$dir/sources.list.d" \
    CI_APT_FIXTURE_APT_GET="$dir/apt-get" \
    "$0" --deadline 20 --grace 2 pandoc 2>&1)" && rc=0 || rc=$?
  expect "already-official list skips rewrite" 0 "$rc" "$out" "no rewrite needed"

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

  # 4. wrong host shape refuses before any rewrite (real grammar, bad host).
  dir="$root/badhost"; mkdir -p "$dir"; log="$dir/stub.log"
  make_env "$dir" yes; make_stub "$dir" plain "$log"
  printf 'http://example.com/mirror/ubuntu/\tpriority:1\n' > "$dir/apt-mirrors.txt"
  out="$(CI_APT_FIXTURE_MIRRORS_FILE="$dir/apt-mirrors.txt" \
    CI_APT_FIXTURE_SOURCES_DIR="$dir/sources.list.d" \
    CI_APT_FIXTURE_APT_GET="$dir/apt-get" \
    "$0" ripgrep 2>&1)" && rc=0 || rc=$?
  expect "unexpected mirror host refuses to rewrite" 1 "$rc" "$out" "unexpected mirror host"

  # 4b. empty mirror list refuses.
  dir="$root/emptylist"; mkdir -p "$dir"; log="$dir/stub.log"
  make_env "$dir" yes; make_stub "$dir" plain "$log"
  : > "$dir/apt-mirrors.txt"
  out="$(CI_APT_FIXTURE_MIRRORS_FILE="$dir/apt-mirrors.txt" \
    CI_APT_FIXTURE_SOURCES_DIR="$dir/sources.list.d" \
    CI_APT_FIXTURE_APT_GET="$dir/apt-get" \
    "$0" ripgrep 2>&1)" && rc=0 || rc=$?
  expect "empty mirror list refuses" 1 "$rc" "$out" "is empty"

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

  # 7. foreign writable temp file (outside the fixture root) is refused; file unchanged.
  dir="$root/foreign"; mkdir -p "$dir"; log="$dir/stub.log"
  make_env "$dir" yes; make_stub "$dir" plain "$log"
  foreign="$(mktemp)"
  printf 'FOREIGN-SENTINEL\n' > "$foreign"
  out="$(CI_APT_FIXTURE_MIRRORS_FILE="$foreign" \
    CI_APT_FIXTURE_SOURCES_DIR="$dir/sources.list.d" \
    CI_APT_FIXTURE_APT_GET="$dir/apt-get" \
    "$0" ripgrep 2>&1)" && rc=0 || rc=$?
  expect "foreign writable temp file as a fixture path is refused" 1 "$rc" "$out" "fixture path validation"
  if ! grep -q '^FOREIGN-SENTINEL$' "$foreign"; then
    echo "SELF-TEST FAIL: foreign file was modified"
    exit 1
  fi
  rm -f "$foreign"
  echo "self-test PASS: foreign file unchanged"

  # 7b. symlinked fixture path is refused; target unchanged.
  dir="$root/symlink"; mkdir -p "$dir"; log="$dir/stub.log"
  make_env "$dir" yes; make_stub "$dir" plain "$log"
  foreign="$(mktemp)"
  printf 'FOREIGN-SENTINEL\n' > "$foreign"
  ln -s "$foreign" "$dir/apt-get-link"
  out="$(CI_APT_FIXTURE_MIRRORS_FILE="$dir/apt-mirrors.txt" \
    CI_APT_FIXTURE_SOURCES_DIR="$dir/sources.list.d" \
    CI_APT_FIXTURE_APT_GET="$dir/apt-get-link" \
    "$0" ripgrep 2>&1)" && rc=0 || rc=$?
  expect "symlinked APT stub is refused" 1 "$rc" "$out" "symlink"
  if ! grep -q '^FOREIGN-SENTINEL$' "$foreign"; then
    echo "SELF-TEST FAIL: symlink target was modified"
    exit 1
  fi
  rm -f "$foreign"
  echo "self-test PASS: symlink target unchanged"

  # 7c. real /etc target is refused.
  dir="$root/etcref"; mkdir -p "$dir"; log="$dir/stub.log"
  make_env "$dir" yes; make_stub "$dir" plain "$log"
  out="$(CI_APT_FIXTURE_MIRRORS_FILE="/etc/apt/apt-mirrors.txt" \
    CI_APT_FIXTURE_SOURCES_DIR="$dir/sources.list.d" \
    CI_APT_FIXTURE_APT_GET="$dir/apt-get" \
    "$0" ripgrep 2>&1)" && rc=0 || rc=$?
  expect "real /etc mirror path is refused" 1 "$rc" "$out" "/etc"

  # 8. missing key and explicit empty value fail with a name, not a set -u abort.
  dir="$root/vars"; mkdir -p "$dir"; log="$dir/stub.log"
  make_env "$dir" yes; make_stub "$dir" plain "$log"
  out="$(CI_APT_FIXTURE_MIRRORS_FILE="$dir/apt-mirrors.txt" \
    CI_APT_FIXTURE_SOURCES_DIR="$dir/sources.list.d" \
    "$0" ripgrep 2>&1)" && rc=0 || rc=$?
  expect "missing CI_APT_FIXTURE_APT_GET fails explicitly" 1 "$rc" "$out" "CI_APT_FIXTURE_APT_GET is missing"
  if printf '%s\n' "$out" | grep -q "unbound variable"; then
    echo "SELF-TEST FAIL: missing key hit set -u instead of an explicit message"
    exit 1
  fi
  out="$(CI_APT_FIXTURE_MIRRORS_FILE= \
    CI_APT_FIXTURE_SOURCES_DIR="$dir/sources.list.d" \
    CI_APT_FIXTURE_APT_GET="$dir/apt-get" \
    "$0" ripgrep 2>&1)" && rc=0 || rc=$?
  expect "explicit empty CI_APT_FIXTURE_MIRRORS_FILE fails explicitly" 1 "$rc" "$out" "set but empty"
  if printf '%s\n' "$out" | grep -q "unbound variable"; then
    echo "SELF-TEST FAIL: empty value hit set -u instead of an explicit message"
    exit 1
  fi

  trap - EXIT
  rm -rf "$root"
  echo "apt_install_bounded self-test: all cases passed"
}

# ---------------------------------------------------------------- dispatch

case "$mode" in
  apt-self-test) self_test ;;
  install) run_bounded_install ;;
esac
