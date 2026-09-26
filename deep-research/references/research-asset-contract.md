# Research assets for every study

Apply this contract whenever `deep-research` is invoked, whether the task uses one route or several. The project that owns the research chooses an explicit, durable study directory and catalog path. A temporary directory can hold downloads during work, but it is not the delivered source archive.

The useful unit for later research is a **source-bound claim with a date and limit**, not a model's report. Keep provider outputs unchanged; a prior model conclusion stays a lead until its underlying source is reopened. The source, research activity and resulting claim have separate identities, following the provenance distinction in [W3C PROV](https://www.w3.org/TR/prov-o/). An explicit catalog and source metadata make studies findable and reusable, as described by the [FAIR principles](https://www.go-fair.org/fair-principles/). This Skill uses small local files; it does not require a graph database or a fixed provider.

## Files and meaning

```text
<study>/
  study.json                business question, dispatch context, exact prompts, provider × mode lanes
  prior-research.json       explicit catalog search, prior candidates and reuse/adapt/reject reasons
  run-events.jsonl          append-only provider task states, origins and collected export hashes
  source-ledger.jsonl       every opened source and provider-surfaced URL, including rejected/failed leads
  claims.jsonl              claims, source IDs, exact locators, status and evidence limits
  sources/                  unmodified provider exports and original-source snapshots
  report.md                 reader-facing synthesis with [C1] claim IDs and linked source URLs
<project-catalog>.jsonl     explicit list of finalized studies and their source/claim indexes
```

`source-ledger.jsonl` records source identity, URL or local content URN, title, type, accessibility, evidence family, publication date, capture time, source status, originating lane, original bytes or a concrete reason why no snapshot could be retained, and an exact page/section/record locator. Record every source actually opened; record every URL surfaced in a collected textual provider report as a `candidate`, then approve, reject or leave it as a lead. If a provider finds an already recorded URL, update its `surfaced_by` lanes without changing the original's evidence status. Also record unavailable sources and why access failed. A candidate is not a citation.

`claims.jsonl` binds a specific claim to approved source IDs and locators, marks it supported/contested/unknown, and states what the source cannot establish. In `report.md`, place `[C1]` and links to **all originals bound to C1** in the same paragraph or table row; a local original links to its archived relative path. A later study can reuse the original source or challenge the old claim without replacing the old record. Multiple model reports quoting one disclosure still form one evidence family.

## Start before external retrieval

1. Choose the owning project, durable study path and explicit project catalog. Run `search` on entity names, aliases and the business question. Open any relevant prior original or claim before deciding reuse; search hits are locators. If this is the first study, an empty catalog is a valid recorded result.
2. Write a `study.json` spec with one or more decision questions and **one lane for each selected provider × actual mode**. Set `dispatch_context` to the exact user-supplied URL, named subjects, verified codes/identifiers and date window needed to distinguish this case. Copy that context into every lane's exact prompt. `start` refuses a spec if any prompt omits it; this catches a generic “four funds” or “specified stocks” prompt before it reaches an isolated provider workspace. For a route that needs extra inputs, name those explicitly in its prompt. Give a direct original-source route its own lane. Include every mode the user explicitly requested or a prior accepted project workflow requires; if a route cannot run or adds no decision value, keep it in the plan and record `deferred` with the reason. A paid lane needs its own authorization. Do not turn ordinary chat into a native Deep Research lane by naming it so.
3. Run `start`, read the prior matches, and record a reasoned `reuse`, `adapt` or `reject` decision for each. Run `provider_runs.py plan` even for one lane. For several modes sharing an app, follow [parallel-provider-ops.md](parallel-provider-ops.md) and keep one UI owner.

```bash
python3 <skill>/scripts/research_assets.py search --catalog <project-catalog.jsonl> --query '<entity and question>'
python3 <skill>/scripts/research_assets.py start <study-dir> --spec <prepared-study.json> --catalog <project-catalog.jsonl> --query '<entity and question>'
python3 <skill>/scripts/research_assets.py decide <study-dir> <prior-study-id> reuse --reason '<what source or claim remains useful and what must be refreshed>'
python3 <skill>/scripts/provider_runs.py plan <study-dir>
```

If a previous task is already running, preserve its original task ID and query that task. `start` refuses to overwrite an existing study directory; resume it through `plan` and inspect its source records.

## Capture sources and claims during the run

For a public or authorized original that can be retained, pass its actual downloaded file to `source`. The command copies bytes to `sources/originals/`, hashes the copy and appends a source event. It never promotes a model report to an original source. When an original cannot be retained, use `--no-snapshot-reason` and preserve the stable URL, date and exact locator. A rejected or unavailable source requires a reason.

```bash
python3 <skill>/scripts/research_assets.py source <study-dir> --url '<actual-source-url>' --title '<title>' --status approved --source-type official --accessibility public --family '<filing-or-dataset-id>' --published-at YYYY-MM-DD --locator '<page/section/table>' --lane-id <lane-id> --file <downloaded-original>
python3 <skill>/scripts/research_assets.py source <study-dir> --title '<local-original-title>' --status approved --source-type other --accessibility exclusive-user-provided --family '<document-family>' --locator '<page/section>' --lane-id <lane-id> --file <local-original>
python3 <skill>/scripts/research_assets.py claim <study-dir> --claim-id C1 --text '<precise claim>' --status supported --source-id <source-id-from-source-command> --locator '<page/section/table>' --boundary '<what this source does not establish>'
python3 <skill>/scripts/research_assets.py harvest <study-dir>
```

`harvest` records URLs in collected Markdown, text, HTML and JSON provider exports as unverified candidates. For a ZIP or other binary export, preserve the original and separately extract its source list or text report into `sources/`; inspect and record every cited source before synthesis. The tool cannot infer source truth from a ZIP, a model citation or a URL.

As you reopen sources, append a newer `approved`, `rejected` or `unavailable` event for the same source ID. Keep the earlier lead and original provider output. Do not place credentials or access tokens in public URLs, the catalog or the Skill.

## Finish and make the next run able to find this one

The report cites claim IDs such as `[C1]` and links its source URLs. Run both checks, then register the study in the project catalog:

```bash
python3 <skill>/scripts/provider_runs.py validate <study-dir>
python3 <skill>/scripts/research_assets.py check <study-dir> --report <study-dir>/report.md
python3 <skill>/scripts/research_assets.py register <study-dir> --catalog <project-catalog.jsonl> --report <study-dir>/report.md --term '<entity>' --term '<topic>'
```

`check` fails when there is no study, a final report outside the study, an unfinished lane, an undecided prior match, no approved original, a missing or changed snapshot, an unrecorded provider URL, an unapproved report URL, a report claim ID absent from the claim registry, or a claim placed beside the wrong original links. It checks records and file integrity; it cannot identify every unmarked consequential sentence, prove the UI really selected a native mode, or prove that a source supports a claim. Use the selected provider Skill's mode readback and P6–P7 original-source checks for those facts.

The catalog indexes finalized studies, source titles/URLs and claim text. A later run searches it first, reopens decisive originals, compares as-of dates and keeps prior conclusions separate from new evidence. A copied source counts as reuse only when the next study records why its scope and date still fit. Source count, route count and catalog size are diagnostics; the research outcome is a better-supported judgment or a clearly bounded unknown.

An older multi-provider study may have valid `study.json` and collected exports but no universal source ledger. `import-legacy <old-study> --catalog <catalog> --reason '<coverage limit>' --term '<subject>'` makes its selected evidence discoverable **without** marking it finalized under this new contract. Open and reverify its originals before citing them in a new run. Do not backfill fabricated source snapshots or convert old model claims into verified facts.
