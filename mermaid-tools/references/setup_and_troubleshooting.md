# Mermaid Diagram Generation - Setup and Troubleshooting

## Table of Contents
- [Prerequisites](#prerequisites)
- [Script Locations](#script-locations)
- [Features](#features)
- [Environment Variables](#environment-variables)
- [Troubleshooting](#troubleshooting)
- [Validation](#validation)

## Prerequisites

### 1. Node.js and mermaid-cli

Install mermaid-cli globally:
```bash
npm install -g @mermaid-js/mermaid-cli
```

Verify installation:
```bash
mmdc --version
```

### 2. Google Chrome for WSL2

Install Chrome and dependencies:
```bash
# Add Chrome repository
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list

# Update and install Chrome
sudo apt update
sudo apt install -y google-chrome-stable

# Install required dependencies for WSL2
sudo apt install -y libgtk2.0-0 libgtk-3-0 libgbm-dev libnotify-dev libgconf-2-4 libnss3 libxss1 libasound2 libxtst6 xauth xvfb fonts-liberation libxml2-utils
```

Verify Chrome installation:
```bash
google-chrome-stable --version
```

### 3. Python 3

The extraction script requires Python 3 (usually pre-installed on Ubuntu):
```bash
python3 --version
```

## Script Locations

The mermaid diagram tools are bundled with this skill in the `scripts/` directory:
- Main script: `~/.claude/skills/mermaid-tools/scripts/extract-and-generate.sh`
- Python extractor: `~/.claude/skills/mermaid-tools/scripts/extract_diagrams.py`
- Puppeteer config: `~/.claude/skills/mermaid-tools/scripts/puppeteer-config.json`

All scripts should be run from the `scripts/` directory to properly locate dependencies.

## Features

### Smart Sizing

The script automatically adjusts diagram dimensions based on filename patterns:

- **Timeline/Gantt charts**: 2400x400 (wide and short)
- **Architecture/System/Caching diagrams**: 2400x1600 (large and detailed)
- **Monitoring/Workflow/Sequence/API diagrams**: 2400x800 (wide for process flows)
- **Default**: 1200x800 (standard size)

### Sequential Numbering

Diagrams are automatically numbered sequentially (01, 02, 03, etc.) in the order they appear in the markdown file.

### High-Resolution Output

Default scale factor is 2x for high-quality output. Can be customized with environment variables.

## Environment Variables

Override default dimensions and scaling:

| Variable | Default | Description |
|----------|---------|-------------|
| `MERMAID_WIDTH` | 1200 | Base width for generated PNGs |
| `MERMAID_HEIGHT` | 800 | Base height for generated PNGs |
| `MERMAID_SCALE` | 2 | Scale factor for high-resolution output |

### Examples

```bash
# Custom dimensions
MERMAID_WIDTH=1600 MERMAID_HEIGHT=1200 ./extract-and-generate.sh "file.md" "output_dir"

# High-resolution mode for presentations
MERMAID_WIDTH=2400 MERMAID_HEIGHT=1800 MERMAID_SCALE=4 ./extract-and-generate.sh "file.md" "output_dir"

# Ultra-high resolution for print materials
MERMAID_SCALE=5 ./extract-and-generate.sh "file.md" "output_dir"
```

## Troubleshooting

### Browser Launch Failures

**Symptom**: Errors about Chrome not launching or Puppeteer failures

**Solution**:
1. Verify Chrome is installed: `google-chrome-stable --version`
2. Check Chrome path in script matches: `/usr/bin/google-chrome-stable`
3. Ensure all dependencies are installed (see Prerequisites section 2)
4. Verify puppeteer-config.json exists at the expected location

### Permission Issues

**Symptom**: "Permission denied" when running the script

**Solution**:
```bash
chmod +x ~/.claude/skills/mermaid-tools/scripts/extract-and-generate.sh
```

### No Diagrams Found

**Symptom**: Script reports "No .mmd files found" or "No diagrams extracted"

**Solution**:
1. Verify the markdown file contains Mermaid code blocks (` ```mermaid`)
2. Check the markdown file path is correct
3. Ensure Mermaid code blocks are properly formatted

### Python Extraction Failures

**Symptom**: Errors during the extraction phase

**Solution**:
1. Verify Python 3 is installed: `python3 --version`
2. Check the markdown file encoding (should be UTF-8)
3. Review the markdown file for malformed Mermaid code blocks

### Output Quality Issues

**Symptom**: Generated images are too small or low quality

**Solution**:
Use environment variables to increase dimensions and scale:
```bash
MERMAID_WIDTH=2400 MERMAID_HEIGHT=1800 MERMAID_SCALE=3 ./extract-and-generate.sh "file.md" "output_dir"
```

### Diagram-Specific Sizing Issues

**Symptom**: Specific diagram types don't render well with default sizes

**Solution**:
The script has smart sizing for common patterns, but you can override for specific cases:
```bash
# For very wide sequence diagrams
MERMAID_WIDTH=3000 MERMAID_HEIGHT=1000 ./extract-and-generate.sh "file.md" "output_dir"

# For very tall flowcharts
MERMAID_WIDTH=1200 MERMAID_HEIGHT=2400 ./extract-and-generate.sh "file.md" "output_dir"
```

## Validation

The script automatically validates generated PNG files by:
1. Checking file size is non-zero
2. Verifying the file is a valid PNG image
3. Reporting actual dimensions
4. Displaying file size in bytes

Look for ✅ validation messages in the output to confirm successful generation.