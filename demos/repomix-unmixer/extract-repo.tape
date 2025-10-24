Output demos/repomix-unmixer/extract-repo.gif

Set FontSize 16
Set Width 1400
Set Height 700
Set Theme "Dracula"
Set Padding 20

Type "# Repomix Unmixer Demo: Extract Packed Repository" Sleep 500ms Enter
Sleep 1s

Type "# Extract files from repomix output" Sleep 500ms Enter
Type "repomix-unmixer/scripts/unmix_repomix.py packed-repo.xml --output ./extracted" Sleep 500ms
Enter
Sleep 3s

Type@500ms "" Enter
Type "# Extraction complete!" Sleep 500ms Enter
Type "tree ./extracted -L 2" Sleep 500ms
Enter
Sleep 2s

Type@500ms "" Enter
Type "# Features:" Sleep 500ms Enter
Type "# ✓ Multi-format support (XML, Markdown, JSON)" Sleep 300ms Enter
Type "# ✓ Auto-format detection" Sleep 300ms Enter
Type "# ✓ Directory structure preserved" Sleep 300ms Enter
Type "# ✓ UTF-8 encoding support" Sleep 300ms Enter
Sleep 2s

Type@500ms "" Enter
Type "# Repository ready to use!" Sleep 500ms Enter
Sleep 2s
