# PPT Creation Workflow

> **From Simple Topic to Presentation-Ready Output**
>
> This workflow guides you through 10 stages, from gathering user intent to packaging final deliverables. Each stage has clear inputs, actions, and outputs. Follow this sequence to ensure consistent, high-quality results.

---

## Stage 0: Archive Input

**Goal**: Capture the raw user request and document all assumptions.

**Actions**:
1. Record the user's original request verbatim
2. Document which intake questions were answered vs. defaulted
3. List all assumptions made (from INTAKE.md defaults)
4. Note any data files or assets provided
5. Create a `/output/` directory for all deliverables

**Output**:
- `archive.txt` containing:
  - Original user request
  - Answered questions (with values)
  - Defaulted questions (with safe defaults applied)
  - Assumptions and limitations

**Example**:
```
ORIGINAL REQUEST: "Make me a presentation about coffee"
ANSWERED QUESTIONS:
- Audience: coffee enthusiasts
- Duration: 10 minutes
- Goal: improve home brewing
- Data available: none
DEFAULTED QUESTIONS:
- Tone: professional, clear, friendly (default)
- Format: slides.md + charts (default)
- Scope: coffee brewing + 1 layer related (default)
ASSUMPTIONS:
- No brand constraints → using neutral theme
- No specific CTA → using "try new methods at home"
```

---

## Stage 1: Structure Goals

**Goal**: Transform vague objectives into a clear, actionable CTA.

**Actions**:
1. Identify the **audience** (who)
2. Define the **action** (what they should do)
3. Specify the **timing** (when/by when)
4. Combine into a one-sentence goal: "After this presentation, [audience] will [action] by [timing]"

**Output**:
- One-sentence goal statement
- Clear call-to-action (CTA) for the final slide

**Example**:
```
INPUT: "I want them to improve their home brewing"
OUTPUT: "After this presentation, coffee enthusiasts will try at least one new brewing technique within the next week."
CTA: "Pick one technique from today's session and try it with your next cup."
```

---

## Stage 2: Storyline (Pyramid Principle)

**Goal**: Structure the argument using the Pyramid Principle: one top-level conclusion supported by 3-5 first-level reasons, each backed by evidence.

**Actions**:
1. Write the **one-sentence conclusion** (top of pyramid)
2. Identify **3-5 first-level reasons** that support the conclusion
3. For each reason, list **2-3 pieces of evidence** (data, examples, case studies, diagrams)
4. Ensure logical flow: conclusion → reasons → evidence

**Output**:
- Pyramid structure diagram
- Story spine summary

**Example**:
```
CONCLUSION: Mastering three variables—grind size, water temperature, and brew time—unlocks consistently great coffee at home.

REASON 1: Grind size controls extraction rate
  - Evidence 1a: Finer grind = more surface area = faster extraction
  - Evidence 1b: Diagram showing grind sizes from espresso to French press
  - Evidence 1c: Over-extracted (bitter) vs. under-extracted (sour) flavor profiles

REASON 2: Water temperature affects solubility
  - Evidence 2a: 195-205°F extracts balanced flavors
  - Evidence 2b: Chart showing temperature vs. extraction compounds
  - Evidence 2c: Cold brew example (low temp, long time)

REASON 3: Brew time determines strength and flavor balance
  - Evidence 3a: Pour-over: 2-4 min; French press: 4 min; espresso: 25-30 sec
  - Evidence 3b: Timeline diagram of brewing methods
  - Evidence 3c: Case study: adjusting brew time to fix weak/bitter coffee

SUPPORTING REASON 4: Simple equipment upgrades improve consistency
  - Evidence 4a: Burr grinder vs. blade grinder
  - Evidence 4b: Kitchen thermometer for precise temperature
  - Evidence 4c: Digital scale for consistent ratios
```

---

## Stage 3: Outline & Slide Titles (Assertion-Style)

**Goal**: Convert the pyramid structure into a 12-15 slide outline with assertion-style headings.

