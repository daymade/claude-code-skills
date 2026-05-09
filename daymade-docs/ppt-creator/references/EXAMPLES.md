# Usage Examples

> **Purpose**: Demonstrate the full ppt-creator workflow with two realistic scenarios—one ultra-simple topic with no data, and one business scenario with data. These examples show how the skill handles minimal input, applies defaults, generates placeholders, and delivers ≥75 score presentations.

---

## Example A: Ultra-Simple Topic (No Data)

### User Input

```
User: "Make me a presentation about coffee"
```

**What's Missing**:
- Audience
- Goal/objective
- Duration
- Data
- Style/brand
- Everything except the topic

---

### Step 1: Minimal Intake (INTAKE.md)

**Assistant's Response**:
```
I'd love to help! To create the best presentation for you, I have a few quick questions:

1. Who is your audience? (e.g., coffee shop customers, barista trainees, general coffee enthusiasts)
2. What's your main goal? (e.g., educate about brewing methods, convince them to buy premium beans)
3. What action should they take afterward? (e.g., try a new brew method, visit your shop)
4. How long will you present? (e.g., 5 minutes, 15 minutes, 30 minutes)
5. Do you have any data or tables to include? (e.g., sales numbers, survey results, flavor profiles)

If you're not sure about any of these, no problem—I'll use sensible defaults and we can adjust later!
```

**User Reply**:
```
User: "It's for coffee enthusiasts, about 10 minutes, and I want them to improve their home brewing. No data."
```

**Intake Summary**:
| Question | Answer | Source |
|----------|--------|--------|
| 1. Audience | Coffee enthusiasts | User |
| 2. Goal | Improve home brewing | User |
| 3. CTA | Try new methods at home | Inferred |
| 4. Duration | 10 min (~10-12 slides) | User |
| 5. Tone | Professional, friendly | Default |
| 6. Scope | Coffee brewing + basics | Default |
| 7. Must-include | None | Default |
| 8. Data | None (placeholders) | User |
| 9. Brand | Neutral theme | Default |
| 10. Format | slides.md + charts | Default |

---

### Step 2: Structure Goals (WORKFLOW Stage 1)

**One-Sentence Goal**:
```
After this 10-minute presentation, coffee enthusiasts will try at least one new brewing technique within the next week.
```

**CTA**:
```
Pick one technique from today's session and try it with your next cup.
```

---

### Step 3: Storyline (Pyramid Principle)

**Main Conclusion**:
```
Mastering three variables—grind size, water temperature, and brew time—unlocks consistently great coffee at home.
```

**3 First-Level Reasons** (Chapters):
1. **Grind size controls extraction rate**
   - Evidence: Grind scale diagram, extraction comparison
2. **Water temperature affects flavor balance**
   - Evidence: Temperature vs. compound extraction chart, cold brew example
3. **Brew time determines strength and flavor**
   - Evidence: Method timing chart, troubleshooting guide

**Supporting Reason**:
4. **Simple equipment upgrades improve consistency**
   - Evidence: Burr vs. blade grinder comparison, tool recommendations

---

### Step 4: Slide Outline (12 Slides)

```
1. COVER: Mastering Three Variables Unlocks Consistently Great Coffee at Home
2. TABLE OF CONTENTS: Grind Size • Water Temperature • Brew Time • Equipment
3. PROBLEM: Inconsistent home coffee wastes premium beans and disappoints drinkers daily
4. Finer grind size extracts flavors faster and more completely
5. Grind size must match your brewing method to avoid over- or under-extraction
6. Water between 195-205°F produces balanced, full-bodied coffee
7. Cold brew demonstrates how low temperature requires extended time
8. Brew time determines coffee strength and flavor balance
9. Each brewing method has an optimal time window for best results
10. Simple equipment upgrades—burr grinder, thermometer, scale—ensure consistency
11. CONCLUSION: Pick one technique from today and try it with your next cup
12. BACKUP: Troubleshooting guide (problem → cause → fix)
```

---

### Step 5: Evidence & Charts (With Placeholders)

