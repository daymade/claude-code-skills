# PPT Quality Scoring Rubric

> **Purpose**: Systematically evaluate presentation quality and identify areas for improvement. A score ≥ 75/100 is required before delivery. If score < 75, refine the weakest items and re-score (max 2 iterations).

---

## Scoring System

- **Total Score**: 100 points (10 items × 10 points each)
- **Passing Threshold**: ≥ 75 points
- **Rating Scale** (per item):
  - **9-10**: Excellent (exceeds expectations)
  - **7-8**: Good (meets expectations)
  - **5-6**: Acceptable (minor improvements needed)
  - **3-4**: Weak (significant improvements required)
  - **0-2**: Poor (fundamental issues, must fix)

---

## 1. Goal Clarity (0-10 points)

**What**: Are the audience, objective, and call-to-action (CTA) clearly defined and documented?

**Scoring Criteria**:
- **10**: Audience, objective, and CTA explicitly stated and tailored; assumptions documented
- **8**: Audience and objective clear; CTA present but could be more specific
- **6**: Audience/objective vague; CTA generic (e.g., "let's discuss")
- **4**: Missing audience definition or objective; no clear CTA
- **2**: Presentation lacks clear purpose or intended action

**How to Check**:
- Review INTAKE.md responses and archive.txt
- Check final slide for specific CTA (not "Thank you" or "Questions?")
- Verify speaker notes mention audience and goal

**Example Scores**:
- **10**: "After this 15-minute presentation, coffee enthusiasts will try at least one new brewing technique within the next week."
- **6**: "This presentation is about coffee brewing for people interested in coffee."
- **2**: "Talk about coffee."

---

## 2. Story Structure (0-10 points)

**What**: Is the Pyramid Principle applied? (One conclusion → 3-5 first-level reasons → evidence)

**Scoring Criteria**:
- **10**: Clear pyramid structure; conclusion upfront; logical flow from reasons to evidence
- **8**: Pyramid structure present but hierarchy could be clearer
- **6**: Some structure but not consistently pyramid-style (e.g., conclusion buried at end)
- **4**: Scattered points without clear logical connection
- **2**: No discernible structure; random order

**How to Check**:
- Review storyline in archive.txt or WORKFLOW Stage 2 output
- Verify cover slide states main conclusion
- Check that 3-5 body sections support the conclusion
- Ensure evidence supports reasons (not random facts)

**Example Scores**:
- **10**: Cover: "Master three variables for great coffee" → Sections: Grind / Temp / Time → Each with 2-3 evidence slides
- **6**: Conclusion at end; sections exist but don't clearly support a single main point
- **2**: Slides jump between topics with no connective thread

---

## 3. Slide Assertions (0-10 points)

**What**: Are slide headings assertion sentences (testable claims), not topic labels?

**Scoring Criteria**:
- **10**: All slide headings are complete, testable assertion sentences
- **8**: Most headings are assertions; 1-2 topic labels remain
- **6**: Mix of assertions and topic labels (50/50)
- **4**: Mostly topic labels with few assertions
- **2**: All headings are topic labels (e.g., "Revenue", "Background", "Methodology")

**How to Check**:
- Review slide titles in slides.md
- Test: Can you agree/disagree with the heading? (If yes → assertion; if no → topic label)
- ✅ Assertion: "Finer grind size extracts flavors faster"
- ❌ Topic label: "Grind Size"

**Example Scores**:
- **10**: Every slide heading is a complete sentence making a claim
- **6**: Half are assertions ("Revenue grew 35%") and half are topics ("Q3 Results")
- **2**: All headings are one-word or topic-style ("Introduction", "Conclusion")

---

## 4. Evidence Quality (0-10 points)

**What**: Is evidence sufficient, credible, and properly cited?

**Scoring Criteria**:
- **10**: All claims backed by data/examples/citations; sources cited; units/methodology clear
- **8**: Most claims have evidence; minor gaps in citations or methodology
- **6**: Some claims lack evidence; sources missing or vague
- **4**: Many unsupported claims; no citations; unclear data provenance
- **2**: Assertions without any evidence or support

**How to Check**:
- Verify each assertion slide has chart/table/example/case study
- Check footer for source citations (e.g., "Source: XYZ, 2024")
- Confirm data units, time ranges, and methodology are specified
- Look for placeholder charts with "Data required: [fields]" if data unavailable

