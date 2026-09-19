---
name: macos-cleaner
description: >-
  Diagnoses and safely reclaims macOS disk space. Use when a Mac is low on
  storage, reports “Caching needs more space,” shows large Apple Content
  Caching or AssetCacheManagerUtil usage, or needs analysis of caches, logs,
  application remnants, large or duplicate files, Docker or OrbStack,
  Chromium code-sign clones, Homebrew, npm, pip, Xcode, and other developer
  storage. Routes known suspects to targeted read-only diagnosis before broad
  scans, distinguishes nominal path accounting from physical release, requires
  an impact-and-recovery plan plus explicit confirmation before state changes,
  and verifies disk space and co-resident services afterward.
---

# macOS Cleaner

Diagnose the actual source of disk pressure, reclaim only approved space, and prove that the cleanup did not damage user data or co-resident services.

## Entry router

Choose the narrowest path that can answer the request:

| User signal | Route |
|---|---|
| Apple Content Caching, `AssetCacheManagerUtil`, `CacheUsed`, `ActualCacheUsed`, iCloud cache, or “Caching needs more space” | Read `references/apple_content_caching.md` completely before probing or proposing commands |
| Docker, OrbStack, images, containers, or volumes | Read `references/docker_analysis.md`; inspect every object and never use prune-family commands |
| Docker build cache | Measure with `docker builder du`; this skill reports it but does not delete it because Docker exposes category-wide prune controls rather than per-record intent |
| Chrome, ChromeDriver, Playwright, Codex Computer Use, Edge, or Chromium has large `*.code_sign_clone` directories | Read `references/chromium_code_sign_clones.md` completely; use the bundled analyzer to separate active, inactive, and unknown exact children and never equate `du` with physical release |
| A named cache, directory, application, or service is already the suspect | Inspect that target first and read the matching semantics in `references/cleanup_targets.md`; do not start a home-directory or whole-disk scan |
| The source is genuinely unknown | Use the general analysis workflow below; Mole is optional, not the universal first step |

User-provided scope exclusions override every generic scan suggestion. Do not inspect personal directories, credentials, databases, application state, or unrelated services when the user excludes them.

## Safety and authorization contract

1. **Separate observation from mutation.** Complete a read-only diagnosis first. Do not delete, stop a service, edit settings, install or upgrade tools, or run a cleanup preview that may mutate state during that phase.
2. **Confirm the exact target.** On a remote Mac, record the current host identity before any other work. Never infer the machine from an IP, old PID, directory name, or prior report.
3. **Plan before asking.** Before any state change, list every command, what it changes, expected physical space reclaimed, impact, recoverability, and postconditions. Then stop if the user requested a plan-only phase.
4. **Require explicit approval.** If the user supplies an exact confirmation phrase, require that phrase. Otherwise ask for unmistakable approval of the listed commands and targets. Approval for one plan does not authorize a fallback or a wider cleanup.
5. **Use precise supported controls.** Prefer an application's supported cache-management command or an exact object ID. If no supported control exists, an exact application-owned cache directory may be removed only after verifying its owner, confirming the application is stopped or the directory is otherwise inactive, explaining rebuild/redownload impact, and receiving approval. Never target a broad cache root or active application state.
6. **Never use Docker prune-family commands.** This includes image, container, volume, system, builder, and buildx prune. Category-wide deletion cannot express per-object user intent.
7. **Avoid broad destructive shell forms.** Do not recommend or execute broad `rm -rf` or glob deletion. For exact approved ordinary files, prefer Finder Trash. The bundled legacy helper permanently deletes and has only the limited guards documented below; never treat it as equivalent to Trash.
8. **Preserve valuable state.** Never target user documents, credentials, SSH material, active databases, application configuration, or running-service state merely to increase the reported savings. Read `references/safety_rules.md` before any file deletion.
9. **Execution follows the user's authorization.** If the user asks only for analysis or wants to run commands personally, hand off the commands. If the user asks the agent to fix the machine and explicitly confirms the scoped plan, execute the exact approved commands and verify them. Unattended recurring deletion logic needs separate approval before it is written or enabled.
10. **Fail fast.** An unexpected non-zero command, a mismatched postcondition, an unexpected target, or a changed dependency stops the cleanup. Interpret documented probe statuses such as `lsof` exit 1 with empty output before deciding they are failures. Report the partial state; do not improvise a fallback.

## Phase contract

Use this state machine for every cleanup:

