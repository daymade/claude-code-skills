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

These were explicit decision points in the original skill and remain reachable for any named-cache request. A cache can be rebuildable and still be valuable. Measure the exact live path and ask whether its rebuild/redownload cost is acceptable before proposing removal.

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
| Xcode DerivedData | Xcode **Settings → Locations → Derived Data** | `~/Library/Developer/Xcode/DerivedData` | Quit Xcode; prefer removing an exact inactive project child. Whole-root Trash requires explicit rebuild-cost approval. |
| npm `_cacache` / `_npx` | `npm config get cache`, then append the exact child name | None; do not guess around npm's returned root | `_npx` may go to Trash after confirming no `npx` process. Keep `_cacache` by default; whole-cache removal requires explicit redownload approval. |
| uv cache | `uv cache dir` (honors `--cache-dir`, `UV_CACHE_DIR`, and uv config) | `$XDG_CACHE_HOME/uv` or `~/.cache/uv` only as a candidate | Prefer `uv cache clean <exact-package>` for a named obsolete package, or `uv cache clean` only when the whole cache is approved. Do not edit uv's internal cache by hand. |
| Playwright browsers | The project's `PLAYWRIGHT_BROWSERS_PATH` / runner configuration | `~/Library/Caches/ms-playwright` only as a candidate | Stop Playwright/browser processes. Prefer project-supported browser removal; otherwise move the verified whole inactive cache to Trash, not internal browser files guessed by name. |
| iOS DeviceSupport | Xcode's active platform/device support view plus the exact on-disk directory | `~/Library/Developer/Xcode/iOS DeviceSupport` | Quit Xcode; move only an exact OS-version child no longer needed for connected-device debugging. |
| Hugging Face cache | Active service/project values for `HF_HOME`, `HF_HUB_CACHE`, or `XDG_CACHE_HOME` | `~/.cache/huggingface` only as a candidate | Prefer the installed Hugging Face cache-management command after verifying its current help. Without a verified supported control, keep internal cache subsets; whole inactive cache Trash is a separate user decision. |
| ModelScope cache | Active service/project cache configuration | `~/.cache/modelscope` only as a candidate | Prefer the installed ModelScope cache-management command after verifying its current help. Without one, keep internal subsets; whole inactive cache Trash needs explicit redownload approval. |
| JetBrains caches | **Help → Diagnostic Tools → Special Files and Folders** or `idea.system.path` | `~/Library/Caches/JetBrains/<product><version>` | Quit the IDE; prefer its cache invalidation UI. An exact cache for an uninstalled/retired product version may go to Trash. Never target config/plugins/local history by assuming every JetBrains directory is cache. |
| Stopped Docker container | `docker inspect <exact-name-or-id>` plus `docker ps -a` | None | Use `references/docker_analysis.md`; stopped status alone never authorizes removal. |

For the resolved `<exact-cache-path>`, use allocated blocks and an in-use check:

```bash
/usr/bin/du -sk "<exact-cache-path>"
/usr/sbin/lsof +D "<exact-cache-path>"
```

`lsof` exit 0 means the target is in use. Exit 1 with empty stdout/stderr is the no-open-files result; timeout, permission errors, or any other output leave the check incomplete. Combine this with the live owning-process check—an empty `lsof` result alone does not prove an application is inactive.

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

**Impact**: Need to run `npm install` to restore

**Finding large node_modules inside an exact approved project root**:
```bash
find "<approved-project-root>" -name "node_modules" -type d -prune -print 2>/dev/null | while read dir; do
  du -sh "$dir"
done | sort -hr
```

**Cleanup**: after confirming the project is reproducible and the exact directory is approved, use the main skill's Finder Trash path. Permanent deletion needs separate irreversible approval.

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

## Safety Checklist

Before deleting ANY directory:

1. ✅ Do you know what it is?
2. ✅ Is the application truly uninstalled?
3. ✅ Have you checked if it's in use? (lsof, Activity Monitor)
4. ✅ Do you have a Time Machine backup?
5. ✅ Have you confirmed with the user?

When in doubt, **DON'T DELETE**.

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
