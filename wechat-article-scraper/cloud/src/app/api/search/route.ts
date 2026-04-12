/**
 * Full-Text Search API
 *
 * Hybrid search combining:
 * - PostgreSQL full-text search (tsvector/tsquery)
 * - Semantic vector similarity (pgvector)
 * - Auto-suggestions
 * - Search history
 */

import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@/lib/supabase';
import Anthropic from '@anthropic-ai/sdk';

// Kimi API for embedding generation
const KIMI_BASE_URL = 'https://api.kimi.com/coding/';
const KIMI_MODEL = 'kimi-for-coding';

interface SearchResult {
  id: string;
  title: string;
  content: string;
  author: string;
  url: string;
  tags: string[];
  summary?: string;
  keywords: string[];
  rank: number;
  matchType: 'keyword' | 'semantic' | 'hybrid';
  highlightedTitle: string;
  highlightedContent: string;
  createdAt: string;
}

interface SearchSuggestion {
  suggestion: string;
  type: 'tag' | 'author' | 'recent';
  count?: number;
}

/**
 * Generate embedding for semantic search
 */
async function generateEmbedding(text: string, apiKey: string): Promise<number[] | null> {
  try {
    const client = new Anthropic({
      apiKey,
      baseURL: KIMI_BASE_URL,
    });

    // Note: Kimi API may have different embedding endpoint
    // This is a placeholder - actual implementation depends on Kimi's API
    const response = await fetch(`${KIMI_BASE_URL}embeddings`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: 'text-embedding-ada-002', // or Kimi's embedding model
        input: text.slice(0, 8000), // Limit input size
      }),
    });

    if (!response.ok) {
      console.warn('Embedding generation failed:', await response.text());
      return null;
    }

    const data = await response.json();
    return data.data[0].embedding;
  } catch (error) {
    console.error('Failed to generate embedding:', error);
    return null;
  }
}

/**
 * POST /api/search
 * Main search endpoint with hybrid keyword + semantic search
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  const startTime = Date.now();

  try {
    const body = await request.json();
    const {
      query,
      workspaceId,
      limit = 20,
      offset = 0,
      semantic = true,
      filters = {},
    }: {
      query: string;
      workspaceId?: string;
      limit?: number;
      offset?: number;
      semantic?: boolean;
      filters?: {
        tags?: string[];
        author?: string;
        dateRange?: { start: string; end: string };
      };
    } = body;

    if (!query || query.trim().length < 2) {
      return NextResponse.json(
        { error: 'Query must be at least 2 characters' },
        { status: 400 }
      );
    }

    const supabase = createClient();

    // Get current user
    const { data: { user }, error: authError } = await supabase.auth.getUser();
    if (authError || !user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    // Build the search query using our database function
    // For now, we use keyword search as the foundation
    let dbQuery = supabase
      .rpc('search_articles', {
        p_user_id: user.id,
        p_query: query.trim(),
        p_workspace_id: workspaceId || null,
        p_limit: limit,
        p_offset: offset,
        p_semantic: semantic,
        p_threshold: 0.7,
      });

    const { data: results, error: searchError } = await dbQuery;

    if (searchError) {
      console.error('Search error:', searchError);
      return NextResponse.json(
        { error: 'Search failed', details: searchError.message },
        { status: 500 }
      );
    }

    // Log search history
    await supabase.from('search_history').insert({
      user_id: user.id,
      query: query.trim(),
      filters,
      result_count: results?.length || 0,
    });

    const searchResults: SearchResult[] = (results || []).map((row: any) => ({
      id: row.id,
      title: row.title,
      content: row.content,
      author: row.author,
      url: row.url,
      tags: row.tags || [],
      summary: row.summary,
      keywords: row.keywords || [],
      rank: row.rank,
      matchType: row.match_type,
      highlightedTitle: row.highlighted_title,
      highlightedContent: row.highlighted_content,
      createdAt: row.created_at,
    }));

    const responseTime = Date.now() - startTime;

    return NextResponse.json({
      query: query.trim(),
      results: searchResults,
      total: searchResults.length,
      responseTime,
      hasMore: searchResults.length === limit,
    });
  } catch (error) {
    console.error('Search API error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}

/**
 * GET /api/search/suggestions?q=prefix
 * Get search suggestions based on prefix
 */
export async function GET(request: NextRequest): Promise<NextResponse> {
  try {
    const { searchParams } = new URL(request.url);
    const prefix = searchParams.get('q');
    const limit = parseInt(searchParams.get('limit') || '10', 10);

    if (!prefix || prefix.length < 2) {
      return NextResponse.json({ suggestions: [] });
    }

    const supabase = createClient();

    const { data: { user }, error: authError } = await supabase.auth.getUser();
    if (authError || !user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    // Get suggestions from database function
    const { data: suggestions, error } = await supabase.rpc('get_search_suggestions', {
      p_user_id: user.id,
      p_prefix: prefix,
      p_limit: limit,
    });

    if (error) {
      console.error('Suggestions error:', error);
      return NextResponse.json({ suggestions: [] });
    }

    // Also get recent searches
    const { data: recentSearches } = await supabase
      .from('search_history')
      .select('query')
      .eq('user_id', user.id)
      .ilike('query', `${prefix}%`)
      .order('created_at', { ascending: false })
      .limit(5);

    const formattedSuggestions: SearchSuggestion[] = [
      ...(recentSearches || []).map((r) => ({
        suggestion: r.query,
        type: 'recent' as const,
      })),
      ...(suggestions || []).map((s: any) => ({
        suggestion: s.suggestion,
        type: s.type,
        count: s.count,
      })),
    ];

    // Deduplicate
    const seen = new Set<string>();
    const unique = formattedSuggestions.filter((s) => {
      if (seen.has(s.suggestion)) return false;
      seen.add(s.suggestion);
      return true;
    });

    return NextResponse.json({
      suggestions: unique.slice(0, limit),
      prefix,
    });
  } catch (error) {
    console.error('Suggestions API error:', error);
    return NextResponse.json({ suggestions: [] });
  }
}

/**
 * GET /api/search/similar?articleId=id
 * Find similar articles to a given article
 */
export async function PUT(request: NextRequest): Promise<NextResponse> {
  try {
    const { searchParams } = new URL(request.url);
    const articleId = searchParams.get('articleId');

    if (!articleId) {
      return NextResponse.json(
        { error: 'articleId is required' },
        { status: 400 }
      );
    }

    const supabase = createClient();

    const { data: { user }, error: authError } = await supabase.auth.getUser();
    if (authError || !user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { data: similar, error } = await supabase.rpc('find_similar_articles', {
      p_article_id: articleId,
      p_limit: 5,
    });

    if (error) {
      console.error('Similar articles error:', error);
      return NextResponse.json({ error: 'Failed to find similar articles' }, { status: 500 });
    }

    return NextResponse.json({
      articleId,
      similar: similar || [],
    });
  } catch (error) {
    console.error('Similar articles API error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}

/**
 * DELETE /api/search/history
 * Clear search history
 */
export async function DELETE(request: NextRequest): Promise<NextResponse> {
  try {
    const supabase = createClient();

    const { data: { user }, error: authError } = await supabase.auth.getUser();
    if (authError || !user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { error } = await supabase
      .from('search_history')
      .delete()
      .eq('user_id', user.id);

    if (error) {
      return NextResponse.json(
        { error: 'Failed to clear history' },
        { status: 500 }
      );
    }

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error('Clear history error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
