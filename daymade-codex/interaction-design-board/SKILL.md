---
name: interaction-design-board
description: >-
  Generate several genuinely different, runnable HTML interaction prototypes for
  one product surface, combine them in an interactive Design Board, collect
  structured selection/remix feedback, and only then hand the approved behavior
  to production implementation. Use when a user asks for multiple clickable UI
  versions, interaction alternatives, progressive-disclosure options, a Design
  Board, HTML prototypes, test-time scaling for product design, or says the visual
  styling is acceptable but the hierarchy, workflow, layout, or interaction still
  feels unprofessional. Prefer this over static image exploration when the decision
  depends on what happens after clicking, expanding, selecting, filtering, or moving
  through states.
---

# Interaction Design Board

Turn interaction uncertainty into inspectable evidence. Keep the product's real
facts and design language fixed; vary the interaction architecture enough that the
user can experience the trade-offs before production code changes.

## Route The Request

- Use this skill when the choice depends on behavior, state, workflow, hierarchy,
  or progressive disclosure.
- Use `design-style-picker` for static visual-style calibration and image matrices.
- Use gstack's `design-consultation` for a new product-wide design system and
  gstack's `design-shotgun` for static generated mockups.
- Return to this skill after a visual direction is chosen if the user still needs
  to compare clickable interaction structures.
- Do not use it for a settled one-line CSS adjustment or when the user already
  supplied an approved interaction specification and asked only for implementation.

## Non-Negotiable Outcome

Produce a decision, not a gallery:

1. Several runnable HTML candidates keep the same business facts, product scope,
   design tokens, and available actions.
2. Each candidate embodies a distinct interaction hypothesis rather than a skin.
3. The Design Board lets the user operate every candidate, record concrete
   feedback, select one, or request a named remix.
4. Production implementation does not start until the user approves the behavior.

Static screenshots are supporting evidence only. A screenshot cannot prove a
collapse state, keyboard path, selection model, or task handoff.

## Workflow

### 1. Freeze The Decision Contract

Before generating variants, write a compact contract in the session workspace:

- **User job:** the real task the operator is trying to complete.
- **Decision scope:** the one page, component, or bounded journey being compared.
- **Immutable facts:** real objects, labels, statuses, permissions, actions, and
  data semantics that every variant must preserve.
- **Existing language:** current tokens, components, navigation, density, and
  brand assets that must remain recognizable.
- **First-view invariant:** what must stay visible before any disclosure.
- **Interaction states:** the meaningful states the user must be able to exercise.
- **Stop condition:** approved variant or explicit remix brief; no product edit yet.

For an existing product, inspect its rendered page and implementation before
writing the contract. Do not replace unknown facts with plausible sample data. Mark
unknowns as unknown or omit them if they are not needed for the interaction choice.

Read `references/interaction-design-method.md` before proposing the candidate
architectures. It contains the hierarchy, progressive-disclosure, comparison, and
accessibility rules that decide whether a direction is legitimate.

### 2. Propose Different Interaction Architectures

Propose three candidates by default. Add candidates only when another independent
interaction hypothesis exists; do not inflate the board with minor variants.

For each candidate state:

- the hypothesis about how it helps the user's job;
- what it makes primary;
- what it defers or hides;
- the likely trade-off;
- the states and actions that must work in the prototype.

Hold the decision contract constant. Change navigation/selection/disclosure/action
ownership or information order—not colors, copy, and data all at once. Useful
families include command-first, queue-detail, object-led, comparison-led, and
ledger-first, but derive candidates from the current task rather than filling a
pattern quota.

### 3. Generate Isolated Runnable Candidates

Create one self-contained HTML file per candidate in a session workspace outside
the product source tree. Keep CSS and JavaScript inline; avoid runtime network
dependencies so every prototype survives inside the Board.

When independent worker contexts are available, assign one candidate to each
worker with the same frozen decision contract and only that candidate's hypothesis.
Do not let workers see one another's output. This isolation is the test-time-scaling
mechanism: it preserves distinct hypotheses instead of converging into siblings.
If workers are unavailable, generate serially but re-read the frozen contract—not
the previous candidate—before starting the next one.

Each candidate must implement the declared states. Decorative buttons that do
nothing are not interaction prototypes. Use honest local state; do not simulate a
backend response the product does not have.

