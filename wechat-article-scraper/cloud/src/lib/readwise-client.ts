/**
 * Readwise API Client
 * 官方 API 文档: https://readwise.io/api_deets
 *
 * 功能:
 * - 用户级 API Token 管理
 * - 高亮同步 (带重试和去重)
 * - 增量同步 (避免重复上传)
 * - Rate limiting 处理
 * - 同步状态追踪
 */

import { createClient, SupabaseClient } from '@supabase/supabase-js';

// Readwise API 配置
const READWISE_API_BASE = 'https://readwise.io/api/v2';
const BATCH_SIZE = 100; // Readwise 单次最大批量
const RATE_LIMIT_DELAY = 1000; // ms

export interface ReadwiseHighlight {
  text: string;
  title?: string;
  author?: string;
  source_type: 'article' | 'book' | 'podcast' | 'tweet' | 'email';
  category?: 'articles' | 'books' | 'podcasts' | 'tweets' | 'emails';
  note?: string;
  highlighted_at?: string;
  highlight_url?: string;
  image_url?: string;
}

export interface ReadwiseSyncResult {
  success: boolean;
  syncedCount: number;
  failedCount: number;
  duplicates: number;
  errors: string[];
}

export interface ReadwiseBook {
  id: number;
  title: string;
  author: string;
  category: string;
  source: string;
  num_highlights: number;
  last_highlight_at: string;
  updated: string;
  cover_image_url: string;
  highlights_url: string;
  source_url: string;
}

export interface ReadwiseExport {
  count: number;
  next: string | null;
  results: ReadwiseBook[];
}

/**
 * Readwise API Client
 */
export class ReadwiseClient {
  private apiToken: string;

  constructor(apiToken: string) {
    if (!apiToken) {
      throw new Error('Readwise API token is required');
    }
    this.apiToken = apiToken;
  }

