---
name: excel-automation
description: Create, parse, and control Excel files on macOS. Professional formatting with openpyxl, complex xlsm parsing with stdlib zipfile+xml for investment bank financial models, and Excel window control via AppleScript. Use when creating formatted Excel reports, parsing financial models that openpyxl cannot handle, or automating Excel on macOS.
---

# Excel Automation

Create professional Excel files, parse complex financial models, and control Excel on macOS.

## Quick Start

```bash
# Create a formatted Excel report
uv run --with openpyxl scripts/create_formatted_excel.py output.xlsx

# Parse a complex xlsm that openpyxl can't handle
uv run scripts/parse_complex_excel.py model.xlsm              # List sheets
uv run scripts/parse_complex_excel.py model.xlsm "DCF"        # Extract a sheet
uv run scripts/parse_complex_excel.py model.xlsm --fix        # Fix corrupted names

# Control Excel via AppleScript (with timeout to prevent hangs)
timeout 5 osascript -e 'tell application "Microsoft Excel" to activate'
```

## Overview

Three capabilities:

| Capability | Tool | When to Use |
|-----------|------|-------------|
| **Create** formatted Excel | `openpyxl` | Reports, mockups, dashboards |
| **Parse** complex xlsm/xlsx | `zipfile` + `xml.etree` | Financial models, VBA workbooks, >1MB files |
| **Control** Excel window | AppleScript (`osascript`) | Zoom, scroll, select cells programmatically |

## Tool Selection Decision Tree

```
Is the file simple (data export, no VBA, <1MB)?
├─ YES → openpyxl or pandas
└─ NO
   ├─ Is it .xlsm or from investment bank / >1MB?
   │   └─ YES → zipfile + xml.etree.ElementTree (stdlib)
   └─ Is it truly .xls (BIFF format)?
       └─ YES → xlrd
```

**Signals of "complex" Excel**: file >1MB, `.xlsm` extension, from investment bank/broker, contains VBA macros.

**IMPORTANT**: Always run `file <path>` first — extensions lie. A `.xls` file may actually be a ZIP-based xlsx.

## Creating Excel Files (openpyxl)

### Professional Color Convention (Investment Banking Standard)

| Color | RGB Code | Meaning |
|-------|----------|---------|
| Blue | `0000FF` | User input / assumption |
| Black | `000000` | Calculated value |
| Green | `008000` | Cross-sheet reference |
| White on dark blue | `FFFFFF` on `4472C4` | Section headers |
| Dark blue text | `1F4E79` | Title |

### Core Formatting Patterns

```python
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment

# Fonts
BLUE_FONT = Font(color="0000FF", size=10, name="Calibri")
BLACK_FONT_BOLD = Font(color="000000", size=10, name="Calibri", bold=True)
GREEN_FONT = Font(color="008000", size=10, name="Calibri")
HEADER_FONT = Font(color="FFFFFF", size=12, name="Calibri", bold=True)

# Fills
DARK_BLUE_FILL = PatternFill("solid", fgColor="4472C4")
LIGHT_BLUE_FILL = PatternFill("solid", fgColor="D9E1F2")
INPUT_GREEN_FILL = PatternFill("solid", fgColor="E2EFDA")
LIGHT_GRAY_FILL = PatternFill("solid", fgColor="F2F2F2")

# Borders
THIN_BORDER = Border(bottom=Side(style="thin", color="B2B2B2"))
BOTTOM_DOUBLE = Border(bottom=Side(style="double", color="000000"))
```

### Number Format Codes

| Format | Code | Example |
|--------|------|---------|
| Currency | `'$#,##0'` | $1,234 |
| Currency with decimals | `'$#,##0.00'` | $1,234.56 |
| Percentage | `'0.0%'` | 12.3% |
| Percentage (2 decimal) | `'0.00%'` | 12.34% |
| Number with commas | `'#,##0'` | 1,234 |
| Multiplier | `'0.0x'` | 1.5x |

### Conditional Formatting (Sensitivity Tables)

Red-to-green gradient for sensitivity analysis:

```python
from openpyxl.formatting.rule import ColorScaleRule

rule = ColorScaleRule(
    start_type="min", start_color="F8696B",   # Red (low)
    mid_type="percentile", mid_value=50, mid_color="FFEB84",  # Yellow (mid)
    end_type="max", end_color="63BE7B"         # Green (high)
)
ws.conditional_formatting.add(f"B2:F6", rule)
```

### Execution

```bash
uv run --with openpyxl scripts/create_formatted_excel.py
```

Full template script: See `scripts/create_formatted_excel.py`

## Parsing Complex Excel (zipfile + xml)

When openpyxl fails on complex xlsm files (corrupted DefinedNames, complex VBA), use stdlib directly.

### XLSX Internal ZIP Structure

```
file.xlsx (ZIP archive)
├── [Content_Types].xml
├── xl/
│   ├── workbook.xml          ← Sheet names + order
│   ├── sharedStrings.xml     ← All text values (lookup table)
│   ├── worksheets/
│   │   ├── sheet1.xml        ← Cell data for sheet 1
│   │   ├── sheet2.xml        ← Cell data for sheet 2
│   │   └── ...
│   └── _rels/
│       └── workbook.xml.rels ← Maps rId → sheetN.xml
└── _rels/.rels
```

### Sheet Name Resolution (Two-Step)

Sheet names in `workbook.xml` link to physical files via `_rels/workbook.xml.rels`:

