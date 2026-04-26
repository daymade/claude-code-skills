# Tool Comparison

Comparison of document-to-markdown conversion tools.

## Feature Matrix

| Feature | pymupdf4llm | markitdown | pandoc |
|---------|-------------|------------|--------|
| **PDF Support** | ✅ Excellent | ✅ Good | ⚠️ Limited |
| **DOCX Support** | ❌ No | ✅ Good | ✅ Excellent |
| **PPTX Support** | ❌ No | ✅ Good | ✅ Good |
| **XLSX Support** | ❌ No | ✅ Good | ⚠️ Limited |
| **Table Detection** | ✅ Multiple strategies | ⚠️ Basic | ✅ Good |
| **Image Extraction** | ✅ With metadata | ❌ No | ✅ Yes |
| **Heading Hierarchy** | ✅ Good | ⚠️ Variable | ✅ Excellent |
| **List Formatting** | ✅ Good | ⚠️ Basic | ✅ Excellent |
| **LLM Optimization** | ✅ Built-in | ❌ No | ❌ No |

## Installation

### pymupdf4llm

```bash
pip install pymupdf4llm

# Or with uv
uv pip install pymupdf4llm
```

**Dependencies:** None (pure Python with PyMuPDF)

### markitdown

```bash
# With PDF support
uv tool install "markitdown[pdf]"

# Or
pip install "markitdown[pdf]"
```

**Dependencies:** Various per format (pdfminer, python-docx, etc.)

### pandoc

```bash
# macOS
brew install pandoc

# Ubuntu/Debian
apt-get install pandoc

# Windows
choco install pandoc
```

**Dependencies:** System installation required

## Performance Benchmarks

### PDF Conversion (100-page document)

| Tool | Time | Memory | Output Quality |
|------|------|--------|----------------|
| pymupdf4llm | ~15s | 150MB | Excellent |
| markitdown | ~45s | 200MB | Good |
| pandoc | ~60s | 100MB | Variable |

### DOCX Conversion (50-page document)

| Tool | Time | Memory | Output Quality |
|------|------|--------|----------------|
| pandoc | ~5s | 50MB | Excellent |
| markitdown | ~10s | 80MB | Good |

## Best Practices

### For PDFs

1. **First choice:** pymupdf4llm
   - Best table detection
   - Image extraction with metadata
   - LLM-optimized output

2. **Fallback:** markitdown
   - When pymupdf4llm fails
   - Simpler documents

### For DOCX/DOC

1. **First choice:** pandoc
   - Best structure preservation
   - Proper heading hierarchy
   - List formatting

2. **Fallback:** markitdown
   - When pandoc unavailable
   - Quick conversion needed

### For PPTX

1. **First choice:** markitdown
   - Good slide content extraction
   - Handles speaker notes

2. **Fallback:** pandoc
   - Better structure preservation

### For XLSX

1. **Only option:** markitdown
   - Table to markdown conversion
   - Sheet handling

## Common Issues by Tool

### pymupdf4llm

| Issue | Solution |
|-------|----------|
| "Cannot import fitz" | `pip install pymupdf` |
| Tables not detected | Try different `table_strategy` |
| Images not extracted | Enable `write_images=True` |

### markitdown

| Issue | Solution |
|-------|----------|
| PDF support missing | Install with `[pdf]` extra |
| Slow conversion | Expected for large files |
| Missing content | Try alternative tool |

### pandoc

| Issue | Solution |
|-------|----------|
| Command not found | Install via package manager |
| PDF conversion fails | Use pymupdf4llm instead |
| Images not extracted | Add `--extract-media` flag |

## API Comparison

### pymupdf4llm

```python
import pymupdf4llm

md = pymupdf4llm.to_markdown(
    "doc.pdf",
    write_images=True,
    table_strategy="lines_strict",
    image_path="./assets"
)
```

### markitdown

```python
from markitdown import MarkItDown

md = MarkItDown()
result = md.convert("document.pdf")
print(result.text_content)
```

### pandoc

```bash
pandoc document.docx -t markdown --wrap=none --extract-media=./assets
```

```python
import subprocess

result = subprocess.run(
    ["pandoc", "doc.docx", "-t", "markdown", "--wrap=none"],
    capture_output=True, text=True
)
print(result.stdout)
```
