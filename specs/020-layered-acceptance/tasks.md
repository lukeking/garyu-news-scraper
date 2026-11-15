# Tasks: 分層驗收——改動照驗收範圍分片，各自發 PR、各自驗收

**Input**: `specs/020-layered-acceptance/` 的 `spec.md`、`plan.md`、`research.md`、`data-model.md`、`contracts/dry-run.md`、`quickstart.md`
**Prerequisites**: plan.md、spec.md（Clarifications 含 2026-11-15 `/speckit-tasks` 這一輪定下的）

**Tests**: 有。research D1、D2 與 `contracts/dry-run.md`「執行紀錄裡的固定行」都指定用測試守；每個實作 task 前面排它的測試，先確認紅。

**Organization**: 照驗收範圍分片（FR-016）。每個 Phase 開頭寫這一片的驗收範圍、用什麼驗、要不要等實跑、對應哪個 PR。

## Format: `[ID] [P?] [Story] [Req] Description`

- **[P]**: 可以並行（不同檔、不相依）
- **[Story]**: 對應 spec.md 的 User Story
- **[Req]**: 這個 task 實作或驗證的 FR／SC，只寫 id

## 片、分支與 PR（已定 2026-11-15）

| 片 | Phase | 驗收範圍 | 用什麼驗 | 要等實跑嗎 | 分支與 PR |
|---|---|---|---|---|---|
| 1 | 1～3 | 功能本身 | 單元測試 | 不用 | `020-layered-acceptance`，`#225`（設計文件與片 1 的實作同一個 PR） |
| 1 的實跑 | 4 | 輸出 | 兩級各在正式執行環境跑一次，SC-001～SC-003 | 不用等排程；要等片 1 進 `main` | 從 `main` 切 `020-dry-run-evidence`，只放紀錄 |
| 2＋3 | 5 | 功能本身（規則文字） | 一輪 cold review；User Story 2 的 Independent Test | 不用 | 從 `main` 切 `020-constitution-slicing`，一個 PR |
| 4 | 6 | 功能本身（紀錄） | SC-004 逐列對照 | 不用 | 從 `main` 切 `020-apply-to-inventory` |
| 讀回 | 7 | 回收檢驗 | 讀片 1 之後第一次排程的週報；讀 `2zc` 的 `tasks.md` | 要 | 從 `main` 切 `020-readback`，只放紀錄 |

片 1 排第一（已定 2026-11-14）；片 2＋3 併成一個 PR（已定 2026-11-15）；片 2＋3 與片 4 的先後是提案（未定），Unit 8 開工前定。

---

## Phase 1: Setup

**Purpose**: 留下片 1 動程式之前的基準

- [ ] T001 跑 `.venv/bin/python -m pytest tests/unit -q`，把摘要行記下來（2026-11-15 在這個分支是 702 passed），之後寫進 `#225` 的內文

---

## Phase 2: Foundational（執行模式）

**Purpose**: 片 1 的每一段都要問「現在是哪一級」，答案只能有一個來源

- [ ] T002 [FR-001, FR-007] 寫 `tests/unit/test_run_mode.py`：`GARYU_RUN_MODE` 沒設或空字串是正式模式；`dry-input` 是第一級、`dry-full` 是第二級（去掉前後空白後要完全相同）；其他任何值（`full`、`input`、`DRY-FULL`、`dry`）丟出錯誤，訊息帶那個值與認得的兩個值；開頭那一行與略過寫入那一行的文字照 `contracts/dry-run.md`「執行紀錄裡的固定行」，正式模式回空、不印。先確認紅
- [ ] T003 [FR-001, FR-007] 實作 `src/run_mode.py`：讀模式、判斷是不是不發布、產生開頭那一行與略過寫入那一行；預設值（正式）只定義在這裡，別的模組不自己讀 `GARYU_RUN_MODE`

**Checkpoint**: 模式有唯一的來源，後面的 task 可以開始

---

## Phase 3: User Story 1 - 片 1：不發布的跑法 (Priority: P1) 🎯 MVP

**驗收範圍**: 功能本身｜**用什麼驗**: 單元測試｜**要等實跑嗎**: 不用｜**PR**: `#225`

**Goal**: 在正式執行環境手動觸發一次不發布的週報，分兩級；正式排程的行為不變

**Independent Test**: `.venv/bin/python -m pytest tests/unit -q` 沒有 failed；`test_storage_dry_run.py` 列到的寫入函式數等於 `src/storage.py` 的寫入函式數；`test_workflow_parity.py` 有跑到（`quickstart.md`「片 1」）

