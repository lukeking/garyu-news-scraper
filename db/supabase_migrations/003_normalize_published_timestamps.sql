-- 003_normalize_published_timestamps.sql
-- Changes published from TEXT to TIMESTAMPTZ, converting mixed formats in-place.
--
-- Handles two formats that accumulated in the column:
--   RFC 2822  e.g. 'Fri, 01 May 2026 03:59:11 GMT'  (from RSS 2.0 feeds)
--   ISO 8601  e.g. '2026-05-05T03:31:08+00:00'       (from Atom feeds)
-- Empty strings become NULL.
--
-- Safe to run once. Run in: Supabase Dashboard → SQL Editor → paste and execute.

ALTER TABLE articles
  ALTER COLUMN published TYPE TIMESTAMPTZ
  USING CASE
    WHEN published IS NULL OR published = ''
      THEN NULL
    WHEN published ~ '^\d{4}-\d{2}-\d{2}T'
      THEN published::TIMESTAMPTZ
    WHEN published ~ '^\w{3},\s+'
      THEN to_timestamp(
             regexp_replace(published, '^\w+,\s+', ''),
             'DD Mon YYYY HH24:MI:SS TZ'
           )
    ELSE NULL
  END;

CREATE INDEX IF NOT EXISTS idx_articles_published
  ON articles (published DESC);
