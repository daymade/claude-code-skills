# Data Visualization Selection & Labeling Standards

> **Purpose**: Choose the right chart type for your data and message, then label it properly for clarity and accessibility. This guide follows industry best practices from the Financial Times, Edward Tufte, and the Assertion-Evidence framework.

---

## Chart Selection Dictionary

Use this dictionary to match your **question/message** to the **best chart type**.

### 1. Change Over Time

**Question**: How has X changed over time?

**Chart Types**:
- **Line chart**: Best for continuous time series, 1-6 series max
  - Use case: Daily stock prices, monthly sales, annual growth
  - Avoid: >6 overlapping lines (use small multiples instead)
- **Area chart**: Emphasizes magnitude of change
  - Use case: Showing volume/scale in addition to trend
  - Stacked area: Show composition over time (max 4-5 categories)
- **Column/bar chart**: Discrete time periods with few data points
  - Use case: Quarterly results, yearly comparisons (≤12 bars)
  - Avoid: Too many bars (switch to line if >12 periods)
- **Step chart**: Values change at specific moments (not gradual)
  - Use case: Policy changes, price updates, version releases

**Heading Example**: "Monthly revenue grew 35% from Jan to Oct, with sharp acceleration in Q3"

---

### 2. Comparison / Ranking

**Question**: How do categories compare to each other?

**Chart Types**:
- **Horizontal bar chart**: Best for comparing categories (especially with long labels)
  - Use case: Ranking cities, products, departments by revenue/size
  - Advantage: Easy to read category names, natural left-to-right reading
- **Grouped bar chart**: Compare 2-3 metrics across categories
  - Use case: Revenue vs. Profit by product line
  - Avoid: >3 groups (gets cluttered)
- **Dot plot**: Precise value comparisons with minimal ink
  - Use case: Salary ranges, performance scores by team
- **Slope chart**: Compare two time points across categories
  - Use case: "Before vs. After" for 5-10 items

**Heading Example**: "Product A outsells Product B by 2:1 across all regions"

---

### 3. Distribution

**Question**: How is data spread out? Where do most values fall?

**Chart Types**:
- **Histogram**: Show frequency distribution of continuous data
  - Use case: Age distribution, income ranges, response times
  - Bins: 10-20 bins for most datasets
- **Box plot (box-and-whisker)**: Show median, quartiles, outliers
  - Use case: Compare distributions across groups (e.g., test scores by class)
  - Advantage: Compact, shows outliers clearly
- **Violin plot**: Combines box plot with density curve
  - Use case: Similar to box plot but shows shape of distribution
- **Strip plot / beeswarm**: Show individual data points
  - Use case: Small datasets (n < 100) where you want to show every point

**Heading Example**: "80% of customers spend between $20-$50, with a long tail of high spenders"

---

### 4. Correlation / Relationship

**Question**: How do two variables relate to each other?

**Chart Types**:
- **Scatter plot**: Show relationship between two continuous variables
  - Use case: Height vs. weight, ad spend vs. sales, price vs. demand
  - Enhancement: Add trend line with R² value
  - Color: Use 3rd variable for color (e.g., region, category)
  - Size: Use 4th variable for bubble size (→ bubble chart)
- **Connected scatter plot**: Show how relationship changes over time
  - Use case: GDP vs. life expectancy over decades
- **Heatmap**: Show correlation matrix for many variables
  - Use case: Feature correlations in ML, survey question relationships

**Heading Example**: "Higher ad spend correlates strongly with sales (R² = 0.82), but returns diminish above $10K/month"

---

### 5. Part-to-Whole / Composition

**Question**: What are the parts of the whole? How do they contribute?

**Chart Types**:
- **Stacked bar chart**: Show composition across categories
  - Use case: Revenue breakdown by product line, customer segments by region
  - Limit: Max 4-5 segments (more gets hard to read)
  - 100% stacked: Emphasize proportions instead of absolute values
- **Treemap**: Show hierarchical part-to-whole with nested rectangles
  - Use case: Budget allocation, file system sizes, market share
  - Advantage: Efficient use of space, shows hierarchy
- **Waterfall chart**: Show cumulative effect of sequential additions/subtractions
  - Use case: Starting revenue → costs → profit, bridge from last year to this year
- **Pie chart**: **Use sparingly** (only for 2-3 slices)
  - Acceptable: "52% approved, 48% rejected" (binary or near-binary)
  - Avoid: >3 slices, 3D effects, exploded slices
  - Better alternative: Stacked bar or treemap in most cases

