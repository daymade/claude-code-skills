# Capture Manifest

Every archive should include `capture-manifest.json`. Minimum fields:

```json
{
  "captured_at": "2026-06-26T00:00:00+00:00",
  "source_url": "https://www.kdocs.cn/view/l/...",
  "source_type": "kdocs_processon",
  "kdocs_share_id": "...",
  "kdocs_link_api_url": "https://drive.kdocs.cn/api/v5/links/...?review=true",
  "processon_api_url": "https://wps.processon.com/wpsapi/diagrams/view/api?...",
  "file_id": "...",
  "group_id": "...",
  "title": "...",
  "creator": "...",
  "counts": {
    "nodes": 0,
    "comments": 0
  },
  "outputs": {
    "processon_api_json": "processon-api.json",
    "processon_definition_json": "processon-definition.json",
    "markdown": "title.md",
    "rendered_svg": "title-全画布.svg",
    "rendered_png": "title-全画布.png"
  },
  "notes": []
}
```

## Acceptance Checks

- Raw API JSON exists.
- Parsed definition JSON exists when a ProcessOn API payload is available.
- Markdown exists and is generated from source structure.
- Original image exists for visual/canvas documents, unless a permission or rendering boundary is documented.
- No text output contains `�`.
- Partial extraction is marked partial in `notes`; do not present it as complete.
