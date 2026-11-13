# Design Style Selection Playbook

## Session Pattern

1. Confirm the artifact type and the current decision: business meaning, spatial organization, visual treatment, or interaction behavior. Record approved dimensions, unresolved dimensions, and the axes allowed to change. Respect the user's review order. A selected layout or palette does not approve its wording, business relationships, or depicted interactions.
   Confirm whether directions are alternatives or jointly retained, any approved role assignment, and what must not be discarded. Leave undecided adoption or fusion choices open.
2. Inspect current screenshots, tokens, brand imagery, and domain purpose. Match each structural reference to the requested surface and interaction levels; preserve existing behavior and vary only authorized axes.
3. Choose candidates that resolve the current uncertainty:
   - Use a vertical ladder for a disputed range, with large enough steps to expose its boundary.
   - Use horizontal directions for disputed organization strategies, within the authorized scope.
   - Add overload or underload samples only when that boundary could change the decision.
   Keep the same business facts and comparable surface/detail coverage. Candidate count follows the decision; these forms are not a required batch of images, and a known dimension needs no new ladder.
4. Show grouped paths and label each with the judgment it helps make and its trade-off. Start with a readable large candidate; provide switching or side-by-side comparison when useful. Test enlargement and return if offered: selected candidate and reading position must survive. A working image viewer does not prove the interactions depicted in a mockup.
5. Ask for feedback on concrete files, not adjectives: choose a direction, retain several, or approve their roles according to the current task.
6. For an approved combination, fuse selected files by extracting roles:
   - Layout density
   - Palette intensity
   - Color placement
   - Focal hierarchy
   - Component style
   - Domain imagery
7. Stop generating when the user can make the current choice. Record what was selected and what remains unapproved, then implement only the approved selection, combination, or role assignment in the existing artifact. Retention alone leaves the implementation choice open.
8. Run rendered visual QA.

## Color Calibration

Use large jumps, not timid tweaks:

- 20: existing UI with light color recovery.
- 35: semantic palette returns, still restrained.
- 50: full palette visible in the design system.
- 65: high color, organized by grid and semantic zones.
- 80: upper bound, likely close to too much.
- Overload: deliberately too much, used only to mark the boundary.

Good color organization:

- Data colors live in charts, legends, evidence source types, and metric contracts.
- Brand red lives in logo, active spine, must-block governance, and highest-risk examples.
- Energy green lives in lead loop, positive flow, successful threshold, and domain atmosphere.
- Solar amber lives in pending, warning, attention, and warm product context.
- Routine UI stays neutral.

Bad color organization:

- Every tag, row, icon, and card has its own saturated color.
- Red, green, amber, and blue all compete in the same small area.
- Removing color entirely after the user says "less colorful".
- Creating images unrelated to the current UI assets.

## Selection Language

When reporting options, use concrete labels:

- "Closest to current artifact, with stronger palette."
- "Good data-color organization, weak domain image."
- "Strong brand spine, red may be too loud."
- "Colorful but still organized."
- "Boundary sample, likely too much."

Avoid:

- "This is more premium."
- "This looks better."
- "Modern and clean."

## Implementation Handoff

When the user approves an implementation, name its reference contributions and frozen behavior before editing:

```text
I will take <file A> for <specific attribute> and <file B> for <specific attribute>.
I will keep existing <assets, tokens, layout, navigation, zoom, reading behavior> and only change <authorized axes>.
```

Then implement and verify.

## Bounded Selection Examples

The executing designer applies these examples; they are manual decision checks,
not an automatic image-count or approval detector.

- **Layout selected, wording open:** the user chooses a folded layout and its
  visual treatment, then asks for several structured wording versions. Keep the
  selected layout and style, compare the business wording in the requested form,
  and retain any explicit content-before-code gate. Do not generate another
  palette matrix or treat the layout choice as approval of the business text.
- **Only the saturation range is open:** the account structure, navigation and
  wording are approved. Offer a meaningful saturation ladder with a boundary
  sample if needed; preserve the same populated screen and interaction levels.
  End that comparison when the user can choose. Do not expand into new layouts
  or complete a preselected number of images after the uncertainty is resolved.
