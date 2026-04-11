# Verification Protocol

How to verify a freshly distilled wrapper skill before commit. This is **post-generation verification** — the original install/debug session already happened (that's where the content came from), so the goal here is not "find new bugs by running the tool" but "confirm the generated skill faithfully describes what happened in the session".

Think of it as closing the loop: session → distillation → regenerated understanding → cross-check against session.

## Why verification is different for wrapper skills

In a normal skill-creator workflow, verification runs test prompts through a fresh subagent, compares outputs, and iterates. That doesn't apply here because:

- The wrapper skill's "output" is a user's install state, not a file. Asserting on it in a sandbox is awkward.
- The session the skill was distilled from is already a high-quality test case — the user watched Claude do the right thing in real time. Replaying it adds little.
- The real risk is not "does the code work" — everything in the skill came from code that already ran successfully. The risk is "does the generated skill faithfully document what happened, or did we lose / reorder / hallucinate details during distillation".

So verification focuses on **cross-referencing the generated files against the conversation history** and doing a **lightweight smoke test** against the actual state the session left on disk.

## The verification checklist

### 1. Structural validity (fast, automatic)

Run the repo's standard validation:

```bash
cd <repo-root>
python3 skill-creator/scripts/quick_validate.py <wrapper-skill-name>
python3 skill-creator/scripts/security_scan.py <wrapper-skill-name>
```

Both should pass. If `quick_validate` complains about frontmatter, path references, or missing files, fix them before moving on. If `security_scan` flags anything, stop and investigate — the session should never have surfaced real credentials into the generated files.

Expected signal: `Skill is valid!` and `Security scan passed: No secrets detected`.

### 2. Session cross-reference (slow, manual)

For each of the following generated artifacts, find its origin in the conversation history and confirm it matches.

- **Every command in `install_<tool>.sh`**: open the script, pick each non-trivial command line (anything more interesting than `mkdir -p`), search for it in the conversation history. It should appear at least once, run by Claude or pasted by the user, in the context of successfully installing the tool. If any command has no match, it is speculative — delete it or replace it with a command that was actually run.
- **Every entry in `known_issues.md`**: for each `ISSUE-<NNN>` block, locate the session moment where the symptom was first observed. Confirm the error message in the entry matches the literal error message from that moment. Then locate the session moment where the fix was applied, and confirm the repair commands in the entry match the commands that were run at that moment. If any entry has no provenance in the session, delete it.
- **Design decisions documented in `best_practices.md` or elsewhere**: each should be traceable to a specific exchange in the session where the user and Claude considered alternatives and chose one. Quote or paraphrase the reasoning the user gave at that moment.
- **Credential paths and env var names**: these should match what the session actually established. If the session stored credentials at `~/.config/<tool>/client_id`, the generated files must say the same path — not a variant.

When in doubt, grep the conversation history. If grep finds nothing, the generated artifact is unsupported and should be removed.

### 3. Lightweight live smoke test (optional but valuable)

If the session left behind a real install of the tool on the user's machine (not in a fake HOME sandbox), run the generated `diagnose.sh` against that real install and compare its output to your memory of the session's final state.

Expected outcomes:

- Each issue the session fixed should report as `✅ ... Strategy <X> applied` or similar, matching the fix the session applied. If diagnose reports `⚠️ TRIGGERED` for an issue the session supposedly fixed, one of two things went wrong: either the generated detection logic is wrong (false negative on the fixed state), or the session didn't actually fix it the way you thought.
- Each issue the session did not encounter should report as `✅ clear` or `⚠️ N/A`, depending on the detection logic's return codes.
- The overall exit code should be `0` if everything the session did is still in place, or `1` if there are still warnings you haven't addressed.

If the live smoke test disagrees with your memory of the session, **believe the smoke test and re-mine the session**. The conversation is long and it is easy to misremember which fix went in first or which agent had which state. The disk is authoritative.

**Do not** run the installer or the repair commands during this smoke test — the goal is to observe, not to modify. The real install is the one the user cares about, and the user has not yet consented to let the generated skill touch it.

### 4. Mental dry-run of the wrapper against a hypothetical second user

Read the generated `SKILL.md` as if you were a fresh Claude session and a user has just asked you to install the tool. Walk through the routing:

- Does the description trigger for the symptom the original session started with?
- Does Capability 1 lead to a complete install if Claude follows the instructions literally?
- Does Capability 3's diagnose flow reach each `known_issues.md` entry?
- Would a new user, given the description and the references, be able to understand what each known issue is and decide between repair strategies?

If any step breaks, the wrapper skill is not yet shippable. The fix is usually to add more signal to the description (for triggering) or to add more concrete detail to a reference file (for understanding).

### 5. Release metadata consistency

Before commit, confirm the marketplace and release docs are consistent with the new skill:

- `marketplace.json`: new `plugins[]` entry exists, `metadata.version` bumped, description list includes the new skill.
- `CHANGELOG.md`: entry under the new version with a summary of what was added.
- `README.md` and `README.zh-CN.md`: if the repo has a skill index, the new skill is listed with accurate description.
- Repo-level `CLAUDE.md`: if it counts skills, the count is incremented.
- `.security-scan-passed` file exists in the wrapper directory (created by `security_scan.py`).

Mismatch between the marketplace metadata and the SKILL.md description is a common slip — triple-check the plugin name, the skill directory name, and the description alignment.

## When verification surfaces a problem

If any step turns up a mismatch between what the skill says and what the session actually did, the correct fix is to **re-mine the relevant section of Step 2 and regenerate the affected file**. Do not patch the generated file to match your memory — patch it to match what the session actually contained, because that is the source of truth.

Common mismatches and their causes:

| Mismatch | Usual cause | Fix |
|---|---|---|
| `install_<tool>.sh` contains a flag you don't recognize | The flag was added during iteration on the script mid-session, not from the first install | Search the session for when the flag was introduced and confirm it's still required. If the earlier version worked, remove the flag. |
| `known_issues.md` entry has a plausible but slightly off error message | Paraphrase drift during distillation | Search the session for the literal error message and paste it verbatim. |
| Two known issues describe the same underlying problem | Distillation split a single bug's investigation into two entries | Merge them — one entry, one root cause, one fix. |
| Credential path in `credentials_setup.md` doesn't match the path in `install_<tool>.sh` | Distillation drew from two different moments in the session, before and after a path change | Determine which path the session ended with and use that in both files. |
| `diagnose.sh` detects an issue that `known_issues.md` doesn't describe | You added a check during generation that isn't grounded in the session | Either add the matching `known_issues.md` entry if the issue is real and you know the fix, or remove the check. |

## Verification is not dogfood

A common mistake when building wrapper skills is to assume "verification" means "run the wrapper end-to-end on a fresh machine and see if it works". That's a valid activity, but it is not what this step is for — the wrapper is an artifact of a session that *already went end-to-end on a real machine*. The dogfood happened during the session. Re-running it proves nothing that wasn't already proved.

What verification here proves is a different, narrower claim: **the generated skill faithfully describes the session**. If that claim holds, the skill will work for the next user by construction, because the session worked and the skill is a faithful copy of the session's conclusions.

Run a live smoke test (step 3) if it's cheap. Skip it if it's expensive or destructive. Focus the effort on cross-reference and dry-run — those find the actual failure modes of this workflow.
