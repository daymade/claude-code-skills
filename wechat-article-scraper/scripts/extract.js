/**
 * 微信公众号文章提取脚本 - 世界级版本 v3.1
 * 通过 Chrome DevTools Protocol 在页面上下文中执行
 *
 * 吸取 camofox 精华：
 * - 详细的 STOP_MARKERS 噪音标记
 * - 日期正则提取发布时间
 * - 图片按原文顺序插入正文
 * - 更强的噪音元素过滤
 *
 * 原有特性：
 * - OG 元数据备选提取
 * - 图片与段落关联
 * - 装饰性图片智能过滤
 * - 结构化内容输出
 *
 * v3.0 新增：
 * - 视频提取支持
 * - 互动数据提取（阅读量、点赞数、在看数）
 *
 * v3.1 新增：
 * - 评论参数提取（comment_id, __biz, appmsg_token 等）
 * - 为评论采集提供必要的加密参数
 */

async function extractWechatArticle(options = {}) {
  const { enableOgfallback = true, scrollTimeout = 2000 } = options;

  // 吸取 camofox 精华：详细的噪音标记
  const STOP_MARKERS = [
    '预览时标签不可点',
    '微信扫一扫 关注该公众号',
    '继续滑动看下一个',
    '轻触阅读原文',
    '当前内容可能存在未经审核',
    '写留言',
    '暂无留言',
    '已无更多数据',
    '选择留言身份',
    '选择互动身份',
    '确认提交投诉',
    '发消息',
    '微信扫一扫可打开此内容',
    '篇原创内容 公众号',
    '点击关注',
    '长按二维码关注',
    '赞赏',
    '喜欢作者',
    '推荐阅读',
    '相关阅读',
    '精选留言',
    '查看往期',
    '分享到朋友圈',
    '收藏',
    '在看',
    '点赞',
  ];

  // 吸取 camofox 精华：需要跳过的子串
  const SKIP_SUBSTRINGS = [
    'Your browser does not support video tags',
    '观看更多',
    '继续观看',
    '分享视频',
    '倍速播放中',
    '切换到横屏模式',
    '退出全屏',
    '全屏',
    '关闭',
    '更多',
    '已关注',
    '关注',
    '赞',
    '推荐',
    '收藏',
    '视频详情',
    '写下你的评论',
    '轻点两下打开表情键盘',
    '轻点两下选择图片',
    '知道了',
    '取消',
    '允许',
  ];

  // 吸取 camofox 精华：日期正则
  const DATE_RE = /\d{4}年\d{1,2}月\d{1,2}(?:\s+\d{1,2}:\d{2})?/;

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
        setTimeout(resolve, scrollTimeout);
      }
    }, 100);
  });

  // 2. 获取内容容器
  const contentEl = document.querySelector('#js_content');
  if (!contentEl) {
    throw new Error('Content element #js_content not found');
  }

  // 3. 提取元数据
  let title = '';
  let author = '';
  let publishTime = '';

  const titleEl = document.querySelector('#activity_name') || document.querySelector('#activity-name');
  const authorEl = document.querySelector('#js_name') || document.querySelector('#js-name');
  const timeEl = document.querySelector('#publish_time') || document.querySelector('#publish-time');

  title = titleEl?.innerText?.trim() || '';
  author = authorEl?.innerText?.trim() || '';
  publishTime = timeEl?.innerText?.trim() || '';

  // 新增：提取互动数据（阅读量、点赞数、在看数）
  const engagement = {};
  try {
    // 阅读量 - 多种选择器尝试
    const readCountEl = document.querySelector('#js_read_num3') ||
                        document.querySelector('#readNum') ||
                        document.querySelector('.read-num');
    if (readCountEl) {
      engagement.readCount = readCountEl.textContent?.trim();
    }

    // 点赞数
    const likeCountEl = document.querySelector('#js_like_num') ||
                        document.querySelector('#likeNum') ||
                        document.querySelector('.like-num');
    if (likeCountEl) {
      engagement.likeCount = likeCountEl.textContent?.trim();
    }

    // 在看数
    const watchCountEl = document.querySelector('#js_watched_num') ||
                         document.querySelector('.watched-num');
    if (watchCountEl) {
      engagement.watchCount = watchCountEl.textContent?.trim();
    }
  } catch (e) {
    // 互动数据提取失败不影响主流程
  }

  // v3.1 新增：提取评论相关参数
  const commentParams = {};
  try {
    // 方法1: 从页面脚本中提取 comment_id
    const scripts = document.querySelectorAll('script');
    for (const script of scripts) {
      const text = script.textContent || '';

      // 提取 comment_id
      const commentIdMatch = text.match(/comment_id\s*=\s*["'](\d+)["']/);
      if (commentIdMatch && !commentParams.commentId) {
        commentParams.commentId = commentIdMatch[1];
      }

      // 提取 __biz
      const bizMatch = text.match(/__biz\s*=\s*["']([^"']+)["']/);
      if (bizMatch && !commentParams.biz) {
        commentParams.biz = bizMatch[1];
      }

      // 提取 appmsg_token
      const tokenMatch = text.match(/appmsg_token\s*=\s*["']([^"']+)["']/);
      if (tokenMatch && !commentParams.appmsgToken) {
        commentParams.appmsgToken = tokenMatch[1];
      }

      // 提取 pass_ticket
      const ticketMatch = text.match(/pass_ticket\s*=\s*["']([^"']+)["']/);
      if (ticketMatch && !commentParams.passTicket) {
        commentParams.passTicket = ticketMatch[1];
      }

      // 提取 wxtoken
      const wxTokenMatch = text.match(/wxtoken\s*=\s*["']([^"']+)["']/);
      if (wxTokenMatch && !commentParams.wxToken) {
        commentParams.wxToken = wxTokenMatch[1];
      }
    }

    // 方法2: 从页面变量中获取（微信页面常将数据挂载到 window）
    if (window.__biz && !commentParams.biz) {
      commentParams.biz = window.__biz;
    }
    if (window.comment_id && !commentParams.commentId) {
      commentParams.commentId = window.comment_id;
    }
    if (window.appmsg_token && !commentParams.appmsgToken) {
      commentParams.appmsgToken = window.appmsg_token;
    }

    // 方法3: 从 URL 参数中提取
    const urlParams = new URLSearchParams(window.location.search);
    if (!commentParams.biz) {
      commentParams.biz = urlParams.get('__biz');
    }
    if (!commentParams.passTicket) {
      commentParams.passTicket = urlParams.get('pass_ticket');
    }

    // 检查是否支持评论
    commentParams.hasComments = !!commentParams.commentId;

  } catch (e) {
    // 评论参数提取失败不影响主流程
    commentParams.error = e.message;
  }

  // OG 元数据备选
  if (enableOgfallback) {
    const ogTitle = document.querySelector('meta[property="og:title"]')?.getAttribute('content');
    const ogAuthor = document.querySelector('meta[property="og:article:author"]')?.getAttribute('content');
    const ogTime = document.querySelector('meta[property="og:article:published_time"]')?.getAttribute('content');

    title = title || ogTitle || document.title?.replace('微信公众平台', '')?.trim();
    author = author || ogAuthor || '';
    publishTime = publishTime || ogTime || '';
  }

  // 吸取 camofox 精华：如果没时间，尝试从正文提取
  if (!publishTime) {
    const bodyText = contentEl.innerText;
    const dateMatch = bodyText.match(DATE_RE);
    if (dateMatch) {
      publishTime = dateMatch[0];
    }
  }

  // 4. 移除噪音元素 - 吸取 camofox 精华：更强的过滤
  const noiseSelectors = [
    'script', 'style', 'svg', 'iframe', 'form', 'button',
    '.js_uneditable',
    '.wx_profile_card_inner',
    '.original_primary_card_tips',
    '.weui-desktop-mass-appmsg__comment',
    '.rich_media_tool',
    '.rich_media_extra'
  ];
  noiseSelectors.forEach(selector => {
    contentEl.querySelectorAll(selector).forEach(el => el.remove());
  });

  // 5. 提取内容 - 吸取 camofox 精华：图片按原文顺序插入
  const images = [];
  const videos = []; // 新增：视频提取
  const paragraphs = [];
  const contentBlocks = []; // 按原文顺序的内容块

  // 递归遍历 DOM，保持原文顺序
  function traverseNode(node, paragraphIndex) {
    if (node.nodeType === Node.TEXT_NODE) {
      const text = node.textContent?.trim();
      if (text && text.length > 5) {
        // 检查噪音标记
        const hasStopMarker = STOP_MARKERS.some(marker => text.includes(marker));
        const hasSkipSubstring = SKIP_SUBSTRINGS.some(sub => text.includes(sub));

        if (!hasStopMarker && !hasSkipSubstring) {
          contentBlocks.push({
            type: 'text',
            text: text,
            paragraphIndex: paragraphIndex
          });
        }
      }
      return paragraphIndex;
    }

    if (node.nodeType === Node.ELEMENT_NODE) {
      const tagName = node.tagName.toLowerCase();

      // 处理视频 - 新增功能
      if (tagName === 'video' || tagName === 'mpvideosrc') {
        const videoData = {
          index: videos.length,
          src: node.getAttribute('data-src') || node.src || '',
          poster: node.getAttribute('data-poster') || node.poster || '',
          duration: node.getAttribute('data-duration') || '',
        };

        // 尝试从父元素获取更多视频信息
        const parent = node.parentElement;
        if (parent) {
          const titleEl = parent.querySelector('.video_title, .video-title');
          if (titleEl) {
            videoData.title = titleEl.textContent?.trim();
          }
        }

        if (videoData.src || videoData.poster) {
          videos.push(videoData);
          contentBlocks.push({
            type: 'video',
            videoIndex: videoData.index,
            ...videoData
          });
        }
        return paragraphIndex;
      }

      // 处理图片
      if (tagName === 'img') {
        const realSrc = node.getAttribute('data-src') ||
                        node.getAttribute('data-backsrc') ||
                        node.src || '';
        const width = node.naturalWidth || node.width || 0;
        const height = node.naturalHeight || node.height || 0;
        const alt = node.alt || '';

        // 过滤装饰性图片
        const isDecorative = (
          !realSrc ||
          realSrc.startsWith('data:') ||
          realSrc.includes('data:image/svg+xml') ||
          realSrc.includes('yZPTcMGWibvsic9Obib') ||
          realSrc.includes('res.wx.qq.com/op_res/') ||
          (width > 0 && width < 50) ||
          (height > 0 && height < 50) ||
          alt === '跳转二维码' ||
          alt === '划线引导图'
        );

        if (!isDecorative && realSrc) {
          const imgData = {
            index: images.length,
            src: realSrc,
            alt: alt,
            width: width,
            height: height,
            isContentImage: width > 200 || height > 200
          };
          images.push(imgData);
          contentBlocks.push({
            type: 'image',
            imageIndex: imgData.index,
            src: realSrc,
            alt: alt
          });
        }
        return paragraphIndex;
      }

      // 跳过隐藏元素
      const style = window.getComputedStyle(node);
      if (style.display === 'none' || style.visibility === 'hidden') {
        return paragraphIndex;
      }

      // 处理段落元素
      if (['p', 'section', 'div', 'h1', 'h2', 'h3', 'h4', 'li', 'blockquote'].includes(tagName)) {
        const text = node.innerText?.trim();
        if (text && text.length > 5) {
          // 检查噪音标记
          const hasStopMarker = STOP_MARKERS.some(marker => text.includes(marker));
          const hasSkipSubstring = SKIP_SUBSTRINGS.some(sub => text.includes(sub));

          if (!hasStopMarker && !hasSkipSubstring) {
            paragraphs.push({
              index: paragraphs.length,
              text: text,
              tagName: tagName
            });
            contentBlocks.push({
              type: 'paragraph',
              text: text,
              paragraphIndex: paragraphs.length - 1,
              tagName: tagName
            });
            return paragraphs.length;
          }
        }
      }

      // 递归处理子节点
      let currentIdx = paragraphIndex;
      for (const child of node.childNodes) {
        currentIdx = traverseNode(child, currentIdx);
      }
      return currentIdx;
    }

    return paragraphIndex;
  }

  // 开始遍历
  traverseNode(contentEl, 0);

  // 6. 构建按原文顺序的 Markdown 内容
  let markdownContent = '';
  let prevType = null;

  for (const block of contentBlocks) {
    if (block.type === 'text' || block.type === 'paragraph') {
      let text = block.text;

      // 处理列表项
      if (block.tagName === 'li') {
        text = '- ' + text;
      }

      // 处理引用
      if (block.tagName === 'blockquote') {
        text = '> ' + text;
      }

      // 列表结束后加空行
      if (prevType === 'list' && block.tagName !== 'li') {
        markdownContent += '\n';
      }

      markdownContent += text + '\n\n';
      prevType = block.tagName === 'li' ? 'list' : 'paragraph';
    } else if (block.type === 'image') {
      markdownContent += `![${block.alt || 'image'}](${block.src})\n\n`;
      prevType = 'image';
    } else if (block.type === 'video') {
      // 新增：视频 Markdown 表示
      const videoTitle = block.title ? `[${block.title}]` : '[视频]';
      markdownContent += `${videoTitle}(${block.src || block.poster})\n\n`;
      prevType = 'video';
    }
  }

  // 7. 返回结构化数据
  return {
    metadata: {
      title,
      author,
      publishTime,
      engagement, // 新增：互动数据
      commentParams, // v3.1 新增：评论参数
      url: window.location.href,
      extractedAt: new Date().toISOString(),
      extractor: 'wechat-article-scraper-v3.1'
    },
    content: {
      textLength: contentEl.innerText.length,
      paragraphCount: paragraphs.length,
      imageCount: images.length,
      videoCount: videos.length, // 新增：视频数量
      text: contentEl.innerText,
      paragraphs,
      images,
      videos, // 新增：视频列表
      contentBlocks, // 按原文顺序的内容块
      markdownContent, // 预生成的 Markdown
      html: contentEl.innerHTML
    }
  };
}

// 执行提取
extractWechatArticle();
