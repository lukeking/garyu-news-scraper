---

description: "Task list for 017-hot-topic-report-page"
---

# Tasks: 熱點報告與新文章拆成兩條流

> Markers: [ ] not started · [-] implemented, awaiting review · [X] reviewed + verified (verification-only task: main-verified)

**Input**: Design documents from `/specs/017-hot-topic-report-page/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/traffic-streams-ui.md, contracts/local-state.md, quickstart.md

**Tests**: **要。** 本 repo 接了 delegated-TDD；每個實作 task 前面有一個會因為「還沒實作」而紅的測試 task。
JS 用 `tests/js/harness.mjs` 在 jsdom 裡跑真正出貨的 `pages/shared/app.js`。版面（並排斷點）沒有 runner，靠簽核截圖與上線後的截圖比對。

**Task markers are three-state**（本 repo 的 delegated-TDD 接線）：
`[ ]` 未開始 → `[-]` 已實作、待審 → `[X]` 已審且 main 驗證過 → `[~]` 移出範圍
驗證型 task（main 跑真實入口、記下結果，沒有實作）由 main 驗證即可標 `[X]`，不派 reviewer：T001、T002、T009、T016、T020。

## Format: `[ID] [P?] [Story] [Req] Description`

- **[P]**: 可平行（不同檔案、無未完成依賴）
- **[Story]**: 對應 spec.md 的 user story
- **[Req]**: 這個 task 實作或驗證的 spec 需求編號

## Path Conventions

單一 repo：`pages/traffic/`、`pages/shared/`、`tests/js/` 皆在根目錄。`workers/`、`src/`、`scripts/` 不動。
⚠️ `python` 不在 PATH，一律用 `.venv/bin/python`。新檔的註解區塊 ≤ 3 行（`tests/unit/test_comment_budget.py`，pre-commit 會跑）。
⚠️ JS 測試不打網路：`fetch` 一律由 harness 注入 stub；`localStorage` 用 jsdom 的，初值由 harness 寫入。只替換邊界，不替換被測邏輯。
⚠️ `pages/shared/app.js` 是全域腳本、結尾是 `init();`（harness 靠這一行把它拿掉）；不要改成 ESM、不要改結尾形狀。

---

## Phase 1: 簽核畫面與量測（實作前）

**Purpose**: FR-014 要求寫正式的前端之前，Luke 先看過兩個主題的實際畫面；三條 Unchecked 假設也在這裡判。

- [X] T001 [FR-002, FR-004, FR-005, FR-006, FR-010, FR-014, SC-005] 驗證型（Luke 簽核）：照 `specs/017-hot-topic-report-page/quickstart.md` §2
      在 scratch 做 spike（stub 取自 prod 公開 API；新結構的 `index.html`、spike 版 `app.js`／`shared.css`），用本機 Chromium 截：
      412 px 亮、暗各一組（熱點在前且「新文章」鈕上有 badge、新文章在前、齒輪面板展開、焦點事件展開），桌機 1024／1280／1440 px 各一張。
      送給 Luke，同時請他判 spec Assumptions 的兩條 Unchecked：「標記與設定只存在這台裝置」（他是不是也常在桌機看）、
      「報告的產生方式與資料不改」。簽核的字樣、位置與並排斷點寫回 `specs/017-hot-topic-report-page/contracts/traffic-streams-ui.md`
      與 spec FR-002；兩條假設的結果寫回 spec 的 Assumptions（改成 Checked 並附 Luke 的話，或照他的話改寫）。
      → 2026-11-04 簽核：斷點 1024 px、畫面元素照截圖、批次導覽改一列橫捲；兩條假設都 Checked；另外裁示 FR-016（整週載入）併入、
      簽核拼圖與截圖腳本進 `signoff/`。記錄在 spec Clarifications「Session 2026-11-04」、contracts/traffic-streams-ui.md、research R2／R10／R12。
- [X] T002 [FR-004, SC-002] 驗證型：在 scratch 寫一支 Node 腳本，照 research R4 的掃法對 prod 公開 API 實測「數新文章」：基準分別是
      3 天前、3 週前、10 週前（超過 8 週上限），每種記下要打幾個請求、並行的總時間、算出的篇數與是否觸頂（`N+`）。
      結果寫進 `specs/017-hot-topic-report-page/research.md` R4 的「量測」。這條驗 spec 的 Unchecked 假設「數新文章不會讓打開變慢到不能接受」：
      3 週前那種的並行總時間超過 5 秒，就把數字帶回 T001 請 Luke 判（備案：只標「有新的」不標篇數）。5 秒是純判斷（手機上等 badge
      出現的容忍度，沒有量過），不是門檻的推導；數字一律帶給 Luke 看，5 秒只決定要不要主動提備案。
      → 2026-11-04：3 天前 3 個請求 0.96～1.51 秒、3 週前 7 個 1.23～1.80 秒、10 週前 15 個 1.47～1.82 秒（「1129+」）；未超過 5 秒，
      數字已給 Luke、spec 的這條假設改成 Checked。全文在 research R4。

---

## Phase 2: Foundational

- [X] T003 `tests/js/harness.mjs`：`loadApp(config, opts)` 多三個選項，預設值讓既有測試不變——`html`（載入時的 body，預設現在的空 body）、
      `storage`（寫進 jsdom `localStorage` 的初值物件）、`fetch`（替換 `window.fetch` 的 stub，預設照舊 reject）；`exports`（這個測試檔要的
      函式名，預設照現在的 `EXPORTED`；要的名字不存在時照舊 throw）。另外 export `FFXIV_CONFIG`（與 `pages/ffxiv/index.html` 的 `SITE_CONFIG` 同形，
      只放被測函式會讀的欄位）。`npm test` 既有的測試全綠。

---

## Phase 3: User Story 1 - 熱點報告與新文章是兩條各自的流 (Priority: P1) 🎯 MVP

**Goal**: 熱點依產生批次、新文章依收集週次，各自有導覽；窄螢幕一次一條可切換、寬螢幕並排；文章列沒有 ★。

**Independent Test**: 412 px 下切換兩條、各自的導覽只動自己；桌機寬度並排；新文章那一條任何週次都沒有報告與 ★。

- [X] T004 [P] [US1] [FR-001, FR-003, FR-011, FR-013] `tests/js/traffic-streams.test.mjs`（新檔）：
      `reportBatches(reports)` 依 `week_start_date` 分組、新的在前、標籤字面值是 `11-02 · 2 份`；`renderReportStream(batches, date)` 把那一批的每份報告
      畫進 `#stream-reports`，每張卡片的 meta 列有所屬週報的字樣（T001 簽核的字面值 `11-02 週報`，不可以是「產生」），切到另一批只換這一條；`setStream('articles')` 讓 `#stream-articles` 拿到 `active`、
      `#stream-reports` 沒有，切換鈕的 `aria-selected` 跟著換；`loadWeek` 之後 `#stream-articles` 裡沒有任何報告卡片；stub 讓 `/api/hot-topics`
      失敗時，熱點那一條出現 contracts/traffic-streams-ui.md 的失敗字樣、新文章那一條照常畫出；用 `FFXIV_CONFIG` 載入 `pages/ffxiv/index.html` 的 body，
      在 `exports` 加 `init`、以 stub fetch 呼叫 `init()` 並 `await` 它結束，不 throw、頁面上沒有切換鈕與齒輪。字面值用 2026-11-02、2026-10-26 兩批（各 2 份）寫死。
