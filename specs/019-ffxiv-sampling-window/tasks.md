# Tasks: FFXIV 週報來源調整（拿掉 Reddit 與論壇列表頁、加收英文官方論壇）

**Input**: Design documents from `specs/019-ffxiv-sampling-window/`
**Prerequisites**: plan.md、spec.md、research.md、data-model.md、contracts/config-and-logs.md、quickstart.md

> Markers: [ ] not started · [-] implemented, awaiting review · [X] reviewed + verified (verification-only task: main-verified)

**Tests**: 要寫。SC-003、SC-004 是 unit test 的硬門檻，repo 走 delegated-TDD（三態標記 `[ ]` → `[-]` → `[X]`）。

**Organization**: US1（英文官方論壇）、US2（拿掉 Reddit）、US3（拿掉論壇列表頁）。US2、US3 只改設定、不等 spike，從 `main` 另開小 PR 先出貨（Unit 0，Luke 2026-11-10）；
US1 與上限在 `#210`。英文版的 id、時區與供給先由 spike 查（Phase 2），上限值由 Luke 核定後才寫進設定。

## Format: `[ID] [P?] [Story] [Req] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1／US2／US3
- **[Req]**: spec.md 的 FR／SC id

---

## Phase 1: Setup

沒有。不新增依賴、不新增模組（plan.md Technical Context）。

---

## Phase 2: Foundational（spike 與裁示，阻擋 US1 的設定與時間解析）

- [X] T001 Spike：英文子版 id 與時間格式、時區（research R3、R4）。對 642、656 的 RSS（`external.php?type=RSS2&forumids=<id>&lastpost=1`）各打一次，從每則的 `<category domain=…/forums/<id>-…>` 讀子版 id 與名稱，對出日文五個版的對應；每個對應的英文子版取一串，比對 RSS `pubDate`（GMT）與串頁面 `span.date` 的顯示，寫下格式與時區，存一份串頁面的 HTML 片段給 T004 當 fixture（`tests/fixtures/ffxiv/` 下，檔名照既有慣例）。請求之間至少隔 30 秒，429 就停、隔天再試或請 Luke 用瀏覽器看版頁。結果寫進 `specs/019-ffxiv-sampling-window/research.md` R3、R4。檢查 spec 的 Unchecked 假設「英文的五個子版各有對應…時間格式與時區可以解析」。
- [X] T002 Spike：英文各子版每週的供給（research R5）。用 T001 查到的 id，對各子版的 `lastpost=1` RSS 數本週窗口（`_forum_window`）內的串數；可以的話隔週再量一次。加上日文版與 Lodestone（`3cq` 節三週約 7～11 篇），在 research R6 提出分析篇數上限的建議值與多出的分析時間（每篇約 15～18 秒）。檢查 spec 的 Unchecked 假設「英文版每週窗口內的串數」。
- [X] T003 Luke 核定分析篇數上限的值（可以維持 20），寫進 `specs/019-ffxiv-sampling-window/spec.md` Clarifications 與 research R6。

**Checkpoint**: 英文子版的 id、時區、上限值都定了，US1 的設定與時間解析可以開始。

---

## Phase 3: User Story 1 - 英文社群的視角改由官方論壇英文版提供 (Priority: P1) 🎯 MVP

**Goal**: 英文對應的五個版照 015 的方式收集、與日文版同級競爭；上限改由設定決定，截掉論壇串時出聲。

**Independent Test**: unit test 綠且咬得到；上線後讀 log 與 `ffxiv-pool`，英文版各自一列、至少 1 串入選。

### Tests for User Story 1

- [X] T004 [P] [US1] [FR-002, SC-003] 在 `tests/unit/test_vb_forum_parse.py` 加英文串頁面的時間解析測試：用 T001 存的英文頁面片段，斷言回覆時間換成的 UTC 等於 RSS `pubDate` 對到的那一刻；`Today`／`Yesterday` 依頁面時區的日期。突變：把時區改成別的（例 UTC），測試轉紅。
- [X] T005 [P] [US1] [FR-003, SC-001] 在 `tests/unit/test_game_deduplicate.py` 加上限（`ffxiv.max_selected`）的測試：缺鍵 → 20（行為不變）；鍵為 25 → 取 25 篇；鍵不是正整數 → 報錯，不退回 20；上限截掉至少一篇論壇（`vb_forum`）項目時印一行 WARNING，格式照 `contracts/config-and-logs.md`，字面寫進斷言；沒截掉論壇時不印。

### Implementation for User Story 1

