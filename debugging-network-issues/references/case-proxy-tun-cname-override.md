# Case Study: Proxy/TUN CNAME Rule Override (June 2026)

A client-side case where a browser failed to reach an authentication domain with `ERR_CONNECTION_CLOSED`, while other properties on the same vendor top-level domain worked fine. The investigation repeatedly looked like a rule-order problem, but the real cause was a CNAME-based rule override combined with a proxy node that could not resolve the target hostname to a working IP.

This case is the canonical teaching material for **client-side proxy/TUN misrouting**. Read it to learn how to test a proxy client as if it were another network hop, and why "I already added a PROXY rule at the top" is not always sufficient.

## Contents

- Symptom
- Environment
- Investigation timeline (with wrong turns)
- The decisive experiments
- Final root cause
- Fix pattern
- Post-mortem lessons

## Symptom

The user tries to open a login URL in the browser:

```
https://<auth-domain>/common/oauth2/v2.0/authorize?...
```

Browser shows:

```
This site can’t be reached
<auth-domain> unexpectedly closed the connection.
ERR_CONNECTION_CLOSED
```

- Reproducible every time in the browser.
- Other properties on the same top-level domain (e.g. `www.<vendor>.com`, `outlook.<vendor>.com`, search) load normally.
- The user has already added top-of-list PROXY rules for `<auth-domain>` and `<vendoronline>.com`.

## Environment

- Client: macOS, `<proxy-client>` running in TUN mode.
- Local HTTP proxy port: `<proxy-port>`.
- DNS returns a TUN-fake IP such as `198.18.0.x` for `<auth-domain>`.
- Default route sends most traffic through the `utun` interface.
- `<auth-domain>` CNAME chain ends in `<cname-suffix>` (e.g. `*.<cname-suffix>`).
- The proxy config contains a rule like `DOMAIN-SUFFIX,<cname-suffix>,DIRECT`.

## Investigation timeline (with wrong turns)

### Wrong turn 1: "Add a PROXY rule at the top"

The user adds:

```ini
DOMAIN,<auth-domain>,PROXY
DOMAIN-SUFFIX,<vendoronline>.com,PROXY
```

at the very top of the rule list. Symptom persists.

**Trap**: Assuming rule-order wins over CNAME-based matching. Many proxy clients evaluate the resolved CNAME against the rule list too; a more specific suffix rule for the CNAME target can override the original-domain rule.

### Wrong turn 2: "The proxy node must be broken for this domain"

Observation: `curl -x http://127.0.0.1:<proxy-port> https://<auth-domain>` returns `SSL_ERROR_SYSCALL` after the proxy tunnel is established.

Hypothesis: The current proxy node cannot reach `<auth-domain>`.

Evidence against: The same node reaches `www.<vendor>.com`, `outlook.<vendor>.com`, and the regional/local variant of the auth service without trouble.

**Trap**: Single-cause bias (Trap 5). The node is not universally broken; the path to this specific hostname is failing for a different reason.

### Decisive experiment 1: real IP vs hostname through the proxy

Resolve `<auth-domain>` via a public DoH endpoint through the proxy:

```bash
curl -sS -x http://127.0.0.1:<proxy-port> \
  'https://dns.google/resolve?name=<auth-domain>&type=A'
```

Result: one working A record `<working-ip>`.

Now test two proxy paths:

| Path | Command | Result |
|------|---------|--------|
| A | `curl -x http://127.0.0.1:<proxy-port> -I https://<auth-domain>` | `SSL_ERROR_SYSCALL` |
| B | `curl -x http://127.0.0.1:<proxy-port> -k -H 'Host: <auth-domain>' -I https://<working-ip>` | `HTTP/1.1 200 OK` |

Path B works. Path A fails. The proxy node can reach the IP; it fails only when it must resolve the hostname itself.

### Decisive experiment 2: direct vs TUN for the real IP

| Path | Command | Result |
|------|---------|--------|
| C | Force route to physical interface `en0`, then curl `<auth-domain>` | `Time to live exceeded` — local ISP cannot reach `<working-ip>` |
| D | Default route through TUN, curl to `<auth-domain>` with `/etc/hosts` mapped to `<working-ip>` | `HTTP/1.1 200 OK` |

Path D works because the TUN forwards the real-IP destination through the proxy node, which can reach it. Path C proves the local network alone cannot.

### Root-cause synthesis

Two conditions are both required:

1. **CNAME rule override**: `<auth-domain>` resolves to a CNAME matching `DOMAIN-SUFFIX,<cname-suffix>,DIRECT`. The proxy client classifies the connection as DIRECT and tries to send it out the local physical interface.
2. **Local network cannot reach the target IP**: The DIRECT path fails (`TTL exceeded` / connection reset).

Additionally, even when forced through the proxy, the proxy node's own DNS resolution for `<auth-domain>` returns an IP that does not work, while a public DoH query returns a working IP. So any fix must either:

- bypass the CNAME override **and** ensure the proxy does not rely on its own DNS, or
- route the traffic through the TUN with an explicit real-IP mapping so the proxy node connects by IP.

## Fix pattern

In `<proxy-client>` the working fix is:

1. Add a `[Host]` mapping so the client resolves the domain locally to the known-working IP instead of using the broken CNAME/proxy-DNS path:

```ini
[Host]
<auth-domain> = <working-ip>
```

2. Enable `use-local-host-item-for-proxy` so the proxy connection uses the mapped IP rather than the hostname:

```ini
[General]
use-local-host-item-for-proxy = true
```

3. Restart the proxy client and flush the OS DNS cache:

```bash
sudo dscacheutil -flushcache
```

Why this works: it bypasses both the CNAME-based rule override and the proxy node's faulty DNS. The proxy receives an IP destination it can reach, and the TLS SNI still contains `<auth-domain>` so the server returns the correct certificate.

## Post-mortem lessons

1. **Treat the proxy client as a network hop, not a black box.** Run the same logical request through multiple proxy paths: hostname-only, IP-only with SNI, no proxy via TUN, no proxy via physical interface. Differences between them isolate whether the problem is rule matching, proxy-node DNS, or local reachability.

2. **CNAME rules can override domain rules.** When a domain has a CNAME chain, check whether any suffix in that chain matches a rule with a different policy. "I put the target domain at the top" does not guarantee victory.

3. **Proxy-node DNS ≠ client DNS.** A client may resolve a working IP via DoH while the proxy node resolves a blocked or non-routable IP for the same hostname. Use `--resolve` / `Host:` header probes to separate DNS from reachability.

4. **Check interface reachability explicitly.** `curl` through a TUN can succeed while the same IP through the physical interface fails. Use `route -n get <ip>` and temporary interface routes to confirm which path can actually reach the target.

5. **Don’t trust ping latency blindly.** A real-IP ping returning `ttl=64` and sub-millisecond time may mean the TUN interface itself is replying or forwarding locally — it does not prove the target is physically close. Always cross-check with a non-TUN path.
