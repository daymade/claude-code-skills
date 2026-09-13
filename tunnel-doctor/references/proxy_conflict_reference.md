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

### The Fix (Three Settings)

Three Shadowrocket settings work together to handle Tailscale traffic correctly:

#### 1. `[Rule]` — Add DIRECT rule (handles TUN-level routing)

```
IP-CIDR,100.64.0.0/10,DIRECT
```

This lets Tailscale traffic enter the Shadowrocket TUN interface, where the DIRECT rule passes it through without proxying. The system route table remains clean.

#### 2. `skip-proxy` — Add Tailscale CGNAT range (fixes browser 503)

In `[General]`, add `100.64.0.0/10` to `skip-proxy`:

```
skip-proxy = 192.168.0.0/16, 10.0.0.0/8, 172.16.0.0/12, 100.64.0.0/10, localhost, *.local, captive.apple.com
```

**Why this is needed**: Browsers (Chrome, Safari) use the system proxy set by the VPN profile, not `http_proxy` env vars. Without `skip-proxy`, the browser sends Tailscale requests to Shadowrocket's proxy process. The DIRECT rule tells the proxy to connect "directly" — but the proxy connects via Wi-Fi (en0), not Tailscale's utun, resulting in HTTP 503.

With `skip-proxy`, the system bypasses the proxy entirely for these IPs. The browser connects through the normal OS network stack where Tailscale's routing works correctly.

#### 3. `tun-excluded-routes` — Do NOT add `100.64.0.0/10`

**Never** add `100.64.0.0/10` to `tun-excluded-routes`. This breaks Tailscale completely:
- Shadowrocket adds `100.64/10 → en0 (UGSc)` to the system route table
- This overrides Tailscale's `100.64/10 → utun (UCSI)` route
- Result: `tailscale ping` works (Tailscale-layer), but SSH, ping, curl, browser all fail (OS-layer)
- Reverting and restarting Shadowrocket VPN restores the routes

### Config API

Shadowrocket exposes a config editor API when the **Edit Plain Text** view is open:

```bash
# Read current config
NO_PROXY="<shadowrocket-ip>" curl -s "http://<shadowrocket-ip>:8080/api/read"

# Save updated config (replaces editor buffer)
NO_PROXY="<shadowrocket-ip>" curl -s -X POST "http://<shadowrocket-ip>:8080/api/save" --data-binary @config.txt
```

**Detect Shadowrocket IP**: The device IP changes with DHCP. Do not hardcode it. Detect it before use:

```bash
# If you know the device is on the same subnet
# Check common ports or use mDNS
curl --noproxy '*' -s --connect-timeout 2 "http://192.168.31.110:8080/api/read" | head -1
```

**Port conflict warning**: Shadowrocket's config API listens on port 8080 by default, which may conflict with other services (e.g., whisper.cpp server, development proxies). If the API returns unexpected content (HTML, JSON from another service), verify what is actually listening on the port:

```bash
lsof -nP -iTCP:8080 | head -5
```

If another service owns port 8080, you need to either stop that service or access the Shadowrocket API from a different device on the same network.

**Critical**: Use `--data-binary`, NOT `-d`. The `-d` flag URL-encodes the content, corrupting `#`, `=`, `&` and other characters in the config. This **destroys the entire configuration** — all rules, settings, and proxy groups are lost. The user must restore from backup.

```bash
# CORRECT — preserves raw content
curl -s -X POST "http://<ip>:8080/api/save" --data-binary @config.txt

# WRONG — URL-encodes special chars, destroys config
curl -s -X POST "http://<ip>:8080/api/save" -d @config.txt
```

**Important**: The API `save` only writes to the editor buffer. The user must click **Save** in the Shadowrocket UI to persist changes. After saving, the VPN connection must be restarted for route changes to take effect.

**API lifecycle and exposure** (verified 2026-09-13, macOS Catalyst build): the API listens on `*:8080` — **all interfaces, so the whole LAN can read *and* rewrite the proxy config while it is up** — and exists only while the Edit Plain Text view is open. Leaving that view (back button) stops the listener. Never leave the editor open unattended; verify shutdown with `lsof -nP -iTCP:8080 -sTCP:LISTEN` (expect zero rows). `api/read` returns the editor buffer with a `# Shadowrocket: <timestamp>` header line, so it reflects unsaved edits, not necessarily the on-disk config.

