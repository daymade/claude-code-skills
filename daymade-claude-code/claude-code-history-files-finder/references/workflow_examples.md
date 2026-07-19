# Workflow Examples

Detailed workflow examples for common session history recovery scenarios.

## Recover Files Deleted in Cleanup

**Scenario**: Files were deleted during code review, need to recover specific components.

```bash
# 1. Find sessions mentioning the deleted files
python3 scripts/analyze_sessions.py search /path/to/project \
    DeletedComponent ModelScreen RemovedFeature

# 2. Copy the exact Path printed for the most relevant active/archive session
python3 scripts/recover_content.py <printed-session-path> \
    -k DeletedComponent ModelScreen \
    -o ./recovered/

# 3. Review provenance before treating a file as final
cat ./recovered/recovery_report.txt
```

`Source: file-history` means exact bytes from the named captured checkpoint.
`Source: Write` means a lower-fidelity Write checkpoint whose later Edit or
shell changes may be absent.

## Recover Vanished Temporary Job Artifacts

**Scenario**: Browser URLs point into an expired Claude job directory, and the
original files are gone.

```bash
# 1. The project is uncertain, so every positional after --all-projects is a keyword
python3 scripts/analyze_sessions.py search --all-projects \
    artifact-a.html artifact-b.html \
    --exclude-session <current-session-id>

# 2. Recover exact captured checkpoints from the best matching session
python3 scripts/recover_content.py <printed-session-path> \
    -k artifact-a.html artifact-b.html \
    -o ./restored-artifacts/

# 3. Confirm source, checkpoint version, byte count, and SHA-256
cat ./restored-artifacts/recovery_report.txt
```

Recovery automatically unions same-ID JSONL copies and companion roots from all
active homes and registered archives. If exact-backup lookup still reports that
bytes are missing, locate an unregistered checkpoint root and add
`--file-history-root /path/to/file-history`. Do not silently call a stale Write
checkpoint the final file. `--write-only` is an explicit lower-fidelity choice,
not an automatic fallback. If the report says `Later state: recorded deleted`,
the bytes are the last available pre-deletion checkpoint, not the current state.

Codex rollout hits can be found with `--codex`, but they cannot be passed to
`recover_content.py`: Codex search and Claude file recovery are separate
capabilities.

## Track File Evolution Across Sessions

**Scenario**: Understand how a file changed over multiple sessions.

```bash
# 1. Find sessions that modified the file
python3 scripts/analyze_sessions.py search /path/to/project \
    "componentName.jsx"

# 2. Analyze each session's file operations
for session in session1.jsonl session2.jsonl session3.jsonl; do
    python3 scripts/analyze_sessions.py stats $session --show-files | \
        grep "componentName.jsx"
done

# 3. Recover the best captured version from each session
python3 scripts/recover_content.py session1.jsonl -k componentName -o ./v1/
python3 scripts/recover_content.py session2.jsonl -k componentName -o ./v2/
python3 scripts/recover_content.py session3.jsonl -k componentName -o ./v3/

# 4. Compare versions (files retain original directory structure)
# Use find to locate the file in subdirectories, or reference the recovery_report.txt
find ./v1/ -name "componentName.jsx" -exec diff {} ./v2/{} \;
```

## Find Session with Specific Implementation

**Scenario**: Remember implementing a feature but can't find which session.

```bash
# Search for distinctive keywords from that implementation
python3 scripts/analyze_sessions.py search /path/to/project \
    "useModelStatus" "downloadProgress" "ModelScope" \
    --from-date 2026-03-01 --to-date 2026-04-30

# Review top match
python3 scripts/analyze_sessions.py stats <top-result-session.jsonl>
```

## Batch Recovery Across Multiple Sessions

**Scenario**: Recover files containing a keyword from all matching sessions.

```bash
# Find relevant sessions
sessions=$(python3 scripts/analyze_sessions.py search /path/to/project \
    keyword | grep "Path:" | awk '{print $2}')

# Recover from each session
for session in $sessions; do
    output_dir="./recovery_$(basename $session .jsonl)"
    python3 scripts/recover_content.py "$session" -k keyword -o "$output_dir"
done
```

The default `list` and `search` commands cover active homes plus registered
archives. Do not add `--main-only` or `--home` to these workflows unless the
task is explicitly to diagnose one store. A required missing archive stops the
search instead of silently returning a partial result.

## Verify a Topic Across a Migrated History

**Scenario**: A machine migration reset file mtimes, and older sessions may live
only in a registered archive.

```bash
python3 scripts/analyze_sessions.py search /path/to/project \
    "distinctive topic" "library-name" \
    --from-date 2026-03-01 --to-date 2026-04-30
```

Verify three fields before reporting absence: the `Searched ... source(s)` line
includes the expected `archive:<label>`, the command did not emit a source
configuration error, and the date window was applied to internal matching-record
timestamps. File mtime is not evidence.

## Custom Extraction from Raw JSONL

For extraction needs not covered by bundled scripts, first use the analyzer to
locate the exact active/archive session. A one-file custom extractor is not a
replacement for whole-history source discovery:

```python
import json

with open('session.jsonl', 'r') as f:
    for line in f:
        data = json.loads(line)
        # Custom extraction logic; use data.get("timestamp") for time evidence.
        # See references/session_file_format.md for structure
```
