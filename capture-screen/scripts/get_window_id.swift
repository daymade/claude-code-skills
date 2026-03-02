#!/usr/bin/env swift
//
// get_window_id.swift
// Enumerate on-screen windows and print their Window IDs.
//
// Usage:
//   swift get_window_id.swift              # List all windows
//   swift get_window_id.swift Excel        # Filter by keyword
//   swift get_window_id.swift "Chrome"     # Filter by app name
//
// Output format:
//   WID=12345 | App=Microsoft Excel | Title=workbook.xlsx
//
// The WID value is compatible with: screencapture -l <WID> output.png
//

import CoreGraphics

let keyword = CommandLine.arguments.count > 1
    ? CommandLine.arguments[1]
    : ""

guard let windowList = CGWindowListCopyWindowInfo(
    .optionOnScreenOnly, kCGNullWindowID
) as? [[String: Any]] else {
    fputs("ERROR: Failed to enumerate windows.\n", stderr)
    fputs("Possible causes:\n", stderr)
    fputs("  - No applications with visible windows are running\n", stderr)
    fputs("  - Screen Recording permission not granted (System Settings → Privacy & Security → Screen Recording)\n", stderr)
    exit(1)
}

var found = false
for w in windowList {
    let owner = w[kCGWindowOwnerName as String] as? String ?? ""
    let name = w[kCGWindowName as String] as? String ?? ""
    let wid = w[kCGWindowNumber as String] as? Int ?? 0

    // Skip windows without a title (menu bar items, system UI, etc.)
    if name.isEmpty && !keyword.isEmpty { continue }

    if keyword.isEmpty
        || owner.localizedCaseInsensitiveContains(keyword)
        || name.localizedCaseInsensitiveContains(keyword) {
        print("WID=\(wid) | App=\(owner) | Title=\(name)")
        found = true
    }
}

if !found && !keyword.isEmpty {
    fputs("No windows found matching '\(keyword)'\n", stderr)
    fputs("Troubleshooting:\n", stderr)
    fputs("  - Is the application running? (check: pgrep -i '\(keyword)')\n", stderr)
    fputs("  - Is the window visible (not minimized to Dock)?\n", stderr)
    fputs("  - Try without keyword to see all windows: swift get_window_id.swift\n", stderr)
    exit(1)
}