**Actions**:
1. Start with **cover slide** (title = main conclusion)
2. Add **table of contents** (3-5 chapters matching first-level reasons)
3. For each reason, create **2-3 slides** with assertion headings (complete sentences, not topic labels)
4. Add **conclusion & CTA slide**
5. Optionally add **backup slides** for extra details

**Output**:
- Slide-by-slide outline with assertion headings
- Estimated timing per slide (45-60 seconds each)

**Assertion Heading Rules**:
- ✅ "Finer grind size extracts flavors faster and more completely"
- ❌ "Grind Size" (topic label)
- ✅ "Water between 195-205°F produces balanced, full-bodied coffee"
- ❌ "Temperature Control" (topic label)

**Example Outline**:
```
1. COVER: Mastering Three Variables Unlocks Consistently Great Coffee at Home
2. TABLE OF CONTENTS: Grind Size • Water Temperature • Brew Time • Equipment
3. PROBLEM: Inconsistent home coffee wastes beans and disappoints drinkers
4. Finer grind size extracts flavors faster and more completely
5. Grind size must match your brewing method to avoid over- or under-extraction
6. Water between 195-205°F produces balanced, full-bodied coffee
7. Cold brew demonstrates how low temperature requires extended time
8. Brew time determines coffee strength and flavor balance
9. Each brewing method has an optimal time window for best results
10. Adjusting brew time fixes common problems like bitterness and weakness
11. Simple equipment upgrades—burr grinder, thermometer, scale—ensure consistency
12. CONCLUSION & CTA: Pick one technique from today and try it with your next cup
13. BACKUP: Detailed brewing ratio chart (1:15 to 1:18)
14. BACKUP: Troubleshooting guide (problem → likely cause → fix)
```

---

## Stage 4: Evidence & Charts

**Goal**: Select the best chart type for each piece of evidence and generate visuals (or placeholders).

**Actions**:
1. For each slide, identify the **evidence type** (comparison, trend, distribution, process, etc.)
2. Use **VIS-GUIDE.md Chart Selection Dictionary** to pick the chart type
3. If **data is available**, call `chartkit.py` to generate PNG charts
4. If **no data**, create a **placeholder description** + list of required data fields
5. Ensure all charts have:
   - Axis labels and units
   - Data source citation
   - Accessible color contrast (WCAG AA)

**Output**:
- Chart specifications for each slide
- PNG files in `/output/assets/` (if data available)
- Placeholder descriptions (if no data)

**Example**:
```
SLIDE 4: "Finer grind size extracts flavors faster and more completely"
EVIDENCE: Diagram showing grind sizes from espresso to French press
CHART TYPE: Horizontal scale with icons and labels
DATA REQUIRED: [none—illustrative diagram]
ACTION: Create placeholder diagram description
PLACEHOLDER: "Horizontal scale showing 5 grind sizes: espresso (fine powder) → pour-over (sand) → drip (table salt) → French press (coarse salt) → cold brew (peppercorns). Each labeled with particle size range."

SLIDE 6: "Water between 195-205°F produces balanced, full-bodied coffee"
EVIDENCE: Chart showing temperature vs. extraction compounds
CHART TYPE: Stacked area chart (temperature on x-axis, compounds on y-axis)
DATA REQUIRED: Temperature (°F), extraction % for acids, sugars, bitter compounds
ACTION: If data provided → chartkit.py; else → placeholder
PLACEHOLDER: "Stacked area chart: X-axis 160-212°F, Y-axis compound %. Three layers: acids (peak 185°F), sugars (peak 200°F), bitter compounds (peak 210°F). Optimal zone highlighted 195-205°F."
```

---

## Stage 5: Layout & Accessibility

**Goal**: Apply consistent visual style and ensure WCAG AA accessibility.

