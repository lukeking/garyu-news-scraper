# Implementation Plan: 熱點報告標示來源涵蓋的日期區間

**Branch**: `016-hot-topic-source-range` | **Date**: 2026-11-02 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/016-hot-topic-source-range/spec.md`

## Summary

交通頁的熱點報告留在原本的週次，卡片寫出焦點事件的發布日期區間；文章列的 ★ 只標真的列進報告的文章，提示寫出報告所在的週次。
做法分四段：

1. **產生時帶日期**：`analyze_hot_topic`、`analyze_category_digest` 回傳的每個焦點事件多帶 `published`（R1）。不改 schema、不改 Worker。
   `upsert_hot_topic_report` 寫完每份報告多印一行「焦點事件帶發布時間 n/m」，讓雲端的週驗收 routine 讀 log 就能驗 SC-003（R7）。
2. **回填**：一次性腳本補齊 56 份既有報告的 `published`，只寫 `source_article_links`，dry-run 預設、`--apply` 寫入後逐份讀回（R3）。
3. **簽核畫面**：實作前用 spike 渲染 412 px 亮、暗兩張加一張桌面，給 Luke 簽核（R5）。
4. **前端**：`app.js` 從焦點事件算台灣日期的區間（R2）；用整份報告清單建 link → 週次對照，★ 與加強樣式改看它（R4）。

研究結論見 [research.md](./research.md)。最關鍵的兩條：日期跟著焦點事件存，三個讀取端（Worker、`publisher.py`、前端）裡只有前端要改（R1）；
`hot_topic_analyzed` 包含只被彙整消耗的文章，所以 ★ 不能再看它（R4）。

## Technical Context

**Language/Version**: Python 3.11（週報與回填腳本）；瀏覽器端原生 JavaScript（`pages/shared/app.js`，全域腳本、無建置）
**Primary Dependencies**: 既有的 supabase-py；JS 測試用既有的 jsdom＋`node --test`。不新增依賴
**Storage**: Supabase PostgreSQL。不改 schema；`hot_topic_reports.source_article_links`（JSONB）每一項加 `published`
**Testing**: `python -m pytest tests/unit`（CI required check `unit`）＋ `npm test`（同在 `unit` job）。回填腳本的轉換是純函式、離線測；
寫入只在 `--apply`，寫後讀回。畫面以截圖簽核
**Target Platform**: GitHub Actions 週報（`weekly.yml`）；Cloudflare Pages（`deploy-pages-traffic.yml`，`pages/shared/**` 改動自動部署）
**Project Type**: 單一 repo 的資料管線＋靜態前端
**Performance Goals**: 不適用。前端多一次 O(報告數 × 焦點事件數) 的對照建立（約 600 項）
**Constraints**: 分享連結不變（`week_start_date`、`topic_label`、卡片 `id` 與分享 URL 的組法都不動）；日期固定台灣時間；
畫面在 412 px 寬、亮暗兩個主題都要讀得清楚
**Scale/Scope**: 程式 3 個檔（`src/analyzer.py`、`src/storage.py` 多一行 log、`pages/shared/app.js`）＋ 1 支新腳本 ＋ CSS ＋ 測試；
資料一次回填 56 份報告、602 項

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

依據憲章 2.1.1（`.specify/memory/constitution.md`）。plan 範本沒有自己的 gate（Constitution Check 只有佔位字），沒有範本獨有、憲章沒寫的 gate 要點名。

| 原則 | 判定 | 依據 |
|---|---|---|
| **I. Pipeline Integrity** | ✅ 通過 | 階段順序不變；Analyze 的輸出多一個欄位；Store 寫完每份報告多印一行「焦點事件帶發布時間 n/m」（0/0 也印），帶不上日期看得見。回填腳本在管線之外，每個跳過的項目印出 link 與原因、讀回不一致就 exit 非 0，不靜默 |
| **II. Configuration over Code** | ✅ 不受影響 | 不增減來源、不換模型 |
| **III. Idempotency & Deduplication** | ✅ 通過 | 報告仍以 `(week_start_date, topic_label)` upsert；`published` 取自已存的文章，重跑同值。回填只補缺的、不覆寫已有的，重跑 0 項 |
| **IV. Explicit Budgets** | ✅ 通過 | 不新增外部服務、不多呼叫 LLM。回填是 56 次 Supabase update，在既有額度內 |
| **V. Single Responsibility** | ✅ 通過 | 焦點事件由 `analyzer.py` 組（它本來就組這份清單）；回填放 `scripts/`，沿用 `src/storage.py` 的 client；不新增 `src/` 模組 |
| **VI. Knowledge Base Integrity** | ✅ 不受影響 | 只動交通報告，FFXIV 分析與 KB 不碰 |

PR 會動到 `src/analyzer.py`、`src/storage.py`（Governance 的 Compliance review）：PR 內文要逐條寫 Principles I–III 的符合情形。

**Post-design re-check（Phase 1 之後）**：仍全數通過。資料形狀的改動只有 JSONB 項目多一個選用欄位（[data-model.md](./data-model.md)），
讀取端對舊形狀都容忍（[contracts/hot-topics-api.md](./contracts/hot-topics-api.md)）；★ 改看對照後，`hot_topic_analyzed` 的寫入與管線內的用法不變。

## Project Structure

### Documentation (this feature)

```text
specs/016-hot-topic-source-range/
├── spec.md
├── plan.md              # 本檔
├── research.md          # R1–R6
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── hot-topics-api.md
│   ├── hot-topic-card-ui.md
│   └── log-lines.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks 產生
```

### Source Code (repository root)

```text
src/analyzer.py                                # analyze_hot_topic／analyze_category_digest 的焦點事件帶 published
src/storage.py                                 # upsert_hot_topic_report 多印一行「焦點事件帶發布時間 n/m」（contracts/log-lines.md）
scripts/backfill_hot_topic_source_dates.py     # 新：一次性回填（預設 dry-run、--apply 寫入、逐份讀回）
pages/shared/app.js                            # 區間計算與格式、卡片顯示；link → 週次對照；★ 與 tr-strong 改看對照
pages/shared/shared.css                        # 區間標示的樣式（簽核後定）
tests/unit/test_hot_topic_source_dates.py      # 新：焦點事件帶 published、log 行的格式、回填的轉換
tests/js/hot-topic-card.test.mjs               # 新：區間計算與格式、★ 對照與提示
tests/js/traffic-row.test.mjs                  # 改：既有的 ★ 測試改成看對照
tests/js/harness.mjs                           # 改：EXPORTED 加新函式
specs/BACKLOG.md                               # closeout：移出 GNS-20261031-005
```

不改：`workers/api/`（原樣轉送 `source_article_links`）、`src/publisher.py`（同上）、schema；`src/storage.py` 只加一行 log，
既有的 `✓ hot_topic_report upserted:` 那行不動（routine 在讀）。

**Structure Decision**: 沿用現有分層——產生端在 `src/analyzer.py`，一次性資料修補在 `scripts/`，顯示在 `pages/shared/`。

## Complexity Tracking

沒有違反憲章的項目，不需要說明。
