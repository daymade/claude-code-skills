# Device throughput fieldwork

Use this READ-DO workflow when gathering evidence through an unfamiliar device or
local-client API, or comparing a device's wired/Wi-Fi throughput. Keep the existing streaming, CDN,
proxy and two-channel investigations in the main Skill; this reference supplies
the device-side admission and measurement checks at their point of use.

The investigator executes these checks. No bundled tool enforces endpoint
classification, experiment validity or causal attribution.

## Bind the machines and paths before probing

Record the operator, controlled host, sender, receiver, protocol, direction and
intended interfaces. Draw the control path separately from the payload path: a
remote management connection can cross the WAN while the measured transfer stays
on a LAN. Management RPC success or failure measures that control path alone.

Reuse existing authorized router/ONT/NAS inventory, credentials and access owners
before discovering another management channel. Check readiness without changing
configuration; keep unavailable access explicit and continue independent read-only
work. Device discovery does not authorize configuration changes or new credentials.

## Classify an unfamiliar endpoint before calling it

1. Read its current implementation, schema or maintained owner contract offline.
   Identify parameters, validation order, state writes and downstream effects.
   HTTP GET, a getter-like name, an RPC transport or an HTTP 400 response does not
   prove the implementation is read-only: a handler can write before validating.
2. End the discovery tool call and inspect the returned evidence. Classify the
   candidate as a verified read, a known mutation or unknown; record the basis.
   Do not print source and then send the dependent request in the same script,
   batch or uninterrupted tool sequence. The agent's decision must precede a
   separate execution call.
3. Execute verified reads within scope. Keep known, already authorized operations
   such as a documented cache refresh available under their owner's contract.
   Route a mutation through its existing authorization and recovery procedure;
   leave an unknown endpoint uncalled until its effects are established.

If an accidental request may have written state, preserve its result and inspect
the complete touched field group, including client-side configuration. Restore
only from an authoritative baseline within authorization; do not invent missing
values or borrow credentials. Reconnection or a repaired network profile cannot
prove that additional client fields recovered. Verify the original consuming
operation separately; keep unobserved recovery unknown.

## Establish the actual data plane and comparison

Read live association on the device, including BSSID, frequency/band, channel
width and available PHY/rate observations. On Linux, use the device's `iw`
link/station observations rather than a cached application label. Preserve
unavailable fields as unknown; a PHY rate is not measured payload throughput.

Bind the probe to its intended interface where supported. Correlate the client's
actual local/remote socket addresses with the receiver's peer address; use socket
or NIC byte deltas when those observations leave the interface ambiguous. Treat
source IP and an unbound default-route query as corroboration, not a standalone
verdict. A wired default route does not invalidate a wireless-bound transfer whose
two ends confirm that path.

Use the same device, receiver, direction, protocol, payload policy and measurement
budget for A/B/A, restoring A after B. Record what actually changed in association
and PHY settings, rather than calling the switch a pure band intervention when
BSSID, width, channel or negotiated rates changed too. A repeatable rate change
supports association-state dependence; it does not isolate AP, radio conditions,
driver, firmware or hardware by itself.

For a horizontal control, compare another device on the same AP and band, with
the same direction, receiver and time window. Record remaining differences such
as antenna placement, capabilities and negotiated rates. A healthy peer brackets
the scope of the symptom; a peer on a different AP/band does not establish a
device defect. Keep this control distinct from the main Skill's two independent
application stacks sharing one path: the experiments answer different questions.

Measure payload received over the observed monotonic interval. For uploads, a
sender's `size_upload` is not the receiver's count; for downloads, server socket
writes are not client reception. State direction and units, preserve return code,
stdout and stderr, and distinguish a budget-ended transfer with received payload
from a DNS, authentication or connection failure. Do not turn a failed probe's
zero bytes into a low-throughput sample.

## Budget the protected experiment and verify recovery

Before any disruptive change, resolve **tunnel-doctor** and load its
[network-change recovery contract](https://github.com/daymade/claude-code-skills/blob/main/tunnel-doctor/references/network_change_recovery.md).
It owns authorization, original-state preservation, independently armed restoration,
failure/cancellation and cleanup. If that owner or the required recovery path is
unavailable, stop before mutation and continue read-only collection.

Save the original connection UUID/profile and relevant configured band/BSSID
restrictions as well as the live association. Budget the complete synchronous
protected section: worst-case activation/association wait, every sequential
transfer, cleanup and in-window readback, plus an explicit margin. Keep the
control session, test services and target-side recovery lifetime sufficient for
that budget; a per-transfer timeout is not the experiment's total duration.

Use a monotonic deadline for elapsed checks and record the actual intervention,
sample and rollback boundaries. A checkpoint TTL or requested timeout is not a
hard wall-clock promise. If rollback enters a sample, the association differs
from the intended state, or a prerequisite fails, mark that round invalid and
stop the next round. Preserve unexpected nonzero outer results even when later
cleanup succeeds.

Label an in-region `profile_after` snapshot as pre-rollback evidence when that is
where it was taken. After rollback has independently completed, or its window
has ended and completion is confirmed, read the original profile fields, active
UUID and actual association again. A rollback message or an earlier snapshot
does not establish restoration. Resolve any mismatch before another trial, and
test the user's original application/download path before claiming recovery.

## Hand off evidence without converting intervention into history

Separate pre-intervention observations from settings introduced during diagnosis.
Use pre-intervention evidence to establish that an attribute was present in the
original failure; a later pinned BSSID or client configuration
cannot be retroactively attributed to the product. Preserve unknown provenance.

For a vendor handoff, include versions, topology, sanitized reproduction commands,
per-round actual association, receiver counts/timing, exit results and validity.
Give every load-bearing factual claim a locatable safe original inside the
handoff package; retain originals privately and provide redacted copies when
necessary. A source path that only exists on the investigator's machine is not
vendor evidence. Keep historical measurements separate from a later corrected
recipe, and state the causal boundary that the comparisons actually support.

Stop when the requested diagnosis and recovery have their necessary evidence.
If the original downloader or real-file completeness check was not rerun, state
that specific unverified result; a synthetic throughput success cannot close it.

## Source semantics

- [HTTP safe-method semantics](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.1)
  define intended method semantics; inspect an unfamiliar implementation's effects.
- [Linux wireless `iw` documentation](https://wireless.docs.kernel.org/en/latest/en/users/documentation/iw.html)
  describes live link and station observations.
- [NetworkManager checkpoint API](https://networkmanager.dev/docs/api/latest/gdbus-org.freedesktop.NetworkManager.html)
  defines checkpoint and rollback interfaces; verify the target's actual recovery.
