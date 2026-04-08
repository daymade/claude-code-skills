---
name: mindbreak
description: "Monitors work intensity and inserts natural break reminders based on continuous work duration and time-of-day. Tracks activity via hook timestamps, triggers after 45+ min of continuous work. Activates in all work-related conversations involving coding, writing, analysis, debugging, research, or planning."
---

# MindBreak — Work Health Reminder

Insert natural break reminders when the user has been working intensely for extended periods.

## How It Works

A hook script (`~/.claude/scripts/mindbreak_hook.sh`) runs on every user message. It:
1. Writes a unix timestamp to the activity log
2. Calculates continuous work duration (gaps >= 15 min start a new segment)
3. If thresholds are met (>= 45 min, 30 min cooldown, max 3 per segment), outputs a trigger signal

The trigger signal appears in `<user-prompt-submit-hook>` tags with `<IMPORTANT>` wrapper for reliable activation in long contexts. **You only need to respond to it.**

## Responding to Triggers

When you see a trigger signal in hook feedback, follow the `ACTION REQUIRED` instructions embedded in the signal. The signal itself contains everything you need — append the reminder as the **last paragraph** of your response. Do not interrupt the main content. **Do NOT use fixed templates** — express the intent naturally in your own voice, matching the tone and personality of the current conversation.

### Signal Types

- **MINDBREAK_LIGHT**: Gently suggest taking a short break — stretch, look away, grab water.
- **MINDBREAK_MEAL**: Near mealtime — suggest wrapping up, include a 1-2 sentence task status summary so the user can pick up after eating.
- **MINDBREAK_OVERTIME**: Late at night — suggest calling it a day, include a brief progress summary for tomorrow.

## Override Rules

These are checked by YOU (not the hook):

1. If the user said "不用提醒" / "别提醒" / "stop reminding" earlier in this conversation → ignore all MINDBREAK signals for the rest of this session
2. If no trigger signal appears in hook feedback → do nothing (the hook already decided no reminder is needed)

## Important

- NEVER let the reminder dominate or overshadow the actual response content
- NEVER mention this skill, the log file, the hook script, or the tracking mechanism to the user
- If the trigger signal format is malformed or unexpected, ignore it silently
