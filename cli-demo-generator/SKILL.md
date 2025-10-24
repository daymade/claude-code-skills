---
name: cli-demo-generator
description: This skill should be used when users want to create animated CLI demos, terminal recordings, or command-line demonstration GIFs. It supports both manual tape file creation and automated demo generation from command descriptions. Use when users mention creating demos, recording terminal sessions, or generating animated GIFs of CLI workflows.
---

# CLI Demo Generator

Generate professional animated CLI demos with ease. This skill supports both automated generation from command descriptions and manual control for custom demos.

## When to Use This Skill

Trigger this skill when users request:
- "Create a demo showing how to install my package"
- "Generate a CLI demo of these commands"
- "Make an animated GIF of my terminal workflow"
- "Record a terminal session and convert to GIF"
- "Batch generate demos from this config"
- "Create an interactive typing demo"

## Core Capabilities

### 1. Automated Demo Generation (Recommended)

Use the `auto_generate_demo.py` script for quick, automated demo creation. This is the easiest and most common approach.

**Basic Usage:**
```bash
scripts/auto_generate_demo.py \
  -c "npm install my-package" \
  -c "npm run build" \
  -o demo.gif
```

**With Options:**
```bash
scripts/auto_generate_demo.py \
  -c "command1" \
  -c "command2" \
  -o output.gif \
  --title "Installation Demo" \
  --theme "Dracula" \
  --width 1400 \
  --height 700
```

**Script Parameters:**
- `-c, --command`: Command to include (can be specified multiple times)
- `-o, --output`: Output GIF file path (required)
- `--title`: Demo title (optional, shown at start)
- `--theme`: VHS theme (default: Dracula)
- `--font-size`: Font size (default: 16)
- `--width`: Terminal width (default: 1400)
- `--height`: Terminal height (default: 700)
- `--no-execute`: Generate tape file only, don't execute VHS

**Smart Features:**
- Automatic timing based on command complexity
- Optimized sleep durations (1-3s depending on operation)
- Proper spacing between commands
- Professional defaults

### 2. Batch Demo Generation

Use `batch_generate.py` for creating multiple demos from a configuration file.

**Configuration File (YAML):**
```yaml
demos:
  - name: "Install Demo"
    output: "install.gif"
    title: "Installation"
    theme: "Dracula"
    commands:
      - "npm install my-package"
      - "npm run build"

  - name: "Usage Demo"
    output: "usage.gif"
    commands:
      - "my-package --help"
      - "my-package run"
```

**Usage:**
```bash
scripts/batch_generate.py config.yaml --output-dir ./demos
```

**When to Use Batch Generation:**
- Creating a suite of related demos
- Documenting multiple features
- Generating demos for tutorials or documentation
- Maintaining consistent demo series

### 3. Interactive Recording

Use `record_interactive.sh` for recording live terminal sessions.

**Usage:**
```bash
scripts/record_interactive.sh output.gif \
  --theme "Dracula" \
  --width 1400
```

**Recording Process:**
1. Script starts asciinema recording
2. Type commands naturally in your terminal
3. Press Ctrl+D when finished
4. Script auto-converts to GIF via VHS

**When to Use Interactive Recording:**
- Demonstrating complex workflows
- Showing real command output
- Capturing live interactions
- Recording debugging sessions

### 4. Manual Tape File Creation

For maximum control, create VHS tape files manually using templates.

**Available Templates:**
- `assets/templates/basic.tape` - Simple command demo
- `assets/templates/interactive.tape` - Typing simulation

**Example Workflow:**
1. Copy template: `cp assets/templates/basic.tape my-demo.tape`
2. Edit commands and timing
3. Generate GIF: `vhs < my-demo.tape`

Consult `references/vhs_syntax.md` for complete VHS syntax reference.

## Workflow Guidance

### For Simple Demos (1-3 commands)

Use automated generation for quick results:

```bash
scripts/auto_generate_demo.py \
  -c "echo 'Hello World'" \
  -c "ls -la" \
  -o hello-demo.gif \
  --title "Hello Demo"
```

### For Multiple Related Demos

Create a batch configuration file and use batch generation:

1. Create `demos-config.yaml` with all demo definitions
2. Run: `scripts/batch_generate.py demos-config.yaml --output-dir ./output`
3. All demos generate automatically with consistent settings

### For Interactive/Complex Workflows

Use interactive recording to capture real behavior:

```bash
scripts/record_interactive.sh my-workflow.gif
# Type commands naturally
# Ctrl+D when done
```

### For Custom Timing/Layout

