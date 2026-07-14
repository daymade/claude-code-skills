# Direct PC Connection and Identity Diagnostics

This reference covers failure modes that affect **direct PC connections** in the new Windows App (macOS 11.x), especially when the app is stuck at a progress dialog such as **"Configuring remote PC..."**. Many of these patterns also apply to AVD/WVD, but the diagnostic approach differs because the direct-PC path has no Connection Info panel, no gateway health check, and no UDP Shortpath to optimize.

## When to use this reference

- The user is connecting to a personal workstation or a local/LAN PC, not an AVD/WVD cloud desktop.
- Windows App gets stuck at "Connecting..." / "Configuring remote PC..." indefinitely.
- The connection worked before, then stopped after a reboot, an app update, or a workplace change.
- You have already ruled out obvious network issues (ping works, port 3389 reachable, RDP protocol probe succeeds).

## Contents

- Distinguish direct PC from AVD/WVD
- Independent server health check (RDP protocol probe + TLS)
- OneAuth / Microsoft account poisoning
- Stuck dialog vs. live session on another display
- Windows-side reboot and update correlation
- Per-session GUID log analysis and timestamps

## Distinguish Direct PC from AVD/WVD

Direct PC connections in the Windows App use the same client codebase as AVD, but the orchestration path is different:

| | AVD/WVD | Direct PC |
|---|---|---|
| Connection Info panel | Yes — shows transport, RTT, gateway | **No** |
| Transport optimization | UDP Shortpath > TCP > WebSocket | Plain RDP over TCP 3389 (or TLS 3389) |
| Authentication | Cloud identity + gateway token | Local credentials or cached Microsoft account |
| Progress dialog | Usually brief | Can stay at "Configuring remote PC..." if auth stalls |

**Implication:** For direct PC, the AVD Step 1 (Connection Info panel) does not apply. Start with the protocol probe and log analysis instead.

## Independent Server Health Check

Before assuming the Windows App client is the problem, prove the server-side RDP stack is alive. The bundled script `scripts/probe_rdp_server.py` does this with zero credentials:

```bash
python3 scripts/probe_rdp_server.py <host> [port]
```

What it does:
1. Opens a TCP socket to port 3389 (or the port you specify).
2. Sends an X.224 Connection Request with an RDP_NEG_REQ payload.
3. Reads the RDP_NEG_RSP and decodes the selected security protocol (usually 0x00000002 = CredSSP/NLA).
4. Upgrades the same socket to TLS to prove the TLS layer works.

Expected output for a healthy server:

```
TPKT length: 19, X.224 type: 0x0e, RDP_NEG type: 0x02
Selected protocol: 2 (0x00000002)
Negotiated security: CredSSP/NLA (Hybrid)
TLS handshake OK: TLSv1.3, cipher=...
RDP server <host>:3389 is reachable and healthy (RDP + TLS).
```

**How to interpret results:**

| Result | Meaning |
|---|---|
| TCP connect failed | Server is off, unreachable, port 3389 blocked, or routing problem. |
| RDP_NEG_FAILURE | Server is reachable but rejects the RDP negotiation (rare). |
| TLS handshake failed | Server has a TLS problem or the probe is being intercepted. |
| RDP + TLS OK | Server is healthy. The problem is client-side (auth, app state, proxy). |

> **Note on TLS verification:** The probe intentionally disables certificate verification so it can confirm the RDP stack accepts TLS even with self-signed or domain-issued certificates. It does not authenticate the server. For a full certificate audit, use a separate TLS inspection tool.

## OneAuth / Microsoft Account Poisoning

The new Windows App uses a shared identity stack (OneAuth/MSAL) for **all** connection types, including direct PC. If a Microsoft work or school account is signed into the app and that account becomes invalid (expired password, tenant disabled, user left the organization), the auth orchestration can poison **even direct PC connections** that do not use that account. The app keeps trying to refresh the expired token and shows an interactive sign-in prompt, but the user may cancel it or it may hide behind the progress dialog.

### Log signatures

Look for these patterns in the Windows App log (case-insensitive):

