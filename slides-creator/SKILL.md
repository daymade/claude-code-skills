---
name: slides-creator
description: >-
  【DEPRECATED · 已废弃】本 skill 已于 2026-08-07 停止维护。对作者本机环境：其方法论
  （First Law 用户原话优先 / ABCDEFG 叙事框架 / baoyu-slide-deck 委托协议 / 四层目录治理）
  已整体并入 deck-creator（私有仓 daymade-skills-pro 的 Route A · narrative），
  装有 deck-creator 的环境不要调用本 skill。对外部用户：这是最终版本，
  保留安装兼容，不再接收更新。将在后续大版本中物理移除。
---

# slides-creator —— DEPRECATED（2026-08-07）

**本 skill 已废弃，停止维护。** 保留此 stub 仅为已安装环境的兼容性通告。

## 发生了什么

PPT 工具链于 2026-08-07 合并：ppt-creator / slides-creator / html-to-ppt / 项目内嵌 pptx_builder
四个工具合并为单一入口 **deck-creator**。本 skill 的方法论已整体并入 deck-creator 的
**Route A · narrative**（First Law 用户原话优先 + ABCDEFG 叙事讨论 + baoyu 图像轨委托协议
+ code 可编辑轨 + 四层目录治理）。

## 不同用户怎么办

| 你是谁 | 怎么办 |
|---|---|
| daymade 本机环境 | 用 `deck-creator`（私有仓 daymade-skills-pro，Route A）。不要再调用本 skill |
| 外部用户（公共 marketplace 安装） | 本版本是最终版，可继续用但不再更新；deck-creator 在私有仓不对外分发 |

## 为什么合并

碎片化（5 个 PPT 工具）已造成真实路由失败：agent 只知部分候选时给出了被客户否决过的方案。
本 skill 的 First Law 与目录治理仍是 deck-creator Route A 的核心——能力没有消失，是搬了家。
