# Implementation Plan: 相關性選材閘（Relevance-Gated Selection）

**Branch**: `012-relevance-gated-selection` | **Date**: 2026-08-05 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/012-relevance-gated-selection/spec.md`

## Summary

每週熱點選材以標題 token 分類（`assign_category`）：凡標題含「機車」token 即落入 `機車事故` 桶
（該類關鍵字含裸詞「機車」，且排在分類詞典最後），再由 `initial_quality_score`（量**標題形式**，
非**主題相關性**）排序選材。於是刑案（竊盜／毒駕羈押）與車媒行銷稿（油耗／市佔／銷量）被當事故
選進發布報告（08-03：3 席 2 席離題，毒駕刑案還被排到全桶第一 0.405）。

**技術方案**：在選材前加一道**純函數、config 驅動、零 AI** 的相關性閘，把「含關鍵字但主題離題」
的文章排除在熱點桶的計分／選材之外；桶若因此清空則不發布（FR-003 自動滿足）。分兩層：

- **Tier 1（config-only，最便宜）**：補齊既有 `blocked_content_keywords`（filter 階段已存在的
  標題關鍵字封鎖，`src/pipeline/traffic.py:66`）缺少的**市場詞**（油耗／市佔／銷量／掛牌數／
  戰報／市占…）。零程式碼吃掉多數金線行銷案。以**內容 token** 而非**來源名**封鎖 → 滿足 FR-007
  （車媒的真實事故報導不被連坐）。
- **Tier 2（相關性閘，需程式碼）**：刑案側目前**無任何機制**。在 `src/filter.py` 新增純函數，對
  事故類桶做 per-category 相關性判定＝「有事故 token（撞／追撞／自撞／車禍／送醫／不治／傷）
  **且** 無刑案 token（竊／羈押／求償／毒駕／通緝）」，由每週選材（`scripts/traffic_weekly_analysis.py`）
  在 `cluster_traffic_articles` 前呼叫。AND-NOT 結構自然解掉「肇事逃逸同時是刑案也是事故」的
  邊界（肇事＝事故 token → 保留）。

**刻意不動的**：無 DB schema 變更（不新增欄位；每週選材期即時判定既有 buffer 資料）；不改每日
路徑成本輪廓；不換模型（發布摘要模型已能辨識離題，但它在選材**之後**，救不了已選進來的——
修正點在選材）。

## Technical Context

**Language/Version**: Python 3.x（既有管線）
**Primary Dependencies**: jieba（既有分詞，token 判定沿用 `normalise_title`）；PyYAML（config）；**無新增依賴**
**Storage**: Supabase（`articles`/buffer）— **本功能不改 schema**
**Testing**: pytest（`tests/unit`，127）；核心為純函數 → 全離線可測、零憑證
**Target Platform**: GitHub Actions 每週工作流（憲章 I：權威執行環境）
**Project Type**: 單一 Python 資料管線（collect → filter → analyze → store → notify）
**Performance Goals**: 選材階段維持**零外部 API 呼叫**（FR-006）；純 token 運算 O(篇數×規則數)，週跑 ≤10 分鐘（憲章 IV）不受影響
**Constraints**: 零 AI（憲章 IV / FR-006）；規則須 config 驅動免改碼（憲章 II）；純函數確定性可重播（憲章 III）
**Scale/Scope**: 每週 buffer 數十至上百篇；主要作用域＝事故類桶（`機車事故` acute），規則 config 可擴及其他事故類

## Constitution Check

*GATE: 通過方可進 Phase 0；Phase 1 設計後複檢。*

| 原則 | 判定 | 說明 |
|---|---|---|
| I. Pipeline Integrity | ✅ PASS | 相關性是 filter 階段職責（憲章明訂 dedup 在 `src/filter.py`，同一精神）。閘的**邏輯放 `src/filter.py`**（與 `assign_category` 同族），**呼叫時機**在每週選材前——邏輯歸位、時機隨選材。 |
| II. Configuration over Code | ✅ PASS（核心要求）| 事故 token 白名單／刑案·市場 token 黑名單／per-category 規則全部進 YAML（`categories_traffic.yml`／`pipeline_config.yml`），調規則免改碼。Tier 1 更是純 config。 |
| III. Idempotency & Dedup | ✅ PASS | 純函數、同輸入同輸出、可重播。 |
| IV. Free Tier Discipline | ✅ PASS（本功能存在理由）| 零 AI、純 token 運算。FR-006 寫死此約束。 |
| V. Single Responsibility | ✅ PASS | 閘函數住 `src/filter.py`（分類／相關性），不塞進 `analyzer.py`。三行勝過早熟抽象——先 seed 規則、不建規則引擎（憲章 V YAGNI）。 |
| VI. KB Integrity | N/A | FFXIV 專屬，本功能為 traffic。 |

**Post-Phase-1 複檢**：設計未新增模組、未改 schema、未引入外部呼叫 → 判定不變，**無違規**。

## Project Structure

### Documentation (this feature)

```text
specs/012-relevance-gated-selection/
├── plan.md              # 本檔
├── research.md          # Phase 0：四個設計決策
├── data-model.md        # Phase 1：config 規則結構、相關性分割、標記基準集（無 DB schema 變更）
├── quickstart.md        # Phase 1：調規則→重播基準→驗 SC 階梯 的流程
├── checklists/
│   └── requirements.md  # /speckit-specify 產出的品質檢查（全通過）
└── tasks.md             # Phase 2（/speckit-tasks 產出，非本命令）
```

契約目錄 `contracts/` **不適用**：本功能為內部選材邏輯，無新增對外介面（無 Worker API、
前端、CLI 或 stored schema 變更）。對外「介面」只有 config 規則格式，記於 data-model.md。

### Source Code (repository root)

```text
src/
├── filter.py                    # + 純函數：事故類桶的 per-category 相關性判定（白/黑名單 AND-NOT）
├── pipeline/traffic.py          # Tier 1：既有 blocked_content_keywords 消費點（config-only，不改碼）
└── analyzer.py                  # 不改邏輯；cluster/score/select 讀「已過閘」的候選

scripts/
├── traffic_weekly_analysis.py   # 在 cluster_traffic_articles 前呼叫相關性閘（Tier 2 唯一 wiring）
└── measure_relevance.py         # + 診斷腳本（唯讀）：對人工標記基準集重播、輸出 SC 階梯分數

config/
├── categories_traffic.yml       # + per-category relevance 規則區塊（事故 token / 刑案 token）
├── categories_traffic.example.yml  # 同步（憲章 II：example 是唯一進 git 的副本）
├── pipeline_config.yml          # Tier 1：補市場詞入 blocked_content_keywords
└── pipeline_config.example.yml     # 同步

tests/unit/
└── test_relevance_gate.py       # + 白/黑名單、AND-NOT 邊界（肇事逃逸保留）、桶清空→不發布
```

**Structure Decision**: 沿用既有單一管線結構。閘的**邏輯**進 `src/filter.py`（憲章 I/V：相關性是
filter 職責、單一模組），**呼叫**在 `scripts/traffic_weekly_analysis.py` 選材前。規則進 config
（憲章 II）。無新模組、無 schema 變更、無新依賴。

## Complexity Tracking

> 無憲章違規，本節留空。
