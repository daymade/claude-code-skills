#!/usr/bin/env python3
"""
Initialize QA Project Structure

Creates QA directories, documentation templates and example tracking CSVs.
Use a fresh project root: generated template files are overwritten.

Usage:
    python scripts/init_qa_project.py <project-name> [output-dir]

Example:
    python scripts/init_qa_project.py my-app ./
"""

import sys
import csv
from pathlib import Path
from datetime import datetime

def create_directory_structure(base_path):
    """Create QA project directory structure."""
    dirs = [
        "tests/docs",
        "tests/docs/templates",
        "tests/e2e",
        "tests/fixtures"
    ]

    for dir_path in dirs:
        full_path = base_path / dir_path
        full_path.mkdir(parents=True, exist_ok=True)
        print(f"✅ Created: {full_path}")

def create_test_execution_tracking(base_path, project_name):
    """Create TEST-EXECUTION-TRACKING.csv with headers."""
    csv_path = base_path / "tests/docs/templates/TEST-EXECUTION-TRACKING.csv"

    headers = [
        "Test Case ID", "Category", "Priority", "Test Name",
        "Estimated Time (min)", "Prerequisites", "Status",
        "Result", "Bug ID", "Execution Date", "Executed By",
        "Notes", "Screenshot/Log"
    ]

    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        # Add example row
        writer.writerow([
            "TC-001", "Core", "P0", "Example Test Case",
            "5", "System running", "Not Started", "", "", "", "",
            "Replace with actual test cases", ""
        ])

    print(f"✅ Created: {csv_path}")

def create_bug_tracking_template(base_path):
    """Create BUG-TRACKING-TEMPLATE.csv."""
    csv_path = base_path / "tests/docs/templates/BUG-TRACKING-TEMPLATE.csv"

    headers = [
        "Bug ID", "Title", "Severity", "Component", "Test Case ID",
        "Status", "Reported Date", "Reported By", "Assigned To",
        "Description", "Steps to Reproduce", "Expected Result",
        "Actual Result", "Environment", "Screenshots/Logs",
        "Resolution", "Resolved Date", "Verified By", "Verification Date"
    ]

    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        # Add example bug
        writer.writerow([
            "BUG-001", "Example Bug Title", "P1", "Component",
            "TC-001", "Open", datetime.now().strftime("%Y-%m-%d"),
            "QA Engineer", "Engineering Lead",
            "Description of the bug", "1. Step 1\n2. Step 2",
            "Expected behavior", "Actual behavior",
            "OS: macOS\nNode.js: v18.0.0", "",
            "", "", "", ""
        ])

    print(f"✅ Created: {csv_path}")

def create_baseline_metrics(base_path, project_name):
    """Create BASELINE-METRICS.md template."""
    content = f"""# Baseline Evidence - {project_name}

Record the actual observation date and immutable evidence before QA execution.
Template creation is not a baseline measurement. Leave unmeasured fields unknown.

## Test and coverage evidence

- Unit, integration and E2E runner commands, source ref and raw output: [locators]
- Coverage report and its measured dimensions: [locator]
- Tested browsers/runtime: [observed environment]

## Known issues and technical debt

- Issue/debt record and reproduction evidence: [locators]

## Security evidence

- Project security policy and applicable OWASP cases: [locators]
- Observed mitigation results and untested categories: [evidence]

## Performance and code quality

- Workload, environment and raw timing measurements: [locators]
- Lint/typecheck/static-analysis commands and output: [locators]

## Hypotheses to test

- Suspected issue, evidence, proposed case ID and verification: [details]

Compute aggregate totals from the original test/bug/coverage records when needed.
Do not maintain a parallel live summary here. Preserve historical observations by
binding their actual date, source ref and raw evidence.
"""

    file_path = base_path / "tests/docs/BASELINE-METRICS.md"
    with open(file_path, 'w') as f:
        f.write(content)

    print(f"✅ Created: {file_path}")

