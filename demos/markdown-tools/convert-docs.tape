Output demos/markdown-tools/convert-docs.gif

Set FontSize 16
Set Width 1400
Set Height 700
Set Theme "Dracula"
Set Padding 20

Type "# Markdown Tools Demo: Convert Documents" Sleep 500ms Enter
Sleep 1s

Type "# Convert Word document to Markdown" Sleep 500ms Enter
Type "markitdown project-spec.docx > project-spec.md" Sleep 500ms
Enter
Sleep 2s

Type@500ms "" Enter
Type "# Convert PDF to Markdown" Sleep 500ms Enter
Type "markitdown research-paper.pdf > research-paper.md" Sleep 500ms
Enter
Sleep 2s

Type@500ms "" Enter
Type "# Converted files ready for Obsidian/Git!" Sleep 500ms Enter
Type "ls -lh *.md" Sleep 500ms
Enter
Sleep 2s
