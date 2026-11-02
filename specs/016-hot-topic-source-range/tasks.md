---

description: "Task list for 016-hot-topic-source-range"
---

# Tasks: 熱點報告標示來源涵蓋的日期區間

> Markers: [ ] not started · [-] implemented, awaiting review · [X] reviewed + verified (verification-only task: main-verified)

**Input**: Design documents from `/specs/016-hot-topic-source-range/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/hot-topics-api.md, contracts/hot-topic-card-ui.md, contracts/log-lines.md, quickstart.md

**Tests**: **要。** 本 repo 接了 delegated-TDD；每個實作 task 前面有一個會因為「還沒實作」而紅的測試 task。
JS 用 `tests/js/harness.mjs` 在 jsdom 裡跑真正出貨的 `pages/shared/app.js`。

**Task markers are three-state**（本 repo 的 delegated-TDD 接線）：
`[ ]` 未開始 → `[-]` 已實作、待審 → `[X]` 已審且 main 驗證過 → `[~]` 移出範圍
驗證型 task（main 跑真實入口、記下結果，沒有實作）由 main 驗證即可標 `[X]`，不派 reviewer：T001、T009、T012、T017。

## Format: `[ID] [P?] [Story] [Req] Description`

- **[P]**: 可平行（不同檔案、無未完成依賴）
- **[Story]**: 對應 spec.md 的 user story
- **[Req]**: 這個 task 實作或驗證的 spec 需求編號

## Path Conventions

單一 repo：`src/`、`scripts/`、`pages/shared/`、`tests/unit/`、`tests/js/` 皆在根目錄。
⚠️ `python` 不在 PATH，一律用 `.venv/bin/python`。新檔的註解／docstring 區塊 ≤ 3 行（`tests/unit/test_comment_budget.py`）。
⚠️ 測試不打網路、不連 DB：Supabase client、`_get_api_key`、`_call_gemini` 一律替換；只替換邊界，不替換被測邏輯。

---

## Phase 1: 簽核畫面（實作前）

**Purpose**: FR-008 要求寫正式的前端之前，Luke 先看過亮、暗兩個主題的實際畫面；兩條 Unchecked 假設也在這裡由 Luke 判。

- [ ] T001 [FR-001, FR-003, FR-007, FR-008, SC-004] 驗證型（Luke 簽核）：照 `specs/016-hot-topic-source-range/quickstart.md` §2
      在 scratch 做 spike（stub 資料取自 prod 公開 API，焦點事件補 DB 唯讀查到的 `published`；`pages/traffic/index.html` 原樣、
      spike 版 `app.js`），用本機 Chromium 截 412 px 亮、暗各一張（W45 的報告卡片、W44 的 ★），再加一張桌面寬度，送給 Luke。
      同時請 Luke 判 spec Assumptions 的兩條 Unchecked：區間用焦點事件算（不用整個 bucket）；卡片「N 篇來源」與焦點事件篇數不一致
      會不會讓人困惑。簽核的字樣、位置與 ★ 提示寫回 `specs/016-hot-topic-source-range/contracts/hot-topic-card-ui.md`；
      兩條假設的結果寫回 `specs/016-hot-topic-source-range/spec.md` 的 Assumptions（改成 Checked 並附 Luke 的話，或照他的話改寫）。

---

## Phase 2: Foundational

本 spec 沒有阻擋所有 story 的前置：資料形狀只多一個選用欄位，前端對舊形狀都容忍（contracts/hot-topics-api.md）。

---

## Phase 3: User Story 2 - 已經分享出去的連結照樣打開原本那份報告 (Priority: P1)

**Goal**: 鎖住分享連結的錨點，讓後面改卡片時不會無聲改掉它。排在 US1 之前，因為它鎖的是現狀。

**Independent Test**: 這條測試在 T007 之前與之後都綠。

- [ ] T002 [P] [US2] [FR-004, SC-002] `tests/js/hot-topic-card.test.mjs`（新檔）：用字面值鎖住 `renderHotTopics` 產生的卡片 `id`
      （`topic-<slug>`）與 LINE 分享 URL（`?week=<ISO 週>#topic-<slug>`），有日期與沒日期的報告各一份；`tests/js/harness.mjs` 的
      `EXPORTED` 加 `renderHotTopics`、`isoWeekId`、`slugify`。對現行 `app.js` 跑應該是綠的（它鎖現狀，不是新行為）。

