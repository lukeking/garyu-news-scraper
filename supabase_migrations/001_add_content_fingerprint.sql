-- 既有資料庫：於 Supabase SQL Editor 執行（測試階段可先 TRUNCATE articles;）
-- 新專案請直接跑完整 supabase_schema.sql 即可，無需再執行本檔。

ALTER TABLE articles
    ADD COLUMN IF NOT EXISTS content_fingerprint TEXT;

COMMENT ON COLUMN articles.content_fingerprint IS
    'Stable sha256 hex for rows without a real URL; NULL when link is canonical.';

CREATE INDEX IF NOT EXISTS idx_articles_content_fingerprint
    ON articles(content_fingerprint)
    WHERE content_fingerprint IS NOT NULL;
