---
description: "Task list for 交通頁可讀性重設計"
---

# Tasks: 交通頁可讀性重設計

**Input**: Design documents from `specs/008-traffic-page-redesign/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ui-and-api-contract.md, quickstart.md

**Tests**: 本 repo 前端無測試框架、spec 未要求 TDD → **不產生前端測試任務**；以 `quickstart.md` 人工驗證，並用既有 `pytest` 防 Python pipeline 回歸。

**Organization**: 依使用者故事 P1→P4 分階段，每階段可獨立交付與驗證。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行（不同檔案、無未完成相依）。注意：大多數任務改同一個 `pages/shared/app.js`，**不可平行**。
- **[Story]**: US1–US4 對應 spec 使用者故事。

## Path Conventions

純前端（Cloudflare Pages）：`pages/traffic/index.html`、`pages/shared/app.js`、`pages/shared/shared.css`。無 `src/` Python 改動、無 DB migration、無 Worker 改動。

---

## Phase 1: Setup

**Purpose**: 建立驗證基線

- [ ] T001 依 `quickstart.md` 起本地靜態站（`python3 -m http.server 8000 --directory pages`）開 `/traffic/`，記錄改動前行為（全週堆疊、nav 在中間）作為回歸基線

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: US1 與 US4 共用的週鍵對齊原語

**⚠️ CRITICAL**: T002 完成前，US1／US4 的選週邏輯無法正確運作

- [ ] T002 在 `pages/shared/app.js` 新增純函式 `isoWeekId(dateStr)`：把 `YYYY-MM-DD`（週一日期）換算為 ISO 週字串 `YYYY-Www`，用於將 `hot_topic_reports.week_start_date` 對齊文章 `week_id`（research D1；不改後端）

**Checkpoint**: 週鍵可在前端對齊，US1 可開工

---

## Phase 3: User Story 1 - 統一週導覽 (Priority: P1) 🎯 MVP

**Goal**: 單一週導覽同時驅動深度分析與新聞列表，預設最新一週，導覽上移至深度分析之上

**Independent Test**: 開 `/traffic/` 僅顯示最新一週兩區；切較舊週 → 兩區同步切換；nav 在深度分析之上（quickstart US1）

- [ ] T003 [US1] 在 `pages/traffic/index.html` 將 `week-nav` 容器移到 `hot-topics-list` 之上（FR-002）
- [ ] T004 [US1] 在 `pages/shared/app.js` `init()`：traffic 時先載入並快取 `/api/hot-topics`（一次），改為由 `loadWeek` 驅動深度分析；預設選最新一週（`allWeeks[0].week_id`）（FR-003）
- [ ] T005 [US1] 在 `pages/shared/app.js` `loadWeek(weekId)`：用 T002 `isoWeekId` 將快取 reports 的 `week_start_date` 換算後過濾出該週子集，呼叫 `renderHotTopics(subset)`，與新聞列表一起更新（FR-001）
- [ ] T006 [US1] 在 `pages/shared/app.js` `renderHotTopics()`：接受「某週 reports 子集」；該週無報告時顯示明確空狀態，且新聞列表既有空狀態沿用，跨區不一致不報錯（FR-005）
- [ ] T007 [US1] 在 `pages/shared/app.js`／`pages/traffic/index.html` 明確標示目前檢視的週（複用 `site-subtitle` 或 nav active 態）（FR-004）
- [ ] T008 [US1] 依 quickstart US1（步驟 1–4）人工驗證

**Checkpoint**: US1 可獨立運作 — 累積閱讀問題已解決（MVP）

---

## Phase 4: User Story 2 - 深度分析卡片化 (Priority: P2)

**Goal**: 深度分析以分區、有層次、可掃讀的純前端卡片呈現，取代生硬條列

**Independent Test**: 任一深度分析 → 三軸分區清楚、關鍵指標凸顯、焦點事件與 `[n]` 引用可用（quickstart US2）

- [ ] T009 [US2] 在 `pages/shared/app.js` 新增 `report_text` 解析器：將 `### 一/二/三` 三軸切為結構資料；遇非預期格式降級為純文字段落（FR-008 穩健降級、FR-014 純前端）
- [ ] T010 [US2] 在 `pages/shared/app.js` 改寫 `renderHotTopics()` 卡片內文為結構分區：三軸分區、凸顯「交織度分布／代表個案」等關鍵指標，焦點事件連結與報告內 `[1][2]` 引用維持可用（FR-006/007/008）
- [ ] T011 [P] [US2] 在 `pages/shared/shared.css` 新增深度分析卡片樣式（分區、指標徽章、視覺層次）
- [ ] T012 [US2] 依 quickstart US2（步驟 5）人工驗證

**Checkpoint**: US1＋US2 各自可獨立運作；歷史報告自動套用新卡片版面（FR-016）

---

## Phase 5: User Story 3 - 新聞密集列 (Priority: P3)

**Goal**: 新聞列表改為時間序＋來源色標的精簡密集列，可快速一覽