**Actions**:
1. Apply **STYLE-GUIDE.md** specifications:
   - Canvas: 16:9, safe margins ≥ 48px
   - Fonts: Heading 34-40pt, Body 18-22pt
   - Line spacing: Heading 1.1, Body 1.3
   - Colors: Dark ink #1F2937, Accent #2563EB, Emphasis #DC2626
2. Check **contrast ratios** (text ≥ 4.5:1, UI elements ≥ 3:1)
3. Add **alt text** for all charts and images
4. Ensure **page density** ≤ 70 words per slide (excluding captions)
5. Unify **units and decimal places** across all data

**Output**:
- Visual style specification document
- Accessibility checklist (checked)

**Example**:
```
SLIDE 4 LAYOUT:
- Heading: "Finer grind size extracts flavors faster and more completely" (36pt, #1F2937, Source Han Sans)
- Body: Horizontal grind scale diagram (alt text: "Five coffee grind sizes from fine espresso powder to coarse cold brew peppercorns")
- Footer: Source citation in 14pt, #6B7280
- Word count: 18 words (within 70-word limit)
- Contrast: Heading on white background = 16.1:1 ✓
```

---

## Stage 6: Speaker Notes

**Goal**: Write 45-60 second speaker notes for each slide.

**Actions**:
1. Follow this structure for each slide:
   - **Opening** (5-10 sec): Hook or transition from previous slide
   - **Core Assertion** (10-15 sec): Restate the slide heading in conversational language
   - **Evidence Explanation** (20-30 sec): Walk through the chart/diagram/data
   - **Transition** (5-10 sec): Bridge to next slide
2. Use **natural, spoken language** (not written prose)
3. Include **timing cues** (e.g., "[PAUSE]", "[CLICK to next slide]")
4. Anticipate **common questions** and address them

**Output**:
- Speaker notes for each slide in `/output/notes.md`
- Total script timing estimate

**Example**:
```
SLIDE 4 SPEAKER NOTES (60 seconds):

[OPENING—10 sec]
"Now that we've seen the problem with inconsistent coffee, let's dive into the first variable: grind size. [CLICK]

[CORE ASSERTION—15 sec]
The key insight here is that finer grind size extracts flavors faster and more completely. Think of it like dissolving sugar: powdered sugar dissolves instantly, while sugar cubes take forever.

[EVIDENCE EXPLANATION—25 sec]
This diagram shows five common grind sizes. On the left, espresso grind looks like fine powder—tons of surface area, so water can extract flavors in just 25-30 seconds. On the right, cold brew grind is like peppercorns—much less surface area, so you need 12-24 hours to extract the same flavors. Pour-over is right in the middle: looks like sand, brews in 3-4 minutes. [PAUSE]

[TRANSITION—10 sec]
But here's the catch: you can't just use any grind size with any method. Let's see why matching grind to method is critical. [CLICK]"
```

---

## Stage 7: Self-Check & Scoring

**Goal**: Evaluate the draft presentation using CHECKLIST.md and RUBRIC.md; refine if score < 75.

**Actions**:
1. Run **CHECKLIST.md** to verify all required elements are present
2. Score using **RUBRIC.md** (10 items, 0-10 points each, total 100)
3. Identify **top 3 lowest-scoring items** and write improvement actions
4. If **total score < 75**, apply improvements and re-score (max 2 iterations)
5. If **score ≥ 75**, proceed to Stage 8

**Output**:
- Completed checklist
- Rubric scorecard with item-by-item scores
- Improvement action log (if score < 75)

