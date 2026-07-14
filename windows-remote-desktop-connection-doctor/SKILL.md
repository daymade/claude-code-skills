---
name: windows-remote-desktop-connection-doctor
description: >-
  Diagnose Windows App (Microsoft Remote Desktop / Azure Virtual Desktop / W365 / direct PC) connection issues on macOS. Analyze transport protocol selection (UDP Shortpath vs WebSocket), detect VPN/proxy interference, parse Windows App logs for Shortpath failures, and resolve stuck "Configuring remote PC..." dialogs caused by expired Microsoft accounts, server reboots, or client-side auth poisoning. Use when VDI connections are slow or stuck, when direct PC connections fail to connect, when transport shows WebSocket instead of UDP, when RDP Shortpath fails, or when Windows App is frozen at a progress dialog.
allowed-tools: Read, Grep, Bash
---

# Windows Remote Desktop Connection Doctor

Diagnose and fix Windows App (Microsoft Remote Desktop / AVD / WVD / W365 / direct PC) connection issues on macOS, with focus on transport protocol optimization and root-cause falsification.

> **Methodology base:** the general evidence-driven diagnosis discipline lives in the **debugging-network-issues** skill. This skill is the Windows-App / AVD transport *domain* layer — it leans toward connection-quality optimization more than root-cause falsification, so the methodology overlap is lighter.

## Background

**Azure Virtual Desktop** transport priority: **UDP Shortpath > TCP > WebSocket**. UDP Shortpath provides the best experience (lowest latency, supports UDP Multicast). When it fails, the client falls back to WebSocket over TCP 443 through the gateway, adding significant latency overhead.

**Direct PC connections** use plain RDP over TCP 3389 (usually TLS-wrapped). They have no Connection Info panel, no gateway reachability tests, and no transport optimization step. For direct PC, the dominant failure modes are:

1. The remote PC is off or unreachable (network/firewall).
2. The Windows App client has a stale or expired Microsoft work/school account that poisons the auth orchestration, leaving the connection stuck at "Configuring remote PC...".
3. The remote PC rebooted (often Windows Update), and the client cannot recover cleanly.

This skill handles both scenarios.

## Diagnostic Workflow

### Step 1: Determine the Connection Type and Symptom

Before collecting evidence, identify which scenario you are diagnosing:

| Scenario | Key Characteristic | Primary Evidence Source |
|---|---|---|
| **AVD/WVD/W365** | User connects to a cloud desktop through a workspace/gateway | Connection Info panel, gateway health checks, UDP Shortpath logs |
| **Direct PC** | User connects to a named PC by hostname or IP (e.g., a home workstation) | RDP protocol probe, Windows App log auth chain, Windows-side reboot events |

For **AVD/WVD/W365**, ask the user to provide the Connection Info from Windows App (click the signal icon in the toolbar). Key fields to extract:

| Field | What It Tells |
|-------|--------------|
| Transport Protocol | Current transport: `UDP`, `UDP Multicast`, `WebSocket`, or `TCP` |
| Round-Trip Time (RTT) | End-to-end latency in ms |
| Available Bandwidth | Current bandwidth in Mbps |
| Gateway | The AVD gateway hostname and port |
| Service Region | Azure region code (e.g., SEAS = South East Asia) |

If Transport Protocol is `UDP` or `UDP Multicast`, the connection is optimal — no further diagnosis needed.

If Transport Protocol is `WebSocket` or `TCP`, proceed to Step 2.

For **Direct PC**, the Connection Info panel does not exist. Instead, first run the **RDP protocol probe** in Step 2E to prove the server is reachable, then analyze the Windows App log for auth poisoning or reconnect failures. If the progress dialog is stuck at "Configuring remote PC...", strongly suspect client-side identity issues (see Category E).

### Step 2: Collect Network Evidence

Gather evidence in parallel — do NOT make assumptions. Run the following checks simultaneously:

#### 2A: Network Interfaces and Routing

```bash
ifconfig | grep -E "^[a-z]|inet |utun"
netstat -rn | head -40
scutil --proxy
```

