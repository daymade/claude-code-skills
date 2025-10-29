#!/usr/bin/env python3
"""
Test suite for LearningEngine thread-safety.

CRITICAL FIX (P1-1): Tests for race condition prevention
- Concurrent writes to pending suggestions
- Concurrent writes to rejected patterns
- Concurrent writes to auto-approved patterns
- Lock acquisition and release
- Deadlock prevention
"""

import json
import tempfile
import threading
import time
from pathlib import Path
from typing import List
from dataclasses import asdict

import pytest

# Import classes - note: run tests from scripts/ directory
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import only what we need to avoid circular dependencies
from dataclasses import dataclass, asdict as dataclass_asdict

# Manually define Suggestion to avoid circular import
@dataclass
class Suggestion:
    """Represents a learned correction suggestion"""
    from_text: str
    to_text: str
    frequency: int
    confidence: float
    examples: List
    first_seen: str
    last_seen: str
    status: str

# Import LearningEngine last
# We'll mock the correction_service dependency to avoid circular imports
import core.learning_engine as le_module
LearningEngine = le_module.LearningEngine


class TestLearningEngineThreadSafety:
    """Test thread-safety of LearningEngine file operations"""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for testing"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            history_dir = temp_path / "history"
            learned_dir = temp_path / "learned"
            history_dir.mkdir()
            learned_dir.mkdir()
            yield history_dir, learned_dir

    @pytest.fixture
    def engine(self, temp_dirs):
        """Create LearningEngine instance"""
        history_dir, learned_dir = temp_dirs
        return LearningEngine(history_dir, learned_dir)

    def test_concurrent_save_pending_no_data_loss(self, engine):
        """
        Test that concurrent writes to pending suggestions don't lose data.

        CRITICAL: This is the main race condition we're preventing.
        Without locks, concurrent appends would overwrite each other.
        """
        num_threads = 10
        suggestions_per_thread = 5

        def save_suggestions(thread_id: int):
            """Save suggestions from a single thread"""
            suggestions = []
            for i in range(suggestions_per_thread):
                suggestions.append(Suggestion(
                    from_text=f"thread{thread_id}_from{i}",
                    to_text=f"thread{thread_id}_to{i}",
                    frequency=1,
                    confidence=0.9,
                    examples=[],
                    first_seen="2025-01-01",
                    last_seen="2025-01-01",
                    status="pending"
                ))
            engine._save_pending_suggestions(suggestions)

        # Launch concurrent threads
        threads = []
        for thread_id in range(num_threads):
            thread = threading.Thread(target=save_suggestions, args=(thread_id,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify: ALL suggestions should be saved
        pending = engine._load_pending_suggestions()
        expected_count = num_threads * suggestions_per_thread

        assert len(pending) == expected_count, (
            f"Data loss detected! Expected {expected_count} suggestions, "
            f"but found {len(pending)}. Race condition occurred."
        )

        # Verify uniqueness (no duplicates from overwrites)
        from_texts = [s["from_text"] for s in pending]
        assert len(from_texts) == len(set(from_texts)), "Duplicate suggestions found"

    def test_concurrent_approve_suggestions(self, engine):
        """Test that concurrent approvals don't cause race conditions"""
        # Pre-populate with suggestions
        initial_suggestions = []
        for i in range(20):
            initial_suggestions.append(Suggestion(
                from_text=f"from{i}",
                to_text=f"to{i}",
                frequency=1,
                confidence=0.9,
                examples=[],
                first_seen="2025-01-01",
                last_seen="2025-01-01",
                status="pending"
            ))
        engine._save_pending_suggestions(initial_suggestions)

        # Approve half of them concurrently
        def approve_suggestion(from_text: str):
            engine.approve_suggestion(from_text)

        threads = []
        for i in range(10):
            thread = threading.Thread(target=approve_suggestion, args=(f"from{i}",))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Verify: exactly 10 should remain
        pending = engine._load_pending_suggestions()
        assert len(pending) == 10, f"Expected 10 remaining, found {len(pending)}"

        # Verify: the correct ones remain
        remaining_from_texts = {s["from_text"] for s in pending}
        expected_remaining = {f"from{i}" for i in range(10, 20)}
        assert remaining_from_texts == expected_remaining

    def test_concurrent_reject_suggestions(self, engine):
        """Test that concurrent rejections handle both pending and rejected locks"""
        # Pre-populate with suggestions
        initial_suggestions = []
        for i in range(10):
            initial_suggestions.append(Suggestion(
                from_text=f"from{i}",
                to_text=f"to{i}",
                frequency=1,
                confidence=0.9,
                examples=[],
                first_seen="2025-01-01",
                last_seen="2025-01-01",
                status="pending"
            ))
        engine._save_pending_suggestions(initial_suggestions)

        # Reject all of them concurrently
        def reject_suggestion(from_text: str, to_text: str):
            engine.reject_suggestion(from_text, to_text)

        threads = []
        for i in range(10):
            thread = threading.Thread(
                target=reject_suggestion,
                args=(f"from{i}", f"to{i}")
            )
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Verify: pending should be empty
        pending = engine._load_pending_suggestions()
        assert len(pending) == 0, f"Expected 0 pending, found {len(pending)}"

        # Verify: rejected should have all 10
        rejected = engine._load_rejected()
        assert len(rejected) == 10, f"Expected 10 rejected, found {len(rejected)}"

        expected_rejected = {(f"from{i}", f"to{i}") for i in range(10)}
        assert rejected == expected_rejected

    def test_concurrent_auto_approve_no_data_loss(self, engine):
        """Test that concurrent auto-approvals don't lose data"""
        num_threads = 5
        patterns_per_thread = 3

        def save_auto_approved(thread_id: int):
            """Save auto-approved patterns from a single thread"""
            patterns = []
            for i in range(patterns_per_thread):
                patterns.append({
                    "from": f"thread{thread_id}_from{i}",
                    "to": f"thread{thread_id}_to{i}",
                    "frequency": 5,
                    "confidence": 0.9,
                    "domain": "general"
                })
            engine._save_auto_approved(patterns)

        # Launch concurrent threads
        threads = []
        for thread_id in range(num_threads):
            thread = threading.Thread(target=save_auto_approved, args=(thread_id,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Verify: ALL patterns should be saved
        with open(engine.auto_approved_file, 'r') as f:
            data = json.load(f)
            auto_approved = data.get("auto_approved", [])

        expected_count = num_threads * patterns_per_thread
        assert len(auto_approved) == expected_count, (
            f"Data loss in auto-approved! Expected {expected_count}, "
            f"found {len(auto_approved)}"
        )

    def test_lock_timeout_handling(self, engine):
        """Test that lock timeout is handled gracefully"""
        # Acquire lock and hold it
        lock_acquired = threading.Event()
        lock_released = threading.Event()

        def hold_lock():
            """Hold lock for extended period"""
            with engine._file_lock(engine.pending_lock, "hold lock"):
                lock_acquired.set()
                # Hold lock for 2 seconds
                lock_released.wait(timeout=2.0)

        # Start thread holding lock
        holder_thread = threading.Thread(target=hold_lock)
        holder_thread.start()

        # Wait for lock to be acquired
        lock_acquired.wait(timeout=1.0)

        # Try to acquire lock with short timeout (should fail)
        original_timeout = engine.lock_timeout
        engine.lock_timeout = 0.5  # 500ms timeout

        try:
            with pytest.raises(RuntimeError, match="File lock timeout"):
                with engine._file_lock(engine.pending_lock, "test timeout"):
                    pass
        finally:
            # Restore original timeout
            engine.lock_timeout = original_timeout
            # Release the held lock
            lock_released.set()
            holder_thread.join()

    def test_no_deadlock_with_multiple_locks(self, engine):
        """Test that acquiring multiple locks doesn't cause deadlock"""
        num_threads = 5
        iterations = 10

        def reject_multiple():
            """Reject multiple suggestions (acquires both pending and rejected locks)"""
            for i in range(iterations):
                # This exercises the lock acquisition order
                engine.reject_suggestion(f"from{i}", f"to{i}")

        # Pre-populate
        for i in range(iterations):
            engine._save_pending_suggestions([Suggestion(
                from_text=f"from{i}",
                to_text=f"to{i}",
                frequency=1,
                confidence=0.9,
                examples=[],
                first_seen="2025-01-01",
                last_seen="2025-01-01",
                status="pending"
            )])

        # Launch concurrent rejections
        threads = []
        for _ in range(num_threads):
            thread = threading.Thread(target=reject_multiple)
            threads.append(thread)
            thread.start()

        # Wait for completion (with timeout to detect deadlock)
        deadline = time.time() + 10.0  # 10 second deadline
        for thread in threads:
            remaining = deadline - time.time()
            if remaining <= 0:
                pytest.fail("Deadlock detected! Threads did not complete in time.")
            thread.join(timeout=remaining)
            if thread.is_alive():
                pytest.fail("Deadlock detected! Thread still alive after timeout.")

        # If we get here, no deadlock occurred
        assert True

    def test_lock_files_created(self, engine):
        """Test that lock files are created in correct location"""
        # Trigger an operation that uses locks
        suggestions = [Suggestion(
            from_text="test",
            to_text="test",
            frequency=1,
            confidence=0.9,
            examples=[],
            first_seen="2025-01-01",
            last_seen="2025-01-01",
            status="pending"
        )]
        engine._save_pending_suggestions(suggestions)

        # Lock files should exist (they're created by filelock)
        # Note: filelock may clean up lock files after release
        # So we just verify the paths are correctly configured
        assert engine.pending_lock.name == ".pending_review.lock"
        assert engine.rejected_lock.name == ".rejected.lock"
        assert engine.auto_approved_lock.name == ".auto_approved.lock"

    def test_directory_creation_under_lock(self, engine):
        """Test that directory creation is safe under lock"""
        # Remove learned directory
        import shutil
        if engine.learned_dir.exists():
            shutil.rmtree(engine.learned_dir)

        # Recreate it concurrently (parent.mkdir in save methods)
        def save_concurrent():
            suggestions = [Suggestion(
                from_text="test",
                to_text="test",
                frequency=1,
                confidence=0.9,
                examples=[],
                first_seen="2025-01-01",
                last_seen="2025-01-01",
                status="pending"
            )]
            engine._save_pending_suggestions(suggestions)

        threads = []
        for _ in range(5):
            thread = threading.Thread(target=save_concurrent)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Directory should exist and contain data
        assert engine.learned_dir.exists()
        assert engine.pending_file.exists()


class TestLearningEngineCorrectness:
    """Test that file locking doesn't break functionality"""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for testing"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            history_dir = temp_path / "history"
            learned_dir = temp_path / "learned"
            history_dir.mkdir()
            learned_dir.mkdir()
            yield history_dir, learned_dir

    @pytest.fixture
    def engine(self, temp_dirs):
        """Create LearningEngine instance"""
        history_dir, learned_dir = temp_dirs
        return LearningEngine(history_dir, learned_dir)

    def test_save_and_load_pending(self, engine):
        """Test basic save and load functionality"""
        suggestions = [Suggestion(
            from_text="hello",
            to_text="你好",
            frequency=5,
            confidence=0.95,
            examples=[{"file": "test.md", "line": 1, "context": "test", "timestamp": "2025-01-01"}],
            first_seen="2025-01-01",
            last_seen="2025-01-02",
            status="pending"
        )]

        engine._save_pending_suggestions(suggestions)
        loaded = engine._load_pending_suggestions()

        assert len(loaded) == 1
        assert loaded[0]["from_text"] == "hello"
        assert loaded[0]["to_text"] == "你好"
        assert loaded[0]["confidence"] == 0.95

    def test_approve_removes_from_pending(self, engine):
        """Test that approval removes suggestion from pending"""
        suggestions = [Suggestion(
            from_text="test",
            to_text="测试",
            frequency=3,
            confidence=0.9,
            examples=[],
            first_seen="2025-01-01",
            last_seen="2025-01-01",
            status="pending"
        )]

        engine._save_pending_suggestions(suggestions)
        assert len(engine._load_pending_suggestions()) == 1

        result = engine.approve_suggestion("test")
        assert result is True
        assert len(engine._load_pending_suggestions()) == 0

    def test_reject_moves_to_rejected(self, engine):
        """Test that rejection moves suggestion to rejected list"""
        suggestions = [Suggestion(
            from_text="bad",
            to_text="wrong",
            frequency=1,
            confidence=0.8,
            examples=[],
            first_seen="2025-01-01",
            last_seen="2025-01-01",
            status="pending"
        )]

        engine._save_pending_suggestions(suggestions)
        engine.reject_suggestion("bad", "wrong")

        # Should be removed from pending
        pending = engine._load_pending_suggestions()
        assert len(pending) == 0

        # Should be added to rejected
        rejected = engine._load_rejected()
        assert ("bad", "wrong") in rejected


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
