#!/usr/bin/env python3
"""
Tech Domain Preset Corrections

Pre-seeded ASR correction rules for AI / Claude Code / software engineering transcripts.
Each entry includes confidence (lower for context-dependent or phonetic matches).

Use load_tech_presets() to get a list of (from_text, to_text, confidence, notes) tuples.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True)
class PresetRule:
    from_text: str
    to_text: str
    confidence: float
    notes: str


TECH_PRESETS: List[PresetRule] = [
    # --- Claude / Anthropic ecosystem ---
    PresetRule("克劳锐", "Claude", 0.95, "Phonetic mishearing of Claude"),
    PresetRule("科劳德", "Claude", 0.95, "Phonetic mishearing of Claude"),
    PresetRule("克劳德", "Claude", 0.95, "Phonetic mishearing of Claude"),
    PresetRule("cloud code", "Claude Code", 0.95, "ASR split of Claude Code"),
    PresetRule("cloucode", "Claude Code", 0.95, "ASR merge of Claude Code"),
    PresetRule("cloudcode", "Claude Code", 0.95, "ASR merge of Claude Code"),
    PresetRule("color code", "Claude Code", 0.85, "Phonetic mishearing of Claude Code"),
    PresetRule("call code", "Claude Code", 0.85, "Phonetic mishearing of Claude Code"),
    PresetRule("Xcode", "Claude Code", 0.70, "ASR mishearing in Claude Code context (use with review)"),
    PresetRule("cloud agent SDK", "Claude Agent SDK", 0.90, "ASR mishearing of Claude Agent SDK"),
    PresetRule("Opaas", "Opus", 0.90, "ASR mishearing of Opus"),
    PresetRule("opaas", "Opus", 0.90, "ASR mishearing of Opus"),

    # --- Claude Code specific features ---
    PresetRule("Ultra code", "ultracode", 0.95, "ASR split of ultracode trigger word"),
    PresetRule("ultra code", "ultracode", 0.95, "ASR split of ultracode trigger word"),
    PresetRule("爱马仕 agent", "Hermes Agent", 0.95, "Chinese nickname + English"),
    PresetRule("爱马仕 Agent", "Hermes Agent", 0.95, "Chinese nickname + English"),
    PresetRule("Dynamic workflow", "Dynamic Workflow", 0.90, "Capitalization normalization"),
    PresetRule("dynamic workflow", "Dynamic Workflow", 0.75, "Possible ASR or lowercase reference"),
    PresetRule("Agent Team", "Agent Team", 0.90, "Already correct, included for normalization"),

    # --- Common English-in-Chinese ASR errors ---
    PresetRule("APR", "Agent", 0.75, "'a peer' misheard as APR; context-dependent"),
    PresetRule("AP 撇儿", "Agent Team", 0.85, "'peer' misheard as AP-pier; context-dependent"),
    PresetRule("infite", "/insights", 0.85, "Claude Code /insights command misheard"),
    PresetRule("web coding", "Vibe Coding", 0.85, "Phonetic mishearing of Vibe Coding"),
    PresetRule("Web coding", "Vibe Coding", 0.85, "Phonetic mishearing of Vibe Coding"),

    # --- Git / GitHub ---
    PresetRule("get Hub", "GitHub", 0.95, "ASR split of GitHub"),
    PresetRule("Git Hub", "GitHub", 0.95, "ASR split of GitHub"),
    PresetRule("Git hub", "GitHub", 0.90, "ASR split of GitHub"),

    # --- LLM / AI concepts ---
    PresetRule("RAG", "RAG", 0.90, "Already correct"),
    PresetRule("大模型", "大模型", 0.90, "Already correct"),
    PresetRule("提示词", "提示词", 0.90, "Already correct"),
    PresetRule("上下文", "上下文", 0.90, "Already correct"),

    # --- macOS / system ---
    PresetRule("MISOS", "macOS", 0.95, "ASR mishearing of macOS"),
    PresetRule("FIBO", "Fable", 0.85, "ASR mishearing of Fable"),
]


def load_tech_presets() -> List[Tuple[str, str, float, str]]:
    """Return preset rules as tuples for easy importing."""
    return [(r.from_text, r.to_text, r.confidence, r.notes) for r in TECH_PRESETS]


def get_preset_names() -> List[str]:
    """Return list of available preset domain names."""
    return ["tech"]


def get_preset_rules(domain: str) -> List[Tuple[str, str, float, str]]:
    """Get preset rules for a named domain."""
    if domain.lower() == "tech":
        return load_tech_presets()
    raise ValueError(f"Unknown preset domain: {domain}. Available: {get_preset_names()}")
