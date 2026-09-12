# Hybrid History Recall

## Contents

- Contract: recall versus exact search
- One-time setup
- Build and refresh
- Boilerplate policy: what never earns a vector
- Embedding: pauses, progress, and one writer
- Query
- Status and freshness
- Platform and dependency boundaries
- State and recovery
- Maintainer smoke checks

## Contract: recall versus exact search

Use the two search paths for different claims:

| Need | Command | What it can support |
|---|---|---|
| You remember the meaning but not the wording | `history_index.py recall` | Ranked candidate sessions |
| Exact phrase, tool call/result, thinking, attachment, queue, summary, or file-history evidence | `analyze_sessions.py search` | Exhaustive scoped evidence and, after the widening ladder, an absence claim |

The recall index intentionally stores only user/assistant prose. It does not
duplicate the forensic event store. Every result includes the project, exact
session ID, internal timestamp, matched source labels, and every physical JSONL
copy that actually contains that record. The primary result path is selected
from those record-bearing copies, so an archive-only hit never points at a
newer active file that lacks the evidence.

Never convert zero recall results into “it was never discussed.” Run exact
search with the complete source set instead.

Both paths exclude prose prompts sent by the main agent to subagents by default
(`type=user` + `isSidechain=true`). They keep assistant-side subagent output.
Exact search also keeps sidechain `tool_result` records. Add
`--include-agent-prompts` only when the question is specifically “how did I
instruct the agent?”

## One-time setup

Install the pinned Chinese FTS5 tokenizer backend:

```bash
python3 scripts/history_index.py setup
```

Expected output names the resolved `libsimple` library. Setup downloads the
official `wangfenjin/simple` release for the current OS/architecture, verifies
GitHub's pinned SHA-256 before extraction, and writes a local install receipt.
The skill does not ship a platform binary or model in Git.

The verified vector backend uses Qwen3-Embedding-0.6B through MLX and is
currently Apple-Silicon-only. Other platforms retain exact search and indexed
BM25 recall; `--mode hybrid` fails visibly rather than pretending BM25 is
semantic retrieval.

## Build and refresh

Build the versioned finder database from Claude active homes plus every archive
in `~/.claude/history-sources.json`:

```bash
python3 scripts/history_index.py index --rebuild
```

The rebuild writes a separate building database, validates its schema and
frontier, checkpoints it, and only then atomically replaces the active index.
Incremental reconciliation is one transaction: a mid-update failure cannot
leave half the sessions updated under the previous complete marker. Session
freshness fingerprints include content SHA-256, not only size and mtime.
An earlier POC database was never altered or trusted as a baseline: it had no
schema/provenance metadata and its checked-in fresh-build schema drifted from
the live database. It was retired after a source-presence audit confirmed it
was fully derivable and held no unique conversation content.

Run an incremental prose/FTS refresh after new conversations:

```bash
python3 scripts/history_index.py index
```

Scope a diagnostic build when needed:

```bash
python3 scripts/history_index.py --db /tmp/tinkle_project-recall.db \
  index --rebuild --project /absolute/project/path
python3 scripts/history_index.py --db /tmp/tinkle_main-only-recall.db \
  index --rebuild --main-only
python3 scripts/history_index.py --db /tmp/tinkle_custom-source-recall.db \
  index --rebuild --history-sources /path/to/registry.json
```

The default database is reserved for the full registered source set. A database
records the exact project/source scope that built it, and incremental refresh
refuses a different scope instead of treating everything outside the narrower
view as deleted.

Build semantic chunks, then embed until `remaining` is zero:

```bash
uv run --with chonkie --with transformers \
  python scripts/history_index.py chunk

uv run --with mlx-embeddings --with numpy --with sqlite-vec \
  python scripts/history_index.py embed --download-model --max-seconds 1800
```

`chunk` records an explicit completeness marker. If one record cannot be
chunked, it fails with that record ID instead of silently embedding a truncated
whole-message fallback. `embed` refuses incomplete chunks and is incremental:
a bounded run commits completed vectors and exits normally, so re-run the same
command to continue. The query path will not claim hybrid readiness while any
message lacks chunks or any usable chunk lacks a vector. Chunks, vectors, and
queries must all resolve the same recorded model revision; mixing revisions is
an error that requires a rebuild.

Embedding is memory-bounded by default: batch size 16, an 8 GiB MLX memory
limit, and a 0.5 GiB Metal cache limit. Source rows are streamed from SQLite,
and every completed batch drops its arrays and clears the MLX cache. Override
with `--batch-size`, `--memory-limit-gb`, or `--cache-limit-gb` only after a
bounded canary demonstrates a stable working set; the memory limit is a hard
stop, not a throughput recommendation.

