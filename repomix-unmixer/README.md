# Repomix Unmixer Skill

A Claude Code skill for extracting files from repomix-packed repositories and restoring their original directory structure.

## Overview

Repomix packs entire repositories into single AI-friendly files (XML, Markdown, or JSON). This skill reverses that process, extracting all files and restoring the original directory structure.

## Quick Start

### Installation

1. Download `repomix-unmixer.zip`
2. Extract to `~/.claude/skills/repomix-unmixer/`
3. Restart Claude Code

### Basic Usage

Extract a repomix file:

```bash
python3 ~/.claude/skills/repomix-unmixer/scripts/unmix_repomix.py \
  "<path_to_repomix_file>" \
  "<output_directory>"
```

Example:

```bash
python3 ~/.claude/skills/repomix-unmixer/scripts/unmix_repomix.py \
  "/path/to/skills.xml" \
  "/tmp/extracted-skills"
```

## Features

- **Multi-format support**: XML (default), Markdown, and JSON repomix formats
- **Auto-detection**: Automatically detects repomix format
- **Structure preservation**: Restores original directory structure
- **UTF-8 encoding**: Handles international characters correctly
- **Progress reporting**: Shows extraction progress and statistics
- **Validation workflows**: Includes comprehensive validation guides

## Supported Formats

### XML Format (default)
```xml
<file path="relative/path/to/file.ext">
content here
</file>
```

### Markdown Format
````markdown
### File: relative/path/to/file.ext

```language
content here
```
````

### JSON Format
```json
{
  "files": [
    {"path": "file.ext", "content": "content here"}
  ]
}
```

## Bundled Resources

### scripts/unmix_repomix.py
Main unmixing script with:
- Format auto-detection
- Multi-format parsing (XML, Markdown, JSON)
- Directory structure creation
- Progress reporting

### references/repomix-format.md
Comprehensive format documentation:
- XML, Markdown, and JSON format specifications
- Extraction patterns and regex
- Edge cases and examples
- Format detection logic

### references/validation-workflow.md
Detailed validation procedures:
- File count verification
- Directory structure validation
- Content integrity checks
- Skill-specific validation for Claude Code skills
- Quality assurance checklists

## Common Use Cases

### Unmix Claude Skills
```bash
python3 ~/.claude/skills/repomix-unmixer/scripts/unmix_repomix.py \
  "skills.xml" "/tmp/review-skills"

# Review and validate
tree /tmp/review-skills

# Install if valid
cp -r /tmp/review-skills/* ~/.claude/skills/
```

### Extract Repository for Review
```bash
python3 ~/.claude/skills/repomix-unmixer/scripts/unmix_repomix.py \
  "repo-output.xml" "/tmp/review-repo"

# Review structure
tree /tmp/review-repo
```

### Restore from Backup
```bash
python3 ~/.claude/skills/repomix-unmixer/scripts/unmix_repomix.py \
  "backup.xml" "~/workspace/restored-project"
```

## Validation

After extraction, validate the results:

1. **Check file count**: Verify extracted count matches expected
2. **Review structure**: Use `tree` to inspect directory layout
3. **Spot check content**: Read a few files to verify integrity
4. **Run validation**: For skills, use skill-creator validation

For detailed validation procedures, see `references/validation-workflow.md`.

## Requirements

- Python 3.6 or higher
- Standard library only (no external dependencies)

## Skill Activation

This skill activates when:
- Unmixing a repomix output file
- Extracting files from a packed repository
- Restoring original directory structure
- Reviewing repomix-packed content
- Converting repomix output back to usable files

## Best Practices

1. **Extract to temp directories** - Always extract to `/tmp` for initial review
2. **Verify file count** - Check extracted count matches expectations
3. **Review structure** - Inspect directory layout before use
4. **Check content** - Spot-check files for integrity
5. **Use validation tools** - For skills, use skill-creator validation
6. **Preserve originals** - Keep the repomix file as backup

## Troubleshooting

### No Files Extracted
- Verify input file is a valid repomix file
- Check format (XML/Markdown/JSON)
- Refer to `references/repomix-format.md`

### Permission Errors
- Ensure output directory is writable
- Use `mkdir -p` to create directory first
- Check file permissions

### Encoding Issues
- Script uses UTF-8 by default
- Verify repomix file encoding
- Check for special characters

## Version

- **Version**: 1.0.0
- **Created**: 2025-10-22
- **Last Updated**: 2025-10-22

## License

This skill follows the same license as Claude Code.

## Support

For issues or questions:
1. Check `references/repomix-format.md` for format details
2. Review `references/validation-workflow.md` for validation help
3. Inspect the script source code at `scripts/unmix_repomix.py`
4. Report issues to the skill creator

## Credits

Created using the skill-creator skill for Claude Code.
