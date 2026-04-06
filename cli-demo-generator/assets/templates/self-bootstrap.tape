# Self-bootstrapping demo template
# Cleans previous state, sets up environment, records clean demo
#
# MARKETPLACE_REPO — replaced by recording script via sed
# BASE64_WRAPPER — base64-encoded output filter function
#   To create: echo 'my_func() { command my_func "$@" 2>&1 | grep -v "noise"; }' | base64

Output demo.gif
Set Theme "Catppuccin Latte"
Set FontSize 24
Set Width 1400
Set Height 600
Set Padding 20
Set TypingSpeed 10ms
Set Shell zsh

# Hidden bootstrap: cleanup + output filter + clear screen
Hide
Type "cleanup-command-here 2>/dev/null"
Enter
Sleep 3s
# Base64-encoded wrapper filters noisy output lines.
# VHS cannot parse shell special chars ($, \") in Type strings, so base64 is the workaround.
Type "echo BASE64_WRAPPER | base64 -d > /tmp/cw.sh && source /tmp/cw.sh"
Enter
Sleep 500ms
Type "clear"
Enter
Sleep 500ms
Show

# Stage 1: Setup
Type "setup-command MARKETPLACE_REPO"
Enter
Sleep 8s
Enter
Sleep 300ms

# Stage 2: Main action
Type "main-command"
Enter
Sleep 3s
Enter
Sleep 300ms

# Stage 3: Verify
Type "verify-command"
Enter
Sleep 2s

Sleep 1s
