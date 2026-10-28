# csharp/tasks/ — 修订感知的 docx 解析脚本

dotnet-script (.csx) 脚本，基于 [OpenXML SDK](https://github.com/dotnet/Open-XML-SDK)
提供下述范围内的修订感知查询和比较快照。

## 为什么存在这个目录

来源项目的 Python 端工具原本用 python-docx 的 `paragraph.text`。但 python-docx 的 `Run.text` 实现不递归 `<w:ins>` 包装的 run，导致**作者通过 Word 修订模式补回的所有内容（真实案例：一份审阅稿中整整 11 个新增段落）都漏读**。

裸 lxml 的 `.//w:t` 能读到 ins，但无法识别"段落标记被 `<w:del>` 包装的整段"——这些段在 docx 里仍有 `<w:t>` 内容，但接受修订后会消失。

OpenXML SDK 是 Word 工程团队维护的 SDK。本目录封装修订/批注/文本视图查询及无未决修订稿的全文比较快照，输出 JSON 供 Python client 消费；各脚本支持范围分别如下。

## 依赖

首次准备沿 [`SKILL.md` 的依赖入口](../SKILL.md#依赖首次使用装一次)执行。
各 `.csx` 的 `#r` 声明定义 NuGet 依赖；Python 入口的环境和 PATH 处理由
[`docx_bridge_client.py`](../scripts/bridge_lib/docx_bridge_client.py) 定义。
直接调用 dotnet-script 时需自行提供相应工具路径和运行环境。

## 段落索引语义

原有 `list_revisions`、`list_comments`、`extract_views` 的段落号统一用
`body.Elements<Paragraph>()`（**只数 body 直接子段，不递归表格内段**），与 python-docx
`Document.paragraphs` 对齐。新增比较快照使用独立的 story/path 地址，包含表格内段落；
不要将其地址当成旧 API 的段落号。

## 脚本清单

### list_revisions.csx

列出 body 直接子段中支持的内联与段落标记 ins/del，不递归表格，也不枚举所有修订类型。

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
- 零批注文件的 summary 保持相同字段形状，threadRoots/replies 为 0，下游无需特殊分支

**典型用途**：批注清单的权威来源（本 skill 中由 extract_review.py 消费）。

### extract_views.csx

每个 body 直接子段输出下列文本视图与修订状态。NDJSON 格式（每行一段）。

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
- `accepted`：保留已支持的内联 ins 文本，跳过 del 文本
- `rejected`：保留已支持的内联 del 文本，跳过 ins 文本
- `display`：含修订标记 → del 用 `[-...-]`，ins 用 `{+...+}`，其余正常

段落标记增删另由 `paraMarkDel` / `paraMarkIns` 报告；这些文本视图并不落实整段合并、
移位、表格或属性修订，不能当成“接受/拒绝全文所有修订”的物化结果。实现与输出字段见
[`extract_views.csx`](../scripts/csharp/tasks/extract_views.csx)。

**典型用途**：替代 paragraph.text 的核心数据接口。Python 端 `bridge_lib/docx_bridge_client.py` 用这个脚本提供 `paragraph_text()` / `paragraphs_text()` / `extract_views()`。

### compare_snapshot.csx

供 `comparison_snapshot(docx)` 调用；读取正文、页眉、页脚、脚注和尾注。先检查这些部件中
未决的插入、删除、段落标记、移位、属性及表格修订；发现即抛错，不生成比较结果，不写文件。
旧查询接口不受此门影响。处理视图的分工见 [全文对比流程](full-comparison.md)。

输出对象字段：`engine`、`revisionPolicy`、`stories`、`unsupported`、`records`。
每条记录包含 `story`、`path`、`kind`（`paragraph` 或 `table_shape`）与完整 `text`。
表格形状按行记录单元格的横向跨度与纵向合并；内容仍逐段保留。路径可包含
`/table1/row1/cell2/p1`，脚注/尾注用 note id。页眉页脚按 part URI 区分，不能据此判断
它当前在某一页是否显示。`unsupported` 标出图片、文本框、嵌入对象或替代内容等另核范围。

## 设计参考

- 修订处理模式：`~/.claude/plugins/cache/minimax-skills/.../Samples/TrackChangesSamples.cs`
- 批注系统：`~/.claude/plugins/cache/minimax-skills/.../Samples/FootnoteAndCommentSamples.cs`
- OOXML 元素顺序：`~/.claude/plugins/cache/minimax-skills/.../references/openxml_element_order.md`

## 调用与缓存

查询 API 的缓存和 csx 启动方式见
[`docx_bridge_client.py`](../scripts/bridge_lib/docx_bridge_client.py)。比较快照不走查询缓存，
由比较入口绑定当前输入哈希。依赖 restore 与执行耗时取决于实际环境，不据固定等待时长
判定成功；检查进程结果和输出。

## 添加新脚本的 SOP

1. 复制 `list_revisions.csx` 作为模板（含 `#r` 头、Args 校验、try/finally、JSON 输出）
2. 扩展旧段落 API 时保留 `body.Elements<Paragraph>()`；比较记录沿用其独立 story/path 地址
3. 文档化：入参/出参 schema、source sample 引用、典型用途
4. 在 `bridge_lib/docx_bridge_client.py` 中加对应的 Python wrapper（含 LRU 缓存 + TypedDict）
5. 在本 README 加一节
6. 不要 import `using var`（dotnet-script 不支持 top-level using），用 `try { ... } finally { doc.Dispose(); }`
7. 不要写 `string?` 等 nullable reference type 注解（dotnet-script 默认未启用 `#nullable enable`）
