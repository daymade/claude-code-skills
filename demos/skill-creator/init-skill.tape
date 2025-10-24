Output demos/skill-creator/init-skill.gif

Set FontSize 16
Set Width 1400
Set Height 700
Set Theme "Dracula"
Set Padding 20

Type "# Skill Creator Demo: Initialize a New Skill" Sleep 500ms Enter
Sleep 1s

Type "# Step 1: Initialize skill from template" Sleep 500ms Enter
Type "skill-creator/scripts/init_skill.py awesome-translator --path ~/demo-skills" Sleep 500ms
Enter
Sleep 3s

Type@500ms "# Step 2: View generated structure" Sleep 500ms Enter
Type "tree ~/demo-skills/awesome-translator -L 2" Sleep 500ms
Enter
Sleep 2s

Type@500ms "" Enter
Type "# Step 3: Generated files ready to customize!" Sleep 500ms Enter
Type "ls -la ~/demo-skills/awesome-translator/" Sleep 500ms
Enter
Sleep 2s

Type@500ms "" Enter
Type "# Next: Edit SKILL.md, add your logic, and validate!" Sleep 500ms Enter
Sleep 2s
