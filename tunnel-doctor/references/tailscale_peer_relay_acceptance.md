# Bind Peer Relay acceptance to the actual path

Use when testing a named Tailscale Peer Relay or interpreting a network speed
claim. Keep the user's selected candidates and protocol requirements. This
recipe grants no authority to change ACLs, credentials, relay settings, routing,
or an active daemon. Keep machine addresses in the owning deployment inventory.

## Bind the test before sending traffic

Record the exact source, destination and proposed relay, their observed network
locations, the approved business operation and its identity/integrity checks.
Distinguish same-LAN, cross-network and actual WAN vantage points. A cloud relay
in the configuration does not prove the tested traffic traverses it; a hotspot
does not by itself identify why SSH timed out.

Reuse the existing trusted SSH or application entry, host-key binding and
permissions. Read its effective configuration before adding per-command route
arguments. Keep SSH-gateway acceptance separate from UDP or arbitrary-protocol
acceptance when the task requires those protocols.

## Observe the business flow and its transport together

1. Capture the installed Tailscale version and exact peer identity. Inspect
   `tailscale status` for that peer and, when authorized, `tailscale ping <peer>`.
   Bind the output to the test's time window; an initial probe can use a different
   path from a later transfer.
2. Run the approved representative operation through its normal entry. For a
   read-only SSH transfer, retain authentication/host-key success, the selected
   content hash, verified bytes and monotonic start/end times. Ping alone is not
   application acceptance.
3. Observe transport during that operation and correlate both endpoints with
   the selected relay's available logs, counters or bounded packet evidence.
   Match endpoint, direction and window; unrelated relay traffic is not proof.
   Do not invent an unavailable counter or diagnostic flag. Report the narrower
   observed scope when the relay-side evidence is unavailable.
4. Preserve the complete per-peer path labels. `direct`, DERP `relay` and
   `peer-relay` are distinct; a substring match for `relay`, a tailnet address or
   relay configuration alone cannot classify the path. A path transition must
   remain visible in the result.

Tailscale prefers direct communication and can fall back through a peer relay
or DERP. An already direct business flow verifies that direct path, not the
proposed relay. To exercise fallback, use only an explicitly authorized isolated
client and its existing preparation workflow; do not disable the working
production path or enroll another node merely to obtain a relay result.

The official [connection types](https://tailscale.com/docs/reference/connection-types)
and [Peer Relay observation](https://tailscale.com/docs/features/peer-relay#step-3-observe-peer-relay-traffic)
describe the labels and probes. Resolve current flags from the installed CLI
and those docs before proposing configuration changes.

## Keep availability and performance claims separate

| Evidence | Supported conclusion |
|---|---|
| Named peer-relay path plus the bound business result and relay-side correlation | That relay carried the tested operation in this window; retain byte count and duration. |
| Successful direct flow, or only a same-LAN relay test | The observed direct or LAN path worked; WAN relay availability remains untested. |
| Relay trial did not establish; only a filtered packet window is available | That trial did not establish under the observed conditions; the specific NAT/firewall cause remains unknown. |
| One SSH stream has low throughput | That workload/path was slow; it does not establish LAN or NIC capacity, nor a performance improvement. |

For a speed comparison, keep source/destination, payload, direction, concurrency,
encryption, tool and observation window comparable, and prove which path each
sample actually used. Record units and verified bytes; CPU, disk and SSH setup
can contribute to elapsed time. Without a comparable baseline, report throughput
as a sample, not an optimization. Stop once the evidence decides the next
business action; do not cycle unrelated network settings to improve a metric.

Return the bound identities, topology, observed path/transitions, business result,
timing, evidence locations and remaining gaps. Clean up only task-owned temporary
clients/rules through their original owner, and independently verify that the
pre-existing consumers still have their preserved entry and trust configuration.
