---
name: tunnel-doctor
description: Diagnoses and fixes conflicts between Tailscale and proxy/VPN tools (Shadowrocket, Clash, Surge) on macOS. Covers four conflict layers - (1) route hijacking, (2) HTTP proxy env var interception, (3) system proxy bypass, and (4) SSH ProxyCommand double tunneling causing git push/pull failures. Includes SOP for remote development via SSH tunnels with proxy-safe Makefile patterns. Use when Tailscale ping works but SSH/HTTP times out, when browser returns 503 but curl works, when git push fails with "failed to begin relaying via HTTP", when setting up Tailscale SSH to WSL instances, or when bootstrapping remote dev environments over Tailscale.
allowed-tools: Read, Grep, Edit, Bash
---

# Tunnel Doctor

Diagnose and fix conflicts when Tailscale coexists with proxy/VPN tools on macOS, with specific guidance for SSH access to WSL instances.

## Four Conflict Layers

Proxy/VPN tools on macOS create conflicts at four independent layers. Layers 1-3 affect Tailscale connectivity; Layer 4 affects SSH git operations (same proxy environment, different target):

| Layer | What breaks | What still works | Root cause |
|-------|-------------|------------------|------------|
| 1. Route table | Everything (SSH, curl, browser) | `tailscale ping` | `tun-excluded-routes` adds `en0` route overriding Tailscale utun |
| 2. HTTP env vars | `curl`, Python requests, Node.js fetch | SSH, browser | `http_proxy` set without `NO_PROXY` for Tailscale |
| 3. System proxy (browser) | Browser only (HTTP 503) | SSH, `curl` (both with/without proxy) | Browser uses VPN system proxy; DIRECT rule routes via Wi-Fi, not Tailscale utun |
| 4. SSH ProxyCommand double tunnel | `git push/pull` (intermittent) | `ssh -T` (small data) | `connect -H` creates HTTP CONNECT tunnel redundant with Shadowrocket TUN; landing proxy drops large/long-lived transfers |

## Diagnostic Workflow

### Step 1: Identify the Symptom

Determine which scenario applies:

- **Browser returns HTTP 503, but `curl` and SSH both work** → System proxy bypass conflict (Step 2C)
- **Tailscale ping works, SSH works, but curl/HTTP times out** → HTTP proxy env var conflict (Step 2A)
- **Tailscale ping works, SSH/TCP times out** → Route conflict (Step 2B)
- **Remote dev server auth redirects to `localhost` → browser can't follow** → SSH tunnel needed (Step 2D)
- **`make status` / scripts curl to localhost fail with proxy** → localhost proxy interception (Step 2E)
- **`git push/pull` fails with `FATAL: failed to begin relaying via HTTP`** → SSH double tunnel (Step 2F)
- **SSH connects but `operation not permitted`** → Tailscale SSH config issue (Step 4)
- **SSH connects but `be-child ssh` exits code 1** → WSL snap sandbox issue (Step 5)

**Key distinctions**:
- SSH does NOT use `http_proxy`/`NO_PROXY` env vars. If SSH works but HTTP doesn't → Layer 2.
- `curl` uses `http_proxy` env var, NOT the system proxy. Browser uses system proxy (set by VPN). If `curl` works but browser doesn't → Layer 3.
- If `tailscale ping` works but regular `ping` doesn't → Layer 1 (route table corrupted).
- If `ssh -T git@github.com` works but `git push` fails intermittently → Layer 4 (double tunnel).

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

**NO_PROXY syntax pitfalls** — see [references/proxy_conflict_reference.md](references/proxy_conflict_reference.md) for the compatibility matrix.

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

### Step 2C: Fix System Proxy Bypass (Browser 503)

**Symptom**: Browser shows HTTP 503 for `http://<tailscale-ip>:<port>`, but both `curl --noproxy '*'` and `curl` (with proxy env var) return 200. SSH also works.

**Root cause**: The browser uses the system proxy configured by the VPN profile (Shadowrocket/Clash/Surge). The proxy matches `IP-CIDR,100.64.0.0/10,DIRECT` and tries to connect directly — but "directly" means via the Wi-Fi interface (en0), NOT through Tailscale's utun interface. The proxy process itself doesn't have a route to Tailscale IPs, so the connection fails with 503.

**Diagnosis**:

