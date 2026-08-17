#!/bin/bash
# watchdog-cooldown.sh — reusable escalating cool-down + manual pause for
# self-healing watchdogs. SOURCE this file from the watchdog script; do not
# execute it directly.
#
# Why this exists: a self-healing watchdog whose full remediation ladder fails
# will otherwise re-run the entire ladder (and re-send its "all failed"
# notification) every launchd interval forever — on an unfixable environment
# that is pure disturbance. ThrottleInterval cannot help: the job exits 0, the
# spam is application-level. The silence must be too.
#
# Wire three call sites in the watchdog:
#   entry gate:    paused_any && { log "stand-down ($PAUSED_VIA)"; exit 0; }
#   ladder failed: info=$(record_exhausted); notify "auto cool-down ${info##*:}s"
#   real heal:     clear_exhausted
#
# Manual override subcommands for the watchdog's CLI:
#   cmd_pause [30m|2h|1d|SECONDS]   (omit duration = indefinite)
#   cmd_resume
#
# Configuration — set BEFORE sourcing, or accept defaults:
#   WATCHDOG_STATE_DIR   directory for state files. Default "${TMPDIR:-/tmp}/watchdog-cooldown".
#                        Point it at a durable per-watchdog dir (e.g. "$HOME/Library/Logs/<name>")
#                        when the cool-down must survive reboot; TMPDIR does not.
#   WATCHDOG_BACKOFFS    space-separated escalating tiers, seconds. Default "1800 7200 21600"
#                        (30min → 2h → 6h; last tier repeats).
#   WATCHDOG_STALE_SECONDS  counter older than this resets (post sleep/wake gap). Default 900.
#   WATCHDOG_LOG_FN      name of a log function called as: fn <level> <message...>.
#                        Default: no logging.

# shellcheck shell=bash

_WC_STATE_DIR="${WATCHDOG_STATE_DIR:-${TMPDIR:-/tmp}/watchdog-cooldown}"
_WC_BACKOFFS="${WATCHDOG_BACKOFFS:-1800 7200 21600}"
_WC_STALE="${WATCHDOG_STALE_SECONDS:-900}"
_WC_PAUSE_FILE="$_WC_STATE_DIR/pause"
_WC_AUTOPAUSE_FILE="$_WC_STATE_DIR/autopause"
_WC_EXHAUSTED_FILE="$_WC_STATE_DIR/exhausted.state"

_wc_log() {
    [ -n "${WATCHDOG_LOG_FN:-}" ] && "$WATCHDOG_LOG_FN" "$@" || true
}

_wc_ensure_dir() {
    [ -d "$_WC_STATE_DIR" ] || mkdir -p "$_WC_STATE_DIR"
}

# --- manual pause -------------------------------------------------------------

_wc_pause_remaining() {
    [ -f "$_WC_PAUSE_FILE" ] || return 1
    local until now
    until=$(cat "$_WC_PAUSE_FILE" 2>/dev/null || true)
    case "$until" in
        ''|*[!0-9]*) rm -f "$_WC_PAUSE_FILE"; return 1 ;;  # corrupt: treat as unpaused
    esac
    [ "$until" = "0" ] && return 0                         # indefinite
    now=$(date +%s)
    [ "$now" -lt "$until" ] && return 0
    rm -f "$_WC_PAUSE_FILE"                                # expired: auto-resume
    return 1
}

_wc_pause_desc() {
    local until
    until=$(cat "$_WC_PAUSE_FILE" 2>/dev/null || echo "?")
    if [ "$until" = "0" ]; then
        echo "indefinite"
    else
        echo "until $(date -r "$until" '+%Y-%m-%d %H:%M:%S')"
    fi
}

_wc_parse_duration() {
    local d="$1"
    case "$d" in
        *[!0-9mhd]*|'') return 1 ;;
        *m) echo $(( ${d%m} * 60 )) ;;
        *h) echo $(( ${d%h} * 3600 )) ;;
        *d) echo $(( ${d%d} * 86400 )) ;;
        *)  echo "$d" ;;  # bare number = seconds
    esac
}

cmd_pause() {
    _wc_ensure_dir
    local dur="${1:-}" until=0
    if [ -n "$dur" ]; then
        local secs
        if ! secs=$(_wc_parse_duration "$dur"); then
            echo "Invalid duration: '$dur' (use e.g. 30m, 2h, 1d, or bare seconds; omit for indefinite)" >&2
            return 2
        fi
        until=$(( $(date +%s) + secs ))
    fi
    echo "$until" > "$_WC_PAUSE_FILE"
    if [ "$until" = "0" ]; then
        echo "watchdog PAUSED indefinitely — resume with: cmd_resume"
        _wc_log WARN "Paused indefinitely by user"
    else
        echo "watchdog PAUSED until $(date -r "$until" '+%Y-%m-%d %H:%M:%S')"
        _wc_log WARN "Paused by user until epoch $until"
    fi
}

