#!/usr/bin/env swift
//
// get_window_id.swift
// Enumerate on-screen windows and print their Window IDs.
//
// Usage:
//   swift scripts/get_window_id.swift               # List all windows
//   swift scripts/get_window_id.swift Excel         # Filter by keyword
//   swift scripts/get_window_id.swift "Chrome"      # Filter by app name
//   swift scripts/get_window_id.swift --permission-hint screen   # Print Screen Recording triage
//   swift scripts/get_window_id.swift --permission-hint microphone  # Print Microphone triage
//
// Output format:
//   WID=12345 | App=Microsoft Excel | Title=workbook.xlsx
//
// The WID value is compatible with: screencapture -l <WID> output.png
//

import CoreGraphics
import Foundation

enum PermissionKind: String {
    case screen
    case microphone
}

let invocationPath = (CommandLine.arguments.first ?? "")
let invokerName = URL(fileURLWithPath: invocationPath).lastPathComponent
let runtimeProcessName = ProcessInfo.processInfo.processName
let invokerIsBundle = invocationPath.hasSuffix(".app") || invocationPath.contains(".app/")
let scriptPath: String? = invocationPath.hasSuffix(".swift") ? invocationPath : nil
let helperBinaries: Set<String> = [
    "swift",
    "swift-frontend",
    "python",
    "python3",
    "node",
    "uv",
    "npm",
    "bun",
    "pnpm",
    "yarn",
    "bash",
    "zsh",
    "sh",
    "osascript",
    "Terminal",
    "iTerm2",
    "iTerm"
]

let invokerCandidates: [String] = {
    var candidates = [String]()
    var seen = Set<String>()
    func append(_ value: String) {
        guard !value.isEmpty, !seen.contains(value) else { return }
        seen.insert(value)
        candidates.append(value)
    }
    if let scriptPath = scriptPath {
        append(scriptPath)
    }
    if !invokerName.isEmpty {
        append(invokerName)
    }
    if !runtimeProcessName.isEmpty && runtimeProcessName != invokerName {
        append(runtimeProcessName)
    }
    return candidates
}()

let args = Array(CommandLine.arguments.dropFirst())

var permissionHintTarget: PermissionKind?
var keyword = ""
var expectPermissionTarget = false

func printUsage() {
    fputs("Usage:\n", stderr)
    fputs("  swift scripts/get_window_id.swift [keyword]\n", stderr)
    fputs("  swift scripts/get_window_id.swift --permission-hint [screen|microphone]\n", stderr)
    fputs("\n", stderr)
    fputs("Options:\n", stderr)
    fputs("  --permission-hint [screen|microphone]  Print permission triage instructions\n", stderr)
    fputs("  -h, --help                            Show this help\n", stderr)
    fputs("\n", stderr)
    fputs("Examples:\n", stderr)
    fputs("  swift scripts/get_window_id.swift Excel\n", stderr)
    fputs("  swift scripts/get_window_id.swift --permission-hint screen\n", stderr)
    fputs("  swift scripts/get_window_id.swift --permission-hint microphone\n", stderr)
}

for arg in args {
    if expectPermissionTarget {
        if let kind = PermissionKind(rawValue: arg.lowercased()) {
            permissionHintTarget = kind
            expectPermissionTarget = false
            continue
        }
        fputs("Unknown permission target: \(arg)\n", stderr)
        printUsage()
        exit(2)
    }

    if arg == "-h" || arg == "--help" {
        printUsage()
        exit(0)
    } else if arg == "--permission-hint" {
        permissionHintTarget = .screen
        expectPermissionTarget = true
    } else if arg.hasPrefix("--permission-hint=") {
        let target = String(arg.dropFirst("--permission-hint=".count)).lowercased()
        guard let kind = PermissionKind(rawValue: target) else {
            fputs("Unknown permission target: \(target)\n", stderr)
            printUsage()
            exit(2)
        }
        permissionHintTarget = kind
    } else if arg == "--permission-hint-screen" {
        permissionHintTarget = .screen
    } else if arg == "--permission-hint-microphone" || arg == "--permission-hint-mic" {
        permissionHintTarget = .microphone
    } else if arg.hasPrefix("-") {
        fputs("Unknown option: \(arg)\n", stderr)
        printUsage()
        exit(2)
    } else if keyword.isEmpty {
        keyword = arg
    }
}

