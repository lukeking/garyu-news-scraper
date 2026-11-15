# Implementation Plan: 分層驗收——改動照驗收範圍分片，各自發 PR、各自驗收

**Branch**: `020-layered-acceptance` | **Date**: 2026-11-15 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/020-layered-acceptance/spec.md`

## Summary

兩件事。第一件是一個新的手動入口：在正式執行環境跑一次不發布的週報，分兩級（只到入選；跑完分析與術語收錄但不寫入）。做法是程式裡一個執行模式，
寫入函式自己檢查；入口是另一個 workflow 檔，`weekly.yml` 不動（research D1、D2）。第二件是把分片原則寫進憲章，定下流程接點，再套用到盤點表的項目。
這個 spec 自己照同一個原則分片出貨。

## 片與 PR（這個 spec 怎麼出貨）

| 片 | 內容 | 驗收範圍 | 用什麼驗 | 要等實跑嗎 |
|---|---|---|---|---|
| 1 | 執行模式、寫入函式的檢查、兩級的停點與產物、不發布的 workflow 檔、`docs/` 的操作說明 | 功能本身 | 單元測試（含「每個寫入函式都檢查了」與兩個 workflow 的比對） | 不用 |
| 1 的實跑 | 兩級各在正式執行環境跑一次；順便驗 `#218` 的接線 | 輸出 | SC-001～SC-003：觸發前後的五個計數、產物讀回 | 不用等排程；要等片 1 進預設分支（workflow 檔在預設分支才觸發得了） |
| 2＋3 | 憲章加「分層驗收」一節與流程接點；本機在地設定跟著改 | 功能本身（規則文字） | 一輪 cold review；User Story 2、3 的 Independent Test | 不用 |
| 4 | 盤點表 10 個項目的驗收條件改寫；移出 `GNS-20261114-bh8`、另開讀回那一列 | 功能本身（紀錄） | SC-004 逐列對照 | 不用 |
| 讀回 | SC-006（片 1 之後第一次排程週報照常寫入與發布）、SC-007（`2zc` 的 tasks）、SC-008 | 回收檢驗 | 讀那一次週報的紀錄；讀 `2zc` 的 `tasks.md` | 要 |

片 2 與片 3 併成一個 PR 是提案（未定）：兩片的驗收範圍與驗法相同，而且都改憲章，併起來只要一次修訂、一輪 cold review。
片的先後：1 →（1 的實跑與 `#218`）→ 2＋3 → 4 → 讀回；1 排第一已定（2026-11-14），其餘是提案（未定）。

## Technical Context

**Language/Version**: Python 3.11（正式執行環境）；本機 `.venv` 是 3.12  
**Primary Dependencies**: 既有的（`requests`、Supabase client、PyYAML）；不加新的相依  
**Storage**: Supabase；不發布的執行只讀  
**Testing**: `python -m pytest tests/unit`（2026-11-14 `main` 是 702 passed）  
**Target Platform**: GitHub Actions `ubuntu-latest`，`production` environment  
**Project Type**: 排程的資料管線加 CLI 腳本  
**Performance Goals**: 第二級在一份週報的時間內跑完（11-09 的排程執行是 10.5 分鐘）；job 的 `timeout-minutes` 跟 `weekly.yml` 相同  
**Constraints**: 正式寫入 0 筆；`weekly.yml` 不改；產物在公開 repo 上外人讀得到（已定可以）  
**Scale/Scope**: 5 個寫入函式加 `auto_kb.py` 的 2 處；1 個新的 workflow 檔；1 個新模組；1 次憲章修訂

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

依 `.specify/memory/constitution.md` 2.1.1（2026-11-15 讀）：

