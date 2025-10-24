Output demos/teams-channel-post-writer/write-post.gif

Set FontSize 16
Set Width 1400
Set Height 700
Set Theme "Dracula"
Set Padding 20

Type "# Teams Channel Post Writer Demo" Sleep 500ms Enter
Sleep 1s

Type "# Create a professional Teams post about a new feature" Sleep 500ms Enter
Sleep 1s

Type@500ms "" Enter
Type "# Using the post template:" Sleep 500ms Enter
Type "cat teams-channel-post-writer/assets/post-template.md" Sleep 500ms
Enter
Sleep 2s

Type@500ms "" Enter
Type "# Example: Announcing Claude Code Skills" Sleep 500ms Enter
Type 'echo "## 🚀 New: Claude Code Skills Marketplace" > post.md' Sleep 300ms Enter
Type 'echo "" >> post.md' Sleep 300ms Enter
Type 'echo "### What Changed" >> post.md' Sleep 300ms Enter
Type 'echo "- ✅ 8 production-ready skills available" >> post.md' Sleep 300ms Enter
Type 'echo "- ✅ Automated installation scripts" >> post.md' Sleep 300ms Enter
Sleep 2s

Type@500ms "" Enter
Type "# Post ready for Teams channel!" Sleep 500ms Enter
Sleep 2s