Look for:
- **utun interfaces**: Identify VPN/proxy TUN tunnels (ShadowRocket, Clash, Tailscale)
- **Default route priority**: Which interface handles default traffic
- **Split routing**: `0/1 + 128.0/1 → utun` pattern means a VPN captures all traffic
- **System proxy**: HTTP/HTTPS proxy enabled on localhost ports

#### 2B: RDP Client Process and Connections

```bash
# Find the Windows App process (NOT "msrdc" — the new client uses "Windows" as process name)
ps aux | grep -i -E 'msrdc|Windows' | grep -v grep
# Check its network connections
lsof -i -n -P 2>/dev/null | grep -i "Windows" | head -20
# Check for UDP connections
lsof -i UDP -n -P 2>/dev/null | head -30
```

Key evidence to look for:
- **Source IP `198.18.0.x`**: Traffic is being routed through ShadowRocket/proxy TUN tunnel
- **No UDP connections from Windows process**: Shortpath not established
- **Only TCP 443**: Fallback to gateway WebSocket transport

#### 2C: VPN/Proxy State

```bash
# Environment proxy variables
env | grep -i proxy
# System proxy via scutil
scutil --proxy
# ShadowRocket config API (if accessible on local network)
NO_PROXY="<local-ip>" curl -s --connect-timeout 5 "http://<local-ip>:8080/api/read"
```

#### 2D: Tailscale State (if running)

```bash
tailscale status
tailscale netcheck
```

The `netcheck` output reveals NAT type (`MappingVariesByDestIP`), UDP support, and public IP — valuable even when Tailscale is not the problem.

#### 2E: Independent RDP Server Health Check (Direct PC)

This step is critical for **direct PC connections** and useful for AVD/WVD/W365 as a falsification test: it proves the server-side RDP stack is alive without relying on the Windows App client or any credentials.

Use the bundled probe script:

```bash
python3 scripts/probe_rdp_server.py <host> [port]
```

Example:

```bash
python3 scripts/probe_rdp_server.py my-pc.local 3389
```

A successful probe reports `RDP server <host>:<port> is reachable and healthy (RDP + TLS).` and means the problem is **client-side** (auth, app state, proxy, or identity). A failed probe means the problem is **server-side or network** (PC off, firewall, port unreachable, TLS interception).

See `references/direct_pc_and_auth_diagnostics.md` for detailed interpretation of probe results.

### Step 3: Analyze Windows App Logs

This is the most critical step. Windows App logs contain transport negotiation details that no network-level test can reveal.

**Log location on macOS:**
```
~/Library/Containers/com.microsoft.rdc.macos/Data/Library/Logs/Windows App/
```

Files are named: `com.microsoft.rdc.macos_v<version>_<date>_<time>.log`

**Important:** Windows App log timestamps are **UTC**. The user's clock and Windows Event logs are usually local time. Convert all timestamps to a single timezone before building a timeline.

**Per-session tracking:** each connection attempt gets a unique activity GUID in braces. Aggregate events by GUID to understand the lifecycle of one attempt. See [references/windows_app_log_analysis.md](references/windows_app_log_analysis.md) for the GUID aggregation technique and [references/direct_pc_and_auth_diagnostics.md](references/direct_pc_and_auth_diagnostics.md) for the direct-PC failure signatures.

See [references/windows_app_log_analysis.md](references/windows_app_log_analysis.md) for detailed log parsing guidance.

#### Quick Log Search

```bash
LOG_DIR=~/Library/Containers/com.microsoft.rdc.macos/Data/Library/Logs/Windows\ App
# Find the most recent log
LATEST_LOG=$(ls -t "$LOG_DIR"/*.log 2>/dev/null | head -1)

# Search for transport-critical entries (filter out noise)
grep -i -E "STUN|TURN|VPN|Routed|Shortpath|FetchClient|clientoption|GATEWAY.*ERR|Certificate.*valid|InternetConnectivity|Passed URL" "$LATEST_LOG" | grep -v "BasicStateManagement\|DynVC\|dynvcstat\|asynctransport"
```

#### Key Log Patterns

