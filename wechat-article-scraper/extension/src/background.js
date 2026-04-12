/**
 * Background Service Worker - Chrome Extension Manifest V3
 *
 * Handles:
 * - Context menu creation and clicks
 * - Keyboard shortcuts
 * - Message passing between content scripts and popup
 * - API communication with the main app
 */

import { ContentExtractor } from './modules/content-extractor.js';
import { APIClient } from './modules/api-client.js';

// Configuration
const CONFIG = {
  API_BASE_URL: 'http://localhost:3000/api', // Will be configurable
  DEFAULT_STRATEGY: 'adaptive',
};

// Initialize extension
chrome.runtime.onInstalled.addListener((details) => {
  console.log('[WeChat Scraper] Extension installed:', details.reason);

  // Create context menu
  createContextMenus();

  // Set default settings
  chrome.storage.sync.get(['apiUrl', 'strategy'], (result) => {
    if (!result.apiUrl) {
      chrome.storage.sync.set({ apiUrl: CONFIG.API_BASE_URL });
    }
    if (!result.strategy) {
      chrome.storage.sync.set({ strategy: CONFIG.DEFAULT_STRATEGY });
    }
  });
});

// Create context menus
function createContextMenus() {
  // Remove existing menus
  chrome.contextMenus.removeAll();

  // Main parent menu
  chrome.contextMenus.create({
    id: 'wechat-scraper-root',
    title: chrome.i18n.getMessage('saveToWeChatScraper'),
    contexts: ['page', 'link', 'selection']
  });

  // Save current page
  chrome.contextMenus.create({
    id: 'save-page',
    parentId: 'wechat-scraper-root',
    title: chrome.i18n.getMessage('saveCurrentPage'),
    contexts: ['page']
  });

  // Save link
  chrome.contextMenus.create({
    id: 'save-link',
    parentId: 'wechat-scraper-root',
    title: chrome.i18n.getMessage('saveLink'),
    contexts: ['link']
  });

  // Save selection
  chrome.contextMenus.create({
    id: 'save-selection',
    parentId: 'wechat-scraper-root',
    title: chrome.i18n.getMessage('saveSelection'),
    contexts: ['selection']
  });

  // Separator
  chrome.contextMenus.create({
    id: 'separator-1',
    parentId: 'wechat-scraper-root',
    type: 'separator',
    contexts: ['page', 'link', 'selection']
  });

  // Quick annotate
  chrome.contextMenus.create({
    id: 'quick-annotate',
    parentId: 'wechat-scraper-root',
    title: chrome.i18n.getMessage('quickAnnotate'),
    contexts: ['selection']
  });
}

// Handle context menu clicks
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  console.log('[WeChat Scraper] Context menu clicked:', info.menuItemId);

  switch (info.menuItemId) {
    case 'save-page':
      await saveCurrentPage(tab);
      break;
    case 'save-link':
      await saveUrl(info.linkUrl);
      break;
    case 'save-selection':
      await saveSelection(tab, info.selectionText);
      break;
    case 'quick-annotate':
      await quickAnnotate(tab, info.selectionText);
      break;
  }
});

// Handle keyboard shortcuts
chrome.commands.onCommand.addListener(async (command, tab) => {
  console.log('[WeChat Scraper] Command received:', command);

  switch (command) {
    case 'save-page':
      await saveCurrentPage(tab);
      break;
    case 'quick-annotate':
      // Inject annotate UI
      chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: injectAnnotateUI
      });
      break;
  }
});

// Save current page
async function saveCurrentPage(tab) {
  if (!tab?.url) return;

  // Show notification
  showNotification('savingArticle');

  try {
    // Check if it's a WeChat article
    if (isWeChatArticle(tab.url)) {
      await saveWeChatArticle(tab.url);
    } else {
      // For non-WeChat pages, extract content using Readability
      await saveGenericPage(tab);
    }
  } catch (error) {
    console.error('[WeChat Scraper] Save failed:', error);
    showNotification('saveFailed', error.message);
  }
}

// Save URL directly
async function saveUrl(url) {
  if (!url) return;

  showNotification('savingArticle');

  try {
    if (isWeChatArticle(url)) {
      await saveWeChatArticle(url);
    } else {
      // For non-WeChat URLs, we need to fetch the page first
      const response = await fetch(url);
      const html = await response.text();
      await saveHtmlContent(url, html);
    }
  } catch (error) {
    console.error('[WeChat Scraper] Save failed:', error);
    showNotification('saveFailed', error.message);
  }
}

// Save selected text with context
async function saveSelection(tab, selectionText) {
  if (!selectionText || !tab?.url) return;

  // Get more context from the page
  const [result] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: getSelectionContext
  });

  const context = result?.result || {};

  // Save as a clip/note
  await saveClip({
    url: tab.url,
    title: tab.title,
    quote: selectionText,
    context: context.paragraph || '',
    timestamp: Date.now()
  });

  showNotification('clipSaved');
}

