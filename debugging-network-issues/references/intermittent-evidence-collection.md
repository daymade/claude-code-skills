# Collect an intermittent incident without losing the failure

Use this READ-DO procedure when the failure may recur after the current session,
when a restart would erase volatile evidence, or when a collector itself failed.
Keep recovery, evidence coverage, root-cause attribution and permanent repair as
separate results. A new collector version does not establish a new causal finding.

## 1. Bind the question and collection window

Name the competing causes the next observation can separate and the signal each
requires. Inspect native logs and current code before adding another observer.
An exported message may be shorter than the original kernel message; identify
the producing buffer and truncation boundary. More copies of a truncated field
cannot recover the missing bytes. Record unavailable kernel, firmware or hardware
signals as gaps, and choose an alternative falsifiable observation when possible.

Resolve these inputs for this run: exact target/firmware, authorized interfaces
and management path, credential owner, output directory, interval, absolute end
time, per-round deadline, total storage allowance and minimum free space. Reuse
the existing client and parsers when suitable. Reject expired windows and missing
required identity; do not inherit incident dates, host paths, addresses or build
offsets from a previous temporary script. Keep user configuration outside the
update-owned package.

Before reusing a script, inspect its actual imports, defaults, side effects and
stop conditions. Parameterization is incomplete while an old hard-coded deadline
still caps a new configured window. Test the ordinary entry with different paths
and a non-secret target; do not promote a one-off collector unchanged.

## 2. Preserve bytes before interpreting them

Use an operator-owned private directory and restrictive file permissions. Raw
responses and packets can contain secrets; keep originals out of public source,
console output and review examples, and sanitize derived status separately.

Write received bytes incrementally to a uniquely named partial artifact before
decrypting, decompressing or parsing. Retain partial/error responses within the
declared bounds. Record attempt/completion times, transport outcome, byte count
and hash without credentials or authenticated URLs. Finalize a complete transfer
atomically and verify it by reading the saved bytes.

Validate transfer completeness and the format's own integrity checks separately.
List every archive member, including unknown names and zero-length members;
never assume a fixed allowlist covers future crash artifacts. Avoid extracting
untrusted archive paths. An intact archive can contain an empty or malformed log.
Preserve the original and isolate that member's decode failure rather than
discarding the package or stopping every channel.

For each decoded channel retain its time/sequence range, overlap and observed
gaps. A sequence gap is an observation, not proof of loss until producer filtering
and counter semantics are known. Deduplicate mirrored ledgers without erasing
real repetition within one channel. Do not sum their duplicate events.

## 3. Separate collection planes and their failure states

Run the needed control, data, client and packet observations independently. A
management timeout must not skip that round's data-plane probe. Bind probes to
the intended interface/path and inspect the actual local/remote addresses; use
packet evidence when routing or a proxy could change the path.

For each plane expose last attempt, last successful observation, last error,
output freshness, current phase and terminal reason. Fresh failure events do not
mean fresh valid data. Check decoder/member status as well as raw-download age.
An unknown observation is not network health. Validate a known-working path and
a safely failing path before trusting the probe.

Prefer one native export executor plus independently checked replicas when the
device stages exports in shared files. Before enabling multiple exporters, inspect
the server implementation and verify concurrent archive/member consistency;
two successful HTTP replies do not establish noninterference. An independent
client/air observer can continue even when native export is unavailable.

## 4. Capture the lead-up, not only the alarm

Start the required client/kernel event stream before recurrence. On macOS inspect
`/usr/bin/log help predicates`, select the needed `process`, `subsystem` and message
fields (such as `composedMessage`), and include the required info/debug levels.
Do not assume JSON output keys are accepted as predicate fields.
An airport process filter alone can miss kernel
events with an empty subsystem. Measure volume and retain bounded segments.

Use [packet capture recipes](packet-capture-recipes.md#wireless-management-and-control)
for radio observations. Verify packets from the target, not merely an opened
capture file. Record channel dwell/survey windows and drop counters; a single
radio cannot certify continuous coverage of two bands. Preserve enough packet
length for the question and inspect captured versus original lengths.

Keep observing through the agreed window after an anomaly unless the user chose
a shorter post-event window or a hard resource bound is reached. Do not silently
stop after the first alarm or automatically reboot the failing target.

## 5. Bound work and preserve shutdown output

Use a per-operation wall-clock bound as well as socket timeouts and the overall
deadline: a slow stream can keep resetting a read timeout. Bound received bytes,
decompressed sizes, retained storage and free-space reserve. On a bound or sink
failure, write the specific terminal/degraded state where possible and preserve
existing evidence. Derive the allowance from measured growth over the requested
window; registration alone does not prove the observer is still collecting.

When stopping a child owned by this experiment, signal it and drain stdout and
stderr concurrently until EOF or a bounded grace deadline before escalating.
Waiting first can block its last flush and lose the packet/drop summary. Record
exit status, escalation and any un-drained bytes. Do not terminate another
session's process. Python documents the PIPE/wait deadlock and the limitations
of buffering all output in memory in its [subprocess reference](https://docs.python.org/3/library/subprocess.html#subprocess.Popen.wait).

For macOS service deployment and authenticated restart, use `macos-watchdog` in
`daymade-macos@daymade-skills`. Resolve its installed entry rather than inventing
a sibling path inside this package. If unavailable, keep raw/manual collection
running within authorization and state which background-recovery step is not yet
verified; do not claim an unavailable helper installed or restored the observer.

## 6. Correlate clocks with an error bound

Retain source timezone, local send/receive times and useful monotonic/counter
evidence. For a cross-host query bracket the returned remote time between local
send and receive; record the resulting offset interval and query duration.
An interval containing zero does not establish clock skew. Repeat at the needed
cadence to detect drift or jumps.

An export header, sample start and packet timestamp are different observations.
A difference can include formatting resolution, caching and generation latency;
do not attribute it to one host's clock without the independent calibration.

## 7. Accept the collector against failures

Use retained real artifacts where available and safe controlled failures for
unobserved branches. At minimum establish:

| Input/condition | Observable result |
|---|---|
| Valid and malformed/partial packages | Original bytes survive both; decode status differs |
| Unknown or empty member in an intact archive | Member is listed; other channels continue; later valid data resumes |
| Management failure with a working alternate plane | Alternate-plane observation still occurs |
| Capture file with only its header | Report no observed packets, not successful radio coverage |
| Child writes a large final stdout/stderr burst | Tail and final counters survive, or the loss is explicitly recorded |
| Restart loses memory-only credentials | Authentication is unready until re-established; PID alone is not recovery |

Stop improving instrumentation when these checks cover the authorized question.
Report exactly what new evidence can now decide and which original causal
question remains unanswered.