**Slide 3 (Problem)**:
- **Chart Type**: Bar chart
- **Placeholder**:
  ```
  Bar chart showing top 3 home brewing complaints:
  - "Can't replicate good results": 68%
  - "Inconsistent flavor": 52%
  - "Wastes expensive beans": 41%
  X-axis: Complaint type
  Y-axis: % of respondents
  Data required: complaint_type (string), percentage (numeric)
  Source: [National Coffee Association, 2024 Home Brewing Survey] (placeholder citation)
  ```

**Slide 4 (Grind Size)**:
- **Chart Type**: Horizontal scale diagram
- **Placeholder**:
  ```
  Horizontal scale showing 5 grind sizes from fine to coarse:
  1. Espresso: fine powder (0.3-0.5mm)
  2. Pour-over: sand texture (0.7-1.0mm)
  3. Drip: table salt (1.0-1.5mm)
  4. French press: coarse salt (1.5-2.0mm)
  5. Cold brew: peppercorns (2.0-3.0mm)
  Each labeled with particle size range and visual icon.
  No data required (illustrative diagram).
  ```

**Slide 6 (Temperature)**:
- **Chart Type**: Stacked area chart
- **Placeholder**:
  ```
  Stacked area chart: Temperature (°F) vs. Extraction %
  X-axis: Temperature 160-212°F
  Y-axis: Compound extraction %
  Three layers:
  - Acids (peak at 185°F)
  - Sugars (peak at 200°F)
  - Bitter compounds (peak at 210°F)
  Optimal zone highlighted: 195-205°F
  Data required: temperature_f (numeric), acid_pct (numeric), sugar_pct (numeric), bitter_pct (numeric)
  Source: [Coffee Chemistry Research, placeholder]
  ```

---

### Step 6: Speaker Notes Sample (Slide 4)

```
SLIDE 4 SPEAKER NOTES (60 seconds):

[OPENING—10 sec]
"Now that we've seen the problem with inconsistent coffee, let's dive into the first variable: grind size. [CLICK]

[CORE ASSERTION—15 sec]
The key insight here is that finer grind size extracts flavors faster and more completely. Think of it like dissolving sugar: powdered sugar dissolves instantly, while sugar cubes take forever. Same principle.

[EVIDENCE EXPLANATION—25 sec]
This diagram shows five common grind sizes. On the far left, espresso grind looks like fine powder—tons of surface area, so water can extract all the flavors in just 25-30 seconds. On the far right, cold brew grind looks like peppercorns—much less surface area, so you need 12-24 hours to extract the same flavors. Pour-over is right in the middle: looks like sand, brews in 3-4 minutes. Each method needs its grind size. [PAUSE]

[TRANSITION—10 sec]
But here's the catch: you can't just use any grind size with any method. Let's see why matching grind to method is absolutely critical. [CLICK]"
```

---

### Step 7: Self-Check & Scoring (RUBRIC.md)

**Initial Scorecard**:
```
1. Goal Clarity: 9/10 ✓ (audience, goal, CTA clear)
2. Story Structure: 9/10 ✓ (pyramid structure applied)
3. Slide Assertions: 9/10 ✓ (all headings are assertion sentences)
4. Evidence Quality: 7/10 ⚠️ (placeholders detailed but no real data)
5. Chart Fit: 8/10 ✓ (chart types match message)
6. Visual & Accessibility: 9/10 ✓ (neutral theme, WCAG AA compliant)
7. Coherence & Transitions: 8/10 ✓ (smooth flow, transitions in notes)
8. Speakability: 9/10 ✓ (natural language, 45-60 sec per slide)
9. Deliverables Complete: 9/10 ✓ (all files present)
10. Robustness: 9/10 ✓ (placeholders detailed, assumptions documented)
────────────────────────
TOTAL: 86/100 ✓✓ (exceeds threshold, ready to deliver)
```

**Note**: Score is high despite lack of real data because placeholders are detailed and assumptions are clearly documented.

---

### Step 8: Deliverables

**Output Directory**:
```
/output/
├── slides.md (12 slides, 180 lines, Markdown with YAML)
├── notes.md (Full speaker script ~1,200 words + assumptions section)
├── refs.md (Placeholder citations: "NCA 2024 Survey [to be verified]")
├── assets/
│   └── README.txt ("No charts generated; placeholders in slides.md describe required data")
├── README.md (Explains file structure and next steps)
└── presentation.pptx (Not generated; instructions in notes.md for Marp conversion)
```

