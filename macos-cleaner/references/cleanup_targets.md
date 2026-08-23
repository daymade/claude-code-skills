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

Inventory exact application-owned subdirectories first and prefer the application's supported cache-management command when one exists. If none exists, verify the owning application is stopped or the directory is otherwise inactive. After the user approves the named directory and rebuild/redownload impact, use the guarded helper from the skill directory:
```bash
uv run scripts/safe_delete.py "<exact-cache-directory>"
```

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

After confirming no active investigation needs the logs, delete exact named files/directories through the guarded helper:
```bash
uv run scripts/safe_delete.py "<exact-log-path>"
```

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

# CRITICAL: For database volumes (mysql, postgres, redis in name), inspect contents
docker run --rm -v <VOLUME_NAME>:/data alpine ls -la /data
docker run --rm -v <VOLUME_NAME>:/data alpine du -sh /data/*
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

This skill does not use `docker builder prune` or `docker buildx prune`. They are category-wide prune commands and cannot express which cache records the user approved. Report the build-cache total and rebuild cost; if it is the chosen target, obtain a separately approved, tool-specific plan instead of treating it as an exception to the prune prohibition.

Build-cache deletion is outside this skill's execution scope. Do not advertise the build-cache number as reclaimable space this skill can automatically deliver.

### node_modules

**What it is**: Installed npm packages for Node.js projects

**Safety**: 🟡 **Rebuildable**

**Impact**: Need to run `npm install` to restore

**Finding large node_modules**:
```bash
find ~ -name "node_modules" -type d -prune -print 2>/dev/null | while read dir; do
  du -sh "$dir"
done | sort -hr
```

**Cleanup**:
```bash
uv run scripts/safe_delete.py "/path/to/approved-project/node_modules"
```

### Python Virtual Environments

**What it is**: Isolated Python environments

**Location**: `venv/`, `.venv/`, `env/` in project directories

**Safety**: 🟡 **Rebuildable; confirm the environment can be recreated**

**Impact**: Need to recreate virtualenv and reinstall packages

**Finding venvs**:
```bash
find ~ -type d -name "venv" -o -name ".venv" 2>/dev/null
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
# Move to trash (recoverable)
osascript -e 'tell app "Finder" to move POSIX file "/path/to/file" to trash'
```

**Guarded permanent deletion after explicit confirmation**:
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
