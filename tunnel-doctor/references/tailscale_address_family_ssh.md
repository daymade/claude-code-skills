# Recover SSH through another address family of the same Tailscale peer

Use this when an approved peer's IPv4 SSH path times out, or an alternate address
has no matching `known_hosts` entry. Keep working IPv4 connections unchanged.
This is a bounded command-plane recovery, not evidence that IPv6 is generally
faster or that the peer, local TUN, or destination firewall caused the failure.

## Bind identity before connecting

1. Resolve the authorized machine and SSH user from the owner's existing inventory.
   Read `tailscale status --json` and select that exact peer's current `TailscaleIPs`.
   Names, cached addresses and `Online: true` alone do not establish a usable path.
2. Inspect `ssh -G <approved-ssh-alias>` for the effective hostname, user, port,
   proxy and `HostKeyAlias`. Locate the previously verified key identity with
   `ssh-keygen -F <known-hosts-lookup-key>`. A non-default port may use a
   `[host]:port` lookup key. Preserve the existing user, port and proxy policy;
   do not guess a key alias from a nearby machine name.
3. Probe the selected family's route and bounded authenticated SSH command.
   `tailscale ping` and an open TCP port do not prove SSH. Calibrate port probes
   when a TUN can answer locally, as described in the main Skill.

## Try the peer's live IPv6 address without relaxing trust

Continue only when the live peer has an IPv6 address and the known-hosts identity
above is already verified for that same machine. Substitute observed values for
the placeholders; do not copy an address or key binding from a historical run.

```bash
ssh -T -6 -o BatchMode=yes -o ConnectTimeout=5 \
  -o StrictHostKeyChecking=yes \
  -o HostName=<live-peer-ipv6> \
  -o HostKeyAlias=<verified-hostkey-identity> \
  <approved-ssh-alias> 'hostname; id -un; uname -s'
```

`HostKeyAlias` selects an existing trust identity; it does not approve a new key.
Require nonempty host, user and OS values matching the approved machine before
continuing the original task. If the alternate address produces a different key,
stop that connection and independently establish the target fingerprint through
an already trusted channel or the owner. Do not use `StrictHostKeyChecking=no`,
discard `known_hosts`, or replace its entries to make the probe pass.

If the peer has no IPv6 address, no verified key binding, a deliberately IPv4-only
proxy path, or another failed probe, report that exact missing condition and use
the existing route/SSH owner. Do not disable a proxy/VPN, restart a service, change
an ACL or firewall, or declare the entire host offline from this one-path result.

## Resume and verify the original operation

After a timeout, read the prior operation's state through the recovered channel
before retrying any write. It may have completed after the original connection
disappeared. Keep dependent actions stopped until that state is known.

Reuse the verified address and trust binding only for the authorized task's
commands, preserving the existing SSH configuration. Recheck live addresses after
a later disconnect; do not persist a temporary address as a fleet default.
Report IPv4 and IPv6 observations separately, plus whether the original business
operation succeeded. A successful SSH identity probe is not application acceptance.
