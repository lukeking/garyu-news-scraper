---
description: "Task list for 011-buffer-noise-triage"
---

# Tasks: Buffer List 雜訊分流呈現層

**Input**: Design documents from `/specs/011-buffer-noise-triage/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/week-detail-api.md, quickstart.md

**Tests**: 僅 `scripts/measure_source_uptake.py` 有自動化測試（pytest，沿用 repo 既有慣例）。
JS 端刻意不引入測試框架——見 plan.md 的 Complexity Tracking 與 `specs/BACKLOG.md`。
前端驗收依 `quickstart.md` 的手動清單。

**Organization**: 依 user story 分階段。**階段順序刻意不照 P1→P3**，改依 plan.md 的交付順序
（US2 → US1 → US3），使用者已核可。理由見下方 Implementation Strategy。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行（不同檔案、無未完成相依）
- **[Story]**: 對應 spec.md 的 user story

## Path Conventions

三層既有結構：`scripts/`（Python 量測）、`workers/api/src/`（Worker API）、
`pages/shared/`（前端）。本功能**不觸及 `src/`**（Python pipeline）。

---

## Phase 1: Setup

**Purpose**: 建立可比對的基線。無相依套件需安裝——本功能零新增依賴。

- [X] T001 記錄現況基線：挑一個近期週與一個圖片覆蓋率 0% 的舊週，截圖並記下各分組篇數與「找到第一篇想讀文章」的秒數，寫入 `specs/011-buffer-noise-triage/quickstart.md` 的驗證段作為 SC-003 的前後對照
- [X] T002 [P] 確認 `pages/traffic/index.html` 與 `pages/shared/app.js` 的本地預覽方式可用，並記錄於 `specs/011-buffer-noise-triage/quickstart.md`（前端無建置步驟，直接開檔或起靜態伺服器）

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 三個 story 都會修改 `trafficGroups` / `trafficRow` 這同一條渲染路徑。先建立單一的
「每篇文章顯示狀態」決策點，避免三個 story 各自散插判斷式。**這不是投機抽象**——三個 story 皆需，
依憲章 V 的 YAGNI 條款屬於有正當理由的共用。

**⚠️ 完成後才可開始任何 user story**

- [X] T003 在 `pages/shared/app.js` 新增純函式 `articleDisplayState(article)`，回傳 `'hidden' | 'collapsed' | 'normal'`，實作 data-model.md「狀態轉換」一節的決策樹；此階段僅實作 `'normal'` 分支，其餘由各 story 填入
- [X] T004 修改 `pages/shared/app.js` 的 `trafficGroups()`，改為經 `articleDisplayState()` 分派渲染，取代目前直接 map 成 `trafficRow` 的寫法；行為必須與現況完全一致（回歸檢查：對照 T001 的分組篇數）

---

## Phase 3: User Story 2 — 一鍵收掉整個收集來源 (Priority: P2) 🚀 先交付

**Goal**: 使用者可用單一動作收起某個收集來源的全部文章，狀態跨週次與跨造訪保留、可還原。

**Why first**: 純前端、零設定依賴、零誤判風險。可獨立部署取得真實使用回饋，
並成為 US1 自動判定失準時的手動安全網。

**Independent Test**: 任一週頁選一個來源收起 → 該來源文章全部消失、篇數統計更新、
重新載入後仍為收起、可還原。不需要 Worker 變更，不需要量測資料。

- [X] T005 [US2] 在 `pages/shared/app.js` 新增收起清單的持久化讀寫，沿用既有 dismiss 機制的同一儲存後端但**獨立的鍵**（FR-015 要求不互相覆寫）
- [X] T006 [US2] 在 `articleDisplayState()` 補上 `'hidden'` 分支：來源在收起清單中即回傳 hidden（`pages/shared/app.js`）
- [X] T007 [US2] 在 `trafficRow()` 的來源色標籤加上收起入口，使收起為單一動作且不隨該來源篇數增加（`pages/shared/app.js`，對應 SC-004）
- [X] T008 [US2] 實作已收起來源的管理與還原 UI，含全部收起時的空狀態與一鍵還原（`pages/shared/app.js`，FR-014）
- [X] T009 [P] [US2] 在 `pages/shared/shared.css` 加入收起入口與空狀態的樣式
- [X] T010 [US2] 依 `quickstart.md` 前端驗收表跑 US2 相關列（FR-012～FR-015、SC-004），兩個週次各一次

**Checkpoint**: US2 可獨立部署。此時列表已具備手動篩選能力。

---

## Phase 4: User Story 1 — 雜訊自動降級 (Priority: P1) ⭐ MVP 核心

**Goal**: 低價值列預設收合為單一提示行，點擊就地展開；分組標頭同時顯示總篇數與降級篇數。

**Independent Test**: 載入任一週頁，確認降級列收合且標示篇數、可展開、未降級列中高價值比例
顯著高於全體。舊週（遠早於量測窗口）同樣成立。

**Note**: 上線時 SC-001／SC-002 記為「未量測」——人工標註基準集尚不存在，
FR-018a 明訂不阻擋交付，且**禁止以主觀印象或 `initial_quality_score` 代填**。

### 量測（產出設定值）

- [X] T011 [US1] 建立 `scripts/measure_source_uptake.py`：分頁查詢 `articles` 全表（單次上限 1000 列），計算各來源的週報採用率與相對基準倍率。**不得使用 `get_traffic_buffer()`**——它內建 `hot_topic_analyzed=False` 過濾會讓分子恆為 0
- [X] T012 [US1] 在 T011 的腳本實作**自動窗口界定**（FR-005c，不得寫死週次）：排除「未分析數為 0」的已清除舊週（生存者偏差），排除週報尚未執行的當週
- [X] T013 [US1] 為 T011 的腳本加上 `--json` 輸出模式，產生 data-model.md 所定義的設定形狀，並套用 n≥15 樣本門檻（FR-005d，低於門檻者不得出現在輸出中）
- [X] T014 [P] [US1] 建立 `tests/unit/test_source_uptake.py`：覆蓋窗口界定的兩個排除規則與 n≥15 門檻，以合成資料驗證（不觸及真實資料庫）

### Worker API（推導）

- [X] T015 [US1] 在 `workers/api/src/index.js` 新增設定解析：讀取 `env.SOURCE_UPTAKE_JSON`，解析失敗或缺失時回傳空設定而**不得拋錯**（contracts 不變式 3）
- [X] T016 [US1] 在 `workers/api/src/index.js` 新增純函式，依 data-model.md 的公式推導 `noise_downgrade` 與 `source_multiple`；來源名稱**必須完全相等比對**，不得子字串比對（多個來源共用 `Google News ` 前綴）
- [X] T017 [US1] 在 `handleWeekDetail()` 的回應組裝套用 T016；確認新欄位**不進入任何 `select=` 子句**（contracts 不變式 1）
- [X] T018 [US1] 在 `.github/workflows/deploy-worker.yml` 的 `vars:` 與 `env:` 區塊各加入 `SOURCE_UPTAKE_JSON`
- [X] T019 [US1] 依 `contracts/week-detail-api.md` 的驗證方式跑 4 項契約檢查（含 W20 舊週、FFXIV 路徑、設定損毀退化）

### 前端（呈現）

- [X] T020 [US1] 在 `articleDisplayState()` 補上 `'collapsed'` 分支：`noise_downgrade === true` 且未被使用者收起（`pages/shared/app.js`）
- [X] T021 [US1] 在 `trafficGroups()` 為每組渲染降級提示行（標示收合篇數），並實作點擊就地展開／再收合；展開狀態**不持久化**（`pages/shared/app.js`，FR-008a／FR-008b）
- [X] T022 [US1] 修改分組標頭同時顯示總篇數與降級篇數（`pages/shared/app.js`，FR-011）；確認分組收合時降級提示行一併隱藏（FR-011a）
- [X] T023 [P] [US1] 在 `pages/shared/shared.css` 加入降級提示行與展開後淡化列的樣式
- [X] T024 [US1] 依 `quickstart.md` 前端驗收表跑 US1 相關列（FR-008～FR-011a），兩個週次各一次

### 設定部署

- [X] T025 [US1] 跑 T013 產生設定 JSON，交由**使用者本人**執行 `gh variable set SOURCE_UPTAKE_JSON --env production`（助理端會被權限擋），注意 CRLF 與尾端空行；**`火花羅` 不列入設定**——使用者已決定該來源由自己在 `sources_traffic.yml` 手動控制去留，不交由演算法降級

**Checkpoint**: US1 + US2 = 完整 MVP。

---

## Phase 5: User Story 3 — 高價值內容視覺加強 (Priority: P3)

**Goal**: 已進熱點報告、具備摘要與圖片的少數文章獲得額外視覺重量。

**Independent Test**: 有圖片的近期週確認高信號文章先被注意到；零圖片舊週確認版面不破損。

- [X] T026 [US3] 在 `trafficRow()` 為 `hot_topic_analyzed === true` 的文章加上可辨識標記，使用者無須展開即知（`pages/shared/app.js`，FR-016）
- [X] T027 [US3] 為同時具備 `image_url` 與可用摘要的文章提高視覺重量；**缺圖時必須優雅退化**，不得出現破圖或版面塌陷（`pages/shared/app.js`，FR-017）
- [X] T028 [P] [US3] 在 `pages/shared/shared.css` 加入突顯樣式，含無圖時的退化樣式
- [ ] T029 [US3] 依 `quickstart.md` 驗收 FR-016／FR-017，**必須在圖片覆蓋率 0% 的舊週實測一次**（SC-005）

---

## Phase 6: Polish & Cross-Cutting

- [ ] T030 量測 SC-003（掃描成本）與 SC-004（操作成本），對照 T001 的基線，記錄爬到第幾階
- [X] T031 [P] 確認 FFXIV 路徑未退化：以 `content_type=ffxiv` 檢查列表渲染與 `noise_downgrade` 恆為 false
- [X] T032 [P] 在 `specs/011-buffer-noise-triage/research.md` 的「待辦」勾除已完成項，並記錄 07-27 週報後需重跑 T011 補六個新來源
- [X] T033 更新 `STATE.md`：記錄交付範圍、SC-001／SC-002 為「未量測」的原因與補記條件

---

## 驗收紀錄（2026-07-21）

**已部署**：PR #67 merged（`9f27e66`）→ Worker、Pages Traffic、Pages FFXIV 三個部署皆 success。
prod 變數 `SOURCE_UPTAKE_JSON` 已設定並讀回確認（window `2026-W22..2026-W29`、baseline 0.1954）。

**T019 API 契約**：五個週次逐一檢查，**零缺欄位**，含量測窗口之外的 W20（不變式 4 成立）。
只有設定中低於門檻的兩個來源被降級，FFXIV 路徑全 false（不變式 5）。

| 週次 | 篇數 | 降級 | 降級來源 |
|---|---|---|---|
| W20 | 50 | 4 | 機車交通 4 |
| W22 | 80 | 21 | 機車交通 21 |
| W28 | 100 | 37 | 機車交通 29、重機 8 |
| W29 | 100 | 37 | 機車交通 31、重機 6 |
| W30 | 100 | 16 | 機車交通 14、重機 2 |

不變式 3（設定損毀退化）**未在正式環境實測**——那需要故意把變數設成無效值。
該路徑已對 Worker 原始碼逐項驗證（缺變數／非 JSON／`null`／缺 `sources` 鍵，四種皆回
`false`+`null`）。代價效益不划算，刻意不做。

**實際效果（W28，零圖片舊週）**：100 篇中 37 篇收進提示行，版面剩 63 列。
最大的 `機車事故` 由 55 列縮到 34 列。

**使用者瀏覽器驗收**：降級收合正常、來源收整個 feed 正常、圖片有出現（比例不高，
符合 W29 33%／W30 23% 的資料現況）。

**未完成**：
- T029 的零圖片舊週（W28）版面確認——使用者回報的是有圖的週次，最容易破版的情境未經確認
- T030 的 SC-003 計時——需使用者本人實測，在此之前 SC-003 階數比照 SC-001／SC-002 記為「未量測」

---

## Dependencies

```
Phase 1 (T001-T002)
    ↓
