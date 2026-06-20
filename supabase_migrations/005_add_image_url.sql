-- Migration 005: Article image URL for RSS feeds
-- Adds a nullable image_url column to articles, populated best-effort from source
-- RSS media (media:thumbnail / media:content / enclosure / first <img>) at collection.
-- The Worker RSS feed emits it as <enclosure>/<media:content>. Apply via Supabase
-- dashboard SQL Editor. Backward-compatible: existing rows stay NULL until re-collected.

ALTER TABLE articles
  ADD COLUMN IF NOT EXISTS image_url TEXT;
