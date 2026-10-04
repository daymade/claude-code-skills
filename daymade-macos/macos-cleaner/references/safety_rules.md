# Safety Rules for macOS Cleanup

Critical safety guidelines to prevent data loss and system damage.

This reference defines the agent's required preflight, not a claim that every check is implemented by `scripts/safe_delete.py`. The bundled helper performs an exact-path existence check, a limited hard denylist, an interactive prompt, and permanent deletion. It does **not** move items to Trash, hard-block all user-data roots, run `lsof`, check a copy budget, or independently measure physical space after deletion. Keep user data and application state outside that helper; choose Trash or authorized permanent deletion under the main skill's contract.

## Golden Rules

### Rule 1: Delete Only Within Verified Authorization

Resolve the main skill's authorization contract first. Ask when the exact target or consequence is outside existing approval; do not ask again for a verified disposable target already covered by an explicit safe-cleanup instruction. Keep exact-phrase requirements and user exclusions intact.

**Bad**:
```python
shutil.rmtree(cache_dir)  # Immediately deletes
```

**Good**:
```python
if authorization_covers(cache_dir, size, description):
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

### Rule 4: High-Risk Paths Are Hard Blocks

`safe_delete.py` must refuse dangerous system and credential paths before confirmation and inside the delete function. A warning is not enough for:
- `/`, `/System`, `/usr`, `/bin`, `/etc`
- `~/.ssh`, `~/.aws`, `~/.gnupg`
- `~/Library/Keychains`

These paths and their descendants are blocked even when the user selects `all` in batch mode.

### Rule 5: Back Up Unique Value, Not a Size Threshold

Use the main skill's deletion-basis rules. Large disposable dependency trees and retired test builds do not need a second full copy merely because they exceed 10 GiB. Preserve unique state; a backup is not evidence that the source is safe to delete. Use a necessary or explicitly requested copy only after the capacity preflight below.

### Rule 6: Docker Prune Prohibition

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

### Rule 7: Double-Check Verification Protocol

Before deleting ANY Docker object, perform independent cross-verification. This applies to images, volumes, and containers.

**Key requirements**:
- For images: verify no container (running or stopped) references the image
- For volumes: verify no container mounts the volume
- For database volumes (name contains mysql, postgres, redis, mongo, mariadb): MANDATORY content inspection through the separately authorized no-pull/no-network/read-only temporary-container procedure
- Even if Docker reports a volume as "dangling", the data inside may be valuable

See `references/docker_analysis.md` for the complete verification commands and database-volume inspection workflow.

### Rule 8: Use Trash When Possible

Prefer moving to Trash over permanent deletion:

```bash
# Recoverable exact-target move
/usr/bin/osascript \
  -e 'on run argv' \
  -e 'tell application "Finder" to delete (POSIX file (item 1 of argv))' \
  -e 'end run' -- "/exact/approved/path"

