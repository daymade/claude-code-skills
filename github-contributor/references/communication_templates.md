# Communication Templates

Templates for effective open-source communication.

## Claiming an Issue

### First-Time Contributor

```markdown
Hi! I'm interested in working on this issue.

I'm new to the project but I've read the contributing guidelines and set up the development environment. I think I understand the scope of the change needed.

My approach would be to:
1. [Step 1]
2. [Step 2]
3. [Step 3]

Does this sound reasonable? Any guidance would be appreciated!
```

### Experienced Contributor

```markdown
I'd like to take this on.

Proposed approach:
- [Technical approach]
- [Testing strategy]

ETA: [timeframe]

Let me know if there are any concerns or if someone else is already working on this.
```

## Asking for Clarification

```markdown
Thanks for filing this issue!

I'd like to work on this but need some clarification:

1. [Question 1]
2. [Question 2]

Once I understand these points, I can start on a fix.
```

## PR Description

### Bug Fix

```markdown
## Summary

Fixes #[issue number]

This PR resolves the [bug description] by [solution approach].

## Root Cause

The issue was caused by [explanation].

## Solution

[Detailed explanation of the fix]

## Testing

- [x] Added regression test
- [x] Verified fix locally
- [x] All existing tests pass

## Screenshots (if applicable)

Before:
[image]

After:
[image]
```

### Feature Addition

```markdown
## Summary

Implements #[issue number]

Adds [feature description] to enable [use case].

## Changes

- Added `feature.py` with [functionality]
- Updated `config.py` to support [new option]
- Added tests in `test_feature.py`

## Usage

```python
# Example usage
from project import new_feature
result = new_feature(...)
```

## Testing

- [x] Unit tests added
- [x] Integration tests pass
- [x] Documentation updated

## Migration Guide (if breaking)

[Instructions for users to migrate]
```

### Documentation Update

```markdown
## Summary

Improves documentation for [area].

## Changes

- Fixed typos in [file]
- Added examples for [feature]
- Updated outdated [section]
- Clarified [confusing part]

## Preview

[Screenshot or link to rendered docs]
```

## Responding to Reviews

### Accepting Feedback

```markdown
Good catch! I've updated the code to [change].

See commit [hash].
```

### Explaining a Decision

```markdown
Thanks for the review!

I chose this approach because:
1. [Reason 1]
2. [Reason 2]

However, I'm open to changing it if you think [alternative] would be better. What do you think?
```

### Requesting Clarification

```markdown
Thanks for the feedback!

Could you clarify what you mean by [quote]? I want to make sure I address your concern correctly.
```

### Disagreeing Respectfully

```markdown
I see your point about [concern].

I went with the current approach because [reasoning]. However, I understand the tradeoff you're highlighting.

Would a middle ground like [alternative] address your concern while keeping [benefit]?
```

## After Merge

```markdown
Thanks for the review and merge! 🎉

I learned [something] from the feedback - I'll apply that in future contributions.

Looking forward to contributing more to the project!
```

## Abandoning a PR

```markdown
Hi, I won't be able to complete this PR due to [reason].

I've pushed my current progress in case someone else wants to continue from here. The remaining work is:
- [ ] [Task 1]
- [ ] [Task 2]

Sorry for any inconvenience, and thanks for the opportunity to contribute!
```

## Tone Guidelines

### Always

- Be grateful
- Be specific
- Be patient
- Be humble

### Never

- Be defensive
- Be dismissive
- Be demanding
- Be passive-aggressive

### Word Choice

```
❌ "You should..."
✅ "It might help to..."

❌ "This is wrong"
✅ "I think there might be an issue with..."

❌ "Obviously..."
✅ "One approach could be..."

❌ "Why didn't you..."
✅ "Could you help me understand..."
```
