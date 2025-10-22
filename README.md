# Claude Code Skills Marketplace

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Skills](https://img.shields.io/badge/skills-6-blue.svg)](https://github.com/daymade/claude-code-skills)
[![Version](https://img.shields.io/badge/version-1.0.0-green.svg)](https://github.com/daymade/claude-code-skills)

Professional Claude Code skills marketplace featuring 6 production-ready skills for enhanced development workflows.

## 🚀 Quick Start

### Installation

Add this marketplace to Claude Code:

```bash
/plugin marketplace add daymade/claude-code-skills
```

Then install the productivity skills bundle:

```bash
/plugin install productivity-skills
```

All 6 skills will be automatically available in your Claude Code session!

## 📦 Included Skills

### 1. **github-ops** - GitHub Operations Suite

Comprehensive GitHub operations using gh CLI and GitHub API.

**When to use:**
- Creating, viewing, or managing pull requests
- Managing issues and repository settings
- Querying GitHub API endpoints
- Working with GitHub Actions workflows
- Automating GitHub operations

**Key features:**
- PR creation with JIRA integration
- Issue management workflows
- GitHub API (REST & GraphQL) operations
- Workflow automation
- Enterprise GitHub support

---

### 2. **markdown-tools** - Document Conversion Suite

Converts documents to markdown with Windows/WSL path handling and Obsidian integration.

**When to use:**
- Converting .doc/.docx/PDF/PPTX to markdown
- Processing Confluence exports
- Handling Windows/WSL path conversions
- Working with markitdown utility

**Key features:**
- Multi-format document conversion
- Confluence export processing
- Windows/WSL path automation
- Obsidian vault integration
- Helper scripts for path conversion

---

### 3. **mermaid-tools** - Diagram Generation

Extracts Mermaid diagrams from markdown and generates high-quality PNG images.

**When to use:**
- Converting Mermaid diagrams to PNG
- Extracting diagrams from markdown files
- Processing documentation with embedded diagrams
- Creating presentation-ready visuals

**Key features:**
- Automatic diagram extraction
- High-resolution PNG generation
- Smart sizing based on diagram type
- Customizable dimensions and scaling
- WSL2 Chrome/Puppeteer support

---

### 4. **statusline-generator** - Statusline Customization

Configures Claude Code statuslines with multi-line layouts and cost tracking.

**When to use:**
- Customizing Claude Code statusline
- Adding cost tracking (session/daily)
- Displaying git status
- Multi-line layouts for narrow screens
- Color customization

**Key features:**
- Multi-line statusline layouts
- ccusage cost integration
- Git branch status indicators
- Customizable colors
- Portrait screen optimization

---

### 5. **teams-channel-post-writer** - Teams Communication

Creates educational Teams channel posts for internal knowledge sharing.

**When to use:**
- Writing Teams posts about features
- Sharing Claude Code best practices
- Documenting lessons learned
- Creating internal announcements
- Teaching effective prompting patterns

**Key features:**
- Post templates with proven structure
- Writing guidelines for quality content
- "Normal vs Better" example patterns
- Emphasis on underlying principles
- Ready-to-use markdown templates

---

### 6. **repomix-unmixer** - Repository Extraction

Extracts files from repomix-packed repositories and restores directory structures.

**When to use:**
- Unmixing repomix output files
- Extracting packed repositories
- Restoring file structures
- Reviewing repomix content
- Converting repomix to usable files

**Key features:**
- Multi-format support (XML, Markdown, JSON)
- Auto-format detection
- Directory structure preservation
- UTF-8 encoding support
- Comprehensive validation workflows

## 🎯 Use Cases

### For GitHub Workflows
Use **github-ops** to streamline PR creation, issue management, and API operations.

### For Documentation
Combine **markdown-tools** for document conversion and **mermaid-tools** for diagram generation to create comprehensive documentation.

### For Team Communication
Use **teams-channel-post-writer** to share knowledge and **statusline-generator** to track costs while working.

### For Repository Management
Use **repomix-unmixer** to extract and validate repomix-packed skills or repositories.

## 📚 Documentation

Each skill includes:
- **SKILL.md**: Core instructions and workflows
- **scripts/**: Executable utilities (Python/Bash)
- **references/**: Detailed documentation
- **assets/**: Templates and resources (where applicable)

### Quick Links

- **github-ops**: See `github-ops/references/api_reference.md` for API documentation
- **markdown-tools**: See `markdown-tools/references/conversion-examples.md` for conversion scenarios
- **mermaid-tools**: See `mermaid-tools/references/setup_and_troubleshooting.md` for setup guide
- **statusline-generator**: See `statusline-generator/references/color_codes.md` for customization
- **teams-channel-post-writer**: See `teams-channel-post-writer/references/writing-guidelines.md` for quality standards
- **repomix-unmixer**: See `repomix-unmixer/references/repomix-format.md` for format specifications

## 🛠️ Requirements

- **Claude Code** 2.0.13 or higher
- **Python 3.6+** (for scripts in multiple skills)
- **gh CLI** (for github-ops)
- **markitdown** (for markdown-tools)
- **mermaid-cli** (for mermaid-tools)
- **ccusage** (optional, for statusline cost tracking)

## 🤝 Contributing

Contributions are welcome! Please feel free to:

1. Open issues for bugs or feature requests
2. Submit pull requests with improvements
3. Share feedback on skill quality

### Skill Quality Standards

All skills in this marketplace follow:
- Imperative/infinitive writing style
- Progressive disclosure pattern
- Proper resource organization
- Comprehensive documentation
- Tested and validated

## 📄 License

This marketplace is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⭐ Support

If you find these skills useful, please:
- ⭐ Star this repository
- 🐛 Report issues
- 💡 Suggest improvements
- 📢 Share with your team

## 🔗 Related Resources

- [Claude Code Documentation](https://docs.claude.com/en/docs/claude-code)
- [Agent Skills Guide](https://docs.claude.com/en/docs/claude-code/skills)
- [Plugin Marketplaces](https://docs.claude.com/en/docs/claude-code/plugin-marketplaces)
- [Anthropic Skills Repository](https://github.com/anthropics/skills)

## 📞 Contact

- **GitHub**: [@daymade](https://github.com/daymade)
- **Email**: daymadev89@gmail.com
- **Repository**: [daymade/claude-code-skills](https://github.com/daymade/claude-code-skills)

---

**Built with ❤️ using the skill-creator skill for Claude Code**

Last updated: 2025-10-22 | Version 1.0.0
