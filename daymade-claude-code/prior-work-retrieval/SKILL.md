---
name: prior-work-retrieval
description: >-
  Only for explicit prior-work/reuse/history requests; never for read-only status or inspection.
  Finds and verifies existing successful work before substantial new production when reuse is
  materially plausible. Use when the user explicitly references earlier work, existing code/SOPs,
  history, prior decisions, another project, or says 以前做过, 已有代码, 别重复造轮子, reuse, or
  retrieve before produce. A mention of current/现有 tests, README, files, implementation, behavior,
  or validation is not a prior-work request. Do not infer the trigger merely because new work might
  duplicate something. Do not invoke for current-file inspection, ordinary bug fixes, mechanical
  verification, or merely because the final answer is a report/summary.
  Produces a source-verified reuse/adapt/reject receipt; zero hits never prove absence.
argument-hint: "<task or question>"
---

# Prior Work Retrieval

Run this before substantial production **only when the trigger above is present**. Read-only
current-state checks stay direct unless the user asks for history. Its job is not to generate another
summary. Its job is to answer: **what already exists, which source is current,
what should be reused, and what remains genuinely new?**

## Completion contract

A retrieval pass is complete only when all five are true:

1. The task's real business outcome is written as one sentence.
2. Every relevant carrier declared in the manifest reports `searched`,
   `manual_completed`, or an explicit failure/coverage gap.
3. Candidate claims are opened at their original path or record, not accepted
   from a search snippet alone.
4. Each adopted item has a `reuse` or `adapt` decision and a reason tied to the
   current task. If nothing is adopted, the receipt carries a concrete
   `no_reuse_reason`.
5. `scripts/prior_work.py check` accepts the receipt for this session.

`retrieved` is not `verified`; `verified` is not `reused`. Keep those states
separate so “I searched” cannot impersonate “I used our best prior work.”

## Workflow

### 1. Read the local operating context first

Before querying, read the current project's `AGENTS.md`/`CLAUDE.md`, navigation
index, and any North Star/current-decision file they name. Historical material
cannot override a newer explicit decision.

### 2. Validate the explicit source manifest

The manifest is the only discovery scope. No directory exists merely because a
convention says it should. Default path:

```bash
uv run --no-project python scripts/prior_work.py \
  --manifest <path> validate-manifest
```

The default is `~/.config/daymade/prior-work/sources.json`; a project may pin
another path. Global options precede the subcommand. The schema and carrier
examples are in `references/source-manifest.md`.

### 3. Retrieve across declared carriers

Write the user-world outcome separately from the proposed implementation. Then
provide two term sets:

- `--outcome-term`: 1–5 artifact/event/entity/date terms that could locate an
  already-finished result (accepted deliverable, canonical transcript, deployed
  service, decision, or operating evidence).
- `--term`: 1–8 implementation terms (code symbols, old workflow names,
  technical nouns, failure symptoms).

The runtime sends the business-outcome query to documents, meetings, archives,
and conversations; it sends the implementation query to code and Skill
carriers. Outcome candidates are ranked first. A code search can therefore no
longer stand in for checking whether the requested result already exists. Do
not pass generic verbs such as “做 / 优化 / 系统” alone.

```bash
uv run --no-project python scripts/prior_work.py retrieve \
  --business-outcome 'the observable result the user actually needs' \
  --outcome-term 'accepted artifact, entity, event, or date' \
  --query 'the implementation or workflow currently being considered' \
  --term 'distinctive entity' \
  --term 'old workflow name' \
  --term 'failure symptom' \
  --session-id "$CODEX_SESSION_ID"
```

Do NOT redirect the output (`> /tmp/run.txt`) to save it: by design
(2026-08-27, regression-locked in `test_unquoted_redirection_even_after_
route_stays_gated`) a file redirection trips the write gate even on a
read-only route command, so a redirected retrieve is blocked and the run
JSON never lands where you aimed. Let the output print and read it from the
transcript; the durable copy is the run JSON under the manifest's `state_dir`
(its `run_path` is printed on the last line).

