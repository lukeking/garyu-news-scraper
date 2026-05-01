# 儲存方案遷移紀錄

> 狀態：已切換至 Supabase + Cloudflare Workers API
> 更新日期：2026-04-30

## 最終架構

```
GitHub Actions（每週一）
  ↓
main.py / publisher.py
  ↓
Supabase（articles）
  ↓
Cloudflare Worker API（/api/weeks, /api/weeks/:id, /api/tags）
  ↓
Cloudflare Pages 前端（docs/index.html）
```

## 已完成項目

- 週報資料持久化寫入 Supabase（`storage.py` / `publisher.py`）。
- 無原始 URL 之文章以 **title + source + published** 正規化後 **sha256** 產生穩定 `link`（`urn:traffic-issue-scraper:{week_id}:{hex}`）與欄位 `content_fingerprint`，避免 workflow 重跑、順序改變時重複插入。遷移見 `supabase_migrations/001_add_content_fingerprint.sql`。
- 前端改為呼叫 API 讀取週別、文章、標籤與搜尋過濾。
- 移除 GitHub Pages artifact/deploy 對資料讀取鏈路的依賴。
- 新增 Worker 專案：`workers/api`。
- 使用歷史資料回補腳本：`backfill_supabase.py`。

## Worker API 規格（目前）

- `GET /api/weeks`：回傳週別索引（`week_id`, `article_count`, `high_count`）。
- `GET /api/weeks/:week_id`：回傳該週文章清單。
  - 支援查詢參數：`importance`, `tag`, `q`, `limit`, `offset`。
- `GET /api/tags`：回傳標籤聚合資料（`ai_tags`, `user_tags`）。

## 必要環境變數

### GitHub Actions（weekly pipeline）

- `SUPABASE_URL`
- `SUPABASE_KEY`

### Cloudflare Worker（runtime secret/vars）

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

## 歷史資料回補

```bash
python backfill_supabase.py --dry-run
python backfill_supabase.py
```

## 待你在平台上完成的設定

1. 在 Cloudflare Workers 設定 `SUPABASE_SERVICE_ROLE_KEY` secret。
2. 將 Cloudflare Pages 網站的 `/api/*` 路由指向 Worker。
3. 設定 GitHub secrets：`CLOUDFLARE_API_TOKEN`、`CLOUDFLARE_ACCOUNT_ID`（若使用自動部署 workflow）。