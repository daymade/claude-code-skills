# Claude Code 技能市场

<div align="center">

[![English](https://img.shields.io/badge/Language-English-blue)](./README.md)
[![简体中文](https://img.shields.io/badge/语言-简体中文-red)](./README.zh-CN.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Skills](https://img.shields.io/badge/skills-11-blue.svg)](https://github.com/daymade/claude-code-skills)
[![Version](https://img.shields.io/badge/version-1.4.0-green.svg)](https://github.com/daymade/claude-code-skills)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-2.0.13+-purple.svg)](https://claude.com/code)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](./CONTRIBUTING.md)
[![Maintenance](https://img.shields.io/badge/Maintained%3F-yes-green.svg)](https://github.com/daymade/claude-code-skills/graphs/commit-activity)

</div>

专业的 Claude Code 技能市场，提供 11 个生产就绪的技能，用于增强开发工作流。

## 📑 目录

- [🌟 必备技能：skill-creator](#-必备技能skill-creator)
- [🚀 快速安装](#-快速安装)
- [🇨🇳 中国用户指南](#-中国用户指南)
- [📦 其他可用技能](#-其他可用技能)
- [🎬 交互式演示画廊](#-交互式演示画廊)
- [🎯 使用场景](#-使用场景)
- [📚 文档](#-文档)
- [🛠️ 系统要求](#️-系统要求)
- [❓ 常见问题](#-常见问题)
- [🤝 贡献](#-贡献)
- [📄 许可证](#-许可证)

---

## 🌟 必备技能：skill-creator

**⭐ 如果你想创建自己的技能，从这里开始！**

`skill-creator` 是一个**元技能**，它使你能够构建、验证和打包自己的 Claude Code 技能。它是这个市场中最重要的工具，因为它赋予你用自己的专业工作流扩展 Claude Code 的能力。

### 为什么首选 skill-creator？

- **🎯 基础工具**：通过创建自己的技能来学习技能的工作原理
- **🛠️ 完整工具包**：包含初始化、验证和打包脚本
- **📖 最佳实践**：从生产就绪的示例中学习
- **🚀 快速启动**：在几秒钟内生成技能模板
- **✅ 质量保证**：内置验证确保你的技能符合标准

### 快速安装

```bash
/plugin marketplace add daymade/claude-code-skills
/plugin marketplace install daymade/claude-code-skills#skill-creator
```

### 你可以做什么

安装 skill-creator 后，只需向 Claude Code 提问：

```
"在 ~/my-skills 中创建一个名为 my-awesome-skill 的新技能"

"验证 ~/my-skills/my-awesome-skill 中的技能"

"打包 ~/my-skills/my-awesome-skill 技能以便分发"
```

加载了 skill-creator 的 Claude Code 将引导你完成整个技能创建过程——从理解你的需求到打包最终技能。

📚 **完整文档**：[skill-creator/SKILL.md](./skill-creator/SKILL.md)

### 实时演示

**📝 初始化新技能**

![初始化技能演示](./demos/skill-creator/init-skill.gif)

**✅ 验证技能结构**

![验证技能演示](./demos/skill-creator/validate-skill.gif)

**📦 打包技能用于分发**

![打包技能演示](./demos/skill-creator/package-skill.gif)

---

## 🚀 快速安装

### 自动化安装（推荐）

**macOS/Linux：**
```bash
curl -fsSL https://raw.githubusercontent.com/daymade/claude-code-skills/main/scripts/install.sh | bash
```

**Windows (PowerShell)：**
```powershell
iwr -useb https://raw.githubusercontent.com/daymade/claude-code-skills/main/scripts/install.ps1 | iex
```

### 手动安装

添加市场：
```bash
/plugin marketplace add daymade/claude-code-skills
```

**必备技能**（推荐首先安装）：
```bash
/plugin marketplace install daymade/claude-code-skills#skill-creator
```

**安装其他技能：**
```bash
# GitHub 操作
/plugin marketplace install daymade/claude-code-skills#github-ops

# 文档转换
/plugin marketplace install daymade/claude-code-skills#markdown-tools

# 图表生成
/plugin marketplace install daymade/claude-code-skills#mermaid-tools

# 状态栏定制
/plugin marketplace install daymade/claude-code-skills#statusline-generator

# Teams 通信
/plugin marketplace install daymade/claude-code-skills#teams-channel-post-writer

# Repomix 提取
/plugin marketplace install daymade/claude-code-skills#repomix-unmixer

# AI/LLM 图标
/plugin marketplace install daymade/claude-code-skills#llm-icon-finder

# CLI 演示生成
/plugin marketplace install daymade/claude-code-skills#cli-demo-generator
```

每个技能都可以独立安装 - 只选择你需要的！

---

## 🇨🇳 中国用户指南

### 推荐工具

**CC-Switch - Claude Code 配置管理器**

对于中国用户，我们强烈推荐使用 [CC-Switch](https://github.com/farion1231/cc-switch) 来管理 Claude Code 的 API 提供商配置。

CC-Switch 的主要功能：
- ✅ 快速切换不同的 API 供应商（DeepSeek、Qwen、GLM 等）
- ✅ 测试端点响应时间，自动选择最快的提供商
- ✅ 管理 MCP 服务器配置
- ✅ 自动备份和导入/导出配置
- ✅ 跨平台支持（Windows、macOS、Linux）

**安装方法：**

1. 从 [Releases](https://github.com/farion1231/cc-switch/releases) 下载对应系统的安装包
2. 安装并启动应用
3. 添加你的 API 配置
4. 通过界面或系统托盘切换配置

**系统要求：** Windows 10+、macOS 10.15+ 或 Linux (Ubuntu 22.04+)

### 常见的中国 API 提供商

CC-Switch 支持以下中国 AI 服务提供商：
- **DeepSeek**：高性价比的深度学习模型
- **Qwen（通义千问）**：阿里云的大语言模型
- **GLM（智谱清言）**：智谱 AI 的对话模型
- 以及其他兼容 OpenAI API 格式的提供商

### 网络问题解决

如果你在中国遇到网络问题：
1. 使用 CC-Switch 配置国内 API 提供商
2. 确保你的代理设置正确
3. 使用 CC-Switch 的响应时间测试功能找到最快的端点

---

## 📦 其他可用技能

### 1. **github-ops** - GitHub 操作套件

使用 gh CLI 和 GitHub API 进行全面的 GitHub 操作。

**使用场景：**
- 创建、查看或管理拉取请求
- 管理问题和仓库设置
- 查询 GitHub API 端点
- 使用 GitHub Actions 工作流
- 自动化 GitHub 操作

**主要功能：**
- 带 JIRA 集成的 PR 创建
- 问题管理工作流
- GitHub API（REST 和 GraphQL）操作
- 工作流自动化
- 企业 GitHub 支持

**🎬 实时演示**

![GitHub 操作演示](./demos/github-ops/create-pr.gif)

---

### 2. **markdown-tools** - 文档转换套件

将文档转换为 markdown，支持 Windows/WSL 路径处理和 Obsidian 集成。

**使用场景：**
- 转换 .doc/.docx/PDF/PPTX 为 markdown
- 处理 Confluence 导出
- 处理 Windows/WSL 路径转换
- 使用 markitdown 工具

**主要功能：**
- 多格式文档转换
- Confluence 导出处理
- Windows/WSL 路径自动化
- Obsidian vault 集成
- 路径转换辅助脚本

**🎬 实时演示**

![Markdown 工具演示](./demos/markdown-tools/convert-docs.gif)

---

### 3. **mermaid-tools** - 图表生成

从 markdown 中提取 Mermaid 图表并生成高质量的 PNG 图像。

**使用场景：**
- 将 Mermaid 图表转换为 PNG
- 从 markdown 文件中提取图表
- 处理包含嵌入图表的文档
- 创建演示用的可视化图形

**主要功能：**
- 自动图表提取
- 高分辨率 PNG 生成
- 基于图表类型的智能尺寸调整
- 可自定义的尺寸和缩放
- WSL2 Chrome/Puppeteer 支持

**🎬 实时演示**

![Mermaid 工具演示](./demos/mermaid-tools/extract-diagrams.gif)

---

### 4. **statusline-generator** - 状态栏定制

配置 Claude Code 状态栏，支持多行布局和成本跟踪。

**使用场景：**
- 自定义 Claude Code 状态栏
- 添加成本跟踪（会话/每日）
- 显示 git 状态
- 窄屏幕的多行布局
- 颜色自定义

**主要功能：**
- 多行状态栏布局
- ccusage 成本集成
- Git 分支状态指示器
- 可自定义的颜色
- 竖屏优化

**🎬 实时演示**

![状态栏生成器演示](./demos/statusline-generator/customize-statusline.gif)

---

### 5. **teams-channel-post-writer** - Teams 通信

创建用于内部知识分享的教育性 Teams 频道帖子。

**使用场景：**
- 编写关于功能的 Teams 帖子
- 分享 Claude Code 最佳实践
- 记录经验教训
- 创建内部公告
- 教授有效的提示模式

**主要功能：**
- 带有经过验证结构的帖子模板
- 高质量内容的写作指南
- "正常 vs 更好"示例模式
- 强调基本原则
- 即用型 markdown 模板

**🎬 实时演示**

![Teams 频道帖子编写器演示](./demos/teams-channel-post-writer/write-post.gif)

---

### 6. **repomix-unmixer** - 仓库提取

从 repomix 打包的仓库中提取文件并恢复目录结构。

**使用场景：**
- 解混 repomix 输出文件
- 提取打包的仓库
- 恢复文件结构
- 审查 repomix 内容
- 将 repomix 转换为可用文件

**主要功能：**
- 多格式支持（XML、Markdown、JSON）
- 自动格式检测
- 目录结构保留
- UTF-8 编码支持
- 全面的验证工作流

**🎬 实时演示**

![Repomix Unmixer 演示](./demos/repomix-unmixer/extract-repo.gif)

---

### 7. **llm-icon-finder** - AI/LLM 品牌图标查找器

从 lobe-icons 库访问 100+ AI 模型和 LLM 提供商品牌图标。

**使用场景：**
- 查找 AI 模型/提供商的品牌图标
- 下载 Claude、GPT、Gemini 等的徽标
- 获取多种格式的图标（SVG/PNG/WEBP）
- 构建 AI 工具文档
- 创建关于 LLM 的演示文稿

**主要功能：**
- 100+ AI/LLM 模型图标
- 多格式支持（SVG、PNG、WEBP）
- 直接访问的 URL 生成
- 本地下载功能
- 可搜索的图标目录

**🎬 实时演示**

![LLM 图标查找器演示](./demos/llm-icon-finder/find-icons.gif)

---

### 8. **cli-demo-generator** - CLI 演示生成器

使用 VHS 自动化生成专业的 CLI 动画演示和终端录制。

**使用场景：**
- 为文档创建演示
- 将终端工作流录制为 GIF
- 生成动画教程
- 批量生成多个演示
- 展示 CLI 工具

**主要功能：**
- 从命令列表自动生成演示
- 使用 YAML/JSON 配置批处理
- 使用 asciinema 进行交互式录制
- 基于命令复杂度的智能时序
- 多种输出格式（GIF、MP4、WebM）
- VHS tape 文件模板

**🎬 实时演示**

![CLI 演示生成器演示](./demos/cli-demo-generator/generate-demo.gif)

---

### 9. **cloudflare-troubleshooting** - Cloudflare 诊断

使用 API 驱动的证据收集来调查和解决 Cloudflare 配置问题。

**使用场景：**
- 网站显示 ERR_TOO_MANY_REDIRECTS
- SSL/TLS 配置错误
- DNS 解析问题
- Cloudflare 相关问题

**主要功能：**
- 基于证据的调查方法
- 全面的 Cloudflare API 参考
- SSL/TLS 模式故障排除（Flexible、Full、Strict）
- DNS、缓存和防火墙诊断
- 代理方法，配有可选的辅助脚本

**🎬 实时演示**

![Cloudflare 故障排除演示](./demos/cloudflare-troubleshooting/diagnose-redirect-loop.gif)

---

### 10. **ui-designer** - UI 设计系统提取器

从参考 UI 图像中提取设计系统，并生成可实施的设计提示。

**使用场景：**
- 拥有需要分析的 UI 截图/模型
- 需要提取色板、排版、间距
- 构建与参考美学匹配的 MVP UI
- 创建一致的设计系统
- 生成多个 UI 变体

**主要功能：**
- 从图像系统化提取设计系统
- 色板、排版、组件分析
- 交互式 MVP PRD 生成
- 模板驱动的工作流（设计系统 → PRD → 实施提示）
- 多变体 UI 生成（3 个移动端，2 个网页端）
- React + Tailwind CSS + Lucide 图标

**🎬 实时演示**

![UI 设计器演示](./demos/ui-designer/extract-design-system.gif)

---

## 🎬 交互式演示画廊

想要在一个地方查看所有演示并具有点击放大功能？访问我们的[交互式演示画廊](./demos/index.html)或浏览[演示目录](./demos/)。

## 🎯 使用场景

### GitHub 工作流
使用 **github-ops** 简化 PR 创建、问题管理和 API 操作。

### 文档处理
结合 **markdown-tools** 进行文档转换和 **mermaid-tools** 进行图表生成，创建全面的文档。使用 **llm-icon-finder** 添加品牌图标。

### 团队通信
使用 **teams-channel-post-writer** 分享知识，使用 **statusline-generator** 在工作时跟踪成本。

### 仓库管理
使用 **repomix-unmixer** 提取和验证 repomix 打包的技能或仓库。

### 技能开发
使用 **skill-creator**（参见上面的[必备技能](#-必备技能skill-creator)部分）构建、验证和打包你自己的 Claude Code 技能，遵循最佳实践。

## 📚 文档

每个技能包括：
- **SKILL.md**：核心说明和工作流
- **scripts/**：可执行工具（Python/Bash）
- **references/**：详细文档
- **assets/**：模板和资源（如适用）

### 快速链接

- **github-ops**：参见 `github-ops/references/api_reference.md` 了解 API 文档
- **markdown-tools**：参见 `markdown-tools/references/conversion-examples.md` 了解转换场景
- **mermaid-tools**：参见 `mermaid-tools/references/setup_and_troubleshooting.md` 了解设置指南
- **statusline-generator**：参见 `statusline-generator/references/color_codes.md` 了解自定义
- **teams-channel-post-writer**：参见 `teams-channel-post-writer/references/writing-guidelines.md` 了解质量标准
- **repomix-unmixer**：参见 `repomix-unmixer/references/repomix-format.md` 了解格式规范
- **skill-creator**：参见 `skill-creator/SKILL.md` 了解完整的技能创建工作流
- **llm-icon-finder**：参见 `llm-icon-finder/references/icons-list.md` 了解可用图标
- **cli-demo-generator**：参见 `cli-demo-generator/references/vhs_syntax.md` 了解 VHS 语法和 `cli-demo-generator/references/best_practices.md` 了解演示指南
- **cloudflare-troubleshooting**：参见 `cloudflare-troubleshooting/references/api_overview.md` 了解 API 文档
- **ui-designer**：参见 `ui-designer/SKILL.md` 了解完整的设计系统提取工作流

## 🛠️ 系统要求

- **Claude Code** 2.0.13 或更高版本
- **Python 3.6+**（用于多个技能中的脚本）
- **gh CLI**（用于 github-ops）
- **markitdown**（用于 markdown-tools）
- **mermaid-cli**（用于 mermaid-tools）
- **VHS**（用于 cli-demo-generator）：`brew install vhs`
- **asciinema**（可选，用于 cli-demo-generator 交互式录制）
- **ccusage**（可选，用于状态栏成本跟踪）

## ❓ 常见问题

### 我如何知道应该安装哪些技能？

如果你想创建自己的技能，从 **skill-creator** 开始。否则，浏览[其他可用技能](#-其他可用技能)部分，安装与你的工作流匹配的技能。

### 没有 Claude Code 可以使用这些技能吗？

不可以，这些技能是专门为 Claude Code 设计的。你需要 Claude Code 2.0.13 或更高版本。

### 如何更新技能？

使用相同的安装命令进行更新：
```bash
/plugin marketplace install daymade/claude-code-skills#skill-name
```

### 我可以贡献自己的技能吗？

当然可以！查看 [CONTRIBUTING.md](./CONTRIBUTING.md) 了解指南。我们建议使用 skill-creator 来确保你的技能符合质量标准。

### 这些技能使用安全吗？

是的，所有技能都是开源的并经过审查。代码可在此仓库中查看。

### 中国用户如何处理 API 访问？

我们建议使用 [CC-Switch](https://github.com/farion1231/cc-switch) 来管理 API 提供商配置。查看上面的[中国用户指南](#-中国用户指南)部分。

### skill-creator 和其他技能有什么区别？

**skill-creator** 是一个元技能 - 它帮助你创建其他技能。其他 10 个技能是最终用户技能，提供特定功能（GitHub 操作、文档转换等）。如果你想用自己的工作流扩展 Claude Code，从 skill-creator 开始。

---

## 🤝 贡献

欢迎贡献！请随时：

1. 为错误或功能请求开启问题
2. 提交带有改进的拉取请求
3. 分享关于技能质量的反馈

### 技能质量标准

此市场中的所有技能遵循：
- 祈使句/不定式写作风格
- 渐进式披露模式
- 适当的资源组织
- 全面的文档
- 经过测试和验证

## 📄 许可证

此市场根据 MIT 许可证授权 - 详见 [LICENSE](LICENSE) 文件。

## ⭐ 支持

如果你觉得这些技能有用，请：
- ⭐ 给这个仓库加星
- 🐛 报告问题
- 💡 提出改进建议
- 📢 与你的团队分享

## 🔗 相关资源

- [Claude Code 文档](https://docs.claude.com/en/docs/claude-code)
- [Agent 技能指南](https://docs.claude.com/en/docs/claude-code/skills)
- [插件市场](https://docs.claude.com/en/docs/claude-code/plugin-marketplaces)
- [Anthropic 技能仓库](https://github.com/anthropics/skills)

## 📞 联系方式

- **GitHub**：[@daymade](https://github.com/daymade)
- **Email**：daymadev89@gmail.com
- **仓库**：[daymade/claude-code-skills](https://github.com/daymade/claude-code-skills)

---

**使用 skill-creator 技能为 Claude Code 精心打造 ❤️**

最后更新：2025-10-22 | 版本 1.2.0
