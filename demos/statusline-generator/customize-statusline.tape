Output demos/statusline-generator/customize-statusline.gif

Set FontSize 16
Set Width 1400
Set Height 700
Set Theme "Dracula"
Set Padding 20

Type "# Statusline Generator Demo: Customize Claude Code" Sleep 500ms Enter
Sleep 1s

Type "# Configure multi-line statusline with cost tracking" Sleep 500ms Enter
Type "# Example statusline configuration:" Sleep 500ms Enter
Sleep 1s

Type@500ms "" Enter
Type 'echo "statusline:" > ~/.claude/config.yaml' Sleep 300ms Enter
Type 'echo "  format: |" >> ~/.claude/config.yaml' Sleep 300ms Enter
Type 'echo "    Line 1: {git_branch} | {session_cost}" >> ~/.claude/config.yaml' Sleep 300ms Enter
Type 'echo "    Line 2: Daily: {daily_cost} | {timestamp}" >> ~/.claude/config.yaml' Sleep 300ms Enter
Sleep 2s

Type@500ms "" Enter
Type "# Features:" Sleep 500ms Enter
Type "# ✓ Multi-line layouts" Sleep 300ms Enter
Type "# ✓ Cost tracking via ccusage" Sleep 300ms Enter
Type "# ✓ Git branch status" Sleep 300ms Enter
Type "# ✓ Customizable colors" Sleep 300ms Enter
Sleep 2s

Type@500ms "" Enter
Type "# Restart Claude Code to see your custom statusline!" Sleep 500ms Enter
Sleep 2s
