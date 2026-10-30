# Tool Comparison

Comparison of document-to-markdown conversion tools.

For the orchestrator's configured format routing, read [Tool Selection](../SKILL.md#tool-selection).
For its actual candidate-selection behavior, read [Heavy Mode](heavy-mode-guide.md#selection-behavior).

## Installation

### pymupdf4llm

```bash
pip install pymupdf pymupdf4llm

# Or with uv
uv pip install pymupdf pymupdf4llm
```

[PyMuPDF 2.0 consolidates PyMuPDF4LLM](https://pymupdf.io/blog/pymupdf-2-0)
and retains `import pymupdf4llm` compatibility. Install `pymupdf` explicitly;
the `pymupdf4llm` distribution name alone does not establish that the module exists.
Before conversion, check the same runtime used to launch the orchestrator:

```bash
uv run --with pymupdf --with pymupdf4llm python -c 'import pymupdf4llm; print(callable(pymupdf4llm.to_markdown))'
```

A successful import establishes availability only; it does not verify extraction
quality or a model's execution device.

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
