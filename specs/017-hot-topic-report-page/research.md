# Research: 熱點報告與新文章拆成兩條流

量測都是 2026-11-03 對 prod 公開 Worker API 的唯讀請求（從本機 curl；數字寫在下面）。

## R1 一個頁面、兩條流，排法交給 CSS

**Decision**: 交通頁仍是同一個 `pages/traffic/index.html`，裡面放兩個區塊：熱點（`#stream-reports`）與新文章（`#stream-articles`）。
窄螢幕一次只顯示「目前那一條」，上方有切換；寬螢幕兩條並排、切換隱藏。哪一條是目前那一條由 `app.js` 決定（R3），
並排或單欄由 CSS 的寬度斷點決定（R2）。

**Rationale**:

- 桌機並排要求兩條在同一份文件裡；拆成兩個 HTML 頁面就只能靠 iframe 並排，切換也變成整頁跳轉、每次重抓資料。
- 現有的列模型已經是「同一份 DOM、CSS 在斷點切形態」（`pages/shared/app.js` 的 `trafficRow` 註解、BACKLOG #5 的選擇），同一個判準。
- FFXIV 頁共用 `app.js`，但沒有這兩個區塊；新程式碼以 `C.contentType === 'traffic'` 與元素是否存在把關（FR-013）。

**Alternatives considered**: 兩個 HTML 頁面（上面兩個理由否決）；hash 路由的單頁應用（為了兩條流引進路由層，超出需要）。

## R2 並排的寬度斷點：簽核時實測決定

**Decision**: 用 viewport 寬度的 `@media` 切並排（這是整頁版面，不是清單內部的形態，所以不用列模型的 `@container`）。
候選值 1200 px，在簽核畫面時用 1024／1280／1440 三個寬度實測，Luke 定案後寫回 spec FR-002。並排時 `.main` 放寬，兩欄各自捲動。

**Rationale**（推導，不是實測）：文章列要在清單寬度 ≥ 560 px 才切成寬形（`pages/shared/shared.css` 第 210～213 行的註解，
那個 560 本身也是推導）；報告欄放報告內文，估 480～560 px；加上兩側與中間的間距約 50 px，合計約 1100～1180 px。
Luke 11-03：不夠寬就是「左右留白偏多的手機版面而已，還不至於不能接受(實測才知道)」。

## R3 打開時落在哪一條：一個純函式

**Decision**: `landingStream({ link, pref, last })` 回 `'reports'` 或 `'articles'`，優先序：

1. 網址是新格式的報告分享連結，而且那份報告存在 → `'reports'`（FR-015）。
2. 齒輪設定是 `'reports'` 或 `'articles'` → 那一條。
3. 設定是 `'default'`（或沒設）且記得上次 → 上次那一條。
4. 第一次進來 → `'reports'`。

舊格式連結（`?week=…#topic-…`）不參與判斷：`week` 參數照現在的行為選文章那一條的週次，`#topic-` 不再處理（FR-007）。
寬螢幕兩條都顯示，落地只影響窄螢幕，但「上次」照樣記。

**Rationale**: 規則有四層優先序，寫成純函式才能用 `tests/js/harness.mjs` 對出貨的 `app.js` 一層一層測（SC-003）。

## R4 「有新的」怎麼算

**Decision**:

- 每一條在本機存「上次看過」的時間（`local-state.md`）。打開頁面時先讀出來當這次的基準，badge 只算 `created_at` 晚於基準的項目。
- 一條被顯示時（窄螢幕的目前那一條，寬螢幕兩條都算），把它的「上次看過」寫成這次打開的時間。badge 在這次造訪裡持續顯示，
  窄螢幕上讀者從那一條切走時才清掉；下次打開依新的基準重算。
- 第一次進來（兩條都沒有記錄）：兩條的「上次看過」都寫成現在，不顯示 badge（FR-004）。
- 熱點：從已經載入的 `/api/hot-topics` 算，不多打請求；badge 只表示「有新報告」與份數。
- 新文章：在週次清單裡挑出週次 ≥ 基準所在 ISO 週的那幾週，逐週、逐頁（每頁 100 篇）抓 `/api/weeks/<週>?content_type=traffic`，
  不帶篩選，數 `created_at` 晚於基準的篇數。在主畫面畫完之後並行跑，不擋第一眼；任何一個請求失敗就不顯示篇數（寧可不標，不標錯）。
- 上限：最多掃 8 週（憲章原則 IV：每次打開的請求數要有寫明的上限）。基準比 8 週還早時顯示「N+」，N 是 8 週內數到的篇數。

**量測**（2026-11-03）：`/api/weeks/<週>` 每次 0.9～1.5 秒、約 50～100 KB；W44、W43、W42 各要 2 頁。基準是 3 週前時約 6～7 個請求，並行。

**`created_at` 的語意**（Checked）：兩條寫入路徑都不帶 `created_at`（`src/storage.py` 第 172 行的 upsert、第 296 行 buffer 的
`ignore_duplicates=True`），欄位是 `DEFAULT NOW()`（`supabase_migrations/002_traffic_pipeline.sql` 第 29 行），所以它是第一次收進來的時間，
重新收集不會改它。報告的 `created_at` 由 `/api/hot-topics` 回傳（`workers/api/src/index.js` 第 206 行）。

