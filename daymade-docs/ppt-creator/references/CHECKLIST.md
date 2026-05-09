# Pre-Flight Checklist

> **Purpose**: Final quality assurance before delivery. Use this checklist **before** running the full RUBRIC.md scoring. This ensures all required elements are present and obvious issues are caught early.

---

## How to Use This Checklist

1. **When**: Run this checklist after completing WORKFLOW Stage 7 (before final scoring)
2. **Method**: Go through each section; check ✓ or note issues
3. **Threshold**: All items in sections 1-5 must be ✓ before delivery; section 6-7 are optional enhancements
4. **Time**: ~5-10 minutes for a 12-15 slide deck

---

## Section 1: Content Completeness

### Slide Count & Structure

- [ ] **Total slide count** matches target range (typically 12-15 slides for 15-20 min presentation)
- [ ] **Cover slide** present with title, subtitle, date, presenter
- [ ] **Table of Contents** present and matches actual sections
- [ ] **Main content slides** (evidence/argument slides) present
- [ ] **Conclusion slide** present with clear call-to-action (CTA)
- [ ] **Backup slides** (if needed) clearly marked "Backup—not presented"

**If any unchecked**: Add missing slides or adjust scope.

---

### Intake & Assumptions

- [ ] **INTAKE.md questions** answered or defaulted (all 10 items)
- [ ] **Assumptions documented** in `/output/notes.md` (if defaults were used)
- [ ] **User's original request** recorded in archive.txt or notes

**If any unchecked**: Review INTAKE.md and document assumptions.

---

## Section 2: Story & Structure

### Pyramid Principle

- [ ] **Main conclusion** stated on cover slide (assertion sentence)
- [ ] **3-5 first-level reasons** identified and each has a section
- [ ] **Evidence slides** support each reason (2-3 slides per reason)
- [ ] **Logical flow**: Conclusion → Reasons → Evidence (not evidence → conclusion)

**If any unchecked**: Revise structure per WORKFLOW Stage 2.

---

### Slide Headings (Assertion-Evidence)

- [ ] **All slide headings are assertion sentences** (testable claims, not topic labels)
  - ✅ Example: "Finer grind size extracts flavors faster"
  - ❌ Counter-example: "Grind Size" or "Background"
- [ ] **Headings are complete sentences** (subject + verb + object)
- [ ] **Headings match the evidence** shown on the slide

