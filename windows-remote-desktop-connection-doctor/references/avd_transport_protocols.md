# AVD Transport Protocol Reference

How Azure Virtual Desktop selects transport protocols and how RDP Shortpath works.

## Contents

- Transport protocol hierarchy
- RDP Shortpath architecture
- STUN/TURN/ICE overview
- Why Shortpath fails
- Network requirements
- Common interference patterns

## Transport Protocol Hierarchy

Azure Virtual Desktop clients attempt transports in this order:

1. **UDP Shortpath** (best) — Direct UDP connection via ICE/STUN/TURN
2. **TCP** — Direct TCP connection to session host
3. **WebSocket** — WebSocket over TCP 443 through the AVD gateway (worst)

The client always establishes a WebSocket connection to the gateway first (for control plane). Then it attempts to upgrade to UDP Shortpath. If Shortpath negotiation fails, the session data stays on the WebSocket channel.

## RDP Shortpath Architecture

### For Public Networks (most common for remote workers)

RDP Shortpath for public networks uses ICE, STUN, and TURN protocols to establish a direct UDP connection between client and session host:

1. Client connects to AVD gateway via WebSocket (TCP 443)
2. Through this control channel, ICE negotiation begins
3. Client and server gather ICE candidates using STUN
4. They exchange candidates and attempt connectivity checks
5. If a direct UDP path exists, Shortpath is established
6. If direct fails but TURN relay is available, traffic relays through TURN
7. If all UDP attempts fail, session stays on WebSocket

### For Managed Networks (corporate LAN)

When client and session host are on the same network, Shortpath uses direct UDP without STUN/TURN. This is the simplest mode and rarely fails.

## STUN/TURN/ICE Overview

### STUN (Session Traversal Utilities for NAT)

STUN discovers the client's public IP and port as seen from outside the NAT. The client sends a STUN Binding Request to a STUN server, which replies with the client's observed address.

**Key port**: UDP 3478

**NAT types that affect STUN:**
- **Endpoint-Independent Mapping (EIM)**: Best — same public port regardless of destination. STUN works reliably.
- **Address-Dependent Mapping**: Moderate — different public port per destination IP. STUN may work with help from TURN.
- **Address-and-Port-Dependent (Symmetric NAT)**: Worst — different public port per destination IP:port. STUN alone often fails; requires TURN relay.

### TURN (Traversal Using Relays around NAT)

When direct UDP fails, TURN provides a relay server. Traffic goes: Client → TURN server → Session Host. Adds latency but still uses UDP.

**Key ports**: UDP 3478, TCP 443 (fallback)

### ICE (Interactive Connectivity Establishment)

ICE orchestrates STUN and TURN to find the best available path. It gathers candidates (direct, server-reflexive via STUN, relayed via TURN), exchanges them with the peer, and tests connectivity.

## Why Shortpath Fails

### 1. VPN/Proxy TUN Hijacking

When a VPN tool (ShadowRocket, Clash, Surge) runs in TUN mode, it captures all outbound traffic including STUN/TURN UDP packets. The proxy typically cannot relay raw UDP correctly, causing ICE negotiation to fail.

**Detection**: Windows App's source IP in `lsof` shows `198.18.0.x` (ShadowRocket) or another VPN virtual IP instead of the real local IP.

### 2. ISP UDP Restrictions

Some ISPs (particularly in China, especially outside tier-1 cities) throttle or block UDP to certain ports or destinations. This prevents STUN binding requests from reaching Azure's STUN servers.

**Detection**: STUN tests fail even with all VPNs disabled.

### 3. Symmetric NAT (Address-and-Port-Dependent)

If the router implements symmetric NAT, each outbound UDP flow gets a different public port. STUN discovers one port, but when the actual Shortpath connection uses a different destination, the NAT assigns a different port, and the peer's packets go to the wrong port.

**Detection**: Tailscale `netcheck` shows `MappingVariesByDestIP: true`.

### 4. FetchClientOptions Timeout

The client needs to fetch transport capabilities from the gateway. If this request times out (network issues, DNS problems, TLS interception), the client never learns about Shortpath availability.

**Detection**: Log entry `CWVDTransport::FetchClientOptions exception: Request timed out`.

### 5. Health Check Failure

Certificate validation errors at app startup prevent the diagnostic subsystem from completing, which can cascade into transport capability discovery failures.

**Detection**: `Failed to validate X509CertificateChain` at the start of the log, followed by absence of the health check block.

### 6. Server-Side Not Enabled

RDP Shortpath must be enabled on the AVD host pool by an administrator. If not enabled, the server never offers Shortpath candidates.

**Detection**: No STUN/TURN/Shortpath entries at all in logs, even though health checks pass.

## Network Requirements for Shortpath

### Ports

| Protocol | Port | Purpose |
|----------|------|---------|
| UDP | 3478 | STUN Binding Requests |
| UDP | 1024-65535 (dynamic) | Shortpath data channel |
| TCP | 443 | Gateway WebSocket (always needed) |

### DNS

The client must resolve these domains correctly:
- `*.wvd.microsoft.com` — AVD gateway
- `rdweb.wvd.microsoft.com` — AVD web client
- STUN/TURN server addresses (provided by the gateway during ICE)

DNS poisoning (returning fake IPs) prevents proper transport negotiation.

### TLS

The client validates TLS certificates for Microsoft endpoints. If the certificate chain is modified (ISP proxy, corporate MITM, DNS poisoning), the health check fails and transport negotiation may be impaired.

## Common Interference Patterns

### Pattern: ShadowRocket TUN Mode

**Mechanism**: Creates utun interface with IP 198.18.0.1, captures all public traffic via `0/1 + 128.0/1` split routing, DNS hijacked to 198.18.0.2.

**Effect on RDP**: All AVD traffic goes through proxy tunnel. STUN/TURN fails because proxy cannot relay raw UDP. DNS returns fake IPs (198.18.0.x).

**Fix**: Add DIRECT rules for Microsoft/Azure domains and IPs.

### Pattern: Tailscale with Exit Node

**Mechanism**: When exit node is enabled, all traffic routes through the Tailscale tunnel.

**Effect on RDP**: Similar to VPN hijacking — UDP packets go through WireGuard tunnel to exit node, then to Azure. Adds latency and may break STUN.

**Fix**: Disable exit node, or add route exceptions for Azure IPs.

### Pattern: Chinese ISP UDP Throttling

**Mechanism**: Some Chinese ISPs, particularly in non-tier-1 cities, apply QoS policies that throttle or drop UDP packets to foreign destinations.

**Effect on RDP**: STUN binding requests time out. Even with perfect client-side configuration, Shortpath cannot establish.

**Fix**: Try mobile hotspot (different ISP/carrier), use a proxy with good UDP support to Azure's region, or accept WebSocket with optimization (change DNS to reduce resolution latency).
