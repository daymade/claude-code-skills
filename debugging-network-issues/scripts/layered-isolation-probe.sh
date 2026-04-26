#!/usr/bin/env bash
# layered-isolation-probe.sh — run the 3-path A/B/C comparison for a CDN-
# fronted service and report which layer closed the connection.
#
# Prereqs: a mock idle upstream running reachable from the origin host,
# and a temporary CDN/reverse-proxy route that forwards a test hostname
# to the mock. See references/layered-isolation-experiment.md for the
# full setup. This script only runs the comparison; setup and cleanup
# are intentionally separate so a failed probe never leaves stale config.
#
# Usage:
#   HOST=test-idle.example.com \
#   ORIGIN_IP=203.0.113.10 \
#   SERVER_SSH=root@203.0.113.10 \
#   LOOPBACK_URL=http://127.0.0.1:19999/probe-c \
#   MAX_SECONDS=300 \
#   ./layered-isolation-probe.sh
#
# Expected output: a matrix showing close time per path. A failing-only-
# on-path-A pattern pins the CDN as the culprit.

set -euo pipefail

: "${HOST:?Set HOST, e.g. test-idle.example.com}"
: "${ORIGIN_IP:?Set ORIGIN_IP, the real IP of the origin host}"
: "${SERVER_SSH:?Set SERVER_SSH, e.g. root@origin.example.com}"
: "${LOOPBACK_URL:?Set LOOPBACK_URL, e.g. http://127.0.0.1:19999/probe-c}"
MAX_SECONDS="${MAX_SECONDS:-300}"
RESULTS_DIR="${RESULTS_DIR:-/tmp/layered-isolation-$(date +%s)}"
mkdir -p "$RESULTS_DIR"

echo "=== Layered isolation probe ==="
echo "HOST=$HOST"
echo "ORIGIN_IP=$ORIGIN_IP"
echo "SERVER_SSH=$SERVER_SSH"
echo "LOOPBACK_URL=$LOOPBACK_URL"
echo "MAX_SECONDS=$MAX_SECONDS"
echo "Results in $RESULTS_DIR"
echo

# env -i strips the caller's environment. This prevents local proxy
# variables (http_proxy, https_proxy, Shadowrocket, etc.) from silently
# routing the "bypass" probe back through the layer we are trying to
# bypass. This is the #1 way layered isolation experiments go wrong.
# See references/cognitive-traps.md Trap 5.
STRIP_ENV='env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp'

run_path() {
    local label="$1"
    local description="$2"
    local cmd="$3"
    echo "--- Path $label: $description ---"
    local out="$RESULTS_DIR/path-$label.out"
    local err="$RESULTS_DIR/path-$label.err"
    local t0
    t0=$(date +%s.%N)
    set +e
    eval "$cmd" > "$out" 2> "$err"
    local rc=$?
    set -e
    local t1
    t1=$(date +%s.%N)
    local elapsed
    elapsed=$(awk "BEGIN{printf \"%.2f\", $t1 - $t0}")
    local bytes
    bytes=$(wc -c < "$out" | tr -d ' ')
    echo "  rc=$rc  elapsed=${elapsed}s  bytes=$bytes"
    if [[ -s "$err" ]]; then
        echo "  stderr: $(head -c 200 "$err")"
    fi
    echo
    # Return a tuple via globals (bash limitation)
    declare -g "ELAPSED_$label=$elapsed"
    declare -g "BYTES_$label=$bytes"
    declare -g "RC_$label=$rc"
}

CURL_COMMON="-sS -o $RESULTS_DIR/__body.tmp -w 'HTTP=%{http_code}\nTIME=%{time_total}\nERRCODE=%{exitcode}\nERRMSG=%{errormsg}\n' --max-time $MAX_SECONDS"

# Path A: full path through the CDN
PATH_A_CMD="$STRIP_ENV curl $CURL_COMMON https://$HOST/probe-a"

# Path B: bypass the CDN via --resolve to origin IP
PATH_B_CMD="$STRIP_ENV curl $CURL_COMMON --resolve $HOST:443:$ORIGIN_IP https://$HOST/probe-b"

# Path C: loopback from inside the origin host
PATH_C_CMD="ssh $SERVER_SSH \"$STRIP_ENV curl -sS -o /tmp/__probe_c_body -w 'HTTP=%{http_code}\nTIME=%{time_total}\nERRCODE=%{exitcode}\nERRMSG=%{errormsg}\n' --max-time $MAX_SECONDS $LOOPBACK_URL\""

# Run the three paths sequentially. Parallel is tempting but makes
# server-side mock logs harder to correlate; sequential with 5s gap
# gives clean per-path logs.
run_path A "via CDN (baseline — expected to fail)" "$PATH_A_CMD"
sleep 5
run_path B "bypass CDN (--resolve to origin IP)"   "$PATH_B_CMD"
sleep 5
run_path C "server loopback (inside origin)"       "$PATH_C_CMD"

echo "=== Result matrix ==="
printf "%-6s  %-10s  %-10s  %-6s\n" "Path" "Elapsed" "Bytes" "rc"
printf "%-6s  %-10s  %-10s  %-6s\n" "-----" "-------" "-----" "--"
for p in A B C; do
    e_var="ELAPSED_$p"; b_var="BYTES_$p"; r_var="RC_$p"
    printf "%-6s  %-10s  %-10s  %-6s\n" "$p" "${!e_var}" "${!b_var}" "${!r_var}"
done

echo
echo "=== Interpretation guide ==="
echo "- Only Path A short-closes: CDN is the cause"
echo "- A and B short-close, C does not: origin external network / LB"
echo "- All three short-close: origin application / upstream"
echo "- All three run to MAX_SECONDS: failure did not reproduce"
echo "- Path B unexpectedly short-closes: CHECK FOR LOCAL PROXY LEAKAGE"
echo "  (env -i above should prevent, but verify with 'curl -v' if in doubt)"
echo
echo "Raw outputs: $RESULTS_DIR"
