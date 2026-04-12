/**
 * Content Script for WeChat Articles
 *
 * Enhances WeChat article pages with:
 * - Floating save button
 * - Reading progress indicator
 * - Quick annotation UI
 * - Integration with main app
 */

// Check if already initialized
if (window.weChatScraperInjected) {
  console.log('[WeChat Scraper] Already injected');
} else {
  window.weChatScraperInjected = true;
  init();
}

function init() {
  console.log('[WeChat Scraper] Content script initialized');

  // Wait for page to load
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', onReady);
  } else {
    onReady();
  }
}

function onReady() {
  // Check if this is a valid WeChat article
  if (!isValidArticle()) {
    console.log('[WeChat Scraper] Not a valid article page');
    return;
  }

  // Extract article metadata
  const metadata = extractMetadata();
  console.log('[WeChat Scraper] Article metadata:', metadata);

  // Inject floating action button
  injectFloatingButton();

  // Inject reading progress
  injectProgressBar();

  // Setup message listener
  setupMessageListener();

  // Track reading progress
  trackReadingProgress();

  // Notify background script
  chrome.runtime.sendMessage({
    action: 'page-loaded',
    metadata: metadata
  });
}

// Check if valid article page
function isValidArticle() {
  const content = document.getElementById('js_content');
  const title = document.getElementById('activity_name');
  return !!(content && title);
}

// Extract article metadata
function extractMetadata() {
  const titleEl = document.getElementById('activity_name');
  const authorEl = document.getElementById('js_name');
  const contentEl = document.getElementById('js_content');
  const publishTimeEl = document.getElementById('publish_time');

  // Try to get read/like counts
  const readCount = extractCount('read_count');
  const likeCount = extractCount('like_count');

  return {
    title: titleEl?.textContent?.trim() || document.title,
    author: authorEl?.textContent?.trim() || '',
    url: window.location.href,
    publishTime: publishTimeEl?.textContent?.trim() || '',
    contentLength: contentEl?.textContent?.length || 0,
    readCount: readCount,
    likeCount: likeCount,
    biz: extractBizFromUrl(),
    sn: extractSnFromUrl()
  };
}

// Extract count from page
function extractCount(id) {
  const el = document.getElementById(id);
  if (el) {
    const text = el.textContent?.trim() || '';
    const match = text.match(/[\d,]+/);
    return match ? parseInt(match[0].replace(/,/g, '')) : 0;
  }
  return 0;
}

// Extract biz parameter from URL
function extractBizFromUrl() {
  const url = new URL(window.location.href);
  return url.searchParams.get('__biz') || '';
}

// Extract sn parameter from URL
function extractSnFromUrl() {
  const url = new URL(window.location.href);
  return url.searchParams.get('sn') || '';
}

// Inject floating save button
function injectFloatingButton() {
  // Check if already exists
  if (document.getElementById('wcs-floating-btn')) return;

  const container = document.createElement('div');
  container.id = 'wcs-floating-btn';

  const mainBtn = document.createElement('button');
  mainBtn.className = 'wcs-btn-main';
  mainBtn.title = '保存到微信文章助手';
  mainBtn.innerHTML = '<svg viewBox="0 0 24 24" width="24" height="24"><path fill="currentColor" d="M17 3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V7l-4-4zm-5 16c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3zm3-10H5V5h10v4z"/></svg>';

  const menu = document.createElement('div');
  menu.className = 'wcs-btn-menu';

  const saveBtn = document.createElement('button');
  saveBtn.className = 'wcs-menu-item';
  saveBtn.dataset.action = 'save';
  saveBtn.textContent = '💾 保存文章';

  const annotateBtn = document.createElement('button');
  annotateBtn.className = 'wcs-menu-item';
  annotateBtn.dataset.action = 'annotate';
  annotateBtn.textContent = '📝 标注模式';

  const settingsBtn = document.createElement('button');
  settingsBtn.className = 'wcs-menu-item';
  settingsBtn.dataset.action = 'settings';
  settingsBtn.textContent = '⚙️ 设置';

  menu.appendChild(saveBtn);
  menu.appendChild(annotateBtn);
  menu.appendChild(settingsBtn);
  container.appendChild(mainBtn);
  container.appendChild(menu);

  document.body.appendChild(container);

  // Setup event listeners
  mainBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    menu.classList.toggle('wcs-show');
  });

  // Menu items
  menu.querySelectorAll('.wcs-menu-item').forEach(item => {
    item.addEventListener('click', (e) => {
      e.stopPropagation();
      const action = item.dataset.action;
      handleAction(action);
      menu.classList.remove('wcs-show');
    });
  });

  // Close menu when clicking outside
  document.addEventListener('click', () => {
    menu.classList.remove('wcs-show');
  });
}