| 原則 | 判定 | 依據 |
|---|---|---|
| I. Pipeline Integrity | 過 | 階段順序不變；不發布的執行是在 Analyze 之後停下，不是跳過上游。交通分析的輸入是 buffer 加上這次收集、還沒存的那一批（research D4），內容等於正式執行時 buffer 會有的東西。執行環境仍是 Actions。 |
| II. Configuration over Code | 過 | 來源、模型、金鑰照舊從變數與 secret 來；不發布的 workflow 讀同一組。執行模式是執行時的開關，不是來源或模型設定。 |
| III. Idempotency & Deduplication | 過 | 不發布的執行不寫入，存下來的狀態不變；正式模式下寫入函式的行為不變。 |
| IV. Explicit Budgets | 過 | 新的 job 設 `timeout-minutes`；每次執行的 LLM 上限沿用既有的設定；第二級算在 Gemini 同一個預算裡，`docs/external-services.md` 補一句（片 1）。 |
| V. Single Responsibility per Module | 過，有一項要記 | 擋寫入放在 `src/storage.py`（它擁有持久化）。新增 `src/run_mode.py` 是跨模組的相依，記在 Complexity Tracking。`scripts/auto_kb.py` 直接寫資料庫是既有的寫法，這次只在原處加檢查，不搬。 |
| VI. Knowledge Base Integrity | 過 | 不發布的術語收錄不寫 `knowledge_base`；KB 讀不到就停的規定在不發布模式照樣適用。 |
| Operations & Deployment | 過 | 「完整管線的標準測試是手動觸發 `weekly.yml`」不變；片 2＋3 的修訂補上不發布的入口。 |
| Governance | 過 | 片 1 動到 `src/storage.py`、`src/publisher.py`，PR 內文要寫原則 I–III 的符合情形；片 2＋3 照修訂程序升版（新增一節，MINOR：2.1.1 → 2.2.0）並附 Sync Impact Report。 |

設計完成後重看（2026-11-15）：沒有新增的違反項目。

## Project Structure

### Documentation (this feature)

```text
specs/020-layered-acceptance/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── dry-run.md        # 不發布的入口：輸入、產物、執行紀錄裡的固定行
└── tasks.md              # /speckit-tasks 產生
```

### Source Code (repository root)

```text
src/
├── run_mode.py                    # 新增：讀執行模式（正式／第一級／第二級）
├── storage.py                     # 5 個寫入函式檢查模式
├── publisher.py                   # 不發布時不產生站台檔
└── pipeline/
    ├── traffic.py                 # 不發布時把這次收集過濾後的清單寫成檔
    └── ffxiv.py                   # 第一級停在分析之前
scripts/
├── traffic_weekly_analysis.py     # 不發布時疊上這次收集的清單；第一級停在選完熱點與彙整池
└── auto_kb.py                     # 不寫入的模式；輸入可以來自這次的 FFXIV 輸出
.github/workflows/
└── weekly-dry-run.yml             # 新增：只能手動觸發；weekly.yml 不動
tests/unit/
├── test_run_mode.py               # 模式的解析與預設值
├── test_storage_dry_run.py        # 列出所有寫入函式，逐一斷言不發布時 client 呼叫 0 次
└── test_workflow_parity.py        # weekly.yml 與 weekly-dry-run.yml 共用的準備步驟逐步相同
docs/
├── dry-run.md                     # 怎麼觸發、產物叫什麼、怎麼讀回
└── external-services.md           # Gemini 那一列補一句
.specify/memory/constitution.md    # 片 2＋3
routines/weekly-verify/FOCUS.md    # 讀回的過渡提醒
specs/BACKLOG.md                   # 片 4：移出 bh8、開讀回那一列、盤點表各項的指標
```

**Structure Decision**: 沿用現有的單一專案結構。執行模式是唯一的新模組；入口是新的 workflow 檔。兩個 workflow 檔的重複用測試守，不抽共用的 workflow（research D2）。

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| 新的跨模組相依：`src/run_mode.py` 被 `storage.py`、`publisher.py`、兩個 pipeline 模組與兩支腳本讀 | 六個地方要對「現在是哪一級」有同一個答案，而且預設值（正式）只能定義一次 | 每個地方各讀一次環境變數：預設值與拼字會有六份，其中一份寫錯就是一次正式寫入被當成不發布，或反過來 |

## 還沒定、交給 tasks 的

- 環境變數與模式的名字、產物的檔名（`contracts/dry-run.md` 先寫了提案）。
- 片 2 與片 3 併不併成一個 PR（提案：併）。
- 第一級在交通分析那一步的確切停點（提案：選完熱點 bucket 與彙整池之後、第一次 LLM 呼叫之前）。
