# CLI Demo Best Practices

Guidelines for creating effective, professional CLI demos.

## General Principles

### 1. Keep It Short
- **Target**: 15-30 seconds per demo
- **Maximum**: 60 seconds (unless documenting complex workflows)
- **Reason**: Short demos maintain viewer attention and are easier to consume

### 2. Show, Don't Tell
- Focus on visual demonstration over textual explanation
- Let the commands and output speak for themselves
- Add brief comment-style titles when needed

### 3. One Concept Per Demo
- Each demo should illustrate a single feature or workflow
- For complex topics, create a series of short demos
- Better to have multiple focused demos than one lengthy tutorial

## Technical Guidelines

### Timing and Pacing

**Command Entry Timing:**
```
Type "command" Sleep 500ms   # Fast enough to feel natural
Enter                        # Immediate
```

**Post-Command Sleep (based on operation):**
- **Quick commands** (ls, pwd, echo): 1s
- **Standard commands** (grep, cat, git status): 1.5-2s
- **Heavy operations** (install, build, test): 3s+
- **Final command**: 2-3s for viewers to see result

**Between Sections:**
- Add 1-1.5s between related commands
- Add 2s+ between different concepts

### Terminal Dimensions

**Standard Sizes:**
```tape
# Compact (for narrow contexts)
Set Width 1200
Set Height 600

# Standard (recommended default)
Set Width 1400
Set Height 700

# Wide (for complex output)
Set Width 1600
Set Height 800

# Presentation (for slides)
Set Width 1800
Set Height 900
```

**Choosing Dimensions:**
- Consider the output width (avoid wrapping)
- Test with longest expected line
- Standard 1400x700 works for most cases

### Font Sizing

**Recommended Sizes:**
```tape
# Documentation (small, information-dense)
Set FontSize 14

# Standard demos (readable)
Set FontSize 16

# Presentations (clear from distance)
Set FontSize 20-24
```

**Choosing Font Size:**
- Smaller fonts allow more output visibility
- Larger fonts improve readability on mobile
- Test on target display devices

### Theme Selection

**By Context:**

**Documentation/Tutorials:**
- Nord - Clean, professional
- GitHub Dark - Familiar to developers
- Catppuccin - Easy on eyes for long reading

**Code Demos:**
- Dracula - Popular, high contrast
- Monokai - Classic, widely recognized
- Tokyo Night - Modern, vibrant

**Presentations:**
- High-contrast themes for visibility
- Avoid very dark themes in bright rooms
- Test on actual projection equipment

**Brand Alignment:**
- Match company/project color schemes
- Custom themes can be defined

## Content Guidelines

### Command Structure

**Clear Sequencing:**
```tape
# Good - Shows logical flow
Type "# Step 1: Setup"
Sleep 500ms Enter
Type "mkdir project && cd project"
Sleep 500ms Enter
Sleep 2s

Type "# Step 2: Install"
Sleep 500ms Enter
Type "npm install"
Sleep 500ms Enter
Sleep 3s
```

**Avoid:**
```tape
# Bad - No context, rushed
Type "mkdir project"
Enter
Type "cd project"
Enter
Type "npm install"
Enter
```

### Adding Context

**Title Slides:**
```tape
Type "# Demo: Package Installation"
Sleep 500ms Enter
Sleep 1.5s
```

**Section Headers:**
```tape
Type "## Installing dependencies..."
Sleep 500ms Enter
Sleep 1s
```

**Comments:**
```tape
Type "npm install  # This may take a moment"
Sleep 500ms Enter
```

### Output Visibility

**Ensure Key Output is Visible:**
- Let important output display fully before next command
- For long output, consider showing excerpts
- Use `Sleep` to give viewers time to read

**Managing Long Output:**
```tape
# Option 1: Show beginning only
Type "npm install"
Enter
Sleep 2s    # Shows first part of output
Ctrl+C      # Stop before it scrolls too much

# Option 2: Use commands that limit output
Type "git log --oneline -5"  # Show last 5 commits only
Enter
```

## File Size Optimization

### Target Sizes
- **Small demos** (<500KB): Ideal for documentation
- **Medium demos** (500KB-1MB): Acceptable for most uses
- **Large demos** (>1MB): Consider compression or shorter duration

