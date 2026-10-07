---
name: fixed-command-entry
description: >-
  Run audit_skill_regression, release_readiness, source_contract, materialize
  or delivery_identity from another working directory through the fixed skill-creator entry.
---

# Fixed command entry

Use the resolved skill-creator source path to call these tools from any working
directory. Keep the selected tool's subcommands, flags and exit meanings.

```bash
python3 "<skill-creator-path>/scripts/creator.py" audit_skill_regression --help
python3 "<skill-creator-path>/scripts/creator.py" release_readiness --help
python3 "<skill-creator-path>/scripts/creator.py" source_contract --help
python3 "<skill-creator-path>/scripts/creator.py" materialize --help
python3 "<skill-creator-path>/scripts/creator.py" delivery_identity --help
```

Replace `<skill-creator-path>` with an absolute path. Supply absolute paths for
artifact inputs and outputs. Relative arguments resolve from the skill-creator
root, matching the original `cd <skill-creator-path>` invocation; they do not
resolve from the caller's directory. Preserve quoted paths containing spaces.

```bash
python3 "<skill-creator-path>/scripts/creator.py" audit_skill_regression snapshot \
  --source "<absolute-skill-directory>" --output "<absolute-new-snapshot-directory>"
```

Read [release readiness](release-readiness.md) before attesting a release, and
[materialization budget](materialization-budget.md) before preparing or running
input copies. Use `source_contract check-path` before source edits and
`source_contract audit` for source/install delivery checks as specified in
SKILL.md. The entry does not select, prepare or run an operation on its own.

Execute only the named tools. The entry resolves its own file, including a
symlink, to locate the owner root and starts exactly one child:
`uv run --frozen --project <owner-root> python -m scripts.<selected-tool>`.
Pass the remaining arguments unchanged; retain the child's stdout, stderr and
exit code. Do not use this entry to execute an arbitrary module or shell command.
Keep direct tool invocation supported.

Expect `uv` on PATH. Let it prepare the normal project-local `.venv` using the
committed lock and shared cache when needed; invocation can create local runtime
files. Keep the existing uv isolation contract. Missing `uv` exits 127. Missing
owner modules, missing entry/owner arguments, unknown entry names, blank tokens
and blank `--flag=value` values exit 2. Let the selected tool's parser reject a
subcommand missing its required inputs before that operation writes its requested
outputs. Inspect any nonzero result; do not retry or switch tools automatically.
