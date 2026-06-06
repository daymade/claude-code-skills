# Git 操作安全细则

## Push Safety — 推送前必须验证仓库可见性

**任何 `git push`（特别推到 main/master）之前，必须用 `gh` CLI 验证目标仓库的真实可见性。**

```bash
gh repo view <owner>/<repo> --json visibility,isPrivate,stargazerCount,forkCount
```

**决策矩阵**：

| 可见性 | Stars/Forks | 操作 |
|--------|-------------|------|
| public | >0 | 默认走 PR 流程（push feature branch + `gh pr create`） |
| public | 0 + 用户明确授权 | 可 push main，但仍需 audit 内容 |
| private/internal | 任意 | push main 需用户确认，风险降一档 |

**禁止**：
- 凭 URL 形态反推 private/public
- 凭用户名/目录路径推断
- 在汇报里写"私人 repo"除非 API 确认 `isPrivate: true`
- 凭历史汇报或 CLAUDE.md 描述推断

## Git Hook Bypass 禁令

**Claude 禁止主动使用 `--no-verify` / `--no-gpg-sign` / `-c commit.gpgsign=false` 等绕过 git hook 的参数。**

- ❌ Hook 失败 → 找根因修好 → **不要**"绕过试试看"
- ❌ 过去 session / 文档里的历史授权 → 不作数
- ❌ 用户没明说，但我觉得"应该跳" → 不行，停下来问
- ✅ 用户本人在当前 session 里**显式输入** `--no-verify` → 照办（只这一次）

**Why**：pre-commit hook 是拦住 secret/PII/大文件的最后一道系统性防线。AI 自作主张绕过 = 防线退化为"看 AI 心情"。

## 历史净化（敏感信息泄露后）

### 评估影响

1. 哪些 commit 含敏感信息？
2. 是否已 push 到 remote？
3. 是否有其他协作者？

### 方法选择

| 场景 | 方法 | 说明 |
|------|------|------|
| 历史可以全部丢弃 | Orphan branch + force push | 最干净，但打断所有协作者 |
| 需保留部分历史 | BFG Repo-Cleaner | 替换文件中的敏感字符串 |
| 仅单个文件 | `git filter-branch` / `git filter-repo` | 移除特定文件从历史 |

### Orphan branch 流程

```bash
# 1. 创建无历史的新分支
git checkout --orphan new-history

# 2. 添加当前工作区内容
git add -A

# 3. 提交（注意：此时不要含敏感信息）
git commit -m "Initial commit: sanitized history"

# 4. 强制推送到 main（会覆盖远程历史）
git push --force origin new-history:main

# 5. 删除旧分支引用（本地）
git branch -D main
git checkout -b main origin/main
```

**⚠️ 警告**：
- Force push 会永久删除远程历史，其他协作者需要重新 clone
- 必须先通知用户并获得确认
- 如果 secret 已泄露到公开网络，force push 不够——还需 revoke 并轮转 key

## 提交规范

### Commit message

- 用中文描述改了什么、为什么改
- 技术细节可附在正文
- 结尾加 `Co-Authored-By: Claude <noreply@anthropic.com>`

### 选择性添加

- 不要无脑 `git add .`
- `git status` 后选择性 `git add <file>`
- 确保 stage 的内容都是意图中的改动