def create_weekly_report_template(base_path):
    """Create WEEKLY-PROGRESS-REPORT.md template."""
    content = """# Weekly QA Progress Report

**Reporting period**: [actual start/end dates]
**Project / responsible engineer**: [identity]

## Evidence

- Immutable test execution and bug records for this period: [locators]
- Coverage/security/performance evidence: [locators or unknown]
- Baseline evidence used for comparison: [locator]
- Authoritative project release policy: [locator]

Calculate progress, pass rates and bug totals from those records at report time.
Keep aggregates in the generated report output when needed, not hand-maintained
counter tables. A dated report is an observation of that period, not live status.

## Findings and acceptance

- Reproduced bug ID, impact and evidence: [details]
- Acceptance decision under the project policy, including unmeasured criteria:
  [decision and evidence]
- Change since baseline supported by the original measurements: [details]

## Blockers and risks

- Blocked prerequisite or case ID, effect and recovery condition: [details]
- Unverified hypothesis and next probe: [details]

## Next authorized batch

- Case IDs and prerequisites: [details]
- Planned work and project schedule: [details]
"""

    file_path = base_path / "tests/docs/templates/WEEKLY-PROGRESS-REPORT.md"
    with open(file_path, 'w') as f:
        f.write(content)

    print(f"✅ Created: {file_path}")

def create_master_qa_prompt(base_path, project_name):
    """Create MASTER-QA-PROMPT.md for autonomous execution."""
    canonical = Path(__file__).resolve().parents[1] / "references/master_qa_prompt.md"
    content = f"# QA execution for {project_name}\n\n" + canonical.read_text(encoding="utf-8")

    file_path = base_path / "tests/docs/MASTER-QA-PROMPT.md"
    with open(file_path, 'w') as f:
        f.write(content)

    print(f"✅ Created: {file_path}")

def create_readme(base_path, project_name):
    """Create README.md for QA docs."""
    content = f"""# QA Documentation - {project_name}

Initialization created templates. Test execution readiness has not been verified.

## Prepare before execution

1. Replace example CSV rows with actual case/bug records; examples are not evidence.
2. Supply the project's current strategy, test specifications and harness commands.
   Handover and onboarding documents must be supplied when the project needs them;
   they are not generated by this initializer.
3. Verify the authorized environment and synthetic fixtures. Record dated baseline
   evidence using [BASELINE-METRICS.md](BASELINE-METRICS.md).
4. Follow [MASTER-QA-PROMPT.md](MASTER-QA-PROMPT.md) for agent execution and recovery,
   or execute the same test specifications manually and track each result.

## Generated files

- [Execution tracking CSV](templates/TEST-EXECUTION-TRACKING.csv)
- [Bug tracking CSV](templates/BUG-TRACKING-TEMPLATE.csv)
- [Weekly report template](templates/WEEKLY-PROGRESS-REPORT.md)
- [Baseline evidence template](BASELINE-METRICS.md)
- [QA execution SOP](MASTER-QA-PROMPT.md)

Use the loaded qa-expert Skill's metrics command to calculate current results.
The target project's release policy owns acceptance; generated templates do not
prove there are no blockers. Future execution needs an authorized active runner.

Do not rerun initialization over populated files: it overwrites the templates.
"""

    file_path = base_path / "tests/docs/README.md"
    with open(file_path, 'w') as f:
        f.write(content)

    print(f"✅ Created: {file_path}")

def main():
    if len(sys.argv) < 2:
        print("❌ Error: Project name required")
        print("Usage: python init_qa_project.py <project-name> [output-dir]")
        sys.exit(1)

    project_name = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "."

    base_path = Path(output_dir).resolve()

    print(f"\n🚀 Initializing QA Project: {project_name}")
    print(f"   Location: {base_path}\n")

    # Fail before creating outputs if the bundled canonical SOP is unavailable.
    canonical = Path(__file__).resolve().parents[1] / "references/master_qa_prompt.md"
    canonical.read_text(encoding="utf-8")

    # Create directory structure
    create_directory_structure(base_path)

    # Create tracking files
    create_test_execution_tracking(base_path, project_name)
    create_bug_tracking_template(base_path)

    # Create documentation
    create_baseline_metrics(base_path, project_name)
    create_weekly_report_template(base_path)
    create_master_qa_prompt(base_path, project_name)
    create_readme(base_path, project_name)

    print(f"\n✅ QA Project '{project_name}' initialized successfully!")
    print(f"\n📝 Next Steps:")
    print(f"   1. Review {base_path}/tests/docs/README.md")
    print(f"   2. Fill in BASELINE-METRICS.md with current project state")
    print(f"   3. Write test cases in category-specific documents")
    print(f"   4. Start testing with MASTER-QA-PROMPT.md")

if __name__ == "__main__":
    main()
