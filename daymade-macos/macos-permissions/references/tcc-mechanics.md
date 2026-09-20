# TCC Mechanics

The general-purpose reference behind `../SKILL.md`. Load when you need the full service catalog,
the database schema, grant-value semantics, `tccutil`, or the SIP/Full-Disk-Access bootstrap.
This is mechanism; `uv-fda-trap.md` is the highest-frequency applied case.

## What TCC is

TCC is macOS's per-app, per-resource privacy layer. When a process touches contacts, the screen,
the mic, keystrokes to another app, or protected files, the request goes through TCC, which either
(1) finds an existing grant and silently allows/denies, or (2) has no grant and shows a system
prompt, recording the answer. A recorded grant persists across reboots until revoked in System
Settings or reset with `tccutil`.

The **silent denial** is the diagnostic trap: an app that used to work stops, the user never saw a
prompt, and the API just returns "not permitted". The app says "feature unavailable" with no clue
that TCC is why.

## Database locations

```
~/Library/Application Support/com.apple.TCC/TCC.db    per-user grants
/Library/Application Support/com.apple.TCC/TCC.db     system-wide grants (needs sudo)
```

Both are SQLite. Both are protected — the reading process itself needs Full Disk Access (see SIP
below). To grant FDA to your terminal: System Settings → Privacy & Security → Full Disk Access →
`+` → add `/Applications/Utilities/Terminal.app` (or Ghostty/iTerm) → restart the terminal.

## Service catalog

Every grant is a `(service, client)` pair. Service strings start with `kTCCService`. Full catalog:

| Service string | Gates | System Settings pane |
|---|---|---|
| `kTCCServiceScreenCapture` | Screen recording, `screencapture` | Screen Recording |
| `kTCCServiceMicrophone` | Audio input | Microphone |
| `kTCCServiceCamera` | Video input | Camera |
| `kTCCServiceAccessibility` | Synthetic input, control other apps | Accessibility |
| `kTCCServicePostEvent` | Synthetic input events | (part of Accessibility) |
| `kTCCServiceListenEvent` | Listen to global input events | Input Monitoring |
| `kTCCServiceAppleEvents` | Control another app via AppleScript | Automation |
| `kTCCServiceSystemPolicyAllFiles` | Read all files (backup, Time Machine) | Full Disk Access |
| `kTCCServiceDeveloperTool` | Run unsigned / not-yet-notarized binaries | Developer Tools |
| `kTCCServiceSystemPolicyDesktopFolder` | Desktop | Files & Folders → Desktop |
| `kTCCServiceSystemPolicyDocumentsFolder` | Documents | Files & Folders → Documents |
| `kTCCServiceSystemPolicyDownloadsFolder` | Downloads | Files & Folders → Downloads |
| `kTCCServiceSystemPolicyRemovableVolumes` | External volumes | Files & Folders → Removable Volumes |
| `kTCCServiceSystemPolicyNetworkVolumes` | Network mounts | Files & Folders → Network Volumes |
| `kTCCServiceFileProviderDomain` | File-provider extensions | (none — system) |
| `kTCCServiceUbiquity` | iCloud Drive sync | (managed by iCloud) |
| `kTCCServicePhotos` / `ContactsFull` / `ContactsLimited` | Photos / all / limited contacts | respective panes |
| `kTCCServiceCalendar` / `Reminders` | Calendar / Reminders | respective panes |
| `kTCCServiceMediaLibrary` | Apple Music library | Media & Apple Music |
| `kTCCServiceSpeechRecognition` | On-device speech recognition | Speech Recognition |
| `kTCCServiceMotion` | Motion / fitness data | Motion & Fitness |
| `kTCCServiceLocation` | Geolocation | Location Services (separate UI) |

`kTCCServiceDeveloperTool` matters for the unsigned-binary family: an unsigned executable that
macOS has never run before can be unblocked by a one-time Developer Tools grant (System Settings →
Privacy & Security → Developer Tools), which is sometimes a cleaner fix than Full Disk Access.

## Schema (stable core of the `access` table)

```sql
service      TEXT    -- kTCCService* string
client       TEXT    -- bundle ID, or absolute path for unsigned binaries
client_type  INTEGER -- 0 = bundle ID, 1 = absolute path
auth_value   INTEGER -- 0=deny, 1=unknown, 2=allow, 3=limited
auth_reason  INTEGER -- why it was set (see below)
csreq        BLOB    -- code-signature requirement
last_modified INTEGER -- unix epoch
-- newer macOS adds columns; the above is the stable core
```

`client_type` is the whole story of the attribution trap: `1` (path) means unsigned/bundless, so
the grant keys on a path that changes with versions; `0` (bundle ID) means it survives.

