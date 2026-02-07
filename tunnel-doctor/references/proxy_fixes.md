# Proxy Tool Fix Reference

Detailed instructions for making each proxy tool coexist with Tailscale on macOS.

## Contents

- Shadowrocket (macOS ARM)
- Clash / ClashX Pro
- Surge
- NO_PROXY Environment Variable
- General Principles

## Shadowrocket (macOS ARM)

### The Problem

Shadowrocket's `tun-excluded-routes` adds a system route `100.64/10 → default gateway (en0)` for each excluded CIDR. This route has higher priority (`UGSc`) than Tailscale's route (`UCSI`), hijacking all Tailscale traffic.

### The Fix

1. **Remove** `100.64.0.0/10` from `tun-excluded-routes` in `[General]`
2. **Add** a DIRECT rule in `[Rule]` section:

```
IP-CIDR,100.64.0.0/10,DIRECT
```

This lets Tailscale traffic enter the Shadowrocket TUN interface, where the DIRECT rule passes it through without proxying. The system route table remains clean.

### Config API

Shadowrocket exposes a config editor API when the **Edit Plain Text** view is open:

```bash
# Read current config
NO_PROXY="<shadowrocket-ip>" curl -s "http://<shadowrocket-ip>:8080/api/read"

# Save updated config (replaces editor buffer)
NO_PROXY="<shadowrocket-ip>" curl -s -X POST "http://<shadowrocket-ip>:8080/api/save" --data-binary @config.txt
```

**Important**: The API `save` only writes to the editor buffer. The user must click **Save** in the Shadowrocket UI to persist changes. After saving, the VPN connection must be restarted for route changes to take effect.

### Example tun-excluded-routes (correct)

```
tun-excluded-routes = 10.0.0.0/8, 127.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12, 192.0.0.0/24, 192.0.2.0/24, 192.88.99.0/24, 192.168.0.0/16, 198.51.100.0/24, 203.0.113.0/24, 224.0.0.0/4, 255.255.255.255/32
```

Note: `100.64.0.0/10` is intentionally absent.

## Clash / ClashX Pro

### The Fix

Add Tailscale CIDRs to the rules section before `MATCH`:

```yaml
rules:
  - IP-CIDR,100.64.0.0/10,DIRECT
  - IP-CIDR,fd7a:115c:a1e0::/48,DIRECT
  # ... other rules ...
  - MATCH,PROXY
```

For Clash with TUN mode, also add to `tun.excluded-routes` (if TUN mode doesn't create conflicting system routes on macOS):

```yaml
tun:
  enable: true
  # Only if this doesn't create conflicting system routes:
  # excluded-routes:
  #   - 100.64.0.0/10
```

Test with `route -n get 100.x.x.x` after applying to confirm no `en0` hijack.

## Surge

### The Fix

Add to the `[Rule]` section:

```
IP-CIDR,100.64.0.0/10,DIRECT
IP-CIDR,fd7a:115c:a1e0::/48,DIRECT
```

In Surge's **TUN Excluded Routes** (if available), the same caveat applies as Shadowrocket: excluding `100.64.0.0/10` may add an `en0` route. Test with `route -n get` to confirm.

Surge also supports `skip-proxy` and `always-real-ip` which may help:

```
[General]
skip-proxy = 100.64.0.0/10, fd7a:115c:a1e0::/48
always-real-ip = *.ts.net
```

## NO_PROXY Environment Variable

### The Problem

Even when system routes are correct (Tailscale `utun` interface wins), HTTP clients like curl, Python requests, and Node.js fetch respect `http_proxy`/`https_proxy` env vars. If `NO_PROXY` doesn't exclude Tailscale addresses, HTTP traffic is sent to the proxy process, which may fail to reach `100.x` addresses.

This is a **different conflict layer** from route hijacking — routes are fine, but the application bypasses them by sending traffic to the local proxy port.

### The Fix

```bash
export NO_PROXY=localhost,127.0.0.1,.ts.net,100.64.0.0/10,192.168.*,10.*,172.16.*
```

### NO_PROXY Syntax Pitfalls

| Syntax | curl | Python requests | Node.js | Meaning |
|--------|------|-----------------|---------|---------|
| `.ts.net` | ✅ | ✅ | ✅ | Domain suffix match (correct) |
| `*.ts.net` | ❌ | ✅ | varies | Glob — curl does NOT support this |
| `100.64.0.0/10` | ✅ 7.86+ | ✅ 2.25+ | ❌ native | CIDR notation |
| `100.*` | ✅ | ✅ | ✅ | Too broad — covers public IPs `100.0-63.*` and `100.128-255.*` |

**Key rule**: Always use `.ts.net` (leading dot, no asterisk) for domain suffix matching. This is the most portable syntax across all HTTP clients.

### Why Not `100.*`?

`100.0.0.0/8` includes public IP space:
- `100.0.0.0 – 100.63.255.255` — **public** IPs
- `100.64.0.0 – 100.127.255.255` — CGNAT (Tailscale uses this)
- `100.128.0.0 – 100.255.255.255` — **public** IPs

Using `100.*` in `NO_PROXY` would bypass the proxy for services on public `100.x` IPs — potentially breaking access to GFW-blocked services that happen to use those addresses.

### MagicDNS Recommendation

Prefer accessing Tailscale devices by MagicDNS name (e.g., `my-server` or `my-server.tailnet.ts.net`) rather than raw IPs. This makes `.ts.net` in `NO_PROXY` the primary bypass mechanism, with `100.64.0.0/10` as a fallback for direct IP usage.

Check MagicDNS status:
```bash
tailscale dns status
```

## General Principles

### Why tun-excluded-routes Breaks Tailscale

On macOS, when a VPN tool excludes a CIDR from its TUN interface, it typically adds a system route pointing that CIDR to the default gateway via `en0`. For `100.64.0.0/10`:

```
100.64/10  192.168.x.1  UGSc  en0       ← VPN tool adds this
100.64/10  link#N       UCSI  utun7     ← Tailscale's route
```

macOS route priority: `UGSc` > `UCSI` for same prefix length. Result: Tailscale traffic goes to the router, which has no route to 100.x addresses.

### The Correct Approach

Let Tailscale traffic enter the VPN TUN interface, then use an application-layer DIRECT/bypass rule to send it out without proxying. This avoids polluting the system route table.

### Quick Verification

After any fix, always verify:

```bash
# Route should go through Tailscale utun, not en0
route -n get <tailscale-ip>

# Should show only one 100.64/10 route (Tailscale's)
netstat -rn | grep 100.64
```

### Emergency Rollback

If a proxy config change breaks other connectivity:

```bash
# Restart the proxy tool (Shadowrocket/Clash/Surge)
# This restores its default routes

# Or manually delete a conflicting route:
sudo route delete -net 100.64.0.0/10 <gateway-ip>
```