| Pattern | What it means |
|---|---|
| `OneAuthError_InteractionRequired` | The cached token cannot be refreshed silently. |
| `No valid refresh tokens available in the cache` | No cached credentials can satisfy the request. |
| `AcquireTokenInteractively` | The app is trying to pop a browser sign-in window. |
| `credential completion has been canceled` | The interactive sign-in was canceled. |
| `User canceled sign in` | User dismissed the prompt. |
| `GATEWAY(ERR): CWVDTransport::OnOrchestrationHttpError error: UserCancelled(8)` | Auth orchestration failed because the sign-in was canceled. |
| `Fail OnDisconnected call` | The connection attempt ended without establishing a session. |
| `sourceArea: Browser` | The sign-in prompt came from an embedded browser. |

**Note:** A direct-PC connection may show "GATEWAY" errors even though it does not use the AVD gateway. The Windows App client reuses the same orchestration code path.

### Fix

1. Open **Windows App → Settings → Accounts** (or the account/identity panel).
2. Sign out the stale or expired Microsoft work/school account.
3. If the account is no longer needed, remove it entirely.
4. **Fully quit** the app (Cmd+Q, not just close the window) and relaunch it.
5. Retry the direct PC connection.

**Why this works:** Removing the invalid account stops the auth orchestration from trying to refresh a token it cannot refresh, so the direct PC connection can proceed with local credentials or device-card authentication.

### Distinguish from server-side issues

If the RDP protocol probe succeeds but the log shows the OneAuth chain above, the problem is **client-side identity**, not the remote PC. This is a crucial falsification step.

## Stuck Dialog vs. Live Session on Another Display

A "Configuring remote PC..." dialog can mean two very different things:

1. **The connection is actually dead.** The client is stuck waiting for auth or network. The log shows the OneAuth chain above, or repeated `CMSTATE_DROPPED` reconnect attempts.
2. **The session is connected but hidden.** The session window is on another Space or another display, and a leftover dialog remains on the main screen.

### Check for a live session window

Enumerate all Windows App windows across all Spaces and displays:

```bash
swift -e '
import Cocoa
let options = CGWindowListOption(arrayLiteral: .optionAll, .excludeDesktopElements)
let windows = CGWindowListCopyWindowInfo(options, kCGNullWindowID) as? [[String: Any]] ?? []
for w in windows {
    guard let owner = w[kCGWindowOwnerName as String] as? String,
          owner.lowercased().contains("windows") else { continue }
    let bounds = w[kCGWindowBounds as String] as? [String: CGFloat] ?? [:]
    let title = w[kCGWindowName as String] as? String ?? ""
    print("\(owner) | \(title) | bounds=\(bounds)")
}
'
```

A window titled with the PC name or IP (e.g., `<pc-name>`) that is large and positioned on a negative Y coordinate (e.g., `Y = -1000`) usually means the session is on an external display above the main screen. If such a window exists, the session is alive and the dialog is just stale UI.

### Log evidence of a live session

When a session is actually connected, the log shows input events such as:

```
IHAddMouseEventToPDU
IHAddMouseWheelEventToPDU
IHAddKeyboardEventToPDU
```

Mouse wheel or pointer activity after a "connected" entry means the session is healthy and receiving input. The absence of these events combined with repeated `CMSTATE_DROPPED` or auth errors means the session is not connected.

## Windows-Side Reboot and Update Correlation

When a connection drops suddenly during a working session, the remote Windows machine may have rebooted. Windows Update can restart the machine automatically, killing the RDP session. The Windows App client then shows reconnect attempts, but if the machine is still booting or if auth state is stale, the reconnect may appear as a stuck progress dialog.

### Check LastBootUpTime

If you have ANY administrative path to the Windows PC (SSH, WSL, RMM, physical console), query the last boot time:

```powershell
Get-CimInstance Win32_OperatingSystem | Select-Object LastBootUpTime
```

### Check shutdown events

Event ID 1074 records a planned shutdown/restart, including the initiator and reason:

```powershell
Get-WinEvent -FilterHashtable @{LogName='System'; ID=1074} -MaxEvents 5 |
  Format-List TimeCreated, Id, LevelDisplayName, Message
```

Key fields in a 1074 event:

| Field | Meaning |
|---|---|
| `process: ... MoNotificationUx.exe` | Windows Update orchestrator initiated the restart. |
| `Reason Code: 0x80020010` | Planned operating system service update. |
| `Shutdown Type: restart` | Confirms a reboot, not a shutdown. |

### Other useful events

| Event ID | Meaning |
|---|---|
| 6006 | The Event Log service stopped (clean shutdown). |
| 6008 | Unexpected shutdown. |
| 41 | Kernel-Power critical shutdown (hard power loss or crash). |
| 109 | Kernel-Boot: operating system started. |

