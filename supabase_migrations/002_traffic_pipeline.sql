-- Migration 002: Traffic Pipeline
-- Adds buffer metadata columns to articles; creates hot_topic_reports table.
-- Apply via Supabase dashboard SQL Editor.

-- New columns on articles (nullable; only populated for content_type = 'traffic')
ALTER TABLE articles
  ADD COLUMN IF NOT EXISTS major_category        TEXT,
  ADD COLUMN IF NOT EXISTS initial_quality_score FLOAT4,
  ADD COLUMN IF NOT EXISTS buffered_at           TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS buffer_expires_at     TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS hot_topic_analyzed    BOOLEAN DEFAULT FALSE;

-- Partial index for fast buffer queries
CREATE INDEX IF NOT EXISTS idx_articles_traffic_buffer
  ON articles (major_category, buffer_expires_at)
  WHERE content_type = 'traffic' AND hot_topic_analyzed = FALSE;

-- Hot topic reports produced by the weekly analysis phase
CREATE TABLE IF NOT EXISTS hot_topic_reports (
  id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  week_start_date      DATE        NOT NULL,
  topic_label          TEXT        NOT NULL,
  report_text          TEXT        NOT NULL,
  source_article_count INTEGER     NOT NULL,
  source_article_links JSONB       NOT NULL DEFAULT '[]',
  cumulative_score     FLOAT4      NOT NULL,
  distinct_sources     INTEGER     NOT NULL,
  distinct_days        INTEGER     NOT NULL,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_hot_topic_reports_week_topic UNIQUE (week_start_date, topic_label)
);

CREATE INDEX IF NOT EXISTS idx_hot_topic_reports_week
  ON hot_topic_reports (week_start_date DESC);

-- Explicit grants required for Data API access (Supabase policy change May/Oct 2026)
GRANT SELECT, INSERT, UPDATE, DELETE ON public.hot_topic_reports TO service_role;
ALTER TABLE public.hot_topic_reports ENABLE ROW LEVEL SECURITY;
