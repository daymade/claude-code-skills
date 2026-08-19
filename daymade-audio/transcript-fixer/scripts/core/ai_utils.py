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
from typing import Any, List, Sequence

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
    # History must record every real edit, including an unanchored insertion or
    # deletion. Learning may only consume replayable non-empty FROM→TO pairs.
    learnable: bool = True
    # The model that actually emitted this edit. This can differ from the
    # configured primary when a fallback model succeeds.
    model: str | None = None


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
                # An unpunctuated run can itself exceed the limit. Slice it
                # deterministically instead of emitting one oversized request.
                pieces = [
                    sentence[start:start + max_chunk_size]
                    for start in range(0, len(sentence), max_chunk_size)
                ] or [""]
                for piece in pieces:
                    if len(temp_para) + len(piece) > max_chunk_size:
                        if temp_para:
                            chunks.append(temp_para)
                        temp_para = piece
                    else:
                        temp_para += piece
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


def reassemble_corrected_chunks(
    original_text: str,
    source_chunks: Sequence[str],
    corrected_chunks: Sequence[str],
) -> str:
    """Reassemble corrected chunks using the original text's exact separators.

    ``split_into_chunks`` omits the separators between chunks. Joining with a
    hard-coded delimiter therefore changes the source whenever a long paragraph
    is split by sentence, including the failure path where every chunk falls
    back to its original text. Locate each source chunk in order and carry the
    untouched text between chunks forward verbatim.

    Raises:
        ValueError: If the result list does not correspond to the source chunks,
            or if a source chunk cannot be anchored in the original text.
    """
    if len(source_chunks) != len(corrected_chunks):
        raise ValueError(
            "Cannot reassemble AI output: source/corrected chunk counts differ "
            f"({len(source_chunks)} != {len(corrected_chunks)})"
        )

    cursor = 0
    reassembled: list[str] = []
    for index, (source_chunk, corrected_chunk) in enumerate(
        zip(source_chunks, corrected_chunks),
        start=1,
    ):
        start = original_text.find(source_chunk, cursor)
        if start == -1:
            raise ValueError(
                "Cannot reassemble AI output: "
                f"source chunk {index} is not present after offset {cursor}"
            )
        reassembled.append(original_text[cursor:start])
        reassembled.append(corrected_chunk)
        cursor = start + len(source_chunk)

    reassembled.append(original_text[cursor:])
    return "".join(reassembled)


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

    stop_reason = response.get("stop_reason")
    if "stop_reason" in response and stop_reason != "end_turn":
        raise AIAPIError(
            "Incomplete API response: "
            f"stop_reason={stop_reason!r}; refusing truncated/refused output"
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

    text_parts: list[str] = []
    for index, block in enumerate(content):
        if not isinstance(block, dict):
            raise AIAPIError(
                "Unexpected content block type at index "
                f"{index}: {type(block).__name__}"
            )
        if block.get("type") not in (None, "text"):
            raise AIAPIError(
                "Unexpected non-text content block at index "
                f"{index}: type={block.get('type')!r}"
            )
        if "text" not in block:
            raise AIAPIError(
                "Missing 'text' in content block at index "
                f"{index}. Keys: {sorted(block.keys())}"
            )
        block_text = block["text"]
        if not isinstance(block_text, str):
            raise AIAPIError(
                "Unexpected text type at index "
                f"{index}: {type(block_text).__name__}"
            )
        text_parts.append(block_text)

    text = "".join(text_parts)
    if not text.strip():
        raise AIAPIError(
            "Empty 'text' in API response; refusing to treat a blank payload "
            "as a correction"
        )

    return text
