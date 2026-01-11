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

**Safety**: 🟢 **Safe to delete**

**Impact**:
- Apps may be slower on first launch after deletion
- Websites may load slower on first visit (need to re-download assets)
- No data loss (caches are regenerated)

**Size**: Typically 10-100 GB depending on usage

**Cleanup command**:
```bash
rm -rf ~/Library/Caches/*
```

### /Library/Caches

**What it is**: System-level cache storage (shared across all users).

**Safety**: 🟢 **Safe to delete** (requires sudo)

**Impact**: Same as user caches, but system-wide

**Cleanup command**:
```bash
sudo rm -rf /Library/Caches/*
```

### Package Manager Caches

#### Homebrew Cache

**Location**: `$(brew --cache)` (typically `~/Library/Caches/Homebrew`)

**What it is**: Downloaded package installers and build artifacts

**Safety**: 🟢 **Safe to delete**

**Impact**: Will need to re-download packages on next install/upgrade

**Cleanup**:
```bash
brew cleanup -s          # Safe cleanup (removes old versions)
brew cleanup --prune=all # Aggressive cleanup (removes all cached downloads)
```

#### npm Cache

**Location**: `~/.npm` or configured cache directory

**Safety**: 🟢 **Safe to delete**

**Impact**: Packages will be re-downloaded when needed

**Cleanup**:
```bash
npm cache clean --force
```

#### pip Cache

**Location**: `~/Library/Caches/pip` (macOS)

**Safety**: 🟢 **Safe to delete**

**Impact**: Packages will be re-downloaded when needed

**Cleanup**:
```bash
pip cache purge
# or for pip3
pip3 cache purge
```

## Application Logs

### ~/Library/Logs

**What it is**: Application log files

**Safety**: 🟢 **Safe to delete**

**Impact**: Loss of diagnostic information (only matters if debugging)

**Typical size**: 1-20 GB

**Cleanup**:
```bash
rm -rf ~/Library/Logs/*
```

### /var/log (System Logs)

**What it is**: System and service log files

**Safety**: 🟢 **Safe to delete old logs** (requires sudo)

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

**When safe to delete**:
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

#### Images

**What it is**: Container images (base OS + application layers)

**Safety**: 🟢 **Safe to delete unused images**

**Check first**:
```bash
docker images
```

**Cleanup**:
```bash
docker image prune -a  # Remove all unused images
```

#### Containers

**What it is**: Running or stopped container instances

**Safety**: 🟢 **Safe to delete stopped containers**

**Check first**:
```bash
docker ps -a
```

**Cleanup**:
```bash
docker container prune  # Remove stopped containers
```

#### Volumes

**What it is**: Persistent data storage for containers

**Safety**: 🔴 **CAUTION - May contain important data**

**Check first**:
```bash
docker volume ls
docker volume inspect <volume_name>
```

**Cleanup** (only if certain):
```bash
docker volume prune  # Remove unused volumes
```

#### Build Cache

**What it is**: Intermediate build layers

**Safety**: 🟢 **Safe to delete**

**Cleanup**:
```bash
docker builder prune -a
```

#### All-in-one cleanup

⚠️ **WARNING**: This removes ALL unused Docker resources including volumes!

```bash
docker system prune -a --volumes
```

### node_modules

**What it is**: Installed npm packages for Node.js projects

**Safety**: 🟢 **Safe to delete** (can be regenerated)

**Impact**: Need to run `npm install` to restore

**Finding large node_modules**:
```bash
find ~ -name "node_modules" -type d -prune -print 2>/dev/null | while read dir; do
  du -sh "$dir"
done | sort -hr
```

**Cleanup**:
```bash
# For old projects
rm -rf /path/to/old-project/node_modules
```

### Python Virtual Environments

**What it is**: Isolated Python environments

**Location**: `venv/`, `.venv/`, `env/` in project directories

**Safety**: 🟢 **Safe to delete** (can be recreated)

**Impact**: Need to recreate virtualenv and reinstall packages

**Finding venvs**:
```bash
find ~ -type d -name "venv" -o -name ".venv" 2>/dev/null
```

### Git Repositories (.git directories)

**What it is**: Git version control data

**Safety**: 🟡 **Depends on use case**

**When SAFE to delete**:
- Project is archived and you have remote backup
- You only need final code, not history

**When to KEEP**:
- Active development
- No remote backup exists
- You might need the history

**Cleanup** (convert to plain folder, lose history):
```bash
rm -rf /path/to/old-project/.git
```

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

**Safety**: 🟢 **Safe to delete after installation**

**Typical location**: ~/Downloads

**Cleanup**: Delete .dmg files for already-installed apps

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

**Safety**: 🟢 **Safe - macOS manages automatically**

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

**Permanent deletion**:
```bash
# Cannot be recovered without Time Machine
rm -rf /path/to/file
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
