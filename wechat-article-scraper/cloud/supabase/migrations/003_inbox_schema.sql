-- Inbox Engine Schema v3.45.0
-- Smart content inbox with AI auto-classification

-- Inbox items table (unified content management)
CREATE TABLE public.inbox_items (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  article_id UUID REFERENCES public.articles(id) ON DELETE CASCADE,
  user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE,

  -- Workflow status
  status TEXT DEFAULT 'inbox' CHECK (status IN ('inbox', 'reading', 'later', 'archived', 'favorite')),
  priority TEXT DEFAULT 'medium' CHECK (priority IN ('high', 'medium', 'low')),
  content_type TEXT DEFAULT 'article' CHECK (content_type IN ('article', 'newsletter', 'paper', 'tweet-thread', 'video-transcript')),

  -- AI-generated metadata
  suggested_tags TEXT[] DEFAULT '{}',
  suggested_folder TEXT,
  estimated_read_time INTEGER DEFAULT 5, -- minutes
  complexity TEXT DEFAULT 'medium' CHECK (complexity IN ('easy', 'medium', 'hard')),
  key_topics TEXT[] DEFAULT '{}',
  summary TEXT,
  score INTEGER DEFAULT 50, -- AI-calculated relevance score (0-100)

  -- User actions
  added_at TIMESTAMPTZ DEFAULT NOW(),
  started_reading_at TIMESTAMPTZ,
  finished_reading_at TIMESTAMPTZ,
  last_position INTEGER DEFAULT 0, -- scroll position for resuming

  -- User overrides
  user_applied_tags TEXT[] DEFAULT '{}',
  user_priority TEXT CHECK (user_priority IN ('high', 'medium', 'low')),
  user_folder TEXT,

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(article_id, user_id)
);

-- Reading sessions (for tracking actual reading time)
CREATE TABLE public.reading_sessions (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  inbox_item_id UUID REFERENCES public.inbox_items(id) ON DELETE CASCADE,
  user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
  started_at TIMESTAMPTZ DEFAULT NOW(),
  ended_at TIMESTAMPTZ,
  duration_seconds INTEGER DEFAULT 0,
  progress_start INTEGER DEFAULT 0, -- scroll position at start
  progress_end INTEGER DEFAULT 0, -- scroll position at end
  device_id TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- User folders (custom organization)
CREATE TABLE public.user_folders (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  color TEXT DEFAULT 'blue' CHECK (color IN ('blue', 'green', 'yellow', 'red', 'purple', 'pink', 'gray')),
  icon TEXT DEFAULT 'folder',
  sort_order INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, name)
);

