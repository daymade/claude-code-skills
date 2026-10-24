# One hostname fails after a DNS move

The executing agent uses this branch when a newly moved hostname fails but other
sites work. It does not establish the multi-domain DIRECT split-brain pattern in
Step 2J and does not authorize a proxy restart, route edit or DNS override.

1. Preserve the original ordinary URL, failure and client path. Read the actual
   resolver/proxy configuration; a fake IP identifies TUN use, not corruption.
2. Separate saved registrar/provider state, authoritative parent NS/DS and public
   recursive answers. UDP DNS can be intercepted by the same TUN, so use an
   independent DoH or authorized client when it would resolve a disagreement.
   The hosting/DNS owner handles incorrect delegation, binding or DNSSEC.
3. Compare ordinary hostname access with a fresh-IP/SNI diagnostic. If only the
   diagnostic succeeds, do not mark the original path recovered or conclude the
   entire forwarding plane is broken. If available, use another already authorized
   machine for the same ordinary URL with normal certificate verification; retain
   its actual network path rather than imposing the failing client's configuration.
4. A remote ordinary-hostname success isolates a path difference; the exact local
   cache or proxy mechanism remains a hypothesis. Observe registry publication and
   relevant cache expiry before altering healthy shared services. Use a bounded
   observation tied to new state, not repeated configuration writes or cache-purge
   receipts. Do not claim that elapsed time or a queued purge caused recovery.
5. Recheck the original ordinary URL after a meaningful state change and inspect
   the actual browser page. Stop when that path works, or name its unresolved
   layer and required next observation. A working second client cannot close the
   first client's failure.

For a Cloudflare Pages hostname, use `cloudflare-troubleshooting`'s custom-domain
procedure if installed; otherwise follow the project's current hosting/registrar
authority. Do not require installing a new Skill or provisioning another test
machine just to inspect the existing path. Any necessary network intervention
retains the entry's existing authorization and recovery boundary.
