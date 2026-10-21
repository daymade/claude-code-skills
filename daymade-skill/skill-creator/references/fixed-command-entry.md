---
name: fixed-command-entry
description: >-
  Run the named audit, release, source, materialization, identity, validation and
  bounded-read tools from another directory through the fixed skill-creator entry.
---

# Fixed command entry

Use the resolved skill-creator source path to call these tools from any working
directory. Keep the selected tool's subcommands, flags and exit meanings.

```bash
python3 "<skill-creator-path>/scripts/creator.py" --help
python3 "<skill-creator-path>/scripts/creator.py" <command> --help
```

Replace `<skill-creator-path>` with an absolute path. Supply absolute paths for
artifact inputs and outputs. Relative arguments resolve from the skill-creator
root, matching the original `cd <skill-creator-path>` invocation; they do not
resolve from the caller's directory. Preserve quoted paths containing spaces.

```bash
python3 "<skill-creator-path>/scripts/creator.py" audit_skill_regression snapshot \
  --source "<absolute-skill-directory>" --output "<absolute-new-snapshot-directory>"
python3 "<skill-creator-path>/scripts/creator.py" quick_validate \
  "<absolute-skill-directory>" --audience public
python3 "<skill-creator-path>/scripts/creator.py" capture_command \
  --cwd "<absolute-existing-business-directory>" \
  --output-dir "<absolute-new-private-output-directory>" \
  -- <already-authorized-executable> <arg>...
```

Read the [bounded-read recipe](stateful-script-verification.md#large-command-output)
before using `skill_read_plan` for content. A plan describes the source; it does
not establish that its contents reached the reader.

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

For `capture_command`, name the explicit owner for an already-authorized argv
after `--`; do not treat that payload as an arbitrary module or shell command or
as authorization. Preserve every payload token, including ordinary empty
arguments after the nonblank executable. Use required `--cwd` to retain the
caller's business context and required `--output-dir` for a new private capture
directory.

Expect `uv` on PATH. Let it prepare the normal project-local `.venv` using the
committed lock and shared cache when needed; invocation can create local runtime
files. Keep the existing uv isolation contract. Missing `uv` exits 127. Missing
owner modules, missing entry/owner arguments, unknown entry names, blank tokens
outside the `capture_command` argv payload and blank `--flag=value` values outside
that payload exit 2. Let the selected tool's parser reject a subcommand missing
its required inputs before that operation writes its requested outputs. Inspect any nonzero result; do not retry or switch tools automatically.
