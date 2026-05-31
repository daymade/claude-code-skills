---
name: auto-repo-setup
description: |
  自动化代码库环境配置、故障诊断与修复。当非技术人员（剪辑、商务、运营）拿到仓库说"跑不起来"、"怎么启动"、"环境怎么配"、"帮我设置代码库"、"初始化项目"、"提交代码"、"冲突了怎么办"时，自动读取 ONBOARDING.md、诊断环境缺口、修复依赖、验证可运行，并安全地完成 git 操作。也用于技术用户快速标准化新仓库的 setup 流程（SessionStart hook、PII Guard、历史净化、项目隔离 API key）。
  只要用户提到"环境"、"配置"、"跑不起来"、"setup"、"启动"、"clone 下来"、"怎么运行"、"依赖"、"装好了吗"、"提交代码"、"merge conflict"、"push 失败"，就触发本 skill。
argument-hint: "[仓库路径]"
---

# Auto Repo Setup — 代码库自助配置与故障修复

## 概述

本 skill 让 Claude Code 成为非技术用户的"环境医生"：用户把仓库 clone 下来或打开项目后说"跑不起来"，Claude 自动按标准流程诊断、修复、验证，无需用户理解底层技术细节。

同时，本 skill 也规范了技术用户搭建可移交仓库的标准动作（ONBOARDING.md、SessionStart hook、PII 安全）。

**目标用户**：
- 主要：非技术人员（剪辑师、商务、运营）——他们不知道什么是 uv、ffmpeg、whisper.cpp
- 次要：技术用户——标准化仓库 setup 流程，降低下游维护成本

---

## 核心工作流

### Step 0: 读取项目地图

进入任何仓库后，**第一件事**是读取以下文件（按优先级）：

1. `ONBOARDING.md` — 项目专属 setup 指南（如果存在）
2. `README.md` — _fallback_
3. `CLAUDE.md` — 项目级规则（如果存在）
4. `.claude/settings.json` — 检查是否有 SessionStart hook

**如果 ONBOARDING.md 不存在**：
- 询问用户是否需要创建（基于仓库结构自动生成草稿）
- 不要在没有指南的情况下盲目猜测 setup 步骤

### Step 1: 环境审计（按 ONBOARDING.md 的验证步骤）

逐条执行 ONBOARDING.md 中的 "Step X: 验证..." 或类似章节。**每执行一条必须验证输出**，不要假设成功。

常见检查项（根据项目类型取舍）：

| 检查项 | 命令示例 | 失败处理 |
|--------|---------|---------|
| git 状态 | `git status` / `git remote -v` | 提示用户配置 git identity |
| 系统依赖 | `ffmpeg -version` / `which uv` | 按 ONBOARDING.md 安装 |
| Python 环境 | `uv --version` / `python --version` | 用 uv 创建 venv |
| 项目依赖 | `uv sync` / `uv pip install -e .` | 读取 pyproject.toml |
| 模型/二进制 | `ls models/` / `whisper.cpp/whisper-cli -h` | 按文档下载/编译 |
| 环境变量 | `cat .env` 检查 key 是否存在 | 指导用户填入或生成 |

**注意**：
- 使用 `uv` 管理 Python，**禁止**用系统自带 Python
- 所有 Python 执行必须在虚拟环境或 uv 中
- 检查命令的**退出码和 stderr**，不要只看 stdout

### Step 2: 修复迭代

**调试先根因后 workaround**（铁律）：
1. 收集证据（读日志/堆栈/配置，不猜）
2. 沿调用链定位 root cause
3. 针对根因修复
4. （可选）标注「临时」workaround 并说明为何不够

**禁止**：
- 看到报错就直接重装/重启
- 用 `rm -rf` 清理（必须分析文件用途、用户确认、创建备份）
- 静默绕过错误（`|| true`、空的 except 块）

### Step 3: 运行验证（自我验证闭环）

修复后必须验证：
- 运行 ONBOARDING.md 中的 smoke test 或测试命令
- 如果项目有 pytest，跑 `uv run pytest`（最小集合）
- 验证失败 → 回 Step 2，不要告诉用户"应该可以了"

### Step 4: 交付状态汇报

用简洁的非技术语言告诉用户：
- ✅ 已修复什么
- ⚠️ 还需要用户手动做什么（如填入个人 API key）
- 📋 接下来该运行什么命令（从 ONBOARDING.md 复制）

---

## 安全与合规铁律

### 仓库可见性检查（Push Safety）

**任何 `git push` 之前**，必须验证仓库真实可见性：

```bash
gh repo view <owner>/<repo> --json visibility,isPrivate,stargazerCount,forkCount
```

