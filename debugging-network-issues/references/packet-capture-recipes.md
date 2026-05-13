# Packet Capture Recipes

## Contents
- When to capture packets
- Interface selection on Docker hosts
- Essential filters for RST isolation
- HTTP/2 specifics (stream RST is not TCP RST)
- Correlating pcap with application logs
- Common pitfalls

## When to capture packets

Reach for `tcpdump` when the question is at Layer 3-4 and application logs cannot answer it:

- Who sent the RST? (application does not see the peer's RST as it is OS-delivered to the socket)
- Was this a TCP-level reset or an HTTP/2 stream-level reset?
- Did the server send a FIN or was the connection torn down mid-response?
- What was the exact byte on the wire at the time of close?

If the application already tells you "client disconnected at T", you do not need pcap for that.

## Interface selection on Docker hosts

Container traffic traverses multiple interfaces on a Docker host. Picking the wrong interface shows only part of the story.

Typical layout:

| Interface | Traffic |
|-----------|---------|
| `eth0` | Public ingress/egress (internet) |
| `br-<hash>` | Custom Docker bridge networks (compose-defined) |
| `docker0` | Default Docker bridge |
| `vethXXXX` | One veth pair per container (host-side end) |
| `lo` | Loopback on the host |

Use `tcpdump -i any` to capture across all interfaces, at the cost of higher volume. For specific scoping:

- Capture between a container and an upstream (e.g., origin to Cloudflare): `tcpdump -i eth0 host <upstream-ip>`
- Capture inside a compose network (container-to-container): `tcpdump -i br-<hash>` (get the hash via `docker network ls`)
- Capture only one container's veth: `docker exec <container> ip route` to find its IP, then `tcpdump -i any host <container-ip>`

## Essential filters for RST isolation

The goal is usually: "find RST packets relevant to my incident, ignore everything else".

### All TCP RST packets

```bash
tcpdump -i any -nn 'tcp[tcpflags] & tcp-rst != 0'
```

Note the `!= 0` — not `== tcp-rst` — because RST can be combined with ACK (RST-ACK packets).

### RST scoped to a target port

```bash
tcpdump -i any -nn '(tcp[tcpflags] & tcp-rst != 0) and (port 443 or port 80)'
```

Watch the operator precedence in compound filters — always parenthesize. A naive `tcp-rst != 0 and port 443 or port 80` will match `port 80` without the RST constraint.

### RST to/from a specific IP

```bash
tcpdump -i any -nn '(tcp[tcpflags] & tcp-rst != 0) and host <ip>'
```

### With write to file for later analysis

```bash
tcpdump -i any -s 0 -w /tmp/capture.pcap 'host <target> and port 443'
# ... reproduce the incident ...
# Then:
tcpdump -r /tmp/capture.pcap -nn | head -50
```

`-s 0` captures full packets (default truncates to 68 bytes for performance).

### Ring-buffer capture for long-running collections

```bash
tcpdump -i any -w /tmp/cap-%Y%m%d-%H%M%S.pcap -G 60 -W 10 'host <target>'
```

60-second files, 10-file rotation, self-cleaning. Safe to leave running overnight.

## HTTP/2 specifics

A key trap: HTTP/2 has its own RST mechanism at the stream level (`RST_STREAM` frame) that is unrelated to TCP-level RST. The two failure modes look different:

| Failure | TCP layer shows | HTTP/2 layer shows | curl reports |
|---------|----------------|--------------------|--------------| 
| TCP RST (connection-level reset) | RST packet | N/A (connection dies) | `Recv failure: Connection reset by peer` |
| HTTP/2 RST_STREAM frame | (no RST packet — connection stays alive) | `RST_STREAM` frame with error code | `HTTP/2 stream N was not closed cleanly: INTERNAL_ERROR (err 2)` |

The case study was the second kind: `tcpdump` showed no TCP RST on the client→origin path but curl reported `HTTP/2 stream 1 was not closed cleanly: INTERNAL_ERROR (err 2)`. The reset was a peer-initiated HTTP/2 `RST_STREAM`, sent as a data frame on a connection that otherwise stayed open for other streams.

### Decoding HTTP/2 with tshark

`tcpdump` alone cannot show HTTP/2 frames because they are TLS-encrypted. If you control both endpoints, you can:

1. Export the TLS session keys via `SSLKEYLOGFILE=/tmp/keylog.log curl ...`
2. Open the pcap in Wireshark with the keylog to decrypt
3. Filter: `http2.type == 3` (RST_STREAM frames)

Alternatively, for internal services where you can intercept before TLS:

```bash
tshark -i any -f 'host <target>' -Y 'http2.type == 3'  # requires plaintext or pre-TLS interception
```

In most production debugging, the HTTP/2 error code is observable from the client-side log (curl, browser devtools Network tab "Status", Node SDK error message) without needing to decrypt pcap.

## Correlating pcap with application logs

Tie pcap to application activity via the request identifier:

1. Log the request ID server-side at request start (e.g., `[REQ-START] req=abc123 src=1.2.3.4:54321 ts=...`)
2. Capture pcap with source IP and port filter
3. Cross-reference: the pcap flow on `(1.2.3.4:54321 ↔ server:443)` maps to application log entries for `req=abc123`

This resolves ambiguities like "which of the 20 concurrent connections is the one that failed?"

## Common pitfalls

### Wrong filter syntax leading to silent over-capture

`tcp[tcpflags] & tcp-rst != 0 and port 443 or port 3002` without parentheses evaluates as `(tcp-rst != 0 and port 443) or port 3002`, capturing all traffic on port 3002 regardless of RST. The resulting pcap contains thousands of packets the investigator did not intend to capture, and the actual RSTs are drowned out.

Fix: always parenthesize compound filters — `(tcp[tcpflags] & tcp-rst != 0) and (port 443 or port 3002)`.

### Capturing nothing because of interface mismatch

`tcpdump -i eth0 'host 10.0.0.5'` on a Docker host where the target is only reachable via `br-abc123` captures nothing. Symptom: "I ran tcpdump but got zero packets even though traffic is flowing."

Fix: use `-i any` first to verify, then narrow once you see traffic.

### Confusing timestamps across tools

`tcpdump` timestamps are in the local timezone of the capture host. Application logs may be in UTC, or in a different timezone. When correlating, convert to a single timezone before comparing timestamps — use epoch seconds if unsure.

### Missing the RST because it happened before capture started

`tcpdump` only captures from the moment it starts. If the RST already happened, there is no going back. The fix is to start capture *before* reproducing the incident (or to leave a ring-buffer capture running in advance for known-intermittent issues).

### Forgetting snaplen

Default `-s 68` (or `-s 262144` on modern systems depending on version) may truncate large frames. Use `-s 0` to capture full packets if you intend to inspect payload bytes. For RST-only analysis, the default is fine (RST is a small packet).
