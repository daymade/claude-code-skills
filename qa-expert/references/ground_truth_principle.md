# Ground Truth Principle - Preventing Documentation Sync Issues

**Purpose**: Prevent test suite integrity problems caused by documentation/tracking file mismatches.

**Lesson Learned**: CCPM project discovered 3.2% consistency rate between CSV and documentation (only 3 out of 93 test IDs matched correctly).

---

## The Problem

### Common Anti-Pattern
Projects often have multiple sources of truth:
- Test case documentation (e.g., `02-CLI-TEST-CASES.md`)
- Execution tracking CSV (e.g., `TEST-EXECUTION-TRACKING.csv`)
- Bug tracking spreadsheet
- Test automation code

**What goes wrong**:
1. Documentation updated → CSV not updated
2. CSV auto-generated from old test list → docs finalized separately
3. Tests executed based on CSV → wrong test steps followed
4. Bug reports reference CSV IDs → cannot trace back to correct test

### Real Example from CCPM

**CSV TC-CLI-012**: "Install Non-Existent Skill"
- Steps: Run `ccpm install this-skill-does-not-exist-12345`
- Expected: Clear error message

**Doc TC-CLI-012**: "Install Skill Already Installed"
- Steps: Run `ccpm install cloudflare-troubleshooting` (already installed)
- Expected: Warning message with --force hint

**Result**: Completely different tests! QA engineer might execute wrong test and report incorrect results.

---

## The Ground Truth Principle

### Rule #1: Single Source of Truth

**Declare one file as authoritative** for test specifications:

```
✅ CORRECT:
Ground Truth: 02-CLI-TEST-CASES.md (detailed test specifications)
Supporting: TEST-EXECUTION-TRACKING.csv (execution status only)

❌ WRONG:
CSV and docs both contain test steps (divergence inevitable)
```

### Rule #2: Clear Role Separation

| File Type | Purpose | Contains | Updated When |
|-----------|---------|----------|--------------|
| **Test Case Docs** | Specification | Prerequisites, Steps, Expected Results, Pass/Fail Criteria | When test design changes |
| **Tracking CSV** | Execution tracking | Status, Result, Bug ID, Execution Date, Notes | After each test execution |
| **Bug Reports** | Failure documentation | Repro steps, Environment, Severity, Resolution | When test fails |

### Rule #3: Explicit References

Always specify which file to use in instructions:

**Good**:
```markdown
Execute test case TC-CLI-042:
1. Read full test specification from 02-CLI-TEST-CASES.md (pages 15-16)
2. Follow steps exactly as documented
3. Update TEST-EXECUTION-TRACKING.csv row TC-CLI-042 with result
```

**Bad**:
```markdown
Execute test case TC-CLI-042 (no reference to source document)
```

---

## Prevention Strategies

### Strategy 1: Automated ID Validation

**Script**: `validate_test_ids.py` (generate this in your project)

```python
#!/usr/bin/env python3
"""Validate test IDs between documentation and CSV"""

import csv
import re
from pathlib import Path

def extract_doc_ids(doc_path):
    """Extract all TC-XXX-YYY IDs from markdown documentation"""
    with open(doc_path, 'r') as f:
        content = f.read()
    pattern = r'TC-[A-Z]+-\d{3}'
    return set(re.findall(pattern, content))

def extract_csv_ids(csv_path):
    """Extract all Test Case IDs from CSV"""
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        return set(row['Test Case ID'] for row in reader if row['Test Case ID'])

def validate_sync(doc_path, csv_path):
    """Check consistency between doc and CSV"""
    doc_ids = extract_doc_ids(doc_path)
    csv_ids = extract_csv_ids(csv_path)

    matching = doc_ids & csv_ids
    csv_only = csv_ids - doc_ids
    doc_only = doc_ids - csv_ids

    consistency_rate = len(matching) / len(csv_ids) * 100 if csv_ids else 0

    print(f"\n{'='*60}")
    print(f"Test ID Validation Report")
    print(f"{'='*60}\n")
    print(f"✅ Matching IDs:     {len(matching)}")
    print(f"⚠️  CSV-only IDs:     {len(csv_only)}")
    print(f"⚠️  Doc-only IDs:     {len(doc_only)}")
    print(f"\n📊 Consistency Rate: {consistency_rate:.1f}%\n")

    if consistency_rate < 100:
        print(f"❌ SYNC ISSUE DETECTED!\n")
        if csv_only:
            print(f"CSV IDs not in documentation: {sorted(csv_only)[:5]}")
        if doc_only:
            print(f"Doc IDs not in CSV: {sorted(doc_only)[:5]}")
    else:
        print(f"✅ Perfect sync!\n")

    return consistency_rate >= 95

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python validate_test_ids.py <doc-path> <csv-path>")
        sys.exit(1)

    doc_path = sys.argv[1]
    csv_path = sys.argv[2]

    valid = validate_sync(doc_path, csv_path)
    sys.exit(0 if valid else 1)
```

**Usage**:
```bash
python <your-project>/scripts/validate_test_ids.py \
  tests/docs/02-CLI-TEST-CASES.md \
  tests/docs/templates/TEST-EXECUTION-TRACKING.csv

# Output:
# ============================================================
# Test ID Validation Report
# ============================================================
#
# ✅ Matching IDs:     3
# ⚠️  CSV-only IDs:     90
# ⚠️  Doc-only IDs:     0
#
# 📊 Consistency Rate: 3.2%
#
# ❌ SYNC ISSUE DETECTED!
```

### Strategy 2: ID Mapping Document

