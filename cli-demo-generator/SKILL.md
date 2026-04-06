---
name: cli-demo-generator
description: Generates professional animated CLI demos as GIFs using VHS terminal recordings. Handles tape file creation, self-bootstrapping demos with hidden setup, output noise filtering, post-processing speed-up, and frame-level verification. Use when users want to create terminal demos, record CLI workflows as GIFs, generate animated documentation, build demo tapes for README files, or need to showcase any command-line tool visually. Also triggers on "record terminal", "VHS tape", "demo GIF", "animate my CLI", or any request to visually demonstrate shell commands.
---

# CLI Demo Generator

Create professional animated CLI demos. Four approaches, from fully automated to pixel-precise manual control.

## Quick Start

**Simplest path** — give commands, get GIF:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/auto_generate_demo.py \
  -c "npm install my-package" \
  -c "npm run build" \
  -o demo.gif
```

**Self-bootstrapping demo** — for repeatable recordings that clean their own state:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/auto_generate_demo.py \
  -c "npm install my-package" \
  -c "npm run build" \
  -o demo.gif \
  --bootstrap "npm uninstall my-package 2>/dev/null" \
  --speed 2
```

## Critical: VHS Parser Limitations

VHS `Type` strings cannot contain `$`, `\"`, or backticks. These cause parse errors:

```tape
# FAILS — VHS parser rejects special chars
Type "echo \"hello $USER\""
Type "claude() { command claude \"$@\"; }"
```

**Workaround: base64 encode the command**, decode at runtime:

```bash
# 1. Encode your complex command
echo 'claude() { command claude "$@" 2>&1 | grep -v "noise"; }' | base64
# Output: Y2xhdWRlKCkgey4uLn0K

# 2. Use in tape
Type "echo Y2xhdWRlKCkgey4uLn0K | base64 -d > /tmp/wrapper.sh && source /tmp/wrapper.sh"
```

This pattern is essential for output filtering, function definitions, and any command with shell special characters.

## Approaches

### 1. Automated Generation (Recommended)

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/auto_generate_demo.py \
  -c "command1" -c "command2" \
  -o output.gif \
  --title "My Demo" \
  --theme "Catppuccin Latte" \
  --font-size 24 \
  --width 1400 --height 600
```

| Flag | Default | Description |
|------|---------|-------------|
| `-c` | required | Command to include (repeatable) |
| `-o` | required | Output GIF path |
| `--title` | none | Title shown at start |
| `--theme` | Dracula | VHS theme name |
| `--font-size` | 16 | Font size in pt |
| `--width` | 1400 | Terminal width px |
| `--height` | 700 | Terminal height px |
| `--bootstrap` | none | Hidden setup command (repeatable) |
| `--filter` | none | Regex pattern to filter from output |
| `--speed` | 1 | Playback speed multiplier (uses gifsicle) |
| `--no-execute` | false | Generate .tape only |

Smart timing: `install`/`build`/`test`/`deploy` → 3s, `ls`/`pwd`/`echo` → 1s, others → 2s.

### 2. Batch Generation

Create multiple demos from one config:

```yaml
# demos.yaml
demos:
  - name: "Install"
    output: "install.gif"
    commands: ["npm install my-package"]
  - name: "Usage"
    output: "usage.gif"
    commands: ["my-package --help", "my-package run"]
```

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/batch_generate.py demos.yaml --output-dir ./gifs
```

### 3. Interactive Recording

Record a live terminal session:

```bash
bash ${CLAUDE_SKILL_DIR}/scripts/record_interactive.sh output.gif --theme "Catppuccin Latte"
# Type commands naturally, Ctrl+D when done
```

Requires asciinema (`brew install asciinema`).

### 4. Manual Tape File

For maximum control, write a tape directly. Templates in `assets/templates/`:

- `basic.tape` — simple command sequence
- `interactive.tape` — typing simulation
- `self-bootstrap.tape` — **self-cleaning demo with hidden setup** (recommended for repeatable demos)

## Advanced Patterns

These patterns come from production use. See `references/advanced_patterns.md` for full details.

### Self-Bootstrapping Demos

Demos that clean previous state, set up environment, and hide all of it from the viewer:

```tape
Hide
Type "cleanup-previous-state 2>/dev/null"
Enter
Sleep 2s
Type "clear"
Enter
Sleep 500ms
Show

Type "the-command-users-see"
Enter
Sleep 3s
```

The `Hide` → commands → `clear` → `Show` sequence is critical. `clear` wipes the terminal buffer so hidden commands don't leak into the GIF.

### Output Noise Filtering

Filter noisy progress lines from commands that produce verbose output:

```tape
# Hidden: create a wrapper function that filters noise
Hide
Type "echo <base64-encoded-wrapper> | base64 -d > /tmp/w.sh && source /tmp/w.sh"
Enter
Sleep 500ms
Type "clear"
Enter
Sleep 500ms
Show

# Visible: clean command, filtered output
Type "my-noisy-command"
Enter
Sleep 3s
```

### Frame Verification

After recording, verify GIF content by extracting key frames:

```bash
# Extract frames at specific positions
ffmpeg -i demo.gif -vf "select=eq(n\,100)" -frames:v 1 /tmp/frame.png -y 2>/dev/null

# View the frame (Claude can read images)
# Use Read tool on /tmp/frame.png to verify content
```

### Post-Processing Speed-Up

Use gifsicle to speed up recordings without re-recording:

```bash
# 2x speed (halve frame delay)
gifsicle -d2 original.gif "#0-" > fast.gif

# 1.5x speed
gifsicle -d4 original.gif "#0-" > faster.gif
```

### Template Placeholder Pattern

Keep tape files generic with placeholders, replace at build time:

```tape
# In tape file
Type "claude plugin marketplace add MARKETPLACE_REPO"

# In build script
sed "s|MARKETPLACE_REPO|$DETECTED_REPO|g" template.tape > rendered.tape
vhs rendered.tape
```

## Timing & Sizing Reference

| Context | Width | Height | Font | Duration |
|---------|-------|--------|------|----------|
| README/docs | 1400 | 600 | 16-20 | 10-20s |
| Presentation | 1800 | 900 | 24 | 15-30s |
| Compact embed | 1200 | 600 | 14-16 | 10-15s |
| Wide output | 1600 | 800 | 16 | 15-30s |

See `references/best_practices.md` for detailed guidelines.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| VHS not installed | `brew install charmbracelet/tap/vhs` |
| gifsicle not installed | `brew install gifsicle` |
| GIF too large | Reduce dimensions, sleep times, or use `--speed 2` |
| Text wraps/breaks | Increase `--width` or decrease `--font-size` |
| VHS parse error on `$` or `\"` | Use base64 encoding (see Critical section above) |
| Hidden commands leak into GIF | Add `clear` + `Sleep 500ms` before `Show` |
| Commands execute before previous finishes | Increase `Sleep` duration |

## Dependencies

**Required:** VHS (`brew install charmbracelet/tap/vhs`)

**Optional:** gifsicle (speed-up), asciinema (interactive recording), ffmpeg (frame verification), PyYAML (batch YAML configs)
