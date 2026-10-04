---
name: first-use-and-resume
description: >-
  Design first-use initialization and interrupted-task recovery for operational
  Skills with dependencies, accounts or manual steps. Read when authoring setup,
  migration, self-contained delivery, onboarding or resumable execution.
---

# First use and interrupted-task recovery

Apply this contract when the changed Skill depends on installation, account
configuration, a running service or a human step. Skip it for reference-only
Skills and self-sufficient file transforms. The author applies it to the affected
workflow; it is not a reason to build a generic installer or add setup to every Skill.

## Define the first successful task

Name the intended operator, target environment and requested result before
designing setup. Distinguish a workflow whose dependencies can be resolved from
an offline package that ships them; claim only the chosen distribution boundary.
List the prerequisites and the observed operation that proves each requested
capability. A complete deployment guide alone does not execute initialization.

Reuse the owning installers, diagnostics and dependency update paths. Add a
bundled helper only for a still-needed deterministic seam; keep application
engines and independently maintained Skills with their existing update owner.

## Allocate work to the agent or the person

| Work | Executor and boundary |
|---|---|
| Inspect existing configuration, tool versions and service health | Agent; keep an inspection-only request read-only |
| Resolve dependencies and prepare configuration | Agent within the user's existing setup authorization; preserve unrelated work and valid configuration |
| Bind a named operator to an account and effective permission | Agent; consult the existing identity record and current authority before asking. The author's admin access or organization default is not the operator's access |
| Login, OS consent, secrets entered into a trusted prompt, or an unresolved user decision | Person; request only the current necessary action, with its reason and observable completion condition |
| Resume and validate the requested result | Agent; re-probe after the person returns rather than asking them to repeat an already completed step |

Detect parameters the environment can determine; expose choices that require the
person's intent. Internal command flags may remain for the agent. Keep required
configuration unknown when the probe cannot establish it; do not borrow the
author's paths, credentials or privileged environment to make setup appear complete.

## Make the continuation executable

Put the first-use route in the Skill's ordinary entry. Specify this loop using
the existing tools' actual interfaces:

1. Probe the selected environment, account and requested capability.
2. If ready, continue the original task without reinstalling or requesting login.
3. If an authorized software step is missing, execute that step and read it back.
4. If a person must act, establish the prerequisite is currently ready, then show
   one action. Preserve the selected target and their answers for continuation.
5. When they return, probe again and advance from the first unmet prerequisite.
6. Stop at the verified task result or an explicit unresolved boundary with a
   recovery action; use bounded waits rather than indefinitely repeating a step.

When a helper returns the next action, make its stage, executor, observed state,
arguments and failure distinguishable. Consume argument vectors without unsafe
shell concatenation, and scope environment changes to the intended child.
Keep completed-step locators outside the update-owned Skill bundle. They locate
work; they do not prove a process, permission or service is still alive.

Preserve identity, profile, endpoint and artifact selection across every handoff.
Check the authority context of a privileged step: terminal-, process- or
time-scoped authorization cannot be assumed to transfer to a background worker.
Keep the dependent operation in its authorized context, or name the exact
authorization gap. An expired grant should not force already verified work to be
repeated. Never ask for a password in chat or save it in status/log output.

## Verify the experience being promised

Select the affected cases below within the existing evidence budget. Use isolated
synthetic states for parsing/control flow and authorized live execution for runtime
claims; reuse earlier proof when its inputs and relevant state have not changed.

| Case | Falsifiable result |
|---|---|
| Missing dependencies/configuration | Agent reaches the next essential human step, then the requested operation; no hidden author-machine prerequisite |
| Existing valid installation | Original task runs without another install, login or replacement of user data |
| Interrupted or expired manual step | Current health decides the next action; completed work and answers survive; stale readiness cannot trigger a futile human action |
| Different account, endpoint or privilege context | The selected context remains bound or fails explicitly; success on the author's context is not substituted |

For a fresh-machine claim, exercise the affected missing-state path and the
intended ordinary privilege level. Testing a service without keys/configuration
can prove its control interface starts; it cannot prove login, privileged access
or the business operation. Report unavailable live cases as unverified.
When building an executable, verify the artifact actually running corresponds to
the selected source; an existing file or a successful source build alone is not proof.

Separate dependency readiness from task acceptance. A model loading is not a
correct transcript; a service responding is not a correct-account record read.
Verify only the requested capabilities against independently known content or
observable output. Keep excluded capabilities out of the completion requirement.
Describe live, replay and synthetic evidence separately using the existing
[grounding contract](knowledge-skill-grounding.md).

Stop this authoring check once the changed workflow's relevant cases and original
task have evidence or named gaps. Do not add another full eval suite, reviewer team
or migration framework merely because initialization is involved.