```python
import zipfile
import xml.etree.ElementTree as ET

MAIN_NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
RELS_NS = 'http://schemas.openxmlformats.org/package/2006/relationships'

def get_sheet_path(zf, sheet_name):
    """Resolve sheet name to physical XML file path inside ZIP."""
    # Step 1: workbook.xml → find rId for the sheet name
    wb_xml = ET.fromstring(zf.read('xl/workbook.xml'))
    sheets = wb_xml.findall(f'.//{{{MAIN_NS}}}sheet')
    rid = None
    for s in sheets:
        if s.get('name') == sheet_name:
            rid = s.get(f'{{{REL_NS}}}id')
            break
    if not rid:
        raise ValueError(f"Sheet '{sheet_name}' not found")

    # Step 2: workbook.xml.rels → map rId to file path
    rels_xml = ET.fromstring(zf.read('xl/_rels/workbook.xml.rels'))
    for rel in rels_xml.findall(f'{{{RELS_NS}}}Relationship'):
        if rel.get('Id') == rid:
            return 'xl/' + rel.get('Target')

    raise ValueError(f"No file mapping for {rid}")
```

### Cell Data Extraction

```python
def extract_cells(zf, sheet_path):
    """Extract all cell values from a sheet XML."""
    # Build shared strings lookup
    shared = []
    try:
        ss_xml = ET.fromstring(zf.read('xl/sharedStrings.xml'))
        for si in ss_xml.findall(f'{{{MAIN_NS}}}si'):
            texts = si.itertext()
            shared.append(''.join(texts))
    except KeyError:
        pass  # No shared strings

    # Parse sheet cells
    sheet_xml = ET.fromstring(zf.read(sheet_path))
    rows = sheet_xml.findall(f'.//{{{MAIN_NS}}}row')

    data = {}
    for row in rows:
        for cell in row.findall(f'{{{MAIN_NS}}}c'):
            ref = cell.get('r')         # e.g., "A1"
            cell_type = cell.get('t')   # "s" = shared string, None = number
            val_el = cell.find(f'{{{MAIN_NS}}}v')

            if val_el is not None and val_el.text:
                if cell_type == 's':
                    data[ref] = shared[int(val_el.text)]
                else:
                    try:
                        data[ref] = float(val_el.text)
                    except ValueError:
                        data[ref] = val_el.text
    return data
```

### Fixing Corrupted DefinedNames

Investment bank xlsm files often have corrupted `<definedName>` entries containing "Formula removed":

```python
def fix_defined_names(zf_in_path, zf_out_path):
    """Remove corrupted DefinedNames and repackage."""
    import shutil, tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        with zipfile.ZipFile(zf_in_path, 'r') as zf:
            zf.extractall(tmp)

        wb_xml_path = tmp / 'xl' / 'workbook.xml'
        tree = ET.parse(wb_xml_path)
        root = tree.getroot()

        ns = {'main': MAIN_NS}
        defined_names = root.find('.//main:definedNames', ns)
        if defined_names is not None:
            for name in list(defined_names):
                if name.text and "Formula removed" in name.text:
                    defined_names.remove(name)

        tree.write(wb_xml_path, encoding='utf-8', xml_declaration=True)

        with zipfile.ZipFile(zf_out_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for fp in tmp.rglob('*'):
                if fp.is_file():
                    zf.write(fp, fp.relative_to(tmp))
```

Full template script: See `scripts/parse_complex_excel.py`

## Controlling Excel on macOS (AppleScript)

All commands verified on macOS with Microsoft Excel.

### Verified Commands

```bash
# Activate Excel (bring to front)
osascript -e 'tell application "Microsoft Excel" to activate'

# Open a file
osascript -e 'tell application "Microsoft Excel" to open POSIX file "/path/to/file.xlsx"'

# Set zoom level (percentage)
osascript -e 'tell application "Microsoft Excel"
    set zoom of active window to 120
end tell'

# Scroll to specific row
osascript -e 'tell application "Microsoft Excel"
    set scroll row of active window to 45
end tell'

# Scroll to specific column
osascript -e 'tell application "Microsoft Excel"
    set scroll column of active window to 3
end tell'

# Select a cell range
osascript -e 'tell application "Microsoft Excel"
    select range "A1" of active sheet
end tell'

# Select a specific sheet by name
osascript -e 'tell application "Microsoft Excel"
    activate object sheet "DCF" of active workbook
end tell'
```

### Timing and Timeout

Always add `sleep 1` between AppleScript commands and subsequent operations (e.g., screenshot) to allow UI rendering.

**IMPORTANT**: `osascript` will hang indefinitely if Excel is not running or not responding. Always wrap with `timeout`:

```bash
# Safe pattern: 5-second timeout
timeout 5 osascript -e 'tell application "Microsoft Excel" to activate'

# Check exit code: 124 = timed out
if [ $? -eq 124 ]; then
    echo "Excel not responding — is it running?"
fi
```

## Common Mistakes

| Mistake | Correction |
|---------|-----------|
| openpyxl fails on complex xlsm → try monkey-patching | Switch to `zipfile` + `xml.etree` immediately |
| Count Chinese characters with `wc -c` | Use `wc -m` (chars, not bytes; Chinese = 3 bytes/char) |
| Trust file extension | Run `file <path>` first to confirm actual format |
| openpyxl `load_workbook` hangs on large xlsm | Use `zipfile` for targeted extraction instead of loading entire workbook |

## Important Notes

- Execute Python scripts with `uv run --with openpyxl` (never use system Python)
- LibreOffice (`soffice --headless`) can convert formats and recalculate formulas
- Detailed formatting reference: See `references/formatting-reference.md`
