# Apple Content Caching: targeted diagnosis and repair

Use this reference when disk pressure points to macOS Content Caching, `AssetCacheManagerUtil`, iCloud cache, or the alert “Caching needs more space.” It is a targeted branch: do not begin with Mole, Docker, or a home-directory scan when Content Caching can already explain the missing physical space.

The command shapes below were verified on macOS 26.5.2 on 2026-08-24 and cross-checked against Apple's installed `AssetCacheManagerUtil(8)` manual and current Apple Platform Deployment documentation. Re-read the target Mac's installed man page when a future macOS release changes the utility.

## Non-negotiable distinctions

- `CacheUsed` is the logical size of cached content.
- `ActualCacheUsed` is the current physical allocation attributable to the content cache.
- `PersonalCacheUsed` and the `iCloud` detail are logical content quantities, not additional physical bytes to add to `ActualCacheUsed`.
- `CacheLimit: 0` means unlimited. Deactivation and limit changes are separate operations, so verify the configured limit independently instead of inferring that deactivation changed it.
- `deactivate` and `flushCache` are separate operations. Turning the service off does not prove the local cache was emptied.

Base release estimates on `ActualCacheUsed`, then cross-check the exact data path with allocated `du` blocks when permissions allow. Never estimate recoverable disk space from `CacheUsed`.

## Phase 1: read-only evidence

### 1. Prove the target

For a local Mac, record the identity anyway. For SSH, connect only to the user-named host and compare the live identity with the request:

```bash
/bin/date "+%F %T %Z %z"
/usr/sbin/scutil --get ComputerName
/usr/sbin/scutil --get LocalHostName
/bin/hostname
/usr/bin/sw_vers
/bin/df -k /System/Volumes/Data
/bin/df -h /System/Volumes/Data
```

Stop on an identity mismatch. Do not “check the other peer” by logging into it unless the user explicitly puts that machine in scope.

### 2. Read Content Caching's own authority

```bash
/usr/bin/AssetCacheManagerUtil status
/usr/bin/AssetCacheManagerUtil settings
/usr/bin/AssetCacheManagerUtil -j status
/usr/bin/AssetCacheManagerUtil isActivated
```

Expected evidence:

- `status` reports `Activated`, `Active`, logical and physical usage, cache health, peers, and service port.
- `settings` reports `CacheLimit`, `DataPath`, cached-content modes, and network policy.
- JSON status provides exact byte counts for calculations.
- `isActivated` independently reports activation state.

Copy values from current output. Do not carry forward an old PID, peer status, cache size, or path.

### 3. Cross-check physical allocation

Use the `DataPath` returned by `settings`; do not assume the default. If the path is the default, the bounded check is:

```bash
/usr/bin/du -sk "/Library/Application Support/Apple/AssetCache/Data"
```

If access is denied and non-interactive sudo is already authorized, retry the same read-only command with `sudo -n`. Do not broaden it to `/Library/Application Support`, the data volume root, or the user's home directory.

Convert units explicitly:

- Apple status bytes / 1,000,000,000 = decimal GB.
- Apple status bytes / 1,073,741,824 = GiB.
- `du -sk` output / 1,048,576 = allocated GiB.

Small differences between `ActualCacheUsed` and `du` are normal metadata/accounting differences. A difference large enough to change the decision requires investigation before cleanup.

### 4. Verify peers without touching them

Read the `Peers` array in the target Mac's status. Record each peer's current address, `healthy`, `friendly`, supported cache modes, and advertised cache size.

A peer IP existing in old notes is not evidence that the peer is healthy now. Conversely, a healthy peer in the target's live status is enough to plan deactivation of the target; it is not permission to log into or reconfigure the peer.

### 5. Protect co-resident services

For every service the user marks as critical, capture a fresh baseline using the narrowest available sources:

- current process and parent;
- current listeners;
- launchd label or other launch mechanism;
- the service's supported health or RPC probe;
- exact log files and their sizes, without reading configuration, sessions, credentials, or databases outside scope.

Use `pgrep`, `ps -p`, `lsof -a -p <pid>`, `launchctl print <domain>/<label>`, and the service's own status command. Do not use `ps ... | grep`, which can match the probe itself. Re-resolve the PID after cleanup instead of assuming it remains unchanged.

To test log growth, record byte sizes at two or more timestamps. State the observation window; do not turn a 30–60 second sample into a claim about long-term growth.

### 6. Check bounded second sources only

When Content Caching alone can meet the free-space target, keep the secondary check narrow:

- the protected service's known log directories;
- system log directory totals;
- local APFS snapshot inventory;
- any other exact path named by existing evidence.

Permission-denied `du` output is incomplete. Label it partial and do not use it as a complete category total.

## Phase 2: choose and report a repair

### Prefer deactivation when another healthy cache is available

Recommend deactivating the target Mac when all are true:

- another content-cache peer is currently healthy;
- the target is under material disk pressure;
- the target's physical cache can meet the recovery goal;
- the user does not require this Mac to remain a cache node.

This removes one cache node, not the originals in Apple or iCloud. Clients may take time to rediscover another cache; restarting client devices accelerates discovery but is not required for the cleanup itself.

### Use a finite limit when the target must stay active

If the target must keep serving content, set an explicit finite `CacheLimit`. Choose it from the user's free-space goal and a safety margin; do not use a memorized constant.

