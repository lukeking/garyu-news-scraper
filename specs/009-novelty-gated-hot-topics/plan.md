# Implementation Plan: 節奏觸發式深度分析 + 深度來源分類補進（交通週報 Layer 3）

**Branch**: `009-novelty-gated-hot-topics` | **Date**: 2026-06-14 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/009-novelty-gated-hot-topics/spec.md`

## Summary

兩件相關改動疊在既有「每日 buffer → 每週分析」管線上：

1. **Novelty gate（US1，主軸）**：週分析在 `select_hot_topics` 後、Gemini 之前，加一道「自上次該話題報告以來是否有實質新進展」的閘。順序為 **gate-then-cap**（先閘所有過門檻 bucket，再取 top `max_hot_topics`）。需持久化每個已報告話題的 novelty 基準（分數、代表詞簽章、最新來源日期），並在比對時讀回。
2. **Source-default 分類（US2）**：`src/pipeline/traffic.py` 分類迴圈在標題 token 判為 `uncategorised` 時，依「來源→預設分類」設定補上 fallback，使低頻深度來源（報導者/天下…）匯入對應政策 bucket。純設定查表、零 AI。

**關鍵實作前提（research 已釐清）**：既有 `upsert_hot_topic_report` 會把來源文章標 `hot_topic_analyzed=TRUE`，`get_traffic_buffer` 會排除它們 → 已報告話題的文章離開 buffer。因此 novelty 比對的本質是「本週新累積 vs 上次報告基準」的**突增偵測**，而非同一文章集的成長；FR-007 的兩條件據此精確化（見 research.md D1）。

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: `supabase-py`、`google-generativeai`（Gemini，僅週分析）、`jieba`、`feedparser`、`PyYAML`  
**Storage**: Supabase (PostgreSQL) — `articles`（buffer 欄位）、`hot_topic_reports`（本 feature 經 migration 004 增欄）  
**Testing**: pytest（`tests/unit`、`tests/integration`）  
**Target Platform**: GitHub Actions（Ubuntu, 週一 cron）為正式執行環境；本機僅供開發除錯  
**Project Type**: 單一資料管線專案（single project）  
**Performance Goals**: 週分析須在 GitHub Actions 10 分鐘內完成；Gemini ≤ `max_hot_topics`(3) 次/週，維持 2.5s inter-request delay  
**Constraints**: 免費額度紀律（憲章 IV）；daily buffer 維持零 AI；novelty gate 只會**減少**、不會增加 Gemini 呼叫；不改評分公式、不改週節奏  
**Scale/Scope**: 每週約 20–60 篇交通文章，buffer 累積至多 8 週；`hot_topic_reports` 每類別每週至多一筆

## Constitution Check

*GATE: 須在 Phase 0 前通過；Phase 1 後複查。*

| 原則 | 評估 | 結論 |
|---|---|---|
| I. Pipeline Integrity | Source-default 屬 **Filter** 階段（`traffic.py` 分類）；novelty gate 屬 **Analyze/Store**（`analyzer` 選取 + `storage` 持久化）。無跨階段跳接；content-type 邏輯仍封裝於 traffic 分支。 | ✅ Pass |
| II. Configuration over Code | 來源→預設分類 map 置於 `CATEGORIES_TRAFFIC_YML`；novelty 參數（成長百分比、相似度門檻）置於 `PIPELINE_CONFIG_YML`。新增一個 source-default 或調 novelty 門檻**免改碼**。 | ✅ Pass |
| III. Idempotency & Dedup | dedup 仍在 `filter.py`；`hot_topic_reports` upsert 以 `(week_start_date, topic_label)` 穩定鍵；novelty 基準讀取**須排除當週自身報告**以保證同 corpus 重跑結果一致（research D5）。 | ✅ Pass（含重跑注意事項） |
| IV. Free Tier Discipline | novelty gate 僅減少觸發；保留 ≤3 上限與 2.5s delay；source-default 零 AI；不影響 10 分鐘上限。 | ✅ Pass |
| V. Single Responsibility | 分類改動只在 `filter.py`/`traffic.py`；選取/閘門在 `analyzer.py`；持久化在 `storage.py`；設定載入在 `pipeline_config.py`。無新增跨模組耦合、無早熟抽象。 | ✅ Pass |
| VI. Knowledge Base Integrity | 與 FFXIV KB 無關。 | ✅ N/A |

**結論：無違規，無需 Complexity Tracking。**

## Project Structure

### Documentation (this feature)

```text
specs/009-novelty-gated-hot-topics/
├── plan.md              # 本檔
├── research.md          # Phase 0：關鍵設計決策
├── data-model.md        # Phase 1：實體與 schema（migration 004）
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
├── pipeline_config.py        # +load_source_default_categories(); +novelty 參數讀取
├── filter.py                 # assign_category 不變（fallback 在呼叫端套用）
├── pipeline/
│   └── traffic.py            # 分類迴圈：uncategorised → source-default fallback
├── analyzer.py               # 新增 novelty gate（gate-then-cap）；代表詞簽章/最新日期計算
└── storage.py                # +get_recent_hot_topic_reports(); upsert 增 token_signature/latest_source_date 欄

scripts/
└── traffic_weekly_analysis.py  # 串接：讀 prior reports → 傳入 gate → 寫入新欄

supabase_migrations/
└── 004_hot_topic_novelty.sql   # hot_topic_reports 增欄（token_signature, latest_source_date）

config/
├── categories_traffic.example.yml  # +source_defaults 範例
└── pipeline_config.example.yml     # +topic_scoring.novelty_growth_pct, topic_identity.similarity_threshold（若有 example）

tests/
├── unit/                     # novelty gate、source-default fallback、topic identity 比對
└── integration/              # 週分析端到端（兩週序列：抑制 / 再觸發）
```

**Structure Decision**: 單一管線專案，沿用既有 `src/` 階段模組與 `scripts/` runner。本 feature 不新增模組、不改目錄結構；所有改動落在既有檔案 + 一支 SQL migration + 設定範例。

## Phase 0 — Research

見 [research.md](./research.md)。解決的關鍵未知：
- D1 novelty 比對語意（hot_topic_analyzed 造成文章集互斥 → 突增偵測）與 FR-007 精確化。
- D2 跨週 topic 身分（hybrid：major_category + 代表詞 Jaccard；含 topic_label 同類別碰撞修正）。
- D3 novelty delta 定值（成長百分比 `p` 預設、結構條件）。
- D4 source-default map 設定位置與載入。
- D5 idempotency / 重跑 與 fail-open。

## Phase 1 — Design & Contracts

- [data-model.md](./data-model.md)：`hot_topic_reports` 增欄與 migration 004；source-default map 設定實體。
- [contracts/internal-contracts.md](./contracts/internal-contracts.md)：新增/變更函式簽章與設定鍵契約。
- [quickstart.md](./quickstart.md)：本機驗證（seed buffer → 兩週序列 → pytest）。
- Agent context：更新 `CLAUDE.md` 的 SPECKIT 區塊指向本 plan。

## Complexity Tracking

無違規，無需填寫。
