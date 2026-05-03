-- 002_add_content_type.sql
-- Adds content_type column to the articles table to distinguish
-- traffic news from FFXIV content.
--
-- Safe to run multiple times (IF NOT EXISTS guards).
-- Existing rows default to 'traffic' with no backfill needed.
--
-- Run in: Supabase Dashboard → SQL Editor → paste and execute.

ALTER TABLE articles
  ADD COLUMN IF NOT EXISTS content_type TEXT NOT NULL DEFAULT 'traffic';

CREATE INDEX IF NOT EXISTS articles_content_type_idx
  ON articles (content_type);