- **public + 多 stars/forks** → 默认走 PR 流程（push feature branch + `gh pr create`）
- **public + 0 stars/forks 且用户明确授权** → 可 push main，但仍需 audit 内容
- **private/internal** → push main 需用户确认，风险降一档
- **禁止凭 URL 反推可见性**，禁止在汇报里写"私人 repo"除非 API 确认 `isPrivate: true`

### PII Guard 与 Secret 管理

**public repo**（多层扫描）：
1. Layer 1 — gitleaks 标准 secret + 私有域名/IP
2. Layer 2 — 路径扫描（禁止本地生成路径）
3. Layer 3 — bash grep 兜底（中文内容、已知身份）
4. Layer 4 — AI 语义通读（前三层结构漏的无 keyword 语义私有信息）

**private repo**：
- `.env` 可直接提交（项目隔离的 API key）
- 但仍需清理**个人绝对路径**（`/Users/<name>/`）

**Git Hook Bypass 禁令**：
- ❌ Claude **禁止**主动使用 `--no-verify` / `--no-gpg-sign`
- ✅ 唯一例外：用户本人在当前 session 里**显式输入** `--no-verify`
- Hook 失败 → 修底层问题，不是绕过

### NO FALLBACK 原则

当系统无法确定一个值（从外部系统获取的关键字段），必须 fail-fast：

```python
# ❌ 禁止
apiKey: process.env.KIMI_API_KEY || 'sk-kimi-...'

# ✅ 正确
import os
api_key = os.environ["KIMI_API_KEY"]  # KeyError if missing
```

- 占位符（`"your-key-here"`）只能在 `.env.example` 里，**永不**进真实代码
- 写完 LLM/API 客户端初始化后自查：`.env` 没加载会发生什么？能看见明文吗？

---

## 标准模式

### ONBOARDING.md 模式

可移交仓库必须包含 `ONBOARDING.md`，结构：

```markdown
# 项目名 Setup 指南

## Step 1: 验证系统依赖
- [ ] git 已安装
- [ ] ffmpeg 已安装（`ffmpeg -version`）
- [ ] uv 已安装（`uv --version`）

## Step 2: 初始化 Python 环境
```bash
uv sync
```

## Step 3: 验证安装
```bash
uv run pytest tests/test_smoke.py -v
```

## Step 4: 配置环境变量
复制 `.env` 中的占位符为真实值（private repo 可直接编辑提交）

## Step 5: 运行项目
[具体命令]
```

**要求**：
- 所有命令可直接复制执行（无个人路径、无假设）
- 使用相对路径或占位符（`<REPO_ROOT>`）
- 包含"验证"步骤，不只是"安装"步骤

### SessionStart Hook 模式

让 Claude Code 打开仓库时自动检查环境：

**`.claude/settings.json`**：
```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/session-start-check.sh"
          }
        ]
      }
    ]
  }
}
```

**`.claude/hooks/session-start-check.sh`**：
```bash
#!/usr/bin/env bash
CACHE_DIR="$HOME/.claude/cache/env-check"
mkdir -p "$CACHE_DIR"
REPO_HASH=$(cd "$(dirname "$0")/../.." && pwd | sha256sum | cut -d' ' -f1)
CACHE_FILE="$CACHE_DIR/$REPO_HASH"
if [ -f "$CACHE_FILE" ] && [ "$(find "$CACHE_FILE" -mtime -1 2>/dev/null)" ]; then
    exit 0
fi
touch "$CACHE_FILE"
echo "【环境自检】你刚刚进入 [项目名] 仓库。请在执行任何任务前，先阅读 ONBOARDING.md 并按 Step 1-3 验证环境。"
```

**一键初始化脚本**：

Skill 自带 `scripts/init_session_start_hook.py`，可为任意项目自动生成配置：

```bash
# 基础用法（自动推断项目名，默认读取 ONBOARDING.md）
python scripts/init_session_start_hook.py --repo /path/to/project

# 完整用法
python scripts/init_session_start_hook.py \
  --repo /path/to/project \
  --guide ONBOARDING.md \
  --update-gitignore
```

**脚本行为**：
1. 创建 `.claude/settings.json`（SessionStart hook 配置）
2. 创建 `.claude/hooks/session-start-check.sh`（24h 缓存 + 自检提示）
3. `--update-gitignore` 时追加规则，允许 `.claude/settings.json` 和 `hooks/` 入 git
4. 自动从 git remote 或目录名推断项目名
5. 已有配置时默认跳过（`--force-overwrite` 覆盖）

**设计原则**：
- hook 只负责**戳**agent 检查（输出提示），**不负责**复杂脚本检查
- 24h TTL 缓存降频（用 repo path sha256 作为 cache key）
- 项目级配置，与全局 settings deep merge

### Counter-Review Workflow

当需要**创建新文件、修改核心配置、添加外部依赖、修改 CI/CD、变更安全策略**时，启动多 agent 审查：