Why this is load-bearing: on 2026-08-27 the former batch-64 loop had no cache
limit and never called `mx.clear_cache()`. During a real incremental run, its
process was user-observed past 70 GiB and was killed with exit 137 after 12,800 chunks. MLX's
Metal allocator keeps freed buffers for reuse unless its cache is bounded or
cleared. After the fix, a 90-second real-index canary embedded 1,872 chunks,
held observed process RSS near 1.5 GiB, reported a 2.13 GB MLX active-memory
peak, and exited normally under the 8 GiB limit.

## Boilerplate policy: what never earns a vector

Most of what a harness writes into a transcript was never said by anyone. Two
mechanisms keep it out, at two different layers.

**Records: machine-injected blocks are dropped by prefix.** Each provider has
its own list, because the evidence is per harness: Codex delivers
`<user_instructions>`, `<environment_context>`, `<goal_context>`,
`<subagent_notification>` and `<skill>` as `role="user"` messages, and Claude
Code delivers `<task-notification>` and `<teammate-message` the same way on the
main thread — past the sidechain test that hides agent prompts, so they used to
rank exactly like something a person typed. The Claude pair was measured at
4,417 records across 712 sessions and 7.66M tokens, 11.5% of all Claude token
mass, every one of them stored with `noise=0` and `agent_prompt=0`. Extraction
skips these, and `index` also sweeps records already stored, because a session
is only re-extracted when its file changes: an archived rollout would otherwise
keep its injected records forever. The sweep is reported as `records_pruned`,
matched with `substr` rather than `LIKE` (every Codex prefix contains `_`, which
LIKE reads as a wildcard), scoped to the provider the evidence came from, and
run before the FTS rebuild — `records_fts` is external-content, so a deleted
record stays lexically searchable until the index is rebuilt from its content
table.

**Chunks: a verbatim repeat keeps exactly one embeddable copy.**
`BOILERPLATE_MIN_COPIES = 3` is the threshold, applied on `chunks.text_hash`
(schema v3). Measured on the live index: 68% of the 125,687-chunk embedding
backlog was exact duplicates by text, 94% of the duplicated texts appeared in
two or more sessions, and tagged plus untagged boilerplate together accounted
for 42.6M of the 60.7M backlog tokens. The already-embedded set carries roughly
23M tokens of the same material. Only the lowest-id copy stays `usable=1`; the
rest become `usable=0`, which means *lexically searchable, but no vector*:
`usable` is consulted only by the embed queue, the vector query join and the
status counts, while BM25 runs on `records.fts_text` and never looks at chunks.
Nothing is deleted, so a text that falls back under three copies is restored on
the next pass. The pass is idempotent and runs on every `chunk` invocation,
including one that added nothing — the policy depends on what is stored, not on
what that run produced. The nightly `chunk` stage runs without `sqlite-vec`, so
it cannot drop the demoted vectors: `vectors_dropped` comes back `null` and
`embed` removes them before it decides what to embed, reporting how many as
`demoted_vectors_dropped`. `non_embeddable_chunks` is reported either way and
is not that deferred work — it counts every `usable=0` chunk, demoted
duplicates plus chunks too short to embed at all, so it is a standing property
of the index rather than a queue that drains to zero.

## Embedding: pauses, progress, and one writer

**The loop pauses on host pressure, not on a timer.** It used to
`time.sleep(4)` every eight batches unconditionally. Measured 2026-09-12, that
sleep was 120 s of a 155 s nightly embed — 77% of the wall clock, and 41% even
on the longest chunks — and it did nothing about the failure it was meant to
prevent, because it slept exactly as long when the host was idle as when the
host was thrashing. The loop now reads
`sysctl -n kern.memorystatus_vm_pressure_level` (1 normal, 2 warning, 4
critical) on the same cadence and only sleeps while the host is at warning or
above, backing off 1, 2, 4, 8, 16, 30 s and re-checking until it clears. Any
probe failure, timeout or non-Darwin platform reads as normal: an unreadable
level is not evidence of pressure, and refusing to embed because `sysctl` is
missing would turn a diagnostic into an outage. A pause prints one line when it
starts, one when it ends, and a heartbeat every minute in between — on stderr,
because stdout has to stay a single JSON document — so a long wait is never
mistaken for a hang. This signal is the right one because MLX's own counters
cannot explain the failure: the process was killed twice by the host while MLX
peaked at 2.07-2.41 GiB on a 128 GiB machine.

