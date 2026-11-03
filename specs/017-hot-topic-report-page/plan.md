# Implementation Plan: 熱點報告與新文章拆成兩條流

**Branch**: `017-hot-topic-report-page` | **Date**: 2026-11-03 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/017-hot-topic-report-page/spec.md`

## Summary

交通頁從「一個週次頁面、上方報告、下方文章」改成兩條各自有導覽的流：熱點依產生的批次，新文章依收集週次。
窄螢幕一次一條、可切換，寬螢幕並排；兩條各自標出上次看過之後的新內容；打開時記得上次（第一次進熱點），齒輪設定可固定。
文章列拿掉 ★ 與加強樣式；焦點事件可就地展開摘要；報告的 LINE 分享改用帶批次與標題的新連結，舊連結只要不壞。
只動前端（`pages/`）；唯一的 prod 寫入是刪掉一份測試殘留的報告。

## Technical Context

**Language/Version**: 前端是原生 JavaScript（瀏覽器全域腳本 `pages/shared/app.js`，沒有建置步驟）、HTML、CSS；Python 3 只用在刪除測試殘留的一次性指令
**Primary Dependencies**: 無新增。測試沿用 `jsdom`（`package.json` 的 devDependency）與 Node 內建 `node --test`
**Storage**: 讀者裝置的 `localStorage`（`contracts/local-state.md`）；Supabase 只做一次刪除，結構不改
**Testing**: `npm test`（`tests/js/harness.mjs` 在 jsdom 裡跑出貨的 `app.js`）；版面與斷點沒有 runner，靠簽核截圖與上線後的 Playwright 截圖比對
**Target Platform**: Cloudflare Pages（交通站）；主要讀者用手機（Luke 11-03），桌機為輔
**Project Type**: 靜態前端＋既有的 Worker API（不改）
**Performance Goals**: 第一眼不因「數新文章」變慢——計數在主畫面畫完之後並行跑（research R4：每個週次請求 0.9～1.5 秒）
**Constraints**: Worker 不改（沒有測試 runner，`GNS-20261103-f71` 記錄要補）；Cloudflare 免費方案（`docs/external-services.md`）；
每次打開多出的請求數有寫明的上限（最多掃 8 週）
**Scale/Scope**: 56 份報告（刪掉測試殘留後 55）、25 個批次；文章每週約 50～180 篇

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

依 `.specify/memory/constitution.md` 2.1.1：

| 條目 | 判定 | 依據 |
|---|---|---|
| I. Pipeline Integrity | ✅ 不涉及 | 不動任何 pipeline 階段；刪一列測試殘留不是 pipeline 的執行 |
| II. Configuration over Code | ✅ 不涉及 | 不動來源、模型、憑證；並排斷點是 CSS 的版面值，不是來源或模型設定 |
| III. Idempotency & Deduplication | ✅ 不涉及 | `src/storage.py` 不動 |
| IV. Explicit Budgets | ✅ 符合 | Cloudflare 免費方案已記在 `docs/external-services.md`；每次打開多出的請求（數新文章）有寫在 `app.js` 呼叫處的上限：最多掃 8 週、每週照頁數抓 |
| V. Single Responsibility per Module | ✅ 不涉及 | `src/` 不動；`app.js` 新增的是純函式，各有測試（不是新的跨模組抽象） |
| VI. Knowledge Base Integrity | ✅ 不涉及 | FFXIV 頁照舊 |
| Technology Constraints | ✅ 符合 | 前端仍是 Cloudflare Pages 上的交通、FFXIV 兩個部署；Worker 不改 |
| Compliance review | ✅ | PR 不動 pipeline 模組，不需逐條驗 I–III；PR 內文仍寫明「不動 pipeline」 |

**設計後重新檢查（Phase 1 之後）**：結論不變。唯一新增的外部請求在 R4 有上限；資料結構與 Worker 都沒改；Complexity Tracking 不需要。

## Project Structure

### Documentation (this feature)

```text
specs/017-hot-topic-report-page/
├── plan.md              # 本檔
├── research.md          # Phase 0：R1～R11
├── data-model.md        # Phase 1：讀進來的欄位、前端推導與存的狀態
├── quickstart.md        # Phase 1：測試、簽核畫面、刪除測試殘留、驗收
├── contracts/
│   ├── traffic-streams-ui.md   # 兩條流、badge、齒輪、網址的行為
│   └── local-state.md          # localStorage 的鍵與值
├── checklists/requirements.md
└── tasks.md             # Phase 2（/speckit-tasks 產生）
```

### Source Code (repository root)

```text
pages/traffic/index.html          # 新結構：切換鈕、齒輪、兩個 stream 區塊；熱點區塊移出週次之下
pages/shared/app.js               # landingStream、批次、新內容計數、分享連結、焦點事件展開；trafficRow 拿掉 ★
pages/shared/shared.css           # 兩條流的版面與斷點、badge、齒輪面板、焦點事件展開；刪掉 .tr-strong／.tr-badge
tests/js/harness.mjs              # EXPORTED 加上新的純函式；stub 的 config 同步
tests/js/traffic-streams.test.mjs # 新：落地規則、新內容計數、批次、分享連結、焦點事件
tests/js/traffic-row.test.mjs     # 改：不論 hot_topic_analyzed 都沒有 ★／tr-strong
tests/js/row-model-css.test.mjs   # 改：排序表拿掉 tr-badge
pages/ffxiv/index.html            # 不改（FR-013 的回歸對象）
```

**Structure Decision**: 單一 repo，改動全在 `pages/` 與 `tests/js/`；`workers/`、`src/`、`scripts/` 不動。刪除測試殘留的指令放在 scratch，
指令與結果寫進 tasks 與 PR 內文，不進 repo（一次性、只刪一列）。

## Complexity Tracking

不需要：Constitution Check 沒有違反。
