import { test, expect } from '@playwright/test';
import { createTestUser, cleanupTestUser, createTestArticle } from '../utils/test-helpers';

/**
 * Reading & Annotation E2E Test Suite
 *
 * Tests: Article reading → Text selection → Annotation creation → Sync
 * Critical path for core user value
 */

test.describe('Reading and Annotation Flow', () => {
  let testUser: { id: string; email: string; token: string };
  let testArticleId: string;

  test.beforeAll(async () => {
    testUser = await createTestUser();
    testArticleId = await createTestArticle(testUser.token, {
      title: 'Test Article for Annotations',
      content: `
        <p>This is the first paragraph with some interesting content about technology.</p>
        <p>This is the second paragraph discussing best practices for software engineering.</p>
        <p>This is the third paragraph with more detailed information about implementation.</p>
        <p>The final paragraph concludes with key takeaways and actionable insights.</p>
      `,
    });
  });

  test.afterAll(async () => {
    await cleanupTestUser(testUser.id);
  });

  test('should display article in reader view', async ({ page }) => {
    await page.goto(`/articles/${testArticleId}`);
    await page.waitForLoadState('networkidle');

    // Check reader layout
    await expect(page.locator('[data-testid="reader-container"]')).toBeVisible();

    // Check typography is readable
    const contentFontSize = await page.locator('.article-content p').first().evaluate(
      el => window.getComputedStyle(el).fontSize
    );
    expect(parseInt(contentFontSize)).toBeGreaterThanOrEqual(16);

    // Check line height
    const lineHeight = await page.locator('.article-content p').first().evaluate(
      el => window.getComputedStyle(el).lineHeight
    );
    expect(lineHeight).not.toBe('normal');
  });

  test('should create text highlight annotation', async ({ page }) => {
    await page.goto(`/articles/${testArticleId}`);
    await page.waitForSelector('.article-content p', { timeout: 10000 });

    // Select text in first paragraph
    const paragraph = page.locator('.article-content p').first();
    await paragraph.click();

    // Triple-click to select paragraph
    await paragraph.click({ clickCount: 3 });

    // Wait for annotation toolbar
    await expect(page.locator('[data-testid="annotation-toolbar"]')).toBeVisible({ timeout: 5000 });

    // Click highlight button
    await page.locator('[data-testid="highlight-button"]').click();

    // Verify highlight is created
    await expect(page.locator('.annotation-highlight')).toBeVisible();

    // Check annotation is saved (API verification)
    const annotationsResponse = await fetch(
      `${process.env.API_URL}/api/articles/${testArticleId}/annotations`,
      { headers: { 'Authorization': `Bearer ${testUser.token}` } }
    );

    const annotations = await annotationsResponse.json();
    expect(annotations.length).toBeGreaterThan(0);
    expect(annotations[0].quote).toContain('first paragraph');
  });

  test('should add comment to annotation', async ({ page }) => {
    await page.goto(`/articles/${testArticleId}`);
    await page.waitForSelector('.article-content p', { timeout: 10000 });

    // Create highlight
    const paragraph = page.locator('.article-content p').nth(1);
    await paragraph.click({ clickCount: 3 });
    await page.locator('[data-testid="highlight-button"]').click();

    // Add comment
    await page.locator('[data-testid="add-comment-button"]').click();
    await page.locator('[data-testid="comment-input"]').fill('This is my important insight about this text.');
    await page.locator('[data-testid="save-comment-button"]').click();

    // Verify comment is saved
    await expect(page.locator('[data-testid="annotation-card"]')).toContainText('This is my important insight');

    // API verification
    const annotationsResponse = await fetch(
      `${process.env.API_URL}/api/articles/${testArticleId}/annotations`,
      { headers: { 'Authorization': `Bearer ${testUser.token}` } }
    );

    const annotations = await annotationsResponse.json();
    const annotationWithComment = annotations.find((a: any) => a.comment?.includes('important insight'));
    expect(annotationWithComment).toBeDefined();
  });

  test('should persist annotations across page reloads', async ({ page }) => {
    // Create annotation
    await page.goto(`/articles/${testArticleId}`);
    await page.waitForSelector('.article-content p', { timeout: 10000 });

    const paragraph = page.locator('.article-content p').nth(2);
    await paragraph.click({ clickCount: 3 });
    await page.locator('[data-testid="highlight-button"]').click();

    // Wait for save
    await page.waitForTimeout(1000);

    // Reload page
    await page.reload();
    await page.waitForSelector('.article-content p', { timeout: 10000 });

    // Verify annotation is restored
    await expect(page.locator('.annotation-highlight')).toBeVisible();

    // Click on highlight to show annotation
    await page.locator('.annotation-highlight').first().click();
    await expect(page.locator('[data-testid="annotation-card"]')).toBeVisible();
  });

  test('should support keyboard navigation in reader', async ({ page }) => {
    await page.goto(`/articles/${testArticleId}`);
    await page.waitForSelector('.article-content p', { timeout: 10000 });

    // Press 'j' to scroll down
    await page.keyboard.press('j');
    const scrollY1 = await page.evaluate(() => window.scrollY);
    expect(scrollY1).toBeGreaterThan(0);

    // Press 'k' to scroll up
    await page.keyboard.press('k');
    const scrollY2 = await page.evaluate(() => window.scrollY);
    expect(scrollY2).toBeLessThan(scrollY1);

    // Press 'h' to show help
    await page.keyboard.press('h');
    await expect(page.locator('[data-testid="keyboard-shortcuts-modal"]')).toBeVisible();

    // Close help with Escape
    await page.keyboard.press('Escape');
    await expect(page.locator('[data-testid="keyboard-shortcuts-modal"]')).toBeHidden();
  });

  test('should track reading progress', async ({ page }) => {
    await page.goto(`/articles/${testArticleId}`);
    await page.waitForSelector('.article-content p', { timeout: 10000 });

    // Scroll to bottom
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(500); // Debounce time

    // Check progress is saved
    const progressResponse = await fetch(
      `${process.env.API_URL}/api/articles/${testArticleId}/progress`,
      { headers: { 'Authorization': `Bearer ${testUser.token}` } }
    );

    const progress = await progressResponse.json();
    expect(progress.progressPercentage).toBeGreaterThan(80);

    // Reload and check progress bar
    await page.reload();
    await expect(page.locator('[data-testid="reading-progress-bar"]')).toBeVisible();
    const progressWidth = await page.locator('[data-testid="reading-progress-bar"]').evaluate(
      el => (el as HTMLElement).style.width
    );
    expect(parseInt(progressWidth)).toBeGreaterThan(80);
  });

  test('should export annotations to markdown', async ({ page }) => {
    // Create annotation first
    await page.goto(`/articles/${testArticleId}`);
    await page.waitForSelector('.article-content p', { timeout: 10000 });

    const paragraph = page.locator('.article-content p').first();
    await paragraph.click({ clickCount: 3 });
    await page.locator('[data-testid="highlight-button"]').click();
    await page.locator('[data-testid="add-comment-button"]').click();
    await page.locator('[data-testid="comment-input"]').fill('Key insight');
    await page.locator('[data-testid="save-comment-button"]').click();

    // Export annotations
    await page.locator('[data-testid="export-annotations-button"]').click();
    await page.locator('[data-testid="export-format-markdown"]').click();

    // Verify download
    const download = await page.waitForEvent('download');
    expect(download.suggestedFilename()).toContain('.md');
  });
});