**Heading Example**: "Payroll accounts for 60% of operating costs, twice the industry average"

---

### 6. Flow / Connection

**Question**: How do things move between states or groups?

**Chart Types**:
- **Sankey diagram**: Show flow quantities between nodes
  - Use case: Energy flow, budget allocation, customer journey stages
  - Limit: ≤10 nodes (gets messy beyond that)
- **Chord diagram**: Show connections between entities
  - Use case: Trade relationships, migration patterns
  - Avoid: >8 entities (overlapping connections get hard to trace)
- **Network graph**: Show relationships and clusters
  - Use case: Social networks, dependency graphs, org charts

**Heading Example**: "70% of website visitors from organic search convert directly to purchase without revisiting"

---

### 7. Geographic / Spatial

**Question**: How does data vary by location?

**Chart Types**:
- **Choropleth map**: Color regions by value (e.g., states, countries)
  - Use case: Sales by state, election results, disease prevalence
  - Color: Use sequential scale (light to dark) for continuous data; diverging scale (red-white-blue) for pos/neg
  - Avoid: Small regions with high variation (perception bias)
- **Dot density map**: Show individual occurrences as dots
  - Use case: Store locations, earthquake epicenters
- **Proportional symbol map**: Circle size = quantity at location
  - Use case: Population by city, sales by store location
- **Bar chart by region**: Alternative to choropleth when precise values matter
  - Use case: Revenue by country (sorted bar chart)

**Heading Example**: "California and Texas account for 45% of total US sales, with sparse coverage in the Midwest"

---

### 8. Deviation / Variance

**Question**: How far is each value from a reference point (mean, target, budget)?

**Chart Types**:
- **Diverging bar chart**: Show positive and negative deviations from zero/baseline
  - Use case: Above/below target, profit/loss by category
  - Color: Positive = green/blue, negative = red/orange
- **Bullet chart**: Compact way to show actual vs. target with context
  - Use case: KPI dashboards (actual, target, good/satisfactory/poor ranges)
- **Lollipop chart**: Similar to bar chart but with less ink
  - Use case: Deviations from average or baseline

**Heading Example**: "Q3 sales exceeded target by 12%, while Q1 and Q2 underperformed by 8% and 5%"

---

### 9. Magnitude (Absolute Sizes)

**Question**: How big is each value (without comparison)?

**Chart Types**:
- **Bar chart**: Standard choice for showing sizes/quantities
  - Orientation: Horizontal if category names are long; vertical for time series
- **Column chart**: Vertical bars for time-based or ordinal categories
- **Packed circles**: Alternative to bar chart (less precise but compact)
  - Use case: Market share visualization, bubble chart without x/y axes

**Heading Example**: "Product A generated $2.3M in Q4, our highest single-product quarter ever"

---

### 10. Table (When Not to Visualize)

**When to use a table instead of a chart**:
- **Precision matters**: Users need exact values, not just trends
- **Lookup use case**: Users will search for specific row/column intersections
- **Many dimensions**: >3 categorical dimensions (chart would be too complex)
- **Small dataset**: 3-10 data points (chart adds no value)
- **Mixed data types**: Text + numbers + categories

**Heading Example**: "Detailed cost breakdown by department and expense category"

---

## Chart Selection Quick Reference

| Your Goal | Question Pattern | Best Chart Type |
|-----------|------------------|-----------------|
| Show trend | How has X changed over time? | Line, area |
| Compare categories | Which is bigger/better? | Horizontal bar |
| Show distribution | Where do most values fall? | Histogram, box plot |
| Show correlation | How do X and Y relate? | Scatter plot |
| Show composition | What are the parts? | Stacked bar, treemap |
| Show flow | How do things move? | Sankey, chord |
| Show location | Where is it happening? | Choropleth map |
| Show deviation | How far from target? | Diverging bar, bullet |
| Show magnitude | How big is it? | Bar chart |
| Show exact values | Need precise lookup? | Table |

---

## Labeling & Annotation Standards

### Required Elements for All Charts

1. **Chart Title / Assertion Heading**
   - Use the slide's assertion sentence (not a generic "Revenue Chart")
   - Example: ✅ "Q3 revenue exceeded plan by 15% despite supply chain headwinds"
   - Example: ❌ "Quarterly Revenue Comparison"

2. **Axis Labels & Units**
   - X-axis: Label with variable name and unit (e.g., "Month (2024)")
   - Y-axis: Label with variable name and unit (e.g., "Revenue ($1000s)" or "Response Time (ms)")
   - Include units in axis label OR directly on values (e.g., "$5M" on bar)

