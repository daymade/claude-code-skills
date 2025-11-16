# EARS (Easy Approach to Requirements Syntax)

## Overview

EARS (Easy Approach to Requirements Syntax) is a structured requirements writing methodology created by Rolls-Royce in 2009. It transforms natural language descriptions into precise, actionable specifications.

## Core Principle

Convert requirements from **descriptive** to **normative** by decomposing them into:

1. **Entity** - What component/system is involved
2. **Action** - What operation/behavior should occur
3. **Relationship** - How entities interact
4. **Scope** - Under what conditions/constraints

## EARS Sentence Patterns

### Pattern 1: Ubiquitous (Unconditional)

**Format:** `系统应 <action>`
**English:** `The system shall <action>`

**Use when:** Requirement always applies, no preconditions

**Example:**
- Natural: "The app needs a login page"
- EARS: "The system shall provide a login interface"

### Pattern 2: Event-Driven

**Format:** `当 <trigger> 时,系统应 <action>`
**English:** `When <trigger>, the system shall <action>`

**Use when:** Requirement applies upon specific event

**Example:**
- Natural: "Send reminder before deadline"
- EARS: "When the task deadline is within 30 minutes, the system shall send a reminder notification"

### Pattern 3: State-Driven

**Format:** `在 <state> 状态下,系统应 <action>`
**English:** `While <state>, the system shall <action>`

**Use when:** Requirement applies during a specific state

**Example:**
- Natural: "Show loading spinner during data fetch"
- EARS: "While data is being fetched, the system shall display a loading spinner"

### Pattern 4: Optional Feature

**Format:** `若 <condition>,系统应 <action>`
**English:** `If <condition>, then the system shall <action>`

**Use when:** Requirement is conditional

**Example:**
- Natural: "Premium users get extra features"
- EARS: "If the user has a premium subscription, the system shall enable advanced analytics features"

### Pattern 5: Unwanted Behavior

**Format:** `若 <condition>,系统应避免 <unwanted action>`
**English:** `If <condition>, the system shall prevent <unwanted action>`

**Use when:** Specifying constraints or prohibited behaviors

**Example:**
- Natural: "Don't allow duplicate submissions"
- EARS: "If a submission is already in progress, the system shall prevent duplicate form submissions"

## Complex EARS Patterns

### Multi-Condition Events

**Format:** `当 <condition1> 且 <condition2> 时,系统应 <action>`

**Example:**
```
When the task deadline is within 30 minutes
AND the user has not started the task,
the system shall trigger a notification with encouraging message and sound alert.
```

### Conditional Actions with Alternatives

**Format:**
```
When <trigger>:
- If <condition1>, the system shall <action1>
- If <condition2>, the system shall <action2>
- Otherwise, the system shall <default action>
```

**Example:**
```
When user submits a form:
- If all required fields are filled, the system shall process the submission
- If any required field is empty, the system shall highlight missing fields
- Otherwise, the system shall display a general error message
```

## EARS Transformation Checklist

When converting natural language to EARS:

- [ ] Identify all implicit conditions and make them explicit
- [ ] Specify the triggering event or state
- [ ] Define the actor (usually "the system")
- [ ] Use precise action verbs (shall, should, must)
- [ ] Specify measurable outcomes where possible
- [ ] Break compound requirements into atomic statements
- [ ] Remove ambiguous language ("user-friendly", "fast", "intuitive")
- [ ] Add quantitative criteria ("within 30 minutes", "at least 8 characters")

## Benefits

1. **Clarity** - Eliminates ambiguity through structured syntax
2. **Completeness** - Forces specification of conditions and triggers
3. **Testability** - Clear requirements enable automated testing
4. **Atomicity** - Each requirement is independent and self-contained
5. **Traceability** - Easy to map requirements to features
