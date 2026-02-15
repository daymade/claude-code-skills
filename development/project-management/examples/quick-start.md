# Project Management Framework - Quick Start Guide

> **快速开始指南** - 5分钟内设置专业项目管理框架

---

## 🚀 场景 1: 新项目初始化

### 用户请求

```
"帮我创建一个新项目 DataPipeline，使用 Python，需要专业的项目管理框架"
```

### Skill 执行流程

#### 步骤 1: 收集信息

Skill 会询问:
1. **项目描述** (可选): "数据处理和 ETL 管道"
2. **项目类型** (自动检测或手动): api
3. **Git 用户信息** (自动获取): 从 ~/.gitconfig 读取
4. **CI/CD 配置** (默认: true): 是
5. **阶段数量** (默认: 5): 5

#### 步骤 2: 创建项目结构

```bash
# 自动执行
mkdir -p ~/DataPipeline
cd ~/DataPipeline

# Git 初始化
git init
git config user.name "Your Name"
git config user.email "your.email@example.com"

# 创建目录结构
mkdir -p docs/{project,phases/{phase1,phase2,phase3,phase4,phase5},guides,api,reports}
mkdir -p src/{python/{core,utils,tests/{unit,integration,performance}},templates}
mkdir -p scripts/{verify,setup,maintenance}
mkdir -p milestones/{phase1,phase2,phase3,phase4,phase5}
mkdir -p config
mkdir -p .github/workflows
```

#### 步骤 3: 生成文件

```bash
# 生成核心文件
- .gitignore (安全优先)
- README.md (项目文档)
- CHANGELOG.md (变更日志)
- CONTRIBUTING.md (贡献指南)

# 生成里程碑追踪
- docs/project/MILESTONES.md
- docs/project/TIMELINE.md
- docs/project/PROJECT_STATE.md
- docs/project/DOCUMENTATION_INDEX.md

# 生成验证脚本
- scripts/verify/verify_milestone.py (可执行)
- scripts/verify/run_tests.sh (可执行)

# 生成 CI/CD 工作流
- .github/workflows/test.yml
- .github/workflows/milestone-check.yml
- .github/workflows/security-scan.yml
```

#### 步骤 4: 初始提交

```bash
git add .
git commit -m "feat: initialize DataPipeline project with professional PM framework

- Set up Git repository with secure .gitignore
- Create professional directory structure
- Initialize milestone tracking system (5 phases)
- Generate verification scripts
- Configure CI/CD workflows

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

# 创建分支
git checkout -b develop
```

#### 步骤 5: 输出总结报告

```
=== Project Management Framework Initialization Summary ===

Project: DataPipeline
Date: 2026-02-15
Type: api
Language: python

✅ Git Repository: Initialized
✅ Directory Structure: Created
✅ Milestone Tracking: Configured (5 phases)
✅ Verification Scripts: Generated
✅ CI/CD Workflows: Configured

Files Created: 25
Lines of Code: ~3,500
Directories Created: 30

Next Steps:
1. Review MILESTONES.md and customize phases
2. Update PROJECT_STATE.md with current status
3. Run: python scripts/verify/verify_milestone.py --phase 1
4. Commit and push to remote repository

Documentation: docs/project/DOCUMENTATION_INDEX.md
```

---

## 🔄 场景 2: 现有项目升级

### 用户请求

```
"为现有项目 OldProject 添加专业项目管理框架"
```

### Skill 执行流程

#### 步骤 1: 分析现有项目

```bash
# 自动执行
cd ~/OldProject

# 检测项目类型
# - 扫描文件扩展名 (.py, .js, .go 等)
# - 检测目录结构
# - 识别已有文件
```

#### 步骤 2: 创建备份

```bash
# 自动执行
BACKUP_DIR="~/OldProject-backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"
cp -r . "$BACKUP_DIR/"

echo "备份已创建: $BACKUP_DIR"
```

#### 步骤 3: 初始化 Git (如果需要)

```bash
# 检查是否已有 Git 仓库
if [ ! -d .git ]; then
    git init
    git config user.name "Your Name"
    git config user.email "your.email@example.com"
fi
```

#### 步骤 4: 创建新目录结构

```bash
# 创建专业目录（不覆盖现有文件）
mkdir -p docs/project
mkdir -p docs/phases/{phase1,phase2,phase3,phase4,phase5}
mkdir -p scripts/verify
mkdir -p .github/workflows
# ... 其他目录
```

#### 步骤 5: 生成新文件

```bash
# 生成框架文件（不覆盖现有文件）
- .gitignore (如果不存在)
- docs/project/MILESTONES.md
- docs/project/TIMELINE.md
- scripts/verify/verify_milestone.py
- .github/workflows/*.yml
```

#### 步骤 6: 可选 - 重组现有文件

```bash
# 如果用户选择 reorganize_existing=true
# 创建映射规则
src/*.py -> src/python/core/
test/*.py -> src/python/tests/unit/
docs/*.md -> docs/guides/

# 执行移动（需要用户确认）
```

#### 步骤 7: 输出迁移报告

```
=== Project Migration Report ===

Project: OldProject
Backup: ~/OldProject-backup-20260215-123456

Files Migrated: 15
Files Conflicts: 2
Directories Created: 25

Migration Log:
- data_processor.py -> src/python/core/data_processor.py
- test_utils.py -> src/python/tests/unit/test_utils.py
- README.md (冲突，已跳过)
- config.json -> config/development.json

Review Needed:
- Check file imports (3 files)
- Update configuration paths (2 files)
- Verify test references (5 files)

Next Steps:
1. Review migrated files
2. Update imports and references
3. Run tests to verify
4. Commit changes

Backup Location: ~/OldProject-backup-20260215-123456
```

