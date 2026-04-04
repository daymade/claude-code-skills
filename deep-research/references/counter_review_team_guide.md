# Counter-Review Team 使用指南

Deep Research V6 P6 阶段的专用 Agent Team，并行执行多维度审查。

## Team 架构

```
counter-review-coordinator (协调者)
    ├── claim-validator (声明验证器)
    ├── source-diversity-checker (来源多样性检查器)
    ├── recency-validator (时效性验证器)
    └── contradiction-finder (矛盾发现器)
```

## Agent 职责

| Agent | 职责 | 输出 |
|-------|------|------|
| **claim-validator** | 验证声明准确性，识别无证据/弱证据声明 | Claim Validation Report |
| **source-diversity-checker** | 检查单一来源依赖，source-type 分布 | Source Diversity Report |
| **recency-validator** | 验证时敏声明的新鲜度，AS_OF 合规 | Recency Validation Report |
| **contradiction-finder** | 发现内部矛盾，缺失的反向观点 | Contradiction and Bias Report |
| **counter-review-coordinator** | 整合所有报告，生成最终 P6 报告 | P6 Counter-Review Report |

## 使用流程

### 1. 准备输入材料

在 P5 (Draft) 完成后，收集以下材料：

```
inputs/
├── draft_report.md          # P5 起草的报告
├── citation_registry.md     # P3 的引用注册表
├── task-notes/
│   ├── task-a.md           # 子代理研究笔记
│   ├── task-b.md
│   └── ...
└── p0_config.md            # P0 配置 (AS_OF 日期, Mode 等)
```

### 2. 并行分发任务

向 4 个 specialist agent 同时发送任务：

```bash
# 向 claim-validator 发送
SendMessage to: claim-validator
  输入: draft_report.md + citation_registry.md + task-notes/
  指令: 验证所有声明的证据支持

# 向 source-diversity-checker 发送
SendMessage to: source-diversity-checker
  输入: draft_report.md + citation_registry.md
  指令: 检查来源多样性和单一来源依赖

# 向 recency-validator 发送
SendMessage to: recency-validator
  输入: draft_report.md + citation_registry.md + p0_config.md
  指令: 验证时敏声明的新鲜度

# 向 contradiction-finder 发送
SendMessage to: contradiction-finder
  输入: draft_report.md + task-notes/ + citation_registry.md
  指令: 发现矛盾和缺失的反向观点
```

### 3. 协调汇总

等待 4 个 specialist 完成后，发送给 coordinator：

```bash
SendMessage to: counter-review-coordinator
  输入:
    - Claim Validation Report
    - Source Diversity Report
    - Recency Validation Report
    - Contradiction and Bias Report
  指令: 整合所有报告，生成最终 P6 Counter-Review Report
```

### 4. 获取最终输出

Coordinator 输出包含：
- 问题汇总（必须 ≥3 个）
- 关键争议部分（可直接复制到最终报告）
- 强制修复清单
- 质量门状态

## 质量门要求

| 检查项 | 标准模式 | 轻量模式 | 失败处理 |
|--------|---------|---------|---------|
| 发现问题数 | ≥3 | ≥3 | 重新审查 |
| 关键声明单来源 | 0 | 0 | 补充来源或降级 |
| 官方来源占比 | ≥30% | ≥20% | 补充官方来源 |
| AS_OF 日期完整 | 100% | 100% | 补充日期 |
| 核心争议文档化 | 必填 | 必填 | 补充争议部分 |

## 输出示例

### Coordinator 最终报告结构

```markdown
# P6 Counter-Review Report

## Executive Summary
- Total issues found: 7 (critical: 2, high: 3, medium: 2)
- Must-fix before publish: 2
- Recommended improvements: 5

## Critical Issues (Block Publish)
| # | Issue | Location | Source | Fix Required |
|---|-------|----------|--------|--------------|
| 1 | 市场份额声明无来源 | 3.2节 | 无 | 补充来源或删除 |
| 2 | 单一社区来源支持收入数据 | 4.1节 | [12] community | 找官方来源替代 |

## 核心争议 / Key Controversies

- **争议 1:** 公司声称增长 50% vs 分析师报告增长 30%
  - 证据强度: official(公司财报) vs academic(第三方研究)
  - 建议: 并列呈现两种数据，说明差异原因

## Mandatory Fixes Checklist
- [ ] 补充 3.2 节市场份额来源
- [ ] 替换 4.1 节收入数据来源
- [ ] 添加 AS_OF: 2026-04-03 到所有时敏声明

## Quality Gates Status
| Gate | Status | Notes |
|------|--------|-------|
| P6 ≥3 issues found | ✅ | 发现 7 个问题 |
| No critical claim single-sourced | ❌ | 2 个问题待修复 |
| AS_OF dates present | ❌ | 3 处缺失 |
| Counter-claims documented | ✅ | 已添加 |
```

## 集成到 SKILL.md 工作流

在 SKILL.md 的 P6 阶段，添加以下指令：

```markdown
## P6: Counter-Review (Mandatory)

**使用 Counter-Review Team 执行并行审查：**

1. **准备材料**: draft_report.md, citation_registry.md, task-notes/, p0_config.md
2. **并行分发**: 同时发送给 4 个 specialist agent
3. **等待完成**: 收集 4 份 specialist 报告
4. **协调汇总**: 发送给 coordinator 生成最终 P6 报告
5. **强制执行**: 所有 Critical 问题必须在 P7 前修复
6. **输出**: 将"核心争议"部分复制到最终报告

**Report**: `[P6 complete] {N} issues found: {critical} critical, {high} high, {medium} medium.`
```

## 团队管理

### 查看团队状态
```bash
cat ~/.claude/teams/counter-review-team/config.json
```

### 向 Agent 发送消息
```bash
SendMessage to: claim-validator
message: 开始审查任务，输入文件在 ./review-inputs/
```

### 关闭团队
```bash
SendMessage to: "*"
message: {"type": "shutdown_request", "reason": "任务完成"}
```

## 注意事项

1. **必须发现 ≥3 个问题** - 如果 coordinator 报告 <3 个问题，需要重新审查
2. **Critical 问题必须修复** - 才能进入 P7
3. **保留所有审查记录** - 作为研究方法论的一部分
4. **中文输入中文输出** - 所有 agent 支持中英文双语
