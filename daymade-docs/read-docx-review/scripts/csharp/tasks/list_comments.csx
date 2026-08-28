// list_comments.csx — 列出 docx 中所有批注，含 resolved 状态、段落锚定
//
// 入参：
//   $1: docx 文件路径
//
// 出参（stdout，单个 JSON）：
//   {
//     summary: { total, resolved, unresolved },
//     comments: [
//       {
//         id, author, date, content, resolved,
//         anchorParagraphIndex,            // CommentRangeStart 所在段
//         anchorParagraphRange: [start, end]  // 跨段批注的范围
//       }
//     ]
//   }
//
// 段落索引语义：与 list_revisions.csx 一致（body.Elements<Paragraph>，不递归表格）
//
// 数据源：
//   - WordprocessingCommentsPart      → comments.xml（id, author, date, content）
//   - WordprocessingCommentsExPart    → commentsExtended.xml（paraId → done 映射）
//   - document.xml CommentRangeStart  → 段落锚定（首选）
//   - document.xml CommentReference   → 锚定回退（WPS 导出件部分批注只有 reference
//     没有 range，实测 2026-08-29：某 WPS 件 96 条中 6 条为此形态）
//
// 来源：
//   - DocumentFormat.OpenXml 3.2.0
//   - 模式参考 minimax-docx Samples/FootnoteAndCommentSamples.cs
//
// 用法：
//   dotnet-script scripts/csharp/tasks/list_comments.csx -- /path/to/file.docx

#r "nuget: DocumentFormat.OpenXml, 3.2.0"

using System.Text.Json;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;
using DocumentFormat.OpenXml.Office2013.Word;

if (Args.Count < 1)
{
    Console.Error.WriteLine("Usage: dotnet-script list_comments.csx -- <docx_path>");
    Environment.Exit(1);
}

var docPath = Args[0];

