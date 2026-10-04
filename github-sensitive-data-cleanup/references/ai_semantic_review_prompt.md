# AI Semantic Review Prompt (PII Guard Layer 4)

Regex and keyword scanners (Layers 1-3) only catch things that someone has
already listed. They cannot recognize novel private context: real names,
project codenames, transcript snippets, internal meeting references,
infra nicknames, or descriptions that reveal internal architecture.

Use this prompt on the refs and file set frozen for the cleanup task, including
items with zero Layer 1-3 findings. Use scanner hits to prioritize inspection,
not to choose the only material the semantic pass can see.

## When to Run

- After a completed `scan_repo.py` run, including a run with zero findings.
- Before any force-push to a public repo.
- When the repo contains meeting transcripts, Slack/WeChat logs, runbooks,
  incident notes, or architectural docs.

## Prompt

```text
Review the following frozen scope for accidental leakage of private business
context. Inspect every listed item even when regex scanners reported no findings.

<exact refs, file set, available source locators and terminal condition>

For each item, answer:
1. Does it contain any real person name, project codename, internal system
   name, private domain, internal IP, meeting/transcript snippet, session/rollout
   identifier, or operational detail from private work? Check descriptions that
   disclose architecture or an incident even without an identifying name.
2. For each concrete example or identifier, is its source verifiably public,
   explicitly approved for this public use, synthetic, private, or unknown?
   Cite the source evidence available within authorized scope; a public-looking
   value or an author assertion does not establish provenance. Do not remove
   verified public examples or examples within explicit publication approval.
3. List the exact strings or excerpts that should be redacted.
4. Suggest replacement placeholders (e.g., internal.example.com, PERSON_NAME,
   PROJECT_CODENAME), or an invented equivalent that preserves the failure
   mechanism. Do not describe invented details as an observed incident.
5. List what you inspected and any missing content or source evidence. A diff
   excerpt cannot establish that the unprovided parts of a listed file are clean.

Keep unresolved provenance unknown. When an equivalent synthetic example
preserves the function, suggest it without forcing a user decision. Stop when
the declared scope is inspected and no actionable in-scope finding remains;
otherwise report the findings or incomplete coverage. Keep private source
locators and minimal redaction excerpts in the private review artifact, not in
public PR text. Do not quote large blocks of private material.
```

## How to Apply

1. Freeze the task's refs/file set and stopping condition, then run the prompt
   across that scope. Keep the review outside the public repository.
2. Verify findings against the actual commits. If both the scan and this review
   completed with no findings, stop without rewriting history.
3. For an authorized cleanup, add the identified private strings to the external
   replacements file (`/tmp/sensitive-replacements.txt`) and re-run
   `rewrite_history.py` with that file.
4. Re-run `verify_cleanup.py` and this semantic review on the rewritten refs in
   the same scope. A failed scanner or missing review coverage stays incomplete;
   a successful pattern verification does not replace this pass.

## Limitations

- AI review is not deterministic. Run it more than once on high-risk material.
- It can miss context that requires domain knowledge you have not provided.
- It may hallucinate private context where none exists. Always verify findings
  against the actual commits.