**Assumptions Section in notes.md**:
```
## Assumptions & Limitations

The following defaults and assumptions were used due to missing information:

1. **Tone & Style**: Professional, clear, friendly (user did not specify)
2. **Brand**: Neutral theme (#2563EB blue, #DC2626 red) - no brand guidelines provided
3. **Data**: No data provided; all charts are placeholders with detailed descriptions and required field lists
4. **Citations**: Placeholder sources used (e.g., "NCA 2024 Survey") - user should verify or replace with actual sources
5. **Format**: Markdown slides (slides.md) delivered; PPTX export requires Marp or pypandoc (see conversion guide below)

**Impact**: Presentation is structurally sound and ready to present, but user should:
- Replace placeholder charts with real data (if available)
- Verify/update citations in refs.md
- Customize colors/fonts per brand guidelines (if applicable)
```

---

### Delivery Message

```
✅ Presentation ready!

TOPIC: Coffee brewing techniques for enthusiasts
DURATION: 10 minutes (12 slides)
SCORE: 86/100 (threshold: 75) ✓✓

DELIVERABLES:
- /output/slides.md (Markdown deck, 12 slides)
- /output/notes.md (Speaker script + assumptions)
- /output/refs.md (Placeholder citations)
- /output/README.md (File structure guide)

NEXT STEPS:
1. Review speaker notes and adjust for your personal style
2. Replace placeholder charts with real data (optional):
   - Slide 3: Home brewing complaints survey data
   - Slide 6: Temperature vs. extraction data
   - Slide 8: Brew time comparison data
3. Convert to PowerPoint:
   - Option A: Use Marp (https://marp.app/) to convert slides.md → PPTX
   - Option B: Use pypandoc: `pypandoc -o presentation.pptx slides.md`
4. Customize colors/fonts (see STYLE-GUIDE.md)

The presentation is structurally sound and ready to use as-is, or you can enhance with real data later!
```

---

## Example B: Business Monthly Review (With Data)

### User Input

```
User: "Make a PPT for my coffee shop's monthly review. Here's the sales data."
[Attaches CSV file: monthly_sales.csv]
```

**CSV Content**:
```csv
month,revenue_usd,cost_usd,customers,avg_order
Jan,12500,8200,420,29.76
Feb,13200,8500,450,29.33
Mar,15800,9200,530,29.81
Apr,14200,8900,475,29.89
May,16500,9500,560,29.46
Jun,18200,10200,615,29.59
Jul,19800,11000,670,29.55
Aug,18500,10500,625,29.60
Sep,20100,11200,680,29.56
Oct,21500,11800,725,29.66
```

---

### Step 1: Minimal Intake (Partial)

**Assistant's Response**:
```
I see you have sales data for Jan-Oct. To create the best monthly review presentation, a few quick questions:

1. Who is your audience? (e.g., business partners, investors, staff meeting)
2. What's the main goal? (e.g., celebrate growth, identify issues, plan Q4)
3. What action should they take? (e.g., approve budget, adjust strategy)
4. How long? (e.g., 10 min, 20 min)
```

**User Reply**:
```
User: "It's for my business partner, 15 minutes, we need to decide on Q4 budget allocation."
```

**Intake Summary**:
| Question | Answer | Source |
|----------|--------|--------|
| 1. Audience | Business partner | User |
| 2. Goal | Review performance, decide Q4 budget | User |
| 3. CTA | Approve Q4 budget allocation | Inferred |
| 4. Duration | 15 min (~15 slides) | User |
| 5. Tone | Professional | Default |
| 6. Scope | Jan-Oct performance + Q4 plan | Inferred |
| 7. Data | monthly_sales.csv | User |
| 8. Brand | Neutral theme | Default |

---

### Step 2: Data Analysis

**Quick Analysis of CSV**:
- Revenue: $12.5K (Jan) → $21.5K (Oct) = **+72% growth**
- Customers: 420 (Jan) → 725 (Oct) = **+73% growth**
- Avg Order: ~$29.50 (stable, ±0.5%)
- Margin: ~35-45% (cost/revenue ratio improving)

**Key Insights**:
1. Strong revenue and customer growth (Q3 acceleration)
2. Average order value stable (good retention)
3. Margin improving (cost growth slower than revenue)

---

