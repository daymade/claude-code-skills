# Minimal Intake Questionnaire (10 Items)

> **Purpose**: Gather essential context to produce a high-quality presentation. If the user doesn't provide information after 2 prompts, use the **safe default** for each item and clearly document the assumption in speaker notes.

---

## 1. Who is the audience?

**Question**: Who will be viewing/listening to this presentation?

**Examples**:
- Executive leadership team
- Technical engineers
- General public / consumers
- Sales prospects
- Students / trainees
- Board members
- Investors

**Default if missing**: General public (educated adults with no specialized background)

**Impact**: Determines technical depth, jargon usage, and evidence types.

---

## 2. What is the core objective?

**Question**: What do you want the audience to understand, believe, or feel?

**Examples**:
- Understand a new product feature
- Accept a proposal or recommendation
- Learn how to use a tool
- Appreciate the severity of a problem
- Gain confidence in a solution

**Default if missing**: "Understand and accept" the main proposition

**Impact**: Shapes the storyline and emphasis throughout the deck.

---

## 3. What is the desired action or decision?

**Question**: What specific action should the audience take after this presentation?

**Examples**:
- Approve budget allocation
- Agree to pilot/trial
- Provide feedback by [date]
- Adopt a new process
- Make a purchase decision
- Schedule a follow-up meeting

**Default if missing**: Agree to move to the next step after the meeting

**Impact**: Defines the call-to-action (CTA) on the closing slide.

---

## 4. What is the presentation duration and slide count limit?

**Question**: How long will you present, and are there any slide count constraints?

**Examples**:
- 5-minute pitch (5-7 slides)
- 15-minute review (12-15 slides)
- 30-minute workshop (20-25 slides)
- 60-minute lecture (30-40 slides)

**Default if missing**: 15-20 minutes, 12-15 slides

**Impact**: Controls depth per slide and total slide count.

---

## 5. What tone and style should the presentation have?

**Question**: How should the presentation feel and sound?

**Examples**:
- Professional and formal
- Friendly and conversational
- Inspirational and aspirational
- Technical and precise
- Urgent and persuasive

**Default if missing**: Professional, clear, and friendly

**Impact**: Affects language choice, speaker notes tone, and visual style.

---

## 6. What is the topic scope and boundaries?

**Question**: What should be included and what should be excluded?

**Examples**:
- Focus only on Q1 results, not Q2 projections
- Cover product features but not pricing
- Technical implementation only, no business case
- High-level overview, no detailed specs

**Default if missing**: The given topic name plus one layer of directly related context

**Impact**: Prevents scope creep and ensures focused messaging.

---

## 7. Are there must-include points or forbidden topics?

**Question**: Are there specific messages you must convey or topics you must avoid?

**Examples**:
- Must mention: regulatory compliance requirement
- Must avoid: competitor names, unannounced features, sensitive financial data
- Required disclaimer: "Subject to board approval"

**Default if missing**: None (no mandatory inclusions or exclusions)

**Impact**: Ensures compliance and strategic messaging alignment.

---

## 8. Do you have data or tables available?

**Question**: Can you provide data files (CSV, Excel, JSON) or tables for visualization?

**Examples**:
- Sales data by month
- User survey results
- Cost breakdown by category
- Performance metrics over time

**Default if missing**: No data available; generate placeholder charts with a list of required data fields

**Impact**: Determines whether to generate actual charts (via chartkit.py) or placeholders.

---

## 9. Are there brand or visual constraints?

**Question**: Are there specific colors, fonts, logos, or templates you must use?

**Examples**:
- Company brand colors: #FF5733, #33A1FF
- Required logo placement: top-right corner
- Mandatory template: [template file]
- Font restrictions: Arial only

**Default if missing**: Built-in neutral theme (dark ink #1F2937, accent #2563EB, emphasis #DC2626)

**Impact**: Affects color palette and visual components in STYLE-GUIDE.

---

## 10. What deliverable format do you prefer?

**Question**: How do you want to receive the final presentation?

**Options**:
- Markdown slides (Marp/Reveal.js compatible)
- PowerPoint (.pptx)
- Google Slides export
- PDF for print
- All of the above

**Default if missing**: slides.md (Markdown) + optional PNG charts; export to PPTX if `python-pptx` is available

**Impact**: Determines final export step in Stage 8.

---

## Usage Instructions

1. **First pass**: Ask all 10 questions in a user-friendly format (e.g., "I have a few quick questions to help me create the best presentation for you...")

2. **Second prompt**: If critical items (1, 2, 3, 4, 8) are still missing, ask again with examples.

3. **Apply defaults**: If still no response, use the safe default for each missing item.

4. **Document assumptions**: In `/output/notes.md`, include a "Assumptions & Limitations" section listing all defaults used and their potential impact.

---

## Example Interaction

**User**: "Make me a presentation about coffee."

**Assistant**: "I'd love to help! To create the best presentation for you, I have a few quick questions:

1. Who is your audience? (e.g., coffee shop customers, barista trainees, general coffee enthusiasts)
2. What's your main goal? (e.g., educate about brewing methods, convince them to buy premium beans, explain coffee origins)
3. What action should they take afterward? (e.g., try a new brew method, visit your shop, change their coffee habits)
4. How long will you present? (e.g., 5 minutes, 15 minutes, 30 minutes)
5. Do you have any data or tables to include? (e.g., sales numbers, survey results, flavor profiles)

If you're not sure about any of these, no problem—I'll use sensible defaults and we can adjust later!"

**User**: "It's for coffee enthusiasts, about 10 minutes, and I want them to improve their home brewing. No data."

**Assistant**: "Perfect! I'll create a 10-minute presentation (about 10-12 slides) for coffee enthusiasts focused on improving home brewing techniques. I'll use a friendly, educational tone and aim for them to try new methods at home. Since you don't have data, I'll include helpful diagrams and placeholder charts where data would be useful (like extraction curves or flavor profiles). Let me get started!"

[Proceeds to Stage 0 of WORKFLOW.md with documented assumptions]

---

## Safe Defaults Summary Table

| # | Question | Safe Default |
|---|----------|--------------|
| 1 | Audience | General public (educated adults) |
| 2 | Core objective | "Understand and accept" the proposition |
| 3 | Desired action | Agree to move to next step |
| 4 | Duration & slides | 15-20 min, 12-15 slides |
| 5 | Tone & style | Professional, clear, friendly |
| 6 | Topic scope | Given topic + 1 layer related |
| 7 | Must-include/taboos | None |
| 8 | Available data | None (use placeholders) |
| 9 | Brand constraints | Neutral theme (see STYLE-GUIDE) |
| 10 | Format preference | slides.md + optional charts/PPTX |

---

**Next step**: Once intake is complete, proceed to WORKFLOW.md Stage 0.
