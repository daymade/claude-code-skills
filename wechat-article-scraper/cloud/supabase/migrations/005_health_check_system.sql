-- Health Check System v3.47.0
-- Database functions for comprehensive health monitoring

-- Function to check pgvector extension
CREATE OR REPLACE FUNCTION check_pgvector()
RETURNS BOOLEAN AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM pg_extension WHERE extname = 'vector'
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to get system metrics
CREATE OR REPLACE FUNCTION get_system_metrics()
RETURNS TABLE (
  active_connections BIGINT,
  pending_jobs BIGINT,
  failed_jobs BIGINT,
  error_rate NUMERIC,
  total_articles BIGINT,
  annotations_count BIGINT
) AS $$
BEGIN
  RETURN QUERY
  SELECT
    -- Active connections (approximate from pg_stat_activity)
    (SELECT COUNT(*) FROM pg_stat_activity WHERE state = 'active')::BIGINT AS active_connections,

    -- Pending export jobs
    (SELECT COUNT(*) FROM public.export_jobs WHERE status = 'pending')::BIGINT AS pending_jobs,

    -- Failed jobs in last hour
    (SELECT COUNT(*) FROM public.export_jobs
     WHERE status = 'failed'
     AND updated_at > NOW() - INTERVAL '1 hour')::BIGINT AS failed_jobs,

    -- Error rate (failed / total in last hour)
    COALESCE(
      (SELECT
        COUNT(*) FILTER (WHERE status = 'failed')::NUMERIC /
        NULLIF(COUNT(*)::NUMERIC, 0)
       FROM public.export_jobs
       WHERE updated_at > NOW() - INTERVAL '1 hour'),
      0
    ) AS error_rate,

    -- Total articles
    (SELECT COUNT(*) FROM public.articles)::BIGINT AS total_articles,

    -- Total annotations
    (SELECT COUNT(*) FROM public.annotations)::BIGINT AS annotations_count;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Table for storing health check history
CREATE TABLE public.health_check_history (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  status TEXT NOT NULL CHECK (status IN ('healthy', 'degraded', 'unhealthy')),
  services JSONB NOT NULL,
  metrics JSONB NOT NULL,
  checked_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for time-based queries
CREATE INDEX idx_health_check_history_checked_at ON public.health_check_history(checked_at DESC);

-- Function to log health check
CREATE OR REPLACE FUNCTION log_health_check(
  p_status TEXT,
  p_services JSONB,
  p_metrics JSONB
)
RETURNS UUID AS $$
DECLARE
  v_id UUID;
BEGIN
  INSERT INTO public.health_check_history (status, services, metrics)
  VALUES (p_status, p_services, p_metrics)
  RETURNING id INTO v_id;

  -- Clean up old records (keep last 7 days)
  DELETE FROM public.health_check_history
  WHERE checked_at < NOW() - INTERVAL '7 days';

  RETURN v_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- View for health check trends
CREATE OR REPLACE VIEW health_check_trends AS
SELECT
  DATE_TRUNC('hour', checked_at) AS hour,
  status,
  COUNT(*) AS count,
  AVG((metrics->>'responseTime')::NUMERIC) AS avg_response_time
FROM public.health_check_history
GROUP BY DATE_TRUNC('hour', checked_at), status
ORDER BY hour DESC;

-- Function to get service availability percentage
CREATE OR REPLACE FUNCTION get_service_availability(
  p_service TEXT,
  p_hours INTEGER DEFAULT 24
)
RETURNS NUMERIC AS $$
DECLARE
  v_total BIGINT;
  v_up BIGINT;
BEGIN
  SELECT
    COUNT(*),
    COUNT(*) FILTER (WHERE (services->p_service->>'status') = 'up')
  INTO v_total, v_up
  FROM public.health_check_history
  WHERE checked_at > NOW() - (p_hours || ' hours')::INTERVAL;

  RETURN COALESCE(v_up::NUMERIC / NULLIF(v_total, 0) * 100, 0);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- RLS for health check history (admin only)
ALTER TABLE public.health_check_history ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Health check history viewable by admins"
  ON public.health_check_history FOR SELECT
  USING (EXISTS (
    SELECT 1 FROM public.profiles
    WHERE id = auth.uid() AND role = 'admin'
  ));
