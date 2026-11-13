---
name: developer-casebook
description: >-
  Historical evidence for Skill creation and maintenance failures. Read only to inspect an incident or calibrate a related regression; do not use this archive as the ordinary execution contract.
---

# Developer casebook

Use the current owning guide for instructions. Inspect these cases only when the specific historical failure or calibration is relevant; the archive does not authorize work or add default gates.

## Missed project-local Skills

**Per-project skills are structurally invisible.** They live inside an unrelated project's working tree, so they appear in no marketplace, no global skill list, and no source-repo listing; nothing you would normally open while planning a new skill mentions them. Real case (2026-07): a session built a global skill for a domain, swept the source repos, the global dirs and the other-agent dirs, found nothing, and shipped. A later conversation-history search turned up a mature project-level skill for that exact domain, a month old, sitting in one project's `.claude/skills/` — carrying eight rules the new skill lacked, including one the user had personally dictated. Every root had been checked except the per-project one, and the sweep reported "no prior art" with complete confidence.

## Duplicating an existing capability

**Why this check earns its place at the top:** a real 2026-07 session spent a day getting a third-party docx engine to produce correct Chinese business documents, then reached for the wrapper-skill branch — which skips straight past Prior Art Research. The shape it was about to ship was a fresh skill re-carrying that engine's capability. The correct shape was a **reference chain**: third-party engine untouched → a thin increment skill holding the correct usage plus the verified generator script → the domain-workflow skill calling that increment. The user had to catch it twice before it landed, with the second correction being the sharper one: *"don't copy an extra one — write the correct usage on top of theirs, and reference their skill; that's what skill-as-code means."*

## Concurrent writers and stale baselines

Power users run several Claude sessions at once, and skill repos are exactly where they collide: while you edit skill A, a sibling session may commit skill B (or even an earlier round of skill A) under you. One real session encountered overlapping changes inside an hour — a `Write` rejected because the file changed after reading, and HEAD moving twice mid-task (methodology Case 16). The failure isn't the collision; it's a stale baseline or a clobbering write that silently mixes two sessions' work.

## Silent success in a reference self-check

**A reference checker needs explicit outcomes.** A one-liner was patched to anchor the diff to the right base, see staged edits, survive committing, skip the diff's own `+++` header and drop a misleading `-n`, but intermediate variants could print nothing and exit 0, which is indistinguishable from "I checked and it was clean". Another variant showed the other shape of the same disease: the `-n` it removed had been printing real hits with line numbers counted off the piped stream, so they looked authoritative and pointed nowhere — worse than silence, because a wrong answer outranks no answer. Either way the check kept shipping the defect it was written to catch. Prose cannot validate its own inputs, cannot say which of its outcomes occurred, and cannot be tested; a script does all three and its contract is that **every outcome is named and bad input fails loudly**.

## Moved workflow, unchanged behavioral checks

This synthetic reconstruction isolates a failure from a video-document Skill
merge. Verification-status instructions move from `SKILL.md` to a linked
`recording-workflow.md`. Baseline tests pass, but the candidate fails because the
tests still search the entry file and require a fixed reference count.

The repair changed the tests' lookup path, not their behavioral expectations:
read the workflow owner, assert it is reachable from `SKILL.md`, and traverse the
entry's local Markdown links to find the shipped references. The prior verified /
unverified statuses, screen-text-only limitation, sampling and refusal criteria
remained checked. Merely replacing the old reference count with the new one would
have kept a layout assertion while leaving runtime reachability untested.

Replay this distinction against a frozen pre-move baseline and candidate. First
confirm the old tests pass on the baseline and fail at the moved location. Then
run the adapted tests on the candidate and on isolated negative variants: change
a required verification status, remove the workflow link, and leave a required
reference unreachable. The correct candidate passes; each defective variant
fails. A passing candidate alone does not show that the adapted tests still catch
the original errors. These are case-specific controls, not an extra default suite.

## Display rename, stable external identifier

This synthetic reconstruction separates a public rename from an external
interface. A Skill and its directory get new names; the patch also renames a CI
job ID. A separate runner-policy repository allows only the old ID, checking
`GITHUB_JOB` for exact membership before execution. Such a policy probe can expose
the mismatch before a renamed job runs; it does not establish a live rejection.

For a synthetic replay, let the allowlist be `["legacy-video-check"]`. The renamed
machine ID `video-doc-check` is rejected by
`job_id in policy["jobs"]`; `legacy-video-check` is accepted. Keeping that internal
ID while changing the job's display `name` and test-directory path lets the new
public name ship without silently changing the external admission interface.
Inspect the actual consumer policy and final workflow together; a repository-local
search cannot establish that no external consumer exists. If the machine ID must
also change, the policy migration is a separate coordinated change. The existing
inbound-reference release check owns this boundary.

## Releases without changelog entries

Real case (2026-08): two consecutive releases of one skill shipped with correct bumps, green
gates and merged PRs — and **no changelog entries at all**, because nothing in this procedure
asked for one. Both were caught only by a later audit. That is discipline #6 turned on this
file itself: a rule that lives in a convention rather than in a step loses to completion-drive
every time.

Resolve numbered standing-discipline citations using [their named owners](change-verification.md#shared-discipline-names); the owning contract supplies the conditions and stopping rule.