### 寫入出口

- [ ] T004 [US1] [FR-004, FR-007, FR-010] 寫 `tests/unit/test_storage_dry_run.py`：從 `src/storage.py` 的原始碼找出所有呼叫 client 寫入方法的函式（不手寫清單），斷言恰好是 research.md 列的 5 個；兩個不發布模式下逐一斷言 client 呼叫 0 次、計數的回 0、印一行 `[不發布] 略過 <函式名>：<N> 筆`；正式模式下 client 照常被呼叫。另加一條咬合：把一個「有寫入、沒檢查模式」的假函式餵給列舉的邏輯，斷言它被抓到。先確認紅
- [ ] T005 [US1] [FR-004, FR-007, FR-010] 在 `src/storage.py` 的 `upsert_articles`、`upsert_traffic_buffer`、`expire_buffer_articles`、`mark_articles_analyzed`、`upsert_hot_topic_report` 開頭檢查模式：不發布時不取 client、印略過那一行、回傳原本型別的空結果；讀取函式不動

### `main.py` 的兩級與呼叫計數

- [ ] T006 [US1] [FR-009, SC-002] 寫 `tests/unit/test_call_counts.py`：替換 HTTP 邊界（不替換 `_call_gemini` 本身），`src/analyzer.py` 的 `_call_gemini` 每送出一次請求生成式計數加一（重試也算），`generate_embedding` 每送出一次請求 embedding 計數加一；結尾那一行 `[不發布] 生成式 LLM 呼叫 <N> 次，embedding 呼叫 <M> 次` 只在不發布模式印。先確認紅
- [ ] T007 [US1] [FR-009, SC-002] 在 `src/analyzer.py` 實作兩個計數與讀數函式；正式模式的輸出不變
- [ ] T008 [US1] [FR-002, FR-003, FR-004, FR-007, FR-008, FR-010] 寫 `tests/unit/test_main_dry_run.py`，替換收集、HTTP 與資料庫 client 的邊界後跑 `src/main.py` 的 `main()`：
  - 兩級：輸出的第一行是級別那一行；交通跑完 collect → filter（embedding 去重照常）→ analyze（充實），`publish` 不寫 buffer、印略過行，`TRAFFIC_POOL_DIR` 底下的檔有每個來源的收集數、過濾後數、過濾後的清單與級別欄位
  - `dry-input`：FFXIV 跑完 collect → filter 後印 `[不發布] 第一級在 FFXIV 分析 之前停下`，`analyze_all` 呼叫 0 次，結尾的生成式次數是 0
  - `dry-full`：`analyze_all` 被呼叫；`pages/ffxiv/` 底下沒有新增或改動的檔；`ANALYSIS_OUTPUT_DIR` 有 FFXIV 逐篇分析的全文與級別欄位
  - 正式模式：寫入與站台檔跟現在相同，輸出沒有任何 `[不發布]` 開頭的行；`GARYU_RUN_MODE` 是不認得的值時 `main()` 在收集之前就失敗
  - 先確認紅
- [ ] T009 [US1] [FR-002, FR-003, FR-004, FR-007, FR-008, FR-010] 實作 T008 的行為：`src/main.py`（開頭那一行、第一級不呼叫 `analyze`／`publish` 的 FFXIV 分支、結尾的次數）、`src/pipeline/traffic.py`（不發布時把 `last_funnel` 與過濾充實後的清單寫進 `TRAFFIC_POOL_DIR`）、`src/pipeline/ffxiv.py`、`src/publisher.py`（不發布時不產生站台檔，把逐篇分析寫進 `ANALYSIS_OUTPUT_DIR`）。`ffxiv-pool` 的檔在正式模式格式不變；不發布時在頂層加級別欄位，頂層不是物件就先回報、不自行改格式

### 交通分析腳本的兩級

