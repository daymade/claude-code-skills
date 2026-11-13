# Skill Creator Prerequisites

Auto-detect and install all dependencies before starting skill creation. This prevents failures mid-workflow (e.g., discovering gitleaks is missing only at the packaging step).

## Quick Check Script

Run all checks in one go:

```bash
cd "<skill-creator-path>" || exit 1
uv sync --frozen || exit 1
echo "=== Skill Creator Prerequisites ==="
echo -n "uv: "; uv --version 2>/dev/null || echo "MISSING"
echo -n "Python: "; uv run --frozen python --version 2>/dev/null || echo "MISSING"
echo -n "PyYAML: "; uv run --frozen python -c "import yaml; print(yaml.__version__)" 2>/dev/null || echo "MISSING"
echo -n "tiktoken: "; uv run --frozen python -c "import tiktoken; print(tiktoken.__version__)" 2>/dev/null || echo "MISSING (conversation mining only)"
echo -n "gitleaks: "; gitleaks version 2>/dev/null || echo "MISSING"
echo -n "Semgrep: "; uv run --frozen semgrep --version 2>/dev/null || echo "MISSING"
echo -n "claude CLI: "; which claude 2>/dev/null || echo "MISSING"
```

## Dependencies by Phase

| Dependency | Required For | Phase | Severity |
|-----------|-------------|-------|----------|
| uv | Python runtime and dependency declaration | All Python phases | **Blocking** |
| Python (range declared in [pyproject.toml](../pyproject.toml)) | All scripts | All | **Blocking** |
| PyYAML | `quick_validate.py`, `package_skill.py` | Validation, Packaging | **Blocking** |
| tiktoken | `mine_conversation.py` | Conversation mining | **Blocking for conversation mining** |
| gitleaks | `security_scan.py` | Security Review (Step 6) | **Blocking for packaging** |
| Semgrep CE (locked) | `code_scan.py`, `security_scan.py` | Security Review (Step 6) | **Blocking when packaged Python is present** |
| claude CLI | `run_eval.py`, `run_loop.py` | Testing, Description Optimization | **Blocking for evals** |
| webbrowser | `generate_review.py` (viewer) | Eval Review | Optional (can use `--static` fallback) |

## Auto-Installation

### Locked Python runtime (required)

Install uv through its [official installation guide](https://docs.astral.sh/uv/getting-started/installation/).
Use a version satisfying `[tool.uv].required-version` in
[pyproject.toml](../pyproject.toml); let `uv sync` enforce the requirement before
running the checks. Keep that requirement compatible with the scoped override
interface documented in [uv's release notes](https://github.com/astral-sh/uv/blob/main/changelogs/0.11.x.md#01125).

```bash
# Restore the project-local environment from the committed lockfile.
cd "<skill-creator-path>" || exit 1
uv sync --frozen

# Validation
uv run --frozen python -m scripts.quick_validate "<skill-path>"
```

The environment belongs only to skill-creator. uv restores its pinned packages from the user's shared cache, so projects reuse package data without sharing one mutable environment. Keep the default global cache (or one user-configured global `UV_CACHE_DIR`); never set a global `UV_PROJECT_ENVIRONMENT`.

Use the locked Semgrep console entry installed by this environment; do not invoke
`python -m semgrep` or substitute an ambient engine version. Run its bundled local
rules without an account or code upload. Read [code-check scope](code-security-checks.md)
before interpreting a successful scan.

### Scanner SDK maintenance

Read the current engine pin, SDK replacements and uv requirement from
[pyproject.toml](../pyproject.toml), and resolved distributions from
[uv.lock](../uv.lock). Keep replacement constraints scoped to the affected
Semgrep release. Preserve the declared MCP interface and align the OpenTelemetry
API, SDK, exporters and instrumentation as one compatible family.

After changing those declarations, run from the Skill Creator directory:

```bash
uv lock
uv sync --frozen
uv pip check
```

Avoid an unrelated whole-graph upgrade. Interpret `uv pip check` against the
original wheel metadata: compare each reported Semgrep requirement mismatch
with the replacements declared in `pyproject.toml`. Accept only an explicitly
replaced constraint with compatibility evidence; treat any other mismatch as
unresolved. Do not suppress errors or report the raw metadata check as passed.
Run [the maintainer calibration](code-security-checks.md#calibrate-before-arming),
then obtain a fresh combined scan and package through
[the security and packaging procedure](publishing-and-packaging.md#step-6-security-review).
Retire an override when an upstream Semgrep release accepts patched dependencies;
retain the advisory-floor and consumer regressions when changing it.

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

Run module commands from the Skill Creator directory in its locked environment.
For another working directory, use [the fixed command entry](fixed-command-entry.md);
`uv run --project` selects an environment but does not make owner modules importable
from an arbitrary caller directory. Avoid ambient Python or per-call dependency overlays.
For scan prerequisites, package flags and execution order, follow
[security review and packaging](publishing-and-packaging.md#step-6-security-review)
rather than treating a list of module invocations as a complete workflow.

## Presenting Results to User

Report the observed versions and results from the checks actually run. Distinguish
an unavailable dependency from a failed command or a declared metadata override;
do not prefill successful statuses or copy sample versions.

If any **blocking** dependency is missing and auto-install fails, clearly explain what the user needs to do and stop before proceeding to skill creation.
