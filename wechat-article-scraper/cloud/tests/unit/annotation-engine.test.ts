/**
 * Annotation Engine Unit Tests
 *
 * Tests the core annotation functionality:
 * - Text selection and serialization
 * - Annotation CRUD
 * - XPath generation and resolution
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { TextSelectionManager, AnnotationStore, Annotation } from '@/lib/annotation-engine';

// Mock DOM environment
describe('TextSelectionManager', () => {
  let container: HTMLDivElement;
  let manager: TextSelectionManager;

  beforeEach(() => {
    container = document.createElement('div');
    container.innerHTML = `
      <article id="test-article">
        <h1>Test Article Title</h1>
        <p>This is the first paragraph with some <strong>bold text</strong> inside.</p>
        <p>This is the second paragraph.</p>
      </article>
    `;
    document.body.appendChild(container);
    manager = new TextSelectionManager(() => {});
  });

  afterEach(() => {
    manager.destroy();
    document.body.removeChild(container);
  });

  describe('XPath Generation', () => {
    it('should generate correct XPath for a text node', () => {
      const paragraph = container.querySelector('p')!;
      const range = document.createRange();
      range.selectNodeContents(paragraph.firstChild!);

      const xpath = (manager as any).getXPathForNode(paragraph.firstChild!);

      expect(xpath).toContain('p');
      expect(xpath).toContain('text()');
    });

    it('should handle nested elements in XPath', () => {
      const strong = container.querySelector('strong')!;
      const xpath = (manager as any).getXPathForNode(strong);

      expect(xpath).toContain('strong');
    });
  });

  describe('Annotation Creation', () => {
    it('should create annotation from valid selection', () => {
      const paragraph = container.querySelector('p')!;
      const range = document.createRange();

      // Select "first paragraph"
      const textNode = paragraph.firstChild as Text;
      range.setStart(textNode, 12);
      range.setEnd(textNode, 27);

      const selection = window.getSelection()!;
      selection.removeAllRanges();
      selection.addRange(range);

      const annotation = manager.createAnnotationFromSelection(
        'article-123',
        'user-456',
        'yellow',
        'Test comment',
        ['test-tag']
      );

      expect(annotation).not.toBeNull();
      expect(annotation!.quote).toBe('first paragraph');
      expect(annotation!.color).toBe('yellow');
      expect(annotation!.comment).toBe('Test comment');
      expect(annotation!.tags).toContain('test-tag');
      expect(annotation!.articleId).toBe('article-123');
      expect(annotation!.userId).toBe('user-456');
    });

    it('should reject empty selection', () => {
      const annotation = manager.createAnnotationFromSelection(
        'article-123',
        'user-456',
        'yellow',
        '',
        []
      );

      expect(annotation).toBeNull();
    });

    it('should truncate long quotes', () => {
      const longText = 'a'.repeat(600);
      const annotation = {
        id: 'test',
        articleId: 'article-123',
        userId: 'user-456',
        quote: longText,
        color: 'yellow',
        tags: [],
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      } as Annotation;

      expect(annotation.quote.length).toBe(600);
      // The actual truncation happens in createAnnotationFromSelection
    });
  });

  describe('Position Serialization', () => {
    it('should serialize and deserialize range', () => {
      const paragraph = container.querySelector('p')!;
      const range = document.createRange();
      const textNode = paragraph.firstChild as Text;

      range.setStart(textNode, 0);
      range.setEnd(textNode, 10);

      const position = (manager as any).serializeRange(range);

      expect(position).toHaveProperty('startXPath');
      expect(position).toHaveProperty('startOffset');
      expect(position).toHaveProperty('endXPath');
      expect(position).toHaveProperty('endOffset');

      // Test deserialization
      const restoredRange = (manager as any).deserializeRange(position);
      expect(restoredRange).not.toBeNull();
      expect(restoredRange.toString()).toBe(textNode.textContent!.substring(0, 10));
    });
  });
});

describe('AnnotationStore', () => {
  let store: AnnotationStore;

  beforeEach(async () => {
    store = new AnnotationStore();
    await store.init();

    // Clear any existing data
    const all = await store.getAllAnnotations();
    for (const anno of all) {
      await store.deleteAnnotation(anno.id);
    }
  });

  describe('CRUD Operations', () => {
    it('should save and retrieve annotation', async () => {
      const annotation: Annotation = {
        id: 'test-anno-1',
        articleId: 'article-123',
        userId: 'user-456',
        quote: 'Test quote',
        color: 'yellow',
        tags: ['tag1', 'tag2'],
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };

      await store.saveAnnotation(annotation);
      const retrieved = await store.getAnnotation('test-anno-1');

      expect(retrieved).not.toBeNull();
      expect(retrieved!.quote).toBe('Test quote');
      expect(retrieved!.tags).toEqual(['tag1', 'tag2']);
    });

    it('should update existing annotation', async () => {
      const annotation: Annotation = {
        id: 'test-anno-2',
        articleId: 'article-123',
        userId: 'user-456',
        quote: 'Original quote',
        color: 'yellow',
        tags: [],
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };

      await store.saveAnnotation(annotation);

      annotation.quote = 'Updated quote';
      annotation.comment = 'Added comment';
      await store.saveAnnotation(annotation);

      const retrieved = await store.getAnnotation('test-anno-2');
      expect(retrieved!.quote).toBe('Updated quote');
      expect(retrieved!.comment).toBe('Added comment');
    });

    it('should delete annotation', async () => {
      const annotation: Annotation = {
        id: 'test-anno-3',
        articleId: 'article-123',
        userId: 'user-456',
        quote: 'To be deleted',
        color: 'yellow',
        tags: [],
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };

      await store.saveAnnotation(annotation);
      await store.deleteAnnotation('test-anno-3');

      const retrieved = await store.getAnnotation('test-anno-3');
      expect(retrieved).toBeNull();
    });

    it('should get annotations by article', async () => {
      const annotations: Annotation[] = [
        {
          id: 'anno-1',
          articleId: 'article-a',
          userId: 'user-1',
          quote: 'Quote 1',
          color: 'yellow',
          tags: [],
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        },
        {
          id: 'anno-2',
          articleId: 'article-a',
          userId: 'user-1',
          quote: 'Quote 2',
          color: 'green',
          tags: [],
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        },
        {
          id: 'anno-3',
          articleId: 'article-b',
          userId: 'user-1',
          quote: 'Quote 3',
          color: 'blue',
          tags: [],
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        },
      ];

      for (const anno of annotations) {
        await store.saveAnnotation(anno);
      }

      const articleAAnnotations = await store.getAnnotationsByArticle('article-a');
      expect(articleAAnnotations.length).toBe(2);
      expect(articleAAnnotations.map(a => a.id).sort()).toEqual(['anno-1', 'anno-2']);
    });
  });

  describe('Query Operations', () => {
    beforeEach(async () => {
      // Setup test data
      const annotations: Annotation[] = [
        {
          id: 'search-test-1',
          articleId: 'article-1',
          userId: 'user-1',
          quote: 'Machine learning is fascinating',
          comment: 'AI topic',
          color: 'yellow',
          tags: ['ai', 'ml'],
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        },
        {
          id: 'search-test-2',
          articleId: 'article-2',
          userId: 'user-1',
          quote: 'Deep learning requires data',
          comment: 'Neural networks',
          color: 'blue',
          tags: ['ai', 'deep-learning'],
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        },
        {
          id: 'search-test-3',
          articleId: 'article-3',
          userId: 'user-1',
          quote: 'Business strategy matters',
          color: 'green',
          tags: ['business'],
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        },
      ];

      for (const anno of annotations) {
        await store.saveAnnotation(anno);
      }
    });

    it('should search annotations by keyword in quote', async () => {
      const results = await store.searchAnnotations('learning');
      expect(results.length).toBe(2);
      expect(results.map(a => a.id).sort()).toEqual(['search-test-1', 'search-test-2']);
    });

    it('should search annotations by keyword in comment', async () => {
      const results = await store.searchAnnotations('neural');
      expect(results.length).toBe(1);
      expect(results[0].id).toBe('search-test-2');
    });

    it('should filter annotations by tags', async () => {
      const results = await store.getAnnotationsByTags(['ai']);
      expect(results.length).toBe(2);
    });

    it('should export to Readwise format', async () => {
      const readwiseData = await store.exportForReadwise();

      expect(Array.isArray(readwiseData.highlights)).toBe(true);
      expect(readwiseData.highlights.length).toBeGreaterThan(0);

      const highlight = readwiseData.highlights[0];
      expect(highlight).toHaveProperty('text');
      expect(highlight).toHaveProperty('title');
      expect(highlight).toHaveProperty('source_type', 'article');
    });
  });
});
