---
name: wechat-article-scraper
description: 世界级微信公众号文章抓取工具，支持智能策略路由、图片下载、搜狗搜索发现、多格式导出。当用户需要下载/保存微信文章、提取公众号正文、批量归档微信内容、通过关键词发现公众号文章、将微信文章转为 PDF 时使用。支持 HTTP/Playwright/Chrome DevTools 三种策略自动切换，具备懒加载图片提取、本地图片下载、反爬绕过等高级功能。
argument-hint: [article-url] [--strategy fast|stable|reliable] [--download-images]
metadata:
  version: "2.0.0"
  openclaw:
    emoji: "📰"
    requires:
      bins: ["python3"]
---

# 微信公众号文章抓取 v2.0

**世界级微信文章抓取方案** — 整合 12 个竞品的精华，具备智能策略路由、懒加载处理、图片下载、搜索发现、多格式导出等完整功能。

## 核心能力

| 能力 | 说明 | 竞品对比 |
|------|------|----------|
| 智能策略路由 | 自动选择最佳抓取策略（HTTP/Playwright/Chrome DevTools） | **独有** |
| 懒加载处理 | 滚动触发图片加载，正确提取 `data-src` 真实 URL | 仅 2/12 竞品支持 |
| 反爬绕过 | 自动添加 `?scene=1` 参数降低风控概率 | 仅 1/12 竞品知晓 |
| 图片下载 | 并行下载图片到本地，避免 URL 过期 | 仅 2/12 竞品支持 |
| 搜狗搜索 | 通过关键词发现微信公众号文章 | 仅 1/12 竞品支持 |
| 多格式导出 | Markdown / JSON / HTML / PDF | 仅 3/12 竞品支持 |

## 前置要求

### 方案 A：Chrome DevTools 模式（推荐，最可靠）

**⚠️ 必须先完成微信登录**：
1. 在 Chrome 浏览器中访问 https://mp.weixin.qq.com
2. 扫码完成微信登录
3. 保持浏览器窗口打开（登录态会保持一段时间）

### 方案 B：Playwright 模式（无需登录，但可能触发验证码）

```bash
pip install playwright
playwright install chromium
```

### 方案 C：Fast 模式（无需任何依赖，但容易被拦截）

```bash
pip install requests beautifulsoup4 lxml
```

## 使用方式

### 基础用法

```bash
# 自动选择最佳策略
/wechat-article-scraper "https://mp.weixin.qq.com/s/xxxxx"

# 指定策略
/wechat-article-scraper "https://mp.weixin.qq.com/s/xxxxx" --strategy reliable

# 下载图片到本地
/wechat-article-scraper "https://mp.weixin.qq.com/s/xxxxx" --download-images

# 导出为 PDF
/wechat-article-scraper "https://mp.weixin.qq.com/s/xxxxx" --format pdf
```

### 搜索发现

```bash
# 通过关键词搜索公众号文章
python3 scripts/search.py "人工智能投资" -n 10 --format markdown

# 按时间筛选
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
| **fast** | ⚡⚡⚡ | ⭐⭐ | requests + BS4 | 快速测试、批量抓取 |
| **stable** | ⚡⚡ | ⭐⭐⭐ | Playwright | 中等重要度文章 |
| **reliable** | ⚡ | ⭐⭐⭐⭐⭐ | Chrome + 登录态 | 重要文章、确保成功 |

### 策略路由逻辑

```
用户请求抓取文章
    │
    ├─ 指定了优先策略？
    │  ├─ 是 → 优先尝试该策略
    │  └─ 否 → 按 fast → stable → reliable 顺序尝试
    │
    ├─ 当前策略失败？
    │  ├─ 是 → 自动降级到下一策略
    │  └─ 否 → 返回成功结果
    │
    └─ 所有策略失败 → 返回详细错误信息
```

## 技术实现

### 关键技巧 1：?scene=1 参数

微信反爬机制对带 `scene=1` 参数的 URL 容忍度更高：

```python
# 自动处理 URL，添加 scene=1
if '?' not in url:
    url = url + '?scene=1'
elif 'scene=' not in url:
    url = url + '&scene=1'
