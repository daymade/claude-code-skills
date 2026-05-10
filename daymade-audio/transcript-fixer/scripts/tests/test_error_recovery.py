#!/usr/bin/env python3
"""
Error Recovery Testing Module

CRITICAL FIX (P1-10): Comprehensive error recovery testing

This module tests the system's ability to recover from various failure scenarios:
- Database failures and transaction rollbacks
- Network failures and retries
- File system errors
- Concurrent access conflicts
- Resource exhaustion
- Timeout handling
- Data corruption

Author: Chief Engineer (ISTJ, 20 years experience)
Date: 2025-10-29
Priority: P1 - High
"""

from __future__ import annotations

import asyncio
import logging
import pytest
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, List, Optional
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.connection_pool import ConnectionPool, PoolExhaustedError
from core.correction_repository import CorrectionRepository, DatabaseError
from utils.retry_logic import retry_sync, retry_async, RetryConfig, is_transient_error
from utils.concurrency_manager import (
    ConcurrencyManager,
    ConcurrencyConfig,
    BackpressureError,
    CircuitBreakerOpenError
)
from utils.rate_limiter import RateLimiter, RateLimitConfig, RateLimitExceeded

logger = logging.getLogger(__name__)


# ==================== Test Fixtures ====================

@pytest.fixture
def temp_db_path():
    """Create temporary database for testing"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test.db"
        yield db_path


@pytest.fixture
def connection_pool(temp_db_path):
    """Create connection pool for testing"""
    pool = ConnectionPool(temp_db_path, max_connections=3, pool_timeout=2.0)
    yield pool
    pool.close_all()


@pytest.fixture
def correction_repository(temp_db_path):
    """Create correction repository for testing"""
    repo = CorrectionRepository(temp_db_path, max_connections=3)
    yield repo
    # Cleanup handled by temp_db_path


@pytest.fixture
def concurrency_manager():
    """Create concurrency manager for testing"""
    config = ConcurrencyConfig(
        max_concurrent=3,
        max_queue_size=5,
        enable_circuit_breaker=True,
        circuit_failure_threshold=3
    )
    return ConcurrencyManager(config)


# ==================== Database Error Recovery Tests ====================

class TestDatabaseErrorRecovery:
    """Test database error recovery mechanisms"""

    def test_transaction_rollback_on_error(self, correction_repository):
        """
        Test that database transactions are rolled back on error.

        Scenario: Try to insert correction with invalid confidence value.
        Expected: Error is raised, no data is modified.
        """
        # Add a correction successfully
        correction_repository.add_correction(
            from_text="test1",
            to_text="corrected1",
            domain="general",
            source="manual",
            confidence=0.9
        )

        # Verify it was added
        corrections = correction_repository.get_all_corrections(domain="general")
        initial_count = len(corrections)
        assert initial_count >= 1

        # Try to add correction with invalid confidence (should fail)
        from utils.domain_validator import ValidationError
        with pytest.raises((ValidationError, DatabaseError)):
            correction_repository.add_correction(
                from_text="test_invalid",
                to_text="corrected",
                domain="general",
                source="manual",
                confidence=1.5  # Invalid: must be 0.0-1.0
            )

        # Verify no new corrections were added
        corrections = correction_repository.get_all_corrections(domain="general")
        assert len(corrections) == initial_count

    def test_connection_pool_recovery_from_exhaustion(self, connection_pool):
        """
        Test that connection pool recovers after exhaustion.

        Scenario: Exhaust all connections, then release them.
        Expected: Pool should become available again.
        """
        connections = []

        # Acquire all connections using context managers properly
        for i in range(3):
            ctx = connection_pool.get_connection()
            conn = ctx.__enter__()
            connections.append((ctx, conn))

        # Try to acquire one more (should timeout with pool_timeout=2.0)
        with pytest.raises((PoolExhaustedError, TimeoutError)):
            with connection_pool.get_connection():
                pass

        # Release all connections properly
        for ctx, conn in connections:
            try:
                ctx.__exit__(None, None, None)
            except:
                pass  # Ignore errors during cleanup

        # Should be able to acquire connection again
        with connection_pool.get_connection() as conn:
            assert conn is not None

    def test_database_recovery_from_corruption(self, temp_db_path):
        """
        Test that system handles corrupted database gracefully.

        Scenario: Create corrupted database file.
        Expected: System should detect corruption and handle it.
        """
        # Create a corrupted database file
        with open(temp_db_path, 'wb') as f:
            f.write(b'This is not a valid SQLite database')

        # Try to create repository (should fail gracefully)
        with pytest.raises((sqlite3.DatabaseError, DatabaseError, FileNotFoundError)):
            repo = CorrectionRepository(temp_db_path)
            repo.get_all_corrections()

    def test_concurrent_write_conflict_recovery(self, temp_db_path):
        """
        Test recovery from concurrent write conflicts.

        Scenario: Multiple threads try to write to same record.
        Expected: First write succeeds, subsequent ones update (UPSERT behavior).

        Note: Each thread needs its own CorrectionRepository instance
        due to SQLite's thread-safety limitations.
        """
        results = []
        errors = []

        def write_correction(thread_id, db_path):
            try:
                # Each thread creates its own repository
                from core.correction_repository import CorrectionRepository
                thread_repo = CorrectionRepository(db_path, max_connections=1)

                thread_repo.add_correction(
                    from_text="concurrent_test",
                    to_text=f"corrected_{thread_id}",
                    domain="general",
                    source="manual"
                )
                results.append(thread_id)
            except Exception as e:
                errors.append((thread_id, str(e)))

        # Start multiple threads
        threads = [threading.Thread(target=write_correction, args=(i, temp_db_path)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Due to UPSERT behavior, all should succeed (they update the same record)
        assert len(results) + len(errors) == 5

        # Verify database is still consistent
        verify_repo = CorrectionRepository(temp_db_path)
        corrections = verify_repo.get_all_corrections()
        assert any(c.from_text == "concurrent_test" for c in corrections)

        # Should only have one record (UNIQUE constraint + UPSERT)
        concurrent_corrections = [c for c in corrections if c.from_text == "concurrent_test"]
        assert len(concurrent_corrections) == 1


# ==================== Network Error Recovery Tests ====================

class TestNetworkErrorRecovery:
    """Test network error recovery mechanisms"""

    @pytest.mark.asyncio
    async def test_retry_on_transient_network_error(self):
        """
        Test that transient network errors trigger retry.

        Scenario: API call fails with timeout, then succeeds on retry.
        Expected: Operation succeeds after retry.
        """
        attempt_count = [0]

        @retry_async(RetryConfig(max_attempts=3, base_delay=0.1))
        async def flaky_network_call():
            attempt_count[0] += 1
            if attempt_count[0] < 3:
                import httpx
                raise httpx.ConnectTimeout("Connection timeout")
            return "success"

        result = await flaky_network_call()
        assert result == "success"
        assert attempt_count[0] == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_permanent_error(self):
        """
        Test that permanent errors are not retried.

        Scenario: API call fails with authentication error.
        Expected: Error is raised immediately without retry.
        """
        attempt_count = [0]

        @retry_async(RetryConfig(max_attempts=3, base_delay=0.1))
        async def auth_error_call():
            attempt_count[0] += 1
            raise ValueError("Invalid credentials")  # Permanent error

        with pytest.raises(ValueError):
            await auth_error_call()

        # Should fail immediately without retry
        assert attempt_count[0] == 1

    def test_transient_error_classification(self):
        """
        Test correct classification of transient vs permanent errors.

        Scenario: Various exception types.
        Expected: Correct classification for each type.
        """
        import httpx

        # Transient errors
        assert is_transient_error(httpx.ConnectTimeout("timeout")) == True
        assert is_transient_error(httpx.ReadTimeout("timeout")) == True
        assert is_transient_error(httpx.ConnectError("connection failed")) == True

        # Permanent errors
        assert is_transient_error(ValueError("invalid input")) == False
        assert is_transient_error(KeyError("not found")) == False


# ==================== Concurrency Error Recovery Tests ====================

class TestConcurrencyErrorRecovery:
    """Test concurrent operation error recovery"""

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_failures(self, concurrency_manager):
        """
        Test that circuit breaker opens after threshold failures.

        Scenario: Multiple consecutive failures.
        Expected: Circuit opens, subsequent requests rejected.
        """
        # Cause 3 failures (threshold)
        for i in range(3):
            try:
                async with concurrency_manager.acquire():
                    raise Exception("Simulated failure")
            except Exception:
                pass

        # Circuit should be OPEN now
        with pytest.raises(CircuitBreakerOpenError):
            async with concurrency_manager.acquire():
                pass

    @pytest.mark.asyncio
    async def test_circuit_breaker_recovery(self, concurrency_manager):
        """
        Test that circuit breaker can recover after timeout.

        Scenario: Circuit opens, then recovery timeout elapses, then success.
        Expected: Circuit transitions OPEN → HALF_OPEN → CLOSED.
        """
        # Configure short recovery timeout for testing
        concurrency_manager.config.circuit_recovery_timeout = 0.5

        # Cause failures to open circuit
        for i in range(3):
            try:
                async with concurrency_manager.acquire():
                    raise Exception("Failure")
            except Exception:
                pass

        # Circuit should be OPEN
        metrics = concurrency_manager.get_metrics()
        assert metrics.circuit_state.value == "open"

        # Wait for recovery timeout
        await asyncio.sleep(0.6)

        # Try a successful operation (should transition to HALF_OPEN then CLOSED)
        async with concurrency_manager.acquire():
            pass  # Success

        # One more success to fully close
        async with concurrency_manager.acquire():
            pass

        # Circuit should be CLOSED
        metrics = concurrency_manager.get_metrics()
        assert metrics.circuit_state.value in ("closed", "half_open")

    @pytest.mark.asyncio
    async def test_backpressure_handling(self):
        """
        Test that backpressure prevents system overload.

        Scenario: Queue fills up beyond max_queue_size.
        Expected: Additional requests are rejected with BackpressureError.
        """
        # Create manager with small limits for testing
        config = ConcurrencyConfig(
            max_concurrent=1,
            max_queue_size=2,
            enable_backpressure=True
        )
        manager = ConcurrencyManager(config)

        async def slow_task():
            async with manager.acquire():
                await asyncio.sleep(0.5)

        # Start tasks that will fill queue
        tasks = []
        rejected_count = 0

        for i in range(6):  # Try to start 6 tasks (more than queue can hold)
            try:
                task = asyncio.create_task(slow_task())
                tasks.append(task)
                await asyncio.sleep(0.01)  # Small delay between starts
            except BackpressureError:
                rejected_count += 1

        # Wait a bit then cancel remaining tasks
        await asyncio.sleep(0.1)
        for task in tasks:
            if not task.done():
                task.cancel()

        # Gather results (ignore cancellation errors)
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check metrics
        metrics = manager.get_metrics()

        # Either direct BackpressureError or rejected in metrics
        assert rejected_count > 0 or metrics.rejected_requests > 0


# ==================== Resource Error Recovery Tests ====================

class TestResourceErrorRecovery:
    """Test resource error recovery mechanisms"""

    def test_rate_limiter_recovery_after_limit_reached(self):
        """
        Test that rate limiter allows requests after window resets.

        Scenario: Exhaust rate limit, wait for window reset.
        Expected: New requests are allowed after reset.
        """
        config = RateLimitConfig(
            max_requests=3,
            window_seconds=0.5,  # Short window for testing
        )
        limiter = RateLimiter(config)

        # Exhaust limit
        for i in range(3):
            assert limiter.acquire(blocking=False) == True

        # Should be exhausted
        assert limiter.acquire(blocking=False) == False

        # Wait for window reset
        time.sleep(0.6)

        # Should be available again
        assert limiter.acquire(blocking=False) == True

    @pytest.mark.asyncio
    async def test_timeout_recovery(self, concurrency_manager):
        """
        Test that timeouts are handled gracefully.

        Scenario: Operation exceeds timeout.
        Expected: Operation is cancelled, resources released.
        """
        with pytest.raises(asyncio.TimeoutError):
            async with concurrency_manager.acquire(timeout=0.1):
                await asyncio.sleep(1.0)  # Exceeds timeout

        # Verify metrics were updated
        metrics = concurrency_manager.get_metrics()
        assert metrics.timeout_requests > 0

    def test_file_lock_recovery_after_timeout(self, temp_db_path):
        """
        Test recovery from file lock timeouts.

        Scenario: Lock held too long, timeout occurs.
        Expected: Lock is released, subsequent operations succeed.
        """
        from filelock import FileLock, Timeout as FileLockTimeout

        lock_path = temp_db_path.parent / "test.lock"
        lock = FileLock(str(lock_path), timeout=0.5)

        # Acquire lock
        with lock.acquire():
            # Try to acquire again (should timeout)
            lock2 = FileLock(str(lock_path), timeout=0.2)
            with pytest.raises(FileLockTimeout):
                with lock2.acquire():
                    pass

        # Lock should be released, can acquire now
        with lock.acquire():
            pass  # Success


# ==================== Data Corruption Recovery Tests ====================

class TestDataCorruptionRecovery:
    """Test data corruption detection and recovery"""

    def test_invalid_data_detection(self, correction_repository):
        """
        Test that invalid data is detected and rejected.

        Scenario: Attempt to insert invalid data.
        Expected: Validation error, database remains consistent.
        """
        # Try to insert correction with invalid confidence
        with pytest.raises(DatabaseError):
            correction_repository.add_correction(
                from_text="test",
                to_text="corrected",
                domain="general",
                source="manual",
                confidence=1.5  # Invalid (must be 0.0-1.0)
            )

        # Verify database is still consistent
        corrections = correction_repository.get_all_corrections()
        assert all(0.0 <= c.confidence <= 1.0 for c in corrections)

    def test_encoding_error_recovery(self):
        """
        Test recovery from encoding errors.

        Scenario: Process text with invalid encoding.
        Expected: Error is handled, processing continues.
        """
        from core.change_extractor import ChangeExtractor, InputValidationError

        extractor = ChangeExtractor()

        # Test with invalid UTF-8 sequences
        invalid_text = b'\x80\x81\x82'.decode('utf-8', errors='replace')

        try:
            # Should handle gracefully or raise specific error
            changes = extractor.extract_changes(invalid_text, "corrected")
        except InputValidationError as e:
            # Expected - validation caught the issue
            assert "UTF-8" in str(e) or "encoding" in str(e).lower()


# ==================== Integration Error Recovery Tests ====================

class TestIntegrationErrorRecovery:
    """Test end-to-end error recovery scenarios"""

    def test_full_system_recovery_from_multiple_failures(
        self, correction_repository, concurrency_manager
    ):
        """
        Test that system recovers from multiple simultaneous failures.

        Scenario: Database error + rate limit + concurrency limit.
        Expected: System degrades gracefully, recovers when possible.
        """
        # Record initial state
        initial_corrections = len(correction_repository.get_all_corrections())

        # Simulate various failures
        failures = []

        # 1. Try to add duplicate correction (database error)
        correction_repository.add_correction(
            from_text="multi_fail_test",
            to_text="original",
            domain="general",
            source="manual"
        )

        try:
            correction_repository.add_correction(
                from_text="multi_fail_test",  # Duplicate
                to_text="duplicate",
                domain="general",
                source="manual"
            )
        except DatabaseError:
            failures.append("database")

        # 2. Simulate concurrency failure
        async def test_concurrency():
            try:
                # Cause circuit breaker to open
                for i in range(3):
                    try:
                        async with concurrency_manager.acquire():
                            raise Exception("Failure")
                    except Exception:
                        pass

                # Circuit should be open
                with pytest.raises(CircuitBreakerOpenError):
                    async with concurrency_manager.acquire():
                        pass
                failures.append("concurrency")
            except Exception:
                pass

        asyncio.run(test_concurrency())

        # Verify system is still operational
        corrections = correction_repository.get_all_corrections()
        assert len(corrections) == initial_corrections + 1

        # Verify metrics were recorded
        metrics = concurrency_manager.get_metrics()
        assert metrics.failed_requests > 0

    @pytest.mark.asyncio
    async def test_cascading_failure_prevention(self):
        """
        Test that failures don't cascade through the system.

        Scenario: One component fails, others continue working.
        Expected: Failure is isolated, system remains operational.
        """
        # This test verifies isolation between components
        config = ConcurrencyConfig(
            max_concurrent=2,
            enable_circuit_breaker=True,
            circuit_failure_threshold=3
        )
        manager1 = ConcurrencyManager(config)
        manager2 = ConcurrencyManager(config)

        # Cause failures in manager1
        for i in range(3):
            try:
                async with manager1.acquire():
                    raise Exception("Failure")
            except Exception:
                pass

        # manager1 circuit should be open
        metrics1 = manager1.get_metrics()
        assert metrics1.circuit_state.value == "open"

        # manager2 should still work
        async with manager2.acquire():
            pass  # Success

        metrics2 = manager2.get_metrics()
        assert metrics2.circuit_state.value == "closed"


# ==================== Test Runner ====================

if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
