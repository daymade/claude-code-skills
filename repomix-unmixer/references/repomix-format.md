# Repomix File Format Reference

This document provides comprehensive documentation of repomix output formats for accurate file extraction.

## Overview

Repomix can generate output in three formats:
1. **XML** (default) - Most common, uses XML tags
2. **Markdown** - Human-readable, uses markdown code blocks
3. **JSON** - Structured data format

## XML Format

### Structure

The XML format is the default and most common repomix output:

```xml
<file_summary>
  [Summary and metadata about the packed repository]
</file_summary>

<directory_structure>
  [Text-based directory tree visualization]
</directory_structure>

<files>
  <file path="relative/path/to/file1.ext">
  content of file1
  </file>

  <file path="relative/path/to/file2.ext">
  content of file2
  </file>
</files>
```

### File Block Pattern

Each file is enclosed in a `<file>` tag with a `path` attribute:

```xml
<file path="src/main.py">
#!/usr/bin/env python3

def main():
    print("Hello, world!")

if __name__ == "__main__":
    main()
</file>
```

### Key Characteristics

- File path is in the `path` attribute (relative path)
- Content starts on the line after the opening tag
- Content ends on the line before the closing tag
- No leading/trailing blank lines in content (content is trimmed)

### Extraction Pattern

The unmixing script uses this regex pattern:

```python
r'<file path="([^"]+)">\n(.*?)\n</file>'
```

**Pattern breakdown:**
- `<file path="([^"]+)">` - Captures the file path from the path attribute
- `\n` - Expects a newline after opening tag
- `(.*?)` - Captures file content (non-greedy, allows multiline)
- `\n</file>` - Expects newline before closing tag

## Markdown Format

### Structure

The Markdown format uses code blocks to delimit file content:

````markdown
# Repository Summary

[Summary content]

## Directory Structure

```
directory/
  file1.txt
  file2.txt
```

## Files

### File: relative/path/to/file1.ext

```python
# File content here
def example():
    pass
```

### File: relative/path/to/file2.ext

```javascript
// Another file
console.log("Hello");
```
````

### File Block Pattern

Each file uses a level-3 heading with "File:" prefix and code block:

````markdown
### File: src/main.py

```python
#!/usr/bin/env python3

def main():
    print("Hello, world!")
```
````

### Key Characteristics

- File path follows "### File: " heading
- Content is within a code block (triple backticks)
- Language hint may be included after opening backticks
- Content preserves original formatting

### Extraction Pattern

```python
r'## File: ([^\n]+)\n```[^\n]*\n(.*?)\n```'
```

**Pattern breakdown:**
- `## File: ([^\n]+)` - Captures file path from heading
- `\n` - Newline after heading
- ``` `[^\n]*` ``` - Opening code block with optional language
- `\n(.*?)\n` - Captures content between backticks
- ``` ` ``` ``` - Closing backticks

## JSON Format

### Structure

The JSON format provides structured data:

```json
{
  "metadata": {
    "repository": "owner/repo",
    "timestamp": "2025-10-22T19:00:00Z"
  },
  "directoryStructure": "directory/\n  file1.txt\n  file2.txt\n",
  "files": [
    {
      "path": "relative/path/to/file1.ext",
      "content": "content of file1\n"
    },
    {
      "path": "relative/path/to/file2.ext",
      "content": "content of file2\n"
    }
  ]
}
```

### File Entry Structure

Each file is an object in the `files` array:

```json
{
  "path": "src/main.py",
  "content": "#!/usr/bin/env python3\n\ndef main():\n    print(\"Hello, world!\")\n\nif __name__ == \"__main__\":\n    main()\n"
}
```

### Key Characteristics

- Files are in a `files` array
- Each file has `path` and `content` keys
- Content includes literal `\n` for newlines
- Content is JSON-escaped (quotes, backslashes)

### Extraction Approach

```python
data = json.loads(content)
files = data.get('files', [])
for file_entry in files:
    file_path = file_entry.get('path')
    file_content = file_entry.get('content', '')
```

## Format Detection

### Detection Logic

The unmixing script auto-detects format using these checks:

1. **XML**: Contains `<file path=` and `</file>`
2. **JSON**: Starts with `{` and contains `"files"`
3. **Markdown**: Contains `## File:`

### Detection Priority

1. Check XML markers first (most common)
2. Check JSON structure second
3. Check Markdown markers last
4. Return `None` if no format matches

### Example Detection Code

