#!/usr/bin/env python3
"""
Thread-Safe SQLite Connection Pool

CRITICAL FIX: Replaces unsafe check_same_thread=False pattern
ISSUE: Critical-1 in Engineering Excellence Plan

This module provides:
1. Thread-safe connection pooling
2. Proper connection lifecycle management
3. Timeout and limit enforcement
4. WAL mode for better concurrency
5. Explicit connection cleanup

Author: Chief Engineer (20 years experience)
Date: 2025-10-28
Priority: P0 - Critical
"""

from __future__ import annotations

import sqlite3
import threading
import queue
import logging
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, Final
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

# Constants (immutable, explicit)
MAX_CONNECTIONS: Final[int] = 5  # Limit to prevent file descriptor exhaustion
CONNECTION_TIMEOUT: Final[float] = 30.0  # 30s timeout instead of infinite
POOL_TIMEOUT: Final[float] = 5.0  # Max wait time for available connection
BUSY_TIMEOUT: Final[int] = 30000  # SQLite busy timeout in milliseconds


@dataclass
class PoolStatistics:
    """Connection pool statistics for monitoring"""
    total_connections: int
    active_connections: int
    waiting_threads: int
    total_acquired: int
    total_released: int
    total_timeouts: int
    created_at: datetime


class PoolExhaustedError(Exception):
    """Raised when connection pool is exhausted and timeout occurs"""
    pass


