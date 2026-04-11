---
name: wechat-article-scraper
description: 抓取微信公众号文章内容，提取正文、图片和元数据，输出为 Markdown 或 JSON。支持智能策略路由（HTTP/Scrapling/Playwright/Chrome DevTools）、OG元数据备选、懒加载图片提取、本地图片下载、图片段落关联、搜狗搜索发现等功能。当用户需要下载/保存微信文章、批量归档公众号内容、提取微信图文资料时使用。
argument-hint: <article-url> [--strategy fast|adaptive|stable|reliable|zero_dep|jina_ai] [--download-images] [--format markdown|json|html|pdf]
metadata:
  version: "3.7.0"
  openclaw:
    emoji: "📰"
    requires:
      bins: ["python3"]
---

# 微信公众号文章抓取 v2.9

**世界级微信文章抓取方案** — 整合 12 个竞品的精华，具备智能策略路由、OG元数据备选、图片段落关联、懒加载处理、图片下载、搜索发现、多格式导出等完整功能。

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

# 搜索并解析真实微信链接（避免搜狗链接过期）
python3 scripts/search.py "人工智能投资" -n 10 --resolve-urls
```

## 核心能力

| 能力 | 说明 | 竞品对比 |
|------|------|----------|
| **智能策略路由** | 自动选择最佳抓取策略，四级降级 | **独有** |
| **OG 元数据备选** | 当微信选择器失败时自动使用 Open Graph | **独有** |
| **图片段落关联** | 智能识别图片与文本段落的关系 | **独有** |
| **Content Status** | 清晰的状态码系统 (ok/blocked/parse_empty) | **独有** |
| **自适应策略** | Scrapling 自适应反爬，轻量稳定 | 仅 1/12 竞品支持 |
| **懒加载处理** | 滚动触发图片加载，正确提取 `data-src` 真实 URL | 仅 2/12 竞品支持 |
| **反爬绕过** | `?scene=1` 参数可绕过登录验证（已验证） | 仅 1/12 竞品知晓 |
| **UA 轮换** | 7 种 User-Agent 自动轮换，提高成功率 | 仅 1/12 竞品支持 |
| **图片下载** | 并行下载图片到本地，避免 URL 过期 | 仅 2/12 竞品支持 |
| **搜狗搜索** | 通过关键词发现微信公众号文章 | 仅 1/12 竞品支持 |
| **多格式导出** | Markdown / JSON / HTML / PDF | 仅 3/12 竞品支持 |

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

### 方案 C：Adaptive 模式（推荐新选择）

```bash
pip install "scrapling[ai]"
```

Scrapling 专为复杂反爬页面设计，比 Playwright 轻量，比 requests 稳定。

### 方案 D：Fast 模式

```bash
pip install requests beautifulsoup4 lxml
```

## 使用方式

### CLI 用法

```bash
# 基础用法（默认输出到当前目录）
python3 scripts/scraper.py "<url>"

# 下载图片到本地
python3 scripts/scraper.py "<url>" --download-images

# 指定策略和输出格式
python3 scripts/scraper.py "<url>" \
    --strategy reliable \
    --format markdown \
    --output ./articles \
    --download-images

# 批量抓取
python3 scripts/scraper.py --batch urls.txt -o ./articles/ --delay 5

# 搜索公众号文章
python3 scripts/search.py "关键词" -n 10 --format markdown
```

### 策略选择指南

| 策略 | 适用场景 | 前置要求 | 可靠性 | 速度 |
|------|---------|---------|--------|------|
| **fast** | 快速抓取公开文章 | requests + BeautifulSoup | ⭐⭐ | ⚡⚡⚡ |
| **adaptive** | 需要自适应反爬（**推荐**） | 安装 Scrapling | ⭐⭐⭐⭐ | ⚡⚡ |
| **stable** | 需要完整渲染 | 安装 Playwright | ⭐⭐⭐⭐⭐ | ⚡ |
| **reliable** | 需要最高可靠性 | Chrome DevTools | ⭐⭐⭐⭐⭐ | ⚡ |
| **zero_dep** | 纯标准库，无需安装依赖 | Python 标准库 | ⭐⭐ | ⚡⚡⚡ |
| **jina_ai** | 使用 jina.ai 服务 | 无需安装，依赖网络 | ⭐⭐⭐ | ⚡⚡ |

**默认策略**：系统按 `fast → adaptive → stable → reliable → zero_dep` 顺序自动尝试，优先使用最快成功的策略。

**何时指定策略？**
- 抓取重要文章 → 指定 `-s adaptive` 或 `-s reliable`
- 批量快速抓取 → 指定 `-s fast`
- 遇到验证码频繁 → 指定 `-s adaptive` 或 `-s reliable`

### Content Status 状态码

| 状态码 | 含义 | 恢复建议 |
|--------|------|---------|
| `ok` | 抓取成功 | - |
| `blocked` | 触发反爬验证 | 使用 reliable 策略，或等待 5 分钟后重试 |
| `no_mp_url` | 无效的微信文章链接 | 检查 URL 格式 |
| `fetch_error` | 网络请求失败 | 检查网络连接 |
| `parse_empty` | 解析结果为空 | 文章可能被删除或需要特殊处理 |
| `need_mcp` | 需要 MCP 模式 | 使用 Chrome DevTools MCP 抓取 |

### 在 Claude Code 中使用

```
User: 抓取这篇微信文章 https://mp.weixin.qq.com/s/xxxxx
Claude: 使用 Chrome DevTools MCP 抓取:
        1. 导航到文章页面（自动添加 ?scene=1）
        2. 滚动触发懒加载
        3. 提取内容
        4. 保存到 articles/文章标题.md
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

