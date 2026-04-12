/**
 * 微信文章抓取助手 - Content Script
 * 注入到微信文章页面，负责提取内容
 */

// 监听来自 popup 的消息
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'scrape') {
    scrapeArticle(request)
      .then(result => sendResponse(result))
      .catch(error => sendResponse({ success: false, error: error.message }));
    return true; // 异步响应
  }
});

// 抓取文章
async function scrapeArticle(options) {
  try {
    console.log('[微信抓取助手] 开始抓取...', options);

    // 提取文章数据
    const articleData = extractArticleData();

    // 如果需要下载图片
    if (options.downloadImages) {
      articleData.images = await extractImages();
    }

    // 格式化输出
    const formattedContent = formatContent(articleData, options.format);

    // 保存到本地
    if (options.saveLocal) {
      await saveToLocal(articleData, formattedContent);
    }

    // 上传到服务器
    if (options.uploadServer) {
      await uploadToServer(articleData, formattedContent);
    }

    return {
      success: true,
      data: {
        title: articleData.title,
        content: formattedContent,
        metadata: articleData
      }
    };

  } catch (error) {
    console.error('[微信抓取助手] 抓取失败:', error);
    return { success: false, error: error.message };
  }
}

// 提取文章数据
function extractArticleData() {
  // 标题
  const title = document.querySelector('#activity_name, .rich_media_title')?.textContent?.trim() || '';

  // 作者
  const author = document.querySelector('#js_name, .profile_nickname')?.textContent?.trim() || '';

  // 发布时间
  const publishTime = document.querySelector('#publish_time, #js_publish_time')?.textContent?.trim() || '';

  // 公众号ID
  const biz = document.querySelector('[data-biz]')?.dataset?.biz || '';

  // 内容区域
  const contentEl = document.querySelector('#js_content, .rich_media_content');

  if (!contentEl) {
    throw new Error('未找到文章内容区域');
  }

  // 提取正文文本
  const content = extractContentText(contentEl);

  // 提取图片
  const images = extractImageData(contentEl);

  // 提取互动数据
  const engagement = extractEngagement();

  // 提取视频
  const videos = extractVideos(contentEl);

  return {
    title,
    author,
    publishTime,
    biz,
    content: content.text,
    html: content.html,
    paragraphs: content.paragraphs,
    images,
    videos,
    engagement,
    url: window.location.href,
    scrapedAt: new Date().toISOString()
  };
}

// 提取内容文本
function extractContentText(contentEl) {
  // 克隆节点以避免修改原页面
  const clone = contentEl.cloneNode(true);

  // 移除不需要的元素
  const removeSelectors = [
    'script', 'style', 'iframe', 'svg', 'form',
    '.rich_media_tool', '.rich_media_extra',
    '.rich_media_content > div:last-child', // 通常是二维码
    '[style*="display: none"]'
  ];

  removeSelectors.forEach(selector => {
    clone.querySelectorAll(selector).forEach(el => el.remove());
  });

  // 提取 HTML
  const html = clone.innerHTML;

  // 提取纯文本
  const text = clone.textContent?.trim() || '';

  // 提取段落
  const paragraphs = [];
  clone.querySelectorAll('p, section').forEach((p, index) => {
    const text = p.textContent?.trim();
    if (text && text.length > 10) {
      paragraphs.push({
        index,
        text: text.substring(0, 500),
        html: p.innerHTML
      });
    }
  });

  return { text, html, paragraphs };
}

// 提取图片数据
function extractImageData(contentEl) {
  const images = [];
  const imgElements = contentEl.querySelectorAll('img');

  imgElements.forEach((img, index) => {
    // 获取真实图片 URL
    let src = img.getAttribute('data-src') ||
              img.getAttribute('data-backsrc') ||
              img.src;

    // 过滤占位图
    if (!src || src.includes('svg+xml') || src.includes('placeholder')) {
      return;
    }

    // 过滤装饰图
    if (src.includes('yZPTcMGWibvsic9Obib') ||
        src.includes('res.wx.qq.com/op_res')) {
      return;
    }

    images.push({
      index,
      src,
      alt: img.alt || '',
      width: img.naturalWidth || img.width,
      height: img.naturalHeight || img.height
    });
  });

  return images;
}

// 提取互动数据
function extractEngagement() {
  const data = {};

  // 阅读量
  const readCountEl = document.querySelector('#readNum, .read-num');
  if (readCountEl) {
    data.readCount = parseCount(readCountEl.textContent);
  }

  // 点赞数
  const likeCountEl = document.querySelector('#likeNum, #old_like_num, .like-num');
  if (likeCountEl) {
    data.likeCount = parseCount(likeCountEl.textContent);
  }

  // 在看数
  const watchCountEl = document.querySelector('#watchNum, .watch-num');
  if (watchCountEl) {
    data.watchCount = parseCount(watchCountEl.textContent);
  }

  return data;
}

