-- WeChat Ecosystem Integration Schema (Round 92)
-- Enables Mini Program + Official Account integration

-- WeChat user binding table
-- Links WeChat OpenID to internal user account
CREATE TABLE public.wechat_bindings (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
  openid VARCHAR(255) NOT NULL,
  unionid VARCHAR(255),
  app_type VARCHAR(50) NOT NULL CHECK (app_type IN ('miniapp', 'official')),
  session_key TEXT,
  bound_at TIMESTAMPTZ DEFAULT NOW(),
  last_used_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(openid, app_type)
);

-- WeChat-specific article metadata
ALTER TABLE public.articles ADD COLUMN IF NOT EXISTS source VARCHAR(50);
ALTER TABLE public.articles ADD COLUMN IF NOT EXISTS source_metadata JSONB DEFAULT '{}';

-- Scraping jobs queue for async processing
CREATE TABLE public.scrape_jobs (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  url TEXT NOT NULL,
  user_id UUID REFERENCES public.profiles(id),
  workspace_id UUID REFERENCES public.workspaces(id),
  source VARCHAR(50) DEFAULT 'extension',
  priority VARCHAR(20) DEFAULT 'normal' CHECK (priority IN ('low', 'normal', 'high')),
  status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
  result JSONB DEFAULT '{}',
  error_message TEXT,
  attempts INTEGER DEFAULT 0,
  max_attempts INTEGER DEFAULT 3,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ
);

-- WeChat message log for debugging and replay
CREATE TABLE public.wechat_message_logs (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  app_type VARCHAR(50) NOT NULL,
  openid VARCHAR(255) NOT NULL,
  msg_type VARCHAR(50),
  content TEXT,
  raw_payload JSONB,
  processed BOOLEAN DEFAULT false,
  response TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_wechat_bindings_user ON public.wechat_bindings(user_id);
CREATE INDEX idx_wechat_bindings_openid ON public.wechat_bindings(openid);
CREATE INDEX idx_scrape_jobs_status ON public.scrape_jobs(status);
CREATE INDEX idx_scrape_jobs_user ON public.scrape_jobs(user_id);
CREATE INDEX idx_articles_source ON public.articles(source);

-- Enable RLS
ALTER TABLE public.wechat_bindings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.scrape_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.wechat_message_logs ENABLE ROW LEVEL SECURITY;

-- RLS Policies

-- WeChat bindings: users can only see their own bindings
CREATE POLICY "Users can view own WeChat bindings"
  ON public.wechat_bindings FOR SELECT
  USING (auth.uid() = user_id);

-- Scrape jobs: users can only see their own jobs
CREATE POLICY "Users can view own scrape jobs"
  ON public.scrape_jobs FOR SELECT
  USING (auth.uid() = user_id);

-- Message logs: service role only (no direct user access)
CREATE POLICY "Message logs service only"
  ON public.wechat_message_logs FOR ALL
  USING (false);

-- Function to get or create user by WeChat OpenID
CREATE OR REPLACE FUNCTION get_or_create_wechat_user(
  p_openid VARCHAR(255),
  p_app_type VARCHAR(50),
  p_unionid VARCHAR(255) DEFAULT NULL
)
RETURNS TABLE(user_id UUID, is_new BOOLEAN) AS $$
DECLARE
  v_user_id UUID;
  v_is_new BOOLEAN := false;
BEGIN
  -- Try to find existing binding
  SELECT wb.user_id INTO v_user_id
  FROM public.wechat_bindings wb
  WHERE wb.openid = p_openid AND wb.app_type = p_app_type;

  IF v_user_id IS NULL THEN
    -- Create new user
    v_is_new := true;

    -- Create user in auth.users (requires service role or trigger)
    -- For now, return null - actual user creation handled in application
    v_user_id := NULL;
  ELSE
    -- Update last used
    UPDATE public.wechat_bindings
    SET last_used_at = NOW()
    WHERE openid = p_openid AND app_type = p_app_type;
  END IF;

  RETURN QUERY SELECT v_user_id, v_is_new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to check if article already saved
CREATE OR REPLACE FUNCTION find_existing_article(
  p_user_id UUID,
  p_url TEXT
)
RETURNS TABLE(article_id UUID, saved_at TIMESTAMPTZ) AS $$
BEGIN
  RETURN QUERY
  SELECT a.id, a.created_at
  FROM public.articles a
  JOIN public.workspaces w ON a.workspace_id = w.id
  JOIN public.workspace_members wm ON w.id = wm.workspace_id
  WHERE wm.user_id = p_user_id
    AND a.url = p_url
  LIMIT 1;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