- [X] T005 [US1] [FR-001, FR-003, FR-011, FR-013] `pages/shared/app.js`：新增 `reportBatches`、`renderReportStream`、`setStream`；`init` 在交通頁把報告清單
      畫進熱點那一條（預設最新一批、批次導覽），`loadWeek` 不再呼叫 `renderHotTopics`；報告清單載入失敗時熱點那一條顯示
      contracts/traffic-streams-ui.md 的失敗字樣，新文章那一條照常。新程式碼以 `C.contentType === 'traffic'` 與元素是否存在把關（FFXIV 不受影響）。
- [X] T006 [US1] [FR-001, FR-002, FR-014] `pages/traffic/index.html`、`pages/shared/shared.css`：照 T001 簽核的畫面改結構——頁首加齒輪鈕的位置、
      頁首下方兩個切換鈕、`#stream-reports`（批次導覽＋報告列表）與 `#stream-articles`（搜尋、週次導覽、標籤列、統計、文章列表）；
      窄螢幕只顯示 `.active` 那一條，`@media (min-width: 1024px)`（T001 簽核）兩條並排、各自捲動、切換鈕隱藏；批次導覽一列、左右捲動、
      不折行（週次導覽照舊）；其餘視覺照 contracts/traffic-streams-ui.md 標「簽核」的各條。`pages/ffxiv/index.html` 不改。
- [X] T007 [P] [US1] [FR-008] `tests/js/traffic-row.test.mjs`：把第 44～56 行「已分析的列要有 ★／`tr-strong`」改成「`hot_topic_analyzed` 是 true 或 false，
      列裡都沒有 `tr-badge`、沒有 `tr-strong`」（含降級列）；`tests/js/row-model-css.test.mjs`：第 50 行的排序表拿掉 `tr-badge`，並斷言
      `shared.css` 裡已經沒有 `.tr-badge`、`.tr-strong` 規則。
- [X] T008 [US1] [FR-008] `pages/shared/app.js` 的 `trafficRow`：不再讀 `hot_topic_analyzed`，拿掉 ★ 與 `tr-strong`；`pages/shared/shared.css` 刪掉
      `.tr-strong`、`.tr-strong .tr-title`、`.tr-badge` 的規則（含寬形斷點裡的 `order`）。
