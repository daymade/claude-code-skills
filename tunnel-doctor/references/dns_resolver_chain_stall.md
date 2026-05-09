# macOS DNS Resolver Chain Stall — Deep Reference

This reference covers the mental model, diagnostic procedure, and a worked example for the failure mode introduced in [SKILL.md § Step 2I](../SKILL.md). Read this when:

- The Step 2I body's bisection alone hasn't isolated the problem
- You need to explain to a teammate why `nslookup` and the application disagree
- You're writing your own automation that interacts with `scutil --dns`

## The Mental Model

### macOS DNS resolution paths (most apps vs. nslookup)

```
                 Application (ssh, curl, git, browser, ...)
                          │ getaddrinfo()
                          ▼
                 DirectoryService (system-wide, async)
                          │ consults
                          ▼
                 mDNSResponder (resolver-chain executor)
                          │ queries in parallel:
            ┌─────────────┼─────────────┬──────────────┐
            ▼             ▼             ▼              ▼
   resolver #1     resolver #2   resolver #3   resolver #N
   (default)       (utunN, VPN)  (per-domain)  (mdns / arpa)
```

`nslookup` does **not** go through this path. It opens a UDP socket to the first nameserver in `/etc/resolv.conf` and parses the reply itself. That's why `nslookup` can return instantly while `ssh`/`curl`/`git`/Chrome all hang.

### Resolver attributes that matter

`scutil --dns` lists every resolver entry. Three fields decide whether a resolver participates in a given lookup:

| Field | Meaning | When dead, what stalls |
|-------|---------|------------------------|
| `nameserver[N]` | Where to send the query | The address that has to respond |
| `domain : <suffix>` | Only matches queries ending in this suffix | Only that suffix's lookups stall |
| `search domain : <suffix>` | Suffix used by short-name expansion; resolver still participates in fully-qualified lookups | Every lookup stalls |
| (no `domain` field) | Default-participation supplemental resolver | Every lookup stalls |
| `flags : Supplemental` | Resolver is consulted in addition to the default, not in place of it | Every lookup stalls |

A useful shorthand: **if a resolver has no `domain :` line, treat it as participating in every lookup.** That's the high-blast-radius case.

### Why a dead daemon ≠ a removed resolver

When a VPN or tunneling daemon (Tailscale, AnyConnect, OpenVPN with `--dhcp-option DNS`, etc.) starts up, it registers a resolver entry with the system network configuration via `SystemConfiguration.framework`. When the daemon dies cleanly, it un-registers the entry as part of teardown. When it crashes, the entry stays.

After a crash:

