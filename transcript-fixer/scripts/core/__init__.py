"""
Core Module - Business Logic and Data Access

This module contains the core business logic for transcript correction:
- CorrectionRepository: Data access layer with ACID transactions
- CorrectionService: Business logic layer with validation
- DictionaryProcessor: Stage 1 dictionary-based corrections
- AIProcessor: Stage 2 AI-powered corrections
- LearningEngine: Pattern detection and learning
"""

# Core SQLite-based components (always available)
from .correction_repository import CorrectionRepository, Correction, DatabaseError, ValidationError
from .correction_service import CorrectionService, ValidationRules

# Processing components (imported lazily to avoid dependency issues)
def _lazy_import(name: str) -> object:
    """Lazy import to avoid loading heavy dependencies."""
    if name == 'DictionaryProcessor':
        from .dictionary_processor import DictionaryProcessor
        return DictionaryProcessor
    elif name == 'AIProcessor':
        # Use async processor by default for 5-10x speedup on large files
        from .ai_processor_async import AIProcessorAsync
        return AIProcessorAsync
    elif name == 'LearningEngine':
        from .learning_engine import LearningEngine
        return LearningEngine
    raise ImportError(f"Unknown module: {name}")

# Export main classes
__all__ = [
    'CorrectionRepository',
    'CorrectionService',
    'Correction',
    'DatabaseError',
    'ValidationError',
    'ValidationRules',
]

# Make lazy imports available via __getattr__
def __getattr__(name):
    if name in ['DictionaryProcessor', 'AIProcessor', 'LearningEngine']:
        return _lazy_import(name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
