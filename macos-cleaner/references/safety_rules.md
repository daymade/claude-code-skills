# Safety Rules for macOS Cleanup

Critical safety guidelines to prevent data loss and system damage.

## Golden Rules

### Rule 1: Never Delete Without Confirmation

**ALWAYS** ask user before deleting ANY file or directory.

**Bad**:
```python
shutil.rmtree(cache_dir)  # Immediately deletes
```

**Good**:
```python
if confirm_delete(cache_dir, size, description):
    shutil.rmtree(cache_dir)
else:
    print("Skipped")
```

### Rule 2: Explain Before Deleting

Users should understand:
- **What** is being deleted
- **Why** it's safe (or not safe)
- **Impact** of deletion
- **Recoverability** (can it be restored?)

### Rule 3: When in Doubt, Don't Delete

If uncertain about safety: **DON'T DELETE**.

Ask user to verify instead.

### Rule 4: Suggest Backups for Large Deletions

Before deleting >10 GB, recommend Time Machine backup.

### Rule 5: Docker Prune Prohibition

**NEVER use any Docker prune command.** This includes:
- `docker image prune` / `docker image prune -a`
- `docker container prune`
- `docker volume prune` / `docker volume prune -f`
- `docker system prune` / `docker system prune -a --volumes`

**Why**: Prune commands operate on categories, not specific objects. They can silently destroy database volumes, user uploads, and container state that the user intended to keep. A user who loses their MySQL data because of a prune command will never trust this tool again.

**Correct approach**: Always specify exact object IDs or names:
```bash
# Images: delete by specific ID
docker rmi a02c40cc28df 555434521374

# Containers: delete by specific name
docker rm container-name-1 container-name-2

# Volumes: delete by specific name
docker volume rm project-mysql-data project-redis-data
```

### Rule 6: Double-Check Verification Protocol

Before deleting ANY Docker object, perform independent cross-verification. This applies to images, volumes, and containers.

**Key requirements**:
- For images: verify no container (running or stopped) references the image
- For volumes: verify no container mounts the volume
- For database volumes (name contains mysql, postgres, redis, mongo, mariadb): MANDATORY content inspection with a temporary container
- Even if Docker reports a volume as "dangling", the data inside may be valuable

See **SKILL.md Step 4** for the complete verification commands and database volume inspection workflow.

### Rule 7: Use Trash When Possible

Prefer moving to Trash over permanent deletion:

```bash
# Recoverable
osascript -e 'tell app "Finder" to move POSIX file "/path/to/file" to trash'

# Permanent (use only when confirmed safe)
rm -rf /path/to/file
```

## Never Delete These

### System Directories

| Path | Why | Impact if Deleted |
|------|-----|-------------------|
| `/System` | macOS core | System unbootable |
| `/Library/Apple` | Apple frameworks | Apps won't launch |
| `/private/etc` | System config | System unstable |
| `/private/var/db` | System databases | System unstable |
| `/usr` | Unix utilities | Commands won't work |
| `/bin`, `/sbin` | System binaries | System unusable |

### User Data

| Path | Why | Impact if Deleted |
|------|-----|-------------------|
| `~/Documents` | User documents | Data loss |
| `~/Desktop` | User files | Data loss |
| `~/Pictures` | Photos | Data loss |
| `~/Movies` | Videos | Data loss |
| `~/Music` | Music library | Data loss |
| `~/Downloads` | May contain important files | Potential data loss |

### Security & Credentials

| Path | Why | Impact if Deleted |
|------|-----|-------------------|
| `~/.ssh` | SSH keys | Cannot access servers |
| `~/Library/Keychains` | Passwords, certificates | Cannot access accounts/services |
| Any file with "credential", "password", "key" in name | Security data | Cannot authenticate |

### Active Databases

| Pattern | Why | Impact if Deleted |
|---------|-----|-------------------|
| `*.db`, `*.sqlite`, `*.sqlite3` | Application databases | App data loss |
| Any database file for running app | Active data | Data corruption |

### Running Applications

| Path | Why | Impact if Deleted |
|------|-----|-------------------|
| `/Applications` | Installed apps | Apps won't launch |
| `~/Applications` | User-installed apps | Apps won't launch |
| Files in use (check with `lsof`) | Currently open | App crash, data corruption |

## Require Extra Confirmation

