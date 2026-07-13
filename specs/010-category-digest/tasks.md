---
description: "Task list for 低頻類別聚合式深度分析（category digest）"
---

# Tasks: 低頻類別聚合式深度分析（category digest，交通週報）

**Input**: Design documents from `specs/010-category-digest/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/internal-contracts.md, quickstart.md

**Tests**: 後端 Python 功能，repo 既有 `pytest`（`tests/unit`、`tests/integration`）；quickstart 已列測試情境 → **產生測試任務**（先寫、先失敗）。

**Organization**: 依使用者故事 US1(P1)→US2(P2)→US3(P3) 分階段。共用核心 `select_digest_pool` 依模板規則置於最早使用它的 US1；US3 的品質下限邏輯是該函式契約的一部分（US1 實作），US3 階段以邊界測試獨立驗證該故事。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行（不同檔案、無未完成相依）。
- **[Story]**: US1 / US2 / US3 對應 spec 使用者故事；Setup/Foundational/Polish 無 story 標。

## Path Conventions

單一資料管線專案：改動落在既有 `src/`、`scripts/`、`config/`、`tests/`。無新模組、**無 migration**（零 schema 變更）。

---

## Phase 1: Setup

**Purpose**: 建立回歸基線

- [X] T001 跑 `pytest` 確認既有測試全綠，並記錄 `scripts/traffic_weekly_analysis.py` 現行行為（cluster→score→novelty 選取→發布迴圈）作為 SC-004 回歸基線

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 三個故事共同依賴的設定層（皆透過 `src/pipeline_config.py` 讀設定）

**⚠️ CRITICAL**: `category_digest` 設定鍵與驗證未就緒前，任何故事的觸發／下限／選材參數都讀不到

- [X] T002 在 `src/pipeline_config.py` 的 `_DEFAULTS` 加頂層鍵 `category_digest: {}`，並在 `_validate_pipeline_config` 加逐類別驗證（`trigger_count`／`max_articles` 為正整數、`quality_floor` ∈ [0,1]、子鍵可省略套預設 10／0.18／15——contracts 設定鍵契約）
- [X] T003 [P] 在 `config/pipeline_config.example.yml` 加 `category_digest` 範例區塊（道安政策：trigger_count 10、quality_floor 0.18、max_articles 15，附註解）
- [X] T004 [P] 單元測試 `tests/unit/test_pipeline_config.py`（既有檔增測或新建）：`category_digest` 合法值通過、非法值（負數、>1 的 floor、非整數）raise、空設定回 `{}`

**Checkpoint**: 設定層就緒，故事可開工

---

## Phase 3: User Story 1 - 低頻類別的彙整報告終於出現 (Priority: P1) 🎯 MVP

**Goal**: 池內有效篇數達門檻 → 產出「<類別> · 彙整」digest 報告，走既有管線發布；未達 → 零行為變化＋FR-009 池狀態 log。digest 先佔 `max_hot_topics` 席次。

**Independent Test**: 池 ≥ 門檻跑週分析 → digest 發布且一般 bucket 只取剩餘席次；池 < 門檻 → 只留 accumulate log，輸出與現狀相同（spec US1 場景 1–3）。

### Tests for User Story 1 ⚠️（先寫、先失敗）

- [X] T005 [P] [US1] 單元測試 `tests/unit/test_digest_pool.py`：`select_digest_pool` 純函數——觸發計數（有效篇數 vs trigger_count）、選材 quality 降冪至多 `max_articles`、`excluded_links` 排除（FR-006）、`pool_all` 含未選材文章、空池／全排除邊界
- [X] T006 [P] [US1] 在 `tests/unit/test_novelty_gate.py` 增測：`topic_token_signature=[]` 的 digest 列永不被 `_match_prior_basis` 匹配（空簽章 Jaccard=0，research D2）——一般 bucket 的 novelty 行為不因 digest 列存在而改變
- [X] T007 [P] [US1] 整合測試 `tests/integration/test_digest_weekly.py`（Gemini stub/mock）：(a) 池達門檻 → 週跑發布「道安政策 · 彙整」報告（空簽章、score=選材 quality 和、latest_source_date 正確），且一般 bucket 席次 = `max_hot_topics - 1`；(b) 池未達門檻 → 無 digest、一般選取與現狀 bit-for-bit 相同、log 含 `digest[道安政策] pool=.. effective=.. threshold=.. → accumulate`（FR-009）

### Implementation for User Story 1

- [X] T008 [US1] `src/analyzer.py`：實作 `select_digest_pool(articles, category, digest_cfg, excluded_links) -> (selected, pool_all, effective_count)`（純函數，contracts 簽章；含 quality_floor 過濾與降冪選材）
- [X] T009 [US1] `src/analyzer.py`：新增 `DIGEST_SYSTEM_PROMPT`／`DIGEST_PROMPT_TEMPLATE`（多事件動態總覽：逐事件短段、不硬湊因果、期間跨度明示、`[n]` 引用對應）與 `analyze_category_digest(pool_articles, topic_label, week_start_date, max_articles) -> (report_text, ordered_links)`（沿用 `_call_gemini`，失敗回 `("", [])`）
- [X] T010 [US1] `scripts/traffic_weekly_analysis.py`：串接 digest 路徑（contracts 串接順序契約）——一般選取後對每個啟用類別跑觸發統計＋FR-009 log（無論觸發與否）；席次分配 `regular_ids = 入選[:max_hot_topics - len(triggered)]`（多 digest 超額依 effective_count 降冪取足）；發布迴圈加 digest 分支（report dict：label「<類別> · 彙整」、`topic_token_signature: []`、`cumulative_score`=選材 quality 和、其餘欄位按選材計算——data-model 表）；維持 2.5s delay

**Checkpoint**: US1 獨立可測——道安政策首份報告可產出（MVP）。註：此時消耗僅及選材 links（既有 upsert 路徑），全池消耗在 US2 補完。

---

## Phase 4: User Story 2 - 彙整過的內容不重複出現 (Priority: P2)

**Goal**: digest 成功持久化後，池內**全部**文章（含未選材）標記 `hot_topic_analyzed=TRUE`；任一環節失敗則零消耗，下週重試。

**Independent Test**: 兩跑序列——第一跑觸發＋消耗後，第二跑池空不觸發；兩跑 `source_article_links` 零交集；失敗路徑（Gemini 空回／upsert raise）驗證零消耗（spec US2 場景 1–3）。

### Tests for User Story 2 ⚠️（先寫、先失敗）

- [ ] T011 [P] [US2] 單元測試 `tests/unit/test_digest_consume.py`（mock Supabase client）：`mark_articles_analyzed` 標記筆數回傳、失敗回 0 且 log ERROR 不 raise；runner digest 分支順序語意——Gemini 失敗→不 upsert 不 mark、upsert raise→不 mark、成功→mark 池殘餘（pool_all − 選材 links）
- [ ] T012 [US2] 在 `tests/integration/test_digest_weekly.py` 增測：兩跑序列（第一跑觸發＋`consumed=<k>` log＋全池標記 → 第二跑 `pool=0 → accumulate` 不重觸發）；失敗-重跑變體：mock `mark_articles_analyzed` 失敗（驗 ERROR log，research D3）→ 池殘餘未清 → 重跑再觸發 → 同 `(week_start_date, topic_label)` upsert 冪等不產生第二筆

### Implementation for User Story 2

- [ ] T013 [P] [US2] `src/storage.py`：新增 `mark_articles_analyzed(links) -> int`（contracts 簽章；fail-soft：例外時 log ERROR 回 0）
- [ ] T014 [US2] `scripts/traffic_weekly_analysis.py`：digest 分支補消耗——`upsert_hot_topic_report` 成功後呼叫 `mark_articles_analyzed(池殘餘 links)`＋`digest[<cat>] consumed=<k>` log；任一步失敗該 digest 本週放棄、池不消耗、不影響其他報告（research D3 順序與失敗語意）

**Checkpoint**: US1+US2——「累積→觸發→清空」完整閉環

---

## Phase 5: User Story 3 - 垃圾素材不進彙整 (Priority: P3)

**Goal**: quality < 下限的文章不計入觸發、不入選材，但隨清池被消耗。下限邏輯已在 US1 的 `select_digest_pool` 契約內實作；本階段以真實邊界值獨立驗證此故事，揭露缺口即修。

**Independent Test**: 池內混入 q=0.165 文章（實案「友善列印」）→ 不計數、不入選材；q=0.193 → 計數且可入選材；觸發後垃圾文仍被消耗（spec US3 場景 1–2）。

### Tests for User Story 3 ⚠️

- [ ] T015 [P] [US3] 在 `tests/unit/test_digest_pool.py` 增測邊界：q=0.165 排除於 effective_count 與 selected、q=0.193 納入（floor=0.18 預設）；floor 自訂值生效；垃圾文仍在 `pool_all`（消耗涵蓋）
- [ ] T016 [US3] 在 `tests/integration/test_digest_weekly.py` 增測 SC-003：觸發跑後 digest 的 `source_article_links` 無任何 quality < floor 者；被排除的垃圾文仍被標記 analyzed
- [ ] T017 [US3] 依 T015/T016 結果修正 `src/analyzer.py` `select_digest_pool` 的 floor 邊界處理（若測試全綠則記錄 no-op，不改碼——誠實省略）

**Checkpoint**: 三故事各自獨立可驗

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T018 [P] SC-004 回歸：在 `tests/integration/test_digest_weekly.py` 增測「`category_digest` 空／缺 → 週跑選取與發布行為與 T001 基線等價」，並跑全 suite `pytest` 確認零回歸
- [ ] T019 quickstart §2 read-only 重放（真實 buffer，零寫入、不打 Gemini）：驗證 `select_digest_pool` 對實池的觸發統計（15 篇 → effective 排除「友善列印」→ TRIGGER）與選材排序
- [ ] T020 Post-merge ops（不在本 branch）：prod `PIPELINE_CONFIG_YML` 補 `category_digest` 區塊＋read-back 用 repo loader 驗證（比照 #59 部署慣例）；首次真實週跑後從 Actions log 驗 SC-001（`✓ hot_topic_report upserted: ... / 道安政策 · 彙整`）與 SC-005（pool/effective/threshold/consumed 可直讀）

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 無相依，立即可跑。
- **Foundational (Phase 2)**: 依賴 T001；**阻擋所有故事**（設定層）。
- **US1 (Phase 3)**: 依賴 Phase 2。故事內：T005–T007（測試）→ T008 → T009 → T010。
- **US2 (Phase 4)**: 依賴 US1 的 T010（digest 分支存在才有消耗掛點）。T011 可與 T012 平行寫；T013 → T014。
- **US3 (Phase 5)**: 依賴 US1 的 T008（floor 邏輯載體）；與 US2 無相依，可平行。
- **Polish (Phase 6)**: T018 依賴全部故事；T019 依賴 T008；T020 在 merge 後。

### Parallel Opportunities

- Phase 2：T003、T004 平行（不同檔）。
- US1 測試：T005、T006、T007 平行（三個不同檔）。
- US2 的 T011（unit）與 US3 的 T015（不同檔）可平行；T013 與 US3 全部平行。
- US2 與 US3 兩個故事在 US1 完成後可平行進行。

## Implementation Strategy

**MVP = Phase 1–3（US1）**：道安政策首份彙整報告可發布。註：US1 的既有 upsert 路徑已標記選材 links（至多 15 篇）——池的大宗在 MVP 就會被消耗，US2 補的是殘餘（低品質文＋超出 K 者）與失敗語意的完整性，因此 MVP 單獨上線的重複風險有限但非零。

**Incremental**：US1（發布）→ US2（閉環）→ US3（防護驗證）→ Polish（回歸＋實池重放）。每個 checkpoint 皆可獨立驗收後再前進。

## Notes

- 全程零 schema 變更；發現需要動 schema 即回頭改 plan（不 silent 擴權）。
- T007/T012/T016/T018 共用 `tests/integration/test_digest_weekly.py`，依序增測（非平行）。
- Gemini 一律 stub/mock；唯一打真 API 的驗證留給 merge 後首次週跑（quickstart §3 的決策）。
- 每完成一個任務或邏輯群組即 commit。