1. **并行启动 4 个 lens**（各一个 subagent）：
   - security-lens：PII/secret 泄露、注入风险、权限过度
   - devops-lens：部署影响、依赖冲突、路径硬编码
   - code-quality-lens：可读性、异常处理、测试覆盖
   - doc-consistency-lens：文档与代码同步、ONBOARDING.md 更新

2. **Judge agent 过滤**：
   - 对每条 finding 用"概率 × 成本 × 现实场景"三维过滤
   - 真实 + 低成本 → 立刻修
   - 真实 + 高成本 → 告诉用户权衡
   - 虚构 / 过度担忧 → 明说"这是过度防御，拒绝"

3. **给用户分类汇报**：✅ 真问题 / ⚠️ 部分对 / ❌ 虚构 / 🚫 反而有害

---

## Git 操作规范

### 提交代码（非技术用户场景）

用户说"帮我提交"或"保存一下"时：

1. `git status` 看改动
2. `git diff` 确认改动内容（向用户解释改了什么）
3. `git add`（选择性，不要无脑 `git add .`）
4. `git commit -m "..."`
   - 信息用中文，描述改了什么、为什么改
   - 结尾加 `Co-Authored-By: Claude <noreply@anthropic.com>`
5. `git push` 前走 **Push Safety** 验证

### 处理冲突

用户说"冲突了"时：

1. `git status` 定位冲突文件
2. 读取冲突文件的 `<<<<<<<` / `=======` / `>>>>>>>` 区块
3. **不要自动选择某一侧**——向用户解释两边的差异，让用户决定（或按业务逻辑判断）
4. 修复后 `git add` + `git commit`

### 历史净化（敏感信息泄露后）

如果仓库历史中存在敏感信息（个人路径、secret、内部域名）：

1. **评估影响范围**：哪些 commit 含敏感信息？是否已 push 到 remote？
2. **Orphan branch + force push**（如果历史可以全部丢弃）：
   ```bash
   git checkout --orphan new-history
   git add -A
   git commit -m "Initial commit: sanitized history"
   git push --force origin new-history:main
   ```
3. **BFG Repo-Cleaner**（如果需保留部分历史）：用于替换文件中的敏感字符串
4. **通知用户**：force push 会打断其他协作者，需协调

---

## 项目隔离规范

### API Key 隔离

每个项目使用独立的 API key，禁止复用个人/生产 key：

- 在 provider 后台为每个项目创建独立 key
- `.env` 中只放项目专属 key
- key 命名体现用途（如 `video-rough-cut-dev`）
- 定期轮转（泄露后可单独 revoke）

### 路径清理

仓库中**禁止**出现：
- 个人绝对路径（`/Users/<name>/`、`/home/<name>/`）
- 内部域名/IP（`<private-domain>.dev`、`<private-domain>.pro` 等）
- 中文真实人名/项目名（用占位符替代）

**清理方法**：
- 用占位符替换（`<REPO_ROOT>`、`<USER_HOME>`、`<YOUR_NAME>`）
- 用相对路径替代绝对路径
- 用 `.env` 或配置文件存储环境相关值

---

## 常见故障排查手册

### "uv 命令找不到"
- 检查 `~/.local/bin` 是否在 PATH
- 重新安装：`curl -LsSf https://astral.sh/uv/install.sh | sh`

### "ffmpeg 命令找不到"
- macOS: `brew install ffmpeg`
- 或按项目文档安装 `ffmpeg-full`

### "whisper.cpp 编译失败"
- 检查 Xcode Command Line Tools: `xcode-select --install`
- 检查 Metal 支持（Apple Silicon）

### "pytest 大量失败"
- 先跑最小 smoke test，不要一次性跑全量
- 检查 `.env` 是否配置了必要的 API key
- 检查测试是否依赖本地文件系统路径（应使用临时目录）

### "git push 被拒绝"
- 检查远程仓库权限
- 检查是否启用了 branch protection
- 走 Push Safety 流程确认仓库可见性

---

## Next Step: 代码审查与交付

完成环境配置和基础修复后，建议的自然下一步：

**Options:**
A) **运行 Counter-Review** — 如果用户准备做较大改动，启动多 agent 安全审查（Recommended）
B) **生成操作文档** — 为用户生成简洁的操作指南（下一步该点什么/运行什么）
C) **No thanks** — 当前状态已足够，用户可以直接开始使用

---

## 资源目录

### references/
- `git_safety.md` — Git 操作安全细则（Push Safety、Hook Bypass、历史净化）
- `pii_guard.md` — PII Guard 规则摘要与应急处理
- `onboarding_template.md` — ONBOARDING.md 标准模板

### scripts/
- `check_env.py` — 环境检查脚本（ffmpeg、uv、python、git 状态）
- `sanitize_history.sh` — 历史净化辅助脚本（检查敏感信息、生成 orphan branch）
