#!/usr/bin/env python3
"""
Type Hints Coverage Checker (P1-12)

Analyzes Python files for type hint coverage and identifies missing annotations.

Author: Chief Engineer (ISTJ, 20 years experience)
Date: 2025-10-29
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass, field


@dataclass
class TypeHintStats:
    """Statistics for type hint coverage in a file"""
    file_path: Path
    total_functions: int = 0
    functions_with_return_type: int = 0
    total_parameters: int = 0
    parameters_with_type: int = 0
    missing_hints: List[str] = field(default_factory=list)

    @property
    def function_coverage(self) -> float:
        """Calculate function return type coverage percentage"""
        if self.total_functions == 0:
            return 100.0
        return (self.functions_with_return_type / self.total_functions) * 100

    @property
    def parameter_coverage(self) -> float:
        """Calculate parameter type coverage percentage"""
        if self.total_parameters == 0:
            return 100.0
        return (self.parameters_with_type / self.total_parameters) * 100

    @property
    def overall_coverage(self) -> float:
        """Calculate overall type hint coverage"""
        total_items = self.total_functions + self.total_parameters
        if total_items == 0:
            return 100.0
        typed_items = self.functions_with_return_type + self.parameters_with_type
        return (typed_items / total_items) * 100


class TypeHintChecker(ast.NodeVisitor):
    """AST visitor to check for type hints"""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.stats = TypeHintStats(file_path)
        self.current_class = None

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit class definition"""
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function/method definition"""
        # Skip private methods starting with __
        if node.name.startswith('__') and node.name.endswith('__'):
            if node.name not in ['__init__', '__call__', '__enter__', '__exit__',
                                  '__aenter__', '__aexit__']:
                self.generic_visit(node)
                return

        self.stats.total_functions += 1

        # Check return type annotation
        if node.returns is not None:
            self.stats.functions_with_return_type += 1
        else:
            # Only report missing return type if function actually returns something
            has_return = any(isinstance(n, ast.Return) and n.value is not None
                           for n in ast.walk(node))
            if has_return:
                context = f"{self.current_class}.{node.name}" if self.current_class else node.name
                self.stats.missing_hints.append(
                    f"  Line {node.lineno}: Function '{context}' missing return type"
                )

        # Check parameter annotations
        for arg in node.args.args:
            # Skip 'self' and 'cls'
            if arg.arg in ['self', 'cls']:
                continue

            self.stats.total_parameters += 1

            if arg.annotation is not None:
                self.stats.parameters_with_type += 1
            else:
                context = f"{self.current_class}.{node.name}" if self.current_class else node.name
                self.stats.missing_hints.append(
                    f"  Line {node.lineno}: Parameter '{arg.arg}' in '{context}' missing type"
                )

        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit async function definition"""
        self.visit_FunctionDef(node)


def analyze_file(file_path: Path) -> TypeHintStats:
    """Analyze a single Python file for type hints"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=str(file_path))

        checker = TypeHintChecker(file_path)
        checker.visit(tree)
        return checker.stats
    except Exception as e:
        print(f"Error analyzing {file_path}: {e}")
        return TypeHintStats(file_path)


def find_python_files(root_dir: Path, exclude_dirs: List[str] = None) -> List[Path]:
    """Find all Python files in directory"""
    if exclude_dirs is None:
        exclude_dirs = ['tests', '__pycache__', '.pytest_cache', 'venv', '.venv']

    python_files = []
    for path in root_dir.rglob('*.py'):
        # Skip excluded directories
        if any(excl in path.parts for excl in exclude_dirs):
            continue
        python_files.append(path)

    return sorted(python_files)


def main():
    """Main entry point"""
    script_dir = Path(__file__).parent

    print("=" * 80)
    print("TYPE HINTS COVERAGE ANALYSIS (P1-12)")
    print("=" * 80)
    print()

    # Find all Python files
    python_files = find_python_files(script_dir)
    print(f"Found {len(python_files)} Python files to analyze\n")

    # Analyze each file
    all_stats = []
    for file_path in python_files:
        stats = analyze_file(file_path)
        all_stats.append(stats)

    # Sort by coverage (worst first)
    all_stats.sort(key=lambda s: s.overall_coverage)

    # Print summary
    print("=" * 80)
    print("FILES WITH INCOMPLETE TYPE HINTS (sorted by coverage)")
    print("=" * 80)
    print()

    files_needing_attention = []
    for stats in all_stats:
        if stats.overall_coverage < 100.0:
            files_needing_attention.append(stats)
            rel_path = stats.file_path.relative_to(script_dir)

            print(f"📄 {rel_path}")
            print(f"   Overall Coverage: {stats.overall_coverage:.1f}%")
            print(f"   Functions: {stats.functions_with_return_type}/{stats.total_functions} "
                  f"({stats.function_coverage:.1f}%)")
            print(f"   Parameters: {stats.parameters_with_type}/{stats.total_parameters} "
                  f"({stats.parameter_coverage:.1f}%)")

            if stats.missing_hints:
                print(f"   Missing type hints ({len(stats.missing_hints)}):")
                # Show first 5 issues
                for hint in stats.missing_hints[:5]:
                    print(hint)
                if len(stats.missing_hints) > 5:
                    print(f"   ... and {len(stats.missing_hints) - 5} more")
            print()

    if not files_needing_attention:
        print("✅ All files have complete type hint coverage!")
    else:
        print(f"\n⚠️  {len(files_needing_attention)} files need type hint improvements")

    # Overall statistics
    print("\n" + "=" * 80)
    print("OVERALL STATISTICS")
    print("=" * 80)

    total_functions = sum(s.total_functions for s in all_stats)
    total_functions_typed = sum(s.functions_with_return_type for s in all_stats)
    total_parameters = sum(s.total_parameters for s in all_stats)
    total_parameters_typed = sum(s.parameters_with_type for s in all_stats)

    overall_function_coverage = (total_functions_typed / total_functions * 100) if total_functions > 0 else 100.0
    overall_parameter_coverage = (total_parameters_typed / total_parameters * 100) if total_parameters > 0 else 100.0
    overall_coverage = ((total_functions_typed + total_parameters_typed) /
                       (total_functions + total_parameters) * 100) if (total_functions + total_parameters) > 0 else 100.0

    print(f"Total Files: {len(all_stats)}")
    print(f"Total Functions: {total_functions}")
    print(f"Functions with Return Type: {total_functions_typed} ({overall_function_coverage:.1f}%)")
    print(f"Total Parameters: {total_parameters}")
    print(f"Parameters with Type: {total_parameters_typed} ({overall_parameter_coverage:.1f}%)")
    print(f"\n📊 Overall Type Hint Coverage: {overall_coverage:.1f}%")

    # Set exit code based on coverage
    if overall_coverage < 100.0:
        print(f"\n⚠️  Type hint coverage is below 100%. Target: 100%")
        sys.exit(1)
    else:
        print(f"\n✅ Type hint coverage meets 100% target!")
        sys.exit(0)


if __name__ == "__main__":
    main()
