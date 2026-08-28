// list_revisions.csx — 列出 docx 中所有修订（ins/del），区分内联和段落级
//
// 入参：
//   $1: docx 文件路径
//
// 出参（stdout）：
//   { summary: { totalParagraphs, totalDelElements, ... },
//     paraMarkDelIndices: [...],       // 整段被作者标记删除（接受后整段消失）
//     paraMarkInsIndices: [...],       // 整段被作者标记插入（接受后保留）
//     details: [...]                    // 每段修订详情
//   }
//
// 段落索引语义：
//   只数 body 直接子段（不递归表格内段），与 python-docx Document.paragraphs 对齐
//
// 来源：
//   - DocumentFormat.OpenXml 3.2.0 Wordprocessing 类型
//   - 模式参考 minimax-docx Samples/TrackChangesSamples.cs
//
// 用法：
//   dotnet-script scripts/csharp/tasks/list_revisions.csx -- /path/to/file.docx

#r "nuget: DocumentFormat.OpenXml, 3.2.0"

using System.Text.Json;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;

if (Args.Count < 1)
{
    Console.Error.WriteLine("Usage: dotnet-script list_revisions.csx -- <docx_path>");
    Environment.Exit(1);
}

var docPath = Args[0];

var doc = WordprocessingDocument.Open(docPath, false);
try
{
    var body = doc.MainDocumentPart!.Document.Body!;
    var paragraphs = body.Elements<Paragraph>().ToList();

    int totalDelElements = 0;
    int totalInsElements = 0;
    int paraWithInlineDel = 0;
    int paraWithInlineIns = 0;
    var paraMarkDelIndices = new List<int>();
    var paraMarkInsIndices = new List<int>();
    var details = new List<object>();

    for (int i = 0; i < paragraphs.Count; i++)
    {
        var p = paragraphs[i];

        // 段内 ins/del runs
        var dels = p.Descendants<DeletedRun>().ToList();
        var ins = p.Descendants<InsertedRun>().ToList();

        totalDelElements += dels.Count;
        totalInsElements += ins.Count;
        if (dels.Count > 0) paraWithInlineDel++;
        if (ins.Count > 0) paraWithInlineIns++;

        // 段落标记本身被 del/ins 包装（pPr/rPr 内）
        var paraMarkRPr = p.ParagraphProperties?.ParagraphMarkRunProperties;
        bool paraMarkDel = paraMarkRPr?.Elements<Deleted>().Any() ?? false;
        bool paraMarkIns = paraMarkRPr?.Elements<Inserted>().Any() ?? false;

        if (paraMarkDel) paraMarkDelIndices.Add(i);
        if (paraMarkIns) paraMarkInsIndices.Add(i);

        if (dels.Count > 0 || ins.Count > 0 || paraMarkDel || paraMarkIns)
        {
            var delText = string.Concat(
                dels.SelectMany(d => d.Descendants<DeletedText>()).Select(t => t.Text));
            var insText = string.Concat(
                ins.SelectMany(r => r.Descendants<Text>()).Select(t => t.Text));

            details.Add(new
            {
                paragraphIndex = i,
                paraMarkDel,
                paraMarkIns,
                inlineDelCount = dels.Count,
                inlineInsCount = ins.Count,
                deletedText = delText,
                insertedText = insText,
            });
        }
    }

    var result = new
    {
        summary = new
        {
            totalParagraphs = paragraphs.Count,
            totalDelElements,
            totalInsElements,
            paragraphsWithInlineDel = paraWithInlineDel,
            paragraphsWithInlineIns = paraWithInlineIns,
            paragraphsWithParaMarkDel = paraMarkDelIndices.Count,
            paragraphsWithParaMarkIns = paraMarkInsIndices.Count,
            revisedParagraphsCount = details.Count,
        },
        paraMarkDelIndices,
        paraMarkInsIndices,
        details,
    };

    Console.WriteLine(JsonSerializer.Serialize(result,
        new JsonSerializerOptions { WriteIndented = true }));
}
finally
{
    doc.Dispose();
}