**Example**:
```
ITERATION 1 SCORECARD:
1. Goal Clarity: 9/10 ✓
2. Story Structure: 8/10 ✓
3. Slide Assertions: 6/10 ⚠️ (some headings still topic-labels)
4. Evidence Quality: 7/10 ⚠️ (missing data sources)
5. Chart Fit: 8/10 ✓
6. Visual & Accessibility: 9/10 ✓
7. Coherence & Transitions: 7/10 ⚠️ (abrupt jump between slides 7-8)
8. Speakability: 8/10 ✓
9. Deliverables Complete: 9/10 ✓
10. Robustness: 8/10 ✓
TOTAL: 79/100 ✓ (≥75, ready to deliver)

If score was 72/100:
TOP 3 WEAKNESSES:
- Item 3 (Slide Assertions): Convert remaining topic-label headings to assertion sentences
- Item 4 (Evidence Quality): Add source citations to all charts
- Item 7 (Coherence): Add transition slide between temperature and time sections
IMPROVEMENT ACTIONS:
1. Revise slides 5, 9, 11 headings to full assertion sentences
2. Add footer citations to all charts (e.g., "Source: National Coffee Association, 2023")
3. Insert transition slide: "Now that we've mastered grind and temperature, let's tackle the third variable: time"
RE-SCORE after improvements → 78/100 ✓ (ready to deliver)
```

---

## Stage 8: Package Deliverables

**Goal**: Generate all final output files in `/output/` directory. If orchestration mode is active, automatically coordinate data synthesis, chart generation, PPTX creation, and chart insertion to deliver a complete presentation-ready PowerPoint file.

### Stage 8a: Package Markdown Deliverables (Baseline)

**Actions**:
1. Create `/output/slides.md`:
   - Markdown slides with YAML frontmatter for Marp/Reveal.js
   - Assertion-style headings
   - Bullet points and chart placeholders
   - Speaker notes in HTML comments `<!-- NOTES: ... -->`
2. Create `/output/notes.md`:
   - Full speaker script with timing
   - Assumptions & limitations section
   - Troubleshooting Q&A
3. Create `/output/refs.md`:
   - All data sources and citations
   - Chart data specifications (for synthesis or user reference)
   - External references and further reading
4. Create `/output/README.md`:
   - File structure explanation
   - Conversion instructions (if manual mode)
   - Customization guide

**Output**: Markdown deliverables ready for manual conversion or orchestration processing

---

### Stage 8b: Synthesize Data (Orchestration Mode Only)

**Condition**: Activate if:
- Orchestration mode is ON
- refs.md specifies data requirements (chart data specs present)
- User did NOT upload data files

**Actions**:
1. Parse `/output/refs.md` for data specifications:
   - Example: "Solar LCOE: $0.38/kWh (2010) → $0.05/kWh (2024), -87% decline"
2. Generate synthetic CSV files matching specs:
   - Use realistic trends (linear/exponential/step function)
   - Add noise (±3-5%) for authenticity
   - Follow authoritative source calibration (IRENA/IEA/IPCC/WHO)
3. Save to `/output/data/*.csv`
4. Document synthesis methodology in `/output/data/README.md`

**Output**: `/output/data/*.csv` files ready for chart generation

**Fallback**: If pandas unavailable, skip to Stage 8c with user-provided data only

---

### Stage 8c: Generate Charts (Orchestration Mode Only)

**Condition**: Activate if orchestration mode is ON

**Actions**:
1. Create comprehensive `generate_charts.py` script:
   - Read CSV data from `/output/data/` or user-provided files
   - Generate all PNG charts using matplotlib
   - Apply STYLE-GUIDE.md color palette and fonts
   - Save to `/output/assets/*.png` (180 DPI, optimized)
2. Execute chart generation:
   ```bash
   cd /output
   uv run --with pandas --with matplotlib generate_charts.py
   ```
3. Verify all chart files exist and meet quality standards:
   - File size: 40-150KB per chart
   - Dimensions: ~10×6 inches
   - Labels readable, colors distinct

**Output**: `/output/assets/*.png` (8-12 charts, publication-quality)

**Fallback**: If matplotlib unavailable, deliver PPTX with text placeholders + standalone script + installation instructions

---

### Stage 8d: Dual-Path PPTX Creation (Orchestration Mode Only)

**Condition**: Activate if orchestration mode is ON

