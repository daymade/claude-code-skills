// extract_views.csx — 输出每段三种文本视图（accepted/rejected/display）+ 修订状态
//
// 入参：
//   $1: docx 文件路径
//
// 出参（stdout，NDJSON：每行一段）：
//   {
//     "index": 6083,
//     "styleId": "4",
//     "outlineLevel": 3,
//     "accepted": "第三步：明确适用范围与边界",   // 接受所有修订后
//     "rejected": "",                                           // 拒绝所有修订（原稿）
//     "display": "{+第三步：明确适用范围与边界+}", // 含修订标记的显示视图
//     "paraMarkDel": false,                                      // 段落标记是否被 del 包装
//     "paraMarkIns": true,                                       // 段落标记是否被 ins 包装
//     "hasInlineDel": false,
//     "hasInlineIns": true
//   }
//
// 视图语义：
//   accepted = 跳过 <w:del> 内文本（含 <w:delText>），保留普通 <w:t> + <w:ins> 内 <w:t>
//   rejected = 跳过 <w:ins> 内文本，保留普通 <w:t> + <w:del> 内 <w:delText>
//   display  = 三段拼接，del 用 [-...-]，ins 用 {+...+}
//
// 段落索引语义：与 list_revisions.csx / list_comments.csx 一致（body 直接子段）
//
// 用法：
//   dotnet-script scripts/csharp/tasks/extract_views.csx -- /path/to/file.docx [--range 6080-6100]

#r "nuget: DocumentFormat.OpenXml, 3.2.0"

using System.Text;
using System.Text.Json;
using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;

if (Args.Count < 1)
{
    Console.Error.WriteLine("Usage: dotnet-script extract_views.csx -- <docx_path> [--range start-end]");
    Environment.Exit(1);
}

var docPath = Args[0];
int? rangeStart = null, rangeEnd = null;
for (int i = 1; i < Args.Count - 1; i++)
{
    if (Args[i] == "--range")
    {
        var parts = Args[i + 1].Split('-');
        if (parts.Length == 2 && int.TryParse(parts[0], out var s) && int.TryParse(parts[1], out var e))
        {
            rangeStart = s;
            rangeEnd = e;
        }
    }
}

string ExtractText(OpenXmlElement el, bool acceptIns, bool acceptDel)
{
    // acceptIns=true → 包含 ins 内文本（视为已接受插入）
    // acceptDel=true → 包含 del 内文本（视为拒绝删除）
    var sb = new StringBuilder();
    void Walk(OpenXmlElement node, bool inDel, bool inIns)
    {
        foreach (var child in node.ChildElements)
        {
            switch (child)
            {
                case DeletedRun dr:
                    Walk(dr, true, inIns);
                    break;
                case InsertedRun ir:
                    Walk(ir, inDel, true);
                    break;
                case Text t:
                    if (inDel && !acceptDel) break;
                    if (inIns && !acceptIns) break;
                    sb.Append(t.Text);
                    break;
                case DeletedText dt:
                    if (!acceptDel) break;
                    sb.Append(dt.Text);
                    break;
                case TabChar:
                    if (inDel && !acceptDel) break;
                    if (inIns && !acceptIns) break;
                    sb.Append('\t');
                    break;
                case Break:
                    if (inDel && !acceptDel) break;
                    if (inIns && !acceptIns) break;
                    sb.Append('\n');
                    break;
                default:
                    Walk(child, inDel, inIns);
                    break;
            }
        }
    }
    Walk(el, false, false);
    return sb.ToString();
}

string ExtractDisplay(OpenXmlElement el)
{
    // del 用 [-...-]，ins 用 {+...+}，普通文本直接保留
    var sb = new StringBuilder();
    void Walk(OpenXmlElement node)
    {
        foreach (var child in node.ChildElements)
        {
            switch (child)
            {
                case DeletedRun dr:
                    var dtxt = string.Concat(dr.Descendants<DeletedText>().Select(t => t.Text));
                    if (!string.IsNullOrEmpty(dtxt)) sb.Append("[-").Append(dtxt).Append("-]");
                    break;
                case InsertedRun ir:
                    var itxt = string.Concat(ir.Descendants<Text>().Select(t => t.Text));
                    if (!string.IsNullOrEmpty(itxt)) sb.Append("{+").Append(itxt).Append("+}");
                    break;
                case Text t:
                    sb.Append(t.Text);
                    break;
                case TabChar:
                    sb.Append('\t');
                    break;
                case Break:
                    sb.Append('\n');
                    break;
                default:
                    Walk(child);
                    break;
            }
        }
    }
    Walk(el);
    return sb.ToString();
}

var doc = WordprocessingDocument.Open(docPath, false);
try
{
    var body = doc.MainDocumentPart!.Document.Body!;
    var paragraphs = body.Elements<Paragraph>().ToList();

    var jsonOpts = new JsonSerializerOptions { WriteIndented = false };

    for (int i = 0; i < paragraphs.Count; i++)
    {
        if (rangeStart.HasValue && i < rangeStart.Value) continue;
        if (rangeEnd.HasValue && i > rangeEnd.Value) break;

        var p = paragraphs[i];
        var pPr = p.ParagraphProperties;
        var paraMarkRPr = pPr?.ParagraphMarkRunProperties;
        bool paraMarkDel = paraMarkRPr?.Elements<Deleted>().Any() ?? false;
        bool paraMarkIns = paraMarkRPr?.Elements<Inserted>().Any() ?? false;

        var styleId = pPr?.ParagraphStyleId?.Val?.Value ?? "";
        int? outlineLevel = pPr?.OutlineLevel?.Val?.Value;

        var accepted = ExtractText(p, acceptIns: true, acceptDel: false);
        var rejected = ExtractText(p, acceptIns: false, acceptDel: true);
        var display = ExtractDisplay(p);

        bool hasInlineDel = p.Descendants<DeletedRun>().Any();
        bool hasInlineIns = p.Descendants<InsertedRun>().Any();

        var line = JsonSerializer.Serialize(new
        {
            index = i,
            styleId,
            outlineLevel,
            accepted,
            rejected,
            display,
            paraMarkDel,
            paraMarkIns,
            hasInlineDel,
            hasInlineIns,
        }, jsonOpts);
        Console.WriteLine(line);
    }
}
finally
{
    doc.Dispose();
}