`--session-id`: use it only with `retrieve`, `complete`, and `check`; `validate-manifest`
does not accept it. On Codex use `$CODEX_SESSION_ID`. Claude Code has no such env
var, so take the exact id carried verbatim in prior-work hook messages
(UserPromptSubmit inject / PreToolUse deny / Stop block). The receipt filename
shown beside it is the id's sha256, not the id itself; completing a receipt
under a guessed id writes a file `check` will never read and the gate keeps
rejecting. Never substitute the hash-looking filename for the id.

When a normally optional live carrier is material to the request, promote it
explicitly: `--require-source live-wechat`. The receipt cannot complete until
that manual route is recorded.

The command searches filesystem carriers with `rg`, calls explicitly declared
command adapters (for example the formal Claude-history finder), and surfaces
manual routes such as live WeChat. Content search is always bounded by declared
globs; full path enumeration runs only when an outcome/implementation term is
explicitly path-shaped (a filename, path, or ISO date). A symbol such as
`project_doc_max_bytes` does not justify walking every filename in a workspace.
The command writes an immutable run JSON under the manifest's `state_dir` and
returns its `run_id`.

If a required carrier says `manual_required`, perform that named Skill route and
record its result before completion. A local WeChat archive search does not
prove live WeChat coverage; a conversation index does not prove meeting or code
coverage.

### 4. Verify candidates at authority

For a request to recover a deployed artifact, first bind the named system and
the requested state (historical edition, used at a specific time, or current
deployment). A related design document is a candidate, not the recovered file.
Follow the project's artifact/deployment owner before selecting a similarly
named experiment. If runtime proof is accessible, obtain it before delivering;
an “unverified” disclaimer does not complete the lookup. If the user explicitly
wants a historical draft, return that edition without imposing a live check.

Open promising candidates at their original path. Check:

- **Match**: does it solve the same business problem, not merely share words?
- **Authority**: current implementation/SSOT beats a historical proposal;
  raw transcript proves what was said, not that it remains correct.
- **Freshness**: compare current Git HEAD, file mtime, decision date, and any
  superseded marker. Do not use an archive to overwrite current behavior.
- **Outcome evidence**: prefer code/tests/accepted deliverables and operating
  results over a process that merely looks complete.

**Dismissing a batch of hits is itself a claim.** When a carrier returns many
matches and you judge all of them irrelevant — "those are just the term being
quoted in documentation", "that is an unrelated module" — that judgement is a
finding you are about to report, not a filtering step you did on the way to one.
Open at least one hit per distinct shape you are dismissing, and say in the
receipt which shapes you ruled out and on what evidence. A carrier that returns
47 matches and contributes nothing to the answer is the same observation as a
carrier that returns nothing, and it deserves the same scepticism as any other
negative result: the run that produced it may be fine while your reading of it
is not.

### 5. Complete the reuse receipt

When an archived request contains an actual file read, first use
[`verify_artifact.py`](scripts/verify_artifact.py) to compare the **selected
deliverable**, not a nearby reference, against its correlated tool result:

```bash
uv run --no-project python scripts/verify_artifact.py \
  --candidate /tmp/agent-backup.zip --member skills/editor/SKILL.md \
  --archive /tmp/request.json.gz --read-path /agent/skills/editor/SKILL.md
```

The checker accepts JSON/gzip bundles with `request_id`, a timezone-qualified
`timestamp`, and `request.body.messages` in Anthropic tool-call format. Omit
`--member` for a plain file. Exit 0 means the candidate's bytes appeared in a
successful correlated `read` at the recorded time — byte-exact for raw-byte
readers (`read`/`read_file`), or, for Claude Code's `Read`, a line-numbered
result whose absolute row numbers provably span the whole file and reconstruct
it (a partial `offset`/`limit` read can never pass; the JSON's `match_basis`
says which proof held, and `rejected_read_reconstructions` counts numbered
reads that failed the coverage preconditions). 1 means no matching proof; 2
means invalid/ambiguous evidence. Path mentions, failed reads and related old
files do not pass. Other evidence formats remain supported by the
source-specific reader; do not convert an unsupported format into a negative
claim.

The archive must come from the verified system's source-specific reader or
observability tool. This check cannot authenticate an archive, decide which
system the user meant, or establish current deployment. It also does not prove
that every dependency was recovered. Preserve these distinctions in the handoff.
For artifact retrieval, record the selected artifact/member and its matching
evidence in the adoption reason. A receipt about a locator document alone does
not establish that the final artifact is correct.

