import { test, expect } from '@playwright/test';
import { createTestUser, cleanupTestUser, TEST_ARTICLE_URL } from '../utils/test-helpers';

/**
 * Article Scraping E2E Test Suite
 *
 * Tests: CLI scrape → Web UI display → Inbox integration
 * Covers the critical path from URL to readable article
 */

test.describe('Article Scraping Flow', () => {
  let testUser: { id: string; email: string; token: string };

  test.beforeAll(async () => {
    testUser = await createTestUser();
  });

  test.afterAll(async () => {
    await cleanupTestUser(testUser.id);
  });

  test('should scrape article via CLI and display in web UI', async ({ page }) => {
    // Step 1: Trigger scrape via API (simulating CLI call)
    const scrapeResponse = await fetch(`${process.env.API_URL}/api/scrape`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${testUser.token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        url: TEST_ARTICLE_URL,
        strategy: 'adaptive',
      }),
    });

    expect(scrapeResponse.status).toBe(200);
    const { articleId } = await scrapeResponse.json();
    expect(articleId).toBeDefined();

    // Step 2: Wait for processing (with retry)
    let articleReady = false;
    let retries = 0;
    while (!articleReady && retries < 30) {
      await page.waitForTimeout(1000);
      const statusResponse = await fetch(
        `${process.env.API_URL}/api/articles/${articleId}/status`,
        { headers: { 'Authorization': `Bearer ${testUser.token}` } }
      );
      const status = await statusResponse.json();
      if (status.status === 'completed') {
        articleReady = true;
      }
      retries++;
    }

    expect(articleReady).toBe(true);

    // Step 3: Verify in web UI
    await page.goto(`/articles/${articleId}`);
    await page.waitForLoadState('networkidle');

    // Check article content is displayed
    const title = await page.locator('h1.article-title').textContent();
    expect(title).toBeTruthy();
    expect(title.length).toBeGreaterThan(5);

    // Check content is rendered
    const content = await page.locator('.article-content').textContent();
    expect(content).toBeTruthy();
    expect(content.length).toBeGreaterThan(100);

    // Check metadata
    const author = await page.locator('.article-meta .author').textContent();
    expect(author).toBeTruthy();
  });

  test('should handle scrape failure gracefully', async ({ page }) => {
    const invalidUrl = 'https://invalid-domain-that-does-not-exist.com/article';

    const response = await fetch(`${process.env.API_URL}/api/scrape`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${testUser.token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ url: invalidUrl }),
    });

    expect(response.status).toBe(400);
    const error = await response.json();
    expect(error.error).toBeDefined();
    expect(error.error).toContain('无法抓取');
  });

  test('should extract and display article images', async ({ page }) => {
    // Scrape article with images
    const scrapeResponse = await fetch(`${process.env.API_URL}/api/scrape`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${testUser.token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        url: TEST_ARTICLE_URL,
        downloadImages: true,
      }),
    });

    const { articleId } = await scrapeResponse.json();

    // Navigate to article
    await page.goto(`/articles/${articleId}`);
    await page.waitForSelector('.article-content img', { timeout: 10000 });

    // Verify images are loaded
    const images = await page.locator('.article-content img').all();
    expect(images.length).toBeGreaterThan(0);

    // Verify images are not broken
    for (const img of images.slice(0, 3)) {
      const naturalWidth = await img.evaluate(el => (el as HTMLImageElement).naturalWidth);
      expect(naturalWidth).toBeGreaterThan(0);
    }
  });

  test('should auto-classify content type in inbox', async ({ page }) => {
    // Scrape different content types
    const urls = [
      { url: 'https://example.com/tech-newsletter', expectedType: 'newsletter' },
      { url: 'https://example.com/research-paper', expectedType: 'paper' },
    ];

    for (const { url, expectedType } of urls) {
      const scrapeResponse = await fetch(`${process.env.API_URL}/api/scrape`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${testUser.token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ url }),
      });

      const { articleId } = await scrapeResponse.json();

      // Check inbox classification
      const inboxResponse = await fetch(
        `${process.env.API_URL}/api/inbox?articleId=${articleId}`,
        { headers: { 'Authorization': `Bearer ${testUser.token}` } }
      );

      const inboxItem = await inboxResponse.json();
      expect(inboxItem.contentType).toBe(expectedType);
    }
  });
});
