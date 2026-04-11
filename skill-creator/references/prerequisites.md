# Skill Creator Prerequisites

Auto-detect and install all dependencies before starting skill creation. This prevents failures mid-workflow (e.g., discovering gitleaks is missing only at the packaging step).

## Quick Check Script

Run all checks in one go:

```bash
echo "=== Skill Creator Prerequisites ==="
echo -n "uv: "; uv --version 2>/dev/null || echo "MISSING"
echo -n "Python: "; uv run python --version 2>/dev/null || echo "MISSING"
echo -n "PyYAML: "; uv run --with PyYAML python -c "import yaml; print('OK')" 2>/dev/null || echo "MISSING"
echo -n "gitleaks: "; gitleaks version 2>/dev/null || echo "MISSING"
echo -n "claude CLI: "; which claude 2>/dev/null || echo "MISSING"
echo -n "anthropic SDK: "; uv run --with anthropic python -c "import anthropic; print('OK')" 2>/dev/null || echo "MISSING (optional)"
```

## Dependencies by Phase

| Dependency | Required For | Phase | Severity |
|-----------|-------------|-------|----------|
| uv | Python runtime and dependency declaration | All Python phases | **Blocking** |
| Python 3.7+ | All scripts | All | **Blocking** |
| PyYAML | `quick_validate.py`, `package_skill.py` | Validation, Packaging | **Blocking** |
| gitleaks | `security_scan.py` | Security Review (Step 6) | **Blocking for packaging** |
| claude CLI | `run_eval.py`, `run_loop.py` | Testing, Description Optimization | **Blocking for evals** |
| anthropic SDK | `improve_description.py`, `run_loop.py` | Description Optimization | Optional (only for desc optimization) |
| webbrowser | `generate_review.py` (viewer) | Eval Review | Optional (can use `--static` fallback) |

## Auto-Installation

### PyYAML (required)

```bash
# Preferred: declare it at the call site
uv run --with PyYAML python -c "import yaml; print(yaml.__version__)"

# Validation
uv run --with PyYAML python -m scripts.quick_validate <skill-path>
```

### gitleaks (required for packaging)

```bash
# macOS
brew install gitleaks

# Linux
wget https://github.com/gitleaks/gitleaks/releases/download/v8.21.2/gitleaks_8.21.2_linux_x64.tar.gz
tar -xzf gitleaks_8.21.2_linux_x64.tar.gz && sudo mv gitleaks /usr/local/bin/

# Verify
gitleaks version
```

### anthropic SDK (optional, for description optimization)

```bash
uv run --with anthropic python -c "import anthropic; print('OK')"
```

Also requires `ANTHROPIC_API_KEY` environment variable to be set.

### claude CLI (required for evals)

The `claude` CLI (Claude Code) must be installed and available in PATH. If the user is already running this skill inside Claude Code, this is already satisfied.

```bash
# Verify
which claude && claude --version
```

If missing, the user needs to install Claude Code from https://claude.ai/claude-code.

## Script Invocation

Run scripts from the skill-creator root directory. Use `uv run --with ...` when a script has Python dependencies:

```bash
# CORRECT — run from skill-creator directory
cd <skill-creator-path>
uv run --with PyYAML python -m scripts.quick_validate <skill-path>
uv run --with PyYAML python -m scripts.package_skill <skill-path>
uv run python -m scripts.security_scan <skill-path>
uv run python -m scripts.aggregate_benchmark <workspace-path> --skill-name <name>

# WRONG — bare Python depends on ambient site packages
python3 scripts/package_skill.py <skill-path>  # Can fail: No module named 'yaml'
python3 -m scripts.quick_validate <skill-path>  # Can fail: No module named 'yaml'
```

This avoids relying on machine-global Python packages and keeps validation/packaging reproducible.

## Presenting Results to User

After running all checks, present a summary table:

```
Skill Creator Prerequisites:
  [x] Python 3.12.0
  [x] PyYAML 6.0.1
  [x] gitleaks 8.21.2
  [x] claude CLI (running inside Claude Code)
  [ ] anthropic SDK — not installed (only needed for description optimization)
  [x] uv 0.6.x
```

If any **blocking** dependency is missing and auto-install fails, clearly explain what the user needs to do and stop before proceeding to skill creation.