- [X] T009 [US1] [FR-009, SC-004] 驗證型（要 Luke 同意才寫 prod）：照 quickstart §3，在 scratch 寫一支載入本機設定的唯讀腳本，印出目標 host 與
      `hot_topic_reports` 裡 `topic_label = '酒駕-integration-test'` 的列（id、`week_start_date`、`created_at`、`source_article_links` 項數）與總列數；
      Luke 同意後刪除那一列，讀回同條件 0 列、總數少 1。指令與輸出摘要寫進 `specs/017-hot-topic-report-page/evaluation.md`（新檔）。
      刪除不影響選題：新意檢查只讀最近 8 週的報告（`src/storage.py:408` 的 `get_recent_hot_topic_reports(max_age_weeks=8)`），2025-01-06 不在範圍內；
      另一個讀這張表的是量測腳本 `scripts/measure_relevance.py`（2026-11-03 查）。

**Checkpoint**: 兩條流成立、文章列沒有 ★；測試殘留已刪。

---

## Phase 4: User Story 2 - 一眼看出哪一條有新的 (Priority: P1)

**Goal**: 兩條各自標出上次看過之後的新內容；看過、切走之後清掉；第一次進來不標。

**Independent Test**: 用預先寫好的「上次看過」打開，badge 數字與 stub 資料一致；切走之後清掉。

- [X] T021 [P] [US2] [FR-016] `tests/js/traffic-streams.test.mjs`：stub 的某週 `article_count` 是 135 時，`loadWeek` 抓 `offset=0` 與 `offset=100` 兩頁
      （兩次都帶同樣的 `content_type` 與篩選參數），畫出 135 篇的列、統計是 135（扣掉收起的來源）；`article_count` 是 81 時只打一個請求；
      第二頁失敗時顯示現在的「載入失敗」，不畫出只有半週的列表。
- [X] T022 [US2] [FR-016] `pages/shared/app.js` 的 `loadWeek`：先抓第一頁，`article_count` 超過 100 就並行補抓其餘頁再合併畫出（research R12）。
      在 T005 之後（同一個函式）。
- [X] T010 [P] [US2] [FR-004, SC-002] `tests/js/traffic-streams.test.mjs`：
      `countNewSince(items, sinceIso)` 只算 `created_at` 嚴格晚於基準的（等於不算、壞日期不算）；`weeksToScan(weeks, sinceIso, 8)` 回
      `{ weekIds, capped }`——週次是基準換成**台灣時間**的 ISO 週（`src/pipeline/traffic.py` 的 `_current_week_id` 用台灣時間切週）起到最新、
      最多 8 週，基準早於第 8 週時 `capped: true`（用 2026-11-02 00:30 +08:00 這種跨週邊界的基準寫一條，UTC 會落在前一週）；
      `newArticleCount(weeks, sinceIso)` 用 stub fetch 逐週逐頁（每頁 100，`article_count` 超過 100 的要抓第二頁）數出篇數，收起的來源
      （`isSourceHidden`）不算，任何一個請求失敗回 `null`；
      `badgeText(23, false)` 是 `23`、`badgeText(23, true)` 是 `23+`、`badgeText(0, …)` 是空字串；第一次打開（`traffic_seen_*` 都沒有）時兩條的
      `traffic_seen_*` 都被寫成現在、不顯示 badge；有基準時，被顯示的那一條的 `traffic_seen_*` 改成這次打開的時間，另一條不動；窄螢幕切走之後
      那一條的 badge 清掉。localStorage 的鍵名照 contracts/local-state.md 寫死。
- [X] T011 [US2] [FR-004] `pages/shared/app.js`（`countNewSince`、`weeksToScan`、`newArticleCount`、`badgeText`、讀寫 `traffic_seen_*`）與
      `pages/shared/shared.css`（badge 的樣式，照 T001 簽核）：主畫面畫完之後並行計數、不擋第一眼；8 週的上限寫成呼叫處旁邊的常數（憲章原則 IV）；
      計數失敗不顯示篇數。

**Checkpoint**: badge 依 contracts/traffic-streams-ui.md 出現與清除。

---

## Phase 5: User Story 3 - 打開時落在讀者要的那一條 (Priority: P2)

**Goal**: 記得上次（第一次進熱點），齒輪可固定；新分享連結打開那份報告；舊連結不壞。

**Independent Test**: SC-003 的五個情境在 jsdom 裡各跑一次；55 份報告的分享連結各自解析回同一份。

