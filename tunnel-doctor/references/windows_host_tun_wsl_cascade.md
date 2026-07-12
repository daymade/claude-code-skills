# Windows Host TUN Proxy Outage Cascading into WSL (and Its Tailscale)

The macOS sections of this skill treat the TUN proxy and Tailscale as peers fighting over routes on one machine. On a Windows + WSL2 workstation the topology is different — and so is the failure shape:

```
Internet
   ↑
Physical NIC (Ethernet / Wi-Fi)
   ↑
[TUN proxy on Windows host]   ← v2rayN (sing-box TUN) / Clash / sing-box — owns the DEFAULT ROUTE when enabled
   ↑
WSL2 NAT (vEthernet, host gateway = 172.x.x.1)
   ↑
WSL2 guest → tailscaled inside WSL → Tailscale control plane
```

WSL2 in NAT mode has **no network path of its own** — every packet exits through the Windows host's stack. When a TUN proxy on the host owns the default route and its upstream node/config is dead, the host's traffic goes into a black hole, and WSL drowns with it. The symptom cluster:

- On the host: every site fails, both domestic and overseas (unlike the macOS split-brain in Step 2J, which kills only one plane)
- Inside WSL: DNS may still resolve (cached / Tailscale MagicDNS), but all TCP fails
- **Tailscale never comes online** — the control-plane connection is also swallowed by the dead TUN. The user reports "even Tailscale won't connect", which *feels* like a Tailscale problem but is entirely upstream of it
- Disabling the TUN restores everything within seconds, with no other change

**Why this gets misattributed:** the user in the middle of the outage usually tries several things at once — plugging in a different NIC, switching from Ethernet to Wi-Fi, toggling the TUN, rebooting. When the network comes back they cannot tell which action fixed it, and often credit the wrong one (e.g. "switching to Wi-Fi fixed it"). Both NICs typically sit on the same LAN and gateway, so switching between them cannot fix a route-hijack problem. Don't argue from theory — prove it from the event log.

## Windows event-log timeline forensics (pinning down *which* action fixed the network)

Windows logs every virtual-adapter connect/disconnect and every connectivity-level change with second precision. Two log channels reconstruct the whole incident after the fact:

| Channel | What it gives you |
|---------|-------------------|
| `Microsoft-Windows-NetworkProfile/Operational` | Event 10000 (Network Connected) / 10001 (Network Disconnected) **with the adapter's name** — a TUN adapter appears here by name (v2rayN 7.x creates `singbox_tun`); Event 4004 (Network State Change) marks every connectivity-level flap |
| `System` (filter by provider) | DHCP client events (lease obtained/lost), physical NIC driver link events (Intel Wi-Fi = `Netwtw*`, Realtek = `rt*`/`Realtek*`) |

Query both (from WSL, see the interop pitfalls below; natively, run in PowerShell):

```powershell
# Adapter connect/disconnect timeline for today — look for the TUN adapter by name
Get-WinEvent -FilterHashtable @{LogName="Microsoft-Windows-NetworkProfile/Operational"; StartTime=(Get-Date).Date} |
  Select-Object -First 30 TimeCreated,Id,Message | Format-List

# Physical-link + DHCP events for today
Get-WinEvent -FilterHashtable @{LogName="System"; StartTime=(Get-Date).Date} -ErrorAction SilentlyContinue |
  Where-Object { $_.ProviderName -match "Dhcp|Tcpip|NCSI|NDIS|Netwtw|Realtek" } |
  Select-Object -First 30 TimeCreated,ProviderName,Id | Format-Table -AutoSize
```

**How to read the timeline** — align the user's actions against connectivity recovery:

```
21:32:36  Event 10000: Network Connected  (Wi-Fi SSID)     ← user action A: joined Wi-Fi
21:32–21:35  repeated Event 4004 connectivity flaps         ← network still broken 3 min after A
21:35:46  Event 10001: Network Disconnected  singbox_tun    ← user action B: disabled TUN mode
21:35:47+ Event 4004: connectivity level changed (stable)   ← recovery follows B within seconds
```

If action A had been the fix, recovery would follow A. The gap between A and recovery — while flaps continue — plus recovery landing seconds after B, pins causation on B. This settles "which of my three panicked actions actually fixed it" with evidence instead of vibes. Cross-check with the TUN tool's own log (v2rayN: `guiLogs/<date>.txt` under its install dir) — its startup/error timestamps should bracket the outage window.

**Corroborating current-state checks** (after the fact):

```powershell
# TUN adapter should be gone when TUN mode is off
Get-NetAdapter -IncludeHidden | Where-Object { $_.InterfaceDescription -match "wintun|TAP|tun" }

# Physical NICs healthy: Up + an IP from the LAN + default route present
Get-NetIPConfiguration | Format-List InterfaceAlias,IPv4Address,IPv4DefaultGateway
Get-NetRoute -DestinationPrefix "0.0.0.0/0" | Format-Table ifIndex,InterfaceAlias,NextHop
```