**Example Scores**:
- **10**: "68% report bad cup experiences (Source: NCA 2024 Survey, n=1,200 home brewers)"
- **6**: "Most people have bad coffee sometimes" (no data, no source)
- **2**: "Coffee is important" (pure opinion, no evidence)

---

## 5. Chart Fit (0-10 points)

**What**: Are charts correctly selected, labeled, and easy to read?

**Scoring Criteria**:
- **10**: Chart type matches data/message (per VIS-GUIDE); axes, units, source, alt text all present
- **8**: Chart type correct; minor labeling gaps (e.g., missing unit or source)
- **6**: Chart type suboptimal (e.g., pie chart with 7 slices); some labels missing
- **4**: Wrong chart type for data; poor labeling; hard to interpret
- **2**: No charts, or charts are misleading/unreadable

**How to Check**:
- Review chart selection against VIS-GUIDE.md Chart Selection Dictionary
- Verify all charts have: axis labels, units, data source, alt text
- Check readability: Can you understand the chart in 5 seconds?

**Example Scores**:
- **10**: Line chart for time series, properly labeled, source cited, alt text provided
- **6**: Bar chart OK but Y-axis missing unit; no source citation
- **2**: 3D exploded pie chart with 10 slices and no labels

---

## 6. Visual & Accessibility (0-10 points)

**What**: Does the design meet WCAG AA standards and STYLE-GUIDE specs?

**Scoring Criteria**:
- **10**: Contrast ≥4.5:1 (text) / ≥3:1 (UI); font sizes ≥18pt body / ≥34pt heading; white space ≥40%; alt text present
- **8**: Minor accessibility issues (e.g., one chart with 4.2:1 contrast)
- **6**: Multiple contrast or font size issues; some alt text missing
- **4**: Poor contrast (<3:1), tiny fonts (<14pt), cluttered layout
- **2**: Unreadable (light gray on white, <12pt fonts, no alt text)

**How to Check**:
- Use WebAIM contrast checker on text/background combos
- Measure font sizes (headings ≥34pt, body ≥18pt)
- Estimate white space (aim for 40-50% empty)
- Verify alt text for all images/charts
- Check colorblind-friendliness (use simulator)

