# Cognitive Traps

Curated list of wrong-turn patterns observed in real investigations. Each entry: the trap, why it is seductive, a concrete example, and the counter-move.

## Contents
- Trap 1: Circumstantial evidence convergence
- Trap 2: Field-semantic confusion
- Trap 3: Single-cause bias
- Trap 4: Naming assumption
- Trap 5: Probe self-verification
- Trap 6: Assumption-rescue cycle
- Trap 7: Time-of-symptom equals time-of-cause
- Trap 8: Duration of investigation biases conclusion weight
- Trap 9: Agent output equals ground truth
- Trap 10: Unverified premise
- Trap 11: Threat-model mismatch

## Trap 1: Circumstantial evidence convergence

Five indirect clues all pointing toward hypothesis H feel like proof. They are not, because they share a common cause (your mental model) that selected them.

**Example** (from this case study): Initial assumption was "VPN node rotation". Supporting circumstantial evidence:
- Client IP flipped between CN and US across requests (real)
- Request to CF hit SJC PoP (real, expected for US-routed)
- Each failed request had short duration in some log field (misread — see Trap 2)
- User was known to sometimes use VPN (real)

All four looked consistent, and the main investigator committed to "VPN instability is the root cause". The user pushed back: "I turned off VPN and it still fails." One falsifying test broke the chain.

**Counter-move**: When circumstantial evidence converges, require at least one direct test before acting. "The IP flips" is circumstantial. "The same user reproduces the failure with VPN verifiably off" is direct.

## Trap 2: Field-semantic confusion

A number from a log field means whatever that field's code defines — not what the name suggests.

**Example** (from this case study): Caddy's access log has `duration=0` and a separate warning log has `duration=5.95s`. The investigator read "duration 5.95s" and concluded "connection lasted 5.95 seconds before being reset". But that particular field in Caddy's `aborting with incomplete response` warning is the elapsed time between the abort signal and the handler winding down — not the total request lifetime. The actual request lifetime (from CLI debug log) was 130 seconds.

The investigator then built a whole theory around "CLI fails at 5-8 seconds due to a bug in chunk parsing", which was wrong at the root.

**Counter-move**: Never cite a numeric field value as evidence without checking its semantics in the source code or vendor documentation. If the field is suggestive but ambiguous, treat it as unverified until its meaning is confirmed.

## Trap 3: Single-cause bias

Real production failures often emerge from multiple cooperating defects. Finding one cause and stopping leaves the amplifying factors in place, which will trigger the next incident.

**Example** (case study in full resolution):

- Direct cause: Cloudflare edge HTTP/2 stream idle timeout at 126s
- Amplifying factor 1: Qiniu proxy does not emit SSE `event: ping` during upstream stalls
- Amplifying factor 2: Upstream Claude Sonnet 4.6 batches tool_use output (125s silences observed)
- Amplifying factor 3: Claude CLI has no client-side idle watchdog (GitHub issue documented)

Fixing only the direct cause (e.g., moving off CF) would leave factors 1-3. Factor 2 means even with a different CDN with a larger idle window, a different idle threshold eventually fires. Factor 3 means the client is blind to the stall. The durable fix addresses factor 1 at minimum and factor 2 via server-side keepalive as defense in depth.

**Counter-move**: After finding the direct cause, ask explicitly: "What amplifying factors enabled this? If the direct cause were fixed, what would still be wrong?" Document all layers, fix the most cost-effective ones.

## Trap 4: Naming assumption

Labels, tags, and names are metadata assigned by humans; they do not reflect runtime attributes. Verify via API, not by reading the name.

**Example**: A cloud instance tagged `claude4dev-spot` was assumed to be a Spot pricing instance during an incident. The instance was actually PostPaid; the tag was legacy from a pre-migration period. The investigator spent 10 minutes down the wrong path (Spot reclamation theory) before checking `DescribeInstanceAttribute`.

**Counter-move**: In incident response, the first step when a property matters is to query the authoritative API, not to read the name.

## Trap 5: Probe self-verification

A probe that uses the thing it is probing to deliver its result cannot independently verify that thing.

**Example**: Using `curl` through a VPN to test whether the VPN is dropping connections. If the VPN drops, `curl` reports an error, which is what you expected — but the same error would occur if the remote host rejected the connection. The probe did not isolate.

**Counter-move**: Probes must be structurally independent of the subject. To test the VPN, use a second network path (mobile hotspot) to compare. To test a CDN, bypass it with `--resolve`. The [layered isolation experiment](layered-isolation-experiment.md) is this principle systematized.

## Trap 6: Assumption-rescue cycle

When evidence contradicts a hypothesis, the temptation is to add a modifier: "yes, but only under condition X". This rescues the hypothesis at the cost of unfalsifiability — eventually the modifiers stack to "it fails when it fails".

**Example** (case study): After "VPN instability" was falsified by "still fails with VPN off", a rescue was "well, maybe the VPN client has a residual system-level hook". Adding more conditions without evidence.

