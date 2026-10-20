---

description: "Task list for 015-ffxiv-sampling-fix"
---

# Tasks: FFXIV 週報取樣修正

> Markers: [ ] not started · [-] implemented, awaiting review · [X] reviewed + verified (verification-only task: main-verified)

**Input**: Design documents from `/specs/015-ffxiv-sampling-fix/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/sources-ffxiv-config.md, contracts/log-lines.md, quickstart.md

**Tests**: **要。** FR-005、FR-007 明訂 unit test；contracts/log-lines.md 的四行有讀者（週驗收 routine），格式用測試鎖住。
每個 user story 先寫測試、確認會因為「還沒實作」而紅，再實作。

**Task markers are three-state**（本 repo 的 delegated-TDD 接線）：
`[ ]` 未開始 → `[-]` 已實作、待審 → `[X]` 已審且 main 驗證過 → `[~]` 移出範圍
驗證型 task（main 跑真實入口或咬合實驗、記下結果，沒有實作）由 main 驗證即可標 `[X]`，不派 reviewer：T021、T025、T026、T027。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行（不同檔案、無未完成依賴）
- **[Story]**: 對應 spec.md 的 user story

## Path Conventions

單一專案：`src/`、`config/`、`tests/unit/`、`tests/fixtures/` 皆在 repo 根目錄。
⚠️ `python` 不在 PATH，一律用 `.venv/bin/python`。新檔的註解／docstring 區塊 ≤ 3 行（`test_comment_budget.py`）。
⚠️ 測試不打網路：`_fetch_rss_bytes`、`requests.get`、`time.sleep` 一律 patch；HTML 用 `tests/fixtures/ffxiv/` 的片段。

## 階段順序與 spec 優先度的關係

US1、US2 都是 P1，但都依賴 Phase 2 的排序基礎（權重蓋章、排序鍵、去重前排序）。US3、US4 互不依賴，也不依賴 US1／US2。
**SC-004 的實測（T026）要在改 prod 的 Lodestone 設定（T027）之前**——用舊設定證明「0 項出聲」咬得到。

---

## Phase 1: Setup

**Purpose**: 測試要的 HTML 片段，取自真實頁面（research R2、R6），裁到最小。

- [ ] T001 [P] 抓真實頁面存成 fixtures，裁到每檔只剩測試需要的節點、不加註解：
      `tests/fixtures/ffxiv/thread_last_page.html`（含 `Today`／`Yesterday` 時間各至少 1 則、`li[id^=post_]`、`span.date`、
      `[id^=post_message_]`、「Page N of N」）、`tests/fixtures/ffxiv/thread_prev_page.html`（絕對日期 `MM-DD-YYYY hh:mm AM/PM`）、
      `tests/fixtures/ffxiv/lodestone_category3.html`（至少 4 個 `li.news__list`：遊戲更新 2 則、`Lodestone` 開頭 1 則、
      `コンパニオンアプリ` 開頭 1 則，各帶 `ldst_strftime(<epoch>`）、`tests/fixtures/ffxiv/lodestone_detail.html`
      （含 `div.news__detail__wrapper`）。來源網址與抓取日（2026-10-20）寫在 `tests/fixtures/ffxiv/SOURCES.md`。

---

## Phase 2: Foundational（排序基礎，US1／US2 都依賴）

**Purpose**: 權重從來源設定蓋到文章上；FFXIV 排序鍵；去重前排序；候選池與入選的 log（FR-004 的機制、FR-010）。

### Tests（先寫、先紅）

- [X] T002 [P] `tests/unit/test_ffxiv_ranking.py`：
      (a) `collect_sources` 對帶 `weight` 的來源把 `source_weight` 蓋到每篇文章；沒帶的不蓋。
      (b) 排序鍵：權重降冪 → `published` 降冪 → 沒有 `published` 的排最後；沒有 `source_weight` 的當 0。
      (c) `game_deduplicate` 依排序鍵取前 20；沒有任何權重時結果與現行（依時間）相同——既有 `test_game_deduplicate.py` 不改、仍綠。
      (d) 候選池與入選兩行的格式完全等於 contracts/log-lines.md（依篇數降冪、`、` 分隔），用 `caplog` 斷言整行字面值。
- [X] T003 [P] `tests/unit/test_ffxiv_filter_order.py`：`FFXIVCategory.filter()`（patch `is_configured` 為 False）收到同標題的兩篇——
      論壇列表頁（`source_weight` 10、只有標題）在前、論壇版（80、有全文）在後——留下的是論壇版那篇。
      另一條：來源沒有 `source_weight` 時，每個來源印一次 `<來源>: 未設 weight，排在最後`。

### Implementation

- [X] T004 `src/collector.py`：`collect_sources` 依來源的 `weight` 蓋 `source_weight`（與 `relevance_exempt`、`lookback_days` 同一處、同一做法）。
- [X] T005 `src/filter.py`：新增 FFXIV 排序鍵函式；`game_deduplicate` 改依排序鍵排序與取前 20，並印候選池（Jaccard 去重後、截斷前）
      與入選兩行；docstring 跟著改（≤ 3 行）。
- [X] T006 `src/pipeline/ffxiv.py`：`filter()` 在 `freshness_filter` 之後、`filter_and_deduplicate` 之前依排序鍵排序；
      對沒有 `source_weight` 的來源各印一次警告。

**Checkpoint**: `pytest tests/unit` 全綠；T002、T003 在實作前是紅的（記在 commit 內文）。

---

## Phase 3: User Story 1 - 週報的 FFXIV 分析看得到日文論壇的玩家討論 (Priority: P1) 🎯 MVP

**Goal**: 五個論壇版以 `vb_forum` 收窗口內的回覆合成一篇；長期串每週有新回覆就能再進來，同一則回覆不分析兩次。

**Independent Test**: T021——本機跑真實入口，log 有每串「窗口內 N 則、收 M 則、翻 P 頁」，候選池裡有論壇版的篇數。

### Tests（先寫、先紅）

- [X] T007 [P] [US1] `tests/unit/test_vb_forum_window.py`：窗口函式——給定「現在」，回傳［該 ISO 週週一 00:00 UTC − 7 天, 該週一 00:00 UTC）；
      週一 00:30Z 與週一 02:30Z、週三同一週都得到同一個窗口；週日 23:59Z 得到前一個窗口。
- [X] T008 [P] [US1] `tests/unit/test_vb_forum_parse.py`：用 T001 的 fixtures 解析回覆（id、時間、內文）：
      `10-15-2026 01:16 PM` 是日本時間 → `2026-10-15T04:16:00+00:00`；`Today`／`Yesterday` 以注入的「現在」的日本日期解析
      （含現在是日本時間凌晨、UTC 仍是前一天的情況）；解析不出的時間回報失敗而不是猜；前一頁網址 `<串網址>/page<N-1>` 從「Page N of N」推得。
- [X] T009 [US1] `tests/unit/test_vb_forum_collect.py`（patch `_fetch_rss_bytes`、`requests.get`、`time.sleep`）：
      (a) 只處理 RSS 最後回覆 ≥ 窗口起點的串；(b) 只收窗口內的回覆，往前翻到頁上最早一則 < 窗口起點或到 `max_pages`；
      (c) 超過 `max_replies` 丟最舊的、合併後截到 `max_chars`，依時間由舊到新、每則前標時間；
      (d) `link`＝`<guid>?p=<窗口內最新回覆 id>`、`dedup_key`＝`forum:<串 id>:<最新回覆 id>`、`published`＝最新回覆時間；
      (e) 窗口內 0 則的串不產出；(f) 三種退回（請求失敗、解析不到回覆、時間解析不出）各印 contracts/log-lines.md 那一句、
      各自退回 RSS 最後一則（若在窗口內）——三句彼此不同；(g) 翻頁上限一句；(h) RSS 回滿 15 筆且第 15 筆 ≥ 窗口起點時印截斷警告，
      14 筆或第 15 筆在窗口外時不印；(i) 每串一行「窗口內 N 則、收 M 則、翻 P 頁」；(j) RSS 回 0 筆不算失敗。
- [X] T010 [P] [US1] `tests/unit/test_forum_dedup_key.py`：`freshness_filter` 對帶 `dedup_key` 的文章略過標題指紋（即使指紋在集合裡也保留）、
      印「跨週去重略過標題指紋（以回覆去重）」；年齡檢查照做；不帶 `dedup_key` 的行為不變。

### Implementation

- [X] T011 [US1] `src/collector.py`：窗口函式、回覆時間解析（日本時間、Today／Yesterday、注入「現在」）、討論串頁面解析（回覆 id、時間、內文、前一頁網址）。
- [X] T012 [US1] `src/collector.py`：`_fetch_vb_forum(source)` 並註冊進 `FETCHERS["vb_forum"]`——讀 RSS（`_fetch_rss_bytes`）、選串、翻頁、
      收回覆、合併與上限、退回、截斷警告、每串一行 log；分頁請求之間 `time.sleep(1)`；上限的初值 3／20／6000（設定可覆寫）。
- [X] T013 [US1] `src/filter.py`：`freshness_filter` 對帶 `dedup_key` 的文章略過標題指紋並印一行。

**Checkpoint**: T007–T010 綠；`pytest tests/unit` 全綠。

---

## Phase 4: User Story 2 - PLL 有新串時一定進分析 (Priority: P1)

**Goal**: PLL 與 25 篇更新的 Reddit 並存時一定入選；測試用字面值權重，咬得到。

**Independent Test**: T015 綠；把 PLL 權重改低後 T015 紅（T025）。

- [X] T014 [US2] 先確認 Phase 2 之後這條是否已綠：若是，T015 直接寫成回歸測試並在 T025 證明它咬得到；若否，補實作到綠。
- [X] T015 [US2] `tests/unit/test_pll_priority.py`：PLL（`source_weight` 100、`published` 比 Reddit 舊 6 天）＋ 25 篇 Reddit（20、最近 16 小時）
      ＋ 論壇版 3 篇（80）＋ 論壇列表頁 15 篇（10、沒有時間）→ 入選 20 篇裡有 PLL、3 篇論壇版、16 篇 Reddit、0 篇列表頁。
      權重寫字面值，不讀設定檔。

---

## Phase 5: User Story 3 - Lodestone 的アップデート進得來 (Priority: P2)

**Goal**: html_patch 支援發布時間、排除標題前綴、詳細頁內文；log 印「解析 N 則、收進 M 則」。

**Independent Test**: T016 綠；T021 本機真實入口 Lodestone 解析 > 0。

- [ ] T016 [P] [US3] `tests/unit/test_html_patch_options.py`（用 T001 的 Lodestone fixtures，patch `requests.get`）：
      `date_pattern` 抽出 UTC epoch 當 `published`、只收 `CUTOFF` 之後的；`exclude_title_prefixes` 排除兩種前綴；
      `detail_selector` 有寫時 `summary` 是詳細頁文字（截到 `max_chars`）；詳細頁請求失敗時只用標題並印一句原因；
      log 行「解析 N 則、收進 M 則（窗口外 a、排除 b）」格式等於 contracts/log-lines.md；三個選項都不寫時行為與現行相同。
- [ ] T017 [US3] `src/collector.py`：`_fetch_html_patch` 加 `date_pattern`、`exclude_title_prefixes`、`detail_selector`、`max_chars` 四個選用設定與 log 行；
      詳細頁請求之間 `time.sleep(1)`。

---

## Phase 6: User Story 4 - 爬蟲解析出 0 項時會出聲 (Priority: P2)

**Goal**: html_patch、html_forum、PTT 回 200 但 selector 對到 0 個節點時記成來源失敗；篩選後 0 與 RSS 0 不算。

**Independent Test**: T018 綠；T026 用舊的 Lodestone 設定跑，`來源失敗` 名單有 Lodestone。

- [X] T018 [P] [US4] `tests/unit/test_parsed_zero_signal.py`（patch `requests.get`／`requests.Session.get`）：
      html_patch selector 對到 0 → 失敗名單有它、印 contracts/log-lines.md 那一句；html_forum 0 個 `threads/\d+` 連結 → 同上；
      PTT 0 個 `div.r-ent` → 同上；PTT 有 `div.r-ent` 但推文數都不到門檻 → 不算失敗；RSS 0 筆 → 不算失敗；
      `collect_sources` 的 `來源失敗：N/M` 彙總行把它們算進去。
- [X] T019 [US4] `src/collector.py`：共用的「解析出 0 項」判斷，接進 `_fetch_html_patch`、`_fetch_html_forum`、`_fetch_ptt`（在任何篩選之前判斷）。

---

## Phase 7: 設定、驗證與 closeout

**Purpose**: 鏡像 example、真實入口驗證、咬合實驗、routine、BACKLOG。prod 變數在 merge 後才改（plan「上線順序」）。

- [ ] T020 `config/sources_ffxiv.example.yml`：五個論壇版改 `type: vb_forum`、網址加 `lastpost=1`、加三個上限；Lodestone 改 `category/3`、
      `selector: li.news__list`、加 `date_pattern`／`exclude_title_prefixes`／`detail_selector`／`max_chars`；每個來源加 `weight`
      （contracts/sources-ffxiv-config.md 的初值）。檔頭的型別說明加 `vb_forum`。
- [ ] T021 [US1] 驗證型：照 quickstart「本機驗證」用 T020 的設定跑 `FFXIVCategory().collect()` 與 `.filter()`（不分析、不寫庫），
      把候選池／入選逐來源篇數、每串的回覆數與退回、Lodestone 解析／收進、收集耗時與請求數寫進 `specs/015-ffxiv-sampling-fix/evaluation.md`。
      通過條件：論壇版至少產出 1 篇（若窗口內有串）、Lodestone 解析 > 0、沒有未預期的退回。
- [ ] T022 `routines/weekly-verify/FOCUS.md`：加一項「015 上線後」——讀候選池與入選兩行，判 SC-001 Gate／L1（論壇版入選數 vs 窗口內串數）、
      SC-002 Gate（Lodestone 解析 > 0）、SC-005（週報 ≤ 30 分、FFXIV 那段耗時）、記 SC-006 候選池總數，結果寫回 BACKLOG
      `GNS-20261020-sbe` 的「逐週紀錄」；適用週照現行不動。
- [ ] T023 `specs/BACKLOG.md`（實作那一列的 closeout）：用 `python3 ~/.agents/bin/backlog.py remove specs/BACKLOG.md GNS-20261019-a0r`
      移出 `a0r`（連同小節）。驗收那一列 `GNS-20261020-sbe` 已在 tasks 階段建立（Luke 10-20 裁示實作與驗收分兩列），
      這裡只核對它的觸發點與完成標準仍與 spec 一致；`GNS-20261019-3cq` 的觸發點改成「`sbe` 記到約一週的候選池、
      遠大於 20 篇時，考慮調整輸出形式（對齊交通週報的彙整，或第三套方法）」；`GNS-016` 小節記下觸發點被 015 踩到、
      只接了「0 項出聲」那一半，403 成因仍開著。
- [ ] T024 `specs/015-ffxiv-sampling-fix/spec.md`：「達成階數」小節（同 014 的形狀），填 merge 前已有的數字（SC-003、SC-004、T021），其餘標「交給 routine」。

### 驗證型（main 驗證，不派 reviewer）

- [ ] T025 咬合實驗（在 scratchpad 的 worktree，pin 受審的 SHA）：把 PLL 權重 100 改成 10 → T015 紅；
      把排序鍵的權重項拿掉 → T002(b)／T015 紅；把「去重前排序」拿掉 → T003 紅；把 `dedup_key` 略過拿掉 → T010 紅；
      把窗口改回「現在往前 7 天」→ T007 紅。每一項記下「紅的是哪幾條」。
- [ ] T026 SC-004 實測（改 Lodestone 設定之前）：照 quickstart 用 prod 現行的 `SOURCES_FFXIV_YML` 跑一次收集，
      `來源失敗` 名單有 `FFXIV Lodestone JP 更新資訊`、有「回 200 但解析出 0 項」那一句。結果寫進 evaluation.md。
- [ ] T027 merge 之後（[你]）：`gh variable set SOURCES_FFXIV_YML --env production < config/sources_ffxiv.yml`，
      `gh variable get … | diff - config/sources_ffxiv.yml` 逐位元組相同；同一天、避開週一 00:00 UTC 前後。

---

## Dependencies & Execution Order

- **Phase 1（T001）** → T008、T016 用它的 fixtures。
- **Phase 2（T002–T006）** → US1、US2 都依賴。
- **US1（T007–T013）**、**US3（T016–T017）**、**US4（T018–T019）** 在 Phase 2 之後可平行（US3、US4 其實不依賴 Phase 2）。
- **US2（T014–T015）** 依賴 Phase 2；與 US1 無依賴。
- **T020** 依賴 US1、US3 的型別與選項已實作；**T021** 依賴 T020；**T026** 依賴 US4 實作、必須在 T027 之前。
- **T022、T023、T024** 在 T021 之後（要填數字）；**T025** 在所有實作之後；**T027** 在 merge 之後。

### Parallel Opportunities

- T001、T002、T003 可同時開始。
- Phase 2 之後：US1 的測試（T007、T008、T010）、T015、T016、T018 都是不同檔案，可同時寫。
- 實作都在 `src/collector.py`（T004、T011、T012、T017、T019）——同一檔，**不可平行**，依 Phase 順序做。

## Implementation Strategy

**MVP**：Phase 2 ＋ US1。只做到這裡，論壇版就能進分析、不會被 Reddit 擠掉（SC-001 Gate）。
**Incremental**：US2（PLL 的測試）→ US4（0 項出聲，並做 T026）→ US3（Lodestone）→ Phase 7。
US4 排在 US3 前面：T026 要用「已有 0 項出聲、但 Lodestone 設定還沒改」的狀態，順序反過來就沒有那個狀態可以量。