---

## Phase 4: User Story 1 - 讀者看得出報告講的是哪段時間的新聞 (Priority: P1) 🎯 MVP

**Goal**: 每張報告卡片顯示焦點事件的發布日期區間（含既有報告）；★ 只標列進報告的文章。

**Independent Test**: 打開任一有報告的週次，每張卡片的區間對得上焦點事件逐篇的最早／最晚日期；★ 都對得到一份報告的焦點事件。

### Tests

- [ ] T003 [P] [US1] [FR-005] `tests/unit/test_hot_topic_source_dates.py`（新檔）：回填轉換純函式——dict 項目補 `published`；純字串項目
      轉成 `{link, published}`；已有 `published` 的不覆寫；找不到文章的項目不補、列進 missing；同一份輸入轉兩次結果相同。先紅。
- [ ] T004 [P] [US1] [FR-001, FR-002, FR-003] `tests/js/hot-topic-card.test.mjs`：區間計算與格式——兩端同年、同一天、跨年、
      沒有任何可用日期（不顯示）、混合舊形狀（dict 沒有 `published`、純字串）、台灣時區跨日（例 `2026-10-31T17:00:00+00:00` 是 11-01）；
      `renderHotTopics` 有區間時顯示簽核過的字樣、沒區間時卡片其餘不變。先紅。
- [ ] T005 [P] [US1] [FR-007, SC-005] `tests/js/hot-topic-card.test.mjs`、`tests/js/traffic-row.test.mjs`：★ 對照——在一份報告裡（提示寫該週）、
      在兩份（週次由舊到新）、不在任何報告裡但 `hot_topic_analyzed=true`（沒有 ★、沒有 `tr-strong`）、報告清單沒載到（全部沒有 ★）、
      純字串項目的 link 也算；既有的「★ 與左邊框」測試改成用對照驅動。先紅。

### Implementation

- [ ] T006 [US1] [FR-004, FR-005] `scripts/backfill_hot_topic_source_dates.py`（新檔）：T003 的純函式＋入口。預設 dry-run：印目標 host、
      每份報告要補幾項、找不到幾項（每項印 link 與原因）；`--apply`：以 `id` update、只寫 `source_article_links`，寫完逐份讀回比對，
      不一致 exit 非 0。用 `src.storage` 的 client，`.env` 由 dotenv 從 repo 根目錄載入。
- [ ] T007 [US1] [FR-001, FR-002, FR-003, FR-008] `pages/shared/app.js`、`pages/shared/shared.css`：區間純函式（`Asia/Taipei`）；
      `renderHotTopics` 在卡片 meta 顯示 T001 簽核的字樣與樣式，亮暗兩個主題都用既有的 CSS 變數。
- [ ] T008 [US1] [FR-007] `pages/shared/app.js`：`init` 載入報告後建 link → 週次對照（`isoWeekId(week_start_date)`，同一 link 收多週）；
      `trafficRow` 的 ★、`tr-strong` 與提示改看對照，不再讀 `hot_topic_analyzed`；降級列不加強的規則不變；FFXIV 路徑不變（FR-009）。

### Verification

- [ ] T009 [US1] [FR-004, FR-005, SC-002] 驗證型：照 quickstart §3 跑回填——先 dry-run 並存回填前的 `(id, week_start_date, topic_label)`，
      **Luke 同意後**才 `--apply`；讀回通過；再跑一次 `--apply` 應為 0 項；回填前後的三元組逐列相同。數字寫進
      `specs/016-hot-topic-source-range/evaluation.md`（新檔）。

---

## Phase 5: User Story 3 - 之後每份新報告自動帶上區間 (Priority: P2)

**Goal**: 週報產生的新報告，焦點事件都帶 `published`。

