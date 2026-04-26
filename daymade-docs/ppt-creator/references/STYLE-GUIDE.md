# Layout & Style Guide (Neutral Theme)

> **Purpose**: Ensure consistent, accessible, professional visual design across all slides. This neutral theme supports easy customization with your own brand colors and fonts.

---

## Canvas & Grid System

### Slide Dimensions
- **Aspect Ratio**: 16:9 (widescreen standard)
- **Resolution**: 1920 × 1080 pixels (Full HD) or 1280 × 720 pixels (HD)
- **Safe Zone**: Margins ≥ 48px on all sides (prevents content from being cut off by projectors)

### Grid System
- **Columns**: 12-column grid (column width varies by content)
- **Gutter**: 24px between columns
- **Baseline Grid**: 8px vertical rhythm (all spacing should be multiples of 8)

### Layout Examples
```
┌─────────────────────────────────────────────┐
│ [48px margin]                               │
│  ┌──────────────────────────────────┐      │
│  │ HEADING (top-aligned)             │      │
│  │                                   │      │
│  │ [Content area: text/chart/image]  │      │
│  │                                   │      │
│  │                                   │      │
│  └──────────────────────────────────┘      │
│       [Footer: source + page #] [48px]     │
└─────────────────────────────────────────────┘
```

---

## Typography

### Font Families

**Recommended Fonts**:
- **Chinese**: Source Han Sans (思源黑体) / PingFang SC (苹方) / Hiragino Sans (冬青黑体)
- **English**: Inter / Calibri / Helvetica Neue / Arial

**Why These Fonts**:
- High readability on screens
- Wide character support (multilingual)
- Professional appearance
- Available on most systems (or free to download)

**Fallback Stack**:
```
font-family: "Inter", "Source Han Sans", "PingFang SC", -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
```

### Font Sizes

| Element | Size (pt) | Weight | Use Case |
|---------|-----------|--------|----------|
| Slide Title | 34-40 | Bold (700) | Main assertion heading |
| Subtitle / Section | 24-28 | Semibold (600) | Chapter intros, subheadings |
| Body Text | 18-22 | Regular (400) | Bullet points, paragraphs |
| Caption / Label | 16-18 | Regular (400) | Chart labels, image captions |
| Footer / Source | 14-16 | Regular (400) | Citations, page numbers |

**Minimum Readable Size**: 14pt (anything smaller is hard to read from audience distance)

---

### Line Spacing (Leading)

| Element | Line Height | Calculation |
|---------|-------------|-------------|
| Headings | 1.1 × font size | Tight for emphasis |
| Subheadings | 1.2 × font size | Slightly relaxed |
| Body Text | 1.3-1.5 × font size | Comfortable reading |
| Captions | 1.3 × font size | Consistent with body |

**Example**:
- Heading: 36pt font → 40pt line height (1.1×)
- Body: 20pt font → 28pt line height (1.4×)

---

### Text Alignment

- **Headings**: Left-aligned (easier to scan)
  - Exception: Cover slide title may be centered
- **Body Text**: Left-aligned
  - Avoid full justification (creates awkward word spacing)
- **Bullet Points**: Left-aligned with 24-32px indent
- **Footers**: Right-aligned (source), left-aligned (page number/date)

---

### Text Formatting

**Bold**:
- Use for headings, key terms, and emphasis
- Do NOT use all-caps for body text (harder to read)

**Italic**:
- Use sparingly for quotes, foreign terms, or subtle emphasis
- Do NOT use for long passages (reduces readability)

**Underline**:
- Avoid (looks like hyperlinks)
- Use bold or color for emphasis instead

**ALL CAPS**:
- OK for short labels (e.g., "SECTION 1", "BACKUP")
- Avoid for sentences (slows reading speed by 10-15%)

---

## Color Palette (Neutral Theme, WCAG AA Compliant)

### Primary Colors

