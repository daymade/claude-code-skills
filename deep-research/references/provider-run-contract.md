# Multi-provider research runs

Use this contract when one decision question is sent to more than one AI product or mode. It extends P1's task board and P3's citation registry; it does not replace either. Make one study directory under the owning project, with `study.json`, append-only `run-events.jsonl`, `sources/` for unedited provider exports, and a separate evidence registry and synthesis. Never put credentials or private source contents in the reusable Skill.

## Task file: `study.json`

```json
{
  "schema_version": 1,
  "study_id": "example-study-2026-09-25",
  "as_of": "2026-09-25",
  "business_outcome": "Find out whether timely evidence changes a user's decision and its result.",
  "decision_questions": [{"id":"Q1","question":"Which decision could this evidence change?"}],
  "lanes": [
    {"lane_id":"chatgpt-pro","provider":"chatgpt","mode":"pro-chat","task_id":"Q1","prompt":"Exact prompt sent or planned; redact secrets before third-party dispatch"},
    {"lane_id":"chatgpt-deep","provider":"chatgpt","mode":"deep-research","task_id":"Q1","prompt":"Exact prompt sent or planned"},
    {"lane_id":"kimi-tools","provider":"kimi","mode":"work-tools","task_id":"Q1","prompt":"Exact prompt sent or planned"},
    {"lane_id":"kimi-deep","provider":"kimi","mode":"deep-research","task_id":"Q1","prompt":"Exact prompt sent or planned"},
    {"lane_id":"gemini-deep","provider":"gemini","mode":"deep-research","task_id":"Q1","prompt":"Exact prompt planned"},
    {"lane_id":"unifuncs-deep","provider":"unifuncs","mode":"deep-research","task_id":"Q1","prompt":"Exact prompt planned"}
  ]
}
```

`provider` identifies the product; `mode` identifies the product route actually used. Names are extensible strings, not synonyms: `pro-chat` does not imply `deep-research`, and Kimi's Work tools are distinct from Kimi Chat deep research. A lane may be planned without being dispatched. `task_id` links each prompt to a decision question or P1 subtask; prompts can vary to exploit a mode's strengths, but each must state the shared business question and requested evidence/unknowns. Record deliberate prompt differences in `study.json`, not only in chat history. Add a future lane by appending a lane object, without changing old events.

## Append-only events: `run-events.jsonl`

Each line is one JSON object with `at` (ISO 8601 with timezone), `lane_id`, `state`, and `note` (brief observation). State transitions are `prepared → submitted → running → collected`; `submitted → collected` is valid when the provider offers no running state. `prepared`, `submitted`, or `running` may lead to `deferred` or `failed_unknown`; either can return to `submitted` for a verified retry. The origin cannot change between submission, running and collection within one run, or be assigned to another mode of the same provider. A retry after `deferred` or `failed_unknown` may start a new origin only with a reason recorded in `note`. Never turn a timeout into a second paid request merely to fill the ledger: query an existing provider task ID first. A later export for a collected lane is another `collected` event with a distinct file under `sources/`, preserving the original; no lane may collect a path already used by another event.

- `prepared`: local prompt is ready; no claim of dispatch.
- `submitted`: require `origin`, either an exact provider `session_url` or `task_id`; this means the external product accepted the task, not that it produced a report.
- `running`: provider task is visibly active; retain the same `origin`.
- `collected`: require `origin`, `artifact.path` relative to study directory, SHA-256 `artifact.sha256`, and `artifact.captured_at`. This proves the exported bytes were collected from the identified task. It **does not** verify claims in the report.
- `deferred`: explicitly postponed, with reason in `note`.
- `failed_unknown`: request result or task identity cannot be established; preserve observed IDs and uncertainty in `note`. Do not equate an uncertain create call with a definite failure.

Example:

```json
{"at":"2026-09-25T14:00:00+08:00","lane_id":"kimi-deep","state":"collected","origin":{"session_url":"https://kimi.com/chat/EXAMPLE"},"artifact":{"path":"sources/kimi-deep/report.md","sha256":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef","captured_at":"2026-09-25T13:59:00+08:00"},"note":"Native Deep Research export; report claims unverified"}
```

Run `python3 <skill>/scripts/provider_runs.py validate <study-dir>` before synthesis and `status <study-dir>` to see every lane, including lanes with no event. `record <study-dir> <lane-id> <state> ...` appends an event and computes the artifact hash for `collected`; use `--origin-url` or `--origin-task-id`, `--file`, and `--note`. The CLI is local-only and makes no provider requests. Keep provider UI/API screenshots or exact task URLs if a mode distinction is contested; the ledger is a claim about what occurred, not self-authenticating proof of UI mode.

### ChatGPT web mode evidence (observed 2026-09-25)

Writing “Deep Research” in a prompt can still produce an ordinary Pro chat. For the `deep-research` lane, select **Add files and more → Deep research**, then read back the selected mode chip before sending. In this run, a rich-text `fill` replaced that chip; selecting the tool first and entering the prompt with `keyboard.insertText` preserved it. After sending, a plan or countdown alone did not establish `running`: read back the actual research activity and later “Research completed.” Export the finished report with **Export → Markdown**, keep those original bytes and the conversation URL. In Ego Browser, a report inside an iframe made an Export element reference stale; locating the visible control from a fresh screenshot worked for this run. Do not reuse that screen position as a fixed coordinate. These observations verify route and collection, not business value.

## P3 handoff

Preserve provider outputs verbatim. Extract candidate claims into P3's citation registry with a separate `report_lane_id`; tag them `model_report_unverified` until a human or agent reopens their original sources and records source locator, date, scope, and disconfirming evidence. Do not count several model reports quoting the same original as independent corroboration. Record contradictions and unknowns. For internal business facts, use authorized first-party originals; for buyer demand and product effect, seek actual external or customer evidence. Provider completion, number of sources, report length, and citation coverage are process diagnostics. Judge the work against the study's `business_outcome`: which user decision changed, what action followed, and what effect was observed or remains unmeasured.

Dispatch boundaries: choose Kimi app through `kimi-use`, ChatGPT web/app through its actual Deep Research or chat UI, and UniFuncs through `unifuncs-router` then the installed specialist. A planned UniFuncs lane is not authorization for a paid run. Browser or app automation must preserve the original session/task identity and collect the provider output before synthesizing it. If a route is unavailable, record `deferred` or `failed_unknown` and proceed with available lanes, stating the coverage gap.
