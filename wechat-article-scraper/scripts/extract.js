/**
 * 微信公众号文章提取脚本
 * 通过 Chrome DevTools Protocol 在页面上下文中执行
 */

async function extractWechatArticle() {
  // 1. 滚动到底部触发所有图片懒加载
  await new Promise(resolve => {
    let totalHeight = 0;
    const distance = 300;
    const timer = setInterval(() => {
      const scrollHeight = document.body.scrollHeight;
      window.scrollBy(0, distance);
      totalHeight += distance;

      if (totalHeight >= scrollHeight) {
        clearInterval(timer);
        // 等待图片加载完成
        setTimeout(resolve, 2000);
      }
    }, 100);
  });

  // 2. 获取内容容器
  const contentEl = document.querySelector('#js_content');
  if (!contentEl) {
    throw new Error('Content element #js_content not found');
  }

  // 3. 提取图片（处理懒加载）
  const images = [];
  contentEl.querySelectorAll('img').forEach((img, index) => {
    // 优先使用 data-src（真实 URL），其次使用 src
    const realSrc = img.getAttribute('data-src') || img.src;

    // 过滤掉占位符图片
    if (realSrc && !realSrc.includes('data:image/svg+xml')) {
      images.push({
        index,
        src: realSrc,
        alt: img.alt || '',
        width: img.naturalWidth,
        height: img.naturalHeight
      });
    }
  });

  // 4. 提取元数据
  const title = document.querySelector('#activity_name')?.innerText?.trim()
    || document.title?.replace('微信公众平台', '')?.trim();

  const author = document.querySelector('#js_name')?.innerText?.trim()
    || document.querySelector('.profile_nickname')?.innerText?.trim();

  const publishTime = document.querySelector('#publish_time')?.innerText?.trim();

  // 5. 提取正文文本（保留段落结构）
  const text = contentEl.innerText;

  // 6. 获取清理后的 HTML
  const html = contentEl.innerHTML
    .replace(/data-src="[^"]*"/g, '')
    .replace(/style="[^"]*"/g, '')
    .replace(/data-\w+="[^"]*"/g, '');

  // 7. 返回结构化数据
  return {
    metadata: {
      title,
      author,
      publishTime,
      url: window.location.href,
      extractedAt: new Date().toISOString()
    },
    content: {
      textLength: text.length,
      imageCount: images.length,
      text,
      images,
      html
    }
  };
}

// 执行提取
extractWechatArticle();
