---

description: "Task list for 014-policy-source-expansion"
---

# Tasks: 補政策 digest 的來源

**Input**: Design documents from `/specs/014-policy-source-expansion/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/source-funnel.md, quickstart.md

**Tests**: **要。** 三行 log 與評估工具都有讀者（週驗收 routine、人工判讀），contracts 把格式訂成契約；
漏斗記帳、池來源 log、評估工具的唯讀保險都是可離線測的純邏輯。先寫測試、確認會失敗，再實作。

**Task markers are three-state**（本 repo 的 delegated-TDD 接線）：
`[ ]` 未開始 → `[-]` 已實作、待審 → `[X]` 已審且 main 驗證過 → `[~]` 移出範圍
驗證型 task（main 跑真實入口或咬合實驗、記下結果，沒有實作：T008、T015、T021）由 main 驗證即可標 `[X]`，不派 reviewer（Luke 2026-10-15 裁示）。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行（不同檔案、無未完成依賴）
- **[Story]**: 對應 spec.md 的 user story

## Path Conventions

單一專案：`src/`、`scripts/`、`config/`、`tests/unit/` 皆在 repo 根目錄。
⚠️ `python` 不在 PATH，一律用 `.venv/bin/python`。新檔的註解／docstring 區塊 ≤ 3 行（`test_comment_budget.py`）。

## 階段順序與 spec 優先度的關係

spec 的優先度是 US1（P1，目標）、US2（P1，前置）、US3（P2）。**執行順序照依賴，不照優先度**：
US1 要改來源，改之前必須先有 US2（來源清單進 git）與 US3（看得見每個來源掉在哪一關）。US2 與 US3 互不依賴，可以平行。

---

## Phase 1: Setup

**Purpose**: 憲章措辭跟上 `crb` 的設計——已由憲章 2.0.0（PR #163）處理，本 spec 不再修憲。

- [~] T001 ~~憲章 PATCH 1.3.1（原則 II／Operations 的鏡像措辭）~~——移出範圍：併入憲章 2.0.0（PR #163），
      II 已寫明「有鏡像的 example 進 git、鏡像清單以 `scripts/check_config_drift.py` 為準」，Operations 已改成「有鏡像就在 PR 同步」。
      本 spec 只要在 T007 把兩份 sources 加進那份清單，條文就涵蓋它們。**#163 要先 merge。**

**Checkpoint**: 憲章文字與 plan 的 Constitution Check 一致。

---

## Phase 2: User Story 2 - 來源清單的現況在 repo 裡看得到（前置） (Priority: P1)

**Goal**: 兩份 `sources_*.example.yml` 成為 prod 鏡像，由 daily 漂移檢查守著（`GNS-20261005-crb`）。

**Independent Test**: 本機跑 `.venv/bin/python scripts/check_config_drift.py` 綠；把鏡像的某個值改掉（在 scratchpad 的副本上，
不在主工作區）再比，會紅並指出那個鍵。

- [ ] T002 [US2] 確認本機 `config/sources_traffic.yml` 與 prod `SOURCES_TRAFFIC_YML` 解析後相同
      （`gh variable get SOURCES_TRAFFIC_YML --env production`，YAML parse 後比物件；不同就以 prod 為準更新本機並記下差異）。
      `config/sources_ffxiv.yml` 與 `SOURCES_FFXIV_YML` 同樣比一次。
- [ ] T003 [P] [US2] 把 `config/sources_traffic.example.yml` 改成 `config/sources_traffic.yml` 的鏡像：`sources:` 的內容逐筆相同，
      保留檔頭的欄位與 type 說明（註解不影響比對），把「這是格式範例」改寫成「這是 prod 的鏡像，改來源要同步這裡」。
- [ ] T004 [P] [US2] 同 T003，對 `config/sources_ffxiv.example.yml`。
- [ ] T005 [US2] 在 `.github/workflows/traffic_daily.yml` 的漂移檢查之前，補一步寫入 `config/sources_ffxiv.yml`
      （照 `weekly.yml` 的寫法，從 `vars.SOURCES_FFXIV_YML`）。沒有這一步，FFXIV 鏡像一列進清單，daily 就會因缺檔而紅。
- [ ] T006 [US2] **RED** 改寫 `tests/unit/test_check_config_drift.py` 的守門員 `test_only_declared_mirrors_are_checked`：
      期望集合加入兩份 sources；docstring 改寫成「2026-10-13 起 sources 的 example 是鏡像（`crb`），清單的成員要與
      各 example 檔頭自稱的身分一致」。**先確認它會紅。**
- [ ] T007 [US2] 在 `scripts/check_config_drift.py` 的 `MIRRORED` 加入兩份 sources，改寫檔頭那段「刻意不在清單裡——不要順手補完」
      為現在的理由（前提換了：example 已同步）。本機跑腳本要綠，T006 要綠。
- [ ] T008 [US2] 咬合驗證：在 scratchpad 複製一份 `sources_traffic.example.yml`、改掉一個來源的 `enabled`，用腳本的比對函式
      對它比一次，要紅並指出鍵路徑；還原不涉及主工作區。

**Checkpoint**: 來源清單的現況在 git 裡、與 prod 一致，且有每天跑的執行者。

---

## Phase 3: User Story 3 - 來源會不會進池、進的是不是正題 (Priority: P2)

**Goal**: 每天看得見每個來源掉在哪一關（C1）；週報看得見池裡每個來源幾篇（C2）；上線前能評估一份提案清單（C3）。

**Independent Test**: 用評估工具跑現行清單，`Google News 天下交通` 的漏斗要顯示「收集 > 0、過濾 0」，與 research R1 一致；
`Google News 交通安全教育` 要有匯流四類篇數。

### Tests for User Story 3 ⚠️

> **先寫、先確認會失敗，再實作**

- [X] T009 [P] [US3] **RED** 新增 `tests/unit/test_source_funnel.py`，對漏斗記帳的純函數：每一關逐來源計數（C1-2 單調不增）；
      收集為 0 的來源（只出現在嘗試名單）也有一列（C1-1）；匯流四類篇數只算 `major_category` 在匯流四類者；
      log 行與 C1 的格式逐字相同；向量去重沒跑時 `f` 等於 `e`（C1-3）。
- [X] T010 [P] [US3] **RED** 在 `tests/unit/test_digest_pool.py` 補 `log_digest_pool_sources` 的 caplog 測試：降冪、同數依名稱（C2-1）；
      篇數總和等於池大小（C2-2）；空池不印（C2-3）；格式逐字相同。
- [X] T011 [P] [US3] **RED** 新增 `tests/unit/test_evaluate_sources.py`：唯讀代理對 `select` 放行、對 `upsert`／`insert`／`update`／`delete`
      raise（C3-1）；`source_defaults` 合併進暫存的 categories 副本、原檔不變（C3-3）；提案檔不是 `sources:` list 或缺 `name`／`type`
      時以非零結束並說明（C3-5）。

### Implementation for User Story 3

- [X] T012 [US3] 在 `src/pipeline/traffic.py`：`collect()` 接受選用的 `sources` 參數（預設照舊 `load_sources()`），記下嘗試的來源名單；
      `filter()` 在每一關之後用 T009 的純函數記帳，存成 `self.last_funnel`，並逐來源印 C1 的行（含 0 篇的來源）。
      daily 呼叫端（`scripts/traffic_buffer.py`）的行為不變。PR 內文要寫原則 I–III 的符合性（管線模組）。
- [X] T013 [P] [US3] 在 `src/topic_scoring.py` 新增 `log_digest_pool_sources`，並在 `scripts/traffic_weekly_analysis.py` 緊接
      `log_digest_pool_concentration` 之後呼叫（C2）。
- [X] T014 [US3] 新增 `scripts/evaluate_sources.py`（C3）：讀提案檔 → 驗證格式 → 合併 `source_defaults` 到暫存 categories 副本並設
      `CATEGORIES_TRAFFIC_YML_PATH` → 換上唯讀代理 → `TrafficCategory().collect(sources)` → `.filter(raw)` → 印逐來源漏斗、
      每個來源的匯流四類標題、embedding 呼叫篇數、逐來源收集耗時。依賴 T012。
- [X] T015 [US3] 真實入口驗證：複製 `config/sources_traffic.yml` 到 scratchpad 當提案檔，跑 T014。確認 `天下交通` 整批掉在過濾那關、
      `交通安全教育` 有匯流四類篇數、唯讀代理沒有被觸發、`config/` 底下沒有任何檔案被改。輸出摘要寫進
      `specs/014-policy-source-expansion/evaluation.md` 的「現行清單基準」一節。

**Checkpoint**: 漏斗、池來源 log、評估工具都通過測試，評估工具在真實資料上重現了 research R1。

---

## Phase 4: User Story 1 - 政策彙整的深度不再繫於單一 feed (Priority: P1) 🎯 目標

**Goal**: 調整既有來源、加新來源，讓非最大來源每週撐得過 `trigger_count`。

**Independent Test**: 上線前：每個採用的來源在評估中「進匯流四類且判讀為正題 > 0」（SC-001 Gate）。
上線後：週報 log 的「抽掉最大剩 N」與「池來源」行（週驗收 routine 追）。

- [X] T016 [US1] 評估既有來源的調整（research R7）：`報導者交通` 收窄 query 並設豁免、`天下交通` 收窄或停用；查 `道安統計`、
      `區間測速科技執法`、`交通部` 當期 0 篇的原因。每個方案各寫一份提案檔跑 T014，結果（漏斗、標題與逐篇判讀、embedding 篇數、
      收集耗時）寫進 `evaluation.md`。
- [X] T017 [US1] 評估新增 query（research R7 的方向：政策行為者與事件）。同 T016 的記錄方式；標題會帶 `行人`／`路口` 的要特別看分類。
      量少的候選隔幾天再評一次，不因單次 0 篇下結論。
- [ ] T018 [US1] 彙整採用清單到 `evaluation.md`：每個來源的 Gate 結果（正題進池篇數）、合計是否達 research R6 的目標（每週多 10 篇非最大來源）、
      runtime 增量估算（每來源約 1.5 秒／run）、embedding 增量。**交 Luke 裁示採用哪些**（`[你]`）。
- [ ] T019 [US1] 把採用的變更寫進本機 `config/sources_traffic.yml`（需要時加 `config/categories_traffic.yml` 的 `source_defaults`），
      同步兩份對應的 example 鏡像；本機漂移檢查要綠。
- [ ] T020 [US1] 改 prod 變數（`gh variable set … --env production < 檔案`，不用 `--body`），讀回後 YAML parse 比對物件相同。
      **動手前再跟 Luke 確認一次**（對外、會影響隔天的 daily）。
- [ ] T021 [US1] 上線後第一個 daily：新增或調整的來源都有 C1 漏斗行、漂移檢查綠、runtime 沒有異常；結果寫進 `evaluation.md`。

**Checkpoint**: SC-001 Gate、SC-003 通過——可以 closeout（spec「驗收時點」）。

---

## Phase 5: Closeout & Polish

- [ ] T022 `specs/BACKLOG.md`：`python3 ~/.agents/bin/backlog.py add` 新增一列追 SC-001 L1／L2 與 SC-002（含停用判準），
      把 `GNS-008` 節的常設重開條件搬進新列的小節；再用 `backlog.py remove` 移出 `GNS-008` 與 `GNS-20261005-crb`，讀 diff 確認。
- [ ] T023 [P] `routines/weekly-verify/PROMPT.md` 的常設檢查 (A) 改指新列；`routines/weekly-verify/FOCUS.md` 寫入要追的來源名單，
      以及怎麼讀 C1／C2 的行（名單上的來源沒出現在「池來源」＝0 篇）。
- [ ] T024 [P] spec.md 補「達成階數」一節（Gate、SC-003 的實測；L1／L2 標明交給 routine），PR 內文寫實際做了什麼
      （採用與放棄的候選、各自的評估數字）與一行 `Backlog:`。

---

## Dependencies & Execution Order

- **Phase 1（T001）**：已移出範圍（PR #163）。#163 merge 後再開始 US2。
- **Phase 2（US2）**：T002 → T003／T004（平行）→ T005 → T006 → T007 → T008。
- **Phase 3（US3）**：T009／T010／T011 平行（RED）→ T012 → T013（可與 T012 平行，不同檔）→ T014（依賴 T012）→ T015。
- **Phase 4（US1）**：依賴 Phase 2（鏡像在，T019 才有地方同步）與 Phase 3（T014 評估工具）。T016／T017 可交錯 → T018（Luke 裁示）→ T019 → T020（Luke 確認）→ T021。
- **Phase 5**：T021 之後。

### Parallel Opportunities

- US2 與 US3 整段平行（不同檔案）。
- T003／T004；T009／T010／T011；T012／T013；T023／T024。

## Implementation Strategy

1. US2 與 US3 先做，各自是可獨立驗收的增量：US2 合了，來源清單就在 git 裡；US3 合了，daily 就看得見每個來源的漏斗。
2. US1 的評估（T016–T018）是人機協作：工具出數字與標題，判讀與採用由 Luke 裁示。
3. 上線（T020）之後 Gate 與 SC-003 一過就 closeout；L1／L2 交給週驗收 routine。
