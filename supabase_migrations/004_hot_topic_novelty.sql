-- Migration 004: Hot-topic novelty gate basis
-- Adds columns to hot_topic_reports so the weekly analysis can compare a topic
-- against its previous report (novelty gate, feature 009). Apply via Supabase
-- dashboard SQL Editor.

ALTER TABLE hot_topic_reports
  ADD COLUMN IF NOT EXISTS topic_token_signature JSONB DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS latest_source_date    DATE;