- [X] T006 [US1] [FR-002] 依 T001 的結果改 `src/collector.py`：英文頁面不是日本時間 → `vb_forum` 來源加一個時區欄位（缺欄位＝日本時間，日文版設定不用改），`_parse_vb_time`／`_parse_vb_page` 用它換算；是日本時間、格式相同 → 程式不改，在 research R4 寫明，T004 用英文樣本鎖住。
- [X] T007 [US1] [FR-003] 改 `src/filter.py` 的 `game_deduplicate`：上限從 `load_pipeline_config()` 的 `ffxiv.max_selected` 讀（`contracts/config-and-logs.md`），取代 `retained[:20]`；截掉論壇項目時印契約那一行。docstring 的「取前 20」一起改。
- [X] T008 [US1] [FR-003] 上限的設定鏡像與預算紀錄：`config/pipeline_config.example.yml` 加 `ffxiv.max_selected`（值照 T003）；`docs/external-services.md` Gemini 那一列的「每次篇數」改指向這個鍵，並讀一次 `src/pipeline/ffxiv.py` 的 `max_articles = 30` 有沒有被用到，結果寫進那一列（沒用到就照實寫，不在本 spec 刪它）。
- [ ] T009 [US1] [FR-001, FR-007] `config/sources_ffxiv.example.yml` 加英文五個 `vb_forum` 項目：名稱 `FFXIV EN Forum - <版名>`、url 用 T001 的 id、權重 PLL 100 其他 80、其他欄位沿用日文版；T006 若加了時區欄位，英文項目照實填。

**Checkpoint**: `pytest tests/unit` 全綠；英文樣本與上限的測試咬得到。

---

## Phase 4: User Story 2 - 拿掉 Reddit (Priority: P1)

T010、T011 在從 `main` 切的小 PR 出貨，不在 `#210`（Unit 0）；上線是 T016。

**Goal**: 週報不再對 reddit.com 發任何請求。

**Independent Test**: 上線後的 log 與 `ffxiv-pool` 沒有 Reddit；設定鏡像沒有 Reddit 項目。

- [X] T010 [P] [US2] [FR-004] `config/sources_ffxiv.example.yml` 刪掉 `Reddit r/ffxiv` 項目；檔頭的說明若提到 Reddit 一起改。既有測試（`tests/unit/test_ffxiv_ranking.py`、`test_pll_priority.py`）只拿「Reddit r/ffxiv」當 fixture 名稱，不讀設定，不改。

---

## Phase 5: User Story 3 - 拿掉論壇列表頁 (Priority: P2)

**Goal**: 候選池不再有論壇列表頁。

**Independent Test**: 上線後的 log 與 `ffxiv-pool` 沒有論壇列表頁；設定鏡像沒有那一項。

- [X] T011 [P] [US3] [FR-005] `config/sources_ffxiv.example.yml` 刪掉 `FFXIV JP Forum`（`html_forum`，`512-Japanese-Forums`）項目；`html_forum` 型別的說明改成「目前沒有來源使用」（research R2：型別與程式碼留著）。

---

## Phase 6: 上線與驗收

### 先出貨（US2、US3）

- [X] T016 [US2, US3] [FR-004, FR-005, FR-008] 小 PR 的上線：merge 之後、下一次 00:00Z 排程之前（時機的理由見 T012），`gh variable set SOURCES_FFXIV_YML --env production < config/sources_ffxiv.yml`（本機檔先與 example 對齊），`gh variable get` 讀回比對（去掉 CR），`scripts/check_config_drift.py` 通過。上線後第一個週一 07:00Z 前，FOCUS 加這週的檢查：Reddit 與論壇列表頁 0 篇、log 沒有對 reddit.com 的請求、FFXIV 篇數會少（日文版加 Lodestone 約 7～11 篇，不判 FAIL）。之後 `#210` 先 merge `origin/main` 再做 T009（同一個檔）。
- [ ] T017 [SC-002] 先出貨後第一份週報的讀回：讀 log 與 `gh run download <run id> -n ffxiv-pool`，記 SC-002 Gate，寫進 `specs/019-ffxiv-sampling-window/evaluation.md`（`#210`）。

### US1 上線

- [ ] T012 [FR-001, FR-003, FR-008] prod 設定：`#210` merge 後，`gh variable set SOURCES_FFXIV_YML --env production < config/sources_ffxiv.yml`、`PIPELINE_CONFIG_YML` 同法（本機檔先與 example 對齊，用重導向不用 `--body`），`gh variable get` 讀回逐位元組比對（去掉 CR），`scripts/check_config_drift.py` 通過。
  時機：merge 與兩個變數在同一個排程間隔內做完。daily 與週報都在 00:00Z 從 `main` 跑，daily 的 `check_config_drift.py` 比的是當時 `main` 的 example，`main` 與 prod 不一致時跨過 00:00Z 就紅，週報也會照舊設定跑。所以先 merge（缺鍵時 20，程式不怕設定晚到），隨即設變數、讀回、跑 drift check，不跨過 00:00Z；週一 00:00Z 是週報，不在週日深夜做。