- [X] T012 [P] [US3] [FR-005, FR-006, FR-007, FR-015, SC-003] `tests/js/traffic-streams.test.mjs`：
      `landingStream({ link, pref, last })` 四層優先序各一條（有效的報告連結 → `reports`；`pref` 是 `reports`／`articles` → 那一條；
      `pref` 是 `default` 或沒有、`last` 有值 → `last`；都沒有 → `reports`），`traffic_stream_pref` 存了不認得的值時當成 `default`；
      `reportShareUrl(report, base)` 的字面值是 `<base>?batch=2026-11-02#report-<slugify(topic_label)>`；`parseReportLink(search, hash, batches)`
      對兩份同名「道安政策 · 彙整」（2026-11-02、2026-10-26）各自解析回自己那一份，批次或 slug 對不到回 `null`，舊格式
      `?week=2026-W45#topic-…` 回 `null`；齒輪面板選了「新文章」之後 `traffic_stream_pref` 是 `articles`；窄螢幕上 `traffic_stream_last` 在打開時的落地
      （包括由固定設定決定的那次）與每次切換都寫成目前那一條。
- [X] T013 [US3] [FR-005, FR-006, FR-007, FR-015] `pages/shared/app.js`（`landingStream`、`reportShareUrl`、`parseReportLink`、齒輪面板、`init` 的落地
      與捲到 `#report-<slug>`；報告卡片的 LINE 分享改用新連結；`scrollToHashTopic` 與 `#topic-` 的處理拿掉）、`pages/traffic/index.html`（齒輪面板）、
      `pages/shared/shared.css`（齒輪面板的樣式，照 T001 簽核）。舊格式的 `week` 參數照現在選新文章那一條的週次。

**Checkpoint**: 五個落地情境與新分享連結都成立。

---

## Phase 6: User Story 4 - 在報告裡就看得到它引用的文章 (Priority: P3)

**Goal**: 焦點事件就地展開摘要與原文連結；沒有摘要的照舊是連結。

**Independent Test**: 報告卡片的焦點事件點一下展開、再點收合；舊格式項目沒有可展開的空殼。

- [X] T014 [P] [US4] [FR-010, SC-006] `tests/js/traffic-streams.test.mjs`：`{link, title, summary}` 的焦點事件畫成可展開的按鈕，展開區預設
      `hidden`、內含摘要（經 `esc`）與指向 `link` 的「閱讀原文 →」；點一下展開、再點收合；純字串項目與 `summary` 是空字串的項目畫成一般連結、
      沒有展開鈕。
- [X] T015 [US4] [FR-010] `pages/shared/app.js`（報告卡片的焦點事件改用可展開的項目與切換函式）、`pages/shared/shared.css`（展開區樣式，照 T001 簽核）。

**Checkpoint**: 四個 story 都成立。

---

## Phase 6b: 版面常數的真實 layout 測試（`GNS-006`，2026-11-04 併入）

**Goal**: `560px`、`5em`、`1024px` 與批次導覽的折行規則都有在 Chromium 上跑、改錯就紅的測試，在 CI 的 `unit` job 跑（SC-007、research R13）；
批次導覽改成只有窄螢幕一列、並排時折行（Luke 2026-11-04）。

- [X] T024 [SC-007] `package.json`（devDependency `playwright`、script `test:layout` ＝ `node --test 'tests/layout/**/*.test.mjs'`）、`package-lock.json`、
      `tests/layout/harness.mjs`（啟 Chromium；`node:http` 送 `pages/traffic/`；`page.route` 把 Worker API 換成 `tests/layout/fixtures/` 的 JSON、
      cdnjs 的 `modern-normalize` 2.0.0 換成 vendored 副本、其餘外部請求 abort）、`tests/layout/fixtures/`（文章與報告各一份最小資料；
      另一份 24 批的報告給折行測試）；`.github/workflows/tests.yml` 的 `unit` job 在 `npm test` 之後加 `npx playwright install --with-deps chromium`
      與 `npm run test:layout`。`npm test` 的 glob 不能撈到 `tests/layout/`。
- [X] T025 [P] [SC-007] `tests/layout/row-model.test.mjs`：視窗 591 與 592 px（文章列表 559／560 px）時 `.tr-slot` 一個顯示、一個藏起；
      寬形裡時間是「10 分鐘前」的列 `.tr-time` 不溢出（測試名寫明「在 CI 的字型下」），時間不同的列寬幅條左緣 x 相同。
      這兩個常數現在就是對的：咬合用改值證明（560→600、5em→3em 各讓對應的測試紅），寫進 executor 的回報。
- [X] T026 [P] [FR-002, SC-007] `tests/layout/streams.test.mjs`：1023 px 切換鈕顯示、只看得到目前那一條；1024 px 切換鈕隱藏、兩條左右並排
      （同一個 top、熱點在左）；批次導覽在 412 px 所有按鈕同一個 `offsetTop` 且可橫捲，在 1280 px 至少兩個不同的 `offsetTop`。
      最後這條在現在的 CSS 上是紅的（Unit 2 做成所有寬度一列）。
- [X] T027 [FR-002] `pages/shared/shared.css`：批次導覽的一列橫捲只在小於 1024 px 時生效，並排時照 `.week-nav` 折行。

