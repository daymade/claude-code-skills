# Archive Storage Contract

Use this contract after faithful extraction and before filing the result into a knowledge base. It prevents a common category error: treating a successful download as proof that a raw binary belongs in Git.

## One artifact, three independent properties

For each artifact record:

1. `storage` states the durable source of record: `git`, `source`, or `oss`.
2. `locator` says how to retrieve that durable object.
3. `cache_path` is optional and never changes the source of record. A cache may disappear on another machine without making the archive incomplete.

Git is the default only for searchable structured material: Markdown, CSV, JSON, YAML, text, XML, and source HTML. MP4, Office files, PDFs, and raster/vector images are raw binaries and must not use `storage: git` or Git LFS under this contract.

## Source-of-record examples

Feishu original with an optional local cache:

```json
{
  "role": "embedded_media_original",
  "storage": "source",
  "locator": {
    "system": "feishu",
    "source_url": "https://example.feishu.cn/wiki/<node-token>",
    "token": "<file-token>"
  },
  "cache_path": "<local-cache-path>/clip.mp4",
  "bytes": 123456,
  "sha256": "<sha256>",
  "mime": "video/mp4"
}
```

Structured derivative in Git:

```json
{
  "role": "sheet_csv",
  "storage": "git",
  "path": "sources/<sheet-id>.csv",
  "bytes": 4321,
  "sha256": "<sha256>",
  "mime": "text/csv"
}
```

Independent object-storage copy:

```json
{
  "role": "owner_exported_docx",
  "storage": "oss",
  "locator": {
    "system": "oss",
    "uri": "oss://<bucket>/<content-addressed-key>"
  },
  "cache_path": "<local-cache-path>/owner-export.docx",
  "bytes": 98765,
  "sha256": "<sha256>",
  "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
}
```

## Decision rule

- Use `source` when Feishu still exposes the original through a stable document/file/whiteboard locator. A temporary CDN URL is not stable; store its token and parent source instead.
- Use `oss` when independent retention is a real requirement or the original platform locator is not a reliable future retrieval path. Uploading changes external state, so it must be authorized and independently read back.
- Use `git` for the structured layer that makes the archive searchable, diffable, and maintainable. Git is not a generic blob store here, and Git LFS does not change that boundary.

If an artifact is both on Feishu and OSS, choose the intended authority as `storage` and record the other under `replicas`. Do not create two competing source-of-truth fields.

## Validation

Run from the skill directory:

```bash
python3 scripts/check_archive_storage.py <artifact-manifest.json>
```

The validator fails when:

- a raw binary is declared `storage: git`;
- an external artifact has no stable locator;
- a Git artifact has no `path`;
- an external artifact uses `path` instead of `cache_path`, which would make a working copy look authoritative;
- `storage` is absent or unknown.

The validator does not upload, delete, or move anything. Byte/hash verification remains the host archive workflow's responsibility because only it knows whether a cache is expected to exist on that machine.