When mismatch detected, create bridge document:

**File**: `tests/docs/TEST-ID-MAPPING.md`

**Contents**:
```markdown
# Test ID Mapping - CSV vs. Documentation

## Ground Truth
**Official Source**: 02-CLI-TEST-CASES.md
**Tracking File**: TEST-EXECUTION-TRACKING.csv (execution tracking only)

## ID Mapping Table
| CSV ID | Doc ID | Test Name | Match Status |
|--------|--------|-----------|--------------|
| TC-CLI-001 | TC-CLI-001 | Install Skill by Name | ✅ Match |
| TC-CLI-012 | TC-CLI-008 | Install Non-Existent Skill | ❌ Mismatch |
```

### Strategy 3: CSV Usage Guide

Create explicit instructions for QA engineers:

**File**: `tests/docs/templates/CSV-USAGE-GUIDE.md`

**Contents**:
```markdown
# TEST-EXECUTION-TRACKING.csv Usage Guide

## ✅ Correct Usage

1. **ALWAYS use test case documentation** as authoritative source for:
   - Test steps
   - Expected results
   - Prerequisites

2. **Use this CSV ONLY for**:
   - Tracking execution status
   - Recording results (PASSED/FAILED)
   - Linking to bug reports

## ❌ Don't Trust CSV for Test Specifications
```

---

## Recovery Workflow

When you discover a sync issue:

### Step 1: Assess Severity
```bash
# Run ID validation script
python <your-project>/scripts/validate_test_ids.py <doc> <csv>

# Consistency Rate:
#   100%:   ✅ No action needed
#   90-99%: ⚠️  Minor fixes needed
#   50-89%: 🔴 Major sync required
#   <50%:   🚨 CRITICAL - regenerate CSV
```

### Step 2: Create Bridge Documents
```bash
# If consistency < 100%, create:
1. TEST-ID-MAPPING.md (maps CSV → Doc IDs)
2. CSV-USAGE-GUIDE.md (instructs QA engineers)
```

### Step 3: Notify Team
```markdown
Subject: [URGENT] Test Suite Sync Issue - Read Before Testing

Team,

We discovered a test ID mismatch between CSV and documentation:
- Consistency Rate: 3.2% (only 3 out of 93 tests match)
- Impact: Tests executed based on CSV may use wrong steps
- Action Required: Read CSV-USAGE-GUIDE.md before continuing

Ground Truth: 02-CLI-TEST-CASES.md (always trust this)
Tracking Only: TEST-EXECUTION-TRACKING.csv

Bridge: TEST-ID-MAPPING.md (maps IDs)
```

### Step 4: Re-validate Executed Tests
```markdown
Tests executed before fix may need re-verification:
- TC-CLI-001~003: ✅ Correct (IDs matched)
- TC-CLI-029: ⚠️  Verify against Doc TC-CLI-029
- TC-CLI-037: ⚠️  Verify against Doc TC-CLI-037
```

### Step 5: Long-Term Fix
**Option A**: Maintain separation (recommended during active testing)
- CSV = execution tracking only
- Doc = test specifications
- Mapping doc bridges gap

**Option B**: Regenerate CSV from docs (post-testing)
- Risk: Loss of execution history
- Benefit: Perfect sync
- Timeline: After current test cycle

---

## Best Practices

### DO ✅

1. **Declare ground truth upfront** in project README
2. **Separate concerns**: Specs vs. tracking vs. bugs
3. **Validate IDs regularly** (weekly or before major milestones)
4. **Document deviations** in mapping file
5. **Train QA team** on ground truth principle

### DON'T ❌

1. ❌ Duplicate test steps in multiple files
2. ❌ Auto-generate tracking files without validation
3. ❌ Execute tests based on CSV alone
4. ❌ Assume "it's just tracking" - IDs matter!
5. ❌ Ignore small mismatches (3% → 50% quickly)

---

## Checklist for QA Project Setup

When using `init_qa_project.py`, ensure:

- [ ] Ground truth declared in README
- [ ] CSV contains ID + tracking fields only (no detailed steps)
- [ ] Test case docs are complete before CSV generation
- [ ] ID validation script added to project
- [ ] CSV usage guide included in templates/
- [ ] QA engineers trained on which file to trust

---

## Integration with qa-expert Skill

When initializing a project with `qa-expert`:

```bash
python scripts/init_qa_project.py my-app ./

# This creates:
tests/docs/
  ├── README.md                        (declares ground truth)
  ├── 02-CLI-TEST-CASES.md            (authoritative specs)
  ├── TEST-ID-MAPPING.md              (if needed)
  └── templates/
      ├── TEST-EXECUTION-TRACKING.csv (tracking only)
      ├── CSV-USAGE-GUIDE.md          (usage instructions)
      └── validate_test_ids.py        (validation script)
```

---

## Success Criteria

**Your test suite has good integrity when**:
- ✅ ID consistency rate ≥ 95%
- ✅ QA engineers know which file to trust
- ✅ Tracking CSV contains status only (no steps)
- ✅ Validation script runs weekly
- ✅ Team trained on ground truth principle

**Red flags**:
- 🚩 Multiple files contain test steps
- 🚩 CSV test names differ from docs
- 🚩 QA engineers "prefer" CSV over docs
- 🚩 No one knows which file is authoritative
- 🚩 Test IDs diverge over time

---

**Document Version**: 1.0
**Created**: 2025-11-10
**Based On**: CCPM test suite integrity incident (3.2% consistency rate)
**Priority**: 🔴 P0 (Critical for test suite quality)
