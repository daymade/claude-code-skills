# Interaction Design Method

Read this reference before proposing candidate architectures or judging whether a
prototype is ready for the Board.

## Start From The Business Decision

The comparison exists to improve a user's real task, not to award a prettier layout.
State the operator, object, decision, required evidence, and next action first.

For operational software, a reliable first-view order is:

1. **Object:** what needs attention?
2. **Reason and evidence:** why does it matter, and how certain is the system?
3. **Action:** what can the operator do now?
4. **Secondary context:** what helps only after the primary decision is understood?

Strong hierarchy, high information density, and explicit actions can coexist. The
test is not how much information is present; it is whether the reader can tell what
is primary, what is evidence, and what can wait.

## Hold Facts Constant, Vary The Architecture

Comparisons become uninterpretable when every candidate changes data, copy, color,
and interaction at once. Freeze business facts and the current design language.
Vary one coherent interaction hypothesis per candidate:

- who owns selection;
- where primary evidence appears;
- whether work is object-first, queue-first, command-first, or comparison-first;
- how secondary detail is disclosed;
- where the next action lives;
- how the user preserves context while moving through items.

The candidates should be meaningfully different. Two files with the same layout and
slightly different spacing are one hypothesis, not two.

## Use Progressive Disclosure Deliberately

Disclosure is useful when it lets experienced users reveal related secondary
content without losing the current task. It is harmful when it hides information
every user needs to understand the object, risk, status, evidence boundary, or next
action.

Before adding an accordion, drawer, details row, or popover, test the page without
it. Prefer clearer grouping or simpler content when that solves the hierarchy. Do
not nest disclosure controls. Make the control label explain what will appear, keep
its expanded state observable, and preserve keyboard access.

The GOV.UK Design System makes the same distinction: accordions are appropriate
when users need an overview and selectively reveal related sections, but not for
content all users need to see. See:
https://design-system.service.gov.uk/components/accordion/

## Match Interaction Fidelity To The Decision

Implement every state needed to compare the hypothesis; omit backend fidelity that
does not affect the decision.

- If choosing between queue and table ownership, selection and detail updates must
  work.
- If choosing disclosure depth, closed and open states must work.
- If choosing a multi-step action, the steps, back path, and confirmation boundary
  must work.
- If the decision is purely visual, stop and use a static-style exploration skill.

Never add decorative controls that imply a workflow the candidate does not support.

Prototype testing is formative: it is used before implementation to expose usability
problems and compare alternative solutions. It does not prove production usability
or replace observation of the real product. See Nielsen Norman Group's UX research
glossary:
https://www.nngroup.com/articles/research-methods-glossary/

## Preserve Comparable Viewports

Use the same desktop viewport, seed state, content, and task for every candidate.
Keep each candidate operable at its intended size. The Design Board's focus mode is
for interaction; its comparison mode is for cross-checking hierarchy and state.

Do not shrink a dense application until the text becomes unreadable merely to fit
all candidates on one screen. Side-by-side inspection is a navigation aid, not the
final usability environment.

## Use Established Keyboard Semantics

Use native controls whenever possible. When the Board presents candidates as tabs:

- expose `tablist`, `tab`, and `tabpanel` roles;
- keep `aria-selected` and `aria-controls` accurate;
- support Left/Right Arrow, Home, End, Space, and Enter;
- keep focus visible;
- avoid automatic activation when loading a panel would introduce noticeable delay.

The W3C WAI-ARIA Authoring Practices tabs pattern is the implementation reference:
https://www.w3.org/WAI/ARIA/apg/patterns/tabs/

Within each prototype, use the relevant WAI-ARIA pattern rather than inventing key
bindings. The Authoring Practices Guide is informative guidance consistent with the
normative ARIA specifications; treat its established keyboard conventions as the
default unless the platform has a stronger native convention.

## Interpret Feedback As Decision Rules

Do not reduce user feedback to adjectives such as "cleaner" or "more professional."
Translate it into observable design rules:

- "I found the urgent item immediately" → keep the top object and reason in the
  first view.
- "I lost where I was after opening evidence" → preserve queue or object context
  during disclosure.
- "The table disappeared" → retain the comparison structure above the fold.
- "This feels busy" → identify which signals compete at the same priority; do not
  blindly remove density.

Record the user's wording in the feedback artifact. Write the generalized rule into
the product's design SSOT only after the user approves the interpretation.

## Quality Gate Before Presentation

For every candidate, verify in a real browser:

- the declared states can be reached and reversed;
- the first-view invariant remains visible;
- primary action and focus order are usable;
- no content is clipped or horizontally lost at the agreed desktop viewport;
- unknown data remains honest;
- the candidate differs from the others in the declared interaction architecture;
- the Board can switch candidates by mouse and keyboard without corrupting notes.

This gate catches implementation defects. It does not select the winner.