**Checkpoint**: `npm run test:layout` 綠、每條有改值咬合的紀錄；CI 的 `unit` job 跑到它。

---

## Phase 6c: T023 找到的缺口補測試（Luke 2026-11-05 裁示）

**Goal**: spec-wide review（T023，PR `#198` 的留言）確認的 GAP 裡，有實作可測的三條與一條 caller edge 補上咬得到的測試；
其餘（FR-009、SC-004 是 prod 資料，T009／T016 驗；FR-013 由 T016 的 FFXIV 截圖比對；標籤、搜尋、重要度 handler 與 subtitle 這 4 條邊緣
在 017 之前就沒有測試、017 也沒改那些 handler）記成接受，理由在 PR 留言。

- [X] T029 [FR-011] `tests/js/traffic-streams.test.mjs`：報告卡片的批次標籤取 `week_start_date`、不取 `created_at`——fixture 的 `created_at`
      與 `week_start_date` 不同天（例：週報在 11-04 手動 dispatch，`week_start_date` 11-02），卡片寫「11-02 週報」、不出現「11-04」。
      現在的實作已經對：咬合用「卡片改顯示 `created_at` 的日期」證明會紅。
- [X] T030 [SC-006] `tests/js/traffic-streams.test.mjs`：窄螢幕上在熱點那一條展開、收合焦點事件，`.stream.active` 一直是熱點、
      `traffic_stream_last` 不變。咬合：`toggleFocus` 裡加 `setStream('articles')` 會紅。
- [X] T031 [SC-007] 新的 `tests/js/ci-wiring.test.mjs`：讀 `.github/workflows/tests.yml`，`unit` job 的步驟依序有 `npm test`、
      `npx playwright install --with-deps chromium`、`npm run test:layout`。咬合：把 `npm run test:layout` 改成 `echo skip` 會紅。
- [X] T032 [FR-016] `tests/js/traffic-streams.test.mjs`：從週次導覽點一個週次（執行出貨的 onclick 字串），新文章那一條載入那一週的全部文章
      （`article_count` 超過 100 的那週全部畫出、`#week-nav .active` 換過去）。咬合：onclick 改成 `loadWeek('')` 會紅。

**Checkpoint**: 四條都有改值咬合的紀錄；`npm test` 綠。

---

## Phase 7: 真實資料上的驗收與 closeout

- [X] T023 驗證型（main 派審、記錄）：Unit 2～6 都 `[X]` 之後、T016 之前，照 `~/.agents/skills/delegated-tdd/spec-reviewer-template.md`
      派一個 `spec-reviewer`（bare `GUB-025` 的第一個實際用例，Luke 2026-11-04 放行），逐條檢查 017 的 FR／SC 有沒有咬得到的測試、
      改動的直接呼叫端有沒有被測到；main 抽驗它的結果，矩陣與 GAP 清單留言在 PR `#198`；GAP 怎麼處理（補測試、記成接受、或照 spec-kit
      `converge` 寫回 tasks.md）由 Luke 裁示，要補的另開 task。
- [X] T016 [SC-003, SC-004] 驗證型：T009 刪除之後、merge 之前，本機用本分支的 `app.js` 對 prod 公開 API 渲染（`__API_BASE__` 指 prod，只讀）：
      熱點那一條瀏覽得到的報告數是 55、沒有 `酒駕-integration-test`；55 份報告各自的 `reportShareUrl` 打開後都落在熱點、那一批、那張卡片（55／55，
      含同名報告）；用 FFXIV 的設定打開 FFXIV 頁畫面照舊。數字寫進 `specs/017-hot-topic-report-page/evaluation.md`。
- [X] T017 [SC-001, SC-002, SC-003, SC-004, SC-005, SC-006] `specs/017-hot-topic-report-page/spec.md`：加「達成階數」小節（同 015 的形狀），
      填 merge 前已有的結果（T002、T009、T016、各 unit 的測試），上線後才有的（T020）標成待填。
- [X] T018 `specs/BACKLOG.md`：`python3 ~/.agents/bin/backlog.py remove specs/BACKLOG.md GNS-20261031-005` 移出 005（連同小節），`GNS-006` 同樣移出
      （2026-11-04 併入，SC-007；先確認它的完成標準都達成，並重推導以它為 blocker 的下游列）；
      重新讀 `GNS-20261103-n9n` 的觸發點（「spec 017 上線之後」）確認仍成立；讀 diff。
- [X] T028 `src/publisher.py` 約第 389 行的 docstring：拿掉「前端 `renderHotTopics()` 讀 `hot_topics.json`」那句（函式在 Unit 2 已刪，前端本來就讀
      `/api/hot-topics`），改成真實的讀者或直接刪掉；只改註解、對執行期零影響。動手前跑 BACKLOG pre-edit 檢查；`tests/unit/test_comment_budget.py`
      的 `LEGACY` 若列了這個檔，行數變了要一起改。Luke 2026-11-04 裁示 017 順手改。
