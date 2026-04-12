/**
 * Inbox Engine Unit Tests
 * Tests inbox management, AI analysis, and recommendations
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { InboxEngine, InboxItem, InboxFilters, InboxStatus } from '../../../src/lib/inbox-engine';

// Mock Supabase
vi.mock('@supabase/supabase-js', () => ({
  createClient: vi.fn().mockImplementation(() => ({
    from: vi.fn().mockReturnThis(),
    select: vi.fn().mockReturnThis(),
    insert: vi.fn().mockReturnThis(),
    update: vi.fn().mockReturnThis(),
    delete: vi.fn().mockReturnThis(),
    eq: vi.fn().mockReturnThis(),
    in: vi.fn().mockReturnThis(),
    contains: vi.fn().mockReturnThis(),
    gte: vi.fn().mockReturnThis(),
    lte: vi.fn().mockReturnThis(),
    or: vi.fn().mockReturnThis(),
    order: vi.fn().mockReturnThis(),
    limit: vi.fn().mockReturnThis(),
    range: vi.fn().mockReturnThis(),
  })),
}));

describe('InboxEngine', () => {
  let engine: InboxEngine;
  const mockSupabaseUrl = 'https://test.supabase.co';
  const mockSupabaseKey = 'test-key';

  beforeEach(() => {
    vi.clearAllMocks();
    engine = new InboxEngine(mockSupabaseUrl, mockSupabaseKey);
  });

  describe('constructor', () => {
    it('should initialize with Supabase credentials', () => {
      expect(engine).toBeDefined();
    });
  });

  describe('addToInbox', () => {
    const mockArticle = {
      title: 'Test Article',
      content: 'This is test content about AI and machine learning. It discusses productivity and startup tips.',
      wordCount: 500,
    };

    it('should add article to inbox with AI analysis', async () => {
      const mockItem: Partial<InboxItem> = {
        articleId: 'article-1',
        userId: 'user-1',
        status: 'inbox',
        priority: 'low',
        contentType: 'article',
        estimatedReadTime: 3,
        complexity: 'easy',
        score: 50,
      };

      const { createClient } = await import('@supabase/supabase-js');
      const mockSupabase = vi.mocked(createClient);
      mockSupabase.mockImplementation(() => ({
        from: vi.fn().mockReturnThis(),
        insert: vi.fn().mockReturnThis(),
        select: vi.fn().mockReturnThis(),
        single: vi.fn().mockResolvedValue({ data: mockItem, error: null }),
      } as any));

      engine = new InboxEngine(mockSupabaseUrl, mockSupabaseKey);
      const result = await engine.addToInbox('article-1', 'user-1', mockArticle);

      expect(result).toBeDefined();
      expect(result.status).toBe('inbox');
    });
  });

  describe('getInboxItems', () => {
    const mockItems: InboxItem[] = [
      {
        id: '1',
        articleId: 'article-1',
        userId: 'user-1',
        status: 'inbox',
        priority: 'high',
        contentType: 'article',
        suggestedTags: ['AI', 'productivity'],
        suggestedFolder: 'Articles',
        estimatedReadTime: 10,
        complexity: 'medium',
        keyTopics: ['AI', 'machine learning'],
        addedAt: '2024-01-01T00:00:00Z',
        score: 75,
      },
      {
        id: '2',
        articleId: 'article-2',
        userId: 'user-1',
        status: 'reading',
        priority: 'medium',
        contentType: 'newsletter',
        suggestedTags: ['startup'],
        suggestedFolder: 'Newsletters',
        estimatedReadTime: 5,
        complexity: 'easy',
        keyTopics: ['startup'],
        addedAt: '2024-01-02T00:00:00Z',
        startedReadingAt: '2024-01-02T01:00:00Z',
        score: 60,
      },
    ];

    it('should fetch inbox items with default options', async () => {
      const { createClient } = await import('@supabase/supabase-js');
      const mockSupabase = vi.mocked(createClient);
      mockSupabase.mockImplementation(() => ({
        from: vi.fn().mockReturnThis(),
        select: vi.fn().mockReturnThis(),
        eq: vi.fn().mockReturnThis(),
        order: vi.fn().mockReturnThis(),
        limit: vi.fn().mockResolvedValue({
          data: mockItems,
          error: null,
          count: mockItems.length
        }),
      } as any));

      engine = new InboxEngine(mockSupabaseUrl, mockSupabaseKey);
      const result = await engine.getInboxItems('user-1');

      expect(result.items).toHaveLength(2);
      expect(result.total).toBe(2);
    });

    it('should filter by status', async () => {
      const { createClient } = await import('@supabase/supabase-js');
      const inMock = vi.fn().mockReturnThis();
      const mockSupabase = vi.mocked(createClient);

      mockSupabase.mockImplementation(() => ({
        from: vi.fn().mockReturnThis(),
        select: vi.fn().mockReturnThis(),
        eq: vi.fn().mockReturnThis(),
        in: inMock,
        order: vi.fn().mockReturnThis(),
        limit: vi.fn().mockResolvedValue({
          data: [mockItems[0]],
          error: null,
          count: 1
        }),
      } as any));

      engine = new InboxEngine(mockSupabaseUrl, mockSupabaseKey);
      const filters: InboxFilters = { status: ['inbox'] };
      await engine.getInboxItems('user-1', filters);

      expect(inMock).toHaveBeenCalledWith('status', ['inbox']);
    });

    it('should filter by priority', async () => {
      const { createClient } = await import('@supabase/supabase-js');
      const inMock = vi.fn().mockResolvedValue({
        data: [mockItems[0]],
        error: null,
        count: 1
      });

      mockSupabase.mockImplementation(() => ({
        from: vi.fn().mockReturnThis(),
        select: vi.fn().mockReturnThis(),
        eq: vi.fn().mockReturnThis(),
        in: inMock,
      } as any));

      engine = new InboxEngine(mockSupabaseUrl, mockSupabaseKey);
      const filters: InboxFilters = { priority: ['high'] };
      await engine.getInboxItems('user-1', filters);
    });

    it('should filter by read time range', async () => {
      const { createClient } = await import('@supabase/supabase-js');
      const gteMock = vi.fn().mockReturnThis();
      const lteMock = vi.fn().mockResolvedValue({
        data: mockItems,
        error: null,
        count: 2
      });

      mockSupabase.mockImplementation(() => ({
        from: vi.fn().mockReturnThis(),
        select: vi.fn().mockReturnThis(),
        eq: vi.fn().mockReturnThis(),
        gte: gteMock,
        lte: lteMock,
      } as any));

      engine = new InboxEngine(mockSupabaseUrl, mockSupabaseKey);
      const filters: InboxFilters = { minReadTime: 5, maxReadTime: 15 };
      await engine.getInboxItems('user-1', filters);

      expect(gteMock).toHaveBeenCalledWith('estimated_read_time', 5);
      expect(lteMock).toHaveBeenCalledWith('estimated_read_time', 15);
    });

    it('should handle pagination', async () => {
      const { createClient } = await import('@supabase/supabase-js');
      const rangeMock = vi.fn().mockResolvedValue({
        data: mockItems,
        error: null,
        count: 10
      });

      mockSupabase.mockImplementation(() => ({
        from: vi.fn().mockReturnThis(),
        select: vi.fn().mockReturnThis(),
        eq: vi.fn().mockReturnThis(),
        order: vi.fn().mockReturnThis(),
        limit: vi.fn().mockReturnThis(),
        range: rangeMock,
      } as any));

      engine = new InboxEngine(mockSupabaseUrl, mockSupabaseKey);
      await engine.getInboxItems('user-1', {}, { limit: 10, offset: 20 });

      expect(rangeMock).toHaveBeenCalledWith(20, 29);
    });
  });

  describe('updateStatus', () => {
    it('should update item status to reading', async () => {
      const { createClient } = await import('@supabase/supabase-js');
      const updateMock = vi.fn().mockReturnThis();
      const eqMock = vi.fn().mockResolvedValue({ error: null });

      mockSupabase.mockImplementation(() => ({
        from: vi.fn().mockReturnThis(),
        update: updateMock,
        eq: eqMock,
      } as any));

      engine = new InboxEngine(mockSupabaseUrl, mockSupabaseKey);
      await engine.updateStatus('item-1', 'reading', 'user-1');

      expect(updateMock).toHaveBeenCalledWith(
        expect.objectContaining({
          status: 'reading',
          startedReadingAt: expect.any(String),
        })
      );
    });

    it('should update item status to archived', async () => {
      const { createClient } = await import('@supabase/supabase-js');
      const updateMock = vi.fn().mockReturnThis();

      mockSupabase.mockImplementation(() => ({
        from: vi.fn().mockReturnThis(),
        update: updateMock,
        eq: vi.fn().mockResolvedValue({ error: null }),
      } as any));

      engine = new InboxEngine(mockSupabaseUrl, mockSupabaseKey);
      await engine.updateStatus('item-1', 'archived', 'user-1');

      expect(updateMock).toHaveBeenCalledWith(
        expect.objectContaining({
          status: 'archived',
          finishedReadingAt: expect.any(String),
        })
      );
    });
  });

  describe('getInboxStats', () => {
    const mockItems: InboxItem[] = [
      {
        id: '1',
        articleId: 'article-1',
        userId: 'user-1',
        status: 'inbox',
        priority: 'high',
        contentType: 'article',
        suggestedTags: [],
        suggestedFolder: '',
        estimatedReadTime: 10,
        complexity: 'medium',
        keyTopics: [],
        addedAt: '2024-01-01T00:00:00Z',
        score: 75,
      },
      {
        id: '2',
        articleId: 'article-2',
        userId: 'user-1',
        status: 'archived',
        priority: 'medium',
        contentType: 'newsletter',
        suggestedTags: [],
        suggestedFolder: '',
        estimatedReadTime: 5,
        complexity: 'easy',
        keyTopics: [],
        addedAt: '2024-01-02T00:00:00Z',
        score: 60,
      },
    ];

    it('should calculate inbox statistics', async () => {
      const { createClient } = await import('@supabase/supabase-js');
      mockSupabase.mockImplementation(() => ({
        from: vi.fn().mockReturnThis(),
        select: vi.fn().mockReturnThis(),
        eq: vi.fn().mockResolvedValue({ data: mockItems, error: null }),
      } as any));

      engine = new InboxEngine(mockSupabaseUrl, mockSupabaseKey);
      const stats = await engine.getInboxStats('user-1');

      expect(stats.total).toBe(2);
      expect(stats.byStatus.inbox).toBe(1);
      expect(stats.byStatus.archived).toBe(1);
      expect(stats.byPriority.high).toBe(1);
      expect(stats.byPriority.medium).toBe(1);
      expect(stats.estimatedTotalReadTime).toBe(15);
      expect(stats.averageReadTime).toBe(7);
      expect(stats.unreadCount).toBe(1);
    });
  });

  describe('getRecommendations', () => {
    const mockItems: InboxItem[] = [
      {
        id: '1',
        articleId: 'article-1',
        userId: 'user-1',
        status: 'inbox',
        priority: 'high',
        contentType: 'article',
        suggestedTags: [],
        suggestedFolder: '',
        estimatedReadTime: 10,
        complexity: 'medium',
        keyTopics: [],
        addedAt: '2024-01-01T00:00:00Z',
        score: 75,
      },
      {
        id: '2',
        articleId: 'article-2',
        userId: 'user-1',
        status: 'inbox',
        priority: 'medium',
        contentType: 'article',
        suggestedTags: [],
        suggestedFolder: '',
        estimatedReadTime: 5,
        complexity: 'easy',
        keyTopics: [],
        addedAt: '2024-01-02T00:00:00Z',
        score: 60,
      },
    ];

    it('should recommend articles that fit available time', async () => {
      const { createClient } = await import('@supabase/supabase-js');
      mockSupabase.mockImplementation(() => ({
        from: vi.fn().mockReturnThis(),
        select: vi.fn().mockReturnThis(),
        eq: vi.fn().mockReturnThis(),
        in: vi.fn().mockReturnThis(),
        lte: vi.fn().mockReturnThis(),
        order: vi.fn().mockReturnThis(),
        limit: vi.fn().mockResolvedValue({
          data: mockItems,
          error: null,
          count: 2
        }),
      } as any));

      engine = new InboxEngine(mockSupabaseUrl, mockSupabaseKey);
      const recommendations = await engine.getRecommendations('user-1', 15, 2);

      expect(recommendations).toHaveLength(2);
      // Should prioritize articles that fit well within time
      expect(recommendations[0].estimatedReadTime).toBeLessThanOrEqual(15);
    });
  });

  describe('applyTags', () => {
    it('should apply user tags to item', async () => {
      const { createClient } = await import('@supabase/supabase-js');
      const updateMock = vi.fn().mockReturnThis();

      mockSupabase.mockImplementation(() => ({
        from: vi.fn().mockReturnThis(),
        update: updateMock,
        eq: vi.fn().mockResolvedValue({ error: null }),
      } as any));

      engine = new InboxEngine(mockSupabaseUrl, mockSupabaseKey);
      await engine.applyTags('item-1', 'user-1', ['AI', 'important']);

      expect(updateMock).toHaveBeenCalledWith({
        user_applied_tags: ['AI', 'important'],
      });
    });
  });
});
