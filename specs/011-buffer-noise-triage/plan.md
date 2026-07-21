# Implementation Plan: Buffer List 雜訊分流呈現層

**Branch**: `011-buffer-noise-triage` | **Date**: 2026-07-21 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/011-buffer-noise-triage/spec.md`

## Summary

讓交通週頁的緩衝區列表能一眼分辨雜訊。三個手法：雜訊列預設收合為單一提示行（P1）、一鍵收掉整個收集來源（P2）、高價值列視覺加強（P3）。

技術路徑的關鍵決定來自澄清階段與 [research.md](./research.md)：**雜訊分級不落地儲存，改由 Worker API 在回應時依「來源 → 倍率設定」推導**。這一個決定同時消除了資料回填、schema 變更、以及舊週無分級的矛盾，也讓設定調整能立即對所有歷史週次生效。

## Technical Context

**Language/Version**: JavaScript（Cloudflare Workers runtime + 瀏覽器原生 JS，無框架）；Python 3.11（僅量測腳本）
**Primary Dependencies**: 無新增。既有 `supabase-py`（量測腳本）、Cloudflare Workers 執行環境、前端零依賴
**Storage**: **不新增任何持久化資料。** 唯一新增設定為 Worker 變數，來源為 GitHub production environment variable
**Testing**: `pytest`（量測腳本）。Worker 與前端目前無 JS 測試框架——見 Complexity Tracking
**Target Platform**: Cloudflare Workers（API）+ Cloudflare Pages（前端）；桌機與行動瀏覽器
**Project Type**: Web，三層既有結構（Python pipeline / Worker API / Pages 前端）
**Performance Goals**: 單週列表約 90–200 篇且成長中；推導為記憶體內 map 查表，MUST NOT 增加任何網路往返
**Constraints**: 讀取時推導（FR-001）、零回填（FR-001a）、須在圖片覆蓋率 0% 的舊週成立（FR-017）、零 AI 成本（FR-007）
**Scale/Scope**: 交通文章全表 642 篇 / 11 週；每日流入約 60 篇且成長；30 個啟用來源，其中 6 個有足夠量測樣本（涵蓋 83% 文章量）

## Constitution Check

*GATE: 通過。無違反項需要豁免。*

| 原則 | 判定 | 依據 |
|---|---|---|
| **I. Pipeline Integrity** | ✅ PASS | 不新增、不修改任何 pipeline stage。量測腳本為唯讀、獨立於管線之外，沿用 `scripts/measure_body_fetch.py` 的既有先例 |
| **II. Configuration over Code** | ✅ PASS（含設計約束） | 來源倍率 MUST 為設定，MUST NOT 以字面值寫進 `app.js` 或 Worker 原始碼。調整某來源的評級或門檻 MUST 只需改設定 |
| **III. Idempotency & Deduplication** | ✅ N/A | 本功能零寫入。不觸及 `src/filter.py` 去重或 `src/storage.py` upsert |
| **IV. Free Tier Discipline** | ✅ PASS | 零 AI 呼叫、零新增外部服務。推導為 map 查表，Worker 請求成本不變；量測腳本為手動觸發的唯讀查詢 |
| **V. Single Responsibility** | ✅ PASS | 推導歸 Worker API（既有職責＝「serves the articles data to frontends」）、呈現歸 `pages/shared/app.js`、量測歸 `scripts/`。同一件事不跨層重複實作 |
| **VI. Knowledge Base Integrity** | ✅ N/A | FFXIV 專屬，本功能不觸及 |

### 設定放置位置的決定

推導需要「來源 → 倍率」對應表，而該表必須抵達 Worker。三個方案：

| 方案 | 調整成本 | 否決理由 |
|---|---|---|
| **A. Worker 變數（採用）** | 改 GH environment variable + 重跑 deploy workflow | — |
| B. Supabase 設定表，請求時讀取 | 改一列資料即生效 | 為 6 個設定值新增資料表與每請求查詢，違反 YAGNI（憲章 V 明文「三行相似程式碼勝過過早抽象」） |
| C. 隨 Pages 部署的靜態 JSON | 改檔案 + 部署 | 設定鍵為來源名稱，而來源清單（`sources_traffic.yml`）依憲章 II 刻意不進版控。把來源名寫進已提交的檔案等於部分洩漏該設定 |

**採用 A**，並記錄其代價：改評級需重跑 Worker 部署（約 1 分鐘），比 pipeline 設定「下次執行生效」稍重。與既有 `SUPABASE_URL` 走同一條路徑（`deploy-worker.yml` 的 `vars:` + `env:` 區塊），不引入新機制。

## Project Structure

### Documentation (this feature)

```text
specs/011-buffer-noise-triage/
├── plan.md              # 本檔
├── spec.md              # 功能規格（含 5 題澄清紀錄）
├── research.md          # 來源雜訊量測（Phase 0，已完成）
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   └── week-detail-api.md   # Phase 1
└── checklists/
    └── requirements.md