**Strategy**: Launch TWO parallel sub-agents to generate PPTX using different technologies:
- **Path A (Marp CLI)**: Native Marp export, preserves Marp themes/directives
- **Path B (document-skills:pptx)**: Anthropic's PowerPoint skill, reveal.js-based

**Why Dual-Path?** slides.md contains Marp-specific syntax that document-skills:pptx cannot parse. Running both paths ensures compatibility and gives users styling choice.

**Actions**:
1. **Launch Path A** (Marp CLI export) via Task tool:
   - Check/install Marp CLI: `npm install -g @marp-team/marp-cli`
   - Export: `marp slides.md -o presentation_marp.pptx --allow-local-files --html`
   - Output: `/output/presentation_marp.pptx` (Marp-styled, 200-500KB)

2. **Launch Path B** (document-skills:pptx) via Task tool (parallel):
   - Pre-process slides.md: strip Marp YAML frontmatter and directives
   - Convert to PPTX using document-skills:pptx
   - Output: `/output/presentation_pptx.pptx` (reveal.js-styled, 200-300KB)

3. **Parallel execution**: Send single message with TWO Task calls

4. Quality checks (per path):
   - File exists and opens correctly
   - Slide count matches slides.md
   - Speaker notes embedded

**Output**:
- Best case: Both PPTX files (user chooses preferred styling)
- Partial: One PPTX + failure documentation
- Fallback: Markdown + pandoc conversion instructions

**Detailed specs**: See `references/ORCHESTRATION_PPTX.md` Stage 8d

---

### Stage 8e: Dual-Path Chart Insertion (Orchestration Mode Only)

**Condition**: Activate if orchestration mode is ON and at least one PPTX from Stage 8d exists

**Strategy**: Insert PNG charts into existing PPTX file(s) using path-specific methods

**Actions**:
1. **Path A chart insertion** (if presentation_marp.pptx exists):
   - Method: python-pptx library direct manipulation
   - Script: `insert_charts_marp.py` (auto-generated)
   - Output: `/output/presentation_marp_with_charts.pptx`

