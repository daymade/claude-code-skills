# Project Context File Template

Use this template to create a `context.md` file for your project. This file helps the skill:
- Correctly identify speakers in transcripts
- Use proper terminology and naming conventions
- Understand team structure and roles

## Template

```markdown
# Project Context

## Team Directory

| Name | Role | Communication Style | Expertise |
|------|------|---------------------|-----------|
| Alice | Backend Lead | Technical, decisive, assigns tasks | API design, database |
| Bob | PM | Product-focused, asks requirements | User stories, roadmap |
| Carol | TPM | Process-focused, tracks resources | Timeline, dependencies |
| Dave | Frontend | UI/UX discussions, component details | React, CSS |
| Eve | Designer | Visual patterns, user experience | Figma, design systems |

## Project Terminology

| Term | Meaning | Notes |
|------|---------|-------|
| Order | Customer purchase record | NOT to be confused with "command" |
| Note | User annotation on orders | Different from system "Comment" |
| Profile | Customer settings | Use "CustomerProfile" not "UserProfile" |

## Naming Conventions

- **Entities**: PascalCase (e.g., `OrderItem`, `CustomerProfile`)
- **APIs**: kebab-case (e.g., `/api/order-items`)
- **Database tables**: snake_case (e.g., `order_items`)

## Existing Systems

List systems/entities that already exist to avoid naming conflicts:

- `Comment` - existing comment system (don't create new "Note" entity with same meaning)
- `Account` - existing user account (don't create "UserProfile" with overlapping fields)

## Meeting Types

| Type | Description | Typical Attendees |
|------|-------------|-------------------|
| Design Review | API/architecture discussions | Backend, PM, TPM |
| Sprint Planning | Task breakdown and assignment | All team members |
| Sync | Quick status updates | Varies |
| Retrospective | Process improvement | All team members |
```

## Usage

1. Create a `context.md` file in your project directory
2. Fill in team directory with actual team members
3. Add project-specific terminology
4. Update as project evolves

When invoking meeting-minutes-taker, provide this file path:
```
Please generate meeting minutes from transcript.md using context.md for speaker identification.
```

## Speaker Identification Example

With this context file, when the transcript has:
```
Speaker 1: Let's discuss the Order API design...
Speaker 2: What about the user requirements for...
Speaker 3: We need to track the timeline for...
```

The skill will analyze and match:
- Speaker 1 → Alice (Backend Lead) - technical focus, API discussion
- Speaker 2 → Bob (PM) - requirements focus
- Speaker 3 → Carol (TPM) - timeline focus
