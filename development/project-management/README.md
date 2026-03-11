# Project Management Framework Skill

> **World-class project management framework initialization for rapid professional project setup**

[![Skill Status](https://img.shields.io/badge/status-production--ready-brightgreen)]()
[![Version](https://img.shields.io/badge/version-1.0.0-blue)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()

---

## 🎯 Overview

This skill automatically initializes professional project management infrastructure for new or existing projects. It sets up Git repositories, directory structures, milestone tracking systems, verification scripts, and CI/CD pipelines following enterprise-grade best practices.

### Key Features

✅ **Git Repository Initialization** - Professional version control setup
✅ **Directory Structure** - Standardized project layout
✅ **Milestone Tracking** - MILESTONES.md and TIMELINE.md
✅ **Verification Scripts** - Automated quality gates
✅ **CI/CD Pipelines** - GitHub Actions configuration
✅ **Documentation Framework** - Standardized documentation structure
✅ **Multi-Language Support** - Python, JavaScript, TypeScript, Go, Rust
✅ **Project Type Detection** - Web, API, CLI, Library, ML projects

---

## 🚀 Quick Start

### New Project

```
"Create a new project called DataPipeline with Python"
```

The skill will:
1. Create directory structure
2. Initialize Git repository
3. Generate milestone tracking system
4. Create verification scripts
5. Set up CI/CD workflows

### Existing Project

```
"Add professional project management to my existing project"
```

The skill will:
1. Analyze existing structure
2. Create backup (important!)
3. Initialize Git (if needed)
4. Add professional directories
5. Generate framework files
6. Output migration report

---

## 📖 Usage

### Triggering the Skill

The skill activates when you mention:
- "Create a new project"
- "Initialize project management"
- "Set up Git repository"
- "Add milestone tracking"
- "Project management framework"

### Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `project_name` | string | required | Project name |
| `project_description` | string | optional | Brief description |
| `project_type` | enum | auto-detected | web, api, cli, library, ml |
| `programming_language` | enum | python | python, javascript, typescript, go, rust |
| `git_user_name` | string | git config | Git user name |
| `git_user_email` | string | git config | Git email |
| `initialize_git` | boolean | true | Initialize Git repository |
| `create_cicd` | boolean | true | Create CI/CD workflows |
| `phases` | integer | 5 | Number of project phases |
| `reorganize_existing` | boolean | false | Move existing files |

---

## 📁 Generated Structure

```
{{PROJECT_NAME}}/
├── .github/workflows/          # CI/CD pipelines
│   ├── test.yml
│   ├── milestone-check.yml
│   └── security-scan.yml
├── .gitignore                  # Security-first rules
├── README.md                   # Project documentation
├── CHANGELOG.md                # Version history
├── CONTRIBUTING.md             # Contribution guidelines
├── docs/
│   ├── project/
│   │   ├── MILESTONES.md       # Milestone tracking
│   │   ├── TIMELINE.md         # Timeline visualization
│   │   ├── PROJECT_STATE.md
│   │   └── DOCUMENTATION_INDEX.md
│   ├── phases/                 # Phase-specific docs
│   ├── guides/                 # Development guides
│   ├── api/                    # API documentation
│   └── reports/                # Various reports
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
│   │   ├── verify_milestone.py
│   │   └── run_tests.sh
│   ├── setup/
│   └── maintenance/
├── milestones/                 # Milestone artifacts
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

## 🔧 Modules

### Module 1: Git Repository Initialization

**Function**: Initialize Git with professional configuration

**Features**:
- Secure .gitignore (prevents sensitive file commits)
- Proper Git configuration
- Initial commit
- Branch strategy (main + develop)

**Output**:
```
✅ Git repository initialized
✅ .gitignore created
✅ Initial commit completed
✅ Branches created (main, develop)
```

### Module 2: Directory Structure Creation

**Function**: Create professional directory structure

**Project Types**:
- **web**: src/frontend/, src/backend/, public/
- **api**: src/api/, src/models/, src/services/
- **cli**: src/commands/, src/utils/
- **library**: src/lib/, examples/, tests/
- **ml**: src/models/, src/data/, notebooks/

**Output**:
```
✅ Professional directory structure created
✅ Existing files migrated (optional)
✅ Migration report generated
```

### Module 3: Milestone Tracking System

**Function**: Create milestone tracking infrastructure

**Files**:
- `docs/project/MILESTONES.md` - Single source of truth
- `docs/project/TIMELINE.md` - Timeline visualization
- `docs/project/DOCUMENTATION_INDEX.md`
- `docs/project/PROJECT_STATE.md`

**Phases** (default 5):
1. Foundation & Infrastructure
2. Core Features
3. Enhancement & Optimization
4. Testing & Quality Assurance
5. Deployment & Documentation

**Output**:
```
✅ MILESTONES.md created with template
✅ TIMELINE.md created with visualizations
✅ DOCUMENTATION_INDEX.md created
✅ PROJECT_STATE.md initialized
✅ Phase directories created
```

### Module 4: Verification Scripts

**Function**: Generate automated verification scripts

**Scripts**:
- `scripts/verify/verify_milestone.py` - Milestone verification
- `scripts/verify/run_tests.sh` - Test runner

**Checks**:
- Test pass rate (target: 100%)
- Code coverage (target: 80%)
- Documentation completeness
- Security scan results
- Code quality metrics
- Git workspace cleanliness

**Output**:
```
✅ verify_milestone.py created
✅ run_tests.sh created (executable)
✅ Verification configured for language
```

### Module 5: CI/CD Workflows

**Function**: Create GitHub Actions workflows

**Workflows**:
- **test.yml**: Multi-version testing, coverage reporting
- **milestone-check.yml**: Documentation verification, milestone detection
- **security-scan.yml**: Security scanning, dependency checks

**Output**:
```
✅ .github/workflows/test.yml created
✅ .github/workflows/milestone-check.yml created
✅ .github/workflows/security-scan.yml created
✅ CI/CD configured
```

---

## 📊 Reporting

### Summary Report

After execution, the skill generates:

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
```

### Migration Report (Existing Projects)

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
```

---

## 🎨 Customization

### Custom Phases

```
"Create project with 3 phases: Design, Develop, Deploy"
```

The skill will:
1. Set `phases: 3`
2. Use custom phase names
3. Generate 3-phase milestone tracking
4. Create 3 phase directories

### Custom Directories

```
"Create ML project with custom directories: data, models, notebooks"
```

The skill will:
1. Add custom directories to structure
2. Create subdirectories as needed
3. Update documentation index
4. Configure verification scripts

### Language-Specific

```
"Create Go project with proper Go structure"
```

The skill will:
1. Use Go project layout
2. Configure Go testing
3. Set up Go CI/CD workflows
4. Generate Go-specific templates

---

## 📚 Examples

### Example 1: Python API Project

```
"Create Python API project UserService"
```

**Generated**:
- Python API structure (src/api/, src/models/, src/services/)
- FastAPI/Flask templates
- pytest configuration
- Python CI/CD workflows

### Example 2: React Web App

```
"Create React web app DashboardApp"
```

**Generated**:
- React structure (src/frontend/, public/)
- Component templates
- Jest testing setup
- JavaScript CI/CD workflows

### Example 3: Go CLI Tool

```
"Create Go CLI tool cli-tool"
```

**Generated**:
- Go CLI structure (src/commands/, src/utils/)
- Cobra templates
- Go testing setup
- Go CI/CD workflows

### Example 4: ML Project

```
"Create ML project ImageClassifier"
```

**Generated**:
- ML structure (src/models/, src/data/, notebooks/)
- Jupyter notebook templates
- ML-specific verification
- Python ML CI/CD workflows

---

## 🔍 Verification

### Check Installation

```bash
# Check Git repository
git status

# Check directory structure
ls -la docs/project/

# Run verification script
python scripts/verify/verify_milestone.py --phase 1

# Check CI/CD workflows
ls -la .github/workflows/
```

### Run Tests

```bash
# Run all tests
./scripts/verify/run_tests.sh

# Run with coverage
./scripts/verify/run_tests.sh --coverage

# Run with verbose output
./scripts/verify/run_tests.sh --verbose
```

### Verify Milestone

```bash
# Verify phase 1
python scripts/verify/verify_milestone.py --phase 1

# Verify all phases
python scripts/verify/verify_milestone.py --phase all

# Verbose output
python scripts/verify/verify_milestone.py --phase 1 --verbose
```

---

## 🛠️ Troubleshooting

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

# Go
go get -u github.com/golang/mock/...

# Rust
cargo install cargo-tarpaulin
```

### CI/CD Workflows Not Running

**Problem**: GitHub repository not configured

**Solution**:
1. Push to GitHub: `git remote add origin <url>`
2. Push branches: `git push -u origin main develop`
3. Check Actions tab in GitHub

---

## 🎯 Best Practices

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

## 🔄 Workflow Integration

### With Code Review

```
1. Initialize project with this skill
2. Develop features
3. Run code-reviewer skill
4. Update milestones
5. Commit changes
```

### With Test Generation

```
1. Create project structure
2. Write core code
3. Run test-generator skill
4. Verify tests pass
5. Update milestone progress
```

### With Security Audit

```
1. Initialize project
2. Complete phase development
3. Run security-auditor skill
4. Fix security issues
5. Verify milestone completion
```

---

## 📈 Metrics and Tracking

### Key Metrics

The skill tracks:
- Files created
- Lines of code generated
- Directories created
- Test coverage
- Documentation completeness
- Security scan results

### Milestone Progress

Track in MILESTONES.md:
- Phase completion status
- Test pass rates
- Code coverage
- Documentation status
- Security scan results

### Timeline Visualization

View in TIMELINE.md:
- Gantt charts
- Dependencies
- Progress indicators
- Velocity metrics

---

## 🤝 Contributing

Contributions are welcome! Please:
1. Read [CONTRIBUTING.md](CONTRIBUTING.md)
2. Check existing issues
3. Create pull request
4. Follow commit conventions

---

## 📄 License

This skill is part of Claude Code and follows the same license terms.

---

## 🔗 Related Skills

- **code-reviewer** - Code quality and best practices analysis
- **test-generator** - Automatic test generation
- **security-auditor** - Security vulnerability scanning
- **git-commit-helper** - Conventional commit messages

---

## 📞 Support

For issues, questions, or suggestions:
- Check the [troubleshooting guide](#-troubleshooting)
- Review [examples](examples/quick-start.md)
- Open an issue on GitHub

---

**Maintained by**: Claude Code Team
**Last Updated**: 2026-02-15
**Status**: Production Ready ✅
**Version**: 1.0.0
