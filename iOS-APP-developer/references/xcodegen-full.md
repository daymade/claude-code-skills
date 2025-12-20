# XcodeGen Complete Reference

## Full project.yml Structure

```yaml
name: ProjectName

options:
  bundleIdPrefix: com.company
  deploymentTarget:
    iOS: "16.0"
    macOS: "13.0"
  xcodeVersion: "16.0"
  generateEmptyDirectories: true
  createIntermediateGroups: true

settings:
  base:
    SWIFT_VERSION: "6.0"
    MARKETING_VERSION: "1.0.0"
    CURRENT_PROJECT_VERSION: "1"

packages:
  # Basic package
  PackageName:
    url: https://github.com/org/repo
    from: "1.0.0"

  # Exact version
  ExactPackage:
    url: https://github.com/org/repo
    exactVersion: "2.0.0"

  # Branch
  BranchPackage:
    url: https://github.com/org/repo
    branch: main

  # Local package
  LocalPackage:
    path: ../LocalPackage

targets:
  MainApp:
    type: application
    platform: iOS
    sources:
      - path: Sources
        excludes:
          - "**/.DS_Store"
          - "**/Tests/**"
      - path: Resources
        type: folder

    settings:
      base:
        INFOPLIST_FILE: Sources/Info.plist
        PRODUCT_BUNDLE_IDENTIFIER: com.company.app
        ASSETCATALOG_COMPILER_APPICON_NAME: AppIcon
        ASSETCATALOG_COMPILER_GLOBAL_ACCENT_COLOR_NAME: AccentColor
        LD_RUNPATH_SEARCH_PATHS: "$(inherited) @executable_path/Frameworks"
        ENABLE_BITCODE: NO
        CODE_SIGN_STYLE: Automatic
        DEVELOPMENT_TEAM: TEAM_ID
      configs:
        Debug:
          SWIFT_OPTIMIZATION_LEVEL: -Onone
        Release:
          SWIFT_OPTIMIZATION_LEVEL: -O

    dependencies:
      # SPM package
      - package: PackageName

      # SPM package with explicit product
      - package: Firebase
        product: FirebaseAnalytics

      # Another target
      - target: Framework

      # System framework
      - framework: UIKit.framework

      # SDK
      - sdk: CoreLocation.framework

    preBuildScripts:
      - name: "Run Script"
        script: |
          echo "Pre-build script"
        runOnlyWhenInstalling: false

    postBuildScripts:
      - name: "Post Build"
        script: |
          echo "Post-build script"

  Tests:
    type: bundle.unit-test
    platform: iOS
    sources:
      - path: Tests
    dependencies:
      - target: MainApp
    settings:
      base:
        TEST_HOST: "$(BUILT_PRODUCTS_DIR)/MainApp.app/$(BUNDLE_EXECUTABLE_FOLDER_PATH)/MainApp"
        BUNDLE_LOADER: "$(TEST_HOST)"
```

## Target Types

| Type | Description |
|------|-------------|
| `application` | iOS/macOS app |
| `framework` | Dynamic framework |
| `staticFramework` | Static framework |
| `bundle.unit-test` | Unit test bundle |
| `bundle.ui-testing` | UI test bundle |
| `app-extension` | App extension |
| `watch2-app` | watchOS app |
| `widget-extension` | Widget extension |

## Build Settings Reference

### Common Settings

```yaml
settings:
  base:
    # Versioning
    MARKETING_VERSION: "1.0.0"
    CURRENT_PROJECT_VERSION: "1"

    # Swift
    SWIFT_VERSION: "6.0"
    SWIFT_STRICT_CONCURRENCY: complete

    # Signing
    CODE_SIGN_STYLE: Automatic
    DEVELOPMENT_TEAM: TEAM_ID
    CODE_SIGN_IDENTITY: "Apple Development"

    # Deployment
    IPHONEOS_DEPLOYMENT_TARGET: "16.0"
    TARGETED_DEVICE_FAMILY: "1,2"  # 1=iPhone, 2=iPad

    # Build
    ENABLE_BITCODE: NO
    DEBUG_INFORMATION_FORMAT: dwarf-with-dsym

    # Paths
    LD_RUNPATH_SEARCH_PATHS: "$(inherited) @executable_path/Frameworks"
```

### Per-Configuration Settings

```yaml
settings:
  configs:
    Debug:
      SWIFT_OPTIMIZATION_LEVEL: -Onone
      SWIFT_ACTIVE_COMPILATION_CONDITIONS: DEBUG
      MTL_ENABLE_DEBUG_INFO: INCLUDE_SOURCE
    Release:
      SWIFT_OPTIMIZATION_LEVEL: -O
      SWIFT_COMPILATION_MODE: wholemodule
      VALIDATE_PRODUCT: YES
```

## Info.plist Keys

Common keys to add:

```xml
<key>NSCameraUsageDescription</key>
<string>Camera access description</string>

<key>NSMicrophoneUsageDescription</key>
<string>Microphone access description</string>

<key>NSPhotoLibraryUsageDescription</key>
<string>Photo library access description</string>

<key>UIBackgroundModes</key>
<array>
    <string>audio</string>
    <string>location</string>
</array>

<key>UISupportedInterfaceOrientations</key>
<array>
    <string>UIInterfaceOrientationPortrait</string>
</array>
```