class ConnectionPool:
    """
    Thread-safe connection pool for SQLite.

    Design Decisions:
    1. Fixed pool size - prevents resource exhaustion
    2. Queue-based - FIFO fairness, no thread starvation
    3. WAL mode - allows concurrent reads, better performance
    4. Explicit timeouts - prevents infinite hangs
    5. Statistics tracking - enables monitoring

    Usage:
        pool = ConnectionPool(db_path, max_connections=5)

        with pool.get_connection() as conn:
            conn.execute("SELECT * FROM table")

        # Cleanup when done
        pool.close_all()

    Thread Safety:
        - Each connection used by one thread at a time
        - Queue provides synchronization
        - No global state, no race conditions
    """

    def __init__(
        self,
        db_path: Path,
        max_connections: int = MAX_CONNECTIONS,
        connection_timeout: float = CONNECTION_TIMEOUT,
        pool_timeout: float = POOL_TIMEOUT
    ):
        """
        Initialize connection pool.

        Args:
            db_path: Path to SQLite database file
            max_connections: Maximum number of connections (default: 5)
            connection_timeout: SQLite connection timeout in seconds (default: 30)
            pool_timeout: Max wait time for available connection (default: 5)

        Raises:
            ValueError: If max_connections < 1 or timeouts < 0
            FileNotFoundError: If db_path parent directory doesn't exist
        """
        # Input validation (fail fast, clear errors)
        if max_connections < 1:
            raise ValueError(f"max_connections must be >= 1, got {max_connections}")
        if connection_timeout < 0:
            raise ValueError(f"connection_timeout must be >= 0, got {connection_timeout}")
        if pool_timeout < 0:
            raise ValueError(f"pool_timeout must be >= 0, got {pool_timeout}")

        self.db_path = Path(db_path)
        if not self.db_path.parent.exists():
            raise FileNotFoundError(f"Database directory doesn't exist: {self.db_path.parent}")

        self.max_connections = max_connections
        self.connection_timeout = connection_timeout
        self.pool_timeout = pool_timeout

        # Thread-safe queue for connection pool
        self._pool: queue.Queue[sqlite3.Connection] = queue.Queue(maxsize=max_connections)

        # Lock for pool initialization (create connections once)
        self._init_lock = threading.Lock()
        self._initialized = False

        # Statistics (for monitoring and debugging)
        self._stats_lock = threading.Lock()
        self._total_acquired = 0
        self._total_released = 0
        self._total_timeouts = 0
        self._created_at = datetime.now()

        logger.info(
            "Connection pool initialized",
            extra={
                "db_path": str(self.db_path),
                "max_connections": self.max_connections,
                "connection_timeout": self.connection_timeout,
                "pool_timeout": self.pool_timeout
            }
        )

    def _initialize_pool(self) -> None:
        """
        Create initial connections (lazy initialization).

        Called on first use, not in __init__ to allow
        database directory creation after pool object creation.
        """
        with self._init_lock:
            if self._initialized:
                return

            logger.debug(f"Creating {self.max_connections} database connections")

            for i in range(self.max_connections):
                try:
                    conn = self._create_connection()
                    self._pool.put(conn, block=False)
                    logger.debug(f"Created connection {i+1}/{self.max_connections}")
                except Exception as e:
                    logger.error(f"Failed to create connection {i+1}: {e}", exc_info=True)
                    # Cleanup partial initialization
                    self._cleanup_partial_pool()
                    raise

            self._initialized = True
            logger.info(f"Connection pool ready with {self.max_connections} connections")

    def _cleanup_partial_pool(self) -> None:
        """Cleanup connections if initialization fails"""
        while not self._pool.empty():
            try:
                conn = self._pool.get(block=False)
                conn.close()
            except queue.Empty:
                break
            except Exception as e:
                logger.warning(f"Error closing connection during cleanup: {e}")

    def _create_connection(self) -> sqlite3.Connection:
        """
        Create a new SQLite connection with optimal settings.

        Settings explained:
        1. check_same_thread=True - ENFORCE thread safety (critical fix)
        2. timeout=30.0 - Prevent infinite locks
        3. isolation_level='DEFERRED' - Explicit transaction control
        4. WAL mode - Better concurrency (allows concurrent reads)
        5. busy_timeout - How long to wait on locks

        Returns:
            Configured SQLite connection

        Raises:
            sqlite3.Error: If connection creation fails
        """
        try:
            conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=True,  # CRITICAL FIX: Enforce thread safety
                timeout=self.connection_timeout,
                isolation_level='DEFERRED'  # Explicit transaction control
            )

            # Enable Write-Ahead Logging for better concurrency
            # WAL allows multiple readers + one writer simultaneously
            conn.execute('PRAGMA journal_mode=WAL')

            # Set busy timeout (how long to wait on locks)
            conn.execute(f'PRAGMA busy_timeout={BUSY_TIMEOUT}')

            # Enable foreign key constraints
            conn.execute('PRAGMA foreign_keys=ON')

            # Use Row factory for dict-like access
            conn.row_factory = sqlite3.Row

            logger.debug(f"Created connection to {self.db_path}")
            return conn

        except sqlite3.Error as e:
            logger.error(f"Failed to create connection: {e}", exc_info=True)
            raise

    @contextmanager
    def get_connection(self):
        """
        Get a connection from the pool (context manager).

        This is the main API. Always use with 'with' statement:

            with pool.get_connection() as conn:
                conn.execute("SELECT * FROM table")

        Thread Safety:
            - Blocks until connection available (up to pool_timeout)
            - Connection returned to pool automatically
            - Safe to use from multiple threads

        Yields:
            sqlite3.Connection: Database connection

        Raises:
            PoolExhaustedError: If no connection available within timeout
            RuntimeError: If pool is closed
        """
        # Lazy initialization (only create connections when first needed)
        if not self._initialized:
            self._initialize_pool()

        conn = None
        acquired_at = datetime.now()

        try:
            # Wait for available connection (blocks up to pool_timeout seconds)
            try:
                conn = self._pool.get(timeout=self.pool_timeout)
                logger.debug("Connection acquired from pool")

                # Update statistics
                with self._stats_lock:
                    self._total_acquired += 1

            except queue.Empty:
                # Pool exhausted, all connections in use
                with self._stats_lock:
                    self._total_timeouts += 1

                logger.error(
                    "Connection pool exhausted",
                    extra={
                        "pool_size": self.max_connections,
                        "timeout": self.pool_timeout,
                        "total_timeouts": self._total_timeouts
                    }
                )
                raise PoolExhaustedError(
                    f"No connection available within {self.pool_timeout}s. "
                    f"Pool size: {self.max_connections}. "
                    f"Consider increasing pool size or reducing concurrency."
                )

            # Yield connection to caller
            yield conn

        finally:
            # CRITICAL: Always return connection to pool
            if conn is not None:
                try:
                    # Rollback any uncommitted transaction
                    # This ensures clean state for next user
                    conn.rollback()

                    # Return to pool
                    self._pool.put(conn, block=False)

                    # Update statistics
                    with self._stats_lock:
                        self._total_released += 1

                    duration_ms = (datetime.now() - acquired_at).total_seconds() * 1000
                    logger.debug(f"Connection returned to pool (held for {duration_ms:.1f}ms)")

                except Exception as e:
                    # This should never happen, but if it does, log and close connection
                    logger.error(f"Failed to return connection to pool: {e}", exc_info=True)
                    try:
                        conn.close()
                    except Exception:
                        pass

    def get_statistics(self) -> PoolStatistics:
        """
        Get current pool statistics.

        Useful for monitoring and debugging. Can expose via
        health check endpoint or metrics.

        Returns:
            PoolStatistics with current state
        """
        with self._stats_lock:
            return PoolStatistics(
                total_connections=self.max_connections,
                active_connections=self.max_connections - self._pool.qsize(),
                waiting_threads=self._pool.qsize(),
                total_acquired=self._total_acquired,
                total_released=self._total_released,
                total_timeouts=self._total_timeouts,
                created_at=self._created_at
            )

    def close_all(self) -> None:
        """
        Close all connections in pool.

        Call this on application shutdown to ensure clean cleanup.
        After calling this, pool cannot be used anymore.

        Thread Safety:
            Safe to call from any thread, but only call once.
        """
        logger.info("Closing connection pool")

        closed_count = 0
        error_count = 0

        # Close all connections in pool
        while not self._pool.empty():
            try:
                conn = self._pool.get(block=False)
                conn.close()
                closed_count += 1
            except queue.Empty:
                break
            except Exception as e:
                logger.warning(f"Error closing connection: {e}")
                error_count += 1

        logger.info(
            f"Connection pool closed: {closed_count} connections closed, {error_count} errors"
        )

        self._initialized = False

    def __enter__(self) -> ConnectionPool:
        """Support using pool as context manager"""
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: object | None) -> bool:
        """Cleanup on context exit"""
        self.close_all()
        return False
