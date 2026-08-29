# Skill Creator Prerequisites

Auto-detect and install all dependencies before starting skill creation. This prevents failures mid-workflow (e.g., discovering gitleaks is missing only at the packaging step).

## Quick Check Script

Run all checks in one go:

```bash
cd <skill-creator-path>
echo "=== Skill Creator Prerequisites ==="
echo -n "uv: "; uv --version 2>/dev/null || echo "MISSING"
echo -n "Python: "; uv run --frozen python --version 2>/dev/null || echo "MISSING"
echo -n "PyYAML: "; uv run --frozen python -c "import yaml; print(yaml.__version__)" 2>/dev/null || echo "MISSING"
echo -n "tiktoken: "; uv run --frozen python -c "import tiktoken; print(tiktoken.__version__)" 2>/dev/null || echo "MISSING (conversation mining only)"
echo -n "gitleaks: "; gitleaks version 2>/dev/null || echo "MISSING"
echo -n "claude CLI: "; which claude 2>/dev/null || echo "MISSING"
```

## Dependencies by Phase

| Dependency | Required For | Phase | Severity |
|-----------|-------------|-------|----------|
| uv | Python runtime and dependency declaration | All Python phases | **Blocking** |
| Python 3.10+ | All scripts | All | **Blocking** |
| PyYAML | `quick_validate.py`, `package_skill.py` | Validation, Packaging | **Blocking** |
| tiktoken | `mine_conversation.py` | Conversation mining | **Blocking for conversation mining** |
| gitleaks | `security_scan.py` | Security Review (Step 6) | **Blocking for packaging** |
| claude CLI | `run_eval.py`, `run_loop.py` | Testing, Description Optimization | **Blocking for evals** |
| webbrowser | `generate_review.py` (viewer) | Eval Review | Optional (can use `--static` fallback) |

## Auto-Installation

### Locked Python runtime (required)

```bash
# Restore the project-local environment from the committed lockfile.
cd <skill-creator-path>
uv sync --frozen

# Validation
uv run --frozen python -m scripts.quick_validate <skill-path>
```

The environment belongs only to skill-creator. uv restores its pinned packages from the user's shared cache, so projects reuse package data without sharing one mutable environment. Keep the default global cache (or one user-configured global `UV_CACHE_DIR`); never set a global `UV_PROJECT_ENVIRONMENT`.

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

### tiktoken (required for conversation mining)

```bash
uv run --frozen python -c "import tiktoken; print(tiktoken.get_encoding('cl100k_base').name)"
uv run --frozen python -m scripts.mine_conversation --help
```

### claude CLI (required for evals)

The `claude` CLI (Claude Code) must be installed and available in PATH. If the user is already running this skill inside Claude Code, this is already satisfied.

```bash
# Verify
which claude && claude --version
```

If missing, the user needs to install Claude Code from https://claude.ai/claude-code.

## Script Invocation

Run scripts from the skill-creator root directory. Use the committed lockfile and its one project-local environment:

```bash
# CORRECT — run from skill-creator directory
cd <skill-creator-path>
uv run --frozen python -m scripts.quick_validate <skill-path>
uv run --frozen python -m scripts.package_skill <skill-path>
uv run --frozen python -m scripts.security_scan <skill-path>
uv run --frozen python -m scripts.aggregate_benchmark <workspace-path> --skill-name <name>

# WRONG — bare Python depends on ambient site packages
python3 scripts/package_skill.py <skill-path>  # Can fail: No module named 'yaml'
python3 -m scripts.quick_validate <skill-path>  # Can fail: No module named 'yaml'
```

This avoids relying on machine-global Python packages, prevents caller projects from contributing dependencies, and avoids disposable `uv run --with` environments for the bundled toolchain.

## Presenting Results to User

After running all checks, present a summary table:

```
Skill Creator Prerequisites:
  [x] Python 3.12.0
  [x] PyYAML 6.0.2
  [x] gitleaks 8.21.2
  [x] claude CLI (running inside Claude Code)
  [x] uv 0.11.x
```

If any **blocking** dependency is missing and auto-install fails, clearly explain what the user needs to do and stop before proceeding to skill creation.
