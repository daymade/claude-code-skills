/**
 * ftr-site-config 适配器
 * 集成社区维护的站点规则库，提供精准内容提取
 * @see https://github.com/fivefilters/ftr-site-config
 */

import { JSDOM } from 'jsdom';
import { Readability } from '@mozilla/readability';

// 规则缓存
const ruleCache = new Map<string, SiteConfigRule>();
const CACHE_TTL = 24 * 60 * 60 * 1000; // 24小时
let lastFetch = 0;

interface SiteConfigRule {
  domain: string;
  body?: string[];
  title?: string[];
  author?: string[];
  date?: string[];
  strip?: string[];
  stripIdOrClass?: string[];
  tidy?: boolean;
  prune?: boolean;
  autodetectOnFailure?: boolean;
  test_url?: string[];
}

interface ExtractedContent {
  title: string;
  content: string;
  author?: string;
  date?: string;
  excerpt?: string;
  siteName?: string;
  extractor: 'site-config' | 'readability' | 'failure';
}

/**
 * 站点配置管理器
 * 负责从 GitHub 获取和缓存站点规则
 */
export class SiteConfigManager {
  private readonly baseUrl = 'https://raw.githubusercontent.com/fivefilters/ftr-site-config/master';

  /**
   * 获取域名对应的规则
   */
  async getRule(domain: string): Promise<SiteConfigRule | null> {
    // 检查缓存
    const cached = ruleCache.get(domain);
    if (cached && Date.now() - lastFetch < CACHE_TTL) {
      return cached;
    }

    try {
      const rule = await this.fetchRule(domain);
      if (rule) {
        ruleCache.set(domain, rule);
        lastFetch = Date.now();
      }
      return rule;
    } catch (error) {
      console.warn(`Failed to fetch rule for ${domain}:`, error);
      return null;
    }
  }

  /**
   * 从 GitHub 获取规则文件
   */
  private async fetchRule(domain: string): Promise<SiteConfigRule | null> {
    // 尝试直接匹配域名
    const urls = [
      `${this.baseUrl}/${domain}.txt`,
      // 尝试去掉 www
      domain.startsWith('www.') ? `${this.baseUrl}/${domain.slice(4)}.txt` : null,
      // 尝试提取主域名 (例如 blog.example.com -> example.com)
      this.extractMainDomain(domain),
    ].filter(Boolean) as string[];

    for (const url of urls) {
      try {
        const response = await fetch(url, {
          headers: {
            'User-Agent': 'WeChat-Scraper/2.0 (Content Extractor)',
          },
        });

        if (response.ok) {
          const content = await response.text();
          return this.parseConfig(content, domain);
        }
      } catch (error) {
        continue;
      }
    }

    return null;
  }

  /**
   * 提取主域名
   */
  private extractMainDomain(domain: string): string | null {
    const parts = domain.split('.');
    if (parts.length >= 2) {
      const mainDomain = parts.slice(-2).join('.');
      return `${this.baseUrl}/${mainDomain}.txt`;
    }
    return null;
  }

  /**
   * 解析 ftr-site-config 格式的配置
   */
  private parseConfig(content: string, domain: string): SiteConfigRule {
    const rule: SiteConfigRule = { domain };
    const lines = content.split('\n');

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;

      const colonIndex = trimmed.indexOf(':');
      if (colonIndex === -1) continue;

      const key = trimmed.slice(0, colonIndex).trim();
      const value = trimmed.slice(colonIndex + 1).trim();

      switch (key) {
        case 'body':
          rule.body = rule.body || [];
          rule.body.push(value);
          break;
        case 'title':
          rule.title = rule.title || [];
          rule.title.push(value);
          break;
        case 'author':
          rule.author = rule.author || [];
          rule.author.push(value);
          break;
        case 'date':
          rule.date = rule.date || [];
          rule.date.push(value);
          break;
        case 'strip':
          rule.strip = rule.strip || [];
          rule.strip.push(value);
          break;
        case 'strip_id_or_class':
          rule.stripIdOrClass = rule.stripIdOrClass || [];
          rule.stripIdOrClass.push(...value.split(/\s+/));
          break;
        case 'tidy':
          rule.tidy = value.toLowerCase() === 'yes';
          break;
        case 'prune':
          rule.prune = value.toLowerCase() !== 'no';
          break;
        case 'autodetect_on_failure':
          rule.autodetectOnFailure = value.toLowerCase() !== 'no';
          break;
        case 'test_url':
          rule.test_url = rule.test_url || [];
          rule.test_url.push(value);
          break;
      }
    }