```

### Source Code (repository root)

```text
scripts/
└── measure_source_uptake.py     # 新增：可重複執行的來源採用率量測（FR-005c 要求窗口隨時間重算）

workers/api/src/
└── index.js                     # 修改：week-detail 回應加上推導欄位；新增 env 設定解析

pages/shared/
├── app.js                       # 修改：trafficGroups/trafficRow 加降級收合、來源收起、高價值標記
└── shared.css                   # 修改：降級與突顯樣式

.github/workflows/
└── deploy-worker.yml            # 修改：vars/env 區塊加入新設定變數

tests/unit/
└── test_source_uptake.py        # 新增：量測邏輯的視窗界定與污染排除
```

**Structure Decision**: 沿用既有三層結構，不新增目錄。本功能**不觸及 `src/`**（Python pipeline）——這是讀取時推導決定帶來的直接好處。量測腳本放 `scripts/`，與 `measure_body_fetch.py`、`eval_gn_enrichment.py` 同層。

## Phase 0：研究（已完成）

見 [research.md](./research.md)。摘要：

- **決定**：以「週報採用率相對全體基準的倍率」作為來源判定值。
- **理由**：品質分數已實測無鑑別力且為循環論證（本功能立案依據即由該分數導出）。採用率是獨立的下游真實結果，實測上下相差 8.6 倍。
- **已排除的替代方案**：摘要可用率與圖片覆蓋率——經對照驗證證實為 per-run 假影（Actions IP 被擋導致 og 抓取失敗），非來源性質。
- **已排除的污染**：舊週生存者偏差（過期未分析資料遭清除，W20/W21 呈現不可能的 100% 採用率）、當週尚未跑週報（結構性 0%）。
- **產出**：6 個來源具備 E1 等級數值，涵蓋 83% 文章量；6 個新來源須待 07-27 首次週報。

**對規格的回饋已套用**：FR-005 措辭由「高價值內容佔比」改為「相對基準倍率」；新增 FR-005c（窗口須隨時間重算）與 FR-005d（樣本不足者不填值）。

## Phase 1：設計與契約

產出三份文件：

1. **data-model.md** — 三個實體：來源倍率設定（Worker 變數的 JSON 形狀）、雜訊分級（推導、不落地）、使用者收起清單（瀏覽器端）。含驗證規則與預設值行為（FR-006）。
2. **contracts/week-detail-api.md** — week-detail 回應新增一個推導欄位的契約：欄位名、型別、缺值語意（設定未涵蓋的來源）、以及「此欄位不存在於資料庫」這項不變式。
3. **quickstart.md** — 三段流程：跑量測腳本 → 產生設定值 → 部署與驗證；含如何在零圖片舊週驗證（FR-017 / SC-005）。

## 實作順序

依 spec 的優先序，且刻意讓最低風險者先落地：

1. **量測腳本先行**（`scripts/measure_source_uptake.py`）——FR-005c 要求窗口隨時間重算，一次性的 scratchpad 腳本不符合。此步驟同時把本 session 的分析固化為可重跑資產。
2. **Story 2（來源收起）**——純前端、零設定依賴、零誤判風險。可獨立部署取得實際使用回饋。
3. **Story 1（雜訊降級）**——需 Worker 設定與推導。上線後其達成階數記為「未量測」，待基準集產出後補記（FR-018a）。
4. **Story 3（高價值突顯）**——最後，且必須同時在零圖片舊週驗證。

## Complexity Tracking

> 無憲章違反項。以下為需要具名記錄的取捨與缺口。

| 項目 | 情況 | 處置 |
|---|---|---|
| **前端／Worker 無測試框架** | repo 現有測試皆為 pytest，JS 端零測試基礎建設。本功能主要改動在 JS | **不引入 JS 測試框架**（違反 YAGNI 且非本功能請求）。改為：推導邏輯寫成無副作用的純函式並保持極小；驗證依賴 quickstart 的手動步驟與 SC-005 的雙週次檢查。**這是誠實的測試缺口，不假裝已覆蓋** |
| **6/30 來源有數值** | 其餘 24 個樣本不足或全新 | 走 FR-006 預設非雜訊。83% 文章量已覆蓋，缺口不阻擋交付 |
| **改評級需重跑 Worker 部署** | 比 pipeline 設定重 | 已在憲章檢查中記錄。與既有 `SUPABASE_URL` 同路徑，不新增機制 |
| **SC-001／SC-002 上線時無法宣告階數** | 人工標註基準集尚不存在 | FR-018a 已明訂不阻擋交付；階數記為「未量測」，禁止以主觀印象或品質分數代填 |
