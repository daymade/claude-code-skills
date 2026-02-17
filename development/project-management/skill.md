# Project Management Framework Initialization Skill

> **World-class project management framework for rapid professional project setup**
>
> **Version**: 1.0.0
> **Last Updated**: 2026-02-15
> **Author**: Claude Sonnet 4.5

---

## Skill Description

Automatically initialize professional project management infrastructure for new or existing projects. This skill sets up Git repositories, directory structures, milestone tracking systems, verification scripts, and CI/CD pipelines following enterprise-grade best practices.

### When to Use This Skill

Use this skill when:
- Starting a new software project
- Upgrading existing projects to professional standards
- Setting up milestone tracking and project documentation
- Initializing Git repositories with best practices
- Creating CI/CD pipelines and automated testing infrastructure
- Establishing project verification and quality gates

### What This Skill Does

1. **Git Repository Initialization**
   - Creates secure .gitignore (security-first approach)
   - Initializes Git repository with proper configuration
   - Sets up branch strategy (main + develop)
   - Creates initial commit

2. **Professional Directory Structure**
   - Creates standardized project layout
   - Sets up documentation hierarchy
   - Organizes source code, tests, scripts
   - Establishes milestones tracking directory

3. **Milestone Tracking System**
   - Creates MILESTONES.md (single source of truth)
   - Creates TIMELINE.md (visualization)
   - Creates DOCUMENTATION_INDEX.md
   - Initializes milestone data structure

4. **Verification Scripts**
   - Generates verify_milestone.py (automated quality gates)
   - Creates run_tests.sh (testing automation)
   - Configures coverage thresholds
   - Sets up security scanning

5. **CI/CD Workflows**
   - GitHub Actions test workflow
   - Milestone check workflow
   - Security scan workflow
   - Automated reporting

6. **Documentation Framework**
   - README.md template
   - CONTRIBUTING.md guide
   - CHANGELOG.md structure
   - API documentation placeholder

---

## Configuration

### Input Parameters

The skill will prompt for:

1. **project_name** (required)
   - Name of the project
   - Used in filenames and documentation

2. **project_description** (optional)
   - Brief project description
   - Used in README.md

3. **project_type** (optional)
   - Options: web, api, cli, library, ml
   - Affects directory structure
   - Default: auto-detected

4. **programming_language** (optional)
   - Options: python, javascript, typescript, go, rust
   - Affects template selection
   - Default: python

5. **git_user_name** (optional)
   - Git user name for commits
   - Default: system git config

6. **git_user_email** (optional)
   - Git email for commits
   - Default: system git config

7. **initialize_git** (optional)
   - Whether to initialize Git repository
   - Options: true, false
   - Default: true

8. **create_cicd** (optional)
   - Whether to create CI/CD workflows
   - Options: true, false
   - Default: true

9. **phases** (optional)
   - Number of project phases
   - Default: 5

10. **reorganize_existing** (optional)
    - Whether to move existing files to new structure
    - Options: true, false
    - Default: false (for new projects)

---

## Template Variables

Templates use the following variable substitution pattern:

- `{{PROJECT_NAME}}` - Project name
- `{{PROJECT_DESCRIPTION}}` - Project description
- `{{PROJECT_TYPE}}` - Project type
- `{{LANGUAGE}}` - Programming language
- `{{GIT_USER_NAME}}` - Git user name
- `{{GIT_USER_EMAIL}}` - Git email
- `{{TODAY_DATE}}` - Current date (YYYY-MM-DD)
- `{{PHASES}}` - Number of phases
- `{{COVERAGE_THRESHOLD}}` - Test coverage threshold (default: 80)

---

## Generated Directory Structure

```
{{PROJECT_NAME}}/
├── .github/
│   └── workflows/
│       ├── test.yml              # CI/CD test pipeline
│       ├── milestone-check.yml   # Milestone verification
│       └── security-scan.yml     # Security scanning
├── .gitignore                    # Security-first ignore rules
├── README.md                     # Project documentation
├── CHANGELOG.md                  # Version history
├── CONTRIBUTING.md               # Contribution guidelines
├── docs/
│   ├── project/
│   │   ├── MILESTONES.md         # Milestone tracking
│   │   ├── TIMELINE.md           # Timeline visualization
│   │   ├── PROJECT_STATE.md      # Project status
│   │   └── DOCUMENTATION_INDEX.md
│   ├── phases/
│   │   ├── phase1/
│   │   ├── phase2/
│   │   ├── phase3/
│   │   ├── phase4/
│   │   └── phase5/
│   ├── guides/
│   ├── api/
│   └── reports/
├── src/
│   ├── {{LANGUAGE}}/
│   │   ├── core/
│   │   ├── utils/
│   │   └── tests/
│   │       ├── unit/
│   │       ├── integration/
│   │       └── performance/
│   └── templates/
├── scripts/
│   ├── verify/
│   │   ├── verify_milestone.py  # Verification script
│   │   └── run_tests.sh         # Test runner
│   ├── setup/
│   └── maintenance/
├── milestones/
│   ├── phase1/
│   ├── phase2/
│   ├── phase3/
│   ├── phase4/
│   └── phase5/
└── config/
    ├── development.yaml
    ├── staging.yaml
    └── production.yaml
```

