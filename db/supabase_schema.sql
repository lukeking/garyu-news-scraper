-- supabase_schema.sql
-- 在 Supabase SQL Editor 執行此檔案以建立資料表與索引
-- 路徑：Supabase Dashboard → SQL Editor → New query → 貼上執行

-- ── 主資料表 ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS articles (
    id          SERIAL PRIMARY KEY,
    week_id     TEXT NOT NULL,              -- 'YYYY-WNN'，例如 '2026-W18'
    title       TEXT NOT NULL,
    link        TEXT UNIQUE,               -- 去重複鍵；無 URL 時為 urn:traffic-issue-scraper:{week}:{sha256}
    source      TEXT,                      -- 來源名稱，例如 'Google News 機車交通'
    published   TIMESTAMPTZ,               -- 發布時間（UTC，NULL 表示來源未提供）
    summary     TEXT,                      -- AI 產生的摘要（冗餘欄位，方便直接查詢）
    analysis    JSONB,                     -- 完整分析物件（含 importance, tags 等）
    content_fingerprint TEXT,             -- 無 URL 列之 sha256 hex；有正式 link 時為 NULL
    created_at  TIMESTAMPTZ DEFAULT NOW()  -- 寫入時間
);

-- ── 索引 ──────────────────────────────────────────────────────

-- 依週別查詢（最常用）
CREATE INDEX IF NOT EXISTS idx_articles_week_id
    ON articles(week_id);

-- 依重要性篩選（JSONB 表達式索引）
CREATE INDEX IF NOT EXISTS idx_articles_importance
    ON articles((analysis->>'importance'));

-- 依建立時間排序
CREATE INDEX IF NOT EXISTS idx_articles_created_at
    ON articles(created_at DESC);

-- 依發布時間排序
CREATE INDEX IF NOT EXISTS idx_articles_published
    ON articles(published DESC);

-- 無 URL 列依內容指紋查詢（與列表順序無關之 dedup）
CREATE INDEX IF NOT EXISTS idx_articles_content_fingerprint
    ON articles(content_fingerprint)
    WHERE content_fingerprint IS NOT NULL;

-- ── 常用查詢範例 ──────────────────────────────────────────────

-- 取得某週所有文章（依重要性排序）
-- SELECT * FROM articles
-- WHERE week_id = '2026-W18'
-- ORDER BY
--   CASE analysis->>'importance'
--     WHEN '高' THEN 0
--     WHEN '中' THEN 1
--     WHEN '低' THEN 2
--     ELSE 3
--   END,
--   created_at;

-- 統計各週文章數與高重要性數
-- SELECT
--   week_id,
--   COUNT(*) AS total,
--   COUNT(*) FILTER (WHERE analysis->>'importance' = '高') AS high_count
-- FROM articles
-- GROUP BY week_id
-- ORDER BY week_id DESC;

-- 搜尋包含特定標籤的文章
-- SELECT week_id, title, analysis->'tags'
-- FROM articles
-- WHERE analysis->'tags' ? '路權'
-- ORDER BY created_at DESC
-- LIMIT 20;

-- 取得近 4 週的高重要性文章
-- SELECT week_id, title, analysis->>'importance', analysis->>'summary'
-- FROM articles
-- WHERE analysis->>'importance' = '高'
--   AND week_id >= TO_CHAR(NOW() - INTERVAL '4 weeks', 'IYYY"-W"IW')
-- ORDER BY created_at DESC;