- [ ] T010 [P] [US1] [FR-002, FR-003, FR-004, FR-007, FR-008, FR-009, FR-010] 寫 `tests/unit/test_weekly_analysis_dry_run.py`，替換資料庫讀取與 HTTP 邊界後跑 `scripts/traffic_weekly_analysis.py` 的 `main()`：
  - 兩級：`expire_buffer_articles` 印略過行；分析的輸入是 buffer 疊上 `TRAFFIC_POOL_DIR` 那份清單，同一個 link 只算一次，印 `[不發布] 分析的輸入：buffer <N> 篇，加上這次收集的 <M> 篇（其中 <K> 篇 buffer 裡已經有）`；清單檔不存在時印一行說沒有疊，不靜靜照 buffer 跑
  - `dry-input`：選完熱點 bucket 與彙整池之後印 `[不發布] 第一級在 熱點分析 之前停下`，`analyze_hot_topic`、`analyze_category_digest` 呼叫 0 次；選出的 bucket、彙整池的篇數與來源分布、級別欄位寫進 `TRAFFIC_POOL_DIR`
  - `dry-full`：每份三軸報告與彙整報告的全文寫進 `ANALYSIS_OUTPUT_DIR`；每份報告跑一次 `src/report_review.py` 的 `check_report()`，命中一起寫進去並標「未經逐條判定」，命中不擋任何東西；`upsert_hot_topic_report`、`mark_articles_analyzed` 各印略過行；`pages/traffic/hot_topics.json` 沒有被產生或改動；結尾印次數
  - 正式模式：寫入與發布的呼叫跟現在相同，不呼叫 `check_report()`，沒有 `[不發布]` 開頭的行
  - 先確認紅
- [ ] T011 [US1] [FR-002, FR-003, FR-004, FR-007, FR-008, FR-009, FR-010] 在 `scripts/traffic_weekly_analysis.py` 實作 T010 的行為；`check_report()` 的輸入怎麼組照 `scripts/replay_report_review.py:115` 的呼叫

### 術語收錄的不寫入模式

- [ ] T012 [P] [US1] [FR-003, FR-004, FR-007, FR-009, FR-010] 寫 `tests/unit/test_auto_kb_dry_run.py`，替換資料庫 client 與 HTTP 邊界後跑 `scripts/auto_kb.py` 的 `main()`：
  - `dry-full`：未知術語取自 `ANALYSIS_OUTPUT_DIR` 裡這次 FFXIV 分析輸出的標記，不取資料庫裡待處理的 `articles`；術語庫照常讀，讀不到就停；`call_gemini` 被呼叫；`knowledge_base` 的 insert 與 `articles` 的 update 都是 0 次；印 `[不發布] 術語收錄：會寫入 <N> 條，沒有寫入` 與逐條內容，結果寫進 `ANALYSIS_OUTPUT_DIR`；結尾印生成式次數
  - `dry-input`：印 `[不發布] 第一級在 術語收錄 之前停下`，`call_gemini` 0 次，正常結束
  - 正式模式：`tests/unit/test_auto_kb_patching.py` 照樣全過
  - 先確認紅
- [ ] T013 [US1] [FR-003, FR-004, FR-007, FR-009, FR-010] 在 `scripts/auto_kb.py` 實作 T012 的行為；`:264`、`:321` 兩處寫入在原處檢查模式，不搬進 `src/storage.py`

### 入口、五個計數與操作說明

- [ ] T014 [P] [US1] [SC-001] 寫 `tests/unit/test_dry_run_counts.py`：比對兩份計數，全部相同回 0；任何一項不同或任何一項是「未取得」回非 0，並指出是哪一項。先確認紅
- [ ] T015 [US1] [SC-001] 實作 `scripts/dry_run_counts.py`：只發 GET，印出並寫成檔：`hot_topic_reports` 與 `articles` 的列數（spec 的「報告數」沒寫是哪一張表，兩張都數）、buffer 筆數、彙整池未分析筆數、術語庫條目數、兩個站的最後部署時間；另一個模式比對兩份檔。列數用 count 取，不抓列（PostgREST 單次 1000 列的上限見 BACKLOG `GNS-20261103-f71`）。部署時間的讀法在這個 task 查證（Cloudflare 的 API 或 wrangler），取不到的項目印「未取得：原因」，不補值。`--help` 寫完整的呼叫方式
- [ ] T016 [P] [US1] [FR-001, FR-004, FR-005, FR-006, FR-010] 寫 `tests/unit/test_workflow_parity.py`，讀 `.github/workflows/weekly.yml`、`weekly-dry-run.yml`、`auto-kb.yml`（PyYAML 把 `on` 這個鍵讀成布林 `True`）：
  - 共用的準備步驟（checkout、五個寫設定檔的步驟、設定 Python、安裝相依）在兩個檔逐步相同
  - 不發布的檔只有 `workflow_dispatch`，沒有 `schedule`、沒有 `workflow_run`；它的 `name` 不在 `auto-kb.yml` 的 `workflow_run.workflows` 裡
  - 沒有部署步驟（沒有 wrangler、沒有 `CLOUDFLARE_API_TOKEN` 用在部署），沒有「驗證本週資料可由 Supabase 讀取」那一步
  - `level` 是必填的選項，值恰好是 `dry-input`、`dry-full`，原樣傳進每個程式步驟的 `GARYU_RUN_MODE`
  - `weekly.yml` 的「執行週報程式」「週交通熱點分析」兩步的每個 env 鍵，不發布的檔對應的步驟都有、值相同，多出來的只能是 `GARYU_RUN_MODE` 與產物路徑；術語收錄那一步對 `auto-kb.yml` 的執行步驟同樣比。這一段比 research D2 多守：`#218` 加在 `weekly.yml` 的模型變數沒跟著加，不發布的執行會讀到預設值而且不出聲
  - `timeout-minutes`、`environment`、`permissions` 跟 `weekly.yml` 相同
  - 對照：未修改的檔全過；把其中一個準備步驟改掉一個字的副本要紅
  - 先確認紅
