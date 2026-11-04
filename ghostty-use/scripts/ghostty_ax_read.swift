import AppKit
import ApplicationServices
import Foundation

// Read one bound Ghostty window. Never activates or changes a value.
@_silgen_name("_AXUIElementGetWindow")
func windowNumber(_ element: AXUIElement, _ result: UnsafeMutablePointer<CGWindowID>) -> AXError
func attribute(_ element: AXUIElement, _ name: String) -> CFTypeRef? {
    var value: CFTypeRef?
    return AXUIElementCopyAttributeValue(element, name as CFString, &value) == .success ? value : nil
}

func emit(_ value: [String: Any]) {
    if let bytes = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]),
       let text = String(data: bytes, encoding: .utf8) { print(text) }
}

let arguments = CommandLine.arguments
guard (arguments.count == 2 && !arguments[1].isEmpty) ||
      (arguments.count == 3 && arguments[1] == "--window-id" && UInt32(arguments[2]) != nil) else {
    emit(["available": false, "reason": "exact unique window marker required"])
    exit(1)
}
guard AXIsProcessTrusted() else {
    emit(["available": false, "reason": "AX permission unavailable; no request or fallback attempted"])
    exit(1)
}
let apps = NSRunningApplication.runningApplications(withBundleIdentifier: "com.mitchellh.ghostty")
guard apps.count == 1 else {
    emit(["available": false, "reason": "exact Ghostty application unavailable"])
    exit(1)
}
let application = AXUIElementCreateApplication(apps[0].processIdentifier)
guard let windows = attribute(application, kAXWindowsAttribute) as? [AXUIElement] else {
    emit(["available": false, "reason": "native AX windows unavailable"])
    exit(1)
}
let wantedID = arguments.count == 3 ? UInt32(arguments[2]) : nil
let matches = windows.filter {
    if let wantedID = wantedID {
        var current: CGWindowID = 0
        return windowNumber($0, &current) == .success && current == wantedID
    }
    return (attribute($0, kAXTitleAttribute) as? String) == arguments[1]
}
guard matches.count == 1 else {
    emit(["available": false, "reason": "unique marker does not bind one readable AX window", "matches": matches.count])
    exit(1)
}
var nodes = [[String: String]]()
var visited = 0
var truncated = false
func walk(_ element: AXUIElement, _ depth: Int) {
    if depth > 16 || visited >= 1500 { truncated = true; return }
    visited += 1
    var row = [String: String]()
    for (key, name) in [("role", kAXRoleAttribute), ("title", kAXTitleAttribute),
                        ("description", kAXDescriptionAttribute), ("value", kAXValueAttribute),
                        ("selected_text", kAXSelectedTextAttribute)] {
        if let value = attribute(element, name) as? String {
            if value.count > 262144 { truncated = true }
            row[key] = String(value.prefix(262144))
        }
    }
    if !row.isEmpty { nodes.append(row) }
    if let children = attribute(element, kAXChildrenAttribute) as? [AXUIElement] {
        for child in children { walk(child, depth + 1) }
    }
}
walk(matches[0], 0)
var matchedID: CGWindowID = 0
guard windowNumber(matches[0], &matchedID) == .success && matchedID > 0 else {
    emit(["available": false, "reason": "native AX window identity unavailable"])
    exit(1)
}
emit(["available": true, "marker": arguments[1], "app_pid": apps[0].processIdentifier,
      "window_id": matchedID,
      "observed_at": Date().timeIntervalSince1970, "nodes": nodes, "visited": visited,
      "truncated": truncated])
