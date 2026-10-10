---
name: authoring-and-reuse
description: >-
  Capture intent and authorized sources, choose reuse/extension ownership, and write executable Skill instructions. Read the matching section before source selection, reuse decisions, frontmatter/runtime design or result presentation.
---

# Author the reusable capability under its owner

Read Capture Intent when the requested job, input source or output remains unresolved; ownership before creating or restructuring a capability; Prior Art Research when selecting infrastructure; and the writing sections only for the fields or runtime structure being changed. Read Show the result at result-design or delivery, and its template contract only for recurring reports. Resolve the task and ownership, then return to the shared creation/update path; special source workflows retain their own source-admission and return contracts.

## Contents

- [Communicating with the user](#communicating-with-the-user)
  - [Show the result, not just the work](#show-the-result-not-just-the-work)
  - [Using AskUserQuestion (Critical — Read This)](#using-askuserquestion-critical--read-this)
  - [Capture Intent](#capture-intent)
  - [The extend-vs-create check — runs BEFORE any specialized branch](#the-extend-vs-create-check--runs-before-any-specialized-branch)
  - [Prior Art Research (Do Not Skip)](#prior-art-research-do-not-skip)
  - [Interview and Research](#interview-and-research)
  - [Write the SKILL.md](#write-the-skillmd)
  - [Skill Writing Guide](#skill-writing-guide)
  - [Writing Style](#writing-style)
  - [Dates and Version References](#dates-and-version-references)
  - [Skill Creation Best Practice](#skill-creation-best-practice)
  - [Step 0: Prerequisites Check](#step-0-prerequisites-check)
  - [Step 1: Understanding the Skill with Concrete Examples](#step-1-understanding-the-skill-with-concrete-examples)
  - [Step 2: Planning the Reusable Skill Contents](#step-2-planning-the-reusable-skill-contents)
  - [Step 3: Initializing the Skill](#step-3-initializing-the-skill)
  - [Step 4: Edit the Skill](#step-4-edit-the-skill)
- [Ground technical and methodological claims](#ground-technical-and-methodological-claims)
  - [Technical assertions and landed-claim verification](#technical-assertions-and-landed-claim-verification)
  - [Capability-negative claims](#capability-negative-claims)
  - [Domain methodology](#domain-methodology)
- [Select the authorized source workflow](#select-the-authorized-source-workflow)
  - [Specialized Workflow: Wrapper Skills for Third-Party CLI Tools](#specialized-workflow-wrapper-skills-for-third-party-cli-tools)
  - [Specialized Workflow: Enrich a Skill from Conversation History](#specialized-workflow-enrich-a-skill-from-conversation-history)
  - [Specialized Workflow: Distill User Preferences from an Approved-Artifact Corpus](#specialized-workflow-distill-user-preferences-from-an-approved-artifact-corpus)

## Communicating with the user

### Show the result, not just the work

For a Skill creation/update delivery, read
[delivery identity](delivery-identity.md). Generate the formal Skill
identity from verified source metadata, preserve its plugin version ownership,
and check the actual final reply against the task-bound candidate. Keep
installation, publication and business-result claims on their own evidence.

At delivery, ask whether the user needs to compare outcomes, inspect several artifacts or evidence items, or choose among unresolved options. If a visual report would make that result easier to understand or judge, load `report-with-html` and let it own the page structure, template, evidence presentation, and browser verification. Load `data-visualization-discipline` through that Skill when the report needs a chart. A single small edit or status update needs only a concise reply; the paired-eval viewer below already owns review of individual eval outputs and feedback, so do not duplicate it with another report.

When creating or improving another skill, apply the same decision to **that skill's normal user-facing result**. If visual reporting is a recurring part of its job, add a conditional handoff to `report-with-html` at the end of its runtime workflow and declare that dependency. If the reporting Skill is unavailable, say the requested visual deliverable is unavailable; do not silently invent a substitute template or claim a report was produced. Do not make every invocation generate HTML, and do not substitute a polished page for a verified result.

**Let a real report earn its template.** For a new Skill that will repeatedly generate customer-specific reports, first run it on a real authorized case and use `report-with-html` to produce and browser-verify the actual report. Show that report to the user. Once they can inspect its content, layout, and interactions, ask separately whether this report's reusable form should become that Skill's default template. Their approval of the report's facts is not approval of its future template. If they reject or have not answered, revise the report or leave it as a one-off; do not promote a template.

An approved template is **user-owned local data, not part of the Skill package**. Extract its reusable structure, visual treatment, and interactions to `~/.claude/skill-report-templates/<publisher-or-project>/<skill-name>/template.html`, with a sibling `manifest.json` recording the qualified Skill identity, approval date, and Skill version. Freeze the two filesystem-safe path segments in the new Skill's runtime instructions; do not derive a different directory from each installation path or current working directory. Remove the first customer's data, names, evidence, and conclusions. Do not write the approved template into the Skill's `assets/`, source repository, installation symlink, or plugin cache: an update to the Skill must not overwrite the user's approved form. Do not create this local directory before approval.

When authoring the new Skill, teach its runtime to check that stable local path. If an approved template exists and still fits the current report output contract, pass it as the approved starting form to `report-with-html`; otherwise use that Skill's ordinary report workflow and seek approval of the new form after the report is shown. If a Skill update changes the report contract, keep the old local template untouched and ask for renewed approval before replacing it. Future reports fill the approved form with each customer's verified data and still use `report-with-html` for generation and visual QA. A template on this machine does not ship with the Skill or automatically appear on another machine; do not freeze customer-specific claims or reuse an old report as current evidence.

So please pay attention to context cues to understand how to phrase your communication! In the default case, just to give you some idea:

- "evaluation" and "benchmark" are borderline, but OK
- for "JSON" and "assertion" you want to see serious cues from the user that they know what those things are before using them without explaining them

It's OK to briefly explain terms if you're in doubt, and feel free to clarify terms with a short definition if you're unsure if the user will get it.

### Using AskUserQuestion (Critical — Read This)

Ask only when missing information, a mutually exclusive product choice or an
authorization boundary changes the work. Reuse answers and existing authorization;
routine implementation choices within that scope do not need another approval.
Use the host's structured question tool when available and suitable; its actual
permission and option limits take precedence over the format below.

**When a question is needed, supply this context:**

1. **Re-ground**: State the skill name, current phase, and what just happened (1-2 sentences). The user may have context-switched away.
2. **Simplify**: Explain the decision in plain language. No function names or internal jargon. Say what it DOES, not what it's called.
3. **Recommend**: Lead with your recommendation and a one-line reason why. If options involve effort, show both scales: `(human: ~X min / Claude: ~Y min)`.
4. **Options**: Provide 2-4 concrete, lettered choices. Each option should be a clear action, not an abstract concept.

**Rules:**
- One decision per question — never batch unrelated choices
- Provide an escape hatch ("Other" is always implicit in AskUserQuestion)
- Accept the user's choice — nudge on tradeoffs but never refuse to proceed
- Skip the question if there's an obvious answer with no tradeoffs (just state what you'll do)
- Silence does not authorize a required product or permission decision. Continue
  independent authorized work and hold only the dependent action. For an optional
  preference, follow the host's unanswered-question contract and state any default.

### Capture Intent

Before the first write, follow [Edit Skills at Source Location](../SKILL.md#critical-edit-skills-at-source-location).

Start by understanding the user's intent. The current conversation might already contain a workflow the user wants to capture (e.g., they say "turn this into a skill"). If so, extract answers from the live conversation first — the tools used, the sequence of steps, corrections the user made, input/output formats observed. Ask only for a remaining gap that changes the task; complete intent and existing authorization permit the next step.

**Source inventory — always before drafting, with consent boundaries.** Inventory the live conversation and existing docs/skills that overlap (see Prior Art Research below). Earlier local sessions are a separate private source: use them only with explicit history authorization. Reuse known source boundaries rather than requesting them again. If approved, retrieve bounded evidence through the owning history reader and follow the conversation-mining workflow's preparation route for selected corpus distillation; never load raw transcript files into your own context. If not approved, continue from the live conversation and existing project sources without treating the missing history as a blocker.

When mining a conversation (or session transcripts), inventory **both asset classes — they land in different places**. *Knowledge* — endpoints, parameters, pitfalls, decision rules — becomes SKILL.md guidance or `references/`. *Code the session had to write* — helper scripts, injected snippets, renderers, one-off templates — is a `scripts/` candidate: first check whether an existing/upstream tool already owns that execution. Parameterize and bundle only the still-needed local helper or adapter; do not preserve a temporary reimplementation merely because this session wrote it. A prior distillation captured polished prose but omitted the reusable helpers; the general lesson is to keep both knowledge→references and code→scripts channels in frame.

When the source material is *past* sessions rather than the live conversation,
enter the conversation-mining workflow. Its bounded retrieval route locates
evidence before its manifest → discover → redact → chunk route prepares selected
content for distillation. Do not give agents raw transcript files or hidden
reasoning; retain roles, source anchors and the declared role/shard budget.

**First, resolve which DIRECTION this is — before the questions below.** The request may be one of several *opposite* things: build a NEW skill / edit an EXISTING skill / optimize skill-creator itself / or it's not-a-skill-at-all (a one-off task). Guessing wrong wastes the whole session — the research you'd do for "new skill" is the wrong research for "optimize the meta-tool." When the phrasing is ambiguous (e.g. "make me a skill" while pointing at skill-creator's own path), one AskUserQuestion here costs 30 seconds. The wrapper-skill fork below is one special case of this; the direction check is general.

`Use skill-creator to optimize <existing-skill>` means the normal existing-skill update path. It does **not** authorize conversation-history mining, a broad rewrite, Tier 3 classification, or multi-agent evaluation. Inspect the actual proposed deltas first; escalate only for a failure surface those deltas really introduce.

1. What should this skill enable Claude to do?
2. When should this skill trigger? (what user phrases/contexts)
3. What's the expected output format?
4. Should we set up test cases to verify the skill works? Skills with objectively verifiable outputs (file transforms, data extraction, code generation, fixed workflow steps) benefit from test cases. Skills with subjective outputs (writing style, art, taste-calibrated reports) often can't use assertions — but "no assertions" is not "no verification". Their verification paths, in order of cost:
   - **Historical-task replay**: when it covers the changed behavior, run one named real prompt with the candidate and check its output against the changed rules ("does the new output actually follow the tokens / title grammar this update introduced?"). This can catch "the rule was written but nothing reads it". An old/new comparison is paired evaluation and requires its separate authorization; permission to research history or use a team does not authorize a benchmark pipeline.
   - **Production-as-eval**: acknowledge that the real test is the user's next actual use — then make the loop explicit: every user correction afterward is an incident to fold back (the skill's own "迭代/活文档" section), every approval is corpus material. A taste skill that ships without this write-back habit doesn't improve; one that has it converges without ever running a formal eval. **And when the skill's output is something that keeps running — a guard, a monitor, a scheduled job, a hook — its own telemetry is eval data, and the highest-signal record in it is the first false alarm.** A user correction requires a user to notice and bother; a deployed mechanism reports on itself unprompted, often within a day, and a false positive is the sharpest form of that report because it proves a rule you wrote is wrong in a way no amount of re-reading would have shown. Treat the first one as a scheduled eval result rather than an annoyance: check it before assuming the mechanism misbehaved, because the more likely finding is that the *instruction* was too absolute. (Real instance: a skill prescribed a fail-loud check, the deployed check fired once overnight on a perfectly healthy condition, and the fix was to correct the over-absolute sentence in the skill — nobody complained; the telemetry did.)
   - **Render + human review** for visual outputs (the skill's own visual-QA gates), never a grep assertion pretending to measure aesthetics. **And the renderer you verify with must be the same engine the deliverable will be consumed in** — whatever previewer is conveniently installed is not a substitute. A thumbnailer whose layout engine differs from the target application will silently *hide* the exact defects you are looking for, and a green verification on the wrong engine is worse than no verification, because it buys false confidence. Real case (2026-07): a .docx was "visually verified" through macOS Quick Look thumbnails, which do not reproduce justified-text stretching; Word showed the document's info blocks blown apart the moment the user opened it. The fix was to install the Word-compatible engine (LibreOffice), convert to PDF, rasterize per page, and read every page. Match the engine, or the verification is theater. **This generalizes past renderers to every verification tool** — parser, linter, validator: it must share an implementation with production, or its green is meaningless. Second case, same shape: an author tried to catch a markup pattern that corrupts the final document by checking at the source stage with a *different* markdown implementation than the production toolchain used — it parsed all three known-bad inputs as perfectly fine, so any pre-check built on it would have silently passed everything. The honest conclusion was that this particular defect is only detectable after the production tool has run, and the check belongs there. **When no available tool shares the production implementation, say the check cannot be done at that stage — do not build the one that can only produce false green.**
   Select the evidence required by the shared verification router. Ask only for an
   unresolved result preference or evidence work outside existing authorization.

After extracting the answers, state the skill type and selected evidence path.
Use the following question only if an unresolved user choice changes them:

```
Creating skill "[name]" — here's what I understand so far:
- Purpose: [1-sentence summary]
- Triggers on: [key phrases]
- Output: [format]

RECOMMENDATION: [Objective/Subjective/Hybrid] skill → [suggested testing approach]

Options:
A) Objective output (files, code, data) — set up automated test cases (Recommended if output is verifiable)
B) Subjective output (writing, design) — qualitative human review only
C) Hybrid — automated checks for structure, human review for quality
D) Skip testing for now — just build the skill and iterate by feel
```

Apply the verification router before choosing downstream evidence; this example
does not waive required checks or authorize paired evaluation.

### The extend-vs-create check — runs BEFORE any specialized branch

Each of the three specialized workflows below ends with "**do not** continue reading the sections below", and *Prior Art Research* happens to sit after them. **That ordering is layout, not execution order.** The extend-vs-create judgment applies to every branch, and skipping it is exactly how a session ships a skill that duplicates one already installed.

So before routing into wrapper-skill / conversation-mining / artifact-corpus, answer one question: **does a skill already exist that this capability belongs to?**

**Discover the roots, don't recall them.** A hand-maintained list of install locations is exactly the artifact that goes stale, and the root you forget is the one that bites.

**Search for the file, not for a directory named `skills`.** Skill directories are named after the *skill* (`skill-creator/`, `<suite>/<skill>/`), so a source repo, a marketplace clone and a plugin cache contain no directory called `skills` at all — searching for that name silently skips them while appearing to work. Every skill has a `SKILL.md`; that is the layout-agnostic handle.

```bash
# 1) discover
find ~ -type f -name SKILL.md -not -path '*/node_modules/*' -not -path '*/.git/*' > /tmp/all-skills.txt

# 2) VERIFY COVERAGE BEFORE TRUSTING IT — `2>/dev/null` and permission denials hide gaps
#    silently, which is exactly how a sweep reports "nothing found" from a root it never
#    entered. A 0 on any line you expect means the search did not go there:
for r in '/.claude/skills/' '/plugins/marketplaces/' '/plugins/cache/' '/.claude-profiles/'; do
  printf '%6s  %s\n' "$(grep -c "$r" /tmp/all-skills.txt)" "$r"
done
# ...and grep for your own skill source repos by path; they must appear too.

# 3) filter by capability VOCABULARY, not by skill name — in every language the target
#    skill might be written in (a skill whose body is Chinese will not match English terms):
xargs grep -li -e '<domain-term>' -e '<域内术语>' < /tmp/all-skills.txt
```

Expect step 3 to take a few seconds and to still return more than you want; narrow with terms specific to the capability rather than generic ones (`chart` matches everything, `stacked bar` does not).

The roots this reaches — and that a from-memory list usually misses: the skill source repos (a `claude-code-skills` checkout and any `-pro` sibling), `~/.claude/plugins/marketplaces/` and `~/.claude/plugins/cache/` (marketplace-installed suites — nothing in the source repos hints they are there), `~/.claude/skills/`, `~/.codex/skills`, `~/.agents/skills`, per-profile config homes (`~/.claude-profiles/<name>/`), and — the one with no signposts at all — **every project's own `.claude/skills/`**. Step 2 is what makes that a claim you verified rather than one you inherited.



**What to do when the overlap *is* a project-level skill in an unrelated project** — the case that war story lands you in, and the one the three bullets below do not cover: you cannot add a sibling to a suite it has none of, and "extend it" would mean editing an unrelated project's working tree. The move that worked: **harvest its rules into the skill you are building, then retire the project-local one with the owner's consent** — it was written against real work, so treat it as the more mature source and reconcile *toward* it. Retiring someone's working skill is the owner's decision, not a side effect of your build.

Four things that sentence leaves out, each of which will stop you:

- **"Reconcile toward it" is a rebuttable presumption, not a rule.** Two standard exits: the project skill may be *stale* (rules written months ago against a system that moved), and it may be *project-specific* (rules that only hold under that project's constraints — importing them wholesale makes your skill narrow, which this file elsewhere tells you not to do). Harvested rules are another author's memory, so **re-verify each one** the way discipline #1 requires of anything you write into a skill.
- **"Retire" needs a mechanism, and its first step is not the one you reach for.** In order:

  1. **`find` the skill's *bodies*, before grepping for its *references*.** A skill routinely has more than one copy in the same repo — `.claude/skills/<name>/` and `.agents/skills/<name>/` are both loaded, by different tools, from the same working tree. Grep answers "who mentions it"; only `find` answers "how many of it are there".
     ```bash
     find <project> -type d -name '<skill-name>' -not -path '*/.git/*'
     ```
     **Do not put the skill's own name in `--exclude-dir`** (it matches by basename, so it hides every same-named directory including the copy you have not found — see the instrument rule in discipline #6). Real case (2026-07): a retirement did exactly that, fixed all five references it found, and left a second full copy under `.agents/skills/` — git-tracked, no retirement marker, a stale snapshot missing the newest rule — which the other tool would still load as live.
  2. **Verify the new home is actually reachable from where the old one was**, *before* deleting anything — a marketplace skill you just pushed is not installed until the marketplace is updated and the plugin installed, and retiring first leaves a window with neither:
     ```bash
     claude plugin marketplace update <marketplace>   # your push is not their cache
     claude plugin install <skill>@<marketplace>
     find -L ~/.claude/plugins/cache -path '*<skill>*' -name '*.md'   # -L: installs are often symlinks
     ```
     The `-L` is not optional — plugin caches frequently symlink into a source repo, and a bare `find` reports the files missing (see the instrument rule in discipline #6).
  3. **Then** grep for references and repoint the live ones. Distinguish **live instructions** (a skill list, a cross-reference, a handoff doc telling the next agent what to use) from **historical records** (a decision log entry saying "on date X we shipped this") — rewriting the second destroys an audit trail to fix a problem it does not have.
  4. **Then** replace each body with a `superseded by <skill>` stub rather than a bare deletion, and make every copy's stub byte-identical. **Keep the YAML frontmatter** — a `SKILL.md` without it may fail to load rather than fail informatively — but rewrite the `description` so the stub announces its own retirement instead of advertising the old triggers; otherwise it keeps winning the routing it no longer serves. The body needs only: where the capability went, and one line on why it moved.
- **Identify the owner with the ownership test below** (it applies here too: a project-level skill has no `marketplace.json`, but the project's `git remote` still tells you whose it is). When the owner is the person you are talking to, "consent" is one `AskUserQuestion`. **When the owner is unreachable, harvest only — do not retire** (which leaves both skills live and competing for the trigger, same end state as a declined retirement — see Coexistence & Precedence below).
- **If the owner declines to retire it**, you now have two skills competing for the same trigger; that is the Coexistence & Precedence problem below, not a failure.

**Search by capability vocabulary, not by skill name.** That project skill would not have matched a name search for the new skill's title; it matched on the domain terms inside its body. Grep the candidate roots for the *concepts* the new skill will handle.

If something overlaps:

**Deciding which bullet applies — whose skill is it?** A filesystem hit does not carry ownership. Read the marketplace's `.claude-plugin/marketplace.json` `owner` field, or `git remote -v` in the containing repo; a hit under `~/.claude/plugins/marketplaces/` can just as easily be your *own* marketplace installed back onto your machine. A project-level skill has no `marketplace.json`, but its project's `git remote` answers the same question.

Two cases the probes get wrong or cannot answer, so check for them before trusting the result: a **fork** shows your own remote while the content is someone else's — treat it as third-party, because their upstream improvements still stop reaching you. And when there is **no marketplace.json and no remote** (a local-only project, a skill hand-copied into a global skills dir), the probes are silent rather than negative: **ask the owner instead of guessing**.

- **The overlap is a third party's skill** (a marketplace suite, an official plugin): **do not re-implement its capability.** Put a *thin increment* in the existing owning router/workflow when one exists — verified pitfalls, invocation and necessary adaptation — and **reference the upstream skill by its installed identity**. A usage lesson does not by itself justify another standalone skill. Cloning someone else's engine into your bundle is the expensive mistake: their upgrades stop reaching you, and the two copies drift apart silently. **Then check the identifiers that cross the seam you just created** — routing to the official tool means handles now travel between two address spaces, and whatever your side emits, theirs has to be able to resolve. Fix that where the identifier is produced, not in a paragraph telling the reader to convert it: the party that suffers may never have loaded your skill. Case 23 in [references/skill-development-methodology.md](skill-development-methodology.md) is the worked example, including why the documentation-shaped fix shipped to a public repo and still failed.
- **The overlap is your own skill**: first decide whether the gap is a workflow within its existing router. Keep one entry when tasks share account/identity, authorization, lifecycle and user intent; put the workflow's guide, scripts and cases beneath that owner. A sibling skill is justified when it needs a distinct invocation, permission or install/update boundary. Shared vendor or vocabulary alone is not a reason to merge unrelated jobs. Retiring an existing entry still requires the user's authorization and verified replacement. **Exception:** for an unrelated project's working tree, use the project-level ownership procedure above.
- **Some related skill already points at the gap you're filling** (e.g. its description says "for X, use Y"): after you build, close the loop — update that pointer, or you have left a dangling reference behind.

Before creating or restructuring a capability, state its **ownership decision** in the
existing plan: user entry → executable owner/upstream → home of our verified increment
→ dependency update path → user-visible completion evidence. Reuse the user's prior
choices; this is not a new approval gate or mandatory document. For a narrow edit
that leaves ownership unchanged, retain that mapping and proceed.

Only when no suitable owner exists, or a distinct invocation/lifecycle boundary is
justified, build a standalone skill. The evidence that permits an independent skill
must also prevent over-merging: an unrelated permission or lifecycle remains separate.



### Prior Art Research (Do Not Skip)

The user's private methodology — their domain rules, workflow decisions, competitive edge — is what makes a skill valuable. No public repo can provide that. But the user shouldn't waste time reinventing infrastructure (API clients, auth flows, rate limiting) when mature tools exist. Prior art research finds building blocks for the infrastructure layer so the skill can focus on encoding the user's unique methodology.

**Two axes, don't conflate them.** This section sources the *infrastructure* layer (tools / MCPs / libraries / existing skills to reuse). The *methodology* layer has two inputs of its own: the user's private edge (theirs alone, un-retrievable) **and the domain's established best-practices / science, which you retrieve into context by default per standing discipline #3.** Finding the right tool does not discharge the second — a viz skill that adopts a charting library but never absorbs Cleveland/Bertin is still capped at your pretraining. Do both.

**Search these channels in order.** Research inline by default. Use subagents only after the heavy-eval/agent-budget gate above establishes genuinely independent unknowns; the public-source channels are not a default fan-out package.

| Priority | Channel | What to search | How |
|----------|---------|---------------|-----|
| 1 | **Live conversation or explicitly approved history** | User's proven workflows, verified API patterns, corrections made during debugging | Use the current conversation directly. Search earlier local history only after the explicit-source gate above, then use the redacted conversation-mining path rather than ad-hoc grep |
| 2 | **Local documents & SOPs** | User's private methodology, runbooks, existing skills | Search project directory, `~/.claude/CLAUDE.md`, `~/.claude/references/` |
| 3 | **Installed plugins & MCPs** | Already-integrated tools | Check `~/.claude/plugins/`, parse `installed_plugins.json`; check `~/.claude.json` for configured MCP servers |
| 4 | **skills.sh** | Community skills | `WebFetch https://skills.sh/?q=<keyword>` |
| 5 | **Anthropic official plugins** | Official/partner plugins | `WebFetch https://github.com/anthropics/claude-plugins-official/tree/main/plugins` and `external_plugins` directory |
| 6 | **MCP servers on GitHub** | Existing MCP servers for the same API | `WebSearch "<service-name> MCP server site:github.com"` |
| 7 | **Official API docs** | The target service's own documentation | `WebSearch "<service-name> API documentation"` or `WebFetch` the docs URL |
| 8 | **npm / PyPI** | SDK or CLI packages | `npm search <keyword>` or `curl https://pypi.org/pypi/<name>/json` |

Channels 1-3 surface the user's own proven patterns and existing integrations. Channels 4-8 find public infrastructure. The user's private SOP always takes precedence — public tools are building blocks, not replacements. In competitive domains (finance, trading, proprietary operations), the valuable methodology will never be public.

**Bias toward merge/extend over create-new, and sweep EVERY skill root — not just `~/.claude`.** When channels 1-3 turn up an existing skill that overlaps the requested domain, the usual right move is to extend or merge into it — **except when it lives in an unrelated project's working tree, where the direction reverses: harvest *from* it into the skill you are building rather than merging *into* it** (see the project-level case in the extend-vs-create check above) (one real "new skill" task became "make the existing extractor the extract-phase of the new archiver"), not to ship a parallel skill that competes for the same triggers — two overlapping skills fight over triggering and confuse users. When searching, **discover the install roots rather than recalling a list** — use the `SKILL.md` sweep and its coverage self-check from the extend-vs-create section above (searching for a directory named `skills` misses source repos, marketplace clones and plugin caches entirely, because their skill directories are named after the skill). Run the coverage check rather than trusting this sentence: **every project's own `.claude/skills/`** is the root a from-memory list reliably drops, because nothing outside that project references it. A skill the user already installed *anywhere* is the strongest prior art there is, and a project-local one is often the most mature: it was written against real work.

**If a public MCP server or skill is found, clone it and verify — don't trust the README:**

1. **Read the actual source code** — many projects have polished READMEs on hollow codebases
2. **Verify auth method** — does it match how the API actually authenticates? (X-Api-Key headers vs Bearer vs OAuth — many get this wrong)
3. **Check test coverage** — zero tests = prototype, not production-grade
4. **Check maintenance** — last commit date, open issue count, response to bug reports
5. **Check environment compatibility** — proxy/network assumptions, hardcoded DNS/IPs, region locks
6. **Check license** — MIT/Apache is fine; GPL/SSPL may conflict with proprietary use
7. **Check dependency weight** — huge dependency trees create conflict and security surface

**Decision matrix:**

| Finding | Action |
|---------|--------|
| Mature MCP/SDK handles the infrastructure | **Adopt it, build on top** — install the MCP, then build the skill as a workflow layer encoding the user's methodology |
| Partial MCP or SDK exists | **Extend** — use for infrastructure, fill gaps in the skill |
| Official/public skill implements a required capability | **Verify and reuse it** — exercise the needed interface; keep local methodology, account constraints and acceptance as an increment under their owner. Public origin neither proves suitability nor makes it merely inspiration |
| Complementary skill provides a required sub-capability | **Choose by ownership/update boundary** — resolve an independently maintained dependency, or bundle an owned self-contained helper. See "Complementary Skills" below |
| Nothing public exists | **Build from scratch** — validate API access patterns work (auth, endpoints, proxy) before writing the full skill |
| Verified integration mismatch makes reuse unsuitable | **Choose the smallest justified adapter or replacement** — distinguish a fixable invocation/version gap from missing capability; explain maintenance and update consequences. Convenience alone does not override a user-selected upstream |
| User deliberately supersedes an installed skill (fork, hardened edition) | **Ship it with a supersede kit** — see "Coexistence & Precedence" below |

#### Coexistence & Precedence (deliberate overlap)

Merging into the existing skill is the default fix for overlap (above). But when the user *deliberately* ships a skill that overlaps an installed one — a fork of an official plugin, a hardened in-house edition — the two entries will sit in the skill list with similar descriptions and Claude will route between them at random. Resolve it, in escalating order: rename if the overlap is accidental; add a description tiebreaker ("supersedes X — when both appear, always use this one"); and for distributed forks, stamp a conditional supersede kit into the skill with `scripts/generate_supersede_kit.py` — a consent-based SessionStart routing hook that only ever installs on machines where the competitor is actually present, refuses to install elsewhere, and self-disables if either side disappears. Mechanics, decision table, SKILL.md sample wording, and sandbox verification: [references/skill-precedence-and-coexistence.md](skill-precedence-and-coexistence.md). This skill dogfoods the same kit against the official skill-creator plugin (see "First: coexistence check" at the top).

**The more common case: your new skill silently loses the trigger to the *installed population*, without any deliberate fork.** A skill's domain (image generation, PDF handling, dashboards) is often already crowded with several installed skills, and a fresh skill can lose auto-routing to all of them. So **verify triggering early — the build isn't done when the content is good.** After a draft exists, fire a few realistic queries through `claude -p` and check the new skill actually WINS; if it doesn't, **name the specific competitor** it lost to (different queries often lose to different skills). Then know two things: (1) **prose can't always win a crowded slot** — the resolution ladder is rename → description tiebreaker/SUPERSEDES → manual invocation → SessionStart routing hook (structural; modifies global config, so requires the user's explicit consent, same discipline as `--no-verify`); and (2) **the fix depends on who authored the competitor** — competitors that are *third-party* → accept manual invocation or a routing hook; competitors that are *your own* → merge/consolidate them into one, don't keep two of your skills fighting for the same trigger. (The full resolution ladder lives in [references/skill-precedence-and-coexistence.md](skill-precedence-and-coexistence.md) — that file is the SSOT; the summaries here and above are pointers, don't extend them independently.) Documenting the chosen path (e.g. an "Activation" note saying "invoke manually, competitors are third-party") stops the next session from re-litigating it. (methodology Case 13)

##### Complementary Skills: preserve the update owner

Resolve dependencies; do not assume they are installed, and do not treat copying
another maintained Skill as the default cure for a missing installation.

| Dependency | Integration |
|---|---|
| Official or independently maintained Skill/tool | Keep its source unmodified. Resolve the installed identity, verify required interface/version, install the exact dependency within existing authorization if missing, and read back a representative operation. Keep invocation fixes and business acceptance in our owning workflow; preserve the upstream update path |
| Our self-contained helper/template deliberately shipped with this capability | Bundle it when that is the chosen distribution contract. Keep one canonical source and a declared copy/update mechanism; test the shipped copy. Do not silently fork a separately maintained engine |
| Explicit standalone/offline distribution or approved fork | Bundle/pin only under that chosen boundary, with provenance/license, update responsibility and replacement tests. Keep this supported escape; a router is not mandatory for every skill |

For example, a profile installer may bundle its owned statusline helper so setup
works after one install. That does not imply copying an official cloud Skill into
a local operations router. The router must resolve/install its declared dependency
and verify the handoff instead of leaving the user to assemble prerequisites.

Stop dependency work once the authorized representative task works with the intended
identity and update owner. Missing dependencies are explicit failures, not permission
to guess APIs, use another account or reimplement a sender.

After research completes, present findings via **AskUserQuestion**:

```
Research complete for "[skill-name]". Here's what I found:

[1-2 sentence summary of what exists publicly]

RECOMMENDATION: [ADOPT / EXTEND / BUILD] because [one-line reason]

Options:
A) Adopt [tool/MCP X] for infrastructure, build methodology layer on top (Recommended)
B) Extend [partial tool Y] — use what works, fill gaps in the skill
C) Build from scratch — nothing found matches well enough
D) Show me the detailed findings before I decide
```

When in doubt, bias toward adopting mature infrastructure for the plumbing layer and building custom logic for the methodology layer — that's where the value lives.

### Interview and Research

Proactively ask questions about edge cases, input/output formats, example files, success criteria, and dependencies. Wait to write test prompts until you've got this part ironed out.

Check available MCPs when useful for research (searching docs, finding similar skills, looking up best practices). Research inline by default. Use a subagent only for a distinct unresolved question, and never turn tool availability into automatic parallel fan-out. Come prepared with context to reduce burden on the user.

### Write the SKILL.md

When composing or reorganizing multiple workflows, apply the ownership decision
before filling directories. Keep the entry focused on routing, put cross-workflow
identity/authorization/completion in one reachable common contract, and keep each
workflow's local guide with its tools and cases. Keep vendor implementation outside
our bundle when its upstream owns it. Simple single-purpose skills can stay flat;
these are responsibility boundaries, not a mandatory folder template.

Before calling the structure ready, walk 1–2 representative changed tasks from the
entry to the selected guide, actual tool, working directory/dependency and final
business evidence. Reuse the selected tier's checks or fresh-context review; do not
launch a second audit merely for this step. A file tree, shorter SKILL.md or passing
links alone cannot prove correct routing. Stop when those tasks select the intended
owner, preserve prior exits and can reach verified outcomes; do not keep splitting
or merging for cosmetic uniformity.

Based on the user interview, fill in these components:

- **name**: Skill identifier
- **description**: the routing key — what the skill does and when to use it, nothing else. Every installed skill's description sits in every session's context, and they all share one listing budget: Claude Code cuts each entry at 1,536 characters and, when the listing overflows, drops the descriptions of the least-used skills entirely, leaving only their names. A long description does not just spend its own tokens; it pushes other skills out of view. 1024 characters is the spec's validity ceiling, not a target.

  Shape: `<what it does, one clause>. Use when <2–4 concrete situations or phrasings users actually type>. Not for <nearest sibling case> (use <sibling>).` Put the key use case first and write in third person. The first ~160 characters must stand on their own — what the skill does and its main trigger: Codex shows each description cut to a short prefix when many skills are installed (measured: ~165 characters with 260 skills), so later "Use when" items and "Not for" redirects reach only Claude Code.

  - **Length**: aim for 200–300 characters. Up to about 420 is fine when the skill must route between siblings or is itself a router; `quick_validate` warns above 420. When keeping every distinct job pushes past that, compress before accepting it: one phrasing per situation, a shorter what-it-does clause, no transport or implementation details ("over Tailscale", "via qmd"). Go over only if a distinct job would otherwise be lost, and say why in the PR.
  - **Hidden trigger moment**: if the moment to use the skill is not visible in the user's words (for example "before choosing any library"), open with one short `MUST be used before …` clause.
  - **Keep**: redirects to the nearest one or two sibling skills; a non-obvious secondary job, in one clause; one short "even when …" clause if it corrects a known misjudgment (e.g. "even when it looks like a one-line ffmpeg job"); two to four phrasings users really type, in their language (Chinese included).
  - **Move to the body**: operational rules ("CRITICAL: fetch media by path"), pitfalls, methodology, failure history, internal mechanisms, file or reference routing, version notes.
  - **Rewriting an existing description**: run the existing-skill regression gate ([Step 4](../SKILL.md#step-4-edit-the-skill): `compare` against a Git-ref baseline, then `classify`, then `verify`). It lists every old description clause that no longer appears verbatim as a `description_clause` candidate. Split a clause that bundles several situations into single items, then give each item a home by its type:
    - **When to use** (a situation or phrasing that should make the skill fire, including timing such as "runs before committing", whose home is the hidden-trigger-moment clause): the home must be in the new description — the body is read only after the skill fires, so a body line cannot bring the trigger back. If the new description no longer covers it, decide: a variant or sub-case of a situation the new description still names, or another phrasing of one, is secondary and may be dropped; a distinct job the user would ask for on its own, which nothing left in the description leads to, goes back in. List every drop in the PR and changelog so a real miss can restore it. Record a drop as `removed_by_explicit_user_request`, citing the owner's request to rewrite under this rule as `user_approval`; without such a request, ask.
    - **Not for** (an exclusion or sibling redirect): the new description or the body. Never dropped.
    - **Operational rule, pitfall or routing**: the body, on a SKILL.md line about that same situation. A reference reached only through a row about a different situation is not a home. Never dropped.

    Same meaning in shorter or broader words is a home ("architecture" in a list of decision types covers "architecture decision"). A shared word with a different meaning is not ("inside a bug fix" does not preserve "Not for bug fixes"). Nor is a placeholder for words users literally type — people's names, product names, error strings: "its named contacts" does not preserve the names themselves.
  - **Drop**: exhaustive keyword lists, synonyms the model can infer, and "use it even when none of these words appear".
  - **Write sibling skills together**: descriptions in one family must agree on which skill owns what.
  - **Tune from real use, not up front**: when a real session shows the skill missing or misfiring, fix the description from that prompt. Do not run trigger-rate optimization on a fresh skill; you do not yet know how people will phrase it.
  - **User-started only**: if only the user should start the skill, set `disable-model-invocation: true`; its description then costs nothing in the listing.
- **compatibility**: Required tools, dependencies (optional, rarely needed)
- **the rest of the skill :)**

### Skill Writing Guide

#### Anatomy of a Skill

```
skill-name/
├── SKILL.md (required)
│   ├── YAML frontmatter (name, description required)
│   └── Markdown instructions
└── Bundled Resources (optional)
    ├── scripts/    - Executable code for deterministic/repetitive tasks
    ├── references/ - Docs loaded into context as needed
    └── assets/     - Files used in output (templates, icons, fonts)
```

#### YAML Frontmatter Reference

All frontmatter fields except `description` are optional. Configure skill behavior using these fields between `---` markers:

```yaml
---
name: my-skill
description: What this skill does and when to use it. Use when...
context: fork
agent: general-purpose
argument-hint: "[topic]"
---
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | No | Display name for the skill. If omitted, uses the directory name. Lowercase letters, numbers, and hyphens only (max 64 characters). |
| `description` | Recommended | What the skill does and when to use it. Claude uses this to decide when to apply the skill. If omitted, uses the first paragraph of markdown content. |
| `context` | No | **Set to `fork` to run in a forked subagent context.** See "Inline vs Fork: Critical Decision" below — choosing wrong breaks your skill. |
| `agent` | No | Which subagent type to use when `context: fork` is set. Options: `Explore`, `Plan`, `general-purpose`, or custom agents from `.claude/agents/`. Default: `general-purpose`. |
| `disable-model-invocation` | No | Set to `true` to prevent Claude from automatically loading this skill. Use for workflows you want to trigger manually with `/name`. Default: `false`. |
| `user-invocable` | No | Set to `false` to hide from the `/` menu. Use for background knowledge users shouldn't invoke directly. Default: `true`. |
| `allowed-tools` | No | Pre-approved tools list. **Recommendation: Do NOT set this field.** Omitting it gives the skill full tool access governed by the user's permission settings. Setting it restricts the skill's capabilities unnecessarily. |
| `model` | No | Model to use when this skill is active. |
| `argument-hint` | No | Hint shown during autocomplete to indicate expected arguments. Example: `[issue-number]` or `[filename] [format]`. |
| `hooks` | No | Hooks scoped to this skill's lifecycle. Example: `hooks: { pre-invoke: [{ command: "echo Starting" }] }`. See Claude Code Hooks documentation. |

**Special placeholder:** `$ARGUMENTS` in skill content is replaced with text the user provides after the skill name. For example, `/deep-research quantum computing` replaces `$ARGUMENTS` with `quantum computing`.

##### Inline vs Fork: Critical Decision

**This is the most important architectural decision when designing a skill.** Choosing wrong will silently break your skill's core capabilities.

**Check the actual host constraint before choosing inline or fork.** Inspect whether the forked context can delegate agents, invoke Skills and use the required tools. Some hosts restrict these capabilities; others expose nested delegation. When the required operation is unavailable in a fork, keep the caller inline. When the host supports it, a fork may orchestrate within the existing authorization and budget. Tool availability does not authorize additional roles.

**Decision guide:**

| Your skill needs to... | Use | Why |
|------------------------|-----|-----|
| Orchestrate parallel agents | **Inline** when the fork lacks delegation; otherwise select by actual host and isolation needs | Preserve the required delegation tools |
| Call other skills | **Inline** when the fork lacks Skill invocation; otherwise use the supported context | Preserve the required invocation interface |
| Run Bash commands for external CLIs | Choose a context with the required tool access | Verify the actual host permissions |
| Perform a single focused task (research, analysis) | **Fork** (`context: fork`) | Isolated context, clean execution |
| Provide reference knowledge (coding conventions) | **Inline** (no `context`) | Guidelines enrich main conversation |
| Be callable BY other skills | **Fork** for supported isolated delegation; inline invocation when supported and appropriate | Verify the caller/callee interface |

**Fork skills that require a target MUST hard-stop when the caller gives none.** A
`context: fork` skill runs non-interactively — it **cannot ask the user** for a
missing input, and a `general-purpose` fork handed a skill body with no task will
**fabricate a plausible one** rather than stop (2026-09-20 incident: a no-arg
`competitors-analysis` fork invented an "A2A market" task 14s in and ran it for
1h23m). So if your fork skill declares a required target via `argument-hint` /
`$ARGUMENTS`, its body MUST open with a gate: *"if the caller did not provide this
target for THIS invocation, STOP and report the missing input — do not invent one,
do not infer one from disk state, do not fall through to a default mode."* The
gate must test **task provenance** (did the caller supply it), not argument-string
presence — a hardcoded default or a self-generated value satisfies the latter and
defeats the purpose. An "ask if missing" line is NOT a substitute: it is inert in
fork context.

**Example: Orchestrator skill (inline when forks lack its required tools):**
```yaml
---
name: product-analysis
description: Multi-path parallel product analysis with cross-model synthesis
---

# Orchestrate agents inline when forked contexts lack the required tools
1. Auto-detect available tools (which codex, etc.)
2. Launch 3-5 Task agents in parallel (Explore subagents)
3. Optionally invoke /competitors-analysis via Skill tool
4. Synthesize all results
```

**Example: Specialist skill (fork is correct):**
```yaml
---
name: deep-research
description: Research a topic thoroughly using multiple sources
context: fork
agent: Explore
---

Research $ARGUMENTS thoroughly:
1. Find relevant files using Glob and Grep
2. Read and analyze the code
3. Summarize findings with specific file references
```

**Example: Reference skill (inline, no task):**
```yaml
---
name: api-conventions
description: API design patterns for this codebase
---

When writing API endpoints:
- Use RESTful naming conventions
- Return consistent error formats
```

##### Composable Skill Design (Orthogonality)

Skills should be **orthogonal**: each skill handles one concern, and they combine through composition.

**Pattern: Orchestrator (inline) calls Specialist (fork)**
```
product-analysis (inline, orchestrator)
  ├─ Task agents for parallel exploration
  ├─ Skill('competitors-analysis', 'X') → fork subagent
  └─ Synthesizes all results

competitors-analysis (fork, specialist)
  └─ Single focused task: analyze one competitor codebase
```

**Rules for composability:**
1. Keep the **caller** inline when its host does not expose the required delegation/Skill tools in a fork; otherwise use the supported context
2. The **callee** should use `context: fork` to run in isolated subagent context
3. Each skill has a single responsibility — don't mix orchestration with execution
4. Share methodology via references (e.g., checklists, templates), not by duplicating code

##### Pipeline Handoff (Sequential Skill Chaining)

Beyond orchestrator/specialist composition, skills often form **sequential pipelines** where one skill's output is the next skill's input. Each skill should proactively suggest the logical next step after completing its work.

**Pattern: "Next Step" section at the end of SKILL.md**

```markdown
## Next Step: [Action Description]

After [this skill completes], suggest the natural next skill:

\```
[Summary of what was just accomplished].

Options:
A) [Next skill] — [one-line reason] (Recommended)
B) [Alternative skill] — [when this is better]
C) No thanks — [the current output is sufficient]
\```
```

**Real-world pipeline examples:**

```
youtube-downloader → asr-transcribe-to-text → transcript-fixer → meeting-minutes-taker → pdf-creator
deep-research → fact-checker → ppt-creator
doc-to-markdown → docs-cleaner
read-claude-code-history → continue-claude-code-work
```

**Rules for pipeline handoff:**
1. Every handoff is **opt-in** via AskUserQuestion — never auto-invoke the next skill without asking
2. Suggest only when the output naturally feeds into another skill — don't force connections
3. Include a "No thanks" option — the user may not need the full pipeline
4. The suggestion should explain **why** the next step helps (e.g., "ASR output typically contains recognition errors")
5. Keep it to 1-2 recommendations max — too many choices cause decision fatigue

**When to add a handoff:** Ask "does this skill's output commonly become another skill's input?" If yes, add a "Next Step" section. If the connection is rare or forced, don't add one.

**Anti-pattern:** Chaining skills that don't share a natural data flow. `pdf-creator → youtube-downloader` makes no sense. The pipeline must follow the user's actual workflow.

##### Auto-Detection Over Manual Flags

**Never add manual flags for capabilities that can be auto-detected.** Instead of requiring users to pass `--with-codex` or `--verbose`, detect capabilities at runtime:

```
# Good: Auto-detect and inform
Step 0: Check available tools
  - `which codex` → If found, inform user of availability; use cross-model analysis only within the authorized evidence plan
  - `ls package.json` → If found, tailor prompts for Node.js project
  - `which docker` → If found, enable container-based execution

# Bad: Manual flags
argument-hint: [scope] [--with-codex] [--docker] [--verbose]
```

**Principle:** Capabilities auto-detect, user decides scope. A skill should discover what it CAN do and act accordingly, not require users to remember what tools are installed.

##### Invocation Control

Interpret the table as the described Claude-style invocation policy. Verify the actual host interfaces before relying on subagent invocation or nested delegation; it is not a universal capability restriction.

| Frontmatter | You can invoke | Claude can invoke | Subagents can use |
|-------------|----------------|-------------------|-------------------|
| (default) | Yes | Yes | No (runs inline) |
| `context: fork` | Yes | Yes | Yes |
| `disable-model-invocation: true` | Yes | No | No |
| `context: fork` + `disable-model-invocation: true` | Yes | No | Yes (when explicitly delegated) |

#### Progressive Disclosure

Skills use a three-level loading system:
1. **Metadata** (name + description) - Always in context (~100 words)
2. **SKILL.md body** - In context whenever skill triggers
3. **Bundled resources** - As needed (unlimited, scripts can execute without loading)

**Key patterns:**
- SKILL.md length should be driven by **information density**, not a line count target. A 600-line skill with no filler is better than a 200-line skill that omits critical knowledge and forces the model to guess. If the skill is getting long, ask: "Is every section earning its keep?" If yes, keep it. If sections are padded or explain things Claude already knows, trim those — not the useful content. When a skill genuinely covers many domains, split into references by domain rather than artificially cramming everything into a short main file.
- For an existing skill, progressive disclosure is a relocation strategy, not a deletion heuristic. The old runtime contract must remain reachable from SKILL.md in the packaged bundle; a trigger query, test assertion, changelog entry, or reviewer memory is not a runtime replacement.
- Reference files clearly from SKILL.md with guidance on when to read them. **`quick_validate` now reports the ones nothing links** (transitively — a reference cited from another reachable reference counts). This rule sat here as prose for a long time while nothing enforced it, and a skill shipped with an unreferenced reference after passing validation, a security scan, a verbatim run of every documented command, and CI: none of them ask whether a bundled file is reachable, and the file existing is exactly what makes the gap invisible. The finding is a note rather than a failure because some unreferenced files are deliberate — an author-facing template is not runtime guidance — and a gate that fails on those gets bypassed, which switches it off for the skills it was built for.
- For large reference files (>300 lines), include a table of contents

**Domain organization**: When a skill supports multiple domains/frameworks, organize by variant:
```
cloud-deploy/
├── SKILL.md (workflow + selection)
└── references/
    ├── aws.md
    ├── gcp.md
    └── azure.md
```
Claude reads only the relevant reference file.

#### Principle of Lack of Surprise

This goes without saying, but skills must not contain malware, exploit code, or any content that could compromise system security. A skill's contents should not surprise the user in their intent if described. Don't go along with requests to create misleading skills or skills designed to facilitate unauthorized access, data exfiltration, or other malicious activities. Things like a "roleplay as an XYZ" are OK though.

#### Writing Patterns

Prefer using the imperative form in instructions.

**Defining output formats** - You can do it like this:
```markdown
## Report structure
ALWAYS use this exact template:
# [Title]
## Executive summary
## Key findings
## Recommendations
```

**Examples pattern** - It's useful to include examples. You can format them like this (but if "Input" and "Output" are in the examples you might want to deviate a little):
```markdown
## Commit message format
**Example 1:**
Input: Added user authentication with JWT tokens
Output: feat(auth): implement JWT-based authentication
```

**Usability patterns worth building into a skill** - These four structural elements repeatedly turned a "works but confusing" skill into one users could actually drive — they were the concrete enhancements that made a heavily-used skill usable, so reach for them when a skill has modes, runs commands, or can be re-run:
- **Entry decision-tree**: if the skill has multiple modes, open with a tiny "user said X → use mode Y" map so the model routes correctly instead of guessing.
- **Expected-output block after each command**: show "what you should see" right after a command, so the model (and the user) can tell real success from silent failure.
- **Troubleshooting section**: enumerate the known failure modes and their fixes — the single most valuable section for a skill others will run on machines you can't see.
- **Step-0 idempotency guard**: if re-running could redo finished work, open with a cheap "is this already done?" check before doing anything expensive.

### Writing Style

Try to explain to the model why things are important in lieu of heavy-handed musty MUSTs. Use theory of mind and try to make the skill general and not super-narrow to specific examples. Start by writing a draft and then look at it with fresh eyes and improve it.

### Dates and Version References

**Keep factual dates — they tell readers when information was verified.** A skill about Suno v5.5 should say "Suno v5.5 (March 2026)" because without the date, future readers can't judge if the information is still current. Removing dates makes things worse, not better.

What to avoid is **conditional logic based on dates** ("if before August 2025, use the old API") — that becomes wrong the moment the date passes and nobody updates it.

Rules:
- **Release dates, "last verified" dates**: Keep them. They're reference points, not expiration dates
- **Pricing, rankings, legal status**: Include but mark as volatile ("~$0.035/gen as of last check") so readers know to re-verify
- **"Before X date do Y, after X date do Z"**: Don't write this. Pick the current method and optionally document the old one in a collapsed/deprecated section

#### Bundled Resources

##### Scripts (`scripts/`)

Executable code (Python/Bash/etc.) for tasks that require deterministic reliability or are repeatedly rewritten.

- **When to include**: When the same code is being rewritten repeatedly or deterministic reliability is needed
- **Example**: `scripts/rotate_pdf.py` for PDF rotation tasks
- **Benefits**: Token efficient, deterministic, may be executed without loading into context
- **Note**: Scripts may still need to be read by Claude for patching or environment-specific adjustments
- **User-mutable data lives outside the bundle**: if a script accumulates user data (correction dictionaries, learned preferences, caches), store it under a stable home-relative directory (e.g. `~/.<skill-name>/`) with its own backup — never inside the skill directory. Skill installs are wiped and re-created on every update and suite migration; a home-relative store survives them untouched. This is how a dictionary-accumulating skill survived a full suite migration with zero user data loss

##### References (`references/`)

Documentation and reference material intended to be loaded as needed into context to inform Claude's process and thinking.

- **When to include**: For documentation that Claude should reference while working
- **Examples**: `references/finance.md` for financial schemas, `references/mnda.md` for company NDA template
- **Use cases**: Database schemas, API documentation, domain knowledge, company policies, detailed workflow guides
- **Benefits**: Keeps SKILL.md lean, loaded only when Claude determines it's needed
- **Best practice**: If files are large (>10k words), include grep search patterns in SKILL.md
- **Avoid duplication**: Information should live in either SKILL.md or references files, not both

##### Assets (`assets/`)

Files not intended to be loaded into context, but rather used within the output Claude produces.

- **When to include**: When the skill needs files that will be used in the final output
- **Examples**: `assets/logo.png` for brand assets, `assets/slides.pptx` for PowerPoint templates
- **Use cases**: Templates, images, icons, boilerplate code, fonts, sample documents
- **Component shelf**: for artifact-generating skills, a `components` subfolder under `assets/` holds user-approved verbatim-embed fragments with frozen behavior contracts and a registry reference — see the [Component-shelf check](existing-skill-migration.md#validation-and-escalation-probes)

##### Privacy and Path References

**Decide the destination before applying any of this.** Everything below describes what
breaks when a skill ships to strangers. For a skill that lives in the author's own private
repo, the same "violations" are usually why it works — a real absolute path is what makes
the script runnable, a real account in a template is what saves the next run from re-filling
it. `quick_validate` auto-detects this (it asks `gh` whether the containing repo is private)
and downgrades portability/identifier findings to notes there; `--audience=public` forces the
strict pass when a private skill is being prepared for release.

**In a private skill, these findings are the owner's call, not yours.** Do not placeholder a
real path, rewrite a hardcoded credential, or "sanitize" an example without asking — you will
break a working tool to satisfy a rule written for a destination it was never going to. If
you think something should change, say what you found and let the owner decide. (The design
precedent is npm's `"private": true`: a declared destination that changes what the tooling
enforces, added because people kept publishing things by accident.)

**CRITICAL for skills intended for public distribution** — these must not contain
user-specific or company-specific information:

- **Forbidden**: Absolute paths to user directories (for example, user home directories)
- **Forbidden**: Personal usernames, company names, product names
- **Forbidden**: Hardcoded skill installation paths like `~/.claude/skills/`
- **Allowed**: Relative paths within the skill bundle (`scripts/example.py`, `references/guide.md`)
- **Allowed**: Standard placeholders (`<workspace>/project`, `<user>`, `<organization>`)
- **Carve-outs** (a validator implementing the Forbidden list literally would flag this very skill — misfiring on healthy input is worse than missing): the publisher's own name/brand when a supersede tiebreaker or attribution *requires* naming it; install paths like `~/.claude/skills/` when the passage is *about* those paths (teaching material, not a hardcoded dependency)

**Cross-skill references**: a bare relative path always means "inside this skill's own bundle" — validators and readers both treat it that way, so a bare path pointing at another skill's file fails validation and misleads readers. When pointing at another skill, name the owner in prose ("marketplace-dev's cache-and-source-patterns reference") and invoke skills by their namespaced name (`/suite-name:skill-name`, not a bare `/skill-name`). Bare cross-references break silently when skills move between suites — one suite migration left 21 broken cross-references across two cleanup passes because of this.

##### Versioning

**CRITICAL**: Skills should NOT contain version history or version numbers in SKILL.md:

- **Forbidden**: Version sections (`## Version`, `## Changelog`) in SKILL.md
- **Correct location**: Skill versions are tracked in marketplace.json under `plugins[].version`
- **Rationale**: Marketplace infrastructure manages versioning; SKILL.md should be timeless content

#### Reference File Naming

Filenames must be self-explanatory without reading contents.

**Pattern**: `<content-type>_<specificity>.md`

**Examples**:
- Bad: `commands.md`, `cli_usage.md`, `reference.md`
- Good: `script_parameters.md`, `api_endpoints.md`, `database_schema.md`

**Test**: Can someone understand the file's contents from the name alone?

**Starting a new reference**: copy `references/reference_template.md` — it carries the
frontmatter shape (`name`, and a `description` that says what the file covers *and when
to read it*, with trigger keywords) plus the section skeleton. Filling a template beats
inventing a layout each time, and the description field is what makes the file findable
rather than merely present.

Two carve-outs: hyphenated names are as good as underscored ones (the separator was never the point — self-explanation is); and files inside a named workflow directory (`workflows/<name>/workflow.md`, `patterns.md`) are directory-qualified — the directory supplies the specificity, and renaming them would break the parallel structure across workflows.

### Skill Creation Best Practice

Anthropic has written skill authoring best practices — retrieve it before you create or update any skills: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices.md

#### Development Methodology Reference

Also read [references/skill-development-methodology.md](skill-development-methodology.md) before starting — it covers the full development process with prior art research, counter review, and real failure case studies. The two references are complementary: the Anthropic doc covers principles, the methodology covers process.

### Step 0: Prerequisites Check

For `audit_skill_regression`, `release_readiness`, `source_contract` and
`materialize`, use the [fixed command entry](fixed-command-entry.md)
when calling from another working directory. Supply absolute artifact paths;
retain each owning tool's subcommands, flags and direct invocation.

Before starting any skill work, auto-detect all dependencies and proactively install anything missing. Discovering a missing tool mid-workflow (e.g., gitleaks at packaging time, PyYAML at validation) wastes time and breaks flow.

Run the quick check from [references/prerequisites.md](prerequisites.md), auto-install what you can, and present the user a summary checklist. Only proceed when all blocking dependencies are satisfied.

Key blockers: Python 3, uv, the locked skill-creator runtime (validation/packaging), and gitleaks (security scan). The claude CLI is blocking only when a separately authorized evidence plan actually runs agent evals. Run bundled Python tools from the skill-creator root with `uv run --frozen`, for example `uv run --frozen python -m scripts.quick_validate <skill-path>`. Bare `python3` depends on ambient site packages and can miss the locked dependencies.

**uv isolation contract:** Treat this directory as one normal uv project. Keep its committed `pyproject.toml` and `uv.lock`, let uv materialize one project-local `.venv` from the shared global cache, and run bundled tools with `uv run --frozen`. Do not add per-call `--with` overlays for dependencies already locked here, do not set one global `UV_PROJECT_ENVIRONMENT` across projects, and do not create a project-specific `UV_CACHE_DIR`. Never use `--no-cache`, `uv cache clean`, or `uv cache prune` as part of ordinary Skill execution; cache maintenance is a separately authorized disk operation.

### Step 1: Understanding the Skill with Concrete Examples

Skip this step only when the skill's usage patterns are already clearly understood.

To create an effective skill, clearly understand concrete examples of how the skill will be used. This understanding can come from either direct user examples or generated examples that are validated with user feedback.

For example, when building an image-editor skill, relevant questions include:

- "What functionality should the image-editor skill support? Editing, rotating, anything else?"
- "Can you give some examples of how this skill would be used?"
- "What would a user say that should trigger this skill?"

To avoid overwhelming users, avoid asking too many questions in a single message.

### Step 2: Planning the Reusable Skill Contents

Analyze each example by:

1. Considering how to execute on the example from scratch
2. Determining the appropriate level of freedom for Claude
3. Identifying what scripts, references, and assets would be helpful when executing these workflows repeatedly
4. Deciding how a user will inspect the result: a concise reply, an existing domain artifact or viewer, or a conditional handoff to `report-with-html` when a visual report would clarify evidence, comparisons, or decisions. For recurring customer reports, plan a first real report and a **post-review template decision**; the approved form lives in user-local data outside the Skill package, never in its `assets/` or an update-owned cache.

**Match specificity to task risk:**
- **High freedom (text instructions)**: Multiple valid approaches exist
- **Medium freedom (pseudocode with parameters)**: Preferred patterns exist with acceptable variation
- **Low freedom (exact scripts)**: Operations are fragile, consistency critical

### Step 3: Initializing the Skill

Skip this step if the skill already exists.

When creating a new skill from scratch, run [scripts/init_skill.py](../scripts/init_skill.py)
from the locked skill-creator project:

```bash
uv run --frozen python -m scripts.init_skill <skill-name> \
  --path <source-parent> --repo <source-repo> --scope marketplace
```

The script creates a template skill directory with proper frontmatter, resource directories, and example files.

### Step 4: Edit the Skill

Before writing, retrieve Anthropic's best-practices doc (linked in "Skill Creation Best Practice" above) and the methodology reference — do this even when you feel you already know them: the doc updates, training-data versions go stale, and "I basically know it" is exactly the state in which editors skip it and miss the newest guidance.

When this edit changes code, configuration or an operating workflow, use
[documentation and example alignment](knowledge-skill-grounding.md#3-首个候选冻结前文档与示例对齐)
before the first candidate is frozen for review. Keep the affected-file inventory,
document dispositions and authorities in the existing plan; finish their updates
with the implementation rather than scheduling a documentation release afterward.

For a valid result that still emits diagnostics, use that reference's
[warning interpretation](knowledge-skill-grounding.md#interpret-validation-warnings)
and the validator's JSON result; validity and a warning's disposition are separate.

When editing, remember that the skill is being created for another instance of Claude to use. Focus on information that would be beneficial and non-obvious to Claude.

For existing-Skill edits, enter [existing-skill-migration.md](existing-skill-migration.md) before the first edit. Select the evidence tier and any separately authorized fan-out with [change-verification.md](change-verification.md) before specialized exits. Source-location checks remain in [the shared entry](../SKILL.md#critical-edit-skills-at-source-location).

For historical evidence behind these procedures, inspect [developer-casebook.md](developer-casebook.md) only when investigating that failure.

## Ground technical and methodological claims

Read before a technical claim enters a Skill, before relying on a landed capability, or before authoring/optimizing methodology. Use current verified facts and the domain’s established methods; return to the planned draft once the load-bearing assertions are grounded or explicitly bounded.

### Technical assertions and landed-claim verification

1. **Verify before you write.** Every technical assertion that enters the skill (endpoint, parameter, command, version, behavior) must trace to something you executed and observed — in this session or an explicitly approved mined one. Can't verify it right now? Either go verify it, or mark it explicitly ("unverified — from memory"). A skill multiplies whatever it contains: verified knowledge compounds, and so do confidently-stated errors. For knowledge skills (content is mostly facts about an external system — API endpoints, parameters, fields, platform behavior), read [references/knowledge-skill-grounding.md](knowledge-skill-grounding.md) for the operational version: the authority ladder (observed behavior > machine-readable contract > exercised production code > official docs > memory), evidence-scope annotation and live/replay/synthetic evidence tiers, pre-ship doc-example smoke runs, and the audience/Windows portability checklist. A source-grounding audit once found multiple confident contract claims that contradicted evidence already available to the author (methodology Case 9). **A "landed" claim is verified against the target ref, not the commit message.** When a commit message, changelog entry, or skill section asserts a capability was implemented/fixed/landed, the assertion is not evidence — before reporting it done, and again before any later session builds on it, grep the *target ref itself* (`git show <ref>:<path>`) for that capability's signature strings and read the key lines back. Real incident (2026-09-17): a commit message claimed a voice-input chain had been rewritten to a single-click model, while the pushed ref still carried the hold-to-talk model — only a post-compaction grep of the actual ref caught it. The commit message, the changelog entry, and the author's summary are one source; counting them as three is exactly how such a claim survives review. Criterion: every capability named in the claim has its implementation signature present in the target ref, read from the ref.
### Capability-negative claims

2. **Treat "impossible / not supported" as a hypothesis, not a conclusion.** When a capability seems blocked (an API error wall, a tool that won't connect, a format that won't open), exhaust the observation paths — the UI's own network traffic, an alternative channel, a different documented identifier — before writing "the platform doesn't support this" into a skill. Observed behavior outranks speculative request shapes.
### Domain methodology

3. **Stand on the field's shoulders — retrieve the domain's established best-practices into context BY DEFAULT, before authoring or optimizing a skill's methodology.** A skill's methodology is only as good as the knowledge in your context window, not the knowledge latent in your weights: pretraining is lossy, goes stale, and often is not even activated unless the canonical sources are actually pulled in. So the quality ceiling of what you write is `your training data + the user's input` — *unless* you deliberately retrieve the subject domain's real prior art. Do it: WebSearch the field's canonical theory / standards / methods, and read any bundled or installed skill in that domain, then fold the load-bearing principles into the skill with attribution. **This is a different axis from "Prior Art Research" below** — that finds *tools/infrastructure* to reuse; this grounds the *quality of the methodology itself* in the discipline's accumulated science. Make it the **default action, not something you wait to be asked for**: briefly tell the user which field you're pulling from and let them say "skip," but never ship a methodology capped by your memory plus their prompt when 40 years of the field's public work is one search away. Examples: a data-visualization skill must absorb Cleveland & McGill's graphical-perception ranking and Bertin's visual variables (position/length beat color beat text — measured, not aesthetic); a date/time skill must surface the mature libraries and their canonical pitfalls; a persuasion/negotiation skill must retrieve the established frameworks rather than reinvent them from memory. If the canonical knowledge lives only in your weights and never enters context, you are guessing where you could be citing.

## Select the authorized source workflow

Read only the matching workflow subsection when its source is proposed. Complete the ownership decision and [verification classification](change-verification.md#verification-depth-router-run-before-choosing-any-workflow) before any specialized exit. Preserve the declared substitute mechanics, compatible shared gates and return to ordinary editing/verification/delivery.

### Specialized Workflow: Wrapper Skills for Third-Party CLI Tools

Before committing to the generic skill-creation flow, check whether the session that led up to this point actually calls for the **wrapper skill** workflow instead. A wrapper skill is a companion that installs, configures, diagnoses, and repairs a pre-existing third-party CLI tool or skill package — code that someone else wrote and that the user has just spent a session getting to work on their machine.

Signals this applies (any two together are enough):

- The user has been installing a tool in the current conversation — downloading a `.zip`, running `npx` / `pip install` / `brew install`, dealing with an official installer.
- The session has produced real, concrete error messages and the user and Claude have worked out concrete fixes for them (edited files, added flags, bypassed aliases).
- The user says something like "wrap this up as a skill", "save this as a wrapper skill", "so other people don't have to go through this again", "把这次 session 做成一个 skill".
- The user explicitly mentions a third-party tool by name and wants other agents or other people to be able to use it without the learning curve they just paid.

Signals it does **not** apply (use the generic workflow above instead):

- The user wants a skill for something they're going to write from scratch.
- The session was smooth — no real friction to capture.
- The skill would wrap a service the user owns or controls (it's their code; edit the source instead of wrapping it).
- The "tool" is actually a methodology or workflow that doesn't involve installing any binary or package.

When the wrapper skill workflow applies, preserve the verification tier selected above. Creating a wrapper is creating a new skill, so it is Tier 3. **Do not** continue reading the generic authoring sections; jump to [`workflows/wrapper-skill/workflow.md`](../workflows/wrapper-skill/workflow.md) and follow that workflow end-to-end, including its verification protocol. It is a **retrospective distillation** workflow — its job is to mine the current conversation for the install flow, the bugs that were fixed, and the design decisions that were made, and to turn that mining output into a complete, self-contained wrapper skill that another user can install and benefit from without reliving the debugging session.

The wrapper skill workflow has its own architecture contract, code templates, and Tier 3 verification protocol — it replaces incompatible generic test-case mechanics because its output is a user's install state rather than a file that can be easily asserted on; it does not downgrade the work. Run the compatible generic steps selected by the evidence plan; generic paired-eval steps still require the heavy-eval authorization gate. Record which mechanics the specialized protocol replaced. The canonical reference implementation is the `ima-copilot` skill (at the root of the daymade/claude-code-skills repository — a bare relative link here already broke once when this skill moved into a suite, exactly as the cross-skill-reference rule below warns), a wrapper around the Tencent IMA skill distilled from a real session using this exact workflow.

### Specialized Workflow: Enrich a Skill from Conversation History

Before committing to the generic skill-creation flow, check whether the session is actually asking to **distill past conversations into a skill**. This is useful when the user has been debugging, designing, or exploring a topic over multiple Claude Code / Codex sessions and wants to turn the accumulated know-how into reusable `references/`.

**Explicit source intent is required.** A long live conversation, a recently completed debugging task, or `use skill-creator to optimize <skill>` is not consent to open local history and is not a reason to enter this workflow. Use the live conversation directly for a normal update. Enter conversation-mining only when the user explicitly asks to mine/distill earlier local conversations or identifies particular prior sessions as source material.

Signals this applies (all must hold):

- The user explicitly names local/past conversation history as an input, such as "mine my chat history", "enrich this skill from earlier sessions", or "把以前的对话沉淀到 skill 里".
- The source sessions and time/scope boundaries are known or confirmed.
- The intended output is reusable knowledge or code assets that are not already expressible from the live conversation and current skill bundle.

Signals it does **not** apply (use the generic workflow above instead):

- The user is creating a brand-new skill from a single prompt or idea.
- The user asks to optimize an existing skill without asking to read prior local history.
- The relevant corrections and evidence are already present in the live conversation.
- The user wants a wrapper around a third-party CLI tool they just installed (use the wrapper-skill workflow above).
- There is no local conversation history to mine and no transcript exports to process.
- The mined content is a one-time personal note with no reusable decision or
  helper. Keep it out of the Skill; when the target project's contract authorizes
  recording it, use that project's existing canonical document. Follow the user's
  storage contract rather than creating a memory file.
- The source material is a batch of finished artifacts the user has endorsed, rather than dialogue — use the artifact-corpus-distillation workflow below.

When the conversation-mining workflow applies, preserve the verification tier selected above. A new mined skill is Tier 3; enriching an existing skill stays at the selected tier only if it satisfies that tier's capability boundary. **Do not** continue reading the generic authoring sections; jump to [`workflows/conversation-mining/workflow.md`](../workflows/conversation-mining/workflow.md) and follow its applicable retrieval or selected-corpus route, including verification. It retrieves bounded approved histories through their owners, redacts and partitions selected content when mining a corpus, runs only the justified pass(es), and promotes reviewed changes after validation. For improvement across task types, use that workflow's matched-case route before choosing maintenance points.

The conversation-mining workflow has its own architecture contract, agent prompts, templates, and verification protocol. That protocol implements the selected tier's specialized mechanics; run the compatible generic steps selected by the evidence plan, keep heavy generic steps behind their authorization gate, and record any substitution. It is the canonical way to turn explicitly approved conversation history into a skill's reusable knowledge base.

### Specialized Workflow: Distill User Preferences from an Approved-Artifact Corpus

Before committing to the generic flow, check whether the session is asking to **extract the user's real preferences from a batch of finished artifacts they have endorsed** — approved HTML report pages, generated documents, designs. This is the third distillation source, distinct from the two above: the material is **products, not conversations**, and the output is **taste made executable** (explicit principles, quantified parameters, vocabulary), not knowledge or install fixes.

Signals this applies (any one is enough):

- The user lists finished artifacts and says "这些都是我认可的样例" / "你来学到底什么是我想要的" / "extract my preferences from these approved examples".
- A taste-calibration skill (report generator, doc styler, deck builder) has an approved-sample corpus that keeps growing, and the user asks to make the skill *learn* from it rather than just index it.
- The user complains that a previous update "只加了示例" — only cataloged samples without changing skill behavior.

Signals it does **not** apply: the source material is dialogue/corrections rather than endorsed products (use conversation-mining); the samples are not personally approved by the user (approval is the admission gate — ask first).

When it applies, preserve the verification tier selected above, then jump to [`workflows/artifact-corpus-distillation/workflow.md`](../workflows/artifact-corpus-distillation/workflow.md) and follow its verification protocol. A new corpus-derived skill is Tier 3; adding a materially new decision capability to an existing skill is also Tier 3. The specialized protocol implements the selected tier's corpus mechanics and does not downgrade them; run the compatible generic steps selected by the evidence plan, keep heavy generic steps behind their authorization gate, and record any substitution. Its core discipline, which also applies any time you add material to an existing skill: **cataloging ≠ distillation** — registering a sample in a corpus table changes nothing about the skill's next run; ask of every addition "*does this change a decision rule?*", and do not declare a distillation session done while the answer is no for everything written (methodology Case 15). The workflow's spine: script-extracted quantitative comparison across ALL artifacts (≥3-artifact threshold per pattern, checked exception lists per claimed constant) → layered induction with evidence anchors → write to the decision-rule layer (separating invariants from register-dependent variables) → independent completeness audit (standing discipline #5) → regression audit.

Resolve numbered standing-discipline citations using [their named owners](change-verification.md#shared-discipline-names); the owning contract supplies the conditions and stopping rule.
