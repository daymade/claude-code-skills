# Packet Capture Recipes

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

| Interface   | Traffic                                         |
| ----------- | ----------------------------------------------- |
| `eth0`      | Public ingress/egress (internet)                |
| `br-<hash>` | Custom Docker bridge networks (compose-defined) |
| `docker0`   | Default Docker bridge                           |
| `vethXXXX`  | One veth pair per container (host-side end)     |
| `lo`        | Loopback on the host                            |

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

Set snaplen explicitly and check the installed `tcpdump` manual. `-s 0` selects
the tool's default large snapshot length; it is not an unlimited-length promise.
Inspect captured versus original packet lengths before claiming complete payloads.

### File-limited time rotation

```bash
tcpdump -i any -w /tmp/cap-%Y%m%d-%H%M%S.pcap -G 60 -W 10 'host <target>'
```

With `-G`, `-W` limits the number of rotated files and exits when that limit is
reached; this is not an indefinitely overwriting ring buffer. Reaching the limit
ends observation, but the rotation limit is not a hard wall-clock deadline and
time-based rotation alone does not bound file size. Set a separate stop for the
experiment-owned capture and a storage allowance for the authorized window; preserve needed
segments before cleanup, and check the collector's actual end time and exit status.
For size-based cyclic overwrite, consult the installed manual's `-C`/`-W` contract;
combining `-C` and `-G` changes how `-W` is handled.

## HTTP/2 specifics

A key trap: HTTP/2 has its own RST mechanism at the stream level (`RST_STREAM` frame) that is unrelated to TCP-level RST. The two failure modes look different:

| Failure                          | TCP layer shows                          | HTTP/2 layer shows                 | curl reports                                                     |
| -------------------------------- | ---------------------------------------- | ---------------------------------- | ---------------------------------------------------------------- |
| TCP RST (connection-level reset) | RST packet                               | N/A (connection dies)              | `Recv failure: Connection reset by peer`                         |
| HTTP/2 RST_STREAM frame          | (no RST packet — connection stays alive) | `RST_STREAM` frame with error code | `HTTP/2 stream N was not closed cleanly: INTERNAL_ERROR (err 2)` |

The case study was the second kind: `tcpdump` showed no TCP RST on the client→origin path but curl reported `HTTP/2 stream 1 was not closed cleanly: INTERNAL_ERROR (err 2)`. The reset was a peer-initiated HTTP/2 `RST_STREAM`, sent as a data frame on a connection that otherwise stayed open for other streams.

### Decoding HTTP/2 with tshark

`tcpdump` alone cannot show HTTP/2 frames because they are TLS-encrypted. If you control both endpoints, you can:

1. Confirm the selected curl TLS backend supports `SSLKEYLOGFILE`, set the local
   parameters `key_log_path` and `authorized_test_url`, then run
   `SSLKEYLOGFILE="$key_log_path" curl "$authorized_test_url"`. Verify that it wrote
   keys for the captured run; setting the variable alone does not prove key logging.
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

## Four-boundary tunnel captures

Use this recipe when an authorized bulk-transfer observation reproduces a tunnel
throughput problem and one capture cannot locate where packets disappear. For a
known Tailscale/TUN/proxy conflict, begin with `tunnel-doctor`; use this recipe for
the unresolved packet-boundary question. The investigator selects interfaces and
filters from the actual route and observed flow, not from example interface names.

For direction A→B, collect the same bounded run at four observation points:

| Capture | What it observes |
| --- | --- |
| A tunnel interface | Inner application flow before encapsulation |
| A physical interface | Outer tunnel datagrams at the sending host's capture tap |
| B physical interface | Outer tunnel datagrams at the receiving host's capture tap |
| B tunnel interface | Inner application flow after decapsulation |

Analyze B→A separately. Record the actual inner flow's protocol, addresses and
ports, outer endpoints, route/interface identity, capture commands, start/end
times with timezone, snaplen and collector exit/drop statistics. Include all
observed endpoint addresses, including stable and temporary IPv6 addresses.
Start all captures before the transfer and keep them through its end and a stated
settling interval. Stop only capture processes owned by this experiment.
Keep captures and their decoding recipe in the incident's persistent evidence
directory when later or post-reboot review is required.

### Match packets before reporting a missing fraction