```python
def detect_format(content):
    if '<file path=' in content and '</file>' in content:
        return 'xml'
    if content.strip().startswith('{') and '"files"' in content:
        return 'json'
    if '## File:' in content:
        return 'markdown'
    return None
```

## File Path Encoding

### Relative Paths

All file paths in repomix output are relative to the repository root:

```
src/components/Header.tsx
docs/README.md
package.json
```

### Special Characters

File paths may contain:
- Spaces: `"My Documents/file.txt"`
- Hyphens: `"some-file.md"`
- Underscores: `"my_script.py"`
- Dots: `"config.local.json"`

Paths are preserved exactly as they appear in the original repository.

### Directory Separators

- Always forward slashes (`/`) regardless of platform
- No leading slash (relative paths)
- No trailing slash for files

## Content Encoding

### Character Encoding

All formats use **UTF-8** encoding for both the container file and extracted content.

### Special Characters

- **XML**: Content may contain XML-escaped characters (`&lt;`, `&gt;`, `&amp;`)
- **Markdown**: Content is plain text within code blocks
- **JSON**: Content uses JSON string escaping (`\"`, `\\`, `\n`)

### Line Endings

- Original line endings are preserved
- May be `\n` (Unix), `\r\n` (Windows), or `\r` (old Mac)
- Extraction preserves original endings

## Edge Cases

### Empty Files

**XML:**
```xml
<file path="empty.txt">
</file>
```

**Markdown:**
````markdown
### File: empty.txt

```
```
````

**JSON:**
```json
{"path": "empty.txt", "content": ""}
```

### Binary Files

Binary files are typically **not included** in repomix output. The directory structure may list them, but they won't have content blocks.

### Large Files

Some repomix configurations may truncate or exclude large files. Check the file summary section for exclusion notes.

## Version Differences

### Repomix v1.x

- Uses XML format by default
- File blocks have consistent structure
- No automatic format version marker

### Repomix v2.x

- Adds JSON and Markdown format support
- May include version metadata in output
- Maintains backward compatibility with v1 XML

## Validation

### Successful Extraction Indicators

After extraction, verify:
1. **File count** matches expected number
2. **Directory structure** matches the `<directory_structure>` section
3. **Content integrity** - spot-check a few files
4. **No empty directories** unless explicitly included

### Common Format Issues

**Issue**: Files not extracted
- **Cause**: Format pattern mismatch
- **Solution**: Check format manually, verify repomix version

**Issue**: Partial content extraction
- **Cause**: Incorrect regex pattern (too greedy or not greedy enough)
- **Solution**: Check for nested tags or malformed blocks

**Issue**: Encoding errors
- **Cause**: Non-UTF-8 content in repomix file
- **Solution**: Verify source file encoding

## Examples

### Complete XML Example

```xml
<file_summary>
This is a packed repository.
</file_summary>

<directory_structure>
my-skill/
  SKILL.md
  scripts/
    helper.py
</directory_structure>

<files>
<file path="my-skill/SKILL.md">
---
name: my-skill
description: Example skill
---

# My Skill

This is an example.
</file>

<file path="my-skill/scripts/helper.py">
#!/usr/bin/env python3

def help():
    print("Helping!")
</file>
</files>
```

### Complete Markdown Example

````markdown
# Repository: my-skill

## Directory Structure

```
my-skill/
  SKILL.md
  scripts/
    helper.py
```

## Files

### File: my-skill/SKILL.md

```markdown
---
name: my-skill
description: Example skill
---

# My Skill

This is an example.
```

### File: my-skill/scripts/helper.py

```python
#!/usr/bin/env python3

def help():
    print("Helping!")
```
````

### Complete JSON Example

```json
{
  "metadata": {
    "repository": "my-skill"
  },
  "directoryStructure": "my-skill/\n  SKILL.md\n  scripts/\n    helper.py\n",
  "files": [
    {
      "path": "my-skill/SKILL.md",
      "content": "---\nname: my-skill\ndescription: Example skill\n---\n\n# My Skill\n\nThis is an example.\n"
    },
    {
      "path": "my-skill/scripts/helper.py",
      "content": "#!/usr/bin/env python3\n\ndef help():\n    print(\"Helping!\")\n"
    }
  ]
}
```

## References

- Repomix documentation: https://github.com/yamadashy/repomix
- Repomix output examples: Check the repomix repository for sample outputs
- XML specification: https://www.w3.org/XML/
- JSON specification: https://www.json.org/