// Handle button actions
function handleAction(action) {
  switch (action) {
    case 'save':
      saveCurrentArticle();
      break;
    case 'annotate':
      enableAnnotateMode();
      break;
    case 'settings':
      openSettings();
      break;
  }
}

// Save current article
async function saveCurrentArticle() {
  const btn = document.querySelector('.wcs-btn-main');
  btn.classList.add('wcs-loading');

  try {
    const response = await chrome.runtime.sendMessage({
      action: 'save-page'
    });

    if (response.error) {
      showToast('保存失败: ' + response.error, 'error');
    } else {
      showToast('文章已保存!', 'success');
    }
  } catch (error) {
    showToast('保存失败', 'error');
  } finally {
    btn.classList.remove('wcs-loading');
  }
}

// Enable annotate mode
function enableAnnotateMode() {
  document.body.classList.add('wcs-annotate-mode');
  showToast('标注模式已开启 - 选中文字即可标注', 'info');

  // Setup selection handler
  setupSelectionHandler();
}

// Setup selection handler for annotations
function setupSelectionHandler() {
  let selectionTimeout;

  document.addEventListener('mouseup', () => {
    clearTimeout(selectionTimeout);
    selectionTimeout = setTimeout(() => {
      const selection = window.getSelection();
      const text = selection.toString().trim();

      if (text.length > 0) {
        showAnnotateToolbar(selection);
      }
    }, 200);
  });
}

// Show annotation toolbar
function showAnnotateToolbar(selection) {
  // Remove existing toolbar
  const existing = document.getElementById('wcs-annotate-toolbar');
  if (existing) existing.remove();

  const range = selection.getRangeAt(0);
  const rect = range.getBoundingClientRect();

  const toolbar = document.createElement('div');
  toolbar.id = 'wcs-annotate-toolbar';

  const colors = [
    { color: 'yellow', bg: '#fef3c7' },
    { color: 'green', bg: '#d1fae5' },
    { color: 'blue', bg: '#dbeafe' },
    { color: 'pink', bg: '#fce7f3' }
  ];

  colors.forEach(({ color, bg }) => {
    const btn = document.createElement('button');
    btn.dataset.color = color;
    btn.style.background = bg;
    btn.addEventListener('click', () => {
      highlightSelection(selection, color);
      toolbar.remove();
    });
    toolbar.appendChild(btn);
  });

  const commentBtn = document.createElement('button');
  commentBtn.dataset.color = 'comment';
  commentBtn.title = '添加批注';
  commentBtn.textContent = '💬';
  commentBtn.addEventListener('click', () => {
    addComment(selection);
    toolbar.remove();
  });
  toolbar.appendChild(commentBtn);

  toolbar.style.cssText = `
    position: fixed;
    left: ${rect.left + rect.width / 2}px;
    top: ${rect.top - 50}px;
    transform: translateX(-50%);
    background: #1f2937;
    border-radius: 8px;
    padding: 8px;
    display: flex;
    gap: 8px;
    z-index: 10000;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  `;

  toolbar.querySelectorAll('button').forEach(btn => {
    btn.style.cssText = `
      width: 28px;
      height: 28px;
      border: none;
      border-radius: 4px;
      cursor: pointer;
      font-size: 14px;
    `;
  });

  document.body.appendChild(toolbar);

  // Remove on outside click
  setTimeout(() => {
    document.addEventListener('click', function removeToolbar(e) {
      if (!toolbar.contains(e.target)) {
        toolbar.remove();
        document.removeEventListener('click', removeToolbar);
      }
    });
  }, 100);
}

// Highlight selection
function highlightSelection(selection, color) {
  const range = selection.getRangeAt(0);
  const span = document.createElement('span');
  span.className = `wcs-highlight wcs-highlight-${color}`;
  span.dataset.timestamp = Date.now();

  try {
    range.surroundContents(span);
  } catch (e) {
    // Handle cross-node selections
    const contents = range.extractContents();
    span.appendChild(contents);
    range.insertNode(span);
  }

  // Save annotation
  saveAnnotation({
    quote: selection.toString(),
    color: color,
    url: window.location.href,
    timestamp: Date.now()
  });
}

// Add comment to selection
function addComment(selection) {
  const text = selection.toString();
  const comment = prompt('添加批注:', '');

  if (comment) {
    highlightSelection(selection, 'yellow');
    saveAnnotation({
      quote: text,
      comment: comment,
      color: 'yellow',
      url: window.location.href,
      timestamp: Date.now()
    });
  }
}

// Save annotation to storage
async function saveAnnotation(annotation) {
  try {
    await chrome.storage.local.get(['annotations'], (result) => {
      const annotations = result.annotations || [];
      annotations.push(annotation);
      chrome.storage.local.set({ annotations });
    });

    // Also send to API
    chrome.runtime.sendMessage({
      action: 'save-annotation',
      annotation: annotation
    });
  } catch (error) {
    console.error('[WeChat Scraper] Failed to save annotation:', error);
  }
}

