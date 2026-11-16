# Versioned Stage 1 history

This optional integration applies only to future successful ordinary file runs
with `--stage 1`. It preserves the bytes actually read, the generated output and
their exact dictionary/context references through daudio. The original correction
dispatch and the native-result receipt share the same pinned input; they record
the call and its obtained result, not two inference runs.

## Bind the installed runtime

Keep the existing source reader, external dispatcher, device identity and source
ownership checks. Select an explicit Python runtime containing daudio 0.1.8 or
newer and this Skill's existing `requirements.txt` dependencies. All paths below
must refer to the same installed bundle and original native configuration directory.
Do not infer a mutation command from the reader or install into an unrelated app.

Add to the existing audio profile:

```json
{
  "history_projection": {
    "protocol": 1,
    "argv": ["/absolute/runtime/bin/python", "/absolute/transcript-fixer/scripts/history_projection.py"]
  },
  "history_projection_provider": "transcript-fixer.stage1-history"
}
```

Configure this named provider in the same daudio profile used by the publisher:

```json
{
  "type": "command",
  "operations": ["correct-stage1"],
  "argv": ["/absolute/runtime/bin/python", "/absolute/transcript-fixer/scripts/history_projection.py", "recompute", "--options", "{options_json}"],
  "allowed_options": ["recipe", "original_source_ref", "target_ref", "evidence_refs"],
  "stdout_format": "json",
  "result_kind": "transcript",
  "result_text_field": "text",
  "timeout": 120
}
```

Replace only `source_publisher.argv` with the literal runtime/helper command plus
`publish --state /absolute/native-config/history-projections.json
--publisher-json '["/absolute/original/bin/daudio","import"]' --`. Pass the exact
original publisher argv as JSON, including any existing global options. The
wrapper forwards all appended dictionary/context arguments, stdout and exit status
unchanged. A failed original import never becomes successful because projection
could run. Projection diagnostics go to stderr.

## Processing and recovery

The ordinary successful Stage 1 work point first saves its complete local pending
receipt. It verifies its running correction parent's exact source and device,
then publishes the obtained result with `record_result`. Registry failure retains
native success and bytes. Existing ordinary work points replay pending
registration; they do not repeat the correction. `history-projections.json` is a
configuration-local outbox and projection cursor, not another transcript library.
After registration, full baselines and observed manual/candidate bytes live in
versioned daudio resources.

Shared dictionary/context publication uses the existing reprocessor and the named
deterministic adapter. It reuses `DictionaryProcessor`, its domain/disabled-pair
rules and context trap parser; it does not call ASR, an LLM or Stage 2. Each result
pins its input and consumed evidence. Native AI Correction remains required for
the full transcript workflow.

After a derived revision commits, projection compares the previous derived text,
current native file and new derived text. Nonoverlapping edits preserve manual
content. Overlap, missing baselines, foreign devices, file/version drift or failed
readback remain pending with both observed and proposed bytes retained. Writes
use an atomic replacement guarded by current bytes and registry version; later
ordinary work points recover a prepared write after interruption. This is an
optimistic file check, not a lock respected by arbitrary external editors.

No historical fragment is promoted into a full baseline. Unbound use keeps its
original behavior. Missing parent/source evidence retains the new native result
as pending rather than guessing another source or overwriting an old file.
