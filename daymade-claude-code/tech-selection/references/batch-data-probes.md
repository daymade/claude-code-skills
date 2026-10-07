# Representative batch-data probes

Apply when selecting or replacing ingestion, indexing or storage machinery. Use the project's actual capacity and consumer contract. Stop after the necessary cases establish the next decision; unknowns remain unknown. Do not invent a distributed requirement from hypothetical future volume.

## Freeze the comparison

Use one representative corpus and known-answer queries for every candidate. Record raw bytes separately from extracted text and index size. Preserve source/version identity, byte hashes and consumer filters. A document may have several source locators while its reusable extraction is computed once.

Choose correctness answers without reading the implementation: a rare term at the end of a long tool log must remain discoverable; a source-filtered query must return the expected document even when other sources occupy the global top results. Include real Chinese short substrings, code identifiers, punctuation and exact-match queries where those are required. Token search passing ordinary prose does not establish these capabilities.

## Cases and observations

| Case | Required observation |
|---|---|
| Baseline and twice the input | Measure actual bytes read, chunk visits, extraction calls, writes, wall time and peak memory. Repeatedly walking every preceding chunk is a growth failure even when the small input finishes. Do not infer linear behavior from one elapsed-time sample. |
| No source changes | Repeating the run must not reparse unchanged records or rewrite the whole archive/index. Record the work actually avoided. |
| Append one record | Existing extraction and checkpoints remain reusable; only the new record and necessary index mutations are performed. |
| Same content from another machine/path | Reuse compatible extraction while retaining each independent provenance locator. Different interpretation context must not share incompatible extraction. |
| Change parsing semantics | Recompute affected extraction. Changing query pagination, a comment or unrelated transport code must not invalidate all extraction. Test both a relevant and irrelevant change. |
| Interrupt and restart | Resume from a documented checkpoint without missing or duplicating logical records. An acknowledged write has a defined durability boundary. |
| Empty or unavailable index | Recover an original from its archive manifest and content hash without consulting the index that is being rebuilt. Test a missing index, not merely a working index with a restore flag. |
| Long record and filtered search | Verify the known tail term and source-filtered result after the complete extraction/search/consumer path. A parser unit test or unfiltered top-K result alone is insufficient. |

Use healthy controls and an actually observed failure shape. For example, a stream with four/eight/sixteen chunks must visit each required chunk once rather than walking ten/thirty-six/one-hundred-thirty-six chunk headers. The values demonstrate a diagnostic input, not a production throughput promise.

For each result retain the exact command, candidate version, corpus identity, expected answer, observed answer and coverage boundary. Do not silently replace an unavailable engine probe with documentation claims. Keep implementation-only tests separate from evidence that the consumer receives the right answer. Do not activate production rebuilds to gather these measurements when migration is stopped.
