/**
 * Export Service Unit Tests
 * Tests export functionality to various destinations
 */

import { describe, it, expect, vi, beforeEach, Mock } from 'vitest';
import { ExportService, ExportOptions, ExportFormat } from '../../../src/lib/export-service';

// Mock dependencies
vi.mock('../../../src/lib/notion-client', () => ({
  NotionClient: vi.fn().mockImplementation(() => ({
    setupDatabase: vi.fn().mockResolvedValue('test-database-id'),
    exportArticle: vi.fn().mockResolvedValue('test-page-id'),
  })),
}));

vi.mock('../../../src/lib/obsidian-client', () => ({
  ObsidianClient: vi.fn().mockImplementation(() => ({
    exportVault: vi.fn().mockReturnValue([
      { path: 'test.md', content: '# Test' },
    ]),
  })),
}));

vi.mock('../../../src/lib/webhook-service', () => ({
  WebhookService: vi.fn().mockImplementation(() => ({
    trigger: vi.fn().mockResolvedValue(undefined),
  })),
}));

vi.mock('@supabase/supabase-js', () => ({
  createClient: vi.fn().mockImplementation(() => ({
    from: vi.fn().mockReturnThis(),
    select: vi.fn().mockReturnThis(),
    insert: vi.fn().mockReturnThis(),
    update: vi.fn().mockReturnThis(),
    eq: vi.fn().mockReturnThis(),
    in: vi.fn().mockReturnThis(),
    gte: vi.fn().mockReturnThis(),
    lte: vi.fn().mockReturnThis(),
    contains: vi.fn().mockReturnThis(),
    storage: {
      from: vi.fn().mockReturnThis(),
      upload: vi.fn().mockResolvedValue({ data: { path: 'test/path' }, error: null }),
      createSignedUrl: vi.fn().mockResolvedValue({ data: { signedUrl: 'https://test.com/file' }, error: null }),
    },
  })),
}));

