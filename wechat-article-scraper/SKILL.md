---
name: wechat-article-scraper
description: 抓取微信公众号文章内容并保存为 Markdown。当用户需要下载微信公众号文章、提取公众号正文内容、批量保存微信文章、获取微信公众号图文时使用此 skill。适用于投研资料归档、知识库建设、内容备份等场景。
argument-hint: [article-url]
---

# 微信公众号文章抓取

抓取微信公众号文章内容，包括正文、图片、标题、作者、发布时间等元数据，输出为结构化的 Markdown 文件。

## 前置要求

**⚠️ 必须先完成微信登录**：
1. 在 Chrome 浏览器中访问 https://mp.weixin.qq.com
2. 扫码完成微信登录
3. 保持浏览器窗口打开（登录态会保持一段时间）

**未登录时会出现**："当前环境异常，完成验证后即可继续访问" 的错误页面。

## 使用方式

```
/wechat-article-scraper [微信公众号文章链接]
```

**支持的链接格式**：
- `https://mp.weixin.qq.com/s/xxxxx`（标准文章链接）
- `https://mp.weixin.qq.com/s?__biz=xxx&mid=xxx`（带参数链接）

## 工作流程

### 步骤 1：导航到文章页面

使用 Chrome DevTools MCP 导航到目标文章 URL。

### 步骤 2：滚动触发懒加载

**关键**：微信文章图片使用懒加载，必须滚动到视口才会加载真实图片。

执行 JavaScript 滚动脚本：
- 滚动到底部触发所有图片加载
- 等待 2 秒让图片完全加载
- 提取真实图片 URL（从 `data-src` 属性）

### 步骤 3：提取结构化数据

提取以下字段：
- `title`: 文章标题
- `author`: 公众号名称
- `publishTime`: 发布时间
- `text`: 正文纯文本
- `images`: 图片列表（真实 URL）
- `html`: 清理后的 HTML 内容

### 步骤 4：保存为 Markdown

将提取的内容格式化为 Markdown 文件：
- 保留文章结构和段落
- 图片使用真实 URL 嵌入
- 包含元数据（作者、时间、原文链接）
- 保存到 `Clippings/` 或用户指定目录

## 技术实现

使用以下 JavaScript 提取脚本（通过 Chrome DevTools MCP 执行）：

```javascript
async () => {
  // 1. 滚动到底部触发懒加载
  await new Promise(resolve => {
    let totalHeight = 0;
    let distance = 300;
    let timer = setInterval(() => {
      let scrollHeight = document.body.scrollHeight;
      window.scrollBy(0, distance);
      totalHeight += distance;
      if (totalHeight >= scrollHeight) {
        clearInterval(timer);
        setTimeout(resolve, 2000); // 等待图片加载
      }
    }, 100);
  });
  
  // 2. 提取内容
  const contentEl = document.querySelector('#js_content');
  
  // 3. 处理图片
  const images = [];
  contentEl.querySelectorAll('img').forEach((img, i) => {
    const realSrc = img.getAttribute('data-src') || img.src;
    if (realSrc && !realSrc.includes('data:image/svg+xml')) {
      images.push({ index: i, src: realSrc, alt: img.alt || '' });
    }
  });
  
  return {
    title: document.querySelector('#activity_name')?.innerText || document.title,
    author: document.querySelector('#js_name')?.innerText || '',
    publishTime: document.querySelector('#publish_time')?.innerText || '',
    text: contentEl.innerText,
    images: images,
    html: contentEl.innerHTML
  };
}
```

## 失败记录（DO NOT ATTEMPT）

| 方案 | 失败模式 | 根因 |
|------|----------|------|
| WebFetch 直接抓取 | 返回"环境异常"验证页 | 微信反爬检测非浏览器 UA |
| Snapshot 方式 | 图片为占位符 SVG | 未触发懒加载，data-src 未转换 |
| opencli 探索 | 无微信 CLI 可用 | 微信未开放公开 API |
| curl/wget | 被拦截返回验证页 | 缺少浏览器 Cookie 和 UA |

## 限制与边界

**无法抓取的情况**：
- 文章被删除或违规下架
- 需要付费阅读的内容（只能抓取预览部分）
- 登录态过期（需要重新扫码）
- 文章包含视频（只能提取封面，视频需单独处理）

**图片处理限制**：
- 图片 URL 有时效性，长期保存需要额外下载
- 微信 CDN 图片可能带水印

## 批量抓取

对于批量抓取，建议间隔 3-5 秒 between 请求，避免触发风控。

## 输出示例

保存的 Markdown 文件结构：

```markdown
# [文章标题]

**作者**: [公众号名称]  
**发布时间**: [时间]  
**来源**: [原文链接]

---

[正文内容...]

![图片描述](真实图片URL)

---

**原文链接**: [URL]  
**抓取时间**: [timestamp]
```
