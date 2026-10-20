# Audit external VAD filtering and batch coverage

Read before filtering a mixed batch with an external VAD, interpreting empty
ASR windows, or claiming that a backlog is fully processed. The executing agent
uses the selected producer's existing receipts and checkpoint format; this
procedure creates no model service, cloud queue or universal manifest schema.
Path L's integrated runner retains its tested no-speech contract and recovery
behavior; record its actual evidence rather than replacing its statuses.

## Bind the evidence before selecting work

Keep these quantities separate:

| Quantity | What it establishes |
|---|---|
| Capture counter and wall-clock interval | Acquisition activity under the observed conditions |
| Retained encoded files and manifest duration | What the recorder kept, with original identity and capture anchors |
| Decoded samples and sample rate | The sample coordinate range actually available to this producer |
| VAD candidate intervals | Model-selected windows under a named configuration |
| Attempted ASR intervals | Which source samples reached a recorded attempt, including failures |
| Readable machine text | A draft, with semantic accuracy and attribution still unverified |

Match each source's bytes/hash, original capture anchor and producer/runtime
identity before reusing results. Keep encoded manifest duration and decoded
duration separately: codec padding must not extend the claimed capture interval
or silently change the original timestamp. Label sample windows as windows,
not word alignment. Overlapping windows may contain repeated text; preserve raw
outputs before applying the existing overlap owner or human correction.

## Challenge the filter without discarding evidence

Treat an external VAD's empty selection as an observation. Retain the source;
do not turn it alone into a content verdict or deletion request. Likewise, empty
ASR text, request failure and independently verified silence are different states.
Keep the producer's error and quality status visible instead of merging them
into a synthetic successful no-speech result.

Before trusting selection across a backlog, inspect bounded excluded windows
that can falsify it: weak signal, file edges, different recording conditions,
or overlap with independently known speech. Reuse existing text and source
evidence first. If an excluded window returns readable ASR text, record a
potential mismatch; the text may itself be a hallucination. Verify against the
original speech before reporting a false-negative rate or changing a threshold.
Use a known speech control and a known silence control when calibrating a filter.
Do not classify personal/media speech or identify a person from VAD output.

## Resume only the work the evidence requires

For each source, union the producer's attempted `[start_sample,end_sample)`
intervals against its decoded sample bound, and report uncovered intervals.
Count readable, empty/unverified, failed and not-attempted work separately.
Coverage of attempts does not establish correct recognition or complete capture.

Reuse matching completed windows. If the user requires every retained sample
to be attempted, schedule only the uncovered complement. Otherwise choose the
smallest additional audit that can decide the filter's fitness; a mismatch is
not automatic permission to rerun the whole collection or switch provider.
Keep source and result identities through transport, and verify the consuming
output after transfer. A transfer receipt alone does not prove import, playback
or downstream memory eligibility.

Respect the current processing and spending constraints. Local GPU, LAN-only
transport or restricted cloud validation remain binding after an earlier, wider
authorization. Device selection, warm-service reuse, bounded requests and cache
validation stay with [execution location and comparison](execution_location_and_comparison.md).

Stop when the requested intervals have recorded outcomes and unresolved content
is explicitly retained, or a bounded audit resolves the next decision. Leave
semantic quality, speaker identity and any unexercised consumer pending; do not
rename them complete to make the batch summary green.
