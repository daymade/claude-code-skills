/**
 * 微信文章抓取助手 - Popup 脚本
 */

// 全局状态
let currentTab = null;
let articleData = null;
let selectedFormat = 'markdown';

// DOM 元素
const statusEl = document.getElementById('status');
const statusTextEl = document.getElementById('statusText');
const articleInfoEl = document.getElementById('articleInfo');
const articleTitleEl = document.getElementById('articleTitle');
const articleAuthorEl = document.getElementById('articleAuthor');
const articleDateEl = document.getElementById('articleDate');
const scrapeBtn = document.getElementById('scrapeBtn');
const scrapeWithImagesBtn = document.getElementById('scrapeWithImagesBtn');
const progressEl = document.getElementById('progress');
const progressTextEl = document.getElementById('progressText');
const progressFillEl = document.getElementById('progressFill');
const resultEl = document.getElementById('result');
const resultTextEl = document.getElementById('resultText');

// 初始化
document.addEventListener('DOMContentLoaded', async () => {
  await checkCurrentTab();
  setupEventListeners();
});

// 检查当前标签页
async function checkCurrentTab() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    currentTab = tab;

    const isWeChat = tab.url && tab.url.includes('mp.weixin.qq.com/s');

    if (isWeChat) {
      statusEl.className = 'status is-wechat';
      statusTextEl.textContent = '✓ 已检测到微信文章';
      scrapeBtn.disabled = false;
      scrapeWithImagesBtn.disabled = false;
      articleInfoEl.style.display = 'block';

      // 获取文章信息
      await getArticleInfo();
    } else {
      statusEl.className = 'status not-wechat';
      statusTextEl.textContent = '请在微信文章页面使用';
      scrapeBtn.disabled = true;
      scrapeWithImagesBtn.disabled = true;
      articleInfoEl.style.display = 'none';
    }
  } catch (error) {
    console.error('检查标签页失败:', error);
    statusTextEl.textContent = '检查页面失败: ' + error.message;
  }
}

// 获取文章信息
async function getArticleInfo() {
  try {
    const [result] = await chrome.scripting.executeScript({
      target: { tabId: currentTab.id },
      func: () => {
        const title = document.querySelector('#activity_name, .rich_media_title')?.textContent?.trim() || '';
        const author = document.querySelector('#js_name, .profile_nickname')?.textContent?.trim() || '';
        const publishTime = document.querySelector('#publish_time, #js_publish_time')?.textContent?.trim() || '';
        return { title, author, publishTime };
      }
    });

    if (result && result.result) {
      const { title, author, publishTime } = result.result;
      articleTitleEl.textContent = title || '未获取到标题';
      articleAuthorEl.textContent = author || '未知作者';
      articleDateEl.textContent = publishTime || '';
    }
  } catch (error) {
    console.error('获取文章信息失败:', error);
  }
}

// 设置事件监听器
function setupEventListeners() {
  // 格式选择
  document.querySelectorAll('.format-option').forEach(option => {
    option.addEventListener('click', () => {
      document.querySelectorAll('.format-option').forEach(o => o.classList.remove('active'));
      option.classList.add('active');
      selectedFormat = option.dataset.format;
    });
  });

  // 抓取按钮
  scrapeBtn.addEventListener('click', () => scrapeArticle(false));
  scrapeWithImagesBtn.addEventListener('click', () => scrapeArticle(true));

  // 设置开关
  setupToggle('saveLocalToggle', true);
  setupToggle('uploadServerToggle', false);
  setupToggle('autoClassifyToggle', true);

  // 结果按钮
  document.getElementById('viewBtn').addEventListener('click', viewResult);
  document.getElementById('downloadBtn').addEventListener('click', downloadResult);
  document.getElementById('copyBtn').addEventListener('click', copyResult);

  // 底部链接
  document.getElementById('openDashboard').addEventListener('click', (e) => {
    e.preventDefault();
    chrome.tabs.create({ url: 'http://localhost:3000' });
  });

  document.getElementById('settingsLink').addEventListener('click', (e) => {
    e.preventDefault();
    chrome.runtime.openOptionsPage?.() || alert('设置页面开发中...');
  });
}

// 设置开关
function setupToggle(id, defaultValue) {
  const toggle = document.getElementById(id);
  if (defaultValue) toggle.classList.add('active');

  toggle.addEventListener('click', () => {
    toggle.classList.toggle('active');
  });
}

// 抓取文章
async function scrapeArticle(downloadImages) {
  try {
    showProgress('正在抓取文章...', 10);

    const saveLocal = document.getElementById('saveLocalToggle').classList.contains('active');
    const uploadServer = document.getElementById('uploadServerToggle').classList.contains('active');
    const autoClassify = document.getElementById('autoClassifyToggle').classList.contains('active');

    // 发送消息给 content script
    const response = await chrome.tabs.sendMessage(currentTab.id, {
      action: 'scrape',
      format: selectedFormat,
      downloadImages: downloadImages,
      saveLocal: saveLocal,
      uploadServer: uploadServer,
      autoClassify: autoClassify
    });

    if (response.success) {
      articleData = response.data;
      showProgress('抓取成功！', 100);
      setTimeout(() => {
        hideProgress();
        showResult(true, '文章抓取成功！');
      }, 500);
    } else {
      hideProgress();
      showResult(false, response.error || '抓取失败');
    }

  } catch (error) {
    console.error('抓取失败:', error);
    hideProgress();
    showResult(false, '抓取失败: ' + error.message);
  }
}

// 显示进度
function showProgress(text, percent) {
  progressEl.classList.add('show');
  progressTextEl.textContent = text;
  progressFillEl.style.width = percent + '%';
}

// 隐藏进度
function hideProgress() {
  progressEl.classList.remove('show');
  progressFillEl.style.width = '0%';
}

// 显示结果
function showResult(success, message) {
  resultEl.classList.add('show');
  resultEl.className = 'result show ' + (success ? 'success' : 'error');
  resultTextEl.textContent = message;
}

// 查看结果
function viewResult() {
  if (articleData) {
    const blob = new Blob([articleData.content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    chrome.tabs.create({ url: url });
  }
}

// 下载结果
function downloadResult() {
  if (articleData) {
    const extension = selectedFormat === 'markdown' ? 'md' : selectedFormat;
    const filename = `wechat_article_${Date.now()}.${extension}`;

    const blob = new Blob([articleData.content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);

    chrome.downloads.download({
      url: url,
      filename: filename,
      saveAs: true
    });
  }
}

// 复制结果
async function copyResult() {
  if (articleData) {
    try {
      await navigator.clipboard.writeText(articleData.content);
      const originalText = document.getElementById('copyBtn').textContent;
      document.getElementById('copyBtn').textContent = '已复制!';
      setTimeout(() => {
        document.getElementById('copyBtn').textContent = originalText;
      }, 2000);
    } catch (error) {
      alert('复制失败: ' + error.message);
    }
  }
}