```bash
# curl with proxy env var works (curl connects to proxy port, but traffic flows differently)
curl -s -o /dev/null -w "%{http_code}" http://<tailscale-ip>:<port>/
# → 200

# Browser gets 503 because it goes through the VPN system proxy, not http_proxy env var
```

**Fix** — add Tailscale CGNAT range to `skip-proxy` in the proxy tool config:

For Shadowrocket, in `[General]`:
```
skip-proxy = 192.168.0.0/16, 10.0.0.0/8, 172.16.0.0/12, 100.64.0.0/10, localhost, *.local, captive.apple.com
```

`skip-proxy` tells the system "bypass the proxy entirely for these addresses." The browser then connects directly through the OS network stack, where Tailscale's routing table correctly handles the traffic.

**Why `skip-proxy` works but `tun-excluded-routes` doesn't**:
- `skip-proxy`: Bypasses the HTTP proxy layer only. Traffic still flows through the TUN interface and Tailscale utun handles it. Safe.
- `tun-excluded-routes`: Removes the CIDR from the TUN routing entirely. This creates a competing `en0` route that overrides Tailscale. Breaks everything.

### Step 2D: Fix Auth Redirect for Remote Dev (SSH Tunnel)

**Symptom**: Dev server runs on a remote machine (e.g., Mac Mini via Tailscale). You access `http://<tailscale-ip>:3010` in the browser. Login/signup works, but after auth, the app redirects to `http://localhost:3010/` which fails — `localhost` on your machine isn't running the dev server.

**Root cause**: The app's `APP_URL` (or equivalent) is set to `http://localhost:3010`. Auth libraries (Better-Auth, NextAuth, etc.) use this URL for callback redirects. Changing `APP_URL` to the Tailscale IP introduces Shadowrocket proxy conflicts and breaks local development on the remote machine.

**Fix** — SSH local port forwarding. This avoids all three conflict layers entirely:

```bash
# Forward local port 3010 to remote machine's localhost:3010
ssh -NL 3010:localhost:3010 <tailscale-ip>

# Or with autossh for auto-reconnect (recommended for long sessions)
autossh -M 0 -f -N -L 3010:localhost:3010 \
    -o "ServerAliveInterval=30" \
    -o "ServerAliveCountMax=3" \
    -o "ExitOnForwardFailure=yes" \
    <tailscale-ip>
```

Now access `http://localhost:3010` in the browser. Auth redirects to `localhost:3010` → tunnel → remote dev server → works correctly.

**Why this is the best approach**:
- No `.env` changes needed — `APP_URL=http://localhost:3010` works everywhere
- No Shadowrocket conflicts — `localhost` is always in `skip-proxy`
- No code changes — same behavior as local development
- Industry standard — VS Code Remote SSH, GitHub Codespaces use the same pattern

**Install autossh**: `brew install autossh` (macOS) or `apt install autossh` (Linux)

**Kill background tunnel**: `pkill -f 'autossh.*<tailscale-ip>'`

### Step 2E: Fix localhost Proxy Interception in Scripts

**Symptom**: Makefile targets or scripts that `curl` localhost (health checks, warmup routes) fail or timeout when `http_proxy` is set globally in the shell.

**Root cause**: `http_proxy=http://127.0.0.1:1082` is set in `~/.zshrc` but `no_proxy` doesn't include `localhost`. All curl commands send localhost requests through the proxy.

**Fix** — add `--noproxy localhost` to all localhost curl commands in scripts:

```makefile
# WRONG — fails when http_proxy is set
@curl -sf http://localhost:9000/minio/health/live && echo "OK"

# CORRECT — always bypasses proxy for localhost
@curl --noproxy localhost -sf http://localhost:9000/minio/health/live && echo "OK"
```

Alternatively, set `no_proxy` globally in `~/.zshrc`:

```bash
export no_proxy=localhost,127.0.0.1
```

### Step 2F: Fix SSH ProxyCommand Double Tunnel (git push/pull failures)

**Symptom**: `ssh -T git@github.com` succeeds consistently, but `git push` or `git pull` fails intermittently with:

```
FATAL: failed to begin relaying via HTTP.
Connection closed by UNKNOWN port 65535
```

Small operations (auth, fetch metadata) work; large data transfers fail.

