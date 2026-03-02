# Excel Formatting Quick Reference

## Font Colors (RGB)

| Use Case | Color Name | RGB Code | openpyxl |
|----------|-----------|----------|----------|
| User input / assumption | Blue | `0000FF` | `Font(color="0000FF")` |
| Calculated value | Black | `000000` | `Font(color="000000")` |
| Cross-sheet reference | Green | `008000` | `Font(color="008000")` |
| Section header text | White | `FFFFFF` | `Font(color="FFFFFF")` |
| Title text | Dark Blue | `1F4E79` | `Font(color="1F4E79")` |
| Subtitle text | Dark Gray | `404040` | `Font(color="404040")` |
| Negative values | Red | `FF0000` | `Font(color="FF0000")` |

## Fill Colors (RGB)

| Use Case | Color Name | RGB Code | openpyxl |
|----------|-----------|----------|----------|
| Section header background | Dark Blue | `4472C4` | `PatternFill("solid", fgColor="4472C4")` |
| Sub-header / alternating row | Light Blue | `D9E1F2` | `PatternFill("solid", fgColor="D9E1F2")` |
| Input cell highlight | Light Green | `E2EFDA` | `PatternFill("solid", fgColor="E2EFDA")` |
| Clean background | White | `FFFFFF` | `PatternFill("solid", fgColor="FFFFFF")` |
| Alternating row | Light Gray | `F2F2F2` | `PatternFill("solid", fgColor="F2F2F2")` |

## Sensitivity Table Gradient Fills

| Level | Color Name | RGB Code | Meaning |
|-------|-----------|----------|---------|
| Worst | Deep Red | `F4CCCC` | Far below target |
| Below | Light Red | `FCE4D6` | Below target |
| Neutral | Light Yellow | `FFF2CC` | Near target |
| Above | Light Green | `D9EAD3` | Above target |
| Best | Deep Green | `B6D7A8` | Far above target |

## Conditional Formatting (ColorScaleRule)

```python
from openpyxl.formatting.rule import ColorScaleRule

# Red → Yellow → Green (3-color scale)
rule = ColorScaleRule(
    start_type="min", start_color="F8696B",
    mid_type="percentile", mid_value=50, mid_color="FFEB84",
    end_type="max", end_color="63BE7B",
)
ws.conditional_formatting.add("B2:F6", rule)

# Red → Green (2-color scale)
rule = ColorScaleRule(
    start_type="min", start_color="F8696B",
    end_type="max", end_color="63BE7B",
)
```

## Number Format Strings

| Format | Code | Example Output |
|--------|------|---------------|
| Currency (no decimals) | `'$#,##0'` | $1,234 |
| Currency (2 decimals) | `'$#,##0.00'` | $1,234.56 |
| Thousands | `'$#,##0,"K"'` | $1,234K |
| Millions | `'$#,##0.0,,"M"'` | $1.2M |
| Percentage (1 decimal) | `'0.0%'` | 12.3% |
| Percentage (2 decimals) | `'0.00%'` | 12.34% |
| Number with commas | `'#,##0'` | 1,234 |
| Multiplier | `'0.0x'` | 1.5x |
| Accounting | `'_($* #,##0_);_($* (#,##0);_($* "-"_);_(@_)'` | $ 1,234 |
| Date | `'YYYY-MM-DD'` | 2026-03-01 |
| Negative in red | `'#,##0;[Red]-#,##0'` | -1,234 (red) |

## Border Styles

| Style | Side Code | Use Case |
|-------|----------|----------|
| Thin gray | `Side(style="thin", color="B2B2B2")` | Row separators |
| Medium black | `Side(style="medium", color="000000")` | Section separators |
| Double black | `Side(style="double", color="000000")` | Final totals |
| Thin black | `Side(style="thin", color="000000")` | Grid lines |

Available `style` values: `'thin'`, `'medium'`, `'thick'`, `'double'`, `'dotted'`, `'dashed'`, `'hair'`

## Column Width Guidelines

| Content Type | Recommended Width |
|-------------|------------------|
| Short label | 12-15 |
| Currency value | 14-16 |
| Percentage | 10-12 |
| Date | 12 |
| Long description | 25-35 |
| Auto-fit formula | `max(10, min(len(str(max_value)) + 2, 20))` |

## Alignment Presets

```python
from openpyxl.styles import Alignment

CENTER = Alignment(horizontal="center", vertical="center")
RIGHT = Alignment(horizontal="right", vertical="center")
LEFT = Alignment(horizontal="left", vertical="center")
WRAP = Alignment(horizontal="left", vertical="top", wrap_text=True)
```

## Font Presets (Calibri 10pt Base)

```python
from openpyxl.styles import Font

# Standard
REGULAR = Font(size=10, name="Calibri")
BOLD = Font(size=10, name="Calibri", bold=True)
ITALIC = Font(size=10, name="Calibri", italic=True)

# Headers
SECTION_HEADER = Font(size=12, name="Calibri", bold=True, color="FFFFFF")
TITLE = Font(size=14, name="Calibri", bold=True, color="1F4E79")

# Semantic (investment banking convention)
INPUT = Font(size=10, name="Calibri", color="0000FF")          # User inputs
CALC = Font(size=10, name="Calibri", color="000000")           # Formulas
XREF = Font(size=10, name="Calibri", color="008000")           # Cross-references
```
