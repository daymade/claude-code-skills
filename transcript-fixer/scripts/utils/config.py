#!/usr/bin/env python3
"""
Configuration Management Module

CRITICAL FIX (P1-5): Production-grade configuration management

Features:
- Centralized configuration (single source of truth)
- Environment-based config (dev/staging/prod)
- Type-safe access with validation
- Multiple config sources (env vars, files, defaults)
- Config schema validation
- Secure secrets management

Use cases:
- Application configuration
- Environment-specific settings
- API keys and secrets management
- Path configuration
- Feature flags
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, Final

logger = logging.getLogger(__name__)


class Environment(Enum):
    """Application environment"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


@dataclass
class DatabaseConfig:
    """Database configuration"""
    path: Path
    max_connections: int = 5
    connection_timeout: float = 30.0
    enable_wal_mode: bool = True  # Write-Ahead Logging for better concurrency

    def __post_init__(self):
        """Validate database configuration"""
        if self.max_connections <= 0:
            raise ValueError("max_connections must be positive")
        if self.connection_timeout <= 0:
            raise ValueError("connection_timeout must be positive")

        # Ensure database directory exists
        self.path = Path(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)


@dataclass
class APIConfig:
    """API configuration"""
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    timeout: float = 60.0
    max_retries: int = 3
    retry_backoff: float = 1.0  # Exponential backoff base (seconds)

    def __post_init__(self):
        """Validate API configuration"""
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if self.retry_backoff < 0:
            raise ValueError("retry_backoff must be non-negative")


@dataclass
class PathConfig:
    """Path configuration"""
    config_dir: Path
    data_dir: Path
    log_dir: Path
    cache_dir: Path

    def __post_init__(self):
        """Validate and create directories"""
        self.config_dir = Path(self.config_dir)
        self.data_dir = Path(self.data_dir)
        self.log_dir = Path(self.log_dir)
        self.cache_dir = Path(self.cache_dir)

        # Create all directories
        for dir_path in [self.config_dir, self.data_dir, self.log_dir, self.cache_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)


@dataclass
class ResourceLimits:
    """Resource limits configuration"""
    max_text_length: int = 1_000_000  # 1MB max text
    max_file_size: int = 10_000_000  # 10MB max file
    max_concurrent_tasks: int = 10
    max_memory_mb: int = 512
    rate_limit_requests: int = 100
    rate_limit_window_seconds: float = 60.0

    def __post_init__(self):
        """Validate resource limits"""
        if self.max_text_length <= 0:
            raise ValueError("max_text_length must be positive")
        if self.max_file_size <= 0:
            raise ValueError("max_file_size must be positive")
        if self.max_concurrent_tasks <= 0:
            raise ValueError("max_concurrent_tasks must be positive")


@dataclass
class FeatureFlags:
    """Feature flags for conditional functionality"""
    enable_learning: bool = True
    enable_metrics: bool = True
    enable_health_checks: bool = True
    enable_rate_limiting: bool = True
    enable_caching: bool = True
    enable_auto_approval: bool = False  # Auto-approve learned suggestions