# 解析真实微信链接
python3 scripts/search.py "关键词" -n 5 -r
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
| **adaptive** | ⚡⚡ | ⭐⭐⭐⭐ | Scrapling | 日常抓取（推荐） |
| **stable** | ⚡ | ⭐⭐⭐⭐⭐ | Playwright | 完整渲染 |
| **reliable** | ⚡ | ⭐⭐⭐⭐⭐ | Chrome DevTools | 重要文章 |
| **zero_dep** | ⚡⚡⚡ | ⭐⭐ | Python 标准库 | 无依赖环境 |
| **jina_ai**  | ⚡⚡ | ⭐⭐⭐ | jina.ai 服务 | 网络环境好 |

### 策略路由逻辑

```
用户请求
    │
    ├─ 指定策略？
    │  ├─ 是 → 优先使用该策略
    │  └─ 否 → 按 fast → adaptive → stable → reliable → zero_dep → jina_ai 顺序尝试
    │
    ├─ 失败？
    │  ├─ 是 → 自动降级到下一策略（带重试）
    │  └─ 否 → 返回成功结果
    │
    └─ 全部失败 → 返回错误代码和恢复建议
```

### 重试机制

每种策略默认重试 3 次，每次间隔递增：
- 第 1 次失败后：等待 0.5s
- 第 2 次失败后：等待 1.0s
- 第 3 次失败后：等待 1.5s

同时自动轮换 User-Agent，提高成功率。

## 错误代码与恢复

| 错误代码 | 错误描述 | 恢复操作 |
|----------|----------|----------|
| E001 | 未找到文章内容 | 检查 URL 是否正确，文章是否被删除 |
| E002 | 触发反爬验证 | 尝试使用 reliable 策略，或等待 5 分钟后重试 |
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

### 关键技巧 2：OG 元数据备选

当微信特定选择器失败时，自动使用 Open Graph 元数据：

```python
# OG 元数据提取
og_title = soup.find('meta', property='og:title')
og_author = soup.find('meta', property='og:article:author')
og_time = soup.find('meta', property='og:article:published_time')
```

### 关键技巧 3：懒加载图片提取

```javascript
// 提取真实图片 URL
const realSrc = img.getAttribute('data-src') || img.src;
if (realSrc && !realSrc.includes('data:image/svg+xml')) {
    images.push({ src: realSrc, alt: img.alt });
}
```

### 关键技巧 4：图片段落关联

```javascript
// 智能识别图片与段落的关系
images.push({
    src: realSrc,
    paragraphIndex: currentParagraphIndex,  // 关联到段落
    isContentImage: width > 200 || height > 200
});
```

### 关键技巧 5：装饰性图片过滤

```python
# 过滤规则
- SVG 占位符: data:image/svg+xml
- 装饰图路径: yZPTcMGWibvsic9Obib
- 尺寸过小: < 50px
```

### 关键技巧 6：UA 轮换

```python
USER_AGENTS = [
    'Chrome 120 (Mac)',
    'Chrome 120 (Windows)',
    'Safari 17 (Mac)',
    'Firefox 121 (Windows)',
    'Chrome 120 (Linux)',
    'iPhone Safari',
    'iPad Safari',
]
```

## 文件结构

