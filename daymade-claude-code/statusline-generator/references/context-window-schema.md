# Statusline Input JSON Schema

The statusline script receives a JSON object on stdin. This reference documents all known fields.

## Top-Level Fields

```json
{
  "session_id": "uuid",
  "transcript_path": "/path/to/transcript.jsonl",
  "cwd": "/current/working/dir",
  "version": "2.1.121",
  "fast_mode": false,
  "exceeds_200k_tokens": false,
  "output_style": { "name": "default" },
  "model": {
    "id": "model-id-string",
    "display_name": "Human-Readable Model Name"
  },
  "workspace": {
    "current_dir": "/path/to/cwd",
    "project_dir": "/path/to/project",
    "added_dirs": ["/additional/dir"]
  },
  "cost": {
    "total_cost_usd": 1.0868,
    "total_duration_ms": 342863,
    "total_api_duration_ms": 282122,
    "total_lines_added": 0,
    "total_lines_removed": 0
  },
  "context_window": { ... },
  "effort": { "level": "max" },
  "thinking": { "enabled": true }
}
```

## `context_window` Object (Key Fields)

```json
{
  "context_window": {
    "context_window_size": 1000000,
    "used_percentage": 9,
    "remaining_percentage": 91,
    "total_input_tokens": 83320,
    "total_output_tokens": 5456,
    "current_usage": {
      "input_tokens": 29,
      "output_tokens": 163,
      "cache_creation_input_tokens": 0,
      "cache_read_input_tokens": 88832
    }
  }
}
```

### Field Meanings

| Field | Type | Description |
|-------|------|-------------|
| `context_window_size` | number | Model's total context window in tokens (e.g., 1000000 = 1M) |
| `used_percentage` | number | Current context usage as percentage (0-100, may have decimals) |
| `remaining_percentage` | number | Remaining context capacity as percentage |
| `total_input_tokens` | number | **Session-cumulative** input tokens (not current context state) |
| `total_output_tokens` | number | **Session-cumulative** output tokens |
| `current_usage.input_tokens` | number | Current turn uncached input tokens |
| `current_usage.output_tokens` | number | Current turn output tokens |
| `current_usage.cache_creation_input_tokens` | number | Tokens written to prompt cache this turn |
| `current_usage.cache_read_input_tokens` | number | Tokens read from prompt cache this turn |

### Computing Actual Context Usage

**Correct formula:**
```
current_context_used = current_usage.input_tokens
                     + current_usage.cache_read_input_tokens
                     + current_usage.cache_creation_input_tokens
```

This sum should approximately equal `context_window_size * used_percentage / 100`.

**Do NOT use `total_input_tokens`** — it's the session-level cumulative total, which can exceed the context window size (e.g., 150K total_input_tokens in a 100K context window is normal because old content gets evicted).

### Model Context Window Sizes (Reference)

| Model Family | Typical `context_window_size` |
|-------------|------------------------------|
| Claude Opus 4.x | 200,000 |
| Claude Sonnet 4.x | 200,000 |
| Claude Opus 4.5+ | 500,000 |
| Claude Sonnet 4.5+ | 1,000,000 |
| DeepSeek V4 Flash | 200,000 |
| DeepSeek V4 Pro | 1,000,000 |
| GPT-5.x | varies |

Always read `context_window_size` from the JSON — never hardcode it.

## `cost` Object

| Field | Type | Description |
|-------|------|-------------|
| `total_cost_usd` | number | Session total cost in USD (may have >2 decimals) |
| `total_duration_ms` | number | Total wall-clock duration in ms |
| `total_api_duration_ms` | number | Total API call duration in ms |
| `total_lines_added` | number | Lines added this session |
| `total_lines_removed` | number | Lines removed this session |
