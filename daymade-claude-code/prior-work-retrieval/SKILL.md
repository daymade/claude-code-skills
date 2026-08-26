---
name: prior-work-retrieval
description: >-
  Finds and verifies the user's existing successful work before producing a new
  implementation, plan, report, workflow, document, or external message. Use
  whenever the task may already have an answer in another project, repository,
  Skill, SOP, decision record, meeting transcript, WeChat archive, or prior
  Claude conversation; especially when the user says “以前做过”, “已有代码”,
  “历史经验”, “别重复造轮子”, “先看看项目最近进展”, “retrieve before produce”,
  or asks to generalize a previous solution. Produces an auditable retrieval
  receipt with source coverage, authority/freshness checks, and explicit
  reuse/adapt/reject decisions. Never treats zero ranked hits as absence.
argument-hint: "<task or question>"
---

# Prior Work Retrieval

Run this before substantial production. Its job is not to generate another
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

Write the outcome sentence, then provide 3–8 distinctive terms: product/entity
names, technical nouns, old project names, and failure symptoms. Do not pass
generic verbs such as “做 / 优化 / 系统” alone.

```bash
uv run --no-project python scripts/prior_work.py retrieve \
  --query 'the real task in one sentence' \
  --term 'distinctive entity' \
  --term 'old workflow name' \
  --term 'failure symptom' \
  --session-id "$CODEX_SESSION_ID"
```

When a normally optional live carrier is material to the request, promote it
explicitly: `--require-source live-wechat`. The receipt cannot complete until
that manual route is recorded.

The command searches filesystem carriers with `rg`, calls explicitly declared
command adapters (for example the formal Claude-history finder), and surfaces
manual routes such as live WeChat. It writes an immutable run JSON under the
manifest's `state_dir` and returns its `run_id`.

If a required carrier says `manual_required`, perform that named Skill route and
record its result before completion. A local WeChat archive search does not
prove live WeChat coverage; a conversation index does not prove meeting or code
coverage.

### 4. Verify candidates at authority

Open promising candidates at their original path. Check:

- **Match**: does it solve the same business problem, not merely share words?
- **Authority**: current implementation/SSOT beats a historical proposal;
  raw transcript proves what was said, not that it remains correct.
- **Freshness**: compare current Git HEAD, file mtime, decision date, and any
  superseded marker. Do not use an archive to overwrite current behavior.
- **Outcome evidence**: prefer code/tests/accepted deliverables and operating
  results over a process that merely looks complete.

### 5. Complete the reuse receipt

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
resolving a failed carrier.

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

The installer adds three handlers to both Claude and Codex without replacing
unrelated hooks:

- `UserPromptSubmit` marks a new prompt-scoped requirement and injects the Skill
  route when prior-work or production signals are present.
- `PreToolUse` blocks substantial new/large writes, patches, delegated
  production, and Bash/Codex exec paths that carry a write signal or an unknown
  executable until the current requirement has a receipt. Read-only discovery,
  small mechanical edits, and `tinkle_` scratch files remain available.
- `Stop` catches substantial chat-only deliverables that never wrote a file.

It migrates the narrower unversioned `recall-first-evidence` UserPromptSubmit
handler into this superset while leaving its script on disk for recovery. The
old trigger families (“我们之前”, “什么来着”, fuzzy memory) are regression tests.
Run the machine's profile-settings synchronizer after installation so every
Claude profile receives the main settings. Codex requires one human trust review
through `/hooks`; the installer never forges it.

The user can explicitly say not to search prior work for the current prompt.
That opt-out becomes prompt-scoped state, not an environment-variable bypass.
Malformed/missing manifest or receipt state fails closed only at substantial
production; read-only investigation and a write targeting exactly the manifest
path remain possible so the agent can repair the gate without bypassing it.

## Search routing

| Need | Route |
|---|---|
| Known exact string, symbol, path | Filesystem carrier (`rg`) |
| Meaning remembered, wording changed | Declared semantic adapter (gbrain or Claude-history hybrid recall) |
| Exact prior Claude tool/thinking/file-history evidence | `read-claude-code-history search` |
| Meeting decision or speaker claim | Project transcript carrier; open raw speaker turn |
| Archived WeChat text/voice transcription | Declared WeChat archive carrier |
| Live/latest WeChat | `read-wechat-messages`; record manual coverage |
| Current code behavior | Open implementation/tests at current Git revision |

## Boundaries

- The manifest is explicit and versioned separately from mutable index state.
- Search results are hypotheses. The receipt records verification and reuse.
- Do not copy private project data into a public example or Skill fixture.
- Do not silently fall back from a failed required carrier. Record the gap.
- External web research starts after local prior work, unless the user explicitly
  asks for current external facts or the local evidence cannot answer.
- This Skill is the workflow. Companion hooks may require a fresh receipt before
  `Write`/`Edit` or a substantial final response, but hooks do not decide which
  candidate is good.

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
