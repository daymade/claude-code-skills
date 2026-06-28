# Explanation Guide

## Plain-language translations

- **Input tokens**: words/files/context sent into the model.
- **Output tokens**: words/code the model produced.
- **Cache create**: large context stored for reuse.
- **Cache read**: previously stored context re-read in later turns. This often dominates Claude Code usage because the agent repeatedly brings project context back into the conversation.
- **5-hour block**: a ccusage grouping that approximates Claude Code session quota windows. It is useful for diagnosing rapid burn, but it is not a contract for the user's exact subscription quota.

## Interpretation patterns

- If cache read is over 80% of total tokens, explain that the user did not type that much; the agent was repeatedly reading large context.
- If a model has similar tokens but higher cost than another, say the model is more expensive per effective token in the ccusage pricing estimate.
- If today's cost rank is high but token rank is ordinary, say the day was not unusually large in raw tokens, but the chosen model mix made it expensive.
- If a block has many entries, explain that the "two questions" likely involved many internal turns/tool calls rather than two simple request-response pairs.
- If session output is empty or unavailable, fall back to daily and block evidence.

## Caveats to include

- `ccusage` estimates cost from local usage logs and pricing data. Treat it as strong local evidence, not an official invoice.
- Local logs can include multiple projects and Claude Code sessions.
- Ordinary Claude.ai desktop chats may not be represented unless they generated Claude Code usage logs.
