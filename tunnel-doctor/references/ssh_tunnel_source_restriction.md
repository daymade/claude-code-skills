# Public gateway failure with a healthy backend

Use this read-do check when a public service returns 502 while its backend still
serves the expected response, or a dedicated SSH tunnel key is rejected as coming
from a non-permitted host. The executing agent gathers evidence; the existing
service/configuration controller owns any authorized repair. This reference adds
no access, restart or deployment permission and no automatic enforcement.

## Separate the failing layers

1. Record the exact public URL, consumer identity, status, response body and time.
   Compare the backend through its normal internal entry, then the gateway's
   configured upstream/listener and the tunnel's current connection evidence.
   Confirm that this configured path actually uses SSH forwarding before applying
   the key checks below; otherwise continue with that upstream's existing owner.
   A backend login redirect can localize a path difference; it does not prove the
   authenticated task page works. A running tunnel process or healthy Tailscale
   peer does not prove the gateway's required forwarding channel exists.
2. Through the approved server log/control channel, correlate one failed attempt
   with its exact destination, SSH account and time. A server authentication log
   saying `correct key but not from a permitted host` establishes that this attempt
   reached sshd and failed its key source restriction. This is distinct from a
   provider security group or host firewall dropping packets, and from a TUN
   dropping traffic before sshd. Do not restart the backend or TUN to repair it.
3. Bind the offered key fingerprint to the dedicated public key and its effective
   `AuthorizedKeysFile` entry. Compare that entry's `from=` pattern with the source
   address recorded by the destination for this attempt. Preserve any NAT/proxy
   difference; a client IP lookup on another forwarding plane cannot replace the
   destination's observation. Do not print private keys or publish live identifiers.
   A different key being rejected is a healthy access control, not proof of source
   drift. Missing fingerprints, mismatched identities or absent logs leave the
   cause unknown; ask the existing controller for that evidence before changing it.

## Correct only the proven restriction through its owner

Read the controller's current source of truth, effective key/account restrictions,
authorized change scope and recovery path. Use its existing reviewed configuration
and deployment route. Do not edit a generated root-owned authorized_keys file in
place, rotate credentials, restart a shared gateway, or terminate another session
as a diagnostic shortcut. If the controller or required authority is unavailable,
report the exact missing handoff and continue only independent read-only work.

For a long-running service on a dynamic residential/mobile egress, check whether
pinning that key to the old source address was an implementation choice or an
explicit access contract. Choose the correction under the current authorization
and service contract: maintaining an approved source restriction and relying on a
dedicated identity with reviewed forwarding limits have different trade-offs.
Neither dynamic addressing nor this failure authorizes universally stripping
`from=` or removing other restrictions. Keep wrong keys, unapproved destinations,
shell/subsystem sessions and unrelated accounts denied as the contract requires.

OpenSSH defines these controls separately: `from=` constrains where a key may
authenticate; `permitopen=` limits local-forward destinations; `restrict` disables
several facilities, including forwarding, unless explicitly re-enabled. Inspect
the effective combination rather than assuming a destination limit enables
forwarding or that `restrict` alone denies shell execution. Where the approved
account uses `MaxSessions 0`, shell/login/subsystem sessions are denied while
forwarding remains possible. Verify the deployed OpenSSH version and effective
configuration before relying on those semantics. See the official
[authorized-key options](https://man.openbsd.org/sshd.8#AUTHORIZED_KEYS_FILE_FORMAT)
and [MaxSessions](https://man.openbsd.org/sshd_config.5#MaxSessions).

## Verify the original public consumer and the boundaries

After the owner-controlled change, observe the existing tunnel supervisor's
natural reconnect and the required forwarding channel; do not force recovery by
restarting shared services. If no reconnect has been observed, leave that criterion
unverified rather than inferring it from a process or an old connection.

Use the current public consumer's normal authentication and exact original URL to
read the expected task/report body. Separately check anonymous protected routes
remain denied or redirect as designed and the login page remains usable. A 200
login page, internal health response or live SSH process cannot replace that body.
Within authorized tests, confirm the dedicated key still cannot open unapproved
ports or shell/subsystem sessions and a different key is refused; preserve existing
sessions and data. Record positive and negative results with their identity and
time. Stop at that usable public result plus the contracted boundaries, or name
the exact unverified criterion and its owner; do not add a new monitor or daemon.
