"""
Utils Module - Utility Functions and Tools

This module contains utility functions:
- diff_generator: Multi-format diff report generation
- validation: Configuration validation
"""

from .diff_generator import generate_full_report
from .validation import validate_configuration, print_validation_summary

__all__ = [
    'generate_full_report',
    'validate_configuration',
    'print_validation_summary',
]