- [ ] T013 [SC-001, SC-002, SC-004, SC-005] `routines/weekly-verify/FOCUS.md`：上線那一週與下一週加 019 的檢查——英文各版的候選與入選數、Reddit 與論壇列表頁 0 篇、截掉論壇那一行、`[ffxiv] 處理失敗`（上限設成非法值時只有這一行，job 不標紅；契約，Luke 2026-11-11）、`來源失敗` 有沒有論壇的 429、週報耗時；照 README「每週維護」的流程，在那一週 07:00Z 前 merge。
- [ ] T014 [SC-001, SC-002, SC-004, SC-005] 上線後第一次 prod 讀回：讀第一份週報的 log 與 `gh run download <run id> -n ffxiv-pool`，記 SC-001～SC-005 各階，英文版逐篇判讀「講得出這週在討論什麼」，寫進 `specs/019-ffxiv-sampling-window/evaluation.md`；另開 PR 把本 task 翻 `[X]`（018 T053 的做法）。之後的觀察放 FOCUS 與 BACKLOG。
- [ ] T015 Closeout（merge 前）：`specs/BACKLOG.md` 的 `GNS-20261019-3cq` 節記 019 的結果（取樣那半交給 019；Reddit 因 robots.txt 拿掉，patch-triggered 原設計用 Reddit 抓討論的那一半要另想，由 Luke 決定這一列怎麼改或移出）；跑 Feature closeout reconciliation；完整記憶掃描（`/memory-distill`，或說出略過的理由）。

---

## Dependencies & Execution Order

- Phase 2（T001→T002→T003）擋住 T004、T006、T008、T009（要 id、時區、上限值）。T005、T007 只要鍵名，可以先做。
- US2（T010）、US3（T011）不依賴 spike，先出貨（Unit 0，從 `main` 另開小 PR）。T009 改同一個檔（`config/sources_ffxiv.example.yml`），等小 PR merge、`#210` merge `origin/main` 之後再做。
- T016 在小 PR merge 的同一個排程間隔內；T017 在它上線後第一份週報之後。
- T012 在 `#210` merge 的同一個排程間隔內；T013 在上線那一週的週一 07:00Z 前；T014 在上線後第一份週報之後。

## Parallel Opportunities

- T004 與 T005（不同測試檔）。
- Unit 0（T010、T011、T016）與 Phase 2 並行：不同分支、不同 PR。

## Review units

### Unit 0: 先出貨：拿掉 Reddit 與論壇列表頁

- Tasks: T010, T011, T016
- Outcome: `config/sources_ffxiv.example.yml` 沒有 Reddit 與論壇列表頁；prod `SOURCES_FFXIV_YML` 與鏡像一致；FOCUS 在上線那週帶這兩項的檢查。
- Prerequisites: 無（不等 spike）。小 PR 從最新的 `origin/main` 切。
- Verification: YAML 有 7 項（日文 5、Lodestone、停用的 TW），`load_ffxiv_sources()` 載入 6 個啟用來源，沒有 `rss`、`html_forum` 型別的項目；`pytest tests/unit` 綠；
  上線後 `gh variable get` 讀回比對、`scripts/check_config_drift.py` 通過。
- Review: 小 PR 的 diff（`config/sources_ffxiv.example.yml`、FOCUS）、設定讀回結果。
- Merge or split: 兩項都是只改設定的移除、各自可以回復（FR-008），同一份檔、同一次上線；跟 US1 分開是 Luke 2026-11-10 的裁示（spec Clarifications）。
  T010、T011 的 `[X]` 在 `#210` 翻（小 PR 從 `main` 切，沒有本 spec 的檔）。

### Unit 1: 英文論壇的事實與上限值 (verification-only)

- Tasks: T001, T002, T003
- Outcome: research R3–R6 填上實測值（子版 id 與對應、時間格式與時區、每週串數、上限建議值），Luke 核定上限，寫進 spec Clarifications。
- Prerequisites: 論壇不再對本機 429；T003 要 Luke 在場。
- Verification: 讀回 research 與 spec；RSS 與頁面的原始片段留在 scratch，fixture 由 T004 進版控。
- Review: `specs/019-ffxiv-sampling-window/research.md`、`spec.md`。只跑既有入口、只改紀錄，main 驗證即可。
- Merge or split: 三者是同一個前提（英文論壇長什麼樣、要多少名額）；實作要等它們。
- Unchecked assumptions: 「英文的五個子版各有對應…時間格式與時區可以解析」由 T001 檢查；「英文版每週窗口內的串數」由 T002 檢查。

