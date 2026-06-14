---
description: "Task list for 節奏觸發式深度分析 + 深度來源分類補進（Layer 3）"
---

# Tasks: 節奏觸發式深度分析 + 深度來源分類補進（交通週報 Layer 3）

**Input**: Design documents from `specs/009-novelty-gated-hot-topics/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/internal-contracts.md, quickstart.md

**Tests**: 後端 Python 功能，repo 既有 `pytest`（`tests/unit`、`tests/integration`）；quickstart 已列測試情境 → **產生測試任務**（與 008 純前端不同）。

**Organization**: 依使用者故事 US1(P1)→US2(P2) 分階段，各自獨立可交付、可測。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行（不同檔案、無未完成相依）。
- **[Story]**: US1 / US2 對應 spec 使用者故事；Setup/Foundational/Polish 無 story 標。

## Path Conventions

單一資料管線專案：改動落在既有 `src/`、`scripts/`、`config/`、`supabase_migrations/`、`tests/`。無新模組、無目錄重整。

---

## Phase 1: Setup

**Purpose**: 建立回歸基線

- [x] T001 跑 `pytest` 確認既有測試全綠，並記錄目前 `scripts/traffic_weekly_analysis.py` 行為（每週重選 top-N、每類別每週一報告）作為回歸基線

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 兩個故事共同依賴的設定層（皆透過 `src/pipeline_config.py` 讀設定）

**⚠️ CRITICAL**: 設定鍵與 loader 未就緒前，US1/US2 的設定讀取無法運作

- [x] T002 在 `src/pipeline_config.py` 的 `_DEFAULTS` 加 `topic_scoring.novelty_growth_pct: 0.5` 與新區塊 `topic_identity.similarity_threshold: 0.3`，並在 `_validate_pipeline_config` 加範圍檢查（`novelty_growth_pct ≥ 0`、`similarity_threshold ∈ [0,1]`）
- [x] T003 在 `src/pipeline_config.py` 新增 `load_source_default_categories(path=None)`（讀 `categories_traffic.yml` 的 `source_defaults` 鍵，缺鍵回 `{}`，同 `load_category_taxonomy` 快取風格），並把新快取納入 `reset_caches()`
- [x] T004 [P] 設定範例：在 `config/categories_traffic.example.yml` 加 `source_defaults:` 範例區塊；在 `config/pipeline_config.example.yml`（若不存在則建立）加 `topic_scoring.novelty_growth_pct` 與 `topic_identity.similarity_threshold`

**Checkpoint**: 設定層就緒，US1/US2 可開工

---

## Phase 3: User Story 1 - 不再重複疲乏的深度分析（Novelty gate）(Priority: P1) 🎯 MVP

**Goal**: 週分析在 Gemini 前加 novelty gate（gate-then-cap），無新進展的話題不再每週重發；持久化 novelty 基準供跨週比對。

**Independent Test**: 兩週序列——第 1 週某話題達門檻產報告；第 2 週無突增→被抑制；第 2 週變體（分數突增且含更晚日期）→再次產報告（quickstart B/C）。

### Tests for User Story 1 ⚠️（先寫、先失敗）

- [x] T005 [P] [US1] 單元測試 `tests/unit/test_novelty_gate.py`：`passes_novelty`（無基準→True；成長 < p→False；成長 ≥ p 且含晚於基準日的文章→True）、hybrid 身分比對（同 category + Jaccard ≥ 門檻）、gate-then-cap 選取（quickstart B1–B4）
- [x] T006 [P] [US1] 整合測試 `tests/integration/test_novelty_weekly.py`：兩週序列（報告→抑制→再觸發）與 prior-reports 讀取失敗的 fail-open（quickstart C、B5；Gemini 以 stub/mock）

### Implementation for User Story 1

- [x] T007 [P] [US1] 建立 `supabase_migrations/004_hot_topic_novelty.sql`：`hot_topic_reports` 加 `topic_token_signature JSONB DEFAULT '[]'`、`latest_source_date DATE`（data-model 草案）
- [x] T008 [US1] `src/storage.py`：新增 `get_recent_hot_topic_reports(max_age_weeks=8, exclude_week=None)`；`upsert_hot_topic_report` 的 `row` 增寫 `topic_token_signature`、`latest_source_date`（其餘不變，含標記 `hot_topic_analyzed=TRUE`）
- [x] T009 [US1] `src/analyzer.py`：新增 `topic_token_signature(bucket_articles, top_k=8)`（`normalise_title` token 聯集取前 K）與 `passes_novelty(bucket_score, bucket_signature, bucket_latest_date, prior_basis, config)`（contract C4：無基準→True；否則 score≥last×(1+p) 且 latest_date 嚴格晚於基準）
- [x] T010 [US1] `src/analyzer.py`：新增 `select_hot_topics_with_novelty(buckets, bucket_scores, prior_reports, config)`（gate-then-cap：過 `min_threshold` → 以 major_category + `compute_jaccard(sig)≥similarity_threshold` 找最近 prior 基準 → `passes_novelty` 過濾 → 存活者依分數取 top `max_hot_topics`）
- [x] T011 [US1] `scripts/traffic_weekly_analysis.py`：在 cluster/score 後讀 `get_recent_hot_topic_reports(..., exclude_week=week_start)`（try/except→fail-open 全部視為新）、改呼叫 `select_hot_topics_with_novelty`、為入選 bucket 計算 signature 與 `latest_source_date`、`topic_label` 改「`major_category` · 代表詞」、把新欄位放入 report dict、加每 bucket 決策 INFO 日誌

**Checkpoint**: US1 獨立可測——疲乏重發已解（MVP）

---

## Phase 4: User Story 2 - 深度來源能進入深度分析（Source-default 分類）(Priority: P2)

**Goal**: 標題判 uncategorised 時，依「來源→預設分類」設定補 fallback，使報導者/天下等深度來源匯入政策 bucket。

**Independent Test**: 深度來源、標題無 token 的文章→被指派預設政策分類；標題已命中者不被覆蓋；不在 map 者維持 uncategorised（quickstart A）。

### Tests for User Story 2 ⚠️（先寫、先失敗）

- [x] T012 [P] [US2] 單元測試 `tests/unit/test_source_default_category.py`：uncategorised + mapped 來源→預設分類；標題已命中 → 不覆蓋（FR-010/SC-005）；unmapped + uncategorised → 維持 uncategorised（quickstart A1–A4）

### Implementation for User Story 2

- [x] T013 [P] [US2] `src/filter.py`：新增 `resolve_source_default(source, mapping) -> str`（第一個 `key in source` 子字串命中回對應類別，否則 `"uncategorised"`）
- [x] T014 [US2] `src/pipeline/traffic.py` 分類迴圈（約 line 76–83）：載入 `load_source_default_categories()`，於 `cat == "uncategorised"` 時以 `resolve_source_default(article["source"], mapping)` 補分類（僅 fallback，不覆蓋命中）

**Checkpoint**: US1＋US2 各自獨立運作

---

## Phase 5: Polish & Cross-Cutting

**Purpose**: 部署設定、回歸、驗收

- [ ] T015 [P] 部署設定：把 `source_defaults`（報導者/天下/道安統計→道安政策、行人地獄→行人事故、區間測速→科技執法）加入 GitHub Variable `CATEGORIES_TRAFFIC_YML`；把 `novelty_growth_pct`/`similarity_threshold` 加入 `PIPELINE_CONFIG_YML`；於 Supabase SQL Editor 套用 `004_hot_topic_novelty.sql`
- [x] T016 跑全套 `pytest`（unit+integration）全綠；確認 `tests/unit/test_category_assign.py`、`tests/unit/test_topic_scoring.py` 無回歸（SC-005）— 2026-06-14：66 passed, 4 skipped
- [ ] T017 依 `quickstart.md` 逐項對照 SC-001~005 完成驗收

---

## Dependencies & Execution Order

### Phase Dependencies
- **Setup (P1)**：無相依，先跑。
- **Foundational (P2)**：依賴 Setup；**阻擋 US1/US2**（設定層）。
- **US1 (P3)**：依賴 Foundational（讀 novelty 設定）→ MVP。
- **US2 (P4)**：依賴 Foundational（`load_source_default_categories`）；與 US1 獨立可測。
- **Polish (P5)**：依賴欲交付故事完成。

### Within US1
- 測試（T005/T006）先寫先失敗 → 實作。
- T007（migration，獨立檔）[P]；T008（storage）；T009→T010（同檔 `analyzer.py` 循序）；T011（script）依賴 T008/T009/T010。

### Within US2
- 測試 T012 先；T013（`filter.py` 助手）[P] → T014（`traffic.py` 套用，依賴 T013 + Foundational T003）。

### Parallel Opportunities
- T004 [P]（範例設定）可與 T002/T003 平行（不同檔）。
- US1 與 US2 在 Foundational 完成後可平行（不同檔，無交叉相依）。
- 各故事內 [P] 測試可平行；T007（migration）可與 US1 其他實作平行。
- ⚠️ `analyzer.py`（T009/T010）、`pipeline_config.py`（T002/T003）同檔任務須循序。

---

## Implementation Strategy

### MVP First（僅 US1）
1. Phase 1 Setup → 2. Phase 2 Foundational → 3. Phase 3 US1
4. **STOP & VALIDATE**：quickstart B/C（疲乏重發即解）→ 套 migration + 設定即可部署觀察。

### Incremental Delivery
US1（MVP，novelty gate）→ US2（深度來源分類補進）→ Polish（部署設定 + 回歸 + 驗收）。每層獨立加值、不破壞前層。

---

## Notes
- novelty gate 只會**減少**、不會增加 Gemini 呼叫；保留 `max_hot_topics` 上限與 2.5s delay（憲章 IV）。
- daily buffer（`traffic_buffer.py`）維持零 AI；source-default 為純查表（FR-014）。
- 重跑同 corpus 須結果一致：基準讀取以 `exclude_week` 排除當週（憲章 III idempotency）。
- 每個任務或邏輯群組完成可提交；於任一 Checkpoint 可停下獨立驗證。
- ⚠️ 部署阻礙：本機 `.venv` 的 `charset_normalizer` C-ext segfault（exit 139）會擋 collector 相關整合測試；純函式單元測試不受影響，必要時重建 venv。