---

## 🎨 场景 3: 自定义配置

### 用户请求

```
"创建项目 MLModel，3 个阶段，自定义目录结构"
```

### Skill 执行流程

#### 步骤 1: 收集自定义配置

Skill 会询问:
1. **项目名称**: MLModel
2. **项目描述**: 机器学习模型训练
3. **项目类型**: ml
4. **编程语言**: python
5. **阶段数量**: 3
6. **自定义目录**: ["data", "models", "notebooks", "experiments"]
7. **阶段名称**: ["Data Preparation", "Model Training", "Deployment"]

#### 步骤 2: 生成自定义结构

```bash
# 创建自定义目录
mkdir -p data/{raw,processed,features}
mkdir -p models/{checkpoints,exported}
mkdir -p notebooks/{exploratory,experiments}
mkdir -p experiments/{runs,logs}

# 创建标准目录
mkdir -p docs/project
mkdir -p src/python/{core,utils,models}
mkdir -p scripts/{train,evaluate,deploy}
# ... 其他标准目录
```

#### 步骤 3: 生成自定义里程碑

```markdown
# MILESTONES.md (自定义)

| M1 | Data Preparation | Phase 1 | 🔄 未开始 | - | 0% |
| M2 | Model Training | Phase 2 | 🔄 未开始 | - | 0% |
| M3 | Deployment | Phase 3 | 🔄 未开始 | - | 0% |
```

#### 步骤 4: 输出总结

```
=== Custom Project Initialization Summary ===

Project: MLModel
Custom Configuration: 3 phases, 4 custom directories

Phases:
1. Data Preparation
2. Model Training
3. Deployment

Custom Directories:
- data/ (raw, processed, features)
- models/ (checkpoints, exported)
- notebooks/ (exploratory, experiments)
- experiments/ (runs, logs)

Files Created: 23
Custom Directories Created: 12

Next Steps:
1. Review custom structure
2. Define phase-specific tasks
3. Set up data pipelines
4. Start model development
```

---

## 📋 常见使用模式

### 模式 1: 快速原型

```
"创建原型项目 Prototype，快速开始开发"
```

- 默认配置
- 3 个阶段
- 跳过 CI/CD (可选)
- 快速迭代

### 模式 2: 生产级项目

```
"创建生产级项目 ProductionApp，完整 CI/CD"
```

- 完整配置
- 5 个阶段
- 完整 CI/CD
- 安全扫描
- 性能测试

### 模式 3: 团队协作项目

```
"创建团队项目 TeamApp，多人协作"
```

- 详细的贡献指南
- 代码审查配置
- 文档完善
- 沟通机制

### 模式 4: 开源项目

```
"创建开源项目 OpenLib，准备发布"
```

- LICENSE 文件
- CONTRIBUTING.md 详尽
- README.md 完整
- 问题模板
- PR 模板

---

## ✅ 验证安装

### 检查 Git 仓库

```bash
cd ~/YourProject
git status
# 应该显示: On branch main (或 develop)
```

### 检查目录结构

```bash
ls -la
# 应该包含: docs/, src/, scripts/, milestones/, .github/

tree docs/project/
# 应该包含: MILESTONES.md, TIMELINE.md, PROJECT_STATE.md
```

### 检查验证脚本

```bash
python scripts/verify/verify_milestone.py --phase 1
# 应该运行并输出验证结果
```

### 检查 CI/CD 配置

```bash
ls -la .github/workflows/
# 应该包含: test.yml, milestone-check.yml, security-scan.yml
```

---

## 🎯 下一步行动

### 立即执行

1. **自定义里程碑**
   ```bash
   vim docs/project/MILESTONES.md
   # 编辑阶段名称、任务、验证标准
   ```

2. **更新项目状态**
   ```bash
   vim docs/project/PROJECT_STATE.md
   # 添加当前项目信息
   ```

3. **运行验证**
   ```bash
   python scripts/verify/verify_milestone.py --phase 1
   ```

4. **提交到远程**
   ```bash
   git remote add origin <your-repo-url>
   git push -u origin main develop
   ```

### 短期任务 (本周)

1. [ ] 定义 Phase 1 具体任务
2. [ ] 设置开发环境
3. [ ] 编写第一个功能
4. [ ] 编写第一个测试
5. [ ] 更新文档

### 中期任务 (本月)

1. [ ] 完成 Phase 1
2. [ ] 代码审查
3. [ ] 性能优化
4. [ ] 开始 Phase 2

---

## 🔧 故障排除

### Git 初始化失败

```bash
# 检查 Git 是否安装
git --version

# 配置 Git
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

### 验证脚本失败

```bash
# 检查 Python 环境
python3 --version

# 安装依赖
pip install pytest pytest-cov coverage bandit flake8
```

### CI/CD 工作流不运行

```bash
# 推送到 GitHub
git push -u origin main develop

# 检查 GitHub Actions 标签页
# https://github.com/yourusername/yourrepo/actions
```

---

## 📚 更多资源

### 文档

- [完整文档](README.md)
- [配置选项](README.md#configuration)
- [最佳实践](README.md#best-practices)

### 示例

- [新项目示例](#场景-1-新项目初始化)
- [现有项目升级](#场景-2-现有项目升级)
- [自定义配置](#场景-3-自定义配置)

### 相关技能

- [code-reviewer](../code-reviewer/) - 代码质量审查
- [test-generator](../test-generator/) - 测试生成
- [security-auditor](../security-auditor/) - 安全审计

---

**最后更新**: {{TODAY_DATE}}
**维护者**: Claude Code Team
**状态**: 生产就绪 ✅
