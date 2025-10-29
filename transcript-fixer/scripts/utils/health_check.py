#!/usr/bin/env python3
"""
Health Check Module - System Health Monitoring

CRITICAL FIX (P1-4): Production-grade health checks for monitoring

Features:
- Database connectivity and schema validation
- File system access checks
- Configuration validation
- Dependency verification
- Resource availability checks

Health Check Levels:
- Basic: Quick connectivity checks (< 100ms)
- Standard: Full system validation (< 1s)
- Deep: Comprehensive diagnostics (< 5s)
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import List, Dict, Optional, Final

logger = logging.getLogger(__name__)

# Import configuration for centralized config management (P1-5 fix)
from .config import get_config

# Health check thresholds
RESPONSE_TIME_WARNING: Final[float] = 1.0  # seconds
RESPONSE_TIME_CRITICAL: Final[float] = 5.0  # seconds
MIN_DISK_SPACE_MB: Final[int] = 100  # MB


class HealthStatus(Enum):
    """Health status levels"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class CheckLevel(Enum):
    """Health check thoroughness levels"""
    BASIC = "basic"        # Quick checks (< 100ms)
    STANDARD = "standard"  # Full validation (< 1s)
    DEEP = "deep"          # Comprehensive (< 5s)


@dataclass
class HealthCheckResult:
    """Result of a single health check"""
    name: str
    status: HealthStatus
    message: str
    duration_ms: float
    details: Optional[Dict] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        result = asdict(self)
        result['status'] = self.status.value
        return result


@dataclass
class SystemHealth:
    """Overall system health status"""
    status: HealthStatus
    timestamp: str
    duration_ms: float
    checks: List[HealthCheckResult]
    summary: Dict[str, int]

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'status': self.status.value,
            'timestamp': self.timestamp,
            'duration_ms': round(self.duration_ms, 2),
            'checks': [check.to_dict() for check in self.checks],
            'summary': self.summary
        }

    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