cmd_resume() {
    if [ -f "$_WC_PAUSE_FILE" ]; then
        rm -f "$_WC_PAUSE_FILE"
        echo "watchdog RESUMED"
        _wc_log INFO "Resumed by user"
    else
        echo "watchdog was not paused"
    fi
}

# --- automatic cool-down ------------------------------------------------------

_wc_autopause_remaining() {
    [ -f "$_WC_AUTOPAUSE_FILE" ] || return 1
    local until now
    until=$(cat "$_WC_AUTOPAUSE_FILE" 2>/dev/null || true)
    case "$until" in
        ''|*[!0-9]*) rm -f "$_WC_AUTOPAUSE_FILE"; return 1 ;;
    esac
    now=$(date +%s)
    [ "$now" -lt "$until" ] && return 0
    rm -f "$_WC_AUTOPAUSE_FILE"                            # expired: retry one round
    return 1
}

_wc_read_counter() {
    local file="$1"
    [ -f "$file" ] || { echo 0; return; }
    local c ts now
    c=$(cut -d' ' -f1 "$file" 2>/dev/null || true)
    ts=$(cut -d' ' -f2 "$file" 2>/dev/null || true)
    case "${c:-}" in ''|*[!0-9]*) echo 0; return ;; esac
    # Staleness is for "a crash/sleep gap broke the consecutive-failure chain".
    # The exhausted counter must NOT go stale: the cool-down wait between rounds
    # is by design longer than the stale window, and a stale-reset would lock the
    # backoff at tier 1 forever. Callers for that counter pass "nostale".
    if [ "${2:-}" != "nostale" ]; then
        case "${ts:-}" in ''|*[!0-9]*) echo 0; return ;; esac
        now=$(date +%s)
        [ $((now - ts)) -gt "$_WC_STALE" ] && { echo 0; return; }
    fi
    echo "$c"
}

_wc_write_counter() {
    _wc_ensure_dir
    echo "$1 $(date +%s)" > "$2"
}

# Single gate for every action path. Sets PAUSED_VIA for log/status messages.
paused_any() {
    if _wc_pause_remaining; then
        PAUSED_VIA="manual pause ($(_wc_pause_desc))"
        return 0
    fi
    if _wc_autopause_remaining; then
        PAUSED_VIA="auto cool-down (until $(date -r "$(cat "$_WC_AUTOPAUSE_FILE")" '+%Y-%m-%d %H:%M:%S'))"
        return 0
    fi
    return 1
}

# Call when the full remediation ladder has failed. Echoes "<round>:<tier-secs>".
record_exhausted() {
    local n secs until
    n=$(_wc_read_counter "$_WC_EXHAUSTED_FILE" nostale)
    n=$((n + 1))
    _wc_write_counter "$n" "$_WC_EXHAUSTED_FILE"
    # Tier select via cut (not bash arrays) so sourcing from zsh works too;
    # beyond the last tier, the last tier repeats.
    secs=$(echo "$_WC_BACKOFFS" | tr -s ' ' | cut -d' ' -f"$n")
    if [ -z "$secs" ]; then
        secs=$(echo "$_WC_BACKOFFS" | tr -s ' ' | awk '{print $NF}')
    fi
    until=$(( $(date +%s) + secs ))
    _wc_ensure_dir
    echo "$until" > "$_WC_AUTOPAUSE_FILE"
    _wc_log WARN "Heal exhausted round $n — auto cool-down $(( secs / 60 ))min, silent until $(date -r "$until" '+%H:%M:%S')"
    echo "$n:$secs"
}

# Call on any real heal. Clears the counter and the cool-down state.
clear_exhausted() {
    if [ "$(_wc_read_counter "$_WC_EXHAUSTED_FILE" nostale)" != "0" ] || [ -f "$_WC_AUTOPAUSE_FILE" ]; then
        _wc_log INFO "Real heal succeeded — clearing exhausted counter and cool-down"
    fi
    _wc_write_counter 0 "$_WC_EXHAUSTED_FILE"
    rm -f "$_WC_AUTOPAUSE_FILE"
}

# Status helper for the watchdog's `status` subcommand.
cooldown_status() {
    if paused_any; then
        echo "Stand-down: PAUSED — ${PAUSED_VIA}"
    else
        echo "Stand-down: active (not paused)"
    fi
    local n
    n=$(_wc_read_counter "$_WC_EXHAUSTED_FILE" nostale)
    [ "$n" != "0" ] && echo "Exhausted rounds: $n (each further failure extends the cool-down tier)"
    return 0   # healthy path must exit 0 — callers source this under set -e
}
