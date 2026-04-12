# CI/CD 设置指南

## 概述

我们建立了企业级的 CI/CD 流水线，参考 Omnivore、Wallabag 等世界级开源项目的最佳实践。

## 工作流程

### 1. CI Workflow (ci.yml)

**触发条件:**
- Push 到 `main` 或 `develop` 分支
- Pull Request 到 `main` 或 `develop` 分支

**任务流水线:**

```
┌─────────────────┐
│ Lint & Type     │ 并行
│ Check           │
└────────┬────────┘
         │
    ┌────┴────┬────────────┬─────────────┐
    ▼         ▼            ▼             ▼
┌────────┐ ┌─────────┐ ┌──────────┐ ┌──────────┐
│ Unit   │ │Integration│ │ E2E      │ │ Security │
│ Tests  │ │ Tests     │ │ Tests    │ │ Scan     │
└────────┘ └─────────┘ └──────────┘ └──────────┘
```

**具体任务:**

| 任务 | 目的 | 失败阻断 |
|-----|------|---------|
| **Lint & Type Check** | 代码风格、类型检查 | ✅ 是 |
| **Unit Tests** | 单元测试 + 覆盖率 | ✅ 是 |
| **Integration Tests** | 集成测试 (需数据库) | ✅ 是 |
| **E2E Tests** | Stagehand AI 端到端测试 | ✅ 是 |
| **Benchmark Tests** | 抓取成功率、批注准确率 | ✅ 是 |
| **Security Scan** | npm audit + Trivy | ⚠️ 否 |
| **Build Verification** | 构建 + 包大小检查 | ✅ 是 |

### 2. CD - Staging (cd-staging.yml)

**触发条件:**
- Push 到 `develop` 分支
- 手动触发

**部署流程:**

```
develop 分支
    │
    ▼
┌─────────────────┐
│ Deploy to       │ Vercel Preview
│ Vercel Staging  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Smoke Tests     │ /api/health
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ DB Migration    │ Supabase
└─────────────────┘
```

### 3. CD - Production (cd-production.yml)

**触发条件:**
- Tag push (`v*`)
- 手动触发（需确认）
- Push 到 `main` 分支

**部署流程:**

```
main 分支 / tag
    │
    ▼
┌─────────────────┐
│ Pre-checks      │ 验证 CI 通过
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Deploy to       │ Vercel Production
│ Production      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Smoke Tests     │ /api/health
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ DB Migration    │ Supabase
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Sentry Release  │ 错误追踪
└─────────────────┘
```

### 4. Scheduled Benchmark (benchmark-scheduled.yml)

**触发条件:**
- 每周日 2:00 AM UTC
- 手动触发

**监控指标:**
- 抓取成功率（目标 ≥ 95%）
- 批注定位准确率（目标 ≥ 98%）
- 性能基准

## 环境变量配置

### GitHub Secrets

在 GitHub Repository → Settings → Secrets and variables → Actions 中配置：

#### Required Secrets

| Secret | 说明 | 获取方式 |
|-------|------|---------|
| `VERCEL_TOKEN` | Vercel 部署令牌 | Vercel Dashboard → Settings → Tokens |
| `VERCEL_ORG_ID` | Vercel 组织 ID | `vercel teams list` |
| `VERCEL_PROJECT_ID` | Vercel 项目 ID | `vercel project list` |
| `SUPABASE_ACCESS_TOKEN` | Supabase 访问令牌 | Supabase Dashboard → Account → Tokens |
| `SUPABASE_PROJECT_REF` | Supabase 项目引用 | 项目 URL 中的 ref |

#### Optional Secrets

| Secret | 说明 | 用途 |
|-------|------|------|
| `ANTHROPIC_API_KEY` | Claude API 密钥 | E2E 测试 Stagehand |
| `SENTRY_AUTH_TOKEN` | Sentry 认证令牌 | 生产错误追踪 |
| `SENTRY_ORG` | Sentry 组织 | 生产错误追踪 |
| `SENTRY_PROJECT` | Sentry 项目 | 生产错误追踪 |
| `SLACK_WEBHOOK_URL` | Slack Webhook | 部署通知 |

## 本地测试 CI 流程

```bash
# 安装依赖
cd cloud
npm ci

# 运行所有检查
npm run lint
npm run typecheck
npm run format:check

# 运行测试
npm run test:unit
npm run test:integration
npm run test:e2e

# 运行基准测试
npm run test:benchmark

# 构建
npm run build
```

## 质量门禁

### 合并到 develop 的条件

- [x] Lint 检查通过
- [x] TypeScript 类型检查通过
- [x] 单元测试通过
- [x] 集成测试通过
- [x] 构建成功

### 合并到 main 的条件

- [x] 所有 develop 的条件
- [x] E2E 测试通过
- [x] 安全扫描完成
- [x] 代码审查通过

### 部署到 production 的条件

- [x] 所有 main 的条件
- [x] 手动确认
- [x] Smoke 测试通过

## 监控和告警

### GitHub Actions 状态

查看所有 workflow 运行状态：
- GitHub Repository → Actions

### 覆盖率报告

查看测试覆盖率：
- Codecov 集成（上传于 CI）
- PR 中的覆盖率 diff

### 基准测试仪表板

每周自动更新的基准测试报告：
- GitHub Actions → Artifacts → benchmark-dashboard

## 故障排查

### CI 失败常见问题

#### 1. 测试超时
```
# 本地检查测试超时设置
npm run test:unit -- --timeout=10000
```

#### 2. 数据库连接失败
```
# 检查服务配置
docker run -p 5432:5432 postgres:15-alpine
```

#### 3. Playwright 安装失败
```
# 重新安装浏览器
npx playwright install --with-deps chromium
```

### Deployment 失败

#### Vercel 部署失败
```bash
# 本地验证构建
vercel build

# 检查环境变量
vercel env pull
```

#### 数据库迁移失败
```bash
# 检查迁移状态
supabase db status

# 重置本地数据库
supabase db reset
```

## 最佳实践

### 提交前检查

```bash
# 在 pre-commit 钩子中运行
npm run lint:fix
npm run typecheck
npm run test:unit -- --changed
```

### 分支策略

```
main (production)
  ↑
develop (staging)
  ↑
feature/*
  ↑
hotfix/*
```

### PR 标签

- `breaking-change`: 破坏性变更
- `feature`: 新功能
- `bugfix`: Bug 修复
- `performance`: 性能优化
- `documentation`: 文档更新

## 竞品对标

| 特性 | Omnivore | Wallabag | 我们 (Round 94) |
|-----|----------|----------|----------------|
| 自动化测试 | ✅ | ✅ | ✅ CI/CD |
| 代码质量门禁 | ✅ | ✅ | ✅ Lint/Type |
| 覆盖率要求 | 80% | 70% | ✅ 30% → 60% |
| 自动部署 | ✅ | ✅ | ✅ Staging/Prod |
| 基准测试 | ❓ | ❓ | ✅ 自动化 |
| 安全扫描 | ✅ | ✅ | ✅ Trivy |

## 后续优化

1. **覆盖率提升** - 从 30% 提升到 60%+
2. **混沌测试** - 引入故障注入
3. **性能回归** - 防止性能下降
4. **多环境支持** - 增加 QA 环境
