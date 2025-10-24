Output demos/skill-creator/validate-skill.gif

Set FontSize 16
Set Width 1400
Set Height 700
Set Theme "Dracula"
Set Padding 20

Type "# Skill Creator Demo: Validate Your Skill" Sleep 500ms Enter
Sleep 1s

Type "# Run validation on your skill" Sleep 500ms Enter
Type "skill-creator/scripts/quick_validate.py ~/demo-skills/awesome-translator" Sleep 500ms
Enter
Sleep 3s

Type@500ms "" Enter
Type "# Validation checks:" Sleep 500ms Enter
Type "# ✓ YAML frontmatter format" Sleep 300ms Enter
Type "# ✓ Required fields (name, description)" Sleep 300ms Enter
Type "# ✓ File organization" Sleep 300ms Enter
Type "# ✓ Resource references" Sleep 300ms Enter
Sleep 2s

Type@500ms "" Enter
Type "# All checks passed! ✓" Sleep 500ms Enter
Sleep 2s