**A pause is bounded, and it is a safe point.** The pass holds the writer lock
while it waits, so an unbounded pause does more than overrun: `--max-seconds
10800` exists to keep the nightly embed out of the working day, and the next
night's `index` refuses to start while the lock is held. The pause therefore
takes the run's own deadline (`started + --max-seconds`) and returns when it is
spent, letting the loop stop as `max_seconds`; it re-reads the deadline at the
top of each iteration rather than mid-sleep, so it can overshoot by at most one
backoff step. An unbounded run has no deadline, so a second bound applies to
both: pressure that has not cleared in `EMBED_PAUSE_CEILING_SECONDS` (600 s,
roughly four times a healthy end-to-end nightly embed) ends the pass through its normal
commit path with `stop_reason=host_pressure`. The loop also commits the
heartbeat and the vectors it already holds immediately *before* waiting: the
pause fires every eight batches and the checkpoint every `EMBED_COMMIT_EVERY`
chunks, so without that commit a kill during the very wait that exists to avoid
being killed would discard up to a checkpoint's worth of finished work.

**Batch size is not a throughput lever.** Compute-only, on this index's own
365-token chunks: 44 chunks/s at batch 16 against 33 chunks/s at batch 48, with
MLX peak between 2.07 and 2.41 GiB in every configuration including 602-token
chunks. The default stays 16. The nightly wall-clock difference people
attributed to batch size was the sleep.

**Progress is measured in tokens.** Chunks are a poor unit for an ETA when the
backlog runs 365-602 tokens per chunk, so every commit prints embedded chunks
*and* tokens against the totals, the rate over the window since the previous
line (not the average since the start, which hides a run that is slowing down),
an ETA derived from remaining tokens over that recent token rate, and
`mx.get_peak_memory()`. The old line printed active plus cache memory *after*
`clear_cache()`, understating the real peak by about 1.8x. Progress lines go to
stderr, so `embed --json` leaves stdout one parseable document — the launchd
job captures both streams in the same log, so nothing is lost. `embed` returns
`embedded`, `embedded_tokens`, `remaining`, `remaining_tokens`,
`orphan_vectors_dropped`, `demoted_vectors_dropped` and `stop_reason`. The two
drop counts are the receipt for the only destructive step in this stage, and
they are the deferred half of the chunk stage's `vectors_dropped: null`: an
orphan is a vector whose chunk no longer exists, a demoted one is a vector
whose chunk is now `usable=0`. `index --json` keeps the same rule — its
per-500-session build progress goes to stderr too, so a fresh build or
`--rebuild` still prints one JSON document on stdout.

**One writer at a time.** `index`, `chunk` and `embed` take an exclusive
`flock` on `<db_path>.lock` for the length of the command, wait up to
`WRITER_LOCK_WAIT_SECONDS` (900 s, announced on stderr) if another run holds
it, and only then fail with the lock's path. The wait exists because the
nightly script treats any non-zero exit as a failed night: refusing instantly
made a one-second overlap with a manual run cost that night's index, chunk
*and* embed. Nothing coordinated a manual run with the
03:30 nightly one before: two embed passes read the same backlog and then
insert the same `vec_chunks` rowids, and the loser dies on
`sqlite3.IntegrityError`, which the memory-boundary handler does not catch. The
lock is released when each command exits, so the nightly `index` → `chunk` →
`embed` sequence passes it hand to hand.

## Query

Auto-select hybrid only when the indexed model revision and every usable vector
are present; otherwise label the output `mode=bm25`:

```bash
uv run --with mlx-embeddings --with numpy --with sqlite-vec \
  python scripts/history_index.py recall 'meaning remembered, wording forgotten'
```

Require the hybrid path, failing if it is incomplete or unavailable:

```bash
uv run --with mlx-embeddings --with numpy --with sqlite-vec \
  python scripts/history_index.py recall 'query' --mode hybrid
```

Useful controls:

```bash
python3 scripts/history_index.py recall 'query' --mode bm25
python3 scripts/history_index.py recall 'query' --project /absolute/project/path
python3 scripts/history_index.py recall 'query' --exclude-session <current-session-id>
python3 scripts/history_index.py recall 'query' --include-agent-prompts
python3 scripts/history_index.py recall 'query' --json
```

The current session can match text just typed. Exclude its session ID before
accepting a result as historical evidence.

## Status and freshness

Read database completeness without walking the source corpus:

```bash
uv run --with sqlite-vec python scripts/history_index.py status --json
```

Add `--check-sources` to compare every current session-copy fingerprint with the
indexed frontier. This is slower because it enumerates and content-hashes the
source corpus. The requested source/project scope must exactly match the stored
database scope; a mismatch fails instead of calling healthy out-of-scope
sessions stale:

```bash
uv run --with sqlite-vec python scripts/history_index.py status --check-sources --json
```

Status reports the schema, tokenizer, model revision, session/record/chunk/
vector counts, missing chunk records, missing vectors, both completeness
markers, last successful indexing time, complete frontier, and stale/missing
session count. Do not copy those changing values into documentation; compute
them when needed.

