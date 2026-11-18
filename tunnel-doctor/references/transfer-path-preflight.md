# Before a remote bulk copy

Apply this before an SSH rsync/scp copy of a directory, a remote source of unknown
size, or local regular files above the executable owner's small-copy limit. Read-only SSH queries, dry
runs, loopback copies and known small local uploads do not require a bulk preflight.

Bind the exact command, working directory, SSH identity/options, current local
network and observation time. A Tailscale address is a logical destination. Its
underlay may be LAN direct, WAN direct, peer relay, DERP or unknown. `direct` alone
does not mean LAN. A route to a Tailscale interface does not identify the underlay.

## Read-only executable preflight

Resolve `<tunnel-doctor-dir>` from this Skill's loaded location. Save the exact
copy command in a private file; the helper reads it as data and never executes it:

```sh
python3 <tunnel-doctor-dir>/scripts/transfer_path.py preflight \
  --command-file <private-command-file> --cwd <original-working-directory>
```

The helper requires SSH, Tailscale CLI for Tailscale targets, `lsof`, and local
route/interface tools (macOS or Linux). It authenticates using existing trusted
SSH keys, discovers remote interface addresses, tests relevant local-subnet
candidates without accepting new host keys, observes a real SSH TCP socket, and
reads a bounded payload. It requires converging Tailscale observations before
accepting a path. It neither changes routes nor restarts a
service. The sample is a path/throughput observation, not proof of line capacity
or the cause of an earlier slow transfer.

The [executable owner](../scripts/transfer_path.py) defines size limits, sample
size and evidence lifetime. Use the returned `expires_in_seconds` to retry the
unchanged command and cwd before the evidence expires.
An available verified LAN candidate prevents a WAN/relay path from being accepted;
select that candidate while preserving its existing host-key namespace, or let
Tailscale converge to LAN direct, then preflight the resulting command. WAN direct,
peer relay and DERP remain usable when no relevant candidate verifies and the
live sample succeeds. Failure to inspect remote interfaces is unknown, not proof
that LAN is unavailable. A ready result is not an instruction to start a copy:
payload identity, destination authorization and progress remain with the caller.

The optional agent execution gate checks the same owner before a literal copy
command, including evidence age, SSH configuration, local network and current
path. It blocks missing or changed evidence; rerun the read-only preflight and
retry the identical command. A changed target needs its own proof. Never fabricate
proof files or disable the gate to resolve an unknown.

## Coverage and recovery

The executable supports one SSH remote per literal rsync/scp command. ProxyJump,
ProxyCommand, SSH multiplexing, rsync-daemon transport and ambiguous DNS remain
unknown; select an inspectable existing connection or use the owning network
operator to establish that route. Do not invent a new credential or weaken SSH
trust. Opaque scripts, arbitrary SSH streams, SMB and dynamically built tool
arguments are outside this gate's verified interception. Use this same evidence
sequence manually there; loading this Skill does not install a hook.

If prerequisites are unavailable, report the missing observation and use existing
platform tools to collect identity, LAN comparison, current underlay and a bounded
sample. Manual observations do not release an installed exact-proof gate; repair
its prerequisite or select a supported transfer. Stop after one bounded probe
failure; preserve partial payloads and report the concrete unknown. Do not loop
on the same failed preflight or disrupt other sessions to manufacture a path.

During the actual copy, retain live progress, bytes, timing and integrity evidence.
Resample when the network/target changes or progress collapses. A fresh observation
must not be used to claim what path an earlier transfer took.

The path labels and transition examples follow Tailscale's
[connection types](https://tailscale.com/docs/reference/connection-types) and
[ping types](https://tailscale.com/docs/reference/ping-types); inspect the installed
CLI's help before using a different version's flags.