    return rule;
  }
}

/**
 * 使用站点规则提取内容
 */
export class SiteConfigExtractor {
  private manager: SiteConfigManager;

  constructor() {
    this.manager = new SiteConfigManager();
  }

  /**
   * 提取内容的主入口
   */
  async extract(html: string, url: string): Promise<ExtractedContent> {
    const domain = this.extractDomain(url);
    const rule = await this.manager.getRule(domain);

    if (rule) {
      const result = this.extractWithRule(html, rule, url);
      if (this.isValidResult(result)) {
        return { ...result, extractor: 'site-config' };
      }

      // 如果规则提取失败且允许自动检测，回退到 Readability
      if (rule.autodetectOnFailure !== false) {
        return this.extractWithReadability(html, url);
      }
    }

    // 无规则或规则失效，使用 Readability
    return this.extractWithReadability(html, url);
  }

  /**
   * 使用站点规则提取
   */
  private extractWithRule(
    html: string,
    rule: SiteConfigRule,
    url: string
  ): ExtractedContent {
    const dom = new JSDOM(html, { url });
    const document = dom.window.document;

    // 提取标题
    let title = '';
    if (rule.title) {
      for (const selector of rule.title) {
        const el = document.querySelector(selector);
        if (el?.textContent) {
          title = el.textContent.trim();
          break;
        }
      }
    }

    // 提取作者
    let author: string | undefined;
    if (rule.author) {
      for (const selector of rule.author) {
        const el = document.querySelector(selector);
        if (el?.textContent) {
          author = el.textContent.trim();
          break;
        }
      }
    }

    // 提取日期
    let date: string | undefined;
    if (rule.date) {
      for (const selector of rule.date) {
        const el = document.querySelector(selector);
        if (el?.textContent) {
          date = el.textContent.trim();
          break;
        }
      }
    }

    // 移除不需要的元素
    if (rule.strip) {
      for (const selector of rule.strip) {
        document.querySelectorAll(selector).forEach((el) => el.remove());
      }
    }

    if (rule.stripIdOrClass) {
      for (const name of rule.stripIdOrClass) {
        document
          .querySelectorAll(`[id*="${name}"], [class*="${name}"]`)
          .forEach((el) => el.remove());
      }
    }

    // 提取正文
    let content = '';
    if (rule.body) {
      for (const selector of rule.body) {
        const elements = document.querySelectorAll(selector);
        if (elements.length > 0) {
          content = Array.from(elements)
            .map((el) => this.elementToMarkdown(el))
            .join('\n\n');
          break;
        }
      }
    }

    return {
      title,
      content,
      author,
      date,
      extractor: 'site-config',
    };
  }

  /**
   * 使用 Readability 作为回退
   */
  private extractWithReadability(html: string, url: string): ExtractedContent {
    const dom = new JSDOM(html, { url });
    const reader = new Readability(dom.window.document);
    const article = reader.parse();

    if (article) {
      return {
        title: article.title || '',
        content: article.content || '',
        excerpt: article.excerpt,
        siteName: article.siteName,
        extractor: 'readability',
      };
    }

    return {
      title: '',
      content: '',
      extractor: 'failure',
    };
  }

  /**
   * 验证提取结果是否有效
   */
  private isValidResult(result: ExtractedContent): boolean {
    const contentLength = result.content?.length || 0;
    const titleLength = result.title?.length || 0;

    // 内容至少要有 100 个字符，标题至少 3 个字符
    return contentLength >= 100 && titleLength >= 3;
  }

  /**
   * 从 URL 提取域名
   */
  private extractDomain(url: string): string {
    try {
      const urlObj = new URL(url);
      return urlObj.hostname;
    } catch {
      return url;
    }
  }

