---
name: competitors-analysis
description: Analyze competitor repositories with evidence-based approach. Use when tracking competitors, creating competitor profiles, or generating competitive analysis. CRITICAL - all analysis must be based on actual cloned code, never assumptions. Triggers include "analyze competitor", "add competitor", "competitive analysis", or "竞品分析".
context: fork
agent: general-purpose
allowed-tools: Read, Grep, Glob, Bash(git *), Bash(mkdir *), Bash(ls *), Bash(wc *)
argument-hint: [product-name] [competitor-url]
---

# Competitors Analysis

Evidence-based competitor tracking and analysis. **All analysis must be based on actual code, never assumptions.**

## CRITICAL: Evidence-Based Analysis Only

**在开始分析之前，必须完成以下检查：**

### Pre-Analysis Checklist

- [ ] 仓库已克隆到本地 `~/Workspace/competitors/{product}/`
- [ ] 可以 `ls` 查看目录结构
- [ ] 可以 `cat package.json` (或等效配置文件) 读取版本信息
- [ ] 可以 `git log -1` 确认代码是最新的

**如果以上任何一项未完成，停止分析，先完成克隆操作。**

### Forbidden Patterns (禁止的表述)

| 禁止 | 原因 |
|------|------|
| "推测..."、"可能..."、"应该..." | 没有证据支持 |
| "架构图（推测版）" | 必须基于实际代码 |
| "未公开"、"未披露" | 如果不知道就不要写 |
| 不带来源的技术细节 | 无法验证 |

### Required Patterns (必须的表述)

| 正确格式 | 示例 |
|----------|------|
| 技术细节 + (来源: 文件:行号) | "使用 better-sqlite3 (来源: package.json:88)" |
| 直接引用 + 来源 | `> "description text" (README.md:3)` |
| 版本号 + 来源 | "版本 1.3.3 (package.json:2)" |

---

## Analysis Workflow

### Step 1: Clone Repository (必须)

```bash
# 创建产品竞品目录
mkdir -p ~/Workspace/competitors/{product-name}

# 克隆竞品仓库 (SSH，失败则重试)
cd ~/Workspace/competitors/{product-name}
git clone git@github.com:org/repo.git
```

**网络问题处理**: 中国网络环境可能需要多次重试。

### Step 2: Gather Facts (收集事实)

按顺序读取以下文件，记录关键信息：

**2.1 项目元数据**
```bash
# Node.js 项目
cat package.json | head -20      # name, version, description
cat package.json | grep -A50 dependencies

# Python 项目
cat pyproject.toml               # 或 setup.py, requirements.txt

# Rust 项目
cat Cargo.toml
```

**2.2 项目结构**
```bash
ls -la                           # 根目录结构
ls src/                          # 源码目录
find . -name "*.md" -maxdepth 2  # 文档文件
```

**2.3 核心模块**
```bash
# 找到入口文件
cat main.js | head -50           # 或 index.js, app.py, main.rs
# 找到核心 helpers/utils
ls src/helpers/ 2>/dev/null || ls src/utils/ 2>/dev/null
```

**2.4 README 和文档**
```bash
cat README.md | head -100        # 官方描述
cat CHANGELOG.md | head -50      # 版本历史
```

### Step 3: Deep Dive (深入分析)

针对关键技术点，读取具体实现文件：

```bash
# 示例：分析 ASR 实现
cat src/helpers/whisper.js       # 读取完整文件
grep -n "class.*Manager" src/helpers/*.js  # 找到核心类
```

**记录格式**:
```
| 文件 | 行号 | 发现 |
|------|------|------|
| whisper.js | 33-35 | 使用 WhisperServerManager |
```

### Step 4: Write Profile (撰写分析)

使用 [references/profile_template.md](references/profile_template.md) 模板，确保每个技术细节都有来源标注。

### Step 5: Post-Analysis Verification (分析后验证)

**自检清单**:

- [ ] 所有版本号都有来源标注？
- [ ] 所有技术栈都来自 package.json/Cargo.toml？
- [ ] 架构描述基于实际代码结构？
- [ ] 没有"推测"、"可能"等词汇？
- [ ] 对比表中的竞品数据都有来源？

---

## Directory Structure

```
~/Workspace/competitors/
├── flowzero/              # Flowzero 的竞品
│   ├── openwhispr/        # git clone 的仓库
│   └── ...
└── {product-name}/        # 其他产品

{project}/docs/competitors/
├── README.md              # 索引（标注分析状态）
├── profiles/
│   └── {competitor}.md    # 基于代码的分析
├── landscape/
├── insights/
└── updates/2026/
```

---

## Templates and Checklists

| 文档 | 用途 |
|------|------|
| [references/profile_template.md](references/profile_template.md) | 竞品分析报告模板 |
| [references/analysis_checklist.md](references/analysis_checklist.md) | 分析前/中/后检查清单 |

**关键要求**:
1. 顶部必须标注数据来源路径和 commit hash
2. 每个技术细节必须有 (来源: 文件:行号)
3. 引用 README 内容必须标注行号
4. 无法验证的标记为"待验证"并说明原因
5. 分析完成后运行检查清单中的验证命令

---

## Tech Stack Analysis Guide

### Node.js / JavaScript

| 信息 | 来源文件 | 关键字段 |
|------|----------|----------|
| 版本 | package.json | `version` |
| 依赖 | package.json | `dependencies`, `devDependencies` |
| 入口 | package.json | `main`, `scripts.start` |
| 框架 | package.json | electron, react, vite 等 |

### Python

| 信息 | 来源文件 | 关键字段 |
|------|----------|----------|
| 版本 | pyproject.toml | `[project].version` |
| 依赖 | pyproject.toml / requirements.txt | `dependencies` |
| 入口 | pyproject.toml | `[project.scripts]` |

### Rust

| 信息 | 来源文件 | 关键字段 |
|------|----------|----------|
| 版本 | Cargo.toml | `[package].version` |
| 依赖 | Cargo.toml | `[dependencies]` |

---

## Common Mistakes to Avoid

### 1. 跳过克隆直接分析

❌ 错误: 从 GitHub 网页或 WebFetch 获取信息后直接写分析
✅ 正确: 必须 `git clone` 到本地，用 `Read` 工具读取文件

### 2. 混合事实和推测

❌ 错误:
```markdown
## 技术栈
- Electron (推测基于桌面应用特征)
- 可能使用了 React
```

✅ 正确:
```markdown
## 技术栈 (来源: package.json)
| 依赖 | 版本 | 来源 |
|------|------|------|
| electron | 36.9.5 | package.json:68 |
| react | 19.1.0 | package.json:96 |
```

### 3. 使用过时信息

❌ 错误: 分析时不检查 git log，使用过时的代码
✅ 正确: 分析前运行 `git pull`，记录分析时的 commit hash

### 4. 对比表中竞品数据无来源

❌ 错误:
```markdown
| 维度 | 竞品 | 我们 |
|------|------|------|
| 支持语言 | 25种 | 58种 |
```

✅ 正确:
```markdown
| 维度 | 竞品 | 来源 | 我们 |
|------|------|------|------|
| 支持语言 | 25种 | modelRegistryData.json:9-35 | 58种 (FunASR 官方文档) |
```

---

## Scripts

See [scripts/update-competitors.sh](scripts/update-competitors.sh) for repository management.

```bash
./scripts/update-competitors.sh clone   # 克隆所有竞品
./scripts/update-competitors.sh pull    # 更新所有竞品
./scripts/update-competitors.sh status  # 检查状态
```