**Independent Test**: 對兩個分析函式給一批帶 `published` 的文章，回傳的每一項都帶同一個值。

- [ ] T010 [P] [US3] [FR-006, FR-010] `tests/unit/test_hot_topic_source_dates.py`：`analyze_hot_topic`、`analyze_category_digest` 回傳的每一項帶來源的
      `published`；來源沒有 `published` 時該項不帶這欄；`title`、`link`、`summary` 不變（替換 `_get_api_key`、`_call_gemini`）。
      `upsert_hot_topic_report`（假 client＋caplog，照 `tests/unit/test_digest_consume.py` 的做法）：照 contracts/log-lines.md 用字面值斷言
      那一行——全部帶（`2/2`）、部分帶（純字串與沒有 `published` 的 dict 算沒帶）、`0/0` 也印、upsert 失敗時不印；既有的
      `✓ hot_topic_report upserted:` 那行不變。先紅。
- [ ] T011 [US3] [FR-006, FR-010] `src/analyzer.py`：兩個函式組 `ordered_articles` 時加上 `published`（來源有值才帶）。
      `src/storage.py`：`upsert_hot_topic_report` 在既有的成功訊息之後印 contracts/log-lines.md 那一行。

---

## Phase 6: 驗證與 closeout

- [ ] T012 [SC-001, SC-005, FR-009] 驗證型：回填（T009）之後，本機用本分支的 `app.js` 對 prod 公開 API 渲染（`__API_BASE__` 指 prod，只讀）：
      55 份真報告的區間與 DB 算出的最早／最晚逐份比對；W44、W45 兩頁的每個 ★ 對得到報告焦點事件、提示週次正確，只被彙整消耗的沒有 ★；
      FFXIV 頁照舊。結果寫進 `specs/016-hot-topic-source-range/evaluation.md`。
- [ ] T013 [SC-003, FR-010] `routines/weekly-verify/FOCUS.md`：在 merge 後第一個週報那週加一項「016 上線後」——讀週報 Actions log 裡每份報告的
      `✓ hot_topic_report 焦點事件帶發布時間：n/m`（contracts/log-lines.md），全部 `m/m` 為通過；`n < m` 或找不到這一行就標待查、交給本地。
      routine 打不到 Worker API（`PROMPT.md` 的環境段落），不要寫成去讀 `/api/hot-topics`。適用週照現行不動。
- [ ] T014 [SC-001, SC-002, SC-004, SC-005] `specs/016-hot-topic-source-range/spec.md`：加「達成階數」小節（同 015 的形狀），填 merge 前已有的
      結果（T001、T009、T012），SC-003 標「交給 routine」。
- [ ] T015 `specs/BACKLOG.md`：`python3 ~/.agents/bin/backlog.py remove specs/BACKLOG.md GNS-20261031-005` 移出 005（連同小節），
      並核對沒有其他列以它為 blocker。
- [ ] T016 PR 內文（`gh pr edit`）：Principles I–III 的符合情形（Governance 的 Compliance review）；bare `GUB-20261101-9qe` 與
      `GUB-20261024-rcf` 的處置；rcf 的樣本資料（step 2a 停了幾次、Unchecked 幾條與 T001 的結果、plan 階段改寫的假設、
      第一個 review unit 推翻了什麼）；`Backlog:` 行貼 `python3 ~/.agents/bin/backlog_trailers.py pr-line` 的輸出。
- [ ] T017 [SC-001, SC-002, SC-004, SC-005] 驗證型（merge 之後）：`deploy-pages-traffic.yml` 部署完，prod 頁面抽查——兩份報告的分享連結打開到
      原本的週次與卡片、卡片顯示區間、W44 的 ★ 正確；用與 T001 相同的寬度與主題（412 px 亮、暗，加桌面）截 prod 頁面，與簽核的截圖並排比對。
      結果留言在本 PR 上。

---

## Dependencies & Execution Order

