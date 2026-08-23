---
name: macos-cleaner
description: >-
  Diagnoses and safely reclaims macOS disk space. Use when a Mac is low on
  storage, reports “Caching needs more space,” shows large Apple Content
  Caching or AssetCacheManagerUtil usage, or needs analysis of caches, logs,
  application remnants, large files, Docker or OrbStack, Homebrew, npm, pip,
  Xcode, and other developer storage. Routes known suspects to targeted
  read-only diagnosis before broad scans, distinguishes logical from physical
  usage, requires an impact-and-recovery plan plus explicit confirmation before
  state changes, and verifies disk space and co-resident services afterward.
---

# macOS Cleaner

Diagnose the actual source of disk pressure, reclaim only approved space, and prove that the cleanup did not damage user data or co-resident services.

## Entry router

Choose the narrowest path that can answer the request:

| User signal | Route |
|---|---|
| Apple Content Caching, `AssetCacheManagerUtil`, `CacheUsed`, `ActualCacheUsed`, iCloud cache, or “Caching needs more space” | Read `references/apple_content_caching.md` completely before probing or proposing commands |
| Docker, OrbStack, images, containers, volumes, or build cache | Read `references/docker_analysis.md`; inspect every object and never use prune-family commands |
| A named cache, directory, application, or service is already the suspect | Inspect that target first; do not start a home-directory or whole-disk scan |
| The source is genuinely unknown | Use the general analysis workflow below; Mole is optional, not the universal first step |

User-provided scope exclusions override every generic scan suggestion. Do not inspect personal directories, credentials, databases, application state, or unrelated services when the user excludes them.

## Safety and authorization contract

1. **Separate observation from mutation.** Complete a read-only diagnosis first. Do not delete, stop a service, edit settings, install or upgrade tools, or run a cleanup preview that may mutate state during that phase.
2. **Confirm the exact target.** On a remote Mac, record the current host identity before any other work. Never infer the machine from an IP, old PID, directory name, or prior report.
3. **Plan before asking.** Before any state change, list every command, what it changes, expected physical space reclaimed, impact, recoverability, and postconditions. Then stop if the user requested a plan-only phase.
4. **Require explicit approval.** If the user supplies an exact confirmation phrase, require that phrase. Otherwise ask for unmistakable approval of the listed commands and targets. Approval for one plan does not authorize a fallback or a wider cleanup.
5. **Use precise supported controls.** Prefer an application's supported management command or an exact object ID. Never delete an application's internal cache files behind its back.
6. **Never use Docker prune-family commands.** This includes image, container, volume, system, builder, and buildx prune. Category-wide deletion cannot express per-object user intent.
7. **Avoid broad destructive shell forms.** Do not recommend or execute broad `rm -rf` or glob deletion. For ordinary files that the user approves, prefer Trash or `scripts/safe_delete.py`, which applies path guards and interactive confirmation.
8. **Preserve valuable state.** Never target user documents, credentials, SSH material, active databases, application configuration, or running-service state merely to increase the reported savings. Read `references/safety_rules.md` before any file deletion.
9. **Execution follows the user's authorization.** If the user asks only for analysis or wants to run commands personally, hand off the commands. If the user asks the agent to fix the machine and explicitly confirms the scoped plan, execute the exact approved commands and verify them. Unattended recurring deletion logic needs separate approval before it is written or enabled.
10. **Fail fast.** A non-zero command, a mismatched postcondition, an unexpected target, or a changed dependency stops the cleanup. Report the partial state; do not improvise a fallback.

## Phase contract

Use this state machine for every cleanup:

1. **Observe — read-only.** Capture identity, disk baseline, the suspected subsystem's status and configuration, physical allocation, and critical-service health.
2. **Plan — no mutation.** Explain findings, commands, impact, recovery, expected release, and success criteria. Stop at the confirmation gate.
3. **Execute — approved scope only.** Re-read live state immediately before acting, then run each approved command separately and check its exit status and postcondition.
4. **Verify — independent readback.** Measure disk space and subsystem state again, recheck protected services, and observe long enough to detect immediate refill.

Do not compress phases 2 and 3 into one message. A plan printed beside a cleanup command is not a confirmation gate.

## Phase 1: read-only diagnosis

### Establish the baseline

At minimum, capture:

```bash
/bin/date "+%F %T %Z %z"
/usr/sbin/scutil --get ComputerName
/usr/sbin/scutil --get LocalHostName
/usr/bin/sw_vers
/bin/df -k /System/Volumes/Data
/bin/df -h /System/Volumes/Data
```

Use `df -k` for calculations and `df -h` for the human-readable report. Treat an extension, label, or old report as a hint until the live command confirms it.

For a local target, persist the exact Data-volume baseline with:

```bash
uv run scripts/cleanup_report.py --snapshot before
```

For a remote target, keep using the direct `df` commands on that host; the local helper must not measure the controller Mac by mistake.

### Follow the named suspect before broad scans

- Query the subsystem's own status and settings.
- Measure physical allocation with a bounded `du` on the exact data path only when permissions and user scope allow it.
- Distinguish logical content size, sparse-file apparent size, purgeable space, and physically allocated bytes.
- For a suspected growing log, record exact file sizes at two or more timestamps. One large file or one recent mtime does not prove sustained growth.
- Capture the current process, listeners, launch mechanism, and supported health probe of any co-resident service the user marks as critical. Re-resolve PIDs at each checkpoint.

