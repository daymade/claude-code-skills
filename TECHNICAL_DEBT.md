# 技术债务清单

## 当前债务状况

| 债务类型 | 严重程度 | 预计修复时间 | 阻塞发布 |
|---------|---------|-------------|----------|
| 测试覆盖不足 | 🔴 极高 | 4周 | ✅ 是 |
| 缺少CI/CD | 🔴 极高 | 1周 | ✅ 是 |
| 错误处理不完善 | 🟠 高 | 2周 | ✅ 是 |
| 性能未优化 | 🟠 高 | 2周 | ❌ 否 |
| 文档不完整 | 🟡 中 | 1周 | ❌ 否 |
| 代码重复 | 🟡 中 | 1周 | ❌ 否 |

## 详细债务清单

### 🔴 极高优先级

#### 1. 测试覆盖不足（5% → 目标80%）

**现状:**
- 总源文件: 2,999
- 测试文件: 5
- 覆盖率: ~5%

**缺失测试:**
- [ ] `inbox-engine.ts` - 核心逻辑无测试
- [ ] `annotation-engine.ts` - 核心逻辑无测试
- [ ] `sync-engine.ts` - 核心逻辑无测试
- [ ] `tts-engine.ts` - 新增无测试
- [ ] `reading-agent-sdk.ts` - 复杂逻辑无测试
- [ ] 所有API routes - 无集成测试

**风险:**
- 重构困难
- 回归bug无法发现
- 无法 confident 地发布

**修复方案:**
```bash
# 优先级1: 核心引擎单元测试
- inbox-engine.test.ts
- annotation-engine.test.ts
- sync-engine.test.ts

# 优先级2: API集成测试
- api/articles.test.ts
- api/scrape.test.ts
- api/sync.test.ts

# 优先级3: E2E测试
- scrape-to-read.spec.ts (已完成)
- reading-annotations.spec.ts (已完成)
- tts-stagehand.spec.ts (已完成)
```

#### 2. 缺少CI/CD流水线

**现状:**
- 无自动化测试
- 无自动化部署
- 无代码质量检查

**需要建立:**
- [ ] GitHub Actions workflow
  - [ ] Lint check
  - [ ] Type check
  - [ ] Unit tests
  - [ ] E2E tests
  - [ ] Security scan
  - [ ] Deploy to staging
  - [ ] Deploy to production

**参考实现:**
Omnivore 的 `.github/workflows/` 配置

#### 3. 错误处理不完善

**现状:**
- 大量 `throw error` 未处理
- 用户看到的是原始错误信息
- 无错误边界(Error Boundaries)

**需要修复:**
- [ ] 统一错误处理中间件
- [ ] 用户友好的错误提示
- [ ] Sentry上报所有未捕获错误
- [ ] React Error Boundaries

### 🟠 高优先级

#### 4. 性能未优化

**已知问题:**
- [ ] 首屏加载无骨架屏
- [ ] 大文章渲染卡顿
- [ ] 图片懒加载不完善
- [ ] 无虚拟滚动

**待测量指标:**
```
LCP (Largest Contentful Paint): 目标 < 2.5s
FID (First Input Delay): 目标 < 100ms
CLS (Cumulative Layout Shift): 目标 < 0.1
TTI (Time to Interactive): 目标 < 3.8s
```

#### 5. 数据库查询未优化

**潜在问题:**
- [ ] 缺少复合索引
- [ ] N+1查询问题
- [ ] 大数据表无分区

**需要:**
- [ ] 查询性能分析
- [ ] EXPLAIN ANALYZE 所有慢查询
- [ ] 连接池配置优化

### 🟡 中优先级

#### 6. 文档不完整

**缺失:**
- [ ] API文档 (OpenAPI/Swagger)
- [ ] 架构决策记录 (ADR)
- [ ] 部署指南
- [ ] 贡献者指南

#### 7. 代码重复

**发现重复:**
- [ ] 日期格式化函数 (多处)
- [ ] API错误处理逻辑 (多处)
- [ ] 类型定义分散

## 还债计划

### Sprint 1: 测试基础 (Week 1-2)

```bash
# 目标: 测试覆盖率 5% → 30%

Week 1:
- [ ] 设置 Vitest + React Testing Library
- [ ] inbox-engine.ts 单元测试
- [ ] annotation-engine.ts 单元测试

Week 2:
- [ ] sync-engine.ts 单元测试
- [ ] tts-engine.ts 单元测试
- [ ] 核心组件单元测试
```

### Sprint 2: CI/CD + 错误处理 (Week 3-4)

```bash
# 目标: 自动化流水线 + 错误监控

Week 3:
- [ ] GitHub Actions workflow
- [ ] 自动化测试触发
- [ ] Sentry生产环境配置

Week 4:
- [ ] 错误边界组件
- [ ] 统一错误处理
- [ ] 用户友好错误提示
```

### Sprint 3: 性能优化 (Week 5-6)

```bash
# 目标: Web Vitals 达标

Week 5:
- [ ] 性能基线测量
- [ ] 图片优化
- [ ] 代码分割

Week 6:
- [ ] 虚拟滚动 (大文章)
- [ ] 骨架屏
- [ ] 缓存策略
```

### Sprint 4: 清理 (Week 7-8)

```bash
# 目标: 代码质量提升

Week 7:
- [ ] 重构重复代码
- [ ] 类型定义集中化
- [ ] 数据库索引优化

Week 8:
- [ ] 文档完善
- [ ] 架构图更新
- [ ] 技术债务复盘
```

## 债务预防

### 代码审查清单

- [ ] 新功能必须包含测试
- [ ] 复杂逻辑必须有注释
- [ ] API变更必须更新文档
- [ ] 性能敏感代码必须有基准测试

### 自动化防护

```yaml
# .github/workflows/quality.yml
- name: Test Coverage
  run: |
    npm run test:coverage
    # 失败如果覆盖率 < 60%
    
- name: Bundle Size
  run: |
    npm run analyze
    # 失败如果 bundle > 500KB
    
- name: Performance Budget
  run: |
    lhci autorun
    # 失败如果 Web Vitals 不达标
```

## 债务追踪

| 日期 | 债务项 | 状态 | 备注 |
|-----|-------|------|------|
| 2025-04-12 | 测试覆盖 | 🟡 进行中 | 已规划E2E |
| 2025-04-12 | CI/CD | 🔴 未开始 | 优先级P0 |
| 2025-04-12 | 错误处理 | 🔴 未开始 | 优先级P0 |

---

最后更新: Round 91
下次审查: Round 95
