---
name: mermaid-tools
description: Extracts Mermaid diagrams from markdown files and generates high-quality PNG images using bundled scripts. Activates when working with Mermaid diagrams, converting diagrams to PNG, extracting diagrams from markdown, or processing markdown files with embedded Mermaid code.
---

# Mermaid Tools

## Overview

This skill enables extraction of Mermaid diagrams from markdown files and generation of high-quality PNG images. The skill bundles all necessary scripts (`extract-and-generate.sh`, `extract_diagrams.py`, and `puppeteer-config.json`) in the `scripts/` directory for portability and reliability.

## Core Workflow

### Standard Diagram Extraction and Generation

Extract Mermaid diagrams from a markdown file and generate PNG images using the bundled `extract-and-generate.sh` script:

```bash
cd ~/.claude/skills/mermaid-tools/scripts
./extract-and-generate.sh "<markdown_file>" "<output_directory>"
```

**Parameters:**
- `<markdown_file>`: Path to the markdown file containing Mermaid diagrams
- `<output_directory>`: (Optional) Directory for output files. Defaults to `<markdown_file_directory>/diagrams`

**Example:**
```bash
cd ~/.claude/skills/mermaid-tools/scripts
./extract-and-generate.sh "/path/to/document.md" "/path/to/output"
```

### What the Script Does

1. **Extracts** all Mermaid code blocks from the markdown file
2. **Numbers** them sequentially (01, 02, 03, etc.) in order of appearance
3. **Generates** `.mmd` files for each diagram
4. **Creates** high-resolution PNG images with smart sizing
5. **Validates** all generated PNG files

### Output Files

For each diagram, the script generates:
- `01-diagram-name.mmd` - Extracted Mermaid code
- `01-diagram-name.png` - High-resolution PNG image

The numbering ensures diagrams maintain their order from the source document.

## Advanced Usage

### Custom Dimensions and Scaling

Override default dimensions using environment variables:

```bash
cd ~/.claude/skills/mermaid-tools/scripts
MERMAID_WIDTH=1600 MERMAID_HEIGHT=1200 ./extract-and-generate.sh "<markdown_file>" "<output_directory>"
```

**Available variables:**
- `MERMAID_WIDTH` (default: 1200) - Base width in pixels
- `MERMAID_HEIGHT` (default: 800) - Base height in pixels
- `MERMAID_SCALE` (default: 2) - Scale factor for high-resolution output

### High-Resolution Output for Presentations

```bash
cd ~/.claude/skills/mermaid-tools/scripts
MERMAID_WIDTH=2400 MERMAID_HEIGHT=1800 MERMAID_SCALE=4 ./extract-and-generate.sh "<markdown_file>" "<output_directory>"
```

### Print-Quality Output

```bash
cd ~/.claude/skills/mermaid-tools/scripts
MERMAID_SCALE=5 ./extract-and-generate.sh "<markdown_file>" "<output_directory>"
```

## Smart Sizing Feature

The script automatically adjusts dimensions based on diagram type (detected from filename):

- **Timeline/Gantt**: 2400×400 (wide and short)
- **Architecture/System/Caching**: 2400×1600 (large and detailed)
- **Monitoring/Workflow/Sequence/API**: 2400×800 (wide for process flows)
- **Default**: 1200×800 (standard size)

Context-aware naming in the extraction process helps trigger appropriate smart sizing.

## Important Principles

### Use Bundled Scripts

**CRITICAL**: Use the bundled `extract-and-generate.sh` script from this skill's `scripts/` directory. All necessary dependencies are bundled together.

### Change to Script Directory

Run the script from its own directory to properly locate dependencies (`extract_diagrams.py` and `puppeteer-config.json`):

```bash
cd ~/.claude/skills/mermaid-tools/scripts
./extract-and-generate.sh "<markdown_file>" "<output_directory>"
```

Running the script without changing to the scripts directory first may fail due to missing dependencies.

## Prerequisites Verification

Before running the script, verify dependencies are installed:

1. **mermaid-cli**: `mmdc --version`
2. **Google Chrome**: `google-chrome-stable --version`
3. **Python 3**: `python3 --version`

If any are missing, consult `references/setup_and_troubleshooting.md` for installation instructions.

## Troubleshooting

For detailed troubleshooting guidance, refer to `references/setup_and_troubleshooting.md`, which covers:

- Browser launch failures
- Permission issues
- No diagrams found
- Python extraction failures
- Output quality issues
- Diagram-specific sizing problems

Quick fixes for common issues:

**Permission denied:**
```bash
chmod +x ~/.claude/skills/mermaid-tools/scripts/extract-and-generate.sh
```

**Low quality output:**
```bash
MERMAID_SCALE=3 ./extract-and-generate.sh "<markdown_file>" "<output_directory>"
```

**Chrome/Puppeteer errors:**
Verify all WSL2 dependencies are installed (see references for full list).

## Bundled Resources

### scripts/

This skill bundles all necessary scripts for Mermaid diagram generation:

- **extract-and-generate.sh** - Main script that orchestrates extraction and PNG generation
- **extract_diagrams.py** - Python script for extracting Mermaid code blocks from markdown
- **puppeteer-config.json** - Chrome/Puppeteer configuration for WSL2 environment

All scripts must be run from the `scripts/` directory to properly locate dependencies.

### references/setup_and_troubleshooting.md

Comprehensive reference documentation including:
- Complete prerequisite installation instructions
- Detailed environment variable reference
- Extensive troubleshooting guide
- WSL2-specific Chrome dependency setup
- Validation procedures

Load this reference when dealing with setup issues, installation problems, or advanced customization needs.