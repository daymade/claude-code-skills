/**
 * Popup Script - Chrome Extension
 *
 * Handles the extension popup UI interactions
 */

// DOM Elements
const statusEl = document.getElementById('status');
const pageTitleEl = document.getElementById('page-title');
const pageUrlEl = document.getElementById('page-url');
const pageIconEl = document.getElementById('page-icon');
const saveBtn = document.getElementById('save-btn');
const annotateBtn = document.getElementById('annotate-btn');
const articleListEl = document.getElementById('article-list');
const viewAllLink = document.getElementById('view-all');
const settingsLink = document.getElementById('settings');

// State
let currentTab = null;
let isWeChatArticle = false;

// Initialize
async function init() {
  // Get current tab
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  currentTab = tabs[0];

  // Update UI with current page info
  updatePageInfo();

  // Load recent articles
  loadRecentArticles();

  // Setup event listeners
  setupEventListeners();
}

// Update page info display
function updatePageInfo() {
  if (!currentTab) return;

  pageTitleEl.textContent = currentTab.title || '未知页面';
  pageUrlEl.textContent = currentTab.url || '';

  // Check if WeChat article
  isWeChatArticle = currentTab.url?.includes('mp.weixin.qq.com') || false;

  if (isWeChatArticle) {
    pageIconEl.textContent = '📰';
  } else {
    pageIconEl.textContent = '🌐';
  }
}

// Setup event listeners
function setupEventListeners() {
  saveBtn.addEventListener('click', handleSave);
  annotateBtn.addEventListener('click', handleAnnotate);
  viewAllLink.addEventListener('click', handleViewAll);
  settingsLink.addEventListener('click', handleSettings);
}

// Handle save button click
async function handleSave() {
  if (!currentTab) return;

  setLoading(true);
  showStatus('');

  try {
    const response = await chrome.runtime.sendMessage({
      action: 'save-page'
    });

    if (response?.error) {
      showStatus('保存失败: ' + response.error, 'error');
    } else {
      showStatus('文章已保存成功!', 'success');
      // Refresh recent articles
      setTimeout(loadRecentArticles, 500);
    }
  } catch (error) {
    showStatus('保存失败: ' + error.message, 'error');
  } finally {
    setLoading(false);
  }
}

// Handle annotate button click
async function handleAnnotate() {
  if (!currentTab) return;

  try {
    await chrome.tabs.sendMessage(currentTab.id, {
      action: 'show-annotate-ui'
    });

    // Close popup
    window.close();
  } catch (error) {
    showStatus('请先在文章中选中文字', 'error');
  }
}

// Handle view all click
function handleViewAll(e) {
  e.preventDefault();

  chrome.storage.sync.get(['apiUrl'], (result) => {
    const baseUrl = result.apiUrl?.replace('/api', '') || 'http://localhost:3000';
    chrome.tabs.create({ url: baseUrl });
  });
}

// Handle settings click
function handleSettings(e) {
  e.preventDefault();
  chrome.runtime.openOptionsPage?.();
}

// Load recent articles
async function loadRecentArticles() {
  try {
    const result = await chrome.storage.local.get(['savedArticles']);
    const articles = result.savedArticles || [];

    // Clear list
    articleListEl.innerHTML = '';

    if (articles.length === 0) {
      const emptyItem = document.createElement('li');
      emptyItem.className = 'empty-state';
      emptyItem.textContent = '暂无保存的文章';
      articleListEl.appendChild(emptyItem);
      return;
    }

    // Show last 5 articles
    const recent = articles.slice(-5).reverse();

    recent.forEach(article => {
      const item = createArticleElement(article);
      articleListEl.appendChild(item);
    });
  } catch (error) {
    console.error('Failed to load recent articles:', error);
  }
}

// Create article element
function createArticleElement(article) {
  const li = document.createElement('li');
  li.className = 'article-item';
  li.dataset.id = article.id;

  const titleDiv = document.createElement('div');
  titleDiv.className = 'article-title';
  titleDiv.textContent = article.title;

  const metaDiv = document.createElement('div');
  metaDiv.className = 'article-meta';
  metaDiv.textContent = `${article.author || '未知作者'} · ${formatDate(article.savedAt)}`;

  li.appendChild(titleDiv);
  li.appendChild(metaDiv);

  li.addEventListener('click', () => openArticle(article.id));

  return li;
}

// Open article in web app
function openArticle(id) {
  chrome.storage.sync.get(['apiUrl'], (result) => {
    const baseUrl = result.apiUrl?.replace('/api', '') || 'http://localhost:3000';
    chrome.tabs.create({ url: `${baseUrl}/articles/${id}` });
  });
}

// Show status message
function showStatus(message, type = '') {
  statusEl.textContent = message;
  statusEl.className = 'status' + (type ? ' ' + type : '');
}

// Set loading state
function setLoading(loading) {
  if (loading) {
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<span class="loading"></span> 保存中...';
  } else {
    saveBtn.disabled = false;
    saveBtn.innerHTML = '💾 保存文章';
  }
}

// Format date
function formatDate(timestamp) {
  const date = new Date(timestamp);
  const now = new Date();
  const diff = now - date;

  // Less than 1 hour
  if (diff < 3600000) {
    const mins = Math.floor(diff / 60000);
    return mins < 1 ? '刚刚' : `${mins}分钟前`;
  }

  // Less than 24 hours
  if (diff < 86400000) {
    const hours = Math.floor(diff / 3600000);
    return `${hours}小时前`;
  }

  // Less than 7 days
  if (diff < 604800000) {
    const days = Math.floor(diff / 86400000);
    return `${days}天前`;
  }

  return date.toLocaleDateString('zh-CN');
}

// Initialize on load
document.addEventListener('DOMContentLoaded', init);