1. **Observe — read-only.** Capture identity, disk baseline, the suspected subsystem's status and configuration, physical allocation, and critical-service health.
1b. **Authorize stateful inspection when unavoidable.** If deeper evidence requires creating a temporary container, pulling an image, mounting a volume, or writing a snapshot, first finish the metadata-only observation, list the exact inspection commands and their side effects, and obtain separate approval. Inspection approval is not cleanup approval.
2. **Plan — no mutation.** Pass the Phase 2 entry gate first (four steps: target confirmation, classification table, gate rules, checker — see below), then explain findings, commands, impact, recovery, expected release, and success criteria. Stop at the confirmation gate.
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

Establish the success target before an unknown-source scan. Copy a user-supplied free-space or capacity target exactly. If the user supplied none, report the current values and ask for a target in GiB, capacity percentage, or both; do not invent one. A named-suspect diagnosis may continue without a cleanup target, but the ordered unknown-source scan cannot claim a stop condition until the target is explicit.

Keep this first phase read-only. Do not run `scripts/cleanup_report.py` yet: it creates a local state directory and snapshot file. Preserve the command output in the report instead. On a remote target, always run the direct `df` commands on that host; the local helper must not measure the controller Mac by mistake.

### Follow the named suspect before broad scans

- Query the subsystem's own status and settings.
- Measure physical allocation with a bounded `du` on the exact data path only when permissions and user scope allow it.
- Distinguish logical content size, sparse-file apparent size, purgeable space, and physically allocated bytes.
- For APFS clones, label `du` as path-accounted or nominal rather than physical: shared extents can be attributed to every path, so actual release remains unknown until deletion and `df` readback.
- For a suspected growing log, record exact file sizes at two or more timestamps. One large file or one recent mtime does not prove sustained growth.
- Capture the current process, listeners, launch mechanism, and supported health probe of any co-resident service the user marks as critical. Re-resolve PIDs at each checkpoint.

If the known suspect alone can meet the user's free-space target, do not scan unrelated personal or development directories “just in case.”

### General analysis when the source is unknown

Run the smallest ordered sequence that can identify enough physical space to meet the target. Stop only when candidates with supported exact actions and defensible expected physical release can meet it. Raw allocation totals, logical cache sizes, shared Docker layers, Trash moves, and unverified “potential savings” do not satisfy the stop condition.

Do not make the physical-confidence ranking hide the user's largest visible
hotspot. When a nominal/path-accounted candidate is larger than the recommended
action, show both numbers and explain why its physical release is uncertain.
Rank by defensible physical release, safety, and effort; report nominal size as
a separate column instead of silently treating it as either zero or fully
reclaimable.

| Order / signal | Read-only action | Stop or continue |
|---|---|---|
| 1. Always | Capture identity and `df -k/-h`; inventory user exclusions | Stop on target mismatch |
| 2. Cache/log pressure, and `~/Library/Caches`, `~/Library/Logs`, plus the XDG dev caches are approved read scopes | `uv run scripts/analyze_caches.py --user-only --include-dev` | Stop when measured candidates can meet the target |
| 3. Developer tools are present and the script's fixed scope is approved | `uv run scripts/analyze_dev_env.py` reads Docker/package managers plus existing `~/Projects`, `~/workspace`, `~/dev`, `~/src`, and `~/code` roots | Route Docker/OrbStack findings to their dedicated reference; skip this helper when any fixed root is out of scope |
| 4. Uninstalled-app residue is plausible and its fixed roots are approved | `uv run scripts/find_app_remnants.py` reads `/Applications`, `~/Applications`, and four documented `~/Library` application-state roots | Treat every result as a candidate, never proof of abandonment; skip when that scope is not approved |
| 5. A content-bearing path is explicitly approved | `uv run scripts/analyze_large_files.py --threshold 100MB --path "<approved-path>"` | Do not substitute `~`, Downloads, Documents, or the data-volume root when no path was approved |
| 6. Still unknown after bounded checks, and the user explicitly approves Mole's fixed broad scan roots | Read `references/mole_integration.md` and use `mo analyze` through a TTY | Mole cannot accept an arbitrary path scope; skip it when approval is narrower than its documented roots |

An `<approved-path>` is an exact path the user named or explicitly accepted after its scope was described. If none exists, skip large-file and duplicate-content scanning, state that this evidence branch was not authorized, and continue with non-content-bearing evidence. Do not install or upgrade Mole during a read-only phase unless the user separately authorizes that change.

