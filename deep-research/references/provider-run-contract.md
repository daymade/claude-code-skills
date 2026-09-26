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

## Seed source handoff

When the user points to a particular article, PDF or dataset, archive that exact original through the direct-source lane **before** submitting an external provider task. Put its URL, title or document identity, date if known, and the relevant entity codes in `dispatch_context`; include the context in every exact lane prompt. An isolated provider does not inherit the coordinator's browser tab, local download or the user's message attachment.

For each provider, verify that it can read the seed URL or that an authorized local copy or excerpt was actually attached or pasted into the provider task. Read back the sent content or attachment in that product and keep the handoff receipt under the lane's `sources/` directory. A link alone does not prove access. If the product cannot read the URL and no permitted source content can be handed over, mark that route deferred or `failed_unknown` with the access reason; do not ask it to find a similar article. If it nonetheless returns a report about another document, preserve the output as collected **mode evidence**, flag the subject mismatch in the lane note and source registry, and exclude its article-specific assertions from synthesis. Reopen the user's original when judging the final report.

For parallel execution, a lane may also set `control_surface` (the UI or API client an agent would control) and `route_skill` (the current Skill to consult for that route). Both are optional nonempty strings. If `control_surface` is absent, the local planner uses the provider name, assigning two modes of one app to one surface owner. Distinct surfaces are a claim about actual UI isolation and must be checked before concurrent control. `route_skill` is a dispatch hint, not a hardcoded adapter: the coordinator resolves and reads the current installed Skill at execution time. An absent or stale `route_skill` requires fresh route selection, and its presence does not authorize a paid run.

## Append-only events: `run-events.jsonl`

Each line is one JSON object with `at` (ISO 8601 with timezone), `lane_id`, `state`, and `note` (brief observation). State transitions are `prepared → submitted → running → collected`; `submitted → collected` is valid when the provider offers no running state. `prepared`, `submitted`, or `running` may lead to `deferred` or `failed_unknown`; either can return to `submitted` for a verified retry. The **submitted origin** remains immutable within one run and cannot be assigned to another mode of the same provider. An observed same-task redirect may add a persistent `origin_alias` with its saved UI/API receipt; this is not a new task or retry. A retry after `deferred` or `failed_unknown` may start a new origin only with a reason recorded in `note`. Never turn a timeout into a second paid request merely to fill the ledger: query an existing provider task ID first. A later export for a collected lane is another `collected` event with a distinct file under `sources/`, preserving the original; no lane may collect a path already used by another event.

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

When a provider creates a provisional URL and the **same UI task** later displays a persistent URL, save a receipt under `sources/` that shows both addresses or otherwise establishes the task continuity. Record a `running` or `collected` event with the original `--origin-url`, plus `--alias-url <persistent-url> --alias-proof <saved-receipt> --note '<same-task observation>'`. The alias receipt is hashed and checked on `validate`; another lane of the same provider cannot claim either URL. `plan` keeps `origin` as the submitted identity and returns `resume_origin` as the latest verified address. Query `resume_origin` when continuing the task, without starting another one.

Run `python3 <skill>/scripts/provider_runs.py plan <study-dir> [--max-parallel 3]` to derive JSON `parallel_groups` of surface queues and active/collected/held lanes before fan-out or resuming. A queue combines active and new lanes on the same surface; `owner_reconciliation_required` flags an active owner who must keep the surface or hand it over before another agent controls it. Accepted asynchronous jobs may keep running while that owner submits the next mode. Active cards include the immutable submitted `origin` and `resume_origin`; collected cards retain the original artifact path, and held cards the reason. Only dispatch candidates repeat full prompts. Read [parallel-provider-ops.md](parallel-provider-ops.md) for ownership, route selection, cost boundaries, polling and synthesis. Run `validate <study-dir>` before synthesis and `status <study-dir>` to see every lane, including lanes with no event. `record <study-dir> <lane-id> <state> ...` appends an event and computes the artifact hash for `collected`; use `--origin-url` or `--origin-task-id`, `--file`, and `--note`. The CLI is local-only and makes no provider requests. Keep provider UI/API screenshots or exact task URLs if a mode distinction is contested; the ledger is a claim about what occurred, not self-authenticating proof of UI mode.

### ChatGPT web mode evidence (observed 2026-09-25)

Writing “Deep Research” in a prompt can still produce an ordinary Pro chat. For the `deep-research` lane, select **Add files and more → Deep research**, then read back the selected mode chip before sending. In this run, a rich-text `fill` replaced that chip; selecting the tool first and entering the prompt with `keyboard.insertText` preserved it. After sending, a plan or countdown alone did not establish `running`: read back the actual research activity and later “Research completed.” Export the finished report with **Export → Markdown**, keep those original bytes and the conversation URL. In Ego Browser, a report inside an iframe made an Export element reference stale; locating the visible control from a fresh screenshot worked for this run. Do not reuse that screen position as a fixed coordinate. These observations verify route and collection, not business value.

## P3 handoff

Preserve provider outputs verbatim. Extract candidate claims into P3's citation registry with a separate `report_lane_id`; tag them `model_report_unverified` until a human or agent reopens their original sources and records source locator, date, scope, and disconfirming evidence. Do not count several model reports quoting the same original as independent corroboration. Record contradictions and unknowns. For internal business facts, use authorized first-party originals; for buyer demand and product effect, seek actual external or customer evidence. Provider completion, number of sources, report length, and citation coverage are process diagnostics. Judge the work against the study's `business_outcome`: which user decision changed, what action followed, and what effect was observed or remains unmeasured.

Dispatch boundaries: compose whichever provider and browser/app Skills are currently installed and appropriate for the requested lanes. In the observed case, Kimi used `kimi-use`, ChatGPT used its actual chat or native Deep Research UI, and UniFuncs used `unifuncs-router` followed by the installed specialist; these are examples, not required routes or a fixed provider list. A planned paid lane is not authorization for a paid run. A Work agent may choose **metered subtools** after submission, even when the top-level lane looks included in an existing account; inspect the subtool cost before dispatch and defer a lane that cannot prevent unapproved metered calls. State an authorized spending boundary in the prompt for traceability, but never treat prompt wording as a technical charge limit. Preserve observed point usage and raw call logs if the boundary fails. Browser or app automation must preserve the original session/task identity and collect the provider output before synthesizing it. If a route is unavailable, record `deferred` or `failed_unknown` and proceed with available lanes, stating the coverage gap.