### Direct database writes (default.db) — when the GUI is not an option

The live config on macOS is a SQLite FTS3 table, not the `.conf` text (the text is an export view):

```
~/Library/Containers/com.liguangming.Shadowrocket/Data/Documents/Databases/default.db
  table config(section, name, value, option, ext, remarks, created)
```

Rules match in **ascending rowid order**; `FINAL` sits at the highest rowid. An `INSERT` lands *after* FINAL and never matches — to add rules you must renumber: insert your rows, `DELETE` the trailing `# China`/`GEOIP`/`# Final`/`FINAL` rows, then re-insert them so they come last. The compiled product the tunnel consumes lives at `~/Library/Group Containers/group.com.liguangming.Shadowrocket/rule.db` (NSKeyedArchiver bplists per config section) — parse it to confirm what the app actually accepted.

Contract for safe writes:

1. `osascript -e 'quit app "Shadowrocket"'` first — a running app holds its own copy and will overwrite the db on exit.
2. Write with a transaction; back up `default.db` first.
3. Relaunch the app, then reconnect the tunnel (`shadowrocket://disconnect` / `shadowrocket://connect`) — a tunnel that survived the app quit keeps the old config.
4. **Subscription refresh (`DLWSubscribeAutoUpdateKey = true` by default) wipes direct db writes.** Direct writes are for one-shot experiments or need a replay script; durable rule injection belongs in modules (below).

5. **Writes to default.db do NOT reach the tunnel by themselves** (verified 2026-09-13): the tunnel consumes compiled products, and the app only regenerates them on its own events. Deleting `rule.db` yields **zero** routes (it is a config source, not a rebuildable cache). After direct db writes the app must be made to recompile — see the pipeline below.

**Compile pipeline, mapped by lsof + byte-level forensics (2026-09-13 evening):**

- The tunnel process (`MacPacketTunnel.appex`) **mmap's `~/Library/Group Containers/group.com.liguangming.Shadowrocket/default.db.rule`** — an `XDAT`-magic binary decision table used for domain/rule matching. `tun-excluded-routes` CIDRs are **not** in it (byte-pattern search finds none of them).
- The excluded routes come from `rule.db` → table `rule` → row `key='general'` → NSKeyedArchiver bplist → `tun-excluded-routes` string array. The route table (`netstat -rn` `UGSc en0` entries) tracks exactly this array. The `ipcidr` table's `policy=2891846` group mirrors the same set, but editing it alone injected **nothing** — the bplist array is the load-bearing copy.
- **On this Catalyst build every GUI compile trigger failed**: double-clicking or keyboard-selecting **Compile Config** (click selects the row; Enter/Space bounce back to Home with no recompile), **Edit Plain Text**'s `api/save` (the editor is an embedded WKWebView CodeMirror page on `*:8080`; its web Save button *is* `POST /api/save`, which writes only the web session buffer — `default.db` mtime unchanged, no recompile), and subscription refresh (`shadowrocket://update-subs`) all left `default.db.rule`'s mtime untouched.
- **What works instead: patch `rule.db`'s `general` bplist directly, then quit+relaunch the app.** Append new segment strings to the archiver's `$objects` tail (never renumber — append-only keeps existing UIDs valid), swap the array's `NS.objects` UID list, re-serialize with `plistlib.dumps(..., FMT_BINARY)`. Relaunch + reconnect injected all 103 segments (99 `UGSc en0` routes verified; earlier failures had edited the bplist *without* the app restart — the running app/tunnel keep their own copies). The app did **not** overwrite the patched `rule.db` on launch. A ready-made implementation is `~/scripts/shadowrocket-splitting/replay.sh` step 2.5.
- Verify with `netstat -rn -f inet | grep -c 'UGSc.*en0'` (count ≈ segments minus a few overlapping system routes) and spot-check new CIDRs as `^<a.b.c>/24` (netstat prints them **without** the trailing `.0`).

### Local modules (.sgmodule) — the durable injection point

