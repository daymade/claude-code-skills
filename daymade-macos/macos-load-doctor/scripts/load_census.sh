#!/bin/bash
# load_census.sh — process census for macOS load triage.
# Read-only. BSD ps (macOS stock) only; no GNU flags, no third-party tools.
#
# Reading 1 (PPID aggregation): who owns many children. Counts identify fan-out
#   or a pool; workload and lifecycle evidence decide whether retention is a leak.
# Reading 2 (cumulative CPU time): who has been burning for hours/days — the
#   busy loop that instantaneous %CPU dilutes.
# Reading 3 (instantaneous %CPU): who is burning right now — the active storm.
#
# Usage: bash load_census.sh [topN]   (topN defaults to 12)

set -u
N=${1:-12}

TMP=$(mktemp -t load_census.XXXXXX)
trap 'rm -f "$TMP"' EXIT
ps -Ao pid,ppid,etime,time,%cpu,command > "$TMP"

echo '=== load average ==='
sysctl -n vm.loadavg
echo

echo "=== reading 1: children per parent (top $N) — fan-out candidate; counts alone do not prove a leak ==="
echo "(ppid=1 is launchd and always large — that row is normal)"
awk 'NR>1 {c[$2]++; cmd[$1]=substr($0, index($0,$6))} END {for (p in c) if (c[p]>1) printf "%6d  ppid=%-8s parent=%s\n", c[p], p, (p in cmd ? cmd[p] : "?")}' "$TMP" | sort -rn | head -"$N"
echo

echo "=== reading 2: cumulative CPU time (top $N) — days of TIME at ~100% = busy loop ==="
# ps -r sorts by %cpu, not TIME; sort TIME (which is [[dd-]hh:]mm:ss) by
# converting to seconds.
awk 'NR>1 {
  t=$4; d=0; h=0; m=0; s=0;
  n=split(t, a, "-"); if (n==2) {d=a[1]; t=a[2]}
  k=split(t, b, ":"); if (k==3) {h=b[1]; m=b[2]; s=b[3]} else if (k==2) {m=b[1]; s=b[2]}
  sec=d*86400+h*3600+m*60+s;
  printf "%10d  %s\n", sec, $0
}' "$TMP" | sort -rn | head -"$N" | cut -c13- | awk '{printf "%-8s %-14s %-7s %s\n", $1, $4, $5, substr($0, index($0,$6))}'
echo

echo "=== reading 3: instantaneous %CPU (top $N) — the active storm ==="
# shellcheck disable=SC2086
{ head -1 "$TMP"; tail -n +2 "$TMP" | sort -k5 -rn | head -"$N"; }
echo

echo '=== context: total processes ==='
tail -n +2 "$TMP" | wc -l
