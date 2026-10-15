# 外部服務：方案、預算與限流設定

憲章原則 IV 規定「每個外部服務都要有寫下來的預算，超過要看得見」，但值不寫在憲章裡——值會變，憲章不該跟著改。
這份是那些值的所在。改方案、換模型、調 timeout，改這份與對應的設定，開一般的 PR，不修憲。

每列附「最後確認」日期：這是快照，以設定檔與實際帳單為準；與現況不符時更新這裡。

| 服務 | 用途 | 方案／預算 | 限流與上限設在哪裡 | 最後確認 |
|---|---|---|---|---|
| Gemini API | 文章分析、熱點彙整、embedding | pay-as-you-go（Tier 1），2026-06-22 Luke 核准由免費層轉換（當時估算全管線約 US$1／月）。預算上限 NT$300／月（Luke 2026-10-15 訂；AI Studio 的設定幣別是台幣，換算約略低於 US$10，依匯率浮動），由 AI Studio 對 project 設的 Monthly spend cap 執行：到上限 API 暫停到下個月 1 號（生效約延遲 10 分鐘），超過會是看得見的失敗，不是靜默超支。本機 `.env` 與 prod 是同一把 key，實驗也算在同一個 cap 裡 | 模型：GitHub 變數 `GEMINI_MODEL_NAME`（寫 `gemini-3.7-flash`，但 2026-10-08 起 Google 把它自動 route 到 `gemini-3.8-flash`，見 BACKLOG `GNS-20261015-8pg`）；分析間隔：`src/analyzer.py` 的 `analyze_all(delay=…)`；每次篇數：`src/pipeline/ffxiv.py` 的 `max_articles`、`config/pipeline_config.yml` 的 digest `max_articles` 與 `max_hot_topics`；embedding 重試：`EMBED_RETRY_BUDGET_SECONDS` | 2026-10-15 |
| GitHub Actions | daily buffer、週報、部署、測試 | repo 是 public，標準 runner 不計分鐘；自訂預算每月 ≤ 2,000 分鐘（近 30 天實測約 148 分鐘） | 每個 workflow job 的 `timeout-minutes`（週報 30：實測最長 15.2 分；tests 10；其餘 20）。值寫在各 workflow 檔 | 2026-10-13 |
| Supabase | 文章、buffer、熱點報告、KB | Free 方案（Luke 2026-10-15 確認）；預算：免費方案內，不付費。採用 2026-04-29（`0204d17`，由 GitHub artifact 遷入）。`weekly.yml` 的「Ping Supabase」是防免費 tier 閒置暫停 | 讀取分頁：`src/storage.py` 的 `_fetch_all_pages` | 2026-10-15 |
| YouTube Data API | 交通 YouTube 頻道收集 | 預設免費配額：每天 10,000 units；官方配額文件沒有付費加額，要更多只能走 Quota and Compliance Audits。預算：配額內，不付費（Luke 2026-10-15）。採用 2026-05-15（spec 007，PR `#39`）。用量：每次 run 每個頻道最多 3 個 list 呼叫（`channels`、`playlistItems`、`videos` 各 1 unit），4 個頻道 ≤ 12 units | 每頻道 `max_items`、`lookback_days`（來源設定） | 2026-10-15 |
| Cloudflare（Worker、Pages） | 公開 API、前端 | Free 方案（Luke 2026-10-15 確認）；預算：免費方案內，不付費。採用 2026-04-30（`6aec5ce`）。一個 Worker（沒有 KV、D1 等 binding）、兩個 Pages 專案以 `wrangler pages deploy` 直接上傳 | — | 2026-10-15 |

「未記錄」是誠實的空格，不是沒有預算——下次碰到該服務時補上。
