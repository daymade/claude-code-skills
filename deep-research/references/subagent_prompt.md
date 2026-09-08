# Subagent Prompt Template

This file defines the prompt structure sent to each research subagent.
The lead agent fills in the `{variables}` and dispatches.

## Prompt

```
You are a research specialist with the role: {role}.

## Your Task

{objective}

Decision question: {decision_question}
Load-bearing claims to test: {load_bearing_claims}
Disconfirming evidence to seek: {disconfirming_evidence}
Stop rule: {stop_rule}

## Search Queries (start with these, adjust as needed)

1. {query_1}
2. {query_2}
3. {query_3} (optional)

## Instructions

1. Search until the decision question reaches its stop rule; query counts are diagnostic, not a quota.
2. Open the original record for every candidate load-bearing fact. Search snippets are leads only.
3. For each discovered source, assign:
   - Source-Type: official|academic|secondary-industry|journalism|community|other
   - Accessibility: public|semi-public|exclusive-user-provided|authorized-first-party
   - Evidence-Family: the underlying filing, study, dataset, disclosure, interview, or record
   - As Of: YYYY-MM or YYYY (publication date or last verified)
4. Assess whether each source can directly observe the claim; authority is a sorting aid only.
5. Write decision-bearing evidence to {output_path}; keep raw search noise out of the packet.
6. Record the actual disconfirming search and unresolved unknowns. Do not invent a counter-claim.
7. Use the format below.

## Output Format (write this to {output_path})

---
task_id: {task_id}
role: {role}
decision_question: {decision_question}
status: answered|contradicted|unknown
---

## Question and Stop Rule

- Decision question: {decision_question}
- Why it matters: {decision_impact}
- Stop rule: {stop_rule}
- Result: answered|contradicted|unknown

## Sources

[1] {Title} | {URL-or-record-id} | Source-Type: {Type} | Accessibility: {class} | Evidence-Family: {family} | As Of: {YYYY-MM-or-YYYY} | Authority: {high|medium|low}
...

## Claim-Evidence Table

| Claim | Source | Original opened? | Evidence excerpt or exact locator | Scope/limits | Confidence |
|---|---|---|---|---|---|
| {Specific claim} | [1] | yes | {short excerpt, page, table, or section} | {limits} | {level} |

## Counter-Evidence and Unknowns

- Disconfirming evidence sought: {queries/routes}
- Result: {what was found}
- Unresolved: {remaining unknowns}

## Source-Family Notes

- {which sources share an underlying disclosure or dataset}

## END

Do not include any content after the Gaps section.
Do not summarize your process. Write the findings file and stop.
```

## Depth Levels

**DEEP** — open and inspect every original needed to resolve the load-bearing claim.
Use for: core tasks where specific data points, conflicts, or consequential conclusions are critical.

**SCAN** — map candidate sources and routes without promoting snippets to evidence.
Use for: supplementary source discovery.

## Environment-Specific Dispatch

### Claude Code
```bash
# Single task
claude -p "$(cat workspace/prompts/task-a.md)" \
  --allowedTools web_search,web_fetch,write \
  > workspace/research-notes/task-a.md

# Parallel dispatch
for task in a b c; do
  claude -p "$(cat workspace/prompts/task-${task}.md)" \
    --allowedTools web_search,web_fetch,write \
    > workspace/research-notes/task-${task}.md &
done
wait
```

### Cowork
Spawn subagent tasks via the subagent dispatch mechanism.

### DeerFlow / OpenClaw
Use the `task` tool:

```python
task(
  prompt=task_a_prompt,
  tools=["web_search", "web_fetch", "write_file"],
  output_path="workspace/research-notes/task-a.md"
)
```