`auth_reason` values:
- `0` = not set
- `1` = error (something went wrong, default-deny)
- `2` = user denied at prompt
- `3` = user consent (granted at a prompt)
- `4` = system set
- `5` = **service policy** — the deny was *structural*, not a user choice. This is the launchd /
  no-GUI-session / unsigned-binary case: granting does not fix it, only changing who/what requests
  does (see `uv-fda-trap.md`).
- `6` = MDM policy — forced by a configuration profile, not user-revocable without removing it.

## auth_value semantics

| Value | Meaning |
|---|---|
| `0` | **Denied.** Requests fail silently with a permission error. |
| `1` | Unknown / not yet asked. Next request triggers a prompt. |
| `2` | **Allowed.** Requests succeed. |
| `3` | Limited (partial Photos/album access and similar). |

## Reading TCC.db

```bash
# Everything this user has allowed
sqlite3 "$HOME/Library/Application Support/com.apple.TCC/TCC.db" \
  "SELECT service, client, datetime(last_modified,'unixepoch') FROM access WHERE auth_value = 2"

# The diagnostic gold mine — everything DENIED
sqlite3 "$HOME/Library/Application Support/com.apple.TCC/TCC.db" \
  "SELECT service, client, datetime(last_modified,'unixepoch') FROM access WHERE auth_value = 0"

# A specific app's grants
sqlite3 "$HOME/Library/Application Support/com.apple.TCC/TCC.db" \
  "SELECT service, auth_value FROM access WHERE client = 'com.example.app'"

# Is a specific binary granted a specific service? (the pre-fix check)
sqlite3 "$HOME/Library/Application Support/com.apple.TCC/TCC.db" \
  "SELECT auth_value FROM access WHERE service='kTCCServiceSystemPolicyAllFiles' AND client='/path/to/bin';"
```

The system DB (system-wide grants) needs `sudo`; both need the reader to hold FDA.

## Resetting grants — `tccutil`

`tccutil` sets a `(service, client)` pair back to Unknown (`1`), so the next request prompts again.
This is the correct fix for "Slack lost Screen Recording after an update":

```bash
tccutil reset ScreenCapture com.tinyspeck.slackmacgap   # by service + bundle ID
tccutil reset All com.tinyspeck.slackmacgap             # all services for one app (rare)
tccutil reset ScreenCapture                             # nuclear: all apps for one service
```

`tccutil` uses a service-name shorthand that strips the `kTCCService` prefix:

| Full service string | tccutil shorthand |
|---|---|
| `kTCCServiceScreenCapture` | `ScreenCapture` |
| `kTCCServiceMicrophone` | `Microphone` |
| `kTCCServiceCamera` | `Camera` |
| `kTCCServiceAccessibility` | `Accessibility` |
| `kTCCServiceAppleEvents` | `AppleEvents` |
| `kTCCServiceSystemPolicyAllFiles` | `SystemPolicyAllFiles` |

After `reset`, quit and relaunch the app — it must re-request to re-prompt.

## SIP and the FDA bootstrap

The system TCC.db is **read-only under SIP**: `sqlite3 ... "insert ..."` fails with
`attempt to write a readonly database`. You **cannot grant or edit a permission from the command
line** — authorization goes through the GUI (System Settings) only. `tccutil reset` is the only
sanctioned way to clear a grant from the shell. TCC.db is for *reading* state.

Check SIP status: `csrutil status` (expect "enabled"). **Do not disable SIP** on a production Mac
just to edit TCC.db.

There is a bootstrap problem: reading TCC.db (to diagnose a permission) itself needs Full Disk
Access for the reading process. Grant FDA to your terminal first, then it can read both DBs.

## Common failure modes

- **"App can't record my screen" after a macOS update**: the grant drifted to Unknown/Denied.
  Fix: toggle the app OFF then ON in Screen Recording, or `tccutil reset ScreenCapture <bundle-id>`
  then relaunch.
- **Automation grant won't stick**: `kTCCServiceAppleEvents` needs a grant on **both** the
  controller AND the target app. Granting only the controller is the classic miss. Separately, a
  Hardened-Runtime binary missing the `com.apple.security.automation.apple-events` entitlement
  blocks Apple Events from its whole child tree — a code-signing issue, not a TCC grant.
- **Terminal can't read TCC.db**: the terminal lacks FDA — see the bootstrap above.
- **A prompt that reappears every run / every update**: the grant is keyed to a path that changes.
  See `uv-fda-trap.md` for the launchd + unsigned-binary case (most common on this machine).
- **An uninstalled app still appears in Privacy & Security**: the TCC entry persists after removal.
  Click `-` in the System Settings list, or `tccutil reset` on its bundle ID.
- **`tccutil reset` doesn't reprompt**: reset sets Unknown but the app must re-request; quit and
  relaunch it.
- **MDM-managed grants**: `auth_reason = 6` means forced by a configuration profile, not
  user-revocable without removing the profile.