**Root cause**: When Shadowrocket TUN is active, it already routes all TCP traffic through its VPN tunnel. If SSH config also uses `ProxyCommand connect -H`, data flows through two proxy layers — the landing proxy drops large/long-lived HTTP CONNECT connections.

**Diagnosis**:

```bash
# 1. Confirm Shadowrocket TUN is active
ifconfig | grep '^utun'

# 2. Check SSH config for ProxyCommand
grep -A5 'Host github.com' ~/.ssh/config

# 3. Confirm: removing ProxyCommand fixes push
GIT_SSH_COMMAND="ssh -o ProxyCommand=none" git push origin main
```

**Fix** — remove ProxyCommand and switch to `ssh.github.com:443`. See [references/proxy_conflict_reference.md § SSH ProxyCommand and Git Operations](references/proxy_conflict_reference.md) for the full SSH config, why port 443 helps, and fallback options when VPN is off.

### Step 3: Fix Proxy Tool Configuration

Identify the proxy tool and apply the appropriate fix. See [references/proxy_conflict_reference.md](references/proxy_conflict_reference.md) for detailed instructions per tool.

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

## SOP: Remote Development via Tailscale

Proactive setup guide for remote development over Tailscale with proxy tools. Follow these steps **before** encountering problems.

### Prerequisites

- Tailscale installed and running on both machines
- Proxy tool (Shadowrocket/Clash/Surge) configured with Tailscale compatibility (see Step 3 above)
- SSH access working: `ssh <tailscale-ip> 'echo ok'`

### 1. Proxy-Safe Makefile Pattern

Any Makefile target that curls `localhost` must use `--noproxy localhost`. This is required because `http_proxy` is often set globally in `~/.zshrc` (common in China), and Make inherits shell environment variables.

```makefile
## ── Health Checks ─────────────────────────────────────

status:                ## Health check dashboard
	@echo "=== Dev Infrastructure ==="
	@docker exec my-postgres pg_isready -U postgres 2>/dev/null && echo "PostgreSQL: OK" || echo "PostgreSQL: FAIL"
	@curl --noproxy localhost -sf http://localhost:9000/minio/health/live >/dev/null 2>&1 && echo "MinIO: OK" || echo "MinIO: FAIL"
	@curl --noproxy localhost -sf http://localhost:3001/api/status >/dev/null 2>&1 && echo "API: OK" || echo "API: FAIL"

## ── Route Warmup ──────────────────────────────────────

warmup:                ## Pre-compile key routes (run after dev server is ready)
	@echo "Warming up dev server routes..."
	@echo -n "  /api/health → " && curl --noproxy localhost -s -o /dev/null -w '%{http_code} (%{time_total}s)\n' http://localhost:3010/api/health
	@echo -n "  /            → " && curl --noproxy localhost -s -o /dev/null -w '%{http_code} (%{time_total}s)\n' http://localhost:3010/
	@echo "Warmup complete."
```

**Rules**:
- Every `curl http://localhost` call MUST include `--noproxy localhost`
- Docker commands (`docker exec`) are unaffected by `http_proxy` — no fix needed
- `redis-cli`, `pg_isready` connect via TCP directly — no fix needed

### 2. SSH Tunnel Makefile Targets

Add these targets for remote development via Tailscale SSH tunnels:

```makefile
## ── Remote Development ────────────────────────────────

REMOTE_HOST    ?= <tailscale-ip>
TUNNEL_FORWARD ?= -L 3010:localhost:3010

tunnel:                ## SSH tunnel to remote machine (foreground)
	ssh -N $(TUNNEL_FORWARD) $(REMOTE_HOST)

tunnel-bg:             ## SSH tunnel to remote machine (background, auto-reconnect)
	autossh -M 0 -f -N $(TUNNEL_FORWARD) \
		-o "ServerAliveInterval=30" \
		-o "ServerAliveCountMax=3" \
		-o "ExitOnForwardFailure=yes" \
		$(REMOTE_HOST)
	@echo "Tunnel running in background. Kill with: pkill -f 'autossh.*$(REMOTE_HOST)'"
```

**Design decisions**:

| Choice | Rationale |
|--------|-----------|
| `?=` (conditional assign) | Allows override: `make tunnel REMOTE_HOST=100.x.x.x` |
| `TUNNEL_FORWARD` as variable | Supports multi-port: `make tunnel TUNNEL_FORWARD="-L 3010:localhost:3010 -L 9000:localhost:9000"` |
| `autossh -M 0` | Disables autossh's own monitoring port; relies on `ServerAliveInterval` instead (more reliable through NAT) |
| `ExitOnForwardFailure=yes` | Fails immediately if port is already bound, instead of silently running without tunnel |
| Kill hint uses `autossh.*$(REMOTE_HOST)` | Precise pattern — won't accidentally kill other SSH sessions |

**Install autossh**: `brew install autossh` (macOS) or `apt install autossh` (Linux/WSL)

### 3. Multi-Port Tunnels

When the project requires multiple services (dev server + object storage + API gateway):

```bash
# Forward multiple ports in one tunnel
make tunnel TUNNEL_FORWARD="-L 3010:localhost:3010 -L 9000:localhost:9000 -L 3001:localhost:3001"

# Or define a project-specific default in Makefile
TUNNEL_FORWARD ?= -L 3010:localhost:3010 -L 9000:localhost:9000
```

Each `-L` flag is independent. If one port is already bound locally, `ExitOnForwardFailure=yes` will abort the entire tunnel — fix the port conflict first.

### 4. SSH Non-Login Shell Setup

SSH non-login shells don't load `~/.zshrc`, so nvm/Homebrew tools and proxy env vars are unavailable. Prefix all remote commands with `source ~/.zshrc 2>/dev/null;`. See [references/proxy_conflict_reference.md § SSH Non-Login Shell Pitfall](references/proxy_conflict_reference.md) for details and examples.

For Makefile targets that run remote commands:

```makefile
REMOTE_CMD = ssh $(REMOTE_HOST) 'source ~/.zshrc 2>/dev/null; $(1)'

remote-status:         ## Check remote dev server status
	$(call REMOTE_CMD,curl --noproxy localhost -sf http://localhost:3010/api/health && echo "OK" || echo "FAIL")
```

### 5. End-to-End Workflow

#### First-time setup (remote machine)

```bash
# 1. Clone repo and install dependencies
ssh <tailscale-ip>
cd /path/to/project
git clone git@github.com:user/repo.git && cd repo
pnpm install  # Add --registry https://registry.npmmirror.com if in China

# 2. Copy .env from local machine (run on local)
scp .env <tailscale-ip>:/path/to/project/repo/.env

# 3. Start Docker infrastructure
make up && make status

# 4. Run database migrations
bun run db:migrate

# 5. Start dev server
bun run dev
```

#### Daily workflow (local machine)

```bash
# 1. Start tunnel
make tunnel-bg

# 2. Open browser
open http://localhost:3010

# 3. Auth, coding, testing — everything works as if local

# 4. When done, kill tunnel
pkill -f 'autossh.*<tailscale-ip>'
```

#### Why this works

```
Browser → localhost:3010 → SSH tunnel → Remote localhost:3010 → Dev server
                                     ↓
                              Auth redirects to localhost:3010
                                     ↓
                              Browser follows redirect → same tunnel → works
```

The key insight: `APP_URL=http://localhost:3010` in `.env` is correct for **both** local and remote development. The SSH tunnel makes the remote server's localhost accessible as the local machine's localhost. Auth callback redirects to `localhost:3010` always resolve correctly.

### 6. Checklist

Before starting remote development, verify:

- [ ] Tailscale connected: `tailscale status`
- [ ] SSH works: `ssh <tailscale-ip> 'echo ok'`
- [ ] Proxy tool configured: `[Rule]` has `IP-CIDR,100.64.0.0/10,DIRECT`
- [ ] `skip-proxy` includes `100.64.0.0/10`
- [ ] `tun-excluded-routes` does NOT include `100.64.0.0/10`
- [ ] `NO_PROXY` includes `.ts.net,100.64.0.0/10`
- [ ] `autossh` installed: `which autossh`
- [ ] Makefile curl commands have `--noproxy localhost`
- [ ] Remote dev server running: `ssh <ip> 'source ~/.zshrc 2>/dev/null; curl --noproxy localhost -sf http://localhost:3010/'`
- [ ] Tunnel works: `make tunnel-bg && curl -sf http://localhost:3010/`

## References

- [references/proxy_conflict_reference.md](references/proxy_conflict_reference.md) — Per-tool configuration (Shadowrocket, Clash, Surge), NO_PROXY syntax, SSH ProxyCommand, and conflict architecture
