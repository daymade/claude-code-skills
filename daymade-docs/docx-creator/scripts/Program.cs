// 协议 markdown → 生产级中文合同 docx(minimax-docx OpenXML SDK + Markdig)
// 用法: dotnet run -- <input.md> <output.docx>
// CJK:宋体正文/黑体标题/RunFonts 双槽; 列表每条独立 NumId restart; 表格全边框;
// 信息块(含软换行)左对齐、正文两端对齐; A4 + 页脚页码。
using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;
using Markdig;
using Markdig.Syntax;
using Markdig.Syntax.Inlines;
using MdTable = Markdig.Extensions.Tables.Table;
using MdTableRow = Markdig.Extensions.Tables.TableRow;
using MdTableCell = Markdig.Extensions.Tables.TableCell;

class Program
{
    const string SONG = "宋体", HEI = "黑体", WEST = "Times New Roman";
    const string BODY = "24", H1 = "36", H2 = "28"; // half-points: 12/18/14pt

    static readonly List<(int numId, bool ordered)> Lists = new();
    static int _numId = 0;

    static RunProperties RunProps(string font, string size, bool bold)
    {
        var rp = new RunProperties();
        rp.Append(new RunFonts { Ascii = WEST, HighAnsi = WEST, EastAsia = font });
        rp.Append(new FontSize { Val = size });
        rp.Append(new FontSizeComplexScript { Val = size });
        if (bold) { rp.Append(new Bold()); rp.Append(new BoldComplexScript()); }
        rp.Append(new Color { Val = "000000" });
        return rp;
    }

    static Run MakeRun(string text, string font, string size, bool bold)
    {
        var r = new Run(RunProps(font, size, bold));
        r.Append(new Text(text) { Space = SpaceProcessingModeValues.Preserve });
        return r;
    }

    static (List<Run> runs, bool hasBreak) InlineRuns(ContainerInline? container, string font, string size, bool baseBold)
    {
        var runs = new List<Run>();
        bool hasBreak = false;
        void Walk(ContainerInline? c, bool bold)
        {
            if (c == null) return;
            for (var n = c.FirstChild; n != null; n = n.NextSibling)
            {
                switch (n)
                {
                    case LiteralInline lit:
                        var s = lit.Content.ToString();
                        if (s.Length > 0) runs.Add(MakeRun(s, font, size, bold));
                        break;
                    case EmphasisInline em:
                        Walk(em, em.DelimiterCount >= 2 ? true : bold);
                        break;
                    case LineBreakInline:
                        hasBreak = true;
                        var br = MakeRun("", font, size, bold);
                        br.AppendChild(new Break());
                        runs.Add(br);
                        break;
                    case CodeInline code:
                        runs.Add(MakeRun(code.Content, font, size, bold));
                        break;
                    default:
                        if (n is ContainerInline ci) Walk(ci, bold);
                        break;
                }
            }
        }
        Walk(container, baseBold);
        if (runs.Count == 0) runs.Add(MakeRun("", font, size, baseBold));
        return (runs, hasBreak);
    }

    static Paragraph Para(IEnumerable<Run> runs, JustificationValues just, string? spaceAfter = "120", string line = "360", int? numId = null)
    {
        var pp = new ParagraphProperties();
        pp.Append(new Justification { Val = just });
        var spacing = new SpacingBetweenLines { Line = line, LineRule = LineSpacingRuleValues.Auto };
        if (spaceAfter != null) spacing.After = spaceAfter;
        pp.Append(spacing);
        if (numId.HasValue)
            pp.Append(new NumberingProperties(new NumberingLevelReference { Val = 0 }, new NumberingId { Val = numId.Value }));
        var p = new Paragraph(pp);
        foreach (var r in runs) p.Append(r);
        return p;
    }

    static Table BuildTable(MdTable mt)
    {
        var single = new EnumValue<BorderValues>(BorderValues.Single);
        var borders = new TableBorders(
            new TopBorder { Val = single, Size = 4, Color = "000000" },
            new BottomBorder { Val = single, Size = 4, Color = "000000" },
            new LeftBorder { Val = single, Size = 4, Color = "000000" },
            new RightBorder { Val = single, Size = 4, Color = "000000" },
            new InsideHorizontalBorder { Val = single, Size = 4, Color = "000000" },
            new InsideVerticalBorder { Val = single, Size = 4, Color = "000000" });
        var table = new Table(new TableProperties(
            new TableWidth { Width = "5000", Type = TableWidthUnitValues.Pct },
            borders));
        foreach (var row in mt)
        {
            var mr = (MdTableRow)row;
            var tr = new TableRow();
            foreach (var cell in mr)
            {
                var mc = (MdTableCell)cell;
                var runs = new List<Run>();
                foreach (var blk in mc)
                    if (blk is ParagraphBlock pb)
                        runs.AddRange(InlineRuns(pb.Inline, SONG, BODY, mr.IsHeader).runs);
                if (runs.Count == 0) runs.Add(MakeRun("", SONG, BODY, false));
                tr.Append(new TableCell(
                    new TableCellProperties(new TableCellVerticalAlignment { Val = TableVerticalAlignmentValues.Center }),
                    Para(runs, JustificationValues.Left, "0")));
            }
            table.Append(tr);
        }
        return table;
    }