| Color Name | Hex Code | RGB | Use Case | Contrast vs White | Contrast vs Black |
|------------|----------|-----|----------|-------------------|-------------------|
| Dark Ink | #1F2937 | rgb(31, 41, 55) | Headings, body text | 16.1:1 ✓ | 1.3:1 ✗ |
| Medium Gray | #6B7280 | rgb(107, 114, 128) | Secondary text, captions | 4.6:1 ✓ | 4.5:1 ✓ |
| Light Gray | #D1D5DB | rgb(209, 213, 219) | Borders, dividers | 1.7:1 ✗ | 12.4:1 ✓ |
| Background White | #FFFFFF | rgb(255, 255, 255) | Slide background | — | 21:1 ✓ |

### Accent Colors

| Color Name | Hex Code | RGB | Use Case | Contrast vs White | Contrast vs Black |
|------------|----------|-----|----------|-------------------|-------------------|
| Primary Blue | #2563EB | rgb(37, 99, 235) | Links, highlights, key points | 4.6:1 ✓ | 4.6:1 ✓ |
| Secondary Teal | #0891B2 | rgb(8, 145, 178) | Alternative highlight | 3.7:1 ⚠️ | 5.7:1 ✓ |
| Emphasis Red | #DC2626 | rgb(220, 38, 38) | Warnings, critical points | 5.0:1 ✓ | 4.2:1 ✓ |
| Success Green | #10B981 | rgb(16, 185, 129) | Positive trends, checkmarks | 2.5:1 ✗ | 8.4:1 ✓ |

**Note**: ✓ = Passes WCAG AA (≥4.5:1 for text, ≥3:1 for UI elements); ⚠️ = Marginal (use carefully); ✗ = Fails

### Color Usage Rules

