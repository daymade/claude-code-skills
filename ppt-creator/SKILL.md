---
name: ppt-creator
description: "Create professional slide decks from topics or documents. Generates structured content with data-driven charts, speaker notes, and complete PPTX files. Applies persuasive storytelling principles (Pyramid Principle, assertion-evidence). Supports multiple formats (Marp, PowerPoint). Use for presentations, pitches, slide decks, or keynotes."
---

# PPT Creator

> **Goal**: Transform a simple topic into a presentation-ready, high-quality slide deck. When key information is missing, use the minimal intake form (references/INTAKE.md) to gather context or apply safe defaults. Then follow the workflow (references/WORKFLOW.md) to produce an outline, slide drafts, charts, and speaker notes. After generation, self-evaluate using the rubric (references/RUBRIC.md); if the score is < 75, automatically refine up to 2 iterations until ≥ 75 before delivery. See **Deliverables** section for final output structure.

## When to Use This Skill

Use this skill when the user requests:
- "Make a presentation/deck/PPT/slides" on any topic
- "Improve/optimize a presentation/pitch/demo"
- Converting scattered materials into a structured, persuasive slide deck
- Creating presentations with data visualization and speaker notes
- Building decks for business reviews, product pitches, educational content, or reports

## Quick Start

1. **Gather Intent**: If critical information is missing, ask the **10 Minimal Questions** (references/INTAKE.md). If the user doesn't respond after 2 prompts, use the **safe default** for each item and clearly note assumptions in speaker notes.

2. **Structure the Story**: Apply the **Pyramid Principle** to establish "one conclusion → 3-5 top-level reasons → supporting evidence." Each slide uses **assertion-style headings** (complete sentences), with body content providing evidence (charts/tables/diagrams/data points). Templates are in references/TEMPLATES.md.

3. **Choose Charts**: Use the **Chart Selection Dictionary** in references/VIS-GUIDE.md to pick the most appropriate visualization for each point. If the user provides data (tables/CSV), **optionally** call `scripts/chartkit.py` to generate PNG charts; otherwise, create placeholder diagrams with a list of required data fields.

4. **Layout & Style**: Follow references/STYLE-GUIDE.md for font sizes, line spacing, white space, contrast ratios, color palettes, and accessibility (WCAG AA compliance).

5. **Speaker Notes**: Generate 45-60 second speaker notes for each slide, structured as: opening → core assertion → evidence explanation → transition.

6. **Self-Check & Score**: Use references/CHECKLIST.md for a pre-flight check, then score with references/RUBRIC.md. If total score < 75, identify the weakest 3 items and refine; repeat scoring (max 2 iterations).

7. **Deliverables** (all saved to `/output/`):
   - `/output/slides.md`: Markdown slides (Marp/Reveal.js compatible), with assertion-style headings + bullet points/chart placeholders + notes
   - `/output/assets/*.png`: Generated charts (if applicable)
   - `/output/notes.md`: Full speaker notes and delivery outline
   - `/output/refs.md`: Citations and data sources
   - `/output/presentation.pptx`: If `python-pptx` is available, export to PPTX; otherwise, keep Markdown and include instructions for "one-click conversion to PPTX" in the first screen (does not block delivery)

## Orchestration Mode (End-to-End Automation)

When the user requests a "complete" or "presentation-ready" deliverable, ppt-creator automatically orchestrates the full pipeline: content creation → data synthesis → chart generation → dual-path PPTX creation (Marp + document-skills:pptx) → chart insertion. This typically delivers TWO complete PPTX files with different styling for user comparison.

**Activation**: Phrases like "complete PPTX", "final deliverable", "ready for presentation"
**Duration**: 4-6 minutes (parallel execution)
**Output**: presentation_marp_with_charts.pptx + presentation_pptx_with_charts.pptx

For orchestration details, see `references/ORCHESTRATION_OVERVIEW.md` (start here), then navigate to specialized guides as needed.

## Core Principles (Must Follow)

- **Information Organization**: Conclusion first, then evidence (Pyramid Principle). Each slide conveys **only 1 core idea**. Headings must be **testable assertion sentences**, not topic labels.
- **Evidence-First**: Use charts/tables/evidence blocks instead of long paragraphs; limit to 3-5 bullet points per slide.
- **Data Visualization**: Chart selection and labeling (axes/units/sources) must comply with references/VIS-GUIDE.md. If data is insufficient, provide "placeholder chart + list of missing fields."
- **Accessibility**: Color and text contrast must meet AA standards (see STYLE-GUIDE). Provide alt/readable descriptions for charts and images.
- **Reusability**: Use consistent naming, stable paths, reproducible output. Do not hard-code random numbers in code.
- **Safety & Dependencies**: Do not scrape the web without permission. Only run scripts when user provides data. If `matplotlib/pandas` are unavailable, fall back to text + placeholder diagram instructions.

## Workflow Overview

**Stage 0 - Archive Input**: Record user's original request, defaults used, and assumptions made.

**Stage 1 - Structure Goals**: Rewrite the goal into "who takes what action when" (clear CTA).

**Stage 2 - Storyline**: Use Pyramid Principle to define "one-sentence conclusion → 3-5 first-level reasons → evidence."

**Stage 3 - Outline & Slide Titles**: Create a 12-15 slide chapter skeleton. Each slide has one assertion-style heading.

**Stage 4 - Evidence & Charts**: Use the Chart Selection Dictionary from VIS-GUIDE. If data is provided, call chartkit.py to generate PNGs; otherwise, create placeholder + required field list.

**Stage 5 - Layout & Accessibility**: Apply STYLE-GUIDE for font sizes, spacing, contrast ratios, color palettes; unify units and decimal places.

