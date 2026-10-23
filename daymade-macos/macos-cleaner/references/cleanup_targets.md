# macOS Cleanup Targets Reference

Detailed explanations of cleanup targets, their safety levels, and impact.

## System Caches

### ~/Library/Caches

**What it is**: Application-level cache storage for user applications.

**Contents**:
- Browser caches (Chrome, Firefox, Safari)
- Application temporary files
- Download caches
- Thumbnail caches
- Font caches

**Safety**: 🟡 **Rebuildable, not automatically disposable**

**Impact**:
- Apps may be slower on first launch after deletion
- Websites may load slower on first visit (need to re-download assets)
- Local cache copies are regenerated, but redownload time, bandwidth, authentication, and offline availability may matter

**Size**: Typically 10-100 GB depending on usage

Inventory exact application-owned subdirectories first and prefer the application's supported cache-management command when one exists. If none exists, verify the owning application is stopped or the directory is otherwise inactive. After the user approves the named directory and rebuild/redownload impact, use the recoverable Finder Trash command from the main skill. Do not route application state through the legacy permanent-deletion helper.

Do not pass `~/Library/Caches/*` or the whole cache root. Do not remove an exact cache directory while its owning application or service is using it. The application may store active state beside disposable cache files.

### /Library/Caches

**What it is**: System-level cache storage (shared across all users).

**Safety**: 🟡 **System-managed; inspect and use the owning subsystem's supported control**

**Impact**: System-wide redownload/rebuild cost; some entries are protected or active.

Do not delete `/Library/Caches/*` as a category. Identify the owning subsystem, confirm the exact target, and prefer its supported reset or cache-management command.

### Package Manager Caches

#### Homebrew Cache

**Location**: `$(brew --cache)` (typically `~/Library/Caches/Homebrew`)

**What it is**: Downloaded package installers and build artifacts

**Safety**: 🟡 **Rebuildable**

**Impact**: Will need to re-download packages on next install/upgrade

**Cleanup after the exact Homebrew impact is approved**:
```bash
brew cleanup -s          # Safe cleanup (removes old versions)
brew cleanup --prune=all # Aggressive cleanup (removes all cached downloads)
```

#### npm Cache

**Location**: `~/.npm` or configured cache directory

**Safety**: 🟡 **Rebuildable**

**Impact**: Packages will be re-downloaded when needed

**Cleanup after the redownload impact is approved**:
```bash
npm cache clean --force
```

Under the Phase 2 entry gate this command is category-wide and unsanctioned in a plan's action set — it wipes the preserve-by-default `_cacache` wholesale, the same reasoning that bars `uv cache prune`. It stays available as a user-directed action or an unlock option with the redownload cost stated, never as a skill-proposed action-set entry. The narrow `_npx` target below is the skill-sanctioned form.

#### pip Cache

**Location**: `~/Library/Caches/pip` (macOS)

**Safety**: 🟡 **Rebuildable**

**Impact**: Packages will be re-downloaded when needed

**Cleanup after the redownload impact is approved**:
```bash
pip cache purge
# or for pip3
pip3 cache purge
```

## Application Logs

### ~/Library/Logs

**What it is**: Application log files

**Safety**: 🟡 **Diagnostic history; inspect before deletion**

**Impact**: Loss of diagnostic information (only matters if debugging)

**Typical size**: 1-20 GB

After confirming no active investigation needs the logs, move exact named files/directories through the recoverable Finder Trash path in the main skill. Do not remove the whole log root.

### /var/log (System Logs)

**What it is**: System and service log files

**Safety**: 🟡 **System-managed diagnostic history**

**Impact**: Loss of system diagnostic history

**Note**: macOS automatically rotates logs, manual deletion rarely needed

## Application Data

### ~/Library/Application Support

**What it is**: Persistent application data, settings, and databases

**Safety**: 🟡 **Caution required**

**Contains**:
- Application databases
- User preferences and settings
- Downloaded content
- Plugins and extensions
- Save games

**When it may become a removal candidate**:
- Application is confirmed uninstalled
- Folder belongs to trial software no longer used
- Folder is for outdated version of app (check first!)