@dataclass
class Config:
    """
    Main configuration class - Single source of truth for all configuration.

    Configuration precedence (highest to lowest):
    1. Environment variables
    2. Config file (if provided)
    3. Default values
    """

    # Environment
    environment: Environment = Environment.DEVELOPMENT

    # Sub-configurations
    database: DatabaseConfig = field(default_factory=lambda: DatabaseConfig(
        path=Path.home() / ".transcript-fixer" / "corrections.db"
    ))
    api: APIConfig = field(default_factory=APIConfig)
    paths: PathConfig = field(default_factory=lambda: PathConfig(
        config_dir=Path.home() / ".transcript-fixer",
        data_dir=Path.home() / ".transcript-fixer" / "data",
        log_dir=Path.home() / ".transcript-fixer" / "logs",
        cache_dir=Path.home() / ".transcript-fixer" / "cache",
    ))
    resources: ResourceLimits = field(default_factory=ResourceLimits)
    features: FeatureFlags = field(default_factory=FeatureFlags)

    # Application metadata
    app_name: str = "transcript-fixer"
    app_version: str = "1.0.0"
    debug: bool = False

    def __post_init__(self):
        """Post-initialization validation"""
        logger.debug(f"Config initialized for environment: {self.environment.value}")

    @classmethod
    def from_env(cls) -> Config:
        """
        Create configuration from environment variables.

        Environment variables:
            - TRANSCRIPT_FIXER_ENV: Environment (development/staging/production)
            - TRANSCRIPT_FIXER_CONFIG_DIR: Config directory path
            - TRANSCRIPT_FIXER_DB_PATH: Database path
            - GLM_API_KEY: API key for GLM service
            - ANTHROPIC_API_KEY: Alternative API key
            - ANTHROPIC_BASE_URL: API base URL
            - TRANSCRIPT_FIXER_DEBUG: Enable debug mode (1/true/yes)

        Returns:
            Config instance with values from environment variables
        """
        # Parse environment
        env_str = os.getenv("TRANSCRIPT_FIXER_ENV", "development").lower()
        try:
            environment = Environment(env_str)
        except ValueError:
            logger.warning(f"Invalid environment '{env_str}', defaulting to development")
            environment = Environment.DEVELOPMENT

        # Parse debug flag
        debug_str = os.getenv("TRANSCRIPT_FIXER_DEBUG", "0").lower()
        debug = debug_str in ("1", "true", "yes", "on")

        # Parse paths
        config_dir = Path(os.getenv(
            "TRANSCRIPT_FIXER_CONFIG_DIR",
            str(Path.home() / ".transcript-fixer")
        ))

        # Database config
        db_path = Path(os.getenv(
            "TRANSCRIPT_FIXER_DB_PATH",
            str(config_dir / "corrections.db")
        ))
        db_max_connections = int(os.getenv("TRANSCRIPT_FIXER_DB_MAX_CONNECTIONS", "5"))

        database = DatabaseConfig(
            path=db_path,
            max_connections=db_max_connections,
        )

        # API config
        api_key = os.getenv("GLM_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        base_url = os.getenv("ANTHROPIC_BASE_URL")
        api_timeout = float(os.getenv("TRANSCRIPT_FIXER_API_TIMEOUT", "60.0"))

        api = APIConfig(
            api_key=api_key,
            base_url=base_url,
            timeout=api_timeout,
        )

        # Path config
        paths = PathConfig(
            config_dir=config_dir,
            data_dir=config_dir / "data",
            log_dir=config_dir / "logs",
            cache_dir=config_dir / "cache",
        )

        # Resource limits
        resources = ResourceLimits(
            max_concurrent_tasks=int(os.getenv("TRANSCRIPT_FIXER_MAX_CONCURRENT", "10")),
            rate_limit_requests=int(os.getenv("TRANSCRIPT_FIXER_RATE_LIMIT", "100")),
        )

        # Feature flags
        features = FeatureFlags(
            enable_learning=os.getenv("TRANSCRIPT_FIXER_ENABLE_LEARNING", "1") != "0",
            enable_metrics=os.getenv("TRANSCRIPT_FIXER_ENABLE_METRICS", "1") != "0",
            enable_auto_approval=os.getenv("TRANSCRIPT_FIXER_AUTO_APPROVE", "0") == "1",
        )

        return cls(
            environment=environment,
            database=database,
            api=api,
            paths=paths,
            resources=resources,
            features=features,
            debug=debug,
        )

    @classmethod
    def from_file(cls, config_path: Path) -> Config:
        """
        Load configuration from JSON file.

        Args:
            config_path: Path to JSON config file

        Returns:
            Config instance with values from file

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config file is invalid
        """
        config_path = Path(config_path)

        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in config file: {e}")

        # Parse environment
        env_str = data.get("environment", "development")
        try:
            environment = Environment(env_str)
        except ValueError:
            logger.warning(f"Invalid environment '{env_str}', defaulting to development")
            environment = Environment.DEVELOPMENT

        # Parse database config
        db_data = data.get("database", {})
        database = DatabaseConfig(
            path=Path(db_data.get("path", str(Path.home() / ".transcript-fixer" / "corrections.db"))),
            max_connections=db_data.get("max_connections", 5),
            connection_timeout=db_data.get("connection_timeout", 30.0),
        )

        # Parse API config
        api_data = data.get("api", {})
        api = APIConfig(
            api_key=api_data.get("api_key"),
            base_url=api_data.get("base_url"),
            timeout=api_data.get("timeout", 60.0),
            max_retries=api_data.get("max_retries", 3),
        )

        # Parse path config
        paths_data = data.get("paths", {})
        config_dir = Path(paths_data.get("config_dir", str(Path.home() / ".transcript-fixer")))
        paths = PathConfig(
            config_dir=config_dir,
            data_dir=Path(paths_data.get("data_dir", str(config_dir / "data"))),
            log_dir=Path(paths_data.get("log_dir", str(config_dir / "logs"))),
            cache_dir=Path(paths_data.get("cache_dir", str(config_dir / "cache"))),
        )

        # Parse resource limits
        resources_data = data.get("resources", {})
        resources = ResourceLimits(
            max_text_length=resources_data.get("max_text_length", 1_000_000),
            max_file_size=resources_data.get("max_file_size", 10_000_000),
            max_concurrent_tasks=resources_data.get("max_concurrent_tasks", 10),
        )

        # Parse feature flags
        features_data = data.get("features", {})
        features = FeatureFlags(
            enable_learning=features_data.get("enable_learning", True),
            enable_metrics=features_data.get("enable_metrics", True),
            enable_auto_approval=features_data.get("enable_auto_approval", False),
        )

        return cls(
            environment=environment,
            database=database,
            api=api,
            paths=paths,
            resources=resources,
            features=features,
            debug=data.get("debug", False),
        )

    def save_to_file(self, config_path: Path) -> None:
        """
        Save configuration to JSON file.

        Args:
            config_path: Path to save config file
        """
        config_path = Path(config_path)
        config_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "environment": self.environment.value,
            "database": {
                "path": str(self.database.path),
                "max_connections": self.database.max_connections,
                "connection_timeout": self.database.connection_timeout,
            },
            "api": {
                "api_key": self.api.api_key,
                "base_url": self.api.base_url,
                "timeout": self.api.timeout,
                "max_retries": self.api.max_retries,
            },
            "paths": {
                "config_dir": str(self.paths.config_dir),
                "data_dir": str(self.paths.data_dir),
                "log_dir": str(self.paths.log_dir),
                "cache_dir": str(self.paths.cache_dir),
            },
            "resources": {
                "max_text_length": self.resources.max_text_length,
                "max_file_size": self.resources.max_file_size,
                "max_concurrent_tasks": self.resources.max_concurrent_tasks,
            },
            "features": {
                "enable_learning": self.features.enable_learning,
                "enable_metrics": self.features.enable_metrics,
                "enable_auto_approval": self.features.enable_auto_approval,
            },
            "debug": self.debug,
        }

        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Configuration saved to {config_path}")

    def validate(self) -> tuple[list[str], list[str]]:
        """
        Validate configuration completeness and correctness.

        Returns:
            Tuple of (errors, warnings)
        """
        errors = []
        warnings = []

        # Check API key for production
        if self.environment == Environment.PRODUCTION:
            if not self.api.api_key:
                errors.append("API key is required in production environment")
        elif not self.api.api_key:
            warnings.append("API key not set (required for AI corrections)")

        # Check database path
        if not self.database.path.parent.exists():
            errors.append(f"Database directory doesn't exist: {self.database.path.parent}")

        # Check paths exist
        for name, path in [
            ("config_dir", self.paths.config_dir),
            ("data_dir", self.paths.data_dir),
            ("log_dir", self.paths.log_dir),
        ]:
            if not path.exists():
                warnings.append(f"{name} doesn't exist: {path}")

        # Check resource limits are reasonable
        if self.resources.max_concurrent_tasks > 50:
            warnings.append(f"max_concurrent_tasks is very high: {self.resources.max_concurrent_tasks}")

        return errors, warnings

    def get_database_url(self) -> str:
        """Get database connection URL"""
        return f"sqlite:///{self.database.path}"

    def is_production(self) -> bool:
        """Check if running in production"""
        return self.environment == Environment.PRODUCTION

    def is_development(self) -> bool:
        """Check if running in development"""
        return self.environment == Environment.DEVELOPMENT