- [X] T019 PR 內文（`gh pr edit`）：不動 pipeline 模組，除了 T028 那句註解（Principles I–III 不需逐條驗，仍寫明）；實際做法與簽核結果；bare `GUB-025` 的處置
      （017 當首例，Luke 2026-11-04 放行，結果在 T023 的 PR 留言）；`GNS-006` 併入（Unit 9）與第一次 CI 的實際耗時；`GNS-20261021-5yg` 在本 PR 排進佇列（`Backlog-reviewed`）；bare `GUB-20261101-9qe`
      不併入（garyu 不在範圍、副本已由 `#196` 刪除）；bare `GUB-20261024-rcf` 的樣本資料（017：Unchecked 3 條、step 2a 停 0 次、T001 對兩條假設的
      裁示、第一個 review unit 推翻了什麼；016：每道閘都過了，意圖面的錯到 T001 簽核畫面才被抓到，PR `#197`）；`GNS-20261020-rhd` 的延後；
      `Backlog:` 行貼 `python3 ~/.agents/bin/backlog_trailers.py pr-line` 的輸出、不手寫。
- [ ] T020 [SC-001, SC-002, SC-003, SC-005, SC-006] 驗證型（merge 之後）：`deploy-pages-traffic.yml` 部署完，照 quickstart §4 在 prod 跑 SC-001、
      SC-002（badge 與資料庫唯讀查詢的列數比，不與 Worker API 比）、SC-003 的五個情境、SC-006，並用 `signoff/shoot.mjs` 截 prod 頁面與
      `signoff/2026-11-04-*.jpg` 並排比對（SC-005）；結果留言在 PR 上，回填 T017 的待填欄。

---

## Dependencies & Execution Order

- **Phase 1（T001、T002）**：最先。T006、T011、T013、T015 的樣式以 T001 的簽核為準；T002 的數字可能改變 T011 的做法。
- **T003** 在所有測試 task 之前。
- **US1（T004～T009）**：T004 → T005 → T006；T007 → T008（跟 T005 同檔，依序改）；T009 隨時可做（只要 Luke 同意），但要在 T016 之前。
- **US2（T021、T022、T010、T011）**、**US3（T012、T013）** 依賴 US1 的切換鈕與兩個 stream 區塊；T022 改的 `loadWeek` 在 T005 之後；**US4（T014、T015）** 依賴 US1 的報告卡片。
  四個 story 的實作都改 `pages/shared/app.js`，依序做。
- **Phase 6b（T024～T027）**：T024 → T025、T026（[P]）→ T027；改 `shared.css`，排在 Unit 2 之後，與其他 unit 依序。
- **Phase 7**：T023 在 Unit 2～6、Unit 9 都 `[X]` 之後、T016 之前；T016 在 T009 與 US1～US4 之後；T017～T019 在 T016 之後；T020 在 merge 之後。

### Parallel Opportunities

- T001 與 T002 可以同時做（都在 scratch）。
- 測試 task（T004、T007、T010、T012、T014）都標 [P]：同一個新測試檔的不同段落可以先寫好，但各自要在對應的實作 task 之前紅。

---

## Review units

### Unit 1: 簽核畫面、計數量測與三條 Unchecked 假設 (verification-only)

- Tasks: T001, T002
- Outcome: Luke 簽核過 412 px 亮、暗與桌機三個寬度的畫面，字樣、位置與並排斷點寫進 contracts/traffic-streams-ui.md 與 spec FR-002；
  數新文章的實測數字寫進 research R4；三條 Unchecked 假設都有結論並寫回 spec。
- Prerequisites: plan 與 contracts 已定行為；spike 與量測腳本不進 repo（簽核拼圖與截圖腳本 2026-11-04 Luke 裁示進 `signoff/`）。
- Verification: 截圖本身與 Luke 的回覆；T002 的請求數與時間；repo 裡只多了 contract、spec、research、quickstart 的紀錄與 `signoff/`（拼圖＋截圖腳本）。
- Review: Luke 本人（畫面簽核不是程式審查）；main 讀回寫進 contract、spec、research 的字句與 Luke 的話、量測輸出一致。
- Merge or split: 簽核與量測都在實作前回答「做成什麼樣」，T002 的結果可能改變 T001 要請 Luke 判的東西，所以同一個 unit。
- Unchecked assumptions: 「數新文章不會讓打開變慢到不能接受」由 T002 實測；「標記與設定只存在這台裝置」與「報告的產生方式與資料不改」由 T001 請 Luke 判。

### Unit 2: 兩條流的骨架

- Tasks: T003, T004, T005, T006
- Outcome: 交通頁是兩條各自有導覽的流：熱點依週報批次（預設最新一批、卡片寫所屬週報），新文章照現在的週次；窄螢幕一次一條可切換、
  寬螢幕並排；新文章那一條沒有報告；FFXIV 頁不受影響。