```

### 关键技巧 2：懒加载图片提取

微信文章图片初始为占位符，需滚动触发加载：

```javascript
// 提取真实图片 URL
const realSrc = img.getAttribute('data-src') || img.src;
if (realSrc && !realSrc.includes('data:image/svg+xml')) {
    images.push({ src: realSrc, alt: img.alt });
}
```

### 关键技巧 3：装饰性图片过滤

自动过滤以下非内容图片：
- 1x1 像素占位图
- SVG 透明图
- 微信装饰性图标
- 小于 50px 的表情包

## 文件结构

```
wechat-article-scraper/
├── SKILL.md                    # 本文件
├── scripts/
│   ├── scraper.py             # 主入口脚本
│   ├── router.py              # 智能策略路由器
│   ├── images.py              # 图片下载模块
│   ├── search.py              # 搜狗搜索模块
│   ├── export.py              # 多格式导出模块
│   └── extract.js             # Chrome DevTools 提取脚本
├── references/
│   └── failed-approaches.md   # 失败方案记录（DO NOT ATTEMPT）
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
- 登录态过期（需要重新扫码）
- 文章包含视频（只能提取封面，视频需单独处理）

### 图片处理限制
- 图片 URL 有时效性（默认 30 天），长期保存建议开启 `--download-images`
- 微信 CDN 图片可能带水印
- GIF 动图可能只保存第一帧

### 批量抓取限制
- 搜狗搜索有频率限制，建议间隔 2 秒以上
- 同一 IP 短时间内大量请求可能触发验证码
- 建议单批次不超过 50 篇

## 高级用法

### 批量抓取脚本

```bash
#!/bin/bash
# 从文件读取 URL 列表批量抓取

URLS_FILE="urls.txt"
OUTPUT_DIR="./articles"

while IFS= read -r url; do
    echo "抓取: $url"
    python3 scripts/scraper.py "$url" \
        --strategy reliable \
        --download-images \
        --output "$OUTPUT_DIR"
    sleep 3  # 避免风控
done < "$URLS_FILE"
```

### 整合到 Workflow

```python
# 在 Python 中调用
import subprocess
import json

result = subprocess.run(
    ['python3', 'scripts/scraper.py', url, '--json-output'],
    capture_output=True, text=True
)

data = json.loads(result.stdout)
if data['success']:
    print(f"保存到: {data['output_path']}")
```

## 输出示例

### Markdown 格式

```markdown
---
title: 文章标题
author: 公众号名称
publish_time: 2026-04-01
source_url: https://mp.weixin.qq.com/s/xxxxx
exported_at: 2026-04-12T10:30:00
---

# 文章标题

**作者**: 公众号名称  
**发布时间**: 2026-04-01  
**来源**: https://mp.weixin.qq.com/s/xxxxx

---

正文内容...

![图片描述](images/img-001.jpg)

---

*本文档由 wechat-article-scraper 生成*
```

### JSON 格式

```json
{
  "title": "文章标题",
  "author": "公众号名称",
  "publishTime": "2026-04-01",
  "content": "正文内容...",
  "images": [
    {"src": "https://mmbiz.qpic.cn/...", "alt": "图片描述"}
  ],
  "source_url": "https://mp.weixin.qq.com/s/xxxxx",
  "_export_meta": {
    "version": "2.0.0",
    "exported_at": "2026-04-12T10:30:00"
  }
}
```

## 版本历史

### v2.0.0 (当前)
- ✨ 智能策略路由器，自动选择最佳抓取策略
- ✨ 图片下载模块，支持并行下载和本地存储
- ✨ 搜狗搜索集成，通过关键词发现文章
- ✨ 多格式导出（Markdown/JSON/HTML/PDF）
- ✨ 自动添加 `?scene=1` 反爬绕过
- ✨ 装饰性图片智能过滤

### v1.0.0
- ✅ Chrome DevTools MCP 抓取
- ✅ 懒加载图片处理
- ✅ 基础 Markdown 导出

## 竞品对比总结

分析了 12 个微信文章抓取相关 Skill 后，本方案整合的优势：

| 功能 | 本方案 | 竞品最佳 | 差距 |
|------|--------|----------|------|
| 懒加载处理 | ✅ | ✅ | 持平 |
| 策略路由 | ✅ | ❌ | **领先** |
| 图片下载 | ✅ | 部分 | **领先** |
| 搜索发现 | ✅ | 少数 | **持平** |
| 多格式导出 | ✅ | 少数 | **持平** |
| 反爬绕过 | ✅ | 少数 | **持平** |

**核心差异化**：智能策略路由器 + 完整的图片处理 + 一站式解决方案
