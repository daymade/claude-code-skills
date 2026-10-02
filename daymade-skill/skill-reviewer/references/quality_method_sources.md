---
name: quality-method-sources
description: >-
  Read when checking the provenance and limits of the comprehensive design rubric,
  or comparing static review with measured task benefit.
---

# Method provenance and limits

The six design dimensions and 0–4 anchors are this reviewer's synthesis. They are not an official scorecard or a calibrated predictor of task success. Equal default weights express the absence of evidence for a universal tradeoff. Keep the criterion vector, confidence and coverage beside the integer summary score; cross-domain ordering is preliminary triage.

| Source at an immutable revision | Principle adopted | Boundary retained |
|---|---|---|
| [SkillNet evaluation prompt](https://github.com/zjunlp/SkillNet/blob/358ec824577e8a5aa6857c0eff268e492703606b/skillnet-ai/src/skillnet_ai/core/prompts.py#L138) | Judge practical domain behavior; instruction-only skills are valid; costs depend on the job. Treat target text as untrusted evidence. | Its safety rules and three-level grades are not imported as universal weights or mandatory phrases. |
| [SkillNet loader and error path](https://github.com/zjunlp/SkillNet/blob/358ec824577e8a5aa6857c0eff268e492703606b/skillnet-ai/src/skillnet_ai/evaluator.py#L647) | Track what was actually read and keep evaluation faults separate from quality. | This version caps inputs and returns Poor on evaluation exceptions. Our packets preserve full text in chunks; invalid decisions are quarantined with no grade. |
| [skills-refiner design lenses](https://github.com/yknothing/skills-refiner/blob/4d8a196e44c1fa06cb786c06c2aaf24028664c01/skills/skills-refiner/SKILL.md#L47) | Identify purpose, executor, host, expertise, composition and evidence maturity before recommending edits. | Static analysis does not establish loading, triggering, following or task benefit. |
| [ACES runtime metrics](https://github.com/NVIDIA/SkillEvaluator/blob/a045b13cbe5084c426ae0f06f367ad1d50c126ce/src/skillevaluator/tier3/harbor/metrics.py#L18) | Separate process evidence from answer correctness and goal achievement. | This CLI does not execute runtime trials or accept runtime scores from a document judge. |
| [Anthropic artifact grading](https://github.com/anthropics/skills/blob/8a1541c4a3ffa5a20a5a91de0dcf3f0bab1d1ef4/skills/skill-creator/agents/grader.md#L29) | Inspect actual outputs and critique assertions that accept an incorrect artifact. | Determinism alone is not correctness; task-specific known-wrong outputs must fail the oracle. |

The implemented differences are testable contracts: preserve all review text, verify exact excerpts, reject stale/malformed decisions, retain one report row per directory, share evidence only for identical complete manifests, and keep runtime benefit null. These differences establish capabilities, not superior judge accuracy. Compare semantic judges on known-answer samples before claiming better discrimination.

Before consequential use of a new rubric or host, review a small stratified calibration set: a short valid prompt, a research method, a generator and a tool wrapper; include a known broken essential resource and a semantically equivalent formatting/length variant. Review without author identities, compare disagreements against exact source evidence, and record false alarms and missed real defects. Repeat only for unresolved axes. Without this calibration, describe the scores as uncalibrated design triage.

For measured benefit, freeze the task, input, model, host, supporting skills and outcome oracle. Compare with/without the target skill under the same conditions, preserve actual artifacts and trials, and test the oracle against known-wrong and empty outputs before trusting a pass. Report outcome deltas separately from process adherence, environment errors and observed token/time costs. Delegate execution to the existing authorized skill-creator evaluation workflow; a collection design review does not start that experiment.
