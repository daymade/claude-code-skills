Output demos/github-ops/create-pr.gif

Set FontSize 16
Set Width 1400
Set Height 700
Set Theme "Dracula"
Set Padding 20

Type "# GitHub Ops Demo: Create Pull Request" Sleep 500ms Enter
Sleep 1s

Type "# Create a PR with NOJIRA prefix (bypasses JIRA checks)" Sleep 500ms Enter
Type 'gh pr create --title "NOJIRA: Add user authentication" --body "Implements OAuth2 login"' Sleep 500ms
Enter
Sleep 3s

Type@500ms "" Enter
Type "# PR created successfully!" Sleep 500ms Enter
Type "# View it: gh pr view 123" Sleep 500ms Enter
Sleep 2s

Type@500ms "" Enter
Type "# Other operations:" Sleep 500ms Enter
Type "# - Approve: gh pr review 123 --approve" Sleep 300ms Enter
Type "# - Merge: gh pr merge 123 --squash" Sleep 300ms Enter
Type "# - Comment: gh pr comment 123 --body 'LGTM'" Sleep 300ms Enter
Sleep 2s