- [ ] T017 [US1] [FR-001, FR-004, FR-005, FR-006, FR-008, FR-010] 新增 `.github/workflows/weekly-dry-run.yml`（`weekly.yml` 不動）：準備步驟；`scripts/dry_run_counts.py` 取一次；`python main.py`；`python scripts/traffic_weekly_analysis.py`；`level` 是 `dry-full` 時跑 `python scripts/auto_kb.py`；`scripts/dry_run_counts.py` 再取一次並比對，不同就讓 job 失敗；上傳 `ffxiv-pool`、`traffic-pool`、`analysis-output` 三個產物（含兩份計數），前面的步驟失敗也上傳
- [ ] T018 [P] [US1] [FR-007, FR-008, FR-009] 寫 `docs/dry-run.md`（怎麼觸發、兩級各做什麼與不做什麼、產物叫什麼與怎麼讀回、它驗的是接線與輸出而不是預演週一、產物在公開 repo 上外人讀得到）；`docs/external-services.md` 的 Gemini 那一列補一句：不發布的第二級算在同一個預算裡
- [ ] T019 [US1] [FR-020, SC-006] 在當時適用週的 `routines/weekly-verify/FOCUS.md` 加一條讀回的提醒：片 1 進 `main` 之後第一次排程的週報，紀錄裡不該有任何 `[不發布]` 開頭的行，寫入與發布照常；FOCUS 滾動時帶著，到 T037 做完才收
- [ ] T020 [US1] [SC-005, FR-017, FR-018] 改寫 `#225` 的標題與內文：這一片的驗收範圍、驗法、結果（T001 的基準與最後的摘要行）、後面還有哪幾片、`GNS-20261114-bh8` 那一列還沒移出的原因、憲章原則 I～III 的符合情形、照 contract 提案實作的固定行文字；`Backlog:` 那一行貼 `python3 ~/.agents/bin/backlog_trailers.py pr-line` 的輸出

**Checkpoint**: 片 1 可以轉 ready、merge；不發布的 workflow 進了 `main` 才觸發得了

---

## Phase 4: User Story 1 - 片 1 的實跑

**驗收範圍**: 輸出｜**用什麼驗**: 兩級各在正式執行環境跑一次｜**要等實跑嗎**: 不用等排程，要等片 1 進 `main`｜**PR**: `020-dry-run-evidence`（只放紀錄）

**Goal**: SC-001～SC-003 有實測的紀錄；`#218` 的接線不經過任何一次排程週報就驗完

**Independent Test**: `quickstart.md`「片 1 的實跑」「`#218` 的接線」

- [ ] T021 [US1] [SC-001, SC-002] `gh workflow run weekly-dry-run.yml --ref main -f level=dry-input`；讀執行紀錄與三個產物，把 run id、兩份計數與比對結果、生成式次數（要是 0）、embedding 次數、每個類別的收集數與過濾後數與入選清單記進 `specs/020-layered-acceptance/evaluation.md`
- [ ] T022 [US1] [SC-001, SC-002, FR-009] 同一個指令改 `-f level=dry-full`；另外記每份報告的全文讀不讀得回來、`check_report()` 的命中、術語收錄會寫入的條目、生成式與 embedding 的次數，並對照 `docs/external-services.md` 的 Gemini 預算，寫進 `evaluation.md`（這一筆檢查 spec 的假設「第二級與正式執行共用額度不會讓正式週報額度不足」）
- [ ] T023 [US4] [FR-022, SC-003] `#218` 的分支（`feat/per-function-gemini-models`）merge `main`、解 `specs/BACKLOG.md` 的衝突，把它加在 `weekly.yml` 的變數同樣加進 `weekly-dry-run.yml`（T016 的比對會指出缺哪些）；對那個分支觸發 `dry-full`，把三軸、彙整、FFXIV 逐篇、術語收錄四條呼叫路徑各自讀到的模型設定與 run id 留言在 `#218`。分支上的改動由 `#218` 自己的 review 收
- [ ] T024 [US1] [SC-005, FR-017] 開紀錄的 PR：`evaluation.md`、T021～T023 的標記；內文寫驗收範圍（輸出）、驗法、結果與剩下的片