if expectPermissionTarget {
    fputs("Missing permission hint target after --permission-hint.\n", stderr)
    printUsage()
    exit(2)
}

if let kind = permissionHintTarget {
    switch kind {
    case .screen:
        fputs("Screen Recording permission required.\n", stderr)
        printCommonPermissionHint(
            pane: "Privacy_ScreenCapture",
            label: "Screen Recording"
        )
        printPermissionContextHint()
    case .microphone:
        fputs("Microphone permission required.\n", stderr)
        printCommonPermissionHint(
            pane: "Privacy_Microphone",
            label: "Microphone"
        )
        printPermissionContextHint()
    }
    exit(0)
}

func printCommonPermissionHint(pane: String, label: String, missing: Bool = true) {
    let openCommand = "x-apple.systempreferences:com.apple.preference.security?\(pane)"
    fputs("Troubleshooting:\n", stderr)
    fputs("  - Open Settings: `open \"\(openCommand)\"`\n", stderr)
    fputs("  - In Privacy & Security → \(label), enable the target application.\n", stderr)
    if missing {
        fputs("  - If the target app is not in the list:\n", stderr)
        fputs("      - Granting happens by real .app bundle, not by helper/terminal scripts.\n", stderr)
        fputs("      - For CLI workflows, grant to the host app you launch from (Terminal, iTerm, iTerm2, Swift, etc.) if no dedicated .app exists yet.\n", stderr)
        fputs("      - Click `+` and add the actual `.app` from `/Applications`.\n", stderr)
    }
    fputs("  - If permission status does not refresh, quit/reopen terminal/app and retry.\n", stderr)
    if helperBinaries.contains(invokerName) || helperBinaries.contains(runtimeProcessName) {
        fputs("  - Current launcher is a helper/runtime process (`\(runtimeProcessName)`) -> OS may show this entry instead of the tool name.\n", stderr)
    } else if invokerIsBundle {
        fputs("  - The launcher path looks like a bundled app, which is the preferred state for permissions.\n", stderr)
    }
    if let scriptPath = scriptPath {
        fputs("  - Script entry: `\(scriptPath)`\n", stderr)
    }
}

func printPermissionContextHint() {
    fputs("  - Invoker path: `\(invocationPath)`\n", stderr)
    fputs("  - Runtime process: `\(runtimeProcessName)`\n", stderr)
    if !invokerCandidates.isEmpty {
        fputs("  - Candidate identities in System Settings:\n", stderr)
        for identity in invokerCandidates {
            fputs("      - \(identity)\n", stderr)
        }
    }
    if invokerIsBundle {
        fputs("    This looks like a bundled app path, so the setting should match the app identity.\n", stderr)
    } else {
        fputs("    If this is not your final app binary, permissions can be inconsistent.\n", stderr)
    }
    fputs("  - Recommended for production: keep permission requests inside your signed `.app` process.\n", stderr)
    if let scriptPath = scriptPath {
        fputs("  - Script entry currently used: `\(scriptPath)`.\n", stderr)
    }
}

func printScreenRecordingPermissionHint() {
    fputs("Screen Recording permission required.\n", stderr)
    fputs("Troubleshooting:\n", stderr)
    printCommonPermissionHint(pane: "Privacy_ScreenCapture", label: "Screen Recording")
    printPermissionContextHint()
}

guard let windowList = CGWindowListCopyWindowInfo(
    .optionOnScreenOnly, kCGNullWindowID
) as? [[String: Any]] else {
    fputs("ERROR: Failed to enumerate windows.\n", stderr)
    fputs("Possible causes:\n", stderr)
    fputs("  - No applications with visible windows are running\n", stderr)
    fputs("  - Screen Recording permission not granted (System Settings → Privacy & Security → Screen Recording)\n", stderr)
    printScreenRecordingPermissionHint()
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
