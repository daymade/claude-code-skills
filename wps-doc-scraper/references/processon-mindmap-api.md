# ProcessOn Mind Map API

Use this reference when the WPS/KDocs public link embeds a ProcessOn `.pof` mind map or canvas.

## Public KDocs Link Metadata

For a share link like:

```text
https://www.kdocs.cn/view/l/<share_id>
```

the unauthenticated metadata endpoint is:

```text
https://drive.kdocs.cn/api/v5/links/<share_id>?review=true
```

For public ProcessOn mind maps, useful fields commonly include:

- `fileinfo.id`: ProcessOn/WPS file id.
- `fileinfo.groupid`: ProcessOn group id.
- `fileinfo.fname`: original filename, often ending with `.pof`.
- `user_acl.download` and `user_permission`: helpful for permission reporting only.

If the endpoint returns `用户未登录`, a placeholder shell, or omits file ids, do not force the path. Report the permission boundary.

## ProcessOn View And Data API

KDocs usually embeds:

```text
https://wps.processon.com/diagrams/view?file_id=<file_id>&group_id=<group_id>&is_recycle=false&user_id=0&product=kdocs_web&platform=&lang=en-US
```

The data API is:

```text
https://wps.processon.com/wpsapi/diagrams/view/api?file_id=<file_id>&group_id=<group_id>&is_recycle=false&user_id=0&product=kdocs_web&platform=&lang=en-US
```

The API returns JSON with a `definition` field. `definition` is usually a JSON-encoded string containing:

- `title`: document title.
- `children`: top-level mind-map nodes.
- `children[].children`: nested nodes.
- `children[].summaries`: summary/brace text attached to a node range.
- `comments`: comments with `selectionId`; the node id is usually the prefix before `_`.
- style/theme fields that are useful for rendering but not for Markdown text extraction.

Always save both the raw API payload and the parsed `definition` JSON.

## Markdown Conversion

Markdown should mirror the tree structure:

- node title -> bullet text
- nested children -> nested bullets
- summaries -> child bullets labeled `摘要`
- comments -> child bullets labeled `评论`

Do not reorder, smooth, summarize, or infer text. Convert HTML line breaks inside node titles to real newlines and strip markup that only exists for display.