// Quick annotate selection
async function quickAnnotate(tab, selectionText) {
  if (!selectionText || !tab?.url) return;

  // Send message to content script to show annotate UI
  chrome.tabs.sendMessage(tab.id, {
    action: 'show-annotate-ui',
    text: selectionText
  });
}

// Save WeChat article via API
async function saveWeChatArticle(url) {
  const settings = await chrome.storage.sync.get(['apiUrl', 'strategy']);
  const apiUrl = settings.apiUrl || CONFIG.API_BASE_URL;

  const response = await fetch(`${apiUrl}/scrape`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      url: url,
      strategy: settings.strategy || CONFIG.DEFAULT_STRATEGY,
      source: 'extension'
    })
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  const data = await response.json();
  showNotification('articleSaved', data.title);

  // Open the article in the web app
  chrome.tabs.create({
    url: `${apiUrl.replace('/api', '')}/articles/${data.id}`
  });

  return data;
}

// Save generic page using content extraction
async function saveGenericPage(tab) {
  // Inject content extraction script
  const [result] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: extractPageContent
  });

  const content = result?.result;
  if (!content) {
    throw new Error('Could not extract page content');
  }

  // Save to API
  const settings = await chrome.storage.sync.get(['apiUrl']);
  const apiUrl = settings.apiUrl || CONFIG.API_BASE_URL;

  const response = await fetch(`${apiUrl}/articles`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      url: tab.url,
      title: content.title,
      content: content.content,
      author: content.author,
      source: 'extension',
      isWeChat: false
    })
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  const data = await response.json();
  showNotification('articleSaved', data.title);

  return data;
}

// Save HTML content
async function saveHtmlContent(url, html) {
  const settings = await chrome.storage.sync.get(['apiUrl']);
  const apiUrl = settings.apiUrl || CONFIG.API_BASE_URL;

  const response = await fetch(`${apiUrl}/articles/import`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      url: url,
      html: html,
      source: 'extension'
    })
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  const data = await response.json();
  showNotification('articleSaved', data.title);

  return data;
}

// Save clip/note
async function saveClip(clipData) {
  const settings = await chrome.storage.sync.get(['apiUrl']);
  const apiUrl = settings.apiUrl || CONFIG.API_BASE_URL;

  const response = await fetch(`${apiUrl}/clips`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(clipData)
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  return response.json();
}

// Check if URL is a WeChat article
function isWeChatArticle(url) {
  return url.includes('mp.weixin.qq.com');
}

// Show notification
function showNotification(messageId, ...args) {
  const message = chrome.i18n.getMessage(messageId, args);

  chrome.notifications.create({
    type: 'basic',
    iconUrl: 'icons/icon-128.png',
    title: chrome.i18n.getMessage('extName'),
    message: message
  });
}

// Message handling from content scripts and popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log('[WeChat Scraper] Message received:', message.action);

  switch (message.action) {
    case 'save-page':
      saveCurrentPage(sender.tab).then(sendResponse).catch(sendResponse);
      return true; // Async response

    case 'get-status':
      getExtensionStatus().then(sendResponse);
      return true;

    case 'get-settings':
      chrome.storage.sync.get(null, sendResponse);
      return true;

    case 'save-settings':
      chrome.storage.sync.set(message.settings, () => {
        sendResponse({ success: true });
      });
      return true;
  }
});

// Get extension status
async function getExtensionStatus() {
  const settings = await chrome.storage.sync.get(null);
  return {
    apiUrl: settings.apiUrl || CONFIG.API_BASE_URL,
    strategy: settings.strategy || CONFIG.DEFAULT_STRATEGY,
    version: chrome.runtime.getManifest().version
  };
}

// Content extraction function (runs in page context)
function extractPageContent() {
  // Try to use Readability if available
  if (typeof Readability !== 'undefined') {
    const documentClone = document.cloneNode(true);
    const reader = new Readability(documentClone);
    const article = reader.parse();

    if (article) {
      return {
        title: article.title,
        content: article.content,
        author: article.byline || '',
        excerpt: article.excerpt || ''
      };
    }
  }

  // Fallback to basic extraction
  return {
    title: document.title,
    content: document.body.innerText,
    author: '',
    excerpt: document.querySelector('meta[name="description"]')?.content || ''
  };
}

// Get selection context
function getSelectionContext() {
  const selection = window.getSelection();
  if (!selection.rangeCount) return {};

  const range = selection.getRangeAt(0);
  const container = range.commonAncestorContainer;
  const paragraph = container.nodeType === Node.TEXT_NODE
    ? container.parentElement
    : container;

  return {
    text: selection.toString(),
    paragraph: paragraph?.textContent || '',
    url: window.location.href
  };
}

// Inject annotate UI
function injectAnnotateUI() {
  // This will be handled by the content script
  window.postMessage({
    type: 'WECHAT_SCRAPER_SHOW_ANNOTATE',
    text: window.getSelection().toString()
  }, '*');
}

console.log('[WeChat Scraper] Background service worker initialized');