class HealthChecker:
    """
    System health checker with configurable thoroughness levels.

    CRITICAL FIX (P1-4): Enables monitoring and observability
    """

    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize health checker

        Args:
            config_dir: Configuration directory (defaults to ~/.transcript-fixer)
        """
        # P1-5 FIX: Use centralized configuration
        config = get_config()

        # For backward compatibility, still accept config_dir parameter
        self.config_dir = config_dir or config.paths.config_dir
        self.db_path = config.database.path

    def check_health(self, level: CheckLevel = CheckLevel.STANDARD) -> SystemHealth:
        """
        Perform health check at specified level

        Args:
            level: Thoroughness level (BASIC, STANDARD, DEEP)

        Returns:
            SystemHealth with overall status and individual check results
        """
        start_time = time.time()
        checks: List[HealthCheckResult] = []

        logger.info(f"Starting health check (level: {level.value})")

        # Always run basic checks
        checks.append(self._check_config_directory())
        checks.append(self._check_database())

        # Standard level: add configuration checks
        if level in (CheckLevel.STANDARD, CheckLevel.DEEP):
            checks.append(self._check_api_key())
            checks.append(self._check_dependencies())
            checks.append(self._check_disk_space())

        # Deep level: add comprehensive diagnostics
        if level == CheckLevel.DEEP:
            checks.append(self._check_database_schema())
            checks.append(self._check_file_permissions())
            checks.append(self._check_python_version())

        # Calculate overall status
        duration_ms = (time.time() - start_time) * 1000
        overall_status = self._calculate_overall_status(checks)

        # Generate summary
        summary = {
            'total': len(checks),
            'healthy': sum(1 for c in checks if c.status == HealthStatus.HEALTHY),
            'degraded': sum(1 for c in checks if c.status == HealthStatus.DEGRADED),
            'unhealthy': sum(1 for c in checks if c.status == HealthStatus.UNHEALTHY),
        }

        # Check for slow response time
        if duration_ms > RESPONSE_TIME_CRITICAL * 1000:
            logger.warning(f"Health check took {duration_ms:.0f}ms (critical threshold)")
        elif duration_ms > RESPONSE_TIME_WARNING * 1000:
            logger.warning(f"Health check took {duration_ms:.0f}ms (warning threshold)")

        return SystemHealth(
            status=overall_status,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            duration_ms=duration_ms,
            checks=checks,
            summary=summary
        )

    def _calculate_overall_status(self, checks: List[HealthCheckResult]) -> HealthStatus:
        """Calculate overall system status from individual checks"""
        if not checks:
            return HealthStatus.UNKNOWN

        # Any unhealthy check = system unhealthy
        if any(c.status == HealthStatus.UNHEALTHY for c in checks):
            return HealthStatus.UNHEALTHY

        # Any degraded check = system degraded
        if any(c.status == HealthStatus.DEGRADED for c in checks):
            return HealthStatus.DEGRADED

        # All healthy = system healthy
        if all(c.status == HealthStatus.HEALTHY for c in checks):
            return HealthStatus.HEALTHY

        return HealthStatus.UNKNOWN

    def _check_config_directory(self) -> HealthCheckResult:
        """Check configuration directory exists and is writable"""
        start_time = time.time()
        name = "config_directory"

        try:
            # Check existence
            if not self.config_dir.exists():
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message="Configuration directory does not exist",
                    duration_ms=(time.time() - start_time) * 1000,
                    details={'path': str(self.config_dir)},
                    error="Directory not found"
                )

            # Check writability
            test_file = self.config_dir / ".health_check_test"
            try:
                test_file.touch()
                test_file.unlink()
            except (PermissionError, OSError) as e:
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.DEGRADED,
                    message="Configuration directory not writable",
                    duration_ms=(time.time() - start_time) * 1000,
                    details={'path': str(self.config_dir)},
                    error=str(e)
                )

            return HealthCheckResult(
                name=name,
                status=HealthStatus.HEALTHY,
                message="Configuration directory accessible",
                duration_ms=(time.time() - start_time) * 1000,
                details={'path': str(self.config_dir)}
            )

        except Exception as e:
            logger.exception("Config directory check failed")
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message="Configuration directory check failed",
                duration_ms=(time.time() - start_time) * 1000,
                error=str(e)
            )

    def _check_database(self) -> HealthCheckResult:
        """Check database exists and is accessible"""
        start_time = time.time()
        name = "database"

        try:
            if not self.db_path.exists():
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.DEGRADED,
                    message="Database not initialized",
                    duration_ms=(time.time() - start_time) * 1000,
                    details={'path': str(self.db_path)},
                    error="Database file not found"
                )

            # Try to open database
            import sqlite3
            try:
                conn = sqlite3.connect(str(self.db_path), timeout=5.0)
                cursor = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
                table_count = cursor.fetchone()[0]
                conn.close()

                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.HEALTHY,
                    message="Database accessible",
                    duration_ms=(time.time() - start_time) * 1000,
                    details={
                        'path': str(self.db_path),
                        'tables': table_count,
                        'size_kb': self.db_path.stat().st_size // 1024
                    }
                )

            except sqlite3.Error as e:
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message="Database connection failed",
                    duration_ms=(time.time() - start_time) * 1000,
                    details={'path': str(self.db_path)},
                    error=str(e)
                )

        except Exception as e:
            logger.exception("Database check failed")
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message="Database check failed",
                duration_ms=(time.time() - start_time) * 1000,
                error=str(e)
            )

    def _check_api_key(self) -> HealthCheckResult:
        """Check API key is configured"""
        start_time = time.time()
        name = "api_key"

        try:
            # P1-5 FIX: Use centralized configuration
            config = get_config()
            api_key = config.api.api_key

            if not api_key:
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.DEGRADED,
                    message="API key not configured",
                    duration_ms=(time.time() - start_time) * 1000,
                    details={'env_vars_checked': ['GLM_API_KEY', 'ANTHROPIC_API_KEY']},
                    error="No API key found in environment"
                )

            # Check key format (don't validate by calling API)
            if len(api_key) < 10:
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.DEGRADED,
                    message="API key format suspicious",
                    duration_ms=(time.time() - start_time) * 1000,
                    details={'key_length': len(api_key)},
                    error="API key too short"
                )

            return HealthCheckResult(
                name=name,
                status=HealthStatus.HEALTHY,
                message="API key configured",
                duration_ms=(time.time() - start_time) * 1000,
                details={'key_length': len(api_key), 'masked_key': api_key[:8] + '***'}
            )

        except Exception as e:
            logger.exception("API key check failed")
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message="API key check failed",
                duration_ms=(time.time() - start_time) * 1000,
                error=str(e)
            )

    def _check_dependencies(self) -> HealthCheckResult:
        """Check required dependencies are installed"""
        start_time = time.time()
        name = "dependencies"

        required_modules = ['httpx', 'filelock']
        missing = []
        installed = []

        try:
            for module in required_modules:
                try:
                    __import__(module)
                    installed.append(module)
                except ImportError:
                    missing.append(module)

            if missing:
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Missing dependencies: {', '.join(missing)}",
                    duration_ms=(time.time() - start_time) * 1000,
                    details={'installed': installed, 'missing': missing},
                    error=f"Install with: pip install {' '.join(missing)}"
                )

            return HealthCheckResult(
                name=name,
                status=HealthStatus.HEALTHY,
                message="All dependencies installed",
                duration_ms=(time.time() - start_time) * 1000,
                details={'installed': installed}
            )

        except Exception as e:
            logger.exception("Dependencies check failed")
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message="Dependencies check failed",
                duration_ms=(time.time() - start_time) * 1000,
                error=str(e)
            )

    def _check_disk_space(self) -> HealthCheckResult:
        """Check available disk space"""
        start_time = time.time()
        name = "disk_space"

        try:
            import shutil
            stat = shutil.disk_usage(self.config_dir.parent)

            free_mb = stat.free / (1024 * 1024)
            total_mb = stat.total / (1024 * 1024)
            used_percent = (stat.used / stat.total) * 100

            if free_mb < MIN_DISK_SPACE_MB:
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Low disk space: {free_mb:.0f}MB free",
                    duration_ms=(time.time() - start_time) * 1000,
                    details={
                        'free_mb': round(free_mb, 2),
                        'total_mb': round(total_mb, 2),
                        'used_percent': round(used_percent, 1)
                    },
                    error=f"Less than {MIN_DISK_SPACE_MB}MB available"
                )

            return HealthCheckResult(
                name=name,
                status=HealthStatus.HEALTHY,
                message=f"Sufficient disk space: {free_mb:.0f}MB free",
                duration_ms=(time.time() - start_time) * 1000,
                details={
                    'free_mb': round(free_mb, 2),
                    'total_mb': round(total_mb, 2),
                    'used_percent': round(used_percent, 1)
                }
            )

        except Exception as e:
            logger.exception("Disk space check failed")
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNKNOWN,
                message="Disk space check failed",
                duration_ms=(time.time() - start_time) * 1000,
                error=str(e)
            )

    def _check_database_schema(self) -> HealthCheckResult:
        """Check database schema is valid (deep check)"""
        start_time = time.time()
        name = "database_schema"

        expected_tables = [
            'corrections', 'context_rules', 'correction_history',
            'correction_changes', 'learned_suggestions', 'suggestion_examples',
            'system_config', 'audit_log'
        ]

        try:
            if not self.db_path.exists():
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.DEGRADED,
                    message="Database not initialized",
                    duration_ms=(time.time() - start_time) * 1000,
                    error="Cannot check schema - database missing"
                )

            import sqlite3
            conn = sqlite3.connect(str(self.db_path), timeout=5.0)
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            actual_tables = [row[0] for row in cursor.fetchall()]
            conn.close()

            missing = [t for t in expected_tables if t not in actual_tables]
            extra = [t for t in actual_tables if t not in expected_tables and not t.startswith('sqlite_')]

            if missing:
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.DEGRADED,
                    message=f"Missing tables: {', '.join(missing)}",
                    duration_ms=(time.time() - start_time) * 1000,
                    details={
                        'expected': expected_tables,
                        'actual': actual_tables,
                        'missing': missing,
                        'extra': extra
                    },
                    error="Schema incomplete"
                )

            return HealthCheckResult(
                name=name,
                status=HealthStatus.HEALTHY,
                message="Database schema valid",
                duration_ms=(time.time() - start_time) * 1000,
                details={
                    'tables': actual_tables,
                    'count': len(actual_tables)
                }
            )

        except Exception as e:
            logger.exception("Database schema check failed")
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message="Database schema check failed",
                duration_ms=(time.time() - start_time) * 1000,
                error=str(e)
            )

    def _check_file_permissions(self) -> HealthCheckResult:
        """Check file permissions (deep check)"""
        start_time = time.time()
        name = "file_permissions"

        try:
            issues = []

            # Check config directory permissions
            if not os.access(self.config_dir, os.R_OK | os.W_OK | os.X_OK):
                issues.append(f"Config dir: insufficient permissions")

            # Check database permissions (if exists)
            if self.db_path.exists():
                if not os.access(self.db_path, os.R_OK | os.W_OK):
                    issues.append(f"Database: read/write denied")

            if issues:
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.DEGRADED,
                    message="Permission issues detected",
                    duration_ms=(time.time() - start_time) * 1000,
                    details={'issues': issues},
                    error='; '.join(issues)
                )

            return HealthCheckResult(
                name=name,
                status=HealthStatus.HEALTHY,
                message="File permissions correct",
                duration_ms=(time.time() - start_time) * 1000
            )

        except Exception as e:
            logger.exception("File permissions check failed")
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNKNOWN,
                message="File permissions check failed",
                duration_ms=(time.time() - start_time) * 1000,
                error=str(e)
            )

    def _check_python_version(self) -> HealthCheckResult:
        """Check Python version (deep check)"""
        start_time = time.time()
        name = "python_version"

        try:
            version = sys.version_info
            version_str = f"{version.major}.{version.minor}.{version.micro}"

            # Minimum required: Python 3.8
            if version < (3, 8):
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Python version too old: {version_str}",
                    duration_ms=(time.time() - start_time) * 1000,
                    details={'version': version_str, 'minimum': '3.8'},
                    error="Python 3.8+ required"
                )

            # Warn if using Python 3.12+ (may have compatibility issues)
            if version >= (3, 13):
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.DEGRADED,
                    message=f"Python version very new: {version_str}",
                    duration_ms=(time.time() - start_time) * 1000,
                    details={'version': version_str, 'recommended': '3.8-3.12'},
                    error="May have untested compatibility issues"
                )

            return HealthCheckResult(
                name=name,
                status=HealthStatus.HEALTHY,
                message=f"Python version supported: {version_str}",
                duration_ms=(time.time() - start_time) * 1000,
                details={'version': version_str}
            )

        except Exception as e:
            logger.exception("Python version check failed")
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNKNOWN,
                message="Python version check failed",
                duration_ms=(time.time() - start_time) * 1000,
                error=str(e)
            )


def format_health_output(health: SystemHealth, verbose: bool = False) -> str:
    """
    Format health check results for CLI output

    Args:
        health: SystemHealth object
        verbose: Show detailed information

    Returns:
        Formatted string for display
    """
    lines = []

    # Header - icon mapping
    status_icon_map = {
        HealthStatus.HEALTHY: "✅",
        HealthStatus.DEGRADED: "⚠️",
        HealthStatus.UNHEALTHY: "❌",
        HealthStatus.UNKNOWN: "❓"
    }

    overall_icon = status_icon_map[health.status]

    lines.append(f"\n{overall_icon} System Health: {health.status.value.upper()}")
    lines.append(f"{'=' * 70}")
    lines.append(f"Timestamp: {health.timestamp}")
    lines.append(f"Duration: {health.duration_ms:.1f}ms")
    lines.append(f"Checks: {health.summary['healthy']}/{health.summary['total']} passed")
    lines.append("")

    # Individual checks
    for check in health.checks:
        icon = status_icon_map.get(check.status, "❓")
        lines.append(f"{icon} {check.name}: {check.message}")

        if verbose and check.details:
            for key, value in check.details.items():
                lines.append(f"    {key}: {value}")

        if check.error:
            lines.append(f"    Error: {check.error}")

        if verbose:
            lines.append(f"    Duration: {check.duration_ms:.1f}ms")

    lines.append(f"\n{'=' * 70}")

    return "\n".join(lines)
