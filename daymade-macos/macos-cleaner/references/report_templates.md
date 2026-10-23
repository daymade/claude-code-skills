# Report templates

Use these templates after the read-only evidence phase. Apply the main skill's [safety and authorization contract](../SKILL.md#safety-and-authorization-contract): a report does not create cleanup authorization. Record the existing authorization covering the verified targets and consequences, or the exact confirmation still missing. Stop when authorization is missing or the user requested a plan-only phase.

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

## Ranked candidates

Keep nominal/path-accounted size separate from expected physical release so a
large APFS clone or shared-layer hotspot remains visible without becoming a
false savings promise.

| Rank | Exact candidate | Nominal/path-accounted size | Expected physical release | Confidence | Why this rank |
|---:|---|---:|---:|---|---|
| 1 | <exact target> | <observed or n/a> | <estimate or unknown> | <high/medium/low> | <safety + evidence + effort> |

State permission errors and incomplete scans. Never present a partial `du` total as the complete category size.

## Protected-service baseline

| Service | Process/parent | Listener | Launch mechanism | Health probe | Log-growth window |
|---|---|---|---|---|---|
| <service> | <live values> | <live values> | <live value> | <result> | <timestamps + byte delta> |

## Proposed commands — not yet executed

| # | Exact command | Exact target | What changes | Recoverability | Expected physical release | User/service impact | Required postcondition |
|---|---|---|---|---|---:|---|---|
| 1 | `<command>` | <object/path/service> | <effect> | <reversible / Trash / backup / redownload-only> | <estimate + unit> | <impact> | <observable value> |

Every verification or confirmation step in the plan must be executable exactly as written: exact command, exact target, exact pass criterion. A step of the shape "re-run one high-frequency chain — which one is side-effect-free must be checked before execution; this report does not choose" is an undelivered decision embedded in a checklist: the executor inherits a choice the planner was paid to make. Measured 2026-10-21 (adversarial R7): the warm-cache verification step stayed open until counter-review fixed the candidate (the sync tool's own `--help`, side-effect-free). Fix the candidate and state the criterion inside the plan, or mark the step explicitly unresolved and keep it out of the approved command set. The same rule bars confirmation steps without falsifiable criteria (see the git-side anchoring case in git-safety-net prevention_practices.md).

Write the single safe form of each disposal, not a risk-asymmetric either/or. "Delete or archive" leaves the choice to the execution moment; when the options carry asymmetric risk (deleting loses a 1.8 G offline rust toolchain that can only be re-downloaded; archiving costs only NAS bytes), the plan must fix the safe form verbatim — "archive to NAS, verify by readback, then delete local copy". Measured 2026-10-21 (adversarial R2): a build-output line item was written as delete-or-archive while the report's own prose said archiving was preferable; an executor picking the first option would have destroyed the offline toolchain. If the report recommends one option anywhere, the command list must say that option and no other.

## Recommendation

Recommend <option> because <evidence-based reason>. Alternatives:

- <alternative>: <trade-off>
- <alternative>: <trade-off>

Expected result: <projected free space and capacity, with assumptions>.

## Authorization status

No state-changing command has run.

- Covering authorization: <original instruction and the verified targets/conditions it covers, or none>
- Missing confirmation: <exact target, consequence or user-supplied confirmation phrase still required, or none>
- Next action: <execute within covering authorization, stop for the missing confirmation, or hand off a plan-only result>
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

For OrbStack, engine-object deletion frees space inside the VM immediately while the sparse image's host-physical release follows via automatic TRIM on a lag (the manual Reclaim button no longer exists in 2.2.x; measured 2026-10-23). Report VM-side and host-side as two separate postconditions with the lag expectation stated; never promise host `df` recovery from Docker's object-size tables alone.

## Phase-4 result

Report emergency service recovery and the requested capacity investigation separately.
Use the known-occupant table below to decide whether authorized investigation remains;
do not invent a free-space target when the user supplied none. The executing agent
checks the evidence and remaining actions; this template does not enforce completion.

```markdown
# Cleanup result

## Result scope

- Emergency recovery: <recovered / partial / not required, with service evidence>
- Capacity investigation: <complete / continuing / blocked, with the next necessary action>
- User-supplied capacity target: <exact value and result / not supplied>

## Before and after

| Metric | Before | After | Delta |
|---|---:|---:|---:|
| Used | <value> | <value> | <value> |
| Available | <value> | <value> | <value> |
| Capacity | <value>% | <value>% | <value pp> |
| Cleaned subsystem physical usage | <value> | <value> | <value> |

## Known major occupants

Reuse the measured inventory; include protected and unexplained large branches.

| Occupant / writer | Path-accounted size | Disposition and evidence | Remaining action or reason to retain |
|---|---:|---|---|
| <exact subsystem> | <value / incomplete> | <retired / active / unique work / not yet classified> | <smallest deciding probe / authorized cleanup / explicit blocker / none> |

## Postconditions

- [ ] Approved target and only that target changed
- [ ] Required activation/configuration state matches
- [ ] Any user-supplied capacity target is checked; otherwise report measured space without claiming a target was met
- [ ] Known major occupants are explained; any remaining required investigation or cleanup is marked continuing or explicitly blocked
- [ ] Protected service process/listeners/launch mechanism/health match the baseline
- [ ] Observation window shows no immediate abnormal refill
- [ ] No user data, credentials, databases, or unrelated caches changed

## Exceptions

<none, or exact failed/mismatched postcondition and the resulting partial state>

If the target was missed, state: “No second cleanup was performed; the next step is read-only analysis.”
```

### Result checks on representative cases

Use these fictional cases when changing the closing workflow. Judge the proposed
next action and completion claim, rather than whether the answer repeats a phrase.

| Case | Evidence supplied to the executing agent | Required result | Counterexample that fails |
|---|---|---|---|
| Emergency recovery with an unexplained large occupant | A full disk stopped a CI VM; retired build output was removed; the same VM completed its queued job. Available space is now 12 GiB. An already measured 60 GiB deployment directory remains unclassified. The user requested cleanup without a numeric target. | Report CI recovery and measured space, keep the capacity investigation continuing, and inspect the large directory's writer, contents and consumers before choosing another deletion. | Declare the whole cleanup complete because CI passed or 12 GiB is available; invent a target; delete the whole deployment directory from its size alone. |
| Old test directory with live-value contents and shared allocation | The directory contains source edits, a retained lockfile and patches, an installed global CLI toolchain, model data, and an inactive generated dependency tree. Exact dependency roots and rebuild inputs have been verified. Dependency allocation is 8 GiB; the unchanged-boot remote `df` window increases by 0.3 GiB. All major occupants are now explained. | Restrict the completed deletion to the verified dependencies, preserve the other contents, report the 0.3 GiB net window separately from the 8 GiB allocation, and state reinstall/download cost. End without more scans when no required authorized action remains. | Remove the whole old directory, call the toolchain disposable because its process exited, promise 8 GiB was freed, or keep scanning explained occupants without a new question. |
