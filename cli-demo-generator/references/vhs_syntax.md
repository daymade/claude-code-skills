# VHS Tape File Syntax Reference

VHS (Video Home System) is a tool for creating terminal recordings as code. This reference covers the complete tape file syntax.

## Basic Structure

```tape
Output demo.gif

Set FontSize 16
Set Width 1400
Set Height 700
Set Theme "Dracula"

Type "echo Hello"
Enter
Sleep 1s
```

## Configuration Commands

### Output

Specify the output file path and format:

```tape
Output demo.gif       # GIF format (default)
Output demo.mp4       # MP4 video
Output demo.webm      # WebM video
```

### Set Commands

Configure the terminal appearance:

```tape
Set FontSize 16               # Font size (10-72)
Set Width 1400                # Terminal width in pixels
Set Height 700                # Terminal height in pixels
Set Theme "Dracula"           # Color theme
Set Padding 20                # Padding around terminal (pixels)
Set TypingSpeed 50ms          # Speed of typing animation
Set Shell bash                # Shell to use (bash, zsh, fish)
Set FontFamily "MonoLisa"     # Font family name
```

## Interaction Commands

### Type

Simulate typing text:

```tape
Type "ls -la"           # Type the command
Type "Hello World"      # Type any text
```

### Enter

Press the Enter key:

```tape
Enter
```

### Backspace

Delete characters:

```tape
Backspace              # Delete one character
Backspace 5            # Delete 5 characters
```

### Sleep

Pause execution:

```tape
Sleep 1s               # Sleep for 1 second
Sleep 500ms            # Sleep for 500 milliseconds
Sleep 2.5s             # Sleep for 2.5 seconds
```

### Ctrl+C

Send interrupt signal:

```tape
Ctrl+C
```

### Key combinations

```tape
Ctrl+D                 # End of transmission
Ctrl+L                 # Clear screen
Tab                    # Tab completion
```

## Advanced Features

### Play (asciinema integration)

Play back an asciinema recording:

```tape
Play recording.cast
```

### Hide/Show

Control terminal visibility:

```tape
Hide
Type "secret command"
Show
```

### Screenshot

Take a screenshot at specific point:

```tape
Screenshot demo-screenshot.png
```

## Available Themes

Popular built-in themes:

- **Dracula** - Dark purple theme
- **Monokai** - Classic dark theme
- **Nord** - Arctic-inspired cool theme
- **Catppuccin** - Soothing pastel theme
- **GitHub Dark** - GitHub's dark theme
- **Tokyo Night** - Vibrant dark theme
- **Gruvbox** - Retro groove colors

## Example Templates

### Basic Command Demo

```tape
Output demo.gif

Set FontSize 16
Set Width 1400
Set Height 700
Set Theme "Dracula"

Type "# Demo Title" Sleep 500ms Enter
Sleep 1s

Type "command1" Sleep 500ms Enter
Sleep 2s

Type "command2" Sleep 500ms Enter
Sleep 2s
```

### Interactive Typing Demo

```tape
Output demo.gif

Set FontSize 16
Set Width 1400
Set Height 700
Set Theme "Dracula"
Set TypingSpeed 100ms

Type "npm install my-package"
Enter
Sleep 3s

Type "npm start"
Enter
Sleep 2s
```

### Multi-Step Tutorial

```tape
Output tutorial.gif

Set FontSize 16
Set Width 1400
Set Height 700
Set Theme "Tokyo Night"

Type "# Step 1: Clone the repository" Enter
Sleep 1s
Type "git clone https://github.com/user/repo.git" Enter
Sleep 3s

Type "# Step 2: Install dependencies" Enter
Sleep 1s
Type "cd repo && npm install" Enter
Sleep 3s

Type "# Step 3: Run the app" Enter
Sleep 1s
Type "npm start" Enter
Sleep 2s
```

## Best Practices

1. **Timing**: Use appropriate sleep durations
   - Quick commands: 1s
   - Medium commands: 2s
   - Long commands (install, build): 3s+

2. **Width/Height**: Standard sizes
   - Compact: 1200x600
   - Standard: 1400x700
   - Wide: 1600x800

3. **Font Size**: Readability
   - Small terminals: 14-16
   - Standard: 16-18
   - Presentations: 20-24

4. **Theme Selection**: Consider context
   - Code demos: Dracula, Monokai
   - Documentation: Nord, GitHub Dark
   - Presentations: High-contrast themes

5. **Title Slides**: Add context
   ```tape
   Type "# Demo: Project Setup" Enter
   Sleep 1s
   ```

6. **Cleanup**: Show clear ending
   ```tape
   Sleep 2s
   Type "# Demo complete!" Enter
   ```
