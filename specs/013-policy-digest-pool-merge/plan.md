# Implementation Plan: 政策 digest 池匯流兄弟政策類別

**Branch**: `013-policy-digest-pool-merge` | **Date**: 2026-08-10 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/013-policy-digest-pool-merge/spec.md`

## Summary

讓 `道安政策` 的 digest 選材池能涵蓋一組**指定的兄弟類別**（初始＝`路權政策`／`科技執法`／
`交通工程`），以解除 BACKLOG #8 的單一 feed 承重依賴。

技術取徑：**設定驅動的池組成擴充**。`select_digest_pool` 目前以單一字串相等比對
`major_category`（`src/analyzer.py:1120`）；改為比對一個**類別集合**，集合由既有的
per-category digest 設定新增一個 `include_categories` 鍵提供。**不動分類法、不動文章的
分類標記、不新增模組、不引入 AI 或網路呼叫。** 缺設定時集合退化為單元素集，行為與現況逐篇相同。

## Technical Context

**Language/Version**: Python 3.11（CI runner 實測 3.11.15）
**Primary Dependencies**: PyYAML（設定載入與驗證）。本功能**不觸及** supabase-py 與
google-generativeai——選材是純函數，位於 LLM 呼叫之前。
**Storage**: Supabase PostgreSQL（`articles`、`hot_topic_reports`）。本功能不改 schema、
不改 upsert 鍵、不改任何寫入語意。
**Testing**: `python -m pytest tests/unit`（148 個，零外部依賴；CI 的 required check `unit` 跑的就是這個）。
本功能的改動面**完全落在可離線單元測試的純函數與設定驗證上**——這是本 spec 少見的有利條件，
不存在 011／012 那種「只能手動驗收」的缺口。
**Target Platform**: GitHub Actions ubuntu runner（每週一 08:00 台北時間的週報 workflow）；
本機為開發與驗證用。
**Project Type**: 單一專案的資料管線（Collect → Filter → Analyze → Store → Notify）。
**Performance Goals**: 不適用。改動是集合成員判定，輸入規模為單週 buffer（實測數十至數百篇），
相對既有的 LLM 呼叫可忽略。
**Constraints**: 憲章 IV 的 workflow 10 分鐘上限（見 Constitution Check 的觀察事項）。
**Scale/Scope**: 改動 2 個原始檔（`src/analyzer.py`、`src/pipeline_config.py`）
＋ 2 份設定（本機 `config/pipeline_config.yml` 與其 `.example` 副本）＋ 1 個 prod 環境變數。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 判定 | 依據 |
|---|---|---|
| **I. Pipeline Integrity** | ⚠️ **需設計修正**（見下） | 改動位於 Analyze 階段內部，不跨階段、不跳過上游 |
| **II. Configuration over Code** | ✅ **強化** | 本功能的**全部目的**就是把池組成從程式碼常數變成設定；調整匯流範圍將不需要改任何程式碼 |
| **III. Idempotency & Deduplication** | ✅ 通過 | 不改 upsert 鍵、不改內容雜湊；消耗標記沿用同鍵 upsert 的冪等性。同一 link 只有一個 `major_category`，集合比對不可能產生重複計入 |
| **IV. Free Tier Discipline** | ✅ 通過 | **零新增 LLM 呼叫**：傳給 `analyze_category_digest` 的是 `selected`，其長度受 `max_articles` 上限（維持 25）約束，不因池變大而變長。零新增網路請求 |
| **V. Single Responsibility** | ✅ 通過 | 改動落在既有 owner：選材邏輯在 `analyzer.py`、設定驗證在 `pipeline_config.py`。不新增模組、不新增抽象（YAGNI） |
| **VI. Knowledge Base Integrity** | N/A | FFXIV 專屬，本功能不觸及 |

### ⚠️ 原則 I 的設計修正（Gate 未失敗，但規格需調整）

spec 的 Edge Cases 寫著「**匯流清單含不存在的類別名：忽略該項，不得使 digest 失敗**」。
憲章 I 明文 **「Stage failures MUST surface with actionable error messages; silent failures
are forbidden.」**——「忽略」若是靜默的，就直接違反這條。

**兩者可以同時滿足，但不能照 spec 字面實作**：解法是**設定載入時驗證＋WARNING 留痕**，
而非執行時靜默跳過。詳見 `research.md` R1。這是 Constitution Check 產生實際設計改變的一項，
不是形式勾選。

### 觀察事項（非本功能造成，不阻擋）

2026-08-10 的週報 run（`31345438480`）耗時 **10m21s**，**已超過憲章 IV 的 10 分鐘上限**。
這是**既有狀況**，與本功能無關（本功能為時間中性：無新增 LLM 呼叫、無新增網路請求，
僅多比對數十個字串）。**在此記錄以免日後把超時歸因到本 spec**；是否處理屬獨立議題。

## Project Structure

### Documentation (this feature)

```text
specs/013-policy-digest-pool-merge/
├── plan.md              # 本檔
├── research.md          # Phase 0 產出
├── data-model.md        # Phase 1 產出
├── quickstart.md        # Phase 1 產出
├── contracts/
│   └── digest-pool.md   # Phase 1 產出：設定契約＋選材函數契約
├── checklists/
│   └── requirements.md  # /speckit-specify 產出
└── tasks.md             # Phase 2（/speckit-tasks 產出，本指令不建立）
```

### Source Code (repository root)

```text
src/
├── analyzer.py          # 改：select_digest_pool 的類別比對改為集合成員判定
└── pipeline_config.py   # 改：category_digest 驗證新增 include_categories

scripts/
└── traffic_weekly_analysis.py   # 改：FR-007 的逐類別貢獻 log（呼叫端）

config/
├── pipeline_config.yml          # 改：加 include_categories（gitignored，本機副本）
└── pipeline_config.example.yml  # 改：同步（這是唯一進 git 的副本）

tests/unit/
└── test_analyzer.py 等          # 增：選材集合、預設關閉、設定驗證的測試
```

**Structure Decision**: 沿用既有單一專案結構，**不新增任何目錄或模組**。本功能的改動
刻意集中在兩個已擁有相應職責的檔案，加上呼叫端的一行 log。這符合憲章 V 對
「三行相似程式碼勝過過早抽象」的要求——匯流不需要新的抽象層，它是既有比對條件的放寬。

## Complexity Tracking

> 本功能無憲章違規需要辯護。

唯一需要記錄的張力已在 Constitution Check 處理：spec 的 fail-soft 措辭與憲章 I 的
「禁止靜默失敗」衝突，解法是把「靜默忽略」換成「載入時驗證＋WARNING 留痕」，
**兩者皆滿足，無需豁免**。設計理由見 `research.md` R1。
