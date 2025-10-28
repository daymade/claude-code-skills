#!/usr/bin/env python3
"""
Security Scanner for Claude Code Skills
Validates skills before packaging to prevent secret leakage and security issues.

SINGLE RESPONSIBILITY: Validate skill security before distribution
ARCHITECTURE:
  - Detection Layer: Gitleaks (secrets) + Pattern matching (code smells)
  - Reporting Layer: Simple mode (gate) / Verbose mode (educational)
  - Action Layer: Creates .security-scan-passed marker on clean scan

USAGE:
  python security_scan.py <skill-dir>              # Quick scan (required for packaging)
  python security_scan.py <skill-dir> --verbose    # Detailed educational review
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import shutil
import tempfile
import argparse
import hashlib
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from dataclasses import dataclass

# ANSI color codes
RED = '\033[91m'
YELLOW = '\033[93m'
GREEN = '\033[92m'
BLUE = '\033[94m'
RESET = '\033[0m'


@dataclass
class SecurityIssue:
    """Represents a security issue found during scan"""
    severity: str  # CRITICAL, HIGH, MEDIUM
    category: str  # secrets, paths, emails, code_patterns
    file_path: str
    line_number: int
    pattern_name: str
    message: str
    matched_text: str
    recommendation: str


# ============================================================================
# DETECTION LAYER - What to scan for
# ============================================================================

def get_pattern_rules() -> List[Dict]:
    """
    Define regex-based security patterns
    Used when --verbose flag is set for educational review

    NOTE: Patterns below are for DETECTION only, not usage
    """
    return [
        {
            "id": "absolute_user_paths",
            "category": "paths",
            "name": "Absolute User Paths",
            "patterns": [
                r'/[Hh]ome/[a-z_][a-z0-9_-]+/',
                r'/[Uu]sers/[A-Za-z][A-Za-z0-9_-]+/',
                r'C:\\\\Users\\\\[A-Za-z][A-Za-z0-9_-]+\\\\',
            ],
            "severity": "HIGH",
            "message": "Absolute path with username found",
            "recommendation": "Use relative paths or Path(__file__).parent",
        },
        {
            "id": "email_addresses",
            "category": "emails",
            "name": "Email Addresses",
            "patterns": [r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'],
            "severity": "MEDIUM",
            "message": "Email address found",
            "recommendation": "Use placeholders like user@example.com",
            "exceptions": ["example.com", "test.com", "localhost", "noreply@anthropic.com"],
        },
        {
            "id": "insecure_http",
            "category": "urls",
            "name": "Insecure HTTP URLs",
            "patterns": [r'http://(?!localhost|127\.0\.0\.1|0\.0\.0\.0|example\.com)'],
            "severity": "MEDIUM",
            "message": "HTTP (insecure) URL detected",
            "recommendation": "Use HTTPS for external resources",
        },
        {
            "id": "dangerous_code",
            "category": "code_patterns",
            "name": "Dangerous Code Patterns",
            "patterns": [
                r'\bos\.system\s*\(',
                r'subprocess\.[a-z_]+\([^)]*shell\s*=\s*True',
                # Pattern below detects unsafe serialization (for detection only)
                r'import\s+pickle',
                r'pickle\.load',
            ],
            "severity": "HIGH",
            "message": "Potentially dangerous code pattern",
            "recommendation": "Use safe alternatives (subprocess.run with list args, JSON instead of unsafe serialization)",
        },
    ]


def check_gitleaks_installed() -> bool:
    """Check if gitleaks is available"""
    return shutil.which('gitleaks') is not None


def print_gitleaks_installation() -> None:
    """Print gitleaks installation instructions"""
    print(f"\n{YELLOW}⚠️  gitleaks not installed{RESET}")
    print(f"\ngitleaks is the industry-standard tool for detecting secrets.")
    print(f"It's used by GitHub, GitLab, and thousands of companies.\n")
    print(f"{BLUE}Installation:{RESET}")
    print(f"  macOS:     brew install gitleaks")
    print(f"  Linux:     wget https://github.com/gitleaks/gitleaks/releases/download/v8.18.2/gitleaks_8.18.2_linux_x64.tar.gz")
    print(f"             tar -xzf gitleaks_8.18.2_linux_x64.tar.gz && sudo mv gitleaks /usr/local/bin/")
    print(f"  Windows:   scoop install gitleaks")
    print(f"\nAfter installation, run this script again.\n")


def run_gitleaks(skill_path: Path) -> Optional[List[Dict]]:
    """
    Run gitleaks scan on skill directory
    Returns: List of findings, empty list if clean, None on error
    """
    try:
        # Use temporary file for cross-platform compatibility (Windows doesn't have /dev/stdout)
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False) as tmp_file:
            tmp_path = tmp_file.name

        try:
            result = subprocess.run(
                ['gitleaks', 'detect', '--source', str(skill_path),
                 '--report-format', 'json', '--report-path', tmp_path, '--no-git'],
                capture_output=True,
                text=True,
                timeout=60
            )

            # gitleaks exits with 1 if secrets found, 0 if clean
            if result.returncode == 0:
                return []

            # Parse findings from temp file
            with open(tmp_path, 'r', encoding='utf-8') as f:
                return json.load(f)

        finally:
            Path(tmp_path).unlink(missing_ok=True)

    except subprocess.TimeoutExpired:
        print(f"{RED}❌ Error: gitleaks scan timed out{RESET}", file=sys.stderr)
        return None
    except json.JSONDecodeError:
        print(f"{RED}❌ Error: Could not parse gitleaks output{RESET}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"{RED}❌ Error running gitleaks: {e}{RESET}", file=sys.stderr)
        return None


def scan_file_patterns(file_path: Path, patterns: List[Dict]) -> List[SecurityIssue]:
    """
    Scan a single file using regex patterns
    Used for verbose mode educational review
    """
    issues = []

    try:
        content = file_path.read_text(encoding='utf-8')
        lines = content.split('\n')

        for line_num, line in enumerate(lines, 1):
            for pattern_def in patterns:
                for regex in pattern_def["patterns"]:
                    matches = re.finditer(regex, line, re.IGNORECASE)
                    for match in matches:
                        matched_text = match.group(0)

                        # Check exceptions
                        if "exceptions" in pattern_def:
                            if any(exc in matched_text for exc in pattern_def["exceptions"]):
                                continue

                        issues.append(SecurityIssue(
                            severity=pattern_def["severity"],
                            category=pattern_def["category"],
                            file_path=str(file_path.relative_to(file_path.parent.parent)),
                            line_number=line_num,
                            pattern_name=pattern_def["name"],
                            message=pattern_def["message"],
                            matched_text=matched_text[:80],
                            recommendation=pattern_def["recommendation"],
                        ))

    except (UnicodeDecodeError, IOError):
        pass

    return issues


def scan_skill_patterns(skill_path: Path) -> tuple[List[SecurityIssue], Dict[str, int]]:
    """
    Scan all files in skill directory using regex patterns
    Returns: (issues list, severity stats dict)
    """
    patterns = get_pattern_rules()
    all_issues = []
    stats = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0}

    code_extensions = {'.py', '.js', '.ts', '.jsx', '.tsx', '.sh', '.bash',
                       '.md', '.yml', '.yaml', '.json', '.toml'}

    for file_path in skill_path.rglob('*'):
        if not file_path.is_file() or file_path.suffix not in code_extensions:
            continue
        if any(part.startswith('.') for part in file_path.parts):
            continue
        if '__pycache__' in file_path.parts or 'node_modules' in file_path.parts:
            continue

        issues = scan_file_patterns(file_path, patterns)
        for issue in issues:
            all_issues.append(issue)
            stats[issue.severity] += 1

    return all_issues, stats


def categorize_gitleaks_severity(rule_id: str) -> str:
    """Categorize gitleaks finding severity"""
    critical_patterns = ['api', 'key', 'token', 'password', 'secret', 'credential']
    if any(pattern in rule_id.lower() for pattern in critical_patterns):
        return "CRITICAL"
    return "HIGH"


# ============================================================================
# REPORTING LAYER - How to present findings
# ============================================================================

def print_simple_report(gitleaks_findings: List[Dict], skill_name: str) -> int:
    """
    Simple report for packaging workflow (exit code matters)
    Returns: Exit code (0=clean, 2=critical, 1=high)
    """
    if not gitleaks_findings:
        print(f"{GREEN}✅ Security scan passed: No secrets detected{RESET}")
        return 0

    critical_count = sum(1 for f in gitleaks_findings
                        if categorize_gitleaks_severity(f.get('RuleID', '')) == 'CRITICAL')

    print(f"\n{RED}❌ Security scan FAILED: {len(gitleaks_findings)} issue(s) found{RESET}")
    print(f"   {RED}Critical: {critical_count}{RESET}")
    print(f"   {YELLOW}High: {len(gitleaks_findings) - critical_count}{RESET}\n")

    print(f"{RED}BLOCKING ISSUES:{RESET}")
    for finding in gitleaks_findings[:5]:  # Show first 5
        file_path = finding.get('File', 'unknown')
        line = finding.get('StartLine', '?')
        rule_id = finding.get('RuleID', 'unknown')
        print(f"  • {file_path}:{line} - {rule_id}")

    if len(gitleaks_findings) > 5:
        print(f"  ... and {len(gitleaks_findings) - 5} more\n")

    print(f"{RED}REQUIRED ACTIONS:{RESET}")
    print(f"  1. Remove all hardcoded secrets from code")
    print(f"  2. Use environment variables: os.environ.get('KEY_NAME')")
    print(f"  3. Re-run scan after fixes\n")

    return 2 if critical_count > 0 else 1


def print_verbose_report(gitleaks_findings: List[Dict], pattern_issues: List[SecurityIssue],
                        pattern_stats: Dict[str, int], skill_name: str) -> int:
    """
    Detailed educational report with explanations
    Returns: Exit code (0=clean, 2=critical, 1=high)
    """
    print(f"\n{'=' * 80}")
    print(f"🔒 Security Review Report: {skill_name}")
    print(f"{'=' * 80}\n")

    # Section 1: Gitleaks findings (secrets)
    if gitleaks_findings:
        critical_count = sum(1 for f in gitleaks_findings
                            if categorize_gitleaks_severity(f.get('RuleID', '')) == 'CRITICAL')

        print(f"📊 Secret Detection (via gitleaks):")
        print(f"  {RED}🔴 CRITICAL: {critical_count}{RESET} (API keys, passwords, tokens)")
        print(f"  {YELLOW}🟠 HIGH: {len(gitleaks_findings) - critical_count}{RESET} (Other secrets)")
        print(f"  Total: {len(gitleaks_findings)}\n")

        for finding in gitleaks_findings:
            severity = categorize_gitleaks_severity(finding.get('RuleID', ''))
            color = RED if severity == "CRITICAL" else YELLOW
            file_path = finding.get('File', 'unknown')
            line = finding.get('StartLine', '?')
            rule_id = finding.get('RuleID', 'unknown')
            description = finding.get('Description', 'No description')

            print(f"{color}[{severity}]{RESET} {file_path}:{line}")
            print(f"  Rule: {rule_id}")
            print(f"  {description}\n")
    else:
        print(f"{GREEN}✅ Secret Detection: Clean{RESET}\n")

    # Section 2: Pattern-based findings
    if pattern_issues:
        print(f"📊 Code Quality & Security Patterns:")
        print(f"  {YELLOW}🟠 HIGH: {pattern_stats['HIGH']}{RESET}")
        print(f"  🟡 MEDIUM: {pattern_stats['MEDIUM']}")
        print(f"  Total: {sum(pattern_stats.values())}\n")

        for severity in ["HIGH", "MEDIUM"]:
            severity_issues = [i for i in pattern_issues if i.severity == severity]
            if severity_issues:
                color = YELLOW if severity == "HIGH" else RESET
                print(f"{color}{severity} Issues ({len(severity_issues)}):{RESET}")
                print("─" * 80)
                for issue in severity_issues[:10]:  # Limit to 10 per severity
                    print(f"\n{color}[{issue.severity}]{RESET} {issue.file_path}:{issue.line_number}")
                    print(f"  Issue: {issue.pattern_name}")
                    print(f"  {issue.message}")
                    print(f"  Matched: {issue.matched_text}")
                    print(f"  Fix: {issue.recommendation}")
                if len(severity_issues) > 10:
                    print(f"\n  ... and {len(severity_issues) - 10} more {severity} issues")
                print()
    else:
        print(f"{GREEN}✅ Code Patterns: Clean{RESET}\n")

    # Summary
    print(f"{'=' * 80}")
    has_critical = any(categorize_gitleaks_severity(f.get('RuleID', '')) == 'CRITICAL'
                       for f in gitleaks_findings)
    has_high = len(gitleaks_findings) > 0 or pattern_stats['HIGH'] > 0

    if has_critical:
        print(f"{RED}🔴 CRITICAL issues MUST be fixed before distribution{RESET}")
        exit_code = 2
    elif has_high:
        print(f"{YELLOW}🟠 HIGH issues SHOULD be fixed before distribution{RESET}")
        exit_code = 1
    else:
        print(f"{GREEN}✅ No critical security issues found!{RESET}")
        exit_code = 0

    print(f"{'=' * 80}\n")
    return exit_code


# ============================================================================
# ACTION LAYER - What to do with results
# ============================================================================

def calculate_skill_hash(skill_path: Path) -> str:
    """
    Calculate deterministic hash of all security-relevant files in skill
    Returns: SHA256 hex digest of combined file contents

    Implementation:
    - Scans same file types as security scanner (code_extensions)
    - Sorts files deterministically by path
    - Hashes concatenated content (path + content for each file)
    - Ignores .security-scan-passed itself and hidden files
    """
    code_extensions = {'.py', '.js', '.ts', '.jsx', '.tsx', '.sh', '.bash',
                       '.md', '.yml', '.yaml', '.json', '.toml'}

    hasher = hashlib.sha256()

    # Collect all relevant files
    files_to_hash = []
    for file_path in skill_path.rglob('*'):
        if not file_path.is_file() or file_path.suffix not in code_extensions:
            continue
        if file_path.name == '.security-scan-passed':
            continue
        if any(part.startswith('.') for part in file_path.parts):
            continue
        if '__pycache__' in file_path.parts or 'node_modules' in file_path.parts:
            continue
        files_to_hash.append(file_path)

    # Sort for deterministic order
    files_to_hash.sort()

    # Hash each file (path + content)
    for file_path in files_to_hash:
        try:
            # Include relative path in hash for file rename detection
            rel_path = file_path.relative_to(skill_path)
            hasher.update(str(rel_path).encode('utf-8'))
            hasher.update(b'\0')  # Null separator

            # Include file content
            content = file_path.read_bytes()
            hasher.update(content)
            hasher.update(b'\0')  # Null separator
        except (IOError, UnicodeDecodeError):
            # Skip files that can't be read
            pass

    return hasher.hexdigest()


def create_security_marker(skill_path: Path) -> None:
    """
    Create marker file indicating security scan passed
    Includes content-based hash for validation
    """
    marker_file = skill_path / ".security-scan-passed"
    content_hash = calculate_skill_hash(skill_path)

    marker_file.write_text(
        f"Security scan passed\n"
        f"Scanned at: {datetime.now().isoformat()}\n"
        f"Tool: gitleaks + pattern-based validation\n"
        f"Content hash: {content_hash}\n"
    )
    print(f"{GREEN}✓ Security marker created: {marker_file.name}{RESET}")


# ============================================================================
# MAIN ORCHESTRATION
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Security scanner for Claude Code skills",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python security_scan.py ../my-skill              # Quick scan (for packaging)
  python security_scan.py ../my-skill --verbose    # Detailed educational review

Exit codes:
  0 - Clean (no issues)
  1 - High severity issues found
  2 - Critical issues found (MUST fix)
  3 - gitleaks not installed
  4 - Scan error
        """
    )
    parser.add_argument("skill_dir", help="Path to skill directory")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Show detailed educational review with pattern-based checks")

    args = parser.parse_args()

    # Validate skill directory
    skill_path = Path(args.skill_dir).resolve()
    if not skill_path.exists():
        print(f"{RED}❌ Error: Skill directory not found: {skill_path}{RESET}")
        sys.exit(1)
    if not skill_path.is_dir():
        print(f"{RED}❌ Error: Path is not a directory: {skill_path}{RESET}")
        sys.exit(1)

    # Check gitleaks availability
    if not check_gitleaks_installed():
        print_gitleaks_installation()
        sys.exit(3)

    # Run gitleaks scan (always)
    print(f"🔍 Scanning: {skill_path.name}")
    print(f"   Tool: gitleaks (industry standard)")
    print(f"   Mode: {'verbose (educational)' if args.verbose else 'simple (packaging gate)'}")
    gitleaks_findings = run_gitleaks(skill_path)

    if gitleaks_findings is None:
        sys.exit(4)

    # Run pattern-based scan (only in verbose mode)
    pattern_issues = []
    pattern_stats = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0}
    if args.verbose:
        print(f"   Running pattern-based checks...")
        pattern_issues, pattern_stats = scan_skill_patterns(skill_path)

    # Generate report
    if args.verbose:
        exit_code = print_verbose_report(gitleaks_findings, pattern_issues,
                                         pattern_stats, skill_path.name)
    else:
        exit_code = print_simple_report(gitleaks_findings, skill_path.name)

    # Create marker file on clean scan
    if exit_code == 0:
        create_security_marker(skill_path)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