---

## Usage Examples

### Example 1: New Python Project

```bash
# User: "Create a new Python project called DataPipeline with project management framework"

# Skill execution:
1. Prompt for missing parameters
2. Create directory structure
3. Initialize Git repository
4. Generate all templates
5. Create initial commit
6. Output summary report
```

### Example 2: Existing Project Upgrade

```bash
# User: "Upgrade this project to use professional project management"

# Skill execution:
1. Analyze existing project structure
2. Create backup (important!)
3. Initialize Git (if needed)
4. Create professional directories
5. Move existing files (if reorganize_existing=true)
6. Create milestone documentation
7. Generate verification scripts
8. Configure CI/CD
9. Output migration report
```

### Example 3: Custom Configuration

```bash
# User: "Create project with 3 phases and custom directories"

# Skill execution:
1. Prompt for configuration
   - phases: 3
   - custom_directories: ["data", "models", "notebooks"]
2. Generate customized structure
3. Create milestone tracking for 3 phases
4. Apply custom directory layout
5. Generate all templates
```

---

## Implementation Details

### Module 1: Git Repository Initialization

**Function**: Initialize Git repository with professional configuration

**Steps**:
1. Check if Git is installed
2. Create .gitignore from template
3. Run `git init`
4. Configure user.name and user.email
5. Create .gitignore file (security-first)
6. Create initial commit
7. Set up branch strategy (main + develop)

**Error Handling**:
- If Git not installed: Error and exit
- If already Git repo: Ask to reinitialize
- If .gitignore exists: Backup and replace

**Output**:
- Git repository initialized
- .gitignore created
- Initial commit completed
- Branches created (main, develop)

---

### Module 2: Directory Structure Creation

**Function**: Create professional directory structure

**Steps**:
1. Create base directories (docs/, src/, scripts/)
2. Create subdirectories based on project_type
3. Create milestone tracking directories
4. Create configuration directories
5. Move existing files (if reorganize_existing=true)

**Directory Mappings**:

| Project Type | Directories |
|--------------|-------------|
| web | src/frontend/, src/backend/, public/ |
| api | src/api/, src/models/, src/services/ |
| cli | src/commands/, src/utils/ |
| library | src/lib/, examples/, tests/ |
| ml | src/models/, src/data/, notebooks/ |

**Error Handling**:
- If directory exists: Skip or merge
- If file conflict: Ask user
- If reorganize: Backup before moving

**Output**:
- Professional directory structure created
- Existing files migrated (optional)
- Migration report generated

---

### Module 3: Milestone Tracking System

**Function**: Create milestone tracking infrastructure

**Steps**:
1. Create docs/project/MILESTONES.md
2. Create docs/project/TIMELINE.md
3. Create docs/project/DOCUMENTATION_INDEX.md
4. Create docs/project/PROJECT_STATE.md
5. Initialize milestone data for N phases

**Milestone Structure**:
- Phase 1: Foundation & Infrastructure
- Phase 2: Core Features
- Phase 3: Enhancement & Optimization
- Phase 4: Testing & Quality Assurance
- Phase 5: Deployment & Documentation

(Customizable based on `phases` parameter)

**Error Handling**:
- If files exist: Backup and replace
- If invalid phase count: Use default (5)

**Output**:
- MILESTONES.md created with template
- TIMELINE.md created with visualizations
- DOCUMENTATION_INDEX.md created
- PROJECT_STATE.md initialized
- Phase directories created

---

### Module 4: Verification Scripts

**Function**: Generate automated verification scripts

**Steps**:
1. Create scripts/verify/verify_milestone.py
2. Create scripts/verify/run_tests.sh
3. Set executable permissions (chmod +x)
4. Configure test framework based on language

**Verification Checks**:
- Test pass rate (target: 100%)
- Code coverage (target: 80%)
- Documentation completeness
- Security scan results
- Code quality metrics
- Git workspace cleanliness

**Error Handling**:
- If scripts exist: Backup and replace
- If test framework not available: Use generic
- If permissions fail: Warning

**Output**:
- verify_milestone.py created
- run_tests.sh created (executable)
- Verification configured for language

---

### Module 5: CI/CD Workflows

**Function**: Create GitHub Actions workflows

**Steps**:
1. Create .github/workflows/ directory
2. Create test.yml workflow
3. Create milestone-check.yml workflow
4. Create security-scan.yml workflow
5. Configure based on programming_language

