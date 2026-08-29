# Hybrid History Recall

## Contents

- Contract: recall versus exact search
- One-time setup
- Build and refresh
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
- Codex and Kimi histories remain opt-in exact-search providers. The first
  recall-index version is Claude-only; do not imply `--codex` or `--kimi` was
  indexed.

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

## Maintainer smoke checks

Run the standard-library tests on every platform:

```bash
python -m unittest discover -s tests -p 'test_*.py'
```

On macOS arm64, additionally build a disposable project-scoped index and query
it through real `libsimple`; then chunk/embed a small fixture and verify one
lexical-only, one vector-only, and one two-route result. The disposable filename
must use the `tinkle_` prefix. Never point a smoke test at the active index.
