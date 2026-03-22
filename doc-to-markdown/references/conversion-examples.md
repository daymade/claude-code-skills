# Document Conversion Examples

Comprehensive examples for converting various document formats to markdown.

## Basic Document Conversions

### PDF to Markdown

```bash
# Simple PDF conversion
markitdown "document.pdf" > output.md

# WSL path example
markitdown "/mnt/c/Users/username/Documents/report.pdf" > report.md

# With explicit output
markitdown "slides.pdf" > "slides.md"
```

### Word Documents to Markdown

```bash
# Modern Word document (.docx)
markitdown "document.docx" > output.md

# Legacy Word document (.doc)
markitdown "legacy-doc.doc" > output.md

# Preserve directory structure
markitdown "/path/to/docs/file.docx" > "/path/to/output/file.md"
```

### PowerPoint to Markdown

```bash
# Convert presentation
markitdown "presentation.pptx" > slides.md

# WSL path
markitdown "/mnt/c/Users/username/Desktop/slides.pptx" > slides.md
```

---

## Windows/WSL Path Conversion

### Basic Path Conversion Rules

```bash
# Windows path
C:\Users\username\Documents\file.doc

# WSL equivalent
/mnt/c/Users/username/Documents/file.doc
```

### Conversion Examples

```bash
# Single backslash to forward slash
C:\folder\file.txt
→ /mnt/c/folder/file.txt

# Path with spaces (must use quotes)
C:\Users\John Doe\Documents\report.pdf
→ "/mnt/c/Users/John Doe/Documents/report.pdf"

# OneDrive path
C:\Users\username\OneDrive\Documents\file.doc
→ "/mnt/c/Users/username/OneDrive/Documents/file.doc"

# Different drive letters
D:\Projects\document.docx
→ /mnt/d/Projects/document.docx
```

### Using convert_path.py Helper

```bash
# Automatic conversion
python scripts/convert_path.py "C:\Users\username\Downloads\document.doc"
# Output: /mnt/c/Users/username/Downloads/document.doc

# Use in conversion command
wsl_path=$(python scripts/convert_path.py "C:\Users\username\file.docx")
markitdown "$wsl_path" > output.md
```

---

## Batch Conversions

### Convert Multiple Files

```bash
# Convert all PDFs in a directory
for pdf in /path/to/pdfs/*.pdf; do
  filename=$(basename "$pdf" .pdf)
  markitdown "$pdf" > "/path/to/output/${filename}.md"
done

# Convert all Word documents
for doc in /path/to/docs/*.docx; do
  filename=$(basename "$doc" .docx)
  markitdown "$doc" > "/path/to/output/${filename}.md"
done
```

### Batch Conversion with Path Conversion

```bash
# Windows batch (PowerShell)
Get-ChildItem "C:\Documents\*.pdf" | ForEach-Object {
  $wslPath = "/mnt/c/Documents/$($_.Name)"
  $outFile = "/mnt/c/Output/$($_.BaseName).md"
  wsl markitdown $wslPath > $outFile
}
```

---

## Confluence Export Handling

### Simple Confluence Export

```bash
# Direct conversion for exports without special characters
markitdown "confluence-export.doc" > output.md
```

### Export with Special Characters

For Confluence exports containing special characters:

1. Save the .doc file to an accessible location
2. Try direct conversion first:
   ```bash
   markitdown "confluence-export.doc" > output.md
   ```

3. If special characters cause issues:
   - Open in Word and save as .docx
   - Or use LibreOffice to convert: `libreoffice --headless --convert-to docx export.doc`
   - Then convert the .docx file

### Handling Encoding Issues

```bash
# Check file encoding
file -i "document.doc"

# Convert if needed (using iconv)
iconv -f ISO-8859-1 -t UTF-8 input.md > output.md
```

---

## Advanced Conversion Scenarios

### Preserving Directory Structure

```bash
# Mirror directory structure
src_dir="/mnt/c/Users/username/Documents"
out_dir="/path/to/output"

find "$src_dir" -name "*.docx" | while read file; do
  # Get relative path
  rel_path="${file#$src_dir/}"
  out_file="$out_dir/${rel_path%.docx}.md"

  # Create output directory
  mkdir -p "$(dirname "$out_file")"

  # Convert
  markitdown "$file" > "$out_file"
done
```

### Conversion with Metadata

```bash
# Add frontmatter to converted file
{
  echo "---"
  echo "title: $(basename "$file" .pdf)"
  echo "converted: $(date -I)"
  echo "source: $file"
  echo "---"
  echo ""
  markitdown "$file"
} > output.md
```

---

## Error Recovery

### Handling Failed Conversions

```bash
# Check if markitdown succeeded
if markitdown "document.pdf" > output.md 2> error.log; then
  echo "Conversion successful"
else
  echo "Conversion failed, check error.log"
fi
```

### Retry Logic

```bash
# Retry failed conversions
for file in *.pdf; do
  output="${file%.pdf}.md"
  if ! [ -f "$output" ]; then
    echo "Converting $file..."
    markitdown "$file" > "$output" || echo "Failed: $file" >> failed.txt
  fi
done
```

---

## Quality Verification

### Check Conversion Quality

```bash
# Compare line counts
wc -l document.pdf.md

# Check for common issues
grep "TODO\|ERROR\|MISSING" output.md

# Preview first/last lines
head -n 20 output.md
tail -n 20 output.md
```

### Validate Output

```bash
# Check for empty files
if [ ! -s output.md ]; then
  echo "Warning: Output file is empty"
fi

# Verify markdown syntax
# Use a markdown linter if available
markdownlint output.md
```

---

## Best Practices

### 1. Path Handling
- Always quote paths with spaces
- Verify paths exist before conversion
- Use absolute paths for scripts

### 2. Batch Processing
- Log conversions for audit trail
- Handle errors gracefully
- Preserve original files

### 3. Output Organization
- Mirror source directory structure
- Use consistent naming conventions
- Separate by document type or date

### 4. Quality Assurance
- Spot-check random conversions
- Validate critical documents manually
- Keep conversion logs

### 5. Performance
- Use parallel processing for large batches
- Skip already converted files
- Clean up temporary files

---

## Common Patterns

### Pattern: Convert and Review

```bash
#!/bin/bash
file="$1"
output="${file%.*}.md"

# Convert
markitdown "$file" > "$output"

# Open in editor for review
${EDITOR:-vim} "$output"
```

### Pattern: Safe Conversion

```bash
#!/bin/bash
file="$1"
backup="${file}.backup"
output="${file%.*}.md"

# Backup original
cp "$file" "$backup"

# Convert with error handling
if markitdown "$file" > "$output" 2> conversion.log; then
  echo "Success: $output"
  rm "$backup"
else
  echo "Failed: Check conversion.log"
  mv "$backup" "$file"
fi
```

### Pattern: Metadata Preservation

```bash
#!/bin/bash
# Extract and preserve document metadata

file="$1"
output="${file%.*}.md"

# Get file metadata
created=$(stat -c %w "$file" 2>/dev/null || stat -f %SB "$file")
modified=$(stat -c %y "$file" 2>/dev/null || stat -f %Sm "$file")

# Convert with metadata
{
  echo "---"
  echo "original_file: $(basename "$file")"
  echo "created: $created"
  echo "modified: $modified"
  echo "converted: $(date -I)"
  echo "---"
  echo ""
  markitdown "$file"
} > "$output"
```