**Checkpoint**: 片 1 的 Gate（SC-001）有實測；`#218` 可以照它自己的條件 merge

---

## Phase 5: User Story 2＋3 - 片 2＋3：專案規則與流程接點 (Priority: P2、P3)

**驗收範圍**: 功能本身（規則文字）｜**用什麼驗**: 一輪 cold review；User Story 2 的 Independent Test｜**要等實跑嗎**: 不用｜**PR**: `020-constitution-slicing`

**Goal**: 分片原則、九類驗收範圍與流程接點寫進憲章，之後的 spec 與小 PR 讀得到

**Independent Test**: 拿 BACKLOG 盤點表的一列，只讀憲章寫出它的分片與每片的驗法，跟盤點表那一列一致

規則落在憲章的哪幾節是 research D6 的提案（未定），這個 Phase 開工前定。

- [ ] T025 [US2] [FR-011, FR-012, FR-013, FR-014, FR-015] 在 `.specify/memory/constitution.md` 加「分層驗收」一節：分片原則；九類驗收範圍與各自夠用的驗法；觀測跟驗收分開寫；遇到新的範圍怎麼加；驗收條件先寫最早就夠用的驗法，等排程只用在其他驗法都驗不到的部分並寫明原因；蓋過 user 層「一個 spec 一個 PR」的範圍只限這個專案。只寫原則與結構性的選擇，操作細節指到 `docs/dry-run.md`
- [ ] T026 [US3] [FR-016, FR-017, FR-018, FR-019, FR-020] 同一個檔寫流程接點：tasks 照驗收範圍分組並標驗法與 PR；小 PR 的內文交代驗收範圍、驗法、結果與剩下的片；BACKLOG 列的移出時點與讀回另開一列；上線與驗收完成是兩個時點；讀回的提醒與日期宣告做好之前的過渡做法。Operations & Deployment 補上不發布的入口（驗的是接線與輸出，不是預演週一）；Governance 的 Compliance review 補上 PR 內文的要求
- [ ] T027 [US2] [FR-015] 同一個檔照修訂程序升版 2.1.1 → 2.2.0：Sync Impact Report、`Last Amended`；確認 `.specify/templates/` 仍然沒有副本
- [ ] T028 [US3] [FR-018] 維護者機器上的 `CLAUDE.local.md`「Spec closeout 綁定」一段跟著改（closeout 不再一律在完成它的那個 PR 做）；這個檔不進版控，改完讀回，在 PR 內文記一行
- [ ] T029 [US2] [FR-015] 對這個 PR 跑一輪 cold review；成立的 finding 修在同一個 PR，分級表留言後貼 `cold-reviewed`
- [ ] T030 [US2] [SC-005] 做 User Story 2 的 Independent Test（建議拿 `GNS-007` 那一列），對照結果寫進 PR 內文，連同這一片的驗收範圍、驗法與剩下的片

**Checkpoint**: `GNS-20261108-2zc` 拆 task 時讀得到規則

---

## Phase 6: User Story 4 - 片 4：套用到手上的項目 (Priority: P4)

**驗收範圍**: 功能本身（紀錄）｜**用什麼驗**: SC-004 逐列對照｜**要等實跑嗎**: 不用｜**PR**: `020-apply-to-inventory`

**Goal**: 盤點表的 10 列照新原則改寫；`GNS-20261114-bh8` 移出，讀回另開一列

**Independent Test**: 標「不用」的 4 列與「不用整個等」的 1 列不再寫等週報；其餘 5 列寫明為什麼只有實跑驗得到