If the known suspect alone can meet the user's free-space target, do not scan unrelated personal or development directories “just in case.”

### General analysis when the source is unknown

Use built-in, bounded checks first. When a broad interactive view is genuinely useful, read `references/mole_integration.md` and use `mo analyze` through a TTY. Do not install or upgrade Mole during a read-only phase unless the user separately authorizes that change.

Use the bundled analyzers only inside the user's allowed scope:

```bash
uv run scripts/analyze_caches.py --user-only
uv run scripts/find_app_remnants.py
uv run scripts/analyze_large_files.py --threshold 100MB --path <approved-path>
uv run scripts/analyze_dev_env.py
```

These are analysis tools, not deletion authorization. Read `references/cleanup_targets.md` for target semantics and network/redownload trade-offs.

### Docker and OrbStack

Read `references/docker_analysis.md` before reporting Docker savings. List every image, container, and volume individually; inspect references and database-like contents; use actual sparse-file allocation rather than apparent size. A resource reported as dangling is not proof that its data is worthless.

## Phase 2: report and stop at the gate

Report observed values rather than inferred properties. Use `references/report_templates.md` for the long-form layout and include these fields for every proposed action:

| Field | Required content |
|---|---|
| Current state | Timestamp, target identity, disk used/free/capacity, and subsystem status |
| Evidence | The command and observed value; state whether the number is logical or physical |
| Exact command | The command that would change state, with the exact target or object ID |
| Change | What the command modifies or removes |
| Recoverability | Reversible command, Trash recovery, backup restore, or redownload-only |
| Expected release | Physical-space estimate with unit and assumptions |
| Service impact | User-visible effects and protected-service invariants |
| Postconditions | Values that must be true before the action is called successful |

Classify findings by consequence, not by how tempting the number is:

- **Rebuildable cache:** deletion loses only a local copy, but state the redownload or rebuild cost.
- **User decision required:** value depends on the user's workflow or ownership knowledge.
- **Preserve:** user data, credentials, database state, active configuration, or anything whose role is uncertain.

Do not call a cache “absolutely safe” merely because software can regenerate it. Regeneration time, bandwidth, authentication, and offline availability are real costs.

## Phase 3: execute the confirmed plan

Immediately before the first state-changing command:

1. Reconfirm the target identity and current disk state.
2. Re-query the objects or subsystem status; cleanup plans expire when live state changes.
3. Recheck protected-service health.
4. Compare the approved commands with the commands about to run. Any difference requires new approval.

Run one state-changing command at a time. Read the result before sending the next command. After each command, run the postcondition that can distinguish success from partial success.

For ordinary file targets, invoke the guarded helper from the skill directory after the user confirms the exact paths:

```bash
uv run scripts/safe_delete.py <exact-path> [<exact-path> ...]
```

Do not use this helper for application-managed caches such as Apple Content Caching; use that subsystem's supported management command instead.

## Phase 4: verify and observe

Verification must cover all clauses of the approved plan:

- Re-read `df -k` and `df -h`; calculate reclaimed space from before/after readings rather than from the deletion tool's claim.
- Re-query the cleaned subsystem's activation, configuration, and physical usage.
- Re-resolve each protected service's PID, listeners, launch mechanism, and health probe. A healthy disk does not prove the service survived.
- Observe at bounded intervals when APFS accounting can lag or the source may refill. Record each timestamp and value.
- If the free-space target is missed, stop all deletion. Begin a second read-only analysis and rank remaining sources by measured physical allocation.

Never report “fixed” when only the command exit code is known. A successful cleanup requires both the intended state and the protected invariants.

For a local target whose before snapshot was captured by the helper, generate the comparison with:

```bash
uv run scripts/cleanup_report.py --snapshot after --compare
```

## Resources

Load only the branch relevant to the current task:

- `references/apple_content_caching.md` — Apple Content Caching diagnosis, unit interpretation, supported remote controls, confirmation plan, and post-cleanup verification.
- `references/cleanup_targets.md` — cache, log, application, developer, large-file, and Time Machine target semantics.
- `references/docker_analysis.md` — per-object Docker and OrbStack analysis, database-volume safeguards, and refill root-cause diagnosis.
- `references/mole_integration.md` — TTY workflow for interactive Mole analysis and preview.
- `references/report_templates.md` — long-form general and Docker report templates.
- `references/safety_rules.md` — blocked paths, confirmation, recovery, and file-deletion safety checks.
- `scripts/analyze_caches.py` — bounded cache inventory.
- `scripts/find_app_remnants.py` — application-remnant candidates.
- `scripts/analyze_large_files.py` — large-file discovery inside an approved path.
- `scripts/analyze_dev_env.py` — Docker and package-manager inventory.
- `scripts/safe_delete.py` — guarded interactive deletion for exact ordinary-file targets.
- `scripts/cleanup_report.py` — local-target before/after reporting for `/System/Volumes/Data` by default, with an explicit `--volume` override.

## Do not use this skill when

- The target is Windows or Linux.
- The requested action requires disabling SIP or bypassing macOS protections.
- The user asks for silent or automatic deletion without an auditable scope and confirmation gate.
- The task is only to tune application behavior and has no disk-space diagnosis or recovery goal.