| Log Pattern | Meaning |
|-------------|---------|
| `Passed: InternetConnectivity` | Health check completed successfully |
| `TCP/IP Traffic Routed Through VPN: No/Yes` | Client detected VPN routing for TCP |
| `STUN/TURN Traffic Routed Through VPN: Yes` | Client detected VPN routing for STUN/TURN |
| `Passed URL: https://...wvd.microsoft.com/ Response Time: Nms` | Gateway reachability confirmed |
| `FetchClientOptions exception: Request timed out` | **Critical**: Client cannot get transport options from gateway |
| `Certificate validation failed` | TLS interception or DNS poisoning detected |
| `OnRDWebRTCRedirectorRpc rtcSession not handled` | WebRTC session setup not handled by client |
| `OneAuthError_InteractionRequired` | A cached Microsoft account token cannot be refreshed silently |
| `No valid refresh tokens available in the cache` | No usable cached credentials for the auth request |
| `credential completion has been canceled` | The interactive sign-in prompt was canceled |
| `GATEWAY(ERR): ... UserCancelled(8)` | Auth orchestration failed because sign-in was canceled |
| `RDP_WAN: Client connMonitor goto CMSTATE_DROPPED` | Connection monitor detected a dropped session |
| `Channel::StartWrite failed` / `GetBuffer failed` | Transport is dead; client is writing to a closed socket |
| `ParseUserData: No data of type 0xc09` | **Non-fatal** — server answered MCS Connect; proves TCP path works |
| `IHAddMouseEventToPDU` / `IHAddMouseWheelEventToPDU` | Session is alive and receiving input |

#### Compare Working vs Broken Logs

When possible, compare a log from when the connection worked (UDP) with the current log:

```bash
# Compare startup health check blocks
for f in "$LOG_DIR"/*.log; do
  echo "=== $(basename "$f") ==="
  grep -E "InternetConnectivity|Routed Through VPN|Passed URL|FetchClient" "$f" | head -10
  echo ""
done
```

A working log will contain the full health check block (InternetConnectivity, VPN routing detection, gateway URL tests). A broken log may show these entries missing entirely, or show certificate/timeout errors instead.

### Step 4: Determine Root Cause

Based on collected evidence, identify the root cause category:

#### Category A: VPN/Proxy Interference

**Evidence**: Windows App source IP is `198.18.0.x`, STUN/TURN routed through VPN, no UDP connections.

**Fix**: Add DIRECT rules for AVD traffic in the proxy tool:
```
DOMAIN-SUFFIX,wvd.microsoft.com,DIRECT
DOMAIN-SUFFIX,microsoft.com,DIRECT
IP-CIDR,13.104.0.0/14,DIRECT
```

**Verify**: Temporarily disable VPN/proxy, reconnect VDI, check if transport changes to UDP.

#### Category B: ISP/Network UDP Restriction

**Evidence**: Even with all VPNs off, still WebSocket. No UDP connections. `FetchClientOptions` timeout.

**Verify**:
```bash
# Test STUN connectivity to a known server
python3 -c "
import socket, struct, os
header = struct.pack('!HHI', 0x0001, 0, 0x2112A442) + os.urandom(12)
for srv in [('stun.l.google.com', 19302), ('stun1.l.google.com', 19302)]:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(3)
        s.sendto(header, srv)
        data, addr = s.recvfrom(1024)
        print(f'STUN from {srv[0]}: OK')
        s.close(); break
    except: print(f'STUN from {srv[0]}: FAILED'); s.close()
"
```

**Fix options**:
- Try mobile hotspot (isolate home network from ISP)
- Check router NAT type (Full Cone NAT preferred)
- Enable UPnP on router
- Try IPv6 if available
- Contact ISP about UDP restrictions

#### Category C: Client Health Check Failure

**Evidence**: Log shows certificate validation errors at startup, health check block (InternetConnectivity, STUN/TURN detection) missing from log, `FetchClientOptions` timeout.

This means the client cannot complete its diagnostic/capability discovery, preventing Shortpath negotiation.

**Possible causes**:
- ISP HTTPS interception/MITM (especially in China)
- DNS poisoning returning incorrect IPs for Microsoft diagnostic endpoints
- Firewall blocking Microsoft telemetry endpoints

