# Implementation Plan: 交通頁可讀性重設計

**Branch**: `008-traffic-page-redesign` | **Date**: 2026-06-08 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/008-traffic-page-redesign/spec.md`

## Summary

把交通頁從「所有週的深度分析與新聞一路堆疊」重設計為「一次一週、可讀」：單一週導覽同時驅動深度分析與新聞列表（預設最新一週、導覽上移），深度分析改成純前端的結構卡片版面，新聞列表改成時間序＋來源色標的精簡密集列，並為深度分析加上可 deep-link 的 LINE 分享。

技術取向：**純前端**（vanilla JS + CSS + HTML），不動 pipeline、不改 Supabase schema、不新增 Gemini 用量（FR-016 僅日後生效）。週鍵對齊在前端完成，預期 Worker API 不需改動。

## Technical Context

**Language/Version**: JavaScript（vanilla，無 build step，`<script>` 直載）、HTML5、CSS3；Cloudflare Worker JS（唯讀 API，預期不改）
**Primary Dependencies**: 無前端框架；Cloudflare Pages（前端）+ Cloudflare Worker（`workers/api`）+ Supabase（經 Worker 唯讀）
**Storage**: Supabase（本功能唯讀）；**無 schema 變更、無 migration**
**Testing**: 既有 pytest 套件（Python pipeline）不受影響；前端無測試框架，依 `quickstart.md` 人工驗證
**Target Platform**: 現代瀏覽器（Cloudflare Pages 靜態站）
**Project Type**: web（靜態前端 + 輕量唯讀 API）
**Performance Goals**: 每頁僅渲染單一週（FR-003），DOM 規模遠小於現況的全週堆疊；單週數十至低百則
**Constraints**: vanilla JS、無打包器；**不得回歸 ffxiv 頁**（共用 `pages/shared/app.js`）；無新增外部呼叫（Free Tier Discipline）；API 改動最小化（目標：零）
**Scale/Scope**: 單週交通文章 + 每週 ≤3 則熱點深度分析

## Constitution Check

*GATE: 通過。本功能為前端重設計，不觸及 pipeline 階段。*

- **I. Pipeline Integrity** — N/A：不更動 Collect→Filter→Analyze→Store→Notify 任一階段。
- **II. Configuration over Code** — N/A：無來源/模型/憑證變更。
- **III. Idempotency & Deduplication** — N/A：唯讀前端，無寫入。
- **IV. Free Tier Discipline** — ✅ PASS：FR-016 採「僅日後生效」，不重生歷史報告 → **零新增 Gemini 用量**。
- **V. Single Responsibility / YAGNI** — ✅ PASS（需留意）：traffic-only 渲染維持在共用 `app.js` 內、以 `contentType` 防衛；**「traffic/ffxiv 共用層整體拆分」明確延後為 008 之後的獨立後續**，本次不做提早抽象。新增的具名渲染函式（熱點卡片、密集列）以可讀性為由，非投機抽象。
- **VI. Knowledge Base Integrity** — N/A：不涉及 FFXIV 分析。

**Complexity Tracking**: 無違規，無須填寫。

## Project Structure

### Documentation (this feature)

```text
specs/008-traffic-page-redesign/
├── plan.md              # 本檔
├── research.md          # Phase 0：關鍵決策（週鍵對齊、deep-link、渲染結構）
├── data-model.md        # Phase 1：前端資料形狀／實體
├── quickstart.md        # Phase 1：本地驗證步驟
├── contracts/
│   └── ui-and-api-contract.md   # API 依賴 + URL/deep-link + UI 契約
└── tasks.md             # /speckit-tasks 產生（非本指令）
```

### Source Code (repository root) — 本功能實際碰觸

```text
pages/
├── traffic/index.html       # 週導覽容器上移至深度分析之上；SITE_CONFIG 不變
└── shared/
    ├── app.js               # 核心改動：
    │                        #  - loadWeek() 同時驅動深度分析與新聞列表
    │                        #  - init() 預設最新一週（兩區）
    │                        #  - renderHotTopics() → 結構卡片版面 + 依週過濾 + 週鍵換算
    │                        #  - 新增密集列渲染（取代/補充 articleCard 的 traffic 分支）
    │                        #  - 載入時讀 ?week=/#topic 做 deep-link 定位
    │                        #  - 熱點卡片的 LINE 分享（建構頁面 deep-link URL）
    └── shared.css           # 分析卡片 + 密集列樣式

workers/api/src/index.js     # 預期不改（週鍵在前端對齊）；若改採後端對齊則為 fallback
```

**Structure Decision**: 沿用既有 Cloudflare Pages 靜態站結構（`pages/`），不引入打包器或框架；traffic 與 ffxiv 繼續共用 `pages/shared/app.js`，traffic-only 行為以 `C.contentType === 'traffic'` 分流。

## Phase 0 — Research

見 [research.md](./research.md)。已無 NEEDS CLARIFICATION（clarify 階段已收斂）；research 記錄四項設計決策：週鍵對齊、deep-link 方案、traffic 渲染結構、確認零後端／零 Gemini 改動。

## Phase 1 — Design & Contracts

- [data-model.md](./data-model.md)：Week、Deep-Analysis Report、News Item、Shareable Deep-Link 的前端資料形狀與可用欄位（含 traffic 無重要度/標籤/LLM 摘要的事實）。
- [contracts/ui-and-api-contract.md](./contracts/ui-and-api-contract.md)：本功能依賴的 API 端點、URL/deep-link 契約、各區塊的 UI 行為契約。
- [quickstart.md](./quickstart.md)：本地起站與逐項驗證 FR 的步驟。
- Agent context：更新 `CLAUDE.md` 的 SPECKIT 區塊指向本 plan。

## Phase 2 — 後續

`/speckit-tasks` 依本 plan 與設計產物產生 `tasks.md`（依使用者故事 P1→P4 切片、可獨立交付）。
