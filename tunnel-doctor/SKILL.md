---
name: tunnel-doctor
description: Diagnose and fix conflicts between Tailscale and proxy/VPN tools (Shadowrocket, Clash, Surge) on macOS. Covers two conflict types - route hijacking (proxy TUN overrides Tailscale routes) and HTTP proxy env var interception (http_proxy/NO_PROXY misconfiguration). Use when Tailscale ping works but SSH/HTTP times out, when curl to Tailscale IPs returns empty/timeout, or when setting up Tailscale SSH to WSL instances.
allowed-tools: Read, Grep, Edit, Bash
---

# Tunnel Doctor

Diagnose and fix conflicts when Tailscale coexists with proxy/VPN tools on macOS, with specific guidance for SSH access to WSL instances.

## Diagnostic Workflow

### Step 1: Identify the Symptom

Determine which scenario applies:

- **Tailscale ping works, SSH works, but curl/HTTP times out** → HTTP proxy env var conflict (Step 2A)
- **Tailscale ping works, SSH/TCP times out** → Route conflict (Step 2B)
- **SSH connects but `operation not permitted`** → Tailscale SSH config issue (Step 4)
- **SSH connects but `be-child ssh` exits code 1** → WSL snap sandbox issue (Step 5)

**Key distinction**: SSH does NOT use `http_proxy`/`NO_PROXY` env vars, but curl/wget/Python requests/Node.js fetch do. If SSH works but HTTP doesn't, it's almost always a proxy env var issue, not a route issue.

### Step 2A: Fix HTTP Proxy Environment Variables

Check if proxy env vars are intercepting Tailscale HTTP traffic:

```bash
env | grep -i proxy
```

**Broken output** — proxy is set but `NO_PROXY` doesn't exclude Tailscale:
```
http_proxy=http://127.0.0.1:1082
https_proxy=http://127.0.0.1:1082
NO_PROXY=localhost,127.0.0.1          ← Missing Tailscale!
```

**Fix** — add Tailscale MagicDNS domain + CIDR to `NO_PROXY`:

```bash
export NO_PROXY=localhost,127.0.0.1,.ts.net,100.64.0.0/10,192.168.*,10.*,172.16.*
```

| Entry | Covers | Why |
|-------|--------|-----|
| `.ts.net` | MagicDNS domains (`host.tailnet.ts.net`) | Matched before DNS resolution |
| `100.64.0.0/10` | Tailscale IPs (`100.64.*` – `100.127.*`) | Precise CIDR, no public IP false positives |
| `192.168.*,10.*,172.16.*` | RFC 1918 private networks | LAN should never be proxied |

**Two layers complement each other**: `.ts.net` handles domain-based access, `100.64.0.0/10` handles direct IP access.

**NO_PROXY syntax pitfalls** — see [references/proxy_fixes.md](references/proxy_fixes.md) for the compatibility matrix.

Verify the fix:

```bash
# Both must return HTTP 200:
NO_PROXY="...(new value)..." curl -s --connect-timeout 5 http://<host>.ts.net:<port>/health -w "HTTP %{http_code}\n"
NO_PROXY="...(new value)..." curl -s --connect-timeout 5 http://<tailscale-ip>:<port>/health -w "HTTP %{http_code}\n"
```

Then persist in shell config (`~/.zshrc` or `~/.bashrc`).

### Step 2B: Detect Route Conflicts

Check if a proxy tool hijacked the Tailscale CGNAT range:

```bash
route -n get <tailscale-ip>
```

**Healthy output** — traffic goes through Tailscale interface:
```
destination: 100.64.0.0
interface: utun7    # Tailscale interface (utunN varies)
```

**Broken output** — proxy hijacked the route:
```
destination: 100.64.0.0
gateway: 192.168.x.1    # Default gateway
interface: en0           # Physical interface, NOT Tailscale
```

Confirm with full route table:

```bash
netstat -rn | grep 100.64
```

Two competing routes indicate a conflict:
```
100.64/10  192.168.x.1   UGSc  en0       ← Proxy added this (wins)
100.64/10  link#N        UCSI  utun7     ← Tailscale route (loses)
```

**Root cause**: On macOS, `UGSc` (Static Gateway) takes priority over `UCSI` (Cloned Static Interface) for the same prefix length.

### Step 3: Fix Proxy Tool Configuration

Identify the proxy tool and apply the appropriate fix. See [references/proxy_fixes.md](references/proxy_fixes.md) for detailed instructions per tool.

**Key principle**: Do NOT use `tun-excluded-routes` to exclude `100.64.0.0/10`. This causes the proxy to add a `→ en0` route that overrides Tailscale. Instead, let the traffic enter the proxy TUN and use a DIRECT rule to pass it through.

**Universal fix** — add this rule to any proxy tool:
```
IP-CIDR,100.64.0.0/10,DIRECT
IP-CIDR,fd7a:115c:a1e0::/48,DIRECT
```

After applying fixes, verify:

```bash
route -n get <tailscale-ip>
# Should show Tailscale utun interface, NOT en0
```

### Step 4: Configure Tailscale SSH ACL

If SSH connects but returns `operation not permitted`, the Tailscale ACL may require browser authentication for each connection.

At [Tailscale ACL admin](https://login.tailscale.com/admin/acls), ensure the SSH section uses `"action": "accept"`:

```json
"ssh": [
    {
        "action": "accept",
        "src": ["autogroup:member"],
        "dst": ["autogroup:self"],
        "users": ["autogroup:nonroot", "root"]
    }
]
```

**Note**: `"action": "check"` requires browser authentication each time. Change to `"accept"` for non-interactive SSH access.

### Step 5: Fix WSL Tailscale Installation

If SSH connects and ACL passes but fails with `be-child ssh` exit code 1 in tailscaled logs, the snap-installed Tailscale has sandbox restrictions preventing SSH shell execution.

**Diagnosis** — check WSL tailscaled logs:

```bash
# For snap installs:
sudo journalctl -u snap.tailscale.tailscaled -n 30 --no-pager

# For apt installs:
sudo journalctl -u tailscaled -n 30 --no-pager
```

Look for:
```
access granted to user@example.com as ssh-user "username"
starting non-pty command: [/snap/tailscale/.../tailscaled be-child ssh ...]
Wait: code=1
```

**Fix** — replace snap with apt installation:

```bash
# Remove snap version
sudo snap remove tailscale

# Install apt version
curl -fsSL https://tailscale.com/install.sh | sh

# Start with SSH enabled
sudo tailscale up --ssh
```

**Important**: The new installation may assign a different Tailscale IP. Check with `tailscale status --self`.

### Step 6: Verify End-to-End

Run a complete connectivity test:

```bash
# 1. Check route is correct
route -n get <tailscale-ip>

# 2. Test TCP connectivity
nc -z -w 5 <tailscale-ip> 22

# 3. Test SSH
ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no <user>@<tailscale-ip> 'echo SSH_OK && hostname && whoami'
```

All three must pass. If step 1 fails, revisit Step 3. If step 2 fails, check WSL sshd or firewall. If step 3 fails, revisit Steps 4-5.

## References

- [references/proxy_fixes.md](references/proxy_fixes.md) — Detailed fix instructions for Shadowrocket, Clash, and Surge
