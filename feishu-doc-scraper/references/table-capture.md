# Capture Wiki Base and Sheets

Use this branch after source-account binding when a Wiki node resolves to
`bitable`, `sheet` or `sheets`. Keep docx, comments and linked documents on their
existing extraction branches. Bind the profile through `lark-cli-router`; use its
preparation route if CLI/auth is missing, then continue the same source.

```bash
python3 scripts/capture_table.py \
  --source 'https://example.feishu.cn/wiki/<node-token>' \
  --profile '<bound-profile>' --out '<new-capture-directory>' \
  --attachments local
```

Use `--attachments metadata` when bytes belong on NAS or only a locator is
authorized. This collector downloads no video extensions. Its local attachment
branch accepts named document/image formats up to 100 MiB; other attachments
remain explicit pending locators. Raise the explicit cell/page budget only when
the selected source scope requires it. An existing output directory is refused;
reuse its completed evidence or choose a new timestamped capture.

## Resolve and interpret responses

Normalize a Wiki URL with `scripts/lark_result.py:wiki_token` before passing it
to `wiki +node-get --node-token`. Passing the complete URL as the token is an
invalid probe, not evidence about access. The helper accepts bare Wiki tokens or
HTTPS Feishu/Lark Wiki URLs; reject unrelated URL types before network access.

Use `parse_cli_result(stdout, stderr, returncode)` for shortcut envelopes. It
preserves a real `ok:false` error after CLI refresh notices on either stream.
Empty, malformed, conflicting or exit-inconsistent output stays unknown. Do not
convert it to permission denied or discard stderr. Declare `receipt_keys` only
for an operation whose installed guide specifies an unwrapped export receipt;
Base `+record-list --output` is such an operation.

## Read the result

The new directory contains `table.md`, `manifest.json`, `_data/` raw API exports
and optional `media/` caches. Source values, record IDs, field schema and grid
formulas remain in the raw exports; Markdown escapes source HTML and associates
each retained attachment with its table, record and field.

- **Base:** require the complete table count, all-record/all-field export scope,
  unique record IDs, exhausted pagination, matching declared counts and a stable
  revision. Retain unsupported schema fields and export warnings as gaps; readable
  fields do not establish whole-table completeness.
- **Sheets:** save the declared grid and formulas, check the CLI completion flag,
  truncation, pagination and revision. The readable preview omits empty rows;
  raw cells remain. Charts, floating images and pivots are separate gaps.
- **Attachments:** retain file token, source coordinates, operation, declared and
  observed bytes, MIME and SHA-256. `drive +preview --type source_file` with equal
  size is a verified cache; absent an independent platform hash, it is not proof
  of original-byte identity. A failed or unretained attachment keeps the capture
  partial.

Exit `0` means complete **within this declared scope**, `3` means a retained
partial capture, and `2` means invalid input or an unstarted capture. Inspect
`gaps` before deciding the next action. Keep real access errors with the bound
identity and observation time; a later decision needs a fresh valid query.

This capture manifest is not the archive-storage schema. At permanent filing,
map raw/searchable files to the recipient's versioned derivative records and
binary caches to stable platform/NAS/OSS locators using
[archive storage](archive-storage-contract.md). Run that owner's storage validator on the
resulting archive manifest. Visually open one nonempty table and retained
attachment before claiming reader acceptance; capture success proves neither
navigation nor playback.
