#!/usr/bin/env python3
"""
AI Processor - Stage 2: AI-powered Text Corrections

SINGLE RESPONSIBILITY: Process text using GLM API for intelligent corrections

Features:
- Split text into chunks for API processing
- Call GLM-5.2 / GLM-5-turbo for context-aware corrections
- Track AI-suggested changes
- Handle API errors gracefully
"""

from __future__ import annotations

from typing import Collection, List, Tuple
import httpx

from .ai_utils import (
    AIChange,
    build_correction_prompt,
    parse_anthropic_response,
    reassemble_corrected_chunks,
    split_into_chunks,
)
from .defaults import (
    DEFAULT_MODEL,
    FALLBACK_MODEL,
    API_BASE_URL,
    AUTH_HEADER_NAME,
    ANTHROPIC_VERSION,
    API_TIMEOUT,
)
from .change_extractor import ChangeExtractor
from .dictionary_processor import (
    _mask_ledger_spans,
    _restore_ledger_spans,
    reveal_ledger_values_for_reporting,
)
from .protected_spans import (
    mask_speaker_labels,
    restore_speaker_labels,
    reveal_speaker_labels_for_reporting,
)


class AIProcessor:
    """
    Stage 2 Processor: AI-powered corrections using GLM-5.2

    Process:
    1. Split text into chunks (respecting API limits)
    2. Send each chunk to GLM API
    3. Track changes for learning engine
    4. Preserve formatting and structure
    """

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL,
                 base_url: str = API_BASE_URL,
                 fallback_model: str = FALLBACK_MODEL,
                 speaker_labels: Collection[str] = ()):
        """
        Initialize AI processor

        Args:
            api_key: GLM API key
            model: Model name (default: GLM-5.2)
            base_url: API base URL
            fallback_model: Fallback model on primary failure
            speaker_labels: Explicit bare labels from a roster/manifest
        """
        self.api_key = api_key
        self.model = model
        self.fallback_model = fallback_model
        self.base_url = base_url
        self.max_chunk_size = 6000  # Characters per chunk
        self.change_extractor = ChangeExtractor()
        self.models_used: set[str] = set()
        self.speaker_labels = set(speaker_labels)
        self.total_chunks = 0
        self.failed_chunks = 0

    def process(self, text: str, context: str = "") -> Tuple[str, List[AIChange]]:
        """
        Process text with AI corrections

        Args:
            text: Text to correct
            context: Optional domain/meeting context

        Returns:
            (corrected_text, list_of_changes)
        """
        ledger_projected_text, ledger_spans = _mask_ledger_spans(text)
        projected_text, speaker_spans = mask_speaker_labels(
            ledger_projected_text, self.speaker_labels
        )
        self.models_used.clear()
        chunks = split_into_chunks(projected_text, self.max_chunk_size)
        self.total_chunks = len(chunks)
        self.failed_chunks = 0
        corrected_chunks = []
        all_changes = []

        print(f"📝 Processing {len(chunks)} chunks with {self.model}...")

        for i, chunk in enumerate(chunks, 1):
            print(f"   Chunk {i}/{len(chunks)}... ", end="", flush=True)
            corrected_chunk = chunk
            api_succeeded = False
            model_used: str | None = None

            try:
                corrected_chunk = self._process_chunk(chunk, context, self.model)
                api_succeeded = True
                model_used = self.model
                self.models_used.add(self.model)
                print("✓")

            except Exception as e:
                print(f"✗ {str(e)[:50]}")

                # Retry with fallback model
                if self.fallback_model and self.fallback_model != self.model:
                    print(f"   Retrying with {self.fallback_model}... ", end="", flush=True)
                    try:
                        corrected_chunk = self._process_chunk(chunk, context, self.fallback_model)
                        api_succeeded = True
                        model_used = self.fallback_model
                        self.models_used.add(self.fallback_model)
                        print("✓")
                    except Exception as e2:
                        print(f"✗ {str(e2)[:50]}")

                if not api_succeeded:
                    print("   Using original text...")
                    self.failed_chunks += 1

            corrected_chunks.append(corrected_chunk)
            if api_succeeded and corrected_chunk != chunk:
                source_for_report = reveal_speaker_labels_for_reporting(
                    chunk, speaker_spans
                )
                corrected_for_report = reveal_speaker_labels_for_reporting(
                    corrected_chunk, speaker_spans
                )
                source_for_report = reveal_ledger_values_for_reporting(
                    source_for_report, ledger_spans
                )
                corrected_for_report = reveal_ledger_values_for_reporting(
                    corrected_for_report, ledger_spans
                )
                for change in self.change_extractor.extract_changes(
                    source_for_report, corrected_for_report
                ):
                    all_changes.append(AIChange(
                        chunk_index=i,
                        from_text=change.from_text,
                        to_text=change.to_text,
                        confidence=change.confidence,
                        context_before=change.context_before,
                        context_after=change.context_after,
                        change_type=change.change_type,
                        learnable=change.learnable,
                        model=model_used,
                    ))

        corrected_text = reassemble_corrected_chunks(
            projected_text, chunks, corrected_chunks
        )
        if speaker_spans:
            corrected_text = restore_speaker_labels(corrected_text, speaker_spans)
        if ledger_spans:
            corrected_text = _restore_ledger_spans(corrected_text, ledger_spans)
        return corrected_text, all_changes

    def _process_chunk(self, chunk: str, context: str, model: str) -> str:
        """Process a single chunk with GLM API"""
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

        with httpx.Client(timeout=API_TIMEOUT, http2=False) as client:
            response = client.post(url, headers=headers, json=data)
            response.raise_for_status()
            return parse_anthropic_response(response.json())
