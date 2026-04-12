/**
 * ftr-site-config 适配器单元测试
 * 验证站点规则获取和内容提取功能
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  SiteConfigManager,
  SiteConfigExtractor,
  hasSiteRule,
  preloadCommonRules,
} from '../../../src/lib/extractors/site-config-adapter';

// Mock fetch
global.fetch = vi.fn();

describe('SiteConfigManager', () => {
  let manager: SiteConfigManager;

  beforeEach(() => {
    manager = new SiteConfigManager();
    vi.clearAllMocks();
  });

  describe('getRule', () => {
    it('should fetch and parse rule from GitHub', async () => {
      const mockRule = `
# Test rule
body: //article[@class="content"]
title: //h1
author: //span[@class="author"]
date: //time
strip: //div[@class="ads"]
strip_id_or_class: sidebar
tidy: yes
prune: no
autodetect_on_failure: yes
test_url: https://example.com/article
      `.trim();

      (fetch as any).mockResolvedValueOnce({
        ok: true,
        text: async () => mockRule,
      });

      const rule = await manager.getRule('example.com');

      expect(rule).not.toBeNull();
      expect(rule?.domain).toBe('example.com');
      expect(rule?.body).toContain('//article[@class="content"]');
      expect(rule?.title).toContain('//h1');
      expect(rule?.author).toContain('//span[@class="author"]');
      expect(rule?.date).toContain('//time');
      expect(rule?.strip).toContain('//div[@class="ads"]');
      expect(rule?.stripIdOrClass).toContain('sidebar');
      expect(rule?.tidy).toBe(true);
      expect(rule?.prune).toBe(false);
      expect(rule?.autodetectOnFailure).toBe(true);
      expect(rule?.test_url).toContain('https://example.com/article');
    });

    it('should return null for non-existent rule', async () => {
      (fetch as any).mockResolvedValueOnce({
        ok: false,
        status: 404,
      });

      (fetch as any).mockResolvedValueOnce({
        ok: false,
        status: 404,
      });

      const rule = await manager.getRule('nonexistent-domain.xyz');

      expect(rule).toBeNull();
    });

    it('should try subdomain fallback', async () => {
      (fetch as any)
        .mockResolvedValueOnce({ ok: false, status: 404 })  // blog.example.com
        .mockResolvedValueOnce({ ok: false, status: 404 })  // example.com (without www)
        .mockResolvedValueOnce({
          ok: true,
          text: async () => 'body: //article',
        }); // main domain

      const rule = await manager.getRule('blog.example.com');

      expect(rule).not.toBeNull();
      expect(fetch).toHaveBeenCalledTimes(3);
    });

    it('should use cached rule within TTL', async () => {
      const mockRule = 'body: //article';

      (fetch as any).mockResolvedValueOnce({
        ok: true,
        text: async () => mockRule,
      });

      // First call should fetch
      await manager.getRule('cached.com');

      // Second call should use cache
      const rule = await manager.getRule('cached.com');

      expect(fetch).toHaveBeenCalledTimes(1);
      expect(rule).not.toBeNull();
    });
  });
});

describe('SiteConfigExtractor', () => {
  let extractor: SiteConfigExtractor;

  beforeEach(() => {
    extractor = new SiteConfigExtractor();
    vi.clearAllMocks();
  });

  describe('extract', () => {
    it('should extract content using site rule', async () => {
      const html = `
<!DOCTYPE html>
<html>
<head><title>Test Article</title></head>
<body>
  <h1>Article Title</h1>
  <span class="author">John Doe</span>
  <time>2024-01-15</time>
  <article class="content">
    <p>This is the main content of the article.</p>
    <p>It has multiple paragraphs.</p>
  </article>
  <div class="ads">Advertisement</div>
</body>
</html>
      `;

      const mockRule = `
body: //article[@class="content"]
title: //h1
author: //span[@class="author"]
date: //time
strip: //div[@class="ads"]
      `;

      (fetch as any).mockResolvedValueOnce({
        ok: true,
        text: async () => mockRule,
      });

      const result = await extractor.extract(html, 'https://example.com/article');

      expect(result.extractor).toBe('site-config');
      expect(result.title).toBe('Article Title');
      expect(result.author).toBe('John Doe');
      expect(result.date).toBe('2024-01-15');
      expect(result.content).toContain('main content');
      expect(result.content).not.toContain('Advertisement');
    });

    it('should fallback to readability when rule fails', async () => {
      const html = `
<!DOCTYPE html>
<html>
<head><title>Fallback Test</title></head>
<body>
  <article>
    <h1>Real Title</h1>
    <p>${'This is a long paragraph with enough content to pass validation. '.repeat(10)}</p>
  </article>
</body>
</html>
      `;

      // Mock a rule that won't find anything
      const mockRule = `
body: //nonexistent
title: //h2
      `;

      (fetch as any).mockResolvedValueOnce({
        ok: true,
        text: async () => mockRule,
      });

      const result = await extractor.extract(html, 'https://example.com/article');

      // Should fallback to readability
      expect(result.extractor).toBe('readability');
    });

    it('should use readability when no rule exists', async () => {
      const html = `
<!DOCTYPE html>
<html>
<head><title>No Rule Test</title></head>
<body>
  <article>
    <h1>Article</h1>
    <p>${'Content content content. '.repeat(20)}</p>
  </article>
</body>
</html>
      `;

      (fetch as any).mockResolvedValueOnce({
        ok: false,
        status: 404,
      });

      (fetch as any).mockResolvedValueOnce({
        ok: false,
        status: 404,
      });

      const result = await extractor.extract(html, 'https://unknown-site.com/article');

      expect(result.extractor).toBe('readability');
    });
  });
});

describe('hasSiteRule', () => {
  it('should return true when rule exists', async () => {
    (fetch as any).mockResolvedValueOnce({
      ok: true,
      text: async () => 'body: //article',
    });

    const hasRule = await hasSiteRule('https://example.com/article');

    expect(hasRule).toBe(true);
  });

  it('should return false when no rule exists', async () => {
    (fetch as any).mockResolvedValueOnce({
      ok: false,
      status: 404,
    });

    (fetch as any).mockResolvedValueOnce({
      ok: false,
      status: 404,
    });

    const hasRule = await hasSiteRule('https://unknown.xyz/article');

    expect(hasRule).toBe(false);
  });
});

describe('preloadCommonRules', () => {
  it('should preload rules for common domains', async () => {
    (fetch as any).mockImplementation(() =>
      Promise.resolve({
        ok: true,
        text: async () => 'body: //article',
      })
    );

    await preloadCommonRules();

    // Should have fetched rules for common domains
    expect(fetch).toHaveBeenCalledTimes(8); // 8 common domains
  });
});
