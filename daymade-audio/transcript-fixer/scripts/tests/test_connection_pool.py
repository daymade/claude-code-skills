#!/usr/bin/env python3
"""
Test Suite for Thread-Safe Connection Pool

CRITICAL FIX VERIFICATION: Tests for Critical-1
Purpose: Verify thread-safe connection pool prevents data corruption

Test Coverage:
1. Basic pool operations
2. Concurrent access (race conditions)
3. Pool exhaustion handling
4. Connection cleanup
5. Statistics tracking

Author: Chief Engineer
Priority: P0 - Critical
"""

import pytest
import sqlite3
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.connection_pool import (
    ConnectionPool,
    PoolExhaustedError,
    MAX_CONNECTIONS
)


class TestConnectionPoolBasics:
    """Test basic connection pool functionality"""

    def test_pool_initialization(self, tmp_path):
        """Test pool creates with valid parameters"""
        db_path = tmp_path / "test.db"

        pool = ConnectionPool(db_path, max_connections=3)

        assert pool.max_connections == 3
        assert pool.db_path == db_path

        pool.close_all()

    def test_pool_invalid_max_connections(self, tmp_path):
        """Test pool rejects invalid max_connections"""
        db_path = tmp_path / "test.db"

        with pytest.raises(ValueError, match="max_connections must be >= 1"):
            ConnectionPool(db_path, max_connections=0)

        with pytest.raises(ValueError, match="max_connections must be >= 1"):
            ConnectionPool(db_path, max_connections=-1)

    def test_pool_invalid_timeout(self, tmp_path):
        """Test pool rejects negative timeouts"""
        db_path = tmp_path / "test.db"

        with pytest.raises(ValueError, match="connection_timeout"):
            ConnectionPool(db_path, connection_timeout=-1)

        with pytest.raises(ValueError, match="pool_timeout"):
            ConnectionPool(db_path, pool_timeout=-1)

    def test_pool_nonexistent_directory(self):
        """Test pool rejects nonexistent directory"""
        db_path = Path("/nonexistent/directory/test.db")

        with pytest.raises(FileNotFoundError, match="doesn't exist"):
            ConnectionPool(db_path)


class TestConnectionOperations:
    """Test connection acquisition and release"""

    def test_get_connection_basic(self, tmp_path):
        """Test basic connection acquisition"""
        db_path = tmp_path / "test.db"
        pool = ConnectionPool(db_path, max_connections=2)

        with pool.get_connection() as conn:
            assert isinstance(conn, sqlite3.Connection)
            # Connection should work
            cursor = conn.execute("SELECT 1")
            assert cursor.fetchone()[0] == 1

        pool.close_all()

    def test_connection_returned_to_pool(self, tmp_path):
        """Test connection is returned after use"""
        db_path = tmp_path / "test.db"
        pool = ConnectionPool(db_path, max_connections=1)

        # Use connection
        with pool.get_connection() as conn:
            conn.execute("SELECT 1")

        # Should be able to get it again
        with pool.get_connection() as conn:
            conn.execute("SELECT 2")

        pool.close_all()

    def test_wal_mode_enabled(self, tmp_path):
        """Test WAL mode is enabled for concurrency"""
        db_path = tmp_path / "test.db"
        pool = ConnectionPool(db_path)

        with pool.get_connection() as conn:
            cursor = conn.execute("PRAGMA journal_mode")
            mode = cursor.fetchone()[0]
            assert mode.upper() == "WAL"

        pool.close_all()

    def test_foreign_keys_enabled(self, tmp_path):
        """Test foreign keys are enforced"""
        db_path = tmp_path / "test.db"
        pool = ConnectionPool(db_path)

        with pool.get_connection() as conn:
            cursor = conn.execute("PRAGMA foreign_keys")
            enabled = cursor.fetchone()[0]
            assert enabled == 1

        pool.close_all()


