---
name: capture-screen
description: Programmatic screenshot capture on macOS. Find window IDs with Swift CGWindowListCopyWindowInfo, control application windows via AppleScript (zoom, scroll, select), and capture with screencapture. Use when automating screenshots, capturing application windows for documentation, or building multi-shot visual workflows.
---

# Capture Screen

Programmatic screenshot capture on macOS: find windows, control views, capture images.

## Quick Start

```bash
# Find Excel window ID
swift scripts/get_window_id.swift Excel

# Capture that window (replace 12345 with actual WID)
screencapture -x -l 12345 output.png
```

## Overview

Three-step workflow:

```
1. Find Window  →  Swift CGWindowListCopyWindowInfo  →  get numeric Window ID
2. Control View  →  AppleScript (osascript)           →  zoom, scroll, select
3. Capture       →  screencapture -l <WID>            →  PNG/JPEG output
```

## Step 1: Get Window ID (Swift)

Use Swift with CoreGraphics to enumerate windows. This is the **only reliable method** on macOS.

### Quick inline execution

```bash
swift -e '
import CoreGraphics
let keyword = "Excel"
let list = CGWindowListCopyWindowInfo(.optionOnScreenOnly, kCGNullWindowID) as? [[String: Any]] ?? []
for w in list {
    let owner = w[kCGWindowOwnerName as String] as? String ?? ""
    let name = w[kCGWindowName as String] as? String ?? ""
    let wid = w[kCGWindowNumber as String] as? Int ?? 0
    if owner.localizedCaseInsensitiveContains(keyword) || name.localizedCaseInsensitiveContains(keyword) {
        print("WID=\(wid) | App=\(owner) | Title=\(name)")
    }
}
'
```

### Using the bundled script

```bash
swift scripts/get_window_id.swift Excel
swift scripts/get_window_id.swift Chrome
swift scripts/get_window_id.swift          # List all windows
```

Output format: `WID=12345 | App=Microsoft Excel | Title=workbook.xlsx`

Parse the WID number for use with `screencapture -l`.

## Step 2: Control Window (AppleScript)

Verified commands for controlling application windows before capture.

### Microsoft Excel (full AppleScript support)

```bash
# Activate (bring to front)
osascript -e 'tell application "Microsoft Excel" to activate'

# Set zoom level (percentage)
osascript -e 'tell application "Microsoft Excel"
    set zoom of active window to 120
end tell'

# Scroll to specific row
osascript -e 'tell application "Microsoft Excel"
    set scroll row of active window to 45
end tell'

# Scroll to specific column
osascript -e 'tell application "Microsoft Excel"
    set scroll column of active window to 3
end tell'

# Select a cell range
osascript -e 'tell application "Microsoft Excel"
    select range "A1" of active sheet
end tell'

# Select a specific sheet
osascript -e 'tell application "Microsoft Excel"
    activate object sheet "DCF" of active workbook
end tell'

# Open a file
osascript -e 'tell application "Microsoft Excel"
    open POSIX file "/path/to/file.xlsx"
end tell'
```

### Any application (basic control)

```bash
# Activate any app
osascript -e 'tell application "Google Chrome" to activate'

# Bring specific window to front (by index)
osascript -e 'tell application "System Events"
    tell process "Google Chrome"
        perform action "AXRaise" of window 1
    end tell
end tell'
```

### Timing and Timeout

Always add `sleep 1` after AppleScript commands before capturing, to allow UI rendering to complete.

**IMPORTANT**: `osascript` hangs indefinitely if the target application is not running or not responding. Always wrap with `timeout`:

```bash
timeout 5 osascript -e 'tell application "Microsoft Excel" to activate'
```

## Step 3: Capture (screencapture)

```bash
# Capture specific window by ID
screencapture -l <WID> output.png

# Silent capture (no camera shutter sound)
screencapture -x -l <WID> output.png

# Capture as JPEG
screencapture -l <WID> -t jpg output.jpg

# Capture with delay (seconds)
screencapture -l <WID> -T 2 output.png

# Capture a screen region (interactive)
screencapture -R x,y,width,height output.png
```

### Retina displays

On Retina Macs, `screencapture` outputs 2x resolution by default (e.g., a 2032x1238 window produces a 4064x2476 PNG). This is normal. To get 1x resolution, resize after capture:

```bash
sips --resampleWidth 2032 output.png --out output_1x.png
```

### Verify capture

```bash
# Check file was created and has content
ls -la output.png
file output.png    # Should show "PNG image data, ..."
```

## Multi-Shot Workflow

Complete example: capture multiple sections of an Excel workbook.

```bash
# 1. Open file and activate Excel
osascript -e 'tell application "Microsoft Excel"
    open POSIX file "/path/to/model.xlsx"
    activate
end tell'
sleep 2

# 2. Set up view
osascript -e 'tell application "Microsoft Excel"
    set zoom of active window to 130
    activate object sheet "Summary" of active workbook
end tell'
sleep 1

# 3. Get window ID
#    IMPORTANT: Always re-fetch before capturing. CGWindowID is invalidated
#    when an app restarts or a window is closed and reopened.
WID=$(swift -e '
import CoreGraphics
let list = CGWindowListCopyWindowInfo(.optionOnScreenOnly, kCGNullWindowID) as? [[String: Any]] ?? []
for w in list {
    let owner = w[kCGWindowOwnerName as String] as? String ?? ""
    let wid = w[kCGWindowNumber as String] as? Int ?? 0
    if owner == "Microsoft Excel" { print(wid); break }
}
')
echo "Window ID: $WID"

# 4. Capture Section A (top of sheet)
osascript -e 'tell application "Microsoft Excel"
    set scroll row of active window to 1
end tell'
sleep 1
screencapture -x -l $WID section_a.png

# 5. Capture Section B (further down)
osascript -e 'tell application "Microsoft Excel"
    set scroll row of active window to 45
end tell'
sleep 1
screencapture -x -l $WID section_b.png

# 6. Switch sheet and capture
osascript -e 'tell application "Microsoft Excel"
    activate object sheet "DCF" of active workbook
    set scroll row of active window to 1
end tell'
sleep 1
screencapture -x -l $WID dcf_overview.png
```

## Failed Approaches (DO NOT USE)

These methods were tested and confirmed to fail on macOS:

| Method | Error | Why It Fails |
|--------|-------|-------------|
| `System Events` → `id of window` | Error -1728 | System Events cannot access window IDs in the format screencapture needs |
| Python `import Quartz` (PyObjC) | `ModuleNotFoundError` | PyObjC not installed in system Python; don't attempt to install it — use Swift instead |
| `osascript` window id | Wrong format | Returns AppleScript window index, not CGWindowID needed by `screencapture -l` |

## Supported Applications

| Application | Window ID | AppleScript Control | Notes |
|------------|-----------|-------------------|-------|
| Microsoft Excel | Swift | Full (zoom, scroll, select, activate sheet) | Best supported |
| Google Chrome | Swift | Basic (activate, window management) | No scroll/zoom via AppleScript |
| Any macOS app | Swift | Basic (activate via `tell application`) | screencapture works universally |

AppleScript control depth varies by application. Excel has the richest AppleScript dictionary. For apps with limited AppleScript, use keyboard simulation via `System Events` as a fallback.