Mole's analyzer scans a fixed set that includes the home directory, application data, system libraries, applications, and volumes. Navigation inside the results does not make the underlying scan path-scoped. If that broad read scope is not approved, do not run Mole; stop with the bounded evidence already collected or ask for the missing scan authorization in the plan.

For an explicitly approved duplicate-file investigation, read the “Optional duplicate files” section in `references/cleanup_targets.md`. It is read-only and never uses an automatic-delete option.

**A large data folder is not a cache — proposing its deletion needs an evidence chain, not a size ranking.** When discovery surfaces a big project-asset / media / dataset directory (not a cache, not an app remnant), do NOT put it in the action set on size alone: read `references/proving-redundancy-before-deletion.md` and climb its ladder (file-level duplication → creation-origin → reference check → session-history tool-call census → .DS_Store manual-usage trace → the project's own decision records) before proposing anything. The deliverable is the evidence table; the unprovable row (purely manual usage) goes to the user, never gets papered over.

When discovery is fanned out to sub-agents, each returns candidates and measurements only — the classification, the acceptance, and the proposal happen in the session that runs the Phase 2 entry gate. A sub-agent's inventory is input to the classification table, never the plan.

### Docker and OrbStack

Read `references/docker_analysis.md` before reporting Docker savings. List every image, container, and volume individually; inspect references and database-like contents; use actual sparse-file allocation rather than apparent size. A resource reported as dangling is not proof that its data is worthless. Build-cache measurement is supported, but build-cache deletion is deliberately out of scope because the available Docker controls are prune-family operations.

## Phase 2: report and stop at the gate

### Phase 2 entry gate — four steps before any plan text

A real 2026-09-19 run followed the Phase 1 machinery to the letter and still shipped three bad plans: it proposed preserve-by-default caches (npm `_cacache`, Playwright browsers, Homebrew) as a "low-risk combo" because the rule lives in `references/cleanup_targets.md` — a file the discovery workflow never opens; it proposed `uv cache prune` as zero-impact from a `--help` line plus size ratios, never verifying semantics or the installed version; and it led with 2 GB items beside a 91 GB candidate because no free-space target had been set. The rules that would have caught all three already existed in this skill — in a reference the procedure never opened, which makes them not rules in practice. A prose checklist is only one level better than the reference it summarizes: an independent review of the first draft of this gate found thirteen blocking defects, the deepest being that the gate itself had no mechanical enforcement. Step 4 is therefore a script, not a promise — run it, or the plan does not exist.

1. **Confirm the free-space target.** A named-suspect diagnosis may continue without one (the Phase 1 exemption); an unknown-source scan may not — if the user supplied none, ask before ranking. A scan without a target has no stop condition and produces size-sorted noise.
2. **Open `references/cleanup_targets.md`** and classify every candidate the discovery produced into this table, written to a file (step 4 parses it):

   | Target | Nominal size | Physical confidence | Class | Governing rule (verbatim quote) | Expected physical release + basis | Restoration cost | Verdict |
   |---|---|---|---|---|---|---|---|
   | exact target: a path, a service setting (e.g. `AssetCacheManagerUtil` or a plist key), or a supported control (e.g. `chrome://settings/clearBrowserData`) | du output | path-accounted (Phase 1's label for APFS-shared or nominal du) / sparse-aware / engine-reported (a subsystem's own accounting, e.g. Docker `system df`) / unknown — never enter a nominal number as release | PRESERVE / PROPOSABLE / REBUILDABLE / USER-DATA / USER-DECISION | a quote from `cleanup_targets.md`, the route's dedicated reference, or this skill's own SKILL.md (the checker verifies every quote against the whole bundle and prints per-file provenance, so SKILL.md-only quotes stay visible); "no rule found" is itself a finding | an estimate plus how it was derived; unknown is an allowed value | redownload/rebuild cost, or n/a | in action set / not in action set / unlocked by user (quote the direction) |

   - **PRESERVE** — every row of the preserve-by-default table in `cleanup_targets.md` (opened in this step, quoted in the table — step 4 verifies the quotes, so a fabricated quote fails). Out of the action set unless (a) verified never-used evidence exists for the target, or (b) the user explicitly names that target for cleaning knowing the cost. Accepting a cost you stated is not (b): the user must name the target themselves.
   - **PROPOSABLE** — verified never-used evidence (a dead project, an explicit user statement, an artifact check). Size ratios are not evidence: "the cache holds 586 environments, 28 project venvs exist" proves nothing about the other 558.
   - **REBUILDABLE** — not in the preserve-by-default table, has a supported management command or cheap rebuild (Homebrew, pip), restoration cost stated in the row.
   - **USER-DATA** — never in an action set; report the location, never a command.
   - **USER-DECISION** — the user's workflow or ownership knowledge decides; ask, don't propose. Also the home for targets no reference covers ("no rule found"): the plan asks before proposing anything for them.

   If no reference anywhere covers a target, say "no rule found" and classify it USER-DECISION — do not stretch an unrelated rule to cover it.

3. **Apply the gate rules.** Step 4's checker enforces each one mechanically — that is what makes them rules rather than reminders:
   - The action set contains exactly the rows marked "in action set" plus rows marked "unlocked by user" with the user's direction quoted. No state-changing command may name a target absent from the table. PRESERVE rows enter the action set only via never-used evidence or explicit user direction (step 2).
   - The plan leads with the in-action-set row holding the largest expected physical release — unless the table marks another row as the user-visible hotspot or bottleneck (the thing the disk pressure is actually about) with a stated reason. Any other lead row fails this gate; that is the small-fish failure, not conservatism. Never rank by nominal size alone: nominal is not release, and for shared-extent candidates the release is unknown until deletion and `df` readback (step 2's labels).
   - Every destructive command records: the owning tool's installed version (for an application control or a service command, the owning application or service); the semantics source (the tool's own help or documentation — if the only available source is this skill's transcription, say so and verify cheaply against the live tool); and for category-wide commands — scope is an entire class of objects with no per-object selection; the skill's existing term is prune-family — a known-issue check. `uv cache prune`, `npm cache clean`, `brew cleanup --prune`, and the Docker prune family are category-wide by definition.
   - Commands the skill declares unsanctioned (`uv cache prune`, `npm cache clean`, the Docker prune family) may not appear in the action set even when every other rule passes — not for any size, not for any version. `npm cache clean` joins the list because it wipes the preserve-by-default `_cacache` wholesale. Only an explicit user instruction for that exact command moves it, and it runs in Phase 3 as a directed action, never as a proposal.
   - Zero in-action-set rows is a legitimate outcome: deliver the ranked decision list (PRESERVE and USER-DECISION rows with their unlock costs and evidence) and ask the user which to unlock. An empty action set with a decision list passes; inventing rows or downgrading PRESERVE to fill it does not.

4. **Write the plan to a file, then run the checker before sending it:**
   ```bash
   uv run scripts/check_gate_plan.py --table <gate-table.md> --plan <plan.md>
   ```
   Exit 0 is required. The checker verifies: the table exists and classifies the candidates; every governing-rule quote appears verbatim in the reference (this is what forces the reference open — a fabricated quote fails); every destructive command the checker recognizes has its stated target matched to a table row (commands in unrecognized forms are counted and reported, never silently passed); the action set obeys the class and unlock rules, including the preserve-by-default cross-check; no category-wide command sits in the action set; the lead row obeys the ranking rule; every destructive command carries its tool verification. A failing run names the violated rule — fix the plan; do not weaken the checker.

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

- **Rebuildable cache:** deletion loses only a local copy, but state the redownload or rebuild cost. **Rebuildable is not proposable by default:** the preserve-by-default table in `references/cleanup_targets.md` (opened and quoted in the Phase 2 entry gate) decides; those targets stay out of the action set until never-used evidence or explicit user direction moves them.
- **User decision required:** value depends on the user's workflow or ownership knowledge.
- **Preserve:** user data, credentials, database state, active configuration, or anything whose role is uncertain.

Do not call a cache “absolutely safe” merely because software can regenerate it. Regeneration time, bandwidth, authentication, and offline availability are real costs.

## Phase 3: execute the confirmed plan

Immediately before the first state-changing command:

1. Reconfirm the target identity and current disk state.
2. Re-query the objects or subsystem status; cleanup plans expire when live state changes.
3. Recheck protected-service health.
4. Compare the approved commands and exact target set with the commands about to run. Any wider or different target set requires new approval. A separately preserved item becoming inactive does not invalidate the plan when it remains explicitly excluded and the approved target-set hash still matches.

If the approved plan includes creation of a local before/after report artifact, capture the before snapshot now, after approval and before the first cleanup command:

```bash
uv run scripts/cleanup_report.py --snapshot before
```

This writes under `~/.macos-cleaner`, so list it in the plan. It is optional and local-target only; direct `df -k/-h` readings remain the source of truth. Never run it on the controller Mac as a substitute for measuring a remote target.

Run one state-changing command at a time. Read the result before sending the next command. After each command, run the postcondition that can distinguish success from partial success.

For an exact ordinary file that is not user data, application state, a database, or a protected path, prefer a recoverable Finder Trash move after the user confirms the exact path:

```bash
/usr/bin/osascript \
  -e 'on run argv' \
  -e 'tell application "Finder" to delete (POSIX file (item 1 of argv))' \
  -e 'end run' -- "<exact-path>"
```

Moving to Trash usually releases no physical space until Trash is emptied; state that in the plan. `scripts/safe_delete.py` is a legacy permanent-deletion helper with an interactive prompt and a limited system/credential denylist. It does not move to Trash, check every user-data root, detect open files, or independently prove reclaimed bytes. Use it only when the exact non-user-data target and irreversible deletion were explicitly approved:

```bash
uv run scripts/safe_delete.py <exact-path> [<exact-path> ...]
```

Do not use this helper for user documents, application-managed caches such as Apple Content Caching, databases, credentials, or any target whose role is uncertain.

Two narrow Finder-Trash branches remain available without weakening those exclusions:

- For an exact inactive application cache with no verified supported management control, follow the named-cache discovery/in-use protocol in `references/cleanup_targets.md`, explain the rebuild cost, and obtain explicit approval for that exact cache path.
- For duplicate files inside an exact approved user-data root, first show each duplicate set's size/hash and every path. The user must name the copy to keep and each copy to remove. Move only those confirmed files to Finder Trash; never use the permanent helper, an automatic duplicate-selection flag, `all`, a glob, or a directory-level target. Verify the source paths moved to Trash, and state that physical space is not released until Trash is separately reviewed and emptied.

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
- `references/chromium_code_sign_clones.md` — Chrome/Chromium/Edge code-sign-clone semantics, nominal-versus-physical reporting, exact inactive-target manifests, cleanup verification, and recurrence prevention.
- `references/cleanup_targets.md` — cache, log, application, developer, large-file, and Time Machine target semantics.
- `references/proving-redundancy-before-deletion.md` — the evidence ladder for large data folders (duplication → creation-origin → references → session-history census → .DS_Store → project decision records). Load BEFORE proposing deletion of any big project-asset / media / dataset directory; a size ranking is not evidence.
- `references/docker_analysis.md` — per-object Docker and OrbStack analysis, database-volume safeguards, and refill root-cause diagnosis.
- `references/mole_integration.md` — TTY workflow for interactive Mole analysis and preview.
- `references/report_templates.md` — long-form general and Docker report templates.
- `references/safety_rules.md` — blocked paths, confirmation, recovery, and file-deletion safety checks.
- `scripts/analyze_caches.py` — bounded cache inventory.
- `scripts/check_gate_plan.py` — Phase 2 entry gate checker: parses the classification table and the plan, verifies governing-rule quotes against the references, destructive-command target coverage (with unrecognized command forms counted and reported), action-set class and unlock rules, the preserve-by-default downgrade cross-check, category-wide exclusions, the lead-row ranking rule, and tool verification. Exit 0 is required before a plan may be sent. Its command whitelist is a declared limitation: forms outside the list are reported as unrecognized rather than silently ignored.
- `scripts/analyze_code_sign_clones.py` — read-only current-user code-sign-clone inventory; after approval it can revalidate an exact candidate SHA and write a non-overwriting batch manifest.
- `scripts/find_app_remnants.py` — application-remnant candidates; reads its fixed Applications and `~/Library` roots, so require that scope first.
- `scripts/analyze_large_files.py` — large-file discovery inside an approved path.
- `scripts/analyze_dev_env.py` — Docker/package-manager inventory plus fixed common-project-root `.git` sizing; require that full read scope first.
- `scripts/safe_delete.py` — legacy guarded permanent deletion for exact approved non-user-data targets; it is not a Trash or recovery tool.
- `scripts/cleanup_report.py` — local-target before/after reporting for `/System/Volumes/Data` by default, with an explicit `--volume` override.

## Do not use this skill when

- The target is Windows or Linux.
- The requested action requires disabling SIP or bypassing macOS protections.
- The user asks for silent or automatic deletion without an auditable scope and confirmation gate.
- The task is only to tune application behavior and has no disk-space diagnosis or recovery goal.
