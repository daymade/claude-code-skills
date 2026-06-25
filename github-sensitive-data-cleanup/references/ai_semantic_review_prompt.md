# AI Semantic Review Prompt (PII Guard Layer 4)

Regex and keyword scanners (Layers 1-3) only catch things that someone has
already listed. They cannot recognize novel private context: real names,
project codenames, transcript snippets, internal meeting references,
infra nicknames, or descriptions that reveal internal architecture.

Use this prompt to perform Layer 4 review on the commits or files flagged by
Layers 1-3, or on any commit you suspect contains private context.

## When to Run

- After `scan_repo.py` reports any Layer 3 findings.
- Before any force-push to a public repo.
- When the repo contains meeting transcripts, Slack/WeChat logs, runbooks,
  incident notes, or architectural docs.

## Prompt

```text
You are reviewing git history for accidental leakage of private business
context. The following commits/files were flagged by regex scanners or are
otherwise suspicious.

<paste commit hashes, file paths, or diff excerpts here>

For each item, answer:
1. Does it contain any real person name, project codename, internal system
   name, private domain, internal IP, meeting/transcript snippet, or business
   context that is not a public entity or generic placeholder?
2. If yes, is the information already public (e.g., on the company website,
   public blog, open-source repo) or genuinely private?
3. List the exact strings or excerpts that should be redacted.
4. Suggest replacement placeholders (e.g., internal.example.com, PERSON_NAME,
   PROJECT_CODENAME).

Be conservative: when in doubt, treat it as private. Do not quote large blocks
of text in your answer; only list the minimal strings that need action.
```

## How to Apply

1. Run the prompt against the flagged commits.
2. Add the identified private strings to your replacements file
   (`/tmp/sensitive-replacements.txt`).
3. Re-run `rewrite_history.py` with the updated replacements file.
4. Re-run `verify_cleanup.py` with the same file.
5. Re-run this AI semantic review until no new private context is found.

## Limitations

- AI review is not deterministic. Run it more than once on high-risk material.
- It can miss context that requires domain knowledge you have not provided.
- It may hallucinate private context where none exists. Always verify findings
  against the actual commits.