Local module files live at `~/Library/Containers/com.liguangming.Shadowrocket/Data/Documents/Modules/*.sgmodule` and are picked up from that directory without any plist registration (`DLWModuleManager` staying empty is normal). `[Rule]` entries in a module do apply; **`[General]` keys in a module are silently ignored** (verified 2026-09-13: `always-real-ip`/`tun-excluded-routes` in a module had no runtime effect while the same keys in the config body worked). Survive subscription refreshes; stack-safe way to ship DIRECT rules.

### Per-app traffic splitting on macOS — what can and cannot escape the TUN

Goal shape: "app X's traffic should not touch the metered proxy (and ideally not even the TUN/status-bar counters)". Three mechanisms stack, and they operate at different layers:

| Mechanism | Layer | Effect | Limit |
|---|---|---|---|
| `[Rule]` DIRECT (config body or module) | policy | zero proxy cost, traffic forwarded by the tunnel directly | still traverses TUN → still counted in the status-bar speed |
| `tun-excluded-routes` += app CIDRs | route table | packets to those CIDRs never enter the TUN; status bar silent | only catches packets whose destination IP is the real CDN IP **at connect time** |
| `always-real-ip` / `fake-ip-filter` | DNS answer | would return real IPs so excluded-routes can catch them | **non-functional on the macOS Catalyst build** (see below) |

The decisive variable is **how the app resolves** its download/upload hosts:

- **Apps that connect to literal IPs** (e.g. BaiduNetdisk's downloader, which gets CDN IPs from its dispatch API and never asks the system resolver): packets carry real destination IPs, so `tun-excluded-routes` catches them at the route layer. Verified working: 90+ tunnel-forwarded connections to its CDN ranges dropped to zero after exclusion; the status bar went silent during active downloads.
- **Apps that use the system resolver** (Feishu/Lark and most): they receive fake IPs (`198.18.0.0/15`) — under this TUN *every* domain resolves to a fake IP, including DIRECT-ruled ones, so `dig` cannot discriminate policy. The packet enters the TUN with a fake destination, excluded-routes never match, and the tunnel forwards post-resolution. For these apps the status bar always counts.

`always-real-ip` / `fake-ip-filter` would close this gap, but on the macOS Catalyst build they are accepted by the config layer and inert at runtime — verified dead via four independent paths: module `[General]`, direct db writes with three syntax variants, the official Edit Plain Text API + GUI Save chain, and the absence of any Fake IP settings page (the `DLWFakeIPViewController` in the binary is iOS-only). Until a build ships them working, the only way to silence the status bar for a system-resolver app is to disconnect the VPN during its bulk transfer.

**Instruments that tell the truth on this machine:**

```bash
# Which form an app's traffic takes: fake-IP (system resolver) vs real-IP (literal connect)
lsof -nP -iTCP -a -p <pid> | grep ESTABLISHED    # destination column: 198.18.x vs real

# Split-brain-proof per-policy throughput (status bar shows the SUM of these two):
plutil -p ~/Library/Group\ Containers/group.com.liguangming.Shadowrocket/NetworkUsage
#   directInPerBytes + proxyInPerBytes == inPerBytes (exactly) — DIRECT traffic IS counted.

# What the tunnel is forwarding where (DIRECT forwarding shows as real-IP sockets owned by the tunnel):
lsof -nP -iTCP -a -p $(pgrep -f MacPacketTunnel) | grep ESTABLISHED
```

### Example tun-excluded-routes (correct)

```
tun-excluded-routes = 10.0.0.0/8, 127.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12, 192.0.0.0/24, 192.0.2.0/24, 192.88.99.0/24, 192.168.0.0/16, 198.51.100.0/24, 203.0.113.0/24, 224.0.0.0/4, 255.255.255.255/32
```

Note: `100.64.0.0/10` is intentionally absent.

### Complete Working Reference Config for Tailscale Compatibility

This is a validated reference showing the correct relationship between `skip-proxy`, `tun-excluded-routes`, and `[Rule]` for Tailscale coexistence:

```
[General]
# skip-proxy: bypass the HTTP proxy for these destinations (fixes browser 503)
# 100.64.0.0/10 MUST be here for browser access to Tailscale IPs
skip-proxy = 192.168.0.0/16, 10.0.0.0/8, 172.16.0.0/12, 100.64.0.0/10, localhost, *.local, captive.apple.com

# tun-excluded-routes: CIDRs excluded from TUN routing (sent directly via physical interface)
# 100.64.0.0/10 must NOT be here — including it creates an en0 route that overrides Tailscale
tun-excluded-routes = 10.0.0.0/8, 127.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12, 192.0.0.0/24, 192.0.2.0/24, 192.88.99.0/24, 192.168.0.0/16, 198.51.100.0/24, 203.0.113.0/24, 224.0.0.0/4, 255.255.255.255/32

[Rule]
# Tailscale traffic enters TUN but is passed through without proxying
IP-CIDR,100.64.0.0/10,DIRECT
# ... other rules ...
```

**Key points**:
- `skip-proxy` — YES, include `100.64.0.0/10` (browser bypass)
- `tun-excluded-routes` — NO, never include `100.64.0.0/10` (would hijack routing)
- `[Rule]` — YES, include `IP-CIDR,100.64.0.0/10,DIRECT` (TUN passthrough)

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

Surge also supports `skip-proxy` and `always-real-ip`. Adding `skip-proxy` is **required** to fix browser 503 (same mechanism as Shadowrocket):

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

| Syntax | curl | Python requests | Go `net/http` | Node.js | Meaning |
|--------|------|-----------------|---------------|---------|---------|
| `.ts.net` | ✅ | ✅ | ✅ | ✅ | Domain suffix match (correct) |
| `*.ts.net` | ❌ | ✅ | ❌ | varies | Glob — curl and Go do NOT support this |
| `100.64.0.0/10` | ✅ 7.86+ | ✅ 2.25+ | ❌ | ❌ native | CIDR notation — Go silently ignores it |
| `100.*` | ✅ | ✅ | ❌ | ✅ | Too broad — covers public IPs `100.0-63.*` and `100.128-255.*` |
| `workstation-name` | ✅ | ✅ | ✅ | ✅ | Exact hostname match (safest for Go) |

**Go `net/http` warning**: Go's proxy bypass logic (`httpproxy.Config.ProxyFunc`) does not implement CIDR matching. `NO_PROXY=100.64.0.0/10` is silently ignored — Go programs will still route traffic through the proxy. Use MagicDNS hostnames (e.g., `my-wsl-box`) or explicit IPs (e.g., `100.101.102.103`) instead of CIDR ranges when Go programs need to bypass the proxy.

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

## SSH ProxyCommand and Git Operations

### The Problem

Many developers in China configure SSH with `ProxyCommand connect -H 127.0.0.1:<port>` to tunnel SSH through their HTTP proxy. This works fine for interactive SSH and small operations. But when Shadowrocket (or Clash/Surge) runs in TUN mode, this creates a **double tunnel**:

1. `connect -H` creates an HTTP CONNECT tunnel to the local proxy port
2. Shadowrocket TUN captures the same traffic at the system level

The landing proxy sees a long-lived HTTP CONNECT connection and may drop it during large data transfers (`git push`, `git clone` of large repos).

### Data Flow Comparison

```
Double tunnel (broken):
SSH → connect -H (HTTP CONNECT tunnel) → Shadowrocket local port 1082
                                          → Shadowrocket TUN → landing proxy → GitHub

Single tunnel (correct):
SSH → system network stack → Shadowrocket TUN → landing proxy → GitHub
```

The HTTP CONNECT tunnel adds protocol framing overhead. The landing proxy (落地代理) sees a long-lived HTTP CONNECT connection and may apply aggressive timeouts or buffer limits, dropping the connection during large transfers.

### Detecting TUN Mode

```bash
# If utun interfaces exist (other than Tailscale's), a VPN TUN is active
ifconfig | grep '^utun'
```

If Shadowrocket/Clash/Surge TUN is active, `ProxyCommand connect -H` is redundant.

### The Fix — SSH over Port 443 without ProxyCommand

```bash
# 1. Add ssh.github.com host key
ssh-keyscan -p 443 ssh.github.com >> ~/.ssh/known_hosts

# 2. Update ~/.ssh/config
```

```
Host github.com
    HostName ssh.github.com
    Port 443
    User git
    # No ProxyCommand — Shadowrocket TUN handles routing at the system level.
    # Port 443 gets longer timeouts from landing proxies than port 22.
    ServerAliveInterval 60
    ServerAliveCountMax 3
    IdentityFile ~/.ssh/id_ed25519
```

### Why Port 443

HTTP proxies (and landing proxies) are optimized for port 443 traffic:
- **Longer connection timeouts**: HTTPS connections are expected to be long-lived (WebSocket, streaming, large file downloads)
- **Larger buffer limits**: Proxies allocate more resources for 443 traffic
- **No protocol inspection**: Port 22 may trigger deep packet inspection on some proxies; 443 is treated as opaque TLS

GitHub officially supports SSH on port 443 via `ssh.github.com` — it's the same service, same authentication, different port.

### Fallback When VPN Is Off

Without Shadowrocket TUN, SSH can't reach GitHub directly from China. Options:

1. **Keep old config as comment** — manually uncomment ProxyCommand when needed
2. **Use Match directive** — conditionally apply ProxyCommand (advanced):

```
Host github.com
    HostName ssh.github.com
    Port 443
    User git
    ServerAliveInterval 60
    ServerAliveCountMax 3
    IdentityFile ~/.ssh/id_ed25519

# Uncomment when Shadowrocket is off:
#   ProxyCommand /opt/homebrew/bin/connect -H 127.0.0.1:1082 %h %p
```

### Verification

```bash
# Auth test
ssh -T git@github.com
# → Hi username! You've successfully authenticated...

# Verbose — confirm ssh.github.com:443
ssh -v -T git@github.com 2>&1 | grep 'Connecting to'
# → Connecting to ssh.github.com [20.205.243.160] port 443.

# Large transfer test
cd /path/to/repo && git push origin main
```

### Performance Trade-off

Connection setup is slightly slower (~6s vs ~2s) because TUN routing has more network hops than a direct HTTP CONNECT tunnel. Actual data transfer speed is the same (bottlenecked by bandwidth, not connection setup).

## General Principles

### Conflict Layers

Proxy tools create conflicts at several independent layers on macOS. Layers 1-3 affect Tailscale connectivity; Layer 4 affects SSH git operations; Layer 5 affects VM/container runtimes:

| Layer | Setting | What it controls | Symptom when wrong |
|-------|---------|------------------|--------------------|
| 1. Route table | `tun-excluded-routes` | OS-level IP routing | Everything broken (SSH, curl, browser). `tailscale ping` works but `ping` doesn't |
| 2. HTTP env vars | `http_proxy` / `NO_PROXY` | CLI tools (curl, wget, Python, Node.js) | `curl` times out, SSH works, browser works |
| 3. System proxy | `skip-proxy` | Browser and system HTTP clients | Browser 503, `curl` works (both with/without proxy), SSH works |
| 4. SSH ProxyCommand | `ProxyCommand connect -H` | SSH git operations (push/pull/clone) | `ssh -T` works, `git push` fails intermittently with `failed to begin relaying via HTTP` |
| 5. VM/Container proxy | Docker/OrbStack proxy config | `docker pull`, `docker build` | Host `curl` works, `docker pull` times out (TLS handshake timeout) |

**Each layer is independent.** A fix at one layer doesn't help the others. You may need fixes at multiple layers simultaneously.

### Why tun-excluded-routes Breaks Tailscale

On macOS, when a VPN tool excludes a CIDR from its TUN interface, it typically adds a system route pointing that CIDR to the default gateway via `en0`. For `100.64.0.0/10`:

```
100.64/10  192.168.x.1  UGSc  en0       ← VPN tool adds this
100.64/10  link#N       UCSI  utun7     ← Tailscale's route
```

macOS route priority: `UGSc` > `UCSI` for same prefix length. Result: Tailscale traffic goes to the router, which has no route to 100.x addresses.

### Why skip-proxy Is Needed for Browsers

Even with correct routes and a DIRECT rule, browsers can still get 503. The flow:

1. Browser sends request to Shadowrocket's system proxy (set by VPN profile)
2. Shadowrocket matches `IP-CIDR,100.64.0.0/10,DIRECT`
3. Shadowrocket tries to connect "directly" — but from its own process context, via Wi-Fi (en0)
4. `100.x.x.x` is unreachable via en0 → 503

`curl` works because it uses the `http_proxy` env var (or no proxy with `--noproxy`), going through the OS network stack where Tailscale routing works. Browsers don't use `http_proxy` — they use the system proxy.

Adding `100.64.0.0/10` to `skip-proxy` makes the system bypass the proxy entirely for those IPs. The browser connects directly through the OS network stack → Tailscale utun handles routing → connection succeeds.

### The Correct Approach

For full Tailscale compatibility with proxy tools, apply all four fixes:

1. **`[Rule]`**: `IP-CIDR,100.64.0.0/10,DIRECT` — handles TUN-level traffic
2. **`skip-proxy`**: Add `100.64.0.0/10` — fixes browser access
3. **`NO_PROXY` env var**: Add `100.64.0.0/10,.ts.net` — fixes CLI HTTP tools
4. **SSH `~/.ssh/config`**: Remove `ProxyCommand`, use `ssh.github.com:443` — fixes git push/pull

**Critical anti-pattern**: Do NOT add `100.64.0.0/10` to `tun-excluded-routes` — this breaks everything (see "Why tun-excluded-routes Breaks Tailscale" above).

### Quick Verification

After any fix, always verify:

```bash
# Route should go through Tailscale utun, not en0
route -n get <tailscale-ip>

# Should show only one 100.64/10 route (Tailscale's)
netstat -rn | grep 100.64

# SSH must work
ssh -o ConnectTimeout=5 <user>@<tailscale-ip> 'echo ok'

# curl must work (with and without proxy)
curl --noproxy '*' -s -o /dev/null -w "%{http_code}" http://<tailscale-ip>:<port>/
curl -s -o /dev/null -w "%{http_code}" http://<tailscale-ip>:<port>/

# Browser must work (open in Chrome, no 503)
```

### SSH Non-Login Shell Pitfall

When SSHing to a remote macOS machine, non-login shells don't load `~/.zshrc`. Tools installed via nvm, Homebrew, or other shell-level managers won't be in `$PATH`. Proxy env vars set in `~/.zshrc` also won't be loaded.

```bash
# FAILS — non-login shell, nvm/proxy not loaded
ssh <tailscale-ip> 'node --version'
# → command not found

# WORKS — explicitly source shell config
ssh <tailscale-ip> 'source ~/.zshrc 2>/dev/null; node --version'
# → v22.18.0
```

**Note**: `bash -lc` loads `.bash_profile` but NOT `.zshrc`. On macOS (default shell is zsh), always use `source ~/.zshrc` or `zsh -ic` for interactive shell initialization.

### localhost Proxy Interception in Scripts

When `http_proxy` is set globally (common in China), any script or Makefile that curls `localhost` will fail unless it bypasses the proxy. This affects health checks, warmup scripts, and test harnesses.

**Fix**: Add `--noproxy localhost` to every localhost curl call in Makefiles and scripts:

```makefile
# Health check that works regardless of proxy settings
@curl --noproxy localhost -sf http://localhost:9000/minio/health/live && echo "OK"
```

Or set `no_proxy` in `~/.zshrc` alongside `http_proxy`:

```bash
export http_proxy=http://127.0.0.1:1082
export https_proxy=http://127.0.0.1:1082
export no_proxy=localhost,127.0.0.1   # Always add this alongside proxy vars
```

### Emergency Rollback

If a proxy config change breaks Tailscale connectivity:

```bash
# Revert the config change and restart Shadowrocket VPN
# This restores the original routes

# Or manually delete a conflicting route:
sudo route delete -net 100.64.0.0/10 <gateway-ip>
```

**Important**: Manually deleting a bad `en0` route with `sudo route delete` is only a temporary fix. Shadowrocket will re-add the route when the VPN connection is next reconnected or toggled. The only permanent fix is modifying the Shadowrocket configuration to remove `100.64.0.0/10` from `tun-excluded-routes` (it should never be there).

If `tun-excluded-routes` was modified, reverting it and restarting Shadowrocket will restore Tailscale's routing immediately.