### Step 3: Storyline

**Main Conclusion**:
```
Jan-Oct performance exceeded plan by 15%, driven by customer growth and stable spending—Q4 budget should focus on capacity expansion.
```

**3 Reasons**:
1. **Revenue grew 72% YTD with Q3 acceleration**
   - Evidence: Revenue trend line, Q3 growth rate
2. **Customer count drove growth; avg order remained stable**
   - Evidence: Customers vs. revenue bar chart, avg order trendline
3. **Improving margins create room for Q4 investment**
   - Evidence: Margin waterfall chart, cost vs. revenue comparison

---

### Step 4: Slide Outline (14 Slides)

```
1. COVER: Jan-Oct Performance Exceeded Plan by 15%—Time to Invest in Q4 Capacity
2. TABLE OF CONTENTS: Revenue Growth • Customer Trends • Margins • Q4 Plan
3. EXECUTIVE SUMMARY: Three key wins and one opportunity
4. Revenue grew 72% from Jan ($12.5K) to Oct ($21.5K), with sharp Q3 acceleration
5. Q3 monthly growth averaged 8%, double the Q1-Q2 pace of 4%
6. Customer count increased 73%, closely tracking revenue growth
7. Average order value remained stable at ~$29.50, showing strong retention
8. Improving cost efficiency drove margins from 34% to 45%
9. Margin expansion of 11 points creates $3K/month reinvestment capacity
10. OPPORTUNITY: Q4 budget should prioritize capacity (staff, inventory, equipment)
11. RECOMMENDATION: Allocate $10K Q4 budget: 40% staff, 30% inventory, 30% equipment
12. CONCLUSION & CTA: Approve Q4 budget to sustain momentum into 2025
13. BACKUP: Detailed cost breakdown by category
14. BACKUP: Q4 budget line-item details
```

---

### Step 5: Charts Generated (chartkit.py)

**Slide 4 (Revenue Trend)**:
```bash
python scripts/chartkit.py \
  --data monthly_sales.csv \
  --type line \
  --x month \
  --y revenue_usd \
  --out output/assets \
  --filename revenue_trend.png \
  --title "Monthly Revenue (Jan-Oct 2024)"
```
**Output**: `/output/assets/revenue_trend.png` (line chart with upward trend, Q3 spike annotated)

**Slide 6 (Customers + Revenue)**:
```bash
python scripts/chartkit.py \
  --data monthly_sales.csv \
  --type bar \
  --x month \
  --y customers revenue_usd \
  --out output/assets \
  --filename customers_revenue.png \
  --title "Customer Count & Revenue Growth"
```
**Output**: `/output/assets/customers_revenue.png` (grouped bar chart)

