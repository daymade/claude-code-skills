// Read-only comparison snapshot. Reject unresolved revision semantics before reading text.
#r "nuget: DocumentFormat.OpenXml, 3.2.0"

using System.Text;
using System.Text.Json;
using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;

if (Args.Count != 1)
{
    Console.Error.WriteLine("Usage: dotnet-script compare_snapshot.csx -- <docx_path>");
    Environment.Exit(2);
}

const string W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main";
var doc = WordprocessingDocument.Open(Args[0], false);
try
{
    var main = doc.MainDocumentPart;
    if (main == null || main.Document?.Body == null)
        throw new InvalidDataException("Missing main document body; comparison not performed.");

    var stories = new List<(string name, OpenXmlElement root)> { ("body", main.Document.Body) };
    foreach (var part in main.HeaderParts.OrderBy(p => p.Uri.ToString()))
        stories.Add(("header:" + part.Uri, part.Header));
    foreach (var part in main.FooterParts.OrderBy(p => p.Uri.ToString()))
        stories.Add(("footer:" + part.Uri, part.Footer));
    if (main.FootnotesPart?.Footnotes != null)
        stories.Add(("footnotes", main.FootnotesPart.Footnotes));
    if (main.EndnotesPart?.Endnotes != null)
        stories.Add(("endnotes", main.EndnotesPart.Endnotes));

    // Include property/table/paragraph-mark revisions, not just inline ins/del.
    var revisionNames = new HashSet<string> {
        "ins", "del", "delText", "delInstrText", "moveFrom", "moveTo",
        "cellIns", "cellDel", "cellMerge", "numberingChange", "conflictIns", "conflictDel"
    };
    var revisions = stories.SelectMany(s => s.root.Descendants()
        .Where(e => (e.NamespaceUri == W
            || e.NamespaceUri == "http://schemas.microsoft.com/office/word/2010/wordml")
            && (revisionNames.Contains(e.LocalName) || e.LocalName.EndsWith("Change")
            || e.LocalName.StartsWith("moveFromRange") || e.LocalName.StartsWith("moveToRange")
            || (e.LocalName.StartsWith("customXml") && e.LocalName.Contains("Range"))))
        .Select(e => s.name + ":" + e.LocalName)).ToList();
    if (revisions.Count > 0)
        throw new InvalidDataException("Unresolved revisions (" + revisions.Count + "): "
            + string.Join(", ", revisions.Distinct())
            + ". Comparison not performed; originals unchanged. Read extract_review first, then "
            + "materialize the confirmed accepted/rejected view on separate copies with a verified "
            + "revision-aware owner and compare those copies.");

    // Do not silently claim coverage of embedded documents, drawings or alternate XML branches.
    var unsupported = stories.SelectMany(s => s.root.Descendants()
        .Where(e => e.LocalName == "altChunk" || e.LocalName == "txbxContent"
            || e.LocalName == "AlternateContent" || e.LocalName == "drawing"
            || e.LocalName == "object" || e.LocalName == "pict" || e.LocalName == "sym")
        .Select(e => s.name + ":" + e.LocalName)).Distinct().ToList();

    string TextOf(OpenXmlElement root)
    {
        var text = new StringBuilder();
        foreach (var e in root.Descendants())
        {
            if (e is Text t) text.Append(t.Text);
            else if (e is TabChar) text.Append('\t');
            else if (e is Break || e is CarriageReturn) text.Append('\n');
            else if (e is FootnoteReference fr) text.Append("[footnote:" + fr.Id + "]");
            else if (e is EndnoteReference er) text.Append("[endnote:" + er.Id + "]");
            else if (e.LocalName == "noBreakHyphen") text.Append('\u2011');
            else if (e.LocalName == "softHyphen") text.Append('\u00ad');
        }
        return text.ToString();
    }

    var records = new List<object>();
    void Walk(OpenXmlElement root, string story, string path)
    {
        int p = 0, t = 0, other = 0;
        foreach (var child in root.ChildElements)
        {
            if (child is Paragraph paragraph)
            {
                string pp = path + "/p" + (++p);
                string text = TextOf(paragraph);
                // Blank body/note paragraphs are layout, not a textual change. Keep blank cells.
                if (!string.IsNullOrEmpty(text) || path.Contains("/table"))
                    records.Add(new { story, path = pp, kind = "paragraph", text });
            }
            else if (child is Table table)
            {
                string tp = path + "/table" + (++t);
                var rows = table.Elements<TableRow>().ToList();
                // Grid spans and vertical merges expose combined date cells even if text survives.
                string shape = string.Join(";", rows.Select(row => string.Join(",",
                    row.Elements<TableCell>().Select(cell => {
                        var props = cell.TableCellProperties;
                        return (props?.GridSpan?.Val?.Value ?? 1).ToString() + ":"
                            + (props?.VerticalMerge == null ? "none"
                                : props.VerticalMerge.Val?.InnerText ?? "continue");
                    }))));
                records.Add(new { story, path = tp, kind = "table_shape", text = shape });
                for (int ri = 0; ri < rows.Count; ri++)
                {
                    var cells = rows[ri].Elements<TableCell>().ToList();
                    for (int ci = 0; ci < cells.Count; ci++)
                        Walk(cells[ci], story, tp + "/row" + (ri + 1) + "/cell" + (ci + 1));
                }
            }
            else if (child.LocalName == "footnote" || child.LocalName == "endnote")
                Walk(child, story, path + "/note" + child.GetAttribute("id", W).Value);
            else if (child.HasChildren && child.LocalName != "sectPr"
                && child.LocalName != "tcPr" && child.LocalName != "trPr")
                Walk(child, story, path + "/" + child.LocalName + (++other));
        }
    }
    foreach (var story in stories) Walk(story.root, story.name, "");
    Console.WriteLine(JsonSerializer.Serialize(new { engine = "OpenXML SDK 3.2.0",
        revisionPolicy = "reject_unresolved", stories = stories.Select(s => s.name).ToList(),
        unsupported, records }));
}
finally { doc.Dispose(); }
