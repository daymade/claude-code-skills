---
name: repomix-unmixer
description: Extracts files from repomix-packed repositories, restoring original directory structures from XML/Markdown/JSON formats. Activates when users need to unmix repomix files, extract packed repositories, restore file structures from repomix output, or reverse the repomix packing process.
---

# Repomix Unmixer

## Overview

This skill extracts files from repomix-packed repositories and restores their original directory structure. Repomix packs entire repositories into single AI-friendly files (XML, Markdown, or JSON), and this skill reverses that process to restore individual files.

## When to Use This Skill

This skill activates when:
- Unmixing a repomix output file (*.xml, *.md, *.json)
- Extracting files from a packed repository
- Restoring original directory structure from repomix format
- Reviewing or validating repomix-packed content
- Converting repomix output back to usable files

## Core Workflow

### Standard Unmixing Process

Extract all files from a repomix file and restore the original directory structure using the bundled `unmix_repomix.py` script:

```bash
python3 scripts/unmix_repomix.py \
  "<path_to_repomix_file>" \
  "<output_directory>"
```

**Parameters:**
- `<path_to_repomix_file>`: Path to the repomix output file (XML, Markdown, or JSON)
- `<output_directory>`: Directory where files will be extracted (will be created if doesn't exist)

**Example:**
```bash
python3 scripts/unmix_repomix.py \
  "/path/to/repomix-output.xml" \
  "/tmp/extracted-files"
```

### What the Script Does

1. **Parses** the repomix file format (XML, Markdown, or JSON)
2. **Extracts** each file path and content
3. **Creates** the original directory structure
4. **Writes** each file to its original location
5. **Reports** extraction progress and statistics

### Output

The script will:
- Create all necessary parent directories
- Extract all files maintaining their paths
- Print extraction progress for each file
- Display total count of extracted files

**Example output:**
```
Unmixing /path/to/skill.xml...
Output directory: /tmp/extracted-files

✓ Extracted: github-ops/SKILL.md
✓ Extracted: github-ops/references/api_reference.md
✓ Extracted: markdown-tools/SKILL.md
...

✅ Successfully extracted 20 files!

Extracted files are in: /tmp/extracted-files
```

## Supported Formats

### XML Format (default)

Repomix XML format structure:
```xml
<file path="relative/path/to/file.ext">
file content here
</file>
```

The script uses regex to match `<file path="...">content</file>` blocks.

### Markdown Format

For markdown-style repomix output with file markers:
```markdown
## File: relative/path/to/file.ext
```
file content
```
```

Refer to `references/repomix-format.md` for detailed format specifications.

### JSON Format

For JSON-style repomix output:
```json
{
  "files": [
    {
      "path": "relative/path/to/file.ext",
      "content": "file content here"
    }
  ]
}
```

## Common Use Cases

### Use Case 1: Unmix Claude Skills

Extract skills that were shared as a repomix file:

```bash
python3 scripts/unmix_repomix.py \
  "/path/to/skills.xml" \
  "/tmp/unmixed-skills"
```

Then review, validate, or install the extracted skills.

### Use Case 2: Extract Repository for Review

Extract a packed repository to review its structure and contents:

```bash
python3 scripts/unmix_repomix.py \
  "/path/to/repo-output.xml" \
  "/tmp/review-repo"

# Review the structure
tree /tmp/review-repo
```

### Use Case 3: Restore Working Files

Restore files from a repomix backup to a working directory:

```bash
python3 scripts/unmix_repomix.py \
  "/path/to/backup.xml" \
  "~/workspace/restored-project"
```

## Validation Workflow

After unmixing, validate the extracted files are correct:

1. **Check file count**: Verify the number of extracted files matches expectations
2. **Review structure**: Use `tree` or `ls -R` to inspect directory layout
3. **Spot check content**: Read a few key files to verify content integrity
4. **Run validation**: For skills, use the skill-creator validation tools

Refer to `references/validation-workflow.md` for detailed validation procedures, especially for unmixing Claude skills.

## Important Principles

### Always Specify Output Directory

Always provide an output directory to avoid cluttering the current working directory:

```bash
# Good: Explicit output directory
python3 scripts/unmix_repomix.py \
  "input.xml" "/tmp/output"

# Avoid: Default output (may clutter current directory)
python3 scripts/unmix_repomix.py "input.xml"
```

### Use Temporary Directories for Review

Extract to temporary directories first for review:

```bash
# Extract to /tmp for review
python3 scripts/unmix_repomix.py \
  "skills.xml" "/tmp/review-skills"

# Review the contents
tree /tmp/review-skills

# If satisfied, copy to final destination
cp -r /tmp/review-skills ~/.claude/skills/
```

### Verify Before Overwriting

Never extract directly to important directories without review:

```bash
# Bad: Might overwrite existing files
python3 scripts/unmix_repomix.py \
  "repo.xml" "~/workspace/my-project"

# Good: Extract to temp, review, then move
python3 scripts/unmix_repomix.py \
  "repo.xml" "/tmp/extracted"
# Review, then:
mv /tmp/extracted ~/workspace/my-project
```

## Troubleshooting

### No Files Extracted

**Issue**: Script completes but no files are extracted.

**Possible causes:**
- Wrong file format (not a repomix file)
- Unsupported repomix format version
- File path pattern doesn't match

**Solution:**
1. Verify the input file is a repomix output file
2. Check the format (XML/Markdown/JSON)
3. Examine the file structure manually
4. Refer to `references/repomix-format.md` for format details

### Permission Errors

**Issue**: Cannot write to output directory.

**Solution:**
```bash
# Ensure output directory is writable
mkdir -p /tmp/output
chmod 755 /tmp/output

# Or use a directory you own
python3 scripts/unmix_repomix.py \
  "input.xml" "$HOME/extracted"
```

### Encoding Issues

**Issue**: Special characters appear garbled in extracted files.

**Solution:**
The script uses UTF-8 encoding by default. If issues persist:
- Check the original repomix file encoding
- Verify the file was created correctly
- Report the issue with specific character examples

### Path Already Exists

**Issue**: Files exist at extraction path.

**Solution:**
```bash
# Option 1: Use a fresh output directory
python3 scripts/unmix_repomix.py \
  "input.xml" "/tmp/output-$(date +%s)"

# Option 2: Clear the directory first
rm -rf /tmp/output && mkdir /tmp/output
python3 scripts/unmix_repomix.py \
  "input.xml" "/tmp/output"
```

## Best Practices

1. **Extract to temp directories** - Always extract to `/tmp` or similar for initial review
2. **Verify file count** - Check that extracted file count matches expectations
3. **Review structure** - Use `tree` to inspect directory layout before use
4. **Check content** - Spot-check a few files to ensure content is intact
5. **Use validation tools** - For skills, use skill-creator validation after unmixing
6. **Preserve originals** - Keep the original repomix file as backup

## Resources

### scripts/unmix_repomix.py

Main unmixing script that:
- Parses repomix XML/Markdown/JSON formats
- Extracts file paths and content using regex
- Creates directory structures automatically
- Writes files to their original locations
- Reports extraction progress and statistics

The script is self-contained and requires only Python 3 standard library.

### references/repomix-format.md

Comprehensive documentation of repomix file formats including:
- XML format structure and examples
- Markdown format patterns
- JSON format schema
- File path encoding rules
- Content extraction patterns
- Format version differences

Load this reference when dealing with format-specific issues or supporting new repomix versions.

### references/validation-workflow.md

Detailed validation procedures for extracted content including:
- File count verification steps
- Directory structure validation
- Content integrity checks
- Skill-specific validation using skill-creator tools
- Quality assurance checklists

Load this reference when users need to validate unmixed skills or verify extraction quality.
