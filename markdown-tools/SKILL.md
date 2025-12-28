---
name: markdown-tools
description: Converts documents to markdown (PDFs, Word docs, PowerPoint, Confluence exports) with Windows/WSL path handling. Activates when converting .doc/.docx/PDF/PPTX files to markdown, processing Confluence exports, handling Windows/WSL path conversions, extracting images from PDFs, or working with markitdown utility.
---

# Markdown Tools

Convert documents to markdown with image extraction and Windows/WSL path handling.

## Quick Start

### Install markitdown with PDF Support

```bash
# IMPORTANT: Use [pdf] extra for PDF support
uv tool install "markitdown[pdf]"

# Or via pip
pip install "markitdown[pdf]"
```

### Basic Conversion

```bash
markitdown "document.pdf" -o output.md
# Or redirect: markitdown "document.pdf" > output.md
```

## PDF Conversion with Images

markitdown extracts text only. For PDFs with images, use this workflow:

### Step 1: Convert Text

```bash
markitdown "document.pdf" -o output.md
```

### Step 2: Extract Images

```bash
# Create assets directory alongside the markdown
mkdir -p assets

# Extract images using PyMuPDF
uv run --with pymupdf python scripts/extract_pdf_images.py "document.pdf" ./assets
```

### Step 3: Add Image References

Insert image references in the markdown where needed:

```markdown
![Description](assets/img_page1_1.png)
```

### Step 4: Format Cleanup

markitdown output often needs manual fixes:
- Add proper heading levels (`#`, `##`, `###`)
- Reconstruct tables in markdown format
- Fix broken line breaks
- Restore indentation structure

## Path Conversion (Windows/WSL)

```bash
# Windows → WSL conversion
C:\Users\name\file.pdf → /mnt/c/Users/name/file.pdf

# Use helper script
python scripts/convert_path.py "C:\Users\name\Documents\file.pdf"
```

## Common Issues

**"dependencies needed to read .pdf files"**
```bash
# Install with PDF support
uv tool install "markitdown[pdf]" --force
```

**FontBBox warnings during PDF conversion**
- These are harmless font parsing warnings, output is still correct

**Images missing from output**
- Use `scripts/extract_pdf_images.py` to extract images separately

## Resources

- `scripts/extract_pdf_images.py` - Extract images from PDF using PyMuPDF
- `scripts/convert_path.py` - Windows to WSL path converter
- `references/conversion-examples.md` - Detailed examples for batch operations
