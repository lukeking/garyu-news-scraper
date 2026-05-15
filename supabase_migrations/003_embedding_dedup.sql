-- Migration 003: Embedding Dedup
-- Adds pgvector support and a 768-dim embedding column for traffic articles.
-- Apply via Supabase dashboard SQL Editor.

-- Enable pgvector extension (idempotent; already available in Supabase)
CREATE EXTENSION IF NOT EXISTS vector;

-- Embedding column: 768-dim MRL truncation of Gemini Embedding 2 (default 3072)
ALTER TABLE articles
  ADD COLUMN IF NOT EXISTS embedding vector(768);

-- Index for future pgvector similarity queries (optional; not used by current Python-side dedup)
CREATE INDEX IF NOT EXISTS idx_articles_traffic_embedding
  ON articles USING ivfflat (embedding vector_cosine_ops)
  WHERE content_type = 'traffic' AND embedding IS NOT NULL;
