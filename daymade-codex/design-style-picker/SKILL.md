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
   - Separate the primary artifact from validation samples. If the task is a design system, business screens are optional validation samples, not the main deliverable.
   - Preserve any existing UI, assets, tokens, layout, brand cues, and domain context unless the user explicitly asks to discard them.

2. **Collect Existing Assets First**
   - Inspect the current rendered UI or screenshots.
   - Read design tokens, CSS variables, component names, key images, brand/domain references, and existing screenshots.
   - Treat current assets as the starting vocabulary. Do not generate unrelated "fresh" concepts over them.

3. **Generate A Matrix, Not Minor Variants**
   - Use at least two axes when taste is unclear:
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
   - Mark which are likely too dead, too colorful, too generic, too business-system-like, or closest to the target.
   - Present file paths and a short decision note for each useful candidate.

6. **Implement From Selected Images**
   - Extract principles, not pixels: color roles, layout density, focal hierarchy, component treatment, image use, governance/data placement.
   - Fuse selected references explicitly. Example: "Use H02 for color placement and V04 for palette intensity."
   - Keep implementation scoped to the existing UI unless the user asks for a new artifact.
   - Run rendered visual QA after implementation.

## Prompt Pattern

When generating images, include:

```text
This is an evolution of the existing UI/design system, not a replacement.
Preserve these assets: <tokens, imagery, sections, components, brand cues>.
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
- After selection, fuse the chosen references and name what each contributes.

## References

- Read `references/selection-playbook.md` when running a full style-selection session or when the user gives taste corrections during image exploration.