- **T001** 在 T007、T008 之前（字樣與樣式要先簽核）；T002～T006、T010、T011 不等它。
- **T002** 在 T007 之前寫好（它鎖的是現狀）。
- 測試在實作之前：T003 → T006；T004 → T007；T005 → T008；T010 → T011。
- **T009** 在 T006 審過之後，而且要 Luke 同意才 `--apply`；**T012** 在 T007、T008、T009 之後。
- **T013～T016** 在 T012 之後（要填數字）；**T017** 在 merge 之後。

### Parallel Opportunities

- T002、T003、T004、T005、T010 都是新寫的測試、分屬不同檔或不相依的段落，可同時寫（T002、T004、T005 同一個新檔，要依序寫入）。
- T006（`scripts/`）、T011（`src/analyzer.py`）、T007＋T008（`pages/shared/app.js`）互不相干，可平行；T007、T008 同檔，依序做。

## Review units

### Unit 1: 簽核畫面與兩條 Unchecked 假設 (verification-only)

- Tasks: T001
- Outcome: Luke 簽核過亮、暗兩張加桌面一張的畫面；簽核的字樣、位置與 ★ 提示寫進 contracts/hot-topic-card-ui.md；兩條 Unchecked 假設有結論並寫回 spec。
- Prerequisites: plan 與 contracts 已定行為；spike 不進 repo。
- Verification: 截圖本身與 Luke 的回覆；repo 裡只多了 contract 與 spec 的紀錄。
- Review: Luke 本人（畫面簽核不是程式審查）；main 讀回寫進 contract 與 spec 的字句與 Luke 的話一致。
- Merge or split: 只有一個產出（簽核）。正式實作（Unit 3、Unit 4）以它為前提，但它們各有自己的驗收，不併進來。
- Unchecked assumptions: 「區間用卡片列出的焦點事件算」與「N 篇來源與焦點事件篇數不一致是否讓人困惑」都由 T001 請 Luke 在畫面上判。

### Unit 2: 回填腳本

- Tasks: T003, T006
- Outcome: `scripts/backfill_hot_topic_source_dates.py` 的轉換符合 data-model 的回填規則；dry-run 不寫入；`--apply` 只寫 `source_article_links`、寫後讀回。
- Prerequisites: data-model.md、contracts/hot-topics-api.md。
- Verification: `.venv/bin/python -m pytest tests/unit -q`；對 prod 跑一次 dry-run（只讀）看輸出。實際寫入在 Unit 6。
- Review: `scripts/backfill_hot_topic_source_dates.py`、`tests/unit/test_hot_topic_source_dates.py`（回填那幾條）、data-model.md。
- Merge or split: 測試與實作是同一個產出。跟 Unit 5 共用測試檔但產出不同（一次性回填 vs 週報產生端），分開審。
- Unchecked assumptions: none（兩條都在 Unit 1）。

### Unit 3: 卡片顯示區間，分享連結不變

- Tasks: T002, T004, T007
- Outcome: 每張報告卡片照簽核的樣子顯示區間；卡片 `id` 與分享 URL 的字面值不變。
- Prerequisites: Unit 1 的簽核；T002 先在現行 `app.js` 上綠。
- Verification: `npm test`；T002 在 T007 前後都綠。
- Review: `pages/shared/app.js`（區間與 `renderHotTopics`）、`pages/shared/shared.css`、`tests/js/hot-topic-card.test.mjs`、`tests/js/harness.mjs`、contracts/hot-topic-card-ui.md。
- Merge or split: 分享連結的鎖是「改卡片不能改掉錨點」這個產出的一部分，跟區間一起審。★ 是另一個行為，見 Unit 4。
- Unchecked assumptions: none。

### Unit 4: ★ 只標列進報告的文章

- Tasks: T005, T008
- Outcome: ★ 與 `tr-strong` 只看 link → 週次對照，提示寫出週次；只被彙整消耗的文章、報告清單沒載到時都沒有 ★。
- Prerequisites: Unit 1 簽核的提示字樣。與 Unit 3 同檔，依序改。
- Verification: `npm test`。
- Review: `pages/shared/app.js`（`init` 的對照與 `trafficRow`）、`tests/js/hot-topic-card.test.mjs`（★ 那幾條）、`tests/js/traffic-row.test.mjs`。
- Merge or split: 跟卡片區間是不同的行為、各有驗收（FR-007／SC-005 vs FR-001～003），同檔不強迫合併。
- Unchecked assumptions: none。

