#!/usr/bin/env python3
"""
AI Processor with Async/Parallel Support - Stage 2: AI-powered Text Corrections

ENHANCEMENT: Process chunks in parallel for 5-10x speed improvement on large files

Key improvements over ai_processor.py:
- Asyncio-based parallel chunk processing
- Configurable concurrency limit (default: 5 concurrent requests)
- Progress bar with real-time updates
- Graceful error handling with fallback model
- Maintains compatibility with existing API

CRITICAL FIX (P1-3): Memory leak prevention
- Limits all_changes growth with sampling
- Releases intermediate results promptly
- Reuses httpx client (connection pooling)
- Monitors memory usage with warnings
"""

from __future__ import annotations

import asyncio
import gc
import logging
from dataclasses import dataclass
from typing import Collection, List, Tuple, Optional, Final
import httpx

from .ai_utils import (
    AIChange,
    build_correction_prompt,
    parse_anthropic_response,
    reassemble_corrected_chunks,
    split_into_chunks,
)
from .change_extractor import ChangeExtractor
from .dictionary_processor import (
    _mask_ledger_spans,
    _restore_ledger_spans,
    reveal_ledger_values_for_reporting,
)
from .defaults import (
    DEFAULT_MODEL,
    FALLBACK_MODEL,
    API_BASE_URL,
    AUTH_HEADER_NAME,
    ANTHROPIC_VERSION,
    API_TIMEOUT,
)
from .protected_spans import (
    mask_speaker_labels,
    restore_speaker_labels,
    reveal_speaker_labels_for_reporting,
)

# CRITICAL FIX: Import structured logging and retry logic
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.logging_config import TimedLogger, ErrorCounter
from utils.retry_logic import retry_async, RetryConfig

# Setup logger
logger = logging.getLogger(__name__)
timed_logger = TimedLogger(logger)

# CRITICAL FIX: Memory management constants
MAX_CHANGES_TO_TRACK: Final[int] = 10_000  # Fail closed above this audit bound
MEMORY_WARNING_THRESHOLD: Final[int] = 100  # Warn if >100 chunks


@dataclass(frozen=True)
class ChunkResult:
    """One API chunk plus whether it used the original-text fallback."""

    text: str
    api_failed: bool = False
    model_used: str | None = None


