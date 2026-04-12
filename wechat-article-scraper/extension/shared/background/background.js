/**
 * 微信文章抓取助手 - Background Script
 * 后台脚本，处理下载、右键菜单等
 */

// 安装时初始化
chrome.runtime.onInstalled.addListener(() => {
  console.log('[微信抓取助手] 扩展已安装');

  // 创建右键菜单
  chrome.contextMenus.create({
    id: 'scrapeArticle',
    title: '📰 抓取此微信文章',
    contexts: ['page'],
    documentUrlPatterns: ['https://mp.weixin.qq.com/s*']
  });

  chrome.contextMenus.create({
    id: 'scrapeWithImages',
    title: '🖼️ 抓取并下载图片',
    contexts: ['page'],
    documentUrlPatterns: ['https://mp.weixin.qq.com/s*']
  });

  chrome.contextMenus.create({
    id: 'separator1',
    type: 'separator',
    contexts: ['page'],
    documentUrlPatterns: ['https://mp.weixin.qq.com/s*']
  });

  chrome.contextMenus.create({
    id: 'openDashboard',
    title: '📊 打开 Web 仪表盘',
    contexts: ['page', 'browser_action', 'action']
  });
});

// 处理右键菜单点击
chrome.contextMenus.onClicked.addListener((info, tab) => {
  switch (info.menuItemId) {
    case 'scrapeArticle':
      scrapeCurrentArticle(tab, false);
      break;
    case 'scrapeWithImages':
      scrapeCurrentArticle(tab, true);
      break;
    case 'openDashboard':
      chrome.tabs.create({ url: 'http://localhost:3000' });
      break;
  }
});

// 处理来自 content script 的消息
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'download') {
    handleDownload(request.url, request.filename)
      .then(result => sendResponse(result))
      .catch(error => sendResponse({ success: false, error: error.message }));
    return true;
  }

  if (request.action === 'notify') {
    showNotification(request.title, request.message);
    sendResponse({ success: true });
  }
});

// 处理快捷键
chrome.commands.onCommand.addListener((command, tab) => {
  if (command === 'quick-scrape') {
    scrapeCurrentArticle(tab, false);
  }
});

// 抓取当前文章
async function scrapeCurrentArticle(tab, downloadImages) {
  try {
    // 检查是否是微信文章页面
    if (!tab.url || !tab.url.includes('mp.weixin.qq.com/s')) {
      showNotification('提示', '请在微信文章页面使用');
      return;
    }

    // 发送消息给 content script
    const response = await chrome.tabs.sendMessage(tab.id, {
      action: 'scrape',
      format: 'markdown',
      downloadImages: downloadImages,
      saveLocal: true,
      uploadServer: false
    });

    if (response.success) {
      // 自动下载
      const blob = new Blob([response.data.content], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const filename = `wechat_${Date.now()}.md`;

      await chrome.downloads.download({
        url: url,
        filename: filename,
        saveAs: false
      });

      showNotification('抓取成功', `已保存: ${response.data.title.substring(0, 30)}...`);
    } else {
      showNotification('抓取失败', response.error || '未知错误');
    }

  } catch (error) {
    console.error('抓取失败:', error);
    showNotification('抓取失败', error.message);
  }
}

// 处理下载
async function handleDownload(url, filename) {
  try {
    const downloadId = await chrome.downloads.download({
      url: url,
      filename: filename,
      saveAs: true
    });
    return { success: true, downloadId };
  } catch (error) {
    return { success: false, error: error.message };
  }
}

// 显示通知
function showNotification(title, message) {
  if (chrome.notifications) {
    chrome.notifications.create({
      type: 'basic',
      iconUrl: '../icons/icon128.png',
      title: title,
      message: message
    });
  } else {
    console.log(`[通知] ${title}: ${message}`);
  }
}

// 监听标签页更新
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url) {
    if (tab.url.includes('mp.weixin.qq.com/s')) {
      // 在微信文章页面显示页面操作
      chrome.action.setBadgeText({
        text: '📰',
        tabId: tabId
      });
      chrome.action.setBadgeBackgroundColor({
        color: '#667eea',
        tabId: tabId
      });
    }
  }
});

console.log('[微信抓取助手] Background script 已加载');