  /**
   * 将 DOM 元素转换为 Markdown
   * 使用安全的 textContent 而非 innerHTML
   */
  private elementToMarkdown(element: Element): string {
    const document = element.ownerDocument;
    if (!document) return element.textContent || '';

    // 克隆元素以避免修改原始 DOM
    const clone = element.cloneNode(true) as Element;

    // 处理段落
    const paragraphs = clone.querySelectorAll('p');
    paragraphs.forEach((p) => {
      const text = this.getTextContent(p).trim();
      if (text) {
        const wrapper = document.createElement('span');
        wrapper.textContent = '\n\n' + text + '\n\n';
        p.replaceWith(wrapper);
      }
    });

    // 处理标题
    const headings = clone.querySelectorAll('h1, h2, h3, h4, h5, h6');
    headings.forEach((h) => {
      const level = parseInt(h.tagName[1]);
      const text = this.getTextContent(h).trim();
      if (text) {
        const wrapper = document.createElement('span');
        wrapper.textContent = '\n\n' + '#'.repeat(level) + ' ' + text + '\n\n';
        h.replaceWith(wrapper);
      }
    });

    // 处理列表
    const lists = clone.querySelectorAll('ul, ol');
    lists.forEach((list) => {
      const items = list.querySelectorAll('li');
      const isOrdered = list.tagName === 'OL';
      let listText = '\n\n';

      items.forEach((li, index) => {
        const text = this.getTextContent(li).trim();
        if (text) {
          const prefix = isOrdered ? `${index + 1}. ` : '- ';
          listText += prefix + text + '\n';
        }
      });

      listText += '\n';

      const wrapper = document.createElement('span');
      wrapper.textContent = listText;
      list.replaceWith(wrapper);
    });

    // 处理代码块
    const codeBlocks = clone.querySelectorAll('pre code');
    codeBlocks.forEach((code) => {
      const text = this.getTextContent(code).trim();
      if (text) {
        const wrapper = document.createElement('span');
        wrapper.textContent = '\n\n```\n' + text + '\n```\n\n';
        code.parentElement?.replaceWith(wrapper);
      }
    });

    // 处理行内代码
    const inlineCodes = clone.querySelectorAll('code:not(pre code)');
    inlineCodes.forEach((code) => {
      const text = this.getTextContent(code).trim();
      if (text) {
        const wrapper = document.createElement('span');
        wrapper.textContent = '`' + text + '`';
        code.replaceWith(wrapper);
      }
    });

    // 处理强调
    const bolds = clone.querySelectorAll('strong, b');
    bolds.forEach((b) => {
      const text = this.getTextContent(b).trim();
      if (text) {
        const wrapper = document.createElement('span');
        wrapper.textContent = '**' + text + '**';
        b.replaceWith(wrapper);
      }
    });

    const italics = clone.querySelectorAll('em, i');
    italics.forEach((em) => {
      const text = this.getTextContent(em).trim();
      if (text) {
        const wrapper = document.createElement('span');
        wrapper.textContent = '*' + text + '*';
        em.replaceWith(wrapper);
      }
    });

    // 处理链接
    const links = clone.querySelectorAll('a[href]');
    links.forEach((a) => {
      const href = a.getAttribute('href') || '';
      const text = this.getTextContent(a).trim();
      if (text && href) {
        const wrapper = document.createElement('span');
        wrapper.textContent = `[${text}](${href})`;
        a.replaceWith(wrapper);
      }
    });

    // 处理图片
    const images = clone.querySelectorAll('img[src]');
    images.forEach((img) => {
      const src = img.getAttribute('src') || '';
      const alt = img.getAttribute('alt') || '';
      const wrapper = document.createElement('span');
      wrapper.textContent = `![${alt}](${src})`;
      img.replaceWith(wrapper);
    });

    // 处理换行
    const breaks = clone.querySelectorAll('br');
    breaks.forEach((br) => {
      const wrapper = document.createElement('span');
      wrapper.textContent = '\n';
      br.replaceWith(wrapper);
    });

    // 最后提取纯文本
    return this.getTextContent(clone).trim();
  }

  /**
   * 安全地获取元素的文本内容
   */
  private getTextContent(element: Element): string {
    return element.textContent || '';
  }
}

/**
 * 检查 URL 是否有对应的站点规则
 */
export async function hasSiteRule(url: string): Promise<boolean> {
  const manager = new SiteConfigManager();
  const domain = new URL(url).hostname;
  const rule = await manager.getRule(domain);
  return rule !== null;
}

/**
 * 批量预加载常用站点的规则
 */
export async function preloadCommonRules(): Promise<void> {
  const manager = new SiteConfigManager();
  const commonDomains = [
    'weixin.qq.com',
    'mp.weixin.qq.com',
    'zhihu.com',
    'jianshu.com',
    'csdn.net',
    'github.com',
    'medium.com',
    'substack.com',
  ];

  await Promise.all(
    commonDomains.map((domain) =>
      manager.getRule(domain).catch(() => null)
    )
  );
}

// 导出类型
export type { SiteConfigRule, ExtractedContent };
