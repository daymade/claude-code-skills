# SwiftUI iOS Version Compatibility

## iOS 17 vs iOS 16 API Differences

### View Modifiers

#### onChange

```swift
// iOS 17+ (dual parameter)
.onChange(of: value) { oldValue, newValue in
    // Can compare old and new
}

// iOS 16 (single parameter)
.onChange(of: value) { newValue in
    // Only new value available
}
```

#### sensoryFeedback (iOS 17+)

```swift
// iOS 17+
.sensoryFeedback(.impact, trigger: triggerValue)

// iOS 16 fallback
UIImpactFeedbackGenerator(style: .medium).impactOccurred()
```

### Views

#### ContentUnavailableView (iOS 17+)

```swift
// iOS 17+
ContentUnavailableView(
    "No Results",
    systemImage: "magnifyingglass",
    description: Text("Try a different search")
)

// iOS 16 fallback
VStack(spacing: 16) {
    Image(systemName: "magnifyingglass")
        .font(.system(size: 48))
        .foregroundStyle(.secondary)
    Text("No Results")
        .font(.title2.bold())
    Text("Try a different search")
        .font(.subheadline)
        .foregroundStyle(.secondary)
}
.frame(maxWidth: .infinity, maxHeight: .infinity)
```

#### Inspector (iOS 17+)

```swift
// iOS 17+
.inspector(isPresented: $showInspector) {
    InspectorContent()
}

// iOS 16 fallback: Use sheet or sidebar
.sheet(isPresented: $showInspector) {
    InspectorContent()
}
```

### Observation

#### @Observable Macro (iOS 17+)

```swift
// iOS 17+ with @Observable
@Observable
class ViewModel {
    var count = 0
}

struct ContentView: View {
    var viewModel = ViewModel()
    var body: some View {
        Text("\(viewModel.count)")
    }
}

// iOS 16 with ObservableObject
class ViewModel: ObservableObject {
    @Published var count = 0
}

struct ContentView: View {
    @StateObject var viewModel = ViewModel()
    var body: some View {
        Text("\(viewModel.count)")
    }
}
```

### Audio

#### AVAudioApplication (iOS 17+)

```swift
// iOS 17+
let permission = AVAudioApplication.shared.recordPermission
AVAudioApplication.requestRecordPermission { granted in }

// iOS 16
let permission = AVAudioSession.sharedInstance().recordPermission
AVAudioSession.sharedInstance().requestRecordPermission { granted in }
```

### Animations

#### Symbol Effects (iOS 17+)

```swift
// iOS 17+
Image(systemName: "heart.fill")
    .symbolEffect(.bounce, value: isFavorite)

// iOS 16 fallback
Image(systemName: "heart.fill")
    .scaleEffect(isFavorite ? 1.2 : 1.0)
    .animation(.spring(), value: isFavorite)
```

### Data

#### SwiftData (iOS 17+)

```swift
// iOS 17+ with SwiftData
@Model
class Item {
    var name: String
    var timestamp: Date
}

// iOS 16: Use CoreData or third-party (Realm)
// CoreData: NSManagedObject subclass
// Realm: Object subclass with @Persisted properties
```

## Conditional Compilation

For features that must use iOS 17 APIs when available:

```swift
if #available(iOS 17.0, *) {
    ContentUnavailableView("Title", systemImage: "icon")
} else {
    LegacyEmptyView()
}
```

For view modifiers:

```swift
extension View {
    @ViewBuilder
    func onChangeCompat<V: Equatable>(of value: V, perform: @escaping (V) -> Void) -> some View {
        if #available(iOS 17.0, *) {
            self.onChange(of: value) { _, newValue in
                perform(newValue)
            }
        } else {
            self.onChange(of: value, perform: perform)
        }
    }
}
```

## Minimum Deployment Targets by Feature

| Feature | Minimum iOS |
|---------|-------------|
| SwiftUI basics | 13.0 |
| @StateObject | 14.0 |
| AsyncImage | 15.0 |
| .searchable | 15.0 |
| NavigationStack | 16.0 |
| .navigationDestination | 16.0 |
| @Observable | 17.0 |
| ContentUnavailableView | 17.0 |
| SwiftData | 17.0 |
| .onChange (dual param) | 17.0 |