Classify the items you actually inspected:

```bash
uv run --no-project python scripts/prior_work.py complete \
  --run <run_id> \
  --reuse '<candidate_id>=reuse unchanged because ...' \
  --adapt '<candidate_id>=adapt boundary X because ...' \
  --session-id "$CODEX_SESSION_ID"
```

If none qualify, use `--no-reuse-reason` with the verified mismatch. “No hits”
is not a reason; it is a retrieval observation and may require widening terms or
resolving a failed carrier. And a zero-candidate required carrier cannot be
reported as "none exists" by paraphrase either: attach the label census — run
`analyze_sessions.py search --all-projects --exclude-session <CURRENT_ID> '<term>'`
for each outcome term and report the per-label hit counts (`message` /
`thinking` / `tool_input:<name>` / `tool_result` / `attachment` / `summary`).
The census does not change the conclusion; it closes the "re-derive the query
syntax" path by showing where the terms do live.

The completed receipt preserves `business_outcome` and `outcome_terms`; `check`
rejects legacy or hand-built receipts that omit either field. Receipt freshness
is bound to the definitions of **required** carriers. Editing an optional carrier
does not invalidate already verified required coverage; changing a required root,
route, mode, authority, or limit does. The full manifest hash remains provenance.
Then verify:

```bash
uv run --no-project python scripts/prior_work.py check \
  --session-id "$CODEX_SESSION_ID"
```

Only after this passes should substantial production begin. Cite adopted
candidate IDs in the implementation/plan so the receipt is connected to the
result instead of becoming ceremonial paperwork.

## Companion hooks

Install after the manifest is valid and the self-test is green:

```bash
scripts/prior-work-retrieval.sh --selftest
scripts/prior-work-retrieval.sh --install
```

The versioned wrapper is the synchronous hook-runtime SSOT. It resolves a
direct Python interpreter and never enters a package-manager/cache lifecycle;
keep the `uv run ... prior_work.py` commands above as explicit retrieval and
receipt operations, not as hook launchers.

The installer adds the required handlers to both Claude and Codex without replacing
unrelated hooks:

- `UserPromptSubmit` creates a prompt-scoped requirement only for an explicit
  prior-work/reuse/history signal and injects the Skill route. The filters keep
  that signal from firing on things the user did not ask for:
  - **Not the user speaking.** Internal templates (`You are a/an …`,
    `# Overview`), harness envelopes (`<agent-message …>`,
    `<task-notification …>`, `<system-reminder …>`) and pasted transcript lines
    (`⏺ …`) all reach this handler as prompts. They never arm a requirement.
  - **The executor cannot satisfy a gate.** A prompt that forbids reading
    skills or running the shell has removed the capabilities completing a
    receipt needs; gating it blocks work with no path to unblock. A prompt that
    says outright it is opting out of prior-work retrieval is honoured in the
    spellings people actually use (`Do NOT perform prior-work retrieval`,
    `opts out of prior-work retrieval`), not just `skip`/`disable`.
  - **Negated reuse.** “不要复用 X”, “别沿用”, `don't reuse` decide *against*
    prior work; dating something as old (“很久之前写的”) argues it is stale
    rather than asking to find it. Both are excised before matching, so a
    genuine ask in the same sentence still counts, while 别重复造轮子 /
    不希望你重新造 — which ask *for* reuse — keep arming.
  - **Hedge recall needs a distal referent.** 上次 / 好像是 / 我记得是 / 记不清
    arm only alongside a work noun carrying a distal or indefinite determiner
    (那个/某个/哪个 脚本), because 这个脚本 is the object in front of you — “这个
    脚本好像是死循环” is a bug report, not a recall. Bare `history` likewise
    needs a carrier (`conversation history`, not `git history`).
  - **A valid receipt already covers this session.** Hedge-phrased recall no
    longer mints a fresh requirement that strands the completed receipt. An
    explicit new prior-work ask still does.