**Independent Test**: 新聞列表為一行一則（來源色標＋標題＋相對時間），點標題展開來源摘要／前往原文；搜尋與標記過時仍可用（quickstart US3）

- [ ] T013 [US3] 在 `pages/shared/app.js` 為 traffic 新增密集列渲染（改寫 `articleCard` 的 traffic 分支或新增 `renderTrafficList`）：來源色標＋標題＋相對時間、時間序最新在上、來源 `summary` 收於展開；不依賴 importance/tags（FR-009/015）
- [ ] T014 [P] [US3] 在 `pages/shared/shared.css` 新增密集列與展開樣式
- [ ] T015 [US3] 在 `pages/shared/app.js` 確認密集列下關鍵字搜尋、標記過時（dismiss）仍可用（FR-010/SC-006）
- [ ] T016 [US3] 依 quickstart US3（步驟 6–7）人工驗證

**Checkpoint**: US1–US3 各自可獨立運作

---

## Phase 6: User Story 4 - 深度分析分享 / deep-link (Priority: P3)

**Goal**: 每則深度分析可分享到 LINE，連結直接定位到該週該主題

**Independent Test**: 某則深度分析分享 → 取得 `?week=...#topic-...`；另開後直接定位；失效連結回退最新週（quickstart US4）

**Depends on**: US1（選週機制）、T002

- [ ] T017 [US4] 在 `pages/shared/app.js` `renderHotTopics()` 為每張卡片加 `id="topic-<slug>"`，並實作 `slugify(topic_label)`（contract B / data-model）
- [ ] T018 [US4] 在 `pages/shared/app.js` 為熱點卡片加分享動作：建構 `<origin+path>?week=<week_id>#topic-<slug>` → 交既有 LINE 分享端點（沿用 `C.shareToLine`；ffxiv 不顯示）（FR-011/013）
- [ ] T019 [US4] 在 `pages/shared/app.js` `init()` 載入時解析 `?week=`（選週、複用 US1 機制）與 `#topic-`（捲動定位）；週/主題不存在則回退最新週且不報錯（FR-012、contract B）
- [ ] T020 [US4] 依 quickstart US4（步驟 8–10，含失效連結回退）人工驗證

**Checkpoint**: 四個使用者故事皆可獨立運作

---

## Phase 7: Polish & Cross-Cutting

**Purpose**: 防回歸與收尾

- [ ] T021 [P] 不回歸驗證：開 `/ffxiv/`，確認重要度徽章、tags、分享等行為與改版前一致（`pages/ffxiv/`，contract D）
- [ ] T022 [P] 執行 `pytest` 確認 Python pipeline 測試不受本前端改動影響
- [ ] T023 跨 US2/US3 視覺收尾：深色模式與窄螢幕（RWD）下的卡片與密集列（`pages/shared/shared.css`）
- [ ] T024 完整跑一遍 `quickstart.md`，逐項對照 FR 與 SC

---

## Dependencies & Execution Order

### Phase Dependencies
- **Setup (P1)**：無相依，可立即開始
- **Foundational (P2)**：依賴 Setup；**阻擋 US1／US4**
- **US1 (P3)**：依賴 Foundational → MVP
- **US2 (P4)**：依賴 Foundational；與 US1 獨立可測（但同改 `app.js`，實作上接在 US1 後較順）
- **US3 (P5)**：依賴 Foundational；與 US1/US2 獨立可測
- **US4 (P6)**：依賴 Foundational ＋ **US1（選週機制）**
- **Polish (P7)**：依賴欲交付的故事完成

### Within Each Story
- 解析/資料 → 渲染 → 樣式 → 驗證
- 同檔（`app.js`）任務循序；CSS 任務（T011/T014）可與對應 JS 平行

### Parallel Opportunities
- T011 [P]（US2 CSS）可與 T009/T010 平行
- T014 [P]（US3 CSS）可與 T013 平行
- T021 [P]（ffxiv 回歸）、T022 [P]（pytest）可彼此平行
- 注意：US1–US4 的 JS 多改同一個 `app.js`，跨故事**不建議平行**以免衝突

---

## Implementation Strategy

### MVP First（僅 US1）
1. Phase 1 Setup → 2. Phase 2 Foundational（T002 週鍵原語）→ 3. Phase 3 US1
4. **STOP & VALIDATE**：quickstart US1（累積閱讀問題即解決）→ 可部署/demo

### Incremental Delivery
US1（MVP）→ US2（卡片化）→ US3（密集列）→ US4（分享/deep-link），每層獨立加值、不破壞前一層 → Polish 收尾。

---

## Notes
- [P] = 不同檔案、無相依；本功能 [P] 機會少（集中於 `app.js`）。
- 所有 traffic-only 行為以 `C.contentType === 'traffic'` 分流，**不得回歸 ffxiv**（contract D）。
- 共用層整體拆分為 008 之後的獨立後續（記憶 `project_traffic_ffxiv_shared_divergence`），本次不做。
- 每個任務或邏輯群組完成後可提交；於任一 Checkpoint 可停下獨立驗證。
