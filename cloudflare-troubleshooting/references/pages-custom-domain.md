# Pages custom domains and DNSSEC migration

Use when Pages serves its provider URL but the intended hostname fails, or when a
Pages domain needs a delegation/DNSSEC move. The executing agent performs these
checks with the authorized project/account, registrar access, a DNS client and a
browser. This procedure does not grant production-write permission. Missing access
remains a named prerequisite; inspect independent layers without inventing values.

## Locate the existing service

Read the project's intended hostname, Pages account/project and deployed revision.
For registrar identity, start with the existing asset inventory and its original
sources; a missing record in one account does not establish loss of ownership.
Current nameservers identify DNS hosting, not necessarily the registrar. Resolve
conflicts through registry/RDAP, transfer confirmation and the current signed-in
registrar account before asking for information already available there. Use only
authorized, bounded history/mail access; keep private identities outside this Skill.

Reuse the entry's authentication. These are read-only API paths under
`https://api.cloudflare.com/client/v4`; require a successful response before
interpreting `result`. An authentication failure is not an empty inventory.

| GET path | What it establishes |
| --- | --- |
| `/accounts/{account_id}/pages/projects/{project}` | Existing project, canonical deployment and its source binding |
| `/accounts/{account_id}/pages/projects/{project}/domains` | Whether the exact hostname is associated with Pages |
| `/accounts/{account_id}/pages/projects/{project}/domains/{hostname}` | Domain activation/validation state |
| `/zones?name={hostname}` | Exact zone/account, assigned nameservers and zone activation state |
| `/zones/{zone_id}/dns_records` | DNS records in that zone, not what every resolver currently serves |
| `/zones/{zone_id}/dnssec` | Zone signing state and current DS data, not parent publication by itself |

A missing exact zone can explain an apex Pages failure. Preserve this result
and continue account-scoped inspection; the zone-oriented bundled diagnostic
scripts do not replace that inspection.

## Repair only the failed layer

For an authorized change, retain the prior delegation, relevant records and DS
for recovery. Preserve mail, verification and other unrelated records, contacts,
privacy and billing settings. Follow [Pages custom domains][pages]: an apex needs
a zone in the Pages account and its assigned nameservers; a subdomain can use an
external DNS provider. Associate the hostname with the existing Pages project;
a CNAME alone is insufficient. Check the resulting CNAME against the actual
project origin instead of duplicating it or using an example target.

A routing-only repair reuses a verified deployment. Rebuild or upload again only
when the deployed content/source is itself wrong.

Before moving signed delegation, follow [Cloudflare's DNSSEC migration][dnssec].
The ordinary path removes the old DS at the registrar, verifies parent removal
and waits out its prior TTL before switching nameservers. A saved deletion or an
empty local answer does not prove cached trust has expired. Active multi-signer
migration is a separate supported path when the old provider supports it; do not
mix the two sequences. After the new delegation activates and the prior NS TTL
expires, enable signing and
submit that zone's current DS at the registrar. Verify it on the public parent
and through a validating resolver. Restore an old DS only with its matching
authoritative DNSKEY; an application rollback does not repair delegation.

## Observe publication separately from caches

Registrar UI and RDAP may update before the registry publishes DNS. Consult that
registry's current schedule and the old record/negative-cache TTLs. Record the
next meaningful observation and use a bounded wait; do not repeatedly resubmit a
saved change or send unchanged progress messages. No universal propagation delay
replaces these observations.

Query an independently established parent nameserver address. For a template
domain, the read-only command shape is:

```sh
dig @<parent-nameserver-ip> example.com NS +norecurse +dnssec +comments +answer +authority
dig @<parent-nameserver-ip> example.com DS +norecurse +dnssec +comments +answer +authority
```

Inspect response status and authority as well as answers. A timeout or empty
stdout is unknown; signed denial can establish absence. `+dnssec` requests DNSSEC
records but does not validate the chain. Use a trusted validating resolver or
local validator for that separate result; a resolver's authenticated answer is
distinct from successful resolution without validation. With a TUN, public UDP
DNS may still be intercepted; compare an independent DoH path when results conflict.

## Accept the intended hostname

Require ordinary hostname GET and browser access with certificate checking,
without hosts overrides, `--resolve`, ignored certificate errors or a substitute
provider URL. Verify the intended page/content and affected assets, then exercise
the declared main journey. Reuse unchanged functional evidence rather than adding
a new design, device or performance audit.

If a fresh-IP diagnostic works while the original client still fails, keep that
client unresolved. Compare the same ordinary URL from another authorized client
when available; it distinguishes paths but does not prove the original recovered.
Use the installed network-diagnosis owner for local-path investigation. An HTTP
cache purge is not a DNS purge; a purge queued receipt is not proof of execution.
Do not restart a shared proxy simply because one newly migrated domain is stale.

Stop after the intended hostname, certificate, required journey and any changed
DNSSEC chain have positive evidence. Otherwise report the exact unresolved layer
and recovery observation, without marking the entire site or every client healed.

[pages]: https://developers.cloudflare.com/pages/configuration/custom-domains/
[dnssec]: https://developers.cloudflare.com/dns/dnssec/#migrate-to-cloudflare-with-dnssec-active