- Prerequisites: Unit 1 的簽核（版面與斷點）。
- Verification: `npm test`（T004 在 T005 之前紅、之後綠；既有測試在 T003 之後仍綠）；版面另由 T020 對簽核截圖比對。
- Review: `tests/js/harness.mjs`、`tests/js/traffic-streams.test.mjs`（US1 那幾條）、`pages/shared/app.js`（`reportBatches`、`renderReportStream`、
  `setStream`、`init`、`loadWeek`）、`pages/traffic/index.html`、`pages/shared/shared.css`（兩條流的版面）、contracts/traffic-streams-ui.md。
- Merge or split: harness 的擴充是這組測試能跑的前提，跟它們一起審；結構與樣式是同一個產出（兩條流）的兩面。★ 是另一個行為，見 Unit 3。
- Unchecked assumptions: none（都在 Unit 1）。

### Unit 3: 文章列拿掉 ★ 與加強樣式

- Tasks: T007, T008
- Outcome: 不論 `hot_topic_analyzed` 是什麼，文章列都沒有 ★、沒有 `tr-strong`；CSS 裡沒有它們的規則。
- Prerequisites: 無（與 Unit 2 同檔 `app.js`、`shared.css`，依序改）。
- Verification: `npm test`（T007 在 T008 之前紅）。
- Review: `pages/shared/app.js`（`trafficRow`）、`pages/shared/shared.css`（刪掉的規則）、`tests/js/traffic-row.test.mjs`、`tests/js/row-model-css.test.mjs`。
- Merge or split: 跟兩條流是不同的行為、各有驗收（FR-008 vs FR-001～003），同檔不強迫合併。
- Unchecked assumptions: none。

### Unit 4: 「有新的」標記

- Tasks: T021, T022, T010, T011
- Outcome: 新文章那一條每週載入整週（FR-016）；兩條各自依「上次看過」標出新內容；第一次不標；看過、切走之後清掉；新文章最多掃 8 週，超出顯示 `N+`；計數失敗不標。
- Prerequisites: Unit 2 的切換鈕與 stream 標頭；Unit 1 的 T002 數字。
- Verification: `npm test`（T021 在 T022 之前紅、T010 在 T011 之前紅）。
- Review: `pages/shared/app.js`（`loadWeek` 的分頁、計數與 `traffic_seen_*`）、`pages/shared/shared.css`（badge）、`tests/js/traffic-streams.test.mjs`（US2 那幾條）、
  contracts/local-state.md、data-model.md 的狀態轉換。
- Merge or split: 一個產出（badge 與它要對得上的頁面篇數）：FR-016 是 2026-11-04 為了讓 badge 的篇數在頁面上找得到而併入的，同一組審；落地規則雖然也讀寫 localStorage，但驗收不同（FR-005 vs FR-004），分到 Unit 5。
- Unchecked assumptions: none。

### Unit 5: 落地規則、齒輪設定與新分享連結

- Tasks: T012, T013
- Outcome: 打開時依 `landingStream` 落地；齒輪三個選項存在本機；報告卡片的分享連結打開那份報告；舊格式連結不壞。
- Prerequisites: Unit 2 的兩條流與報告卡片。
- Verification: `npm test`（T012 在 T013 之前紅）；55／55 的真實資料驗收在 T016。
- Review: `pages/shared/app.js`（`landingStream`、`reportShareUrl`、`parseReportLink`、齒輪、`init` 的落地）、`pages/traffic/index.html`（齒輪面板）、
  `pages/shared/shared.css`、`tests/js/traffic-streams.test.mjs`（US3 那幾條）、contracts/traffic-streams-ui.md 的「網址」。
- Merge or split: 分享連結是落地規則的第一優先，同一個函式決定，一起審。
- Unchecked assumptions: none。

### Unit 6: 焦點事件就地展開

- Tasks: T014, T015
- Outcome: 有摘要的焦點事件可展開看摘要與原文連結，預設收合；沒有摘要的是一般連結。
- Prerequisites: Unit 2 的報告卡片。
- Verification: `npm test`（T014 在 T015 之前紅）。
- Review: `pages/shared/app.js`（焦點事件的渲染與切換）、`pages/shared/shared.css`、`tests/js/traffic-streams.test.mjs`（US4 那幾條）。
- Merge or split: 一個產出；跟報告卡片的其他部分（Unit 2、Unit 5）各有驗收。
- Unchecked assumptions: none。

### Unit 9: 版面常數的真實 layout 測試（`GNS-006`）

- Tasks: T024, T025, T026, T027
- Outcome: `npm run test:layout` 在 Chromium 上量 `560px`、`5em`、`1024px` 與批次導覽的折行，改錯任一個值就紅，並在 CI 的 `unit` job 跑；
  批次導覽只有窄螢幕一列。