**與 `GNS-20261103-f71` 的關係**：週次清單被截在 1000 列，只影響約 8 週以前的週次；8 週的掃描上限落在清單完整的範圍內。
基準早於清單最舊的週時，照「N+」處理。

**Alternatives considered**: Worker 加一個 `since` 參數直接回篇數——要改沒有測試 runner 的 Worker（`f71` 已記錄要補 runner），
換到的只是少幾個請求；用週次清單的 `article_count` 估算——它是整週總數，不是「上次之後」，而且最舊那週被截斷。

## R5 熱點那一條：依產生的批次瀏覽

**Decision**: 報告依 `week_start_date`（產生那天的週一）分批，新的在前；批次導覽的形狀跟週次導覽一樣（例「11-02 · 2 份」）。
預設是最新一批。每張卡片的 meta 列多一個「11-02 產生」（FR-011）；「N 篇來源 · M 個媒體」照舊。

**測試殘留**：2025-01-06 的 `酒駕-integration-test`（來源 0 篇找得到）從 prod 刪除，Luke 11-03 裁示；前端不寫特例。
刪除是一個要 Luke 同意才跑的 task：先唯讀印出那一列（id、`week_start_date`、`topic_label`、`created_at`），同意後刪除並讀回 0 列。

**Rationale**: 2026-11-03 的 `/api/hot-topics` 有 56 份、25 個產生日期、每個日期最多 3 份，一批的量放得進一個畫面。

## R6 報告分享連結的新格式

**Decision**: 卡片的 LINE 分享改用 `?batch=<YYYY-MM-DD>#report-<slug>`。`batch` 是那份報告的 `week_start_date`，`slug` 沿用現在的
`slugify(topic_label)`。打開時：有 `batch` 參數且那一批裡有那個 slug → 落在熱點、切到那一批、捲到那張卡片；否則照 R3 的其餘規則。

**Rationale**: 每週都有同名的「道安政策 · 彙整」，只帶標題會混淆，所以批次與標題一起帶。用日期不用 ISO 週字串，
是因為熱點那一條的導覽單位就是產生日期；與文章那一條的 `week` 參數分開，舊連結的 `week` 也就不會被誤認成報告連結。

## R7 焦點事件就地展開

**Decision**: 焦點事件的項目有 `summary` 時，標題變成可展開的按鈕，展開顯示摘要與「閱讀原文 →」；沒有 `summary` 的
（舊格式只存連結的 11 項、或摘要是空字串）照現在顯示成連結，不給可展開的空殼。預設收合（FR-010）。

**Rationale**: 與文章列的 `toggleRow` 同一種互動；資料已在 `source_article_links`（016 `research.md` R3：602 項有 591 項是
`{link, summary, title}`）。

## R8 文章列拿掉 ★ 與加強樣式

**Decision**: `trafficRow` 不再讀 `hot_topic_analyzed`：拿掉 ★（`.tr-badge`）與 `tr-strong`，連同它們的 CSS。
`tests/js/traffic-row.test.mjs` 第 44～56 行鎖的是「已分析就有 ★ 與 `tr-strong`」，改成「不論已不已分析都沒有」；
`tests/js/row-model-css.test.mjs` 第 50 行的排序表拿掉 `tr-badge`。API 照樣回 `hot_topic_analyzed`，前端不用它。

**Rationale**: Luke 11-03「buffer 頁面則不需要知道自己被哪一則熱點引用」；加強樣式只由這一項觸發（`strong = !dimmed && analyzed`）。

## R9 不動的部分

Worker（`workers/api/`）、`src/` 的 pipeline 模組、`src/publisher.py`、資料庫結構都不動；唯一的 prod 寫入是 R5 的那一列刪除。
FFXIV 頁照舊（FR-013），用 jsdom 載入 FFXIV 的設定跑一次確認不壞。

## R10 簽核畫面（FR-014、SC-005）

**Decision**: 照 016 T001 的做法在 scratch 做 spike：stub 取自 prod 公開 API，`pages/traffic/index.html` 改成新結構、spike 版 `app.js`，
本機 Chromium（`~/.cache/ms-playwright/chromium-1223/`）截：412 px 亮、暗各兩張（熱點在前、文章 tab 有 badge；文章在前），
齒輪設定展開一張；桌機 1024／1280／1440 各一張（決定 R2 的斷點）。焦點事件展開一張。截圖送 Luke 簽核後才寫正式前端。

## R11 `GUB-20261101-9qe` 不併入

`/speckit-plan` 觸發了 bare 的這條提醒。它的範圍是 expense-tracker、assertion-engine、mapf-router、slot-allocator 的 plan-template 副本；
garyu 不在名單上，副本已由 `#196` 刪除（2026-11-03 查：沒有 `.specify/templates/`，`check_speckit_residue.py` 回 0）。
Luke 2026-11-03 裁示不併入；PR 內文照記。提醒會在 garyu 每次 `/speckit-plan` 都響，是因為 `on:` 宣告沒有 repo 範圍的鍵
（`~/.agents/docs/exp054-pre-edit.md`「`on:` 宣告」）。