An estimate for a limit-only plan is:

```text
estimated release ≈ max(0, ActualCacheUsed - proposed finite limit)
projected free ≈ current free + estimated release
```

Treat this as a planning estimate, not a promise. The service controls eviction and APFS reporting can lag.

### Set a dormant safety limit when the acceptance criteria require “not unlimited”

If the user wants the service disabled *and* explicitly requires that the configuration no longer say unlimited, include a finite limit in the approved plan before deactivation. This prevents a later accidental reactivation from immediately returning to unlimited growth.

Changing the limit while active can begin eviction as soon as settings reload. State that effect before asking for confirmation.

### Required plan fields

Before mutation, present:

- current disk, `CacheUsed`, `ActualCacheUsed`, `CacheLimit`, activation, path, and peer health;
- exact commands in execution order;
- what each command changes;
- whether and how each change can be reversed;
- expected physical release in GB and GiB;
- impact on clients, peers, and protected co-resident services;
- success criteria and the observation window;
- the exact confirmation phrase, when the user supplied one.

Then stop. Do not place state-changing commands in the same shell call as the read-only gate that is meant to authorize them.

## Phase 3: supported repair commands

Use Apple's supported command-line interfaces. Never manually delete anything under `DataPath`.

### Optional: set an approved finite limit

`CacheLimit` is expressed in decimal bytes. Replace `<approved-bytes>` only with the value shown in the approved plan:

```bash
/usr/bin/sudo -u _assetcache /usr/bin/defaults write /Library/Preferences/com.apple.AssetCache.plist CacheLimit -int <approved-bytes>
/usr/bin/sudo /usr/bin/AssetCacheManagerUtil reloadSettings
/usr/bin/AssetCacheManagerUtil settings
```

Postcondition: `settings` shows the approved finite limit, not unlimited. If it does not, stop before deactivation or flushing.

To change the limit later, write a newly approved finite value and reload settings. Do not silently restore `0`/unlimited as a fallback.

### Deactivate the target cache

```bash
/usr/bin/sudo /usr/bin/AssetCacheManagerUtil deactivate
/usr/bin/AssetCacheManagerUtil isActivated
```

Postcondition: the target reports that content caching is deactivated. If it remains activated, stop. Do not flush an active cache under a plan that assumed it was off.

Reactivation is possible with `sudo AssetCacheManagerUtil activate`, but that is a separate future change and requires current authorization.

### Flush the approved cache scope

For all cached content:

```bash
/usr/bin/sudo /usr/bin/AssetCacheManagerUtil flushCache
```

For a plan explicitly limited to one category, Apple also provides `flushPersonalCache` and `flushSharedCache`. Do not substitute one for another after confirmation.

The flush is not locally reversible: cached bytes return only through later downloads or peer transfers. It removes local cache copies, not the original Apple software or users' iCloud originals.

If the command exits non-zero, report “deactivated but not purged” and stop. Do not continue to a success report.

## Phase 4: postconditions and observation

Immediately after the flush and at bounded intervals while APFS settles, run:

```bash
/usr/bin/AssetCacheManagerUtil -j status
/usr/bin/AssetCacheManagerUtil settings
/usr/bin/AssetCacheManagerUtil isActivated
/bin/df -k /System/Volumes/Data
/bin/df -h /System/Volumes/Data
```

Verify all applicable acceptance criteria independently:

- `Activated` and `Active` match the approved mode;
- `CacheLimit` is finite when required;
- `ActualCacheUsed` is zero or has fallen to the approved residual scope;
- available space and capacity meet the user's targets;
- the protected service process, listeners, launch mechanism, and health probe still match the pre-cleanup baseline;
- the target does not immediately refill during the agreed observation window;
- no peer configuration, user files, credentials, databases, or unrelated caches changed.

If the flush succeeds but APFS space has not appeared yet, continue read-only observation. If the final target is still missed, stop deletion and start a second read-only analysis of measured physical sources.

## Failure handling

| Failure | Required response |
|---|---|
| Target identity differs | Stop without probing other machines |
| `settings` or status unavailable | Report the missing authority; do not guess the path or limit |
| Peer no longer healthy | Recompute the service-impact plan before deactivation |
| Limit reload does not show the approved value | Stop before deactivation/flush |
| Deactivation postcondition fails | Leave the finite limit in place if already approved; report partial state; do not flush |
| Flush command fails | Report “deactivated but not purged”; do not claim space recovered |
| `ActualCacheUsed` falls but `df` does not yet move | Observe APFS at bounded intervals; do not repeat flush blindly |
| Free-space target is still missed | Begin read-only second-source analysis; do not delete another category without a new plan and confirmation |
| Protected service differs | Stop, collect read-only evidence, and report the regression before considering any restart or workaround |

## Sources

- Apple Platform Deployment: [Content caching from the command line on Mac](https://support.apple.com/guide/deployment/content-caching-from-the-command-line-depfaba5bc52/web)
- Apple Platform Deployment: [Advanced content caching settings on Mac](https://support.apple.com/guide/deployment/advanced-content-caching-settings-depc8f669b20/web)
- Apple macOS User Guide: [Set up content caching on Mac](https://support.apple.com/guide/mac-help/set-up-content-caching-on-mac-mchl3b6c3720/mac)
- Installed macOS manuals: `AssetCacheManagerUtil(8)` and `AssetCache(8)`