  /**
   * 验证 API Token 是否有效
   */
  async validateToken(): Promise<boolean> {
    try {
      const response = await fetch(`${READWISE_API_BASE}/auth/`, {
        headers: {
          'Authorization': `Token ${this.apiToken}`,
        },
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  /**
   * 批量上传高亮
   * 遵循 Readwise API 限制：单次最多 100 条
   */
  async saveHighlights(highlights: ReadwiseHighlight[]): Promise<ReadwiseSyncResult> {
    const result: ReadwiseSyncResult = {
      success: true,
      syncedCount: 0,
      failedCount: 0,
      duplicates: 0,
      errors: [],
    };

    // 分批处理
    for (let i = 0; i < highlights.length; i += BATCH_SIZE) {
      const batch = highlights.slice(i, i + BATCH_SIZE);

      try {
        const response = await fetch(`${READWISE_API_BASE}/highlights/`, {
          method: 'POST',
          headers: {
            'Authorization': `Token ${this.apiToken}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ highlights: batch }),
        });

        if (response.status === 429) {
          // Rate limited, wait and retry
          await this.delay(RATE_LIMIT_DELAY);
          i -= BATCH_SIZE; // Retry this batch
          continue;
        }

        if (!response.ok) {
          const error = await response.text();
          throw new Error(`Readwise API error: ${response.status} - ${error}`);
        }

        const data = await response.json();

        // 统计结果
        if (data.modified_highlights) {
          result.syncedCount += data.modified_highlights.length;
        }
        if (data.ignored_highlights) {
          result.duplicates += data.ignored_highlights.length;
        }

      } catch (error) {
        result.failedCount += batch.length;
        result.errors.push(error instanceof Error ? error.message : 'Unknown error');
        result.success = false;
      }

      // Rate limiting delay between batches
      if (i + BATCH_SIZE < highlights.length) {
        await this.delay(RATE_LIMIT_DELAY);
      }
    }

    return result;
  }

  /**
   * 获取已同步的书籍/文章列表
   * 用于增量同步
   */
  async getBooks(updatedAfter?: string): Promise<ReadwiseExport> {
    const params = new URLSearchParams();
    if (updatedAfter) {
      params.append('updatedAfter', updatedAfter);
    }

    const response = await fetch(
      `${READWISE_API_BASE}/books/?${params.toString()}`,
      {
        headers: {
          'Authorization': `Token ${this.apiToken}`,
        },
      }
    );

    if (!response.ok) {
      throw new Error(`Failed to fetch books: ${response.status}`);
    }

    return response.json();
  }

  /**
   * 获取特定书籍的所有高亮
   */
  async getHighlights(
    bookId: number,
    updatedAfter?: string
  ): Promise<{ count: number; results: any[] }> {
    const params = new URLSearchParams();
    params.append('book_id', bookId.toString());
    if (updatedAfter) {
      params.append('updatedAfter', updatedAfter);
    }

    const response = await fetch(
      `${READWISE_API_BASE}/highlights/?${params.toString()}`,
      {
        headers: {
          'Authorization': `Token ${this.apiToken}`,
        },
      }
    );

    if (!response.ok) {
      throw new Error(`Failed to fetch highlights: ${response.status}`);
    }

    return response.json();
  }

  /**
   * 导出所有数据 (Readwise 官方导出功能)
   */
  async exportAll(): Promise<ReadwiseExport> {
    const response = await fetch(`${READWISE_API_BASE}/export/`, {
      headers: {
        'Authorization': `Token ${this.apiToken}`,
      },
    });

    if (!response.ok) {
      throw new Error(`Export failed: ${response.status}`);
    }

    return response.json();
  }

  private delay(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}

/**
 * 用户 Readwise 集成管理
 */
export class ReadwiseIntegration {
  private supabase: SupabaseClient;

  constructor(supabaseUrl: string, supabaseKey: string) {
    this.supabase = createClient(supabaseUrl, supabaseKey);
  }

  /**
   * 保存用户 Readwise API Token
   * Token 在数据库中加密存储
   */
  async saveToken(userId: string, apiToken: string): Promise<{ success: boolean; error?: string }> {
    try {
      // 验证 token 有效性
      const client = new ReadwiseClient(apiToken);
      const isValid = await client.validateToken();

      if (!isValid) {
        return { success: false, error: 'Invalid Readwise API token' };
      }

      // 加密存储 (简化实现，生产环境使用更安全的加密)
      const encryptedToken = this.encryptToken(apiToken);

      const { error } = await this.supabase
        .from('user_integrations')
        .upsert({
          user_id: userId,
          provider: 'readwise',
          access_token: encryptedToken,
          is_active: true,
          connected_at: new Date().toISOString(),
        }, {
          onConflict: 'user_id,provider',
        });

      if (error) throw error;

      return { success: true };
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Failed to save token',
      };
    }
  }

  /**
   * 获取用户的 Readwise Token
   */
  async getToken(userId: string): Promise<string | null> {
    const { data, error } = await this.supabase
      .from('user_integrations')
      .select('access_token')
      .eq('user_id', userId)
      .eq('provider', 'readwise')
      .eq('is_active', true)
      .single();

    if (error || !data) return null;

    return this.decryptToken(data.access_token);
  }

  /**
   * 断开 Readwise 连接
   */
  async disconnect(userId: string): Promise<void> {
    await this.supabase
      .from('user_integrations')
      .update({ is_active: false, disconnected_at: new Date().toISOString() })
      .eq('user_id', userId)
      .eq('provider', 'readwise');
  }

  /**
   * 同步文章高亮到 Readwise
   */
  async syncHighlights(
    userId: string,
    articleIds?: string[]
  ): Promise<ReadwiseSyncResult> {
    const token = await this.getToken(userId);
    if (!token) {
      return {
        success: false,
        syncedCount: 0,
        failedCount: 0,
        duplicates: 0,
        errors: ['Readwise not connected'],
      };
    }

    // 获取上次同步时间
    const { data: lastSync } = await this.supabase
      .from('sync_logs')
      .select('last_sync_at')
      .eq('user_id', userId)
      .eq('provider', 'readwise')
      .single();

    const lastSyncAt = lastSync?.last_sync_at;

    // 获取需要同步的标注
    let query = this.supabase
      .from('annotations')
      .select(`
        *,
        article:articles(id, title, author, url)
      `)
      .eq('user_id', userId);

    if (articleIds?.length) {
      query = query.in('article_id', articleIds);
    }

    if (lastSyncAt) {
      query = query.gt('updated_at', lastSyncAt);
    }

    // 排除已同步的
    query = query.not('sync_status', 'eq', 'synced');

    const { data: annotations, error } = await query;

    if (error || !annotations?.length) {
      return {
        success: true,
        syncedCount: 0,
        failedCount: 0,
        duplicates: 0,
        errors: [],
      };
    }

    // 转换为 Readwise 格式
    const highlights: ReadwiseHighlight[] = annotations.map((anno: any) => ({
      text: anno.quote,
      title: anno.article?.title || 'Untitled',
      author: anno.article?.author || 'Unknown',
      source_type: 'article',
      category: 'articles',
      note: anno.comment,
      highlighted_at: anno.created_at,
      highlight_url: `${process.env.NEXT_PUBLIC_APP_URL}/articles/${anno.article_id}#annotation-${anno.id}`,
    }));

    // 同步到 Readwise
    const client = new ReadwiseClient(token);
    const result = await client.saveHighlights(highlights);

    // 更新同步状态
    if (result.syncedCount > 0) {
      const syncedIds = annotations
        .slice(0, result.syncedCount)
        .map((a: any) => a.id);

      await this.supabase
        .from('annotations')
        .update({ sync_status: 'synced', synced_at: new Date().toISOString() })
        .in('id', syncedIds);
    }

    // 记录同步日志
    await this.supabase.from('sync_logs').upsert({
      user_id: userId,
      provider: 'readwise',
      last_sync_at: new Date().toISOString(),
      synced_count: result.syncedCount,
      failed_count: result.failedCount,
    }, {
      onConflict: 'user_id,provider',
    });

    return result;
  }

  /**
   * 获取同步状态
   */
  async getSyncStatus(userId: string): Promise<{
    connected: boolean;
    lastSyncAt: string | null;
    pendingCount: number;
  }> {
    const token = await this.getToken(userId);

    if (!token) {
      return { connected: false, lastSyncAt: null, pendingCount: 0 };
    }

    const { data: lastSync } = await this.supabase
      .from('sync_logs')
      .select('last_sync_at')
      .eq('user_id', userId)
      .eq('provider', 'readwise')
      .single();

    const { count: pendingCount } = await this.supabase
      .from('annotations')
      .select('*', { count: 'exact', head: true })
      .eq('user_id', userId)
      .not('sync_status', 'eq', 'synced');

    return {
      connected: true,
      lastSyncAt: lastSync?.last_sync_at || null,
      pendingCount: pendingCount || 0,
    };
  }

  // 简化加密实现 - 生产环境使用专业加密库
  private encryptToken(token: string): string {
    // 实际实现应使用 crypto 库
    return Buffer.from(token).toString('base64');
  }

  private decryptToken(encrypted: string): string {
    return Buffer.from(encrypted, 'base64').toString('utf8');
  }
}

// 导出类型
export type { ReadwiseHighlight, ReadwiseSyncResult, ReadwiseBook };
