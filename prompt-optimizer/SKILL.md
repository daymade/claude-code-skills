---
name: prompt-optimizer
description: Transform vague prompts into precise, well-structured specifications using EARS (Easy Approach to Requirements Syntax) methodology. This skill should be used when users provide loose requirements, ambiguous feature descriptions, or need to enhance prompts for AI-generated code, products, or documents. Triggers include requests to "optimize my prompt", "improve this requirement", "make this more specific", or when raw requirements lack detail and structure.
---

# Prompt Optimizer

## Overview

Optimize vague prompts into precise, actionable specifications using EARS (Easy Approach to Requirements Syntax) - a Rolls-Royce methodology for transforming natural language into structured, testable requirements.

**Methodology inspired by:** This skill's approach to combining EARS with domain theory grounding was inspired by [阿星AI工作室 (A-Xing AI Studio)](https://mp.weixin.qq.com/s/yUVX-9FovSq7ZGChkHpuXQ), which demonstrated practical EARS application for prompt enhancement.

**Four-layer enhancement process:**

1. **EARS syntax transformation** - Convert descriptive language to normative specifications
2. **Domain theory grounding** - Apply relevant industry frameworks (GTD, BJ Fogg, Gestalt, etc.)
3. **Example extraction** - Surface concrete use cases with real data
4. **Structured prompt generation** - Format using Role/Skills/Workflows/Examples/Formats framework

## When to Use

Apply when:
- User provides vague feature requests ("build a dashboard", "create a reminder app")
- Requirements lack specific conditions, triggers, or measurable outcomes
- Natural language descriptions need conversion to testable specifications
- User explicitly requests prompt optimization or requirement refinement

## Six-Step Optimization Workflow

### Step 1: Analyze Original Requirement

Identify weaknesses:
- **Overly broad** - "Add user authentication" → Missing password requirements, session management
- **Missing triggers** - "Send notifications" → Missing when/why notifications trigger
- **Ambiguous actions** - "Make it user-friendly" → No measurable usability criteria
- **No constraints** - "Process payments" → Missing security, compliance requirements

### Step 2: Apply EARS Transformation

Convert requirements to EARS patterns. See `references/ears_syntax.md` for complete syntax rules.

**Five core patterns:**
1. **Ubiquitous**: `The system shall <action>`
2. **Event-driven**: `When <trigger>, the system shall <action>`
3. **State-driven**: `While <state>, the system shall <action>`
4. **Conditional**: `If <condition>, the system shall <action>`
5. **Unwanted behavior**: `If <condition>, the system shall prevent <unwanted action>`

**Quick example:**
```
Before: "Create a reminder app with task management"

After (EARS):
1. When user creates a task, the system shall guide decomposition into executable sub-tasks
2. When task deadline is within 30 minutes AND user has not started, the system shall send notification with sound alert
3. When user completes a sub-task, the system shall update progress and provide positive feedback
```

**Transformation checklist:**
- [ ] Identify implicit conditions and make explicit
- [ ] Specify triggering events or states
- [ ] Use precise action verbs (shall, must, should)
- [ ] Add measurable criteria ("within 30 minutes", "at least 8 characters")
- [ ] Break compound requirements into atomic statements
- [ ] Remove ambiguous language ("user-friendly", "fast")

### Step 3: Identify Domain Theories

Match requirements to established frameworks. See `references/domain_theories.md` for full catalog.

**Common domain mappings:**
- **Productivity** → GTD, Pomodoro, Eisenhower Matrix
- **Behavior Change** → BJ Fogg Model (B=MAT), Atomic Habits
- **UX Design** → Hick's Law, Fitts's Law, Gestalt Principles
- **Security** → Zero Trust, Defense in Depth, Privacy by Design

**Selection process:**
1. Identify primary domain from requirement keywords
2. Match to 2-4 complementary theories
3. Apply theory principles to specific features
4. Cite theories in enhanced prompt for credibility

### Step 4: Extract Concrete Examples

Generate specific examples with real data:
- User scenarios: "When user logs in on mobile device..."
- Data examples: "Product: 'Laptop', Price: $999, Stock: 15"
- Workflow examples: "Task: Write report → Sub-tasks: Research (2h), Draft (3h), Edit (1h)"

Examples must be **realistic**, **specific**, **varied** (success/error/edge cases), and **testable**.

### Step 5: Generate Enhanced Prompt

Structure using the standard framework:

```markdown
# Role
[Specific expert role with domain expertise]

## Skills
- [Core capability 1]
- [Core capability 2]
[List 5-8 skills aligned with domain theories]

## Workflows
1. [Phase 1] - [Key activities]
2. [Phase 2] - [Key activities]
[Complete step-by-step process]

## Examples
[Concrete examples with real data, not placeholders]

## Formats
[Precise output specifications:
- File types, structure requirements
- Design/styling expectations
- Technical constraints
- Deliverable checklist]
```

**Quality criteria:**
- **Role specificity**: "Product designer specializing in time management apps" > "Designer"
- **Theory grounding**: Reference frameworks explicitly
- **Actionable workflows**: Clear inputs/outputs and decision points
- **Concrete examples**: Real data, not "Example 1", "Example 2"
- **Measurable formats**: Specific requirements, not "good design"

### Step 6: Present Optimization Results

Output in structured format:

```markdown
## Original Requirement
[User's vague requirement]

**Identified Issues:**
- [Issue 1: e.g., "Lacks specific trigger conditions"]
- [Issue 2: e.g., "No measurable success criteria"]

## EARS Transformation
[Numbered list of EARS-formatted requirements]

## Domain & Theories
**Primary Domain:** [e.g., Authentication Security]

**Applicable Theories:**
- **[Theory 1]** - [Brief relevance]
- **[Theory 2]** - [Brief relevance]

## Enhanced Prompt
[Complete Role/Skills/Workflows/Examples/Formats prompt]

---

**How to use:**
[Brief guidance on applying the prompt]
```

## Advanced Techniques

For complex scenarios, see `references/advanced_techniques.md`:
- **Multi-stakeholder requirements** - EARS statements for each user type
- **Non-functional requirements** - Performance, security, scalability with quantified thresholds
- **Complex conditional logic** - Nested conditions with boolean operators

## Quick Reference

**Do's:**
✅ Break down compound requirements (one EARS statement per requirement)
✅ Specify measurable criteria (numbers, timeframes, percentages)
✅ Include error/edge cases
✅ Ground in established theories
✅ Use concrete examples with real data

**Don'ts:**
❌ Avoid vague language ("fast", "user-friendly")
❌ Don't assume implicit knowledge
❌ Don't mix multiple actions in one statement
❌ Don't use placeholders in examples

## Resources

Load these reference files as needed:

- **`references/ears_syntax.md`** - Complete EARS syntax rules, all 5 patterns, transformation guidelines, benefits
- **`references/domain_theories.md`** - 40+ theories mapped to 10 domains (productivity, UX, gamification, learning, e-commerce, security, etc.)
- **`references/examples.md`** - Four complete transformation examples (procrastination app, e-commerce product page, learning dashboard, password reset security) with before/after comparisons and reusable template
- **`references/advanced_techniques.md`** - Multi-stakeholder requirements, non-functional specs, complex conditional logic patterns

**When to load references:**
- EARS syntax clarification needed → `ears_syntax.md`
- Domain theory selection requires extensive options → `domain_theories.md`
- User requests multiple optimization examples → `examples.md`
- Complex requirements with multiple stakeholders or non-functional specs → `advanced_techniques.md`