2. **Path B chart insertion** (if presentation_pptx.pptx exists):
   - Method: document-skills:pptx editing via Task tool
   - Insert 8 charts at standard positions (5.5", 2.0", width 4.0")
   - Output: `/output/presentation_pptx_with_charts.pptx`

3. **Parallel execution**: If both PPTX files exist, launch both insertion tasks simultaneously

4. Chart-to-slide mapping:
   - Parse slides.md for placeholders (`**[占位图表]**:`)
   - Map to slide numbers (typically slides 3-10)
   - Standard positioning: right column layout

5. Final quality checks:
   - File size increase: 300-600KB per PPTX (charts embedded)
   - Visual verification: all charts visible, no overlaps

**Output**:
- Best case: `presentation_marp_with_charts.pptx` + `presentation_pptx_with_charts.pptx` ✓ **BOTH COMPLETE**
- Partial: One complete PPTX + one with placeholders + manual instructions
- Fallback: Base PPTX + separate chart files + assembly guide

**Detailed specs**: See `references/ORCHESTRATION_PPTX.md` Stage 8e

---

### Output Examples

**Manual Mode** (`/output/` structure):
```
/output/
├── slides.md (Markdown deck, 165 lines)
├── notes.md (Speaker script, 1200 words)
├── refs.md (Citations and data specs)
└── README.md (conversion instructions)
```

**Orchestration Mode - Dual-Path** (`/output/` structure):
```
/output/
├── slides.md (Markdown source, Marp-formatted, backup)
├── notes.md (Speaker script with assumptions)
├── refs.md (Citations and data sources)
├── data/
│   ├── cost_trend.csv (synthetic data)
│   ├── capacity_growth.csv
│   └── README.md (synthesis methodology)
├── assets/
│   ├── cost_trend.png (180 DPI)
│   ├── capacity_growth.png
│   └── employment.png (8-12 charts total)
├── presentation_marp.pptx (intermediate, 210KB)
├── presentation_marp_with_charts.pptx ✓ FINAL A (557KB, Marp-styled)
├── presentation_pptx.pptx (intermediate, 200KB)
├── presentation_pptx_with_charts.pptx ✓ FINAL B (543KB, document-skills styled)
├── generate_charts.py (chart generation script)
├── insert_charts_marp.py (Marp insertion script)
└── README.md (usage guide + styling comparison)
```

**Note**: Both FINAL files contain identical content with different styling. Users can choose their preferred version or compare both.

**Note**: For orchestration implementation details, see:
- Overview and activation logic: `references/ORCHESTRATION_OVERVIEW.md`
- Data synthesis & chart generation: `references/ORCHESTRATION_DATA_CHARTS.md`
- PPTX creation & chart insertion: `references/ORCHESTRATION_PPTX.md`

---

## Stage 9: Reuse Instructions

**Goal**: Empower users to customize and extend the presentation.

**Actions**:
1. Append "5-Step Reuse Guide" to `/output/notes.md`:
   - **Step 1**: Replace placeholder charts with your own data (use chartkit.py)
   - **Step 2**: Customize color palette in STYLE-GUIDE.md (find/replace hex codes)
   - **Step 3**: Add your logo to cover slide and footer
   - **Step 4**: Adjust speaker notes for your personal style
   - **Step 5**: Export to your preferred format (PPTX, PDF, Google Slides)
2. Include **chartkit.py usage examples** for common chart types
3. Provide **Markdown-to-PPTX conversion commands** (if PPTX wasn't auto-generated)

**Output**:
- Enhanced `/output/notes.md` with reuse guide
- Example commands for customization

**Example Reuse Guide**:
```
## 5-Step Guide: Customize This Presentation

### Step 1: Replace Placeholder Charts with Your Data
If you have real data, use chartkit.py to generate updated charts:
```bash
python scripts/chartkit.py \
  --data your_data.csv \
  --type line \
  --x month \
  --y revenue profit \
  --out output/assets \
  --filename revenue_trend.png \
  --title "Monthly Revenue & Profit"
```

### Step 2: Customize Colors
Open STYLE-GUIDE.md and replace these hex codes:
- Accent: #2563EB → your brand blue
- Emphasis: #DC2626 → your brand red
Then find/replace in slides.md

### Step 3: Add Your Logo
Insert logo file in `/output/assets/logo.png`
Add to slides.md cover slide: `![Logo](assets/logo.png)`

### Step 4: Personalize Speaker Notes
Edit `/output/notes.md` to match your speaking style
Add personal anecdotes or examples

### Step 5: Export to PowerPoint
If python-pptx is available:
```bash
python -m pypandoc slides.md -o presentation.pptx
```
Or use online converters: https://www.marp.app/
```

---

## Workflow Summary Checklist

Use this checklist to track progress through all 9 stages:

- [ ] **Stage 0**: Archive input (original request, assumptions, defaults)
- [ ] **Stage 1**: Structure goals (one-sentence goal + CTA)
- [ ] **Stage 2**: Storyline (pyramid structure: conclusion → reasons → evidence)
- [ ] **Stage 3**: Outline & slide titles (12-15 slides with assertion headings)
- [ ] **Stage 4**: Evidence & charts (chart selection + chartkit.py or placeholders)
- [ ] **Stage 5**: Layout & accessibility (STYLE-GUIDE + WCAG AA compliance)
- [ ] **Stage 6**: Speaker notes (45-60 sec per slide, natural language)
- [ ] **Stage 7**: Self-check & scoring (CHECKLIST + RUBRIC, score ≥ 75)
- [ ] **Stage 8**: Package deliverables (slides.md, notes.md, refs.md, assets/)
- [ ] **Stage 9**: Reuse instructions (5-step customization guide)

---

**Next Steps**: After completing all stages, proceed to final validation with CHECKLIST.md and delivery to user.