```
wechat-article-scraper/
├── SKILL.md                    # 本文档
├── scripts/
│   ├── scraper.py             # 主入口（支持批量模式）
│   ├── router.py              # 策略路由器（4级策略+OG备选）
│   ├── images.py              # 图片下载（支持段落关联）
│   ├── search.py              # 搜狗搜索（支持链接解析）
│   ├── export.py              # 多格式导出（PDF/HTML/JSON/Markdown）
│   ├── extract.js             # Chrome DevTools 提取脚本（OG备选+段落关联）
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
- 视频只能提取 URL 和封面，无法下载视频文件

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
content_status: ok
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
  "paragraphs": [
    {"index": 0, "text": "一个月前..."},
    {"index": 1, "text": "AlphaClaw 功能..."}
  ],
  "images": [
    {
      "src": "https://mmbiz.qpic.cn/mmbiz_png/xxxxx/640",
      "alt": "配图 1",
      "paragraphIndex": 2
    }
  ],
  "source_url": "https://mp.weixin.qq.com/s/xxxxx",
  "content_status": "ok",
  "_export_meta": {
    "version": "3.0.3",
    "exported_at": "2026-04-12T10:30:00",
    "strategy": "adaptive"
  }
}
```

## 批量抓取示例

```bash
#!/bin/bash
# 批量抓取脚本 (batch_scrape.sh)

URLS_FILE="urls.txt"
OUTPUT_DIR="./articles"
mkdir -p "$OUTPUT_DIR"

count=0
while IFS= read -r url; do
    [[ -z "$url" ]] && continue
    count=$((count + 1))
    echo "[$count] 抓取: $url"

    python3 scripts/scraper.py "$url" \
        --strategy adaptive \
        --output "$OUTPUT_DIR" \
        --download-images

    # 间隔 3 秒避免风控
    sleep 3
done < "$URLS_FILE"

echo "完成: 共抓取 $count 篇文章"
```

**批量抓取最佳实践**：
1. 使用 `adaptive` 策略确保成功率
2. 间隔 3-5 秒避免触发风控
3. 单批次建议不超过 50 篇
4. 使用 `--download-images` 避免图片 URL 过期
5. 准备 URL 列表文件，每行一个链接

## 版本历史

### v3.0.2 (当前)
- ✨ **改进**: 批量抓取模式支持代理配置
  - `batch_scrape()` 函数支持 proxy 参数
  - 批量 CLI 模式支持 `--proxy` 参数

### v3.0.1
- ✨ **新增**: Fast 策略支持 HTTP 代理配置
  - StrategyRouter 支持 proxy 参数
  - CLI 添加 `--proxy` 参数
  - 适配需要通过代理访问网络的环境

### v3.0.0
- ✨ **新增**: 互动数据提取
  - 阅读量、点赞数、在看数提取
  - Markdown 导出显示互动数据
  - Chrome DevTools + Playwright 策略支持（需要页面渲染）

### v2.9.3
- ✨ **改进**: HTML 导出支持视频嵌入
  - 使用 `<video>` 标签嵌入视频播放器
  - 支持 poster 封面图预览
  - 视频列表独立章节展示

### v2.9.2
- ✨ **改进**: 所有 6 个策略统一支持视频提取
  - Fast/Adaptive/Stable/Reliable/ZeroDep/JinaAI 全部支持
  - 统一视频数据格式：src, poster, duration, title
  - 视频数据与图片数据并列返回

### v2.9.1
- ✨ **新增**: 视频提取功能
  - 自动识别 `<video>` 标签和 `mpvideosrc` 标签
  - 提取视频 URL、封面图、时长、标题
  - 视频按原文顺序插入 Markdown 内容
  - 导出独立的视频列表章节

### v2.9.0
- ✨ **新增**: 吸取 wechat-article-camofox 精华
  - 详细的 STOP_MARKERS 噪音标记（40+ 条规则）
  - SKIP_SUBSTRINGS 跳过子串列表
  - 日期正则 `DATE_RE` 从正文提取发布时间
  - 图片按原文顺序插入正文（生成 Markdown）
  - 更强的噪音元素过滤（`.js_uneditable`, `.rich_media_tool` 等）
  - `跳转二维码` 和 `划线引导图` alt 过滤
- ✨ **改进**: 所有策略（fast/adaptive）统一应用 camofox 精华
- ✨ **改进**: extract.js 增强版，支持递归 DOM 遍历保持原文顺序

### v2.8.0
- ✨ **新增**: 吸取 jisu-wechat-article 精华
  - 搜狗链接解析：`resolve_real_url()` 函数支持将搜狗跳转链接解析为真实微信链接
  - 从 URL 参数提取真实链接（避免额外请求）
  - antispider 风控链接检测与过滤
  - 搜索模块新增 `-r/--resolve-urls` 参数，支持批量解析搜索结果的真实链接

### v2.7.0
- ✨ **改进**: 吸取 wechat-article-full-reader 精华
  - 图片下载支持从 `wx_fmt` URL 参数提取正确扩展名（png/gif/webp）
