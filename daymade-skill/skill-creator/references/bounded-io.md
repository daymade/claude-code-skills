# Bounded file reading and command capture

Use these standalone tools for ordinary file reads and already-authorized command
capture. They use Python 3's standard library and do not load or create a Skill.
The maintained implementations are the repository's
[reader](https://github.com/daymade/claude-code-skills/blob/main/scripts/bounded_file_read.py)
and [capture tool](https://github.com/daymade/claude-code-skills/blob/main/scripts/capture_command.py).

Install the optional source-backed commands with:

```bash
python3 <repository>/scripts/install_bounded_io.py --bin-dir <absolute-bin-directory>
```

The installer prints and verifies both entry points. Without installation, replace
`bounded-file-read` with `python3 <repository>/scripts/bounded_file_read.py` and
`bounded-command-capture` with `python3 <repository>/scripts/capture_command.py`.
Keep paths absolute; quote paths containing spaces.

Skill Creator keeps its existing `creator.py skill_read_plan`, direct
`skill_read_plan.py`, and capture entry points as compatibility adapters. Its
standalone bundle includes generated copies of these same implementations and
this contract. Maintain these sources here; `<repository>/scripts/sync_bounded_io.py --check`
rejects distribution drift. Business callers use the generic commands above.

## Large command output

When the host returns a running-session or cell identifier, the executing agent
preserves the complete result: output, identifier and available status fields.
Forwarding only the text field discards the handle needed to observe completion.
Resume through that host's documented wait/poll API until a terminal exit status
is received. Partial output without terminal status remains running or unknown.
If the handle is lost, recover the existing run through the host's supported
status/artifact query; leave its outcome unknown when that evidence is unavailable.
Do not repeat a write to replace missing completion evidence.

Before a command that may produce large output, choose an absolute new private
output directory outside the shipped Skill. Treat unmeasured JSON output as
potentially large; scope or count flags do not establish a byte bound. Capture
raw stdout/stderr and the exit status before inspecting its shape or selecting
values. Use the standalone capture owner:

```bash
bounded-command-capture \
  --cwd <absolute-existing-business-directory> \
  --output-dir <absolute-new-private-output-directory> \
  -- <already-authorized-executable> <arg>...
```

Preserve the caller's business working directory with required `--cwd`; a wrapper must not change the child working directory. Supply an absolute,
task-owned `--output-dir` that does not exist. The owner validates argv, paths and
the summary budget before spawning, then creates the directory privately and
exclusively instead of overwriting an existing path. Add
`--max-output-bytes <bytes>` before `--` to set the metadata envelope budget.

Run only the caller's already-authorized argv. The owner neither selects nor
authorizes commands and is not a permission sandbox. It uses `shell=False`, so
shell metacharacters remain literal; ordinary empty arguments after the nonblank
executable also reach the child unchanged.

Read one bounded JSON metadata envelope on wrapper stdout, persisted unchanged as
`result.json`. It contains real paths and byte counts for separate `stdout.bin`
and `stderr.bin` files, plus status and the exact child returncode; it does not
contain command text, environment values or output bodies. The serialized envelope,
including metadata and its newline, stays within the selected budget. Unusable
budget/path metadata fails before launch. Separate files preserve stream identity;
they do not establish cross-stream ordering.

Expect `child_exited` with the exact integer returncode, including a negative
signal code, or `spawn_failed` with a null returncode and explicit error class and
errno. A spawn failure exits 127 at the wrapper. A nonzero child remains nonzero
at the wrapper, and its metadata is persisted as well. Do not rerun the command to
recapture output or replace failure evidence.

Inspect the saved files through the bounded reader below. Bind each range to the
returned SHA-256 and return one reader envelope per outer call. Use `--schema-json`
for JSON key/type/count metadata, then select exact scalar leaves with repeatable
`--json-pointer /path` arguments and the returned `--expect-sha256`. Missing keys
fail; a container requires a schema query or explicit leaf selection. Do not
construct a summary by excluding guessed field names: an unexpected key can carry
the entire payload. Preserve present null/empty values as distinct from missing.

If a response is already truncated, read the missing evidence from the saved output;
if nothing was saved, rerun only a safe read-only command or retrieve its existing
artifact. Do not rerun a write merely to recapture its output. Truncated responses
cannot establish completeness. File length alone does not justify reorganizing
the Skill.

## Complete file reads

### Codex Code Mode receipt

When the host exposes `functions.exec`, use one literal absolute `cat` or bounded
`sed` command per cell. Emit the source text separately from command metadata;
keep both the inner command and outer response within their output budgets:

```javascript
const result = await tools.exec_command({
  cmd: "sed -n '1,20p' '<absolute-source-file>'",
  max_output_tokens: 2000,
});
text({ exit_code: result?.exit_code, session_id: result?.session_id });
if (result === null || typeof result !== "object" || Array.isArray(result)
    || result.exit_code !== 0 || typeof result.output !== "string"
    || Object.prototype.hasOwnProperty.call(result, "session_id")) exit();
text(result.output);
```

Replace the path and range with the selected source before execution. This is a
range read, not a whole-file loading claim; use the hash-bound plan below when
the complete file is required. A running command must reach its terminal receipt
before its output can establish a completed read.

For hosts with a loading-evidence adapter, an inner PostToolUse observation may
say `model-facing-receipt-pending` before the outer cell returns. The next guarded
boundary can reconcile that returned text. Check the resulting source-bound
coverage rather than rereading solely because of the earlier pending notice.
Serialized command results can also be recognized by current adapters; JSON
wrapping alone does not prove a read failed. Omitted text, partial ranges and
unrecognized host envelopes remain incomplete or unknown. This recipe neither
sets a loaded marker nor overrides the host's loading check.

### Planned ranges and whole-file coverage

Prefer the host's native Read loader. For a shell fallback, use the standalone
`bounded-file-read` command with an absolute source path. First request a plan:

```bash
bounded-file-read <file> \
  --max-chunk-bytes 2000 --max-output-bytes 6000
```

Choose a budget below both the inner tool and outer response limits; these values
are starting choices. `--max-output-bytes` caps the final UTF-8 JSON envelope,
including escaping, metadata and its newline. Oversized content fails with exit 2
before any content is emitted. Error envelopes obey a valid usable budget;
malformed arguments with only an unusable budget may return a small generic
diagnostic or no output, never source content. Success exits 0. The reader
does not constrain several results aggregated into one outer tool response or
prevent truncation when the caller chooses a smaller token budget. Return one
reader envelope per outer call, with adequate inner and outer response budgets;
do not append several pages into one capped payload.

Read a planned range in a separate call, binding it to the returned `sha256`:

```bash
bounded-file-read <file> \
  --lines 1:20 --expect-sha256 <sha256> --max-output-bytes 6000
```

Use one-based inclusive line ranges; use `--chars 0:200` for a zero-based,
half-open Unicode character range when a single line is too large. `--chars` can
also accompany exactly one `--json-pointer` to slice a large string leaf. It
cannot accompany several pointers or a schema query. Read JSON shape first with
`--schema-json`, optionally `--at-pointer /path`, then request only the needed
leaves. Character positions count decoded codepoints; output limits count bytes.

If a first plan refuses an oversized plain-text line before returning a hash,
compute that same file's SHA-256 with a local hashing tool, then pass the digest
with `--expect-sha256` to the character read. Do not remove the hash requirement.

Plan/schema responses contain only a bounded page. Follow `next_cursor` using
`--cursor` and the same `--expect-sha256`; `plan_complete`/`schema_complete` are
true only when one response contains the whole plan/shape. Collect pages against
that hash. A complete plan is metadata, not source-content loading. Content
responses identify the requested range or pointers and `source_coverage`;
`requested_range_complete` describes the selection, not whole-file loading.

Track successfully received content ranges against the source hash. A changed
hash fails rather than stitching versions together. If either tool layer
truncates, reduce the budget and recover the missing range. The reader never sets
a loaded marker: preserve unknown when a host's loading-evidence adapter does not
recognize its receipt. For such a host's mandatory loading check, retain the
recognized native Read or separate literal `sed -n '<start>,<end>p' <file>` path
using the bounded plan; do not bypass the check. Do not promote a JSON selection
to a complete file read. Reuse verified loading in the same session instead of
repeatedly rereading unchanged text.