describe('ExportService', () => {
  let service: ExportService;
  const mockSupabaseUrl = 'https://test.supabase.co';
  const mockSupabaseKey = 'test-key';

  beforeEach(() => {
    vi.clearAllMocks();
    service = new ExportService(mockSupabaseUrl, mockSupabaseKey);
  });

  describe('constructor', () => {
    it('should initialize with Supabase credentials', () => {
      expect(service).toBeDefined();
    });

    it('should initialize Notion client when token provided', () => {
      const serviceWithNotion = new ExportService(
        mockSupabaseUrl,
        mockSupabaseKey,
        { notionToken: 'test-notion-token' }
      );
      expect(serviceWithNotion).toBeDefined();
    });

    it('should initialize Obsidian client when config provided', () => {
      const serviceWithObsidian = new ExportService(
        mockSupabaseUrl,
        mockSupabaseKey,
        {
          obsidianConfig: {
            apiUrl: 'http://localhost:27123',
            apiToken: 'test-token',
          },
        }
      );
      expect(serviceWithObsidian).toBeDefined();
    });
  });

  describe('export', () => {
    const mockArticles = [
      {
        id: '1',
        title: 'Test Article',
        author: 'Test Author',
        content: '<p>Test content</p>',
        url: 'https://example.com/article',
        publish_time: '2024-01-01T00:00:00Z',
        created_at: '2024-01-01T00:00:00Z',
        tags: ['test'],
        annotations: [
          {
            id: 'a1',
            quote: 'Test highlight',
            comment: 'Test note',
            color: 'yellow',
            created_at: '2024-01-01T00:00:00Z',
          },
        ],
      },
    ];

    beforeEach(() => {
      const mockSupabase = vi.mocked((await import('@supabase/supabase-js')).createClient);
      mockSupabase.mockImplementation(() => ({
        from: vi.fn().mockReturnThis(),
        select: vi.fn().mockResolvedValue({ data: mockArticles, error: null }),
        insert: vi.fn().mockReturnThis(),
        update: vi.fn().mockReturnThis(),
        eq: vi.fn().mockResolvedValue({ data: mockArticles, error: null }),
        in: vi.fn().mockReturnThis(),
        gte: vi.fn().mockReturnThis(),
        lte: vi.fn().mockReturnThis(),
        contains: vi.fn().mockReturnThis(),
        storage: {
          from: vi.fn().mockReturnThis(),
          upload: vi.fn().mockResolvedValue({ data: { path: 'test/path' }, error: null }),
          createSignedUrl: vi.fn().mockResolvedValue({ data: { signedUrl: 'https://test.com/file.zip' }, error: null }),
        },
      } as any));
    });

    it('should return error when no articles found', async () => {
      const mockSupabase = vi.mocked((await import('@supabase/supabase-js')).createClient);
      mockSupabase.mockImplementation(() => ({
        from: vi.fn().mockReturnThis(),
        select: vi.fn().mockResolvedValue({ data: [], error: null }),
        eq: vi.fn().mockReturnThis(),
        storage: {
          from: vi.fn().mockReturnThis(),
          upload: vi.fn().mockResolvedValue({ data: null, error: null }),
          createSignedUrl: vi.fn().mockResolvedValue({ data: null, error: null }),
        },
      } as any));

      service = new ExportService(mockSupabaseUrl, mockSupabaseKey);
      const result = await service.export('user1', {
        format: 'markdown',
        articleIds: ['non-existent'],
      });

      expect(result.success).toBe(false);
      expect(result.error).toContain('No articles found');
    });

    it('should export to markdown format', async () => {
      const mockSupabase = vi.mocked((await import('@supabase/supabase-js')).createClient);
      mockSupabase.mockImplementation(() => ({
        from: vi.fn().mockReturnThis(),
        select: vi.fn().mockResolvedValue({ data: mockArticles, error: null }),
        eq: vi.fn().mockReturnThis(),
        storage: {
          from: vi.fn().mockReturnThis(),
          upload: vi.fn().mockResolvedValue({ data: { path: 'test/path' }, error: null }),
          createSignedUrl: vi.fn().mockResolvedValue({ data: { signedUrl: 'https://test.com/file.md' }, error: null }),
        },
      } as any));

      service = new ExportService(mockSupabaseUrl, mockSupabaseKey);
      const result = await service.export('user1', {
        format: 'markdown',
        articleIds: ['1'],
      });

      expect(result.success).toBe(true);
      expect(result.url).toBeDefined();
    });

    it('should export to JSON format', async () => {
      const mockSupabase = vi.mocked((await import('@supabase/supabase-js')).createClient);
      mockSupabase.mockImplementation(() => ({
        from: vi.fn().mockReturnThis(),
        select: vi.fn().mockResolvedValue({ data: mockArticles, error: null }),
        eq: vi.fn().mockReturnThis(),
        storage: {
          from: vi.fn().mockReturnThis(),
          upload: vi.fn().mockResolvedValue({ data: { path: 'test/path' }, error: null }),
          createSignedUrl: vi.fn().mockResolvedValue({ data: { signedUrl: 'https://test.com/file.json' }, error: null }),
        },
      } as any));

      service = new ExportService(mockSupabaseUrl, mockSupabaseKey);
      const result = await service.export('user1', {
        format: 'json',
        articleIds: ['1'],
      });

      expect(result.success).toBe(true);
    });

    it('should export to HTML format', async () => {
      const mockSupabase = vi.mocked((await import('@supabase/supabase-js')).createClient);
      mockSupabase.mockImplementation(() => ({
        from: vi.fn().mockReturnThis(),
        select: vi.fn().mockResolvedValue({ data: mockArticles, error: null }),
        eq: vi.fn().mockReturnThis(),
        storage: {
          from: vi.fn().mockReturnThis(),
          upload: vi.fn().mockResolvedValue({ data: { path: 'test/path' }, error: null }),
          createSignedUrl: vi.fn().mockResolvedValue({ data: { signedUrl: 'https://test.com/file.html' }, error: null }),
        },
      } as any));

      service = new ExportService(mockSupabaseUrl, mockSupabaseKey);
      const result = await service.export('user1', {
        format: 'html',
        articleIds: ['1'],
      });

      expect(result.success).toBe(true);
    });

    it('should return error for unsupported format', async () => {
      const mockSupabase = vi.mocked((await import('@supabase/supabase-js')).createClient);
      mockSupabase.mockImplementation(() => ({
        from: vi.fn().mockReturnThis(),
        select: vi.fn().mockResolvedValue({ data: mockArticles, error: null }),
        eq: vi.fn().mockReturnThis(),
        storage: {
          from: vi.fn().mockReturnThis(),
          upload: vi.fn().mockResolvedValue({ data: null, error: null }),
          createSignedUrl: vi.fn().mockResolvedValue({ data: null, error: null }),
        },
      } as any));

      service = new ExportService(mockSupabaseUrl, mockSupabaseKey);
      const result = await service.export('user1', {
        format: 'pdf' as ExportFormat,
        articleIds: ['1'],
      });

      // PDF is not yet implemented
      expect(result.success).toBe(false);
      expect(result.error).toContain('Unsupported format');
    });

    it('should include annotations when requested', async () => {
      const mockSupabase = vi.mocked((await import('@supabase/supabase-js')).createClient);
      mockSupabase.mockImplementation(() => ({
        from: vi.fn().mockReturnThis(),
        select: vi.fn().mockResolvedValue({ data: mockArticles, error: null }),
        eq: vi.fn().mockReturnThis(),
        storage: {
          from: vi.fn().mockReturnThis(),
          upload: vi.fn().mockResolvedValue({ data: { path: 'test/path' }, error: null }),
          createSignedUrl: vi.fn().mockResolvedValue({ data: { signedUrl: 'https://test.com/file.md' }, error: null }),
        },
      } as any));

      service = new ExportService(mockSupabaseUrl, mockSupabaseKey);
      const result = await service.export('user1', {
        format: 'markdown',
        articleIds: ['1'],
        includeAnnotations: true,
      });

      expect(result.success).toBe(true);
    });

    it('should filter by date range', async () => {
      const mockSupabase = vi.mocked((await import('@supabase/supabase-js')).createClient);
      const gteMock = vi.fn().mockReturnThis();
      const lteMock = vi.fn().mockResolvedValue({ data: mockArticles, error: null });

      mockSupabase.mockImplementation(() => ({
        from: vi.fn().mockReturnThis(),
        select: vi.fn().mockReturnThis(),
        eq: vi.fn().mockReturnThis(),
        gte: gteMock,
        lte: lteMock,
        storage: {
          from: vi.fn().mockReturnThis(),
          upload: vi.fn().mockResolvedValue({ data: { path: 'test/path' }, error: null }),
          createSignedUrl: vi.fn().mockResolvedValue({ data: { signedUrl: 'https://test.com/file.md' }, error: null }),
        },
      } as any));

      service = new ExportService(mockSupabaseUrl, mockSupabaseKey);
      await service.export('user1', {
        format: 'markdown',
        dateRange: {
          start: '2024-01-01T00:00:00Z',
          end: '2024-12-31T23:59:59Z',
        },
      });

      expect(gteMock).toHaveBeenCalledWith('created_at', '2024-01-01T00:00:00Z');
      expect(lteMock).toHaveBeenCalledWith('created_at', '2024-12-31T23:59:59Z');
    });

    it('should filter by tags', async () => {
      const mockSupabase = vi.mocked((await import('@supabase/supabase-js')).createClient);
      const containsMock = vi.fn().mockResolvedValue({ data: mockArticles, error: null });

      mockSupabase.mockImplementation(() => ({
        from: vi.fn().mockReturnThis(),
        select: vi.fn().mockReturnThis(),
        eq: vi.fn().mockReturnThis(),
        contains: containsMock,
        storage: {
          from: vi.fn().mockReturnThis(),
          upload: vi.fn().mockResolvedValue({ data: { path: 'test/path' }, error: null }),
          createSignedUrl: vi.fn().mockResolvedValue({ data: { signedUrl: 'https://test.com/file.md' }, error: null }),
        },
      } as any));

      service = new ExportService(mockSupabaseUrl, mockSupabaseKey);
      await service.export('user1', {
        format: 'markdown',
        tags: ['test', 'important'],
      });

      expect(containsMock).toHaveBeenCalledWith('tags', ['test', 'important']);
    });
  });

  describe('exportToNotion', () => {
    it('should return error if Notion client not configured', async () => {
      const result = await service.export('user1', {
        format: 'notion',
        articleIds: ['1'],
      });

      expect(result.success).toBe(false);
      expect(result.error).toContain('Notion client not configured');
    });
  });

  describe('exportToObsidian', () => {
    it('should return error if Obsidian client not configured', async () => {
      const result = await service.export('user1', {
        format: 'obsidian',
        articleIds: ['1'],
      });

      expect(result.success).toBe(false);
      expect(result.error).toContain('Obsidian client not configured');
    });
  });

  describe('getExportJobStatus', () => {
    it('should fetch job status', async () => {
      const mockJob = {
        id: 'job-1',
        status: 'completed',
        format: 'markdown',
        file_url: 'https://test.com/file.md',
      };

      const mockSupabase = vi.mocked((await import('@supabase/supabase-js')).createClient);
      mockSupabase.mockImplementation(() => ({
        from: vi.fn().mockReturnThis(),
        select: vi.fn().mockReturnThis(),
        eq: vi.fn().mockResolvedValue({ data: mockJob, error: null }),
      } as any));

      service = new ExportService(mockSupabaseUrl, mockSupabaseKey);
      const result = await service.getExportJobStatus('job-1');

      expect(result).toEqual(mockJob);
    });
  });
});