**Example Scores**:
- **10**: Dark text (#1F2937) on white, 36pt headings, 20pt body, 45% white space, all alt text present
- **6**: Some 16pt body text, one chart missing alt text, 25% white space (crowded)
- **2**: Light gray text on white, 12pt font, no margins, no alt text

---

## 7. Coherence & Transitions (0-10 points)

**What**: Do slides flow logically with smooth chapter and page transitions?

**Scoring Criteria**:
- **10**: Clear section dividers; speaker notes include transitions; logical progression
- **8**: Good flow overall; minor abrupt jumps
- **6**: Some disjointed transitions; missing section dividers
- **4**: Slides feel disconnected; unclear how one leads to next
- **2**: Random order; no transitions or connective tissue

**How to Check**:
- Review speaker notes for transition phrases (e.g., "Now that we've covered X, let's explore Y")
- Check for section divider slides between major chapters
- Verify table of contents matches actual slide sequence

**Example Scores**:
- **10**: Section dividers present; every speaker note ends with "This leads us to [next topic]..."
- **6**: Flow is OK but one abrupt jump from "Problem" to "Conclusion" skipping "Solution"
- **2**: Slides seem shuffled; no clear reason for order

---

## 8. Speakability (0-10 points)

**What**: Are speaker notes natural, well-paced (45-60 sec/slide), and easy to deliver?

**Scoring Criteria**:
- **10**: All notes 45-60 sec; natural spoken language; structured (opening → assertion → evidence → transition)
- **8**: Most notes well-paced; minor awkward phrasing
- **6**: Some notes too long (>90 sec) or too short (<30 sec); some written-style language
- **4**: Many notes poorly paced; reads like an essay, not speech
- **2**: No speaker notes, or notes are bullet-point lists (not full script)

**How to Check**:
- Read notes aloud and time them
- Listen for natural speech patterns (contractions, questions, pauses)
- Verify structure: opening hook → core assertion → evidence walkthrough → transition

**Example Scores**:
- **10**: "Now, here's the key insight: finer grind means more surface area. Think of it like sugar—powdered sugar dissolves instantly, while sugar cubes take forever. [PAUSE] Let's see how this plays out across five grind sizes..."
- **6**: "The slide shows five grind sizes ranging from espresso to cold brew. Each has different particle size." (too dry, too short)
- **2**: "• Espresso grind • Pour-over grind • French press grind" (bullet list, not script)

---

## 9. Deliverables Complete (0-10 points)

**What**: Are all required output files present and correctly formatted?

**Scoring Criteria**:
- **10**: All files present and correct: slides.md, notes.md, refs.md, assets/*.png (if applicable), README.md
- **8**: All core files present; minor formatting issues or missing README
- **6**: Missing one deliverable (e.g., refs.md) or major formatting issue
- **4**: Missing multiple deliverables or files are incomplete
- **2**: Only partial output (e.g., slides.md exists but no notes or charts)

**How to Check**:
- Verify `/output/` directory contains:
  - `slides.md` (Markdown slides with YAML frontmatter, speaker notes)
  - `notes.md` (Full speaker script + assumptions section)
  - `refs.md` (Citations and sources)
  - `assets/*.png` (charts, if data was provided)
  - `README.md` (explains file structure)
  - `presentation.pptx` (optional, if python-pptx available)

**Example Scores**:
- **10**: All 5-6 files present, properly formatted, no broken links
- **6**: Missing refs.md or README.md; one broken chart image link
- **2**: Only slides.md exists; everything else missing

---

## 10. Robustness (0-10 points)

**What**: Are gaps/assumptions documented, and fallback plans provided?

**Scoring Criteria**:
- **10**: All assumptions documented in notes.md; placeholders for missing data include field lists; next steps clear
- **8**: Most assumptions noted; minor gaps in fallback plans
- **6**: Some assumptions undocumented; placeholder charts lack detail
- **4**: Many assumptions hidden; no guidance for missing data
- **2**: Assumptions concealed; no acknowledgment of limitations

**How to Check**:
- Review "Assumptions & Limitations" section in notes.md
- Check placeholder charts have "Data required: [field list]"
- Verify next steps or follow-up actions are mentioned (if applicable)

**Example Scores**:
- **10**: "Assumptions: (1) Used default 15-min duration (user did not specify). (2) No data provided for extraction curves; placeholder included with required fields: temperature_f, extraction_pct, time_sec."
- **6**: Assumptions partially noted but missing some; placeholders generic ("Add chart here")
- **2**: No mention of assumptions; missing data silently ignored

---

## Scoring Workflow

### Step 1: Initial Scoring

1. Review the presentation against all 10 criteria
2. Assign 0-10 points for each item
3. Calculate total score (sum of 10 items)

**Example Initial Scorecard**:
```
1. Goal Clarity: 9/10 ✓
2. Story Structure: 8/10 ✓
3. Slide Assertions: 6/10 ⚠️
4. Evidence Quality: 7/10 ⚠️
5. Chart Fit: 8/10 ✓
6. Visual & Accessibility: 9/10 ✓
7. Coherence & Transitions: 7/10 ⚠️
8. Speakability: 8/10 ✓
9. Deliverables Complete: 9/10 ✓
10. Robustness: 8/10 ✓
────────────────────────
TOTAL: 79/100 ✓ (≥75, ready to deliver)
```

---

### Step 2: If Score < 75, Identify Top 3 Weaknesses

1. Sort items by score (ascending)
2. Identify the **3 lowest-scoring items**
3. Write specific improvement actions for each

**Example (if total was 72/100)**:
```
TOP 3 WEAKNESSES:
1. Item 3 (Slide Assertions): Score 5/10
   - Problem: Slides 4, 7, 11 use topic labels ("Grind Size", "Temperature")
   - Action: Revise to assertion sentences:
     • Slide 4: "Finer grind size extracts flavors faster and more completely"
     • Slide 7: "Water between 195-205°F produces balanced, full-bodied coffee"
     • Slide 11: "Simple equipment upgrades ensure consistent results"

2. Item 4 (Evidence Quality): Score 6/10
   - Problem: Missing source citations on 3 charts; no methodology note
   - Action:
     • Add footer to charts: "Source: National Coffee Association, 2024"
     • Add methodology note in refs.md: "Survey n=1,200 home brewers, margin of error ±3%"

3. Item 7 (Coherence & Transitions): Score 6/10
   - Problem: Abrupt jump from Slide 8 (temperature) to Slide 9 (time); missing section divider
   - Action:
     • Insert transition slide: "Now that we've mastered grind and temperature, let's tackle the third variable: time"
     • Update speaker notes for Slide 8 to bridge: "...and this brings us to our final variable."
```

---

### Step 3: Apply Improvements & Re-Score

1. Make the improvements
2. Re-score all 10 items
3. If new total ≥ 75 → **deliver**
4. If new total < 75 → repeat Step 2-3 (max 2 iterations total)

**Example Re-Score**:
```
1. Goal Clarity: 9/10 ✓
2. Story Structure: 8/10 ✓
3. Slide Assertions: 9/10 ✓ (improved from 5)
4. Evidence Quality: 8/10 ✓ (improved from 6)
5. Chart Fit: 8/10 ✓
6. Visual & Accessibility: 9/10 ✓
7. Coherence & Transitions: 8/10 ✓ (improved from 6)
8. Speakability: 8/10 ✓
9. Deliverables Complete: 9/10 ✓
10. Robustness: 8/10 ✓
────────────────────────
TOTAL: 84/100 ✓✓ (exceeds threshold, ready to deliver)
```

---

## Iteration Limits

- **Max Iterations**: 2 rounds of improvements
- **Why Limit**: Avoid infinite refinement loop; deliver practical value quickly
- **If Still < 75 After 2 Rounds**:
  - Deliver with clear disclaimer: "This presentation scores [X]/100. The following items need further work: [list weakest 3 items]."
  - Provide improvement roadmap in notes.md

---

## Common Score Ranges & Interpretations

| Score Range | Interpretation | Typical Issues |
|-------------|----------------|----------------|
| 90-100 | Exceptional | Exceeds all criteria; publication-ready |
| 75-89 | Good (passing) | Minor polish needed; ready to present |
| 60-74 | Needs improvement | Missing some assertions, evidence, or accessibility fixes |
| 45-59 | Weak | Major structure or clarity issues; requires significant rework |
| 0-44 | Poor | Fundamental problems; restart from WORKFLOW Stage 2 |

---

## Self-Evaluation Checklist (Quick Version)

Use this quick checklist before full scoring:

- [ ] **Goal**: Audience, objective, CTA documented and clear?
- [ ] **Structure**: Pyramid (conclusion → reasons → evidence)?
- [ ] **Assertions**: All headings are testable sentences?
- [ ] **Evidence**: All claims have data/examples/citations?
- [ ] **Charts**: Correct type, fully labeled, source cited?
- [ ] **Accessibility**: Contrast ≥4.5:1, fonts ≥18pt, alt text?
- [ ] **Transitions**: Smooth flow, section dividers, speaker notes?
- [ ] **Speakability**: Notes 45-60 sec, natural language?
- [ ] **Deliverables**: slides.md, notes.md, refs.md, assets/?
- [ ] **Robustness**: Assumptions documented, placeholders detailed?

If all checkboxes are ✓, score is likely ≥ 75.

---

## Final Delivery Criteria

**Before delivering to user, confirm**:
1. Total score ≥ 75/100 (or 2 improvement iterations completed)
2. All deliverables in `/output/` directory
3. Assumptions and limitations documented in notes.md
4. If score < 75, include improvement roadmap

**Delivery Message Template**:
```
✅ Presentation ready!

SCORE: [X]/100 (threshold: 75)
QUALITY: [Exceptional / Good / Needs improvement]

DELIVERABLES:
- /output/slides.md (Markdown deck, [N] slides)
- /output/notes.md (Speaker script + assumptions)
- /output/refs.md (Citations and sources)
- /output/assets/ ([N] charts)
- /output/presentation.pptx (if available)

NEXT STEPS:
- Review speaker notes and adjust for your personal style
- Replace placeholder charts with your data (use chartkit.py if needed)
- Customize colors/fonts per STYLE-GUIDE.md

[If score < 75: Add improvement roadmap here]
```

---

**Next Steps**: Once scoring is complete and score ≥ 75, proceed to Stage 8 (Package Deliverables) in WORKFLOW.md.
