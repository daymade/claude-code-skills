#!/usr/bin/env python3
"""
Default constants - single source of truth for values that can drift.

This module intentionally has no dependencies on other project modules.
Any runtime default, provider setting, or filesystem permission that appears
in more than one place should live here and be imported everywhere else.
"""

from __future__ import annotations

from typing import Final

# Application metadata
APP_NAME: Final[str] = "transcript-fixer"
APP_VERSION: Final[str] = "1.2.2"
SCHEMA_VERSION: Final[str] = "2.0"

# AI provider defaults
API_PROVIDER: Final[str] = "GLM"
DEFAULT_MODEL: Final[str] = "GLM-5.2"
FALLBACK_MODEL: Final[str] = "GLM-5-turbo"
API_BASE_URL: Final[str] = "https://open.bigmodel.cn/api/anthropic"
AUTH_HEADER_NAME: Final[str] = "x-api-key"
ANTHROPIC_VERSION: Final[str] = "2023-06-01"

# Processing defaults
API_TIMEOUT: Final[float] = 60.0
API_MAX_RETRIES: Final[int] = 3
MAX_CHUNK_SIZE: Final[int] = 6000
DEFAULT_DOMAIN: Final[str] = "general"

# Filesystem security
CONFIG_DIR_MODE: Final[int] = 0o700
CONFIG_FILE_MODE: Final[int] = 0o600

# Default values written to system_config on database initialization.
# Order matches the historical schema.sql INSERT block.
SYSTEM_CONFIG_DEFAULTS: Final[dict[str, tuple[str, str, str]]] = {
    "schema_version": (SCHEMA_VERSION, "string", "Database schema version"),
    "api_provider": (API_PROVIDER, "string", "API provider name"),
    "api_model": (DEFAULT_MODEL, "string", "Default AI model"),
    "api_base_url": (API_BASE_URL, "string", "API endpoint URL"),
    "default_domain": (DEFAULT_DOMAIN, "string", "Default correction domain"),
    "auto_learn_enabled": ("true", "boolean", "Enable automatic pattern learning"),
    "backup_enabled": ("true", "boolean", "Create backups before operations"),
    "learning_frequency_threshold": ("3", "int", "Min frequency for learned suggestions"),
    "learning_confidence_threshold": ("0.8", "float", "Min confidence for learned suggestions"),
    "history_retention_days": ("90", "int", "Days to retain correction history"),
    "max_correction_length": ("1000", "int", "Maximum length for correction text"),
}
