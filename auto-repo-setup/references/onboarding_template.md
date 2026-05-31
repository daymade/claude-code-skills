# ONBOARDING.md 标准模板

## 模板（复制到新项目后修改）

```markdown
# <项目名称> Setup 指南

> 本指南面向非技术用户。遇到任何问题，直接问 Claude Code："跑不起来了"、"环境怎么配"。

## Step 1: 验证系统依赖

在终端运行以下命令，**每行都要运行并确认输出**：

```bash
# 1.1 git 状态检查
git status
# 期望：显示 "On branch main"，无未提交改动

# 1.2 ffmpeg 检查
ffmpeg -version | head -1
# 期望：显示版本号（如 "ffmpeg version 7.0"）

# 1.3 uv 检查
uv --version
# 期望：显示版本号（如 "uv 0.5.x"）
```

**任一失败 → 按下方"故障排除"修复，不要跳过。**

## Step 2: 初始化 Python 环境

```bash
# 2.1 进入项目目录（如果还没进）
cd <REPO_ROOT>

# 2.2 同步依赖（根据 pyproject.toml 安装）
uv sync

# 2.3 验证安装
uv run python -c "import <main_package>; print('OK')"
```

## Step 3: 配置环境变量

```bash
# 3.1 查看当前 .env
cat .env
```

- 如果值是占位符（如 `YOUR_KEY_HERE`），替换为真实值
- private repo：直接编辑 `.env` 然后 `git add .env && git commit -m "配置环境变量"`
- public repo：**不要提交 .env**，问 Claude Code 如何处理

## Step 4: 运行验证测试

```bash
# 4.1 运行 smoke test
uv run pytest tests/test_smoke.py -v

# 或运行项目自带验证脚本
uv run python scripts/verify_setup.py
```

**全部通过 → 环境就绪。**

## Step 5: 日常使用

| 任务 | 命令 |
|------|------|
| 运行项目 | `uv run python main.py` |
| 运行测试 | `uv run pytest` |
| 更新依赖 | `uv sync` |
| 提交代码 | 问 Claude Code "帮我提交" |

## 故障排除

### "命令找不到"（ffmpeg / uv / git）
- macOS: `brew install ffmpeg` / `curl -LsSf https://astral.sh/uv/install.sh | sh`
- 重新打开终端，让 PATH 生效

### "uv sync 失败"
- 检查网络连接
- 检查 `pyproject.toml` 是否存在
- 问 Claude Code

### "pytest 失败"
- 检查 `.env` 是否配置正确
- 先跑 `tests/test_smoke.py`（最小测试），不要一次性跑全量
- 问 Claude Code

### "git push 被拒"
- 问 Claude Code "push 失败了"
- 不要强行用 `--force`
```

## 设计原则

1. **所有命令可直接复制执行** — 无个人路径、无假设
2. **每步有验证** — 不只是"安装"，而是"安装后检查"
3. **相对路径或占位符** — `<REPO_ROOT>`、`<YOUR_NAME>`
4. **故障排除独立成节** — 常见问题自助，复杂问题找 Claude
5. **面向非技术用户** — 解释"期望输出是什么"、"失败了怎么办"
6. **与 Claude Code 配合** — 明确说"问 Claude Code"的场景