**Counter-move**: When a falsifier fires, the correct response is to scrap the hypothesis, not to narrow its scope. Return to Step 2 of the workflow and write new hypotheses.

## Trap 7: Time-of-symptom equals time-of-cause

The time the user notices a symptom is often much later than the time the cause first engaged. Correcting this requires examining upstream time series.

**Example**: Disk fills at midnight, various retries and degradations through the morning, user-facing failure at 10:30 AM. The 10:30 timestamp is when to start looking at logs, but if you examine only the 10:30 ± 5 minute window you will miss the midnight root cause.

**Counter-move**: Always extend the investigation window backward by at least 10x the symptom-to-report time, or to the last known-good state. Look for monotonic metric trends crossing thresholds, not just error spikes.

## Trap 8: Duration of investigation biases conclusion weight

After four hours of deep investigation, the investigator has a strong psychological bias toward "we must be close" and against "start over". This leads to over-weighting marginal evidence that fits the current theory.

**Example** (case study): After 3 hours of circumstantial evidence for "VPN theory", then "CLI bug theory", then "Caddy IdleConnTimeout theory", the investigator was resistant to "start a fresh experiment from scratch". The user pushed to switch approach. The experiment resolved in 10 minutes what 3 hours of deep reasoning had not.

**Counter-move**: Time-box. If a hypothesis has not been confirmed (not just "consistent with evidence", but actually confirmed by a direct test) within a set time, switch to a structurally different approach. Layered isolation or an experiment is a good default switch.

## Trap 9: Agent output equals ground truth

Spawning an agent to investigate returns text that reads authoritatively. Accepting that text without verification treats the agent as a peer reviewer, but agents do not have skin in the game — they over-produce risks and claims.

**Example**: A counter-review agent cites "Cloudflare proxy_read_timeout is 100s" with high confidence. This appears to match the observed 130s. The investigator concludes CF is the cause — except the actual CF limit in this case is a different timeout (HTTP/2 stream idle, ~126s), and "100s" was the agent generalizing from community posts without matching the exact protocol.

**Counter-move**: Every agent claim that feeds into an action needs at least one cheap verification step. If the agent says "X is 100s", test whether X is actually 100s in your environment (or find the primary source). Filter agent findings through the [four-question filter](counter-review-pattern.md#the-four-question-filter).

## Trap 10: Unverified premise

Investigating a symptom that was never directly observed. The premise enters the conversation as "users say X is happening" or "the alert fired so X must be failing" and drives hours of hypothesis-building before anyone checks whether X is actually occurring.

**Example**: A user reports "our SSE connections keep dropping at 130 seconds". The team spends 3 hours building a keepalive patch. On the verification run before ship, they realize the original symptom was a single-digit frequency over the last week — well within normal disconnect noise for that service — and the "130-second pattern" was coincidence across two samples.

**Another example** (surfaced by counter-review in this case study): the proposed fix was server-side SSE keepalive. Counter-review asked: "does the user have direct evidence the RST is actually happening right now, or is this inferred from a past incident?" The fix was for a real incident that *had* occurred, so the question was answered correctly — but the habit of asking is what prevents investigating a non-problem.

**Counter-move**: Before investigating, answer one question: "What direct artifact (log line with timestamp, captured packet, screenshot) shows this symptom is currently real?" If the answer is "nothing I can point to", the first action is not investigation — it is adding the telemetry and waiting for the next real occurrence. This is faster and more correct than investigating on vapor.

See [SKILL.md Step 0.5](../SKILL.md) for the verification checklist.

## Trap 11: Threat-model mismatch

Proposing a fix that operates on the wrong hop. The hypothesis correctly identifies that *some layer* is at fault, but the implementation lands at a different layer, so the fix cannot actually remediate the real cause.

**Example** (from eval-3 baseline in this skill's iteration-1 tests): a proposed SSE keepalive patch writes `: keepalive\n\n` to `res` (downstream client-facing connection). But the stated concern was "upstream idle > 15s". Writing bytes to the downstream socket does nothing to maintain the upstream TCP connection — if the idle timeout fires on the proxy→upstream hop, the keepalive is directed at the wrong boundary. The patch would ship without reducing the incidence of the original symptom.

This trap is particularly insidious because the hypothesis about "why" was correct (idle timeout somewhere) and the fix category was correct (keepalive). Only the *layer* was wrong.

**Counter-move**: For every proposed fix, explicitly name which layer boundary it operates on, and then check whether that boundary is the one where the problem originates. If they do not match, the fix is targeting the wrong thing regardless of how reasonable it looks in isolation.

Phrased as a question: "My fix makes bytes flow at boundary X. Is X the same as the boundary where the problem manifests?"

In the SKILL.md workflow, this is the Step-2 third-question prompt. Do it before writing code.

## Summary: the meta-move

All nine traps share a common structure: the investigator is willing to act on indirect evidence when a cheap direct test is available but was skipped.

The universal counter-move, restated:

> Before acting on a conclusion, identify the cheapest direct test that could falsify it. Run that test.

If the test is expensive, accept the conclusion is provisional and design instrumentation that will make the test cheap next time.