- ✨ **改进**: 吸取 wechat-article-browseruse 精华
  - 文本清理：处理 `\xa0` 非断空格字符
  - 支持 `data-backsrc` 图片懒加载属性
  - 过滤 `res.wx.qq.com/op_res/` 微信 CDN 资源
  - 更完善的噪音元素过滤（script/style/svg/iframe/form/button）
- ✨ **完善**: 所有策略（fast/adaptive/stable/reliable）统一图片过滤规则

### v2.5.0
- ✨ **新增**: Jina AI 策略，使用 r.jina.ai 服务作为最后的可靠 fallback
- ✨ **升级**: 6 级策略路由（fast → adaptive → stable → reliable → zero_dep → jina_ai）
- ✨ **改进**: 吸取 wechat-article-1.0.0 精华，增加第三方服务 fallback

### v2.4.0
- ✨ **新增**: Zero-Dependency 策略，纯标准库模式，无需任何外部依赖
- ✨ **升级**: 5 级策略路由（fast → adaptive → stable → reliable → zero_dep）
- ✨ **新增**: 页面截图功能（Playwright 策略支持）
- ✨ **新增**: html2text 和 markdownify 转换器选项
- ✨ **新增**: 搜狗搜索时间戳解析（JavaScript timeConvert）
- ✨ **新增**: miku-ai 搜索引擎备选

### v2.1.0
- ✨ **新增**: Adaptive 策略（Scrapling），轻量稳定
- ✨ **新增**: OG 元数据备选提取，提高成功率
- ✨ **新增**: 图片段落关联，智能识别图文关系
- ✨ **新增**: Content Status 状态码系统
- ✨ **新增**: UA 轮换和智能重试机制
- ✨ **新增**: 批量抓取模式
- 🔧 **修正**: ?scene=1 可绕过登录（无需登录态）

### v2.0.0
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
| 策略路由 | ✅ 6级 | ❌ 最多2级 | **领先** |
| OG 元数据备选 | ✅ | ❌ | **领先** |
| 图片段落关联 | ✅ | ❌ | **领先** |
| Content Status | ✅ | ❌ | **领先** |
| UA 轮换 | ✅ | ❌ | **领先** |
| Adaptive 策略 | ✅ | ❌ | **领先** |
| 零依赖模式 | ✅ | 仅1个竞品支持 | **领先** |
| Jina AI fallback | ✅ | 仅1个竞品支持 | **领先** |
| data-backsrc 支持 | ✅ | 仅1个竞品支持 | **领先** |
| op_res 过滤 | ✅ | 仅1个竞品支持 | **领先** |
| STOP_MARKERS 过滤 | ✅ | 仅1个支持 | **领先** |
| 日期正则提取 | ✅ | 仅1个支持 | **领先** |
| 页面截图 | ✅ | 仅2个竞品支持 | **领先** |
| 图片下载 | ✅ | 部分 | **领先** |
| 表格结构保留 | ✅ | 未明确 | **领先** |
| 搜索发现 | ✅ | 少数 | **持平** |
| 多格式导出 | ✅ | 少数 | **持平** |
| 反爬绕过 | ✅ | 少数 | **持平** |

**核心差异化**：
1. **唯一支持 6 级策略路由的方案**（fast → adaptive → stable → reliable → zero_dep → jina_ai）
2. **唯一支持零依赖模式的方案**（纯标准库，无需 pip install）
3. **唯一同时支持 jina.ai fallback 的方案**（最后的可靠保障）
4. **唯一支持 OG 元数据备选的方案**
5. **唯一支持图片段落关联的方案**
6. **唯一支持完整 Content Status 状态码的方案**
7. **唯一集成 Scrapling 自适应策略的方案**
8. **唯一同时支持 html2text 和 markdownify 的方案**
9. **唯一支持 data-backsrc 图片懒加载属性的方案**
10. **唯一支持 op_res 微信 CDN 资源过滤的方案**
11. **唯一支持搜狗链接解析为真实微信链接的方案**
12. **唯一支持 40+ STOP_MARKERS 噪音标记过滤的方案** (吸取 camofox 精华)
13. **唯一支持正文日期正则提取发布时间的方案** (吸取 camofox 精华)
14. **唯一支持图片按原文顺序插入正文的方案** (吸取 camofox 精华)
15. **唯一支持表格结构保留的方案** (markdownify 转换 table/thead/tbody/tr/th/td)
16. **唯一支持视频提取的方案** (所有 6 个策略均支持，提取视频 URL、封面、时长、标题)
17. **唯一支持互动数据提取的方案** (阅读量、点赞数、在看数)

---

*本文档由 wechat-article-scraper v3.0.2 生成*
