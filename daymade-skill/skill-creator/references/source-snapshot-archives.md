# Preserve a source snapshot for later verification

Use this route when a pre-edit snapshot must survive a handoff, a workspace cleanup,
or storage in another repository. A snapshot is evidence of the included source
files; it is not a backup of the user's runtime credentials.

## What belongs in the snapshot

`scripts/packaging_policy.py` owns the versioned inclusion policy. New snapshots
record the policy in `.skill-regression-baseline.json`; regression reports and
attestations retain the policy used for their hashes.

- A local `.authorization` file outside root `tests/` and `evals/` is runtime state.
  New snapshots, packages, and package-content hashes exclude it.
- Configuration templates such as `.env.example` and
  `config-template/authorization.json.example` remain source files. Do not remove
  them merely because an archive repository ignores similarly named files.
- Root `tests/` and `evals/` remain in the regression audit, including fake
  authorization fixtures. Package inclusion keeps its existing, separate scope.

This is an exact runtime-file boundary, not a general secret detector. Keep using
the existing security scan for other files. Do not broaden it into an exclusion
of all configuration files or all `.env*` paths.

## Create and preserve the baseline

Before editing the skill:

```bash
cd <skill-creator-path>
uv run --frozen python -m scripts.audit_skill_regression snapshot \
  --source <skill-path> --output <new-before-directory>
```

Use the resulting directory for the normal `compare`, `classify`, and `verify`
workflow. Do not edit its included files or regenerate its manifest to make a
failed hash check pass.

When that baseline needs an archive:

```bash
uv run --frozen python -m scripts.audit_skill_regression archive-snapshot \
  --source <before-directory> --output <new-archive.zip>
```

The archive command verifies the recorded policy and source hash before writing.
It preserves included files, executable permissions, and the provenance manifest,
and refuses to overwrite an existing destination. Storing one archive also keeps
an outer repository's ignore rules from silently omitting an included template.

Restore to a new directory with an extractor that preserves Unix executable
permissions, then use the restored directory as `--before`. On POSIX systems,
the `unzip` command provides that extraction path. The normal identity check still
applies: use the existing `--renamed-from` option only for a declared move of the
skill, never to suppress an unexplained mismatch.

## Existing records and failures

Schema-3 records without an inclusion-policy field retain their legacy inclusion
rules. A newer tool does not reinterpret their old hashes under the current policy.
Unknown policies and audit scopes that omit root tests or evals fail explicitly.

A legacy snapshot may contain a local authorization file. Verifying its original
hash and distributing it are different operations: the archive route must not
silently remove that file and claim the old hash still describes the result. Keep
the original evidence and follow the reported error; do not relabel a modified
directory as the original baseline.

If the source changed, executable permissions changed, or the snapshot was partly
copied, stop at that concrete mismatch. Recover an authoritative pre-edit source
or report the gap. Passing a package scan does not repair a broken baseline.
