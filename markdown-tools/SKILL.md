---
name: markdown-tools
description: Converts documents to markdown (PDFs, Word docs, PowerPoint, Confluence exports) with Windows/WSL path handling. Activates when converting .doc/.docx/PDF/PPTX files to markdown, processing Confluence exports, handling Windows/WSL path conversions, or working with markitdown utility.
---

# Markdown Tools

## Overview

This skill provides document conversion to markdown with Windows/WSL path handling support. It helps convert various document formats to markdown and handles path conversions between Windows and WSL environments.

## Core Capabilities

### 1. Markdown Conversion
Convert documents to markdown format with automatic Windows/WSL path handling.

### 2. Confluence Export Processing
Handle Confluence .doc exports with special characters for knowledge base integration.

## Quick Start

### Convert Any Document to Markdown

```bash
# Basic conversion
markitdown "path/to/document.pdf" > output.md

# WSL path example
markitdown "/mnt/c/Users/username/Documents/file.docx" > output.md
```

See `references/conversion-examples.md` for detailed examples of various conversion scenarios.

### Convert Confluence Export

```bash
# Direct conversion for simple exports
markitdown "confluence-export.doc" > output.md

# For exports with special characters, see references/
```

## Path Conversion

### Windows to WSL Path Format

Windows paths must be converted to WSL format before use in bash commands.

**Conversion rules:**
- Replace `C:\` with `/mnt/c/`
- Replace `\` with `/`
- Preserve spaces and special characters
- Use quotes for paths with spaces

**Example conversions:**
```bash
# Windows path
C:\Users\username\Documents\file.doc

# WSL path
/mnt/c/Users/username/Documents/file.doc
```

**Helper script:** Use `scripts/convert_path.py` to automate conversion:

```bash
python scripts/convert_path.py "C:\Users\username\Downloads\document.doc"
```

See `references/conversion-examples.md` for detailed path conversion examples.

## Document Conversion Workflows

### Workflow 1: Simple Markdown Conversion

For straightforward document conversions (PDF, .docx without special characters):

1. Convert Windows path to WSL format (if needed)
2. Run markitdown
3. Redirect output to .md file

See `references/conversion-examples.md` for detailed examples.

### Workflow 2: Confluence Export with Special Characters

For Confluence .doc exports that contain special characters or complex formatting:

1. Save .doc file to accessible location
2. Use appropriate conversion method (see references)
3. Verify output formatting

See `references/conversion-examples.md` for step-by-step command examples.

## Error Handling

### Common Issues and Solutions

**markitdown not found:**
```bash
# Install markitdown via pip
pip install markitdown

# Or via uv tools
uv tool install markitdown
```

**Path not found:**
```bash
# Verify path exists
ls -la "/mnt/c/Users/username/Documents/file.doc"

# Use convert_path.py helper
python scripts/convert_path.py "C:\Users\username\Documents\file.doc"
```

**Encoding issues:**
- Ensure files are UTF-8 encoded
- Check for special characters in filenames
- Use quotes around paths with spaces

## Resources

### references/conversion-examples.md
Comprehensive examples for all conversion scenarios including:
- Simple document conversions (PDF, Word, PowerPoint)
- Confluence export handling
- Path conversion examples for Windows/WSL
- Batch conversion operations
- Error recovery and troubleshooting examples

Load this reference when users need specific command examples or encounter conversion issues.

### scripts/convert_path.py
Python script to automate Windows to WSL path conversion. Handles:
- Drive letter conversion (C:\ → /mnt/c/)
- Backslash to forward slash
- Special characters and spaces

## Best Practices

1. **Convert Windows paths to WSL format** before bash operations
2. **Verify paths exist** before operations using ls or test commands
3. **Check output quality** after conversion
4. **Use markitdown directly** for simple conversions
5. **Test incrementally** - Verify each conversion step before proceeding
6. **Preserve directory structure** when doing batch conversions
