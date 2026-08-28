# csharp/tasks/ — 修订感知的 docx 解析脚本

dotnet-script (.csx) 脚本，基于 [DocumentFormat.OpenXml 3.2.0](https://github.com/dotnet/Open-XML-SDK) 提供修订感知的 docx 文本提取。

## 为什么存在这个目录

来源项目的 Python 端工具原本用 python-docx 的 `paragraph.text`。但 python-docx 的 `Run.text` 实现不递归 `<w:ins>` 包装的 run，导致**作者通过 Word 修订模式补回的所有内容（真实案例：一份审阅稿中整整 11 个新增段落）都漏读**。

裸 lxml 的 `.//w:t` 能读到 ins，但无法识别"段落标记被 `<w:del>` 包装的整段"——这些段在 docx 里仍有 `<w:t>` 内容，但接受修订后会消失。

OpenXML SDK 是 Word 工程团队官方维护的 SDK，对 ins/del/move/format 修订有完整一等公民支持。本目录的 3 个 csx 脚本封装了修订/批注/文本视图三类查询，输出 JSON 供 Python client 消费。

## 依赖

```bash
# 一次性安装 dotnet-script 全局工具
dotnet tool install -g dotnet-script
export PATH="$PATH:$HOME/.dotnet/tools"

# 如果本机只有 .NET 9+ 而 csx 引用 net8，需要 roll-forward
export DOTNET_ROLL_FORWARD=Major
```

NuGet 包（DocumentFormat.OpenXml 3.2.0）由 dotnet-script 自动 restore，无需手动管理。

## 段落索引语义

所有脚本统一用 `body.Elements<Paragraph>()`（**只数 body 直接子段，不递归表格内段**），与 python-docx `Document.paragraphs` 行为对齐。改用 `Descendants<Paragraph>()` 会包含表格内段落，索引会跟 Python 端错位。

## 脚本清单

### list_revisions.csx

列出 docx 中所有修订（内联 + 段落级），区分 ins/del 类型。

```bash
dotnet-script scripts/csharp/tasks/list_revisions.csx -- /path/to/file.docx
```

输出 JSON：
```json
{
  "summary": {
    "totalParagraphs": 6249,
    "totalDelElements": 76,
    "totalInsElements": 92,
    "paragraphsWithInlineDel": 63,
    "paragraphsWithInlineIns": 63,
    "paragraphsWithParaMarkDel": 21,
    "paragraphsWithParaMarkIns": 30,
    "revisedParagraphsCount": 96
  },
  "paraMarkDelIndices": [5433, 5434, ..., 6146],
  "paraMarkInsIndices": [5049, 5053, ..., 6092],
  "details": [{ "paragraphIndex": ..., "deletedText": ..., "insertedText": ... }, ...]
}
```

**典型用途**：识别"作者明确删除/插入的整段"，避免把这些段当成格式残骸误报。

### list_comments.csx

列出所有批注，含 thread 关系（reply 链）+ 段落锚定 + done 状态。

```bash
dotnet-script scripts/csharp/tasks/list_comments.csx -- /path/to/file.docx
```

输出 JSON：
```json
{
  "summary": { "total": 23, "resolved": 0, "unresolved": 23, "threadRoots": 14, "replies": 9 },
  "comments": [
    {
      "id": "82",
      "author": "审阅者A",
      "date": "2026-04-24T18:35:00",
      "content": "上面是第 2 点，下面是第 4 点，中间缺了第 3 点",
      "resolved": false,
      "replyToCommentId": null,
      "anchorParagraphIndex": 947,
      "anchorParagraphRange": [947, 947]
    },
    ...
  ]
}
```

**typed source files**：
- `comments.xml` — 批注 id/author/date/content（date 输出完整 `yyyy-MM-ddTHH:mm:ss`）
- `commentsExtended.xml` — done 状态 + paraIdParent（reply 链）
- `document.xml` 的 `<w:commentRangeStart>` / `<w:commentRangeEnd>` — 段落锚定（首选）
- `document.xml` 的 `<w:commentReference>` — 锚定回退：WPS 导出件部分批注只有引用点没有
  range（实测 2026-08-29 某 WPS 件 96 条中 6 条），此时用引用点所在段做单段锚定
- 零批注文件的 summary 同样输出五键（threadRoots/replies 为 0），下游无需特殊分支

**典型用途**：批注清单的权威来源（本 skill 中由 extract_review.py 消费）。

### extract_views.csx

每段输出三种文本视图 + 修订状态。NDJSON 格式（每行一段）。

```bash
# 全文
dotnet-script scripts/csharp/tasks/extract_views.csx -- /path/to/file.docx
# 段落范围
dotnet-script scripts/csharp/tasks/extract_views.csx -- /path/to/file.docx --range 6082-6094
```

输出每行：
```json
{"index":6088,"styleId":"a0","outlineLevel":null,
 "accepted":"第三步：明确适用范围与边界",
 "rejected":"",
 "display":"{+第三步：明确适用范围与边界+}",
 "paraMarkDel":false,"paraMarkIns":true,"hasInlineDel":false,"hasInlineIns":true}
```

视图语义：
- `accepted`：模拟"接受所有修订" → 包含 ins 文本，跳过 del 文本（`<w:t>` + `<w:ins>` 内 `<w:t>`，跳过 `<w:del>` 子树）
- `rejected`：模拟"拒绝所有修订" → 包含 del 文本，跳过 ins 文本（`<w:t>` + `<w:delText>`，跳过 `<w:ins>` 子树）
- `display`：含修订标记 → del 用 `[-...-]`，ins 用 `{+...+}`，其余正常

**典型用途**：替代 paragraph.text 的核心数据接口。Python 端 `bridge_lib/docx_bridge_client.py` 用这个脚本提供 `paragraph_text()` / `paragraphs_text()` / `extract_views()` 三个函数。

## 设计参考

- 修订处理模式：`~/.claude/plugins/cache/minimax-skills/.../Samples/TrackChangesSamples.cs`
- 批注 4-file 系统：`~/.claude/plugins/cache/minimax-skills/.../Samples/FootnoteAndCommentSamples.cs`
- OOXML 元素顺序：`~/.claude/plugins/cache/minimax-skills/.../references/openxml_element_order.md`

## 性能

- 首次调用：~1.5 秒（dotnet-script 启动 + NuGet restore，restore 在 ~/.nuget/packages/ 首次后会缓存）
- 后续调用同一 docx：Python client 内存级 LRU 缓存命中，~0ms
- 不同 docx：每次重新启动 csx，~1 秒

## 添加新脚本的 SOP

1. 复制 `list_revisions.csx` 作为模板（含 `#r` 头、Args 校验、try/finally、JSON 输出）
2. 段落索引必须用 `body.Elements<Paragraph>()`
3. 文档化：入参/出参 schema、source sample 引用、典型用途
4. 在 `bridge_lib/docx_bridge_client.py` 中加对应的 Python wrapper（含 LRU 缓存 + TypedDict）
5. 在本 README 加一节
6. 不要 import `using var`（dotnet-script 不支持 top-level using），用 `try { ... } finally { doc.Dispose(); }`
7. 不要写 `string?` 等 nullable reference type 注解（dotnet-script 默认未启用 `#nullable enable`）
