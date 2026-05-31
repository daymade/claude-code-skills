# PII Guard 规则摘要与应急处理

## 三层扫描架构（public repo）

### Layer 1 — gitleaks

标准 secret + 私有基础设施域名/IP。

**覆盖规则**：
- LLM provider key：`sk-kimi-` (Moonshot)、`sk-or-v1-` (OpenRouter)、`sk-ant-(api|admin)` (Anthropic)、`sk-(proj|svcacct|admin)-` (OpenAI)
- Generic `sk-` 兜底（allowlist 了占位符如 `sk-test-`/`sk-example`/`sk-your-`）
- PII：macOS 绝对路径 `/Users/<user>/`、中国手机号、个人邮箱
- 私有基础设施：内部域名（`<private-domain>.dev`、`<private-domain>.pro` 等）+ 已知生产 IP
- 内置：AWS、GitHub PAT、Stripe 等

**⚠️ 注意**：gitleaks 有**熵过滤**——低熵占位符不会拦，只有高熵真实格式才拦。测试时必须用真实格式。

### Layer 2 — 路径扫描

禁止本地生成路径（coverage、node_modules 等）。

### Layer 3 — bash grep 兜底

同步 gitleaks 域名/IP 规则 + 已知身份（如中文人名）。gitleaks 不覆盖中文内容，Layer 3 补充拦截。

### Layer 4 — AI 语义通读

1-3 全是关键词/正则/grep，只命中"有人列进规则的词"。对**无 keyword 的语义私有结构性盲**（中文人名/项目名、真实转录口语片段、随手举的真实例子）——hook 必漏。

**push public repo 前除 hook 自动扫，必须自己 AI 通读全文做语义判断**："这名词/例子/片段，像通用占位/公开实体，还是从真实项目/人/转录拿的？"

"grep/gitleaks 无命中" ≠ 干净。

## private repo 规则

- `.env` 可直接提交（项目隔离的 API key）
- 但仍需清理**个人绝对路径**（`/Users/<name>/`）
- 仍需清理**内部域名/IP**
- 仍需清理**中文真实人名/项目名**

## 命中后怎么办

| 处理方式 | 是否允许 |
|---------|---------|
| 改规则（调 gitleaks.toml）/ 加 allowlist | ✅ |
| `--no-verify` 绕过 | ❌（除非用户本人当场打） |
| 仓库追加 `.pii-patterns` 文件定义仓库特有模式 | ✅ |
| 直接 push 不管 | ❌ |

## 应急处理（secret 已 push）

1. **立即 revoke key** — 在 provider 后台 disable key
2. **生成新 key** — 用新 key 替换 `.env`
3. **历史净化** — 按 `git_safety.md` 的 Orphan branch 或 BFG 流程清理
4. **通知受影响方** — 如果 key 有访问日志，评估影响范围
