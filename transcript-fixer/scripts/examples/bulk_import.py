#!/usr/bin/env python3
"""
Example: Bulk Import Corrections to SQLite Database

This script demonstrates how to import corrections from various sources
into the transcript-fixer SQLite database.

Usage:
    uv run scripts/examples/bulk_import.py
"""

from pathlib import Path
from core import CorrectionRepository, CorrectionService


def import_from_dict():
    """Example: Import corrections from Python dictionary"""

    # Initialize service
    db_path = Path.home() / ".transcript-fixer" / "corrections.db"
    repository = CorrectionRepository(db_path)
    service = CorrectionService(repository)

    # Define corrections as dictionary
    corrections_dict = {
        "巨升智能": "具身智能",
        "巨升": "具身",
        "奇迹创坛": "奇绩创坛",
        "火星营": "火星营",
        "矩阵公司": "初创公司",
        "股价": "框架",
        "三观": "三关"
    }

    # Convert to list format for import
    corrections_list = []
    for from_text, to_text in corrections_dict.items():
        corrections_list.append({
            "from_text": from_text,
            "to_text": to_text,
            "domain": "embodied_ai",
            "source": "imported",
            "confidence": 1.0
        })

    # Import
    inserted, updated, skipped = service.import_corrections(
        corrections=corrections_list,
        merge=True
    )

    print(f"✅ Import complete:")
    print(f"   - Inserted: {inserted}")
    print(f"   - Updated: {updated}")
    print(f"   - Skipped: {skipped}")

    service.close()


def import_from_json_file():
    """Example: Import from old JSON format file"""
    import json

    # Sample JSON structure (v1.0 format)
    sample_json = {
        "metadata": {
            "version": "1.0",
            "domains": ["embodied_ai"],
        },
        "corrections": {
            "巨升智能": "具身智能",
            "巨升": "具身",
        }
    }

    # Initialize service
    db_path = Path.home() / ".transcript-fixer" / "corrections.db"
    repository = CorrectionRepository(db_path)
    service = CorrectionService(repository)

    # Convert JSON to import format
    domain = sample_json["metadata"].get("domains", ["general"])[0]
    corrections_list = []

    for from_text, to_text in sample_json["corrections"].items():
        corrections_list.append({
            "from_text": from_text,
            "to_text": to_text,
            "domain": domain,
            "source": "imported",
            "confidence": 1.0
        })

    # Import
    inserted, updated, skipped = service.import_corrections(
        corrections=corrections_list,
        merge=True
    )

    print(f"✅ JSON import complete:")
    print(f"   - Inserted: {inserted}")
    print(f"   - Updated: {updated}")
    print(f"   - Skipped: {skipped}")

    service.close()


def add_context_rules():
    """Example: Add context-aware regex rules directly"""

    db_path = Path.home() / ".transcript-fixer" / "corrections.db"
    repository = CorrectionRepository(db_path)

    # Add context rules via SQL
    with repository._transaction() as conn:
        rules = [
            ("巨升方向", "具身方向", "巨升→具身", 10),
            ("巨升现在", "具身现在", "巨升→具身", 10),
            ("近距离的去看", "近距离地去看", "的→地 副词修饰", 5),
            ("近距离搏杀", "近距离搏杀", "这里的'近距离'是正确的", 5),
        ]

        for pattern, replacement, description, priority in rules:
            conn.execute("""
                INSERT OR IGNORE INTO context_rules
                (pattern, replacement, description, priority)
                VALUES (?, ?, ?, ?)
            """, (pattern, replacement, description, priority))

    print("✅ Context rules added successfully")
    repository.close()


if __name__ == "__main__":
    print("Transcript-Fixer Bulk Import Examples\n")
    print("=" * 60)

    # Example 1: Import from dictionary
    print("\n1. Importing from Python dictionary...")
    import_from_dict()

    # Example 2: Import from JSON file
    print("\n2. Importing from JSON format...")
    import_from_json_file()

    # Example 3: Add context rules
    print("\n3. Adding context rules...")
    add_context_rules()

    print("\n" + "=" * 60)
    print("✅ All examples completed!")
    print("\nVerify with:")
    print("  sqlite3 ~/.transcript-fixer/corrections.db 'SELECT COUNT(*) FROM active_corrections;'")