For direct WireGuard transport-data packets, the public
[protocol specification](https://www.wireguard.com/protocol/) defines a 16-byte
prefix: type/reserved bytes, a little-endian 32-bit receiver index and a
little-endian 64-bit counter. Compare `(receiver index, counter)` within the same
direction, peer/session and key epoch; do not combine directions or unrelated
sessions. Preserve the original captured headers and the decoding command or
parser revision so another investigator can recompute the sets. Rekeying or
endpoint changes require separate groups. A relayed or differently encapsulated
path needs its actual framing decoded; do not interpret arbitrary UDP bytes as
direct WireGuard headers.

Choose snaplen after verifying that the actual link/IP/UDP headers and the full
identifier prefix survive in both captures. IPv6 extension headers, fragmentation
and different link-layer formats invalidate a fixed-offset assumption. Avoid
payload capture when headers suffice; if the identifiers are truncated, the
comparison is unknown rather than a missing-packet result.

Use a common interior observation window, with a stated boundary margin, so a
packet captured just before the other collector starts or just after it stops
does not become apparent loss. Allow for reordering and capture-clock differences;
compare packet identities, not timestamp equality. Deduplicate capture appearances
and report raw and unique counts. For one compatible group, let `S` be the unique
identifiers at the sending physical tap and `R` those at the receiving physical
tap over that comparable window. Report `|S|`, `|R|`, `|S∩R|`, `|S−R|`, `|R−S|`
and, only when `|S| > 0`, the missing fraction `|S−R| / |S|`. A gap in counter
sequence alone is not evidence of loss: other traffic may share that session.

Before attributing unmatched packets, inspect every collector's reported drops,
endpoint/filter coverage, identifier decoding and host capture/offload behavior.
Unresolved collector loss, omitted endpoints or incomparable packet segmentation
leave the network-loss estimate unknown; zero collector drops alone do not prove
complete capture. Do not subtract raw packet totals from different taps.

### Bound the conclusion to the observed run

Packets present at A's physical tap but absent at B's physical tap localize an
observed discrepancy between those taps, subject to the capture checks above.
That interval includes host driver/NIC, local access network and intermediate
path; it does not identify the ISP, tunnel software or one router by itself.
Outer delivery with missing inner delivery moves the next question toward
decapsulation or host processing. Reverse-path agreement is a directional control,
not proof that the forward path is healthy. An encrypted outer session can carry
several inner flows: correlate the experiment window and traffic isolation before
assigning its discrepancy to one application's transfer.

Record whether the original symptom actually recurred. A slow transfer observed
after a reboot can establish a current network defect without reproducing a prior
whole-machine hang. Neither that result nor a healthy short SSH handshake closes
the historical crash's causal chain. These are investigator-run checks, not an
automatic packet-loss detector or a new permanent capture service.

## Common pitfalls

### Wrong filter syntax leading to silent over-capture

`tcp[tcpflags] & tcp-rst != 0 and port 443 or port 3002` without parentheses evaluates as `(tcp-rst != 0 and port 443) or port 3002`, capturing all traffic on port 3002 regardless of RST. The resulting pcap contains thousands of packets the investigator did not intend to capture, and the actual RSTs are drowned out.

Fix: always parenthesize compound filters — `(tcp[tcpflags] & tcp-rst != 0) and (port 443 or port 3002)`.

### Capturing nothing because of interface mismatch

`tcpdump -i eth0 'host 10.0.0.5'` on a Docker host where the target is only reachable via `br-abc123` captures nothing. Symptom: "I ran tcpdump but got zero packets even though traffic is flowing."

Fix: use `-i any` first to verify, then narrow once you see traffic.

### Confusing timestamps across tools

Separate saved packet timestamps from their textual display. Text output uses the
reader's display timezone, which can differ from the capture host or application
log. Use `-tt` for epoch-style output when correlating, record capture-host clock
offsets separately, and do not treat timezone conversion as clock synchronization.

### Missing the RST because it happened before capture started

`tcpdump` only captures from the moment it starts. If the RST already happened,
there is no going back. Start a bounded capture before an authorized reproduction;
for an intermittent symptom, verify that observation still covers the event rather
than assuming a time-rotated collector kept running.

### Forgetting snaplen

Use the snaplen check above. For tunnel matching, apply
[identifier coverage](#match-packets-before-reporting-a-missing-fraction) before
interpreting absent identifiers as packet loss. Small packets alone do not prove
that the required headers survived the actual link-layer and encapsulation layout.
