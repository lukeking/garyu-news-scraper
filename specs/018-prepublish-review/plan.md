# Implementation Plan: 週報發布前審核——修生成指令，加一步審稿＋修稿

> 2026-11-08：spec 縮成 US1，審稿、修稿與審核紀錄（US2、US3）拿掉，下面講它們的部分是當時的設計紀錄，沒有實作（spec Clarifications 最後一節）。

**Branch**: `018-prepublish-review` | **Date**: 2026-11-07 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/018-prepublish-review/spec.md`

## Summary

兩件事併行（Luke 2026-11-07）：

- **改生成指令**：
  - 彙整模板拿掉「事件互相獨立」的宣告；日期標明是報導日；計數由程式寫。
  - 只有標題的報導不進給模型的清單，由程式在文末照抄成 `### 僅標題` 一節。
  - 兩種模板都加數字範圍與因果的指令。
  - 三軸模板加兩個出口（Luke 2026-11-07，Unit 1 之後）：沒有事故的批次 A 軸寫「不適用」；人因與工程欄來源沒寫就寫「來源未載」。
  - 「只有標題」的判定先去掉已知的網站樣板字串（research R4）。
- **生成之後、寫入之前多一次審稿呼叫**：
  - 審稿模型是同一家的另一個模型，預設 `gemini-4-argon`，由變數指定。
  - 它回一份 JSON：每條發現附逐字原句與替換文字。
  - 程式只套用中、高嚴重度的那幾條；原句要剛好出現一次，套完逐條、再整份跑機械檢查，沒過就退回。
  - 結果寫進新表 `hot_topic_report_reviews`，週報 log 每份報告印一行 `[審稿]` 摘要，由週驗收 routine 轉進 Linear 報告。
- **驗證**：用重播腳本拿已發布的報告跑，不寫資料庫。

## Technical Context

**Language/Version**: Python 3.11（`weekly.yml` 的 setup-python）
**Primary Dependencies**: `requests`（`_call_gemini` 走 REST）、`supabase` client、`python-dotenv`（本機腳本）；不新增套件
**Storage**: Supabase（PostgreSQL）新表 `hot_topic_report_reviews`（`data-model.md`）
**Testing**: `pytest tests/unit`（CI 的 `unit` job）；`pytest tests/integration`（本機 Supabase 54331，寫入新表）；重播腳本跑真的 API（本機、手動、計費）
**Target Platform**: GitHub Actions `weekly.yml`（ubuntu-latest），本機 WSL 跑重播
**Project Type**: 排程資料管線（Collect → Filter → Analyze → Store → Publish）
**Performance Goals**: 一份報告的審稿加套用在 60 秒內（推論，research R9 估 20–40 秒）；週報總耗時 ≤ 20 分（SC-004 第二階）
**Constraints**: 週報 job `timeout-minutes: 30`；Gemini 月上限 NT$300（同一把 key）；`GEMINI_MAX_RETRIES` 沿用
**Scale/Scope**: 每週約 3 份報告（熱點最多 `max_hot_topics` 份＋彙整）；彙整清單最多 25 篇、三軸 10 篇

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

依 `.specify/memory/constitution.md` 2.1.1 現行條文逐條：

| 原則 | 本 feature 的對應 | 判定 |
|---|---|---|
| I Pipeline Integrity：階段依序、失敗要出聲、不得無上游輸出 | 審稿放在 Analyze 之內、Store 之前；生成空字串不送審。審稿失敗照發原稿，但每份都印 `[審稿]` 行、狀態與原因寫進紀錄、週驗收轉進報告（FR-012、FR-013、FR-014a），不是靜默 | 通過 |
| II Configuration over Code：模型名稱外部化，換模型不改程式 | 審稿模型由 GitHub 變數 `GEMINI_REVIEW_MODEL_NAME` 指定；沒設定就不跑審稿並記 `model_unset` | 通過 |
| III Idempotency：同一份語料重跑得到相同的儲存狀態，主鍵穩定 | 新表以 `(week_start_date, topic_label)` 為唯一鍵 upsert，與 `hot_topic_reports` 同鍵。LLM 輸出本身不確定，這點與現有報告相同，不是新引入的 | 通過 |
| IV Explicit Budgets：預算寫在 `docs/external-services.md`、呼叫有上限、job 有 timeout | 每份報告最多一次審稿呼叫，報告數已受 `max_hot_topics` 與 digest 設定限制；審稿呼叫前照 `scripts/traffic_weekly_analysis.py` 的 `_GEMINI_DELAY` 間隔，跟現有的生成呼叫一樣，限流值寫在呼叫旁邊；重試沿用 `GEMINI_MAX_RETRIES`；`docs/external-services.md` 的 Gemini 列補上審稿模型與估算；timeout 30 不變（SC-004 驗） | 通過（要改 `docs/external-services.md`） |
| V Single Responsibility：一個模組一個階段；共用 helper 放在名稱清楚的共用模組；新抽象要有理由 | 審稿 prompt 與呼叫放 `src/analyzer.py`（它擁有 LLM 呼叫）；純文字處理（錨點、套用替換、機械檢查、摘要行）放新模組 `src/report_review.py`，週報與重播共用；寫入放 `src/storage.py`；串接放 `scripts/traffic_weekly_analysis.py`。新模組的理由見 Complexity Tracking | 通過（附理由） |
| VI Knowledge Base Integrity | 不碰 FFXIV 分析 | 不適用 |
| Technology Constraints | 同一個 LLM API（`src/analyzer.py` 呼叫）、同一個 Supabase；加一張表不改系統形狀 | 通過 |
| Governance：動到 pipeline 模組的 PR 要在內文驗 I–III | PR 會動 `src/analyzer.py`、`src/storage.py`，內文要逐條寫 I–III | 待 PR 內文 |

