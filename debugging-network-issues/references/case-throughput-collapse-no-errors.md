# Case: three hours lost to a link that never threw an error

The canonical "everything is green and nothing works" incident. Unlike the other case studies
in this skill, there is **no error string anywhere in it** — no reset, no timeout, no 5xx. Every
request returned `200`. The system was simply moving bytes at roughly 1/130th of the rate it
should have, and every instrument pointed the wrong way.

It is included because the wrong turns are unusually instructive: each one was a *reasonable*
inference from a *real* measurement, and the measurements were of the wrong quantity.

## Setup

A workstation on a home network served two things over a mesh VPN (Tailscale) to a laptop:
an HTTP media service, and plain SSH. The task was bulk: fetch a few hundred media objects
and ~35 large documents. Sizes: individual objects 0.2–4 MB, documents up to 33 MB.

## Symptom

The bulk fetch was "slow." That was the entire symptom. Specifically:

- Every HTTP response: `200`
- Round-trip latency to the host: **12 ms**
- The service's own lightweight endpoint (a session list): **0.04–0.07 s**, all day
- Transport status: `active; direct <wan-endpoint>` — a *direct* path, not a relay
- Actual transfer rate, when finally measured: **0.09–0.11 MB/s**

At that rate a byte-level verification pass over ~345 objects projects to about **70 minutes**.
It ran for two and a half hours and produced nothing, because it was `--audit-only`.

Total time from "this seems slow" to the correct root cause: **about three hours**, of which that
verification pass was the single largest block.

## The wrong turns, in order

**1. "The verification pass is inherently slow."** True but useless — it reframed a symptom as
an explanation. The pass was slow *because* of the rate; treating "it verifies a lot of objects"
as the cause meant no further questions got asked.

**2. "The host's home upstream is just ~1 Mbps."** This was the load-bearing error. It is a
plausible number for a residential uplink, it explained the measurement perfectly, and **no
evidence supported it** — no one had measured the uplink, or asked what path the traffic took.
Worse, it was *actionable*: the whole task got re-planned around "this will take hours,"
including killing and restructuring work that was fine. **A wrong root cause does not merely
fail to fix the problem; it reorganizes the work around a fiction.**

**3. "It's the DERP relay."** After the laptop changed networks, `tailscale ping` showed four
relayed replies (`via DERP(<region>)`, 80–85 ms) before the fifth came back direct over the LAN
(4 ms). This looked like the answer — relay is slow, direct is fast, story closed. It was wrong,
and the record disproves it: the 0.09–0.11 MB/s measurements had been taken while the status
line read **`direct`**. The relay appeared only during the post-network-change transition.
The real variable was the network change itself; the relay was a coincidence on the path there.

**4. "The far host is overloaded."** A probe measured ~21 seconds to return 17 bytes. That reads
like a struggling server — but the probe was broken: a Windows-style object key (`…\archive\…`)
went through a shell that ate `\a` as a BEL byte, so the request carried a corrupted key, missed
every index, triggered a full scan, and 404'd. The tell was in the numbers: **21 seconds for 17
bytes is not a bandwidth symptom.** See trap 17.

## The decisive experiment

Two channels, same host, same direction, same payload size, **no shared application code**:

```bash
# Channel A — the media service under suspicion
#   7.8 MB across six objects → 73.1 s  = 0.11 MB/s

# Channel B — plain SSH, a completely different stack, timed from the receiving end
#   8.4 MB → 95.3 s = 0.09 MB/s
```

Two unrelated stacks agreeing to within ~20% is not a coincidence about either stack. **The
bottleneck is the path.** Every hypothesis about the media service — its transcoding, its
scan behavior, its concurrency — was ruled out by one command that never touched it.

> A detail worth stealing, found while writing this up rather than during the incident:
> **time the transfer from the receiving end, not from the sender's own report.** The obvious
> shortcut for channel B is to let `dd` print its own summary line, which both GNU and BSD
> versions do. That number is wrong for this purpose — it measures how fast `dd` wrote into
> its stdout, which a pipe and SSH's channel window absorb, and it never sees connection
> setup. Measured against a link whose true end-to-end rate was 44 MB/s, `dd` self-reported
> 54.9 MB/s. A sender-side rate is an upper bound on the wire rate, never a measurement of it.

## Root cause

The laptop and the workstation were on **different networks** for the slow phase; traffic took
a direct-but-WAN path. When the laptop later joined the workstation's LAN, the mesh VPN
hole-punched a LAN path to the same logical address, and the rate went to **11–16 MB/s**.

The 70-minute verification became a 1-minute one. Nothing about the service, the host, or the
VPN configuration changed — only which physical path the same address resolved to.

**What made this invisible:** the address never changed, the status field said `direct` in both
states, and every liveness signal is scale-blind (see Principle 5). There was no moment where
anything reported a problem.

## The damage the wrong assumption had already done

Working under "the link is ~1 Mbps forever," a bulk document fetch was given a 180-second cap
per file — generous at the healthy rate, impossible at the degraded one. Result: **14 of 35
documents arrived truncated**, and the fetch loop recorded **all 35 as successes**, because its
check was `HTTP 200 && bytes > 1000`. The status line arrives long before the body stops; a
transfer killed mid-body still has a `200`.

The fix has two independent halves, and the second is what made the blast radius knowable:

1. **Check the transfer tool's exit status**, not just the response status. `200` describes the
   response's beginning; only the exit code describes its end.
2. **Verify the artifact against its own format.** These were PDFs, which end in `%%EOF`. Files
   carrying the terminator: 21. Files the parser accepted: 21. **Exact correspondence, zero
   exceptions** — which promoted "some of these might be bad" into a precise list, and proved
   the cause was truncation rather than corrupt sources. Re-fetched with a workable cap, the
   truncated files came back 3–4× larger (one was 7.5 MB truncated, 33.4 MB complete).

## What to take from this

- **"Slow" is a symptom once you write it as a rate.** `0.09 MB/s over 8.4 MB` is falsifiable.
  "It feels slow" is not, and neither is "the pass takes a long time."
- **Two independent channels beat any amount of reasoning about one.** It cost one command and
  eliminated an entire subsystem from suspicion.
- **A status field that says `direct` is answering a different question than you are asking.**
  So is RTT. Neither measures capacity; the slower state here had the *better*-looking 12 ms.
- **Plausible + explains-the-data + unverified is the most expensive combination in debugging.**
  "Home uplink is ~1 Mbps" satisfied the first two and was never subjected to the third, and the
  cost was not the wrong answer — it was hours of work re-planned around it.
- **When capacity was wrong, go audit what that assumption already produced.** Timeouts derived
  from it have been silently truncating artifacts, and naive success checks have been passing them.