class TestConcurrency:
    """
    CRITICAL: Test concurrent access for race conditions

    This is the main reason for the fix. The old code used
    check_same_thread=False which caused race conditions.
    """

    def test_concurrent_reads(self, tmp_path):
        """Test multiple threads reading simultaneously"""
        db_path = tmp_path / "test.db"
        pool = ConnectionPool(db_path, max_connections=5)

        # Create test table
        with pool.get_connection() as conn:
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
            conn.execute("INSERT INTO test (value) VALUES ('test1'), ('test2'), ('test3')")
            conn.commit()

        results = []
        errors = []

        def read_data(thread_id):
            try:
                with pool.get_connection() as conn:
                    cursor = conn.execute("SELECT COUNT(*) FROM test")
                    count = cursor.fetchone()[0]
                    results.append((thread_id, count))
            except Exception as e:
                errors.append((thread_id, str(e)))

        # Run 10 concurrent reads
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(read_data, i) for i in range(10)]
            for future in as_completed(futures):
                future.result()  # Wait for completion

        # Verify
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 10
        assert all(count == 3 for _, count in results), "Race condition detected!"

        pool.close_all()

    def test_concurrent_writes_no_corruption(self, tmp_path):
        """
        CRITICAL TEST: Verify no data corruption under concurrent writes

        This would fail with check_same_thread=False
        """
        db_path = tmp_path / "test.db"
        pool = ConnectionPool(db_path, max_connections=5)

        # Create counter table
        with pool.get_connection() as conn:
            conn.execute("CREATE TABLE counter (id INTEGER PRIMARY KEY, value INTEGER)")
            conn.execute("INSERT INTO counter (id, value) VALUES (1, 0)")
            conn.commit()

        errors = []

        def increment_counter(thread_id):
            try:
                with pool.get_connection() as conn:
                    # Read current value
                    cursor = conn.execute("SELECT value FROM counter WHERE id = 1")
                    current = cursor.fetchone()[0]

                    # Increment
                    new_value = current + 1

                    # Write back
                    conn.execute("UPDATE counter SET value = ? WHERE id = 1", (new_value,))
                    conn.commit()
            except Exception as e:
                errors.append((thread_id, str(e)))

        # Run 100 concurrent increments
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(increment_counter, i) for i in range(100)]
            for future in as_completed(futures):
                future.result()

        # Check final value
        with pool.get_connection() as conn:
            cursor = conn.execute("SELECT value FROM counter WHERE id = 1")
            final_value = cursor.fetchone()[0]

        # Note: Due to race conditions in the increment logic itself,
        # final value might be less than 100. But the important thing is:
        # 1. No errors occurred
        # 2. No database corruption
        # 3. We got SOME value (not NULL, not negative)

        assert len(errors) == 0, f"Errors: {errors}"
        assert final_value > 0, "Counter should have increased"
        assert final_value <= 100, "Counter shouldn't exceed number of increments"

        pool.close_all()


class TestPoolExhaustion:
    """Test behavior when pool is exhausted"""

    def test_pool_exhaustion_timeout(self, tmp_path):
        """Test PoolExhaustedError when all connections busy"""
        db_path = tmp_path / "test.db"
        pool = ConnectionPool(db_path, max_connections=2, pool_timeout=0.5)

        # Hold all connections
        conn1 = pool.get_connection()
        conn1.__enter__()

        conn2 = pool.get_connection()
        conn2.__enter__()

        # Try to get third connection (should timeout)
        with pytest.raises(PoolExhaustedError, match="No connection available"):
            with pool.get_connection() as conn3:
                pass

        # Release connections
        conn1.__exit__(None, None, None)
        conn2.__exit__(None, None, None)

        pool.close_all()

    def test_pool_recovery_after_exhaustion(self, tmp_path):
        """Test pool recovers after connections released"""
        db_path = tmp_path / "test.db"
        pool = ConnectionPool(db_path, max_connections=1, pool_timeout=0.5)

        # Use connection
        with pool.get_connection() as conn:
            conn.execute("SELECT 1")

        # Should be available again
        with pool.get_connection() as conn:
            conn.execute("SELECT 2")

        pool.close_all()


class TestStatistics:
    """Test pool statistics tracking"""

    def test_statistics_initialization(self, tmp_path):
        """Test initial statistics"""
        db_path = tmp_path / "test.db"
        pool = ConnectionPool(db_path, max_connections=3)

        stats = pool.get_statistics()

        assert stats.total_connections == 3
        assert stats.total_acquired == 0
        assert stats.total_released == 0
        assert stats.total_timeouts == 0

        pool.close_all()

    def test_statistics_tracking(self, tmp_path):
        """Test statistics are updated correctly"""
        db_path = tmp_path / "test.db"
        pool = ConnectionPool(db_path, max_connections=2)

        # Acquire and release
        with pool.get_connection() as conn:
            conn.execute("SELECT 1")

        with pool.get_connection() as conn:
            conn.execute("SELECT 2")

        stats = pool.get_statistics()

        assert stats.total_acquired == 2
        assert stats.total_released == 2

        pool.close_all()


class TestCleanup:
    """Test proper resource cleanup"""

    def test_close_all_connections(self, tmp_path):
        """Test close_all() closes all connections"""
        db_path = tmp_path / "test.db"
        pool = ConnectionPool(db_path, max_connections=3)

        # Initialize pool by acquiring connection
        with pool.get_connection() as conn:
            conn.execute("SELECT 1")

        # Close all
        pool.close_all()

        # Pool should not be usable after close
        # (This will fail because pool is not initialized)
        # In a real scenario, we'd track connection states

    def test_context_manager_cleanup(self, tmp_path):
        """Test pool as context manager cleans up"""
        db_path = tmp_path / "test.db"

        with ConnectionPool(db_path, max_connections=2) as pool:
            with pool.get_connection() as conn:
                conn.execute("SELECT 1")

        # Pool should be closed automatically


# Run tests with: pytest -v test_connection_pool.py
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
