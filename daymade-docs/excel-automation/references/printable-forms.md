# Reconstruct an editable printable form

Use this READ-DO workflow when an image or scan contains a paper form and the
requested result is an editable `.xlsx` with a suitable print layout. Build the
form's content as cells; an image placed on a worksheet is not editable content.
Use the spreadsheet authoring tool required by the current host. Retain openpyxl
as an adapter where permitted; this workflow does not require another Skill or
a new template generator.

The executing agent owns source comparison, workbook construction and result
checks. Cell inspection can establish content and data types; only the selected
print engine can establish its page layout. No bundled tool enforces the source
comparison or visual print checks automatically.

## 1. Establish the source and fill facts

Before writing cells, inspect the original and make a field inventory covering:

- Title, section headings and table groups.
- Every field label, option and unit.
- Input areas, including large narrative or handwritten areas.
- Signature, seal and date positions.
- Notes, instructions and source/version statements.

Map each item to a planned cell or merged range. Keep labels and options in the
source's order and retain the meaning of grouped fields. If a character or region
cannot be read, identify that item as unresolved and request a clearer source or
the missing text; do not invent a label or silently omit the field. Continue only
the construction that does not depend on the unresolved item.

Separate the template from its example answers. Prefill only facts explicitly
provided for the current task. Leave unknown values genuinely blank, with usable
input space. Do not copy sample answers, a seal or a signature from the source as
the applicant's information. Mark an option only when the supplied facts establish
it; a qualification name does not establish an acquisition method such as
examination or evaluation.

Judge source/version text by the document's intended use. Retain template
instructions or provenance needed to identify or use it. Remove irrelevant source
decoration only when that does not alter its required identity or meaning. Do not
label a self-made reconstruction as officially issued without evidence.

## 2. Build editable cells with the right types

Reproduce the grid, groups and writing areas with cells, borders and only the
merges needed by the layout. Keep the workbook and worksheet unprotected unless
the user explicitly requests a restriction. Use black text on white for a black
and white paper form; do not apply financial-report input colors to it.

Set an identifier field to text **before** filling it, and store its value as a
string. Apply this to identity, certificate and account numbers so leading zeroes
and long digits survive. Do not use a numeric display mask to disguise a numeric
identifier. In an openpyxl adapter, use `cell.number_format = "@"` and a string
value; keep unknown identifier fields empty while retaining that format.

Keep quantities numeric. Store supplied dates as date values with an appropriate
display format, rather than making every field a string. For separate year,
month and day boxes, use numeric values in the respective cells when known.
Preserve the blank signature, seal and date areas needed for later completion.

Use explicit line breaks and wrapping for long labels or narrative text. Adjust
column widths, merged spans and row heights together; inspect merged cells
explicitly rather than trusting automatic row fitting. Keep adequate writing
space and readable type. Do not shrink the font to hide a missing field or an
undersized input area.

## 3. Set the print layout and export

Set an explicit print area around the complete form, including notes and the
signature/date block. Use the requested paper size and orientation; default to
A4 when the task gives no different paper requirement. Set page margins and
fit-to-page settings for the required page count. For a one-page form, fit to one
page wide and one page tall; treat this as a configuration target until the
printed page has been checked.

Export the `.xlsx`, then inspect that exact exported file. Reopen it to verify
the field inventory, editable input cells, blank areas and data types. Check
leading zeroes and every digit of long identifiers against the supplied string;
check dates by both their stored type and displayed value. Cell or range previews
can help find local defects, but cannot establish pagination.

## 4. Check the actual printed pages

Use the target Excel or WPS engine to open the exported workbook and inspect its
print preview, or export a PDF from that engine and inspect every page. Respect
user activity, agent occupancy and the host's foreground authorization before
operating the application. Use current documented control interfaces; do not
invent print-setting setters or recover a blocked background action by activating
the application or sending global keys without authorization.

At the export pause point, compare the printed page with the source inventory:

- Every title, label, option, unit and note appears completely.
- Long labels and narrative fields do not clip at cell or page boundaries.
- Input areas remain usable and signature, seal and date positions are intact.
- The form has the required page count, paper size and orientation, with no
  accidental blank or spill pages.
- Text remains readable and borders preserve the intended field grouping.

Fix clipping with column widths, row heights, merged spans, wrapping or explicit
line breaks. Export again and check the new output after each layout change.
Do not accept a range-rendering screenshot or valid worksheet XML as print
evidence.

If the target engine is unavailable, retain the exported workbook and name the
unmet check. A substitute such as LibreOffice may provide useful layout evidence,
but report that engine explicitly and leave Excel/WPS printing unverified.
Substitute-engine success does not establish the target engine's behavior.
After access or authorization returns, open the saved workbook in the target
engine and resume at this print check; do not rebuild completed content merely
because verification was interrupted.

## 5. Deliver with precise evidence

Deliver the editable workbook and any PDF requested by the user. State the print
engine actually used, the inspected page count and the checks that remain unmet.
Distinguish workbook-content checks from print-layout checks. Describe a workbook
as ready for the requested printing only when that target-engine check passes;
otherwise say which engine was checked and what is still unverified.
