# 快速入门指南

在不到 2 分钟的时间内开始使用 Claude Code 技能市场！

## 面向技能创建者

**想要创建自己的技能？从这里开始！**

### 步骤 1：安装 skill-creator

```bash
# 添加市场
claude plugin marketplace add https://github.com/daymade/claude-code-skills

# Marketplace 名称：daymade-skills（来自 marketplace.json）
# 安装 skill-creator
claude plugin install skill-creator@daymade-skills
```

### 步骤 2：初始化你的第一个技能

```bash
# 从模板创建一个新技能
skill-creator/scripts/init_skill.py my-first-skill --path ~/my-skills
```

这将生成：
```
~/my-skills/my-first-skill/
├── SKILL.md                  # 主技能文件
├── scripts/                  # 可执行代码
│   └── example_script.py
├── references/               # 文档
│   └── example_reference.md
└── assets/                   # 模板/资源
    └── example_asset.txt
```

### 步骤 3：自定义你的技能

编辑 `~/my-skills/my-first-skill/SKILL.md`：

1. **更新前置信息** - 设置名称和描述
2. **编写"何时使用此技能"** - 定义激活条件
3. **记录工作流** - 解释 Claude 应如何使用你的技能
4. **添加资源** - 根据需要创建脚本、参考文档或资源

### 步骤 4：验证你的技能

```bash
# 检查你的技能是否符合质量标准
skill-creator/scripts/quick_validate.py ~/my-skills/my-first-skill
```

修复报告的任何错误，然后再次验证。

### 步骤 5：打包用于分发

```bash
# 创建可分发的 .zip 文件
skill-creator/scripts/package_skill.py ~/my-skills/my-first-skill
```

这将创建 `my-first-skill.zip`，可以分享了！

### 步骤 6：测试你的技能

```bash
# 复制到 Claude Code 技能目录
cp -r ~/my-skills/my-first-skill ~/.claude/skills/

# 重启 Claude Code
# 你的技能现在已激活！
```

### 下一步

- 📖 阅读 [skill-creator/SKILL.md](./skill-creator/SKILL.md) 获取全面指导
- 🔍 研究此市场中的现有技能以获取示例
- 💡 查看 [CONTRIBUTING.md](./CONTRIBUTING.md) 以分享你的技能

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
# 所有命令都应使用 `claude plugin ...`（没有 `/plugin` 命令）
# 步骤 2：安装你需要的技能
claude plugin install github-ops@daymade-skills
claude plugin install markdown-tools@daymade-skills
# ... 根据需要添加更多

# 步骤 3：重启 Claude Code
```

### 可用技能（快速入门）

本表为快速入门列表。完整 25 个技能请见 [README.zh-CN.md](./README.zh-CN.md)。

| 技能 | 描述 | 使用场景 |
|-------|-------------|-------------|
| **skill-creator** ⭐ | 创建你自己的技能 | 构建自定义工作流 |
| **github-ops** | GitHub 操作 | 管理 PR、问题、工作流 |
| **markdown-tools** | 文档转换 | 将文档转换为 markdown |
| **mermaid-tools** | 图表生成 | 创建 PNG 图表 |
| **statusline-generator** | 状态栏定制 | 自定义 Claude Code UI |
| **teams-channel-post-writer** | Teams 通信 | 编写专业帖子 |
| **repomix-unmixer** | 仓库提取 | 提取 repomix 文件 |
| **llm-icon-finder** | AI/LLM 品牌图标 | 查找模型徽标 |

### 更新技能

```bash
# 使用相同的安装命令进行更新
claude plugin install skill-name@daymade-skills
```

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
A：如果你想创建技能，从 **skill-creator** 开始。否则，根据你的需求安装（参见快速入门表及 README 完整列表）。

**Q：我可以安装多个技能吗？**
A：可以！每个技能都是独立的。根据需要安装任意数量的技能。

**Q：如何卸载技能？**
A：从 `~/.claude/skills/` 中删除它并重启 Claude Code。

**Q：我在哪里可以获得帮助？**
A：在 [github.com/daymade/claude-code-skills](https://github.com/daymade/claude-code-skills/issues) 开启问题

**Q：技能是否安全？**
A：是的！所有技能都是开源的，代码可供检查。我们遵循严格的质量标准。

**Q：如何为这个项目做贡献？**
A：查看 [CONTRIBUTING.md](./CONTRIBUTING.md) 了解指南。我们欢迎技能提交、错误报告和改进建议！

---

## 下一步

- 📖 阅读完整的 [README.zh-CN.md](./README.zh-CN.md) 获取详细信息
- 🌐 English users see [README.md](./README.md)
- 💡 查看 [CHANGELOG.md](./CHANGELOG.md) 了解近期更新
- 🤝 在 [CONTRIBUTING.md](./CONTRIBUTING.md) 贡献

**祝你构建技能愉快！🚀**