**Workflow Features**:

**test.yml**:
- Multi-version testing (Python 3.11, 3.12)
- Coverage reporting
- Artifact uploads
- Test summary generation

**milestone-check.yml**:
- Documentation verification
- Milestone detection
- Code quality metrics
- Automated reports

**security-scan.yml**:
- Bandit security scan
- Safety dependency check
- Semgrep static analysis
- Secrets detection
- .gitignore verification

**Error Handling**:
- If .github exists: Merge workflows
- If workflows exist: Backup and replace
- If GitHub not configured: Warning

**Output**:
- .github/workflows/test.yml created
- .github/workflows/milestone-check.yml created
- .github/workflows/security-scan.yml created
- CI/CD configured

---

## Output and Reporting

### Summary Report

After execution, skill generates a summary report:

```
=== Project Management Framework Initialization Summary ===

Project: {{PROJECT_NAME}}
Date: {{TODAY_DATE}}
Type: {{PROJECT_TYPE}}
Language: {{LANGUAGE}}

✅ Git Repository: Initialized
✅ Directory Structure: Created
✅ Milestone Tracking: Configured ({{PHASES}} phases)
✅ Verification Scripts: Generated
✅ CI/CD Workflows: Configured

Files Created: {{COUNT}}
Lines of Code: {{LINES}}
Directories Created: {{DIRS}}

Next Steps:
1. Review MILESTONES.md and customize phases
2. Update PROJECT_STATE.md with current status
3. Run: python scripts/verify/verify_milestone.py --phase 1
4. Commit and push to remote repository

Documentation: docs/project/DOCUMENTATION_INDEX.md
```

### Migration Report (Existing Projects)

For existing project upgrades:

```
=== Project Migration Report ===

Project: {{PROJECT_NAME}}
Backup: {{BACKUP_PATH}}

Files Migrated: {{MIGRATED_COUNT}}
Files Conflicts: {{CONFLICTS_COUNT}}
Directories Created: {{DIRS_CREATED}}

Migration Log:
- file1.py -> src/core/file1.py
- file2.py -> src/utils/file2.py
...

Review Needed:
- Check file imports
- Update configuration paths
- Verify test references

Next Steps:
1. Review migrated files
2. Update imports and references
3. Run tests to verify
4. Commit changes
```

---

## Best Practices

### For New Projects
1. Use this skill at project start
2. Customize MILESTONES.md before development
3. Commit initial structure before coding
4. Update milestone progress regularly

### For Existing Projects
1. **Always create backup first**
2. Review migration report carefully
3. Test all file references
4. Update documentation incrementally
5. Keep old structure until verified

### For Team Collaboration
1. Discuss milestone structure with team
2. Agree on phase definitions
3. Configure CI/CD before inviting team
4. Document custom conventions
5. Train team on verification scripts

---

## Troubleshooting

### Git Initialization Fails
**Problem**: Git not installed or not configured
**Solution**:
```bash
# Install Git
brew install git  # macOS
sudo apt-get install git  # Ubuntu

# Configure Git
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

### Directory Conflicts
**Problem**: Directories already exist
**Solution**:
- Skill will skip existing directories
- Use `reorganize_existing=true` to move files
- Review conflicts before proceeding

### Verification Scripts Fail
**Problem**: Test framework not installed
**Solution**:
```bash
# Python
pip install pytest pytest-cov coverage bandit flake8

# JavaScript
npm install --save-dev jest eslint
```

### CI/CD Workflows Not Running
**Problem**: GitHub repository not configured
**Solution**:
1. Push to GitHub: `git remote add origin <url>`
2. Push branches: `git push -u origin main develop`
3. Check Actions tab in GitHub

---

## Extension Points

### Custom Templates
Add custom templates in `templates/custom/`:
- Create .template files
- Use {{VARIABLE}} placeholders
- Reference in skill configuration

### Additional Workflows
Add custom CI/CD workflows in `templates/workflows/custom/`:
- Create .yml files
- Follow GitHub Actions syntax
- Skill will automatically include

### Language-Specific Features
Add language detection logic:
- Detect from existing files
- Choose appropriate templates
- Configure language-specific tools

---

## Related Skills

- **code-reviewer**: Code quality and best practices analysis
- **test-generator**: Automatic test generation
- **security-auditor**: Security vulnerability scanning
- **git-commit-helper**: Conventional commit messages

---

## Version History

### 1.0.0 (2026-02-15)
- Initial release
- Git repository initialization
- Professional directory structure
- Milestone tracking system
- Verification scripts
- CI/CD workflows
- Multi-language support (Python, JavaScript, Go, Rust)
- Project type detection (web, api, cli, library, ml)

---

## License

This skill is part of Claude Code and follows the same license terms.

---

**Maintained by**: Claude Code Team
**Last Updated**: 2026-02-15
**Status**: Production Ready ✅
