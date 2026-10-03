# 快速入门指南

安装技能，或在已有源码仓库中创建技能。

## 面向技能创建者

**想要创建自己的技能？从这里开始！**

### 步骤 1：安装 skill-creator

**在 Claude Code 内（应用内）：**
```text
/plugin marketplace add daymade/claude-code-skills
```

然后：
1. 选择 **Browse and install plugins**
2. 选择 **daymade/claude-code-skills**
3. 选择 **daymade-skill**
4. 选择 **Install now**

**在终端（CLI）：**
```bash
# 添加市场
claude plugin marketplace add https://github.com/daymade/claude-code-skills

# Marketplace 名称：daymade-skills（来自 marketplace.json）
# 安装 daymade-skill 套件（含 skill-creator）
claude plugin install daymade-skill@daymade-skills
```

### 步骤 2：选定源码后初始化

先加载 [skill-creator](./daymade-skill/skill-creator/SKILL.md#critical-edit-skills-at-source-location)，按其源码预检确认归属。下面演示已有 Git 项目中的项目级技能；可复用的全局技能应先选定自己的 marketplace 源码仓库，再走该 Skill 的创建流程。

将变量替换为实际加载的 skill-creator 目录和已有 Git 项目的绝对路径：

```bash
TASK_CREATOR=/absolute/path/to/loaded/skill-creator
TASK_PROJECT=/absolute/path/to/existing/git-project
uv run --project "$TASK_CREATOR" --frozen python "$TASK_CREATOR/scripts/init_skill.py" my-first-skill \
  --path "$TASK_PROJECT/.claude/skills" --repo "$TASK_PROJECT" --scope project
```

### 步骤 3：编辑与验证

编辑 `$TASK_PROJECT/.claude/skills/my-first-skill/SKILL.md`，定义触发条件、操作和失败判据，添加需要的资源。删除未使用的模板示例。

```bash
uv run --project "$TASK_CREATOR" --frozen python "$TASK_CREATOR/scripts/quick_validate.py" \
  "$TASK_PROJECT/.claude/skills/my-first-skill"
```

继续按 [skill-creator 的交付流程](./daymade-skill/skill-creator/SKILL.md#skill-creation-process-step-by-step)完成所需的安全、回归和打包检查；结构验证通过不等于已完成交付。

### 步骤 4：验证宿主读取结果

按 [skill-governance](./daymade-skill/skill-governance/references/skill-surface-governance.md) 中的安装生命周期和 fresh-host 检查，读回实际消费的文件并验证任务行为。不要用 `cp -r` 创建另一份维护副本，也不要把重启或目录可见当作已加载的证明。

贡献范围见 [CONTRIBUTING.md](./CONTRIBUTING.md)。

---

## 面向技能用户

**只想使用现有技能？方法如下！**

### 选项 1：自动化安装（最快）

**macOS/Linux：**
```bash
curl -fsSL https://raw.githubusercontent.com/daymade/claude-code-skills/main/scripts/install.sh | bash
```

**Windows (PowerShell)：**
```powershell
iwr -useb https://raw.githubusercontent.com/daymade/claude-code-skills/main/scripts/install.ps1 | iex
```

按照交互提示选择技能。

### 选项 2：手动安装

```bash
# 步骤 1：添加市场
claude plugin marketplace add https://github.com/daymade/claude-code-skills

# Marketplace 名称：daymade-skills（来自 marketplace.json）
# 安装命令请使用 @daymade-skills（例如 skill-name@daymade-skills）
# 在 Claude Code 内使用 `/plugin ...`，在终端中使用 `claude plugin ...`
# 步骤 2：安装你需要的技能
claude plugin install github-ops@daymade-skills
claude plugin install daymade-docs@daymade-skills
# ... 根据需要添加更多

# 步骤 3：重启 Claude Code
```

### 查找、更新与卸载

技能目录见 [README.zh-CN.md](./README.zh-CN.md)。安装来源、套件边界、更新和卸载按 [skill-governance](./daymade-skill/skill-governance/references/skill-surface-governance.md) 的对应流程操作。

---

## 🇨🇳 中国用户专区

### 推荐：使用 CC-Switch

如果你在中国，首先安装 [CC-Switch](https://github.com/farion1231/cc-switch) 来管理 API 提供商：

1. 从 [Releases](https://github.com/farion1231/cc-switch/releases) 下载
2. 安装并配置你偏好的提供商（DeepSeek、Qwen、GLM）
3. 测试响应时间以找到最快的端点
4. 然后正常安装 Claude Code 技能

**为什么选择 CC-Switch？**
- ✅ 支持中国 AI 提供商
- ✅ 自动选择最快端点
- ✅ 轻松切换配置
- ✅ 支持 Windows、macOS、Linux

### 推荐的中国 API 提供商

通过 CC-Switch，你可以使用：
- **DeepSeek**：高性价比的深度学习模型
- **Qwen（通义千问）**：阿里云的大语言模型
- **GLM（智谱清言）**：智谱 AI 的对话模型
- 其他兼容 OpenAI API 格式的提供商

### 网络问题解决

遇到网络问题时：
1. 使用 CC-Switch 配置国内 API 提供商
2. 确保你的代理设置正确
3. 使用 CC-Switch 的响应时间测试功能

---

## 常见问题

**Q：我应该首先安装哪些技能？**
A：如果你想创建技能，从 **skill-creator** 开始。否则，根据你的需求安装（参见 README 技能目录）。

**Q：我可以安装多个技能吗？**
A：插件边界以 [marketplace manifest](./.claude-plugin/marketplace.json) 为准。

**Q：如何卸载技能？**
A：按 [skill-governance](./daymade-skill/skill-governance/references/skill-surface-governance.md) 的卸载流程操作。

**Q：我在哪里可以获得帮助？**
A：在 [github.com/daymade/claude-code-skills](https://github.com/daymade/claude-code-skills/issues) 开启问题

**Q：技能是否安全？**
A：开源便于检查，但不能证明安全。审查方法见 [skill-reviewer](./daymade-skill/skill-reviewer/SKILL.md) 与 [安全检查清单](./daymade-skill/skill-creator/references/sanitization_checklist.md)。

**Q：如何为这个项目做贡献？**
A：查看 [CONTRIBUTING.md](./CONTRIBUTING.md)。

---

## 下一步

- 📖 阅读完整的 [README.zh-CN.md](./README.zh-CN.md) 获取详细信息
- 🌐 English users see [README.md](./README.md)
- 💡 查看 [CHANGELOG.md](./CHANGELOG.md) 了解近期更新
- 🤝 在 [CONTRIBUTING.md](./CONTRIBUTING.md) 贡献

**祝你构建技能愉快！🚀**
