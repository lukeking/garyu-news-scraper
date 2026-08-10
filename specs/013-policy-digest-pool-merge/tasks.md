---

description: "Task list for 013-policy-digest-pool-merge"
---

# Tasks: 政策 digest 池匯流兄弟政策類別

**Input**: Design documents from `/specs/013-policy-digest-pool-merge/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/digest-pool.md, quickstart.md

**Tests**: **明確要求。** research R4 訂了逐條測試表與「改壞就會失敗」的判準，
quickstart 步驟 1 要求實際跑一次突變驗證。本功能改動面 100% 落在純函數與設定驗證
（不像 011／012 有只能手動驗收的前端缺口），**沒有理由降低驗證強度**。

**Task markers are three-state**（本 repo 的 delegated-TDD 接線）：
`[ ]` 未開始 → `[-]` 已實作、待審 → `[X]` 已審且 main 驗證過 → `[~]` 移出範圍

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行（不同檔案、無未完成依賴）
- **[Story]**: 對應 spec.md 的 user story

## Path Conventions

單一專案：`src/`、`scripts/`、`config/`、`tests/unit/` 皆在 repo 根目錄。
⚠️ `python` 不在 PATH，一律用 `.venv/bin/python`。

---

## Phase 1: Setup

**Purpose**: 建立變更前的對照組。**這一步不可跳過**——反事實必須被建構，
變更後就再也拿不到「未匯流」的數字了。

- [X] T001 以離線重播記錄變更前基準，寫入 `specs/013-policy-digest-pool-merge/baseline-0810.md`：
      對 `buffered_at ≥ 2026-08-04` 的窗口，記下 `pool_all`／`effective`／`selected` 三層數量、
      `distinct_sources`、最大來源佔比、抽掉最大來源後的餘量，以及現行 25 篇選材的
      link＋quality 清單（供 **T008** 的擠出歸因比對）。指令見 quickstart 步驟 2。

**Checkpoint**: 對照組已存檔，可以開始改動。

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 設定契約與驗證。**所有 user story 都經由這個鍵取得行為**，故為阻擋前置。

**⚠️ CRITICAL**: 本階段完成前，任何 user story 都不能開始

- [X] T002 [P] **RED** 在 `tests/unit/test_pipeline_config.py` 補 `include_categories` 的驗證測試：
      缺鍵補 `[]`（C1-1）、非 list 拋 `RuntimeError`（C1-2）、元素非字串拋 `RuntimeError`（C1-3）、
      未知類別名記 WARNING 但不中止（C1-4）。**先確認這些測試會失敗再往下。**
- [X] T003 在 `src/pipeline_config.py` 的 `category_digest` 驗證區塊（約 118–144 行）
      加入 `include_categories`（**FR-006**）：`digest_defaults` 補 `"include_categories": []`，
      並依 C1-2／C1-3 驗證型別、依 C1-4 對未知類別名記 WARNING。
      錯誤訊息沿用既有形式（含類別名與設定檔路徑）。
      ⚠️ **必須是 WARNING 而非靜默略過**——憲章原則 I 禁止靜默失敗，見 research R1。

**Checkpoint**: 設定鍵可被安全載入，T002 全綠。

---

## Phase 3: User Story 1 - 政策彙整不再靠單一 feed 撐 (Priority: P1) 🎯 MVP

**Goal**: digest 池能涵蓋指定的兄弟類別，使「抽掉最大來源」後仍達觸發門檻。

**Independent Test**: 對任一週 buffer 快照離線重播，比對匯流前後的 `distinct_sources`
與「抽掉最大來源後的有效篇數 vs `trigger_count`」。不需等新資料、不需外部服務。

### Tests for User Story 1 ⚠️

> **先寫、先確認會失敗，再實作**

- [X] T004 [P] [US1] **RED** 在 `tests/unit/test_digest_pool.py` 補匯流測試：
      給含兄弟類別的輸入，斷言它們進入 `pool_all` 與 `effective`（C2-1／C2-2）；
      斷言 `excluded_links` 中的兄弟類別文章**不得**進池（C2-4／INV-3）；
      斷言清單含主類別自己時不重複計數（C1-5／INV-6）；
      斷言清單順序不影響輸出（C1-6）。

### Implementation for User Story 1

- [X] T005 [US1] 在 `src/analyzer.py::select_digest_pool`（約 1105–1128 行）
      把 `major_category` 的單一字串相等比對改為集合成員判定（**FR-001／FR-004／FR-008**）：
      `cats = {category} | set(digest_cfg.get("include_categories") or [])`。
      **簽章不變**（C2）、`quality_floor`／`max_articles`／排序規則**完全不變**（C2-5）、
      **不得在文章上原地附加任何欄位**（C2-3／INV-2）。
- [X] T006 [US1] 在 `scripts/traffic_weekly_analysis.py` 的 digest 迴圈（約 118–126 行）
      加入池組成 log（**FR-007**／C3）：逐來源類別各印一項含篇數、**零篇也要印**（C3-1）、
      匯流清單為空時**不印**（C3-2）、印在觸發判定**之前**（C3-3）。
- [X] T007 [US1] 離線重播驗收 **SC-001**，結果寫回 spec 的達成階數表：
      L0（`distinct_sources` 嚴格變大）／L1（抽掉最大來源後 ≥ `trigger_count`＝承重解除）／
      L2（最大來源佔比 ≤ 50%，**預期未達成**，如實記錄）。指令見 quickstart 步驟 2。
- [X] T008 [US1] 離線重播驗收 **SC-002（內容不流失）**，結果寫回 spec 的達成階數表。
      以 T001 的基準清單比對匯流前後的 `selected`：
      **L0 / Gate** — 逐筆歸因每一個被擠出者（「被分數更高的匯流文章取代」），
      **不得有無法解釋的消失**，且擠出數 ≤ 新進數；
      **L1** — 擠出者分數**全部低於**新進者最低分（無交錯）；
      **L2** — 擠出數為 0（**預期未達成**，需 `max_articles ≥ effective`，屬編輯決定，如實記錄）。
      ⚠️ **若出現分數交錯**（某擠出者高於某新進者），表示排序邏輯被動到了——
      停下來回頭查 T005，不要直接記為「未達 L1」。

**Checkpoint**: US1 可獨立驗證——承重是否解除、內容是否流失，離線都能回答。

---

## Phase 4: User Story 2 - 被丟掉的政策內容進得了報告 (Priority: P2)

**Goal**: 兄弟類別文章被消耗，不再只佔資料庫。

**Independent Test**: 斷言匯流後 `pool_all` 涵蓋兄弟類別文章，且消耗以 `pool_all` 為準。

**⚠️ 本階段預期無新增產品程式碼**：消耗用的是 `pool_all`（`traffic_weekly_analysis.py:233`），
而 T005 已讓 `pool_all` 涵蓋兄弟類別——US2 因此是 T005 的結構性結果。
本階段的工作是**把這個隱含結果變成明文斷言**，否則它會在未來某次重構中無聲消失。

### Tests for User Story 2 ⚠️

- [X] T009 [P] [US2] **RED→GREEN** 在 `tests/unit/test_digest_consume.py` 補測試（**FR-005**）：
      斷言匯流進池的兄弟類別文章出現在消耗名單中（INV-7）；
      斷言 `selected ⊆ effective ⊆ pool_all` 在匯流下仍成立（INV-4）；
      順帶確認 `len(selected) ≤ max_articles`（INV-5）在既有測試中已被守住，沒有就補上。
      **若此測試一開始就是綠的，記錄該事實**——那代表行為已由 T005 提供，
      但仍需這條測試把它釘住（見本階段說明）。

### Implementation for User Story 2

- [X] T010 [US2] 驗證「消耗未發布」的差額並記錄：離線比對 `len(pool_all) - len(selected)`
      在匯流前後的變化（基準：12/37 → 21/46），並確認擴大的部分**全部落在低分填充稿**、
      兄弟類別文章全數進入 `selected`。**若此前提被推翻**（有兄弟類別文章落在
      `selected` 之外），停下來回報——那會推翻澄清 Q1 的決策依據。

**Checkpoint**: 消耗語意有明文測試守住，且 Q1 的決策前提經實測確認。

---

## Phase 5: User Story 3 - 匯流名單可調且可逆 (Priority: P3)

**Goal**: 改設定即改變匯流範圍；清空即回到匯流前行為。

**Independent Test**: 空清單時輸出與改動前逐篇相同；改清單則池組成隨之改變。

### Tests for User Story 3 ⚠️

- [X] T011 [P] [US3] **RED** 在 `tests/unit/test_digest_pool.py` 補可逆性測試：
      **INV-1／C2-6**（不給 `include_categories` 時，三層輸出與只含主類別時**逐篇相同**，含順序）＝**FR-002**；
      **INV-2**（匯流前後每篇的 `major_category` 不變）＝**FR-003**。
      INV-1 是「預設關閉」的承重測試——**這條若是空的，整個「預設不改變行為」
      的保證就沒有東西守著**。

### Implementation for User Story 3

- [X] T012 [US3] 更新設定檔：`config/pipeline_config.yml` 的 `category_digest.道安政策`
      加入 `include_categories: [路權政策, 科技執法, 交通工程]`，
      並**同步** `config/pipeline_config.example.yml`（它是唯一進 git 的副本，
      不同步則此決策在 repo 裡不留痕跡）。附註明 `行人事故`／`路口安全` 為何不納入。

**Checkpoint**: 三個 user story 皆可獨立驗證。

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T013 **突變驗證**（quickstart 步驟 1）：對 T004／T009／T011 各挑一條，
      故意把實作改壞（集合改回單一字串比對／預設改成非空／選材時改寫 `major_category`），
      確認對應測試**確實變紅**，再改回來。**沒做這一步，無法分辨「測試通過」與
      「測試根本不可能失敗」**——本 repo 已有 `test_filter_attaches_category_and_score`
      長期失敗被標 latent 繞過的前例。將結果記入 quickstart 驗收欄。
- [X] T014 執行 `.venv/bin/python -m pytest tests/unit -q` 全綠（CI 的 required check `unit`）。
- [X] T015 設定驗證的負向測試實跑（quickstart 步驟 5）：把 `include_categories` 改成字串
      確認 `RuntimeError`；放一個不存在的類別名確認 **WARNING 且流程繼續**。
      **這兩條是本功能對憲章 I「禁止靜默失敗」的答覆，沒實跑過就只是宣稱。**
- [X] T016 **SC-003** 雜訊人工判讀（quickstart 步驟 4）：列出匯流新進文章標題逐篇判讀，
      **把哪幾篇離題、為什麼寫進驗收紀錄**。已知一例：「頻變換車道.行駛禁行機車道
      一查又是毒駕」。這個數字是 BACKLOG #7 的校準起點，**不得略過**。
- [ ] T017 Prod 部署（quickstart 步驟 6）：`gh variable set PIPELINE_CONFIG_YML --env production`
      後以 **YAML parse 比物件**確認一致。⚠️ **不可比位元組**——012 實測
      `gh variable set < 檔案` 會把尾端 `\r\n` 存成單一 `\n`，偏移不可預測。
- [ ] T018 上線後第一份週報驗收（quickstart 步驟 7）：確認 log 出現池組成行（含零篇類別）、
      `pool` 數字與離線重播一致、報告標題仍為「道安政策 · 彙整」（**FR-009**）。
      **此任務需等下一個週一**，不阻擋 PR merge。
- [ ] T019 Closeout：`specs/BACKLOG.md` 的 #8 由「轉行動」改為 ✅ 已完成（附 PR 編號），
      並更新 `STATE.md` 與 memory `project_digest_single_feed_dependency`。
      ⚠️ **三份是各自獨立的副本**，動一份不會連動另外兩份。

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1（Setup）**：無依賴，且**必須最先做**（對照組一旦錯過就拿不回來）
- **Phase 2（Foundational）**：依賴 T001；**阻擋所有 user story**
- **Phase 3–5（User Stories）**：皆依賴 Phase 2
- **Phase 6（Polish）**：依賴 Phase 3–5

### User Story Dependencies

- **US1（P1）**：Phase 2 完成後即可開始。**其餘兩個 story 的行為由 T005 一併提供**——
  這是本功能的實際形狀（核心改動只有一行集合運算），US2／US3 的價值在於**把隱含行為
  釘成明文斷言**，而不是各自增加程式碼。誠實標註此事，避免把任務拆得比工作本身複雜。
- **US2（P2）**：依賴 T005（測試對象）。無新增產品程式碼。
- **US3（P3）**：依賴 T005。僅新增測試與設定。

### Within Each User Story

- 測試先寫、先確認失敗，再實作
- **T007／T008 皆依賴 T001 的基準清單**（沒有對照組就無法歸因）
- 同檔案的任務不可平行（`tests/unit/test_digest_pool.py` 由 T004 與 T011 共用）

### Parallel Opportunities

- T002（`test_pipeline_config.py`）與 T004（`test_digest_pool.py`）不同檔，可平行
- T009（`test_digest_consume.py`）與 T011（`test_digest_pool.py`）不同檔，可平行
- ⚠️ **T004 與 T011 同檔，不可平行**

---

## Parallel Example

```bash
# Phase 2 與 Phase 3 的 RED 階段（不同檔案）：
Task: "T002 include_categories 驗證測試 in tests/unit/test_pipeline_config.py"
Task: "T004 匯流生效測試 in tests/unit/test_digest_pool.py"
```

---

## Implementation Strategy

### MVP（US1 only）

1. T001 對照組 → 2. Phase 2（T002–T003）→ 3. Phase 3（T004–T008）
4. **停下驗證**：承重是否解除（SC-001）、內容是否流失（SC-002）——離線重播即可回答兩者

到此已交付本 spec 的全部價值——BACKLOG #8 的承重依賴解除。
US2／US3 是把隱含行為釘住的保險，不是額外功能。

### 誠實標註：本功能的任務數多於它的程式碼量

核心改動是 `select_digest_pool` 的一行集合運算 ＋ 設定驗證 ＋ 一行 log。
19 個任務裡**只有 4 個會動到產品程式碼**（T003／T005／T006／T012），
其餘是測試、驗證與紀錄同步。這個比例是刻意的：改動小但**影響已發布的報告內容**，
而驗證成本遠低於一份錯誤週報的代價。

---

## Notes

- `[P]` ＝ 不同檔案、無依賴
- 三態標記：實作 commit 標 `[-]`，**審核＋main 驗證後**才標 `[X]`
- T018 需等下一個週一，不阻擋 PR merge——merge 時標 `[-]`，週報驗收後再標 `[X]`
