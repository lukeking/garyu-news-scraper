# Research: 熱點報告標示來源涵蓋的日期區間

資料量測都是 2026-11-02 對 prod 的唯讀查詢（腳本在 scratch、沒有進 repo；數字寫在下面）。

## R1 日期存在哪裡：每個焦點事件帶自己的發布時間

**Decision**: 報告的 `source_article_links`（JSONB 陣列）每一項加 `published`（來源文章的發布時間原字串）。
產生報告時由 `src/analyzer.py` 的 `analyze_hot_topic`／`analyze_category_digest` 寫進 `ordered_articles`；既有的報告一次回填。
區間不存成欄位，由前端從這些 `published` 算。

**Rationale**:

- 不改 schema：prod 的 migration 要到 dashboard 手動套用，少一個上線步驟就少一個會漏的步驟。
- 不改 Worker：`handleHotTopics` 原樣轉送 `source_article_links`（`workers/api/src/index.js:206`）；`src/publisher.py` 的
  `hot_topics.json` 也是原樣轉送。Worker 沒有測試 runner，不動它最安全。
- 區間跟著卡片列出的那幾篇走（FR-001），讀者看到的焦點事件就是算區間的對象，不會兩邊對不上。

**Alternatives considered**:

- `hot_topic_reports` 加兩欄（最早／最晚日期）：要 migration、Worker 要多 select、`publisher.py` 要多帶，三處都要改，換到的只是
  前端少算一次 min/max。
- 沿用 `latest_source_date`：一般報告用整個 bucket 算（`scripts/traffic_weekly_analysis.py` 的 `day_set`），而且 novelty gate
  依它判斷（`src/topic_scoring.py` 的 `prior.latest_source_date`）。改它的語意會動到選題，不能碰。
- Worker 在回應時用 link 查 `articles`：一次要查約 600 個 link，查詢字串長度有風險，又是沒有測試的那一層。

## R2 區間在前端算，以台灣時間的日期顯示

**Decision**: `pages/shared/app.js` 新增純函式，輸入一份報告的 `source_article_links`，輸出最早／最晚的台灣日期
（`Intl.DateTimeFormat`，`timeZone: 'Asia/Taipei'`）；卡片 meta 列顯示「新聞發布 09-29～11-01」。同一天只寫一個日期；
兩端不同年才寫年份。沒有任何可用日期的報告不顯示。

**Rationale**: 量測 599／599 個來源發布時間都是「日期 T 時間 ± 時區」，`new Date()` 解析不會有歧義；固定 `Asia/Taipei`
與 PR #117 把相對時間釘成 zh-TW 是同一個判準（不跟瀏覽器 locale 走）。純函式可以用 `tests/js/harness.mjs` 在 jsdom 裡對
真正出貨的 `app.js` 測。

**Alternatives considered**: 在 Python 端先算好字串存進報告——顯示格式一改就要重新回填，格式應該住在顯示它的地方。

## R3 回填既有的 56 份報告

**Decision**: 一次性腳本 `scripts/backfill_hot_topic_source_dates.py`：

- 預設 dry-run，只印每份報告要補幾項、找不到幾項；`--apply` 才寫。
- 用 `id` 對 `hot_topic_reports` 做 update，只動 `source_article_links`；`week_start_date`、`topic_label` 不碰（分享連結的錨點，FR-004）。
- 每一項：dict 加上 `published`；舊的純字串項目（11 項，在 2025-01-06 測試殘留、2026-05-18、2026-05-25 三份）轉成
  `{"link": …, "published": …}`。前端對 dict 顯示 `title || link`，沒有 title 時顯示的仍是 link，畫面不變。
- 找不到對應文章的項目（3 項）不補 `published`，印出 link 與原因；已經有 `published` 的項目不覆寫。重跑結果相同（冪等）。
- 寫完逐份讀回，比對每一項的 `published` 與 `articles` 的值；不一致就 exit 非 0。

**Rationale**: 只讀查詢量到的形狀：602 項，591 項是 `{link, summary, title}`、11 項是純字串；找不到 3 項；找得到的 599 項
0 個空值。來源是已分析的文章，`expire_buffer_articles` 不會刪它們（`src/storage.py` 只刪 `hot_topic_analyzed=FALSE`），
所以補得到。

**Alternatives considered**: 用 `upsert_hot_topic_report` 重寫整列——它會再把來源標成已分析、而且以 `(week_start_date,
topic_label)` 為鍵，回填不需要也不該觸發這些副作用。

**寫入目的地**（`test-write-destination` 規則）：這支腳本的目的地就是 prod，是刻意指定，不是從環境撿來的。`--apply` 前
印出目標 host（URL 不是憑證）與要更新的列數，dry-run 先跑一次給人看。

## R4 ★ 只標列進報告的文章（plan 階段的裁示）

**Decision**: 前端在載入報告清單時建一張「link → 報告週次」的對照（同一篇在多份報告就收多個週次）。文章列的 ★ 與加強樣式
改看「這篇的 link 在不在對照裡」，不再看 `hot_topic_analyzed`；提示寫「已納入 2026-W45 的熱點報告」（多份就列多個週次）。
報告清單載入失敗時對照是空的，★ 全部不顯示。

**Rationale**: spec 011 對 ★ 的定義是「已進入熱點報告的」文章，但 `hot_topic_analyzed` 也包含彙整時沒選進報告、只被消耗
的文章（09-08～11-02 有 205 篇，GNS-011 的 11-02 量測）。Luke 2026-11-02 裁示 ★ 只標列進報告的。資料已經在前端：交通頁
`init` 一開始就載入整份報告清單，`handleHotTopics` 不帶上限。

**Alternatives considered**: Worker 回傳文章時多帶一個「在哪些報告裡」的欄位——要改 Worker 的查詢與回應形狀，資料前端已經有。

## R5 簽核用的實際畫面

**Decision**: 實作前先做 spike：`pages/traffic/index.html` 原樣、`app.js` 用 spike 版，`window.__API_BASE__` 指到本機的
stub（從 prod 公開 API 抓 `/api/hot-topics` 與兩個週次的 JSON，焦點事件補上從 DB 唯讀查到的 `published`）。用本機已有的
Chromium（`~/.cache/ms-playwright/chromium-1223/`）以 412 px 寬截亮、暗兩張（主題由 `localStorage.theme` 決定，見
`pages/traffic/index.html` 的開頭 script），再加一張桌面寬度。截圖給 Luke 簽核後才寫正式的前端實作。

**Rationale**: Luke 的手機約 412 CSS px、日常用深色（`claims-and-verification` §一）；簽核要看實際渲染，不看文字描述或 ASCII
（`learning-style`）。spike 不進 repo。

## R6 GUB-20261101-9qe（spec-kit 範本副本）

`/speckit-plan` 觸發了 bare 的這條提醒。查證：garyu 的 plan-template 副本沒有 gate、與 user 層共用範本逐位元組相同，不在 9qe
的四個 repo 名單上。Luke 2026-11-02 裁示不併入本 spec，另以 PR #196 刪掉副本（已 merge）。本 plan 用的是 user 層範本。
