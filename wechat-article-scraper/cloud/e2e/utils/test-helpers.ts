/**
 * E2E Test Helpers
 *
 * Shared utilities for Playwright tests
 */

import { randomUUID } from 'crypto';

const API_URL = process.env.API_URL || 'http://localhost:3000';

// Test article URLs for different scenarios
export const TEST_ARTICLE_URL = 'https://mp.weixin.qq.com/s/example-article-id';

// Mock HTML content for testing
export const MOCK_ARTICLE_HTML = `
<!DOCTYPE html>
<html>
<head>
  <title>Test Article Title</title>
  <meta name="author" content="Test Author">
  <meta property="og:title" content="Test Article Title">
  <meta property="og:description" content="This is a test article description.">
</head>
<body>
  <article>
    <h1>Test Article Title</h1>
    <p>This is the first paragraph with some interesting content about technology and software development best practices.</p>
    <p>This is the second paragraph discussing implementation details and architectural decisions.</p>
    <p>The final paragraph concludes with key takeaways and actionable insights for readers.</p>
  </article>
</body>
</html>
`;

interface TestUser {
  id: string;
  email: string;
  token: string;
}

interface ArticleInput {
  title: string;
  content: string;
  author?: string;
  url?: string;
}

/**
 * Create a test user for E2E testing
 */
export async function createTestUser(): Promise<TestUser> {
  const uuid = randomUUID();
  const email = `test-${uuid}@example.com`;
  const password = `TestPass123!${uuid}`;

  // Register user
  const signupResponse = await fetch(`${API_URL}/api/auth/signup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });

  if (!signupResponse.ok) {
    throw new Error(`Failed to create test user: ${await signupResponse.text()}`);
  }

  const signupData = await signupResponse.json();

  // Login to get token
  const loginResponse = await fetch(`${API_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });

  if (!loginResponse.ok) {
    throw new Error(`Failed to login test user: ${await loginResponse.text()}`);
  }

  const { token } = await loginResponse.json();

  return {
    id: signupData.user.id,
    email,
    token,
  };
}

/**
 * Cleanup test user after tests
 */
export async function cleanupTestUser(userId: string): Promise<void> {
  // Note: This requires admin API or direct database access
  // For now, we'll mark user as deleted or use test isolation
  try {
    await fetch(`${API_URL}/api/admin/users/${userId}`, {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${process.env.ADMIN_TOKEN || ''}`,
      },
    });
  } catch (error) {
    console.warn('Failed to cleanup test user:', error);
  }
}

/**
 * Create a test article via API
 */
export async function createTestArticle(
  token: string,
  input: ArticleInput
): Promise<string> {
  const response = await fetch(`${API_URL}/api/articles`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      title: input.title,
      content: input.content,
      author: input.author || 'Test Author',
      url: input.url || `https://example.com/test-${randomUUID()}`,
    }),
  });

  if (!response.ok) {
    throw new Error(`Failed to create test article: ${await response.text()}`);
  }

  const data = await response.json();
  return data.id;
}

/**
 * Wait for article processing to complete
 */
export async function waitForArticleProcessing(
  articleId: string,
  token: string,
  maxRetries: number = 30
): Promise<void> {
  for (let i = 0; i < maxRetries; i++) {
    const response = await fetch(`${API_URL}/api/articles/${articleId}/status`, {
      headers: { 'Authorization': `Bearer ${token}` },
    });

    const { status } = await response.json();

    if (status === 'completed') {
      return;
    }

    if (status === 'failed') {
      throw new Error('Article processing failed');
    }

    // Wait 1 second before retrying
    await new Promise(resolve => setTimeout(resolve, 1000));
  }

  throw new Error('Article processing timeout');
}

/**
 * Create a workspace for testing
 */
export async function createTestWorkspace(
  token: string,
  name?: string
): Promise<string> {
  const response = await fetch(`${API_URL}/api/workspaces`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      name: name || `Test Workspace ${randomUUID()}`,
      slug: `test-${randomUUID().slice(0, 8)}`,
    }),
  });

  if (!response.ok) {
    throw new Error(`Failed to create workspace: ${await response.text()}`);
  }

  const data = await response.json();
  return data.id;
}

/**
 * Mock server for external APIs during testing
 */
export function createMockServer() {
  // This would set up a mock server for:
  // - WeChat article responses
  // - Notion API
  // - Obsidian sync
  // etc.

  return {
    start: async () => {
      // Start mock server
    },
    stop: async () => {
      // Stop mock server
    },
    setResponse: (endpoint: string, response: any) => {
      // Configure mock response
    },
  };
}
