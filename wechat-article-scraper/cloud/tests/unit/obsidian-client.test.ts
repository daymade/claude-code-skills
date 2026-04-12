/**
 * Obsidian Client Unit Tests
 *
 * Tests the Obsidian export functionality:
 * - Markdown generation
 * - Frontmatter formatting
 * - File naming sanitization
 */

import { describe, it, expect } from 'vitest';
import { ObsidianClient, ExportToObsidianOptions } from '@/lib/obsidian-client';

describe('ObsidianClient', () => {
  let client: ObsidianClient;

  beforeEach(() => {
    client = new ObsidianClient();
  });

  describe('exportArticle', () => {
    it('should generate valid markdown with frontmatter', () => {
      const options: ExportToObsidianOptions = {
        article: {
          id: 'test-article-1',
          title: 'Test Article',
          author: 'John Doe',
          content: '<p>This is a test paragraph.</p>',
          url: 'https://example.com/article',
          publishTime: '2024-01-15T00:00:00Z',
          tags: ['test', 'example'],
        },
        annotations: [
          {
            id: 'anno-1',
            quote: 'Important quote',
            comment: 'My thoughts',
            color: 'yellow',
            tags: ['highlight'],
            createdAt: '2024-01-15T10:00:00Z',
          },
        ],
      };

      const result = client.exportArticle(options);

      expect(result.filename).toContain('Test Article');
      expect(result.filename).toEndWith('.md');
      expect(result.content).toContain('---'); // Frontmatter
      expect(result.content).toContain('title: "Test Article"');
      expect(result.content).toContain('author: "John Doe"');
      expect(result.content).toContain('source: "https://example.com/article"');
      expect(result.content).toContain('## 📝 标注');
    });

    it('should handle articles without optional fields', () => {
      const options: ExportToObsidianOptions = {
        article: {
          id: 'minimal-article',
          title: 'Minimal Article',
          content: 'Simple content',
        },
      };

      const result = client.exportArticle(options);

      expect(result.content).toContain('Minimal Article');
      expect(result.content).toContain('author: "Unknown"');
    });

    it('should sanitize filenames', () => {
      const options: ExportToObsidianOptions = {
        article: {
          id: 'bad-filename',
          title: 'Article: With <Invalid> Characters | Test?',
          content: 'Content',
        },
      };

      const result = client.exportArticle(options);

      expect(result.filename).not.toContain('<');
      expect(result.filename).not.toContain('>');
      expect(result.filename).not.toContain('|');
      expect(result.filename).not.toContain('?');
    });

    it('should convert HTML to Markdown', () => {
      const options: ExportToObsidianOptions = {
        article: {
          id: 'html-article',
          title: 'HTML Article',
          content: `
            <h1>Heading</h1>
            <p>Paragraph with <strong>bold</strong> and <em>italic</em>.</p>
            <ul>
              <li>Item 1</li>
              <li>Item 2</li>
            </ul>
          `,
        },
      };

      const result = client.exportArticle(options);

      expect(result.content).toContain('# Heading');
      expect(result.content).toContain('**bold**');
      expect(result.content).toContain('*italic*');
      expect(result.content).toContain('- Item 1');
    });
  });

  describe('exportVault', () => {
    it('should generate multiple files with index', () => {
      const articles: ExportToObsidianOptions[] = [
        {
          article: {
            id: 'article-1',
            title: 'First Article',
            author: 'Author A',
            content: 'Content A',
          },
        },
        {
          article: {
            id: 'article-2',
            title: 'Second Article',
            author: 'Author B',
            content: 'Content B',
          },
        },
      ];

      const files = client.exportVault(articles);

      expect(files.length).toBeGreaterThan(2); // Index + articles
      expect(files.some((f) => f.path.includes('Index'))).toBe(true);
      expect(files[0].content).toContain('WeChat Articles Index');
    });

    it('should group by author in index', () => {
      const articles: ExportToObsidianOptions[] = [
        {
          article: {
            id: 'a1',
            title: 'Article 1',
            author: 'Same Author',
            content: 'Content',
          },
        },
        {
          article: {
            id: 'a2',
            title: 'Article 2',
            author: 'Same Author',
            content: 'Content',
          },
        },
      ];

      const files = client.exportVault(articles);
      const indexFile = files.find((f) => f.path.includes('Index'));

      expect(indexFile?.content).toContain('Same Author');
    });
  });
});
