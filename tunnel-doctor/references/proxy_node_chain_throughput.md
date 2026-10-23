# Proxy node, exit, and chain throughput

Use this branch when the proxy is reachable and small requests succeed, but real
downloads, Git packs, or batch jobs are slow. It covers both a single-hop proxy
node and a multi-hop chain. It does not assume that a residential second hop is
always required or always harmful; the requested topology is an input, not a fix.

## Route the symptom first

| Observation | Next action |
|---|---|
| Proxy listener or repeated small requests fail | Run the existing connectivity and TUN-plane branches in `SKILL.md` |
| Listener and small requests pass, but bulk transfer is slow | Continue with the capacity workflow below |
| Two independent channels are both slow and the active node is not yet known | Freeze the current topology, then compare nodes |
| The path is fast but one application remains slow | Return to `debugging-network-issues` for application/protocol isolation |

## Capacity workflow

1. **Freeze the target topology.** Read back the active node, subscription, and
   chain depth before changing anything. If the user requested a single-hop exit,
   do not “repair” it by adding a residential next hop. If they require a chain,
   do not silently clear it. Change one variable per round.
2. **Record a real slow baseline.** Measure bytes, wall time, average rate, and
   transfer exit code from the affected client. Keep one small request only as a
   reachability control; it is not a capacity measurement.
3. **Compare every declared candidate serially.** Use the same endpoint, payload,
   time budget, and client for each node. Confirm each selection was persisted and
   became active before measuring. Do not run candidates concurrently: they would
   compete for the same access link and corrupt the ranking. Do not stop at the
   first node that returns 200; availability is not throughput. Neither is the
   tool's displayed node latency: in one measured set, four entry lines of a
   single product displayed 140–152 ms while delivering 78 KB/s to 1.5 MB/s in
   serial fixed-window downloads — a 19× spread that did not rank with the
   displayed numbers. Measure every candidate.
4. **Re-test from the real client path.** A fast result on the proxy host proves
   only that host's path. If production traffic arrives through another Mac, WSL,
   VM, LAN proxy, or reverse SSH tunnel, repeat the rate test there and add an
   original-protocol control such as GitHub `ls-remote`. A host/client split is the
   signal to inspect the forwarding segment.
5. **Replay the original complete workload.** After the representative rate
   recovers, run the full clone, full download, or original batch with its original
   timeout and completeness checks. A partial/shallow clone or a relaxed timeout is
   a hypothesis, not proof. If the unchanged full workload passes, preserve the
   application semantics; if it still fails, retain the result and investigate the
   application layer.
6. **Read back the final configuration.** Prove that the active node and chain
   depth still match the user's requested topology, then report the before/after
   rates and the full-workload result.

Use one read-only measurement shape for every candidate so the numbers remain
comparable. Point it at a sufficiently large neutral object; change only the
active node between runs:

```bash
PROXY_URL=http://127.0.0.1:<proxy-port>
TARGET_URL=https://<host>/<large-object>

curl -sS -o /dev/null --max-time 20 --proxy "$PROXY_URL" \
  --write-out 'http=%{http_code} bytes=%{size_download} wall=%{time_total}s rate=%{speed_download}B/s\n' \
  "$TARGET_URL"
CURL_EXIT=$?
printf 'curl_exit=%s\n' "$CURL_EXIT"
```

For this fixed-time sample, exit 28 is usable only when the cutoff was intended
and the reported byte count is nonzero; DNS, connection, TLS, or authentication
failures are invalid measurements, not “slow” nodes. The final original-workload
replay must still meet its own success exit and completeness contract.

RFC 6349 separates sustained TCP throughput from RTT and liveness and recommends
tests long enough for transfer behavior to dominate setup cost. The practical
translation here is simple: choose a payload or fixed time budget large enough to
measure capacity, and finish on the workload the user actually needs.

## Candidate sets when the exit identity is fixed

When the requested topology is a static-IP product — one fixed exit address
reached through several entry lines — the candidate set is that product's own
entry lines. Switching lines preserves the egress identity the user selected;
switching to another product's node changes the exit IP, which is a topology
change, not a throughput experiment.

After each switch, confirm two things independently: the tool's active-node
readout (the switch took effect) and the egress IP through the tunnel (identity
was preserved). An unchanged egress IP alone proves nothing — a failed switch
reads identically; the changed measurement is the other half of the proof.

## Headline capacity probes on macOS

`networkQuality -s` is the built-in capacity probe. Under a TUN, a default run
rides the tunnel — verified: the identical run moved 64.7 → 472.6 Mbps after a
node switch (2026-10-23) — so it measures the path the user experiences, not the
wire. `networkQuality -s -I en0` binds the test to the physical interface (`-I`:
"Bind test to interface", per its own help) for the wire baseline. Trust the
capacity numbers; do not compare the latency/responsiveness sub-metrics across
binding modes — an interface-bound run has reported higher idle latency than the
tunneled run on a healthy host. Whether the default run exercises the node at
all depends on the proxy tool's rules for the test endpoints; a number that
moves when the node changes is proof it rode the tunnel.

An instant HTTP error with ~0 bytes from a measurement endpoint is the endpoint
refusing the exit address, not node incapacity — a speed-test CDN answered 403
in 1.3 s through a residential exit (observed 2026-10-23) while the same node
served a plain CDN-hosted 100 MB object (Hetzner's speed-test file) fine. Switch
to a neutral object that serves the exit's class, and keep one target for the
whole ranking.

## Mutation boundary

Node selection and subscription refresh are implementation-specific. Read the
current tool's own schema or UI before changing it, stop the owning process before
editing its database, and re-read the active selection after restart. If an
installed compatibility operator exposes an authorized heal command, use it only
when its declared success topology matches the user's request. Never run a
“residential chain intact” command for a task whose contract is “remain single
hop,” and never copy a version-sensitive database writer into this reference.

Shadowrocket on macOS exposes no CLI; drive its accessibility tree. Click the
node row's button, then read back the active marker before measuring — the
row's label gains a "Use Server" prefix and the toolbar button shows the active
node name. Element indexes invalidate after every click; re-observe the tree
before the next action instead of reusing a stale index.
