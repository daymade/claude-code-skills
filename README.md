# Claude Code Skills Marketplace

<div align="center">

[![English](https://img.shields.io/badge/Language-English-blue)](./README.md)
[![简体中文](https://img.shields.io/badge/语言-简体中文-red)](./README.zh-CN.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Skills](https://img.shields.io/badge/skills-13-blue.svg)](https://github.com/daymade/claude-code-skills)
[![Version](https://img.shields.io/badge/version-1.6.0-green.svg)](https://github.com/daymade/claude-code-skills)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-2.0.13+-purple.svg)](https://claude.com/code)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](./CONTRIBUTING.md)
[![Maintenance](https://img.shields.io/badge/Maintained%3F-yes-green.svg)](https://github.com/daymade/claude-code-skills/graphs/commit-activity)

</div>

Professional Claude Code skills marketplace featuring 13 production-ready skills for enhanced development workflows.

## 📑 Table of Contents

- [🌟 Essential Skill: skill-creator](#-essential-skill-skill-creator)
- [🚀 Quick Installation](#-quick-installation)
- [🇨🇳 Chinese User Guide](#-chinese-user-guide)
- [📦 Other Available Skills](#-other-available-skills)
- [🎬 Interactive Demo Gallery](#-interactive-demo-gallery)
- [🎯 Use Cases](#-use-cases)
- [📚 Documentation](#-documentation)
- [🛠️ Requirements](#️-requirements)
- [❓ FAQ](#-faq)
- [🤝 Contributing](#-contributing)
- [📄 License](#-license)

---

## 🌟 Essential Skill: skill-creator

**⭐ Start here if you want to create your own skills!**

The `skill-creator` is the **meta-skill** that enables you to build, validate, and package your own Claude Code skills. It's the most important tool in this marketplace because it empowers you to extend Claude Code with your own specialized workflows.

### Why skill-creator First?

- **🎯 Foundation**: Learn how skills work by creating your own
- **🛠️ Complete Toolkit**: Initialization, validation, and packaging scripts included
- **📖 Best Practices**: Learn from production-ready examples
- **🚀 Quick Start**: Generate skill templates in seconds
- **✅ Quality Assurance**: Built-in validation ensures your skills meet standards

### Quick Install

```bash
claude plugin marketplace add daymade/claude-code-skills
claude plugin install skill-creator@daymade/claude-code-skills
```

### What You Can Do

After installing skill-creator, simply ask Claude Code:

```
"Create a new skill called my-awesome-skill in ~/my-skills"

"Validate my skill at ~/my-skills/my-awesome-skill"

"Package my skill at ~/my-skills/my-awesome-skill for distribution"
```

Claude Code, with skill-creator loaded, will guide you through the entire skill creation process - from understanding your requirements to packaging the final skill.

📚 **Full documentation**: [skill-creator/SKILL.md](./skill-creator/SKILL.md)

### Live Demos

**📝 Initialize New Skill**

![Initialize Skill Demo](./demos/skill-creator/init-skill.gif)

**✅ Validate Skill Structure**

![Validate Skill Demo](./demos/skill-creator/validate-skill.gif)

**📦 Package Skill for Distribution**

![Package Skill Demo](./demos/skill-creator/package-skill.gif)

---

## 🚀 Quick Installation

### Automated Installation (Recommended)

**macOS/Linux:**
```bash
curl -fsSL https://raw.githubusercontent.com/daymade/claude-code-skills/main/scripts/install.sh | bash
```

**Windows (PowerShell):**
```powershell
iwr -useb https://raw.githubusercontent.com/daymade/claude-code-skills/main/scripts/install.ps1 | iex
```

### Manual Installation

Add the marketplace:
```bash
/plugin marketplace add daymade/claude-code-skills
```

**Essential Skill** (recommended first install):
```bash
claude plugin install skill-creator@daymade/claude-code-skills
```

**Install Other Skills:**
```bash
# GitHub operations
claude plugin install github-ops@daymade/claude-code-skills

# Document conversion
claude plugin install markdown-tools@daymade/claude-code-skills

# Diagram generation
claude plugin install mermaid-tools@daymade/claude-code-skills

# Statusline customization
claude plugin install statusline-generator@daymade/claude-code-skills

# Teams communication
claude plugin install teams-channel-post-writer@daymade/claude-code-skills

# Repomix extraction
claude plugin install repomix-unmixer@daymade/claude-code-skills

# AI/LLM icons
claude plugin install llm-icon-finder@daymade/claude-code-skills

# CLI demo generation
claude plugin install cli-demo-generator@daymade/claude-code-skills

# YouTube video/audio downloading
claude plugin install youtube-downloader@daymade/claude-code-skills
```

Each skill can be installed independently - choose only what you need!

---

## 🇨🇳 Chinese User Guide

**For Chinese users:** We highly recommend using [CC-Switch](https://github.com/farion1231/cc-switch) to manage Claude Code API provider configurations.

CC-Switch enables you to:
- ✅ Quickly switch between different API providers (DeepSeek, Qwen, GLM, etc.)
- ✅ Test endpoint response times to find the fastest provider
- ✅ Manage MCP server configurations
- ✅ Auto-backup and import/export settings
- ✅ Cross-platform support (Windows, macOS, Linux)

**Setup:** Download from [Releases](https://github.com/farion1231/cc-switch/releases), install, add your API configs, and switch via UI or system tray.

### Complete Chinese Documentation

For full documentation in Chinese, see [README.zh-CN.md](./README.zh-CN.md).

---

## 📦 Other Available Skills

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

**🎬 Live Demo**

![GitHub Ops Demo](./demos/github-ops/create-pr.gif)

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

**🎬 Live Demo**

![Markdown Tools Demo](./demos/markdown-tools/convert-docs.gif)

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

**🎬 Live Demo**

![Mermaid Tools Demo](./demos/mermaid-tools/extract-diagrams.gif)

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

**🎬 Live Demo**

![Statusline Generator Demo](./demos/statusline-generator/customize-statusline.gif)

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

**🎬 Live Demo**

![Teams Channel Post Writer Demo](./demos/teams-channel-post-writer/write-post.gif)

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

**🎬 Live Demo**

![Repomix Unmixer Demo](./demos/repomix-unmixer/extract-repo.gif)

---

### 7. **llm-icon-finder** - AI/LLM Brand Icon Finder

Access 100+ AI model and LLM provider brand icons from lobe-icons library.

**When to use:**
- Finding brand icons for AI models/providers
- Downloading logos for Claude, GPT, Gemini, etc.
- Getting icons in multiple formats (SVG/PNG/WEBP)
- Building AI tool documentation
- Creating presentations about LLMs

**Key features:**
- 100+ AI/LLM model icons
- Multiple format support (SVG, PNG, WEBP)
- URL generation for direct access
- Local download capabilities
- Searchable icon catalog

**🎬 Live Demo**

![LLM Icon Finder Demo](./demos/llm-icon-finder/find-icons.gif)

---

### 8. **cli-demo-generator** - CLI Demo Generation

Generate professional animated CLI demos and terminal recordings with VHS automation.

**When to use:**
- Creating demos for documentation
- Recording terminal workflows as GIFs
- Generating animated tutorials
- Batch-generating multiple demos
- Showcasing CLI tools

**Key features:**
- Automated demo generation from command lists
- Batch processing with YAML/JSON configs
- Interactive recording with asciinema
- Smart timing based on command complexity
- Multiple output formats (GIF, MP4, WebM)
- VHS tape file templates

**🎬 Live Demo**

![CLI Demo Generator Demo](./demos/cli-demo-generator/generate-demo.gif)

---

### 9. **cloudflare-troubleshooting** - Cloudflare Diagnostics

Investigate and resolve Cloudflare configuration issues using API-driven evidence gathering.

**When to use:**
- Site shows ERR_TOO_MANY_REDIRECTS
- SSL/TLS configuration errors
- DNS resolution problems
- Cloudflare-related issues

**Key features:**
- Evidence-based investigation methodology
- Comprehensive Cloudflare API reference
- SSL/TLS mode troubleshooting (Flexible, Full, Strict)
- DNS, cache, and firewall diagnostics
- Agentic approach with optional helper scripts

**🎬 Live Demo**

![Cloudflare Troubleshooting Demo](./demos/cloudflare-troubleshooting/diagnose-redirect-loop.gif)

---

### 10. **ui-designer** - UI Design System Extractor

Extract design systems from reference UI images and generate implementation-ready design prompts.

**When to use:**
- Have UI screenshots/mockups to analyze
- Need to extract color palettes, typography, spacing
- Building MVP UI matching reference aesthetics
- Creating consistent design systems
- Generating multiple UI variations

**Key features:**
- Systematic design system extraction from images
- Color palette, typography, component analysis
- Interactive MVP PRD generation
- Template-driven workflow (design system → PRD → implementation prompt)
- Multi-variation UI generation (3 mobile, 2 web)
- React + Tailwind CSS + Lucide icons

**🎬 Live Demo**

![UI Designer Demo](./demos/ui-designer/extract-design-system.gif)

---

### 11. **ppt-creator** - Professional Presentation Creation

Create persuasive, audience-ready slide decks from topics or documents with data-driven charts and dual-format PPTX output.

**When to use:**
- Creating presentations, pitch decks, or keynotes
- Need structured content with professional storytelling
- Require data visualization and charts
- Want complete PPTX files with speaker notes
- Building business reviews or product pitches

**Key features:**
- Pyramid Principle structure (conclusion → reasons → evidence)
- Assertion-evidence slide framework
- Automatic data synthesis and chart generation (matplotlib)
- Dual-path PPTX creation (Marp CLI + document-skills:pptx)
- Complete orchestration: content → data → charts → PPTX with charts
- 45-60 second speaker notes per slide
- Quality scoring with auto-refinement (target: 75/100)

**🎬 Live Demo**

![PPT Creator Demo](./demos/ppt-creator/create-presentation.gif)

---

### 12. **youtube-downloader** - YouTube Video & Audio Downloader

Download YouTube videos and audio using yt-dlp with robust error handling and automatic workarounds for common issues.

**When to use:**
- Downloading YouTube videos or playlists
- Extracting audio from YouTube videos as MP3
- Experiencing yt-dlp download failures or nsig extraction errors
- Need help with format selection or quality options
- Working with YouTube content in regions with access restrictions

**Key features:**
- Android client workaround for nsig extraction issues (automatic)
- Audio-only download with MP3 conversion
- Format listing and custom format selection
- Output directory customization
- Network error handling for proxy/restricted environments
- Availability check for yt-dlp dependency

**🎬 Live Demo**

![YouTube Downloader Demo](./demos/youtube-downloader/download-video.gif)

---

## 🎬 Interactive Demo Gallery

Want to see all demos in one place with click-to-enlarge functionality? Check out our [interactive demo gallery](./demos/index.html) or browse the [demos directory](./demos/).

## 🎯 Use Cases

### For GitHub Workflows
Use **github-ops** to streamline PR creation, issue management, and API operations.

### For Documentation
Combine **markdown-tools** for document conversion and **mermaid-tools** for diagram generation to create comprehensive documentation. Use **llm-icon-finder** to add brand icons.

### For Team Communication
Use **teams-channel-post-writer** to share knowledge and **statusline-generator** to track costs while working.

### For Repository Management
Use **repomix-unmixer** to extract and validate repomix-packed skills or repositories.

### For Skill Development
Use **skill-creator** (see [Essential Skill](#-essential-skill-skill-creator) section above) to build, validate, and package your own Claude Code skills following best practices.

### For Presentations & Business Communication
Use **ppt-creator** to generate professional slide decks with data visualizations, structured storytelling, and complete PPTX output for pitches, reviews, and keynotes.

### For Media & Content Download
Use **youtube-downloader** to download YouTube videos and extract audio from videos with automatic workarounds for common download issues.

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
- **skill-creator**: See `skill-creator/SKILL.md` for complete skill creation workflow
- **llm-icon-finder**: See `llm-icon-finder/references/icons-list.md` for available icons
- **cli-demo-generator**: See `cli-demo-generator/references/vhs_syntax.md` for VHS syntax and `cli-demo-generator/references/best_practices.md` for demo guidelines
- **ppt-creator**: See `ppt-creator/references/WORKFLOW.md` for 9-stage creation process and `ppt-creator/references/ORCHESTRATION_OVERVIEW.md` for automation
- **youtube-downloader**: See `youtube-downloader/SKILL.md` for usage examples and troubleshooting

## 🛠️ Requirements

- **Claude Code** 2.0.13 or higher
- **Python 3.6+** (for scripts in multiple skills)
- **gh CLI** (for github-ops)
- **markitdown** (for markdown-tools)
- **mermaid-cli** (for mermaid-tools)
- **yt-dlp** (for youtube-downloader): `brew install yt-dlp` or `pip install yt-dlp`
- **VHS** (for cli-demo-generator): `brew install vhs`
- **asciinema** (optional, for cli-demo-generator interactive recording)
- **ccusage** (optional, for statusline cost tracking)
- **pandas & matplotlib** (optional, for ppt-creator chart generation)
- **Marp CLI** (optional, for ppt-creator Marp PPTX export): `npm install -g @marp-team/marp-cli`

## ❓ FAQ

### How do I know which skills to install?

Start with **skill-creator** if you want to create your own skills. Otherwise, browse the [Other Available Skills](#-other-available-skills) section and install what matches your workflow.

### Can I use these skills without Claude Code?

No, these skills are specifically designed for Claude Code. You'll need Claude Code 2.0.13 or higher.

### How do I update skills?

Use the same install command to update:
```bash
claude plugin install skill-name@daymade/claude-code-skills
```

### Can I contribute my own skill?

Absolutely! See [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines. We recommend using the skill-creator to ensure your skill meets quality standards.

### Are these skills safe to use?

Yes, all skills are open-source and reviewed. The code is available in this repository for inspection.

### How do Chinese users handle API access?

We recommend using [CC-Switch](https://github.com/farion1231/cc-switch) to manage API provider configurations. See the [Chinese User Guide](#-chinese-user-guide) section above.

### What's the difference between skill-creator and other skills?

**skill-creator** is a meta-skill - it helps you create other skills. The other 7 skills are end-user skills that provide specific functionalities (GitHub ops, document conversion, etc.). If you want to extend Claude Code with your own workflows, start with skill-creator.

---

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

Last updated: 2025-10-22 | Version 1.2.0
