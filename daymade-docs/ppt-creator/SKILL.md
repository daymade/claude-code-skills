---
name: ppt-creator
description: >-
  【DEPRECATED · 已废弃】本 skill 已于 2026-08-07 停止维护。对作者本机环境：其方法论已整体并入
  deck-creator（私有仓 daymade-skills-pro 的 Route B · draft），装有 deck-creator 的环境不要调用本 skill。
  对外部用户：这是最终版本，保留安装兼容，不再接收更新——你可以继续按本文档使用，
  但请知悉上游已冻结。将在 daymade-docs v2.0.0 中物理移除。
---

# ppt-creator —— DEPRECATED（2026-08-07）

**本 skill 已废弃，停止维护。** 保留此 stub 仅为已安装环境的兼容性通告。

## 发生了什么

PPT 工具链于 2026-08-07 合并：ppt-creator / slides-creator / html-to-ppt / 项目内嵌 pptx_builder
四个工具合并为单一入口 **deck-creator**。本 skill 的方法论（INTAKE 10 问 / Pyramid Principle 工作流 /
assertion-evidence 模板 / VIS-GUIDE 图表选型 / STYLE-GUIDE / RUBRIC 评分）已整体并入
deck-creator 的 **Route B · draft**。

## 不同用户怎么办

| 你是谁 | 怎么办 |
|---|---|
| daymade 本机环境 | 用 `deck-creator`（私有仓 daymade-skills-pro，Route B）。不要再调用本 skill |
| 外部用户（公共 marketplace 安装） | 本版本是最终版，可继续用但不再更新；deck-creator 在私有仓不对外分发。v2.0.0 将物理移除本目录 |

## 为什么合并

碎片化（5 个 PPT 工具）已造成真实路由失败：agent 只知部分候选时给出了被客户否决过的方案。
合并的完整论证见作者私有知识库（ppt-tools-guide.md，2026-08-07）。
