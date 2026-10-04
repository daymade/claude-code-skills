# Case: the IoT fleet that died three weeks after a "seamless" router swap

The only case in this skill about **client-side association failure** rather than path or service failure: nothing here was slow or reset — a population of devices simply was not on the network anymore. It is included for two reasons. First, the entire falsification chain runs on *passive observation from one laptop* — the failing devices are headless IoT gear with no logs to pull, so every step has to work from the outside. Second, the failure was manufactured by the migration's own success criteria: the swap was declared done on evidence from exactly the population that was never at risk.

## Setup

A home network replaced its dedicated Wi-Fi router with the Wi-Fi of a carrier-provided gateway (a Wi-Fi 6 ONT). The migration used the standard clone-the-SSID trick: rename the new AP to the old network's SSID and password so every client rejoins "without being told". On migration day this looked completely successful — the LAN device count roughly doubled within hours as clients rejoined, and nothing needed re-pairing.

The IoT fleet behind that Wi-Fi: smart curtains, air conditioners, lamps. Topologically two classes: devices hanging off a Zigbee/BLE **hub** (a multi-mode smart-home gateway — itself a Wi-Fi client), and devices with their own Wi-Fi radio.

## Symptom

About three weeks later: a whole group of devices offline in the vendor app — some curtains, one AC, some lamps. Some were hub children, some were direct-Wi-Fi. The hub was visibly present and powered. The user's summary: "the gateway is right there — why did everything behind it die?"

## The evidence chain

Each step rules out one layer, and each runs from one ordinary machine on the LAN. The commands below are the macOS forms the case was executed with; Linux equivalents are named in the recipes section.

**1. Is client-to-client traffic even possible? — mDNS census.** `dns-sd -B _services._dns-sd._udp local.` returned a rich list of service types (`_hap`, `_airplay`, `_smb`, `_ipp`, Thread border-router records…). Multicast was flowing, so the gateway was **not** enforcing AP/client isolation. One whole class of explanation — "the new AP blocks local control" — dies in ten seconds.

**2. Who is actually on the network? — ARP sweep + OUI census.** Ping-sweep the subnet, read the neighbor table, look up each MAC prefix:

```
# macOS — warm the neighbor table, then read it (substitute your subnet)
for i in $(seq 1 254); do ping -c 1 -W 200 192.168.1.$i >/dev/null 2>&1 & done; wait
arp -an | grep -v incomplete
# OUI → vendor
curl -s https://api.macvendors.com/54:ef:44
```

(On Linux the same sweep with `ping -c 1 -W 1`, then `ip neigh`.) Result: ~28 devices. The hub vendor's OUI family (e.g. Lumi `54:EF:44`) appeared **zero times**, while newer devices from the same ecosystem — a speaker, a bedside lamp, a camera — were present and accounted for. The hub was not on the LAN at all.

That single observation reorganizes the incident. The hub's Zigbee/BLE children have no IP existence — they appear in the app only through the hub — so "curtains offline" is not N device failures, it is **one** failure casting N shadows. When a group of devices dies together, decompose the group by topology before touching any device, and check the hub's *network membership*, not its power LED. A hub is a Wi-Fi client that happens to own radios pointing the other way too.

**3. What is the new AP actually beaconing? — read the association parameters.** On macOS, `system_profiler SPAirPortDataType` shows the connected network's security and band; the AP's admin UI shows the same per SSID. The new gateway was beaconing **WPA2/WPA3 transition mode** (and 802.11ax on 2.4 GHz). The retired router had been WPA2-only.

That completes the picture. Newer IoT chips parse a transition-mode RSN without trouble; a lot of pre-2020 Wi-Fi silicon — exactly what inexpensive IoT devices carry — fails to associate once SAE appears in the AKM suite list. So the migration *was* seamless, for every device new enough to be observed on migration day. The failures were delayed because the association problem only bites on re-join: a DHCP renewal, a deauth event, a power blink. The fleet did not fail at the swap; it spent three weeks falling off, one renewal at a time.

## The decisive measurement

Intervention → effect. The security mode was set back to **WPA2-PSK (AES) only** on both bands — same SSID, same password, nothing else touched. Note whose hands this step is: flipping an AP's security mode is a production change on the gateway and needs its admin credential, so unless you already hold it, it belongs to the owner (this skill's Principle 6 boundary — credentials and production changes are two of the three things that legitimately reach the user). Within minutes the hub's OUI appeared in the ARP table, the LAN census went from 28 devices to 40, and the hub's children restored in the app with no re-pairing. One configuration value flipped, twelve devices returned. No competing hypothesis on the table — signal coverage, hub hardware failure, corrupted pairings — produces that signature.

## The wrong turn that was available

Re-pairing everything. It was plausible, it was the vendor-app-blessed ritual, and it would have appeared to work — devices rejoin, one tedious device at a time — while leaving the root cause armed to collect the next renewal wave. The tell that it was the wrong move was the group structure itself: hardware does not fail in hub-shaped clusters.

## Recipes this case contributes

**Router/AP replacement alignment checklist.** Cloning SSID + password does not clone a network. Four things must line up, and the last two are the ones nobody checks:

1. SSID (same)
2. Password (same)
3. **Security mode** — WPA2-PSK/AES-only if any legacy IoT must survive; WPA2/WPA3 transition is the factory default on new gear and is the killer here
4. **Band/PHY compatibility** — 2.4 GHz enabled, 20 MHz, b/g/n permitted (not ax-only)

Then validate the migration with the **oldest** client on the network, not the newest — the new phone and the new speaker are the least informative sample you own (trap 20).

**Passive IoT census from one laptop** (macOS forms first, Linux equivalents after each):

- `dns-sd -B _services._dns-sd._udp local.` — service-type census; any multicast answers at all also falsify AP isolation. Linux: `avahi-browse -a -t` (package `avahi-utils`), or per type `avahi-browse -t _miio._udp`
- `dns-sd -B _hap._tcp` / `_miio._udp` / `_mi-connect._udp` — HomeKit / Xiaomi-family announcements
- Ping-sweep + neighbor table + OUI lookup (commands in step 2 above; Linux read-out: `ip neigh`) — the objective device inventory; vendor OUIs say which *ecosystem* is present or absent, independent of what any app claims
- `system_profiler SPAirPortDataType` (macOS) — the AP's real beacon parameters: security, band, channel. Caveat: it reports the network *this machine is associated to* — if your laptop is on Ethernet or a different SSID, read the AP's admin UI instead. Linux, while associated to the IoT SSID: `sudo iw dev <if> scan`

One identity caution: mDNS names are chosen for usefulness, not accuracy. A Thread border-router record named "living room" can turn out to be a streaming box, not the IoT hub — resolve the hostname and OUI-check the MAC before counting it as the device you are looking for (trap 13: fingerprint ≠ identity).

**Hub-first decomposition for group outages.** Map the dead devices by topology — hub children vs direct Wi-Fi. If the dead set is a hub-shaped subtree, the investigation is about *one* Wi-Fi client; verify its membership from the network side (its OUI in the ARP table, its mDNS announcements), because "it is powered and right there" is a statement about electricity, not association. Hub children restore on their own once the hub re-associates; re-pairing is almost never the fix for a group outage.