// 解析数字（处理 "1.2万" 格式）
function parseCount(text) {
  if (!text) return 0;

  text = text.toString().trim();

  if (text.includes('万')) {
    return parseFloat(text.replace('万', '')) * 10000;
  }

  if (text.includes('k') || text.includes('K')) {
    return parseFloat(text.replace(/[kK]/, '')) * 1000;
  }

  const num = parseInt(text.replace(/[^\d]/g, ''), 10);
  return isNaN(num) ? 0 : num;
}

// 提取视频
function extractVideos(contentEl) {
  const videos = [];

  // video 标签
  contentEl.querySelectorAll('video').forEach((video, index) => {
    videos.push({
      index,
      src: video.src || video.querySelector('source')?.src,
      poster: video.poster,
      duration: video.duration
    });
  });

  // mpvideosrc 标签
  contentEl.querySelectorAll('mpvideosrc').forEach((mpvideo, index) => {
    const data = mpvideo.dataset;
    if (data.src) {
      videos.push({
        index,
        src: data.src,
        poster: data.poster,
        title: data.title
      });
    }
  });

  return videos;
}

// 格式化输出
function formatContent(data, format) {
  switch (format) {
    case 'markdown':
      return formatMarkdown(data);
    case 'html':
      return formatHTML(data);
    case 'json':
      return formatJSON(data);
    default:
      return formatMarkdown(data);
  }
}

// Markdown 格式
function formatMarkdown(data) {
  let md = `---\n`;
  md += `title: "${data.title}"\n`;
  md += `author: "${data.author}"\n`;
  md += `publish_time: "${data.publishTime}"\n`;
  md += `source_url: "${data.url}"\n`;
  md += `scraped_at: "${data.scrapedAt}"\n`;

  if (data.engagement.readCount) {
    md += `read_count: ${data.engagement.readCount}\n`;
  }
  if (data.engagement.likeCount) {
    md += `like_count: ${data.engagement.likeCount}\n`;
  }

  md += `---\n\n`;
  md += `# ${data.title}\n\n`;
  md += `**作者**: ${data.author}  \n`;
  md += `**发布时间**: ${data.publishTime}  \n`;
  md += `**来源**: ${data.url}\n\n`;
  md += `---\n\n`;

  // 内容
  md += data.content;

  // 图片
  if (data.images && data.images.length > 0) {
    md += `\n\n## 图片\n\n`;
    data.images.forEach(img => {
      md += `![${img.alt || '配图'}](${img.src})\n\n`;
    });
  }

  // 视频
  if (data.videos && data.videos.length > 0) {
    md += `\n\n## 视频\n\n`;
    data.videos.forEach(video => {
      md += `[视频](${video.src})\n\n`;
    });
  }

  md += `\n\n---\n\n`;
  md += `*本文由 微信文章抓取助手 于 ${new Date().toLocaleString()} 生成*\n`;

  return md;
}

// HTML 格式
function formatHTML(data) {
  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>${data.title}</title>
  <style>
    body { max-width: 800px; margin: 0 auto; padding: 20px; font-family: -apple-system, sans-serif; line-height: 1.8; }
    h1 { font-size: 24px; margin-bottom: 10px; }
    .meta { color: #666; font-size: 14px; margin-bottom: 20px; }
    img { max-width: 100%; height: auto; }
  </style>
</head>
<body>
  <h1>${data.title}</h1>
  <div class="meta">
    <p>作者: ${data.author}</p>
    <p>发布时间: ${data.publishTime}</p>
    <p>来源: <a href="${data.url}">${data.url}</a></p>
  </div>
  <hr>
  <div class="content">${data.html}</div>
  <hr>
  <p style="color: #999; font-size: 12px;">由 微信文章抓取助手 生成</p>
</body>
</html>`;
}

// JSON 格式
function formatJSON(data) {
  return JSON.stringify(data, null, 2);
}

// 保存到本地
async function saveToLocal(data, content) {
  try {
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);

    await chrome.runtime.sendMessage({
      action: 'download',
      url: url,
      filename: `wechat_${Date.now()}.${data.format || 'md'}`
    });
  } catch (error) {
    console.error('保存到本地失败:', error);
  }
}

// 上传到服务器
async function uploadToServer(data, content) {
  try {
    const response = await fetch('http://localhost:8000/api/scrape', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url: data.url,
        title: data.title,
        author: data.author,
        content: content,
        metadata: data
      })
    });

    if (!response.ok) {
      throw new Error('上传失败: ' + response.status);
    }

    return await response.json();
  } catch (error) {
    console.error('上传到服务器失败:', error);
    throw error;
  }
}

// 提取图片
async function extractImages() {
  const images = document.querySelectorAll('img[data-src], img[data-backsrc]');
  const imageData = [];

  for (const img of images) {
    const src = img.getAttribute('data-src') || img.getAttribute('data-backsrc');
    if (src && !src.includes('svg+xml')) {
      imageData.push({
        src,
        alt: img.alt || ''
      });
    }
  }

  return imageData;
}

console.log('[微信抓取助手] Content script 已加载');
