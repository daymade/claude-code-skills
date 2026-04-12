/**
 * Annotation Engine - 段落级标注系统
 *
 * 参考世界级框架:
 * - Hypothesis (标注存储模型)
 * - Rangy (文本范围序列化)
 * - Readwise (标注工作流)
 */

export interface TextPosition {
  start: number;
  end: number;
  startNode: string; // XPath or data-node-id
  endNode: string;
}

export interface Annotation {
  id: string;
  articleId: string;
  userId: string;
  position: TextPosition;
  quote: string; // 选中的原文
  comment?: string; // 用户批注
  tags: string[];
  color: 'yellow' | 'green' | 'blue' | 'pink' | 'purple';
  createdAt: string;
  updatedAt: string;
}

export interface ReadingSession {
  id: string;
  articleId: string;
  userId: string;
  startedAt: string;
  lastReadAt: string;
  progress: number; // 0-100
  timeSpent: number; // seconds
  annotations: Annotation[];
}

// XPath工具函数 - 用于持久化文本位置
export class XPathHelper {
  static getXPath(element: Node): string {
    if (element.nodeType === Node.TEXT_NODE && element.parentNode) {
      const textIndex = Array.from(element.parentNode.childNodes)
        .filter(n => n.nodeType === Node.TEXT_NODE)
        .indexOf(element as Text);
      return `${this.getXPath(element.parentNode)}/text()[${textIndex + 1}]`;
    }

    if (!(element instanceof Element)) return '';
    if (element.id) return `//*[@id="${element.id}"]`;

    const tag = element.tagName.toLowerCase();
    const parent = element.parentNode;

    if (!parent || parent.nodeType !== Node.ELEMENT_NODE) {
      return tag;
    }

    const siblings = Array.from((parent as Element).children)
      .filter(e => e.tagName === element.tagName);
    const index = siblings.indexOf(element) + 1;

    return `${this.getXPath(parent)}/${tag}[${index}]`;
  }

  static getElementByXPath(xpath: string, context: Node = document): Node | null {
    try {
      const result = document.evaluate(
        xpath,
        context,
        null,
        XPathResult.FIRST_ORDERED_NODE_TYPE,
        null
      );
      return result.singleNodeValue;
    } catch (e) {
      console.error('XPath evaluation failed:', e);
      return null;
    }
  }
}

// 文本选择管理器
export class TextSelectionManager {
  private currentSelection: Selection | null = null;
  private onSelectionChange: ((range: Range | null) => void) | null = null;

  constructor(onChange?: (range: Range | null) => void) {
    this.onSelectionChange = onChange || null;
    this.setupListeners();
  }

  private setupListeners() {
    document.addEventListener('selectionchange', this.handleSelectionChange);
    document.addEventListener('mouseup', this.handleMouseUp);
  }

  private handleSelectionChange = () => {
    this.currentSelection = window.getSelection();
  };

  private handleMouseUp = () => {
    const selection = window.getSelection();
    if (selection && !selection.isCollapsed) {
      const range = selection.getRangeAt(0);
      this.onSelectionChange?.(range);
    } else {
      this.onSelectionChange?.(null);
    }
  };

  getSelectedText(): string {
    return this.currentSelection?.toString() || '';
  }

  getRange(): Range | null {
    const selection = window.getSelection();
    if (selection && selection.rangeCount > 0) {
      return selection.getRangeAt(0);
    }
    return null;
  }

