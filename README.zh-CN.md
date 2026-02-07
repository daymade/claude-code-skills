# Claude Code 技能市场

<div align="center">

[![English](https://img.shields.io/badge/Language-English-blue)](./README.md)
[![简体中文](https://img.shields.io/badge/语言-简体中文-red)](./README.zh-CN.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Skills](https://img.shields.io/badge/skills-36-blue.svg)](https://github.com/daymade/claude-code-skills)
[![Version](https://img.shields.io/badge/version-1.31.0-green.svg)](https://github.com/daymade/claude-code-skills)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-2.0.13+-purple.svg)](https://claude.com/code)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](./CONTRIBUTING.md)
[![Maintenance](https://img.shields.io/badge/Maintained%3F-yes-green.svg)](https://github.com/daymade/claude-code-skills/graphs/commit-activity)

</div>

专业的 Claude Code 技能市场，提供 36 个生产就绪的技能，用于增强开发工作流。

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

**在 Claude Code 内（应用内）：**
```text
/plugin marketplace add daymade/claude-code-skills
```

然后：
1. 选择 **Browse and install plugins**
2. 选择 **daymade/claude-code-skills**
3. 选择 **skill-creator**
4. 选择 **Install now**

**在终端（CLI）：**
```bash
claude plugin marketplace add https://github.com/daymade/claude-code-skills
# Marketplace 名称：daymade-skills（来自 marketplace.json）
claude plugin install skill-creator@daymade-skills
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

### 在 Claude Code 内安装（应用内）

```text
/plugin marketplace add daymade/claude-code-skills
```

然后：
1. 选择 **Browse and install plugins**
2. 选择 **daymade/claude-code-skills**
3. 选择你需要的插件
4. 选择 **Install now**

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
claude plugin marketplace add https://github.com/daymade/claude-code-skills
```

Marketplace 名称是 `daymade-skills`（来自 marketplace.json），安装插件时请使用 `@daymade-skills`。
不要把仓库路径当成 marketplace 名称（例如 `@daymade/claude-code-skills` 会失败）。
在 Claude Code 内使用 `/plugin ...` 斜杠命令，在终端中使用 `claude plugin ...`。

**必备技能**（推荐首先安装）：
```bash
claude plugin install skill-creator@daymade-skills
```

**安装其他技能：**
```bash
# GitHub 操作
claude plugin install github-ops@daymade-skills

# 文档转换
claude plugin install markdown-tools@daymade-skills

# 图表生成
claude plugin install mermaid-tools@daymade-skills

# 状态栏定制
claude plugin install statusline-generator@daymade-skills

# Teams 通信
claude plugin install teams-channel-post-writer@daymade-skills

# Repomix 提取
claude plugin install repomix-unmixer@daymade-skills

# AI/LLM 图标
claude plugin install llm-icon-finder@daymade-skills

# CLI 演示生成
claude plugin install cli-demo-generator@daymade-skills

# Cloudflare 诊断
claude plugin install cloudflare-troubleshooting@daymade-skills

# UI 设计系统提取
claude plugin install ui-designer@daymade-skills

# 演示文稿创建
claude plugin install ppt-creator@daymade-skills

# YouTube 视频/音频下载
claude plugin install youtube-downloader@daymade-skills

# 安全 Repomix 打包
claude plugin install repomix-safe-mixer@daymade-skills

# ASR 转录校正
claude plugin install transcript-fixer@daymade-skills

# 视频比较和质量分析
claude plugin install video-comparer@daymade-skills

# QA 测试基础设施和自主执行
claude plugin install qa-expert@daymade-skills

# 使用 EARS 方法论优化提示词
claude plugin install prompt-optimizer@daymade-skills

# 会话历史恢复
claude plugin install claude-code-history-files-finder@daymade-skills

# 文档整合
claude plugin install docs-cleaner@daymade-skills

# PDF 生成（含中文字体支持）
claude plugin install pdf-creator@daymade-skills

# CLAUDE.md 渐进式披露优化
claude plugin install claude-md-progressive-disclosurer@daymade-skills

# CCPM 技能注册表搜索和管理
claude plugin install skills-search@daymade-skills

# Promptfoo LLM 评测框架
claude plugin install promptfoo-evaluation@daymade-skills

# iOS 应用开发
claude plugin install iOS-APP-developer@daymade-skills

# Twitter/X 内容获取
claude plugin install twitter-reader@daymade-skills

# macOS 磁盘空间清理
claude plugin install macos-cleaner@daymade-skills

# 技能质量审查与改进
claude plugin install skill-reviewer@daymade-skills

# GitHub 贡献策略
claude plugin install github-contributor@daymade-skills
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

将文档转换为 markdown，支持 Windows/WSL 路径处理和 PDF 图片提取。

**使用场景：**
- 转换 .doc/.docx/PDF/PPTX 为 markdown
- 从 PDF 文件中提取图片
- 处理 Confluence 导出
- 处理 Windows/WSL 路径转换

**主要功能：**
- 多格式文档转换
- PDF 图片提取（使用 PyMuPDF）
- Windows/WSL 路径自动化
- Confluence 导出处理
- 路径转换和图片提取辅助脚本

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

### 11. **ppt-creator** - 专业演示文稿创建

使用金字塔原理和断言-证据框架创建专业幻灯片。

**使用场景：**
- 从主题或文档创建演示文稿
- 生成带有数据可视化的幻灯片
- 创建推介演讲、业务评审或主题演讲
- 应用说服性叙事结构
- 生成完整的 PPTX 文件和演讲备注

**主要功能：**
- 金字塔原理结构（结论 → 理由 → 证据）
- 断言-证据幻灯片框架
- 自动数据合成和图表生成（matplotlib）
- 双路径 PPTX 创建（Marp CLI + document-skills:pptx）
- 完整编排：内容 → 数据 → 图表 → 带图表的 PPTX
- 每张幻灯片 45-60 秒演讲备注
- 质量评分和自动改进（目标：75/100）

**示例用法：**
```bash
# 从主题创建演示文稿
"为季度业务回顾创建一个演示文稿"

# 从文档生成幻灯片
"从这个产品规格文档创建一个推介演讲"
```

**🎬 实时演示**

*即将推出*

📚 **文档**：参见 [ppt-creator/references/WORKFLOW.md](./ppt-creator/references/WORKFLOW.md) 了解 9 阶段创建流程

---

### 12. **youtube-downloader** - YouTube 视频和音频下载器

使用 yt-dlp 下载 YouTube 视频和音频，具有强大的错误处理功能。

**使用场景：**
- 下载 YouTube 视频和播放列表
- 提取音频并转换为 MP3
- 处理 yt-dlp 下载问题（nsig 提取失败、网络错误）
- 在受限环境中下载视频

**主要功能：**
- 自动 PO Token 提供器（优先 Docker，失败自动切换浏览器方案）
- 通过浏览器 Cookie 处理“不是机器人”验证（更友好）
- 仅音频下载并转换为 MP3
- 格式列表和自定义格式选择
- 输出目录自定义
- 代理/受限环境的下载支持

**示例用法：**
```bash
# 下载视频
python3 scripts/download_video.py "https://www.youtube.com/watch?v=VIDEO_ID"

# 仅下载音频（MP3）
python3 scripts/download_video.py "https://www.youtube.com/watch?v=VIDEO_ID" --audio-only
```

**🎬 实时演示**

![YouTube 下载器演示](./demos/youtube-downloader/download-video.gif)

📚 **文档**：参见 [youtube-downloader/SKILL.md](./youtube-downloader/SKILL.md) 了解使用示例和故障排除

**要求**：Python 3.8+，yt-dlp（`brew install yt-dlp` 或 `pip install yt-dlp`）

---

### 13. **repomix-safe-mixer** - 安全 Repomix 打包

通过在打包前自动检测和删除硬编码凭据来安全地打包代码库。

**使用场景：**
- 使用 repomix 打包代码以供分发
- 创建参考包
- 对共享代码的安全问题有顾虑
- 防止意外泄露密钥/令牌/凭据

**主要功能：**
- 自动凭据检测（API 密钥、密码、令牌）
- 打包前凭据删除
- 安全扫描报告
- Repomix 集成
- 检测到凭据时的阻止机制

**示例用法：**
```bash
# 安全打包代码库
python3 scripts/safe_mix.py /path/to/codebase
```

**🎬 实时演示**

*即将推出*

📚 **文档**：参见 [repomix-safe-mixer/references/common_secrets.md](./repomix-safe-mixer/references/common_secrets.md) 了解检测到的凭据模式

**要求**：Python 3.8+，repomix

---

### 14. **transcript-fixer** - ASR 转录校正

通过基于字典的规则和 AI 驱动的校正来纠正语音转文本（ASR/STT）转录错误。

**使用场景：**
- 纠正会议记录、讲座录音、访谈中的转录错误
- 修复同音词错误（"their"/"there"，"to"/"too"）
- 处理 ASR/STT 转录文件
- 改进转录文本的可读性和准确性

**主要功能：**
- 基于字典的规则引擎
- AI 驱动的上下文校正
- 自动学习和字典更新
- 批处理
- 团队协作模式（共享字典）
- 支持多种 ASR 引擎（Whisper、Google Speech、Azure Speech）

**示例用法：**
```bash
# 校正转录文件
python3 scripts/fix_transcript.py meeting_notes.txt

# 使用自定义字典
python3 scripts/fix_transcript.py transcript.txt --dictionary custom_dict.json
```

**🎬 实时演示**

*即将推出*

📚 **文档**：参见 [transcript-fixer/references/workflow_guide.md](./transcript-fixer/references/workflow_guide.md) 了解分步工作流

**要求**：Python 3.8+

---

### 15. **video-comparer** - 视频比较和质量分析

比较两个视频并生成带有质量指标和逐帧视觉比较的交互式 HTML 报告。

**使用场景：**
- 比较原始和压缩视频
- 分析视频压缩质量和效率
- 评估编解码器性能或比特率降低影响
- 评估压缩前后结果
- 视频编码工作流的质量分析

**主要功能：**
- 质量指标计算（PSNR、SSIM）
- 逐帧视觉比较，提供三种查看模式：
  - 滑块模式：拖动以显示差异
  - 并排模式：同时显示
  - 网格模式：紧凑的 2 列布局
- 视频元数据提取（编解码器、分辨率、比特率、时长、文件大小）
- 自包含的 HTML 报告（无需服务器，可离线工作）
- 安全功能（路径验证、资源限制、超时控制）
- 多平台 FFmpeg 支持（macOS、Linux、Windows）

**示例用法：**
```bash
# 基本比较
python3 scripts/compare.py original.mp4 compressed.mp4

# 自定义输出和帧间隔
python3 scripts/compare.py original.mp4 compressed.mp4 -o report.html --interval 10
```

**🎬 实时演示**

*即将推出*

📚 **文档**：参见 [video-comparer/references/](./video-comparer/references/) 了解质量指标解释、FFmpeg 命令和配置选项

**要求**：Python 3.8+，FFmpeg/FFprobe（`brew install ffmpeg`、`apt install ffmpeg` 或 `winget install ffmpeg`）

---

### 16. **qa-expert** - 综合 QA 测试基础设施

使用自主 LLM 执行、Google 测试标准和 OWASP 安全最佳实践建立世界级 QA 测试流程。

**使用场景：**
- 为新项目或现有项目设置 QA 基础设施
- 编写遵循 Google 测试标准（AAA 模式）的标准化测试用例
- 实施安全测试（OWASP Top 10 覆盖）
- 执行具有自动进度跟踪的综合测试计划
- 使用适当的 P0-P4 严重性分类提交错误
- 计算质量指标和执行质量门禁
- 启用自主 LLM 驱动的测试执行（100 倍加速）
- 为第三方团队交接准备 QA 文档

**主要功能：**
- **一键初始化**：使用模板、CSV 和文档完成 QA 基础设施
- **自主执行**：主提示使 LLM 能够自动执行所有测试、自动跟踪结果、自动提交错误
- **Google 测试标准**：AAA 模式合规性、90% 覆盖率目标、快速失败验证
- **OWASP 安全测试**：90% Top 10 覆盖，具有特定攻击向量
- **质量门禁执行**：100% 执行、≥80% 通过率、0 个 P0 错误、≥80% 代码覆盖率
- **基本事实原则**：防止文档/CSV 同步问题（测试文档 = 权威来源）
- **错误跟踪**：P0-P4 分类，详细重现步骤和环境信息
- **第 1 天入职**：新 QA 工程师的 5 小时指南
- **30+ LLM 提示**：用于特定 QA 任务的即用型提示
- **指标仪表板**：测试执行进度、通过率、错误分析、质量门禁状态

**示例用法：**
```bash
# 初始化 QA 项目（创建完整基础设施）
python3 scripts/init_qa_project.py my-app ./

# 计算质量指标和门禁状态
python3 scripts/calculate_metrics.py tests/TEST-EXECUTION-TRACKING.csv

# 对于自主执行，从以下位置复制主提示：
# references/master_qa_prompt.md → 粘贴到 LLM → 在 5 周内自动执行 342 个测试
```

**🎬 实时演示**

*即将推出*

📚 **文档**：参见 [qa-expert/references/](./qa-expert/references/)：
- `master_qa_prompt.md` - 自主执行的单一命令（100 倍加速）
- `google_testing_standards.md` - AAA 模式、覆盖率阈值、OWASP 测试
- `day1_onboarding.md` - 新 QA 工程师的 5 小时入职时间表
- `ground_truth_principle.md` - 防止文档/CSV 同步问题
- `llm_prompts_library.md` - 30+ 即用型 QA 提示

**要求**：Python 3.8+

**💡 创新**：自主执行能力（通过主提示）使 LLM 能够以比手动执行快 100 倍的速度执行整个测试套件，跟踪零人为错误。非常适合第三方 QA 交接 - 只需提供主提示，他们就可以立即开始测试。

---

### 17. **prompt-optimizer** - 使用 EARS 方法论进行提示词工程

使用 EARS（简易需求语法）将模糊的提示词转换为精确、结构化的规范 - 这是罗尔斯·罗伊斯公司创建的一种将自然语言转换为可测试需求的方法论。

**方法论灵感来源：** [阿星AI工作室](https://mp.weixin.qq.com/s/yUVX-9FovSq7ZGChkHpuXQ)，他们开创性地将 EARS 与领域理论基础相结合，实现了实用的提示词增强。

**使用场景：**
- 将松散的需求转换为结构化规范
- 优化 AI 代码生成或内容创作的提示词
- 将模糊的功能请求分解为原子化、可测试的陈述
- 为技术需求添加领域理论基础
- 将"构建 X"请求转换为详细的实施规范
- 通过经过验证的框架学习提示词工程最佳实践

**主要功能：**
- **EARS 转换**：5 种句式模式（普适、事件驱动、状态驱动、条件、不期望行为）
- **6 步优化工作流**：分析 → 转换 → 识别理论 → 提取示例 → 增强 → 呈现
- **领域理论目录**：40+ 框架映射到 10 个领域（生产力、UX、游戏化、学习、电商、安全）
- **结构化提示框架**：角色/技能/工作流/示例/格式模板
- **高级技术**：多利益相关者需求、非功能性规范、复杂条件逻辑
- **完整示例**：拖延症应用、电商产品页、学习平台、密码重置
- **理论基础**：GTD、BJ Fogg 行为模型、格式塔原则、AIDA、零信任等
- **渐进式披露**：捆绑参考文档（ears_syntax.md、domain_theories.md、examples.md）

**示例用法：**
```markdown
# 之前（模糊）
"帮我构建一个密码重置功能"

# EARS 转换后（7 个原子需求）
1. 当用户点击"忘记密码"时，系统应显示邮箱输入框
2. 当用户提交有效邮箱时，系统应发送有效期为 1 小时的密码重置链接
3. 当用户点击重置链接时，系统应验证令牌是否未过期
4. 当令牌有效时，系统应显示密码创建表单，要求最少 12 个字符、1 个大写字母、1 个数字、1 个特殊字符
5. 当用户提交符合要求的新密码时，系统应使用 bcrypt 哈希密码并使令牌失效
6. 当用户在 1 小时内尝试密码重置超过 3 次时，系统应阻止进一步尝试 1 小时
7. 如果重置令牌已过期，系统应显示错误消息和请求新链接的选项

# 使用领域理论增强
- 零信任架构（每步验证）
- 纵深防御（速率限制 + 令牌过期 + 密码复杂性）
- 渐进式披露（多步骤 UX 流程）

# 完整提示包括角色、技能、工作流、示例、格式
```

**🎬 实时演示**

*即将推出*

📚 **文档**：参见 [prompt-optimizer/references/](./prompt-optimizer/references/)：
- `ears_syntax.md` - 完整的 EARS 模式和转换规则
- `domain_theories.md` - 40+ 理论映射到领域并提供选择指导
- `examples.md` - 包含前后对比的完整转换示例

**💡 创新**：EARS 方法论通过强制明确条件、触发器和可测量标准来消除歧义。结合领域理论基础（GTD、BJ Fogg、格式塔等），它将"构建一个待办事项应用"转换为包含行为心理学原则、UX 最佳实践和具体测试用例的完整规范 - 从第一天起就支持测试驱动开发。

---

### 18. **claude-code-history-files-finder** - 会话历史恢复

从存储在 `~/.claude/projects/` 的 Claude Code 会话历史文件中查找和恢复内容。

**使用场景：**
- 从之前的 Claude Code 会话中恢复已删除或丢失的文件
- 在对话历史中搜索特定代码
- 跨多个会话跟踪文件修改
- 查找包含特定关键字或实现的会话

**主要功能：**
- **会话搜索**：按关键字查找会话并按频率排名
- **内容恢复**：从 Write 工具调用中提取文件并去重
- **统计分析**：消息计数、工具使用明细、文件操作
- **批量操作**：使用关键字过滤处理多个会话
- **流式处理**：高效处理大型会话文件（>100MB）

**示例用法：**
```bash
# 列出项目的最近会话
python3 scripts/analyze_sessions.py list /path/to/project

# 搜索包含关键字的会话
python3 scripts/analyze_sessions.py search /path/to/project "ComponentName" "featureX"

# 从会话中恢复已删除的文件
python3 scripts/recover_content.py ~/.claude/projects/.../session.jsonl -k DeletedComponent -o ./recovered/

# 获取会话统计信息
python3 scripts/analyze_sessions.py stats /path/to/session.jsonl --show-files
```

**🎬 实时演示**

*即将推出*

📚 **文档**：参见 [claude-code-history-files-finder/references/](./claude-code-history-files-finder/references/)：
- `session_file_format.md` - JSONL 结构和提取模式
- `workflow_examples.md` - 详细的恢复和分析工作流

---

### 19. **docs-cleaner** - 文档整合

整合冗余文档的同时保留所有有价值的内容。

**使用场景：**
- 清理项目中的文档膨胀
- 合并涵盖相同主题的冗余文档
- 减少快速开发后的文档扩散
- 将多个文件整合为权威来源

**主要功能：**
- **内容保留**：清理过程中永不丢失有价值的信息
- **冗余检测**：识别重叠的文档
- **智能合并**：在保持结构的同时合并相关文档
- **验证**：确保整合后的文档完整准确

**🎬 实时演示**

*即将推出*

---

### 20. **skills-search** - CCPM 技能注册表搜索

从 CCPM（Claude Code 插件管理器）注册表中搜索、发现、安装和管理 Claude Code 技能。

**使用场景：**
- 为特定任务查找技能（例如"查找 PDF 技能"）
- 按名称安装技能
- 列出当前已安装的技能
- 获取技能的详细信息
- 管理你的 Claude Code 技能集合

**主要功能：**
- **注册表搜索**：使用 `ccpm search <query>` 搜索 CCPM 注册表
- **技能安装**：使用 `ccpm install <skill-name>` 安装技能
- **版本支持**：使用 `@version` 语法安装特定版本
- **批量安装**：安装预配置的技能包（web-dev、content-creation、developer-tools）
- **多种格式**：支持注册表名称、GitHub owner/repo 和完整 URL
- **技能信息**：使用 `ccpm info <skill-name>` 获取详细的技能信息

**示例用法：**
```bash
# 搜索技能
ccpm search pdf              # 查找 PDF 相关技能
ccpm search "code review"    # 查找代码审查技能

# 安装技能
ccpm install skill-creator                # 从注册表安装
ccpm install daymade/skill-creator        # 从 GitHub 安装
ccpm install skill-creator@1.0.0          # 安装特定版本

# 列出和管理
ccpm list                    # 列出已安装的技能
ccpm info skill-creator      # 获取技能详情
ccpm uninstall pdf-processor # 删除技能

# 安装技能包
ccpm install-bundle web-dev  # 安装 Web 开发技能包
```

**🎬 实时演示**

*即将推出*

📚 **文档**：参见 [skills-search/SKILL.md](./skills-search/SKILL.md) 了解完整的命令参考

**要求**：CCPM CLI（`npm install -g @daymade/ccpm`）

---

### 21. **pdf-creator** - PDF 生成（中文字体支持）

使用 WeasyPrint 将 markdown 转换为专业 PDF，并提供完善的中文字体支持。

**使用场景：**
- 将 markdown 转换为可分享/可打印的 PDF
- 生成正式文档（法律文件、报告）
- 需要正确的中文排版

**主要功能：**
- WeasyPrint + Markdown 转换管道
- 内置中文字体回退
- A4 版式与打印友好边距
- 批量转换脚本

**示例用法：**
```bash
uv run --with weasyprint --with markdown scripts/md_to_pdf.py input.md output.pdf
```

**🎬 实时演示**

*即将推出*

📚 **文档**：参见 [pdf-creator/SKILL.md](./pdf-creator/SKILL.md) 了解设置与工作流。

**要求**：Python 3.8+，`weasyprint`、`markdown`

---

### 22. **claude-md-progressive-disclosurer** - CLAUDE.md 优化

使用渐进式披露原则优化 CLAUDE.md，减少上下文负担但保留关键规则。

**使用场景：**
- CLAUDE.md 过长或重复
- 需要将详细流程移至 references
- 希望把可复用工作流抽成技能

**主要功能：**
- 章节分类（保留/迁移/提取/移除）
- 变更前后行数对比
- references 指针格式与最佳实践

**示例用法：**
```
"请用渐进式披露优化我的 ~/.claude/CLAUDE.md，并给出方案"
```

**🎬 实时演示**

*即将推出*

📚 **文档**：参见 [claude-md-progressive-disclosurer/SKILL.md](./claude-md-progressive-disclosurer/SKILL.md)。

---

### 23. **promptfoo-evaluation** - Promptfoo LLM 评测

使用 Promptfoo 配置并运行 LLM 评测，进行提示词测试与模型对比。

**使用场景：**
- 搭建 prompt 测试与评测配置
- 对比不同模型输出
- 编写自定义断言或 LLM-as-judge 评分

**主要功能：**
- promptfooconfig.yaml 模板
- Python 自定义断言
- llm-rubric 评分指引
- echo provider 预览流程

**示例用法：**
```bash
npx promptfoo@latest init
npx promptfoo@latest eval
npx promptfoo@latest view
```

**🎬 实时演示**

*即将推出*

📚 **文档**：参见 [promptfoo-evaluation/references/promptfoo_api.md](./promptfoo-evaluation/references/promptfoo_api.md)。

**要求**：Node.js（Promptfoo 通过 `npx promptfoo@latest`）

---

### 24. **iOS-APP-developer** - iOS 应用开发

使用 XcodeGen、SwiftUI 与 SPM 构建、配置和调试 iOS 应用。

**使用场景：**
- 配置 XcodeGen `project.yml`
- 修复 SPM 依赖或嵌入问题
- 处理签名与真机部署错误
- 调试相机/AVFoundation

**主要功能：**
- XcodeGen 项目模板
- SPM 动态框架嵌入修复
- 代码签名与配置指导
- 真机部署与故障排查清单

**示例用法：**
```bash
xcodegen generate
xcodebuild -destination 'platform=iOS Simulator,name=iPhone 17' build
```

**🎬 实时演示**

*即将推出*

📚 **文档**：参见 [iOS-APP-developer/references/xcodegen-full.md](./iOS-APP-developer/references/xcodegen-full.md)。

**要求**：macOS + Xcode，XcodeGen

---

### 25. **twitter-reader** - Twitter/X 内容获取

使用 Jina.ai API 获取 Twitter/X 帖子内容，无需 JavaScript 渲染或身份验证即可绕过限制。

**使用场景：**
- 检索推文内容用于分析或文档记录
- 获取话题回复与对话上下文
- 从帖子中提取图片和媒体
- 批量下载多条推文作为参考

**主要功能：**
- 无需 JavaScript 渲染或浏览器自动化
- 无需 Twitter 身份验证
- 返回带元数据的 Markdown 格式内容
- 支持单条和批量获取
- 包含作者、时间戳、帖子文本、图片和回复
- 环境变量配置实现安全的 API 密钥管理

**示例用法：**
```bash
# 设置你的 Jina API 密钥（从 https://jina.ai/ 获取）
export JINA_API_KEY="your_api_key_here"

# 获取单条推文
curl "https://r.jina.ai/https://x.com/USER/status/TWEET_ID" \
  -H "Authorization: Bearer ${JINA_API_KEY}"

# 批量获取多条推文
scripts/fetch_tweets.sh \
  "https://x.com/user/status/123" \
  "https://x.com/user/status/456"

# 使用 Python 脚本获取到文件
python scripts/fetch_tweet.py https://x.com/user/status/123 output.md
```

**🎬 实时演示**

*即将推出*

📚 **文档**：参见 [twitter-reader/SKILL.md](./twitter-reader/SKILL.md) 了解完整细节和 URL 格式支持。

**要求**：
- **Jina.ai API 密钥**（从 https://jina.ai/ 获取 - 提供免费套餐）
- **curl**（大多数系统预装）
- **Python 3.6+**（用于 Python 脚本）

---

### 26. **macos-cleaner** - 智能 macOS 磁盘空间恢复

**在 macOS 上恢复磁盘空间最安全的方式。** 通过智能分类和交互式清理，分析系统缓存、应用残留、大文件和开发环境。

**为什么 macos-cleaner 与众不同：**
- **安全优先理念**：在明确用户确认之前绝不删除。每项操作都包含风险评估（🟢 安全 / 🟡 谨慎 / 🔴 保留）。
- **智能胜于自动化**：先分析，详细解释，然后由你决定。与盲目删除的一键清理工具不同，我们帮助你理解要删除的内容及原因。
- **开发者友好**：深度分析 Docker、Homebrew、npm、pip 缓存 - 这些是通用清理工具遗漏的工具。
- **透明且教育性**：每项建议都包含对文件的解释、为什么安全（或不安全）以及删除后的影响。
- **专业品质**：由了解误删重要文件痛苦的开发者构建。包含全面的安全检查和 Time Machine 备份建议。

**我们的设计原则：**
1. **用户控制优先**：你做决定，我们提供洞察
2. **解释一切**：没有神秘的删除 - 完全透明的影响说明
3. **保守的默认值**：不确定时，我们保留而不是删除
4. **开发者视角**：理解开发工具缓存，而不仅仅是系统文件
5. **混合方法**：结合脚本精度与可视化工具（Mole 集成）

**使用场景：**
- 你的 Mac 磁盘空间不足（使用率 >80%）
- 你是开发者，Docker/npm/pip/Homebrew 缓存堆积如山
- 你想了解占用空间的内容，而不仅仅是盲目删除
- 你需要清理已卸载应用程序的残留
- 你更喜欢理解而非自动化

**主要功能：**
- **智能缓存分析**：按安全级别对系统缓存、应用缓存、日志进行分类
- **应用残留检测**：查找已卸载应用程序的孤立数据，并提供可信度评分
- **大文件发现**：智能分类（视频、归档、数据库、磁盘镜像、构建产物）
- **开发环境清理**：Docker（镜像、容器、卷、构建缓存）、Homebrew、npm、pip、旧 Git 仓库
- **交互式安全删除**：批量确认、选择性删除、撤销友好（尽可能使用废纸篓）
- **前后报告**：跟踪空间恢复并提供详细分解
- **Mole 集成**：与可视化清理工具无缝协作，适合 GUI 偏好
- **风险分类**：每个项目都标有安全级别和说明
- **Time Machine 感知**：建议在大批量删除（>10 GB）前进行备份

**我们的优势：**
- ✅ **通过透明度建立信任**：其他清理工具隐藏删除内容。我们展示一切并解释原因。
- ✅ **以开发者为中心**：我们清理 Docker，而不仅仅是浏览器缓存。我们理解 `.git` 目录、`node_modules` 和构建产物。
- ✅ **内置安全检查**：保护系统文件、用户数据、凭据、活动数据库或正在使用的文件不被删除。
- ✅ **教育性**：了解什么可以安全删除及原因，以便你能自信地维护你的 Mac。
- ❌ **不是一键解决方案**：我们不会自动删除。如果你想要"立即清理所有内容"，请使用其他工具。我们面向想要控制的用户。

**示例用法：**
```bash
# 安装技能
claude plugin install macos-cleaner@daymade-skills

# 要求 Claude Code 分析你的 Mac
"我的 Mac 快没空间了，帮我分析一下是什么在占用存储空间"

# Claude 将会：
# 1. 运行全面的磁盘分析
# 2. 展示带有安全级别的分类结果
# 3. 解释每个类别（缓存、残留、大文件、开发工具）
# 4. 推荐清理方法
# 5. 仅执行你确认的操作

# 示例分析输出：
📊 磁盘空间分析
━━━━━━━━━━━━━━━━━━━━━━━
总计:       500 GB
已用:       450 GB (90%)
可用:        50 GB (10%)

🟢 安全清理 (95 GB):
  - 系统缓存:          45 GB (应用会自动重新生成)
  - Homebrew 缓存:      5 GB (需要时重新安装)
  - npm 缓存:           3 GB (清除安全)
  - 旧日志:             8 GB (仅诊断数据)
  - 废纸篓:            34 GB (已标记为删除)

🟡 建议审查 (62 GB):
  - 大型下载:          38 GB (可能包含重要文件)
  - 应用残留:           8 GB (验证应用是否真正卸载)
  - Docker 镜像:       12 GB (可能正在使用)
  - 旧 .git 仓库:       4 GB (验证项目是否已归档)

🔴 除非确定否则保留 (0 GB):
  - 未检测到高风险项目

建议：从 🟢 安全项目开始 (95 GB)，然后一起审查 🟡 项目。
```

**🎬 实时演示**

*即将推出*

📚 **文档**：参见 [macos-cleaner/references/](./macos-cleaner/references/) 了解：
- `cleanup_targets.md` - 每个清理目标的详细说明
- `mole_integration.md` - 如何将脚本与 Mole 可视化工具结合使用
- `safety_rules.md` - 全面的安全指南以及永远不应删除的内容

**要求**：
- **Python 3.6+**（macOS 预装）
- **macOS**（在 macOS 10.15+ 上测试）
- **可选**：[Mole](https://github.com/tw93/Mole) 用于可视化清理界面

---

### 27. **fact-checker** - 文档事实核查

使用网络搜索和权威来源验证文档中的事实声明，然后提议更正并等待用户确认。

**使用场景：**
- 核实文档准确性
- 验证 AI 模型规格和技术文档
- 更新文档中的过时信息
- 验证统计声明和基准测试
- 检查 API 功能和版本号

**主要功能：**
- 集成权威来源的网络搜索
- AI 模型规格验证
- 技术文档准确性检查
- 统计数据验证
- 自动更正报告（需用户确认）
- 支持一般事实声明和技术声明

**示例用法：**
```bash
# 安装技能
claude plugin install fact-checker@daymade-skills

# 核实文档
"请核查这部分关于 AI 模型功能的内容"

# 验证技术规格
"检查这些 Claude 模型规格是否仍然准确"

# 更新过时信息
"验证并更新此文档中的版本号"
```

**🎬 实时演示**

*即将推出*

📚 **文档**：参见 [fact-checker/SKILL.md](./fact-checker/SKILL.md) 了解完整的工作流程和声明类型。

**要求**：
- 网络搜索访问（通过 Claude Code）

---

### 28. **skill-reviewer** - 技能质量审查与改进

以三种强大模式审查和改进 Claude Code 技能，确保符合官方最佳实践。

**使用场景：**
- 发布前验证你自己的技能
- 评估他人的技能仓库
- 通过 auto-PR 为开源技能贡献改进
- 确保技能符合市场标准

**主要功能：**
- **自检模式**：通过 skill-creator 脚本运行自动化验证
- **外部审查模式**：克隆、分析并生成改进报告
- **Auto-PR 模式**：Fork → 改进 → 提交 PR（仅添加性更改）
- **评估清单**：验证 frontmatter、说明、资源
- **仅添加原则**：贡献他人项目时绝不删除文件
- **PR 指南**：语气建议和专业模板
- **自动安装依赖**：若缺少 skill-creator 则自动安装

**示例用法：**
```bash
# 安装技能
claude plugin install skill-reviewer@daymade-skills

# 自检你的技能
"验证 ~/my-skills/my-awesome-skill 的技能"

# 审查外部技能仓库
"审查 https://github.com/user/skill-repo 的技能"

# Auto-PR 改进
"Fork、改进并为 https://github.com/user/skill-repo 提交 PR"
```

**🎬 实时演示**

*即将推出*

📚 **文档**：参见 [skill-reviewer/references/](./skill-reviewer/references/) 了解：
- `evaluation_checklist.md` - 完整的技能评估标准
- `pr_template.md` - 专业 PR 描述模板
- `marketplace_template.json` - marketplace 配置模板

---

### 29. **github-contributor** - GitHub 贡献策略

成为高效 GitHub 贡献者并建立开源声誉的战略指南。

**使用场景：**
- 寻找可贡献的项目
- 学习贡献最佳实践
- 建立你的 GitHub 影响力和声誉
- 了解如何撰写高质量 PR

**主要功能：**
- **四种贡献类型**：文档、代码质量、Bug 修复、功能开发
- **项目选择标准**：优质首选项目 vs 危险信号
- **PR 卓越工作流**：提交前 → 撰写中 → 提交后清单
- **声誉建设阶梯**：文档 → Bug 修复 → 功能开发 → 维护者
- **GitHub CLI 命令**：fork、PR、issue 操作快速参考
- **约定式提交格式**：type、scope、description 结构
- **常见错误**：需要避免的问题和最佳实践

**贡献类型解释：**
```
Level 1: 文档修复（门槛最低，影响力高）
    ↓ (建立熟悉度)
Level 2: 代码质量（中等努力，展示技能）
    ↓ (理解代码库)
Level 3: Bug 修复（高影响力，建立信任）
    ↓ (受信任的贡献者)
Level 4: 功能添加（最高可见度）
    ↓ (潜在维护者)
```

**示例用法：**
```bash
# 安装技能
claude plugin install github-contributor@daymade-skills

# 找到好的首次贡献机会
"帮我找一些 Python 项目中有 good first issue 的项目"

# 撰写高质量 PR
"指导我为这个 bug 修复创建一个 PR"

# 制定贡献策略
"帮我规划一个建立 GitHub 档案的贡献策略"
```

**🎬 实时演示**

*即将推出*

📚 **文档**：参见 [github-contributor/references/](./github-contributor/references/) 了解：
- `pr_checklist.md` - 完整的 PR 质量清单
- `project_evaluation.md` - 如何评估可贡献的项目
- `communication_templates.md` - Issue 和 PR 沟通模板

---

### 31. **i18n-expert** - 国际化与本地化

为 UI 代码库提供完整的国际化/本地化设置和审计。配置 i18n 框架、将硬编码字符串替换为翻译键、确保 en-US 和 zh-CN 之间的语言环境一致性，并验证复数形式和格式设置。

**使用场景：**
- 为新的 React/Next.js/Vue 应用程序设置 i18n
- 审计现有 i18n 实现的键一致性和完整性
- 将硬编码字符串替换为翻译键
- 确保错误代码正确映射到本地化消息
- 验证跨语言环境的复数形式、日期/时间/数字格式设置
- 实现语言切换和 SEO 元数据本地化

**主要功能：**
- 库选择和设置（react-i18next、next-intl、vue-i18n）
- 键架构和语言环境文件组织（JSON、YAML、PO、XLIFF）
- 翻译生成策略（AI、专业、手动）
- 路由和语言检测/切换
- SEO 和元数据本地化
- 适用语言环境的 RTL 支持
- en-US 和 zh-CN 之间的键一致性验证
- 复数形式和格式设置验证
- 错误代码映射到本地化消息
- 捆绑的 i18n_audit.py 脚本用于键使用提取

**示例用法：**
```bash
# 安装技能
claude plugin install i18n-expert@daymade-skills

# 为新项目设置 i18n
"为我的 React 应用设置支持英文和中文的 i18n"

# 审计现有 i18n 实现
"审计 i18n 设置并查找缺失的翻译键"

# 替换硬编码字符串
"将此组件中的所有硬编码字符串替换为 i18n 键"
```

**🎬 实时演示**

*即将推出*

📚 **文档**：参见 [i18n-expert/SKILL.md](./i18n-expert/SKILL.md) 了解完整的工作流程和架构指导。

**要求**：
- **Python 3.6+**（用于审计脚本）
- **React/Next.js/Vue**（框架特定的 i18n 库）

---

### 32. **claude-skills-troubleshooting** - 插件与技能故障排除

诊断和解决 Claude Code 插件和技能配置问题。通过系统化工作流程调试插件安装、启用和激活问题。

**使用场景：**
- 插件已安装但未显示在可用技能列表中
- 尽管已安装，技能仍未按预期激活
- 调试 settings.json 中的 enabledPlugins 配置
- 调试"插件不工作"或"技能未显示"问题
- 了解插件状态架构和生命周期

**主要功能：**
- 通过诊断脚本快速诊断（检测已安装但未启用的不匹配）
- 插件状态架构文档（installed_plugins.json vs settings.json）
- 市场缓存新鲜度检测和更新指导
- 已知 GitHub 问题跟踪（#17832、#19696、#17089、#13543、#16260）
- 用于批量启用市场缺失插件的脚本
- 技能与命令架构解释
- 全面的诊断命令参考

**示例用法：**
```bash
# 安装技能
claude plugin install claude-skills-troubleshooting@daymade-skills

# 运行诊断
python3 scripts/diagnose_plugins.py

# 批量启用缺失的插件
python3 scripts/enable_all_plugins.py daymade-skills
```

**🎬 实时演示**

*即将推出*

📚 **文档**：参见 [claude-skills-troubleshooting/SKILL.md](./claude-skills-troubleshooting/SKILL.md) 了解完整的故障排除工作流程和架构指导。

**要求**：无（使用 Claude Code 内置 Python）

---

### 33. **meeting-minutes-taker** - 会议纪要生成器

将会议录音转写稿转换为高保真、结构化的会议纪要，支持迭代式人工审核。

**使用场景：**
- 提供会议转写稿，需要生成会议纪要/笔记/摘要
- 多个版本的会议纪要需要合并且不丢失内容
- 现有纪要需要对照原始转写稿审核是否遗漏

**主要功能：**
- 多轮并行生成与 UNION 合并策略
- 基于证据的记录，附带发言者引用
- 用于架构讨论的 Mermaid 图表
- 迭代式人机协作优化流程
- 跨 AI 对比以减少偏差
- 完整性检查清单用于系统化审核

**示例用法：**
```bash
# 安装技能
claude plugin install meeting-minutes-taker@daymade-skills

# 然后提供会议转写稿并请求生成纪要
```

**🎬 实时演示**

*即将推出*

📚 **文档**：参见 [meeting-minutes-taker/SKILL.md](./meeting-minutes-taker/SKILL.md) 了解完整的工作流程和模板指导。

**要求**：无

---

### 34. **deep-research** - 深度调研报告生成器

生成格式可控的调研报告，支持证据追踪与引用。

**使用场景：**
- 需要结构化调研报告、文献综述或行业/市场分析
- 需要严格的章节格式或模板约束
- 需要证据映射、引用与来源质量审查
- 需要多轮综合以避免遗漏关键发现

**主要功能：**
- 报告规格与格式合约工作流
- 证据表与来源质量评级
- 多轮完整草稿与 UNION 合并
- 引用校验与冲突处理
- 即用型报告模板与格式规则

**示例用法：**
```bash
# 安装技能
claude plugin install deep-research@daymade-skills

# 然后提供报告规格或模板并请求生成调研报告
```

**🎬 实时演示**

*即将推出*

📚 **文档**：参见 [deep-research/SKILL.md](./deep-research/SKILL.md) 与 [deep-research/references/research_report_template.md](./deep-research/references/research_report_template.md) 了解工作流程与结构。

**要求**：无

---

### 35. **competitors-analysis** - 证据驱动的竞品追踪

基于证据的竞品仓库分析。所有分析必须基于实际克隆的代码，禁止任何推测。

**使用场景：**
- 追踪和分析竞品产品或技术
- 创建基于证据的竞品档案
- 生成竞争分析报告
- 需要以引用来源记录技术决策

**主要功能：**
- 分析前检查清单，确保仓库已本地克隆
- 禁止模式以防止假设（"推测..."、"可能..."、"应该..."）
- 必须的引用格式（文件:行号）
- 支持 Node.js、Python、Rust 项目的技术栈分析指南
- 目录结构规范用于组织竞品追踪
- 内置模板：竞品档案模板、分析检查清单
- 管理脚本用于批量克隆/拉取/状态检查操作

**示例用法：**
```bash
# 安装技能
claude plugin install competitors-analysis@daymade-skills

# 然后让 Claude 分析竞品
"分析竞品 https://github.com/org/repo"
"添加竞品到 flowzero 产品的竞品列表"
```

**🎬 实时演示**

*即将推出*

📚 **文档**：参见 [competitors-analysis/SKILL.md](./competitors-analysis/SKILL.md) 与 [competitors-analysis/references/](./competitors-analysis/references/) 了解模板。

**要求**：Git（用于克隆仓库）

---

### 36. **tunnel-doctor** - Tailscale + 代理/VPN 路由冲突修复

诊断和修复 macOS 上 Tailscale 与代理/VPN 工具（Shadowrocket、Clash、Surge）的路由冲突，特别针对 SSH 访问 WSL 实例的场景。

**使用场景：**
- Tailscale ping 正常但 SSH/TCP 连接超时
- 代理工具劫持了 Tailscale CGNAT 网段（100.64.0.0/10）
- 设置 Tailscale SSH 到 WSL 时遇到 `operation not permitted`
- 需要让 Tailscale 和 Shadowrocket/Clash/Surge 在 macOS 上共存

**主要功能：**
- 6 步诊断流程：从症状识别到端到端验证
- Root cause 分析：`tun-excluded-routes` 添加冲突的 `en0` 系统路由
- 针对 Shadowrocket、Clash、Surge 的逐工具修复指南
- Tailscale SSH ACL 配置（`check` vs `accept`）
- WSL snap vs apt 安装 Tailscale（snap 沙箱导致 SSH 失败）
- Shadowrocket 配置 API 用于自动化配置

**示例用法：**
```bash
# 安装技能
claude plugin install tunnel-doctor@daymade-skills

# 然后让 Claude 诊断
"Tailscale ping 正常但 SSH 超时"
"修复 macOS 上 Tailscale 和 Shadowrocket 的路由冲突"
"设置 Tailscale SSH 到我的 WSL 实例"
```

**🎬 实时演示**

*即将推出*

📚 **文档**：参见 [tunnel-doctor/references/proxy_fixes.md](./tunnel-doctor/references/proxy_fixes.md) 了解各工具修复指南。

---

## 🎬 交互式演示画廊

想要在一个地方查看所有演示并具有点击放大功能？访问我们的[交互式演示画廊](./demos/index.html)或浏览[演示目录](./demos/)。

## 🎯 使用场景

### GitHub 工作流
使用 **github-ops** 简化 PR 创建、问题管理和 API 操作。

### 文档处理
结合 **markdown-tools** 进行文档转换和 **mermaid-tools** 进行图表生成，创建全面的文档。使用 **llm-icon-finder** 添加品牌图标。

### 调研与分析
使用 **deep-research** 生成格式可控的调研报告，包含证据表与引用。与 **fact-checker** 结合用于验证关键结论，或与 **twitter-reader** 结合收集社媒资料。

### 竞争情报
使用 **competitors-analysis** 以证据驱动的方法追踪和分析竞品仓库。所有发现都来自实际代码（文件:行号），杜绝臆测。与 **deep-research** 结合生成全面的竞争格局报告。

### PDF 与可打印文档
使用 **pdf-creator** 将 markdown 转换为适合打印的 PDF，并提供中文字体支持，适用于正式报告和归档材料。

### 团队通信
使用 **teams-channel-post-writer** 分享知识，使用 **statusline-generator** 在工作时跟踪成本。

### 仓库管理与安全
使用 **repomix-unmixer** 提取和验证 repomix 打包的技能或仓库。使用 **repomix-safe-mixer** 安全地打包代码库，在分发前自动检测和阻止硬编码凭据。

### 技能开发
使用 **skill-creator**（参见上面的[必备技能](#-必备技能skill-creator)部分）构建、验证和打包你自己的 Claude Code 技能，遵循最佳实践。

### 演示文稿与商务沟通
使用 **ppt-creator** 生成具有数据可视化、结构化叙事和完整 PPTX 输出的专业幻灯片，用于推介、评审和主题演讲。

### 视频质量分析
使用 **video-comparer** 分析压缩结果、评估编解码器性能并生成交互式比较报告。与 **youtube-downloader** 结合使用以比较不同质量的下载。

### 媒体与内容下载
使用 **youtube-downloader** 下载 YouTube 视频并从视频中提取音频，自动解决常见下载问题。

### 转录与 ASR 校正
使用 **transcript-fixer** 通过基于字典的规则和 AI 驱动的校正自动学习，纠正会议记录、讲座和访谈中的语音转文本错误。

### 会议文档
使用 **meeting-minutes-taker** 将原始会议转写稿转换为结构化、基于证据的会议纪要。与 **transcript-fixer** 结合使用可在生成纪要前清理 ASR 错误。特点是多轮生成配合 UNION 合并以避免内容丢失。

### QA 测试与质量保证
使用 **qa-expert** 建立具有自主 LLM 执行、Google 测试标准和 OWASP 安全测试的综合 QA 测试基础设施。非常适合项目启动、第三方 QA 交接和执行质量门禁（100% 执行、≥80% 通过率、0 个 P0 错误）。主提示可实现 100 倍更快的测试执行，零跟踪错误。

### 提示词工程与需求工程
使用 **prompt-optimizer** 将模糊的功能请求转换为具有领域理论基础的精确 EARS 规范。非常适合产品需求文档、AI 辅助编码和学习提示词工程最佳实践。与 **skill-creator** 结合使用以创建结构良好的技能提示，或与 **ppt-creator** 结合使用以确保演示内容需求清晰明确。

### 会话历史与文件恢复
使用 **claude-code-history-files-finder** 从之前的 Claude Code 会话中恢复已删除的文件、在对话历史中搜索特定实现，或跟踪文件随时间的演变。对于恢复意外删除的代码或查找你记得但找不到的功能实现至关重要。

### 文档维护
使用 **docs-cleaner** 在保留有价值内容的同时整合冗余文档。非常适合在快速开发阶段后清理文档扩散或将重叠的文档合并为权威来源。

### CLAUDE.md 优化
使用 **claude-md-progressive-disclosurer** 通过渐进式披露减少 CLAUDE.md 体积，同时保留关键规则。

### LLM 评测与模型对比
使用 **promptfoo-evaluation** 运行提示词测试、对比模型输出并执行自定义断言评测。

### iOS 应用开发
使用 **iOS-APP-developer** 配置 XcodeGen 项目，处理 SPM 依赖、签名与部署问题。

### Twitter/X 内容研究
使用 **twitter-reader** 无需 JavaScript 渲染或身份验证即可获取推文内容。非常适合记录社交媒体讨论、归档话题、分析推文内容或从 Twitter/X 收集参考资料。与 **markdown-tools** 结合可将获取的内容转换为其他格式，或与 **repomix-safe-mixer** 结合安全地打包研究集合。

### macOS 系统维护与磁盘空间恢复
使用 **macos-cleaner** 以安全优先的方式智能分析和恢复 macOS 上的磁盘空间。与盲目删除的一键清理工具不同，macos-cleaner 解释每个文件是什么、按风险级别分类（🟢/🟡/🔴），并在任何删除前需要明确确认。非常适合处理 Docker/Homebrew/npm/pip 缓存膨胀的开发者、希望了解存储空间消耗的用户，或任何重视透明度而非自动化的人。结合基于脚本的精度和可选的 Mole 可视化工具集成以实现混合工作流。

### 技能发现与管理
使用 **skills-search** 从 CCPM 注册表中查找、安装和管理 Claude Code 技能。非常适合为特定任务发现新技能、为常见工作流安装技能包，以及保持技能集合的有序管理。

### 技能质量与开源贡献
使用 **skill-reviewer** 在发布前验证你的技能是否符合最佳实践，或审查并改进他人的技能仓库。与 **github-contributor** 结合使用，寻找高影响力的开源项目、创建专业的 PR，并系统性地建立贡献者声誉。非常适合希望为 Claude Code 生态系统或任何 GitHub 项目做出贡献的开发者。

### 国际化与本地化
使用 **i18n-expert** 为 React/Next.js/Vue 应用程序设置完整的 i18n 基础设施、审计现有实现中缺失的翻译键，并确保 en-US 和 zh-CN 之间的语言环境一致性。非常适合向全球市场推出产品的团队、维护多语言 UI，或将硬编码字符串替换为正确的 i18n 键。与 **skill-creator** 结合使用可创建支持语言环境的技能，或与 **docs-cleaner** 结合使用可整合多种语言的文档。

### 网络与 VPN 故障排查
使用 **tunnel-doctor** 诊断和修复 macOS 上 Tailscale 与代理/VPN 工具的路由冲突。当 Tailscale ping 正常但 TCP 连接失败，或在使用 Shadowrocket、Clash、Surge 的同时设置 Tailscale SSH 到 WSL 实例时特别有用。

### 插件与技能故障排除
使用 **claude-skills-troubleshooting** 诊断和解决 Claude Code 插件和技能配置问题。调试为什么插件显示已安装但未显示在可用技能列表中、了解 installed_plugins.json 与 settings.json enabledPlugins 架构，以及批量启用市场中缺失的插件。非常适合市场维护者调试安装问题、开发者调试技能激活，或任何对 GitHub #17832 自动启用 bug 感到困惑的人。

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
- **ppt-creator**：参见 `ppt-creator/references/WORKFLOW.md` 了解 9 阶段创建流程和 `ppt-creator/references/ORCHESTRATION_OVERVIEW.md` 了解自动化
- **youtube-downloader**：参见 `youtube-downloader/SKILL.md` 了解使用示例和故障排除
- **repomix-safe-mixer**：参见 `repomix-safe-mixer/references/common_secrets.md` 了解检测到的凭据模式
- **video-comparer**：参见 `video-comparer/references/video_metrics.md` 了解质量指标解释和 `video-comparer/references/configuration.md` 了解自定义选项
- **transcript-fixer**：参见 `transcript-fixer/references/workflow_guide.md` 了解分步工作流和 `transcript-fixer/references/team_collaboration.md` 了解协作模式
- **qa-expert**：参见 `qa-expert/references/master_qa_prompt.md` 了解自主执行（100 倍加速）和 `qa-expert/references/google_testing_standards.md` 了解 AAA 模式和 OWASP 测试
- **prompt-optimizer**：参见 `prompt-optimizer/references/ears_syntax.md` 了解 EARS 转换模式、`prompt-optimizer/references/domain_theories.md` 了解理论目录和 `prompt-optimizer/references/examples.md` 了解完整转换示例
- **claude-code-history-files-finder**：参见 `claude-code-history-files-finder/references/session_file_format.md` 了解 JSONL 结构和 `claude-code-history-files-finder/references/workflow_examples.md` 了解恢复工作流
- **docs-cleaner**：参见 `docs-cleaner/SKILL.md` 了解整合工作流
- **deep-research**：参见 `deep-research/references/research_report_template.md` 了解报告结构，并参见 `deep-research/references/source_quality_rubric.md` 了解来源分级标准
- **pdf-creator**：参见 `pdf-creator/SKILL.md` 了解 PDF 转换与字体设置
- **claude-md-progressive-disclosurer**：参见 `claude-md-progressive-disclosurer/SKILL.md` 了解 CLAUDE.md 优化工作流
- **skills-search**：参见 `skills-search/SKILL.md` 了解 CCPM CLI 命令和注册表操作
- **promptfoo-evaluation**：参见 `promptfoo-evaluation/references/promptfoo_api.md` 了解评测模式
- **iOS-APP-developer**：参见 `iOS-APP-developer/references/xcodegen-full.md` 了解 XcodeGen 选项与 project.yml 细节
- **twitter-reader**：参见 `twitter-reader/SKILL.md` 了解 API 密钥设置和 URL 格式支持
- **macos-cleaner**：参见 `macos-cleaner/references/cleanup_targets.md` 了解详细清理目标说明、`macos-cleaner/references/mole_integration.md` 了解 Mole 可视化工具集成、`macos-cleaner/references/safety_rules.md` 了解全面安全指南
- **skill-reviewer**：参见 `skill-reviewer/references/evaluation_checklist.md` 了解完整评估标准、`skill-reviewer/references/pr_template.md` 了解 PR 模板、`skill-reviewer/references/marketplace_template.json` 了解 marketplace 配置
- **github-contributor**：参见 `github-contributor/references/pr_checklist.md` 了解 PR 质量清单、`github-contributor/references/project_evaluation.md` 了解项目评估标准、`github-contributor/references/communication_templates.md` 了解 issue/PR 沟通模板
- **i18n-expert**：参见 `i18n-expert/SKILL.md` 了解完整的 i18n 设置工作流程、键架构指导和审计程序
- **claude-skills-troubleshooting**：参见 `claude-skills-troubleshooting/SKILL.md` 了解插件故障排除工作流程和架构
- **fact-checker**：参见 `fact-checker/SKILL.md` 了解事实核查工作流程和声明验证过程
- **competitors-analysis**：参见 `competitors-analysis/SKILL.md` 了解证据驱动的分析工作流程和 `competitors-analysis/references/profile_template.md` 了解竞品档案模板

## 🛠️ 系统要求

- **Claude Code** 2.0.13 或更高版本
- **Python 3.6+**（用于多个技能中的脚本）
- **gh CLI**（用于 github-ops）
- **markitdown**（用于 markdown-tools）
- **mermaid-cli**（用于 mermaid-tools）
- **VHS**（用于 cli-demo-generator）：`brew install vhs`
- **asciinema**（可选，用于 cli-demo-generator 交互式录制）
- **ccusage**（可选，用于状态栏成本跟踪）
- **yt-dlp**（用于 youtube-downloader）：`brew install yt-dlp` 或 `pip install yt-dlp`
- **FFmpeg/FFprobe**（用于 video-comparer）：`brew install ffmpeg`、`apt install ffmpeg` 或 `winget install ffmpeg`
- **weasyprint、markdown**（用于 pdf-creator）
- **CCPM CLI**（用于 skills-search）：`npm install -g @daymade/ccpm`
- **Promptfoo**（用于 promptfoo-evaluation）：`npx promptfoo@latest`
- **macOS + Xcode、XcodeGen**（用于 iOS-APP-developer）
- **Jina.ai API 密钥**（用于 twitter-reader）：https://jina.ai/ 提供免费套餐
- **Mole**（可选，用于 macos-cleaner 可视化清理）：从 https://github.com/tw93/Mole 下载

## ❓ 常见问题

### 我如何知道应该安装哪些技能？

如果你想创建自己的技能，从 **skill-creator** 开始。否则，浏览[其他可用技能](#-其他可用技能)部分，安装与你的工作流匹配的技能。

### 没有 Claude Code 可以使用这些技能吗？

不可以，这些技能是专门为 Claude Code 设计的。你需要 Claude Code 2.0.13 或更高版本。

### 如何更新技能？

使用相同的安装命令进行更新：
```bash
claude plugin install skill-name@daymade-skills
```

### 我可以贡献自己的技能吗？

当然可以！查看 [CONTRIBUTING.md](./CONTRIBUTING.md) 了解指南。我们建议使用 skill-creator 来确保你的技能符合质量标准。

### 这些技能使用安全吗？

是的，所有技能都是开源的并经过审查。代码可在此仓库中查看。

### 中国用户如何处理 API 访问？

我们建议使用 [CC-Switch](https://github.com/farion1231/cc-switch) 来管理 API 提供商配置。查看上面的[中国用户指南](#-中国用户指南)部分。

### skill-creator 和其他技能有什么区别？

**skill-creator** 是一个元技能 - 它帮助你创建其他技能。其他技能是面向最终用户的技能，提供特定功能（GitHub 操作、文档转换等）。如果你想用自己的工作流扩展 Claude Code，从 skill-creator 开始。

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

最后更新：2026-01-22 | 市场版本 1.23.0
