---
name: fixed-command-entry
description: >-
  Invoke a registered Skill Creator tool from another working directory.
---

# Fixed command entry

Use the resolved skill-creator source path to call these tools from any working
directory. Keep the selected tool's subcommands, flags and exit meanings.

```bash
python3 "<skill-creator-path>/scripts/creator.py" --help
python3 "<skill-creator-path>/scripts/creator.py" <command> --help
```

Replace `<skill-creator-path>` with an absolute path. Supply absolute paths for
artifact inputs and outputs. For `capture_command`, follow the
[capture recipe](stateful-script-verification.md#large-command-output), which owns
its invocation and child working-directory semantics. Other tools resolve relative
artifact arguments from the skill-creator root, matching the original
`cd <skill-creator-path>` invocation. Preserve quoted paths containing spaces.

```bash
python3 "<skill-creator-path>/scripts/creator.py" audit_skill_regression snapshot \
  --source "<absolute-skill-directory>" --output "<absolute-new-snapshot-directory>"
python3 "<skill-creator-path>/scripts/creator.py" quick_validate \
  "<absolute-skill-directory>" --audience public
```

Read the [bounded-read recipe](stateful-script-verification.md#large-command-output)
before using `skill_read_plan` for content. A plan describes the source; it does
not establish that its contents reached the reader.

Read [release readiness](release-readiness.md) before attesting a release, and
[materialization budget](materialization-budget.md) before preparing or running
input copies. Use `source_contract check-path` before source edits and
`source_contract audit` for source/install delivery checks as specified in
SKILL.md. The entry does not select, prepare or run an operation on its own.

Select only a registered tool name. The entry resolves its own file, including a
symlink, to locate the owner root and starts exactly one child:
`uv run --frozen --project <owner-root> python -m scripts.<selected-tool>`.
Pass the remaining arguments unchanged; retain the child's stdout, stderr and
exit code. Keep direct tool invocation supported.

Expect `uv` on PATH. Let it prepare the normal project-local `.venv` using the
committed lock and shared cache when needed; invocation can create local runtime
files. Keep the existing uv isolation contract. Missing `uv` exits 127. Missing
owner modules, missing entry/owner arguments, unknown entry names, blank tokens
outside the `capture_command` argv payload and blank `--flag=value` values outside
that payload exit 2. Let the selected tool's parser reject a subcommand missing
its required inputs before that operation writes its requested outputs. Inspect any nonzero result; do not retry or switch tools automatically.