// Open settings
function openSettings() {
  chrome.runtime.openOptionsPage?.() ||
  chrome.tabs.create({
    url: chrome.runtime.getURL('src/options.html')
  });
}

// Inject reading progress bar
function injectProgressBar() {
  if (document.getElementById('wcs-progress-bar')) return;

  const progress = document.createElement('div');
  progress.id = 'wcs-progress-bar';

  const fill = document.createElement('div');
  fill.className = 'wcs-progress-fill';
  progress.appendChild(fill);

  document.body.appendChild(progress);
}

// Track reading progress
function trackReadingProgress() {
  const progressBar = document.querySelector('.wcs-progress-fill');
  if (!progressBar) return;

  let ticking = false;

  window.addEventListener('scroll', () => {
    if (!ticking) {
      window.requestAnimationFrame(() => {
        const scrollTop = window.scrollY;
        const docHeight = document.documentElement.scrollHeight - window.innerHeight;
        const progress = Math.min(100, Math.round((scrollTop / docHeight) * 100));

        progressBar.style.width = progress + '%';

        // Save progress
        chrome.storage.local.set({
          [`progress_${window.location.href}`]: {
            progress,
            timestamp: Date.now()
          }
        });

        ticking = false;
      });
      ticking = true;
    }
  });
}

// Setup message listener
function setupMessageListener() {
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    switch (message.action) {
      case 'get-metadata':
        sendResponse(extractMetadata());
        break;

      case 'show-annotate-ui':
        enableAnnotateMode();
        sendResponse({ success: true });
        break;

      case 'extract-content':
        sendResponse({
          content: document.getElementById('js_content')?.innerHTML || '',
          metadata: extractMetadata()
        });
        break;
    }
  });
}

// Show toast notification
function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `wcs-toast wcs-toast-${type}`;
  toast.textContent = message;

  const colors = {
    success: '#10b981',
    error: '#ef4444',
    info: '#3b82f6'
  };

  toast.style.cssText = `
    position: fixed;
    top: 20px;
    left: 50%;
    transform: translateX(-50%);
    background: ${colors[type]};
    color: white;
    padding: 12px 24px;
    border-radius: 8px;
    font-size: 14px;
    z-index: 10001;
  `;

  document.body.appendChild(toast);

  // Add animation
  toast.animate([
    { opacity: 0, transform: 'translateX(-50%) translateY(-20px)' },
    { opacity: 1, transform: 'translateX(-50%) translateY(0)' }
  ], { duration: 300, easing: 'ease' });

  setTimeout(() => {
    toast.animate([
      { opacity: 1 },
      { opacity: 0 }
    ], { duration: 300 }).onfinish = () => toast.remove();
  }, 3000);
}

// Add CSS styles
const style = document.createElement('style');
style.textContent = `
  #wcs-floating-btn {
    position: fixed;
    right: 20px;
    bottom: 100px;
    z-index: 9999;
  }
  .wcs-btn-main {
    width: 56px;
    height: 56px;
    border-radius: 50%;
    background: #0ea5e9;
    color: white;
    border: none;
    box-shadow: 0 4px 12px rgba(14, 165, 233, 0.4);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: transform 0.2s, box-shadow 0.2s;
  }
  .wcs-btn-main:hover {
    transform: scale(1.05);
    box-shadow: 0 6px 16px rgba(14, 165, 233, 0.5);
  }
  .wcs-btn-menu {
    position: absolute;
    bottom: 64px;
    right: 0;
    background: white;
    border-radius: 12px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.15);
    padding: 8px;
    min-width: 140px;
    opacity: 0;
    visibility: hidden;
    transform: translateY(10px);
    transition: all 0.2s;
  }
  .wcs-btn-menu.wcs-show {
    opacity: 1;
    visibility: visible;
    transform: translateY(0);
  }
  .wcs-menu-item {
    display: block;
    width: 100%;
    padding: 10px 12px;
    border: none;
    background: none;
    text-align: left;
    cursor: pointer;
    border-radius: 8px;
    font-size: 14px;
    white-space: nowrap;
  }
  .wcs-menu-item:hover {
    background: #f3f4f6;
  }
  #wcs-progress-bar {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: rgba(0,0,0,0.1);
    z-index: 10000;
  }
  .wcs-progress-fill {
    height: 100%;
    background: #0ea5e9;
    width: 0%;
    transition: width 0.1s;
  }
  .wcs-highlight {
    padding: 2px 0;
    border-radius: 2px;
  }
  .wcs-highlight-yellow { background: #fef3c7; }
  .wcs-highlight-green { background: #d1fae5; }
  .wcs-highlight-blue { background: #dbeafe; }
  .wcs-highlight-pink { background: #fce7f3; }
`;
document.head.appendChild(style);

console.log('[WeChat Scraper] WeChat content script loaded');
