#!/bin/bash
# vpn-heal.sh — checks the VPN every cycle and reconnects it when down.
#
# To stop this job:  launchctl unload ~/Library/LaunchAgents/com.example.vpn-heal.plist
# To start again:    launchctl load ~/Library/LaunchAgents/com.example.vpn-heal.plist
set -euo pipefail

notify() { osascript -e "display notification \"$1\" with title \"vpn-heal\""; }

if curl -fsS --max-time 5 https://www.googleapis.com/generate_204 >/dev/null 2>&1; then
    exit 0
fi

# Network is down — reconnect the VPN app and tell me every time.
open "examplevpn://connect"
notify "VPN was down — reconnect fired"