### 4. Build And Open The Design Board

Create `board.json` using `references/board-contract.md`, then run:

```bash
SKILL_ROOT="<absolute directory containing this loaded SKILL.md>"
python3 "$SKILL_ROOT/scripts/build_board.py" \
  --manifest <session-dir>/board.json \
  --output <session-dir>/design-board.html
```

Expected output:

```text
BOARD_BUILT variants=<derived count> output=<absolute path>
```

The builder rejects byte-identical candidates, path traversal, missing declared
states, and static external styles, scripts, or media. The Board also injects a
network-denying Content Security Policy into every sandboxed candidate so dynamic
JavaScript cannot create an undeclared runtime dependency. Fix the candidate; do
not weaken either boundary to make the Board green.

If gstack's design executable is already installed, resolve its absolute path from
the active gstack Skill installation; do not assume `$D` exists in a new shell. Then
capture the exact Board URL printed by the server:

```bash
GSTACK_DESIGN="<resolved gstack design executable>"
SERVER_OUTPUT="$("$GSTACK_DESIGN" serve \
  --html <session-dir>/design-board.html --timeout 1800 2>&1)"
printf '%s\n' "$SERVER_OUTPUT"
BOARD_URL="$(printf '%s\n' "$SERVER_OUTPUT" | sed -n 's/^BOARD_URL: //p' | tail -1)"
test -n "$BOARD_URL"
```

If the executable cannot be resolved or the command prints no `BOARD_URL`, open
`design-board.html` directly with the host's browser-opening tool. Direct-file mode
remains functional: Submit and Remix download `feedback.json` or
`feedback-pending.json` for the agent to read. The Board itself is the chooser;
chat is only the fallback channel.

### 5. Observe Tasks, Not Vibes

Ask the user to operate the same representative task in every candidate. Record:

- what they noticed first;
- where they knew or did not know what to do next;
- which disclosure helped or hid necessary evidence;
- which state transition felt natural or surprising;
- which elements to preserve, reject, or remix.

Do not replace these observations with a numeric score or a claim that the most
polished candidate is best. The user may choose one candidate or combine named
parts of several.

When `feedback-pending.json` appears, preserve the accepted parts, alter the named
failure axis, regenerate only the affected candidates, and build a versioned Board
file in the same session directory. If a gstack Board is already serving, reload
that exact Board instead of calling `serve` again on the old source path:

```bash
curl -sS -X POST "${BOARD_URL%/}/api/reload" \
  -H 'Content-Type: application/json' \
  -d '{"html":"<absolute-versioned-board-path>"}'
```

Expected response: `{"reloaded":true}`. Repeated `serve` calls may reuse a Board
instance without reading changed bytes, so they are not a reload mechanism. Ask the
user to retry the task in the same Board URL. Stop adding rounds when feedback no
longer changes the decision.

### 6. Freeze Approval Before Production

After the user confirms your feedback summary, write `approved.json` beside the
Board using the schema in `references/board-contract.md`. Capture:

- selected or remixed candidate;
- approved interaction rules and first-view invariant;
- rejected trade-offs;
- states the user actually exercised;
- remaining unknowns;
- exact prototype file identities.

Then—and only then—implement in the product. Preserve the current design system and
real data contracts. Use the project's frontend implementation and visual-QA skills,
then verify the same representative task in the real browser. Pixel resemblance is
insufficient; the approved state transitions and information order must survive.

If the project has a design SSOT, write the approved interaction decision there as
part of implementation. Keep session feedback and prototype files as evidence; do
not copy their changing values into general project instructions.

## Failure Boundaries

- Do not turn every candidate into a different product or data model.
- Do not let static image generation stand in for runnable interaction.
- Do not hide identity, current status, primary evidence, or the next action behind
  progressive disclosure when they are necessary to decide.
- Do not implement the apparent winner before the user has operated it.
- Do not write prototypes into production component directories.
- Do not claim usability validation from the author's own click-through. Agent QA
  catches broken states; the user's task observation decides the interaction.

## Delivery

Return the Board path or URL, candidate hypotheses, feedback/approval artifact
paths, browser verification performed, and the explicit next step: iterate the
Board, implement the approved candidate, or stop.
