---
name: design-style-picker
description: Batch-generate and compare visual design directions so a user can choose the style they actually want. Use when the user says they cannot describe an abstract visual style, asks for many style options, wants to choose from generated UI/design-system images, rejects outputs as too colorful/too dead/too generic, or needs an existing UI/design system evolved without discarding current assets.
---

# Design Style Picker

## Purpose

Use this skill to turn vague taste into concrete visual choices. The goal is not to guess one final design; it is to generate a structured set of options that exposes the user's taste boundary quickly.

## Core Rule

Do not ask the user to describe an abstract style if they already said they cannot. Generate comparable visual evidence, let them pick, then implement from the selected references.

## Workflow

1. **Restate The Real Target**
   - Say what the user is actually choosing: design-system style, business app surface, landing page, deck, component library, etc.
   - Distinguish choosing one direction, retaining several directions, and assigning directions to different visual roles. Multiple options do not imply mutual exclusion; retaining both does not decide how they coexist. Keep an unresolved adoption or fusion choice open while exploring the authorized directions.
   - Separate the primary artifact from validation samples. If the task is a design system, business screens are optional validation samples, not the main deliverable.
   - Preserve any existing UI, assets, tokens, layout, brand cues, and domain context unless the user explicitly asks to discard them.
   - Freeze the existing spatial structure, navigation, zoom/detail levels, and reading behavior outside this round's authorized axes. Name those axes before evolving a product; do not rearrange it into another page merely to make a style comparison easier.

2. **Collect Existing Assets First**
   - Inspect the current rendered UI or screenshots.
   - Before selecting a structural screenshot, match its actual surface and interaction level to the user's target. A local detail screen can anchor a local-screen task; it cannot stand in for a whole workspace or its overview-to-detail flow. Obtain the missing views or use the verified specification, labeling any part not visually observed.
   - Read design tokens, CSS variables, component names, key images, brand/domain references, and existing screenshots.
   - Treat current assets as the starting vocabulary. Do not generate unrelated "fresh" concepts over them.

3. **Generate A Matrix, Not Minor Variants**
   - Use at least two authorized axes when taste is unclear:
     - Vertical ladder: one dimension changes by large steps, such as color intensity 20/35/50/65/80.
     - Horizontal directions: different organization strategies, such as data-driven color, brand spine, warm product imagery, scenario modules, or governance-led layout.
   - Make options visibly different. If two images look like siblings, regenerate one with a clearer contrast.
   - Prefer batch generation. The user is waiting for selection, not watching one slow image at a time.

4. **Use Color As A System**
   - "Less colorful" does not mean black-and-white. It usually means fewer competing focal points.
   - Keep the product palette alive, but assign color roles:
     - Broad zones and section bands for architecture.
     - Data visualization and evidence systems for multi-color semantics.
     - Brand/risk colors for rare, high-signal emphasis.
     - Neutral components for routine UI.
   - Include explicit upper-bound samples when the user is tuning color: safe, middle, high, and overload boundary.

5. **Review Before Presenting**
   - Open generated images yourself.
   - Check target coverage before taste: can the user inspect the requested surface, scale, states, and interaction levels, and do the candidates retain the stated relationship? Repair missing coverage before judging colors or character details. Static images illustrate interaction levels; they do not prove interaction behavior.
   - Mark which are likely too dead, too colorful, too generic, too business-system-like, or closest to the target.
   - Present file paths and a short decision note for each useful candidate.

6. **Implement From Selected Images**
   - Extract principles, not pixels: color roles, layout density, focal hierarchy, component treatment, image use, governance/data placement.
   - Fuse selected references explicitly when that combination is approved. Example: "Use H02 for color placement and V04 for palette intensity." If several directions are only retained for exploration, keep them available without treating retention as approval to fuse or assign roles.
   - Keep implementation scoped to the existing UI unless the user asks for a new artifact.
   - Run rendered visual QA after implementation.

## Prompt Pattern

When generating images, include:

```text
This is an evolution of the existing UI/design system, not a replacement.
Preserve these assets: <tokens, imagery, sections, components, brand cues>.
Target surface and levels: <requested view, scale, states, overview/detail coverage>.
Reference coverage: <what each screenshot proves; missing views or specification-only parts>.
Frozen behavior: <spatial structure, navigation, zoom, reading>.
Direction relationship: <choose one / retain several / approved role assignment; unresolved choices>.
Axis: <vertical ladder or horizontal direction>.
Variant name: <clear label>.
Color/visual rule: <specific budget or organization method>.
Primary focal point: <one thing>.
Avoid: <known rejected styles from the user>.
```

## Lessons To Preserve

- A user saying "not colorful" may mean "no dozens of equal-weight small color chips", not "remove all color".
- A user saying "more weight" may mean visual authority and hierarchy, not dark-mode control room.
- For design-system work, do not replace the system with a business dashboard. Business screens can validate style, but should not become the answer.
- Always create deliberate boundary samples. They make "too much" visible and speed up selection.
- After an approved combination, fuse the chosen references and name what each contributes.

## References

- Read `references/selection-playbook.md` when running a full style-selection session or when the user gives taste corrections during image exploration.
