#!/bin/bash
# new-launchagent.sh — idempotent LaunchAgent/LaunchDaemon installer.
#
# Usage:
#   new-launchagent.sh <label> <program-abs-path> <interval-seconds> [--system] [--run-at-load] [-- arg2 ...]
#
# Example:
#   new-launchagent.sh com.example.thermal-watch ~/scripts/thermal-watch.sh 300 --run-at-load
#   new-launchagent.sh com.example.disk-guard /usr/local/bin/disk-guard.sh 600 --system
#
# Idempotent: safe to re-run — if the label is already loaded it is booted out
# first, so editing the generated plist and re-running converges state.
set -euo pipefail

usage() { sed -n '2,10p' "$0"; exit 2; }

[ $# -ge 3 ] || usage
LABEL="$1"; PROGRAM="$2"; INTERVAL="$3"; shift 3

SYSTEM=false
RUNATLOAD=false
EXTRA_ARGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --system)     SYSTEM=true ;;
        --run-at-load) RUNATLOAD=true ;;
        --)           shift; EXTRA_ARGS=("$@"); break ;;
        *)            echo "Unknown flag: $1" >&2; usage ;;
    esac
    shift
done

# --- validation (fail fast with a named reason, never a half-written plist) ---
case "$LABEL" in
    *[!a-zA-Z0-9.-]*|.*|*.|*..*)
        echo "Label must be reverse-DNS like com.example.name (no leading/trailing/double dots), got: $LABEL" >&2; exit 2 ;;
    *.*) ;;  # must contain at least one dot
    *) echo "Label must be reverse-DNS like com.example.name, got: $LABEL" >&2; exit 2 ;;
esac
case "$INTERVAL" in
    *[!0-9]*|'') echo "Interval must be integer seconds, got: $INTERVAL" >&2; exit 2 ;;
esac
[ "$INTERVAL" -ge 30 ] || { echo "Interval <30s is almost certainly a mistake (crash-loop territory)" >&2; exit 2; }
[ -f "$PROGRAM" ] || { echo "Program not found: $PROGRAM" >&2; exit 2; }
[ -x "$PROGRAM" ] || { echo "Program not executable (chmod +x first): $PROGRAM" >&2; exit 2; }
case "$PROGRAM" in
    /*) ;;
    *) echo "Program must be an absolute path (launchd has no PATH), got: $PROGRAM" >&2; exit 2 ;;
esac

if $SYSTEM; then
    PLIST_DIR="/Library/LaunchDaemons"
    DOMAIN="system"
    SUDO="sudo"
    LOG_DIR="/Library/Logs"   # a root daemon must not log into one user's home
else
    PLIST_DIR="$HOME/Library/LaunchAgents"
    DOMAIN="gui/$(id -u)"
    SUDO=""
    LOG_DIR="$HOME/Library/Logs"
fi
PLIST="$PLIST_DIR/$LABEL.plist"
LOG_OUT="$LOG_DIR/$LABEL.out.log"
LOG_ERR="$LOG_DIR/$LABEL.err.log"

# --- bootout if already loaded (converge, never double-install) ---------------
if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
    echo "Already loaded — booting out for reload"
    $SUDO launchctl bootout "$DOMAIN/$LABEL"
fi

# --- write plist ---------------------------------------------------------------
$SUDO mkdir -p "$PLIST_DIR" "$LOG_DIR"

args_xml="    <string>$PROGRAM</string>"
for a in ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}; do
    args_xml="$args_xml
    <string>$a</string>"
done

runatload_xml=""
$RUNATLOAD && runatload_xml="  <key>RunAtLoad</key>
  <true/>
"

tmp_plist="$(mktemp -t "$LABEL")"
cat > "$tmp_plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
$args_xml
  </array>
  <key>StartInterval</key>
  <integer>$INTERVAL</integer>
$runatload_xml  <key>StandardOutPath</key>
  <string>$LOG_OUT</string>
  <key>StandardErrorPath</key>
  <string>$LOG_ERR</string>
  <key>ThrottleInterval</key>
  <integer>10</integer>
</dict>
</plist>
EOF

plutil -lint "$tmp_plist" >/dev/null || { echo "Generated plist failed plutil -lint" >&2; rm -f "$tmp_plist"; exit 1; }
if $SYSTEM; then
    # launchd rejects a LaunchDaemon plist not owned root:wheel ("dubious
    # ownership", Bootstrap failed: 5) — mktemp files are mode 600, user-owned
    sudo chown root:wheel "$tmp_plist"
    sudo chmod 644 "$tmp_plist"
fi
$SUDO mv "$tmp_plist" "$PLIST"

# --- bootstrap and verify -------------------------------------------------------
$SUDO launchctl bootstrap "$DOMAIN" "$PLIST"

if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
    echo "OK: $LABEL loaded into $DOMAIN"
    echo "  plist:  $PLIST"
    echo "  logs:   $LOG_OUT / $LOG_ERR"
    echo "  verify: launchctl list | grep $LABEL"
    echo "  run now: launchctl kickstart -k $DOMAIN/$LABEL"
    echo "  stop:    launchctl bootout $DOMAIN/$LABEL"
else
    echo "FAIL: bootstrap reported success but label not found in $DOMAIN" >&2
    exit 1
fi