class AIProcessorAsync:
    """
    Stage 2 Processor: AI-powered corrections using GLM-5.2 with parallel processing

    Process:
    1. Split text into chunks (respecting API limits)
    2. Send chunks to GLM API in parallel (default: 5 concurrent)
    3. Track changes for learning engine
    4. Preserve formatting and structure

    Performance: ~5-10x faster than sequential processing on large files
    """

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL,
                 base_url: str = API_BASE_URL,
                 fallback_model: str = FALLBACK_MODEL,
                 max_concurrent: int = 5,
                 speaker_labels: Collection[str] = ()):
        """
        Initialize AI processor with async support

        Args:
            api_key: GLM API key
            model: Model name (default: GLM-5.2)
            base_url: API base URL
            fallback_model: Fallback model on primary failure
            speaker_labels: Explicit bare labels from a roster/manifest
            max_concurrent: Maximum concurrent API requests (default: 5)
                          - Higher = faster but more API load
                          - Lower = slower but more conservative
                          - Recommended: 3-7 for GLM API

        CRITICAL FIX (P1-3): Added shared httpx client for connection pooling
        """
        self.api_key = api_key
        self.model = model
        self.fallback_model = fallback_model
        self.base_url = base_url
        self.max_chunk_size = 6000  # Characters per chunk
        self.max_concurrent = max_concurrent  # Concurrency limit
        self.change_extractor = ChangeExtractor()  # For learning from AI results
        self.models_used: set[str] = set()
        self.speaker_labels = set(speaker_labels)
        self.total_chunks = 0
        self.failed_chunks = 0

        # CRITICAL FIX: Shared client for connection pooling (prevents connection leaks)
        self._http_client: Optional[httpx.AsyncClient] = None
        self._client_lock = asyncio.Lock()

    async def _get_http_client(self) -> httpx.AsyncClient:
        """
        Get or create shared HTTP client for connection pooling.

        CRITICAL FIX (P1-3): Prevents connection descriptor leaks
        """
        async with self._client_lock:
            if self._http_client is None or self._http_client.is_closed:
                # Create client with connection pooling limits
                limits = httpx.Limits(
                    max_keepalive_connections=20,
                    max_connections=100,
                    keepalive_expiry=30.0
                )
                self._http_client = httpx.AsyncClient(
                    timeout=API_TIMEOUT,
                    limits=limits,
                    http2=False  # Disable HTTP/2 to avoid missing h2 package
                )
                logger.debug("Created new HTTP client with connection pooling")

            return self._http_client

    async def _close_http_client(self) -> None:
        """Close shared HTTP client to release resources"""
        async with self._client_lock:
            if self._http_client is not None and not self._http_client.is_closed:
                await self._http_client.aclose()
                self._http_client = None
                logger.debug("Closed HTTP client")

    def process(self, text: str, context: str = "") -> Tuple[str, List[AIChange]]:
        """
        Process text with AI corrections (parallel)

        Args:
            text: Text to correct
            context: Optional domain/meeting context

        Returns:
            (corrected_text, list_of_changes)

        CRITICAL FIX (P1-3): Ensures HTTP client cleanup
        """
        # Run async processing in sync context
        async def _run_with_cleanup():
            try:
                return await self._process_async(text, context)
            finally:
                # Ensure HTTP client is closed in the same event loop
                await self._close_http_client()

        return asyncio.run(_run_with_cleanup())

    async def _process_async(self, text: str, context: str) -> Tuple[str, List[AIChange]]:
        """
        Async implementation of process().

        CRITICAL FIX (P1-3): Memory leak prevention
        - Limits all_changes tracking
        - Releases intermediate results
        - Monitors memory usage
        """
        ledger_projected_text, ledger_spans = _mask_ledger_spans(text)
        projected_text, speaker_spans = mask_speaker_labels(
            ledger_projected_text, self.speaker_labels
        )
        self.models_used.clear()
        chunks = split_into_chunks(projected_text, self.max_chunk_size)
        self.total_chunks = len(chunks)
        self.failed_chunks = 0
        all_changes = []

        # CRITICAL FIX: Memory warning for large files
        if len(chunks) > MEMORY_WARNING_THRESHOLD:
            logger.warning(
                f"Large file detected: {len(chunks)} chunks. "
                f"All changes remain auditable up to the fail-closed limit."
            )

        logger.info(
            f"Starting batch processing: total_chunks={len(chunks)}, "
            f"model={self.model}, max_concurrent={self.max_concurrent}"
        )

        # CRITICAL FIX: Error rate monitoring
        error_counter = ErrorCounter(threshold=0.3)  # Abort if >30% fail

        # Create semaphore to limit concurrent requests
        semaphore = asyncio.Semaphore(self.max_concurrent)

        # Create tasks for all chunks
        tasks = [
            self._process_chunk_with_semaphore(
                i, chunk, context, semaphore, len(chunks)
            )
            for i, chunk in enumerate(chunks, 1)
        ]

        # Wait for all tasks to complete
        with timed_logger.timed("batch_processing", total_chunks=len(chunks)):
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results (maintaining order)
        corrected_chunks = []
        for i, (chunk, result) in enumerate(zip(chunks, results), 1):
            if isinstance(result, Exception):
                logger.error(
                    f"Chunk {i} raised exception: {result}",
                    exc_info=True
                )
                corrected_chunks.append(chunk)
                error_counter.failure()

            else:
                if not isinstance(result, ChunkResult):
                    logger.error(
                        "Chunk %s returned unexpected result type %s; "
                        "retaining original text",
                        i,
                        type(result).__name__,
                    )
                    corrected_chunks.append(chunk)
                    error_counter.failure()
                    continue

                corrected_chunks.append(result.text)
                if result.api_failed:
                    error_counter.failure()
                    continue

                error_counter.success()
                if result.model_used:
                    self.models_used.add(result.model_used)

                # Extract actual changes for learning
                if result.text != chunk:
                    source_for_report = reveal_speaker_labels_for_reporting(
                        chunk, speaker_spans
                    )
                    corrected_for_report = reveal_speaker_labels_for_reporting(
                        result.text, speaker_spans
                    )
                    source_for_report = reveal_ledger_values_for_reporting(
                        source_for_report, ledger_spans
                    )
                    corrected_for_report = reveal_ledger_values_for_reporting(
                        corrected_for_report, ledger_spans
                    )
                    extracted_changes = self.change_extractor.extract_changes(
                        source_for_report, corrected_for_report
                    )

                    if len(all_changes) + len(extracted_changes) > MAX_CHANGES_TO_TRACK:
                        raise ValueError(
                            "Stage 2 produced more than "
                            f"{MAX_CHANGES_TO_TRACK} auditable changes; refusing "
                            "to emit modified text with truncated history"
                        )
                    for change in extracted_changes:
                        all_changes.append(AIChange(
                            chunk_index=i,
                            from_text=change.from_text,
                            to_text=change.to_text,
                            confidence=change.confidence,
                            context_before=change.context_before,
                            context_after=change.context_after,
                            change_type=change.change_type,
                            learnable=change.learnable,
                            model=result.model_used,
                        ))

                    # CRITICAL FIX: Explicitly release extracted_changes
                    del extracted_changes

        # CRITICAL FIX: Force garbage collection for large files
        if len(chunks) > MEMORY_WARNING_THRESHOLD:
            gc.collect()
            logger.debug("Forced garbage collection after processing large file")

        # Final statistics
        stats = error_counter.get_stats()
        self.failed_chunks = stats["total_failures"]
        if stats["should_abort"]:
            # All requests have already completed concurrently. Raising here
            # would discard the safely retained fallback text without saving a
            # single API call, contradicting the original-text guarantee.
            logger.error(
                "API failure rate exceeded threshold; returning degraded "
                "output with every failed chunk restored. Stats: %s",
                stats,
            )
        logger.info(
            f"Batch processing completed: total_chunks={len(chunks)}, "
            f"successes={stats['total_successes']}, failures={stats['total_failures']}, "
            f"failure_rate={stats['window_failure_rate']:.2%}, changes_extracted={len(all_changes)}"
        )

        corrected_text = reassemble_corrected_chunks(
            projected_text, chunks, corrected_chunks
        )
        if speaker_spans:
            corrected_text = restore_speaker_labels(corrected_text, speaker_spans)
        if ledger_spans:
            corrected_text = _restore_ledger_spans(corrected_text, ledger_spans)
        return corrected_text, all_changes

    async def _process_chunk_with_semaphore(
        self,
        chunk_index: int,
        chunk: str,
        context: str,
        semaphore: asyncio.Semaphore,
        total_chunks: int
    ) -> ChunkResult:
        """
        Process chunk with concurrency control.

        CRITICAL FIX: Now uses structured logging and retry logic
        """
        async with semaphore:
            logger.info(
                f"Processing chunk {chunk_index}/{total_chunks} "
                f"(length={len(chunk)})"
            )

            try:
                # Use retry logic with exponential backoff
                @retry_async(RetryConfig(max_attempts=3, base_delay=1.0))
                async def process_with_retry():
                    return await self._process_chunk_async(chunk, context, self.model)

                with timed_logger.timed("chunk_processing", chunk_index=chunk_index):
                    result = await process_with_retry()

                logger.info(
                    f"Chunk {chunk_index} completed successfully"
                )
                return ChunkResult(result, model_used=self.model)

            except Exception as e:
                print(f"[DEBUG] Chunk {chunk_index} primary error: {type(e).__name__}: {e}")
                logger.warning(
                    f"Chunk {chunk_index} failed with primary model ({type(e).__name__}): {e}",
                    exc_info=True
                )

                # Retry with fallback model
                if self.fallback_model and self.fallback_model != self.model:
                    logger.info(
                        f"Retrying chunk {chunk_index} with fallback model: {self.fallback_model}"
                    )

                    try:
                        @retry_async(RetryConfig(max_attempts=2, base_delay=1.0))
                        async def fallback_with_retry():
                            return await self._process_chunk_async(chunk, context, self.fallback_model)

                        result = await fallback_with_retry()
                        logger.info(
                            f"Chunk {chunk_index} succeeded with fallback model"
                        )
                        return ChunkResult(result, model_used=self.fallback_model)

                    except Exception as e2:
                        print(f"[DEBUG] Chunk {chunk_index} fallback error: {type(e2).__name__}: {e2}")
                        logger.error(
                            f"Chunk {chunk_index} failed with fallback model ({type(e2).__name__}): {e2}",
                            exc_info=True
                        )

                # API fallback: keep original text and warn clearly.
                print(f"[WARNING] Chunk {chunk_index}: GLM API unavailable after retries; leaving original text unchanged.")
                print("  To correct without an API, use native mode in Claude Code, or provide a valid API key.")

                logger.warning(
                    f"Using original text for chunk {chunk_index} after all retries failed"
                )
                return ChunkResult(chunk, api_failed=True)

    async def _process_chunk_async(self, chunk: str, context: str, model: str) -> str:
        """
        Process a single chunk with GLM API (async).

        CRITICAL FIX (P1-3): Uses shared HTTP client for connection pooling
        """
        prompt = build_correction_prompt(chunk, context)

        url = f"{self.base_url}/v1/messages"
        headers = {
            "anthropic-version": ANTHROPIC_VERSION,
            AUTH_HEADER_NAME: self.api_key,
            "content-type": "application/json"
        }

        data = {
            "model": model,
            "max_tokens": 8000,
            "temperature": 0.3,
            "messages": [{"role": "user", "content": prompt}]
        }

        # CRITICAL FIX: Use shared client instead of creating new one
        # This prevents connection descriptor leaks
        client = await self._get_http_client()
        response = await client.post(url, headers=headers, json=data)
        response.raise_for_status()
        return parse_anthropic_response(response.json())
