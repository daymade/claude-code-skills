---
name: wechat-article-scraper
description: 抓取微信公众号文章内容，提取正文、图片和元数据，输出为 Markdown 或 JSON。支持智能策略路由（HTTP/Playwright/Chrome DevTools）、懒加载图片提取、本地图片下载、搜狗搜索发现等功能。当用户需要下载/保存微信文章、批量归档公众号内容、提取微信图文资料时使用。
argument-hint: <article-url> [--strategy fast|stable|reliable] [--download-images] [--format markdown|json|html|pdf]
metadata:
  version: "2.0.0"
  openclaw:
    emoji: "📰"
    requires:
      bins: ["python3"]
---

# 微信公众号文章抓取 v2.0

**世界级微信文章抓取方案** — 整合 12 个竞品的精华，具备智能策略路由、懒加载处理、图片下载、搜索发现、多格式导出等完整功能。

## 快速开始

```bash
# 抓取单篇文章（自动选择最佳策略）
/wechat-article-scraper "https://mp.weixin.qq.com/s/xxxxx"

# 下载图片到本地
/wechat-article-scraper "https://mp.weixin.qq.com/s/xxxxx" --download-images

# 导出为 PDF
/wechat-article-scraper "https://mp.weixin.qq.com/s/xxxxx" --format pdf

# 搜索公众号文章
python3 scripts/search.py "人工智能投资" -n 10
```

## 核心能力

| 能力 | 说明 | 竞品对比 |
|------|------|----------|
| 智能策略路由 | 自动选择最佳抓取策略（HTTP/Playwright/Chrome DevTools） | **独有** |
| 懒加载处理 | 滚动触发图片加载，正确提取 `data-src` 真实 URL | 仅 2/12 竞品支持 |
| 反爬绕过 | `?scene=1` 参数可绕过登录验证（已验证） | 仅 1/12 竞品知晓 |
| 图片下载 | 并行下载图片到本地，避免 URL 过期 | 仅 2/12 竞品支持 |
| 搜狗搜索 | 通过关键词发现微信公众号文章 | 仅 1/12 竞品支持 |
| 多格式导出 | Markdown / JSON / HTML / PDF | 仅 3/12 竞品支持 |

## 前置要求

**⚠️ 重要发现**: 使用 `?scene=1` 参数可绕过微信登录要求（已验证）。如果抓取失败，再考虑登录微信。

### 方案 A：Chrome DevTools 模式（推荐，最可靠）

**大多数情况下无需登录**，如果抓取失败：
1. 在 Chrome 浏览器中访问 https://mp.weixin.qq.com
2. 扫码完成微信登录
3. 保持浏览器窗口打开

### 方案 B：Playwright 模式

```bash
pip install playwright
playwright install chromium
```

### 方案 C：Fast 模式

```bash
pip install requests beautifulsoup4 lxml
```

## 使用方式

### CLI 用法

```bash
# 基础用法
python3 scripts/scraper.py "<url>"

# 完整参数
python3 scripts/scraper.py "<url>" \
    --strategy reliable \
    --format markdown \
    --output ./articles \
    --download-images
```

### 在 Claude Code 中使用

```
User: 抓取这篇微信文章 https://mp.weixin.qq.com/s/xxxxx
Claude: 使用 Chrome DevTools MCP 抓取:
        1. 导航到文章页面（自动添加 ?scene=1）
        2. 滚动触发懒加载
        3. 提取内容
        4. 保存到 Clippings/文章标题.md
```

实际调用代码：
```javascript
// 步骤 1: 导航到文章（自动添加 ?scene=1）
mcp__chrome-devtools__navigate_page({
  type: "url",
  url: "https://mp.weixin.qq.com/s/xxxxx?scene=1"
});

// 步骤 2: 执行提取脚本
mcp__chrome-devtools__evaluate_script({
  function: extractArticle  // 见 scripts/extract.js
});
```

### 搜索发现

