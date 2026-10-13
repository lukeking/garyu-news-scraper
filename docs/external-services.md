# 外部服務：方案、預算與限流設定

憲章原則 IV 規定「每個外部服務都要有寫下來的預算，超過要看得見」，但值不寫在憲章裡——值會變，憲章不該跟著改。
這份是那些值的所在。改方案、換模型、調 timeout，改這份與對應的設定，開一般的 PR，不修憲。

每列附「最後確認」日期：這是快照，以設定檔與實際帳單為準；與現況不符時更新這裡。

| 服務 | 用途 | 方案／預算 | 限流與上限設在哪裡 | 最後確認 |
|---|---|---|---|---|
| Gemini API | 文章分析、熱點彙整、embedding | pay-as-you-go（Tier 1），2026-06-22 Luke 由免費層轉換；預算上限：未訂（轉換當時估算全管線約 $1／月） | 模型：GitHub 變數 `GEMINI_MODEL_NAME`（prod `gemini-3.7-flash`）；分析間隔：`src/analyzer.py` 的 `analyze_all(delay=…)`；每次篇數：`src/pipeline/ffxiv.py` 的 `max_articles`、`config/pipeline_config.yml` 的 digest `max_articles` 與 `max_hot_topics`；embedding 重試：`EMBED_RETRY_BUDGET_SECONDS` | 2026-10-13 |
| GitHub Actions | daily buffer、週報、部署、測試 | repo 是 public，標準 runner 不計分鐘；自訂預算每月 ≤ 2,000 分鐘（近 30 天實測約 148 分鐘） | 每個 workflow job 的 `timeout-minutes`（週報 30：實測最長 15.2 分；tests 10；其餘 20）。值寫在各 workflow 檔 | 2026-10-13 |
| Supabase | 文章、buffer、熱點報告、KB | 免費方案（推論：`weekly.yml` 有「Ping Supabase（防免費 tier 閒置暫停）」） | 讀取分頁：`src/storage.py` 的 `_fetch_all_pages` | 2026-10-13 |
| YouTube Data API | 交通 YouTube 頻道收集 | 未記錄 | 每頻道 `max_items`、`lookback_days`（來源設定） | — |
| Cloudflare（Worker、Pages） | 公開 API、前端 | 未記錄 | — | — |

「未記錄」是誠實的空格，不是沒有預算——下次碰到該服務時補上。