**Stage 6 - Speaker Notes**: Generate 45-60 second notes per slide: opening → assertion → evidence explanation → transition.

**Stage 7 - Self-Check & Scoring**: Run CHECKLIST; score with RUBRIC. If score < 75, focus on weakest 3 items, refine, re-score (max 2 iterations).

**Stage 8 - Package Deliverables**: Generate `/output/` directory with slides.md / notes.md / refs.md / assets/*.png. If `python-pptx` is available, export PPTX.

**Stage 9 - Reuse Instructions**: Append a "5-step guide to replace data/colors with your own" at the end of notes.md.

## Resources

### references/INTAKE.md
**Minimal 10-Item Questionnaire** (use defaults if missing):
1. Who is the audience? (Default: general public)
2. Core objective? (Default: "understand and accept" a proposition)
3. Desired action/decision? (Default: agree to move to next step after the meeting)
4. Duration & slide count limit? (Default: 15-20 min, 12-15 slides)
5. Tone & style? (Default: professional, clear, friendly)
6. Topic scope & boundaries? (Default: given topic + 1 layer related)
7. Must-include points/taboos? (Default: none)
8. Available data/tables? (Default: none; can generate structure placeholder + list required fields)
9. Brand & visual constraints? (Default: built-in neutral theme)
10. Deliverable format preference? (Default: slides.md + optional PNG charts; export PPTX if available)

### references/WORKFLOW.md
Detailed step-by-step process from "topic" to "presentation-ready output."

### references/TEMPLATES.md
**Slide Template Library** (assertion-evidence style):
- Cover, Table of Contents, Problem Statement, Opportunity/Goal, Solution Overview, Evidence 1-3, Risk & Mitigation, Case Study/Comparison, Roadmap/Timeline, Conclusion & Actions, Backup Slides
- Micro-templates: Comparison (A vs B), Pyramid Summary, Process 4-Step, KPI Dashboard, Geographic Distribution, Funnel, Pareto, Sensitivity, Cost Structure (Waterfall), Contribution (Stacked)

### references/VIS-GUIDE.md
**Data Visualization Selection & Labeling Standards**:
- Chart Selection Dictionary (common questions → chart types)
- Labeling & units (axes, units, data scope, time range; source in footer)
- Accessibility & contrast (WCAG 2.1 AA: text vs background ≥ 4.5:1; UI elements ≥ 3:1)
- Assertion-Evidence writing tips

### references/STYLE-GUIDE.md
**Layout & Style** (neutral theme, supports brand replacement):
- Canvas: 16:9; safe margins ≥ 48px; grid column spacing 24px
- Fonts: Chinese (Source Han Sans/PingFang/Hiragino Sans), English (Inter/Calibri)
- Font sizes: Heading 34-40, Subheading 24-28, Body 18-22, Footer 14-16
- Line spacing: Heading 1.1, Body 1.3; bullet spacing ≥ 8px
- Color palette (AA compliant): Dark ink #1F2937 / Background #FFFFFF / Accent #2563EB / Emphasis #DC2626
- Components: unified 6-8px border radius; charts and images with 8px padding
- Images: add brief alt descriptions for screen readers
- Page density: ≤ 70 words per slide (excluding captions)

### references/RUBRIC.md
**PPT Quality Scoring Rubric** (100 points; ≥ 75 to deliver):
Each item scored 0-10:
1. **Goal Clarity**: Audience, objective, CTA well-defined
2. **Story Structure**: Pyramid structure complete, hierarchy clear
3. **Slide Assertions**: Headings are "assertion sentences" supported by evidence
4. **Evidence Quality**: Data/cases/citations sufficient, credible, consistent calibration
5. **Chart Fit**: Correct selection, complete labeling, readable
6. **Visual & Accessibility**: Contrast, font size, white space, color compliance
7. **Coherence & Transitions**: Natural chapter and page transitions
8. **Speakability**: 45-60 sec per slide, natural language
9. **Deliverables Complete**: slides.md / notes.md / refs.md / (optional) assets/*.png
10. **Robustness**: Gaps explicitly marked, fallback plan & next steps provided

Self-evaluation process: Run CHECKLIST first, then score each item and write top 3 low-scoring items + improvement actions. If total < 75, apply actions and re-score (max 2 iterations).

### references/CHECKLIST.md
Pre-flight checklist for final quality assurance before delivery.

### references/EXAMPLES.md
**Two Usage Examples**:
- **Example A**: Ultra-simple topic ("coffee") → trigger minimal questionnaire, generate 12-page framework with placeholder charts
- **Example B**: Small business monthly review with attached CSV → parse data, select charts per VIS-GUIDE, call chartkit.py, refine 1-2 iterations if score < 75

### scripts/chartkit.py
**Minimal chart renderer** for ppt-creator.

**Usage**:
```bash
python scripts/chartkit.py \
  --data path/to/data.csv \
  --type line \
  --x date \
  --y sales profit \
  --out output/assets \
  --filename kpi_trend.png \
  --title "Monthly KPIs"
```

**Notes**:
- Requires: `pandas`, `matplotlib`
- Fallback: If packages unavailable, print instruction message and exit(0)
- Uses matplotlib defaults for readability (no hard-coded brand colors)

## Advanced Tips

- This skill **complements** (not conflicts with) Anthropic's built-in PowerPoint generation capabilities. Use this skill to produce "high-quality structure & content," then optionally invoke system capabilities to export the final PPTX file.
- For complex data analysis needs, combine with other skills (e.g., data analysis, charting) before invoking ppt-creator.
- The skill is designed to be forgiving: missing information triggers safe defaults rather than blocking progress.