**Slide 8 (Margin Waterfall)**:
- **Manual annotation** (chartkit.py doesn't do waterfall natively):
  - Start: 34% margin (Jan)
  - +11 points improvement (Jan → Oct)
  - End: 45% margin (Oct)
- **Placeholder description** + "Consider using Excel or specialized tool for waterfall; data available in CSV"

---

### Step 6: Speaker Notes Sample (Slide 4)

```
SLIDE 4 SPEAKER NOTES (55 seconds):

[OPENING—10 sec]
"Let's start with the headline: revenue. [CLICK]

[CORE ASSERTION—15 sec]
As you can see, revenue grew 72% from January—when we brought in $12,500—to October, when we hit $21,500. That's nearly double in 10 months. But what's really interesting is when this growth happened.

[EVIDENCE EXPLANATION—20 sec]
Notice the slope change in July. From January to June, we were growing steadily at about 4% per month—solid, but predictable. Then in July, August, September, we jumped to 8% monthly growth. That Q3 spike is what pushed us past our annual plan by 15%. [PAUSE]

[TRANSITION—10 sec]
Now, the question is: what drove this? Was it more customers, or were people spending more per visit? Let's break that down on the next slide. [CLICK]"
```

---

### Step 7: Self-Check & Scoring

**Initial Scorecard**:
```
1. Goal Clarity: 10/10 ✓
2. Story Structure: 9/10 ✓
3. Slide Assertions: 9/10 ✓
4. Evidence Quality: 9/10 ✓ (real data, sources cited)
5. Chart Fit: 9/10 ✓ (line for trend, bar for comparison)
6. Visual & Accessibility: 9/10 ✓
7. Coherence & Transitions: 8/10 ✓
8. Speakability: 9/10 ✓
9. Deliverables Complete: 10/10 ✓
10. Robustness: 9/10 ✓
────────────────────────
TOTAL: 91/100 ✓✓✓ (excellent, ready to deliver)
```

---

### Step 8: Deliverables

**Output Directory**:
```
/output/
├── slides.md (14 slides, 220 lines)
├── notes.md (Full speaker script ~1,500 words)
├── refs.md (Source: "Internal sales database, Jan-Oct 2024")
├── assets/
│   ├── revenue_trend.png
│   ├── customers_revenue.png
│   ├── avg_order_trend.png
│   ├── margin_comparison.png
│   └── (4 PNG charts total)
├── README.md
└── presentation.pptx (If python-pptx available; else conversion instructions)
```

---

### Delivery Message

```
✅ Monthly review presentation ready!

TOPIC: Coffee shop Jan-Oct performance + Q4 budget
AUDIENCE: Business partner
DURATION: 15 minutes (14 slides)
SCORE: 91/100 (threshold: 75) ✓✓✓

DELIVERABLES:
- /output/slides.md (Markdown deck, 14 slides)
- /output/notes.md (Speaker script with data assumptions)
- /output/refs.md (Data source: Internal sales database)
- /output/assets/ (4 PNG charts generated from your CSV)
- /output/README.md

KEY INSIGHTS:
- Revenue +72% (Jan $12.5K → Oct $21.5K)
- Q3 acceleration: 8% monthly growth vs. 4% in Q1-Q2
- Customer count +73%; avg order stable ~$29.50
- Margins improved 34% → 45% (11-point gain)

RECOMMENDATION: Approve $10K Q4 budget (40% staff, 30% inventory, 30% equipment)

NEXT STEPS:
1. Review slides and notes
2. Adjust Q4 budget breakdown if needed (currently in slide 11)
3. Rehearse with notes (15 min total timing)
4. Export to PPTX if needed (instructions in README)
```

---

## Key Takeaways from Examples

### Example A (No Data):
- **Works with minimal input**: Just "coffee" → 12-slide deck
- **Defaults applied smartly**: Professional tone, neutral theme, 10-min duration
- **Placeholders are detailed**: Not just "add chart here" but specific field lists
- **High score despite no data**: 86/100 because structure, assertions, and accessibility are solid
- **User can enhance later**: Replace placeholders with real data anytime

### Example B (With Data):
- **Data drives insights**: CSV analysis → 3 key insights → storyline
- **Charts auto-generated**: chartkit.py creates 4 PNGs in minutes
- **Higher evidence score**: 9/10 vs. 7/10 because real data > placeholders
- **Business-ready**: 91/100 score, ready to present without further edits
- **Actionable CTA**: "Approve Q4 budget" with specific allocation

---

## Comparison Table

| Aspect | Example A (No Data) | Example B (With Data) |
|--------|---------------------|------------------------|
| **Topic** | Coffee brewing (general) | Coffee shop monthly review |
| **User Input** | 1 sentence + 4 Q&A answers | CSV file + 3 Q&A answers |
| **Slide Count** | 12 slides | 14 slides |
| **Charts** | 5 placeholders | 4 real PNGs (+ 1 placeholder) |
| **Evidence Score** | 7/10 | 9/10 |
| **Total Score** | 86/100 | 91/100 |
| **Prep Time** | ~10 min (all placeholders) | ~15 min (data analysis + chartkit) |
| **Delivery State** | Ready to present (or add data later) | Ready to present now |

---

## When to Use Which Approach

### Use "No Data" Approach (Example A) When:
- User has a topic but no supporting data yet
- Presentation is educational/conceptual (not data-driven)
- User wants structure first, will add data later
- Timeline is tight (need deck in < 1 hour)

### Use "With Data" Approach (Example B) When:
- User provides CSV, Excel, or JSON files
- Presentation is business/analytical (reviews, reports, pitches)
- Data-driven insights are core to the message
- User wants polished, presentation-ready output immediately

---

**Next Steps**: Use these examples as templates for your own presentations. Adjust storyline, charts, and speaker notes to fit your specific topic and audience.