3. **Data Labels** (when helpful)
   - Add value labels on bars/points if precision matters and space allows
   - Format consistently: "$1.2M" not "$1,234,567"
   - Avoid clutter: label only key points (e.g., first, last, min, max)

4. **Legend** (when multiple series)
   - Place legend close to data (top-right or right side preferred)
   - Order legend to match visual order (e.g., top-to-bottom matches line stacking)
   - Consider direct labeling (labels next to lines) instead of separate legend

5. **Data Source**
   - Always cite source in footer: "Source: [Organization, Year]" or "Data: [Source]"
   - If internal data: "Source: Internal analysis" or "Data: Company sales database"
   - If estimated/projected: "Projected values based on [methodology]"

6. **Time Range & Scope**
   - Specify date range: "Jan-Dec 2024" or "FY2023-2024"
   - Note exclusions: "Excluding returns and refunds" or "Top 10 markets only"

7. **Color Key** (for categorical colors)
   - If using color to encode categories, provide a legend or direct labels
   - Avoid relying solely on color (see Accessibility section below)

---

## Number Formatting Best Practices

### Decimal Places
- **Percentages**: 1 decimal place (e.g., "15.3%")
  - Exception: Very small percentages (e.g., "0.02%") may need 2 decimals
- **Currency**: Round to nearest appropriate unit
  - Small values: "$1,234.56"
  - Large values: "$1.2M" or "$5.6B" (not "$5,600,000,000")
- **Scientific values**: 2-3 significant figures (e.g., "3.14 × 10⁶")
- **Counts**: No decimals (e.g., "1,543 customers" not "1,543.0")

### Consistency
- **Within a chart**: Use same decimal places for all values
- **Across charts**: Use same units and rounding for same metric type
- **In tables**: Align decimal points vertically

### Large Numbers
- Use thousands separators: "1,234,567" (US/UK) or "1 234 567" (SI)
- Use abbreviations for very large numbers:
  - K = thousand (1,000)
  - M = million (1,000,000)
  - B = billion (1,000,000,000)
- Be consistent: Don't mix "1.2M" and "850K" with "950,000" in same chart

---

## Color & Accessibility

### WCAG 2.1 AA Contrast Requirements

**Text Contrast**:
- Normal text (< 18pt): Minimum 4.5:1 contrast ratio against background
- Large text (≥ 18pt or ≥ 14pt bold): Minimum 3:1 contrast ratio

**UI Components & Charts**:
- Chart elements (bars, lines, dots): Minimum 3:1 contrast against adjacent colors and background
- Active/inactive states: Must have 3:1 contrast difference

**Color Alone Insufficient**:
- Do NOT use color as the only way to convey information
- Add patterns, labels, or shapes for colorblind users
- Example: In a line chart with 3 series, use solid/dashed/dotted lines + color

### Colorblind-Friendly Palettes

