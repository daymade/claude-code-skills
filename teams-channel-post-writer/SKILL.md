---
name: teams-channel-post-writer
description: Creates educational Teams channel posts for internal knowledge sharing about Claude Code features, tools, and best practices. Applies when writing posts, announcements, or documentation to teach colleagues effective Claude Code usage, announce new features, share productivity tips, or document lessons learned. Provides templates, writing guidelines, and structured approaches emphasizing concrete examples, underlying principles, and connections to best practices like context engineering. Activates for content involving Teams posts, channel announcements, feature documentation, or tip sharing.
---

# Teams Channel Post Writer

## Overview

Create well-structured, educational Teams channel posts for internal knowledge sharing about Claude Code features and best practices. This skill provides templates, writing guidelines, and a structured workflow to produce consistent, actionable content that helps colleagues learn effective Claude Code usage.

## When to Use This Skill

This skill activates when creating Teams channel posts to:
- Announce and explain new Claude Code features
- Share Claude Code tips and best practices
- Teach effective prompting patterns and workflows
- Connect features to broader engineering principles (e.g., context engineering)
- Document lessons learned from using Claude Code

## Workflow

### 1. Understand the Topic

Gather information about what to write about:
- Research the feature/topic thoroughly using official documentation
- Verify release dates and version numbers from changelogs
- Identify the core benefit or principle the post should teach
- Collect concrete examples from real usage

**Research checklist:**
- [ ] Found official release date/version number
- [ ] Verified feature behavior through testing or documentation
- [ ] Identified authoritative sources to link to
- [ ] Understood the underlying principle or best practice

### 2. Plan the Content

Based on the writing guidelines in `references/writing-guidelines.md`, plan:
- **Hook**: What's new or important about this topic?
- **Core principle**: What best practice does this illustrate?
- **Examples**: What concrete prompts or workflows demonstrate this?
- **Call-to-action**: What should readers try next?

### 3. Draft Using the Template

Start with the template in `assets/post-template.md` and fill in:

1. **Title**: Use an emoji and clear description
2. **Introduction**: Include release date and brief context
3. **What it is**: 1-2 sentence explanation
4. **How to use it**: Show "Normal vs Better" pattern with explicit instructions
5. **Why use it**: Explain the underlying principle with 4 key benefits
6. **Examples**: Provide 3+ realistic, concrete prompts
7. **Options/Settings**: List key configurations or parameters
8. **Call-to-action**: End with actionable next step
9. **Learn more**: Link to authoritative resources

### 4. Apply Writing Guidelines

Review the draft against the quality checklist in `references/writing-guidelines.md`:
- Educational and helpful tone
- "Normal/Better" pattern (not "Wrong/Correct")
- Concrete, realistic examples
- Explains the "why" with principles
- Clear structure with bullets and formatting
- Verified facts and dates

### 5. Save and Share

Save the final post to your team's documentation location with a descriptive filename like "Claude Code Tips.md" or "[Topic Name].md"

## Key Principles

### Show, Don't Just Tell
Always include concrete examples users can adapt. Use "Normal vs Better" comparisons to demonstrate improvements without making readers feel criticized.

### Connect to Principles
Don't just describe features—explain the underlying best practices. For example, connect the Explore agent to "context offloading" principles in context engineering.

### Make it Actionable
Be explicit about invocation patterns. Users should be able to copy/paste examples and immediately use them.

### Verify Everything
Always research release dates, verify feature behavior, and link to authoritative sources. Accuracy builds trust.

## Resources

### references/writing-guidelines.md
Comprehensive writing guidelines including:
- Tone and style standards
- Structure patterns for different post types
- Formatting conventions
- Research requirements
- Quality checklist

Reference this file for detailed guidance on tone, structure, and quality standards.

### assets/post-template.md
Ready-to-use markdown template with placeholder structure for:
- Title and introduction
- Feature explanation
- Usage examples
- Benefits and principles
- Options and settings
- Call-to-action and resources

Copy this template as a starting point for new posts, then customize the content while maintaining the proven structure.