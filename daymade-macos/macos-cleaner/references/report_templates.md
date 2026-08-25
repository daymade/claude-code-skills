# Report templates

Use these templates after the read-only evidence phase. They implement the main skill's Observe → Plan → Confirm → Execute → Verify contract. A report is not cleanup authorization: finish the plan, stop at the gate, and wait for the user's explicit approval.

## General phase-2 cleanup plan

```markdown
# macOS disk-space diagnosis and proposed repair

## Current state

- Timestamp: <YYYY-MM-DD HH:MM:SS ZONE OFFSET>
- Target identity: <ComputerName / LocalHostName / hostname>
- Volume: <exact mount>
- Disk: <total> total, <used> used, <available> available, <capacity>%
- Scope exclusions honored: <directories/services not inspected>

## Evidence

| Suspect | Observed value | Logical or physical? | Authority | Confidence |
|---|---:|---|---|---|
| <subsystem/path> | <value + unit> | <logical/physical> | `<command>` | <complete/partial> |

State permission errors and incomplete scans. Never present a partial `du` total as the complete category size.

## Protected-service baseline

| Service | Process/parent | Listener | Launch mechanism | Health probe | Log-growth window |
|---|---|---|---|---|---|
| <service> | <live values> | <live values> | <live value> | <result> | <timestamps + byte delta> |

## Proposed commands — not yet executed

| # | Exact command | Exact target | What changes | Recoverability | Expected physical release | User/service impact | Required postcondition |
|---|---|---|---|---|---:|---|---|
| 1 | `<command>` | <object/path/service> | <effect> | <reversible / Trash / backup / redownload-only> | <estimate + unit> | <impact> | <observable value> |

## Recommendation

Recommend <option> because <evidence-based reason>. Alternatives:

- <alternative>: <trade-off>
- <alternative>: <trade-off>

Expected result: <projected free space and capacity, with assumptions>.

## Confirmation gate

No state-changing command has run.

Reply with:

`<the exact confirmation phrase supplied for this plan>`
```

## Apple Content Caching variant

Use this compact variant with `references/apple_content_caching.md`:

```markdown
## Content Caching evidence

| Field | Current value | Interpretation |
|---|---:|---|
| Activated / Active | <values> | <currently serving or not> |
| CacheLimit | <bytes/display> | <finite or unlimited> |
| CacheUsed | <bytes + GB> | Logical cached-content size; not release estimate |
| ActualCacheUsed | <bytes + GB/GiB> | Physical release basis |
| PersonalCacheUsed / iCloud | <bytes + GB> | Logical subset; do not add to ActualCacheUsed |
| DataPath allocated `du` | <KiB + GiB> | Independent physical cross-check |
| Peers | <address + current healthy/friendly/capabilities> | Read from target status; peer not modified |

## Preferred repair

<Deactivate target and flush / retain service with finite limit>.

Why: <peer health, target pressure, service requirement, target free-space math>.

## Exact command plan

| # | Command | Change | Recoverability | Postcondition |
|---|---|---|---|---|
| 1 | `<approved finite-limit command, if applicable>` | Replace unlimited with approved finite bytes | Set another approved finite value | `settings` shows finite limit |
| 2 | `sudo AssetCacheManagerUtil deactivate` | Stop target cache node | Separately authorized `activate` | `isActivated` says deactivated |
| 3 | `sudo AssetCacheManagerUtil flushCache` | Remove local Apple/iCloud cache copies | Redownload/peer transfer only | `ActualCacheUsed` reaches approved residual |

Expected physical release: <ActualCacheUsed-based estimate>.
Projected volume: <available GiB>, <capacity>%.

Impact:
- Apple/iCloud originals remain intact.
- Clients may rediscover another healthy cache over time.
- <protected service> must retain its process, listeners, launch mechanism, and healthy probe.
- No peer configuration changes.

Failure exits:
- Limit mismatch → stop before deactivation.
- Deactivation mismatch → report partial state; do not flush.
- Flush failure → report “deactivated but not purged.”
- Target still missed → second read-only analysis only.
```

## Docker object-level detail

List every object rather than reporting category totals:

```markdown
### Images

| Image ID | Repository:tag | Engine size evidence | Host physical release estimate | Referenced by running containers | Referenced by stopped containers | Decision |
|---|---|---|---|---|---|---|
| <id> | <repo:tag> | <SIZE / SHARED / UNIQUE from `docker system df -v`> | <unknown or defensible upper bound> | <names/none> | <names/none> | <preserve/confirm exact removal> |

### Containers

| Name | Image | Status | Engine writable-layer size | Host physical release estimate | Restartable state | Decision |
|---|---|---|---|---|---|---|
| <name> | <image> | <status> | <size> | <unknown or upper bound> | <what would be lost> | <preserve/confirm> |

### Volumes

| Volume | Engine volume size | Host physical release estimate | Mounted by | Inspected contents | Database/user-data risk | Decision |
|---|---|---|---|---|---|---|
| <name> | <size> | <unknown or upper bound> | <all running/stopped containers> | <bounded inspection or incomplete> | <risk> | <preserve/confirm exact ID> |

No prune-family command is part of the plan.
```

For OrbStack, add **OrbStack Settings → Reclaim disk space** as a separate, explicitly approved manual plan item when host APFS recovery is required. Engine-object deletion and sparse-image compaction have different effects and postconditions; never promise host `df` recovery from Docker's object-size tables alone.

## Phase-4 result

```markdown
# Cleanup result

## Before and after

| Metric | Before | After | Delta |
|---|---:|---:|---:|
| Used | <value> | <value> | <value> |
| Available | <value> | <value> | <value> |
| Capacity | <value>% | <value>% | <value pp> |
| Cleaned subsystem physical usage | <value> | <value> | <value> |

## Postconditions

- [ ] Approved target and only that target changed
- [ ] Required activation/configuration state matches
- [ ] Free-space and capacity targets are met
- [ ] Protected service process/listeners/launch mechanism/health match the baseline
- [ ] Observation window shows no immediate abnormal refill
- [ ] No user data, credentials, databases, or unrelated caches changed

## Exceptions

<none, or exact failed/mismatched postcondition and the resulting partial state>

If the target was missed, state: “No second cleanup was performed; the next step is read-only analysis.”
```