If the previously-"broken" NIC now shows Up with a valid lease on the same gateway as the "working" one, that NIC was never the problem — the TUN was.

## Diagnosing the host from inside WSL: three interop pitfalls

You will often be SSH'd into the WSL guest (that may be the only door in). Windows can be interrogated from there via interop — but three traps break naive attempts, each producing misleading "no output" results:

1. **Windows executables may not be on PATH.** Many WSL setups disable `appendWindowsPath`. A bare `powershell.exe` or `tasklist.exe` fails as command-not-found — which, inside a `cmd || echo "(none found)"` pattern, silently masquerades as "no matching processes". Always call by full path:
   ```bash
   PS=/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe
   TL=/mnt/c/Windows/System32/tasklist.exe
   ```

2. **Localized Windows emits legacy-codepage output** (Chinese systems: GBK). Piping `tasklist.exe` into `grep` can make grep treat the stream as binary and print nothing. Transcode first, and force PowerShell to UTF-8:
   ```bash
   $TL | iconv -f GBK -t UTF-8//IGNORE | grep -iaE "v2ray|xray|sing-box|clash|tailscale"
   ```
   ```powershell
   [Console]::OutputEncoding=[Text.Encoding]::UTF8; <rest of command>
   ```

3. **In a no-tty SSH session (e.g. `tailscale ssh host 'script'`), a Windows exe finishing can kill the output pipe** — every command after the first successful `.exe` call produces no visible output, so a multi-step diagnostic script appears to "die" mid-way. Workaround: redirect each Windows call to a file, then `cat` it from the Linux side:
   ```bash
   $PS -NoProfile -Command '...' </dev/null >/tmp/win-diag.out 2>&1
   cat /tmp/win-diag.out
   ```

## Two tailscaleds: which one is "online"?

A Windows + WSL machine can run **two independent Tailscale nodes**: the Windows client (service `Tailscale`, `tailscaled.exe`) and a Linux tailscaled inside WSL. They register as separate devices with separate names and IPs. Confusion pattern: the user says "Tailscale is online now" — but *which one?* You may be SSH'd in via the WSL node while the Windows node has never been logged in at all.

Disambiguate in three checks:

```bash
# 1. Inside WSL: is a local tailscaled running, and what node is "self"?
ps aux | grep tailscaled | grep -v grep
tailscale status   # first line = the node you are talking through

# 2. Windows service state (from WSL, full paths per above)
/mnt/c/Windows/System32/sc.exe query Tailscale        # RUNNING ≠ logged in!
"/mnt/c/Program Files/Tailscale/tailscale.exe" status # "Logged out." / "NoState" = engine never came up
```

**Signature of a Windows Tailscale that is installed but not actually connected:**

- `sc query Tailscale` → `RUNNING` (the service exists and runs — this proves nothing about login state)
- `tailscale.exe status` → `unexpected state: NoState` or "Tailscale is starting"
- The `Tailscale` network adapter is Up but holds a **169.254.x.x APIPA address** instead of a `100.x.y.z` CGNAT address — the IPN engine never configured it, Windows self-assigned. This one-line check (`Get-NetIPConfiguration`) is the fastest tell.
- The tailnet's device list has no entry for the Windows host (only the WSL node)

This state is stable and harmless if the WSL node is the one doing the work — but recognize it before "fixing" it, and before attributing any outage to it. If the Windows node is wanted, `tailscale.exe login`; if not, consider stopping the service so its wintun driver never contends with the TUN proxy's.

## Fix and prevention

- **Immediate fix**: disable TUN mode in the proxy tool (v2rayN: toggle TUN off — the `singbox_tun` adapter disappears; recovery is near-instant). Verify with the four-plane checks from Step 2J adapted to the host: domestic direct, overseas via proxy port, WSL outbound, WSL tailscaled connected.
- **Prevention**: on a workstation whose real proxy consumers live inside WSL, TUN mode is usually unnecessary — a single point of failure that amplifies any node outage into a whole-machine outage that even takes down the remote-access path (Tailscale). Prefer explicit per-process proxying from WSL against the host's HTTP/SOCKS port:
  ```bash
  # WSL guest → host proxy port; host gateway IP from: ip route show default
  export http_proxy=http://$(ip route show default | awk '{print $3}'):<proxy-port>
  export https_proxy=$http_proxy
  export no_proxy="localhost,127.0.0.1,::1,$(ip route show default | awk '{print $3}'),100.64.0.0/10,.ts.net,192.168.0.0/16,10.0.0.0/8"
  ```
  (The `no_proxy` line matters: without it, requests to localhost services and Tailscale peers get shoved through the proxy — a proxied `curl http://localhost:<port>` returning **503 from the proxy** instead of **connection refused** is the tell that `no_proxy` is missing. See Step 2A/2E for the general rule.)
- **If the node pool is dead** (the reason the TUN black-holed in the first place), refresh the subscription over a direct connection — the proxy cannot fetch its own cure through itself.