**When to KEEP**:
- Active applications
- Any folder you're uncertain about

**Recommendation**: Use `find_app_remnants.py` to identify orphaned data

### ~/Library/Containers

**What it is**: Sandboxed application data (for App Store apps)

**Safety**: 🟡 **Caution required**

**Same rules** as Application Support - only delete for uninstalled apps

### ~/Library/Preferences

**What it is**: Application preference files (.plist)

**Safety**: 🟡 **Caution required**

**Impact of deletion**: App returns to default settings

**When to delete**:
- App is confirmed uninstalled
- Troubleshooting a misbehaving app (as last resort)

## Development Environment

### High-value developer caches: preserve by default

These were explicit decision points in the original skill and remain reachable for any named-cache request. A cache can be rebuildable and still be valuable. Measure the exact live path and ask whether its rebuild/redownload cost is acceptable before proposing removal — but an acceptable cost is not by itself sufficient: under the Phase 2 entry gate, these targets enter an action set only on verified never-used evidence or an explicit user direction naming the target.

| Target | Value retained | Real deletion impact | Default |
|---|---|---|---|
| Xcode DerivedData | Compiled products and indexes for active projects | The next full build can take materially longer; prior field examples were 10–30 minutes | Keep unless the user names inactive projects or accepts the rebuild |
| npm `_cacache` | Downloaded package content | `npm install` redownloads packages; constrained networks can turn this into a long reinstall | Keep; do not confuse it with `_npx` |
| uv cache | Downloaded/built Python packages | Environments may need to fetch or rebuild dependencies again | Keep unless the user accepts dependency restoration cost |
| Playwright browser cache | Browser binaries used by automation | Browsers must be downloaded again; this can be several GiB | Keep when tests or automation use Playwright |
| iOS DeviceSupport | Symbols/support files for attached iOS versions | Xcode/device debugging may need to download support again | Keep for iOS versions still in use |
| Hugging Face cache | Model weights and datasets | Large models may take hours to redownload and may be unavailable offline | Keep unless exact artifacts are obsolete |
| ModelScope cache | Model weights and datasets, often chosen for China-accessible delivery | Same redownload/offline cost as other model stores | Keep unless exact artifacts are obsolete |
| JetBrains caches | IDE indexes and caches | The IDE must re-index; prior field examples were 5–10 minutes | Keep for active projects |
| Stopped Docker containers | Writable container state and restartable instances | Removing them can lose state and prevents `docker start` reuse | Inspect every container; never classify by stopped status alone |

The historical time/size examples above are impact illustrations, not current measurements. Use live allocation and the user's actual network/project activity in the plan.

#### Targeted discovery and measurement

Do not reopen a broad Mole scan for a named developer cache. Resolve one exact path from the current tool/application configuration, then measure only that path.