- Prerequisites: Unit 2 的頁面結構（`#stream-reports`、`#batch-nav`、`.stream-switch`）。
- Verification: `npm run test:layout`（T026 的折行那條在 T027 之前紅）；每個常數的改值咬合；PR 的 `unit` check 有跑到 `test:layout`。
- Review: `package.json`、`package-lock.json`、`tests/layout/`、`.github/workflows/tests.yml`、`pages/shared/shared.css`（批次導覽）、research R13。
- Merge or split: 測試基礎建設與它第一批要守的常數是同一個產出（沒有被守的常數，harness 證明不了什麼）；批次導覽的折行是
  用同一個 harness 才測得到的那條規則，一起審。
- Unchecked assumptions: none（字型的界線寫在 R13）。

### Unit 10: T023 缺口的測試

- Tasks: T029, T030, T031, T032
- Outcome: FR-011、SC-006、SC-007 與「週次導覽 → loadWeek」這條 caller edge 各有一條改錯就紅的測試。
- Prerequisites: T023 的矩陣（PR `#198` 留言）與 Luke 的處置裁示。
- Verification: 每條的改值咬合；`npm test`。
- Review: `tests/js/traffic-streams.test.mjs`、`tests/js/ci-wiring.test.mjs`。
- Merge or split: 都只加測試、不動實作，一起審。
- Unchecked assumptions: none。

### Unit 7: 真實資料上的驗收 (verification-only)

- Tasks: T009, T023, T016, T020
- Outcome: 測試殘留已從 prod 刪除並讀回；本分支的前端在 prod 資料上 SC-003（55／55）、SC-004 成立；merge 後 prod 頁面通過 SC-001、SC-002、
  SC-003、SC-006，畫面與簽核一致（SC-005）。
- Prerequisites: T009 要 Luke 同意；T016 在 Unit 2～6 審過之後；T020 在 merge 與部署之後。
- Verification: 刪除前後的讀回、渲染比對，數字寫進 evaluation.md；T020 的結果留言在 PR 上。
- Review: main 驗證；T009 的刪除要 Luke 同意。
- Merge or split: 三個都只跑既有入口（或一次性的唯讀／刪除指令）並記錄結果，repo 裡沒有實作。
- Unchecked assumptions: none。

### Unit 8: closeout 紀錄

- Tasks: T017, T018, T019, T028
- Outcome: spec 有達成階數；BACKLOG 移出 005、下游列的觸發點仍成立；PR 內文有不動 pipeline 的說明、9qe／rcf 的處置與 rcf 樣本資料、rhd 的延後、
  `pr-line` 產生的 `Backlog:` 行。
- Prerequisites: Unit 7 的 T009、T016 已有數字。
- Verification: `backlog.py remove` 的輸出與 diff；`backlog_trailers.py pr-line` 與 PR 的 `Backlog:` 行相同。
- Review: `specs/017-hot-topic-report-page/spec.md`（達成階數）、`specs/BACKLOG.md`、PR 內文、`src/publisher.py`（T028 的註解）。
- Merge or split: 都是同一個 closeout 的紀錄，彼此對得上才算完成。
- Unchecked assumptions: none。

---

## Parallel Example: User Story 1

```bash
# T001 簽核與 T002 量測可以同時在 scratch 進行
Task: "T001 spike 截圖：412 px 亮暗、桌機 1024／1280／1440"
Task: "T002 Node 腳本：基準 3 天、3 週、10 週的請求數與並行時間"

# T004 與 T007 是不同的測試檔，可以同時寫（各自在 T005、T008 之前紅）
Task: "T004 tests/js/traffic-streams.test.mjs 的 US1 段落"
Task: "T007 tests/js/traffic-row.test.mjs、tests/js/row-model-css.test.mjs"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Unit 1：簽核畫面、計數量測、三條假設
2. Unit 2、Unit 3：兩條流＋拿掉 ★——這兩個做完，`GNS-20261031-005` 的核心（不同時間帶不在同一個頁面）就成立
3. **STOP and VALIDATE**：本機 412 px 與桌機各看一次

### Incremental Delivery

1. Unit 4（badge）→ Unit 5（落地、齒輪、分享連結）→ Unit 6（焦點事件展開）
2. Unit 7 的 T009、T023 → Unit 10 → T016 → Unit 8 → PR ready → merge → T020
3. 一個 spec 一個 PR：`/speckit-tasks` 之後開 draft PR，實作 commit 疊在同一條分支，PR 內文最後才改。

---

## Notes

- 每個實作 task 前面的測試要先紅、紅的是對的那幾條，再實作。
- 驗證型 task 不經 `[-]`；其餘照三態標記，`[X]` 要有 reviewer 的 APPROVED。
- T009 的刪除與 T020 之前的任何 prod 寫入都要 Luke 同意。
