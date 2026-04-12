/**
 * End-to-End Reading Workflow Integration Test
 *
 * Tests the complete user journey:
 * 1. Article creation in database
 * 2. Open in Reader
 * 3. Add annotations
 * 4. AI extracts insights
 * 5. Export to Obsidian
 *
 * This test validates the entire data flow.
 */

import { describe, it, expect, beforeAll } from 'vitest';
import { createClient, SupabaseClient } from '@supabase/supabase-js';
import { ObsidianClient } from '@/lib/obsidian-client';
import { ReadingAgentSDK } from '@/lib/reading-agent-sdk';

describe('Complete Reading Workflow', () => {
  let supabase: SupabaseClient;
  const testUserId = 'test-user-' + Date.now();
  const testArticleId = 'test-article-' + Date.now();

  beforeAll(() => {
    // Initialize Supabase client for testing
    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || 'http://localhost:54321';
    const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || 'test-key';

    supabase = createClient(supabaseUrl, supabaseKey);
  });

  it('should complete full reading workflow', async () => {
    // Step 1: Create article in database
    const { data: article, error: articleError } = await supabase
      .from('articles')
      .insert({
        id: testArticleId,
        title: 'Test Article for Workflow',
        author: 'Test Author',
        content: '<p>This is the first paragraph with important information.</p><p>This is the second paragraph.</p>',
        url: 'https://example.com/test-article',
        created_by: testUserId,
      })
      .select()
      .single();

    expect(articleError).toBeNull();
    expect(article).not.toBeNull();
    expect(article.title).toBe('Test Article for Workflow');

    // Step 2: Create annotations
    const annotations = [
      {
        id: `anno-${Date.now()}-1`,
        article_id: testArticleId,
        user_id: testUserId,
        quote: 'important information',
        comment: 'This is key insight',
        color: 'yellow',
        tags: ['key-insight'],
      },
      {
        id: `anno-${Date.now()}-2`,
        article_id: testArticleId,
        user_id: testUserId,
        quote: 'second paragraph',
        comment: '',
        color: 'blue',
        tags: [],
      },
    ];

    const { data: savedAnnotations, error: annoError } = await supabase
      .from('annotations')
      .insert(annotations)
      .select();

    expect(annoError).toBeNull();
    expect(savedAnnotations).toHaveLength(2);

    // Step 3: Extract insights using Reading Agent (mocked for integration test)
    const apiKey = process.env.TEST_KIMI_API_KEY || 'test-key';
    const agent = new ReadingAgentSDK(apiKey);

    const agentResult = await agent.processAnnotations(
      savedAnnotations!.map(a => ({
        id: a.id,
        articleId: a.article_id,
        userId: a.user_id,
        quote: a.quote,
        comment: a.comment,
        color: a.color as any,
        tags: a.tags,
        position: null,
        createdAt: a.created_at,
        updatedAt: a.updated_at,
      })),
      {
        title: article.title,
        author: article.author,
        content: article.content,
      }
    );

    expect(agentResult).toHaveProperty('insights');
    expect(agentResult).toHaveProperty('notes');
    expect(agentResult).toHaveProperty('actions');

    // Step 4: Export to Obsidian
    const obsidianClient = new ObsidianClient();
    const exportData = {
      article: {
        id: article.id,
        title: article.title,
        author: article.author,
        content: article.content,
        url: article.url,
        publishTime: article.publish_time,
        tags: article.tags || [],
      },
      annotations: savedAnnotations!.map(a => ({
        id: a.id,
        quote: a.quote,
        comment: a.comment,
        color: a.color,
        tags: a.tags,
        createdAt: a.created_at,
      })),
    };

    const obsidianExport = obsidianClient.exportArticle(exportData);

    expect(obsidianExport.filename).toContain('Test Article for Workflow');
    expect(obsidianExport.content).toContain('Test Article for Workflow');
    expect(obsidianExport.content).toContain('important information');
    expect(obsidianExport.content).toContain('This is key insight');

    // Cleanup
    await supabase.from('annotations').delete().eq('article_id', testArticleId);
    await supabase.from('articles').delete().eq('id', testArticleId);
  });

  it('should handle article without annotations', async () => {
    const emptyArticleId = 'empty-article-' + Date.now();

    const { data: article } = await supabase
      .from('articles')
      .insert({
        id: emptyArticleId,
        title: 'Empty Article',
        content: '<p>Content without annotations</p>',
        created_by: testUserId,
      })
      .select()
      .single();

    const { data: annotations } = await supabase
      .from('annotations')
      .select('*')
      .eq('article_id', emptyArticleId);

    expect(annotations).toHaveLength(0);

    // Export should still work
    const obsidianClient = new ObsidianClient();
    const result = obsidianClient.exportArticle({
      article: {
        id: emptyArticleId,
        title: article.title,
        content: article.content,
      },
      annotations: [],
    });

    expect(result.content).toContain('Empty Article');

    await supabase.from('articles').delete().eq('id', emptyArticleId);
  });
});
