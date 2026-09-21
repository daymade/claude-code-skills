#!/bin/bash
# Failure recorder for the marketplace skill-source sync daemon.
#
# Problem it solves: the upstream daemon runs under `set -euo pipepipefail` and
# prints its "verified" line only after every step succeeded. A failed pass
# therefore writes NOTHING to source-sync.out.log, so 4000+ lines of "verified"
# are indistinguishable from a healthy run. The traceback does land in
# source-sync.err.log, but nothing reads that file, so a pass can fail every
# 5 minutes for an hour with no signal anywhere.
#
# What this does — and only this: on a non-zero exit, append ONE line
# (timestamp + exit code + last stderr line) to source-sync.failures.log, then
# re-raise the original exit code so launchd still records the failure.
#
# Deliberately absent, per the quiet-watchdog contract (macos-watchdog skill):
#   * no notification      — a log line is a ticket, not a page
#   * no auto-remediation  — nothing here is safe to fix unattended
#   * no repeated lines    — consecutive identical failures collapse to one
#   * bounded log          — rotates at 1 MB, one backup (clause: a recorder
#                            must not itself become the unbounded file)
#
# Premise self-check (clause 1): if the upstream script is gone, say so loudly
# instead of exiting silently — a missing target is exactly the failure mode
# that goes unnoticed for days.
#
# SYNC_TARGET overrides the upstream script so the failure branch can be
# calibrated without breaking the real daemon:
#   SYNC_TARGET=/bin/false bash sync-daemon-recorder.sh

set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# The daemon entry this wraps lives at the RUN location (~/.config/...), a symlink
# into the plugin cache — not beside this file. Resolve it there so the recorder
# always wraps the copy launchd actually runs.
TARGET="${SYNC_TARGET:-$HOME/.config/claude-switch-models-setup/sync-local-skill-sources-daemon.sh}"
# SYNC_LOG_DIR exists so the failure branch can be calibrated against a scratch
# log instead of the real one.
LOG_DIR="${SYNC_LOG_DIR:-$HOME/Library/Logs/claude-switch-models-setup}"
ERR_LOG="$LOG_DIR/source-sync.err.log"
FAIL_LOG="$LOG_DIR/source-sync.failures.log"
MAX_BYTES=1048576   # 1 MB

record() {
    mkdir -p "$LOG_DIR"
    # Rotate before appending: keep one previous file, never grow unbounded.
    if [ -f "$FAIL_LOG" ]; then
        size="$(wc -c < "$FAIL_LOG" | tr -d ' ')"
        if [ "$size" -ge "$MAX_BYTES" ]; then
            mv -f "$FAIL_LOG" "$FAIL_LOG.1"
        fi
    fi
    # Collapse consecutive identical failures: compare the signature only, so a
    # repeating failure every 5 min does not produce 12 identical lines an hour.
    # The date is ONE whitespace-free field (%Y-%m-%dT%H:%M:%SZ), so stripping a
    # single leading field is what recovers the signature — stripping two eats
    # the first word of the signature and makes every line look new.
    sig="$1"
    prev=""
    [ -f "$FAIL_LOG" ] && prev="$(tail -n 1 "$FAIL_LOG" 2>/dev/null | sed 's/^[^ ]* //')"
    if [ "$prev" != "$sig" ]; then
        printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$sig" >> "$FAIL_LOG"
    fi
}

# --- premise self-check -------------------------------------------------------
if [ ! -e "$TARGET" ]; then
    record "PREMATURE-EXIT target-missing :: $TARGET (upstream symlink broken?)"
    exit 75          # EX_TEMPFAIL: launchd keeps scheduling, we do not lie
fi

# err.log is launchd's append-only StandardErrorPath: it holds every earlier
# failure too. Snapshot its length so the reason below can only ever be a line
# THIS pass wrote — otherwise a silent failure inherits the previous one's
# traceback and the log blames the wrong cause.
err_before=0
[ -f "$ERR_LOG" ] && err_before="$(wc -l < "$ERR_LOG" 2>/dev/null | tr -d ' ')"
err_before="${err_before:-0}"

"$TARGET"
rc=$?

if [ "$rc" -ne 0 ]; then
    err_after=0
    [ -f "$ERR_LOG" ] && err_after="$(wc -l < "$ERR_LOG" 2>/dev/null | tr -d ' ')"
    err_after="${err_after:-0}"
    reason="(no new stderr this pass)"
    if [ "$err_after" -gt "$err_before" ]; then
        last="$(tail -n 1 "$ERR_LOG" 2>/dev/null)"
        [ -n "$last" ] && reason="$last"
    fi
    record "FAILED exit=$rc :: $reason"
fi

exit "$rc"