1. **Text on White Background**:
   - Primary text: Dark Ink (#1F2937) → 16.1:1 ✓
   - Secondary text: Medium Gray (#6B7280) → 4.6:1 ✓
   - Links/Highlights: Primary Blue (#2563EB) → 4.6:1 ✓

2. **Text on Dark Background** (e.g., dark slide):
   - Use white (#FFFFFF) or very light gray (#F3F4F6)
   - Ensure ≥4.5:1 contrast

3. **Chart Colors**:
   - Use Primary Blue, Emphasis Red, Secondary Teal, Success Green
   - Avoid relying on color alone (add patterns/labels)
   - Test with colorblind simulator (see VIS-GUIDE.md)

4. **Avoid These Combinations**:
   - Red text on green background (colorblind issue)
   - Light gray text on white background (insufficient contrast)
   - Pure black (#000000) on pure white (too harsh; use Dark Ink instead)

---

## Spacing & Layout

### Margin & Padding

| Element | Spacing | Notes |
|---------|---------|-------|
| Slide Margins | 48px (all sides) | Safe zone for projectors |
| Heading to Body | 24-32px | Clear separation |
| Paragraph Spacing | 16-24px | Between bullet points or paragraphs |
| Chart to Caption | 16px | Between chart and source citation |
| Footer Padding | 24px from bottom | Consistent footer placement |

### Bullet Point Formatting

- **Indent**: 24-32px from left margin
- **Bullet Style**: Simple (•) or numbered (1., 2., 3.)
  - Avoid fancy bullets (stars, arrows, custom icons)
- **Max Bullets Per Slide**: 3-5 (more gets overwhelming)
- **Nested Bullets**: Max 2 levels (Level 1 → Level 2)
  - Level 2 indent: +24px from Level 1

**Example**:
```
• Main point one (Level 1)
  • Supporting detail (Level 2)
  • Another detail (Level 2)
• Main point two (Level 1)
• Main point three (Level 1)
```

---

## Visual Elements

### Charts & Graphs

- **Padding**: 8px internal padding around chart area
- **Border**: None (or very subtle 1px light gray if needed)
- **Grid Lines**: Minimal (horizontal only, light gray #E5E7EB)
- **Axis Lines**: 1-2px, Medium Gray (#6B7280)
- **Data Labels**: 16-18pt, positioned above/beside data points (not overlapping)

### Images & Photos

- **Border Radius**: 6-8px (subtle rounded corners)
- **Padding**: 8px around image
- **Alt Text**: Always include (see Accessibility section)
- **Aspect Ratio**: Maintain original (don't stretch/distort)
- **Max Size**: Leave 48px margins on all sides

### Icons

- **Size**: 24px × 24px (small), 48px × 48px (medium), 96px × 96px (large)
- **Style**: Outline or filled (be consistent across deck)
- **Color**: Match accent colors (Primary Blue, Emphasis Red, etc.)
- **Spacing**: 16px between icon and label

### Dividers & Borders

- **Horizontal Divider**: 1-2px, Light Gray (#D1D5DB)
- **Use Sparingly**: Only when needed to separate sections
- **Border Radius**: 6-8px for boxes, cards, or containers

---

## Page Density & White Space

### The "70-Word Rule"

- **Max Words Per Slide**: ≤70 words (excluding chart labels and footer)
- **Why**: Audience can't read and listen simultaneously; slides should support speech, not replace it
- **Exception**: Backup slides or reference tables (not presented, for Q&A)

### White Space Guidelines

- **Don't Fill Every Pixel**: Aim for 40-50% white space per slide
- **Purpose**: Guides eye, reduces cognitive load, looks professional
- **How to Achieve**:
  - Use generous margins (48px+)
  - Space out bullet points (16-24px apart)
  - One chart or image per slide (not 3-4 crammed together)

---

## Accessibility (WCAG 2.1 AA Compliance)

### Contrast Requirements

**Text Contrast** (against background):
- **Normal text** (<18pt or <14pt bold): ≥ 4.5:1
- **Large text** (≥18pt or ≥14pt bold): ≥ 3:1

**UI Components & Chart Elements**:
- **Graphical objects** (bars, lines, icons): ≥ 3:1 against adjacent colors
- **Active vs inactive states**: ≥ 3:1 contrast difference

**Test Your Contrast**:
- WebAIM Contrast Checker: https://webaim.org/resources/contrastchecker/
- Browser DevTools: Inspect element → Contrast ratio displayed

---

### Color Blindness

**Do NOT Rely on Color Alone**:
- Add text labels, patterns, or shapes to distinguish chart series
- Example: Line chart with 3 series → use solid, dashed, dotted lines + color

**Use Colorblind-Friendly Palettes**:
- Avoid red + green combinations
- Use blue + orange or blue + yellow instead
- Test with simulators: Coblis, Color Oracle

---

### Alt Text for Images & Charts

**Every image and chart must have alt text** for screen readers.

**Good Alt Text**:
- Describes content concisely (1-2 sentences)
- Includes key data insights (for charts)
- Example (chart): "Line chart showing monthly revenue Jan-Dec 2024, with 35% growth and a sharp Q3 spike."
- Example (photo): "Product prototype with transparent casing and LED display showing time."

**Bad Alt Text**:
- "Chart 1" (too vague)
- "Revenue graph" (no insight)
- [Empty alt tag] (inaccessible)

---

### Screen Reader Compatibility

- **Heading Hierarchy**: Use proper heading levels (H1 → H2 → H3), don't skip
- **Reading Order**: Ensure content flows logically (top-to-bottom, left-to-right)
- **Link Text**: Descriptive ("Download Q4 Report" vs. "Click here")

---

## Animation & Transitions (Use Sparingly)

### When to Animate

- **Reveal bullet points**: One at a time (helps pacing)
- **Highlight data**: Fade in chart elements sequentially (e.g., line-by-line)
- **Slide transitions**: Simple fade or push (not flashy)

### When NOT to Animate

- **Avoid**: Spinning, bouncing, dissolving, 3D effects
- **Why**: Distracting, unprofessional, slows down presentation
- **Exception**: Data storytelling where sequence matters (e.g., building a chart layer-by-layer)

---

## Slide-Specific Layouts

### Cover Slide

```
┌─────────────────────────────────────────┐
│                                         │
│         [Centered or Left-Aligned]      │
│                                         │
│   MAIN TITLE (36-40pt, Bold)           │
│   Subtitle (24-28pt, Regular)          │
│                                         │
│   Date | Presenter Name                │
│                                         │
└─────────────────────────────────────────┘
```

---

### Content Slide (Text + Chart)

```
┌─────────────────────────────────────────┐
│ ASSERTION HEADING (34-36pt)             │
│                                         │
│  • Bullet point 1 (20pt)                │
│  • Bullet point 2                       │
│  • Bullet point 3                       │
│                                         │
│  [Chart with alt text]                  │
│                                         │
│         Source: XYZ, 2024 | Page 5     │
└─────────────────────────────────────────┘
```

---

### Section Divider Slide

```
┌─────────────────────────────────────────┐
│                                         │
│                                         │
│        SECTION TITLE (40pt)            │
│        Brief Description (24pt)         │
│                                         │
│                                         │
│                                         │
└─────────────────────────────────────────┘
```

---

## Customization Guide (Replace with Your Brand)

### Step 1: Update Colors

**Find and replace these hex codes** in your slides:

| Theme Color | Default | Your Brand | Use Case |
|-------------|---------|------------|----------|
| Primary Text | #1F2937 | _________ | Headings, body |
| Accent | #2563EB | _________ | Highlights, links |
| Emphasis | #DC2626 | _________ | Warnings, critical |
| Background | #FFFFFF | _________ | Slide background |

**Test Contrast**: Use WebAIM checker to ensure ≥4.5:1 for text, ≥3:1 for UI.

---

### Step 2: Update Fonts

**Find and replace font families**:
- Headings: Inter → [Your Brand Font]
- Body: Source Han Sans → [Your Brand Font]

**Web Font Loading** (if using Google Fonts or Adobe Fonts):
```html
<link href="https://fonts.googleapis.com/css2?family=YourFont:wght@400;600;700&display=swap" rel="stylesheet">
```

---

### Step 3: Add Logo

- Place logo file in `/output/assets/logo.png`
- Add to **cover slide** (top-left or top-right)
- Add to **footer** of content slides (small, 32-48px height)

---

### Step 4: Customize Templates

- Open `references/TEMPLATES.md`
- Adjust spacing, margins, or layout to match your brand guidelines
- Update STYLE-GUIDE.md to document your changes

---

### Step 5: Export & Test

- Export to PPTX or PDF
- Test on projector (check margins, readability)
- Verify accessibility (screen reader, contrast, colorblind mode)

---

## Quick Reference Checklist

Before finalizing each slide, check:

- [ ] **Contrast**: Text ≥ 4.5:1, UI elements ≥ 3:1
- [ ] **Margins**: ≥ 48px safe zone on all sides
- [ ] **Font Size**: Headings ≥ 34pt, body ≥ 18pt
- [ ] **Line Spacing**: Headings 1.1×, body 1.3-1.5×
- [ ] **Word Count**: ≤ 70 words per slide
- [ ] **Alt Text**: All charts and images have descriptive alt text
- [ ] **Bullet Points**: Max 3-5 per slide
- [ ] **White Space**: 40-50% of slide is empty
- [ ] **Source Citation**: Every chart has source in footer
- [ ] **Color Independence**: Not relying on color alone (patterns/labels added)

---

## Tools & Resources

1. **Contrast Checkers**:
   - WebAIM: https://webaim.org/resources/contrastchecker/
   - Chrome DevTools: Inspect → Contrast ratio

2. **Colorblind Simulators**:
   - Coblis: https://www.color-blindness.com/coblis-color-blindness-simulator/
   - Color Oracle (desktop app)

3. **Fonts**:
   - Google Fonts: https://fonts.google.com/
   - Adobe Fonts: https://fonts.adobe.com/
   - Source Han Sans (free): https://github.com/adobe-fonts/source-han-sans

4. **WCAG 2.1 Guidelines**:
   - Contrast (Minimum): https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html

---

**Next Steps**: Once style is finalized, proceed to Stage 6 (Speaker Notes) in WORKFLOW.md.