### Unit 5: 新報告的焦點事件帶發布時間

- Tasks: T010, T011
- Outcome: `analyze_hot_topic`、`analyze_category_digest` 回傳的每一項帶來源的 `published`；每寫入一份報告，log 印出
  contracts/log-lines.md 那一行。
- Prerequisites: 無。
- Verification: `.venv/bin/python -m pytest tests/unit -q`；上線後的實際週報由 T013 交給 routine 讀那一行。
- Review: `src/analyzer.py`（兩個函式組 `ordered_articles` 的段落）、`src/storage.py`（`upsert_hot_topic_report`）、
  `tests/unit/test_hot_topic_source_dates.py`（分析與 log 那幾條）、contracts/log-lines.md。
- Merge or split: 產生端帶日期與「帶了幾項」的 log 是同一個產出（新報告自動帶上、而且每週看得到）；跟回填腳本分開（見 Unit 2）。
- Unchecked assumptions: none。

### Unit 6: 回填與真實資料上的驗收 (verification-only)

- Tasks: T009, T012, T017
- Outcome: 56 份報告回填完成並讀回一致、錨點未變；本分支的前端在 prod 資料上 SC-001、SC-005 成立；merge 後 prod 頁面抽查通過，
  畫面與簽核的截圖一致（SC-004 的後半）。
- Prerequisites: Unit 2 審過（T009）；Unit 3、4 審過（T012）；merge 與部署（T017）。
- Verification: 腳本讀回、三元組比對、渲染比對，數字寫進 evaluation.md；T017 的結果留言在 PR 上。
- Review: main 驗證；T009 的 `--apply` 要 Luke 同意。
- Merge or split: 三個都只跑已審過的入口並記錄結果，沒有實作。
- Unchecked assumptions: none。

### Unit 7: closeout 紀錄

- Tasks: T013, T014, T015, T016
- Outcome: routine 接手 SC-003；spec 有達成階數；BACKLOG 移出 005；PR 內文有 Principles I–III、9qe／rcf 的處置與 rcf 樣本資料。
- Prerequisites: Unit 6 的 T009、T012 已有數字。
- Verification: `FOCUS.md` 的新項目指得到 quickstart 的檢查；`backlog.py remove` 的輸出；`backlog_trailers.py pr-line` 與 PR 的 `Backlog:` 行相同。
- Review: `routines/weekly-verify/FOCUS.md`、`specs/016-hot-topic-source-range/spec.md`（達成階數）、`specs/BACKLOG.md`、PR 內文。
- Merge or split: 都是同一個 closeout 的紀錄，彼此對得上才算完成；FOCUS.md 是 routine 的程序，所以不算驗證型。
- Unchecked assumptions: none。

---

## Parallel Example: User Story 1

```bash
# 測試可同時寫（同一個新檔的 T004、T005 依序寫入）：
Task: "T003 回填轉換的測試 in tests/unit/test_hot_topic_source_dates.py"
Task: "T004 區間計算與格式的測試 in tests/js/hot-topic-card.test.mjs"

# 實作分屬不同檔，可平行：
Task: "T006 回填腳本 in scripts/backfill_hot_topic_source_dates.py"
Task: "T011 焦點事件帶 published in src/analyzer.py"
```

---

## Implementation Strategy

1. **先簽核**（T001）：字樣與位置定了才寫前端；兩條 Unchecked 在這裡就有答案。
2. **MVP＝US1**：回填＋卡片區間＋★。回填可以在 merge 之前做（舊前端忽略多出來的欄位，純字串轉成 dict 後畫面不變），所以 T012 能在
   merge 前用真實資料驗收。
3. **US3** 讓之後的週報自動帶日期；它的實際驗收在 merge 後第一個週報，由 routine 接手（T013）。
4. closeout 照 `spec-closeout`：同一個 PR 移出 BACKLOG 的 005、PR 內文填 `Backlog:`。
