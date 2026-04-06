# Advanced VHS Demo Patterns

Battle-tested patterns from production demo recording workflows.

## Contents
- Self-bootstrapping tapes
- Output noise filtering with base64 wrapper
- Frame-level verification
- Post-processing with gifsicle
- Auto-detection and template rendering
- Recording script structure

## Self-Bootstrapping Tapes

A self-bootstrapping tape cleans its own state before recording, so running it twice produces identical output. Three phases:

```tape
# Phase 1: HIDDEN CLEANUP — remove previous state
Hide
Type "my-tool uninstall 2>/dev/null; my-tool reset 2>/dev/null"
Enter
Sleep 3s

# Phase 2: HIDDEN SETUP — create helpers (base64 for special chars)
Type "echo <base64-wrapper> | base64 -d > /tmp/helper.sh && source /tmp/helper.sh"
Enter
Sleep 500ms

# Phase 3: CLEAR + SHOW — wipe buffer before revealing
Type "clear"
Enter
Sleep 500ms
Show

# Phase 4: VISIBLE DEMO — what the viewer sees
Type "my-tool install"
Enter
Sleep 3s
```

**Why `clear` before `Show`:** VHS's `Hide` stops recording frames, but the terminal buffer still accumulates text. Without `clear`, the hidden commands' text appears in the first visible frame.

## Output Noise Filtering with Base64

Many CLI tools produce verbose progress output that clutters demos. The solution: a hidden shell wrapper that filters noise lines.

### Step 1: Create the wrapper function

```bash
# The function you want (can't type directly in VHS due to $/" chars)
my_tool() { command my_tool "$@" 2>&1 | grep -v -E "cache|progress|downloading|timeout"; }
```

### Step 2: Base64 encode it

```bash
echo 'my_tool() { command my_tool "$@" 2>&1 | grep -v -E "cache|progress|downloading|timeout"; }' | base64
# Output: bXlfdG9vbCgpIHsgY29tbWFuZC4uLn0K
```

### Step 3: Use in tape

```tape
Hide
Type "echo bXlfdG9vbCgpIHsgY29tbWFuZC4uLn0K | base64 -d > /tmp/w.sh && source /tmp/w.sh"
Enter
Sleep 500ms
Type "clear"
Enter
Sleep 500ms
Show

# Now `my_tool` calls the wrapper — clean output
Type "my_tool deploy"
Enter
Sleep 5s
```

### When to filter

- Git operations: filter "Cloning", "Refreshing", cache messages
- Package managers: filter download progress, cache hits
- Build tools: filter intermediate compilation steps
- Any command with `SSH not configured`, `timeout: 120s`, etc.

## Frame-Level Verification

After recording, extract and inspect key frames to verify the GIF shows what you expect.

### Extract specific frames

```bash
# Frame at position N (0-indexed)
ffmpeg -i demo.gif -vf "select=eq(n\,100)" -frames:v 1 /tmp/frame_100.png -y 2>/dev/null

# Multiple frames at once
for n in 50 200 400; do
  ffmpeg -i demo.gif -vf "select=eq(n\,$n)" -frames:v 1 "/tmp/frame_$n.png" -y 2>/dev/null
done
```

### Check total frame count and duration

```bash
ffmpeg -i demo.gif 2>&1 | grep -E "Duration|fps"
# Duration: 00:00:10.50, ... 25 fps → 262 frames total
```

### What to verify

| Frame | Check |
|-------|-------|
| First (~frame 5) | No leaked hidden commands |
| Mid (~frame N/2) | Key output visible, no noise |
| Final (~frame N-10) | All commands completed, result shown |

### Claude can read frames

Use the Read tool on extracted PNG files — Claude's vision can verify text content in terminal screenshots.

## Post-Processing with gifsicle

Speed up or optimize GIFs after recording, avoiding re-recording.

### Speed control

```bash
# 2x speed — halve frame delay (most common)
gifsicle -d2 input.gif "#0-" > output.gif

# 1.5x speed
gifsicle -d4 input.gif "#0-" > output.gif

# 3x speed
gifsicle -d1 input.gif "#0-" > output.gif
```

### Optimize file size

```bash
# Lossless optimization
gifsicle -O3 input.gif > optimized.gif

# Reduce colors (lossy but smaller)
gifsicle --colors 128 input.gif > smaller.gif
```

### Typical recording script pattern

```bash
# Record at normal speed
vhs demo.tape

# Speed up 2x for final output
cp demo.gif /tmp/demo_raw.gif
gifsicle -d2 /tmp/demo_raw.gif "#0-" > demo.gif
rm /tmp/demo_raw.gif
```

## Auto-Detection and Template Rendering

For demos that need to adapt to the environment (e.g., different repo URLs, detected tools).

### Template placeholders

Use `sed` to replace placeholders before recording:

```tape
# demo.tape (template)
Type "tool marketplace add REPO_PLACEHOLDER"
Enter
```

```bash
# Build script detects the correct repo
REPO=$(detect_repo)
sed "s|REPO_PLACEHOLDER|$REPO|g" demo.tape > /tmp/rendered.tape
vhs /tmp/rendered.tape
```

### Auto-detect pattern (shell function)

```bash
detect_repo() {
  local upstream origin
  upstream=$(git remote get-url upstream 2>/dev/null | sed 's|.*github.com[:/]||; s|\.git$||') || true
  origin=$(git remote get-url origin 2>/dev/null | sed 's|.*github.com[:/]||; s|\.git$||') || true

  # Check upstream first (canonical), then origin (fork)
  if [[ -n "$upstream" ]] && gh api "repos/$upstream/contents/.target-file" &>/dev/null; then
    echo "$upstream"
  elif [[ -n "$origin" ]]; then
    echo "$origin"
  else
    echo "fallback/default"
  fi
}
```

## Recording Script Structure

A complete recording script follows this pattern:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# 1. Check prerequisites
for cmd in vhs gifsicle; do
  command -v "$cmd" &>/dev/null || { echo "Missing: $cmd"; exit 1; }
done

# 2. Auto-detect dynamic values
REPO=$(detect_repo)
echo "Using repo: $REPO"

# 3. Render tape template
sed "s|PLACEHOLDER|$REPO|g" "$SCRIPT_DIR/demo.tape" > /tmp/rendered.tape

# 4. Clean previous state
cleanup_state || true

# 5. Record
(cd "$REPO_DIR" && vhs /tmp/rendered.tape)

# 6. Speed up
cp "$REPO_DIR/demo.gif" /tmp/raw.gif
gifsicle -d2 /tmp/raw.gif "#0-" > "$REPO_DIR/demo.gif"

# 7. Clean up
cleanup_state || true
rm -f /tmp/raw.gif /tmp/rendered.tape

# 8. Report
SIZE=$(ls -lh "$REPO_DIR/demo.gif" | awk '{print $5}')
echo "Done: demo.gif ($SIZE)"
```
