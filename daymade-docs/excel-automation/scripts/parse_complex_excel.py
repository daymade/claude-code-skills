# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Parse complex xlsx/xlsm files using stdlib zipfile + xml.etree.

No external dependencies required — uses only Python standard library.

Usage:
    uv run scripts/parse_complex_excel.py <excel_file> [sheet_name]

This handles files that openpyxl cannot open (corrupted DefinedNames,
complex VBA macros, investment bank financial models).
"""

import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

# XML namespaces used in Office Open XML
MAIN_NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
RELS_NS = 'http://schemas.openxmlformats.org/package/2006/relationships'


def verify_format(file_path: str) -> str:
    """Verify actual file format using the `file` command."""
    result = subprocess.run(
        ['file', '--brief', file_path],
        capture_output=True, text=True
    )
    return result.stdout.strip()


def list_sheets(zf: zipfile.ZipFile) -> list[dict]:
    """List all sheet names and their physical XML paths."""
    wb_xml = ET.fromstring(zf.read('xl/workbook.xml'))
    sheets_el = wb_xml.findall(f'.//{{{MAIN_NS}}}sheet')

    rels_xml = ET.fromstring(zf.read('xl/_rels/workbook.xml.rels'))
    rid_to_path = {}
    for rel in rels_xml.findall(f'{{{RELS_NS}}}Relationship'):
        rid_to_path[rel.get('Id')] = 'xl/' + rel.get('Target')

    sheets = []
    for s in sheets_el:
        name = s.get('name')
        rid = s.get(f'{{{REL_NS}}}id')
        path = rid_to_path.get(rid, '?')
        sheets.append({'name': name, 'rId': rid, 'path': path})

    return sheets


def get_sheet_path(zf: zipfile.ZipFile, sheet_name: str) -> str:
    """Resolve a sheet name to its physical XML path inside the ZIP."""
    # Step 1: workbook.xml — find rId for the named sheet
    wb_xml = ET.fromstring(zf.read('xl/workbook.xml'))
    sheets = wb_xml.findall(f'.//{{{MAIN_NS}}}sheet')
    rid = None
    for s in sheets:
        if s.get('name') == sheet_name:
            rid = s.get(f'{{{REL_NS}}}id')
            break
    if not rid:
        available = [s.get('name') for s in sheets]
        raise ValueError(
            f"Sheet '{sheet_name}' not found. Available: {available}"
        )

    # Step 2: workbook.xml.rels — map rId to file path
    rels_xml = ET.fromstring(zf.read('xl/_rels/workbook.xml.rels'))
    for rel in rels_xml.findall(f'{{{RELS_NS}}}Relationship'):
        if rel.get('Id') == rid:
            return 'xl/' + rel.get('Target')

    raise ValueError(f"No file mapping for {rid}")


def build_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    """Build the shared strings lookup table."""
    shared = []
    try:
        ss_xml = ET.fromstring(zf.read('xl/sharedStrings.xml'))
        for si in ss_xml.findall(f'{{{MAIN_NS}}}si'):
            shared.append(''.join(si.itertext()))
    except KeyError:
        pass  # No shared strings in this file
    return shared


def parse_cell_ref(ref: str) -> tuple[str, int]:
    """Parse 'AB123' into ('AB', 123)."""
    match = re.match(r'^([A-Z]+)(\d+)$', ref)
    if not match:
        return ref, 0
    return match.group(1), int(match.group(2))


def extract_cells(zf: zipfile.ZipFile, sheet_path: str,
                  shared: list[str]) -> dict[str, any]:
    """Extract all cell values from a sheet XML."""
    sheet_xml = ET.fromstring(zf.read(sheet_path))
    rows = sheet_xml.findall(f'.//{{{MAIN_NS}}}row')

    data = {}
    for row in rows:
        for cell in row.findall(f'{{{MAIN_NS}}}c'):
            ref = cell.get('r')
            cell_type = cell.get('t')  # "s" = shared string, None = number
            val_el = cell.find(f'{{{MAIN_NS}}}v')

            if val_el is not None and val_el.text:
                if cell_type == 's':
                    idx = int(val_el.text)
                    data[ref] = shared[idx] if idx < len(shared) else f'[SSI:{idx}]'
                elif cell_type == 'b':
                    data[ref] = bool(int(val_el.text))
                else:
                    try:
                        num = float(val_el.text)
                        data[ref] = int(num) if num == int(num) else num
                    except ValueError:
                        data[ref] = val_el.text

    return data


def extract_rows(cells: dict, start_row: int = 1,
                 end_row: int | None = None) -> list[dict]:
    """Organize cells into row-based structure for easier consumption."""
    # Determine row range
    all_rows = set()
    for ref in cells:
        _, row_num = parse_cell_ref(ref)
        if row_num > 0:
            all_rows.add(row_num)

    if not all_rows:
        return []

    start = max(start_row, min(all_rows))
    end = min(end_row, max(all_rows)) if end_row else max(all_rows)

    rows = []
    for r in range(start, end + 1):
        row_cells = {
            ref: val for ref, val in cells.items()
            if parse_cell_ref(ref)[1] == r
        }
        if row_cells:
            rows.append({'row': r, 'cells': row_cells})

    return rows


def fix_defined_names(input_path: str, output_path: str) -> int:
    """
    Remove corrupted DefinedNames entries (containing "Formula removed")
    and repackage the file.

    Returns the number of removed entries.
    """
    import shutil
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)

        # Extract
        with zipfile.ZipFile(input_path, 'r') as zf:
            zf.extractall(tmp)

        # Fix workbook.xml
        wb_path = tmp / 'xl' / 'workbook.xml'
        tree = ET.parse(wb_path)
        root = tree.getroot()

        ns = {'main': MAIN_NS}
        defined_names = root.find('.//main:definedNames', ns)
        removed = 0
        if defined_names is not None:
            for name in list(defined_names):
                if name.text and "Formula removed" in name.text:
                    defined_names.remove(name)
                    removed += 1

        tree.write(wb_path, encoding='utf-8', xml_declaration=True)

        # Repackage
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for fp in tmp.rglob('*'):
                if fp.is_file():
                    zf.write(fp, fp.relative_to(tmp))

    return removed


# ── CLI Entry Point ──────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: parse_complex_excel.py <excel_file> [sheet_name]")
        print("\nExamples:")
        print("  parse_complex_excel.py model.xlsm           # List all sheets")
        print("  parse_complex_excel.py model.xlsm DCF       # Extract DCF sheet")
        print("  parse_complex_excel.py model.xlsm --fix     # Fix corrupted names")
        sys.exit(1)

    file_path = sys.argv[1]
    path = Path(file_path)

    if not path.exists():
        print(f"File not found: {file_path}")
        sys.exit(1)

    # Verify format
    fmt = verify_format(file_path)
    print(f"File: {path.name}")
    print(f"Format: {fmt}")

    # "Microsoft Excel 2007+" = ZIP-based xlsx/xlsm
    # "Zip archive" = generic ZIP (also valid)
    # "Composite Document File" = old BIFF .xls format
    is_zip_based = any(kw in fmt.lower() for kw in ['zip', 'excel 2007', 'ooxml'])
    if not is_zip_based:
        print("WARNING: File is not ZIP-based xlsx/xlsm.")
        if 'composite' in fmt.lower() or 'biff' in fmt.lower():
            print("This appears to be an old .xls (BIFF format). Use xlrd instead.")
        else:
            print(f"Unexpected format. If it should be xlsx/xlsm, check the file.")
        sys.exit(1)

    # Handle --fix flag
    if len(sys.argv) > 2 and sys.argv[2] == '--fix':
        out_path = str(path.with_stem(path.stem + '_fixed'))
        removed = fix_defined_names(file_path, out_path)
        print(f"Removed {removed} corrupted DefinedNames entries.")
        print(f"Fixed file: {out_path}")
        sys.exit(0)

    with zipfile.ZipFile(file_path, 'r') as zf:
        # List sheets
        sheets = list_sheets(zf)
        print(f"\nSheets ({len(sheets)}):")
        for i, s in enumerate(sheets, 1):
            print(f"  {i}. {s['name']} → {s['path']}")

        # If sheet name given, extract it
        if len(sys.argv) > 2:
            sheet_name = sys.argv[2]
            print(f"\nExtracting sheet: {sheet_name}")

            sheet_path = get_sheet_path(zf, sheet_name)
            shared = build_shared_strings(zf)
            cells = extract_cells(zf, sheet_path, shared)

            print(f"Total cells: {len(cells)}")

            # Show first 20 rows
            rows = extract_rows(cells, start_row=1, end_row=20)
            for row in rows:
                print(f"  Row {row['row']:3d}: ", end="")
                items = sorted(row['cells'].items(),
                               key=lambda x: parse_cell_ref(x[0]))
                for ref, val in items[:8]:
                    val_str = str(val)[:25]
                    print(f"{ref}={val_str}  ", end="")
                print()


if __name__ == "__main__":
    main()