設計完成後重新檢查（Phase 1 之後）：判定不變。`hot_topic_report_reviews` 不開 anon policy，Worker API 讀不到，不影響公開 API 的形狀。

## Project Structure

### Documentation (this feature)

```text
specs/018-prepublish-review/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── review-output.md
│   ├── summary-line.md
│   └── replay-cli.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
src/
├── analyzer.py              # 改：DIGEST_*／HOT_TOPIC_* 指令；清單組裝（報導日、只有標題的分流）；review_report()；_call_gemini 加 model 與 JSON 模式參數
├── report_review.py         # 新：錨點資料與標準組裝（可排除 id）、只有標題的判定、套用替換、機械檢查、狀態決定、[審稿] 摘要行
└── storage.py               # 改：upsert_report_review()

scripts/
├── traffic_weekly_analysis.py   # 改：生成 → 審稿 → 套用 → upsert 報告 → upsert 紀錄 → 印摘要行；一週合計行
├── replay_report_review.py      # 新：重播（唯讀資料庫）
└── setup_test_db.sh             # 改：加 006

supabase_migrations/006_report_reviews.sql   # 新
routines/weekly-verify/PROMPT.md             # 改：讀 [審稿] 行（cold review 路徑）
docs/external-services.md                    # 改：Gemini 列補審稿模型、估算、變數名

tests/unit/
├── test_report_review.py        # 新：套用、檢查、狀態、摘要行格式、錨點排除、只有標題判定
├── test_digest_prompt.py        # 新：指令不含「互相獨立」、清單標「報導日」、只有標題的分流與 ### 僅標題、計數行
└── test_weekly_review_flow.py   # 新：串接的每條失敗路徑（monkeypatch _call_gemini 與 storage）
tests/integration/test_report_review_storage.py   # 新：本機 Supabase upsert／讀回
```

**Structure Decision**: 沿用單一 Python 專案的現有配置；只新增 `src/report_review.py` 一個模組與一支重播腳本。

## Phase 0 / Phase 1 產物

- `research.md`：R1 審稿模型、R2 審與修合一、R3 指令改法、R4 只有標題的判定、R5 機械檢查、R6 標準與錨點、R7 紀錄存放、
  R8 週驗收、R9 時間與費用、R10「誤報少」門檻。
- `data-model.md`：新表、六種狀態、錨點、生成輸入。
- `contracts/`：審稿輸出 JSON、`[審稿]` 摘要行、重播腳本介面。
- `quickstart.md`：重播、量 SC-001～003、本機整合測試、上線步驟。

## 驗證順序（給 tasks 的骨架）

1. **先量現況**，不改程式：
   - 重建三份彙整的輸入，校準 R4 的「只有標題」判定；
   - 用 R5 的檢查跑已發布的原稿，證明檢查咬得到（SC-001 的對照組）。
2. **US1 指令修正**（可單獨出貨）：改指令與清單組裝，重播 `--regenerate` 量 SC-001。
3. **錨點**：
   - 核對偏頗類（彙整）；
   - 三軸跑一次編輯評論並核對；
   - 寫進 `src/report_review.py`。
4. **US2 審稿＋套用**：
   - 單元測試先行；
   - 重播量 SC-002（留一）、SC-003；
   - argon 過不了 Gate 就換候選再測。
5. **US3 紀錄與摘要**：
   - 新表、storage、摘要行、routine；
   - 上線後連兩週量 SC-004～006。

## Complexity Tracking

| 項目 | 為什麼需要 | 更簡單的做法為什麼不夠 |
|---|---|---|
| 新模組 `src/report_review.py` | 錨點、套用替換、機械檢查、摘要行要同時給週報腳本與重播腳本用，而且都是不碰網路的純函式，單元測試直接打 | 放進 `src/analyzer.py`：該檔已約 1,000 行，而且負責 LLM 呼叫；純文字處理混進去，測試要繞過呼叫邊界。放進腳本：重播腳本就得 import 週報腳本 |
| 新表 `hot_topic_report_reviews` | FR-014 要長期查得到，SC-006 要比對發布版本 | 加欄位在 `hot_topic_reports`：Worker API 會一起讀出審核資料；只留 log 或 artifact：90 天後就沒了，也不能查詢 |
