#!/usr/bin/env python3
"""
Shared AI Correction Utilities

Single source of truth for components used by both sync and async AI processors:
- AIChange dataclass
- Text chunking strategy
- Correction prompt construction
- Anthropic-compatible response parsing
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, List

from .defaults import MAX_CHUNK_SIZE as DEFAULT_MAX_CHUNK_SIZE


class AIAPIError(Exception):
    """Raised when the AI API returns an unexpected or malformed response"""
    pass


@dataclass
class AIChange:
    """Represents an AI-suggested change"""
    chunk_index: int
    from_text: str
    to_text: str
    confidence: float  # 0.0 to 1.0
    context_before: str = ""
    context_after: str = ""
    change_type: str = "unknown"


def split_into_chunks(text: str, max_chunk_size: int = DEFAULT_MAX_CHUNK_SIZE) -> List[str]:
    """
    Split text into processable chunks.

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

        # If single paragraph exceeds limit, force split by sentences
        if para_length > max_chunk_size:
            if current_chunk:
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = []
                current_length = 0

            sentences = re.split(r'([。！？\n])', para)
            temp_para = ""
            for i in range(0, len(sentences), 2):
                sentence = sentences[i] + (sentences[i + 1] if i + 1 < len(sentences) else "")
                if len(temp_para) + len(sentence) > max_chunk_size:
                    if temp_para:
                        chunks.append(temp_para)
                    temp_para = sentence
                else:
                    temp_para += sentence
            if temp_para:
                chunks.append(temp_para)

        # Normal case: accumulate paragraphs
        elif current_length + para_length > max_chunk_size and current_chunk:
            chunks.append('\n\n'.join(current_chunk))
            current_chunk = [para]
            current_length = para_length
        else:
            current_chunk.append(para)
            current_length += para_length + 2  # +2 for \n\n

    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))

    return chunks


def build_correction_prompt(chunk: str, context: str = "") -> str:
    """Build correction prompt for GLM / Anthropic-compatible endpoints."""
    base_prompt = """你是专业的会议记录校对专家。请修复以下会议转录中的语音识别错误。

**修复原则**：
1. 严格保留原有格式（时间戳、发言人标识、Markdown标记等）
2. 修复明显的同音字错误
3. 修复专业术语错误
4. 修复标点符号错误
5. 不改变语句含义和结构
6. 不确定的地方保持原样，不要过度修改

**不要做**：
- 不要添加或删除内容
- 不要重新组织段落
- 不要改变发言人标识
- 不要修改时间戳

直接输出修复后的文本，不要解释。
"""

    if context:
        base_prompt += f"\n\n**领域上下文**：{context}\n"

    return base_prompt + f"\n\n{chunk}"


def parse_anthropic_response(response: Any) -> str:
    """
    Safely extract the corrected text from an Anthropic-style response.

    Raises:
        AIAPIError: If the response structure is unexpected or missing text.
    """
    if not isinstance(response, dict):
        raise AIAPIError(
            f"Unexpected API response type: {type(response).__name__}"
        )

    if "content" not in response:
        raise AIAPIError(
            f"Missing 'content' in API response. Keys: {sorted(response.keys())}"
        )

    content = response["content"]
    if not isinstance(content, list) or len(content) == 0:
        raise AIAPIError(
            f"Invalid API response 'content': expected non-empty list, got {type(content).__name__}"
        )

    first_block = content[0]
    if not isinstance(first_block, dict):
        raise AIAPIError(
            f"Unexpected content block type: {type(first_block).__name__}"
        )

    if "text" not in first_block:
        raise AIAPIError(
            f"Missing 'text' in content block. Keys: {sorted(first_block.keys())}"
        )

    text = first_block["text"]
    if not isinstance(text, str):
        raise AIAPIError(
            f"Unexpected text type: {type(text).__name__}"
        )

    return text