**Safe Palettes** (work for deuteranopia, protanopia, tritanopia):
- **Categorical** (up to 5 colors):
  - Blue (#2563EB), Orange (#F97316), Green (#10B981), Purple (#8B5CF6), Gray (#6B7280)
  - Avoid: Red + Green together (most common colorblindness)
- **Sequential** (light to dark for continuous data):
  - Blues: #EFF6FF → #1E40AF
  - Greens: #ECFDF5 → #065F46
  - Oranges: #FFF7ED → #9A3412
- **Diverging** (for pos/neg or two extremes):
  - Blue-White-Orange: #1E40AF ↔ #FFFFFF ↔ #9A3412
  - Purple-White-Green: #7C3AED ↔ #FFFFFF ↔ #059669

**Test Tools**:
- Use online simulators (e.g., Coblis, Color Oracle) to preview charts in colorblind modes
- Check contrast ratios with WebAIM Contrast Checker or browser dev tools

---

## Chart Dos and Don'ts

### DO

✅ Start Y-axis at zero for bar/column charts (shows proportions honestly)
✅ Use horizontal bars when category names are long (easier to read)
✅ Sort bars by value (descending or ascending) unless there's a meaningful order (e.g., time, ranking)
✅ Annotate key data points (peaks, troughs, inflection points)
✅ Use a reference line or shaded area to show targets, benchmarks, or context
✅ Combine chart types when appropriate (e.g., bar + line combo for actuals + trend)
✅ Use small multiples for comparing many series (instead of overlapping 10+ lines)

### DON'T

❌ Use 3D effects, drop shadows, or gratuitous decoration (Tufte's "chartjunk")
❌ Use pie charts for >3 slices or when precise comparison matters (human eye bad at angles)
❌ Truncate Y-axis to exaggerate small differences (unless clearly marked)
❌ Use dual Y-axes unless absolutely necessary (confusing; prefer indexed scales)
❌ Overload with grid lines (use sparingly, light gray at most)
❌ Use default Excel/PowerPoint colors (often poor contrast and not colorblind-friendly)
❌ Put more than 5-7 series on one chart (use small multiples or filter to top N)

---

## Assertion-Evidence Chart Writing

**Principle**: The slide heading states the **conclusion** (assertion), and the chart provides the **evidence** to support it.

### Example Workflow

**Data**: Monthly sales Jan-Dec 2024 (trend upward)

**Bad Slide**:
- Heading: "Monthly Sales 2024"
- Chart: Line chart with no annotation
- Problem: Heading is a topic label, not a testable claim

**Good Slide**:
- Heading: "Monthly sales grew 35% in 2024, with sharp acceleration in Q3"
- Chart: Line chart with:
  - Jan-Dec 2024 on X-axis
  - Revenue ($1000s) on Y-axis
  - Annotation: "Q3 spike: +18% MoM" with arrow
  - Source footer: "Source: Internal sales database"
- Why it works: Heading makes a claim; chart proves it with specific visual evidence

---

## Advanced: When to Use Specialized Charts

### Waterfall Chart

**Use when**: Showing cumulative effect of sequential additions/subtractions

**Example**: "Starting revenue $1M → -$200K costs → -$100K returns → +$400K upsells = $1.1M final"

**Heading**: "Upsells and renewals offset a $300K loss from returns and operational costs"

---

### Sankey Diagram

**Use when**: Showing flow quantities between stages/categories

**Example**: Website traffic sources → landing pages → conversion outcomes

**Heading**: "Organic search drives 60% of traffic but only 30% of conversions, while email drives 15% of traffic but 40% of conversions"

**Limit**: ≤10 nodes (more gets visually overwhelming)

---

### Small Multiples (Faceted Charts)

**Use when**: Comparing the same chart across many categories or time periods

**Example**: Monthly sales trend for each of 12 regions (12 mini line charts in a grid)

**Heading**: "All regions show positive growth, but West and South outpace East and Midwest by 2×"

**Advantage**: Easier to compare than 12 overlapping lines on one chart

---

## Placeholder Charts (When Data Is Missing)

If user doesn't provide data, create a **placeholder description** with:

1. **Chart type**: "Line chart" / "Stacked bar chart" / "Scatter plot"
2. **Axes & variables**: "X-axis: Month (Jan-Dec), Y-axis: Revenue ($)"
3. **Expected pattern**: "Upward trend with Q3 spike"
4. **Required data fields**: "Need: month, revenue_usd, optional: target_revenue"
5. **Annotation points**: "Label Q3 peak, show +35% YoY growth"

**Example**:
```
PLACEHOLDER: Line chart
- X-axis: Month (Jan-Dec 2024)
- Y-axis: Monthly Revenue ($1000s)
- Pattern: Steady growth Jan-Aug, sharp spike in Sep-Oct, plateau Nov-Dec
- Data required: month (date), revenue (numeric, USD)
- Annotations: Highlight Sep-Oct spike with "+18% MoM" label
- Source: [To be provided by user]
```

---

## References & Further Learning

1. **Financial Times Visual Vocabulary**
   - Comprehensive chart selection guide for journalism and business
   - https://github.com/Financial-Times/chart-doctor/tree/main/visual-vocabulary

2. **Edward Tufte: The Visual Display of Quantitative Information**
   - Classic text on data visualization principles (minimize chartjunk, maximize data-ink ratio)

3. **Assertion-Evidence Framework** (Michael Alley)
   - Research-backed method for scientific and technical presentations
   - https://www.assertion-evidence.com/

4. **WCAG 2.1 Contrast Guidelines**
   - Web Content Accessibility Guidelines for color contrast
   - https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html

5. **ColorBrewer / Coblis Colorblind Simulator**
   - Tools for selecting colorblind-friendly palettes
   - https://colorbrewer2.org / https://www.color-blindness.com/coblis-color-blindness-simulator/

---

**Next Steps**: Once you've selected chart types using this guide, proceed to Stage 5 (Layout & Accessibility) in WORKFLOW.md to finalize visual style.
