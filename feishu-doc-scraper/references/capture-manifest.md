# Capture Manifest

Use `scripts/build_feishu_markdown.py` when extraction is easier to stage as structured data before rendering.

This capture manifest describes the Markdown body. It is not the artifact-storage manifest for attachments. When a capture includes video, Office, PDF, image, or whiteboard resources, keep their durable-storage decisions in the separate `files[]` schema from [archive-storage-contract.md](archive-storage-contract.md) and validate that manifest before filing the archive.

## Minimal Shape

```json
{
  "title": "Document title",
  "source": "https://example.feishu.cn/wiki/...",
  "author": ["Author A", "Author B"],
  "published": "",
  "created": "2026-05-07",
  "description": "Short summary",
  "tags": ["clippings", "feishu"],
  "sections": [
    {
      "heading_level": 1,
      "heading": "Main Heading",
      "body": [
        "Paragraph one.",
        "- Bullet item",
        "| Col A | Col B |",
        "| --- | --- |",
        "| A1 | B1 |"
      ]
    }
  ]
}
```

## Field Rules

- `title`: required
- `source`: strongly recommended
- `author`: string or array of strings
- `published`: optional
- `created`: optional, defaults to today only if the caller sets it
- `description`: optional
- `tags`: optional, string or array
- `sections`: required array
- `heading_level`: optional, defaults to `2`
- `body`: string or array of Markdown blocks

## Rendering Command

```bash
python3 scripts/build_feishu_markdown.py \
  --input /path/to/capture.json \
  --output /path/to/output.md
```

If `--output` is omitted, the renderer prints Markdown to stdout.
