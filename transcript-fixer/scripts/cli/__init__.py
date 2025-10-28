"""
CLI Module - Command-Line Interface Handlers

This module contains command handlers and argument parsing:
- commands: Command handler functions (cmd_*)
- argument_parser: CLI argument configuration
"""

from .commands import (
    cmd_init,
    cmd_add_correction,
    cmd_list_corrections,
    cmd_run_correction,
    cmd_review_learned,
    cmd_approve,
    cmd_validate,
)
from .argument_parser import create_argument_parser

__all__ = [
    'cmd_init',
    'cmd_add_correction',
    'cmd_list_corrections',
    'cmd_run_correction',
    'cmd_review_learned',
    'cmd_approve',
    'cmd_validate',
    'create_argument_parser',
]
