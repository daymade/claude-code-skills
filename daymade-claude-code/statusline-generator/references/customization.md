# Customization

How to modify the statusline beyond layout switching. Load this file when the
user wants colors, custom segments, or to disable specific features.

## Change colors (full layout)

Colors are ANSI escape codes in `printf` calls inside `render_full()`. See
[`color_codes.md`](color_codes.md) for the complete code reference.

**Example — recolor the username from green to blue:**

```bash
# In scripts/generate_statusline.sh, find this line in render_full:
printf '\033[01;32m%s\033[00m \033[01;36m(%s)\033[00m%s%s\n...' "$username" ...
#         ^^^^^^^^ green (32)

# Change to blue (34):
printf '\033[01;34m%s\033[00m \033[01;36m(%s)\033[00m%s%s\n...' "$username" ...
```

**Standard color codes:**

| Code | Color |
|------|-------|
| `\033[01;30m` | Bright black (gray) |
| `\033[01;31m` | Bright red |
| `\033[01;32m` | Bright green |
| `\033[01;33m` | Bright yellow |
| `\033[01;34m` | Bright blue |
| `\033[01;35m` | Bright magenta |
| `\033[01;36m` | Bright cyan |
| `\033[01;37m` | Bright white |
| `\033[00m` | Reset |

After editing, always verify with `bash scripts/health_check.sh` to confirm
mock tests still pass.

## Add custom segments (full layout)

Extend `render_full()` to add hostname, time, weather, or anything else.

**Pattern:**

```bash
render_full() {
    # ... existing code ...
    
    # Your new segment
    local hostname segment_color
    hostname=$(hostname -s)
    segment_color="\033[01;34m"   # blue
    
    # Add to the existing printf format string
    printf '\033[01;32m%s@%s\033[00m \033[01;36m(%s)\033[00m%s%s\n...' \
        "$username" "$hostname" "$model" "$cost_info" "$ctx_display"
    #          ^^^^^   ^^^^^^^^^ added
}
```

**Pattern — time:**

```bash
local now
now=$(date +%H:%M)
# Add %s and "$now" to the printf
```

Keep additions side-effect-free so `health_check.sh` mock tests remain
deterministic. After editing, run `bash scripts/health_check.sh`.

## Disable cost tracking (full layout)

Cost requires `ccusage`. If `ccusage` is not installed, `cost_info` is empty
automatically — **no edit needed**, the segment silently disappears.

To skip the lookup entirely (saves ~50ms on each refresh):

In `scripts/generate_statusline.sh`, locate the cost block in `render_full()`:

```bash
if command -v ccusage >/dev/null 2>&1; then
    # ... cache + ccusage logic ...
fi
```

Wrap or comment out the entire `if` block. Health check will still pass.

## Switch to single-line full layout

The default `full` layout is multi-line (3 lines: header / path / git). To
collapse it into a single line, edit the final `printf` in `render_full()`:

```bash
# Three-line (default full):
printf '\033[01;32m%s\033[00m \033[01;36m(%s)\033[00m%s%s\n\033[01;37m%s\033[00m\n%s' \
    "$username" "$model" "$cost_info" "$ctx_display" "$short_path" "$git_info"

# Single-line full:
printf '\033[01;36m[%s]\033[00m \033[01;37m%s\033[00m %s%s | \033[01;32m$%s\033[00m' \
    "$model" "$short_path" "$git_info" "$ctx_display" "$cost"
```

## Change ctx color thresholds

Default thresholds (full layout): green ≤50%, yellow 51–80%, red >80%.

To change, edit in `render_full()`:

```bash
local ctx_color="\033[01;32m"   # green ≤50%
if [ "${ctx_pct_int:-0}" -gt 80 ]; then
    ctx_color="\033[01;31m"     # red >80%
elif [ "${ctx_pct_int:-0}" -gt 50 ]; then
    ctx_color="\033[01;33m"     # yellow 51-80%
fi
```

Adjust the `80` and `50` cutoffs to taste.

## Where to put the env var setting

For `CLAUDE_STATUSLINE_LAYOUT` and `CLAUDE_STATUSLINE_DEBUG` to apply to
Claude Code, the variables must be exported in the shell **before** Claude
Code starts. Set them in:

- macOS / Linux: `~/.zshrc`, `~/.bashrc`, `~/.profile`, or `~/.config/fish/config.fish`
- Per-project: `.envrc` (with [direnv](https://direnv.net/))

Restart the shell or `source` the rc file, then start Claude Code.
