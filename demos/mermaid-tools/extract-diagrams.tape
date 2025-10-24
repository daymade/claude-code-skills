Output demos/mermaid-tools/extract-diagrams.gif

Set FontSize 16
Set Width 1400
Set Height 700
Set Theme "Dracula"
Set Padding 20

Type "# Mermaid Tools Demo: Extract and Generate Diagrams" Sleep 500ms Enter
Sleep 1s

Type "# Step 1: Extract Mermaid diagrams from markdown" Sleep 500ms Enter
Type "mermaid-tools/scripts/extract_diagrams.py architecture.md" Sleep 500ms
Enter
Sleep 2s

Type@500ms "" Enter
Type "# Extracted diagrams saved to:" Sleep 500ms Enter
Type "ls -lh architecture-*.mmd" Sleep 500ms
Enter
Sleep 2s

Type@500ms "" Enter
Type "# Step 2: Generate PNG from Mermaid diagram" Sleep 500ms Enter
Type "mmdc -i architecture-flowchart.mmd -o flowchart.png" Sleep 500ms
Enter
Sleep 2s

Type@500ms "" Enter
Type "# High-quality PNG diagram ready!" Sleep 500ms Enter
Type "open flowchart.png" Sleep 300ms
Enter
Sleep 2s