**Quick Test**: Can you agree or disagree with each heading? (If no → it's a topic label, needs revision)

**If any unchecked**: Convert topic labels to assertion sentences (see TEMPLATES.md).

---

## Section 3: Evidence & Data

### Evidence for Claims

- [ ] **Every assertion slide** has supporting evidence (chart, table, example, case study, or diagram)
- [ ] **No unsupported claims** (all "X is true" statements backed by data/citations)
- [ ] **Placeholder charts** (if data unavailable) include:
  - Chart type (e.g., "line chart", "bar chart")
  - Axes and variables (e.g., "X: month, Y: revenue")
  - Required data fields (e.g., "Need: month, revenue_usd")

**If any unchecked**: Add evidence or create detailed placeholders.

---

### Charts & Visualizations

- [ ] **Chart type matches message** (verified against VIS-GUIDE.md Chart Selection Dictionary)
  - Trend over time → line/area chart
  - Comparison → horizontal bar chart
  - Composition → stacked bar / treemap
  - Correlation → scatter plot
- [ ] **All charts have axis labels** (X-axis and Y-axis labeled with units)
- [ ] **All charts have data sources** cited in footer (e.g., "Source: XYZ, 2024")
- [ ] **All charts have alt text** for screen readers (brief description of insight)
- [ ] **Chart colors are colorblind-friendly** (avoid red+green; use blue+orange)

**If any unchecked**: Fix chart selection, labeling, or add missing elements.

---

## Section 4: Visual Design & Accessibility

### Typography

- [ ] **Heading font size** ≥ 34pt
- [ ] **Body font size** ≥ 18pt
- [ ] **Footer font size** ≥ 14pt (but not smaller)
- [ ] **Line spacing**: Headings 1.1×, body 1.3-1.5×
- [ ] **Fonts consistent** across all slides (same family for headings, same for body)

**If any unchecked**: Adjust font sizes per STYLE-GUIDE.md.

---

### Color & Contrast

- [ ] **Text contrast** ≥ 4.5:1 against background (normal text <18pt)
- [ ] **Large text contrast** ≥ 3:1 (headings ≥18pt or ≥14pt bold)
- [ ] **UI elements contrast** ≥ 3:1 (chart bars, icons, dividers)
- [ ] **Not relying on color alone** (patterns/labels added for charts with multiple series)

**How to check**: Use WebAIM Contrast Checker or browser DevTools.

**If any unchecked**: Adjust colors to meet WCAG AA standards (see STYLE-GUIDE.md).

---

### Layout & Spacing

- [ ] **Safe margins** ≥ 48px on all sides (content within safe zone)
- [ ] **Bullet points** limited to 3-5 per slide (not 8-10)
- [ ] **Word count** ≤ 70 words per slide (excluding chart labels and footer)
- [ ] **White space** ~40-50% of each slide (not crammed full)
- [ ] **Consistent alignment**: Headings and body text left-aligned (unless intentionally centered)

**If any unchecked**: Increase margins, reduce text, or split into multiple slides.

---

### Images & Alt Text

- [ ] **All images have alt text** (descriptive, 1-2 sentences)
- [ ] **All charts have alt text** (includes key insight, e.g., "Line chart showing 35% revenue growth Jan-Dec 2024")
- [ ] **Images not stretched or distorted** (maintain aspect ratio)

**If any unchecked**: Add alt text or fix image formatting.

---

## Section 5: Speaker Notes & Timing

### Speaker Notes Quality

- [ ] **Every slide has speaker notes** (except backup slides)
- [ ] **Notes are 45-60 seconds per slide** (read aloud to verify)
- [ ] **Notes use natural spoken language** (not bullet points or written prose)
- [ ] **Notes follow structure**: Opening → Core Assertion → Evidence Explanation → Transition
- [ ] **Notes include transitions** to next slide (e.g., "This leads us to...")

**If any unchecked**: Revise notes per WORKFLOW Stage 6.

---

### Total Timing

- [ ] **Total presentation time** matches target (e.g., 15 min = ~15 slides × 60 sec)
- [ ] **Timing buffer** included (5-10% slack for questions/pauses)

**Quick Calc**: Count slides (excluding cover, TOC, backup) × 60 sec = estimated time.

**If any unchecked**: Adjust slide count or speaker notes length.

---

## Section 6: Deliverables (Output Files)

### Required Files

- [ ] `/output/slides.md` exists and is properly formatted (Markdown with YAML frontmatter)
- [ ] `/output/notes.md` exists with full speaker script
- [ ] `/output/refs.md` exists with all citations and sources
- [ ] `/output/assets/` directory exists (even if empty)
- [ ] `/output/README.md` exists explaining file structure

**If any unchecked**: Generate missing files per WORKFLOW Stage 8.

---

### Optional Files (If Applicable)

- [ ] `/output/assets/*.png` charts generated (if data was provided and chartkit.py was used)
- [ ] `/output/presentation.pptx` exported (if python-pptx is available)
  - If not available: Instructions for PPTX conversion included in notes.md

**If any unchecked**: Generate charts or add conversion instructions.

---

## Section 7: Polish & Enhancements (Optional but Recommended)

### Consistency Checks

- [ ] **Number formatting consistent**: Same decimal places for same metric (e.g., all percentages to 1 decimal)
- [ ] **Units consistent**: All currency in $ or all in €; don't mix
- [ ] **Date format consistent**: All "Jan 2024" or all "2024-01" (pick one)
- [ ] **Capitalization consistent**: Heading case for all slide titles

---

### Branding (If Applicable)

- [ ] **Brand colors applied** (if provided in INTAKE question 9)
- [ ] **Logo added** to cover slide and/or footer (if applicable)
- [ ] **Brand fonts used** (if specified)

**If unchecked and brand was specified**: Apply per STYLE-GUIDE customization section.

---

### Reuse Guide

- [ ] **"5-Step Reuse Guide" appended** to notes.md (helps user customize later)
- [ ] **chartkit.py usage examples** included (if charts were generated)
- [ ] **Markdown-to-PPTX conversion instructions** included (if PPTX not auto-generated)

**If any unchecked**: Add per WORKFLOW Stage 9.

---

## Section 8: Final Sanity Checks

### Links & References

- [ ] **All internal links work** (e.g., references to "See backup slide 14")
- [ ] **All chart/image paths correct** (no broken image links in slides.md)
- [ ] **All citations complete** (author, year, source name)

---

### Spelling & Grammar

- [ ] **Spell-check run** on all text (slides + notes)
- [ ] **Grammar checked** (especially speaker notes, which are full sentences)
- [ ] **Consistent terminology** (e.g., don't switch between "users" and "customers")

**Tool suggestions**: Grammarly, LanguageTool, or built-in spell-checker.

---

### Edge Cases

- [ ] **Long words or URLs** broken or shortened (avoid overflow)
- [ ] **Special characters** (©, ®, ™, °, etc.) display correctly
- [ ] **Non-English text** (if any) uses correct fonts and displays properly

---

## Checklist Summary

**Count your checks**:

- **Section 1 (Content)**: ___ / 9 items ✓
- **Section 2 (Structure)**: ___ / 8 items ✓
- **Section 3 (Evidence)**: ___ / 9 items ✓
- **Section 4 (Design)**: ___ / 18 items ✓
- **Section 5 (Notes)**: ___ / 7 items ✓
- **Section 6 (Deliverables)**: ___ / 7 items ✓
- **Section 7 (Polish)**: ___ / 7 items ✓ (optional)
- **Section 8 (Sanity)**: ___ / 6 items ✓

**TOTAL**: ___ / 64 core items (sections 1-6)

**PASSING CRITERIA**:
- **Sections 1-6**: All items ✓ (64/64 required)
- **Section 7-8**: Nice-to-have but not required for delivery

---

## What to Do If Items Are Unchecked

### Minor Issues (1-5 unchecked in sections 1-6)

**Action**: Fix the specific items now before moving to RUBRIC scoring.

**Example**:
- Missing alt text on 2 charts → Add alt text
- One topic-label heading → Convert to assertion sentence
- Font size 16pt on one slide → Increase to 18pt

---

### Moderate Issues (6-15 unchecked in sections 1-6)

**Action**: Prioritize the most impactful fixes first:
1. **Structure issues** (Section 2): Fix pyramid structure, convert headings
2. **Evidence gaps** (Section 3): Add missing charts or citations
3. **Accessibility** (Section 4): Fix contrast, font sizes
4. **Speaker notes** (Section 5): Revise timing or add transitions

**Estimated Time**: 15-30 minutes of fixes before re-running checklist.

---

### Major Issues (16+ unchecked in sections 1-6)

**Action**: Return to WORKFLOW Stage 3-4 and rebuild:
- If structure is broken (Section 2): Restart from Stage 3 (Outline)
- If evidence is weak (Section 3): Restart from Stage 4 (Evidence & Charts)
- If design is poor (Section 4): Apply STYLE-GUIDE systematically

**Estimated Time**: 1-2 hours of rework.

---

## After Checklist: Next Steps

Once all core items (Sections 1-6) are ✓:

1. **Proceed to RUBRIC.md** for detailed scoring (0-10 per item, total 100)
2. **If RUBRIC score ≥ 75**: Package deliverables and deliver
3. **If RUBRIC score < 75**: Apply top 3 improvements and re-score (max 2 iterations)

---

## Quick Reference: Most Common Issues

Based on typical PPT creation, here are the **top 10 most common checklist failures**:

1. ❌ **Slide headings are topic labels** (not assertion sentences) → Fix: Convert to testable claims
2. ❌ **Missing source citations on charts** → Fix: Add "Source: XYZ, 2024" in footer
3. ❌ **Font sizes too small** (body <18pt) → Fix: Increase to 18-22pt
4. ❌ **No alt text on charts** → Fix: Add brief description with key insight
5. ❌ **Poor contrast** (<4.5:1) → Fix: Darken text or lighten background
6. ❌ **Too many bullets** (>5 per slide) → Fix: Split into 2 slides or reduce
7. ❌ **No speaker notes** on some slides → Fix: Write 45-60 sec script per slide
8. ❌ **Assumptions not documented** (if defaults used) → Fix: Add to notes.md
9. ❌ **Chart type mismatch** (e.g., pie chart for 7 categories) → Fix: Use bar chart instead
10. ❌ **Inconsistent number formatting** (mixing "1.2M" and "850,000") → Fix: Use same abbreviation style

---

## Checklist Completion Log

**Presentation**: [Title]
**Date**: [YYYY-MM-DD]
**Checked by**: Claude
**Status**: [PASS / FAIL]

**Issues Found**: [Number]
**Issues Fixed**: [Number]
**Remaining**: [Number]

**Notes**:
- [List any issues not yet fixed]
- [Next steps or blockers]

---

**Next Steps**: After all checklist items are ✓, proceed to RUBRIC.md for full scoring.
