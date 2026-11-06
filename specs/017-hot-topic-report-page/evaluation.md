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

## T016 SC-003、SC-004：本分支的前端在 prod 資料上

**時間**：2026-11-05 22:4x（+0800），本機，程式 `5224ebb`（Unit 2～6、9 已審過；之後的 Unit 10 只加測試、不動 `pages/`）。
**做法**：scratch 的 Playwright 腳本，照 `deploy-pages-*.yml` 的組法送本分支的 `pages/`（`index.html` 取自各頁目錄、`app.js`／`shared.css`
取自 `pages/shared/`），Worker API 照常打 prod（只放行 GET），`modern-normalize` 用 `tests/layout/vendor/` 的同版副本，其餘請求 abort 並計數。
視窗 412×915。

```text
reports browsable: 55 in 24 batches; integration-test: 0
same-name labels: 6 (機車事故 · 中時×3、道安政策 · 彙整×16、機車事故 · 機車×7、路口安全 · 新聞網×2…)
share links landing on their card: 52/55
ffxiv base: {"streams":false,"gear":false,"cards":20,"keys":[]}
ffxiv branch: {"streams":false,"gear":false,"cards":20,"keys":[]}
ffxiv screenshots identical: true (2317057 vs 2317057 bytes)
api paths seen: /api/hot-topics /api/tags /api/weeks /api/weeks/2026-W45
other requests blocked: 0
```

那 3 條沒過的是腳本的等待（平滑捲動 800 ms）不夠，不是落點錯：三份都在熱點、對的那一批、對的那張卡片，只是離頁首 4000～5000 px，
800 ms 時卡片頂端還在 152～290 px。等 3 秒重跑同三條，卡片頂端都在 -16 px 左右（其餘 52 條第一次就在 ±120 px 內，確切位置沒印）：

```text
科技執法 · 新聞 2026-10-19: card 2/2 top=-16 … active=stream-reports batch=10-19 · 2 份 cardBatch=10-19 週報
機車事故 · 機車 2026-09-21: card 3/3 top=-15 … active=stream-reports batch=09-21 · 3 份 cardBatch=09-21 週報
機車事故 · TVBS 2026-09-07: card 3/3 top=-16 … active=stream-reports batch=09-07 · 3 份 cardBatch=09-07 週報
```

FFXIV 頁：`main`（`origin/main` 的 worktree）與本分支同一時刻對 prod 各截一張整頁圖，位元組相同；兩邊都沒有兩條流、齒輪，也沒有讀寫 `traffic_*` 鍵。
這也是 T023 把 FR-013 共用 CSS 那半記成接受時的依據。

**結論**：通過。SC-004：熱點那一條瀏覽得到 55 份＝真報告數，測試殘留 0。SC-003 的分享連結那半：55／55 定位到同一份（含 6 組同名報告）。
觀察（不是缺陷，只量了這 3 條）：捲到的卡片頂端在視窗頂端上方約 16 px。

## T020 SC-001、SC-002、SC-003、SC-004、SC-005、SC-006：上線後在 prod

**時間**：2026-11-06 19:55～19:58（+0800），本機。prod 交通頁 `https://garyu-traffic-news.pages.dev`，`deploy-pages-traffic.yml` run `42213283965`
部署 merge commit `ffd9688`（PR `#198`）；部署後 prod 的 `app.js`、`shared.css` 與 `ffd9688` 的 `pages/shared/` 逐位元組相同（sha256 前 16 碼
`b80643a3a0439217`、`ca8bbc19158f9f0d`）。
**做法**：scratch 的 Playwright 腳本（repo 的 `playwright` 1.60.0、預設 Chromium）直接開 prod 頁面，只讀；每個情境一個新的瀏覽器 context，
localStorage 從空的開始（＝清掉站上資料），需要的鍵用 context 的初始 storage 放進去，同一個 context 裡重開分頁會保留頁面自己寫的值。
SC-002 的資料庫那半：scratch 的 Python 腳本在 repo 根目錄執行時自己載入本機設定、斷言目標不是本機，對 prod 唯讀數
`articles`（`content_type=traffic`、`created_at` 晚於基準）與 `hot_topic_reports`（`created_at` 晚於基準）的列數——跟 Worker 給前端的查詢條件相同，
但不經 Worker。SC-005：`signoff/shoot.mjs --url <prod>` 截四張拼圖，跟 `signoff/2026-11-04-*.jpg` 左右並排給 Luke 看。

```text
SC-001 narrow412: 2026-W44: rows=135 cards=0 stars=0 2026-W45: rows=115 cards=0 stars=0; batch 11-02 · 2 份 -> 10-19 · 2 份, week stays 2026-W45 (115篇); week click -> batch stays 10-19 · 2 份; errors=0
SC-001 wide1440: 2026-W44: rows=135 cards=0 stars=0 2026-W45: rows=115 cards=0 stars=0; batch 11-02 · 2 份 -> 10-19 · 2 份, week stays 2026-W45 (115篇); week click -> batch stays 10-19 · 2 份; errors=0
SC-002 badges: reports=新 2 articles=67 (since_articles=2026-11-03T11:55:06.000Z, since_reports=2026-11-01T16:00:00.000Z); errors=0
SC-003 1 清掉站上資料: stream-reports; errors=0
SC-003 2 切到文章、重開: stream-articles; errors=0
SC-003 3 齒輪設成 reports（上次是另一條）: stream-reports; errors=0
SC-003 3 齒輪設成 articles（上次是另一條）: stream-articles; errors=0
SC-003 4 舊格式連結 ?week=2026-W44#topic-test: stream-reports week=2026-W44 (135篇) cards=2; errors=0
SC-004: batches=24 reports=55 integration-test=0; errors=0
SC-006: 機車事故 · 中時 active each step=['stream-reports', 'stream-reports', 'stream-reports'] expanded=2 visible=2; errors=0
DB (read-only): articles(traffic, created_at > 2026-11-03T11:55:06.000Z) = 67; hot_topic_reports(created_at > 2026-11-01T16:00:00.000Z) = 2
```

SC-005：手機亮暗、桌機 1024／1280／1440 亮暗四張並排，Luke 11-06 判定與簽核一致。差在資料（W45 81→115 篇、badge 的基準不同），
以及簽核那張手機拼圖多一格，提交的 `shoot.mjs`（`db67411`）只截 4 個狀態——差在截圖組，不在頁面。

**結論**：通過。SC-001：兩種寬度、W44 與 W45 都只有文章（0 份報告卡片、0 個 ★），兩條的導覽互不牽動。SC-002：badge 2／67 與資料庫 2／67 相同。
SC-003：五個情境 5／5，0 個錯誤。SC-004：55 份、24 批、殘留 0。SC-005：Luke 判定一致。SC-006：讀報告、展開兩個焦點事件時，三個步驟都停在熱點那一條。
全部情境 0 個 JS 錯誤。