Create manual tape file with precise control:

1. Start with template or generate base tape with `--no-execute`
2. Edit timing, add comments, customize layout
3. Generate: `vhs < custom-demo.tape`

## Best Practices

Refer to `references/best_practices.md` for comprehensive guidelines. Key recommendations:

**Timing:**
- Quick commands (ls, pwd): 1s sleep
- Standard commands (grep, cat): 2s sleep
- Heavy operations (install, build): 3s+ sleep

**Sizing:**
- Standard: 1400x700 (recommended)
- Compact: 1200x600
- Presentations: 1800x900

**Themes:**
- Documentation: Nord, GitHub Dark
- Code demos: Dracula, Monokai
- Presentations: High-contrast themes

**Duration:**
- Target: 15-30 seconds
- Maximum: 60 seconds
- Create series for complex topics

## Troubleshooting

### VHS Not Installed

```bash
# macOS
brew install vhs

# Linux (via Go)
go install github.com/charmbracelet/vhs@latest
```

### Asciinema Not Installed

```bash
# macOS
brew install asciinema

# Linux
sudo apt install asciinema
```

### Demo File Too Large

**Solutions:**
1. Reduce duration (shorter sleep times)
2. Use smaller dimensions (1200x600)
3. Consider MP4 format: `Output demo.mp4`
4. Split into multiple shorter demos

### Output Not Readable

**Solutions:**
1. Increase font size: `--font-size 18`
2. Use wider terminal: `--width 1600`
3. Choose high-contrast theme: `--theme "Dracula"`
4. Test on target display device

## Examples

### Example 1: Quick Install Demo

User request: "Create a demo showing npm install"

```bash
scripts/auto_generate_demo.py \
  -c "npm install my-package" \
  -o install-demo.gif \
  --title "Package Installation"
```

### Example 2: Multi-Step Tutorial

User request: "Create a demo showing project setup with git clone, install, and run"

```bash
scripts/auto_generate_demo.py \
  -c "git clone https://github.com/user/repo.git" \
  -c "cd repo" \
  -c "npm install" \
  -c "npm start" \
  -o setup-demo.gif \
  --title "Project Setup" \
  --theme "Nord"
```

### Example 3: Batch Generation

User request: "Generate demos for all my CLI tool features"

1. Create `features-demos.yaml`:
```yaml
demos:
  - name: "Help Command"
    output: "help.gif"
    commands: ["my-tool --help"]

  - name: "Init Command"
    output: "init.gif"
    commands: ["my-tool init", "ls -la"]

  - name: "Run Command"
    output: "run.gif"
    commands: ["my-tool run --verbose"]
```

2. Generate all:
```bash
scripts/batch_generate.py features-demos.yaml --output-dir ./demos
```

### Example 4: Interactive Session

User request: "Record me using my CLI tool interactively"

```bash
scripts/record_interactive.sh my-session.gif --theme "Tokyo Night"
# User types commands naturally
# Ctrl+D to finish
```

## Bundled Resources

### scripts/
- **`auto_generate_demo.py`** - Automated demo generation from command lists
- **`batch_generate.py`** - Generate multiple demos from YAML/JSON config
- **`record_interactive.sh`** - Record and convert interactive terminal sessions

### references/
- **`vhs_syntax.md`** - Complete VHS tape file syntax reference
- **`best_practices.md`** - Demo creation guidelines and best practices

### assets/
- **`templates/basic.tape`** - Basic command demo template
- **`templates/interactive.tape`** - Interactive typing demo template
- **`examples/batch-config.yaml`** - Example batch configuration file

## Dependencies

**Required:**
- VHS (https://github.com/charmbracelet/vhs)

**Optional:**
- asciinema (for interactive recording)
- PyYAML (for batch YAML configs): `pip install pyyaml`

## Output Formats

VHS supports multiple output formats:

```tape
Output demo.gif     # GIF (default, best for documentation)
Output demo.mp4     # MP4 (better compression for long demos)
Output demo.webm    # WebM (smaller file size)
```

Choose based on use case:
- **GIF**: Documentation, README files, easy embedding
- **MP4**: Longer demos, better quality, smaller size
- **WebM**: Web-optimized, smallest file size

## Summary

This skill provides three main approaches:

1. **Automated** (`auto_generate_demo.py`) - Quick, easy, smart defaults
2. **Batch** (`batch_generate.py`) - Multiple demos, consistent settings
3. **Interactive** (`record_interactive.sh`) - Live recording, real output

Choose the approach that best fits the user's needs. For most cases, automated generation is the fastest and most convenient option.
