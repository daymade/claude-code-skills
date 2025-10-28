#!/usr/bin/env python3
"""
AI Processor - Stage 2: AI-powered Text Corrections

SINGLE RESPONSIBILITY: Process text using GLM API for intelligent corrections

Features:
- Split text into chunks for API processing
- Call GLM-4.6 for context-aware corrections
- Track AI-suggested changes
- Handle API errors gracefully
"""

from __future__ import annotations

import os
import re
from typing import List, Tuple
from dataclasses import dataclass
import httpx


@dataclass
class AIChange:
    """Represents an AI-suggested change"""
    chunk_index: int
    from_text: str
    to_text: str
    confidence: float  # 0.0 to 1.0


class AIProcessor:
    """
    Stage 2 Processor: AI-powered corrections using GLM-4.6

    Process:
    1. Split text into chunks (respecting API limits)
    2. Send each chunk to GLM API
    3. Track changes for learning engine
    4. Preserve formatting and structure
    """

    def __init__(self, api_key: str, model: str = "GLM-4.6",
                 base_url: str = "https://open.bigmodel.cn/api/anthropic",
                 fallback_model: str = "GLM-4.5-Air"):
        """
        Initialize AI processor

        Args:
            api_key: GLM API key
            model: Model name (default: GLM-4.6)
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
        chunks = self._split_into_chunks(text)
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

    def _split_into_chunks(self, text: str) -> List[str]:
        """
        Split text into processable chunks

        Strategy:
        - Split by double newlines (paragraphs)
        - Keep chunks under max_chunk_size
        - Don't split mid-paragraph if possible
        """
        paragraphs = text.split('\n\n')
        chunks = []
        current_chunk = []
        current_length = 0

        for para in paragraphs:
            para_length = len(para)

            # If single paragraph exceeds limit, force split
            if para_length > self.max_chunk_size:
                if current_chunk:
                    chunks.append('\n\n'.join(current_chunk))
                    current_chunk = []
                    current_length = 0

                # Split long paragraph by sentences
                sentences = re.split(r'([。！？\n])', para)
                temp_para = ""
                for i in range(0, len(sentences), 2):
                    sentence = sentences[i] + (sentences[i+1] if i+1 < len(sentences) else "")
                    if len(temp_para) + len(sentence) > self.max_chunk_size:
                        if temp_para:
                            chunks.append(temp_para)
                        temp_para = sentence
                    else:
                        temp_para += sentence
                if temp_para:
                    chunks.append(temp_para)

            # Normal case: accumulate paragraphs
            elif current_length + para_length > self.max_chunk_size and current_chunk:
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = [para]
                current_length = para_length
            else:
                current_chunk.append(para)
                current_length += para_length + 2  # +2 for \n\n

        if current_chunk:
            chunks.append('\n\n'.join(current_chunk))

        return chunks

    def _process_chunk(self, chunk: str, context: str, model: str) -> str:
        """Process a single chunk with GLM API"""
        prompt = self._build_prompt(chunk, context)

        url = f"{self.base_url}/v1/messages"
        headers = {
            "anthropic-version": "2023-06-01",
            "Authorization": f"Bearer {self.api_key}",
            "content-type": "application/json"
        }

        data = {
            "model": model,
            "max_tokens": 8000,
            "temperature": 0.3,
            "messages": [{"role": "user", "content": prompt}]
        }

        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()
            return result["content"][0]["text"]

    def _build_prompt(self, chunk: str, context: str) -> str:
        """Build correction prompt for GLM"""
        base_prompt = """你是专业的会议记录校对专家。请修复以下会议转录中的语音识别错误。

**修复原则**：
1. 严格保留原有格式（时间戳、发言人标识、Markdown标记等）
2. 修复明显的同音字错误
3. 修复专业术语错误
4. 修复语法错误，但保持口语化特征
5. 不确定的地方保持原样，不要过度修改

"""

        if context:
            base_prompt += f"\n**会议背景**：\n{context}\n"

        base_prompt += f"""
**需要修复的内容**：
{chunk}

**请直接输出修复后的文本，不要添加任何解释或标注**："""

        return base_prompt
