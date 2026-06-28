# Design Style Selection Playbook

## Session Pattern

1. Confirm the artifact type and what must not be discarded.
2. Inspect current screenshots, tokens, brand imagery, and domain purpose.
3. Generate a first matrix:
   - 5 vertical ladder images for one disputed axis.
   - 5 horizontal images for different organization strategies.
   - 1-2 boundary images showing likely overload or underload.
4. Show grouped paths and label each with why it exists.
5. Ask the user to choose concrete files, not adjectives.
6. Fuse selected files by extracting roles:
   - Layout density
   - Palette intensity
   - Color placement
   - Focal hierarchy
   - Component style
   - Domain imagery
7. Implement the selected fusion in the existing artifact.
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

When the user selects images, write a fusion statement before editing:

```text
I will take <file A> for <specific attribute> and <file B> for <specific attribute>.
I will keep existing <assets/tokens/layout> and only change <scope>.
```

Then implement and verify.
