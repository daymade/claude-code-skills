#!/usr/bin/env python3
"""
Database Migration CLI - Migration Management Commands

CRITICAL FIX (P1-6): Production database migration CLI commands

Features:
- Run migrations with dry-run support
- Migration status and history
- Rollback capability
- Migration validation
- Migration planning
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any, List
from dataclasses import asdict

from .database_migration import DatabaseMigrationManager, MigrationRecord, MigrationStatus
from .migrations import MIGRATION_REGISTRY, LATEST_VERSION, get_migration, get_migrations_up_to
from .config import get_config

logger = logging.getLogger(__name__)


class DatabaseMigrationCLI:
    """CLI interface for database migrations"""

    def __init__(self, db_path: Path = None):
        """
        Initialize migration CLI

        Args:
            db_path: Database path (uses config if not provided)
        """
        if db_path is None:
            config = get_config()
            db_path = config.database.path

        self.db_path = Path(db_path)
        self.migration_manager = DatabaseMigrationManager(self.db_path)

        # Register all migrations
        for migration in MIGRATION_REGISTRY.values():
            self.migration_manager.register_migration(migration)

    def cmd_status(self, args) -> None:
        """
        Show migration status

        Args:
            args: Command line arguments
        """
        try:
            current_version = self.migration_manager.get_current_version()
            history = self.migration_manager.get_migration_history()
            pending = self.migration_manager.get_pending_migrations()

            print("Database Migration Status")
            print("=" * 40)
            print(f"Database Path: {self.db_path}")
            print(f"Current Version: {current_version}")
            print(f"Latest Version: {LATEST_VERSION}")
            print(f"Pending Migrations: {len(pending)}")
            print(f"Total Migrations Applied: {len([h for h in history if h.status == MigrationStatus.COMPLETED])}")

            if pending:
                print("\nPending Migrations:")
                for migration in pending:
                    print(f"  - {migration.version}: {migration.name}")

            if history:
                print("\nRecent Migration History:")
                for i, record in enumerate(history[:5]):
                    status_icon = "✅" if record.status == MigrationStatus.COMPLETED else "❌"
                    print(f"  {status_icon} {record.version}: {record.name} ({record.status.value})")

        except Exception as e:
            print(f"❌ Error getting status: {e}")
            sys.exit(1)

    def cmd_history(self, args) -> None:
        """
        Show migration history

        Args:
            args: Command line arguments
        """
        try:
            history = self.migration_manager.get_migration_history()

            if not history:
                print("No migration history found")
                return

            if args.format == 'json':
                records = [record.to_dict() for record in history]
                print(json.dumps(records, indent=2, default=str))
            else:
                print("Migration History")
                print("=" * 40)
                for record in history:
                    status_icon = {
                        MigrationStatus.COMPLETED: "✅",
                        MigrationStatus.FAILED: "❌",
                        MigrationStatus.ROLLED_BACK: "↩️",
                        MigrationStatus.RUNNING: "⏳",
                    }.get(record.status, "❓")

                    print(f"{status_icon} {record.version} ({record.direction.value})")
                    print(f"  Name: {record.name}")
                    print(f"  Status: {record.status.value}")
                    print(f"  Executed: {record.executed_at}")
                    print(f"  Duration: {record.execution_time_ms}ms")

                    if record.error_message:
                        print(f"  Error: {record.error_message}")
                    print()

        except Exception as e:
            print(f"❌ Error getting history: {e}")
            sys.exit(1)

    def cmd_migrate(self, args) -> None:
        """
        Run migrations

        Args:
            args: Command line arguments
        """
        try:
            target_version = args.version if args.version else LATEST_VERSION
            dry_run = args.dry_run
            force = args.force

            print(f"Running migrations to version: {target_version}")
            if dry_run:
                print("🚨 DRY RUN MODE - No changes will be applied")
            if force:
                print("🚨 FORCE MODE - Safety checks bypassed")

            # Get migration plan
            plan = self.migration_manager.get_migration_plan(target_version)

            if not plan:
                print("✅ No migrations to apply")
                return

            print(f"\nMigration Plan:")
            print("=" * 40)
            for i, step in enumerate(plan, 1):
                breaking_icon = "🔴" if step.get('is_breaking') else "🟢"
                print(f"{i}. {breaking_icon} {step['version']}: {step['name']}")
                print(f"   Description: {step['description']}")
                if step.get('dependencies'):
                    print(f"   Dependencies: {', '.join(step['dependencies'])}")
                if step.get('is_breaking'):
                    print("   ⚠️  Breaking change - may require data migration")
                print()

            if not args.yes and not dry_run:
                response = input("Continue with migration? (y/N): ")
                if response.lower() != 'y':
                    print("Migration cancelled")
                    return

            # Run migration
            self.migration_manager.migrate_to_version(target_version, dry_run, force)

            if dry_run:
                print("✅ Dry run completed successfully")
            else:
                print("✅ Migration completed successfully")

                # Show new status
                new_version = self.migration_manager.get_current_version()
                print(f"Database is now at version: {new_version}")

        except Exception as e:
            print(f"❌ Migration failed: {e}")
            sys.exit(1)

    def cmd_rollback(self, args) -> None:
        """
        Rollback migration

        Args:
            args: Command line arguments
        """
        try:
            target_version = args.version
            dry_run = args.dry_run
            force = args.force

            if not target_version:
                print("❌ Target version is required for rollback")
                sys.exit(1)

            current_version = self.migration_manager.get_current_version()

            print(f"Rolling back from version {current_version} to {target_version}")
            if dry_run:
                print("🚨 DRY RUN MODE - No changes will be applied")
            if force:
                print("🚨 FORCE MODE - Safety checks bypassed")

            # Warn about potential data loss
            if not args.yes and not dry_run:
                response = input("⚠️  WARNING: Rollback may cause data loss. Continue? (y/N): ")
                if response.lower() != 'y':
                    print("Rollback cancelled")
                    return

            # Run rollback
            self.migration_manager.migrate_to_version(target_version, dry_run, force)

            if dry_run:
                print("✅ Dry run completed successfully")
            else:
                print("✅ Rollback completed successfully")

                # Show new status
                new_version = self.migration_manager.get_current_version()
                print(f"Database is now at version: {new_version}")

        except Exception as e:
            print(f"❌ Rollback failed: {e}")
            sys.exit(1)

    def cmd_plan(self, args) -> None:
        """
        Show migration plan

        Args:
            args: Command line arguments
        """
        try:
            target_version = args.version if args.version else LATEST_VERSION
            plan = self.migration_manager.get_migration_plan(target_version)

            if not plan:
                print("✅ No migrations to apply")
                return

            print(f"Migration Plan (to version {target_version})")
            print("=" * 50)

            current_version = self.migration_manager.get_current_version()
            print(f"Current Version: {current_version}")
            print(f"Target Version: {target_version}")
            print()

            for i, step in enumerate(plan, 1):
                breaking_icon = "🔴" if step.get('is_breaking') else "🟢"
                rollback_icon = "✅" if step.get('has_rollback') else "❌"

                print(f"{i}. {breaking_icon} {step['version']}: {step['name']}")
                print(f"   Description: {step['description']}")
                print(f"   Rollback: {rollback_icon}")

                if step.get('dependencies'):
                    print(f"   Dependencies: {', '.join(step['dependencies'])}")

                print()

            # Safety validation
            is_safe, issues = self.migration_manager.validate_migration_safety(target_version)
            if is_safe:
                print("✅ Migration plan is safe")
            else:
                print("⚠️  Safety issues detected:")
                for issue in issues:
                    print(f"   - {issue}")

        except Exception as e:
            print(f"❌ Error getting migration plan: {e}")
            sys.exit(1)

    def cmd_validate(self, args) -> None:
        """
        Validate migration safety

        Args:
            args: Command line arguments
        """
        try:
            target_version = args.version if args.version else LATEST_VERSION

            is_safe, issues = self.migration_manager.validate_migration_safety(target_version)

            if is_safe:
                print("✅ Migration plan is safe")
                sys.exit(0)
            else:
                print("❌ Migration safety issues found:")
                for issue in issues:
                    print(f"   - {issue}")
                sys.exit(1)

        except Exception as e:
            print(f"❌ Validation failed: {e}")
            sys.exit(1)

    def cmd_create_migration(self, args) -> None:
        """
        Create a new migration template

        Args:
            args: Command line arguments
        """
        try:
            version = args.version
            name = args.name
            description = args.description

            if not version or not name:
                print("❌ Version and name are required")
                sys.exit(1)

            # Check if migration already exists
            if version in MIGRATION_REGISTRY:
                print(f"❌ Migration {version} already exists")
                sys.exit(1)

            # Create migration template
            template = f'''
# Migration {version}: {name}
# Description: {description}

from __future__ import annotations
import sqlite3
from typing import Tuple
from .database_migration import Migration
from utils.migrations import get_migration


def _validate_migration(conn: sqlite3.Connection, migration: Migration) -> Tuple[bool, str]:
    """Validate migration"""
    # Add custom validation logic here
    return True, "Migration validation passed"


MIGRATION_{version.replace(".", "_")} = Migration(
    version="{version}",
    name="{name}",
    description="{description}",
    forward_sql=\"\"\"
    -- Add your forward migration SQL here
    \"\"\",
    backward_sql=\"\"\"
    -- Add your backward migration SQL here (optional)
    \"\"\",
    dependencies=["2.2"],  # List required migrations
    check_function=_validate_migration,
    is_breaking=False  # Set to True for breaking changes
)

# Add to MIGRATION_REGISTRY in migrations.py
# ALL_MIGRATIONS.append(MIGRATION_{version.replace(".", "_")})
# MIGRATION_REGISTRY["{version}"] = MIGRATION_{version.replace(".", "_")}
# LATEST_VERSION = "{version}"  # Update if this is the latest
            '''.strip()

            print("Migration Template:")
            print("=" * 50)
            print(template)
            print("\n⚠️  Remember to:")
            print("1. Add the migration to ALL_MIGRATIONS list in migrations.py")
            print("2. Update MIGRATION_REGISTRY and LATEST_VERSION")
            print("3. Test the migration before deploying")

        except Exception as e:
            print(f"❌ Error creating template: {e}")
            sys.exit(1)


def create_migration_cli(db_path: Path = None) -> DatabaseMigrationCLI:
    """Create migration CLI instance"""
    return DatabaseMigrationCLI(db_path)