var doc = WordprocessingDocument.Open(docPath, false);
try
{
    var mainPart = doc.MainDocumentPart!;
    var body = mainPart.Document.Body!;
    var paragraphs = body.Elements<Paragraph>().ToList();

    // 1. 读所有批注（comments.xml）
    var commentsPart = mainPart.WordprocessingCommentsPart;
    if (commentsPart == null)
    {
        // 与有批注路径保持同形（五键），下游不用为零批注写特殊分支
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            summary = new { total = 0, resolved = 0, unresolved = 0, threadRoots = 0, replies = 0 },
            comments = Array.Empty<object>(),
        }, new JsonSerializerOptions { WriteIndented = true }));
        Environment.Exit(0);
    }

    var commentRecords = new Dictionary<string, (string Author, string Date, string Content, string ParaId)>();
    foreach (var c in commentsPart.Comments.Elements<Comment>())
    {
        var cid = c.Id?.Value ?? "";
        var author = c.Author?.Value ?? "";
        var date = c.Date?.Value.ToString("yyyy-MM-ddTHH:mm:ss") ?? "";

        // 批注内容：拼接所有 Text（批注本身没有修订标记）
        var content = string.Concat(c.Descendants<Text>().Select(t => t.Text));

        // paraId 用于关联 commentsExtended（done 状态）
        var lastP = c.Descendants<Paragraph>().LastOrDefault();
        var paraId = "";
        if (lastP != null)
        {
            paraId = lastP.GetAttributes().FirstOrDefault(a => a.LocalName == "paraId").Value ?? "";
        }

        commentRecords[cid] = (author, date, content, paraId);
    }

    // 2. 读 done 状态 + thread 关系（commentsExtended.xml）
    //    paraIdParent 表示"这是某条批注的回复"
    var doneMap = new Dictionary<string, bool>();
    var parentMap = new Dictionary<string, string>();  // paraId → paraIdParent
    var commentsExPart = mainPart.WordprocessingCommentsExPart;
    if (commentsExPart?.CommentsEx != null)
    {
        foreach (var ext in commentsExPart.CommentsEx.Elements<CommentEx>())
        {
            var paraId = ext.ParaId?.Value ?? "";
            var done = ext.Done?.Value ?? false;
            var parent = ext.ParaIdParent?.Value ?? "";
            if (!string.IsNullOrEmpty(paraId))
            {
                doneMap[paraId] = done;
                if (!string.IsNullOrEmpty(parent))
                    parentMap[paraId] = parent;
            }
        }
    }

    // paraId → commentId 反向映射（用于把 reply 关系翻译为 commentId 关系）
    var paraIdToCommentId = commentRecords
        .Where(kv => !string.IsNullOrEmpty(kv.Value.ParaId))
        .ToDictionary(kv => kv.Value.ParaId, kv => kv.Key);

    // 3. 在 document.xml 中找每个批注的 CommentRangeStart 段落锚定
    var anchorMap = new Dictionary<string, (int Start, int End)>();
    for (int i = 0; i < paragraphs.Count; i++)
    {
        var p = paragraphs[i];
        foreach (var s in p.Descendants<CommentRangeStart>())
        {
            var cid = s.Id?.Value ?? "";
            if (!string.IsNullOrEmpty(cid))
            {
                if (!anchorMap.ContainsKey(cid))
                    anchorMap[cid] = (i, i);
                else
                    anchorMap[cid] = (anchorMap[cid].Start, i);  // 不该走到这，但兜底
            }
        }
        foreach (var e in p.Descendants<CommentRangeEnd>())
        {
            var cid = e.Id?.Value ?? "";
            if (!string.IsNullOrEmpty(cid) && anchorMap.ContainsKey(cid))
                anchorMap[cid] = (anchorMap[cid].Start, i);
        }
    }

    // 3b. 锚定回退：WPS 导出件部分批注没有 CommentRangeStart/End，只有正文里的
    //     CommentReference（批注气泡引用点）。对 range 缺失的批注，用 reference
    //     所在段落做单段锚定，否则这些批注在对账表上无法定位（实测 6/96 条）。
    for (int i = 0; i < paragraphs.Count; i++)
    {
        foreach (var r in paragraphs[i].Descendants<CommentReference>())
        {
            var cid = r.Id?.Value ?? "";
            if (!string.IsNullOrEmpty(cid) && !anchorMap.ContainsKey(cid))
                anchorMap[cid] = (i, i);
        }
    }

    // 4. 拼装结果
    var comments = new List<object>();
    int resolved = 0, unresolved = 0;
    int threadRoots = 0, replies = 0;
    foreach (var (cid, rec) in commentRecords.OrderBy(kv => int.TryParse(kv.Key, out var n) ? n : 0))
    {
        bool isResolved = !string.IsNullOrEmpty(rec.ParaId) && doneMap.GetValueOrDefault(rec.ParaId, false);
        if (isResolved) resolved++; else unresolved++;

        // thread 关系：如果当前 paraId 有 parent，说明这是回复
        string replyToCommentId = null;
        if (!string.IsNullOrEmpty(rec.ParaId) && parentMap.TryGetValue(rec.ParaId, out var parentParaId))
        {
            paraIdToCommentId.TryGetValue(parentParaId, out replyToCommentId);
            replies++;
        }
        else
        {
            threadRoots++;
        }

        int? anchorStart = null, anchorEnd = null;
        if (anchorMap.TryGetValue(cid, out var anchor))
        {
            anchorStart = anchor.Start;
            anchorEnd = anchor.End;
        }

        comments.Add(new
        {
            id = cid,
            author = rec.Author,
            date = rec.Date,
            content = rec.Content,
            resolved = isResolved,
            replyToCommentId,
            anchorParagraphIndex = anchorStart,
            anchorParagraphRange = anchorStart.HasValue
                ? new[] { anchorStart.Value, anchorEnd!.Value }
                : null,
        });
    }

    var result = new
    {
        summary = new {
            total = comments.Count,
            resolved,
            unresolved,
            threadRoots,
            replies,
        },
        comments,
    };

    Console.WriteLine(JsonSerializer.Serialize(result,
        new JsonSerializerOptions { WriteIndented = true }));
}
finally
{
    doc.Dispose();
}
