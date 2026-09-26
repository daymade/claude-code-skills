# Multi-provider research runs

Use this contract for every Deep Research study, including a single direct original-source route. It extends P1's task board and P3's citation registry; it does not replace either. Make one study directory under the owning project, with `study.json`, append-only `run-events.jsonl`, `sources/` for unedited provider exports, and a separate evidence registry and synthesis. [research-asset-contract.md](research-asset-contract.md) owns prior-study discovery, original-source records, claim binding and the final archival check. Never put credentials or private source contents in the reusable Skill.

## Task file: `study.json`

```json
{
  "schema_version": 1,
  "study_id": "example-study-2026-09-25",
  "as_of": "2026-09-25",
  "business_outcome": "Find out whether timely evidence changes a user's decision and its result.",
  "dispatch_context": "Seed: https://example.org/case; target: Example Co (EX01); window: 2026 H1.",
  "decision_questions": [{"id":"Q1","question":"Which decision could this evidence change?"}],
  "lanes": [
    {"lane_id":"chatgpt-pro","provider":"chatgpt","mode":"pro-chat","task_id":"Q1","prompt":"Seed: https://example.org/case; target: Example Co (EX01); window: 2026 H1. Assess the strongest counterevidence."},
    {"lane_id":"chatgpt-deep","provider":"chatgpt","mode":"deep-research","task_id":"Q1","prompt":"Seed: https://example.org/case; target: Example Co (EX01); window: 2026 H1. Trace the original sources."}
  ]
}
```

`provider` identifies the product; `mode` identifies the product route actually used. Names are extensible strings, not synonyms: `pro-chat` does not imply `deep-research`, and Kimi's Work tools are distinct from Kimi Chat deep research. A lane may be planned without being dispatched. `task_id` links each prompt to a decision question or P1 subtask; prompts can vary to exploit a mode's strengths, but each must contain the exact `dispatch_context` and state the requested evidence/unknowns. `research_assets.py start` checks that containment before dispatch. Record deliberate prompt differences and any later corrective follow-up separately; never overwrite the initial exact prompt or provider response. Add a future lane by appending a lane object, without changing old events.

For direct source retrieval, use a separate lane such as `provider: "direct", mode: "primary-source"`; its collected artifact is the investigator's source packet under `sources/`, while the original PDFs or pages are recorded separately in `source-ledger.jsonl`. Internal subagents split questions but do not become external provider modes. A user-requested mode stays visible in `study.json` even when deferred; omitting it is a different decision from declining to dispatch it.

For parallel execution, a lane may also set `control_surface` (the UI or API client an agent would control) and `route_skill` (the current Skill to consult for that route). Both are optional nonempty strings. If `control_surface` is absent, the local planner uses the provider name, assigning two modes of one app to one surface owner. Distinct surfaces are a claim about actual UI isolation and must be checked before concurrent control. `route_skill` is a dispatch hint, not a hardcoded adapter: the coordinator resolves and reads the current installed Skill at execution time. An absent or stale `route_skill` requires fresh route selection, and its presence does not authorize a paid run.

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

Run `python3 <skill>/scripts/provider_runs.py plan <study-dir> [--max-parallel 3]` to derive JSON `parallel_groups` of surface queues and active/collected/held lanes before fan-out or resuming. A queue combines active and new lanes on the same surface; `owner_reconciliation_required` flags an active owner who must keep the surface or hand it over before another agent controls it. Accepted asynchronous jobs may keep running while that owner submits the next mode. Active cards include the existing origin for query, collected cards the original artifact path, and held cards the reason; only dispatch candidates repeat full prompts. Read [parallel-provider-ops.md](parallel-provider-ops.md) for ownership, route selection, cost boundaries, polling and synthesis. Run `validate <study-dir>` before synthesis and `status <study-dir>` to see every lane, including lanes with no event. `record <study-dir> <lane-id> <state> ...` appends an event and computes the artifact hash for `collected`; use `--origin-url` or `--origin-task-id`, `--file`, and `--note`. The CLI is local-only and makes no provider requests. Keep provider UI/API screenshots or exact task URLs if a mode distinction is contested; the ledger is a claim about what occurred, not self-authenticating proof of UI mode.

### ChatGPT web mode evidence (observed 2026-09-25)

Writing “Deep Research” in a prompt can still produce an ordinary Pro chat. For the `deep-research` lane, select **Add files and more → Deep research**, then read back the selected mode chip before sending. In this run, a rich-text `fill` replaced that chip; selecting the tool first and entering the prompt with `keyboard.insertText` preserved it. After sending, a plan or countdown alone did not establish `running`: read back the actual research activity and later “Research completed.” Export the finished report with **Export → Markdown**, keep those original bytes and the conversation URL. In Ego Browser, a report inside an iframe made an Export element reference stale; locating the visible control from a fresh screenshot worked for this run. Do not reuse that screen position as a fixed coordinate. These observations verify route and collection, not business value.

## P3 handoff

Preserve provider outputs verbatim. Extract candidate claims into P3's citation registry with a separate `report_lane_id`; tag them `model_report_unverified` until a human or agent reopens their original sources and records source locator, date, scope, and disconfirming evidence. Do not count several model reports quoting the same original as independent corroboration. Record contradictions and unknowns. For internal business facts, use authorized first-party originals; for buyer demand and product effect, seek actual external or customer evidence. Provider completion, number of sources, report length, and citation coverage are process diagnostics. Judge the work against the study's `business_outcome`: which user decision changed, what action followed, and what effect was observed or remains unmeasured.

Dispatch boundaries: compose whichever provider and browser/app Skills are currently installed and appropriate for the requested lanes. In the observed case, Kimi used `kimi-use`, ChatGPT used its actual chat or native Deep Research UI, and UniFuncs used `unifuncs-router` followed by the installed specialist; these are examples, not required routes or a fixed provider list. A planned paid lane is not authorization for a paid run. A Work agent may choose **metered subtools** after submission, even when the top-level lane looks included in an existing account; inspect the subtool cost before dispatch, set an explicit spending boundary in its prompt, and defer a lane that cannot prevent unapproved metered calls. Preserve observed point usage and raw call logs if the boundary fails. Browser or app automation must preserve the original session/task identity and collect the provider output before synthesizing it. If a route is unavailable, record `deferred` or `failed_unknown` and proceed with available lanes, stating the coverage gap.
