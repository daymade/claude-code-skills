#!/usr/bin/env pwsh
# Cross-platform PowerShell installer for Claude Code Skills

& {
# Color output functions
function Write-Success { Write-Host $args -ForegroundColor Green }
function Write-Failure { Write-Host $args -ForegroundColor Red }
function Write-Info { Write-Host $args -ForegroundColor Yellow }
function Write-Cyan { Write-Host $args -ForegroundColor Cyan }

# Registered plugin IDs from .claude-plugin/marketplace.json.
$plugins = @(
    @{ Name = "daymade-skill"; Description = "bundles skill-creator and friends" }
    @{ Name = "github-ops"; Description = "GitHub operations" }
    @{ Name = "daymade-docs"; Description = "document conversion and Mermaid diagrams" }
    @{ Name = "daymade-claude-code"; Description = "Claude Code tools and statusline customization" }
    @{ Name = "teams-channel-post-writer"; Description = "Teams communication" }
    @{ Name = "repomix-unmixer"; Description = "repomix extraction" }
    @{ Name = "llm-icon-finder"; Description = "AI/LLM icons" }
)

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Claude Code Skills Marketplace Installer" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Detect platform
if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
    $Platform = "Windows"
} elseif (Get-Variable IsMacOS -ValueOnly -ErrorAction SilentlyContinue) {
    $Platform = "macOS"
} elseif (Get-Variable IsLinux -ValueOnly -ErrorAction SilentlyContinue) {
    $Platform = "Linux"
} else {
    $Platform = "Unknown"
}

Write-Host "Detected Platform: $Platform"
Write-Host ""

# Check if Claude Code is available (simplified check)
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Failure "Warning: Claude Code command not found in PATH!"
    Write-Host "Please ensure Claude Code is installed: https://claude.com/code"
    Write-Host ""
    $continue = Read-Host "Continue anyway? (y/n)"
    if ($continue -ne 'y') {
        throw "Claude Code is unavailable; installation commands were not generated."
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
    Write-Host "1) daymade-skill only (RECOMMENDED - bundles skill-creator and friends)"
    Write-Host "2) Featured plugins"
    Write-Host "3) Custom selection"
    Write-Host "4) Exit"
    Write-Host ""
    $choice = Read-Host "Enter your choice (1-4)"
} else {
    Write-Info "Running in non-interactive mode."
    Write-Host "Defaulting to option 1: daymade-skill only (RECOMMENDED)"
    Write-Host ""
    Write-Host "To run interactively, download and run directly:"
    Write-Host "  & { Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/daymade/claude-code-skills/main/scripts/install.ps1' -OutFile install.ps1 -ErrorAction Stop; & .\install.ps1 }"
    Write-Host ""
    $choice = "1"
}

$commands = @()
$commands += "claude plugin marketplace add https://github.com/daymade/claude-code-skills"
$afterInstall = $null

switch ($choice) {
    "1" {
        Write-Host ""
        Write-Cyan "Generating commands for daymade-skill (bundles skill-creator)..."
        Write-Host ""
        $commands += "claude plugin install $($plugins[0].Name)@daymade-skills"

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
        Write-Cyan "Generating commands for featured plugins..."
        Write-Host ""
        foreach ($plugin in $plugins) {
            $commands += "claude plugin install $($plugin.Name)@daymade-skills"
        }
    }
    "3" {
        Write-Host ""
        Write-Host "Available plugins:"
        for ($index = 0; $index -lt $plugins.Count; $index++) {
            Write-Host "  $($index + 1)) $($plugins[$index].Name) ($($plugins[$index].Description))"
        }
        Write-Host ""

        if ($isInteractive) {
            $selectionText = Read-Host "Enter plugin numbers separated by spaces (e.g., '1 2 3')"
        } else {
            Write-Info "Non-interactive mode: Selecting daymade-skill only"
            $selectionText = "1"
        }

        # Validate the whole list before printing any installation commands.
        if ($selectionText -notmatch '\A\s*[0-9]+(?:\s+[0-9]+)*\s*\z') {
            throw "Invalid plugin selection! Enter numbers from 1 to $($plugins.Count)."
        }
        $selections = [regex]::Split($selectionText.Trim(), '\s+')
        foreach ($num in $selections) {
            $normalized = $num.TrimStart([char]'0')
            if ($normalized.Length -eq 0 -or $normalized.Length -gt ([string]$plugins.Count).Length) {
                throw "Invalid plugin selection! Enter numbers from 1 to $($plugins.Count)."
            }
            $index = 0
            if (-not [int]::TryParse($normalized, [ref]$index) -or $index -lt 1 -or $index -gt $plugins.Count) {
                throw "Invalid plugin selection! Enter numbers from 1 to $($plugins.Count)."
            }
            $commands += "claude plugin install $($plugins[$index - 1].Name)@daymade-skills"
        }
    }
    "4" {
        Write-Host "Installation cancelled."
        return
    }
    default {
        throw "Invalid choice!"
    }
}

Write-Host ""
Write-Success "================================================"
Write-Success "Installation commands generated!"
Write-Success "================================================"
Write-Host ""
Write-Host "RUN IN TERMINAL:" -ForegroundColor Cyan
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
Write-Host "2. Paste them into your terminal"
Write-Host "3. Restart Claude Code"
Write-Host "4. Start using your skills!"
Write-Host ""
Write-Host "Documentation: https://github.com/daymade/claude-code-skills"
Write-Host ""
}