| Target | Authority for the exact live path | Default candidate only when no override is found | Supported/narrow next step |
|---|---|---|---|
| Chromium code-sign clones | `scripts/analyze_code_sign_clones.py` resolves the current user's `DARWIN_USER_TEMP_DIR` sibling `X` directory and validates exact owned roots | None; do not scan every user's `/private/var/folders` tree | Read `chromium_code_sign_clones.md`; preserve active/unknown children and bind any inactive batch to the analyzer's exact candidate SHA |
| Xcode DerivedData | Xcode **Settings → Locations → Derived Data** | `~/Library/Developer/Xcode/DerivedData` | Quit Xcode; prefer removing an exact inactive project child. Whole-root Trash requires explicit rebuild-cost approval. |
| npm `_cacache` / `_npx` | `npm config get cache`, then append the exact child name | None; do not guess around npm's returned root | `_npx` may go to Trash after confirming no `npx` process. Keep `_cacache` by default; whole-cache removal requires explicit redownload approval. |
| uv cache | `uv cache dir` (honors `--cache-dir`, `UV_CACHE_DIR`, and uv config) | `$XDG_CACHE_HOME/uv` or `~/.cache/uv` only as a candidate | [uv cache retirement](#uv-cache-retirement) |
| Playwright browsers | The project's `PLAYWRIGHT_BROWSERS_PATH` / runner configuration | `~/Library/Caches/ms-playwright` only as a candidate | Stop Playwright/browser processes. Prefer project-supported browser removal; otherwise move the verified whole inactive cache to Trash, not internal browser files guessed by name. |
| iOS DeviceSupport | Xcode's active platform/device support view plus the exact on-disk directory | `~/Library/Developer/Xcode/iOS DeviceSupport` | Quit Xcode; move only an exact OS-version child no longer needed for connected-device debugging. |
| Hugging Face cache | Active service/project values for `HF_HOME`, `HF_HUB_CACHE`, or `XDG_CACHE_HOME` | `~/.cache/huggingface` only as a candidate | Prefer the installed Hugging Face cache-management command after verifying its current help. Without a verified supported control, keep internal cache subsets; whole inactive cache Trash is a separate user decision. |
| ModelScope cache | Active service/project cache configuration | `~/.cache/modelscope` only as a candidate | Prefer the installed ModelScope cache-management command after verifying its current help. Without one, keep internal subsets; whole inactive cache Trash needs explicit redownload approval. |
| JetBrains caches | **Help → Diagnostic Tools → Special Files and Folders** or `idea.system.path` | `~/Library/Caches/JetBrains/<product><version>` | Quit the IDE; prefer its cache invalidation UI. An exact cache for an uninstalled/retired product version may go to Trash. Never target config/plugins/local history by assuming every JetBrains directory is cache. |
| Stopped Docker container | `docker inspect <exact-name-or-id>` plus `docker ps -a` | None | Use `references/docker_analysis.md`; stopped status alone never authorizes removal. |

#### uv cache retirement

Before classifying a uv target, distinguish its role from its directory name:

| Role | Check before retirement | Consequence |
|---|---|---|
| Downloaded/built package archives | Resolve the configured cache and exact package names; check current references and restoration inputs | A later install may download or build again; shared extents/hard links can limit physical release |
| Cache-managed execution environments | Inspect the actual launcher, environment configuration and active consumers | A running or later invocation may depend on the cached environment; preserve active or unresolved references |
| Project/service persistent virtual environment | Resolve its Python, base interpreter, lockfile and owning installer | This is a runtime, even when reproducible; retire it through its project/service lifecycle, not a cache cleanup |

Treat internal bucket names and suffixes as installed-version details. Do not
infer abandonment from a name, age, bucket version or cache-to-project count.
Keep missing reference evidence `unknown`; a cache's total allocation is not a
garbage estimate. Never manually delete an internal cache subset.

For an approved finite package list, check `uv --version`, `uv cache clean --help`
and relevant known issues for that installed release before selecting the command.
When its help accepts `[PACKAGE]...`, clean the approved names in one official
invocation, for example `uv cache clean <package-a> <package-b>`; otherwise retain
the supported single-package form. Keep whole-cache cleanup separately authorized.

If another uv command holds the cache lock, identify its owner and active work
read-only. A transient busy observation is not a cleanup failure: allow one
bounded official wait using `UV_LOCK_TIMEOUT=<seconds> uv cache clean <package-a> <package-b>`,
with the duration chosen for this task and confirmed against current
uv documentation. Do not use `--force`, stop another job, or repeatedly restart the
same attempt. On timeout, report the holder and remaining approved targets; resume
only after a changed condition, such as the holder completing its work. Recheck
the target and protected consumers before resuming.

After success, verify the approved package postcondition, preserved environments
and a real affected consumer through the existing Phase 4 checks. Do not infer
physical release from the command's estimate or include non-target objects in the
claimed cleanup. The executing agent owns this classification and lock decision;
the plan checker does not prove environment liveness or approval of each package
argument. Compare every supplied name with the approved list before execution.

Use the current [uv cache documentation](https://docs.astral.sh/uv/concepts/cache/)
for bucket versioning, supported cleanup, cache locks and `UV_LOCK_TIMEOUT`.

**Measured phantom calibration (2026-10-21, same disk, three probes):** `du` nominal 123 G on the uv cache produced only ~38 GiB of physical release on `df` — a >3x nominal overstatement. `find -links +1` between project venvs and the cache returned 0 and archive-v0 samples all had nlink=1, yet the clonefile/CoW shared extents were invisible at the stat/links layer: blocks still referenced by venvs were not released by the clean. A 108 G full-clonefile snapshot that same day reported du=108 G and released ≈0 on deletion. Consequences: (a) ranking emergency targets by nominal `du` can select a physically near-zero clonefile snapshot as the top target while skipping real bytes — this happened three times in one day; (b) every expected-release entry for this cache stays `unknown` until a `df` readback; (c) uv ≥ 0.12.17 offers `uv cache clean --preview-features cache-physical-space` whose hardlink/CoW-corrected estimate can be cross-checked against the `df` delta. The generic mechanism table lives in SKILL.md safety rule 11; this entry is the uv-specific measured anchor.

**Growth semantics (measured 2026-10-21, three-way checked against docs + installed help + source comments).** uv has no cache size limit and no stable auto-prune: issue #5731 (cache size limit) was still open/needs-design as of 2026-10-12 and the auto-prune PR (#20116) had not landed in the installed 0.12.17 stable — so retention exists only via an externally scheduled `uv cache clean`. Growth engine measured on this machine: 41.3 GiB (post 09-19 prune) → 123 GiB (10-21), ~2.6 GB/day; composition ≈ environments-v2 (1,966 ephemeral environments, 48-58 new/day ≈ 1.3 GB/day, mostly agent-session `uv run --script`) + archive-v0 ≈ 1.2 GB/day; 22 LaunchAgents invoke uv ~2,800 times/day. Without a scheduled clean this is a monthly +78 G-class refill loop — the 09-19 prune → 10-21 full disk was one complete measured cycle. Scheduled-clean wrapper design: weekly, no `--force`; rely on uv's own lock wait plus bounded retries (5 x 120 s) to absorb the ~2,800/day short-task jitter; precheck network (one small online resolve) before cleaning and abort the run if it fails — a full clean followed by an offline rebuild window silently breaks dependent jobs; total retry failure needs a notification exit, not a log line (one missed week ≈ +18 G on a 99%-full disk); stagger the window against other heavy-IO jobs. Post-clean, the only truly hurt consumer class is `--offline` jobs with non-empty dependencies (e.g. a 45-second scheduled sync) whose failure mode is a silent stall writing only a local last-failure JSON; warm the cache through the real chain (run the actual launcher once so the forked inner script rebuilds its own PEP-723 environment), never through guessed `--with` keys — cache keys drift silently across release switches.

**Lock semantics (source-verified 2026-10-21).** While the cache is active, any running uv command holds a read (shared) lock that prevents cache cleaning; `clean`/`prune` need the exclusive lock (`<cache>/.lock`). `UV_LOCK_TIMEOUT` defaults to 300 s (configurable since 0.9.4); a timeout is a retryable failure exit, not corruption — do not read it as damage and do not "fix" it with `--force`, which skips the in-use check and can turn the ~2,800 daily short jobs into real failures inside a millions-of-files delete window. A full clean of a 123 G / millions-of-files cache is slow (issue #9790 has a '270 GB took hours' sample — duration unmeasured here, treat as unknown); high-frequency jobs that hit the window will fail transiently on their own 300 s wait and self-heal after the clean, except `--offline` consumers (see the growth-semantics entry).

#### `uv cache prune` is not sanctioned here — a hard exclusion (verified 2026-09-19)

`uv cache prune` may never appear in a plan's action set:

- **"Unreachable" is cache-graph reachability, not venv liveness.** `uv cache prune` does not track which environments use which objects (astral-sh/uv#10153, maintainer), so "the cache holds 586 environments but only 28 project venvs exist" is not evidence that the rest are dead.
- **Pre-0.12.x builds follow symlinks out of the cache during prune** (astral-sh/uv#19542; fixed in 0.12.x by PR #19543). Measured on a machine running uv 0.11.21: `environments-v2` held 1918 symlinks, 1775 of them pointing at managed Python install trees under `~/.local/share/uv/python/`, and prune's removal is directory-level — it can delete the interpreter trees of live venvs.

In a recorded 2026-09-19 run, upgrading 0.11.21 → 0.12.17 and pruning changed cache readings from 92.2 to 41.3 GiB, with sampled venvs still importing and the managed Python tree intact. A user who explicitly directs that command may run it in Phase 3 — but a version fix addresses only the symlink bug, not the reachability semantics, so this stays a directed action, never a skill proposal. Do not cite that historical cache-size change as a reason to propose it: size is not evidence, and the Phase 2 entry gate's lead rule would otherwise structurally reward exactly that. For the supported alternative, follow [uv cache retirement](#uv-cache-retirement).

This entry is the worked example for safety rule 5's known-issue check. What made it decisive was searching the command's defect history **before** running it — the session that found #19542 this way was one search away from pruning a machine whose 1775 cache symlinks pointed at the interpreter trees of live venvs, and it had no independent way to notice the damage afterward. Note the shape of both defects: neither is visible from the tool's own help text or from the size of the cache, and both are specific to a *version* of the command, which is why the check must name the installed version rather than the command. Apply the same check to every supported control in this table before it enters a plan — including the ones already recommended here.

For an ordinary resolved `<exact-cache-path>`, use path-accounted blocks and an
in-use check. APFS code-sign clones use their dedicated analyzer/reference
instead because shared extents and multi-child activity need separate handling:

```bash
/usr/bin/du -sk "<exact-cache-path>"
/usr/sbin/lsof +D "<exact-cache-path>"
```

Canonicalize the target path before interpreting `lsof`. Any output record
naming the target or one of its descendants proves it is in use. Exit 1 with
empty stdout/stderr is the no-open-files result. The bundled `lsof` 4.91
observed during validation also returned 1 while printing valid `+D` matches,
so treat exit 0 or 1 with empty stderr as a completed scan. A timeout, stderr,
or an exit outside 0/1 leaves
unmatched paths unknown; do not convert an incomplete scan into “not in use.”
Combine this with the live owning-process check—an empty process-name search
alone does not prove a path is inactive.

The plan must name the exact supported command or exact Finder Trash target, rebuild/redownload impact, and a postcondition. After action, re-resolve the configured path, re-run `du -sk`, and read target-volume `df -k/-h`. Trash is a recovery step, not physical reclamation; do not claim freed bytes until the separately approved removal from Trash is reflected in `df`.

Source notes (accessed 2026-08-24):

- uv cache resolution and supported `uv cache dir` / `uv cache clean [package]`: <https://docs.astral.sh/uv/concepts/cache/> and <https://docs.astral.sh/uv/reference/storage/>
- Playwright browser binaries, macOS cache default, and `PLAYWRIGHT_BROWSERS_PATH`: <https://playwright.dev/docs/browsers#managing-browser-binaries>
- Hugging Face cache environment variables: <https://huggingface.co/docs/huggingface_hub/en/package_reference/environment_variables>
- JetBrains live-path authority, `idea.system.path`, and macOS cache layout: <https://www.jetbrains.com/help/idea/directories-used-by-the-ide-to-store-settings-caches-plugins-and-logs.html>

### Narrow npm `_npx` candidate

`_npx` stores temporary packages fetched for `npx` executions. It is narrower than npm's content-addressed `_cacache`; deleting it means future `npx` commands may download those packages again.

Resolve the current npm cache root first:

```bash
npm config get cache
```

Then measure the exact returned `<npm-cache-root>/_npx` path. If no `npx` process is using it and the user approves the redownload cost, move that exact directory to Trash using the main skill's Finder command. Permanent deletion through the legacy helper requires separate irreversible approval. Never replace this narrow target with the whole npm cache.

### Docker

**ABSOLUTE RULE**: NEVER use any `prune` command (`docker image prune`, `docker volume prune`, `docker system prune`, `docker container prune`). Always delete by specifying exact object IDs or names.

#### Images

**What it is**: Container images (base OS + application layers)

**Safety**: 🟡 **Requires per-image verification**

**Analysis**:
```bash
# List all images sorted by size
docker images --format "table {{.ID}}\t{{.Repository}}:{{.Tag}}\t{{.Size}}\t{{.CreatedSince}}" | sort -k3 -h -r

# Identify dangling images
docker images -f "dangling=true" --format "{{.ID}}\t{{.Size}}\t{{.CreatedSince}}"

# For EACH image, verify no container references it
docker ps -a --filter "ancestor=<IMAGE_ID>" --format "{{.Names}}\t{{.Status}}"
```

**Cleanup** (only after per-image verification):
```bash
# Remove specific images by ID
docker rmi a02c40cc28df 555434521374 f471137cd508
```

#### Containers

**What it is**: Running or stopped container instances

**Safety**: 🟡 **Stopped containers may be restarted -- verify with user**

**Analysis**:
```bash
docker ps -a --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Size}}"
```

**Cleanup** (only after user confirms each container/project):
```bash
# Remove specific containers by name
docker rm container-name-1 container-name-2
```

#### Volumes

**What it is**: Persistent data storage for containers

**Safety**: 🔴 **CAUTION - May contain databases, user uploads, and irreplaceable data**

**Analysis**:
```bash
# List all volumes
docker volume ls

# Check which container uses each volume
docker ps -a --filter "volume=<VOLUME_NAME>" --format "{{.Names}}\t{{.Status}}"

# Database/anonymous-volume content inspection is mandatory before deletion,
# but it creates a temporary container. Use the separately authorized,
# no-pull/no-network/read-only procedure in references/docker_analysis.md.
```

**Cleanup** (only after per-volume confirmation, database volumes require content inspection):
```bash
# Remove specific volumes by name
docker volume rm project-mysql-data project-redis-data
```

#### Build Cache

**What it is**: Intermediate build layers

**Safety**: 🟡 **Rebuildable, but category-wide deletion still needs an explicit decision**

Inspect the allocation without deleting it:
```bash
docker builder du
```

This skill does not use `docker builder prune` or `docker buildx prune`. They are category-wide prune commands and conflict with this skill's explicit prune prohibition. Report the build-cache total and rebuild cost, then state that build-cache deletion is not executable through this skill; do not leave a dangling promise to obtain an unspecified plan.

Build-cache deletion is outside this skill's execution scope. Do not advertise the build-cache number as reclaimable space this skill can automatically deliver.

### node_modules

**What it is**: Installed npm packages for Node.js projects

**Safety**: 🟡 **Rebuildable**

**Impact**: Restore with the project's package manager and retained lockfile. Verify registry/private-package availability and any patch inputs rather than assuming `npm install` reproduces every project.

**Finding large node_modules inside an exact approved project root**:
```bash
find "<approved-project-root>" -name "node_modules" -type d -prune -print 2>/dev/null | while read dir; do
  du -sh "$dir"
done | sort -hr
```

**Cleanup**: verify inactivity, retained source/lockfile and reinstall inputs. With an existing instruction covering safe permanent cleanup, remove the exact disposable directory without making a dependency backup or asking again. Otherwise use the main skill's approval/Trash path. Actual hand edits or unavailable dependencies require preservation; do not invent them as a reason to copy every dependency tree.

Classify mixed project directories by their actual contents. A private `tools/node`
prefix can be an installed global CLI toolchain, even inside an old test directory;
a process exiting does not retire that installation. Preserve source edits, model
data and installed tools, and select only the verified dependency or build roots.
The executing agent establishes those roles from installation metadata and live
consumers; the directory name and the deletion helper do not establish them.

**pnpm hard links make `du` a phantom.** pnpm links every installed file into the store (`nlink=2`), so deleting a project `node_modules` while the store stays releases ≈0 — the preserve-by-default store keeps the content alive (the SKILL.md mechanism table's hard-link row). Probe before promising any release: `find "<dir>" -type f -links +1 | head` — any hit means the directory is a link farm and the only real reclamation is the store itself. An empty probe does not clear the phantom either: on APFS, pnpm can import via clonefile — shared extents with nlink=1, invisible to `-links +1`. Keep expected release unknown until a df readback in either import mode. Reclaiming the store itself remains a separate USER-DECISION (it is not a row in the preserve-by-default table, so the Phase 2 cross-check does not apply; ask, don't propose) (2026-10-07: four project `node_modules` totaling 6.3 GiB sampled 200/200 hard-linked; all four left the action set with expected release ≈0).

### Retired packaged test Apps and build caches

Verify that an exact bundle/cache is a generated test artifact rather than an installed or currently selected application. Check current processes, open files and live launch/configuration references; retain source, build inputs and diagnostic records outside the deletion target. Confirm retirement independently of inactivity: an offline installer or required historical reproduction may still matter.

Under an existing safe-cleanup instruction, delete a verified disposable build cache or retired test bundle without first cloning or archiving it. An explicit instruction to discard the old binary does not require proving that the identical signed binary can be rebuilt. Embedded unique data, an active/reference-dependent runtime or a still-required offline artifact stays protected until resolved. Report physical release from `df`, not the bundle's nominal size.

### Python Virtual Environments

**What it is**: Isolated Python environments

**Location**: `venv/`, `.venv/`, `env/` in project directories

**Safety**: 🟡 **Rebuildable; confirm the environment can be recreated**

**Impact**: Need to recreate virtualenv and reinstall packages

**Finding venvs inside an exact approved project root**:
```bash
find "<approved-project-root>" -type d \( -name "venv" -o -name ".venv" \) 2>/dev/null
```

### Optional duplicate files

Duplicate detection reads file metadata and contents and can be expensive. Run it only when the user explicitly approves each search root. Never default to the whole home directory, Downloads, Documents, or the data volume.

If `fdupes` is already installed:

```bash
fdupes -r "<approved-path>" [<approved-path> ...]
```

This is discovery only. Do not use `fdupes -d`, `--delete`, or any automatic-selection option. Present each duplicate set with paths and sizes; the user decides whether the files are semantically interchangeable. If `fdupes` is missing, report that fact—do not install it inside a read-only phase.

### Git Repositories (.git directories)

**What it is**: Git version control data

**Safety**: 🟡 **Depends on use case**

**When it may be expendable**:
- The project is archived
- Every commit and branch is proven present in a reachable remote or verified bundle
- The user explicitly wants a plain source folder without local history

**When to KEEP**:
- Active development
- No remote backup exists
- You might need the history

Prefer archiving or removing the whole obsolete project through a separate, explicitly approved plan. Do not recommend deleting only `.git`: it silently converts a repository into an unversioned folder and destroys local-only history, reflogs, branches, and recovery data.

### Git LFS object caches (`.git/lfs/objects`)

The local LFS object cache is a re-downloadable copy while the remote endpoint is intact — REBUILDABLE, not history. Pruning sequence (measured 2026-10-23, 39.6 GiB released from a 62.1 GiB cache):

1. Prove endpoint completeness from the push side: `git lfs push --all origin` transferring 0 B means every ref-reachable object is already on the endpoint. Under a standalone transfer agent, `git lfs prune --verify-remote` does not merely lose its check — it **fabricates success** (observed on git-lfs 3.7.1 by independent review probe: reports `N verified with remote`, exit 0, for objects absent from the remote). Never treat its output as evidence in this configuration; the push-side proof (or per-object HEAD checks through the repo's own transfer helper for a named candidate set) is the only verification.
2. Objects absent from the endpoint AND unreferenced by any pushed ref are orphans of amended/abandoned history, not a backup hole — **remote-missing does not imply data loss; check referenced-ness before raising an alarm**. `git lfs prune`'s built-in retention (current checkout across all worktrees, recent commits, stash, unpushed branches) already covers what a cleanup must keep — but prune ignores the reflog: objects referenced only by abandoned commits are deleted even when the local copy is the only one, so accept that loss explicitly before pruning.
3. Report expected release as unknown until the `df` readback; measure the cache with `du -x -k -s .git/lfs` and the HEAD-referenced share by summing `git lfs ls-files -s`.

## Large Files

### Downloads Folder

**What it is**: Files downloaded from internet

**Safety**: 🟡 **User judgment required**

**Common cleanable items**:
- Old installers (.dmg, .pkg)
- Zip archives already extracted
- Temporary downloads
- Duplicate files

**Check before deleting**: Might contain important downloads

**Scanning and deleting are separate authorizations.** A metadata-level inventory and classification (names, sizes, ages — never content reads) may be standing-authorized by the user; deleting any batch still requires the user to name that exact batch. A classification table is the deliverable, not a deletion list.

### Disk Images (.dmg, .iso)

**What it is**: Mountable disk images, often installers

**Safety**: 🟡 **User decision; the image may still be needed for offline reinstall or recovery**

**Typical location**: ~/Downloads

**Cleanup**: After the user confirms the installer is no longer needed, move the exact file to Trash

### Archives (.zip, .tar.gz)

**What it is**: Compressed archives

**Safety**: 🟡 **Check if extracted**

**Before deleting**: Verify contents are extracted elsewhere

### Old iOS Backups

**Location**: `~/Library/Application Support/MobileSync/Backup/`

**What it is**: iTunes/Finder iPhone/iPad backups

**Safety**: 🟡 **Caution - backup data**

**Check**:
```bash
ls -lh ~/Library/Application\ Support/MobileSync/Backup/
```

**Cleanup**: Delete old backups via Finder preferences, not manually

### Old Time Machine Local Snapshots

**What it is**: Local Time Machine backups

**Safety**: 🟡 **System-managed; normally leave it to macOS**

**macOS automatically deletes** these when disk space is low

**Check**:
```bash
tmutil listlocalsnapshots /
```

**Manual cleanup** (rarely needed):
```bash
tmutil deletelocalsnapshots <snapshot_date>
```

## What to NEVER Delete

### User Data Directories

- `~/Documents`
- `~/Desktop`
- `~/Pictures`
- `~/Movies`
- `~/Music`

### Agent Session History (user's absolute ruling, 2026-09-19)

- `~/workspace/claude-dotfiles/projects/` — local Claude/Codex session
  transcripts and per-project session data. The user ruled this **absolutely
  off-limits** after it appeared once in a "large items" candidate list. It can
  be many tens of GB (one project directory held 15 GB) and it looks like
  reclaimable session cruft by every size heuristic — it is not. Never propose,
  never include in a candidate list, never "helpfully" clean it. If the user
  ever wants it trimmed, that is their instruction with their scope, not a
  cleanup proposal.
- `~/.codex/sessions/` — Codex session transcripts. The user extended the same
  absolute off-limits ruling to all agent chat history on 2026-10-23
  (standing): never propose deleting, archiving, or migrating it as a cleanup
  move.

### Application Chat Data (user's absolute ruling, 2026-10-23)

- `~/Library/Containers/com.tencent.xinWeChat` — WeChat's sandboxed container,
  including anything reachable through the app's own storage manager. Ruled
  absolutely off-limits (standing). It shows up large in every container
  inventory; it is never a candidate.

### System Files

- `/System`
- `/Library/Apple` (unless you know what you're doing)
- `/private/etc`

### Security & Credentials

- `~/.ssh` (SSH keys)
- `~/Library/Keychains` (passwords, certificates)
- Any files containing credentials

### Active Databases

- `*.db`, `*.sqlite` files for running applications
- Docker volumes in active use

Apply the main skill's [safety and authorization contract](../SKILL.md#safety-and-authorization-contract) together with the target-specific semantics in this reference.

## Recovery Options

### Trash vs. Permanent Deletion

**Use Trash when possible**:
```bash
# Move exact target to Trash (recoverable)
/usr/bin/osascript \
  -e 'on run argv' \
  -e 'tell application "Finder" to delete (POSIX file (item 1 of argv))' \
  -e 'end run' -- "/exact/approved/path"
```

**Legacy permanent deletion for an exact non-user-data target after separate irreversible confirmation**:
```bash
uv run scripts/safe_delete.py "/exact/approved/path"
```

### Time Machine

If you deleted something important:

1. Open Time Machine
2. Navigate to parent directory
3. Select date before deletion
4. Restore

### File Recovery Tools

If no Time Machine backup:
- Disk Drill (commercial)
- PhotoRec (free, for photos)
- TestDisk (free, for files)

**Note**: Success rate depends on how recently deleted and disk usage since deletion.