**Fix options**:
- Change DNS to 8.8.8.8 or 1.1.1.1 (bypass ISP DNS)
- Route Microsoft traffic through a clean proxy
- Check if ISP injects certificates

#### Category D: Server-Side Shortpath Not Enabled

**Evidence**: Log shows no STUN/TURN or Shortpath related entries at all (not even detection), but health checks pass and no errors.

This means the AVD host pool does not have RDP Shortpath enabled. This requires admin action on the Azure portal.

#### Category E: Client Identity / Expired Microsoft Account Poisoning (Direct PC and AVD)

**Evidence**: The RDP protocol probe succeeds (server is healthy), but the Windows App log shows the OneAuth/MSAL chain:
- `OneAuthError_InteractionRequired`
- `No valid refresh tokens available in the cache`
- `AcquireTokenInteractively`
- `credential completion has been canceled`
- `User canceled sign in`
- `GATEWAY(ERR): CWVDTransport::OnOrchestrationHttpError error: UserCancelled(8)`
- `Fail OnDisconnected call`

The progress dialog may stay at "Configuring remote PC..." because the app is waiting for an interactive sign-in prompt that is hidden or canceled. This can affect **direct PC connections** even when the expired account is unrelated to that PC, because the Windows App client shares the same auth orchestration across all connection types.

**Fix**: Open Windows App → Settings → Accounts, sign out or remove the stale Microsoft work/school account, then fully quit (Cmd+Q) and relaunch the app. Retry the connection.

See `references/direct_pc_and_auth_diagnostics.md` for the full signature set and troubleshooting steps.

#### Category F: Server-Side Reboot / Windows Update

**Evidence**: A previously working session dropped suddenly, followed by reconnect failures. The Windows App log shows `CMSTATE_DROPPED` and possibly `Channel::StartWrite failed`. The Windows PC's `LastBootUpTime` is close to the drop time, and Event ID 1074 shows `MoNotificationUx.exe` (Windows Update orchestrator) or another planned restart reason.

**Fix**: Wait for the PC to finish booting, then reconnect. To prevent recurrence, set active hours / disable automatic restart during active hours in Windows Update settings, or schedule reboots when the user is not using the machine.

If you have admin access, use `Get-CimInstance Win32_OperatingSystem` for `LastBootUpTime` and `Get-WinEvent` for Event ID 1074. See `references/direct_pc_and_auth_diagnostics.md` for the WSL/SSH encoded-command technique.

### Step 5: Verify Fix

After applying a fix, reconnect and verify the appropriate symptoms:

**For AVD/WVD/W365:**
1. Check Connection Info — Transport Protocol should show `UDP` or `UDP Multicast`.
2. RTT should drop significantly (e.g., from 165ms to 40-60ms).
3. Verify with lsof:
```bash
lsof -i UDP -n -P 2>/dev/null | grep -i "Windows"
# Should show UDP connections if Shortpath is active
```

**For Direct PC:**
1. The progress dialog should disappear and the session window should appear.
2. The Windows App log for the new session should show mouse/keyboard input events (`IHAddMouseEventToPDU`, `IHAddKeyboardEventToPDU`) and no `UserCancelled(8)` errors.
3. If the issue was an expired Microsoft account, confirm that only valid accounts remain in Windows App → Settings → Accounts.

**For server reboots:**
1. Verify the PC is reachable again with `ping` and `scripts/probe_rdp_server.py`.
2. Confirm `LastBootUpTime` is recent and matches the outage window.

## References

- [references/windows_app_log_analysis.md](references/windows_app_log_analysis.md) — Detailed log parsing patterns, error signatures, GUID lifecycle analysis, and comparison methodology
- [references/avd_transport_protocols.md](references/avd_transport_protocols.md) — How AVD transport selection works, STUN/TURN/ICE overview, Shortpath architecture
- [references/direct_pc_and_auth_diagnostics.md](references/direct_pc_and_auth_diagnostics.md) — Direct PC connection failures, expired Microsoft account poisoning, RDP protocol probe usage, Windows-side reboot correlation, stuck-dialog vs. live-session discrimination
- [scripts/probe_rdp_server.py](scripts/probe_rdp_server.py) — Standalone RDP protocol + TLS health probe