- [ ] T031 [US4] [FR-021] 改寫 `specs/BACKLOG.md` 裡盤點表指到的各列與小節的驗收條件：`GNS-007`、`GNS-20261110-sjc`、`GNS-20261019-3cq`、`GNS-20261013-4g9`、`GNS-20261019-1vk`、`GNS-20261026-fwz`、`GNS-20261019-dkm`（後兩個歸成觀測）。先對當時的現況：已經做完或移出的寫明在哪裡完成，不改寫
- [ ] T032 [US4] [FR-021] 改寫 `specs/019-ffxiv-sampling-window/` 的 SC 與 T017、T014，以及 `specs/018-prepublish-review/tasks.md` 的 T053 裡等排程的寫法；同樣先對現況，已經讀回的只補指標
- [ ] T033 [US4] [SC-004] 逐列對照盤點表與改寫後的文字，對照表寫進 PR 內文：標「不用」與「不用整個等」的 5 列裡沒有「連兩週」「第一份週報」「週報後」；其餘 5 列各寫明只有實跑驗得到的是什麼
- [ ] T034 [US3] [FR-018, FR-019, SC-008] 用 `python3 ~/.agents/bin/backlog.py remove specs/BACKLOG.md GNS-20261114-bh8` 移出那一列與小節；同一個 PR 用 `backlog.py add` 開讀回那一列（SC-006、SC-007、SC-008）
- [ ] T035 [US3] [FR-020] 讀回那一列的提醒：先查 bare 的 `GUB-20261114-gw7` 做好了沒（這一筆檢查 spec 的假設「日期宣告會在讀回那一片需要之前做好」）；做好了就在那一列寫日期宣告，沒做好就確認 T019 那一條還在 `routines/weekly-verify/FOCUS.md`
- [ ] T036 [US3] [SC-005] 對照這個 spec 到這裡出的每個 PR：內文都有驗收範圍、驗法與結果；結果寫進這個 PR 的內文

**Checkpoint**: 上線前驗得完的片都出了；剩讀回

---

## Phase 7: 讀回（回收檢驗）

**驗收範圍**: 回收檢驗｜**用什麼驗**: 讀那一次實跑的紀錄；讀 `2zc` 的 `tasks.md`｜**要等實跑嗎**: 要｜**PR**: `020-readback`（只放紀錄）

- [ ] T037 [SC-006] 片 1 進 `main` 之後第一次排程的週報：先確認那一次 run 存在；紀錄裡沒有任何 `[不發布]` 開頭的行；報告、buffer、彙整池標記、兩個站的部署、`auto-kb.yml` 的連帶觸發都照常發生。記進 `specs/020-layered-acceptance/evaluation.md`，收掉 T019 的 FOCUS 那一條
- [ ] T038 [SC-007] `GNS-20261108-2zc` 的 `tasks.md` 產生之後：每一組都標了驗收範圍與驗法。記進 `evaluation.md`
- [ ] T039 [SC-008] 記下讀回那一列的提醒響過一次的紀錄；開讀回的 PR，移出那一列

---

## Dependencies & Execution Order

- Phase 2（T002、T003）擋住 Phase 3 的全部。
- Phase 3 裡：T004～T005 → T006～T009 → T010～T011 與 T012～T013（兩組可以並行，都讀 T009 寫出的檔）。T014～T015、T016、T018 不依賴前面幾組的程式；T017 要等 T009、T011、T013、T015 的名字與路徑定下來；T019、T020 最後。
- Phase 4 要等 `#225` merge：新的 workflow 檔進預設分支之前觸發不了（GitHub 的行為，沒有在這個 repo 實測；T021 就是第一次實測）。
- Phase 5、6 不依賴 Phase 4；Phase 6 的 T034 是 `GNS-20261114-bh8` 移出的地方，所以 Phase 6 排在上線前驗得完的片的最後。
- Phase 7 的 T037 等片 1 之後的第一個週一；T038 等 `2zc` 拆 task。

### Parallel Opportunities

T010 與 T012（不同腳本）；T014、T016、T018（各自的檔，不依賴 T004～T013）。

---

## Review units

### Unit 1: 模式與寫入出口

- Tasks: T002、T003、T004、T005
- Outcome: 執行模式有唯一的來源；不發布時 `src/storage.py` 的每個寫入函式都不碰資料庫並留下一行；正式模式不變。完成＝`test_run_mode.py`、`test_storage_dry_run.py` 全過，列舉到的寫入函式是 5 個
- Prerequisites: 現有的 `src/storage.py`；這個 unit 自己包含 `src/run_mode.py`
- Verification: `.venv/bin/python -m pytest tests/unit/test_run_mode.py tests/unit/test_storage_dry_run.py -q`；全套 `tests/unit` 的摘要行。限制：只證明函式層不寫，實際 0 筆要等 Unit 7 的五個計數
- Review: `src/run_mode.py`、`src/storage.py`、`tests/unit/test_run_mode.py`、`tests/unit/test_storage_dry_run.py`、`contracts/dry-run.md`「執行模式」「執行紀錄裡的固定行」
- Merge or split: 模式是為了擋寫入才存在，單獨交付沒有可驗的行為，所以併在一起；`main.py` 的流程是另一個結果，有自己的測試
- Unchecked assumptions:
  - 「第二級與正式執行共用額度，不會讓正式週報額度不足」：這個 unit 驗不到，要一次真的第二級才有用量；第一個驗它的是 Unit 7 的 T022
  - 「日期宣告（bare `GUB-20261114-gw7`）會在讀回那一片需要之前做好」：是之後的狀態，現在只查得到還沒開工；第一個驗它的是 Unit 9 的 T035，在那之前 T019 走過渡做法
  - 「其餘三片的先後照提案」：不是程式驗得到的事，是一個還沒定的先後；Unit 8 開工前定

