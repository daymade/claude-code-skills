# Testing @MainActor Classes

## The Problem

Testing `@MainActor` classes like `ObservableObject` controllers in Swift 6 is challenging because:

1. `setUp()` and `tearDown()` are nonisolated
2. Properties with `private(set)` can't be set from tests
3. Direct property access from tests triggers concurrency errors

## Solution: setStateForTesting Pattern

Add a DEBUG-only method to allow tests to set internal state:

```swift
@MainActor
final class TrainingSessionController: ObservableObject {
    @Published private(set) var state: TrainingState = .idle

    // ... rest of controller ...

    // MARK: - Testing Support

    #if DEBUG
    /// Set state directly for testing purposes only
    func setStateForTesting(_ newState: TrainingState) {
        state = newState
    }
    #endif
}
```

## Test Class Structure

```swift
import XCTest
@testable import YourApp

@MainActor
final class TrainingSessionControllerTests: XCTestCase {

    var controller: TrainingSessionController!

    override func setUp() {
        super.setUp()
        controller = TrainingSessionController()
    }

    override func tearDown() {
        controller = nil
        super.tearDown()
    }

    func testConfigureFromFailedStateAutoResets() {
        // Arrange: Set to failed state
        controller.setStateForTesting(.failed("Recording too short"))

        // Act: Configure should recover
        controller.configure(with: PhaseConfig.default)

        // Assert: Should be back in idle
        XCTAssertEqual(controller.state, .idle)
    }
}
```

## State Machine Testing Patterns

### Testing State Transitions

```swift
func testStateTransitions() {
    // Test each state's behavior
    let states: [TrainingState] = [.idle, .completed, .failed("error")]

    for state in states {
        controller.setStateForTesting(state)
        controller.configure(with: PhaseConfig.default)

        // Verify expected outcome
        XCTAssertTrue(controller.canStart, "\(state) should allow starting")
    }
}
```

### Regression Tests

For bugs that have been fixed, add specific regression tests:

```swift
/// Regression test for: State machine dead-lock after recording failure
/// Bug: After error, controller stayed in failed state forever
func testRegressionFailedStateDeadLock() {
    // Simulate the bug scenario
    controller.configure(with: PhaseConfig.default)
    controller.setStateForTesting(.failed("录音太短"))

    // The fix: configure() should auto-reset from failed state
    controller.configure(with: PhaseConfig.default)

    XCTAssertEqual(controller.state, .idle,
        "REGRESSION: Failed state should not block configure()")
}
```

### State Machine Invariants

Test invariants that should always hold:

```swift
/// No terminal state should become a "dead end"
func testAllTerminalStatesAreRecoverable() {
    let terminalStates: [TrainingState] = [
        .idle,
        .completed,
        .failed("test error")
    ]

    for state in terminalStates {
        controller.setStateForTesting(state)
        // Action that should recover
        controller.configure(with: PhaseConfig.default)

        // Verify recovery
        XCTAssertTrue(canConfigure(),
            "\(state) should be recoverable via configure()")
    }
}
```

## Why This Pattern Works

1. **`#if DEBUG`**: Method only exists in test builds, zero production overhead
2. **Explicit method**: Makes test-only state manipulation obvious and searchable
3. **MainActor compatible**: Method is part of the @MainActor class
4. **Swift 6 safe**: Avoids concurrency errors by staying on the main actor

## Alternative: Internal Setter

If you prefer, you can use `internal(set)` instead of `private(set)`:

```swift
@Published internal(set) var state: TrainingState = .idle
```

However, this is redundant since properties are already internal by default. The `setStateForTesting()` pattern is more explicit about test-only intent.
