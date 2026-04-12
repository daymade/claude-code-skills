/**
 * Readwise Client Unit Tests
 * 验证 Readwise API 集成和同步功能
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ReadwiseClient, ReadwiseIntegration, ReadwiseHighlight } from '../../../src/lib/readwise-client';

// Mock fetch
global.fetch = vi.fn();

// Mock Supabase
vi.mock('@supabase/supabase-js', () => ({
  createClient: vi.fn().mockImplementation(() => ({
    from: vi.fn().mockReturnThis(),
    select: vi.fn().mockReturnThis(),
    insert: vi.fn().mockReturnThis(),
    upsert: vi.fn().mockReturnThis(),
    update: vi.fn().mockReturnThis(),
    eq: vi.fn().mockReturnThis(),
    not: vi.fn().mockReturnThis(),
    gt: vi.fn().mockReturnThis(),
    in: vi.fn().mockReturnThis(),
    single: vi.fn().mockResolvedValue({ data: null, error: null }),
  })),
}));

describe('ReadwiseClient', () => {
  const mockToken = 'test-readwise-token';
  let client: ReadwiseClient;

  beforeEach(() => {
    vi.clearAllMocks();
    client = new ReadwiseClient(mockToken);
  });

  describe('constructor', () => {
    it('should initialize with API token', () => {
      expect(client).toBeDefined();
    });

    it('should throw error if token is empty', () => {
      expect(() => new ReadwiseClient('')).toThrow('Readwise API token is required');
    });
  });

  describe('validateToken', () => {
    it('should return true for valid token', async () => {
      (fetch as any).mockResolvedValueOnce({ ok: true });

      const isValid = await client.validateToken();

      expect(isValid).toBe(true);
      expect(fetch).toHaveBeenCalledWith(
        'https://readwise.io/api/v2/auth/',
        expect.objectContaining({
          headers: { Authorization: 'Token test-readwise-token' },
        })
      );
    });

    it('should return false for invalid token', async () => {
      (fetch as any).mockResolvedValueOnce({ ok: false, status: 401 });

      const isValid = await client.validateToken();

      expect(isValid).toBe(false);
    });

    it('should return false on network error', async () => {
      (fetch as any).mockRejectedValueOnce(new Error('Network error'));

      const isValid = await client.validateToken();

      expect(isValid).toBe(false);
    });
  });

  describe('saveHighlights', () => {
    const mockHighlights: ReadwiseHighlight[] = [
      {
        text: 'Test highlight 1',
        title: 'Test Article',
        author: 'Test Author',
        source_type: 'article',
        category: 'articles',
      },
      {
        text: 'Test highlight 2',
        title: 'Test Article',
        author: 'Test Author',
        source_type: 'article',
        category: 'articles',
      },
    ];

    it('should successfully sync highlights', async () => {
      (fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          modified_highlights: [{ id: 1 }, { id: 2 }],
          ignored_highlights: [],
        }),
      });

      const result = await client.saveHighlights(mockHighlights);

      expect(result.success).toBe(true);
      expect(result.syncedCount).toBe(2);
      expect(result.failedCount).toBe(0);
      expect(result.duplicates).toBe(0);
    });

    it('should handle duplicates', async () => {
      (fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          modified_highlights: [{ id: 1 }],
          ignored_highlights: [{ id: 2 }], // Duplicate
        }),
      });

      const result = await client.saveHighlights(mockHighlights);

      expect(result.syncedCount).toBe(1);
      expect(result.duplicates).toBe(1);
    });

    it('should handle API errors', async () => {
      (fetch as any).mockResolvedValueOnce({
        ok: false,
        status: 500,
        text: async () => 'Internal Server Error',
      });

      const result = await client.saveHighlights(mockHighlights);

      expect(result.success).toBe(false);
      expect(result.failedCount).toBe(2);
      expect(result.errors).toHaveLength(1);
    });

    it('should handle rate limiting with retry', async () => {
      (fetch as any)
        .mockResolvedValueOnce({ ok: false, status: 429 }) // Rate limited
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            modified_highlights: [{ id: 1 }, { id: 2 }],
            ignored_highlights: [],
          }),
        });

      const result = await client.saveHighlights(mockHighlights);

      expect(fetch).toHaveBeenCalledTimes(2);
      expect(result.success).toBe(true);
      expect(result.syncedCount).toBe(2);
    });

    it('should batch large numbers of highlights', async () => {
      const manyHighlights = Array(150).fill(null).map((_, i) => ({
        text: `Highlight ${i}`,
        title: 'Test Article',
        source_type: 'article' as const,
      }));

      (fetch as any)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            modified_highlights: Array(100).fill({ id: 1 }),
            ignored_highlights: [],
          }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            modified_highlights: Array(50).fill({ id: 1 }),
            ignored_highlights: [],
          }),
        });

      const result = await client.saveHighlights(manyHighlights);

      expect(fetch).toHaveBeenCalledTimes(2);
      expect(result.syncedCount).toBe(150);
    });
  });

  describe('getBooks', () => {
    it('should fetch books list', async () => {
      const mockBooks = {
        count: 2,
        next: null,
        results: [
          { id: 1, title: 'Book 1', author: 'Author 1' },
          { id: 2, title: 'Book 2', author: 'Author 2' },
        ],
      };

      (fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => mockBooks,
      });

      const result = await client.getBooks();

      expect(result.count).toBe(2);
      expect(result.results).toHaveLength(2);
    });

    it('should support updatedAfter filter', async () => {
      (fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ count: 0, next: null, results: [] }),
      });

      await client.getBooks('2024-01-01T00:00:00Z');

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('updatedAfter=2024-01-01T00%3A00%3A00Z'),
        expect.any(Object)
      );
    });
  });

  describe('getHighlights', () => {
    it('should fetch highlights for a book', async () => {
      (fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          count: 3,
          results: [{ id: 1, text: 'Highlight 1' }],
        }),
      });

      const result = await client.getHighlights(123);

      expect(result.count).toBe(3);
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('book_id=123'),
        expect.any(Object)
      );
    });
  });

  describe('exportAll', () => {
    it('should export all data', async () => {
      (fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          count: 10,
          next: null,
          results: [],
        }),
      });

      const result = await client.exportAll();

      expect(result.count).toBe(10);
    });
  });
});

describe('ReadwiseIntegration', () => {
  const mockSupabaseUrl = 'https://test.supabase.co';
  const mockSupabaseKey = 'test-key';
  let integration: ReadwiseIntegration;

  beforeEach(() => {
    vi.clearAllMocks();
    integration = new ReadwiseIntegration(mockSupabaseUrl, mockSupabaseKey);
  });

  describe('saveToken', () => {
    it('should save valid token', async () => {
      (fetch as any).mockResolvedValueOnce({ ok: true }); // validateToken

      const { createClient } = await import('@supabase/supabase-js');
      const mockSupabase = vi.mocked(createClient);
      mockSupabase.mockImplementation(() => ({
        from: vi.fn().mockReturnThis(),
        upsert: vi.fn().mockResolvedValue({ error: null }),
      } as any));

      integration = new ReadwiseIntegration(mockSupabaseUrl, mockSupabaseKey);
      const result = await integration.saveToken('user-1', 'valid-token');

      expect(result.success).toBe(true);
    });

    it('should reject invalid token', async () => {
      (fetch as any).mockResolvedValueOnce({ ok: false, status: 401 });

      const result = await integration.saveToken('user-1', 'invalid-token');

      expect(result.success).toBe(false);
      expect(result.error).toContain('Invalid');
    });
  });

  describe('getToken', () => {
    it('should return token if exists', async () => {
      const { createClient } = await import('@supabase/supabase-js');
      const mockSupabase = vi.mocked(createClient);
      mockSupabase.mockImplementation(() => ({
        from: vi.fn().mockReturnThis(),
        select: vi.fn().mockReturnThis(),
        eq: vi.fn().mockReturnThis(),
        single: vi.fn().mockResolvedValue({
          data: { access_token: Buffer.from('my-token').toString('base64') },
          error: null,
        }),
      } as any));

      integration = new ReadwiseIntegration(mockSupabaseUrl, mockSupabaseKey);
      const token = await integration.getToken('user-1');

      expect(token).toBe('my-token');
    });

    it('should return null if no token', async () => {
      const { createClient } = await import('@supabase/supabase-js');
      const mockSupabase = vi.mocked(createClient);
      mockSupabase.mockImplementation(() => ({
        from: vi.fn().mockReturnThis(),
        select: vi.fn().mockReturnThis(),
        eq: vi.fn().mockReturnThis(),
        single: vi.fn().mockResolvedValue({ data: null, error: { message: 'Not found' } }),
      } as any));

      integration = new ReadwiseIntegration(mockSupabaseUrl, mockSupabaseKey);
      const token = await integration.getToken('user-1');

      expect(token).toBeNull();
    });
  });

  describe('syncHighlights', () => {
    it('should return error if not connected', async () => {
      const { createClient } = await import('@supabase/supabase-js');
      const mockSupabase = vi.mocked(createClient);
      mockSupabase.mockImplementation(() => ({
        from: vi.fn().mockReturnThis(),
        select: vi.fn().mockReturnThis(),
        eq: vi.fn().mockReturnThis(),
        single: vi.fn().mockResolvedValue({ data: null, error: null }),
      } as any));

      integration = new ReadwiseIntegration(mockSupabaseUrl, mockSupabaseKey);
      const result = await integration.syncHighlights('user-1');

      expect(result.success).toBe(false);
      expect(result.errors[0]).toContain('not connected');
    });

    it('should sync highlights successfully', async () => {
      const mockAnnotations = [
        {
          id: 'anno-1',
          quote: 'Test quote',
          comment: 'Test note',
          created_at: '2024-01-01T00:00:00Z',
          article_id: 'article-1',
          article: { title: 'Test Article', author: 'Author', url: 'https://test.com' },
        },
      ];

      const { createClient } = await import('@supabase/supabase-js');
      const mockSupabase = vi.mocked(createClient);

      mockSupabase.mockImplementation(() => ({
        from: vi.fn().mockImplementation((table: string) => ({
          select: vi.fn().mockReturnThis(),
          insert: vi.fn().mockReturnThis(),
          upsert: vi.fn().mockResolvedValue({ error: null }),
          update: vi.fn().mockReturnThis(),
          eq: vi.fn().mockReturnThis(),
          not: vi.fn().mockReturnThis(),
          gt: vi.fn().mockReturnThis(),
          in: vi.fn().mockResolvedValue({ error: null }),
          single: vi.fn().mockResolvedValue({
            data: { access_token: Buffer.from('valid-token').toString('base64') },
            error: null,
          }),
        })),
      } as any));

      (fetch as any)
        .mockResolvedValueOnce({ ok: true }) // validateToken in saveToken
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            modified_highlights: [{ id: 1 }],
            ignored_highlights: [],
          }),
        });

      integration = new ReadwiseIntegration(mockSupabaseUrl, mockSupabaseKey);
      // First save token
      await integration.saveToken('user-1', 'valid-token');
      // Then sync
      const result = await integration.syncHighlights('user-1');

      expect(result.success).toBe(true);
    });
  });
});
