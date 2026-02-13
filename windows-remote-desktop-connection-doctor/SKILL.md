---
name: windows-remote-desktop-connection-doctor
description: Diagnose Windows App (Microsoft Remote Desktop / Azure Virtual Desktop / W365) connection quality issues on macOS. Analyze transport protocol selection (UDP Shortpath vs WebSocket), detect VPN/proxy interference with STUN/TURN negotiation, and parse Windows App logs for Shortpath failures. This skill should be used when VDI connections are slow, when transport shows WebSocket instead of UDP, when RDP Shortpath fails to establish, or when RTT is unexpectedly high.
allowed-tools: Read, Grep, Bash
---

# Windows Remote Desktop Connection Doctor

Diagnose and fix Windows App (AVD/WVD/W365) connection quality issues on macOS, with focus on transport protocol optimization.

## Background

Azure Virtual Desktop transport priority: **UDP Shortpath > TCP > WebSocket**. UDP Shortpath provides the best experience (lowest latency, supports UDP Multicast). When it fails, the client falls back to WebSocket over TCP 443 through the gateway, adding significant latency overhead.

## Diagnostic Workflow

### Step 1: Collect Connection Info

Ask the user to provide the Connection Info from Windows App (click the signal icon in the toolbar). Key fields to extract:

| Field | What It Tells |
|-------|--------------|
| Transport Protocol | Current transport: `UDP`, `UDP Multicast`, `WebSocket`, or `TCP` |
| Round-Trip Time (RTT) | End-to-end latency in ms |
| Available Bandwidth | Current bandwidth in Mbps |
| Gateway | The AVD gateway hostname and port |
| Service Region | Azure region code (e.g., SEAS = South East Asia) |

If Transport Protocol is `UDP` or `UDP Multicast`, the connection is optimal — no further diagnosis needed.

If Transport Protocol is `WebSocket` or `TCP`, proceed to Step 2.

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

### Step 3: Analyze Windows App Logs

This is the most critical step. Windows App logs contain transport negotiation details that no network-level test can reveal.

**Log location on macOS:**
```
~/Library/Containers/com.microsoft.rdc.macos/Data/Library/Logs/Windows App/
```

Files are named: `com.microsoft.rdc.macos_v<version>_<date>_<time>.log`

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

### Step 5: Verify Fix

After applying a fix, reconnect the VDI session and verify:

1. Check Connection Info — Transport Protocol should show `UDP` or `UDP Multicast`
2. RTT should drop significantly (e.g., from 165ms to 40-60ms)
3. Verify with lsof:
```bash
lsof -i UDP -n -P 2>/dev/null | grep -i "Windows"
# Should show UDP connections if Shortpath is active
```

## References

- [references/windows_app_log_analysis.md](references/windows_app_log_analysis.md) — Detailed log parsing patterns, error signatures, and comparison methodology
- [references/avd_transport_protocols.md](references/avd_transport_protocols.md) — How AVD transport selection works, STUN/TURN/ICE overview, Shortpath architecture