-- Review history (for spaced repetition)
CREATE TABLE public.review_history (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  inbox_item_id UUID REFERENCES public.inbox_items(id) ON DELETE CASCADE,
  user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
  reviewed_at TIMESTAMPTZ DEFAULT NOW(),
  feedback TEXT CHECK (feedback IN ('remembered', 'fuzzy', 'forgotten')),
  memory_strength INTEGER DEFAULT 0, -- 0-100
  next_review_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable RLS
ALTER TABLE public.inbox_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reading_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_folders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.review_history ENABLE ROW LEVEL SECURITY;

-- RLS Policies

-- Inbox items: users can CRUD their own
CREATE POLICY "Users can view own inbox items"
  ON public.inbox_items FOR SELECT
  USING (user_id = auth.uid());

CREATE POLICY "Users can create own inbox items"
  ON public.inbox_items FOR INSERT
  WITH CHECK (user_id = auth.uid());

CREATE POLICY "Users can update own inbox items"
  ON public.inbox_items FOR UPDATE
  USING (user_id = auth.uid());

CREATE POLICY "Users can delete own inbox items"
  ON public.inbox_items FOR DELETE
  USING (user_id = auth.uid());

-- Reading sessions: private to user
CREATE POLICY "Users can view own reading sessions"
  ON public.reading_sessions FOR SELECT
  USING (user_id = auth.uid());

CREATE POLICY "Users can manage own reading sessions"
  ON public.reading_sessions FOR ALL
  USING (user_id = auth.uid());

-- User folders: private to user
CREATE POLICY "Users can view own folders"
  ON public.user_folders FOR SELECT
  USING (user_id = auth.uid());

CREATE POLICY "Users can manage own folders"
  ON public.user_folders FOR ALL
  USING (user_id = auth.uid());

-- Review history: private to user
CREATE POLICY "Users can view own review history"
  ON public.review_history FOR SELECT
  USING (user_id = auth.uid());

CREATE POLICY "Users can manage own review history"
  ON public.review_history FOR ALL
  USING (user_id = auth.uid());

-- Enable Realtime
ALTER PUBLICATION supabase_realtime ADD TABLE public.inbox_items;
ALTER PUBLICATION supabase_realtime ADD TABLE public.reading_sessions;
ALTER PUBLICATION supabase_realtime ADD TABLE public.user_folders;
ALTER PUBLICATION supabase_realtime ADD TABLE public.review_history;

-- Indexes for performance
CREATE INDEX idx_inbox_items_user ON public.inbox_items(user_id);
CREATE INDEX idx_inbox_items_status ON public.inbox_items(status);
CREATE INDEX idx_inbox_items_priority ON public.inbox_items(priority);
CREATE INDEX idx_inbox_items_score ON public.inbox_items(score DESC);
CREATE INDEX idx_inbox_items_added_at ON public.inbox_items(added_at DESC);
CREATE INDEX idx_inbox_items_content_type ON public.inbox_items(content_type);
CREATE INDEX idx_inbox_items_suggested_tags ON public.inbox_items USING GIN(suggested_tags);
CREATE INDEX idx_inbox_items_user_folder ON public.inbox_items(user_folder);

CREATE INDEX idx_reading_sessions_inbox_item ON public.reading_sessions(inbox_item_id);
CREATE INDEX idx_reading_sessions_user ON public.reading_sessions(user_id);
CREATE INDEX idx_reading_sessions_started_at ON public.reading_sessions(started_at DESC);

CREATE INDEX idx_user_folders_user ON public.user_folders(user_id);
CREATE INDEX idx_user_folders_sort_order ON public.user_folders(sort_order);

CREATE INDEX idx_review_history_inbox_item ON public.review_history(inbox_item_id);
CREATE INDEX idx_review_history_user ON public.review_history(user_id);
CREATE INDEX idx_review_history_next_review ON public.review_history(next_review_at) WHERE next_review_at IS NOT NULL;

-- Triggers for updated_at
CREATE TRIGGER update_inbox_items_updated_at BEFORE UPDATE ON public.inbox_items
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function to auto-update reading progress
CREATE OR REPLACE FUNCTION update_reading_progress_on_session()
RETURNS TRIGGER AS $$
BEGIN
  -- Update inbox item with latest reading position and time
  UPDATE public.inbox_items
  SET
    last_position = NEW.progress_end,
    started_reading_at = COALESCE(started_reading_at, NEW.started_at),
    status = CASE
      WHEN NEW.progress_end >= 90 THEN 'archived'
      WHEN NEW.progress_end > 0 THEN 'reading'
      ELSE status
    END,
    updated_at = NOW()
  WHERE id = NEW.inbox_item_id;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER update_progress_after_session
  AFTER INSERT ON public.reading_sessions
  FOR EACH ROW EXECUTE FUNCTION update_reading_progress_on_session();

-- Function to calculate next review date (spaced repetition)
CREATE OR REPLACE FUNCTION calculate_next_review(
  p_feedback TEXT,
  p_current_strength INTEGER,
  p_review_count INTEGER
)
RETURNS TIMESTAMPTZ AS $$
DECLARE
  v_interval INTERVAL;
  v_multiplier NUMERIC;
BEGIN
  -- Base intervals based on feedback
  CASE p_feedback
    WHEN 'remembered' THEN
      v_multiplier := 2.5;
      v_interval := (p_review_count * 2.5) * INTERVAL '1 day';
      IF v_interval > INTERVAL '365 days' THEN
        v_interval := INTERVAL '365 days';
      END IF;
    WHEN 'fuzzy' THEN
      v_multiplier := 1.5;
      v_interval := GREATEST(INTERVAL '1 day', (p_review_count * 1.5) * INTERVAL '1 day');
    WHEN 'forgotten' THEN
      v_multiplier := 0.5;
      v_interval := INTERVAL '10 minutes'; -- Review soon
    ELSE
      v_interval := INTERVAL '1 day';
  END CASE;

  RETURN NOW() + v_interval;
END;
$$ LANGUAGE plpgsql;

-- Change logging for inbox items
CREATE TRIGGER log_inbox_items_changes
  AFTER INSERT OR UPDATE OR DELETE ON public.inbox_items
  FOR EACH ROW EXECUTE FUNCTION log_change();

-- Default folders for new users
CREATE OR REPLACE FUNCTION create_default_folders()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.user_folders (user_id, name, color, icon, sort_order)
  VALUES
    (NEW.id, 'Quick Reads', 'green', 'zap', 1),
    (NEW.id, 'Deep Dives', 'purple', 'book-open', 2),
    (NEW.id, 'Newsletters', 'blue', 'mail', 3),
    (NEW.id, 'Research', 'red', 'microscope', 4),
    (NEW.id, 'Later', 'gray', 'clock', 5);

  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER create_default_folders_after_profile
  AFTER INSERT ON public.profiles
  FOR EACH ROW EXECUTE FUNCTION create_default_folders();
