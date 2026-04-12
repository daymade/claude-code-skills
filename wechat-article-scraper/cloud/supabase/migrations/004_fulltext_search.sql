-- Full-Text Search Schema v3.46.0
-- PostgreSQL + pgvector for semantic search

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Add embedding columns to articles
ALTER TABLE public.articles ADD COLUMN IF NOT EXISTS title_embedding vector(1536);
ALTER TABLE public.articles ADD COLUMN IF NOT EXISTS content_embedding vector(1536);
ALTER TABLE public.articles ADD COLUMN IF NOT EXISTS search_vector tsvector;
ALTER TABLE public.articles ADD COLUMN IF NOT EXISTS summary TEXT;
ALTER TABLE public.articles ADD COLUMN IF NOT EXISTS keywords TEXT[] DEFAULT '{}';
ALTER TABLE public.articles ADD COLUMN IF NOT EXISTS indexed_at TIMESTAMPTZ;

-- Add embedding to inbox_items for semantic recommendations
ALTER TABLE public.inbox_items ADD COLUMN IF NOT EXISTS embedding vector(1536);

-- Create search indexes
CREATE INDEX IF NOT EXISTS idx_articles_search_vector ON public.articles USING GIN(search_vector);
CREATE INDEX IF NOT EXISTS idx_articles_title_embedding ON public.articles USING ivfflat(title_embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_articles_content_embedding ON public.articles USING ivfflat(content_embedding vector_cosine_ops);

-- Composite index for hybrid search
CREATE INDEX IF NOT EXISTS idx_articles_hybrid_search ON public.articles
  USING GIN(search_vector, tags);

-- Full-text search function with ranking
CREATE OR REPLACE FUNCTION search_articles(
  p_user_id UUID,
  p_query TEXT,
  p_workspace_id UUID DEFAULT NULL,
  p_limit INTEGER DEFAULT 20,
  p_offset INTEGER DEFAULT 0,
  p_semantic BOOLEAN DEFAULT true,
  p_threshold FLOAT DEFAULT 0.7
)
RETURNS TABLE (
  id UUID,
  title TEXT,
  content TEXT,
  author TEXT,
  url TEXT,
  tags TEXT[],
  summary TEXT,
  keywords TEXT[],
  rank FLOAT,
  match_type TEXT,
  highlighted_title TEXT,
  highlighted_content TEXT,
  created_at TIMESTAMPTZ
) AS $$
DECLARE
  v_query_embedding vector(1536);
  v_search_query tsquery;
BEGIN
  -- Convert query to tsquery
  v_search_query := plainto_tsquery('chinese', p_query);

  -- If semantic search is enabled, we'd need to get embedding from external service
  -- For now, we'll do keyword-based search with ranking

  RETURN QUERY
  WITH keyword_matches AS (
    SELECT
      a.id,
      a.title,
      a.content,
      a.author,
      a.url,
      a.tags,
      a.summary,
      a.keywords,
      ts_rank_cd(a.search_vector, v_search_query, 32) AS keyword_rank,
      'keyword'::TEXT AS match_type,
      ts_headline('chinese', a.title, v_search_query,
        'StartSel=<mark>, StopSel=</mark>, MaxWords=50, MinWords=10') AS highlighted_title,
      ts_headline('chinese', LEFT(a.content, 10000), v_search_query,
        'StartSel=<mark>, StopSel=</mark>, MaxWords=100, MinWords=20') AS highlighted_content,
      a.created_at
    FROM public.articles a
    JOIN public.workspace_members wm ON a.workspace_id = wm.workspace_id
    WHERE
      wm.user_id = p_user_id
      AND a.search_vector @@ v_search_query
      AND (p_workspace_id IS NULL OR a.workspace_id = p_workspace_id)
  ),
  -- Semantic similarity search (when embedding is available)
  semantic_matches AS (
    SELECT
      a.id,
      a.title,
      a.content,
      a.author,
      a.url,
      a.tags,
      a.summary,
      a.keywords,
      1 - (a.title_embedding <=> v_query_embedding) AS semantic_rank,
      'semantic'::TEXT AS match_type,
      a.title AS highlighted_title,
      LEFT(a.content, 500) AS highlighted_content,
      a.created_at
    FROM public.articles a
    JOIN public.workspace_members wm ON a.workspace_id = wm.workspace_id
    WHERE
      wm.user_id = p_user_id
      AND a.title_embedding IS NOT NULL
      AND 1 - (a.title_embedding <=> v_query_embedding) > p_threshold
      AND (p_workspace_id IS NULL OR a.workspace_id = p_workspace_id)
      AND p_semantic = true
      AND v_query_embedding IS NOT NULL
  ),
  combined AS (
    SELECT * FROM keyword_matches
    UNION ALL
    SELECT * FROM semantic_matches
  )
  SELECT DISTINCT ON (id)
    id,
    title,
    content,
    author,
    url,
    tags,
    summary,
    keywords,
    MAX(keyword_rank) AS rank,
    MAX(match_type) AS match_type,
    highlighted_title,
    highlighted_content,
    created_at
  FROM combined
  GROUP BY id, title, content, author, url, tags, summary, keywords,
           highlighted_title, highlighted_content, created_at
  ORDER BY MAX(keyword_rank) DESC
  LIMIT p_limit
  OFFSET p_offset;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to update search vector
CREATE OR REPLACE FUNCTION update_article_search_vector()
RETURNS TRIGGER AS $$
BEGIN
  NEW.search_vector :=
    setweight(to_tsvector('chinese', COALESCE(NEW.title, '')), 'A') ||
    setweight(to_tsvector('chinese', COALESCE(NEW.author, '')), 'B') ||
    setweight(to_tsvector('chinese', COALESCE(array_to_string(NEW.tags, ' '), '')), 'B') ||
    setweight(to_tsvector('chinese', COALESCE(NEW.content, '')), 'C');
  NEW.indexed_at := NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update search vector
DROP TRIGGER IF EXISTS trigger_update_search_vector ON public.articles;
CREATE TRIGGER trigger_update_search_vector
  BEFORE INSERT OR UPDATE OF title, content, author, tags ON public.articles
  FOR EACH ROW
  EXECUTE FUNCTION update_article_search_vector();

-- Function to find similar articles
CREATE OR REPLACE FUNCTION find_similar_articles(
  p_article_id UUID,
  p_limit INTEGER DEFAULT 5
)
RETURNS TABLE (
  id UUID,
  title TEXT,
  author TEXT,
  similarity FLOAT
) AS $$
DECLARE
  v_embedding vector(1536);
BEGIN
  SELECT title_embedding INTO v_embedding
  FROM public.articles
  WHERE id = p_article_id;

  IF v_embedding IS NULL THEN
    RETURN;
  END IF;

  RETURN QUERY
  SELECT
    a.id,
    a.title,
    a.author,
    1 - (a.title_embedding <=> v_embedding) AS similarity
  FROM public.articles a
  WHERE a.id != p_article_id
    AND a.title_embedding IS NOT NULL
  ORDER BY a.title_embedding <=> v_embedding
  LIMIT p_limit;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Search suggestions function
CREATE OR REPLACE FUNCTION get_search_suggestions(
  p_user_id UUID,
  p_prefix TEXT,
  p_limit INTEGER DEFAULT 10
)
RETURNS TABLE (
  suggestion TEXT,
  type TEXT,
  count BIGINT
) AS $$
BEGIN
  RETURN QUERY

  -- Tag suggestions
  SELECT
    unnest(tags) AS suggestion,
    'tag'::TEXT AS type,
    COUNT(*) AS count
  FROM public.articles a
  JOIN public.workspace_members wm ON a.workspace_id = wm.workspace_id
  WHERE wm.user_id = p_user_id
    AND EXISTS (
      SELECT 1 FROM unnest(tags) t
      WHERE t ILIKE p_prefix || '%'
    )
  GROUP BY unnest(tags)

  UNION ALL

  -- Author suggestions
  SELECT
    author AS suggestion,
    'author'::TEXT AS type,
    COUNT(*) AS count
  FROM public.articles a
  JOIN public.workspace_members wm ON a.workspace_id = wm.workspace_id
  WHERE wm.user_id = p_user_id
    AND author ILIKE p_prefix || '%'
  GROUP BY author

  ORDER BY count DESC
  LIMIT p_limit;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Search history table
CREATE TABLE public.search_history (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
  query TEXT NOT NULL,
  filters JSONB DEFAULT '{}',
  result_count INTEGER,
  clicked_article_id UUID REFERENCES public.articles(id),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for search history
CREATE INDEX idx_search_history_user ON public.search_history(user_id);
CREATE INDEX idx_search_history_created ON public.search_history(created_at);

-- RLS for search history
ALTER TABLE public.search_history ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own search history"
  ON public.search_history FOR SELECT
  USING (user_id = auth.uid());

CREATE POLICY "Users can create own search history"
  ON public.search_history FOR INSERT
  WITH CHECK (user_id = auth.uid());

CREATE POLICY "Users can delete own search history"
  ON public.search_history FOR DELETE
  USING (user_id = auth.uid());

-- Enable realtime for search-related updates
ALTER PUBLICATION supabase_realtime ADD TABLE public.search_history;

-- Materialized view for search analytics
CREATE MATERIALIZED VIEW public.search_analytics AS
SELECT
  DATE_TRUNC('day', created_at) AS date,
  query,
  COUNT(*) AS search_count,
  AVG(result_count) AS avg_results,
  COUNT(clicked_article_id) AS click_count
FROM public.search_history
GROUP BY DATE_TRUNC('day', created_at), query;

-- Index on materialized view
CREATE UNIQUE INDEX idx_search_analytics_unique ON public.search_analytics(date, query);

-- Function to refresh search analytics
CREATE OR REPLACE FUNCTION refresh_search_analytics()
RETURNS void AS $$
BEGIN
  REFRESH MATERIALIZED VIEW CONCURRENTLY public.search_analytics;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
