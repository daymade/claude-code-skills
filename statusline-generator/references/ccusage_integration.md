# ccusage Integration Reference

This reference explains how the statusline integrates with `ccusage` for cost tracking and troubleshooting.

## What is ccusage?

`ccusage` is a command-line tool that tracks Claude Code usage and costs by reading conversation transcripts. It provides session-based and daily cost reporting.

## How Statusline Uses ccusage

The statusline script calls `ccusage` to display session and daily costs:

```bash
session=$(ccusage session --json --offline -o desc 2>/dev/null | jq -r '.sessions[0].totalCost' 2>/dev/null | xargs printf "%.2f")
daily=$(ccusage daily --json --offline -o desc 2>/dev/null | jq -r '.daily[0].totalCost' 2>/dev/null | xargs printf "%.2f")
```

### Key Features

1. **JSON Output**: Uses `--json` flag for machine-readable output
2. **Offline Mode**: Uses `--offline` to avoid fetching pricing data (faster)
3. **Descending Order**: Uses `-o desc` to get most recent data first
4. **Error Suppression**: Redirects errors to `/dev/null` to prevent statusline clutter

## Caching Strategy

To avoid slowing down the statusline, costs are cached:

- **Cache File**: `/tmp/claude_cost_cache_YYYYMMDD_HHMM.txt`
- **Cache Duration**: 2 minutes (refreshes based on minute timestamp)
- **Background Refresh**: First run fetches costs in background
- **Fallback**: Uses previous cache (up to 10 minutes old) while refreshing

### Cache Behavior

1. **First Display**: Statusline shows without costs
2. **2-5 Seconds Later**: Costs appear after background fetch completes
3. **Next 2 Minutes**: Cached costs shown instantly
4. **After 2 Minutes**: New cache generated in background

## ccusage JSON Structure

### Session Data
```json
{
  "sessions": [
    {
      "sessionId": "conversation-id",
      "totalCost": 0.26206769999999996,
      "inputTokens": 2065,
      "outputTokens": 1313,
      "lastActivity": "2025-10-20"
    }
  ]
}
```

### Daily Data
```json
{
  "daily": [
    {
      "date": "2025-10-20",
      "totalCost": 25.751092800000013,
      "inputTokens": 16796,
      "outputTokens": 142657
    }
  ]
}
```

## Troubleshooting

### Costs Not Showing

**Symptoms**: Statusline appears but no `[$X.XX/$X.XX]` shown

**Possible Causes**:
1. ccusage not installed
2. ccusage not in PATH
3. No transcript data available yet
4. Background fetch still in progress

**Solutions**:
```bash
# Check if ccusage is installed
which ccusage

# Test ccusage manually
ccusage session --json --offline -o desc

# Check cache files
ls -lh /tmp/claude_cost_cache_*.txt

# Wait 5-10 seconds and check again (first fetch runs in background)
```

### Slow Statusline

**Symptoms**: Statusline takes >1 second to appear

**Possible Causes**:
1. Cache not working (being regenerated too often)
2. ccusage taking too long to execute

**Solutions**:
```bash
# Check cache timestamp
ls -lh /tmp/claude_cost_cache_*.txt

# Test ccusage speed
time ccusage session --json --offline -o desc

# If slow, consider disabling cost tracking by commenting out cost section in script
```

### Incorrect Costs

**Symptoms**: Costs don't match expected values

**Possible Causes**:
1. Cache stale (showing old data)
2. ccusage database out of sync
3. Multiple Claude sessions confusing costs

**Solutions**:
```bash
# Clear cache to force refresh
rm /tmp/claude_cost_cache_*.txt

# Verify ccusage data
ccusage session -o desc | head -20
ccusage daily -o desc | head -20

# Check ccusage database location
ls -lh ~/.config/ccusage/
```

## Installing ccusage

If ccusage is not installed:

```bash
# Using npm (Node.js required)
npm install -g @anthropic-ai/ccusage

# Or check the official ccusage repository for latest installation instructions
```

## Disabling Cost Tracking

To disable costs (e.g., if ccusage not available), comment out the cost section in `generate_statusline.sh`:

```bash
# Cost information using ccusage with caching
cost_info=""
# cache_file="/tmp/claude_cost_cache_$(date +%Y%m%d_%H%M).txt"
# ... rest of cost section commented out
```

Then update the final printf to remove `%s` for cost_info:

```bash
printf '\033[01;32m%s\033[00m \033[01;36m(%s)\033[00m\n\033[01;37m%s\033[00m\n%s' \
    "$username" "$model" "$short_path" "$git_info"
```