-- Sync Engine and Webhook Automation Schema
-- v3.42.0: Offline-first sync + Automated exports

-- Annotations table (for highlighting and notes)
CREATE TABLE public.annotations (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  article_id UUID REFERENCES public.articles(id) ON DELETE CASCADE,
  user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
  quote TEXT NOT NULL,
  comment TEXT,
  color TEXT DEFAULT 'yellow' CHECK (color IN ('yellow', 'green', 'blue', 'pink', 'purple')),
  tags TEXT[],
  position JSONB, -- { startXPath, endXPath, startOffset, endOffset }
  device_id TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Reading progress tracking
CREATE TABLE public.reading_progress (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  article_id UUID REFERENCES public.articles(id) ON DELETE CASCADE,
  user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
  progress_percentage INTEGER DEFAULT 0 CHECK (progress_percentage BETWEEN 0 AND 100),
  scroll_position INTEGER DEFAULT 0,
  time_spent_seconds INTEGER DEFAULT 0,
  last_read_at TIMESTAMPTZ DEFAULT NOW(),
  device_id TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(article_id, user_id)
);

-- Change log for sync (tracks all mutations)
CREATE TABLE public.change_log (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  table_name TEXT NOT NULL,
  operation TEXT NOT NULL CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE')),
  record_id UUID NOT NULL,
  old_data JSONB,
  new_data JSONB,
  user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
  device_id TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  synced_at TIMESTAMPTZ,
  sync_status TEXT DEFAULT 'pending' CHECK (sync_status IN ('pending', 'synced', 'conflict', 'failed'))
);

-- Webhook integrations (Notion, Obsidian, etc.)
CREATE TABLE public.webhooks (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  workspace_id UUID REFERENCES public.workspaces(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  provider TEXT NOT NULL CHECK (provider IN ('notion', 'obsidian', 'readwise', 'custom')),
  webhook_url TEXT NOT NULL,
  secret TEXT, -- For HMAC signature verification
  config JSONB DEFAULT '{}', -- Provider-specific config
  events TEXT[] DEFAULT '{}', -- ['article.saved', 'annotation.created', etc.]
  is_active BOOLEAN DEFAULT true,
  last_triggered_at TIMESTAMPTZ,
  last_error TEXT,
  created_by UUID REFERENCES public.profiles(id),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Webhook delivery logs
CREATE TABLE public.webhook_deliveries (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  webhook_id UUID REFERENCES public.webhooks(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  payload JSONB NOT NULL,
  response_status INTEGER,
  response_body TEXT,
  error_message TEXT,
  retry_count INTEGER DEFAULT 0,
  delivered_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Export jobs (async exports to external systems)
CREATE TABLE public.export_jobs (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  workspace_id UUID REFERENCES public.workspaces(id) ON DELETE CASCADE,
  user_id UUID REFERENCES public.profiles(id),
  format TEXT NOT NULL CHECK (format IN ('markdown', 'json', 'html', 'pdf', 'notion', 'obsidian')),
  filters JSONB DEFAULT '{}', -- { article_ids, date_range, tags, etc. }
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
  file_url TEXT,
  file_size INTEGER,
  error_message TEXT,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Sync devices registry
CREATE TABLE public.sync_devices (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
  device_id TEXT UNIQUE NOT NULL,
  device_name TEXT,
  device_type TEXT, -- 'chrome_extension', 'pwa', 'mobile_app', 'desktop'
  last_sync_at TIMESTAMPTZ,
  last_seen_at TIMESTAMPTZ DEFAULT NOW(),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Conflict resolution queue
CREATE TABLE public.sync_conflicts (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  table_name TEXT NOT NULL,
  record_id UUID NOT NULL,
  local_data JSONB NOT NULL,
  remote_data JSONB NOT NULL,
  local_device_id TEXT,
  remote_device_id TEXT,
  user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
  resolution TEXT CHECK (resolution IN ('local', 'remote', 'merged', 'manual')),
  merged_data JSONB,
  resolved_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable RLS
ALTER TABLE public.annotations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reading_progress ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.change_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.webhooks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.webhook_deliveries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.export_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sync_devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sync_conflicts ENABLE ROW LEVEL SECURITY;

-- RLS Policies

-- Annotations: users can CRUD their own
CREATE POLICY "Users can view annotations on accessible articles"
  ON public.annotations FOR SELECT
  USING (user_id = auth.uid() OR EXISTS (
    SELECT 1 FROM public.articles a
    JOIN public.workspace_members wm ON a.workspace_id = wm.workspace_id
    WHERE a.id = annotations.article_id AND wm.user_id = auth.uid()
  ));

CREATE POLICY "Users can create own annotations"
  ON public.annotations FOR INSERT
  WITH CHECK (user_id = auth.uid());

CREATE POLICY "Users can update own annotations"
  ON public.annotations FOR UPDATE
  USING (user_id = auth.uid());

CREATE POLICY "Users can delete own annotations"
  ON public.annotations FOR DELETE
  USING (user_id = auth.uid());

-- Reading progress: private to user
CREATE POLICY "Users can view own reading progress"
  ON public.reading_progress FOR SELECT
  USING (user_id = auth.uid());

CREATE POLICY "Users can manage own reading progress"
  ON public.reading_progress FOR ALL
  USING (user_id = auth.uid());

-- Change log: viewable by user who made the change
CREATE POLICY "Users can view own change log"
  ON public.change_log FOR SELECT
  USING (user_id = auth.uid());

-- Webhooks: workspace admins only
CREATE POLICY "Webhooks viewable by workspace members"
  ON public.webhooks FOR SELECT
  USING (EXISTS (
    SELECT 1 FROM public.workspace_members
    WHERE workspace_id = webhooks.workspace_id AND user_id = auth.uid()
  ));

CREATE POLICY "Webhooks manageable by workspace admins"
  ON public.webhooks FOR ALL
  USING (EXISTS (
    SELECT 1 FROM public.workspace_members
    WHERE workspace_id = webhooks.workspace_id
    AND user_id = auth.uid()
    AND role IN ('owner', 'admin')
  ));

-- Webhook deliveries: viewable by webhook owners
CREATE POLICY "Webhook deliveries viewable by owners"
  ON public.webhook_deliveries FOR SELECT
  USING (EXISTS (
    SELECT 1 FROM public.webhooks w
    JOIN public.workspace_members wm ON w.workspace_id = wm.workspace_id
    WHERE w.id = webhook_deliveries.webhook_id AND wm.user_id = auth.uid()
  ));

-- Export jobs: workspace members
CREATE POLICY "Export jobs viewable by workspace members"
  ON public.export_jobs FOR SELECT
  USING (EXISTS (
    SELECT 1 FROM public.workspace_members
    WHERE workspace_id = export_jobs.workspace_id AND user_id = auth.uid()
  ));

CREATE POLICY "Users can create export jobs"
  ON public.export_jobs FOR INSERT
  WITH CHECK (user_id = auth.uid());

-- Sync devices: private to user
CREATE POLICY "Users can manage own devices"
  ON public.sync_devices FOR ALL
  USING (user_id = auth.uid());

-- Sync conflicts: private to user
CREATE POLICY "Users can manage own conflicts"
  ON public.sync_conflicts FOR ALL
  USING (user_id = auth.uid());

-- Enable Realtime
ALTER PUBLICATION supabase_realtime ADD TABLE public.annotations;
ALTER PUBLICATION supabase_realtime ADD TABLE public.reading_progress;
ALTER PUBLICATION supabase_realtime ADD TABLE public.change_log;
ALTER PUBLICATION supabase_realtime ADD TABLE public.sync_conflicts;

-- Indexes
CREATE INDEX idx_annotations_article ON public.annotations(article_id);
CREATE INDEX idx_annotations_user ON public.annotations(user_id);
CREATE INDEX idx_reading_progress_user ON public.reading_progress(user_id);
CREATE INDEX idx_reading_progress_article ON public.reading_progress(article_id);
CREATE INDEX idx_change_log_user ON public.change_log(user_id);
CREATE INDEX idx_change_log_sync_status ON public.change_log(sync_status);
CREATE INDEX idx_webhooks_workspace ON public.webhooks(workspace_id);
CREATE INDEX idx_webhook_deliveries_webhook ON public.webhook_deliveries(webhook_id);
CREATE INDEX idx_export_jobs_workspace ON public.export_jobs(workspace_id);
CREATE INDEX idx_export_jobs_status ON public.export_jobs(status);
CREATE INDEX idx_sync_devices_user ON public.sync_devices(user_id);
CREATE INDEX idx_sync_conflicts_user ON public.sync_conflicts(user_id);
CREATE INDEX idx_sync_conflicts_resolved ON public.sync_conflicts(resolved_at) WHERE resolved_at IS NULL;

-- Triggers for updated_at
CREATE TRIGGER update_annotations_updated_at BEFORE UPDATE ON public.annotations
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_reading_progress_updated_at BEFORE UPDATE ON public.reading_progress
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_webhooks_updated_at BEFORE UPDATE ON public.webhooks
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_export_jobs_updated_at BEFORE UPDATE ON public.export_jobs
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function to log changes for sync
CREATE OR REPLACE FUNCTION log_change()
RETURNS TRIGGER AS $$
DECLARE
  v_user_id UUID;
  v_device_id TEXT;
BEGIN
  -- Get current user from JWT claim
  v_user_id := auth.uid();
  v_device_id := current_setting('request.headers', true)::json->>'x-device-id';

  IF TG_OP = 'DELETE' THEN
    INSERT INTO public.change_log (table_name, operation, record_id, old_data, user_id, device_id)
    VALUES (TG_TABLE_NAME, 'DELETE', OLD.id, to_jsonb(OLD), v_user_id, v_device_id);
    RETURN OLD;
  ELSIF TG_OP = 'UPDATE' THEN
    INSERT INTO public.change_log (table_name, operation, record_id, old_data, new_data, user_id, device_id)
    VALUES (TG_TABLE_NAME, 'UPDATE', NEW.id, to_jsonb(OLD), to_jsonb(NEW), v_user_id, v_device_id);
    RETURN NEW;
  ELSIF TG_OP = 'INSERT' THEN
    INSERT INTO public.change_log (table_name, operation, record_id, new_data, user_id, device_id)
    VALUES (TG_TABLE_NAME, 'INSERT', NEW.id, to_jsonb(NEW), v_user_id, v_device_id);
    RETURN NEW;
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Apply change logging to tables
CREATE TRIGGER log_annotations_changes
  AFTER INSERT OR UPDATE OR DELETE ON public.annotations
  FOR EACH ROW EXECUTE FUNCTION log_change();

CREATE TRIGGER log_reading_progress_changes
  AFTER INSERT OR UPDATE OR DELETE ON public.reading_progress
  FOR EACH ROW EXECUTE FUNCTION log_change();

-- Function to notify webhooks on annotation creation
CREATE OR REPLACE FUNCTION notify_webhook_on_annotation()
RETURNS TRIGGER AS $$
DECLARE
  webhook RECORD;
  payload JSONB;
  article_record RECORD;
BEGIN
  -- Get article info
  SELECT a.*, p.full_name as user_name
  INTO article_record
  FROM public.articles a
  JOIN public.profiles p ON p.id = NEW.user_id
  WHERE a.id = NEW.article_id;

  -- Build payload
  payload := jsonb_build_object(
    'event', 'annotation.created',
    'timestamp', NOW(),
    'data', jsonb_build_object(
      'annotation', to_jsonb(NEW),
      'article', to_jsonb(article_record)
    )
  );

  -- Queue webhook deliveries
  FOR webhook IN
    SELECT * FROM public.webhooks
    WHERE is_active = true
    AND 'annotation.created' = ANY(events)
    AND workspace_id = article_record.workspace_id
  LOOP
    INSERT INTO public.webhook_deliveries (webhook_id, event_type, payload)
    VALUES (webhook.id, 'annotation.created', payload);
  END LOOP;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER webhook_on_annotation_created
  AFTER INSERT ON public.annotations
  FOR EACH ROW EXECUTE FUNCTION notify_webhook_on_annotation();
