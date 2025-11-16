# Claude Code 技能市场

<div align="center">

[![English](https://img.shields.io/badge/Language-English-blue)](./README.md)
[![简体中文](https://img.shields.io/badge/语言-简体中文-red)](./README.zh-CN.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Skills](https://img.shields.io/badge/skills-18-blue.svg)](https://github.com/daymade/claude-code-skills)
[![Version](https://img.shields.io/badge/version-1.11.0-green.svg)](https://github.com/daymade/claude-code-skills)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-2.0.13+-purple.svg)](https://claude.com/code)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](./CONTRIBUTING.md)
[![Maintenance](https://img.shields.io/badge/Maintained%3F-yes-green.svg)](https://github.com/daymade/claude-code-skills/graphs/commit-activity)

</div>

专业的 Claude Code 技能市场，提供 18 个生产就绪的技能，用于增强开发工作流。

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
claude plugin marketplace add daymade/claude-code-skills
claude plugin install skill-creator@daymade/claude-code-skills
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
claude plugin install skill-creator@daymade/claude-code-skills
```

**安装其他技能：**
```bash
# GitHub 操作
claude plugin install github-ops@daymade/claude-code-skills

# 文档转换
claude plugin install markdown-tools@daymade/claude-code-skills

# 图表生成
claude plugin install mermaid-tools@daymade/claude-code-skills

# 状态栏定制
claude plugin install statusline-generator@daymade/claude-code-skills

# Teams 通信
claude plugin install teams-channel-post-writer@daymade/claude-code-skills

# Repomix 提取
claude plugin install repomix-unmixer@daymade/claude-code-skills

# AI/LLM 图标
claude plugin install llm-icon-finder@daymade/claude-code-skills

# CLI 演示生成
claude plugin install cli-demo-generator@daymade/claude-code-skills

# YouTube 视频/音频下载
claude plugin install youtube-downloader@daymade/claude-code-skills

# 视频比较和质量分析
claude plugin install video-comparer@daymade/claude-code-skills

# QA 测试基础设施和自主执行
claude plugin install qa-expert@daymade/claude-code-skills

# 使用 EARS 方法论优化提示词
claude plugin install prompt-optimizer@daymade/claude-code-skills
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
- 视频和播放列表下载
- 仅音频下载并转换为 MP3
- Android 客户端绕过 nsig 提取问题（自动）
- 格式列表和自定义格式选择
- 代理/受限环境的网络错误处理
- 常见 yt-dlp 问题的综合故障排除

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

## 🎬 交互式演示画廊

想要在一个地方查看所有演示并具有点击放大功能？访问我们的[交互式演示画廊](./demos/index.html)或浏览[演示目录](./demos/)。

## 🎯 使用场景

### GitHub 工作流
使用 **github-ops** 简化 PR 创建、问题管理和 API 操作。

### 文档处理
结合 **markdown-tools** 进行文档转换和 **mermaid-tools** 进行图表生成，创建全面的文档。使用 **llm-icon-finder** 添加品牌图标。

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

### QA 测试与质量保证
使用 **qa-expert** 建立具有自主 LLM 执行、Google 测试标准和 OWASP 安全测试的综合 QA 测试基础设施。非常适合项目启动、第三方 QA 交接和执行质量门禁（100% 执行、≥80% 通过率、0 个 P0 错误）。主提示可实现 100 倍更快的测试执行，零跟踪错误。

### 提示词工程与需求工程
使用 **prompt-optimizer** 将模糊的功能请求转换为具有领域理论基础的精确 EARS 规范。非常适合产品需求文档、AI 辅助编码和学习提示词工程最佳实践。与 **skill-creator** 结合使用以创建结构良好的技能提示，或与 **ppt-creator** 结合使用以确保演示内容需求清晰明确。

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

## ❓ 常见问题

### 我如何知道应该安装哪些技能？

如果你想创建自己的技能，从 **skill-creator** 开始。否则，浏览[其他可用技能](#-其他可用技能)部分，安装与你的工作流匹配的技能。

### 没有 Claude Code 可以使用这些技能吗？

不可以，这些技能是专门为 Claude Code 设计的。你需要 Claude Code 2.0.13 或更高版本。

### 如何更新技能？

使用相同的安装命令进行更新：
```bash
claude plugin install skill-name@daymade/claude-code-skills
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