# Global configuration instance
_config: Optional[Config] = None


def get_config() -> Config:
    """
    Get global configuration instance (singleton pattern).

    Returns:
        Config instance loaded from environment variables
    """
    global _config

    if _config is None:
        # Load from environment by default
        _config = Config.from_env()
        logger.info(f"Configuration loaded: {_config.environment.value}")

        # Validate
        errors, warnings = _config.validate()
        if errors:
            logger.error(f"Configuration errors: {errors}")
        if warnings:
            logger.warning(f"Configuration warnings: {warnings}")

    return _config


def set_config(config: Config) -> None:
    """
    Set global configuration instance (for testing or manual config).

    Args:
        config: Config instance to set globally
    """
    global _config
    _config = config
    logger.info(f"Configuration set: {config.environment.value}")


def reset_config() -> None:
    """Reset global configuration (mainly for testing)"""
    global _config
    _config = None
    logger.debug("Configuration reset")


# Example configuration file template
CONFIG_FILE_TEMPLATE: Final[str] = """{
  "environment": "development",
  "database": {
    "path": "~/.transcript-fixer/corrections.db",
    "max_connections": 5,
    "connection_timeout": 30.0
  },
  "api": {
    "api_key": "your-api-key-here",
    "base_url": null,
    "timeout": 60.0,
    "max_retries": 3
  },
  "paths": {
    "config_dir": "~/.transcript-fixer",
    "data_dir": "~/.transcript-fixer/data",
    "log_dir": "~/.transcript-fixer/logs",
    "cache_dir": "~/.transcript-fixer/cache"
  },
  "resources": {
    "max_text_length": 1000000,
    "max_file_size": 10000000,
    "max_concurrent_tasks": 10
  },
  "features": {
    "enable_learning": true,
    "enable_metrics": true,
    "enable_auto_approval": false
  },
  "debug": false
}
"""


def create_example_config(output_path: Path) -> None:
    """
    Create example configuration file.

    Args:
        output_path: Path to write example config
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(CONFIG_FILE_TEMPLATE)

    logger.info(f"Example config created: {output_path}")