### Reducing File Size

**1. Shorter Duration:**
```tape
# Reduce unnecessary sleep time
Sleep 1s    # Instead of Sleep 3s
```

**2. Smaller Dimensions:**
```tape
# Use compact size for simple demos
Set Width 1200
Set Height 600
```

**3. Appropriate Format:**
```tape
Output demo.mp4     # Better compression for longer demos
Output demo.webm    # Smaller file size than GIF
Output demo.gif     # Good for short demos
```

## Accessibility

### Consider All Viewers

**Color Choices:**
- High contrast improves readability
- Avoid color-only distinctions
- Test with color-blind simulators

**Font Size:**
- 16pt minimum for web documentation
- 20pt minimum for presentations
- Test on mobile devices

**Pacing:**
- Allow time to read output
- Avoid rapid command sequences
- Provide clear visual breaks

## Testing and Quality Assurance

### Before Publishing

**1. Watch the Entire Demo:**
- Verify all commands execute as expected
- Check for timing issues
- Ensure output is visible

**2. Test on Different Displays:**
- Desktop monitors
- Mobile devices
- Projection screens (if for presentations)

**3. Check File Size:**
- Optimize if necessary
- Consider alternative formats

**4. Verify Accessibility:**
- Readable fonts
- Clear contrast
- Appropriate pacing

**5. Get Feedback:**
- Show to someone unfamiliar with the content
- Ask if the flow is clear
- Adjust based on feedback

## Common Mistakes to Avoid

### ❌ Too Fast
```tape
Type "command1" Enter Sleep 0.5s
Type "command2" Enter Sleep 0.5s
Type "command3" Enter Sleep 0.5s
# Viewers can't process this
```

### ✅ Appropriate Pacing
```tape
Type "command1" Sleep 500ms Enter
Sleep 2s

Type "command2" Sleep 500ms Enter
Sleep 2s
```

### ❌ No Context
```tape
Type "npm install"
Enter
# What are we installing? Why?
```

### ✅ With Context
```tape
Type "# Installing dependencies"
Sleep 500ms Enter
Sleep 1s

Type "npm install"
Sleep 500ms Enter
```

### ❌ Output Scrolls Too Fast
```tape
Type "long-running-command"
Enter
Sleep 1s  # Output still scrolling!
Type "next-command"
```

### ✅ Allow Output to Complete
```tape
Type "long-running-command"
Enter
Sleep 3s  # Let it finish

Type "next-command"
```

## Examples of Good Demos

### Simple Feature Demo (15 seconds)
```tape
Output feature-demo.gif
Set FontSize 16
Set Width 1400
Set Height 700
Set Theme "Dracula"

Type "# Demo: Quick Start" Sleep 500ms Enter
Sleep 1.5s

Type "npm install my-tool" Sleep 500ms Enter
Sleep 2.5s

Type "my-tool --help" Sleep 500ms Enter
Sleep 2s
```

### Multi-Step Workflow (30 seconds)
```tape
Output workflow-demo.gif
Set FontSize 16
Set Width 1400
Set Height 700
Set Theme "Nord"

Type "# Demo: Complete Workflow" Sleep 500ms Enter
Sleep 1.5s

Type "# 1. Create project" Sleep 500ms Enter
Type "mkdir my-project && cd my-project" Sleep 500ms Enter
Sleep 2s

Type "# 2. Initialize" Sleep 500ms Enter
Type "npm init -y" Sleep 500ms Enter
Sleep 2s

Type "# 3. Install package" Sleep 500ms Enter
Type "npm install express" Sleep 500ms Enter
Sleep 3s

Type "# 4. Ready to code!" Sleep 500ms Enter
Sleep 2s
```

## Summary Checklist

Before publishing a demo, verify:

- [ ] Duration is appropriate (15-30s ideal)
- [ ] Timing allows reading output
- [ ] Commands are clear and purposeful
- [ ] Context is provided where needed
- [ ] Output is fully visible
- [ ] File size is reasonable
- [ ] Theme and fonts are readable
- [ ] Tested on target devices
- [ ] Accessible to all viewers
- [ ] Demonstrates one clear concept
