# Implementation Plan: 低頻類別聚合式深度分析（category digest，交通週報）

**Branch**: `010-category-digest` | **Date**: 2026-07-13 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/010-category-digest/spec.md`

## Summary

在既有「每日 buffer → 每週分析」管線的**選取層**加一條平行路徑：對設定啟用的低頻類別（首發：道安政策），每週統計 buffer 池內有效文章數（quality ≥ 下限），達觸發門檻即以 digest 專用 Gemini prompt 產出一份多事件彙整報告，走既有 `hot_topic_report` 實體與發布管線上頁；成功持久化後把池內**全部**文章標記 `hot_topic_analyzed=TRUE`（消耗、池歸零）。「累積→觸發→清空」自成節奏。

**關鍵實作前提（research 已釐清）**：

- digest 的 `topic_token_signature` 存**空 list** → `compute_jaccard` 對空集合回 0.0（`src/filter.py:334`），digest 永遠不會成為未來一般 bucket 的 novelty prior basis，不會誤壓真正的政策 cluster（research D2）。
- 消耗分兩段：既有 `upsert_hot_topic_report` 已標記選材 links；新增 `storage.mark_articles_analyzed(links)` 標記池內其餘（含低品質未選材者）。Gemini 或 upsert 失敗 → 兩段都不執行，池不消耗（research D3）。
- digest 先佔 `max_hot_topics` 名額，一般 bucket 取剩餘名額（gate-then-cap 順序不變，cap 前先扣 digest 席次；research D5）。

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: `supabase-py`、`google-generativeai`（Gemini，僅週分析）、`jieba`、`PyYAML`
**Storage**: Supabase (PostgreSQL) — `articles`（buffer，欄位零變更）、`hot_topic_reports`（欄位零變更；本 feature **無 migration**）
**Testing**: pytest（`tests/unit`、`tests/integration`）
**Target Platform**: GitHub Actions（Ubuntu, 週一 cron）為正式執行環境；本機僅供開發除錯
**Project Type**: 單一資料管線專案（single project）
**Performance Goals**: 週分析維持 GitHub Actions 10 分鐘內；Gemini 呼叫總數仍 ≤ `max_hot_topics`(3)/週（digest 佔額內名額，不增量），2.5s inter-request delay 不變
**Constraints**: 額度紀律（憲章 IV）；不改一般 bucket 評分公式與流程；不改週節奏；零 schema／零前端變更（spec 承諾）
**Scale/Scope**: 政策類池流入約 3–4 篇/週，門檻 10 篇 → 約每 2–3 週觸發一次；啟用類別數初期 = 1

## Constitution Check

*GATE: 須在 Phase 0 前通過；Phase 1 後複查。*

| 原則 | 評估 | 結論 |
|---|---|---|
| I. Pipeline Integrity | digest 全部落在 **Analyze**（觸發統計＋Gemini 彙整，`analyzer.py`）與 **Store**（upsert＋消耗標記，`storage.py`）階段，由既有週跑 runner 串接；不跳接上游、不產無上游輸入的輸出。觸發未達時零行為變化。 | ✅ Pass |
| II. Configuration over Code | 啟用類別、觸發門檻、品質下限、選材上限全部置於 `PIPELINE_CONFIG_YML` 新增的 `category_digest` 區塊；增刪類別或調參**免改碼**。未設定 → feature off，行為與現狀完全一致。 | ✅ Pass |
| III. Idempotency & Dedup | digest upsert 沿用 `(week_start_date, topic_label)` 穩定鍵（label =「<類別> · 彙整」，每類每週至多一筆）；同週重跑時池已消耗 → 不重觸發，upsert 冪等。消耗失敗語意見 research D3。 | ✅ Pass |
| IV. Free Tier Discipline | digest 佔 `max_hot_topics` 額內名額，Gemini 總呼叫數不增；2.5s delay 沿用；不影響 10 分鐘上限（觸發統計是 O(pool) 的純計數）。 | ✅ Pass |
| V. Single Responsibility | 觸發統計＋彙整分析在 `analyzer.py`；標記 helper 在 `storage.py`；設定載入/驗證在 `pipeline_config.py`；串接在週跑 runner。無新模組、無跨模組耦合。 | ✅ Pass |
| VI. Knowledge Base Integrity | 與 FFXIV KB 無關。 | ✅ N/A |

**結論：無違規，無需 Complexity Tracking。**（Phase 1 設計後複查：仍無違規——零 schema 變更、零新模組。）

## Project Structure

### Documentation (this feature)

```text
specs/010-category-digest/
├── plan.md              # 本檔
├── research.md          # Phase 0：關鍵設計決策
├── data-model.md        # Phase 1：實體語意（無 schema 變更）
├── quickstart.md        # Phase 1：本機驗證步驟
├── contracts/
│   └── internal-contracts.md   # 函式與設定鍵契約（內部管線，無對外 API）
├── checklists/
│   └── requirements.md  # /speckit-specify 產出
├── spec.md
└── tasks.md             # /speckit-tasks 產出（本指令不建立）
```

### Source Code (repository root)

```text
src/
├── pipeline_config.py         # +category_digest 預設值與驗證
├── analyzer.py                # +DIGEST prompt 模板；+select_digest_pool()（純函數：有效篇數統計＋選材）；
│                              #  +analyze_category_digest()（沿用 _call_gemini）
└── storage.py                 # +mark_articles_analyzed(links)（消耗池內未選材文章）

scripts/
└── traffic_weekly_analysis.py # 串接：digest 觸發檢查（含 FR-009 池狀態 log）→ 席次保留 →
                               #  一般 bucket 選取（剩餘名額）→ digest 分析/持久化/消耗

config/
└── pipeline_config.example.yml  # +category_digest 區塊範例

tests/
├── unit/                      # 觸發計數（品質下限）、席次保留、空簽章不當 prior、config 驗證、消耗語意
└── integration/               # 兩次週跑序列：觸發＋消耗 → 第二跑不重觸發、零重複來源
```

**Structure Decision**: 單一管線專案，沿用既有 `src/` 階段模組與 `scripts/` runner。不新增模組、不新增 migration（零 schema 變更）；所有改動落在 4 個既有檔案 + 設定範例 + 測試。

## Phase 0 — Research

見 [research.md](./research.md)。解決的關鍵未知：

- D1 觸發度量＝有效篇數（非 Σ 分數）；預設門檻 10、品質下限 0.18 的依據。
- D2 digest 與 novelty gate 的隔離（空簽章 → 永不成為 prior basis）。
- D3 消耗的兩段實作與失敗語意（不消耗 vs 殘餘標記失敗的 ERROR 可見性）。
- D4 `category_digest` 設定形狀、載入與驗證。
- D5 席次保留（digest 先佔格）與同週同類 bucket 文章排除的實作點。
- D6 digest 選材（K=15）、專用 prompt、`cumulative_score`／`latest_source_date` 欄位在 digest 列的語意。

## Phase 1 — Design & Contracts

- [data-model.md](./data-model.md)：類別聚合池（查詢視角）、digest 報告列語意（label 樣式、空簽章、欄位語意）、`category_digest` 設定實體。**無 migration**。
- [contracts/internal-contracts.md](./contracts/internal-contracts.md)：新增/變更函式簽章與設定鍵契約、runner 串接順序契約。
- [quickstart.md](./quickstart.md)：本機驗證（read-only 重放實池 → dry-run 觸發統計 → pytest；含 prod 設定部署步驟）。
- Agent context：更新 `CLAUDE.md` 的 SPECKIT 區塊指向本 plan。

## Complexity Tracking

無違規，無需填寫。
