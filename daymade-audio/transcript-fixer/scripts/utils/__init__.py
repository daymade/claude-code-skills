"""
Utils Module - Utility Functions and Tools

This module contains utility functions:
- diff_generator: Multi-format diff report generation
- validation: Configuration validation
- health_check: System health monitoring (P1-4 fix)
- metrics: Metrics collection and monitoring (P1-7 fix)
- rate_limiter: Production-grade rate limiting (P1-8 fix)
- config: Centralized configuration management (P1-5 fix)
- database_migration: Database migration system (P1-6 fix)
- concurrency_manager: Concurrent request handling (P1-9 fix)
- audit_log_retention: Audit log retention and compliance (P1-11 fix)
"""

from .diff_generator import generate_full_report
from .validation import validate_configuration, print_validation_summary
from .health_check import HealthChecker, CheckLevel, HealthStatus, format_health_output
from .metrics import get_metrics, format_metrics_summary, MetricsCollector
from .rate_limiter import (
    RateLimiter,
    RateLimitConfig,
    RateLimitStrategy,
    RateLimitExceeded,
    RateLimitPresets,
    get_rate_limiter,
)
from .config import (
    Config,
    Environment,
    DatabaseConfig,
    APIConfig,
    PathConfig,
    get_config,
    set_config,
    reset_config,
    create_example_config,
)
from .database_migration import (
    DatabaseMigrationManager,
    Migration,
    MigrationRecord,
    MigrationDirection,
    MigrationStatus,
)
from .migrations import (
    MIGRATION_REGISTRY,
    LATEST_VERSION,
    get_migration,
    get_migrations_up_to,
    get_migrations_from,
)
from .db_migrations_cli import create_migration_cli
from .concurrency_manager import (
    ConcurrencyManager,
    ConcurrencyConfig,
    ConcurrencyMetrics,
    CircuitState,
    BackpressureError,
    CircuitBreakerOpenError,
    get_concurrency_manager,
    reset_concurrency_manager,
)
from .audit_log_retention import (
    AuditLogRetentionManager,
    RetentionPolicy,
    RetentionPeriod,
    CleanupStrategy,
    CleanupResult,
    ComplianceReport,
    CRITICAL_ACTIONS,
    get_retention_manager,
    reset_retention_manager,
)

__all__ = [
    'generate_full_report',
    'validate_configuration',
    'print_validation_summary',
    'HealthChecker',
    'CheckLevel',
    'HealthStatus',
    'format_health_output',
    'get_metrics',
    'format_metrics_summary',
    'MetricsCollector',
    'RateLimiter',
    'RateLimitConfig',
    'RateLimitStrategy',
    'RateLimitExceeded',
    'RateLimitPresets',
    'get_rate_limiter',
    'Config',
    'Environment',
    'DatabaseConfig',
    'APIConfig',
    'PathConfig',
    'get_config',
    'set_config',
    'reset_config',
    'create_example_config',
    'DatabaseMigrationManager',
    'Migration',
    'MigrationRecord',
    'MigrationDirection',
    'MigrationStatus',
    'MIGRATION_REGISTRY',
    'LATEST_VERSION',
    'get_migration',
    'get_migrations_up_to',
    'get_migrations_from',
    'create_migration_cli',
    'ConcurrencyManager',
    'ConcurrencyConfig',
    'ConcurrencyMetrics',
    'CircuitState',
    'BackpressureError',
    'CircuitBreakerOpenError',
    'get_concurrency_manager',
    'reset_concurrency_manager',
    'AuditLogRetentionManager',
    'RetentionPolicy',
    'RetentionPeriod',
    'CleanupStrategy',
    'CleanupResult',
    'ComplianceReport',
    'CRITICAL_ACTIONS',
    'get_retention_manager',
    'reset_retention_manager',
]