- The `utun` interface is still in `ifconfig` (kernel doesn't auto-tear it down)
- The route table still has the daemon's CGNAT/RFC1918 ranges pointing at that `utun`
- `scutil --dns` still has the resolver entry the daemon registered
- The actual port-53 listener inside the daemon is gone

This explains the Step 2I trap: `ping <resolver-ip>` works because the `utun` interface still owns the IP and answers ICMP at the kernel level. `dig @<resolver-ip>` fails because there's no UDP/53 listener anymore.

## Worked Example

Reproduces a real diagnosis. Substitute any environment-specific values (nameservers, hostnames) with what `scutil --dns` shows on your machine.

### 1. The original symptom

```text
$ git push
# … hangs ~60 seconds, then either succeeds slowly or times out

$ ssh -vvv git@github.com
…
debug2: resolving "ssh.github.com" port 443
debug3: resolve_host: lookup ssh.github.com:443
# (frozen here for ~60 seconds)
```

### 2. First-line check: nslookup vs dscacheutil divergence

```text
$ time nslookup ssh.github.com
Server: 198.18.0.2
Address: 198.18.0.2#53
Non-authoritative answer:
Name: ssh.github.com
Address: 198.18.0.14
nslookup ssh.github.com  0.01s user 0.00s system 23% cpu 0.06 total

$ time dscacheutil -q host -a name ssh.github.com
# (no output for 60 seconds, then …)
dscacheutil ssh.github.com  0.00s user 0.00s system 0% cpu 1:00.01 total
```

A 1000x divergence (`0.06s` vs `60.01s`) between these two on the same hostname is diagnostic for a stalled supplemental resolver. Stop suspecting the proxy or the route table; this is system DNS.

### 3. List every resolver

```text
$ scutil --dns | grep -E "^resolver|nameserver|domain :|search domain|if_index"
resolver #1
  search domain[0] : <user-tailnet>.ts.net
  nameserver[0] : 198.18.0.2
  if_index : 37 (utun7)
resolver #2
  nameserver[0] : 100.100.100.100
  nameserver[1] : fd7a:115c:a1e0::53
  if_index : 24 (utun6)
resolver #3
  nameserver[0] : 198.18.0.2
  if_index : 37 (utun7)
resolver #4
  domain   : <user-tailnet>.ts.net.
  nameserver[0] : 100.100.100.100
  nameserver[1] : fd7a:115c:a1e0::53
  if_index : 24 (utun6)
resolver #11
  domain   : baidu.com
  nameserver[0] : 223.5.5.5
  nameserver[1] : 119.29.29.29
…
```

Three observations from this output:

- Resolver #2 has `nameserver` but **no `domain :` line** → it participates in every lookup
- Resolver #2 lives on `utun6` → trace back what owns `utun6`
- Resolver #4 has `domain : <tenant>.ts.net.` → bounded scope; only `*.ts.net` queries route through it

If resolver #2 stalls, every system DNS query stalls. This is the high-blast-radius case.

### 4. Bisect

```text
$ for ns in 198.18.0.2 100.100.100.100 223.5.5.5 119.29.29.29; do
    printf "  %s: " "$ns"
    /usr/bin/time -p dig @$ns +tries=1 +timeout=3 +short example.com 2>&1 | tr '\n' ' '
    echo
  done
  198.18.0.2: 93.184.215.14 real 0.01 ...
  100.100.100.100: ;; connection timed out; no servers could be reached real 3.01 ...
  223.5.5.5: 93.184.215.14 real 0.01 ...
  119.29.29.29: 93.184.215.14 real 0.01 ...
```

`100.100.100.100` is dead. The IPv6 nameserver should also be tested:

```text
$ /usr/bin/time -p dig @fd7a:115c:a1e0::53 +tries=1 +timeout=3 +short example.com
;; connection timed out; no servers could be reached
real 3.01 ...
```

Both halves of resolver #2 are dead. Both addresses (v4 and v6) are inside the same VPN's address space (Tailscale's CGNAT/ULA), so they share fate.

### 5. Identify the owning component

`100.100.100.100` is Tailscale's MagicDNS address (well-known). Confirm:

```text
$ tailscale status
failed to connect to local Tailscale service; is Tailscale running?
```

The daemon is dead but the network configuration it registered is still present.

### 6. The "ping ok but DNS dead" check

This step is what catches false-negative diagnoses ("ping works, can't be the network"):

```text
$ ping -c 1 -W 2000 100.100.100.100
PING 100.100.100.100 (100.100.100.100): 56 data bytes
64 bytes from 100.100.100.100: icmp_seq=0 ttl=64 time=0.448 ms
```

ICMP comes back in under half a millisecond. The interface is alive. **The service on that interface is not.**

### 7. Fix and verify

```text
$ osascript -e 'quit app "Tailscale"' && sleep 3 && open -a Tailscale

$ tailscale status | head -3
100.x.x.x   <hostname>   <user>@   macOS  -
…

$ /usr/bin/time -p dig @100.100.100.100 +tries=1 +timeout=3 +short example.com
93.184.215.14
real 0.01 …

$ /usr/bin/time -p dscacheutil -q host -a name example.com
name: example.com
ip_address: 93.184.215.14
real 0.01 …

$ ssh -o "ProxyCommand=none" -T git@github.com
Hi <user>! You've successfully authenticated, but GitHub does not provide shell access.
```

Four-dimensional verification passes; system DNS path is healed.

## Counterexamples — When This Is NOT The Problem

The Step 2I pattern is specific. Several adjacent symptoms have different fixes:

| Symptom | Looks like Step 2I, but is actually | Fix |
|---------|-------------------------------------|-----|
| `nslookup` is also slow | Default DNS is bad, not a supplemental resolver | Replace `nameserver` in `/etc/resolv.conf` (won't persist across DHCP) or fix proxy DNS |
| `ssh` hangs at `debug1: connect to address X.X.X.X` (after resolution succeeds) | Network/route layer, not DNS | Step 2B (route conflict) or Step 2H (TUN DNS hijack) |
| Lookup works initially, slows down over hours | Cache poisoning or memory pressure on `mDNSResponder` | `sudo killall -HUP mDNSResponder` |
| Only one specific domain is slow | Per-domain resolver with a `domain :` filter is dead | Same Step 2I procedure, but the blast radius is bounded |
| `curl -x http://127.0.0.1:<port>` works but `curl` (no `-x`) doesn't | Proxy works; DNS works; the issue is `NO_PROXY` config or env vars | Step 2A |

The four-dimensional verification at the end of Step 2I is what distinguishes "I fixed DNS" from "I worked around DNS." If dimension 4 (`ssh -o "ProxyCommand=none"`) still fails after the daemon restart, the resolver chain isn't the problem — go back to Step 1 and re-bisect.