Phase 2 (T003-T004)  ← 阻擋所有 story
    ↓
    ├─→ Phase 3 US2 (T005-T010)  ── 可獨立部署
    │        ↓
    ├─→ Phase 4 US1 (T011-T025)  ── T020 需 T006 已建立 hidden 分支的分派結構
    │        ↓
    └─→ Phase 5 US3 (T026-T029)  ── 與 US1/US2 無資料相依，僅共用 trafficRow
             ↓
        Phase 6 (T030-T033)
```

**Story 間相依**：US1 與 US2 在 `articleDisplayState()` 有結構相依（US2 先建 hidden、US1 再加
collapsed），這是刻意的——先做的 story 建立分派骨架。US3 與兩者皆無相依。

**US1 內部**：量測（T011-T014）→ 設定部署（T025）為一條線；Worker（T015-T019）與
前端（T020-T024）可平行，但 T024 的實測需 T019 已部署。

## Parallel Opportunities

- **Phase 3**: T009（CSS）可與 T005-T008 平行
- **Phase 4**: T014（測試）可與 T011-T013 平行；Worker 組（T015-T018）與前端組（T020-T023）
  可由不同人平行，T023 CSS 亦可平行
- **Phase 5**: T028（CSS）可與 T026-T027 平行
- **Phase 6**: T031、T032 可平行

## Implementation Strategy

### 階段順序為何不照 P1 → P3

plan.md 的決定，使用者已核可：

1. **US2 先於 US1**——US2 純前端、零設定依賴、零誤判風險，可先上線取得真實回饋；
   且它是 US1 判定失準時的手動安全網，先有安全網再開自動判定較穩。
2. **量測腳本先於 US1 實作**——FR-005c 要求窗口隨時間重算，本 session 的 scratchpad
   分析不符合；固化為可重跑腳本同時保住已完成的分析。
3. **US3 最後**——受圖片覆蓋率限制（舊週 0%），素材最少、收益最低。

### MVP 範圍

**US2 + US1**（T001-T025）。US3 為增益，不影響核心價值。

### 已知會帶著缺口交付

- **SC-001／SC-002 記為「未量測」**：人工標註基準集尚不存在。FR-018a 明訂不阻擋交付。
  補記條件＝基準集產出後掃描門檻取操作點（FR-005b）。
- **6/30 來源有設定值**（涵蓋 83% 文章量），其餘走 FR-006 預設非雜訊；
  六個新來源需 07-27 首次週報後重跑 T011。
- **JS 端無自動化測試**：刻意不引入框架，已登記於 `specs/BACKLOG.md`。