### Unit 2: `main.py` 的兩級與呼叫計數

- Tasks: T006、T007、T008、T009
- Outcome: `main.py` 在兩級各自停在該停的地方、留下產物、不產生站台檔，結尾印生成式與 embedding 的次數；正式模式的寫入與輸出不變
- Prerequisites: Unit 1
- Verification: `pytest tests/unit/test_call_counts.py tests/unit/test_main_dry_run.py -q` 與全套摘要行。限制：收集與 HTTP 是替換的，抓不抓得到要等 Unit 7
- Review: `src/main.py`、`src/analyzer.py`（計數）、`src/pipeline/traffic.py`、`src/pipeline/ffxiv.py`、`src/publisher.py`、兩個測試檔、`contracts/dry-run.md`「產物」
- Merge or split: 次數那一行是 `main.py` 結尾的一部分，計數沒有別的讀者，所以併；交通分析與術語收錄是另外兩支程式，各自一個結果
- Unchecked assumptions: none

### Unit 3: 交通分析腳本的兩級

- Tasks: T010、T011
- Outcome: 分析的輸入疊上這次收集的清單；第一級停在選完熱點與彙整池；第二級留下報告全文與 `check_report()` 的命中，不寫報告、不標已分析、不產生 `hot_topics.json`
- Prerequisites: Unit 1、Unit 2（清單檔的格式）
- Verification: `pytest tests/unit/test_weekly_analysis_dry_run.py -q` 與全套摘要行
- Review: `scripts/traffic_weekly_analysis.py`、測試檔、`src/report_review.py` 的呼叫方式、`contracts/dry-run.md`
- Merge or split: 跟 Unit 4 是不同的程式、不同的寫入點，各自能下完成的判定
- Unchecked assumptions: none

### Unit 4: 術語收錄的不寫入模式

- Tasks: T012、T013
- Outcome: 第二級用這次的 FFXIV 輸出當輸入、呼叫 LLM、印出會寫入的條目，不寫 `knowledge_base`、不改 `articles`；正式模式不變
- Prerequisites: Unit 1、Unit 2（`ANALYSIS_OUTPUT_DIR` 的格式）
- Verification: `pytest tests/unit/test_auto_kb_dry_run.py tests/unit/test_auto_kb_patching.py -q` 與全套摘要行
- Review: `scripts/auto_kb.py`、兩個測試檔
- Merge or split: 見 Unit 3
- Unchecked assumptions: none

### Unit 5: 入口、五個計數與操作說明

- Tasks: T014、T015、T016、T017、T018、T019
- Outcome: 一個只能手動觸發的 workflow，跟 `weekly.yml` 的準備步驟與程式步驟的 env 用測試守住；每次執行自己取前後的五個計數並比對；操作說明與讀回的過渡提醒
- Prerequisites: Unit 2～4 定下的名字與路徑
- Verification: `pytest tests/unit/test_workflow_parity.py tests/unit/test_dry_run_counts.py -q` 與全套摘要行；`docs/dry-run.md` 對 `contracts/dry-run.md` 逐項讀。限制：workflow 本身跑不跑得起來，merge 之前驗不到，要等 Unit 7
- Review: `.github/workflows/weekly-dry-run.yml`、`scripts/dry_run_counts.py`、兩個測試檔、`docs/dry-run.md`、`docs/external-services.md`、`routines/weekly-verify/FOCUS.md`
- Merge or split: workflow、它的計數步驟與說明是同一個入口的幾個必要部分；程式的行為已經在 Unit 1～4 各自下過判定
- Unchecked assumptions: none

### Unit 6: 片 1 的基準與 PR 紀錄 (verification-only)

