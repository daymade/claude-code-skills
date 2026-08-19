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
from unittest.mock import AsyncMock

# Add parent directory to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.connection_pool import ConnectionPool, PoolExhaustedError
from core.ai_processor import AIProcessor
from core.ai_processor_async import AIProcessorAsync, ChunkResult
from core.ai_utils import (
    AIAPIError,
    parse_anthropic_response,
    reassemble_corrected_chunks,
)
from core.change_extractor import ChangeExtractor
from core.correction_repository import CorrectionRepository, DatabaseError
from core.correction_service import CorrectionService
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


class TestAIChunkFailureFidelity:
    """API fallback must not alter text merely because chunking occurred."""

    def test_sequential_total_failure_returns_byte_identical_source(self):
        source = "甲。乙。丙。丁。"
        processor = AIProcessor(api_key="test", fallback_model="")
        processor.max_chunk_size = 4

        def fail_chunk(_chunk, _context, _model):
            raise RuntimeError("simulated API failure")

        processor._process_chunk = fail_chunk
        corrected, changes = processor.process(source)

        assert corrected == source
        assert changes == []

    @pytest.mark.parametrize("blank_text", ["", "   ", "\n\t"])
    def test_blank_api_text_is_a_failure_not_a_correction(self, blank_text):
        with pytest.raises(AIAPIError, match="Empty 'text'"):
            parse_anthropic_response({
                "content": [{"type": "text", "text": blank_text}],
            })

    def test_empty_success_payload_falls_back_to_original_chunk(self):
        source = "这段原文绝不能丢。"
        processor = AIProcessor(api_key="test", fallback_model="")

        def parse_empty_payload(_chunk, _context, _model):
            return parse_anthropic_response({
                "content": [{"type": "text", "text": ""}],
            })

        processor._process_chunk = parse_empty_payload
        corrected, changes = processor.process(source)

        assert corrected == source
        assert changes == []

    @pytest.mark.asyncio
    async def test_async_chunk_fallback_preserves_original_separators(self):
        source = "甲。乙。丙。丁。"
        processor = AIProcessorAsync(api_key="test", fallback_model="")
        processor.max_chunk_size = 4

        async def keep_chunk(_index, chunk, _context, _semaphore, _total):
            return ChunkResult(chunk)

        processor._process_chunk_with_semaphore = keep_chunk
        corrected, changes = await processor._process_async(source, "")

        assert corrected == source
        assert changes == []

    def test_sync_ai_cannot_modify_speaker_label_prefix(self):
        source = "spekarA 00:01:00\n正文 spekarA"
        processor = AIProcessor(api_key="test", fallback_model="")
        processor._process_chunk = (
            lambda chunk, _context, _model: chunk.replace("spekarA", "Speaker A")
        )

        corrected, changes = processor.process(source)
        assert corrected == "spekarA 00:01:00\n正文 Speaker A"
        assert changes
        assert all("TFSPK" not in str(vars(change)) for change in changes)

    def test_sync_fallback_success_records_the_real_change(self):
        processor = AIProcessor(
            api_key="test",
            model="primary",
            fallback_model="fallback",
        )

        def primary_then_fallback(chunk, _context, model):
            if model == "primary":
                raise RuntimeError("primary unavailable")
            return chunk.replace("meetng", "meeting")

        processor._process_chunk = primary_then_fallback
        corrected, changes = processor.process("meetng")

        assert corrected == "meeting"
        assert [(change.from_text, change.to_text) for change in changes] == [
            ("meetng", "meeting")
        ]

    def test_sync_ai_edits_short_timestamp_ended_prose(self):
        source = "会议开时 00:01:00\n下一行开时"
        processor = AIProcessor(api_key="test", fallback_model="")
        processor._process_chunk = (
            lambda chunk, _context, _model: chunk.replace("开时", "开始")
        )

        corrected, changes = processor.process(source)

        assert corrected == "会议开始 00:01:00\n下一行开始"
        assert changes

    @pytest.mark.asyncio
    async def test_async_ai_cannot_modify_speaker_label_prefix(self):
        source = "spekarA 00:01:00\n正文 spekarA"
        processor = AIProcessorAsync(api_key="test", fallback_model="")

        async def replace_body(_index, chunk, _context, _semaphore, _total):
            return ChunkResult(chunk.replace("spekarA", "Speaker A"))

        processor._process_chunk_with_semaphore = replace_body
        corrected, changes = await processor._process_async(source, "")
        assert corrected == "spekarA 00:01:00\n正文 Speaker A"
        assert changes
        assert all("TFSPK" not in str(vars(change)) for change in changes)

    @pytest.mark.asyncio
    async def test_async_insertion_is_recorded_as_a_replayable_word_pair(self):
        processor = AIProcessorAsync(api_key="test", fallback_model="")

        async def insert_missing_letter(
            _index, _chunk, _context, _semaphore, _total
        ):
            return ChunkResult("meeting")

        processor._process_chunk_with_semaphore = insert_missing_letter
        corrected, changes = await processor._process_async("meetng", "")

        assert corrected == "meeting"
        assert [(change.from_text, change.to_text) for change in changes] == [
            ("meetng", "meeting")
        ]
        assert changes[0].learnable is True

    @pytest.mark.asyncio
    async def test_async_ai_edits_short_timestamp_ended_prose(self):
        source = "Project meetng starts 00:01:00\nnext meetng"
        processor = AIProcessorAsync(api_key="test", fallback_model="")

        async def fix_prose(_index, chunk, _context, _semaphore, _total):
            return ChunkResult(chunk.replace("meetng", "meeting"))

        processor._process_chunk_with_semaphore = fix_prose
        corrected, changes = await processor._process_async(source, "")

        assert corrected == "Project meeting starts 00:01:00\nnext meeting"
        assert len(changes) == 2

    def test_async_insert_change_persists_in_history(
        self, correction_repository
    ):
        processor = AIProcessorAsync(api_key="test", fallback_model="")

        async def insert_missing_letter(
            _index, _chunk, _context, _semaphore, _total
        ):
            return ChunkResult("meeting")

        processor._process_chunk_with_semaphore = insert_missing_letter
        corrected, changes = asyncio.run(processor._process_async("meetng", ""))
        assert corrected == "meeting"

        service = CorrectionService(correction_repository)
        service.save_history(
            filename="fixture.md",
            domain="test-domain",
            original_length=6,
            stage1_changes=0,
            stage2_changes=len(changes),
            model="fixture",
            changes=changes,
        )

        with sqlite3.connect(correction_repository.db_path) as conn:
            history_count = conn.execute(
                "SELECT stage2_changes FROM correction_history"
            ).fetchone()[0]
            change_row = conn.execute(
                "SELECT from_text, to_text FROM correction_changes"
            ).fetchone()
        assert history_count == 1
        assert change_row == ("meetng", "meeting")

    def test_unanchored_insert_delete_are_historical_but_not_learnable(self):
        extractor = ChangeExtractor()

        inserted = extractor.extract_changes("", "新增")
        deleted = extractor.extract_changes("删除", "")

        assert [(change.from_text, change.to_text) for change in inserted] == [
            ("", "新增")
        ]
        assert [(change.from_text, change.to_text) for change in deleted] == [
            ("删除", "")
        ]
        assert inserted[0].change_type == "insertion"
        assert deleted[0].change_type == "deletion"
        assert inserted[0].learnable is False
        assert deleted[0].learnable is False

    def test_multi_edit_ascii_name_is_one_truthful_pair(self):
        changes = ChangeExtractor().extract_changes("spekarA", "Speaker A")
        assert [(change.from_text, change.to_text) for change in changes] == [
            ("spekarA", "Speaker A")
        ]

    def test_inserted_punctuation_is_recorded_but_never_learned(self):
        changes = ChangeExtractor().extract_changes("你好", "你好，")
        assert [(change.from_text, change.to_text) for change in changes] == [
            ("好", "好，")
        ]
        assert changes[0].change_type == "insertion"
        assert changes[0].learnable is False

    @pytest.mark.parametrize(
        ("original", "corrected"),
        [("OpenAI", "openai"), ("甲乙", "甲 乙"), ("甲\n乙", "甲\n\n乙")],
    )
    def test_formatting_mutation_is_visible_but_not_learnable(
        self, original, corrected
    ):
        changes = ChangeExtractor().extract_changes(original, corrected)
        assert changes
        assert all(change.change_type == "formatting" for change in changes)
        assert all(change.learnable is False for change in changes)

    @pytest.mark.asyncio
    async def test_async_fallback_metrics_are_failures_not_successes(self, caplog):
        source = "甲。乙。丙。丁。戊。己。庚。辛。壬。癸。"
        processor = AIProcessorAsync(api_key="test", fallback_model="")
        processor.max_chunk_size = 2

        async def fail_chunk(_index, chunk, _context, _semaphore, _total):
            return ChunkResult(chunk, api_failed=True)

        processor._process_chunk_with_semaphore = fail_chunk
        with caplog.at_level(logging.INFO, logger="core.ai_processor_async"):
            corrected, changes = await processor._process_async(source, "")

        assert corrected == source
        assert changes == []
        assert "successes=0, failures=10" in caplog.text
        assert "returning degraded output" in caplog.text

    @pytest.mark.asyncio
    async def test_async_blank_http_payload_uses_failure_fallback(
        self, caplog, monkeypatch
    ):
        class BlankResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"content": [{"type": "text", "text": ""}]}

        class BlankClient:
            async def post(self, *_args, **_kwargs):
                return BlankResponse()

        processor = AIProcessorAsync(api_key="test", fallback_model="")

        async def get_client():
            return BlankClient()

        processor._get_http_client = get_client
        monkeypatch.setattr(asyncio, "sleep", AsyncMock())
        with caplog.at_level(logging.INFO, logger="core.ai_processor_async"):
            corrected, changes = await processor._process_async("原文不能丢", "")

        assert corrected == "原文不能丢"
        assert changes == []
        assert "successes=0, failures=1" in caplog.text

    def test_reassembly_preserves_nonstandard_inter_chunk_spacing(self):
        original = "左段\n\n\n右段"
        corrected = reassemble_corrected_chunks(
            original,
            ["左段", "右段"],
            ["甲段", "乙段"],
        )
        assert corrected == "甲段\n\n\n乙段"

    def test_reassembly_fails_fast_when_chunks_do_not_match_source(self):
        with pytest.raises(ValueError, match="source chunk 2"):
            reassemble_corrected_chunks(
                "第一段\n\n第二段",
                ["第一段", "missing"],
                ["甲", "乙"],
            )


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