```bash
# 搜索公众号文章
python3 scripts/search.py "关键词" -n 10 --format markdown

# 按时间筛选（day/week/month/year）
python3 scripts/search.py "新能源汽车" --time week -n 20
```

### 批量下载已有 Markdown 中的图片

```bash
python3 scripts/images.py "文章.md" --output ./article-images/
```

## 策略详解

### 策略对比

| 策略 | 速度 | 稳定性 | 前置要求 | 适用场景 |
|------|------|--------|----------|----------|
| **fast** | ⚡⚡⚡ | ⭐⭐ | requests + BS4 | 快速测试 |
| **stable** | ⚡⚡ | ⭐⭐⭐ | Playwright | 批量抓取 |
| **reliable** | ⚡ | ⭐⭐⭐⭐⭐ | Chrome DevTools | 重要文章 |

### 策略路由逻辑

```
用户请求
    │
    ├─ 指定策略？
    │  ├─ 是 → 优先使用该策略
    │  └─ 否 → 按 fast → stable → reliable 顺序尝试
    │
    ├─ 失败？
    │  ├─ 是 → 自动降级到下一策略
    │  └─ 否 → 返回成功结果
    │
    └─ 全部失败 → 返回错误代码和恢复建议
```

## 错误代码与恢复

| 错误代码 | 错误描述 | 恢复操作 |
|----------|----------|----------|
| E001 | 未找到文章内容 | 检查 URL 是否正确，文章是否被删除 |
| E002 | 触发反爬验证 | 尝试登录微信后重试，或等待 5 分钟后重试 |
| E003 | 登录态过期 | 重新访问 https://mp.weixin.qq.com 扫码登录 |
| E004 | 网络超时 | 检查网络连接，或增加超时参数 |
| E005 | 策略全部失败 | 检查依赖是否安装，或报告问题 |

## 技术实现

### 关键技巧 1：?scene=1 参数（绕过登录）

**已验证**: 使用 `?scene=1` 参数可以在无登录状态下获取文章内容。

```python
# 自动处理 URL
if '?' not in url:
    url = url + '?scene=1'
elif 'scene=' not in url:
    url = url + '&scene=1'
```

### 关键技巧 2：懒加载图片提取

```javascript
// 提取真实图片 URL
const realSrc = img.getAttribute('data-src') || img.src;
if (realSrc && !realSrc.includes('data:image/svg+xml')) {
    images.push({ src: realSrc, alt: img.alt });
}
```

### 关键技巧 3：装饰性图片过滤

```python
# 过滤规则
- SVG 占位符: data:image/svg+xml
- 装饰图路径: yZPTcMGWibvsic9Obib
- 尺寸过小: < 50px
```

## 文件结构

```
wechat-article-scraper/
├── SKILL.md                    # 本文档
├── scripts/
│   ├── scraper.py             # 主入口
│   ├── router.py              # 策略路由器
│   ├── images.py              # 图片下载
│   ├── search.py              # 搜狗搜索
│   ├── export.py              # 多格式导出
│   ├── extract.js             # Chrome DevTools 提取脚本
│   └── playwright_scraper.py  # Playwright 抓取
├── references/
│   └── failed-approaches.md   # 失败方案记录
└── evals/
    └── evals.json             # 评测用例
```

## 失败方案记录（DO NOT ATTEMPT）

| 方案 | 失败模式 | 根因 | 经验教训 |
|------|----------|------|----------|
| WebFetch 直接抓取 | 返回"环境异常"验证页 | 微信反爬检测非浏览器 UA | 必须使用真实浏览器或高质量 UA |
| Snapshot 方式 | 图片为占位符 SVG | 未触发懒加载，data-src 未转换 | 必须滚动页面触发加载 |
| opencli 探索 | 无微信 CLI 可用 | 微信未开放公开 API | 不要浪费时间寻找不存在的 CLI |
| curl/wget | 被拦截返回验证页 | 缺少浏览器 Cookie 和 UA | 命令行工具无法绕过现代反爬 |
| r.jina.ai 服务 | 偶尔超时 | 第三方服务不稳定 | 作为 fallback，不要依赖 |

