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

from typing import List, Tuple
import httpx

from .ai_utils import AIChange, AIAPIError, split_into_chunks, build_correction_prompt, parse_anthropic_response
from .defaults import (
    DEFAULT_MODEL,
    FALLBACK_MODEL,
    API_BASE_URL,
    AUTH_HEADER_NAME,
    ANTHROPIC_VERSION,
    API_TIMEOUT,
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
                 fallback_model: str = FALLBACK_MODEL):
        """
        Initialize AI processor

        Args:
            api_key: GLM API key
            model: Model name (default: GLM-5.2)
            base_url: API base URL
            fallback_model: Fallback model on primary failure
        """
        self.api_key = api_key
        self.model = model
        self.fallback_model = fallback_model
        self.base_url = base_url
        self.max_chunk_size = 6000  # Characters per chunk

    def process(self, text: str, context: str = "") -> Tuple[str, List[AIChange]]:
        """
        Process text with AI corrections

        Args:
            text: Text to correct
            context: Optional domain/meeting context

        Returns:
            (corrected_text, list_of_changes)
        """
        chunks = split_into_chunks(text, self.max_chunk_size)
        corrected_chunks = []
        all_changes = []

        print(f"📝 Processing {len(chunks)} chunks with {self.model}...")

        for i, chunk in enumerate(chunks, 1):
            print(f"   Chunk {i}/{len(chunks)}... ", end="", flush=True)

            try:
                corrected_chunk = self._process_chunk(chunk, context, self.model)
                corrected_chunks.append(corrected_chunk)

                # TODO: Extract actual changes for learning
                # For now, we assume the whole chunk changed
                if corrected_chunk != chunk:
                    all_changes.append(AIChange(
                        chunk_index=i,
                        from_text=chunk[:50] + "...",
                        to_text=corrected_chunk[:50] + "...",
                        confidence=0.9  # Placeholder
                    ))

                print("✓")

            except Exception as e:
                print(f"✗ {str(e)[:50]}")

                # Retry with fallback model
                if self.fallback_model and self.fallback_model != self.model:
                    print(f"   Retrying with {self.fallback_model}... ", end="", flush=True)
                    try:
                        corrected_chunk = self._process_chunk(chunk, context, self.fallback_model)
                        corrected_chunks.append(corrected_chunk)
                        print("✓")
                        continue
                    except Exception as e2:
                        print(f"✗ {str(e2)[:50]}")

                print("   Using original text...")
                corrected_chunks.append(chunk)

        return "\n\n".join(corrected_chunks), all_changes

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