It also reports the embedding lifecycle: `last_embedded_at` is written at every
embed commit rather than only at the end, and `embed_stop_reason` is one of
`running` (claimed in the same transaction that starts the pass), `complete`
(the pass reached the end of its queue), `max_seconds` (it hit its time
budget), `host_pressure` (host memory pressure outlasted the pause ceiling),
`memory_boundary` (MLX stopped at the configured limit) or `warmup_failed`
(MLX failed before the first batch); the last two commit their marker before
the error surfaces. `complete`, `max_seconds` and `host_pressure` all exit 0:
the pressure stop leaves through the normal ending, not through an error. A
host that stays under pressure therefore advances a few batches a night and
stops, while the exit code — the only thing the nightly wrapper checks — still
says OK. Nothing but `embed_stop_reason` and a `remaining` count that will not
fall can show that, so alert on the status fields rather than on the exit
status. `running` is what makes a killed pass legible: host OOM and Ctrl-C run
no handler, so without a marker written on the way in, status would
report the *previous* pass's ending. Read the reason with the heartbeat — a
`remaining` count alone cannot distinguish a run still working from one that
stopped at a bound hours ago, and `running` next to an hours-old
`last_embedded_at` is a pass that was killed. `vectors_complete` is now derived from the live
backlog at start, at every commit and at exit, so a status check that lands
mid-run reads the last honest answer instead of a `false` the current run wrote
about work it had not done yet.

## Platform and dependency boundaries

- `--help`, exact search, and registered unit tests import no optional ML
  dependency.
- `setup` supports the pinned official release assets for macOS arm64/x64,
  Linux x64/arm64, and Windows x64/arm64/x86. A platform without a verified
  asset fails with the supported matrix.
- Chinese indexed BM25 requires SQLite FTS5, extension loading, `libsimple`, and
  its Jieba dictionary. Missing capability is an error with the next command,
  not a silent `unicode61` fallback that loses two-character Chinese terms.
- Database filenames are converted with filesystem URI escaping before a
  read-only open, so spaces, CJK, `%`, `?`, and `#` cannot redirect SQLite to a
  different file. Broken or wrong-architecture tokenizer libraries return one
  actionable index error rather than an uncaught traceback.
- Hybrid vectors require Apple Silicon, `sqlite-vec`, `mlx-embeddings`, NumPy,
  and one explicit Qwen snapshot. Multiple installed snapshots require
  `--model-path`; the tool never guesses which revision owns existing vectors.
- Codex and Kimi are indexable but never implicit. `index` covers Claude unless
  `--codex` / `--kimi` is passed, and the database records which providers it
  actually holds. Read that back rather than assuming: `status` reports the
  bound sources, every `recall` result carries its `provider`, and the
  `coverage` line names the providers the index does **not** hold. Asking
  `recall --provider` for an uncovered provider fails loudly instead of
  returning zero rows that look like absence.
- Codex is a large corpus — roughly 9k rollouts and 40 GB on the maintainer
  machine, of which about 9% of records are indexable prose. Adding it multiplies
  record count and costs a proportional embedding pass, so turn it on
  deliberately rather than wiring it into a daily job by default.

## State and recovery

Mutable state defaults to `~/.claude-history-index/finder-index-v1.db`. Override
the directory with `CLAUDE_HISTORY_INDEX_HOME`, or one invocation with `--db`.
User data never lives inside the skill installation, so plugin updates cannot
erase it.

The CLI reconfigures stdout/stderr as UTF-8 when the host permits it. Chinese
history and emoji therefore remain printable under Windows or redirected
non-UTF-8 environments instead of failing after a partial result.

The index is rebuildable. The JSONL sources and their registered archives remain
authority. If status reports schema mismatch, incomplete build, stale sessions,
or model-revision mismatch, rebuild or refresh from those sources; do not patch
the SQLite schema by hand.

Schema v3 adds `chunks.text_hash` and its index for the duplicate-chunk policy.
The upgrade is an in-place `ALTER TABLE` plus a batch-committed backfill, run by
`index`, chaining v1 → v2 → v3 in one call: an older index already holds every
record and every vector, and hours of recompute is not an acceptable price for
one column. Each step checks the table before altering it and commits each
backfill batch, so an interrupted migration re-runs cleanly, and none of it
needs `sqlite-vec`.

## Maintainer smoke checks

Run the standard-library tests on every platform:

```bash
python -m unittest discover -s tests -p 'test_*.py'
```

On macOS arm64, additionally build a disposable project-scoped index and query
it through real `libsimple`; then chunk/embed a small fixture and verify one
lexical-only, one vector-only, and one two-route result. The disposable filename
must use the `tinkle_` prefix. Never point a smoke test at the active index.
