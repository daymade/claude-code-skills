# Camera / AVFoundation Reference

## Camera Preview Implementation

### Complete Working Example

```swift
import SwiftUI
import AVFoundation
import os

private let logger = Logger(subsystem: "com.app", category: "Camera")

// MARK: - Session Manager

@MainActor
final class CameraSessionManager: ObservableObject {
    @Published private(set) var isRunning = false
    @Published private(set) var error: CameraError?

    let session = AVCaptureSession()
    private var videoInput: AVCaptureDeviceInput?

    enum CameraError: LocalizedError {
        case noCamera
        case setupFailed(String)
        case permissionDenied

        var errorDescription: String? {
            switch self {
            case .noCamera: return "No camera available"
            case .setupFailed(let reason): return "Setup failed: \(reason)"
            case .permissionDenied: return "Camera permission denied"
            }
        }
    }

    func start() async {
        logger.info("start() called, isRunning=\(self.isRunning)")
        guard !isRunning else { return }

        // Check permission
        guard await requestPermission() else {
            error = .permissionDenied
            return
        }

        // Get camera
        guard let device = AVCaptureDevice.default(
            .builtInWideAngleCamera,
            for: .video,
            position: .front
        ) else {
            logger.error("No front camera available")
            error = .noCamera
            return
        }

        // Configure session
        session.beginConfiguration()
        session.sessionPreset = .high

        do {
            let input = try AVCaptureDeviceInput(device: device)
            if session.canAddInput(input) {
                session.addInput(input)
                videoInput = input
            }
            session.commitConfiguration()

            // Start on background thread
            await withCheckedContinuation { continuation in
                DispatchQueue.global(qos: .userInitiated).async { [weak self] in
                    self?.session.startRunning()
                    DispatchQueue.main.async {
                        self?.isRunning = true
                        logger.info("Camera session started")
                        continuation.resume()
                    }
                }
            }
        } catch {
            session.commitConfiguration()
            self.error = .setupFailed(error.localizedDescription)
        }
    }

    func stop() {
        guard isRunning else { return }
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            self?.session.stopRunning()
            DispatchQueue.main.async {
                self?.isRunning = false
            }
        }
    }

    private func requestPermission() async -> Bool {
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized: return true
        case .notDetermined:
            return await AVCaptureDevice.requestAccess(for: .video)
        default: return false
        }
    }
}

// MARK: - SwiftUI View

struct CameraPreviewView: UIViewRepresentable {
    let session: AVCaptureSession

    func makeUIView(context: Context) -> CameraPreviewUIView {
        let view = CameraPreviewUIView()
        view.backgroundColor = .black
        view.session = session
        return view
    }

    func updateUIView(_ uiView: CameraPreviewUIView, context: Context) {}
}

final class CameraPreviewUIView: UIView {
    override class var layerClass: AnyClass { AVCaptureVideoPreviewLayer.self }

    var previewLayer: AVCaptureVideoPreviewLayer { layer as! AVCaptureVideoPreviewLayer }

    var session: AVCaptureSession? {
        get { previewLayer.session }
        set {
            previewLayer.session = newValue
            previewLayer.videoGravity = .resizeAspectFill
            configureMirroring()
        }
    }

    private func configureMirroring() {
        guard let connection = previewLayer.connection,
              connection.isVideoMirroringSupported else { return }
        // CRITICAL: Must disable automatic adjustment BEFORE setting manual mirroring
        // Without this, iOS throws: "Cannot be set when automaticallyAdjustsVideoMirroring is YES"
        connection.automaticallyAdjustsVideoMirroring = false
        connection.isVideoMirrored = true
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        previewLayer.frame = bounds
    }
}

// MARK: - Usage in SwiftUI

struct ContentView: View {
    @StateObject private var cameraManager = CameraSessionManager()

    var body: some View {
        ZStack {
            // CRITICAL: Use GeometryReader for proper sizing
            GeometryReader { geo in
                CameraPreviewView(session: cameraManager.session)
                    .frame(width: geo.size.width, height: geo.size.height)
            }
            .ignoresSafeArea()

            // Overlay content here
        }
        .onAppear {
            Task { await cameraManager.start() }
        }
        .onDisappear {
            cameraManager.stop()
        }
    }
}
```

## Common Issues and Solutions

### Issue: Camera preview shows nothing

**Debug steps:**

1. Check if running on simulator (camera not available):
```swift
#if targetEnvironment(simulator)
logger.warning("Camera not available on simulator")
#endif
```

2. Add logging to trace execution:
```swift
logger.info("Permission status: \(AVCaptureDevice.authorizationStatus(for: .video).rawValue)")
logger.info("Session running: \(session.isRunning)")
logger.info("Preview layer bounds: \(previewLayer.bounds)")
```

3. Verify Info.plist has camera permission:
```xml
<key>NSCameraUsageDescription</key>
<string>Camera access for preview</string>
```

### Issue: UIViewRepresentable has zero size

**Cause**: In ZStack, UIViewRepresentable doesn't expand like SwiftUI views.

**Solution**: Wrap in GeometryReader with explicit frame:
```swift
GeometryReader { geo in
    CameraPreviewView(session: session)
        .frame(width: geo.size.width, height: geo.size.height)
}
```

### Issue: Preview layer connection is nil

**Cause**: Connection isn't established until session is running and layer is in view hierarchy.

**Solution**: Configure mirroring in layoutSubviews:
```swift
override func layoutSubviews() {
    super.layoutSubviews()
    previewLayer.frame = bounds
    // Retry mirroring here
    configureMirroring()
}

private func configureMirroring() {
    guard let conn = previewLayer.connection,
          conn.isVideoMirroringSupported else { return }
    conn.automaticallyAdjustsVideoMirroring = false
    conn.isVideoMirrored = true
}
```

### Issue: Crash on setVideoMirrored

**Error**: `*** -[AVCaptureConnection setVideoMirrored:] Cannot be set when automaticallyAdjustsVideoMirroring is YES`

**Cause**: iOS automatically adjusts mirroring by default. Setting `isVideoMirrored` while automatic adjustment is enabled throws an exception.

**Solution**: Always disable automatic adjustment first:
```swift
// WRONG - crashes on some devices
connection.isVideoMirrored = true

// CORRECT - disable automatic first
connection.automaticallyAdjustsVideoMirroring = false
connection.isVideoMirrored = true
```

**Affected Devices**: Primarily older devices (iPhone X, etc.) but can affect any device.

### Issue: Swift 6 concurrency errors with AVCaptureSession

**Error**: "cannot access property 'session' with non-Sendable type from nonisolated deinit"

**Solution**: Don't access session in deinit. Use explicit stop() call:
```swift
deinit {
    // Don't access session here
    // Cleanup handled by stop() call from view
}
```

## Debugging with Console.app

1. Open Console.app
2. Select your device
3. Filter by:
   - Subsystem: `com.yourapp`
   - Category: `Camera`
4. Look for the log sequence:
   ```
   start() called, isRunning=false
   Permission granted
   Found front camera: Front Camera
   Camera session started
   ```

## Camera + Audio Conflict

If using AudioKit or AVAudioEngine, camera audio input may conflict.

**Solution**: Use video-only input, no audio:
```swift
// Only add video input, skip audio
let videoInput = try AVCaptureDeviceInput(device: videoDevice)
session.addInput(videoInput)
// Do NOT add audio input
```