- Tasks: T001、T020
- Outcome: `#225` 的內文有片 1 的驗收範圍、驗法與結果
- Prerequisites: Unit 1～5
- Verification: `gh pr view 225 --json title,body` 讀回
- Review: 不派 reviewer；main 讀回
- Merge or split: 只跑既有的入口、只寫紀錄
- Unchecked assumptions: none

### Unit 7: 片 1 的實跑 (verification-only)

- Tasks: T021、T022、T023、T024
- Outcome: SC-001～SC-003 的實測紀錄；`#218` 的接線紀錄
- Prerequisites: `#225` 已經 merge
- Verification: `evaluation.md` 裡的 run id 可以重新讀；兩份計數的比對在執行紀錄裡
- Review: 不派 reviewer；T023 在 `#218` 分支上的改動由 `#218` 的 review 收
- Merge or split: 兩級與 `#218` 用的是同一個入口、同一份紀錄
- Unchecked assumptions: 「第二級與正式執行共用額度」由 T022 的次數對照預算來驗

### Unit 8: 憲章修訂（片 2＋3）

- Tasks: T025、T026、T027、T028、T029、T030
- Outcome: 憲章 2.2.0 有「分層驗收」一節與流程接點；只讀憲章就能替盤點表的一列分片
- Prerequisites: `docs/dry-run.md` 已經在 `main`（憲章要指過去）；D6 的落點與片的先後定案
- Verification: cold review 的分級表；T030 的對照。限制：規則文字沒有測試，執行者是之後每個 spec 的 Constitution Check
- Review: `.specify/memory/constitution.md`，對照 spec 的 FR-011～FR-020
- Merge or split: 片 2 與片 3 都改同一個檔、驗法相同，一次修訂一輪 cold review（已定 2026-11-15）
- Unchecked assumptions: 「其餘三片的先後照提案」在這個 unit 開工前定

### Unit 9: 片 4：盤點表改寫與 BACKLOG 收尾

- Tasks: T031、T032、T033、T034、T035、T036
- Outcome: 盤點表 10 列照新原則改寫；`GNS-20261114-bh8` 移出、讀回另開一列並有提醒
- Prerequisites: Unit 8（改寫照憲章的分類）；Unit 7（`#218` 那兩列的現況）
- Verification: T033 的對照表；`python3 ~/.agents/bin/backlog_trailers.py pr-line` 的輸出列出移出的 id
- Review: `specs/BACKLOG.md`、`specs/019-ffxiv-sampling-window/`、`specs/018-prepublish-review/tasks.md`、`routines/weekly-verify/FOCUS.md`
- Merge or split: 改寫與那一列的移出在同一個 PR（FR-018）；讀回是上線後的事，另一個 unit
- Unchecked assumptions: 「日期宣告會做好」由 T035 查

### Unit 10: 讀回 (verification-only)

- Tasks: T037、T038、T039
- Outcome: SC-006～SC-008 的紀錄；讀回那一列移出
- Prerequisites: 片 1 之後的第一次排程週報；`2zc` 的 `tasks.md`
- Verification: `evaluation.md` 的 run id 與檔案指標
- Review: 不派 reviewer；main 讀回
- Merge or split: 三條都是讀別處已經發生的事、只寫紀錄
- Unchecked assumptions: none

---

## Parallel Example: User Story 1

```bash
# Unit 2 交回之後，兩支腳本的測試可以同時寫：
Task: "T010 寫 tests/unit/test_weekly_analysis_dry_run.py"
Task: "T012 寫 tests/unit/test_auto_kb_dry_run.py"
```

---

## Implementation Strategy

1. 片 1（Phase 1～3）在 `#225` 上做完、review 過、merge。這是 MVP：之後每個改動都可以不等週一就驗輸入與輸出。
2. 片 1 一進 `main` 就跑 Phase 4；`#218` 的接線在這裡驗完。
3. 片 2＋3、片 4 各自一個 PR，先後照定下來的順序。
4. 讀回等它要等的那一次實跑；前面幾片的 merge 與完成不等它。

## 還沒定的

- 片 2＋3 與片 4 的先後（提案：2＋3 → 4）；research D6 規則落在憲章哪幾節（提案）。Unit 8 開工前定。
- 固定行的文字、產物目錄裡的檔名、`TRAFFIC_POOL_DIR` 與 `ANALYSIS_OUTPUT_DIR` 這兩個名字（提案）：片 1 的測試鎖住的就是定案的版本，列在 `#225` 的內文。
- 生成式次數算的是送出的請求、重試也算（提案）：理由是這個數字是給額度看的。
