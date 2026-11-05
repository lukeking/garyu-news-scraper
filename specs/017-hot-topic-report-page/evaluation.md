# Evaluation: 熱點報告與新文章拆成兩條流

merge 前的驗證紀錄。merge 之後在 prod 跑的（T020）留言在 PR 上，回填 `spec.md` 的達成階數。

## T009 FR-009、SC-004：從 prod 刪除測試殘留的報告

**時間**：2026-11-05 22:2x（+0800），本機。Luke 同日同意刪除（互動式問答，看過 id、標籤、日期與總數之後）。
**腳本**：scratch 的一次性腳本，以 `python-dotenv` 載入本機 `.env`、用 `src/storage.py` 的 `_get_client()` 連線；預設唯讀，
`--delete <id>` 只刪那個 id，而且條件同時帶 `topic_label = '酒駕-integration-test'`，刪完再讀一次。只印目標 host，不印金鑰。

唯讀（刪除前）：

```text
target host: gxlmcipjqjgslgtoqqgg.supabase.co
[before] total rows in hot_topic_reports: 56
[before] rows with topic_label = '酒駕-integration-test': 1
  id=5a4dfda3-f8b1-4974-8457-8b1523e96614 week_start_date=2025-01-06 created_at=2026-07-21T12:37:51.246882+00:00 source_article_links=1
read-only: nothing deleted
```

刪除與讀回：

```text
[after] total rows in hot_topic_reports: 55
[after] rows with topic_label = '酒駕-integration-test': 0
delta total: -1
```

公開 Worker API（`https://garyu-news-scraper.lukeking0325.workers.dev/api/hot-topics`，前端讀的同一份）：55 份報告，
`topic_label` 含 `integration-test` 的 0 份。

**影響面**：新意檢查只讀最近 8 週的報告（`src/storage.py` 的 `get_recent_hot_topic_reports(max_age_weeks=8)`），2025-01-06 不在範圍內；
另一個讀這張表的是 `scripts/measure_relevance.py`。`created_at` 2026-07-21 就是那次整合測試寫進正式庫的時間
（`tests/integration/conftest.py` 之後強制指向本機）。

**結論**：通過。熱點那一條拿到的報告數＝真報告數 55（SC-004 的前半；在 prod 資料上渲染的那一半是 T016）。
