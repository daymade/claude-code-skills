#!/bin/bash
# Calibration for sync-daemon-recorder.sh — self-contained (builds its own fixtures).
#
# Two-sided by design: every case asserts BOTH that the recorder wrote what it
# should AND that it stayed silent where it must. A recorder that logs
# everything passes the positive cases and fails the negative ones.
#
# Fixture note: /bin/true does NOT exist on this machine (verified). Use
# /usr/bin/true. A missing path is a valid premise-check input, not a success one.
#
# Run: bash sync-daemon-recorder.test.sh     (safe: never touches the real logs)
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REC="$DIR/sync-daemon-recorder.sh"
FIX="$(mktemp -d /tmp/syncrec-fixtures.XXXXXX)"
trap 'rm -rf "$FIX"' EXIT

PASS=0; FAIL=0
ok()  { echo "  PASS: $1"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

fresh_log() { mktemp -d /tmp/syncrec.XXXXXX; }
lines() { [ -f "$1" ] && wc -l < "$1" | tr -d ' ' || echo 0; }

# fixtures: a distinct exit code, and stderr noise that still succeeds
printf '#!/bin/bash\nexit 3\n' > "$FIX/exit3.sh"
printf '#!/bin/bash\necho "warning on stderr" >&2\nexit 0\n' > "$FIX/noisy-success.sh"
chmod +x "$FIX"/*.sh

echo "== case 1: successful pass must write NOTHING =="
D=$(fresh_log)
SYNC_LOG_DIR="$D" SYNC_TARGET=/usr/bin/true bash "$REC"; rc=$?
[ "$rc" -eq 0 ] && ok "exit 0 propagated" || bad "expected exit 0, got $rc"
[ "$(lines "$D/source-sync.failures.log")" = "0" ] && ok "no failure line on success" || bad "wrote a line on success"

echo "== case 2: failing pass must write exactly one line =="
D=$(fresh_log)
SYNC_LOG_DIR="$D" SYNC_TARGET=/usr/bin/false bash "$REC"; rc=$?
[ "$rc" -eq 1 ] && ok "exit 1 propagated (launchd still sees the failure)" || bad "expected exit 1, got $rc"
n=$(lines "$D/source-sync.failures.log")
[ "$n" = "1" ] && ok "one failure line" || bad "expected 1 line, got $n"
grep -q "FAILED exit=1" "$D/source-sync.failures.log" && ok "line carries exit code" || bad "line lacks exit code"

echo "== case 3: repeated identical failure collapses to one line =="
D=$(fresh_log)
for _ in 1 2 3; do SYNC_LOG_DIR="$D" SYNC_TARGET=/usr/bin/false bash "$REC" >/dev/null 2>&1; done
n=$(lines "$D/source-sync.failures.log")
[ "$n" = "1" ] && ok "3 identical failures -> 1 line (no spam)" || bad "expected 1 line after 3 identical failures, got $n"

echo "== case 4: a DIFFERENT failure must add a new line =="
D=$(fresh_log)
SYNC_LOG_DIR="$D" SYNC_TARGET=/usr/bin/false  bash "$REC" >/dev/null 2>&1
SYNC_LOG_DIR="$D" SYNC_TARGET="$FIX/exit3.sh" bash "$REC" >/dev/null 2>&1
n=$(lines "$D/source-sync.failures.log")
[ "$n" = "2" ] && ok "distinct failures -> distinct lines" || bad "expected 2 lines, got $n"
grep -q "FAILED exit=3" "$D/source-sync.failures.log" && ok "second line carries its own exit code" || bad "exit=3 line missing"

echo "== case 5: missing upstream target must be loud, not silent =="
D=$(fresh_log)
SYNC_LOG_DIR="$D" SYNC_TARGET=/nonexistent/daemon.sh bash "$REC"; rc=$?
[ "$rc" -eq 75 ] && ok "exit 75 (EX_TEMPFAIL) on missing target" || bad "expected 75, got $rc"
grep -q "PREMATURE-EXIT target-missing" "$D/source-sync.failures.log" && ok "missing target recorded" || bad "missing target not recorded"

echo "== case 6: log rotates at 1 MB instead of growing forever =="
D=$(fresh_log)
head -c 1200000 /dev/zero | tr '\0' 'x' > "$D/source-sync.failures.log"
echo "old-content-line" >> "$D/source-sync.failures.log"
before=$(wc -c < "$D/source-sync.failures.log" | tr -d ' ')
SYNC_LOG_DIR="$D" SYNC_TARGET=/usr/bin/false bash "$REC" >/dev/null 2>&1
[ -f "$D/source-sync.failures.log.1" ] && ok "rotated to .1 backup" || bad "no rotation happened"
after=$(wc -c < "$D/source-sync.failures.log" | tr -d ' ')
[ "$after" -lt "$before" ] && ok "active log shrank ($before -> $after bytes)" || bad "log did not shrink"
[ "$(lines "$D/source-sync.failures.log")" = "1" ] && ok "fresh line after rotation" || bad "expected exactly the new line after rotation"

echo "== case 7: false-positive probe — noisy but successful target =="
D=$(fresh_log)
SYNC_LOG_DIR="$D" SYNC_TARGET="$FIX/noisy-success.sh" bash "$REC"; rc=$?
[ "$rc" -eq 0 ] && ok "stderr noise with exit 0 stays a success" || bad "expected exit 0, got $rc"
[ "$(lines "$D/source-sync.failures.log")" = "0" ] && ok "no failure line for stderr noise" || bad "false positive: logged a successful pass"

echo "== case 8: premise check and a real failure must not be conflated =="
D=$(fresh_log)
SYNC_LOG_DIR="$D" SYNC_TARGET=/nonexistent/x.sh bash "$REC" >/dev/null 2>&1
SYNC_LOG_DIR="$D" SYNC_TARGET=/usr/bin/false   bash "$REC" >/dev/null 2>&1
n=$(lines "$D/source-sync.failures.log")
[ "$n" = "2" ] && ok "premise-exit and real failure both recorded" || bad "expected 2 lines, got $n"
grep -q "PREMATURE-EXIT" "$D/source-sync.failures.log" && grep -q "FAILED exit=1" "$D/source-sync.failures.log" \
  && ok "the two kinds stay distinguishable" || bad "the two kinds blurred together"

echo "== case 9: 历史残留不得冒充本次失败原因（假阳性方向）=="
# A silent failure must not inherit the previous pass's traceback. err.log is
# launchd's append-only stderr, so a naive tail -n 1 blames whatever failed last
# time — measured 2026-09-21: exit 1 with zero stderr recorded the previous
# run's "duplicate source skill name" line.
D=$(fresh_log)
mkdir -p "$D"
printf 'Traceback (most recent call last):\nValueError: an OLD failure from a previous pass\n' \
  > "$D/source-sync.err.log"
printf '#!/bin/bash\nexit 1\n' > "$D/silent.sh"; chmod +x "$D/silent.sh"
SYNC_LOG_DIR="$D" SYNC_TARGET="$D/silent.sh" bash "$REC" >/dev/null 2>&1
if grep -q "no new stderr this pass" "$D/source-sync.failures.log"; then
  ok "silent failure 不继承历史 traceback"
else
  bad "silent failure 继承了历史 reason: $(cat "$D/source-sync.failures.log")"
fi
if grep -q "an OLD failure" "$D/source-sync.failures.log"; then
  bad "把上一次的失败原因写进了本轮"
else
  ok "上一次的失败原因未被写入"
fi

echo "== case 10: 本次有新 stderr 时必须归因本次（假阴性方向）=="
D=$(fresh_log)
mkdir -p "$D"
printf 'ValueError: an OLD failure from a previous pass\n' > "$D/source-sync.err.log"
# The fixture appends to ERR_LOG itself: err.log is filled by launchd's
# StandardErrorPath redirection, which does not exist in this harness. Construct
# that external premise explicitly instead of assuming >&2 reaches the file.
printf '#!/bin/bash\necho "ValueError: THIS pass is the real cause" >> "$SYNC_LOG_DIR/source-sync.err.log"\nexit 1\n' \
  > "$D/loud.sh"; chmod +x "$D/loud.sh"
SYNC_LOG_DIR="$D" SYNC_TARGET="$D/loud.sh" bash "$REC" >/dev/null 2>&1
if grep -q "THIS pass is the real cause" "$D/source-sync.failures.log"; then
  ok "reason 取自本次新增的 stderr"
else
  bad "reason 未取到本次 stderr: $(cat "$D/source-sync.failures.log")"
fi
if grep -q "an OLD failure" "$D/source-sync.failures.log"; then
  bad "reason 是历史残留而非本次"
else
  ok "历史残留未被误用"
fi

echo
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