## 限制与边界

### 无法抓取的情况
- 文章被删除或违规下架
- 需要付费阅读的内容（只能抓取预览部分）
- 文章包含视频（只能提取封面，视频需单独处理）

### 图片处理限制
- 图片 URL 有时效性（默认 30 天），长期保存建议开启 `--download-images`
- 微信 CDN 图片可能带水印
- GIF 动图可能只保存第一帧

### 批量抓取限制
- 搜狗搜索有频率限制，建议间隔 2 秒以上
- 同一 IP 短时间内大量请求可能触发验证码
- 建议单批次不超过 50 篇

## 输出示例

### Markdown 格式（带 YAML Front Matter）

```markdown
---
title: AlphaClaw投研小龙虾第三讲
author: 熵简科技Value Simplex
publish_time: 2026年4月2日 18:59
source_url: https://mp.weixin.qq.com/s/xxxxx
exported_at: 2026-04-12T10:30:00
---

# AlphaClaw投研小龙虾第三讲：接入iFind数据源

**作者**: 熵简科技Value Simplex  
**发布时间**: 2026年4月2日 18:59  
**来源**: https://mp.weixin.qq.com/s/xxxxx

---

一个月前，AlphaEngine 正式推出了 AlphaClaw 功能...

![配图 1](https://mmbiz.qpic.cn/mmbiz_png/xxxxx/640)

---

*本文档由 wechat-article-scraper 于 2026-04-12 生成*
```

### JSON 格式

```json
{
  "title": "AlphaClaw投研小龙虾第三讲",
  "author": "熵简科技Value Simplex",
  "publishTime": "2026年4月2日 18:59",
  "content": "一个月前，AlphaEngine 正式推出了...",
  "images": [
    {
      "src": "https://mmbiz.qpic.cn/mmbiz_png/xxxxx/640",
      "alt": "配图 1"
    }
  ],
  "source_url": "https://mp.weixin.qq.com/s/xxxxx",
  "_export_meta": {
    "version": "2.0.0",
    "exported_at": "2026-04-12T10:30:00",
    "strategy": "reliable"
  }
}
```

## 批量抓取示例

```bash
#!/bin/bash
# 批量抓取脚本

URLS_FILE="urls.txt"
OUTPUT_DIR="./articles"
mkdir -p "$OUTPUT_DIR"

count=0
while IFS= read -r url; do
    count=$((count + 1))
    echo "[$count] 抓取: $url"
    
    python3 scripts/scraper.py "$url" \
        --strategy reliable \
        --output "$OUTPUT_DIR" \
        --download-images
    
    # 间隔 3 秒避免风控
    sleep 3
done < "$URLS_FILE"

echo "完成: 共抓取 $count 篇文章"
```

## 版本历史

### v2.0.0 (当前)
- ✨ **重大发现**: `?scene=1` 参数可绕过微信登录（已验证）
- ✨ 智能策略路由器，自动选择最佳抓取策略
- ✨ 图片下载模块，支持并行下载和本地存储
- ✨ 搜狗搜索集成，通过关键词发现文章
- ✨ 多格式导出（Markdown/JSON/HTML/PDF）
- ✨ 装饰性图片智能过滤

### v1.0.0
- ✅ Chrome DevTools MCP 抓取
- ✅ 懒加载图片处理
- ✅ 基础 Markdown 导出

## 竞品对比总结

| 功能 | 本方案 | 竞品最佳 | 差距 |
|------|--------|----------|------|
| 懒加载处理 | ✅ | ✅ | 持平 |
| 策略路由 | ✅ | ❌ | **领先** |
| 图片下载 | ✅ | 部分 | **领先** |
| 搜索发现 | ✅ | 少数 | **持平** |
| 多格式导出 | ✅ | 少数 | **持平** |
| 反爬绕过 | ✅ | 少数 | **持平** |

**核心差异化**：智能策略路由器 + 完整的图片处理 + 一站式解决方案