    static void Main(string[] args)
    {
        if (args.Length < 2) { Console.Error.WriteLine("用法: dotnet run -- <in.md> <out.docx>"); Environment.Exit(1); }
        var mdText = File.ReadAllText(args[0]);
        var pipeline = new MarkdownPipelineBuilder().UsePipeTables().Build();
        var docAst = Markdown.Parse(mdText, pipeline);

        var body = new Body();
        foreach (var block in docAst)
        {
            switch (block)
            {
                case HeadingBlock h:
                    var (hr, _) = InlineRuns(h.Inline, HEI, h.Level == 1 ? H1 : H2, true);
                    body.Append(Para(hr, h.Level == 1 ? JustificationValues.Center : JustificationValues.Left,
                        h.Level == 1 ? "360" : "120", "360"));
                    break;
                case ParagraphBlock p:
                    var (pr, hasBreak) = InlineRuns(p.Inline, SONG, BODY, false);
                    body.Append(Para(pr, hasBreak ? JustificationValues.Left : JustificationValues.Both));
                    break;
                case ListBlock lb:
                    bool ordered = lb.IsOrdered;
                    _numId++;
                    Lists.Add((_numId, ordered));
                    int thisNum = _numId;
                    foreach (var item in lb)
                    {
                        var runs = new List<Run>();
                        foreach (var sub in (ListItemBlock)item)
                            if (sub is ParagraphBlock ipb)
                                runs.AddRange(InlineRuns(ipb.Inline, SONG, BODY, false).runs);
                        if (runs.Count == 0) runs.Add(MakeRun("", SONG, BODY, false));
                        body.Append(Para(runs, JustificationValues.Both, "80", "340", thisNum));
                    }
                    break;
                case MdTable mt:
                    body.Append(BuildTable(mt));
                    break;
                case ThematicBreakBlock:
                    var hrPp = new ParagraphProperties(new ParagraphBorders(
                        new BottomBorder { Val = BorderValues.Single, Size = 6, Color = "888888", Space = 1 }));
                    hrPp.Append(new SpacingBetweenLines { After = "160", Before = "80" });
                    body.Append(new Paragraph(hrPp, MakeRun("", SONG, BODY, false)));
                    break;
            }
        }

        body.Append(new SectionProperties(
            new PageSize { Width = 11906, Height = 16838 },
            new PageMargin { Top = 1440, Bottom = 1440, Left = 1440, Right = 1440, Header = 720, Footer = 720 }));

        using var doc = WordprocessingDocument.Create(args[1], WordprocessingDocumentType.Document);
        var main = doc.AddMainDocumentPart();
        main.Document = new Document(body);

        var numPart = main.AddNewPart<NumberingDefinitionsPart>();
        var numbering = new Numbering();
        Level MakeLevel(bool ordered) => ordered
            ? new Level(new NumberingFormat { Val = NumberFormatValues.Decimal }, new LevelText { Val = "%1." },
                new LevelJustification { Val = LevelJustificationValues.Left },
                new PreviousParagraphProperties(new Indentation { Left = "480", Hanging = "300" })) { LevelIndex = 0 }
            : new Level(new NumberingFormat { Val = NumberFormatValues.Bullet }, new LevelText { Val = "•" },
                new LevelJustification { Val = LevelJustificationValues.Left },
                new PreviousParagraphProperties(new Indentation { Left = "480", Hanging = "300" })) { LevelIndex = 0 };
        numbering.Append(new AbstractNum(MakeLevel(true)) { AbstractNumberId = 0 });
        numbering.Append(new AbstractNum(MakeLevel(false)) { AbstractNumberId = 1 });
        foreach (var (numId, ordered) in Lists)
            numbering.Append(new NumberingInstance(new AbstractNumId { Val = ordered ? 0 : 1 },
                new LevelOverride(new StartOverrideNumberingValue { Val = 1 }) { LevelIndex = 0 }) { NumberID = numId });
        numPart.Numbering = numbering;

        var footerPart = main.AddNewPart<FooterPart>();
        var pageRun = new Run(RunProps(SONG, "20", false));
        pageRun.Append(new FieldChar { FieldCharType = FieldCharValues.Begin });
        var instr = new Run(RunProps(SONG, "20", false));
        instr.Append(new FieldCode(" PAGE ") { Space = SpaceProcessingModeValues.Preserve });
        var endRun = new Run(RunProps(SONG, "20", false));
        endRun.Append(new FieldChar { FieldCharType = FieldCharValues.End });
        footerPart.Footer = new Footer(new Paragraph(
            new ParagraphProperties(new Justification { Val = JustificationValues.Center }),
            pageRun, instr, endRun));
        var footerId = main.GetIdOfPart(footerPart);
        body.GetFirstChild<SectionProperties>()!.PrependChild(new FooterReference { Type = HeaderFooterValues.Default, Id = footerId });

        doc.Save();
        var fi = new FileInfo(args[1]);
        Console.WriteLine($"✅ {args[1]} ({fi.Length} 字节, {Lists.Count} 个列表)");
    }
}