### Large Deletions

**Threshold**: >10 GB

**Action**: Warn user and suggest Time Machine backup

**Example**:
```
⚠️ This operation will delete 45 GB of data.

💡 Recommendation:
   Create a Time Machine backup first.

   Check last backup:
     tmutil latestbackup

   Create backup now:
     tmutil startbackup

Proceed without backup? [y/N]:
```

### System-Wide Caches

**Paths**: `/Library/Caches`, `/var/log`

**Action**: Require manual sudo command (don't execute directly)

**Example**:
```
⚠️ This operation requires administrator privileges.

Please run this command manually:
  sudo rm -rf /Library/Caches/*

⚠️ You will be asked for your password.
```

**Reason**:
- Requires elevated privileges
- User should be aware of system-wide impact
- Audit trail (user types password)

### Docker Objects (Images, Containers, Volumes)

**Action**: List every object individually. Use precision deletion only (see Rule 5 and Rule 6).

**NEVER use prune commands.** Always specify exact IDs/names.

**Example for volumes**:
```
Docker volumes found:
  postgres_data    (1.2 GB)  - Contains PostgreSQL database
  redis_data       (500 MB)  - Contains Redis cache data
  app_uploads      (3 GB)    - Contains user-uploaded files

Database volumes inspected with temporary container:
  postgres_data: 8 databases, 45 tables, last modified 2 days ago
  redis_data: 12 MB dump.rdb

Confirm EACH volume individually:
  Delete postgres_data? [y/N]:
  Delete redis_data? [y/N]:
  Delete app_uploads? [y/N]:

Deletion commands (after confirmation):
  docker volume rm postgres_data redis_data
```

### Application Preferences

**Path**: `~/Library/Preferences/*.plist`

**Action**: Warn that app will reset to defaults

**Example**:
```
⚠️ Deleting preferences will reset the app to defaults.

Impact:
- All settings will be lost
- Custom configurations will be reset
- May need to re-enter license keys

Only delete if:
- App is misbehaving (troubleshooting)
- App is confirmed uninstalled

Proceed? [y/N]:
```

## Safety Checks Before Deletion

### Check 1: Path Exists

```python
if not os.path.exists(path):
    print(f"❌ Path does not exist: {path}")
    return False
```

### Check 2: Not a System Path

```python
system_paths = [
    '/System', '/Library/Apple', '/private/etc',
    '/usr', '/bin', '/sbin', '/private/var/db'
]

for sys_path in system_paths:
    if path.startswith(sys_path):
        print(f"❌ Cannot delete system path: {path}")
        return False
```

### Check 3: Not User Data

```python
user_data_paths = [
    '~/Documents', '~/Desktop', '~/Pictures',
    '~/Movies', '~/Music', '~/.ssh'
]

expanded_path = os.path.expanduser(path)
for data_path in user_data_paths:
    if expanded_path.startswith(os.path.expanduser(data_path)):
        print(f"⚠️ This is a user data directory: {path}")
        print("   Are you ABSOLUTELY sure? [type 'DELETE' to confirm]:")
        response = input().strip()
        if response != 'DELETE':
            return False
```

### Check 4: Not in Use

```python
def is_in_use(path):
    """Check if file/directory is in use."""
    try:
        result = subprocess.run(
            ['lsof', path],
            capture_output=True,
            text=True
        )
        # If lsof finds processes using the file, returncode is 0
        if result.returncode == 0:
            return True
        return False
    except:
        return False  # Assume not in use if check fails

if is_in_use(path):
    print(f"⚠️ Warning: {path} is currently in use")
    print("   Close the application first, then try again.")
    return False
```

### Check 5: Permissions

```python
def can_delete(path):
    """Check if we have permission to delete."""
    try:
        # Check parent directory write permission
        parent = os.path.dirname(path)
        return os.access(parent, os.W_OK)
    except:
        return False

if not can_delete(path):
    print(f"❌ No permission to delete: {path}")
    print("   You may need sudo, but be careful!")
    return False
```

## Safe Deletion Workflow

```python
def safe_delete(path, size, description):
    """
    Safe deletion workflow with all checks.

    Args:
        path: Path to delete
        size: Size in bytes
        description: Human-readable description

    Returns:
        (success, message)
    """
    # Safety checks
    if not os.path.exists(path):
        return (False, "Path does not exist")

    if is_system_path(path):
        return (False, "Cannot delete system path")

    if is_user_data(path):
        if not extra_confirm(path):
            return (False, "User cancelled")

    if is_in_use(path):
        return (False, "Path is in use")

    if not can_delete(path):
        return (False, "No permission")

    # Backup warning for large deletions
    if size > 10 * 1024 * 1024 * 1024:  # 10 GB
        if not confirm_large_deletion(size):
            return (False, "User cancelled")

    # Final confirmation
    if not confirm_delete(path, size, description):
        return (False, "User cancelled")

    # Execute deletion
    try:
        if os.path.isfile(path):
            os.unlink(path)
        else:
            shutil.rmtree(path)
        return (True, f"Deleted successfully ({format_size(size)} freed)")
    except Exception as e:
        return (False, f"Deletion failed: {str(e)}")
```

## Error Handling

### Permission Denied

```python
except PermissionError:
    print(f"❌ Permission denied: {path}")
    print("   Try running with sudo (use caution!)")
```

### Operation Not Permitted (SIP)

```python
# macOS System Integrity Protection blocks some deletions
except OSError as e:
    if e.errno == 1:  # Operation not permitted
        print(f"❌ System Integrity Protection prevents deletion: {path}")
        print("   This is a protected system file.")
        print("   Do NOT attempt to bypass SIP unless you know what you're doing.")
```

### Path Too Long

```python
except OSError as e:
    if e.errno == 63:  # File name too long
        print(f"⚠️ Path too long, trying alternative method...")
        # Try using find + rm
```

## Recovery Options

### If User Accidentally Confirmed

**Immediate action**: Check Trash first

```bash
# Files may be in Trash
ls -lh ~/.Trash
```

**Next**: Time Machine

```bash
# Open Time Machine to date before deletion
tmutil browse
```

**Last resort**: File recovery tools

- Disk Drill (commercial)
- PhotoRec (free)
- TestDisk (free)

**Note**: Success rate depends on:
- How recently deleted
- How much disk activity since deletion
- Whether SSD (TRIM) or HDD

### Preventing Accidents

1. **Use Trash instead of rm** when possible
2. **Require Time Machine backup** for >10 GB deletions
3. **Test on small items first** before batch operations
4. **Show dry-run results** before actual deletion

## Red Flags to Watch For

### User Requests

If user asks to:
- "Delete everything in ~/Library"
- "Clear all caches including system"
- "Delete all .log files on the entire system"
- "Remove all databases"

**Response**:
```
⚠️ This request is too broad and risky.

Let me help you with a safer approach:
1. Run analysis to identify specific targets
2. Review each category
3. Delete selectively with confirmation

This prevents accidental data loss.
```

### Script Behavior

If script is about to:
- Delete >100 GB at once
- Delete entire directory trees without listing contents
- Run `rm -rf /` or similar dangerous commands
- Delete from system paths

**Action**: STOP and ask for confirmation

## Testing Guidelines

### Before Packaging

Test safety checks:

1. ✅ Attempt to delete system path → Should reject
2. ✅ Attempt to delete user data → Should require extra confirmation
3. ✅ Attempt to delete in-use file → Should warn
4. ✅ Attempt to delete without permission → Should fail gracefully
5. ✅ Large deletion → Should suggest backup

### In Production

Always:
- Start with smallest items
- Confirm results after each deletion
- Monitor disk space before/after
- Ask user to verify important apps still work

## Summary

### Conservative Approach

When implementing cleanup:

1. **Assume danger** until proven safe
2. **Explain everything** to user
3. **Confirm each step**
4. **Suggest backups** for large operations
5. **Use Trash** when possible
6. **Test thoroughly** before packaging

### Remember

> "It's better to leave 1 GB of unnecessary files than to delete 1 MB of important data."

User trust is fragile. One bad deletion loses it forever.

### Final Checklist

Before any deletion:

- [ ] Path is verified to exist
- [ ] Path is not a system path
- [ ] Path is not user data (or extra confirmed)
- [ ] Path is not in use
- [ ] User has been informed of impact
- [ ] User has explicitly confirmed
- [ ] Backup suggested for large deletions
- [ ] Error handling in place
- [ ] Recovery options documented

Only then: proceed with deletion.
