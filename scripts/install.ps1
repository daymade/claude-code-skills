#!/usr/bin/env pwsh
# Cross-platform PowerShell installer for Claude Code Skills

# Color output functions
function Write-Success { Write-Host $args -ForegroundColor Green }
function Write-Error { Write-Host $args -ForegroundColor Red }
function Write-Info { Write-Host $args -ForegroundColor Yellow }
function Write-Cyan { Write-Host $args -ForegroundColor Cyan }

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Claude Code Skills Marketplace Installer" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Detect platform
if ($IsWindows -or $env:OS -eq "Windows_NT") {
    $Platform = "Windows"
} elseif ($IsMacOS) {
    $Platform = "macOS"
} elseif ($IsLinux) {
    $Platform = "Linux"
} else {
    $Platform = "Unknown"
}

Write-Host "Detected Platform: $Platform"
Write-Host ""

# Check if Claude Code is available (simplified check)
$claudeInstalled = $true
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Error "Warning: Claude Code command not found in PATH!"
    Write-Host "Please ensure Claude Code is installed: https://claude.com/code"
    Write-Host ""
    $continue = Read-Host "Continue anyway? (y/n)"
    if ($continue -ne 'y') {
        exit 1
    }
} else {
    Write-Success "✓ Claude Code detected"
    Write-Host ""
}

# Check if running interactively
$isInteractive = [Environment]::UserInteractive -and -not [Console]::IsInputRedirected

if ($isInteractive) {
    # Installation menu
    Write-Host "What would you like to install?"
    Write-Host ""
    Write-Host "1) skill-creator only (RECOMMENDED - enables you to create your own skills)"
    Write-Host "2) All skills"
    Write-Host "3) Custom selection"
    Write-Host "4) Exit"
    Write-Host ""
    $choice = Read-Host "Enter your choice (1-4)"
} else {
    Write-Info "Running in non-interactive mode."
    Write-Host "Defaulting to option 1: skill-creator only (RECOMMENDED)"
    Write-Host ""
    Write-Host "To run interactively, download and run directly:"
    Write-Host "  Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/daymade/claude-code-skills/main/scripts/install.ps1' -OutFile install.ps1"
    Write-Host "  .\install.ps1"
    Write-Host ""
    $choice = "1"
}

$commands = @()
$commands += "claude plugin marketplace add https://github.com/daymade/claude-code-skills"

switch ($choice) {
    "1" {
        Write-Host ""
        Write-Cyan "Installing skill-creator..."
        Write-Host ""
        $commands += "claude plugin install skill-creator@daymade-skills"

        $afterInstall = @"
After installation, ask Claude Code:
  "Create a new skill called my-awesome-skill in ~/my-skills"
  "Validate my skill at ~/my-skills/my-awesome-skill"
  "Package my skill at ~/my-skills/my-awesome-skill"

Claude Code will guide you through the skill creation process!
"@
    }
    "2" {
        Write-Host ""
        Write-Cyan "Installing all skills..."
        Write-Host ""
        $skills = @("skill-creator", "github-ops", "markdown-tools", "mermaid-tools",
                    "statusline-generator", "teams-channel-post-writer", "repomix-unmixer", "llm-icon-finder")
        foreach ($skill in $skills) {
            $commands += "claude plugin install $skill@daymade-skills"
        }
    }
    "3" {
        Write-Host ""
        Write-Host "Available skills:"
        Write-Host "  1) skill-creator (meta-skill for creating skills)"
        Write-Host "  2) github-ops (GitHub operations)"
        Write-Host "  3) markdown-tools (document conversion)"
        Write-Host "  4) mermaid-tools (diagram generation)"
        Write-Host "  5) statusline-generator (statusline customization)"
        Write-Host "  6) teams-channel-post-writer (Teams communication)"
        Write-Host "  7) repomix-unmixer (repomix extraction)"
        Write-Host "  8) llm-icon-finder (AI/LLM icons)"
        Write-Host ""

        if ($isInteractive) {
            $selections = (Read-Host "Enter skill numbers separated by spaces (e.g., '1 2 3')").Split(' ')
        } else {
            Write-Info "Non-interactive mode: Installing skill-creator only"
            $selections = @("1")
        }

        $skillMap = @{
            "1" = "skill-creator"
            "2" = "github-ops"
            "3" = "markdown-tools"
            "4" = "mermaid-tools"
            "5" = "statusline-generator"
            "6" = "teams-channel-post-writer"
            "7" = "repomix-unmixer"
            "8" = "llm-icon-finder"
        }

        foreach ($num in $selections) {
            if ($skillMap.ContainsKey($num)) {
                $commands += "claude plugin install $($skillMap[$num])@daymade-skills"
            }
        }
    }
    "4" {
        Write-Host "Installation cancelled."
        exit 0
    }
    default {
        Write-Error "Invalid choice!"
        exit 1
    }
}

Write-Host ""
Write-Success "================================================"
Write-Success "Installation commands generated!"
Write-Success "================================================"
Write-Host ""
Write-Host "Run these commands in Claude Code:" -ForegroundColor Cyan
Write-Host ""
foreach ($cmd in $commands) {
    Write-Info $cmd
}

if ($afterInstall) {
    Write-Host ""
    Write-Success $afterInstall
}

Write-Host ""
Write-Host "Next steps:" -ForegroundColor Green
Write-Host "1. Copy the commands above"
Write-Host "2. Paste them into Claude Code"
Write-Host "3. Restart Claude Code"
Write-Host "4. Start using your skills!"
Write-Host ""
Write-Host "Documentation: https://github.com/daymade/claude-code-skills"
Write-Host ""
