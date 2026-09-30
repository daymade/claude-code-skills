# Workflow Examples

Use `history_index.py status` to check provider coverage and freshness, then
`history_index.py recall '<term>' --mode bm25 --provider claude` to find
candidate Session IDs. Open only those exact sessions. The old raw search
command is disabled for live stores; its date flags did not bound file reads.

## Recover Files Deleted in Cleanup

**Scenario**: Files were deleted during code review, need to recover specific components.

```bash
# 1. Find candidate sessions in the index, then inspect their exact records
python3 scripts/history_index.py recall 'DeletedComponent' --mode bm25 --provider claude

# 2. Copy the exact Path printed for the most relevant active/archive session
python3 scripts/recover_content.py <printed-session-path> \
    -k DeletedComponent ModelScreen \
    -o ./recovered/

# 3. Review provenance before treating a file as final
cat ./recovered/recovery_report.txt
```

`Source: file-history` means exact bytes from the named captured checkpoint.
`Source: Write` means a lower-fidelity Write checkpoint whose later Edit or
shell changes may be absent. Write calls with an explicit failed `tool_result`
are excluded because their requested content was not confirmed written.

## Recover Vanished Temporary Job Artifacts

**Scenario**: Browser URLs point into an expired Claude job directory, and the
original files are gone.

```bash
# 1. Find candidate sessions through the index
python3 scripts/history_index.py recall 'artifact-a.html' --mode bm25 --provider claude

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

Codex rollout hits can be found with indexed `--provider codex`, but they cannot be passed to
`recover_content.py`: Codex search and Claude file recovery are separate
capabilities.

## Track File Evolution Across Sessions

**Scenario**: Understand how a file changed over multiple sessions.

```bash
# 1. Find candidate sessions that mention the file
python3 scripts/history_index.py recall 'componentName.jsx' --mode bm25 --provider claude

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
# Search the index for a distinctive term
python3 scripts/history_index.py recall 'useModelStatus' --mode bm25 --provider claude

# Review top match
python3 scripts/analyze_sessions.py stats <top-result-session.jsonl>
```

## Batch Recovery Across Multiple Sessions

**Scenario**: Recover files containing a keyword from all matching sessions.

```bash
# First review indexed candidates and select exact Session paths
sessions='session1.jsonl session2.jsonl'

# Recover from each session
for session in $sessions; do
    output_dir="./recovery_$(basename $session .jsonl)"
    python3 scripts/recover_content.py "$session" -k keyword -o "$output_dir"
done
```

The index may omit recent or unindexed archives. Check `status` and state its
frontier; do not turn zero recall hits into an absence claim.

## Verify a Topic Across a Migrated History

**Scenario**: A machine migration reset file mtimes, and older sessions may live
only in a registered archive.

```bash
python3 scripts/history_index.py status
python3 scripts/history_index.py recall 'distinctive topic' --mode bm25 --provider claude
```

Check whether the index includes the archive and its last indexed time. An
incomplete index cannot support an absence claim. File mtime is not evidence
of conversation chronology.

## Custom Extraction from Raw JSONL

For extraction needs not covered by bundled scripts, first locate a candidate
through the index and verify its exact Session identity. A one-file custom
extractor stays confined to that Session:

```python
import json

with open('session.jsonl', 'r') as f:
    for line in f:
        data = json.loads(line)
        # Custom extraction logic; use data.get("timestamp") for time evidence.
        # See references/session_file_format.md for structure
```