# Legacy permanent deletion (exact approved non-user-data target only)
uv run scripts/safe_delete.py "/exact/approved/path"
```

## Never Delete These

### System Directories

| Path | Why | Impact if Deleted |
|------|-----|-------------------|
| `/System` | macOS core | System unbootable |
| `/Library/Apple` | Apple frameworks | Apps won't launch |
| `/etc`, `/private/etc` | System config | System unstable |
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
| `~/.aws` | Cloud credentials | Cannot access cloud resources |
| `~/.gnupg` | GPG keys | Cannot decrypt or sign data |
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

Classify contents and verify current authorization regardless of size. State permanent deletion and rebuild cost once. Ask only for unresolved unique value or a consequence not covered by the instruction; do not turn a size threshold into a backup or reconfirmation requirement.

### Necessary-copy capacity preflight

Run `scripts/check_gate_plan.py --table <gate-table.md> --plan <plan.md> --copy-budget <manifest.json>` on the destination host before starting a backup, extraction or verification copy. The JSON object contains:

| Field | Required value |
|---|---|
| `destination_parent` | Absolute existing directory on the destination filesystem |
| `max_total_bytes` | Positive integer allowance for all retained copies, partials, logs and metadata |
| `minimum_free_bytes` | Positive integer destination free-space reserve |
| `copies` | Nonempty array; each entry has an exact classification-table `target`, positive integer `source_bytes` and `copies_at_peak`, a nonblank `reason`, and `basis` of `unique-state` or `user-requested` |
| `copies[].user_direction` | Nonblank original instruction when `basis` is `user-requested`; the executor verifies its authority and scope |

Count each archive, extracted tree, verification tree and retained partial as a copy at its measured uncompressed size. Charge metadata/log overhead within the total allowance. The checker rejects absent/invalid fields, automatic copies of REBUILDABLE/PROPOSABLE targets, a peak estimate above the allowance, and insufficient live destination space for the allowance plus reserve. For necessary preservation, reclassify genuine unique state with evidence before copying; user-requested artifact preservation remains supported.

Without `--copy-budget`, a passing plan grants no copy preparation. This preflight does not run or monitor copies and cannot prove source classification or user authority. Re-run it before each stage with the complete still-retained set. On low space or an unknown measurement, stop the affected copy, keep the original, reassess its necessity, and continue independent authorized cleanup.

### System-Wide Caches

**Paths**: `/Library/Caches`, `/var/log`

**Action**: Identify the owning subsystem and use its supported cache-management command. Do not delete the whole category.

**Reason**:
- Requires elevated privileges
- The approved plan must state the system-wide impact and exact target
- Audit trail (user types password)

### Docker Objects (Images, Containers, Volumes)

**Action**: List every object individually. Use precision deletion only (see Rule 6 and Rule 7).

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

## Agent-side safety checks before deletion

The snippets below are decision requirements and pseudocode. Do not assume they are wired into the bundled helper.

### Check 1: Path Exists

```python
if not os.path.exists(path):
    print(f"❌ Path does not exist: {path}")
    return False
```

### Check 2: Not a Blocked Path

```python
blocked_paths = [
    '/System', '/Library/Apple', '/etc', '/private/etc',
    '/usr', '/bin', '/sbin', '/private/var/db',
    '~/.ssh', '~/.aws', '~/.gnupg', '~/Library/Keychains',
]

expanded_path = os.path.realpath(os.path.expanduser(path))
if expanded_path == '/':
    print("❌ Cannot delete root path")
    return False

for blocked_path in blocked_paths:
    expanded_blocked = os.path.realpath(os.path.expanduser(blocked_path))
    if expanded_path == expanded_blocked or expanded_path.startswith(expanded_blocked + os.sep):
        print(f"❌ Cannot delete blocked path: {path}")
        return False
```

### Check 3: Not User Data

```python
user_data_paths = [
    '~/Documents', '~/Desktop', '~/Pictures',
    '~/Movies', '~/Music'
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
def open_file_state(path):
    """Return 'active', 'inactive', or 'unknown'; never fail open."""
    canonical = os.path.realpath(path)
    try:
        result = subprocess.run(
            ['/usr/sbin/lsof', '-Fn', '+D', canonical],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 'unknown'

    names = [os.path.realpath(line[1:]) for line in result.stdout.splitlines()
             if line.startswith('n')]
    prefix = canonical + os.sep
    if any(name == canonical or name.startswith(prefix) for name in names):
        return 'active'
    if result.stderr.strip():
        return 'unknown'
    if result.returncode in (0, 1):
        return 'inactive'
    return 'unknown'

state = open_file_state(path)
if state != 'inactive':
    print(f"⚠️ Refusing deletion because inactivity is not proven: {path}")
    print(f"   Open-file state: {state}; refuse deletion until inactive is proven.")
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

## Required deletion decision model (pseudocode)

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

    # Existing authorization covers this verified target and consequence.
    if not authorization_covers(path, size, description):
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
2. **Preserve unique state**; run capacity preflight for any necessary copy
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
5. ✅ Disposable artifact → No automatic backup; necessary copy → Capacity preflight

### In Production

Always:
- Follow the main skill's physical-release/hotspot ranking
- Confirm results after each deletion
- Monitor disk space before/after
- Verify protected apps/services with available probes; ask only for a user-only check

## Summary

### Conservative Approach

When implementing cleanup:

1. **Assume danger** until proven safe
2. **Explain everything** to user
3. **Resolve authorization once per scope**, then verify each action
4. **Choose recovery from the contents**, not their size
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
- [ ] Existing explicit authorization covers this exact target and consequence
- [ ] Unique state preserved; any necessary copy passed destination capacity preflight
- [ ] Error handling in place
- [ ] Recovery options documented

Only then: proceed with deletion.
