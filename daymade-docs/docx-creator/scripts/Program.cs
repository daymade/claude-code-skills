// 协议 markdown → 生产级中文合同 docx(minimax-docx OpenXML SDK + Markdig)
// 用法: dotnet run -- <input.md> <output.docx>
// CJK:宋体正文/黑体标题/RunFonts 双槽; 列表每条独立 NumId restart; 表格全边框;
// 信息块(含软换行)左对齐、正文两端对齐; A4 + 页脚页码。
using System.Linq;
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
    const string BODY = "21", H1 = "36", H2 = "28"; // half-points: 10.5/18/14pt（10.5pt = 中文书稿正文常用号）
    const string BODY_INDENT = "420";               // twips: 2 字符 × 10.5pt × 20（改 BODY 字号时必须同步改这里）

    static readonly List<(int numId, bool ordered)> Lists = new();
    static int _numId = 0;

    // CT_RPr 子元素顺序（ECMA-376）：rFonts, b, bCs, ..., color, spacing, w, kern, position, sz, szCs, ...
    // 顺序写错时 LibreOffice 照常渲染，真正的 Word 会判定 document.xml 不合规并触发自身修复/回退
    // 渲染（ISSUE-012）——所以这里的顺序不是风格问题，是正确性问题。
    static RunProperties RunProps(string font, string size, bool bold)
    {
        var rp = new RunProperties();
        // 中文加粗切黑体：宋体没有真粗体字重，渲染器只能算法合成，笔画多的汉字会粘连成一团
        // （实测多个三画以上的姓名在 LibreOffice 与 Word 下均糊）。中文排版惯例本就是「强调用黑体」
        // 而非「宋体加粗」。西文仍靠 Bold——Times New Roman 有真 Bold 字重，合成不了才需要换字族。
        var eastAsia = (bold && font == SONG) ? HEI : font;
        rp.Append(new RunFonts { Ascii = WEST, HighAnsi = WEST, EastAsia = eastAsia });
        if (bold) { rp.Append(new Bold()); rp.Append(new BoldComplexScript()); }
        rp.Append(new Color { Val = "000000" });
        rp.Append(new FontSize { Val = size });
        rp.Append(new FontSizeComplexScript { Val = size });
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

    // CT_PPrBase 子元素顺序：pStyle, keepNext, keepLines, pageBreakBefore, ..., numPr, ..., spacing, ind, ..., jc, ...
    static Paragraph Para(IEnumerable<Run> runs, JustificationValues just, string? spaceAfter = "120", string line = "360", int? numId = null, string? firstLineIndent = null)
    {
        var pp = new ParagraphProperties();
        if (numId.HasValue)
            pp.Append(new NumberingProperties(new NumberingLevelReference { Val = 0 }, new NumberingId { Val = numId.Value }));
        var spacing = new SpacingBetweenLines { Line = line, LineRule = LineSpacingRuleValues.Auto };
        if (spaceAfter != null) spacing.After = spaceAfter;
        pp.Append(spacing);
        // ind 必须落在 spacing 与 jc 之间（见上方 CT_PPrBase 顺序）。缩进只由调用方按块类型传入：
        // 标题、列表项、表格单元格都不缩进，含软换行的 info block 也不缩进（ISSUE-004 同源——
        // 它是一个多行段落，首行缩进只作用在第一行，反而把整块拉歪）。
        if (firstLineIndent != null) pp.Append(new Indentation { FirstLine = firstLineIndent });
        pp.Append(new Justification { Val = just });
        var p = new Paragraph(pp);
        foreach (var r in runs) p.Append(r);
        return p;
    }

    // CT_TblPrBase 顺序：tblW, ..., tblBorders, shd, tblLayout, ...；CT_TblBorders 顺序：top, left,
    // bottom, right, insideH, insideV。CT_Tbl 还要求 tblGrid 紧随 tblPr 之后且必须存在——此前完全没写
    // 这个元素，不是顺序问题而是结构性缺失（ISSUE-012）。
    static Table BuildTable(MdTable mt)
    {
        var single = new EnumValue<BorderValues>(BorderValues.Single);
        var borders = new TableBorders(
            new TopBorder { Val = single, Size = 4, Color = "000000" },
            new LeftBorder { Val = single, Size = 4, Color = "000000" },
            new BottomBorder { Val = single, Size = 4, Color = "000000" },
            new RightBorder { Val = single, Size = 4, Color = "000000" },
            new InsideHorizontalBorder { Val = single, Size = 4, Color = "000000" },
            new InsideVerticalBorder { Val = single, Size = 4, Color = "000000" });
        var table = new Table(new TableProperties(
            new TableWidth { Width = "5000", Type = TableWidthUnitValues.Pct },
            borders));
        var rows = mt.Cast<MdTableRow>().ToList();
        int colCount = rows.Count > 0 ? rows.Max(r => r.Cast<MdTableCell>().Count()) : 1;
        const int contentWidthDxa = 9026; // A4 减左右各 1440 twips 页边距
        var colWidth = (contentWidthDxa / Math.Max(1, colCount)).ToString();
        var grid = new TableGrid();
        for (int c = 0; c < colCount; c++) grid.Append(new GridColumn { Width = colWidth });
        table.Append(grid);
        foreach (var row in mt)
        {
            var mr = (MdTableRow)row;
            // 无表头信息表（md 语法被迫写 `| | |`）的全空 header 行不渲染——否则表顶多一条窄空行
            if (mr.IsHeader && mr.Cast<MdTableCell>().All(c =>
                    !c.Descendants<LiteralInline>().Any(l => !string.IsNullOrWhiteSpace(l.Content.ToString()))))
                continue;
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
                    body.Append(Para(pr, hasBreak ? JustificationValues.Left : JustificationValues.Both,
                        firstLineIndent: hasBreak ? null : BODY_INDENT));
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

        // 标准实践：补齐 styles.xml。它不是本条缺陷的根因（详见下面 settings.xml 的注释），
        // 但没有它包结构不完整，属于该补的卫生工作。
        var stylesPart = main.AddNewPart<StyleDefinitionsPart>();
        var styles = new Styles();
        var normalStyle = new Style { Type = StyleValues.Paragraph, StyleId = "Normal", Default = true };
        normalStyle.Append(new StyleName { Val = "Normal" }, new PrimaryStyle());
        styles.Append(normalStyle);
        var defaultCharStyle = new Style { Type = StyleValues.Character, StyleId = "DefaultParagraphFont", Default = true, CustomStyle = false };
        defaultCharStyle.Append(new StyleName { Val = "Default Paragraph Font" }, new UIPriority { Val = 1 }, new SemiHidden(), new UnhideWhenUsed());
        styles.Append(defaultCharStyle);
        var tableNormalStyle = new Style { Type = StyleValues.Table, StyleId = "TableNormal", Default = true, CustomStyle = false };
        tableNormalStyle.Append(new StyleName { Val = "Normal Table" }, new UIPriority { Val = 99 }, new SemiHidden(), new UnhideWhenUsed());
        styles.Append(tableNormalStyle);
        stylesPart.Styles = styles;

        // 真正的根因（ISSUE-012，2026-08-12 用 Microsoft Word.app 实测锁定）：缺 settings.xml 里的
        // compatibilityMode 声明时，Word 标题栏会显示"兼容模式"打开本文档——兼容模式套用旧版 Word 的
        // 默认渲染规则，会产生看似无关的格式错乱（如项目符号泛滥）。LibreOffice 不受此影响、照常渲染
        // 干净，所以只靠 LibreOffice 视觉验证发现不了这条（ISSUE-008 已经指出 qlmanage vs LibreOffice
        // 会漏同类问题，这里是同一个教训在 LibreOffice vs 真实 Word 这一层再次出现）。
        var settingsPart = main.AddNewPart<DocumentSettingsPart>();
        settingsPart.Settings = new Settings(
            new Compatibility(
                new CompatibilitySetting { Name = new EnumValue<CompatSettingNameValues>(CompatSettingNameValues.CompatibilityMode), Uri = "http://schemas.microsoft.com/office/word", Val = "15" }));

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