### Unit 2: 英文串頁面的時間換算

- Tasks: T004, T006
- Outcome: 英文頁面的回覆時間正確換成 UTC，窗口判斷不偏；日文版行為不變。
- Prerequisites: Unit 1 的 R4 與 fixture。
- Verification: `pytest tests/unit/test_vb_forum_parse.py`＋時區突變轉紅；全套 unit 綠。
- Review: `tests/unit/test_vb_forum_parse.py`、`tests/fixtures/ffxiv/`（英文片段）、`src/collector.py`、research R4。
- Merge or split: 測試與實作是同一個行為；R4 若判定不用改程式，這個 unit 只剩 T004 加 research 的說明，仍要 review（測試是新的）。

### Unit 3: 分析篇數上限改由設定決定

- Tasks: T005, T007, T008
- Outcome: 上限從設定讀（缺鍵 20、非法值報錯）、截掉論壇時印契約那一行；鏡像與 `docs/external-services.md` 指向同一個鍵。
- Prerequisites: 鍵名（契約）；值等 T003，可先用 20。
- Verification: `pytest tests/unit/test_game_deduplicate.py`＋突變（上限寫死回 20、拿掉 log）轉紅；`test_ffxiv_ranking.py`、`test_pll_priority.py` 照舊綠（SC-004）。
- Review: `tests/unit/test_game_deduplicate.py`、`src/filter.py`、`config/pipeline_config.example.yml`、`docs/external-services.md`、`contracts/config-and-logs.md`。
- Merge or split: 測試、實作與設定鏡像是同一個結果；跟 Unit 2 不同的行為、不同的檔，分開。

### Unit 4: FFXIV 來源設定的鏡像

- Tasks: T009
- Outcome: `config/sources_ffxiv.example.yml` 加英文五版，變成新的來源組合。
- Prerequisites: Unit 0 已 merge 進 `main`、`#210` merge 過 `origin/main`；Unit 1 的 id；Unit 2 決定有沒有時區欄位。
- Verification: YAML 有 12 項（日文 5、英文 5、Lodestone、停用的 TW），`load_ffxiv_sources()` 載入 11 個啟用來源（它只回傳啟用的）；`pytest tests/unit` 綠。設定的真身在 T012 才生效。
- Review: `config/sources_ffxiv.example.yml`。
- Merge or split: 只剩加英文版（刪除的兩項在 Unit 0 先出貨）；review 看完整的來源組合。

### Unit 5: 上線

- Tasks: T012, T013
- Outcome: prod 兩個變數與鏡像逐位元組一致、drift check 通過；FOCUS 在上線那週帶 019 的檢查。
- Prerequisites: PR merge；Unit 1 的上限值。
- Verification: `gh variable get` 讀回比對、`scripts/check_config_drift.py`；FOCUS PR merge 在那週 07:00Z 前。
- Review: 設定讀回結果、`routines/weekly-verify/FOCUS.md`。
- Merge or split: 改的是 prod 設定與程序（不是只跑既有入口），所以是 review unit；兩件一起讓第一份週報可以被驗。

### Unit 6: 上線後讀回與收尾 (verification-only)

- Tasks: T017, T014, T015
- Outcome: `evaluation.md` 有兩次上線各自第一份週報的 SC 讀回（T017 是 SC-002，T014 是其餘）；`3cq` 節記上 019 的結果；closeout reconciliation 與記憶掃描有結果。
- Prerequisites: Unit 0 上線後第一份週報（T017）；US1 上線後第一份週報（T014）；T015 在 `#210` merge 前。
- Verification: 讀回 evaluation.md、BACKLOG 節；reconciliation 的輸出。
- Review: 只改紀錄，main 驗證即可。
- Merge or split: 都是收尾紀錄；T014 在 merge 之後，另開 PR 翻 `[X]`。

## Implementation Strategy

- **先出貨**：Unit 0（US2、US3）從 `main` 另開小 PR，不等 spike（Luke 2026-11-10，analyze H1）；本 spec 因此有兩個 PR。
- **MVP**：Unit 1 → Unit 3 → Unit 2 → Unit 4（US1），在 `#210`；merge 後 Unit 5 上線、Unit 6 讀回。
- 上限值若 Luke 決定維持 20，Unit 3 仍要做（值從程式搬到設定，憲章 IV）。
- 英文論壇的 spike 查不到（持續 429）時，US1 等；Unit 0 已出貨，FOCUS 在那時已寫明 FFXIV 篇數會少。