Run `scripts/prior_work.py audit` to see whether the gate is behaving: it
reports the trigger mix, the empty-gate rate (armed requirements that never
produced a receipt — the signature of gating something that cannot comply),
stranded receipts, non-user-input arms, and the matched token behind each
still-arming entry. `--json` for machine output. Judge the gate by that number,
not by whether its own tests pass.
- `PreToolUse` blocks substantial writes only when that explicit requirement
  already exists and lacks a valid receipt. It never turns an ordinary write
  into a retrieval obligation. Read-only discovery and small mechanical edits
  remain available while a requirement is active.
- `Stop` validates an explicit requirement that already exists. It never invents
  one from output length, code, tool use, or a generic production request.

It migrates the narrower unversioned `recall-first-evidence` UserPromptSubmit
handler into this superset while leaving its script on disk for recovery. The
old trigger families (“我们之前”, “什么来着”, fuzzy memory) are regression tests.
Run the machine's profile-settings synchronizer after installation so every
Claude profile receives the main settings. Codex requires one human trust review
through `/hooks`; the installer never forges it.

The user can explicitly say not to search prior work for the current prompt.
That opt-out becomes prompt-scoped state, not an environment-variable bypass.
Recognized phrasings pair a refusal verb (不用/不要/不需要/跳过, or
skip/disable/opt out/do not perform) with a retrieval noun (查历史/历史检索/
prior-work/prior work/history retrieval) in the same breath — a bare
「不需要检索」without the carrier phrase does not match, so when advising the
user mid-gate, quote a full working form such as 「本任务不需要 prior work
检索」.
Malformed/missing manifest or receipt state fails closed only at substantial
production; read-only investigation and a write targeting exactly the manifest
path remain possible so the agent can repair the gate without bypassing it.

## Search routing

| Need | Route |
|---|---|
| Known exact string, symbol, path | Filesystem carrier (`rg`) |
| Meaning remembered, wording changed | Declared semantic adapter (gbrain, or Claude-history hybrid recall — that index covers Claude sessions only) |
| Exact prior Claude tool/thinking/file-history evidence | `read-claude-code-history search` |
| Prior conversation evidence whose platform is unknown, plural, or not Claude | `local-conversation-history`; each provider is a separate store, so a Claude-only answer cannot support "we never discussed it" |
| Meeting decision or speaker claim | Project transcript carrier; open raw speaker turn |
| Archived WeChat text/voice transcription | Declared WeChat archive carrier |
| Live/latest WeChat | `read-wechat-messages`; record manual coverage |
| Current code behavior | Open implementation/tests at current Git revision |
| Work targets a remote box or a foreign checkout (deploy dir, upstream fork) | That repo's own `docs/`, `Makefile`, deploy README **first** — they are not manifest carriers, so record them as manual coverage; never reconstruct a build/deploy command the box already documents |

## Boundaries

- The manifest is explicit and versioned separately from mutable index state.
- Search results are hypotheses. The receipt records verification and reuse.
- Do not copy private project data into a public example or Skill fixture.
- Do not silently fall back from a failed required carrier. Record the gap.
- External web research starts after local prior work, unless the user explicitly
  asks for current external facts or the local evidence cannot answer.
- This Skill is the workflow. Companion hooks may require a fresh receipt before
  `Write`/`Edit`; Stop may enforce that same existing obligation, but final-answer
  shape cannot create a new one. Hooks do not decide which candidate is good.

## Surface contract

First use in a session: run `python3 scripts/surface_version.py` once and note
the 12-char fingerprint — the sha256 of this skill's `scripts/**/*.py` code
surface. If it differs from the fingerprint you last saw for this skill, the
code changed under you: re-read this SKILL.md and the references from disk
before acting on in-context echoes of them. The fingerprint covers code only;
documentation edits do not change it.

## Maintainer verification

```bash
uv run --no-project python -m unittest discover -s tests -p 'test_*.py'
uv run --no-project python scripts/prior_work.py \
  --manifest tests/fixtures/manifest.json validate-manifest
scripts/prior-work-retrieval.sh --selftest
```

Regression cases must include the real failure families: cross-project rules not
loaded, existing provider contract ignored, old decision beating North Star,
artifact capability declared nonexistent, adjacent agent evidence missed, and
conversation/meeting/WeChat carrier gaps hidden by a global “searched” claim.