  createAnnotationFromSelection(
    articleId: string,
    userId: string,
    color: Annotation['color'] = 'yellow',
    comment?: string,
    tags: string[] = []
  ): Annotation | null {
    const range = this.getRange();
    if (!range) return null;

    const quote = range.toString().trim();
    if (quote.length < 2) return null; // 太短的选中忽略

    return {
      id: `anno_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      articleId,
      userId,
      position: {
        start: 0, // Will be calculated from nodes
        end: quote.length,
        startNode: XPathHelper.getXPath(range.startContainer),
        endNode: XPathHelper.getXPath(range.endContainer),
      },
      quote,
      comment,
      tags,
      color,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
  }

  highlightRange(range: Range, color: Annotation['color']): HTMLElement {
    const span = document.createElement('span');
    span.className = `annotation-highlight annotation-${color}`;
    span.dataset.annotationId = `temp_${Date.now()}`;

    try {
      range.surroundContents(span);
    } catch (e) {
      // Handle partial selections across nodes
      const contents = range.extractContents();
      span.appendChild(contents);
      range.insertNode(span);
    }

    return span;
  }

  destroy() {
    document.removeEventListener('selectionchange', this.handleSelectionChange);
    document.removeEventListener('mouseup', this.handleMouseUp);
  }
}

// 标注存储管理 - 对标 Hypothesis 存储模型
export class AnnotationStore {
  private dbName = 'WeChatScraperAnnotations';
  private dbVersion = 1;
  private db: IDBDatabase | null = null;

  async init(): Promise<void> {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(this.dbName, this.dbVersion);

      request.onerror = () => reject(request.error);
      request.onsuccess = () => {
        this.db = request.result;
        resolve();
      };

      request.onupgradeneeded = (event) => {
        const db = (event.target as IDBOpenDBRequest).result;

        // Annotations store
        if (!db.objectStoreNames.contains('annotations')) {
          const store = db.createObjectStore('annotations', { keyPath: 'id' });
          store.createIndex('articleId', 'articleId', { unique: false });
          store.createIndex('userId', 'userId', { unique: false });
          store.createIndex('tags', 'tags', { unique: false, multiEntry: true });
        }

        // Reading sessions store
        if (!db.objectStoreNames.contains('sessions')) {
          const store = db.createObjectStore('sessions', { keyPath: 'id' });
          store.createIndex('articleId', 'articleId', { unique: false });
          store.createIndex('userId', 'userId', { unique: false });
        }
      };
    });
  }

  async saveAnnotation(annotation: Annotation): Promise<void> {
    if (!this.db) await this.init();

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction(['annotations'], 'readwrite');
      const store = transaction.objectStore('annotations');
      const request = store.put(annotation);

      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }

  async getAnnotationsByArticle(articleId: string): Promise<Annotation[]> {
    if (!this.db) await this.init();

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction(['annotations'], 'readonly');
      const store = transaction.objectStore('annotations');
      const index = store.index('articleId');
      const request = index.getAll(articleId);

      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  async deleteAnnotation(id: string): Promise<void> {
    if (!this.db) await this.init();

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction(['annotations'], 'readwrite');
      const store = transaction.objectStore('annotations');
      const request = store.delete(id);

      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }

  async getAllTags(): Promise<string[]> {
    if (!this.db) await this.init();

    return new Promise((resolve, reject) => {
      const transaction = this.db!.transaction(['annotations'], 'readonly');
      const store = transaction.objectStore('annotations');
      const request = store.getAll();

      request.onsuccess = () => {
        const annotations: Annotation[] = request.result;
        const tags = new Set(annotations.flatMap(a => a.tags));
        resolve(Array.from(tags));
      };
      request.onerror = () => reject(request.error);
    });
  }

  // Export annotations in Readwise-compatible format
  async exportForReadwise(): Promise<any[]> {
    const allAnnotations = await new Promise<Annotation[]>((resolve, reject) => {
      const transaction = this.db!.transaction(['annotations'], 'readonly');
      const store = transaction.objectStore('annotations');
      const request = store.getAll();
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });

    return allAnnotations.map(anno => ({
      text: anno.quote,
      note: anno.comment || '',
      tags: anno.tags.join(', '),
      source_url: `https://mp.weixin.qq.com/s/${anno.articleId}`,
      source_type: 'wechat_article',
      highlighted_at: anno.createdAt,
    }));
  }
}

// 阅读进度追踪
export class ReadingProgressTracker {
  private articleId: string;
  private userId: string;
  private startTime: number;
  private lastScrollPosition: number = 0;
  private progressCallback?: (progress: number) => void;

  constructor(articleId: string, userId: string, onProgress?: (progress: number) => void) {
    this.articleId = articleId;
    this.userId = userId;
    this.startTime = Date.now();
    this.progressCallback = onProgress;
    this.setupScrollTracking();
  }

  private setupScrollTracking() {
    let ticking = false;

    window.addEventListener('scroll', () => {
      if (!ticking) {
        window.requestAnimationFrame(() => {
          this.calculateProgress();
          ticking = false;
        });
        ticking = true;
      }
    });
  }

  private calculateProgress() {
    const scrollTop = window.scrollY;
    const docHeight = document.documentElement.scrollHeight - window.innerHeight;
    const progress = Math.min(100, Math.round((scrollTop / docHeight) * 100));

    if (progress !== this.lastScrollPosition) {
      this.lastScrollPosition = progress;
      this.progressCallback?.(progress);
    }
  }

  getTimeSpent(): number {
    return Math.round((Date.now() - this.startTime) / 1000);
  }

  generateSessionSummary(): {
    timeSpent: number;
    progress: number;
    wordsPerMinute: number;
    articleWordCount: number;
  } {
    const timeSpent = this.getTimeSpent();
    const articleText = document.body.innerText;
    const wordCount = articleText.length; // Chinese characters
    const minutes = timeSpent / 60;
    const wpm = minutes > 0 ? Math.round(wordCount / minutes) : 0;

    return {
      timeSpent,
      progress: this.lastScrollPosition,
      wordsPerMinute: wpm,
      articleWordCount: wordCount,
    };
  }
}