### Running from WSL via Tailscale/SSH

If the Mac can reach the Windows PC via Tailscale or SSH, but PowerShell quoting is painful through WSL, encode the command as UTF-16LE base64 and pass it with `-EncodedCommand`:

```bash
CMD='Get-CimInstance Win32_OperatingSystem | Select-Object LastBootUpTime | Format-List'
B64=$(python3 -c "import base64; print(base64.b64encode(\"$CMD\".encode('utf-16-le')).decode())")
ssh user@windows-host "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -EncodedCommand $B64"
```

Use the full Windows path to `powershell.exe` inside WSL; a bare `powershell.exe` may not be found.

### Timezone alignment

Windows App logs on macOS are written in **UTC**. Windows Event logs are in the local time of the Windows machine. Align them by converting both to UTC or to the user's local timezone before building a timeline.

Example: if the user is in China Standard Time (CST, UTC+8) and Windows is set to CST:
- A Windows App log entry at `2026-07-14 04:38:33Z` is `12:38:33 CST`.
- A Windows Event 1074 at `12:38:03` CST is the same real time.

## Per-Session GUID Log Analysis

Each connection attempt in the Windows App log gets a unique activity/session GUID in braces, such as `{xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx}`. The null GUID `{00000000-0000-0000-0000-000000000000}` indicates background/system events.

### Aggregate a session's lifecycle

To understand what happened during one attempt, group all lines for one GUID and sort by timestamp:

```bash
LOG=~/Library/Containers/com.microsoft.rdc.macos/Data/Library/Logs/Windows\ App/com.microsoft.rdc.macos_v*.log
GUID="{a1b2c3d4-...}"
python3 - <<'PY'
import re, sys
from pathlib import Path
log_path = Path("/Users/$USER/Library/Containers/com.microsoft.rdc.macos/Data/Library/Logs/Windows App")
guid = "{...}"
noise = re.compile(r"BasicStateManagement|DynVC|dynvcstat|asynctransport|FlushTracesInternal")
for f in sorted(log_path.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True):
    for line in f.open():
        if guid not in line: continue
        if noise.search(line): continue
        print(line.rstrip())
PY
```

### What to look for in a failed session

| Sequence | Interpretation |
|---|---|
| `ConnectionStateConnecting` → `No data of type 0xc09` | Server answered the MCS Connect — this is **non-fatal** and proves the TCP path works. |
| `RDP_WAN: Client connMonitor goto CMSTATE_DROPPED` | Connection monitor gave up after missed heartbeats (default ~12). |
| `Channel::StartWrite failed` / `GetBuffer failed` | Transport is dead; the client is trying to write to a closed socket. |
| `OneAuthError_InteractionRequired` → `User canceled sign in` | Auth orchestration stalled. |
| `GATEWAY(ERR): ... UserCancelled(8)` → `Fail OnDisconnected call` | Connection failed because the user canceled the interactive sign-in. |

### "No data of type 0xc09" is not fatal

```
rdpstack.cpp(...): ParseUserData: No data of type 0xc09
```

This line appears in both successful and failed sessions. It means the server did not include an optional user data block in the MCS Connect Response, but the client continued. Its presence is actually evidence that the server answered and the RDP negotiation reached MCS Connect.

## Direct-PC Diagnostic Summary

When a direct PC connection is stuck at "Configuring remote PC...":

1. **Prove the server is alive:** run `scripts/probe_rdp_server.py <host>`.
   - If it fails, the problem is network, firewall, or the PC is off.
   - If it succeeds, the problem is client-side.
2. **Check for a live session:** use `swift CGWindowList` or look for mouse/keyboard input events in the log.
3. **Search for OneAuth/MSAL errors:** grep for `OneAuthError_InteractionRequired`, `No valid refresh tokens`, `credential completion has been canceled`, `User cancelled`, `UserCancelled(8)`.
4. **If found, fix identity:** sign out or remove the stale Microsoft account in Windows App, Cmd+Q quit, relaunch.
5. **Correlate with Windows-side reboots:** check `LastBootUpTime` and Event ID 1074 to see if Windows Update restarted the PC during the original session.
6. **Build a timeline:** align Windows App log timestamps (UTC) with Windows events (local time) per the user's timezone.
