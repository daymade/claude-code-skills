---
name: developing-ios-apps
description: Develops iOS applications with XcodeGen, SwiftUI, and SPM. Triggers on XcodeGen project.yml configuration, SPM dependency issues, device deployment problems, code signing errors, camera/AVFoundation debugging, iOS version compatibility, or "Library not loaded @rpath" framework errors. Use when building iOS apps, fixing Xcode build failures, or deploying to real devices.
---

# iOS App Development

Build, configure, and deploy iOS applications using XcodeGen and Swift Package Manager.

## Critical Warnings

| Issue | Cause | Solution |
|-------|-------|----------|
| "Library not loaded: @rpath/Framework" | XcodeGen doesn't auto-embed SPM dynamic frameworks | **Build in Xcode GUI first** (not xcodebuild). See [Troubleshooting](#spm-dynamic-framework-not-embedded) |
| `xcodegen generate` loses signing | Overwrites project settings | Configure in `project.yml` target settings, not global |
| Command-line signing fails | Free Apple ID limitation | Use Xcode GUI or paid developer account ($99/yr) |
| "Cannot be set when automaticallyAdjustsVideoMirroring is YES" | Setting `isVideoMirrored` without disabling automatic | Set `automaticallyAdjustsVideoMirroring = false` first. See [Camera](#camera--avfoundation) |

## Quick Reference

| Task | Command |
|------|---------|
| Generate project | `xcodegen generate` |
| Build simulator | `xcodebuild -destination 'platform=iOS Simulator,name=iPhone 17' build` |
| Build device (paid account) | `xcodebuild -destination 'platform=iOS,name=DEVICE' -allowProvisioningUpdates build` |
| Clean DerivedData | `rm -rf ~/Library/Developer/Xcode/DerivedData/PROJECT-*` |
| Find device name | `xcrun xctrace list devices` |

## XcodeGen Configuration

### Minimal project.yml

```yaml
name: AppName
options:
  bundleIdPrefix: com.company
  deploymentTarget:
    iOS: "16.0"

settings:
  base:
    SWIFT_VERSION: "6.0"

packages:
  SomePackage:
    url: https://github.com/org/repo
    from: "1.0.0"

targets:
  AppName:
    type: application
    platform: iOS
    sources:
      - path: AppName
    settings:
      base:
        INFOPLIST_FILE: AppName/Info.plist
        PRODUCT_BUNDLE_IDENTIFIER: com.company.appname
        CODE_SIGN_STYLE: Automatic
        DEVELOPMENT_TEAM: TEAM_ID_HERE
    dependencies:
      - package: SomePackage
```

### Code Signing Configuration

**Personal (free) account**: Works in Xcode GUI only. Command-line builds require paid account.

```yaml
# In target settings
settings:
  base:
    CODE_SIGN_STYLE: Automatic
    DEVELOPMENT_TEAM: TEAM_ID  # Get from Xcode → Settings → Accounts
```

**Get Team ID**:
```bash
security find-identity -v -p codesigning | head -3
```

## iOS Version Compatibility

### API Changes by Version

| iOS 17+ Only | iOS 16 Compatible |
|--------------|-------------------|
| `.onChange { old, new in }` | `.onChange { new in }` |
| `ContentUnavailableView` | Custom VStack |
| `AVAudioApplication` | `AVAudioSession` |
| `@Observable` macro | `@ObservableObject` |
| SwiftData | CoreData/Realm |

### Lowering Deployment Target

1. Update `project.yml`:
```yaml
deploymentTarget:
  iOS: "16.0"
```

2. Fix incompatible APIs:
```swift
// iOS 17
.onChange(of: value) { oldValue, newValue in }
// iOS 16
.onChange(of: value) { newValue in }

// iOS 17
ContentUnavailableView("Title", systemImage: "icon")
// iOS 16
VStack {
    Image(systemName: "icon").font(.system(size: 48))
    Text("Title").font(.title2.bold())
}

// iOS 17
AVAudioApplication.shared.recordPermission
// iOS 16
AVAudioSession.sharedInstance().recordPermission
```

3. Regenerate: `xcodegen generate`

## Device Deployment

### First-time Setup

1. Connect device via USB
2. Trust computer on device
3. In Xcode: Settings → Accounts → Add Apple ID
4. Select device in scheme dropdown
5. Run (`Cmd + R`)
6. On device: Settings → General → VPN & Device Management → Trust

### Command-line Build (requires paid account)

```bash
xcodebuild \
  -project App.xcodeproj \
  -scheme App \
  -destination 'platform=iOS,name=DeviceName' \
  -allowProvisioningUpdates \
  build
```

### Common Issues

| Error | Solution |
|-------|----------|
| "Library not loaded: @rpath/Framework" | SPM dynamic framework not embedded. Build in Xcode GUI first, then CLI works |
| "No Account for Team" | Add Apple ID in Xcode Settings → Accounts |
| "Provisioning profile not found" | Free account limitation. Use Xcode GUI or get paid account |
| Device not listed | Reconnect USB, trust computer on device, restart Xcode |
| DerivedData won't delete | Close Xcode first: `pkill -9 Xcode && rm -rf ~/Library/Developer/Xcode/DerivedData/PROJECT-*` |

### Free vs Paid Developer Account

| Feature | Free Apple ID | Paid ($99/year) |
|---------|---------------|-----------------|
| Xcode GUI builds | ✅ | ✅ |
| Command-line builds | ❌ | ✅ |
| App validity | 7 days | 1 year |
| App Store | ❌ | ✅ |
| CI/CD | ❌ | ✅ |

## SPM Dependencies

### SPM Dynamic Framework Not Embedded

**Root Cause**: XcodeGen doesn't generate the "Embed Frameworks" build phase for SPM dynamic frameworks (like RealmSwift, Realm). The app builds successfully but crashes on launch with:

```
dyld: Library not loaded: @rpath/RealmSwift.framework/RealmSwift
  Referenced from: /var/containers/Bundle/Application/.../App.app/App
  Reason: image not found
```

**Why This Happens**:
- Static frameworks (most SPM packages) are linked into the binary - no embedding needed
- Dynamic frameworks (RealmSwift, etc.) must be copied into the app bundle
- XcodeGen generates link phase but NOT embed phase for SPM packages
- `embed: true` in project.yml causes build errors (XcodeGen limitation)

**The Fix** (Manual, one-time per project):
1. Open project in Xcode GUI
2. Select target → General → Frameworks, Libraries
3. Find the dynamic framework (RealmSwift)
4. Change "Do Not Embed" → "Embed & Sign"
5. Build and run from Xcode GUI first

**After Manual Fix**: Command-line builds (`xcodebuild`) will work because Xcode persists the embed setting in project.pbxproj.

**Identifying Dynamic Frameworks**:
```bash
# Check if a framework is dynamic
file ~/Library/Developer/Xcode/DerivedData/PROJECT-*/Build/Products/Debug-iphoneos/FRAMEWORK.framework/FRAMEWORK
# Dynamic: "Mach-O 64-bit dynamically linked shared library"
# Static: "current ar archive"
```

### Adding Packages

```yaml
packages:
  AudioKit:
    url: https://github.com/AudioKit/AudioKit
    from: "5.6.5"
  RealmSwift:
    url: https://github.com/realm/realm-swift
    from: "10.54.6"

targets:
  App:
    dependencies:
      - package: AudioKit
      - package: RealmSwift
        product: RealmSwift  # Explicit product name when package has multiple
```

### Resolving Dependencies (China proxy)

```bash
git config --global http.proxy http://127.0.0.1:1082
git config --global https.proxy http://127.0.0.1:1082
xcodebuild -scmProvider system -resolvePackageDependencies
```

**Never clear global SPM cache** (`~/Library/Caches/org.swift.swiftpm`). Re-downloading is slow.

## Camera / AVFoundation

Camera preview requires real device (simulator has no camera).

### Quick Debugging Checklist

1. **Permission**: Added `NSCameraUsageDescription` to Info.plist?
2. **Device**: Running on real device, not simulator?
3. **Session running**: `session.startRunning()` called on background thread?
4. **View size**: UIViewRepresentable has non-zero bounds?
5. **Video mirroring**: Disabled `automaticallyAdjustsVideoMirroring` before setting `isVideoMirrored`?

### Video Mirroring (Front Camera)

**CRITICAL**: Must disable automatic adjustment before setting manual mirroring:

```swift
// WRONG - crashes with "Cannot be set when automaticallyAdjustsVideoMirroring is YES"
connection.isVideoMirrored = true

// CORRECT - disable automatic first
connection.automaticallyAdjustsVideoMirroring = false
connection.isVideoMirrored = true
```

### UIViewRepresentable Sizing Issue

UIViewRepresentable in ZStack may have zero bounds. Fix with explicit frame:

```swift
// BAD: UIViewRepresentable may get zero size in ZStack
ZStack {
    CameraPreviewView(session: session)  // May be invisible!
    OtherContent()
}

// GOOD: Explicit sizing
ZStack {
    GeometryReader { geo in
        CameraPreviewView(session: session)
            .frame(width: geo.size.width, height: geo.size.height)
    }
    .ignoresSafeArea()
    OtherContent()
}
```

### Debug Logging Pattern

Add logging to trace camera flow:

```swift
import os
private let logger = Logger(subsystem: "com.app", category: "Camera")

func start() async {
    logger.info("start() called, isRunning=\(self.isRunning)")
    // ... setup code ...
    logger.info("session.startRunning() completed")
}

// For CGRect (doesn't conform to CustomStringConvertible)
logger.info("bounds=\(NSCoder.string(for: self.bounds))")
```

Filter in Console.app by subsystem.

**For detailed camera implementation**: See [references/camera-avfoundation.md](references/camera-avfoundation.md)

## Resources

- [references/xcodegen-full.md](references/xcodegen-full.md) - Complete project.yml options
- [references/swiftui-compatibility.md](references/swiftui-compatibility.md) - iOS version API differences
- [references/camera-avfoundation.md](references/camera-avfoundation.md) - Camera preview debugging
- [references/testing-mainactor.md](references/testing-mainactor.md) - Testing @MainActor classes (state machines, regression tests)
